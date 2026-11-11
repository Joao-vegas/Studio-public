"""Quadradinho que segue o rosto: o vídeo de quem fala encolhe pra um quadro no canto e o
recorte acompanha o rosto enquanto a pessoa fala e se mexe (OpenCV acha o rosto a cada 0,5 s,
o caminho é suavizado e o recorte anda junto). Nasceu no convite do Coaching Jurídico (WSJ, 29-set).

1) Achar os rostos (mesmas coordenadas do quadro da SUA edição, 1080x1920):
     python3 quadradinho.py rostos <video> --out rostos.json [--zoom 1.0] [--passo 0.5]
   Se a edição dá zoom/recorte, passe --zoom igual, ou chame detectar(quadro_pil) no seu loop.

2) No script da edição:
     import sys; sys.path.insert(0, "~/Projetos/Skill/Estúdio/app/ferramentas/motion")
     from quadradinho import Trilha, desenhar
     tr = Trilha("rostos.json", a=8.9, b=21.1, x=517, y=747)   # janela + rosto inicial de quem fala
     ...no quadro t (tela = PIL RGBA 1080x1920 já com o fundo da cena; video = quadro cheio do vídeo):
     desenhar(tela, video, t, tr, k, rect=(640,150,1020,625), nome="Dr. Cliente3",
              cor=cor_hex(ident["papeis"]["destaque"]), cor_nome=cor_hex(ident["papeis"]["fundo"]), fonte="<a .ttf do cliente>")
   k vai de 0 (vídeo em tela cheia) a 1 (quadradinho): anime k SÓ na entrada (ex.: k = ease((t-a)/.6) dentro da janela
   a..b). A volta pra pessoa é corte seco (regra I11 do motion-narrado): em t >= b, k = 0 direto, sem animar a saída.
   Cores e fonte vêm do cliente (identidade.json); sem passar, ficam as do Cliente3 (ouro, navy, Poppins), de onde nasceu.
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
OURO, NAVY = (199, 157, 90), (14, 21, 34)
FONTE_NOME = "/Users/joaomarcospiki/Library/Fonts/Poppins-Bold.ttf"
FONTE_RESERVA = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def cor_hex(h):
    """'#C79D5A' → (199, 157, 90): pra passar a cor do identidade.json do cliente em cor= e cor_nome=."""
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _fonte(caminho, tam):
    for c in (caminho, FONTE_NOME, FONTE_RESERVA):
        if c and Path(c).expanduser().is_file():
            return ImageFont.truetype(str(Path(c).expanduser()), tam)
    return ImageFont.load_default()


def detectar(quadro):
    """Rostos num quadro PIL 1080x1920 → [[cx, cy, largura], ...] ordenados da esquerda pra direita."""
    import cv2
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    g = np.asarray(quadro.convert("L"))
    fs = casc.detectMultiScale(g, 1.1, 6, minSize=(60, 60))
    return sorted([[int(x + w / 2), int(y + h / 2), int(w)] for x, y, w, h in fs])


def rostos(video, out, zoom=1.0, passo=0.5):
    """Varre o vídeo (cover 1080x1920 com zoom central) e grava {t: [[cx, cy, w], ...]}."""
    sw, sh = int(W * zoom) // 2 * 2, int(H * zoom) // 2 * 2
    vf = f"fps={1 / passo},scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={W}:{H}"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    res, i = {}, 0
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3: break
        res[round(i * passo, 2)] = detectar(Image.fromarray(np.frombuffer(b, np.uint8).reshape(H, W, 3)))
        i += 1
    json.dump(res, open(out, "w"))
    return res


class Trilha:
    """Caminho do rosto de UMA pessoa numa janela: segue a detecção mais próxima da anterior e suaviza."""
    def __init__(self, rostos_json, a, b, x, y, wmin=95, salto=230):
        R = {float(k): v for k, v in (json.load(open(rostos_json)) if isinstance(rostos_json, str) else rostos_json).items()}
        pts = []
        for t in sorted(k for k in R if a - .6 <= k <= b + .6):
            cand = [f for f in R[t] if f[2] >= wmin and 400 < f[1] < 1300]
            if cand:
                f = min(cand, key=lambda f: (f[0] - x) ** 2 + (f[1] - y) ** 2)
                if (f[0] - x) ** 2 + (f[1] - y) ** 2 < salto ** 2: x, y = f[0], f[1]
            pts.append((t, x, y))
        if not pts: pts = [(a, x, y), (b, x, y)]
        self.ts = [p[0] for p in pts]
        xs = np.convolve([p[1] for p in pts], np.ones(3) / 3, "same"); ys = np.convolve([p[2] for p in pts], np.ones(3) / 3, "same")
        xs[0], ys[0], xs[-1], ys[-1] = pts[0][1], pts[0][2], pts[-1][1], pts[-1][2]
        self.xs, self.ys = xs, ys

    def em(self, t):
        return float(np.interp(t, self.ts, self.xs)), float(np.interp(t, self.ts, self.ys))


def desenhar(tela, video, t, trilha, k, rect=(640, 150, 1020, 625), nome=None, recorte=(560, 700), cor=OURO, cor_nome=NAVY,
             fonte=None):
    """Encolhe `video` (PIL 1080x1920) de tela cheia (k=0) até o quadradinho `rect` (k=1), recortando em cima do rosto.
    cor (borda e plaquinha), cor_nome (texto do nome) e fonte (.ttf da plaquinha) são do cliente; sem elas, as do Cliente3."""
    hx, hy = trilha.em(t); cw, ch = recorte
    sx = min(max(hx - cw / 2, 0), W - cw); sy = min(max(hy - 230, 0), H - ch)
    src = (sx, sy, sx + cw, sy + ch)
    sb = [src[0] * k, src[1] * k, W + (src[2] - W) * k, H + (src[3] - H) * k]
    db = [rect[0] * k, rect[1] * k, W + (rect[2] - W) * k, H + (rect[3] - H) * k]
    dw, dh = int(db[2] - db[0]), int(db[3] - db[1])
    v = video.resize((dw, dh), Image.BILINEAR, box=tuple(sb)).convert("RGBA")
    r = int(34 * k)
    mk = Image.new("L", (dw, dh), 0); ImageDraw.Draw(mk).rounded_rectangle([0, 0, dw - 1, dh - 1], r, fill=255); v.putalpha(mk)
    if k > .05:
        sh = Image.new("RGBA", (dw + 60, dh + 60), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([30, 36, dw + 30, dh + 36], r, fill=(0, 0, 0, int(160 * k)))
        tela.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)), (int(db[0]) - 30, int(db[1]) - 30))
    tela.alpha_composite(v, (int(db[0]), int(db[1])))
    if k > .05: ImageDraw.Draw(tela).rounded_rectangle(db, r, outline=cor + (int(255 * k),), width=5)
    if nome and k > .6:                                              # plaquinha com o nome
        a = min(1, (k - .6) / .4); d = ImageDraw.Draw(tela); fn = _fonte(fonte, 40)
        tw = fn.getlength(nome) + 50; x0 = (rect[0] + rect[2]) / 2 - tw / 2; y0 = rect[3] - 30
        d.rounded_rectangle([x0, y0, x0 + tw, y0 + 62], 31, fill=cor + (int(255 * a),))
        d.text((x0 + tw / 2, y0 + 31), nome, font=fn, anchor="mm", fill=cor_nome + (int(255 * a),))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "rostos":
        args = sys.argv[2:]; video = args[0]
        out = args[args.index("--out") + 1] if "--out" in args else "rostos.json"
        zoom = float(args[args.index("--zoom") + 1]) if "--zoom" in args else 1.0
        passo = float(args[args.index("--passo") + 1]) if "--passo" in args else 0.5
        res = rostos(video, out, zoom, passo)
        print(f"{len(res)} amostras → {out}")
    else:
        print(__doc__)
