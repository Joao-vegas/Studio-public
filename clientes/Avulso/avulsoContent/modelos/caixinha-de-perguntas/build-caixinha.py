#!/usr/bin/env python3
"""Caixinha de perguntas: grava a camada (<sandbox>/camada.json, "tipo": "caixinha") no formato do editor
(app/ferramentas/camada.py). O desenho é o do app/ferramentas/caixinha.py (o mesmo da tela "Editar o texto"):
SF Pro, medidas do print do Instagram, fixas. Este script só decide o texto e a altura.

Uso: python3 build-caixinha.py --dir <sandbox> --pergunta "..." --saida <mp4> [--titulo "O que você quer saber?"]
       [--posicao cima|peito] [--topo px] [--cliente <Nome>] [--png caixa.png]"""
import argparse, json, os, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(RAIZ / "app/ferramentas"))
import caixinha as cx  # noqa: E402
import camada as cam  # noqa: E402


def cliente_do_caminho(sb):
    partes = sb.parts
    return partes[partes.index("clientes") + 1] if "clientes" in partes else "Avulso"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--pergunta", required=True)
    ap.add_argument("--titulo", default=cx.TITULO_PADRAO)
    ap.add_argument("--posicao", default="cima", choices=["cima", "peito"])
    ap.add_argument("--topo", type=int, help="y do topo da caixa (padrão: 255 em cima)")
    ap.add_argument("--saida", required=True); ap.add_argument("--cliente"); ap.add_argument("--png")
    a = ap.parse_args()
    sb = Path(os.path.abspath(a.dir)); rel = lambda x: os.path.relpath(os.path.abspath(x), RAIZ)
    y = a.topo if a.topo is not None else cx.topo_padrao(a.posicao, a.pergunta, a.titulo)
    p = cam.limpar({"tipo": "caixinha", "texto": a.pergunta, "titulo": a.titulo, "y": y})
    c = {"video": rel(sb / "work/joao.mp4"), "saida": rel(a.saida), **p, "posicao": a.posicao,
         "andamento": [a.cliente or cliente_do_caminho(sb), sb.name.removeprefix("_sandbox-")]}
    (sb / "camada.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.png: cam.caixa_png(c).save(a.png)
    lt, lp, _, h = cx.medir(a.pergunta, a.titulo)
    if len(lp) > 4:
        print(f"⚠ pergunta com {len(lp)} linhas: no Instagram ela costuma ter 1 a 3", file=sys.stderr)
    print(json.dumps({"topo": p["y"], "altura": h, "titulo": lt, "linhas": lp}, ensure_ascii=False))
