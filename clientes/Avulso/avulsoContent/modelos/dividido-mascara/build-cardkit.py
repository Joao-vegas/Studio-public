#!/usr/bin/env python3
"""
Card ESPECIAL de OFERTA/BÔNUS: mesmo fundo claro dos cards do modelo, frase-chave
em cima (Bebas, *palavra* = vermelho) e o MOCKUP do produto (PNG com alpha)
entrando embaixo. Gera o mp4 e o gerar.sh usa como `card:s-e:@arquivo.mp4`.

Dois modos de texto:
  ESTATICO  -> texto inteiro já no fundo (default).
  ANIMADO   -> --times "t1,t2,..." (tempos ABSOLUTOS de cada palavra na fala) +
               --t0 <início do card>: cada palavra entra na hora que o João fala,
               igual aos cards normais (João 19/08: "faz o texto também aparecendo,
               clica clica clica"). Escreve um sidecar <out>.clicks com os offsets
               relativos ao início do card -> o gerar.sh usa pra tocar 1 CLICK por
               palavra (no lugar dos 2 clicks fixos do card de arquivo).

Uso:
  build-cardkit.py --texto "VOCÊ LEVA A CARTILHA DO *PACIENTE PERDIDO*" \
      --mockup /caminho/mock.png --out /caminho/kit.mp4 [--dur 4.4] \
      [--top 400] [--mock-w 940] [--t0 40.4 --times "40.5,40.9,..."]
"""
import argparse, os, re, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BEBAS = "/Users/joaomarcospiki/Library/Fonts/BebasNeue-Regular.ttf"
BG = (245, 244, 240)
BLACK = (17, 17, 17)
RED = (180, 35, 44)   # #B4232C — dor/alerta
GOLD = (212, 175, 55) # #D4AF37 — oferta/preço (a marca não tem verde)
PAD_X = 100


def tokens(text, realce=RED):
    out = []
    for part in re.split(r"(\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("*") and part.endswith("*"):
            for w in part[1:-1].split(" "):
                if w:
                    out.append((w, realce))
        else:
            for w in part.split(" "):
                if w:
                    out.append((w, BLACK))
    return out


def layout(texto, fontsize, top, realce=RED):
    """Devolve (posições das palavras, y_final). posições = (x, y, palavra, cor)."""
    tmp = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(tmp)
    font = ImageFont.truetype(BEBAS, fontsize)
    space = d.textlength(" ", font=font)
    max_w = W - 2 * PAD_X
    lines, cur, cw = [], [], 0
    for w, c in tokens(texto, realce):
        ww = d.textlength(w, font=font)
        if cur and cw + space + ww > max_w:
            lines.append(cur); cur, cw = [], 0
        cur.append((w, c, ww)); cw += (space if cur[:-1] else 0) + ww
    if cur:
        lines.append(cur)
    lh = int(fontsize * 0.95)
    placed, y = [], top
    for ln in lines:
        tot = sum(t[2] for t in ln) + space * (len(ln) - 1)
        x = (W - tot) // 2
        for w, c, ww in ln:
            placed.append((x, y, w, c))
            x += ww + space
        y += lh
    return placed, y, font


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texto", required=True)
    ap.add_argument("--mockup", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dur", type=float, default=3.4)
    ap.add_argument("--fontsize", type=int, default=130)
    ap.add_argument("--top", type=int, default=520)
    ap.add_argument("--mock-w", type=int, default=0, help="largura do mockup (0 = W-60)")
    ap.add_argument("--times", default="", help="tempos ABSOLUTOS das palavras (csv) -> texto animado")
    ap.add_argument("--t0", type=float, default=0.0, help="instante em que o card entra no vídeo")
    ap.add_argument("--realce", choices=["red", "gold"], default="red", help="cor da palavra em *asteriscos* (preço = gold)")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="cardkit-")
    placed, y_end, font = layout(a.texto, a.fontsize, a.top, GOLD if a.realce == "gold" else RED)
    times = [float(x) for x in a.times.split(",") if x.strip()]
    animado = bool(times)

    bg = Image.new("RGB", (W, H), BG)
    if not animado:
        d = ImageDraw.Draw(bg)
        for x, y, w, c in placed:
            d.text((x, y), w, font=font, fill=c)
    bg_p = os.path.join(tmp, "bg.png"); bg.save(bg_p)

    # uma camada por palavra (só no modo animado)
    word_ps = []
    if animado:
        if len(times) != len(placed):
            raise SystemExit(f"✗ --times tem {len(times)} tempos e o texto tem {len(placed)} palavras")
        for i, (x, y, w, c) in enumerate(placed):
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((x, y), w, font=font, fill=c)
            p = os.path.join(tmp, f"word_{i:03d}.png"); layer.save(p)
            word_ps.append(p)

    # mockup centralizado logo abaixo do texto
    mk = Image.open(a.mockup).convert("RGBA")
    tw = a.mock_w if a.mock_w else W - 2 * 30
    mk = mk.resize((tw, int(mk.height * tw / mk.width)), Image.LANCZOS)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    my = y_end + 120
    if my + mk.height > H - 220:
        my = H - 220 - mk.height
    layer.paste(mk, ((W - mk.width) // 2, my), mk)
    mk_p = os.path.join(tmp, "mock.png"); layer.save(mk_p)

    # o mockup entra DEPOIS da última palavra (senão rouba a leitura do texto)
    mk_in = 0.35 if not animado else max(0.35, times[-1] - a.t0 + 0.25)

    inputs = ["-loop", "1", "-t", str(a.dur), "-i", bg_p]
    f = "[0:v]fps=30,format=rgba[v0];"
    vl, n = "[v0]", 1
    for i, p in enumerate(word_ps):
        inputs += ["-loop", "1", "-t", str(a.dur), "-i", p]
        st = max(0.0, times[i] - a.t0)
        f += f"[{n}:v]fps=30,format=rgba,fade=in:st={st:.2f}:d=0.10:alpha=1,setsar=1[w{i}];"
        f += f"{vl}[w{i}]overlay=0:0[vw{i}];"
        vl = f"[vw{i}]"; n += 1
    inputs += ["-loop", "1", "-t", str(a.dur), "-i", mk_p]
    f += (f"[{n}:v]fps=30,format=rgba,fade=in:st={mk_in:.2f}:d=0.35:alpha=1,"
          f"scale=w='iw*(1+0.03*min(1,max(0,(t-{mk_in:.2f})/0.8)))':h=-1:eval=frame[m];")
    f += f"{vl}[m]overlay=x='(W-w)/2':y='(H-h)/2':format=auto[v]"

    subprocess.run(["ffmpeg", "-nostdin"] + inputs + [
        "-filter_complex", f, "-map", "[v]", "-t", str(a.dur), "-r", "30",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-y", a.out, "-loglevel", "error",
    ], check=True)

    if animado:
        offs = [max(0.0, t - a.t0) for t in times]
        with open(a.out + ".clicks", "w") as fh:
            fh.write(" ".join(f"{o:.3f}" for o in offs) + "\n")
        print(f"✓ {a.out}  (animado, {len(offs)} palavras/clicks)")
    else:
        if os.path.exists(a.out + ".clicks"):
            os.remove(a.out + ".clicks")
        print(f"✓ {a.out}")


if __name__ == "__main__":
    main()
