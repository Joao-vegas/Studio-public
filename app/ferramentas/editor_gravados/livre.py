"""Modo livre: vale pra todo vídeo gravado que tem pasta de trabalho, vídeo pronto e um COMANDO que refaz o vídeo (comando.sh,
RESULTADO.json → comando, montar.sh ou montar.py), mas que nenhum spec estruturado entende (vídeo montado à mão).

Não há elementos: o alcance é a cena, um trecho de cenas ou o vídeo todo. A IA edita os arquivos da pasta que precisar (o script, o plano,
mídia nova). O Estúdio guarda tudo antes, roda o comando depois e confere o vídeo novo contra o antigo:
  - a duração tem de ser a mesma (±0,15 s);
  - fora da cena marcada (com folga de 0,3 s), 2 quadros por segundo, pequenos e em cinza, têm de ficar iguais em 95% deles;
  - no alcance "vídeo todo" só vale a duração e o vídeo abrir;
  - a voz (work/joao.mp4) nunca muda.
Vazou ou falhou: volta todos os arquivos de texto, a voz e o vídeo, e avisa. Nada é apagado.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from _comum import RAIZ, clonar, ler_json

from . import _base

TEXTOS = (".json", ".sh", ".py", ".txt", ".ass", ".srt", ".md")
LIMITE = 2 * 1024 * 1024
COMANDOS = ("comando.sh", "RESULTADO.json", "montar.sh", "montar.py")
TOL_DURACAO = .15
FOLGA = .3
IGUAIS = .95
DIFF_MAX = 6.0   # diferença média (0-255) entre dois quadros 48x84 em cinza que ainda conta como "iguais" (ruído do re-encode)


def _cwd(txt: str, p: Path) -> Path:
    return RAIZ if re.search(r"(^|&&|;|\n)\s*cd\s", txt) else p


def _comando(p: Path):
    p = Path(p)
    f = p / "comando.sh"
    if f.is_file() and f.read_text(encoding="utf-8", errors="ignore").strip():
        return ["zsh", str(f)], _cwd(f.read_text(encoding="utf-8", errors="ignore"), p)
    r = ler_json(p / "RESULTADO.json", {})
    c = r.get("comando") if isinstance(r, dict) else None
    if isinstance(c, str) and c.strip():
        return ["zsh", "-c", c], _cwd(c, p)
    if (p / "montar.sh").is_file():
        return ["zsh", "montar.sh"], p
    if (p / "montar.py").is_file():
        return [sys.executable, "montar.py"], p
    return None


def _fonte(p: Path) -> str:
    p = Path(p)
    if (p / "comando.sh").is_file():
        return "comando.sh"
    r = ler_json(p / "RESULTADO.json", {})
    if isinstance(r, dict) and isinstance(r.get("comando"), str) and r["comando"].strip():
        return "RESULTADO.json"
    return next((n for n in ("montar.sh", "montar.py") if (p / n).is_file()), "comando.sh")


def _saida(p: Path) -> Path:
    p = Path(p)
    padrao = _base.saida_padrao(p)
    if padrao.is_file():
        return padrao
    r = ler_json(p / "RESULTADO.json", {})
    for k in ("saida", "video", "video_final", "mp4"):
        v = r.get(k) if isinstance(r, dict) else None
        if isinstance(v, str) and v.endswith(".mp4"):
            q = Path(v) if os.path.isabs(v) else RAIZ / v
            if q.is_file():
                return q
    return padrao


def _citados(p: Path) -> list[str]:
    """Arquivos de work/ que o script do comando cita por nome literal (sem $ nem *): têm de existir pra o comando rodar."""
    f = Path(p) / _fonte(p)
    txt = f.read_text(encoding="utf-8", errors="ignore") if f.is_file() else ""
    return sorted(set(re.findall(r"(?<![\w$/.-])(work/[\w./-]+\.(?:mp4|mov|mp3|wav|png|jpg|json))", txt)))


def achar(p: Path) -> bool:
    p = Path(p)
    return (p / "work").is_dir() and _saida(p).is_file() and _comando(p) is not None


def arquivos(p: Path) -> list[str]:
    """Todo arquivo de texto da raiz e de work/ (até 2 MB): o que a versão guarda e o que volta se o vídeo novo não servir."""
    out = []
    for d in (Path(p), Path(p) / "work"):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in TEXTOS and f.stat().st_size <= LIMITE:
                out.append(str(f.relative_to(p)))
    return out


# ───────────────────────── cenas ─────────────────────────

def _pontos_do_plano(p: Path, dur: float) -> list[float]:
    """Começos de beats ou janelas do PLANO.json (se houver)."""
    pl = ler_json(Path(p) / "PLANO.json", {})
    if not isinstance(pl, dict):
        return []
    pts: list[float] = []
    for j in pl.get("janelas") or []:
        try:
            pts += [float(j[0]), float(j[1])]
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    for b in pl.get("beats") or []:
        if isinstance(b, (int, float)):
            pts.append(float(b))
        elif isinstance(b, dict):
            for k in ("de", "t", "t0", "inicio", "start"):
                if isinstance(b.get(k), (int, float)):
                    pts.append(float(b[k]))
                    break
    return sorted({round(t, 2) for t in pts if 0 <= t < dur - .5})


def _ler(p: Path) -> dict:
    p = Path(p)
    saida = _saida(p)
    dur = _base.duracao_video(saida)
    pal = next((r for r in ("work/words.json", "work/cortado/words.json", "work/legenda/words.json") if (p / r).is_file()), "")
    pts = _pontos_do_plano(p, dur)
    if len(pts) >= 2:
        cortes = sorted({0.0, *pts})
    else:
        ws = _base.palavras(p / pal) if pal else []
        cortes = _base.trechos_da_fala(ws, dur) if ws else [float(t) for t in range(0, int(dur), 5)] or [0.0]
    r = ler_json(p / "RESULTADO.json", {})
    titulo = (r.get("titulo") if isinstance(r, dict) else None) or p.name.removeprefix("_sandbox-").replace("-", " ").capitalize()
    doc = {"titulo": str(titulo)[:80], "saida": str(saida), "duracao": round(dur, 3), "cenas": [{"de": t, "tipo": "trecho"} for t in cortes]}
    if pal:
        doc["palavras"] = pal
    return doc


def _gravar(p: Path, doc: dict) -> None:
    """No modo livre as cenas só marcam o tempo: nada a gravar (a IA mexe nos arquivos da pasta)."""
    return None


# ───────────────────────── antes / depois ─────────────────────────

def antes(p: Path) -> dict:
    """Guarda na memória os textos e, ao lado (clone, sem gastar espaço), o vídeo e a voz."""
    p = Path(p)
    ed = p / "editor"
    ed.mkdir(parents=True, exist_ok=True)
    saida = _saida(p)
    prep = {"t0": time.time(), "saida": saida, "textos": {}, "dur": _base.duracao_video(saida), "video": None, "voz": None}
    for a in arquivos(p):
        prep["textos"][a] = (p / a).read_bytes()
    if saida.is_file():
        prep["video"] = ed / "livre-antes.mp4"
        clonar(saida, prep["video"])
    voz = p / "work" / "joao.mp4"
    if voz.is_file():
        prep["voz"] = ed / "livre-antes-voz.mp4"
        clonar(voz, prep["voz"])
        prep["voz_tam"] = voz.stat().st_size
    return prep


def mudou(p: Path, prep: dict) -> bool:
    """A IA mexeu em algum arquivo da pasta (texto diferente, arquivo novo ou mídia nova)."""
    p = Path(p)
    for a, b in prep["textos"].items():
        f = p / a
        if not f.is_file() or f.read_bytes() != b:
            return True
    for raiz, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in ("editor", "qa", "quadros", "__pycache__")]
        for n in files:
            f = Path(raiz) / n
            if f.suffix.lower() == ".mp4" and f == prep["saida"]:
                continue
            try:
                if f.stat().st_mtime > prep["t0"]:
                    return True
            except OSError:
                continue
    return False


def voltar(p: Path, prep: dict) -> None:
    """Volta os textos, a voz e o vídeo como estavam antes do pedido (arquivo novo que a IA criou fica; nada é apagado)."""
    p = Path(p)
    for a, b in prep["textos"].items():
        f = p / a
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.is_file() or f.read_bytes() != b:
            f.write_bytes(b)
    if prep.get("voz") and Path(prep["voz"]).is_file():
        v = p / "work" / "joao.mp4"
        if not v.is_file() or v.stat().st_size != prep.get("voz_tam"):
            clonar(prep["voz"], v)
    if prep.get("video") and Path(prep["video"]).is_file():
        clonar(prep["video"], prep["saida"])


def _quadros(video: Path):
    """Cada 0,5 s, 48x84 em cinza: matriz (n, 4032) de bytes."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vf", "fps=2,scale=48:84:flags=bilinear,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=600)
    n = len(r.stdout) // (48 * 84)
    return np.frombuffer(r.stdout[:n * 48 * 84], dtype="uint8").reshape(n, 48 * 84).astype("int16") if n else None


def conferir(p: Path, prep: dict, ped: dict, cs: list[dict]) -> str:
    """"" se o vídeo novo serve; senão a frase (em português) do motivo. Quem chama volta tudo e mostra a frase."""
    p = Path(p)
    novo = _saida(p)
    dn = _base.duracao_video(novo)
    if not novo.is_file() or dn <= 0:
        return "O vídeo novo não abriu; voltei como estava."
    if abs(dn - prep["dur"]) > TOL_DURACAO:
        return f"A duração do vídeo mudou (de {prep['dur']:.1f} s pra {dn:.1f} s); voltei como estava."
    voz = p / "work" / "joao.mp4"
    if prep.get("voz") and voz.is_file() and voz.stat().st_size != prep.get("voz_tam"):
        return "A mudança mexeu na voz (work/joao.mp4); voltei como estava."
    if ped["escopo"] == "video" or not prep.get("video"):
        return ""
    a, b = _quadros(prep["video"]), _quadros(novo)
    if a is None or b is None:
        return "Não consegui comparar o vídeo novo com o antigo; voltei como estava."
    n = min(len(a), len(b))
    i, j = ped["n"] - 1, (ped.get("n_fim") or ped["n"]) - 1
    de, ate = cs[i]["de"], cs[j]["ate"]
    fora = [k for k in range(n) if k * .5 < de - FOLGA or k * .5 > ate + FOLGA]
    if len(fora) >= 4:
        iguais = sum(1 for k in fora if abs(a[k] - b[k]).mean() < DIFF_MAX)
        if iguais < IGUAIS * len(fora):
            alvo = f"cena {ped['n']}" if ped["escopo"] == "cena" else f"trecho das cenas {ped['n']} a {ped.get('n_fim') or ped['n']}"
            return f"A mudança passou da {alvo}; voltei como estava." if ped["escopo"] == "cena" else f"A mudança passou do {alvo}; voltei como estava."
    return ""


# ───────────────────────── pedido à IA ─────────────────────────

def prompt(p: Path, ped: dict, cs: list[dict], doc: dict, cmd: str) -> str:
    p = Path(p)
    if ped["escopo"] == "video":
        alvo = "ALCANCE: o vídeo todo, mas mude só o que o pedido pede. A duração tem de ficar igual."
    else:
        i, j = ped["n"] - 1, (ped.get("n_fim") or ped["n"]) - 1
        fala = " ".join(c["fala"] for c in cs[i:j + 1])
        alvo = (f"ALCANCE: SÓ {'a cena ' + str(ped['n']) if i == j else 'as cenas ' + str(ped['n']) + ' a ' + str(j + 1)} "
                f"(de {cs[i]['de']} a {cs[j]['ate']} s do vídeo pronto). Fora desses segundos o vídeo tem de ficar IDÊNTICO: o Estúdio compara "
                f"quadro a quadro e, se passar, volta tudo.\nA fala desse trecho: \"{fala}\"")
    arqs = arquivos(p)
    return f"""Você é o editor de um vídeo do Estúdio. Trabalhe SÓ dentro da pasta {p}.
O vídeo pronto é {doc['saida']} ({doc['duracao']} s). Ele foi montado por um comando e NÃO tem um plano estruturado: {cmd}
Os arquivos que montam o vídeo estão na pasta (scripts, plano, listas). Arquivos de texto: {', '.join(arqs[:40])}.
Regras do cliente: {p.parent}/aprendizado/regras.json. Gerais: {RAIZ}/REGRAS.md.

PEDIDO DO JOÃO: {ped['texto']}{(chr(10) + 'O João anexou um print: ' + str(RAIZ / ped['print']) + '. Abra a imagem (Read) antes.') if ped.get('print') else ''}

{alvo}

Como trabalhar:
1. Descubra no script (comando.sh, montar.sh ou montar.py) onde nasce essa parte do vídeo e mude SÓ isso, nos arquivos da pasta.
2. NÃO rode o comando que refaz o vídeo, NÃO escreva em {doc['saida']} e NÃO apague nenhum vídeo ou arquivo: o Estúdio guarda tudo e refaz o vídeo depois.
3. A voz (work/joao.mp4 e o corte) NUNCA muda; a duração do vídeo tem de ficar igual (±0,15 s). Mídia nova entra em arquivo NOVO (nunca por cima de um existente), real e do assunto (acervo em {RAIZ}/acervo/itens/*/clip.mp4); nada de banco de imagem posando nem Wikipédia.
4. Pra conferir uma imagem ou clipe novo, tire um quadro com ffmpeg e OLHE a imagem.
5. Termine com UMA frase dizendo o que mudou (é o que o João vai ler)."""


SPEC = {
    "gravado": True, "livre": True, "fonte": _fonte, "arquivos": arquivos, "precisa": lambda p: [str(_saida(p)), *_citados(p)],
    "achar": achar, "ler": _ler, "gravar": _gravar, "cmd": _comando, "saida": _saida, "timeout": 3600, "tempo_fixo": True,
    "rotulos": {}, "tipos": {"trecho": "Trecho do vídeo"}, "tipo_padrao": "trecho", "juntos": {}, "sempre": (),
    "sugestoes": ["Troca o b-roll desta cena por um que case mais com a fala", "O texto da tela está grande demais",
                  "Tira o efeito desta cena", "Põe uma transição na entrada desta cena"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "o comando que refaz o vídeo",
    "motivo_narracao": "Neste vídeo a voz é a gravação do João: a fala só muda trocando o bruto.",
    "dicas": "", "prompt": prompt, "livre_antes": antes, "livre_mudou": mudou, "livre_voltar": voltar, "livre_conferir": conferir,
}
SPECS = {"_livre": SPEC}
