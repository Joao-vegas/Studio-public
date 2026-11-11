#!/usr/bin/env python3
"""
Gera faixa.png 1080x1920 RGBA da Análise de tela: tudo transparente, exceto
- a sombrinha na emenda (degradê escuro dos dois lados da divisão tela/câmera);
- a frase fixa empilhada em faixas que abraçam o texto, alternando branca (texto preto)
  e vermelha (texto branco), centralizada na horizontal e em cima da emenda.

Quebra: "|" na frase força a linha; sem "|", quebra sozinha em até 3 linhas (encolhe a fonte se precisar).
"""
import argparse
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
GILROY = "/Users/joaomarcospiki/Library/Fonts/Gilroy-ExtraBold.otf"
BRANCO = (255, 255, 255)
PRETO = (17, 17, 17)
VERMELHO = (222, 28, 33)   # o mesmo #DE1C21 da faixa do reel-dividido-por-video
MAX_W = 980                # largura máxima da faixa (folga lateral pro IG)
PAD_X, PAD_Y = 20, 13


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def quebrar(draw, texto, fonte, max_w):
    palavras, linhas, cur = texto.split(), [], ""
    for p in palavras:
        teste = (cur + " " + p).strip()
        if draw.textlength(teste, font=fonte) + 2 * PAD_X <= max_w:
            cur = teste
        else:
            if cur:
                linhas.append(cur)
            cur = p
    if cur:
        linhas.append(cur)
    return linhas


def sombra(canvas, corte, alcance, forca):
    """Degradê escuro centrado na emenda: forte no corte, some em `alcance` px pra cima e pra baixo."""
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for y in range(max(0, corte - alcance), min(H, corte + alcance)):
        t = 1 - abs(y - corte) / alcance
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(255 * forca * t * t)))
    canvas.alpha_composite(camada)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--corte", type=int, default=960, help="y da emenda tela/câmera")
    ap.add_argument("--tamanho", type=int, default=64)
    ap.add_argument("--fonte", default=GILROY)
    ap.add_argument("--cor-a", default="#FFFFFF", help="faixa das linhas 1, 3, ...")
    ap.add_argument("--cor-b", default="#DE1C21", help="faixa das linhas 2, 4, ...")
    ap.add_argument("--sombra", type=float, default=0.55, help="0 desliga a sombrinha")
    ap.add_argument("--sombra-alcance", type=int, default=150)
    ap.add_argument("--y", type=int, default=None, help="centro do bloco de texto (padrão: a emenda)")
    a = ap.parse_args()

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if a.sombra > 0:
        sombra(canvas, a.corte, a.sombra_alcance, a.sombra)
    draw = ImageDraw.Draw(canvas)

    texto = a.titulo.upper()
    tam = a.tamanho
    while True:
        fonte = ImageFont.truetype(a.fonte, tam)
        if "|" in texto:
            linhas = [l.strip() for l in texto.split("|") if l.strip()]
        else:
            linhas = quebrar(draw, texto, fonte, MAX_W)
        largo = max(draw.textlength(l, font=fonte) for l in linhas) + 2 * PAD_X
        if (len(linhas) <= 3 and largo <= MAX_W) or tam <= 40:
            break
        tam -= 2

    cap = fonte.getbbox("H")
    cap_h = cap[3] - cap[1]
    linha_h = cap_h + 2 * PAD_Y
    total = linha_h * len(linhas)
    topo = (a.y if a.y is not None else a.corte) - total // 2
    cores = [hexrgb(a.cor_a), hexrgb(a.cor_b)]
    for i, l in enumerate(linhas):
        fundo = cores[i % 2]
        cor_txt = PRETO if sum(fundo) > 600 else BRANCO
        w = draw.textlength(l, font=fonte) + 2 * PAD_X
        x0 = (W - w) / 2
        y0 = topo + i * linha_h
        draw.rectangle([x0, y0, x0 + w, y0 + linha_h], fill=fundo + (255,))
        # baseline pela altura da maiúscula: texto em caixa-alta fica no meio de verdade
        draw.text((W / 2, y0 + PAD_Y + cap_h), l, font=fonte, fill=cor_txt, anchor="ms")

    canvas.save(a.out)
    print(f"{a.out} · {len(linhas)} linha(s) · {tam}px")


if __name__ == "__main__":
    main()
