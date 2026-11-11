#!/usr/bin/env python3
"""
Gera as legendas da FASE 2 (Cliente8 em tela cheia falando).
Lê o JSON de palavras do Whisper/GROQ (response_format=verbose_json,
timestamp_granularities[]=word) e emite:
  - um PNG por chunk (1080x1920 RGBA transparente, texto branco Barlow Black
    com traçado preto), posicionado UM POUCO ABAIXO DO QUEIXO do Cliente8;
  - um manifest.txt com  png|start|end  (tempos RELATIVOS ao início da fase 2),
    cada chunk segurando até o próximo (legenda sempre presente).

Uso:
  build-legenda.py --words words.json --word-offset 24 --t0 25.74 \
      --out-dir <dir> [--legy 1250] [--fontsize 62] [--maxwords 4]
"""
import argparse, json, os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
# João 31/07: legenda mais SUTIL — Barlow SemiBold (não a Black pesada),
# SEM caixa-alta total (usa a caixa natural da fala), espaçamento MENOR e
# contorno preto MAIS FINO. Vale pra todos os vídeos, não só o da IA.
BARLOW = "/Users/joaomarcospiki/Library/Fonts/Barlow-SemiBold.ttf"
PAD_X = 90
WHITE = (255, 255, 255, 255)
STROKE = (0, 0, 0, 255)
STROKE_W = 5    # contorno mais sutil (era 8, ficava pesado)
# João 31/07: palavras MAIS JUNTAS/alinhadas (o espaço natural ficou largo demais).
# O gap entre palavras = space * SPACE_SCALE (não o espaço cheio da fonte).
SPACE_SCALE = 0.95   # 14/08: com textlength (sem o padding do stroke) 0.5 colava as palavras
WORD_GAP = 0


def line_w(draw, words, font):
    space = draw.textlength(" ", font=font) * SPACE_SCALE
    tot = 0
    for i, w in enumerate(words):
        # largura REAL do glifo (textbbox com stroke soma 2*STROKE_W por palavra
        # e deixava as palavras soltas — João 14/08 pediu "mais juntinhas").
        tot += draw.textlength(w, font=font)
        if i < len(words) - 1:
            tot += space + WORD_GAP
    return tot


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], []
    for w in words:
        if cur and line_w(draw, cur + [w], font) > max_w:
            lines.append(cur); cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def chunk_words(words, maxwords, gap):
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        txt = w["word"].strip()
        end_punct = txt.endswith((".", ",", "!", "?", ";", ":"))
        nxt_gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        if len(cur) >= maxwords or end_punct or nxt_gap > gap:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def render_png(text, path, legy, fontsize):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(BARLOW, fontsize)
    lines = wrap(d, text, font, W - 2 * PAD_X)
    space = d.textlength(" ", font=font) * SPACE_SCALE
    lh = int(fontsize * 1.06)
    y = legy
    for words in lines:
        x = (W - line_w(d, words, font)) // 2
        for i, w in enumerate(words):
            d.text((x, y), w, font=font, fill=WHITE, stroke_width=STROKE_W, stroke_fill=STROKE)
            x += d.textlength(w, font=font) + space + WORD_GAP
        y += lh
    img.save(path, "PNG")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", required=True)
    ap.add_argument("--word-offset", type=float, default=0.0)  # início do wav (abs)
    ap.add_argument("--t0", type=float, required=True)          # switch (abs) = 0 da fase 2
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--legy", type=int, default=1250)
    ap.add_argument("--fontsize", type=int, default=62)
    ap.add_argument("--maxwords", type=int, default=4)
    ap.add_argument("--gap", type=float, default=0.5)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    words = json.load(open(args.words))["words"]
    chunks = chunk_words(words, args.maxwords, args.gap)

    man = open(os.path.join(args.out_dir, "manifest.txt"), "w")
    for i, ch in enumerate(chunks):
        text = " ".join(w["word"].strip() for w in ch)
        start = ch[0]["start"] + args.word_offset - args.t0
        last_end = ch[-1]["end"] + args.word_offset - args.t0
        # NÃO segurar além do fim da fala do chunk + 0.5s (evita legenda parada
        # 'tempo demais' nas pausas). Se o próximo chunk vier antes, corta nele.
        if i + 1 < len(chunks):
            nxt = chunks[i + 1][0]["start"] + args.word_offset - args.t0
            end = min(nxt, last_end + 0.3)
        else:
            end = last_end + 0.4
        start = max(0.0, start)
        png = os.path.join(args.out_dir, f"leg_{i:03d}.png")
        render_png(text, png, args.legy, args.fontsize)
        man.write(f"{png}|{start:.2f}|{end:.2f}\n")
    man.close()
    print(f"  legendas: {len(chunks)} chunks -> {args.out_dir}")


if __name__ == "__main__":
    main()
