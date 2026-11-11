#!/usr/bin/env python3
"""
Card de FUNDO claro com uma frase-chave grande (estilo flash card do Cliente8).
Full-screen 1080x1920, centralizado. Palavra em *asteriscos* = VERMELHO.

Dois modos:
  --out card.png                 -> um PNG único (card estático)
  --layers-dir DIR               -> bg.png (fundo) + word_000.png, word_001.png ...
                                    (cada token numa camada transparente, na posição
                                    final). Imprime "NWORDS <n>" pro gerar.sh animar
                                    (palavra aparecendo uma a uma + click de mouse).

Uso:
  build-card.py --out card.png --texto "PARECE *MELHOR*" [--fontsize 150]
  build-card.py --layers-dir DIR --texto "PARECE *MELHOR*" [--fontsize 150]
"""
import argparse, json, os, re, unicodedata
from PIL import Image, ImageDraw, ImageFont


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def sync_times(texto, words_json, after):
    """Casa cada palavra visível do card com o start REAL falado (>= after),
    pra o card aparecer EXATAMENTE quando o João fala (nunca adiantar)."""
    vis = [norm(w) for w, _ in tokens(texto)]
    words = json.load(open(words_json))["words"]
    # ponteiro: 1º índice com start >= after-0.5
    p = 0
    while p < len(words) and words[p]["start"] < after - 0.5:
        p += 1
    out = []
    for tk in vis:
        found = None
        q = p
        while q < len(words):
            if norm(words[q]["word"]) == tk or norm(words[q]["word"]).startswith(tk):
                found = words[q]["start"]; p = q + 1; break
            q += 1
        if found is None:
            found = (out[-1] + 0.4) if out else after
        out.append(round(found, 3))
    return out

W, H = 1080, 1920
BEBAS = "/Users/joaomarcospiki/Library/Fonts/BebasNeue-Regular.ttf"
BG = (245, 244, 240)
BLACK = (17, 17, 17)
RED = (180, 35, 44)   # #B4232C — dor/alerta, paleta canônica Vegas
PAD_X = 120


def tokens(text):
    out = []
    for part in re.split(r"(\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("*") and part.endswith("*"):
            out.append((part[1:-1], RED))
        else:
            for w in part.split(" "):
                if w:
                    out.append((w, BLACK))
    return out


def layout(draw, toks, font, max_w):
    """quebra em linhas e devolve posições (x,y,word,color) de cada token."""
    space = draw.textlength(" ", font=font)
    lines, cur, cw = [], [], 0
    for w, c in toks:
        ww = draw.textlength(w, font=font)
        if cur and cw + space + ww > max_w:
            lines.append(cur); cur, cw = [], 0
        cur.append((w, c, ww)); cw += (space if len(cur) > 1 else 0) + ww
    if cur:
        lines.append(cur)
    lh = int(font.size * 1.02)
    total_h = lh * len(lines)
    y = (H - total_h) // 2
    placed = []
    for ln in lines:
        lw = sum(t[2] for t in ln) + space * (len(ln) - 1)
        x = (W - lw) // 2
        for w, c, ww in ln:
            placed.append((int(x), int(y), w, c))
            x += ww + space
        y += lh
    return placed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--layers-dir")
    ap.add_argument("--texto", required=True)
    ap.add_argument("--fontsize", type=int, default=150)
    ap.add_argument("--sync")          # words.json -> imprime tempos reais das palavras
    ap.add_argument("--after", type=float, default=0.0)
    args = ap.parse_args()

    if args.sync:
        ts = sync_times(args.texto, args.sync, args.after)
        print("SYNC " + " ".join(f"{t:.3f}" for t in ts))
        return

    font = ImageFont.truetype(BEBAS, args.fontsize)
    tmp = Image.new("RGB", (W, H)); d0 = ImageDraw.Draw(tmp)
    placed = layout(d0, tokens(args.texto), font, W - 2 * PAD_X)

    if args.layers_dir:
        os.makedirs(args.layers_dir, exist_ok=True)
        bg = Image.new("RGB", (W, H), BG)
        bg.save(os.path.join(args.layers_dir, "bg.png"))
        for i, (x, y, w, c) in enumerate(placed):
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((x, y), w, font=font, fill=c)
            layer.save(os.path.join(args.layers_dir, f"word_{i:03d}.png"))
        print(f"NWORDS {len(placed)}")
    else:
        img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
        for x, y, w, c in placed:
            d.text((x, y), w, font=font, fill=c)
        img.save(args.out)
        print(f"  card '{args.texto}' -> {args.out}")


if __name__ == "__main__":
    main()
