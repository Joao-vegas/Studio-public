"""
Busca B-roll no Pexels (via skill get-brolls, só leitura) e monta uma folha de capas por cena.

broll/_candidatos/<cena>.jpg  → folha com as capas numeradas
broll/_candidatos/<cena>.json → id, duração e link do mp4 de cada capa

Uso: python3 ~/Projetos/Skill/Estúdio/app/ferramentas/motion/buscar_broll.py --pasta <projeto> \
         --cena trabalho "professional man working focused office desk" --cena celular "man looking at smartphone" [--vertical]
Busca em inglês. Depois de escolher na folha, baixar o mp4 do .json e virar quadros (ver referencias/tecnico.md).
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

try:
    sys.path.append("/Users/joaomarcospiki/Cerebro/scripts")
    from limpar_runtime import registrar_cleanup_no_atexit
except ImportError:
    registrar_cleanup_no_atexit = lambda: None  # noqa: E731

AQUI = Path(".")
GB = Path.home() / ".claude/skills/get-brolls/scripts/gb.py"
GB_PY = Path.home() / ".claude/skills/get-brolls/.venv/bin/python"   # o Python do get-brolls (o python3 do PATH pode ser outra versão)


def buscar(cena: str, q: str, vertical: bool = False) -> None:
    out = subprocess.run([str(GB_PY) if GB_PY.exists() else sys.executable, str(GB), "search", "--provider", "pexels", "--query", q, "--dry-run",
                          "--project", str(AQUI)], capture_output=True, text=True).stdout
    def serve(m):  # vertical: clipe em pé com pelo menos 1080 de largura; horizontal: 1920+
        w, h = m.get("width") or 0, m.get("height") or 0
        return (h > w and w >= 1080) if vertical else w >= 1920
    itens = [i for i in json.loads(out)["items"] if serve(i["media"])][:8]
    if not itens:
        print(cena, 0, "(nada no formato; tente outra busca)")
        return
    capas, dados = [], []
    for k, it in enumerate(itens):
        img = Image.open(io.BytesIO(requests.get(it["preview"]["poster_url"], timeout=30).content)).convert("RGB")
        img = img.resize((200, 356) if vertical else (480, 252))
        ImageDraw.Draw(img).text((10, 8), f"{k}  {it['media']['duration_s']}s", fill=(255, 220, 0))
        capas.append(img)
        dados.append({"k": k, "id": it["source_id"], "dur": it["media"]["duration_s"], "mp4": it["media_url"],
                      "autor": it["creator"]["name"], "fonte": it["source_url"]})
    cw, ch = capas[0].size
    por = 4 if vertical else 2
    folha = Image.new("RGB", (cw * por, ch * ((len(capas) + por - 1) // por)))
    for k, c in enumerate(capas):
        folha.paste(c, ((k % por) * cw, (k // por) * ch))
    d = AQUI / "broll" / "_candidatos"
    d.mkdir(parents=True, exist_ok=True)
    folha.save(d / f"{cena}.jpg", quality=85)
    (d / f"{cena}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1))
    print(cena, len(dados))


if __name__ == "__main__":
    import argparse

    registrar_cleanup_no_atexit()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True, type=Path)
    ap.add_argument("--cena", nargs=2, action="append", metavar=("NOME", "BUSCA"), required=True)
    ap.add_argument("--vertical", action="store_true", help="motion 1080x1920: só clipes em pé")
    a = ap.parse_args()
    AQUI = a.pasta.resolve()
    for c, q in a.cena:
        buscar(c, q, a.vertical)
