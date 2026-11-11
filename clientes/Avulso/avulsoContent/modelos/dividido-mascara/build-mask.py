#!/usr/bin/env python3
"""
Gera os dois PNGs que criam a MESCLAGEM (não é tela dividida com faixa):

  1. mask (grayscale L): 1080 x JOAO_H. Branco (opaco) em cima, e nas últimas
     FEATHER linhas faz um degradê branco->preto. Usado com `alphamerge` pra dar
     à camada do João uma BORDA ESFUMADA que se dissolve no b-roll de baixo.
  2. shadow (RGBA): 1080 x 1920 transparente, com uma faixa escura suave logo
     ABAIXO da borda esfumada do João -> a "sombra em volta da máscara" que o
     João pediu (dá profundidade, parece que ele flutua sobre o b-roll).

Uso:
  build-mask.py --out-mask mask.png --out-shadow shadow.png \
      [--joao-h 1180] [--feather 170] [--shadow-h 240] [--shadow-alpha 140]
"""
import argparse
from PIL import Image, ImageDraw, ImageFilter

W = 1080


def build_mask(path, joao_h, feather):
    m = Image.new("L", (W, joao_h), 255)
    d = ImageDraw.Draw(m)
    seam = joao_h - feather
    for i in range(feather):
        y = seam + i
        a = int(round(255 * (1 - i / max(1, feather - 1))))
        d.line([(0, y), (W, y)], fill=a)
    m.save(path)
    print(f"  mask  {m.size} feather={feather}")


def build_shadow(path, joao_h, feather, shadow_h, shadow_alpha):
    sh = Image.new("RGBA", (W, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    # sombra começa um pouco ACIMA da borda (onde o João já está bem transparente)
    # e desce, mais escura no topo, sumindo embaixo.
    top = joao_h - feather // 2
    for i in range(shadow_h):
        y = top + i
        if y >= 1920:
            break
        a = int(round(shadow_alpha * (1 - i / max(1, shadow_h - 1))))
        d.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    sh = sh.filter(ImageFilter.GaussianBlur(28))
    sh.save(path)
    print(f"  shadow {sh.size} h={shadow_h} alpha={shadow_alpha}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-mask", required=True)
    ap.add_argument("--out-shadow", required=True)
    ap.add_argument("--joao-h", type=int, default=1180)
    ap.add_argument("--feather", type=int, default=170)
    ap.add_argument("--shadow-h", type=int, default=240)
    ap.add_argument("--shadow-alpha", type=int, default=140)
    args = ap.parse_args()
    build_mask(args.out_mask, args.joao_h, args.feather)
    build_shadow(args.out_shadow, args.joao_h, args.feather,
                 args.shadow_h, args.shadow_alpha)


if __name__ == "__main__":
    main()
