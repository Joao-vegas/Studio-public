#!/usr/bin/env python3
"""
Camada de MANCHETES do `anuncio-vegas` aplicada por cima do dividido-mascara.

É a peça que faltava pra "mistura dos dois modelos de anúncio" que o João pediu
(02/09/2026): o dividido-mascara já dá a faixa de b-roll MESCLADA + karaokê +
cards; daqui vem a manchete Bebas disparada por TRIGGER de palavra da fala, com
as CORES SEMÂNTICAS da paleta canônica Vegas e o SFX de impacto — igual ao
anuncio-vegas (manifesto anuncios-odonto.json).

Cores (Cérebro Eu/trabalho/vegas/marca/paleta.md):
  white  -> fala/callout      #FFFFFF
  red    -> dor/alerta        #B4232C
  yellow -> oferta            #D4AF37   (a marca não tem verde: green cai no gold)
  green  -> preço             #D4AF37 + SFX money (cha-ching) no lugar do boom

Uso:
  build-manchete.py --video final.mp4 --words work/words.json --out out.mp4 \
    --manchetes "start|5 ANOS ESTUDANDO O ROSTO|white|2.2;agenda|A AGENDA NÃO ENCHE|red|1.6"

Formato de cada manchete: TRIGGER|TEXTO|COR|HOLD
  TRIGGER = palavra da fala (case/acento-insensível) ou "start" (t=0) ou "@12.5"
  HOLD    = segundos que a manchete fica na tela.
"""
import argparse, os, re, subprocess, sys, tempfile, unicodedata
from PIL import Image, ImageDraw, ImageFont
import json

W, H = 1080, 1920
BEBAS = "/Users/joaomarcospiki/Library/Fonts/BebasNeue-Regular.ttf"
COLORS = {
    "white": (255, 255, 255),
    "red": (180, 35, 44),      # #B4232C
    "yellow": (212, 175, 55),  # #D4AF37
    "green": (212, 175, 55),   # preço -> gold (a marca não tem verde)
}
STROKE = (0, 0, 0)
PAD_X = 80
MAX_LINES = 2


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


def find_trigger(words, trig, after):
    """Primeira palavra que casa o trigger depois de `after` segundos."""
    tn = norm(trig)
    for w in words:
        if w["start"] < after:
            continue
        if norm(w["word"]).startswith(tn) or tn in norm(w["word"]):
            return float(w["start"])
    return None


def render(texto, color, y_base):
    """Manchete Bebas, autofit até MAX_LINES, ancorada pela BASE em y_base."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    max_w = W - 2 * PAD_X
    for size in range(150, 59, -4):
        font = ImageFont.truetype(BEBAS, size)
        space = d.textlength(" ", font=font)
        lines, cur, cw = [], [], 0
        for word in texto.split():
            ww = d.textlength(word, font=font)
            if cur and cw + space + ww > max_w:
                lines.append(cur); cur, cw = [], 0
            cur.append((word, ww)); cw += (space if len(cur) > 1 else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) <= MAX_LINES and all(
            sum(t[1] for t in ln) + space * (len(ln) - 1) <= max_w for ln in lines
        ):
            break
    lh = int(size * 0.92)
    y = y_base - lh * len(lines)
    sw = max(3, size // 22)
    for ln in lines:
        tot = sum(t[1] for t in ln) + space * (len(ln) - 1)
        x = (W - tot) // 2
        for word, ww in ln:
            d.text((x, y), word, font=font, fill=COLORS[color],
                   stroke_width=sw, stroke_fill=STROKE)
            x += ww + space
        y += lh
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--words", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manchetes", required=True, help="TRIGGER|TEXTO|COR|HOLD; ...")
    ap.add_argument("--y", type=int, default=1150, help="base da manchete (px)")
    ap.add_argument("--lead", type=float, default=0.10, help="entra um tico antes da palavra")
    ap.add_argument("--sfx-dir", default="")
    ap.add_argument("--sfx-vol", type=float, default=0.5)
    a = ap.parse_args()

    words = json.load(open(a.words))["words"]
    tmp = tempfile.mkdtemp(prefix="manchete-")

    items, after = [], 0.0
    for i, spec in enumerate([s for s in a.manchetes.split(";") if s.strip()]):
        trig, texto, color, hold = [p.strip() for p in spec.split("|")]
        if trig.lower() == "start":
            t = 0.0
        elif trig.startswith("@"):
            t = float(trig[1:])
        else:
            t = find_trigger(words, trig, after)
            if t is None:
                sys.exit(f"✗ trigger não encontrado na fala: '{trig}'")
        t = max(0.0, t - a.lead)
        after = t + 0.05
        # TEXTO "-" = só o SFX naquele instante (ex: cha-ching no preço quando o
        # card de oferta já está cobrindo a tela e não cabe outra manchete).
        p = None
        if texto != "-":
            p = os.path.join(tmp, f"m{i:02d}.png")
            render(texto, color, a.y).save(p)
        items.append({"png": p, "t": t, "hold": float(hold), "color": color, "texto": texto})
        print(f"  {t:6.2f}s +{hold}s  [{color}] {texto}")

    inputs = ["-i", a.video]
    f, vl, n = "", "[0:v]", 1
    for it in items:
        if it["png"] is None:
            continue
        inputs += ["-loop", "1", "-t", f"{it['hold'] + 0.6:.2f}", "-i", it["png"]]
        s, e = it["t"], it["t"] + it["hold"]
        f += (f"[{n}:v]format=rgba,fade=in:st=0:d=0.12:alpha=1,"
              f"fade=out:st={it['hold'] - 0.2:.2f}:d=0.2:alpha=1,"
              f"setpts=PTS-STARTPTS+{s}/TB[m{n}];")
        f += f"{vl}[m{n}]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})':eof_action=pass[v{n}];"
        vl = f"[v{n}]"; n += 1
    f = f.rstrip(";")

    # SFX: boom em toda manchete, money (cha-ching) na de preço (green)
    amix, af, nmix = "[0:a]", "", 1
    if a.sfx_dir:
        for it in items:
            sfx = os.path.join(a.sfx_dir, "money.mp3" if it["color"] == "green" else "boom.mp3")
            if not os.path.exists(sfx):
                continue
            inputs += ["-i", sfx]
            vol = 0.9 if it["color"] == "green" else a.sfx_vol
            af += f"[{n}:a]adelay={int(it['t']*1000)}|{int(it['t']*1000)},volume={vol}[s{n}];"
            amix += f"[s{n}]"; nmix += 1; n += 1
    if nmix > 1:
        af += f"{amix}amix=inputs={nmix}:duration=first:dropout_transition=0:normalize=0[aout]"
        amap = "[aout]"
        filt = f"{f};{af}"
    else:
        amap = "0:a"
        filt = f

    subprocess.run(["ffmpeg", "-nostdin"] + inputs + [
        "-filter_complex", filt, "-map", vl, "-map", amap,
        "-c:v", "h264_videotoolbox", "-b:v", "8M", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-y", a.out, "-loglevel", "error",
    ], check=True)
    print(f"✓ {a.out}")


if __name__ == "__main__":
    main()
