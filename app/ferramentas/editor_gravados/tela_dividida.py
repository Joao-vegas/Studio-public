#!/usr/bin/env python3
"""
editor_gravados.tela_dividida — "Editar vídeo por cena" da Tela dividida (modelo reel-dividido-por-video).

O vídeo é o João em cima, a faixa com a manchete no meio e, embaixo, cenas mudas que o `gerar.sh` do modelo corta de UM arquivo
(`work/master.mp4`: as cenas escolhidas, cortadas e juntas na ordem da fala, do tamanho dela). A "cena" do editor é um momento da
fala com a cena de baixo dele: {de, clipe, inicio}. A lista fica no PLANO.json (`cenas_baixo`, com os parâmetros em `render`) e o
comando.sh é regravado com a manchete, o --takes e a calibração.

    python3 tela_dividida.py refazer <sandbox>     # refaz o master.mp4 pela lista e roda o gerar.sh (o editor chama)

Master e gerar.sh são determinísticos: mesma lista → mesmo vídeo. Cena sem clipe conhecido (o PLANO não diz qual clipe o master usou)
aponta pro próprio master original, congelado em work/master-base.mp4 na 1ª refeita (nada se perde).
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import RAIZ, clonar, com_venv, gravar_json, ler_json, rodar_com_limite  # noqa: E402

SLUG = "tela-dividida"
FPS = 30
BANDA_H = 270                      # a faixa vermelha do meio (gerar.sh)
ROTULOS = {"clipe": "Cena de baixo", "inicio": "Ponto do clipe", "manchete": "Manchete da faixa",
           "cta": "CTA da faixa", "enquadramento": "Enquadramento do João"}
ENQUADRAMENTO = ("joao_h", "video_offset_y", "video_zoom", "video_offset_x", "rosto_fixo")
GLOBAIS = {"manchete": ["manchete"], "cta": ["cta", "cta_t"], "enquadramento": list(ENQUADRAMENTO)}
FLAGS = {"joao_h": "--joao-h", "video_offset_y": "--video-offset-y", "video_zoom": "--video-zoom", "video_offset_x": "--video-offset-x",
         "step": "--step", "cta": "--cta", "cta_t": "--cta-t", "manchete": "--titulo"}
BOOLS = {"rosto_fixo": "--rosto-fixo", "invertido": "--invertido"}
IMAGEM = (".png", ".jpg", ".jpeg", ".webp")


# ───────────────────────── arquivos do vídeo ─────────────────────────

def _duracao(f: Path) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                                              str(f)], text=True, timeout=30))
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def saida(p: Path) -> Path:
    """Onde o vídeo final fica: <x>Content/output/<modelo>/<slug>.mp4."""
    return p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(RAIZ))
    except ValueError:
        return str(p)


def _abs(p: Path, c: str) -> Path:
    return Path(c) if str(c).startswith("/") else p / c


# ───────────────────────── comando.sh ─────────────────────────

def _comando(p: Path) -> tuple[list[str], int | None, str, list[str]]:
    """(linhas do comando.sh, índice da linha do gerar.sh, o que vem antes de 'gerar.sh', argumentos)."""
    f = p / "comando.sh"
    txt = f.read_text(encoding="utf-8").replace("\\\n", " ") if f.is_file() else ""
    linhas = txt.splitlines()
    i = next((k for k in range(len(linhas) - 1, -1, -1) if "gerar.sh" in linhas[k] and not linhas[k].lstrip().startswith("#")), None)
    if i is None:
        return linhas, None, "", []
    pre, _, resto = linhas[i].partition("gerar.sh")
    try:
        toks = shlex.split(resto)
    except ValueError:
        toks = resto.split()
    return linhas, i, pre, toks


def _args(toks: list[str]) -> dict:
    d, i = {}, 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("--"):
            if t in BOOLS.values() or i + 1 >= len(toks) or toks[i + 1].startswith("--"):
                d[t], i = True, i + 1
            else:
                d[t], i = toks[i + 1], i + 2
        else:
            i += 1
    return d


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return v


def _tok_set(toks: list[str], flag: str, valor) -> None:
    """Põe/troca `flag valor` nos argumentos (valor None ou False tira; True é flag sem valor)."""
    for i, t in enumerate(toks):
        if t == flag:
            fim = i + 1 if (i + 1 >= len(toks) or toks[i + 1].startswith("--") or flag in BOOLS.values()) else i + 2
            del toks[i:fim]
            break
    if valor is None or valor is False:
        return
    toks += [flag] if valor is True else [flag, str(valor)]


def _render(p: Path, plano: dict) -> dict:
    """Os parâmetros do render: o `render` do PLANO.json (depois da 1ª edição) ou o que o comando.sh da produção usou."""
    if plano.get("render"):
        return dict(plano["render"])
    a = _args(_comando(p)[3])
    ren = {"manchete": a.get("--titulo") or plano.get("manchete") or "", "step": _num(a.get("--step", 2.0))}
    for k, fl in FLAGS.items():
        if k not in ren and a.get(fl) not in (None, True):
            ren[k] = _num(a[fl])
    for k, fl in BOOLS.items():
        if a.get(fl):
            ren[k] = True
    return ren


# ───────────────────────── PLANO.json ⇄ lista de cenas ─────────────────────────

def _clipe_do_beat(p: Path, b: dict) -> tuple[str, float]:
    """O clipe que o beat usou (a opção escolhida, o clipe do beat ou brolls/escolhidos/<id>.mp4) e o ponto dele onde a cena começa."""
    esc = next((o for o in b.get("opcoes") or [] if isinstance(o, dict) and o.get("id") == b.get("escolha")), {}) or {}
    ini = 0.0
    try:
        ini = float(str(esc.get("trecho", "0")).split("-")[0])
    except ValueError:
        pass
    for c in (esc.get("arquivo"), b.get("clipe"), b.get("arquivo"), f"brolls/escolhidos/{b.get('id')}.mp4", f"brolls/cuts/{b.get('id')}.mp4"):
        if c and _abs(p, c).is_file():
            return str(c), float(b.get("inicio_no_clipe", ini) or 0)
    return "", 0.0


def _master_base(p: Path) -> str:
    return "work/master-base.mp4" if (p / "work" / "master-base.mp4").is_file() else "work/master.mp4"


def _cenas_dos_beats(p: Path, plano: dict, dur: float) -> list[dict]:
    """Os beats broll do PLANO viram momentos que cobrem o vídeo todo (embaixo nunca fica parado): o 1º começa em 0 e cada um vai até o seguinte."""
    bs = sorted((b for b in plano.get("beats") or [] if isinstance(b, dict) and b.get("tipo") in ("broll", "citacao")
                 and isinstance(b.get("inicio"), (int, float))), key=lambda b: b["inicio"])
    cs = []
    for b in bs:
        clipe, ini = _clipe_do_beat(p, b)
        de = round(float(b["inicio"]), 3)
        if clipe:
            cs.append({"de": de, "clipe": clipe, "inicio": ini})
        else:   # o PLANO não diz qual clipe o master usou aqui: a cena aponta pro trecho dele mesmo
            cs.append({"de": de, "clipe": _master_base(p), "inicio": de})
    if not cs:
        cs = [{"de": 0.0, "clipe": _master_base(p), "inicio": 0.0}]
    de0 = cs[0]["de"]
    cs[0]["de"] = 0.0
    cs[0]["inicio"] = 0.0 if cs[0]["clipe"].startswith("work/master") else max(0.0, cs[0]["inicio"] - de0)   # o clipe anda junto com o começo
    return cs


def ler(p: Path) -> dict:
    """PLANO.json (+ comando.sh) → lista de cenas. Cada cena é um momento da fala; termina onde a seguinte começa."""
    plano = ler_json(p / "PLANO.json", {}) or {}
    ren = _render(p, plano)
    dur = _duracao(p / "work" / "joao.mp4")
    cs = [dict(de=float(c["de"]), clipe=c["clipe"], inicio=c.get("inicio", 0)) for c in plano.get("cenas_baixo") or []] \
        or _cenas_dos_beats(p, plano, dur)
    doc = {"titulo": str(ren.get("manchete") or p.name).capitalize(), "duracao": dur, "saida": str(saida(p)), "manchete": ren.get("manchete", "")}
    if (p / "work" / "words.json").is_file():
        doc["palavras"] = "work/words.json"
    for k in ("cta", "cta_t", *ENQUADRAMENTO):
        if ren.get(k) not in (None, ""):
            doc[k] = ren[k]
    doc["cenas"] = cs
    return doc


def gravar(p: Path, doc: dict) -> None:
    """Lista de cenas → PLANO.json (`cenas_baixo` + `render`) e comando.sh. O resto do PLANO fica como estava."""
    f = p / "PLANO.json"
    plano = ler_json(f, {}) or {}
    ren = _render(p, plano)
    for k in ("manchete", "cta", "cta_t", *ENQUADRAMENTO):
        if doc.get(k) not in (None, ""):
            ren[k] = doc[k]
        else:
            ren.pop(k, None)
    dur = float(doc.get("duracao") or _duracao(p / "work" / "joao.mp4"))
    cs = []
    for c in doc.get("cenas") or []:
        if not isinstance(c, dict) or not c.get("clipe"):
            continue
        cs.append({"de": float(c["de"]), "clipe": str(c["clipe"]), "inicio": float(c.get("inicio") or 0)})
    plano["cenas_baixo"] = cs
    plano["manchete"] = ren.get("manchete", "")
    plano["render"] = ren
    f.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    _gravar_comando(p, ren, dur)


def _takes(dur: float, step: float) -> str:
    """Um corte a cada `step` s até o fim (como o gerar.sh conta): a cena de baixo anda junto com a fala."""
    n = int(dur / step)
    if dur - n * step > 0.1:
        n += 1
    return ",".join(f"{i * step:g}" for i in range(n))


def _tokens(p: Path, ren: dict, dur: float) -> list[str]:
    toks = list(_comando(p)[3]) or ["--dir", "."]
    step = float(ren.get("step") or 2.0)
    for k in ("manchete", "step", "cta", "cta_t", "joao_h", "video_offset_y", "video_zoom", "video_offset_x"):
        _tok_set(toks, FLAGS[k], ren.get(k) if k != "step" else f"{step:g}")
    for k, fl in BOOLS.items():
        _tok_set(toks, fl, True if ren.get(k) else None)
    _tok_set(toks, "--srcs", "work/master.mp4")
    _tok_set(toks, "--takes", _takes(dur, step))
    return toks


def _gravar_comando(p: Path, ren: dict, dur: float) -> None:
    """comando.sh com a manchete, o --takes e a calibração de agora (o resto da linha e os comentários ficam)."""
    linhas, i, pre, _ = _comando(p)
    toks = _tokens(p, ren, dur)
    cmd = (pre or f"cd {_rel(p)} && zsh ../") + "gerar.sh " + " ".join(shlex.quote(t) for t in toks)
    if i is None:
        linhas.append(cmd)
    else:
        linhas[i] = cmd
    (p / "comando.sh").write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ───────────────────────── refazer: master.mp4 + gerar.sh ─────────────────────────

def _congelar_master(p: Path) -> None:
    """O master que a produção fez vira work/master-base.mp4 (uma vez): cena sem clipe conhecido continua usando ele."""
    m, b = p / "work" / "master.mp4", p / "work" / "master-base.mp4"
    if m.is_file() and not b.is_file():
        clonar(m, b)


def _altura_baixo(ren: dict) -> int:
    jh = int(ren.get("joao_h") or 816)
    return jh if ren.get("invertido") else 1920 - jh - BANDA_H


def montar_master(p: Path, doc: dict, ren: dict) -> Path:
    """work/master.mp4 = os clipes das cenas na ordem da fala, cada um cortado (cover) no tamanho do bloco de baixo, mudo, 30 fps,
    sem acumular erro: cada cena ocupa exatamente os quadros entre o instante dela e o da seguinte."""
    cs = doc["cenas"]
    dur = float(doc["duracao"])
    bh = _altura_baixo(ren)
    _congelar_master(p)
    tmp = Path(tempfile.mkdtemp(prefix=".master-", dir=p / "work"))
    try:
        lista = []
        for i, c in enumerate(cs):
            ate = float(cs[i + 1]["de"]) if i + 1 < len(cs) else dur
            n = max(1, round(ate * FPS) - round(float(c["de"]) * FPS))
            seg = n / FPS
            clipe = _abs(p, c["clipe"])
            if str(c["clipe"]) == "work/master.mp4":
                clipe = _abs(p, _master_base(p))
            if not clipe.is_file():
                raise SystemExit(f"Não achei o clipe da cena {i + 1}: {c['clipe']}")
            ini = float(c.get("inicio") or 0)
            out = tmp / f"s{i:03d}.mp4"
            fin = "format=yuv420p,fps=30,setsar=1"
            if clipe.suffix.lower() in IMAGEM:   # imagem/tela → rolagem vertical suave (como o gerar.sh)
                cmd = ["-loop", "1", "-t", f"{seg:.3f}", "-i", str(clipe), "-vf",
                       f"scale=1080:-1:flags=bicubic,pad=1080:max(ih\\,{bh}):0:0:black,"
                       f"crop=1080:{bh}:0:'min((ih-{bh})*t/{seg:.3f}\\,ih-{bh})',{fin}"]
            else:
                dc = _duracao(clipe)
                if dc and ini + seg > dc:   # clipe curto: começa mais cedo; menor que a cena, repete
                    ini = max(0.0, dc - seg)
                rep = ["-stream_loop", "-1"] if dc and dc < seg else []
                cmd = [*rep, "-ss", f"{ini:.3f}", "-i", str(clipe), "-vf",
                       f"scale=1080:{bh}:force_original_aspect_ratio=increase,crop=1080:{bh},{fin}"]
            r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *cmd, "-an", "-r", str(FPS), "-frames:v", str(n),
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)], capture_output=True, text=True)
            if r.returncode or not out.is_file():
                raise SystemExit(f"ffmpeg falhou na cena {i + 1}: {(r.stderr or '')[-300:]}")
            lista.append(f"file '{out}'")
        (tmp / "lista.txt").write_text("\n".join(lista) + "\n", encoding="utf-8")
        novo = tmp / "master.mp4"
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "lista.txt"),
                            "-c", "copy", "-an", str(novo)], capture_output=True, text=True)
        if r.returncode or not novo.is_file():
            raise SystemExit(f"ffmpeg falhou ao juntar as cenas: {(r.stderr or '')[-300:]}")
        destino = p / "work" / "master.mp4"
        os.replace(novo, destino)
        return destino
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # só a pasta temporária deste render


def refazer(p: Path) -> int:
    """Refaz o master pela lista de cenas e roda o gerar.sh do modelo; o vídeo sai em saida(p). 0 = ok."""
    p = Path(p).resolve()
    doc = ler(p)
    plano = ler_json(p / "PLANO.json", {}) or {}
    ren = _render(p, plano)
    gerar = p.parent / "gerar.sh"
    if not gerar.is_file():
        print(f"Não achei o gerar.sh do modelo em {gerar}")
        return 1
    montar_master(p, doc, ren)
    toks = _tokens(p, ren, float(doc["duracao"]))
    destino = saida(p)
    destino.parent.mkdir(parents=True, exist_ok=True)
    sh = gerar.read_text(encoding="utf-8", errors="ignore")
    tem_out = "--out)" in sh
    if tem_out:
        _tok_set(toks, "--out", str(destino))
    pasta_saida = p.parents[2] / "output" / "reel-dividido-por-video"   # onde o gerar.sh sem --out grava (<ts>.mp4)
    antes = {q: q.stat().st_mtime for q in pasta_saida.glob("*.mp4")} if pasta_saida.is_dir() else {}
    t0 = time.time()
    r = rodar_com_limite(["zsh", str(gerar), *toks], 3600, cwd=p, env=com_venv(), capture_output=True, text=True)
    if r.returncode:
        print((r.stderr or r.stdout)[-600:])
        return r.returncode
    if not tem_out:
        novos = [q for q in pasta_saida.glob("*.mp4") if q.stat().st_mtime >= t0 - 1 and antes.get(q) != q.stat().st_mtime]
        if not novos:
            print("O gerar.sh terminou mas não achei o vídeo novo em", pasta_saida)
            return 1
        os.replace(max(novos, key=lambda q: q.stat().st_mtime), destino)
    print("ok", destino)
    return 0


def cmd(p: Path) -> tuple[list[str], Path]:
    """O comando que refaz o vídeo inteiro (rode com cwd=p)."""
    return [sys.executable, str(Path(__file__).resolve()), "refazer", str(p)], p


def cmd_txt(p: Path) -> str:
    return f"python3 {Path(__file__).resolve()} refazer {p}"


def achar(p: Path) -> bool:
    """Esta pasta é um vídeo da Tela dividida que o editor entende (PLANO.json, comando.sh e o bruto)."""
    return all((p / f).is_file() for f in ("PLANO.json", "comando.sh", "work/joao.mp4"))


SPEC = {
    "gravado": True, "fonte": "PLANO.json", "ler": ler, "gravar": gravar,
    "arquivos": ["PLANO.json", "comando.sh"], "precisa": ["PLANO.json", "comando.sh", "work/joao.mp4"],
    "achar": achar, "cmd": cmd, "cmd_txt": cmd_txt, "saida": saida, "timeout": 3600,
    "rotulos": ROTULOS, "tipos": {"baixo": "Cena de baixo"}, "tipo_padrao": "baixo",
    "juntos": {"clipe": ["inicio"]}, "sempre": ("clipe",), "globais": GLOBAIS,
    "sugestoes": ["Troca a cena de baixo desse momento por uma que case mais com a fala", "Troca a manchete da faixa",
                  "Põe uma cena de baixo mais parada neste trecho", "Desce a faixa: ela está encostando no queixo"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "gerar.sh, o master.mp4 e o comando.sh",
    "motivo_narracao": "Neste formato a voz é o João gravado: a fala só muda trocando o bruto (a câmera cortada).",
    "onde": ("O vídeo é o João gravado (work/joao.mp4) em cima, a faixa vermelha com a manchete no meio e, embaixo, cenas mudas montadas "
             "no work/master.mp4 pelo gerar.sh do modelo. Você NÃO mexe no PLANO.json, no comando.sh nem no master: edite só a lista de cenas "
             "(cada cena é um momento da fala, com \"de\" = segundo em que começa; ela termina onde a próxima começa; a cena de baixo nunca fica sem clipe)."),
    "conferir": ("Pra conferir uma cena nova, tire um quadro do clipe com ffmpeg (-ss <inicio> -i <clipe> -frames:v 1) e OLHE a imagem: sem marca d'água, "
                 "letterbox, legenda queimada nem rosto falando (compete com o João de cima). O vídeo todo é feito pelo Estúdio depois."),
    "dicas": ("Cada cena é um momento da fala; \"clipe\" é o caminho de um vídeo mudo (do acervo, {raiz}/acervo/itens/*/clip.mp4, ou achado com a skill "
              "get-brolls: real e do assunto, nunca banco de imagem posando) ou de uma imagem (vira rolagem), e \"inicio\" é o segundo do clipe onde a cena "
              "começa (a cena dura até a próxima: o clipe precisa ter esse tempo). \"manchete\" (no topo) é a faixa vermelha: caixa-alta, frase seca de "
              "até ~35 letras, que complementa a 1ª frase sem repeti-la. \"cta\" + \"cta_t\" (segundos) trocam a faixa por um CTA. Enquadramento "
              "(no topo): \"joao_h\" (altura do bloco do João, 816 a 1200; maior = faixa desce), \"video_offset_y\" (menor = rosto desce), "
              "\"video_zoom\", \"video_offset_x\", \"rosto_fixo\" (true desliga o seguir o rosto). Só mexa nisso se o pedido for de enquadramento."),
}
SPECS = {SLUG: SPEC}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "refazer":
        sys.exit(refazer(Path(sys.argv[2])))
    print(__doc__)
    sys.exit(2)
