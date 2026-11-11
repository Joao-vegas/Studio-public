#!/usr/bin/env python3
"""
folha_broll — a FOLHA DE PRÉVIA do b-roll: por opção, 6 quadros lado a lado com um cabeçalho legível
(nº da opção, fonte, link, tempo de/até, resolução). Tudo desenhado com PIL (o ffmpeg daqui não tem drawtext).
Várias opções (as 3 de uma cena) viram uma folha só, uma faixa por opção.

  python3 app/ferramentas/folha_broll.py <video> --saida X.jpg [--fonte youtube] [--link URL] [--de S] [--ate S] [--numero 1]
  python3 app/ferramentas/folha_broll.py --opcoes opcoes.json --saida work/brolls/folha-cena1.jpg
      (opcoes.json = lista de {"video", "fonte", "link", "de", "ate"}; a opção vem numerada na ordem)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ffprobe  # noqa: E402
from folha import _fonte, _rotulo  # noqa: E402

LARGURA = 1800
QUADROS = 6


def _resolucao(video: Path) -> str:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0:s=x", str(video)], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or "?"
    except Exception:
        return "?"


def _quadros(video: Path, de: float, ate: float, n: int, larg: int, tmp: Path) -> list[Path]:
    saidas = []
    trecho = max(0.2, ate - de)
    for i in range(n):
        t = de + trecho * (i + 0.5) / n
        out = tmp / f"q{i}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={larg}:-2", "-q:v", "4", str(out)], check=False)
        if out.is_file():
            saidas.append((t, out))
    return saidas


def faixa(video: Path, fonte: str = "", link: str = "", de: float = 0.0, ate: float | None = None, numero: int = 1):
    """Uma opção: devolve a imagem PIL (cabeçalho + 6 quadros)."""
    from PIL import Image, ImageDraw
    video = Path(video)
    dur = float(ffprobe(video).get("duracao") or 0)
    ate = min(ate, dur) if (ate and dur) else (ate or dur)
    if not ate or ate <= de:
        raise ValueError(f"trecho vazio ({de} a {ate} s) em {video}")
    larg_q = LARGURA // QUADROS
    with tempfile.TemporaryDirectory() as t:
        qs = _quadros(video, de, ate, QUADROS, larg_q, Path(t))
        if not qs:
            raise ValueError(f"nenhum quadro saiu de {video}")
        ims = [(tt, Image.open(p).convert("RGB")) for tt, p in qs]
    alt_q = max(im.height for _, im in ims)
    cab = 74
    tela = Image.new("RGB", (larg_q * QUADROS, cab + alt_q), (20, 20, 20))
    d = ImageDraw.Draw(tela)
    d.text((14, 8), f"OPÇÃO {numero}", fill=(255, 230, 0), font=_fonte(34))
    d.text((230, 12), f"{fonte or 'fonte ?'}   {_rotulo(de)} → {_rotulo(ate)}   {_resolucao(video)}", fill=(255, 255, 255), font=_fonte(24))
    d.text((14, 48), (link or str(video))[:150], fill=(170, 170, 170), font=_fonte(18))
    for i, (tt, im) in enumerate(ims):
        tela.paste(im, (i * larg_q, cab))
        d.rectangle((i * larg_q + 4, cab + 4, i * larg_q + 92, cab + 30), fill=(0, 0, 0))
        d.text((i * larg_q + 8, cab + 6), _rotulo(tt), fill=(255, 230, 0), font=_fonte(18))
    return tela


def folha_opcoes(opcoes: list[dict], saida: Path) -> Path:
    from PIL import Image
    faixas = [faixa(Path(o["video"]), o.get("fonte", ""), o.get("link", ""), float(o.get("de") or 0),
                    float(o["ate"]) if o.get("ate") else None, i) for i, o in enumerate(opcoes, 1)]
    tela = Image.new("RGB", (faixas[0].width, sum(f.height + 8 for f in faixas)), (0, 0, 0))
    y = 0
    for f in faixas:
        tela.paste(f, (0, y))
        y += f.height + 8
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    tela.save(saida, quality=88)
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Folha de prévia do b-roll (6 quadros + cabeçalho por opção).")
    ap.add_argument("video", type=Path, nargs="?")
    ap.add_argument("--opcoes", type=Path)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--fonte", default="")
    ap.add_argument("--link", default="")
    ap.add_argument("--de", type=float, default=0.0)
    ap.add_argument("--ate", type=float)
    ap.add_argument("--numero", type=int, default=1)
    a = ap.parse_args()
    try:
        if a.opcoes:
            ops = json.loads(a.opcoes.read_text(encoding="utf-8"))
        elif a.video:
            ops = [{"video": str(a.video), "fonte": a.fonte, "link": a.link, "de": a.de, "ate": a.ate}]
        else:
            sys.exit("erro: passe o vídeo ou --opcoes")
        print(folha_opcoes(ops, a.saida))
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"erro: {e}")
