#!/usr/bin/env python3
"""
editor_gravados.fala_com_cenas — "Editar vídeo por cena" da Fala com cenas (modelo dividido-mascara, qualquer variante).

O vídeo é o João em tela cheia com legenda e, a cada 6 a 10 s, um beat: cena de apoio na faixa de baixo (broll), frase na tela (card),
zoom no rosto (punch) ou uma peça pronta (`card:s-e:@arquivo.mp4`, ex.: impacto). Os beats moram no `--beats` do gerar.sh, dentro do
comando.sh. A "cena" do editor é um trecho da fala: cada beat vira uma cena e o que sobra entre eles vira uma cena "fala" (o João
sozinho). Mudar uma cena regrava o `--beats` (o resto do comando, a música, o enquadramento e a legenda não mudam).

    python3 fala_com_cenas.py refazer <sandbox>    # corta o que faltar (limpa-broll.py) e roda o gerar.sh (o editor chama)

Cena de apoio nova: o corte sai do clipe escolhido (brolls/cuts/ed-<hash>.mp4, pelo limpa-broll.py da variante quando ela tem, senão o
próprio gerar.sh corta `arquivo@segundo`). Só se refaz o que mudou; o mapa corte → clipe de origem fica numa linha de comentário no
fim do comando.sh (`# editor-cortes: {...}`), pra o editor mostrar sempre o clipe e o ponto de origem.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import RAIZ, com_venv, rodar_com_limite  # noqa: E402

SLUG = "fala-com-cenas"
MARCA_CORTES = "# editor-cortes:"
TIPOS = {"fala": "Você falando", "gancho": "Gancho de abertura", "broll": "Cena de apoio embaixo", "card": "Frase na tela", "punch": "Zoom no rosto",
         "peca": "Frase na tela (peça pronta)"}
ROTULOS = {"tipo": "Tela", "clipe": "Cena de apoio", "inicio": "Ponto do clipe", "texto": "Frase na tela", "peca": "Peça pronta (card ou impacto)"}
BAND_H_PADRAO = 640


# ───────────────────────── comando.sh ─────────────────────────

def _duracao(f: Path) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                                              str(f)], text=True, timeout=30))
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def saida(p: Path) -> Path:
    return p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(RAIZ))
    except ValueError:
        return str(p)


def _abs(p: Path, c: str) -> Path:
    return Path(c) if str(c).startswith("/") else p / c


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


def _valor(toks: list[str], flag: str) -> str | None:
    for i, t in enumerate(toks):
        if t == flag and i + 1 < len(toks):
            return toks[i + 1]
    return None


def _tok_set(toks: list[str], flag: str, valor) -> None:
    for i, t in enumerate(toks):
        if t == flag:
            del toks[i:i + 2]
            break
    if valor is not None:
        toks += [flag, str(valor)]


def _cortes(linhas: list[str]) -> dict:
    for l in linhas:
        if l.startswith(MARCA_CORTES):
            try:
                return json.loads(l[len(MARCA_CORTES):])
            except ValueError:
                return {}
    return {}


# ───────────────────────── beats ⇄ cenas ─────────────────────────

def _fmt(x: float) -> str:
    return f"{float(x):.2f}".rstrip("0").rstrip(".") or "0"


def parse_beats(txt: str) -> tuple[list[dict], list[str]]:
    """'broll:4-8:arq@2;card:11-14:TEXTO;punch:16-20' → ([{tipo, s, e, arg}], [beats que o editor não entende ou que se sobrepõem])."""
    ok, extras = [], []
    for b in (txt or "").split(";"):
        b = b.strip()
        if not b:
            continue
        m = re.match(r"^(\w+):([\d.]+)-([\d.]+)(?::(.*))?$", b, re.S)
        if not m or m.group(1) not in ("broll", "card", "punch"):
            extras.append(b)
            continue
        ok.append({"tipo": m.group(1), "s": float(m.group(2)), "e": float(m.group(3)), "arg": m.group(4) or ""})
    ok.sort(key=lambda b: b["s"])
    limpos, fim = [], 0.0
    for b in ok:
        if b["s"] < fim - 0.01 or b["e"] <= b["s"]:   # sobreposto: fica como está, fora da lista
            extras.append(f"{b['tipo']}:{_fmt(b['s'])}-{_fmt(b['e'])}" + (f":{b['arg']}" if b["arg"] else ""))
            continue
        limpos.append(b)
        fim = b["e"]
    return limpos, extras


def _origem(arg: str, mapa: dict) -> tuple[str, float]:
    """O clipe e o ponto de um beat broll ('arquivo@segundo'); se o arquivo é um corte que o editor fez, o clipe de origem dele."""
    arq, _, ini = arg.rpartition("@") if re.search(r"@[\d.]+$", arg) else (arg, "", "0")
    orig = mapa.get(arq)
    return (orig["clipe"], float(orig["inicio"])) if orig else (arq, float(ini or 0))


def ler(p: Path) -> dict:
    """comando.sh (--beats) → lista de cenas. Cada beat é uma cena; o que sobra entre eles (e antes/depois) é o João falando."""
    linhas, _, _, toks = _comando(p)
    dur = _duracao(p / "work" / "joao.mp4")
    bs, _ = parse_beats(_valor(toks, "--beats") or "")
    mapa = _cortes(linhas)
    cs, t = [], 0.0
    for b in bs:
        if b["s"] - t > 0.05:
            cs.append({"de": round(t, 3), "tipo": "fala"})
        c = {"de": round(b["s"], 3), "tipo": b["tipo"]}
        if b["tipo"] == "broll":
            c["clipe"], c["inicio"] = _origem(b["arg"], mapa)
        elif b["tipo"] == "card":
            if b["arg"].startswith("@"):
                c["tipo"], c["peca"] = "peca", b["arg"][1:]
            else:
                c["texto"] = b["arg"]
        cs.append(c)
        t = b["e"]
    if dur - t > 0.05 or not cs:
        cs.append({"de": round(min(t, dur), 3), "tipo": "fala"})
    if cs[0]["de"] > 0:
        cs.insert(0, {"de": 0.0, "tipo": "fala"})
    g = _gancho(toks)   # os beats e a fala são do CORPO; no vídeo final o gancho vem antes: cena 1 própria e o resto desloca
    doc = {"titulo": p.name.removeprefix("_sandbox-").replace("-", " ").capitalize(), "duracao": round(dur + g, 3), "saida": str(saida(p))}
    if (p / "work" / "words.json").is_file():
        doc["palavras"] = "work/words.json"
        if g:
            from _comum import gravar_json, ler_json
            d = json.loads((p / "work" / "words.json").read_text(encoding="utf-8"))
            pal = [dict(w, start=round(float(w["start"]) + g, 3), end=round(float(w.get("end", w["start"])) + g, 3))
                   for w in (d.get("words", d) if isinstance(d, dict) else d) if isinstance(w, dict) and "start" in w]
            (p / "editor").mkdir(parents=True, exist_ok=True)
            if ler_json(p / "editor" / "palavras.json", None) != pal:
                gravar_json(p / "editor" / "palavras.json", pal)
            doc["palavras"] = "editor/palavras.json"
    if g:
        cs = [{"de": 0.0, "tipo": "gancho"}] + [dict(c, de=round(c["de"] + g, 3)) for c in cs]
    doc["cenas"] = cs
    return doc


def _gancho(toks: list[str]) -> float:
    """Duração do gancho de abertura (--gancho / --gancho-dur, padrão 2,5 s) que o gerar.sh põe ANTES do corpo; 0 sem gancho."""
    if not _valor(toks, "--gancho"):
        return 0.0
    try:
        return float(_valor(toks, "--gancho-dur") or 2.5)
    except ValueError:
        return 2.5


def _band_h(toks: list[str]) -> int:
    try:
        return int(float(_valor(toks, "--band-h") or BAND_H_PADRAO))
    except ValueError:
        return BAND_H_PADRAO


def _corte_de(p: Path, clipe: str, inicio: float, dur: float, band_h: int) -> str:
    """Nome (relativo) do corte desta cena: o mesmo clipe, ponto, duração e altura sempre dão o mesmo arquivo."""
    h = hashlib.sha1(f"{clipe}|{inicio:.2f}|{dur:.2f}|{band_h}".encode()).hexdigest()[:10]
    return f"brolls/cuts/ed-{h}.mp4"


def gravar(p: Path, doc: dict) -> None:
    """Lista de cenas → o --beats do comando.sh. O resto da linha (música, enquadramento, legenda) e os beats que o editor não entende ficam."""
    linhas, i, pre, toks = _comando(p)
    atuais, extras = parse_beats(_valor(toks, "--beats") or "")
    mapa_velho = _cortes(linhas)
    por_de = {round(b["s"], 2): b["arg"] for b in atuais if b["tipo"] == "broll"}   # o arg de cada broll de agora
    tem_limpa = (p.parent / "limpa-broll.py").is_file()
    bh = _band_h(toks)
    g = _gancho(toks)
    dur = float(doc.get("duracao") or (_duracao(p / "work" / "joao.mp4") + g)) - g
    cs = [dict(c, de=round(float(c["de"]) - g, 3)) for c in doc.get("cenas") or [] if isinstance(c, dict) and c.get("tipo") != "gancho"]
    beats, mapa = [], {}
    for k, c in enumerate(cs):
        s = float(c["de"])
        e = float(cs[k + 1]["de"]) if k + 1 < len(cs) else dur
        if e - s < 0.1:
            continue
        tipo = c.get("tipo")
        if tipo == "punch":
            beats.append(f"punch:{_fmt(s)}-{_fmt(e)}")
        elif tipo == "card" and str(c.get("texto") or "").strip():
            beats.append(f"card:{_fmt(s)}-{_fmt(e)}:{str(c['texto']).strip()}")
        elif tipo == "peca" and c.get("peca"):
            beats.append(f"card:{_fmt(s)}-{_fmt(e)}:@{c['peca']}")
        elif tipo == "broll" and c.get("clipe"):
            clipe, ini = str(c["clipe"]), float(c.get("inicio") or 0)
            igual = round(s, 2) in por_de and _origem(por_de[round(s, 2)], mapa_velho) == (clipe, ini)
            if igual:   # a cena não mudou: o arg fica como estava (nenhum corte novo)
                beats.append(f"broll:{_fmt(s)}-{_fmt(e)}:{por_de[round(s, 2)]}")
            elif tem_limpa and "brolls/cuts/" not in clipe:
                nome = _corte_de(p, clipe, ini, e - s, bh)
                mapa[nome] = {"clipe": clipe, "inicio": ini, "dur": round(e - s, 2), "h": bh}
                beats.append(f"broll:{_fmt(s)}-{_fmt(e)}:{nome}@0")
            else:
                beats.append(f"broll:{_fmt(s)}-{_fmt(e)}:{clipe}@{_fmt(ini)}")
    for nome, v in mapa_velho.items():   # corte que a edição de antes fez e esta não usa mais fica no mapa (o arquivo nunca é apagado)
        mapa.setdefault(nome, v)
    _tok_set(toks, "--beats", ";".join(beats + extras))
    cmd = (pre or f"cd {_rel(p)} && zsh ../") + "gerar.sh " + " ".join(shlex.quote(t) for t in toks)
    if i is None:
        linhas.append(cmd)
    else:
        linhas[i] = cmd
    linhas = [l for l in linhas if not l.startswith(MARCA_CORTES)]
    if mapa:
        linhas.append(MARCA_CORTES + " " + json.dumps(mapa, ensure_ascii=False, sort_keys=True))
    (p / "comando.sh").write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ───────────────────────── refazer ─────────────────────────

def _fazer_cortes(p: Path) -> None:
    """Cria só os cortes que o comando.sh pede e ainda não existem (limpa-broll.py da variante: tira tarja e centraliza)."""
    linhas, _, _, toks = _comando(p)
    limpa = p.parent / "limpa-broll.py"
    usados = (_valor(toks, "--beats") or "")
    for nome, v in _cortes(linhas).items():
        if nome not in usados or (p / nome).is_file():
            continue
        origem = _abs(p, v["clipe"])
        if not origem.is_file():
            raise SystemExit(f"Não achei o clipe {v['clipe']}")
        (p / nome).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(limpa), "--src", str(origem), "--ss", str(v["inicio"]), "--dur", str(v["dur"]),
                            "--out", str(p / nome), "--h", str(v.get("h") or BAND_H_PADRAO)], capture_output=True, text=True, cwd=p)
        if r.returncode or not (p / nome).is_file():
            raise SystemExit(f"limpa-broll falhou em {nome}: {(r.stderr or r.stdout)[-300:]}")


def refazer(p: Path) -> int:
    """Corta o que faltar e roda o gerar.sh do modelo com o comando.sh de agora; o vídeo sai em saida(p). 0 = ok."""
    p = Path(p).resolve()
    gerar = p.parent / "gerar.sh"
    _, _, _, toks = _comando(p)
    if not gerar.is_file() or not toks:
        print("Não achei o gerar.sh do modelo ou o comando.sh.")
        return 1
    _fazer_cortes(p)
    destino = saida(p)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tem_out = "--out)" in gerar.read_text(encoding="utf-8", errors="ignore")
    toks = list(toks)
    if tem_out:
        _tok_set(toks, "--out", str(destino))
    pasta_saida = p.parents[2] / "output" / "dividido-mascara"   # onde o gerar.sh sem --out grava (<ts>.mp4)
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
    return [sys.executable, str(Path(__file__).resolve()), "refazer", str(p)], p


def cmd_txt(p: Path) -> str:
    return f"python3 {Path(__file__).resolve()} refazer {p}"


def achar(p: Path) -> bool:
    return all((p / f).is_file() for f in ("comando.sh", "work/joao.mp4")) and "--beats" in (p / "comando.sh").read_text(encoding="utf-8", errors="ignore")


SPEC = {
    "gravado": True, "fonte": "comando.sh", "ler": ler, "gravar": gravar,
    "arquivos": ["comando.sh"], "precisa": ["comando.sh", "work/joao.mp4"],
    "achar": achar, "cmd": cmd, "cmd_txt": cmd_txt, "saida": saida, "timeout": 3600,
    "rotulos": ROTULOS, "tipos": TIPOS, "tipo_padrao": "fala",
    "juntos": {"tipo": ["clipe", "inicio", "texto", "peca"], "clipe": ["inicio", "tipo"], "texto": ["tipo"]}, "sempre": ("tipo", "clipe", "texto"), "globais": {},
    "sugestoes": ["Troca a cena de apoio por uma que case mais com a fala", "Troca a frase da tela por uma mais forte",
                  "Põe um zoom no rosto nesse trecho", "Volta pro João sozinho nesse trecho"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "gerar.sh e o comando.sh",
    "motivo_narracao": "Neste formato a voz é o João gravado: a fala só muda trocando o bruto (a câmera cortada).",
    "onde": ("O vídeo é o João gravado (work/joao.mp4) em tela cheia com legenda, e a cada 6 a 10 s um beat (cena de apoio na faixa de baixo, "
             "frase na tela ou zoom no rosto), montado pelo gerar.sh do modelo a partir do comando.sh. Você NÃO mexe no comando.sh: edite só a "
             "lista de cenas (cada cena é um trecho da fala, com \"de\" = segundo em que começa; ela termina onde a próxima começa)."),
    "conferir": ("Pra conferir uma cena de apoio nova, tire um quadro do clipe com ffmpeg (-ss <inicio> -i <clipe> -frames:v 1) e OLHE a imagem: "
                 "sem marca d'água, tarja preta nem legenda queimada. O vídeo todo é feito pelo Estúdio depois."),
    "dicas": ("Cada cena é um trecho da fala. \"tipo\": \"fala\" (só o João), \"broll\" (cena de apoio na faixa de baixo), \"card\" (frase na tela) ou "
              "\"punch\" (zoom no rosto); \"peca\" é uma peça pronta (card/impacto) e não se mexe. \"broll\": \"clipe\" é o caminho de um vídeo mudo "
              "(do acervo, {raiz}/acervo/itens/*/clip.mp4, ou achado com a skill get-brolls: real e do assunto, nunca banco de imagem posando) e "
              "\"inicio\" o segundo do clipe onde a cena começa (o clipe precisa ter a duração da cena a partir dele; sem marca d'água nem tarja). "
              "\"card\": \"texto\" é a frase literal da fala, com *palavra* entre asteriscos pro destaque. Pra pôr uma cena de apoio ou uma frase "
              "numa cena \"fala\", troque o \"tipo\" e preencha o campo. Não mude o \"de\" nem o número de cenas; a cena \"gancho\" (a 1ª, quando existe) é o vídeo de abertura e não se mexe."),
}
SPECS = {SLUG: SPEC}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "refazer":
        sys.exit(refazer(Path(sys.argv[2])))
    print(__doc__)
    sys.exit(2)
