#!/usr/bin/env python3
"""
CRONÔMETRO REGRESSIVO no topo (João 19/08): anel de progresso + "M:SS" contando
de trás pra frente ao longo do vídeo inteiro — reforça o "me dá um minuto" da
fala e segura a retenção.

Gera um overlay com alpha (1 PNG por segundo do contador, cada um esticado pra
duração_do_video/segundos) e QUEIMA por cima de um mp4 já pronto.

Uso:
  build-timer.py --video final.mp4 --out final-timer.mp4 [--segundos 60] [--y 300]
"""
import argparse, math, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BEBAS = "/Users/joaomarcospiki/Library/Fonts/BebasNeue-Regular.ttf"

RED = (220, 38, 38, 255)


def frame(path, restante, total, cy, cx, R, STROKE):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = [cx - R, cy - R, cx + R, cy + R]
    # disco de fundo (escuro translúcido) + trilho
    d.ellipse([cx - R - 5, cy - R - 5, cx + R + 5, cy + R + 5], fill=(0, 0, 0, 130))
    d.arc(box, 0, 360, fill=(255, 255, 255, 70), width=STROKE)
    # arco do que RESTA, começando no topo e andando no sentido horário
    frac = max(0.0, min(1.0, restante / total))
    if frac > 0:
        d.arc(box, -90, -90 + 360 * frac, fill=RED, width=STROKE)
    txt = f"{int(restante) // 60}:{int(restante) % 60:02d}"
    font = ImageFont.truetype(BEBAS, int(R * 0.84))
    bb = d.textbbox((0, 0), txt, font=font)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]),
           txt, font=font, fill=(255, 255, 255, 255))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--segundos", type=int, default=60, help="de quanto o relógio parte")
    ap.add_argument("--y", type=int, default=250, help="centro vertical do anel")
    ap.add_argument("--x", type=int, default=100, help="centro horizontal do anel (canto sup. esquerdo)")
    ap.add_argument("--r", type=int, default=42, help="raio do anel")
    a = ap.parse_args()

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nk=1:nw=1", a.video],
                               capture_output=True, text=True).stdout.strip())
    tmp = tempfile.mkdtemp(prefix="timer-")
    n = a.segundos
    step = dur / n                      # 1:00 -> 0:00 exatamente no fim do vídeo
    lista = os.path.join(tmp, "list.txt")
    with open(lista, "w") as fh:
        for i in range(n):
            p = os.path.join(tmp, f"t_{i:03d}.png")
            frame(p, n - i, n, a.y, a.x, a.r, max(4, a.r // 7))
            fh.write(f"file '{p}'\nduration {step:.4f}\n")
        fh.write(f"file '{p}'\n")

    ov = os.path.join(tmp, "timer.mov")
    subprocess.run(["ffmpeg", "-nostdin", "-f", "concat", "-safe", "0", "-i", lista,
                    "-r", "30", "-c:v", "prores_ks", "-profile:v", "4444",
                    "-pix_fmt", "yuva444p10le", "-y", ov, "-loglevel", "error"], check=True)
    subprocess.run(["ffmpeg", "-nostdin", "-i", a.video, "-i", ov,
                    "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass[v]",
                    "-map", "[v]", "-map", "0:a", "-t", f"{dur:.3f}",
                    "-c:v", "h264_videotoolbox", "-b:v", "8M", "-c:a", "copy",
                    "-movflags", "+faststart", "-y", a.out, "-loglevel", "error"], check=True)
    print(f"✓ {a.out}  ({a.segundos}s -> 0 em {dur:.1f}s de vídeo)")


if __name__ == "__main__":
    main()
