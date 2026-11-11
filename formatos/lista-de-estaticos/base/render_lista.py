#!/usr/bin/env python3
"""Lista de estáticos: pessoa num canto, lista numerada que se preenche e a estática de cada item aparece.
O lado da lista e da estática é decidido pelo ROSTO (OpenCV): pessoa à esquerda -> coluna à direita, e vice-versa;
pessoa no meio -> estática acima da cabeça e lista estreita ao lado (melhor esforço).
Uso: python3 render_lista.py --video bruto.mov --cenas cenas.json --out saida.mp4 [--lado auto|direita|esquerda|centro] [--quadro SEG]
cenas.json: {"titulo": [[texto, "forte"|"normal"], ...], "itens": [{"nome","imagem","t"}], "fim": s, "cortes": [[ini,fim]],
  "estilo": "lista" (padrão: lista que se preenche) | "ao-lado" (sem lista, estática ao lado da cabeça), "palavras": words.json (legenda palavra por palavra, opcional)}
Todos os tempos (itens.t, fim, cortes) estão no tempo do BRUTO; o motor desconta os cortes.
"""
import argparse, json, subprocess, os, tempfile, statistics
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")   # Mac: OpenCL roda no Metal e pode travar a saída do processo
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920
F = "/System/Library/Fonts/Supplemental/"
AMARELO = (255, 214, 10, 255)
def font(n, s): return ImageFont.truetype(F + n, s)

def achar_rosto(video, fim, tmp):
    """Caixa do rosto (x,y,w,h) em coordenadas 1080x1920 e a proporção do bruto, com a mediana de 7 quadros."""
    caixas, dim = [], None
    for k in range(7):
        t = 0.3 + (fim - 0.6) * k / 6
        p = os.path.join(tmp, f"r{k}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", "-vf", "scale=720:-2", p], check=True)
        im = cv2.imread(p); dim = im.shape[1], im.shape[0]
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        r = det.detectMultiScale(g, 1.1, 5, minSize=(40, 40))
        if len(r): caixas.append(max(r, key=lambda b: b[2] * b[3]))
    if not caixas: return None, dim
    m = [statistics.median(c[i] for c in caixas) for i in range(4)]
    return m, dim

def camada_fundo(x0, x1, forte=0.62):
    """Degradê escuro pra ler por cima da estante (x0..x1 = faixa da rampa; escurece o lado cheio)."""
    im = Image.new("L", (W, 1), 0); px = im.load()
    for x in range(W):
        a = min(1, max(0, (x - x0) / (x1 - x0))) if x1 > x0 else min(1, max(0, (x0 - x) / (x0 - x1)))
        px[x, 0] = int(255 * forte * a)
    m = im.resize((W, H))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0)); out.putalpha(m); return out

def png_titulo(linhas, y0):
    """Cada linha é uma lista de trechos [texto, "forte"|"normal"], centralizada junto."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); y = y0
    fn = font("Arial.ttf", 62); ff = font("Arial Rounded Bold.ttf", 68)
    for linha in linhas:
        if isinstance(linha[0], str): linha = [linha]
        larg = [d.textlength(t, font=ff if p == "forte" else fn) for t, p in linha]
        x = (W - sum(larg)) / 2
        for (t, p), w in zip(linha, larg):
            d.text((x, y), t, font=ff if p == "forte" else fn, fill=AMARELO if p == "forte" else (255, 255, 255, 255),
                   stroke_width=5, stroke_fill=(0, 0, 0, 235)); x += w
        y += 92
    return im

def png_lista(itens, n, x0, y0, passo, tam):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f = font("Arial.ttf", tam)
    for i in range(len(itens)):
        y = y0 + i * passo
        if i < n:
            cor = AMARELO if i == n - 1 else (255, 255, 255, 255)
            d.text((x0, y), f"{i+1}. {itens[i]['nome']}", font=f, fill=cor, stroke_width=3, stroke_fill=(0, 0, 0, 220))
        else:
            d.text((x0, y), f"{i+1}.", font=f, fill=(255, 255, 255, 150), stroke_width=3, stroke_fill=(0, 0, 0, 160))
    return im

def png_estatica(path, caixa, x_ref, y0, alinha):
    s = Image.open(path).convert("RGB"); s.thumbnail(caixa, Image.LANCZOS); w, h = s.size
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = {"dir": x_ref - w, "esq": x_ref, "meio": x_ref - w // 2}[alinha]; y = y0 + (caixa[1] - h) // 2
    sombra = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rectangle((30, 34, w + 30, h + 34), fill=(0, 0, 0, 170))
    im.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)), (x - 30, y - 30))
    ImageDraw.Draw(im).rectangle((x - 6, y - 6, x + w + 5, y + h + 5), fill=(255, 255, 255, 255))
    im.paste(s, (x, y)); return im

def png_rotulo_lado(texto, x_ref, y, alinha):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); f = font("Arial Bold.ttf", 40); w = d.textlength(texto, font=f)
    d.text(((x_ref - w) if alinha == "dir" else x_ref, y), texto, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 235))
    return im

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video"); ap.add_argument("--cenas"); ap.add_argument("--out")
    ap.add_argument("--lado", default="auto"); ap.add_argument("--quadro", type=float)
    ap.add_argument("--pasta"); ap.add_argument("--storyboard", action="store_true"); ap.add_argument("--conferir", action="store_true"); ap.add_argument("--saida-dir")
    a = ap.parse_args()
    if a.pasta:   # a pasta do vídeo (sandbox) tem cenas.json com "video" e as imagens ao lado
        a.cenas = a.cenas or os.path.join(a.pasta, "cenas.json"); v = json.load(open(a.cenas))["video"]; a.video = a.video or (v if os.path.isabs(v) else os.path.join(a.pasta, v))
        a.saida_dir = a.saida_dir or (a.pasta if a.storyboard else os.path.join(a.pasta, "qa"))
    import sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "app", "ferramentas"))
    import lista_comum
    if a.conferir: return lista_comum.conferir(a.out, a.saida_dir or os.path.dirname(os.path.abspath(a.out)))
    if a.storyboard:
        c0 = json.load(open(a.cenas)); cs = sorted(c0.get("cortes", []))
        Tt = lambda t: t - sum(min(max(t - i, 0), f - i) for i, f in cs)
        tm = [0.5] + [Tt(it["t"]) + 0.5 for it in c0["itens"]]; lg = ["abertura"] + [f"{k+1}. {it['nome']}" for k, it in enumerate(c0["itens"])]
        return lista_comum.storyboard(os.path.abspath(__file__), a.video, a.cenas, a.saida_dir or os.path.dirname(os.path.abspath(a.cenas)), tm, lg)

    c = json.load(open(a.cenas)); itens = c["itens"]; cortes = sorted(c.get("cortes", []))
    tmp = tempfile.mkdtemp(prefix="lista-")
    def T(t): return t - sum(min(max(t - i, 0), f - i) for i, f in cortes)  # tempo no vídeo cortado
    fim = T(c["fim"])
    cx = None
    caixa, dim = achar_rosto(a.video, c["fim"], tmp)
    esc = H / dim[1]
    if caixa: fx, fy, fw, fh = [v * esc for v in caixa]; cx = (fx + fw / 2) / W if dim[0] / dim[1] > 0.57 else (fx + fw / 2) / (dim[0] * esc)
    lado = a.lado
    if lado == "auto":
        if cx is None: lado = "direita"; print("aviso: rosto não achado, usando coluna à direita")
        else: lado = "direita" if cx < 0.4 else "esquerda" if cx > 0.6 else "centro"
    print("rosto cx=%s -> coluna %s" % (None if cx is None else round(cx, 2), lado))
    topo_cab = (caixa[1] * esc - 0.3 * caixa[3] * esc) if caixa else 780  # testa + cabelo
    # layout (coordenadas 1080x1920)
    titulo_y = 190
    if lado == "direita":   col_x0, col_x1, alinha, x_est = 560, 1040, "dir", 1040; fundo = (480, 640)
    elif lado == "esquerda": col_x0, col_x1, alinha, x_est = 40, 520, "esq", 40; fundo = (600, 440)
    else:                    col_x0, col_x1, alinha, x_est = 40, 330, "meio", W // 2; fundo = None
    if lado != "centro":
        caixa_est = (480, 520); est_y = 560; lista_y = 1100; passo = 56; tam = 38; lista_x = col_x0 + 25
    else:
        alt = max(320, int(topo_cab - 500 - 30)); caixa_est = (640, min(alt, 600)); est_y = 500; lista_y = int(topo_cab); passo = 46; tam = 30; lista_x = 40
    arqs = []
    def salva(im, nome): p = os.path.join(tmp, nome); im.save(p); return p
    base_dir = os.path.dirname(os.path.abspath(a.cenas)); rel = lambda q: q if os.path.isabs(q) else os.path.join(base_dir, q)
    fx, fy, fw, fh = [v * esc for v in caixa] if caixa else (W * 0.3, 760, 420, 420)
    queixo = fy + fh * 1.08; cap_y = int(min(queixo + 70, 1700)); cx_cap = int(fx + fw / 2)
    estilo = c.get("estilo", "lista")
    arqs.append((salva(png_titulo(c["titulo"], titulo_y), "titulo.png"), 0, fim, False))
    if estilo == "ao-lado":
        # sem lista: a estática aparece ao lado da cabeça, com "N. nome" em cima; pessoa no meio → alterna os lados
        if lado == "centro": caixa_est, lados = (300, 420), ["esq", "dir"]
        else: caixa_est, lados = (460, 520), ["dir" if lado == "direita" else "esq"]
        est_y = int(max(330, fy + fh / 2 - caixa_est[1] / 2 - 40))
        for i, it in enumerate(itens):
            t0 = T(it["t"]); t1 = T(itens[i + 1]["t"]) if i + 1 < len(itens) else fim
            al = lados[i % len(lados)]; x_ref = 1045 if al == "dir" else 35; img = rel(it["imagem"])
            arqs.append((salva(png_estatica(img, caixa_est, x_ref, est_y, al), f"e{i+1}.png"), t0, t1, True))
            th = Image.open(img); th.thumbnail(caixa_est); topo = est_y + (caixa_est[1] - th.height) // 2
            arqs.append((salva(png_rotulo_lado(f"{i+1}. {it['nome']}", x_ref, topo - 62, al), f"n{i+1}.png"), t0, t1, True))
    else:
        if fundo: arqs.insert(0, (salva(camada_fundo(*fundo), "fundo.png"), 0, fim, False))
        arqs.append((salva(png_lista(itens, 0, lista_x, lista_y, passo, tam), "l0.png"), 0, T(itens[0]["t"]), False))
        for i, it in enumerate(itens):
            t0 = T(it["t"]); t1 = T(itens[i + 1]["t"]) if i + 1 < len(itens) else fim
            arqs.append((salva(png_lista(itens, i + 1, lista_x, lista_y, passo, tam), f"l{i+1}.png"), t0, t1, False))
            arqs.append((salva(png_estatica(rel(it["imagem"]), caixa_est, x_est, est_y, alinha), f"e{i+1}.png"), t0, t1, True))
    ent = ["-i", a.video]
    for p, *_ in arqs: ent += ["-loop", "1", "-i", p]
    pal = lista_comum.palavras_legenda(rel(c["palavras"]), cortes, T, fim) if c.get("palavras") else None
    if pal: ent += ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x120", "-r", "30", "-i", "pipe:0"]
    # vídeo: corta os trechos, enquadra 9:16 em torno do rosto, escala
    iv = [(0, None)]; ini = 0; segs = []
    for i, f in cortes: segs.append((ini, i)); ini = f
    segs.append((ini, c["fim"] + 0.5))
    fl = []
    n = len(segs)
    fl.append(f"[0:v]split={n}" + "".join(f"[iv{k}]" for k in range(n)) + f";[0:a]asplit={n}" + "".join(f"[ia{k}]" for k in range(n)))
    for k, (i, f) in enumerate(segs):
        fl.append(f"[iv{k}]trim={i}:{f},setpts=PTS-STARTPTS[sv{k}];[ia{k}]atrim={i}:{f},asetpts=PTS-STARTPTS[sa{k}]")
    cat = "".join(f"[sv{k}][sa{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[cv][ca]"
    fl.append(cat)
    ar = dim[0] / dim[1]
    if ar > 0.57:  # bruto mais largo que 9:16: recorta em volta do rosto
        fl.append(f"[cv]crop=ih*9/16:ih:'min(max({(caixa[0]+caixa[2]/2)/dim[0] if caixa else .5}*iw-ih*9/32,0),iw-ih*9/16)':0,scale={W}:{H},setsar=1,format=yuv420p[v0]")
    else:
        fl.append(f"[cv]scale={W}:{H}:flags=lanczos,setsar=1,format=yuv420p[v0]")
    ult = "v0"
    for k, (p, t0, t1, fade) in enumerate(arqs, 1):
        r = f"[{k}:v]format=rgba" + (f",fade=in:st={t0}:d=0.18:alpha=1" if fade else "")
        fl.append(f"{r}[o{k}];[{ult}][o{k}]overlay=0:0:enable='between(t,{t0},{t1})'[v{k}]"); ult = f"v{k}"
    if pal:
        k = len(arqs) + 1; fl.append(f"[{k}:v]format=rgba[leg];[{ult}][leg]overlay=0:{cap_y - 60}[vl]"); ult = "vl"
    if a.quadro is not None: fl.append("[ca]anullsink")
    base = ["ffmpeg", "-v", "error", "-y"] + ent + ["-filter_complex", ";".join(fl)]
    if a.quadro is not None:
        cmd = base + ["-map", f"[{ult}]", "-ss", str(a.quadro), "-frames:v", "1", a.out]
    else:
        cmd = base + ["-map", f"[{ult}]", "-map", "[ca]", "-t", str(fim), "-c:v", "h264_videotoolbox", "-b:v", "12M", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-b:a", "192k", "-shortest", a.out]
    if not pal: subprocess.run(cmd, check=True)
    else:
        pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for q in lista_comum.faixa_legenda(pal, fim, cx_cap): pr.stdin.write(q)
            pr.stdin.close()
        except (BrokenPipeError, OSError): pass
        if pr.wait() != 0: raise SystemExit("ffmpeg falhou")
    print("ok", a.out)

if __name__ == "__main__":
    main()
