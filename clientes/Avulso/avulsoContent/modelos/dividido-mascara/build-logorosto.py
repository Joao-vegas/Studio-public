#!/usr/bin/env python3
"""
Card 'LOGO vs ROSTO' (fala: "não compram de uma logo, compram de um rosto").
Fundo claro, 2 colunas: em cima a LOGO preta da marca, embaixo o ROSTO do dono
(círculo) + nome. Emite 3 camadas p/ animar (logos aparecem em 'logo', rostos em
'rosto'):  bg.png, layer_logos.png, layer_faces.png

Uso: build-logorosto.py --logos-dir <dir> --out-dir <dir>
"""
import argparse, os
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1920
BG = (245, 244, 240)
BARLOW = "/Users/joaomarcospiki/Library/Fonts/Barlow-Black.ttf"
COLX = {"L": 300, "R": 780}
LOGO_Y = 760
FACE_Y = 1180
FACE_D = 300


def fit_h(im, h):
    r = h / im.height
    return im.resize((max(1, int(im.width * r)), h), Image.LANCZOS)


def fit_w(im, w):
    r = w / im.width
    return im.resize((w, max(1, int(im.height * r))), Image.LANCZOS)


def circle(im, d):
    im = ImageOps.fit(im.convert("RGB"), (d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d, d), fill=255)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    ImageDraw.Draw(out).ellipse((0, 0, d - 1, d - 1), outline=(17, 17, 17, 255), width=6)
    return out


def paste_center(canvas, im, cx, cy):
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logos-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    L = args.logos_dir
    os.makedirs(args.out_dir, exist_ok=True)

    Image.new("RGB", (W, H), BG).save(os.path.join(args.out_dir, "bg.png"))

    logos = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    apple = fit_h(Image.open(os.path.join(L, "apple.png")).convert("RGBA"), 210)
    ms = fit_w(Image.open(os.path.join(L, "microsoft.png")).convert("RGBA"), 340)
    paste_center(logos, apple, COLX["L"], LOGO_Y)
    paste_center(logos, ms, COLX["R"], LOGO_Y)
    logos.save(os.path.join(args.out_dir, "layer_logos.png"))

    faces = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    jobs = circle(Image.open(os.path.join(L, "jobs.jpg")), FACE_D)
    gates = circle(Image.open(os.path.join(L, "gates.jpg")), FACE_D)
    paste_center(faces, jobs, COLX["L"], FACE_Y)
    paste_center(faces, gates, COLX["R"], FACE_Y)
    d = ImageDraw.Draw(faces)
    font = ImageFont.truetype(BARLOW, 46)
    for name, col in (("STEVE JOBS", "L"), ("BILL GATES", "R")):
        bb = d.textbbox((0, 0), name, font=font)
        d.text((COLX[col] - (bb[2] - bb[0]) / 2, FACE_Y + FACE_D / 2 + 30), name,
               font=font, fill=(17, 17, 17))
    faces.save(os.path.join(args.out_dir, "layer_faces.png"))
    print("LOGOROSTO ok")


if __name__ == "__main__":
    main()
