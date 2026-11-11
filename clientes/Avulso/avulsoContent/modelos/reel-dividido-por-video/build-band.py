#!/usr/bin/env python3
"""
Gera band.png 1080x1920 RGBA: tudo transparente, exceto a faixa vermelha
(estilo "marker/destaque pintado") com titulo branco CENTRALIZADO (h e v).

- Fonte: Bebas Neue (a mesma do modelo reel-dividido-por-imagem).
- Vermelho vivo + bordas sup/inf irregulares (rasgadas), so pra fora (sem gap).
- Texto centralizado horizontal E vertical de verdade (usa bbox real dos glifos).
"""
import argparse, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H   = 1080, 1920
TOP_H  = 816   # padrao; sobrescrito por --top-h
BAND_H = 270
BEBAS  = "/Users/joaomarcospiki/Library/Fonts/BebasNeue-Regular.ttf"  # fonte do modelo
PAD_X  = 44
RED    = (222, 28, 33)
WHITE  = (255, 255, 255)


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def torn_band_mask(top, height, seed=7):
    """Faixa com bordas sup/inf irregulares. Ruido SO pra fora -> nunca abre gap."""
    random.seed(seed)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    step = 26
    top_pts, bot_pts = [], []
    x = -20
    while x <= W + 20:
        top_pts.append((x, top + random.randint(-16, 0)))
        bot_pts.append((x, top + height + random.randint(0, 18)))
        x += step
    d.polygon(top_pts + bot_pts[::-1], fill=255)
    for _ in range(40):
        sx = random.choice([random.randint(-10, 60), random.randint(W - 60, W + 10)])
        sy = random.randint(top - 8, top + height + 8)
        r = random.randint(2, 9)
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(0.6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--titulo", default="")
    ap.add_argument("--fontsize", type=int, default=94)   # igual ao modelo
    ap.add_argument("--flat", action="store_true")
    ap.add_argument("--top-h", type=int, default=None)   # desce/sobe a faixa (altura do bloco do Joao)
    args = ap.parse_args()
    if args.top_h:
        global TOP_H
        TOP_H = args.top_h

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band_layer = Image.new("RGBA", (W, H), RED + (255,))
    if args.flat:
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rectangle([0, TOP_H, W, TOP_H + BAND_H], fill=255)
    else:
        mask = torn_band_mask(TOP_H, BAND_H)
    canvas.paste(band_layer, (0, 0), mask)

    if args.titulo:
        draw = ImageDraw.Draw(canvas)
        fs = args.fontsize
        font = ImageFont.truetype(BEBAS, fs)
        lines = wrap(draw, args.titulo.upper(), font, W - 2 * PAD_X)
        while len(lines) > 2 and fs > 58:
            fs -= 4
            font = ImageFont.truetype(BEBAS, fs)
            lines = wrap(draw, args.titulo.upper(), font, W - 2 * PAD_X)
        lh = int(fs * 0.92)

        # --- centralizacao vertical REAL via bbox dos glifos ---
        bb0 = draw.textbbox((0, 0), lines[0], font=font)
        bbN = draw.textbbox((0, 0), lines[-1], font=font)
        n = len(lines)
        block_top = bb0[1]                       # espaco acima do 1o glifo
        block_bottom = (n - 1) * lh + bbN[3]     # base do ultimo glifo
        band_center = TOP_H + BAND_H / 2
        ty = int(band_center - (block_top + block_bottom) / 2)

        for i, line in enumerate(lines):
            tw = draw.textbbox((0, 0), line, font=font)[2]
            draw.text(((W - tw) // 2, ty + i * lh), line, font=font, fill=WHITE + (255,))

    canvas.save(args.out, "PNG")
    print(f"  band: Bebas fs={fs if args.titulo else '-'} linhas={len(lines) if args.titulo else 0}")


if __name__ == "__main__":
    main()
