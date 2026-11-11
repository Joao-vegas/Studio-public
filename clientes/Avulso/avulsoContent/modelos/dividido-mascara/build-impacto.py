#!/usr/bin/env python3
# BEAT DE IMPACTO (tela cheia): b-roll forte em 1080x1920 com tratamento DARK
# + texto grande EMBAIXO (Bebas, branco com *palavra* em vermelho).
# Entra no gerar.sh como  card:s-e:@brolls/<nome>.mp4  (o card e overlay de tela
# cheia). Escreve tambem o sidecar .clicks VAZIO -> sem click de mouse.
#
#   build-impacto.py --src brolls/olhodark.mp4 --ss 3.2 --dur 3.4 \
#       --texto "ESPERANDO A SUA *RESPOSTA*" --out brolls/olhao.mp4
import argparse, os, re, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BEBAS = "/Users/joaomarcospiki/Library/Fonts/BebasNeue-Regular.ttf"
WHITE = (245, 244, 240)
RED = (196, 42, 52)
PAD_X = 90

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--ss", default="0")
ap.add_argument("--dur", default="3.0")
ap.add_argument("--texto", default="")
ap.add_argument("--bloco", action="append", default=[],
                help="OFFSET:TEXTO — varios blocos que trocam dentro do clipe, "
                     "acompanhando a FALA (o reel tem que ser legivel SEM SOM)")
ap.add_argument("--texty", type=int, default=1430)   # topo do texto
ap.add_argument("--fontsize", type=int, default=104)
ap.add_argument("--fade", default="0.45")            # quando o texto entra
a = ap.parse_args()


def tokens(t):
    out = []
    for part in re.split(r"(\*[^*]+\*)", t):
        if not part:
            continue
        if part.startswith("*") and part.endswith("*"):
            for w in part[1:-1].split(" "):
                if w:
                    out.append((w, RED))
        else:
            for w in part.split(" "):
                if w:
                    out.append((w, WHITE))
    return out


tmp = tempfile.mkdtemp()


def render_txt(texto, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if texto:
        f = ImageFont.truetype(BEBAS, a.fontsize)
        toks = tokens(texto)
        space = d.textlength(" ", font=f)
        lines, cur, curw = [], [], 0.0
        for w, c in toks:
            ww = d.textlength(w, font=f)
            if cur and curw + space + ww > W - 2 * PAD_X:
                lines.append((cur, curw)); cur, curw = [], 0.0
            cur.append((w, c, ww)); curw += ww + (space if len(cur) > 1 else 0)
        if cur:
            lines.append((cur, curw))
        lh = int(f.size * 1.02)
        y = a.texty - (len(lines) - 1) * lh      # cresce pra CIMA, base fixa
        for ws, tw in lines:
            x = (W - tw) / 2
            for w, c, ww in ws:
                d.text((x, y), w, font=f, fill=c + (255,))
                x += ww + space
            y += lh
    im.save(path)


blocos = []
if a.bloco:
    for i, b in enumerate(a.bloco):
        off, txt = b.split(":", 1)
        png = os.path.join(tmp, f"b{i}.png")
        render_txt(txt, png)
        blocos.append((float(off), txt, png))
elif a.texto:
    png = os.path.join(tmp, "b0.png")
    render_txt(a.texto, png)
    blocos.append((float(a.fade), a.texto, png))

# tratamento DARK + zoom lento; cada bloco de texto entra com fade na sua vez
vf = ("[0:v]scale=-2:1920,crop=1080:1920,"
      "eq=contrast=1.18:brightness=-0.07:saturation=0.7,vignette=PI/4,"
      "fps=30,setsar=1,"
      "zoompan=z='min(1.0+0.006*on/30,1.06)':d=1:x='iw/2-(iw/zoom/2)':"
      "y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[v0];")
inputs = ["ffmpeg", "-nostdin", "-ss", a.ss, "-t", a.dur, "-i", a.src]
prev = "[v0]"
for i, (off, txt, png) in enumerate(blocos):
    inputs += ["-loop", "1", "-t", a.dur, "-i", png]
    end = blocos[i + 1][0] if i + 1 < len(blocos) else float(a.dur)
    vf += f"[{i+1}:v]format=rgba,fade=in:st={off}:d=0.20:alpha=1[t{i}];"
    vf += (f"{prev}[t{i}]overlay=0:0:enable='between(t,{off},{end})'[v{i+1}];")
    prev = f"[v{i+1}]"
vf = vf.rstrip(";")
subprocess.run(inputs + ["-filter_complex", vf, "-map", prev, "-an", "-c:v",
                         "libx264", "-preset", "veryfast", "-crf", "20",
                         "-pix_fmt", "yuv420p", "-y", a.out,
                         "-loglevel", "error"], check=True)
open(a.out + ".clicks", "w").close()   # sem click de mouse
print(f"  {a.out}  ({a.dur}s)  {len(blocos)} bloco(s) de texto")
