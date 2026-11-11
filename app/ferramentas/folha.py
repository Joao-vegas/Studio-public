"""Folha de quadros de um vídeo: vários quadros numa imagem só, com o segundo escrito em cada um.

Pra IA olhar um b-roll (ou um trecho) inteiro com UMA leitura de imagem, em vez de abrir quadro por quadro
ou escrever um script de folha na hora.

  python3 app/ferramentas/folha.py <video> --saida X.jpg [--de S] [--ate S] [--passo S] [--colunas N]

Sem --passo: ~12 quadros no trecho (no mínimo 1 a cada 0,5 s). Largura máxima 1600 px.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ffprobe  # noqa: E402

LARGURA = 1600
MAX_QUADROS = 36


def _fonte(tam: int):
    from PIL import ImageFont
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _rotulo(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}" if m else f"{s:.1f}s"


def folha(video: Path, saida: Path, de: float = 0.0, ate: float | None = None, passo: float | None = None,
          colunas: int = 4) -> Path:
    from PIL import Image, ImageDraw
    dur = float(ffprobe(video).get("duracao") or 0)
    ate = min(ate, dur) if (ate and dur) else (ate or dur)
    if not ate or ate <= de:
        raise ValueError(f"trecho vazio ({de} a {ate} s) em {video}")
    trecho = ate - de
    passo = passo or max(0.5, round(trecho / 12 * 2) / 2)
    passo = max(passo, trecho / MAX_QUADROS)
    colunas = max(1, int(colunas))
    larg_q = LARGURA // colunas
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{de:.3f}", "-t", f"{trecho:.3f}", "-i", str(video),
                        "-vf", f"fps=1/{passo:.4f},scale={larg_q}:-2", "-q:v", "4", f"{tmp}/q%04d.jpg"], check=True)
        quadros = sorted(Path(tmp).glob("q*.jpg"))[:MAX_QUADROS]
        if not quadros:
            raise ValueError(f"nenhum quadro saiu de {video}")
        ims = []
        for q in quadros:
            with Image.open(q) as im:
                ims.append(im.convert("RGB"))
        alt_q = ims[0].height
        linhas = -(-len(ims) // colunas)
        tela = Image.new("RGB", (larg_q * colunas, alt_q * linhas), (20, 20, 20))
        fonte = _fonte(max(16, larg_q // 12))
        for i, im in enumerate(ims):
            x, y = (i % colunas) * larg_q, (i // colunas) * alt_q
            tela.paste(im, (x, y))
            d = ImageDraw.Draw(tela)
            txt = _rotulo(de + i * passo)
            caixa = d.textbbox((0, 0), txt, font=fonte)
            d.rectangle((x + 6, y + 6, x + 18 + caixa[2], y + 14 + caixa[3]), fill=(0, 0, 0))
            d.text((x + 12, y + 8), txt, fill=(255, 230, 0), font=fonte)
    saida.parent.mkdir(parents=True, exist_ok=True)
    tela.save(saida, quality=85)
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Folha de quadros com o segundo escrito em cada um.")
    ap.add_argument("video", type=Path)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--de", type=float, default=0.0)
    ap.add_argument("--ate", type=float)
    ap.add_argument("--passo", type=float)
    ap.add_argument("--colunas", type=int, default=4)
    a = ap.parse_args()
    try:
        print(folha(a.video, a.saida, a.de, a.ate, a.passo, a.colunas))
    except (ValueError, subprocess.CalledProcessError) as e:
        sys.exit(f"erro: {e}")
