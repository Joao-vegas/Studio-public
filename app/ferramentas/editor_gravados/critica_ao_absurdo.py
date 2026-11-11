"""Crítica ao absurdo: em cima o trecho de um vídeo absurdo (com legenda de 1 a 3 palavras), embaixo a foto fixa do João reagindo e,
no fim, a resposta dele em tela cheia. O render é o gerar.sh do modelo:
    zsh ../gerar.sh --dir . --de <DE> --ate <ATE> [--sem-legenda] [--sem-resposta] [--foco-x 0..1] [--foco-y 0..1] [--foto-y 0..1] [--foto <img>]

Os parâmetros moram no PLANO.json (de, ate, sem_legenda, sem_resposta, foco_x, foco_y, foto_y, foto) e no comando.sh que a esteira grava;
sem PLANO.json o editor lê o comando.sh (ou o RESULTADO.json → comando). Ao editar, o editor grava os dois.
Cenas: o trecho do vídeo absurdo por trechos da fala (words da legenda) e a resposta do João. Elementos do vídeo todo: trecho (de/até),
legenda, foco do vídeo de cima, resposta e foto.
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

from _comum import RAIZ, gravar_json, ler_json

from . import _base

FLAGS = {"de": "--de", "ate": "--ate", "foco_x": "--foco-x", "foco_y": "--foco-y", "foto_y": "--foto-y", "foto": "--foto"}


def _tempo(v) -> float | None:
    """'1:23.5' ou '83.5' ou número → segundos."""
    if v in (None, ""):
        return None
    seg = 0.0
    for parte in str(v).split(":"):
        seg = seg * 60 + float(str(parte).replace(",", "."))
    return seg


def _do_comando(p: Path) -> dict:
    """Os parâmetros do último comando que a esteira gravou (comando.sh, senão RESULTADO.json → comando)."""
    txt = ""
    f = Path(p) / "comando.sh"
    if f.is_file():
        txt = f.read_text(encoding="utf-8", errors="ignore")
    else:
        txt = str((ler_json(Path(p) / "RESULTADO.json", {}) or {}).get("comando") or "")
    out: dict = {}
    if "gerar.sh" not in txt:
        return out
    try:
        t = shlex.split(txt.splitlines()[-1] if "\n" in txt.strip() else txt)
    except ValueError:
        return out
    for k, flag in FLAGS.items():
        if flag in t and t.index(flag) + 1 < len(t):
            out[k] = t[t.index(flag) + 1]
    out["sem_legenda"] = "--sem-legenda" in t
    out["sem_resposta"] = "--sem-resposta" in t
    return out


def _params(p: Path) -> dict:
    pl = ler_json(Path(p) / "PLANO.json", {}) or {}
    base = {**_do_comando(p), **{k: v for k, v in pl.items() if k in (*FLAGS, "sem_legenda", "sem_resposta")}}
    return base


def _absurdo(p: Path) -> Path:
    return Path(p) / "work" / "absurdo.mp4"


def _resposta(p: Path) -> Path:
    return Path(p) / "work" / "joao.mp4"


def _ler(p: Path) -> dict:
    p = Path(p)
    a = _params(p)
    de = _tempo(a.get("de")) or 0.0
    ate = _tempo(a.get("ate"))
    if ate is None:
        ate = _base.duracao_video(_absurdo(p))
    dt = max(ate - de, 0.0)
    resp = 0.0 if a.get("sem_resposta") else _base.duracao_video(_resposta(p)) if _resposta(p).is_file() else 0.0
    pal = "work/legenda/words.json" if (p / "work" / "legenda" / "words.json").is_file() else ""
    ws = _base.palavras(p / pal) if pal else []
    cortes = _base.trechos_da_fala(ws, dt)
    cenas = [{"de": t, "tipo": "trecho"} for t in cortes]
    if resp > 0:
        cenas.append({"de": round(dt, 3), "tipo": "resposta"})
    doc = {"titulo": p.name.removeprefix("_sandbox-").replace("-", " ").capitalize(), "saida": str(_base.saida_padrao(p)),
           "duracao": round(dt + resp, 3), "trecho_de": round(de, 2), "trecho_ate": round(ate, 2),
           "sem_legenda": bool(a.get("sem_legenda")), "sem_resposta": bool(a.get("sem_resposta")),
           "foco_x": float(a.get("foco_x", .5)), "foco_y": float(a.get("foco_y", .3)), "foto_y": float(a.get("foto_y", .35)),
           "foto": str(a.get("foto") or ""), "cenas": cenas}
    if pal:
        doc["palavras"] = pal
    return doc


PARAMS = ("trecho_de", "trecho_ate", "sem_legenda", "sem_resposta", "foco_x", "foco_y", "foto_y", "foto")


def _linha(p: Path, doc: dict) -> str:
    c = ["zsh", "../gerar.sh", "--dir", ".", "--de", f"{doc['trecho_de']:g}", "--ate", f"{doc['trecho_ate']:g}"]
    if doc.get("sem_legenda"):
        c.append("--sem-legenda")
    if doc.get("sem_resposta"):
        c.append("--sem-resposta")
    c += ["--foco-x", f"{doc['foco_x']:g}", "--foco-y", f"{doc['foco_y']:g}", "--foto-y", f"{doc['foto_y']:g}"]
    if doc.get("foto"):
        c += ["--foto", doc["foto"]]
    try:
        onde = str(Path(p).resolve().relative_to(RAIZ.resolve()))
    except ValueError:
        onde = str(p)
    return f"cd {shlex.quote(onde)} && " + " ".join(shlex.quote(x) for x in c)


def _gravar(p: Path, doc: dict) -> None:
    p = Path(p)
    atual = _ler(p) if (p / "work").is_dir() else {}
    if all(doc.get(k) == atual.get(k) for k in PARAMS):
        return   # nada dos parâmetros mudou: PLANO.json e comando.sh ficam como a esteira gravou
    pl = ler_json(p / "PLANO.json", {}) or {}
    ate, de = float(doc["trecho_ate"]), float(doc["trecho_de"])
    if ate <= de:
        raise ValueError("O fim do trecho tem de vir depois do começo.")
    cl = lambda v: min(max(float(v), 0.0), 1.0)
    novo = {**pl, "de": round(de, 2), "ate": round(ate, 2), "sem_legenda": bool(doc.get("sem_legenda")),
            "sem_resposta": bool(doc.get("sem_resposta")), "foco_x": cl(doc["foco_x"]), "foco_y": cl(doc["foco_y"]), "foto_y": cl(doc["foto_y"])}
    if doc.get("foto"):
        novo["foto"] = str(doc["foto"])
    else:
        novo.pop("foto", None)
    gravar_json(p / "PLANO.json", novo)
    (p / "comando.sh").write_text(_linha(p, {**doc, "trecho_de": de, "trecho_ate": ate, "foco_x": novo["foco_x"], "foco_y": novo["foco_y"],
                                              "foto_y": novo["foto_y"]}) + "\n", encoding="utf-8")


def _cmd(p: Path):
    p = Path(p)
    g = p.parent / "gerar.sh"
    if not g.is_file():
        return None
    a = _params(p)
    if a.get("de") is None and a.get("ate") is None:
        return None   # sem trecho conhecido não dá pra refazer
    de, ate = _tempo(a.get("de")) or 0.0, _tempo(a.get("ate"))
    c = ["zsh", "../gerar.sh", "--dir", ".", "--saida", str(_base.saida_padrao(p)), "--de", f"{de:g}"]
    if ate is not None:
        c += ["--ate", f"{ate:g}"]
    if a.get("sem_legenda"):
        c.append("--sem-legenda")
    if a.get("sem_resposta"):
        c.append("--sem-resposta")
    for k in ("foco_x", "foco_y", "foto_y", "foto"):
        if a.get(k) not in (None, ""):
            c += [FLAGS[k], str(a[k])]
    return c, p


SPEC = {
    "gravado": True, "fonte": lambda p: "PLANO.json" if (Path(p) / "PLANO.json").is_file() else "comando.sh", "arquivos": ["PLANO.json", "comando.sh"], "precisa": ["work/absurdo.mp4"],
    "achar": lambda p: _absurdo(p).is_file() and Path(p).parent.joinpath("gerar.sh").is_file() and bool(_params(p)),
    "ler": _ler, "gravar": _gravar, "cmd": _cmd, "saida": _base.saida_padrao, "tempo_fixo": True, "timeout": 1800,
    "rotulos": {"trecho": "Trecho do vídeo (de/até)", "legenda": "Legenda do vídeo de cima", "foco": "Enquadramento do vídeo de cima",
                "resposta": "Sua resposta no fim", "foto": "Foto de baixo"},
    "globais": {"trecho": ["trecho_de", "trecho_ate"], "legenda": ["sem_legenda"], "foco": ["foco_x", "foco_y"],
                "resposta": ["sem_resposta"], "foto": ["foto_y", "foto"]},
    "tipos": {"trecho": "Trecho do vídeo", "resposta": "Sua resposta"}, "tipo_padrao": "trecho", "juntos": {}, "sempre": (),
    "sugestoes": ["Começa o trecho 2 segundos depois", "Tira a legenda (o vídeo já tem)", "Centraliza o rosto de quem fala",
                  "Tira a minha resposta do fim"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "gerar.sh e build.py",
    "motivo_narracao": "A fala vem do vídeo absurdo (em cima) e da sua resposta gravada: só muda trocando o vídeo.",
    "onde": ("O vídeo é o trecho de um vídeo absurdo (work/absurdo.mp4) em cima, a foto fixa do João embaixo e a resposta dele no fim, "
             "montado pelo gerar.sh do modelo. Você NÃO mexe no PLANO.json nem no comando.sh: edite só {arq_ia}. As cenas só marcam o tempo "
             "(o trecho por trechos da fala, e a resposta); o que muda mora nos campos do TOPO do arquivo."),
    "conferir": "O vídeo todo é refeito pelo Estúdio depois; para o trecho, confira os segundos olhando um quadro do work/absurdo.mp4 "
                "(`ffmpeg -ss <segundo> -i work/absurdo.mp4 -frames:v 1 q.jpg`) e OLHE a imagem.",
    "dicas": ("Campos do topo: \"trecho_de\" e \"trecho_ate\" (segundos do vídeo absurdo, uns 20 a 30 s; o começo na fala, sem respiro morto), "
              "\"sem_legenda\" (true quando o vídeo de cima já vem com legenda queimada), \"foco_x\" e \"foco_y\" (0 a 1: onde o rosto de quem "
              "fala fica no corte de cima), \"sem_resposta\" (true tira a sua resposta do fim) e \"foto_y\" (0 a 1: corte vertical da foto de "
              "baixo). Pra olhar o enquadramento tire um quadro do vídeo e OLHE. Não mude o \"de\" das cenas."),
}
SPECS = {"critica-ao-absurdo": SPEC}
