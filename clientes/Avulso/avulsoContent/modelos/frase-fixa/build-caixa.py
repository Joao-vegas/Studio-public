#!/usr/bin/env python3
"""Frase fixa: monta a camada de texto (<sandbox>/camada.json) no formato do editor (app/ferramentas/camada.py).
O desenho da caixa é o do camada.caixa_png (o mesmo da tela "Editar o texto"); este script só decide parâmetros:
estilo (preto|branco), posição (cima y=470 | peito y=1430 | auto pelo rosto, OpenCV) e o tamanho (60 encolhendo até 48
pra caber em 2 linhas; --tamanho fixa).

Uso: python3 build-caixa.py --dir <sandbox> --frase "..." [--estilo preto|branco] [--posicao peito|cima|auto]
       [--cor-caixa #hex --cor-texto #hex --fonte "Barlow SemiBold" --tamanho px --y centro]
       [--saida mp4] [--cliente <Nome>; padrão: o do caminho clientes/<Nome>/] [--png caixa.png]"""
import argparse, json, statistics, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(RAIZ / "app/ferramentas"))
import camada as cam  # noqa: E402

W, H = cam.W, cam.H
Y_PEITO, Y_CIMA = 1430, 470  # peito: abaixo do queixo; cima: acima da cabeça, fora da zona de topo do Instagram (~250 px)
LIMITE_CABECA = H / 3        # topo da cabeça abaixo disso = pessoa baixa no quadro
ESTILOS = {"preto": ("#000000", "#FFFFFF"), "branco": ("#FFFFFF", "#000000")}


def topo_da_cabeca(video, n=7):
    """Mediana do topo da cabeça (px, em 1080x1920) em n quadros; None se não achou rosto."""
    import cv2
    cap = cv2.VideoCapture(str(video)); tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    tops = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(tot * (k + 0.5) / n))
        ok, fr = cap.read()
        if not ok: continue
        cinza = cv2.cvtColor(cv2.resize(fr, (W, H)), cv2.COLOR_BGR2GRAY)
        rostos = det.detectMultiScale(cinza, 1.1, 5, minSize=(200, 200))
        if len(rostos):
            x, y, w, h = max(rostos, key=lambda r: r[2] * r[3])
            tops.append(y - 0.25 * h)  # o detector pega da testa; soma o cabelo
    cap.release()
    return statistics.median(tops) if tops else None


ALTURA_MAX_BLOCO = 450  # caixa de texto de verdade tem até ~4 linhas; faixa maior é a sala escura/clara inteira


def limites_do_texto(centro, ini, fim, escura):
    """(primeira, última) linha com pixel de texto dentro do bloco [ini, fim), ou None se não tem texto.
    Texto = mais de 1,5% da largura central no tom oposto ao do fundo da caixa (>200 numa caixa escura, <55 numa clara)."""
    faixa = centro[ini:fim]
    texto = (faixa > 200) if escura else (faixa < 55)
    linhas = texto.mean(axis=1) > 0.015
    idx = linhas.nonzero()[0]
    if len(idx) == 0: return None
    return ini + int(idx[0]), ini + int(idx[-1]) + 1


def blocos_do_quadro(cinza, folga_px=60):
    """Faixas (y0, y1) de pelo menos 60 px onde mais de 55% dos pixels da largura central são quase pretos (<30)
    ou quase brancos (>225): cara de caixa de texto. Descarta faixa com mais de 450 px e faixa sem texto dentro;
    o que sobra vai do 1º ao último pixel de texto. cinza = matriz H x W (numpy, 1080x1920)."""
    centro = cinza[:, int(W * 0.15):int(W * 0.85)]
    out = []
    for escura, mascara in ((True, centro < 30), (False, centro > 225)):
        linhas = mascara.mean(axis=1) > 0.55
        ini = None
        for y in range(len(linhas) + 1):
            if y < len(linhas) and linhas[y]:
                if ini is None: ini = y
            elif ini is not None:
                if folga_px <= y - ini <= ALTURA_MAX_BLOCO:
                    lim = limites_do_texto(centro, ini, y, escura)
                    if lim: out.append(lim)
                ini = None
    return out


def caixa_queimada(video):
    """Bloco (y0, y1) onde o bruto já tem uma caixa de texto queimada, ou None. Olha 3 quadros (10%, 50%, 90%)
    e só vale o bloco que aparece em pelo menos 2 deles (caixa fixa, não roupa nem parede)."""
    import cv2
    cap = cv2.VideoCapture(str(video)); tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    por_quadro = []
    for k in (0.1, 0.5, 0.9):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(tot * k))
        ok, fr = cap.read()
        if ok: por_quadro.append(blocos_do_quadro(cv2.cvtColor(cv2.resize(fr, (W, H)), cv2.COLOR_BGR2GRAY)))
    cap.release()
    return escolher_bloco(por_quadro)


def escolher_bloco(por_quadro):
    achados = []
    for i, bl in enumerate(por_quadro):
        for b0, b1 in bl:
            outros = [o for j, ol in enumerate(por_quadro) if j != i for o in ol if min(b1, o[1]) - max(b0, o[0]) > 0.5 * (b1 - b0)]
            if outros: achados.append((b0, b1))
    if not achados: return None
    return min(a[0] for a in achados), max(a[1] for a in achados)


def cobrir_bloco(p, bloco, folga=28):
    """Ajusta y e pad_y da caixa nova pra cobrir o bloco inteiro com `folga` px em cima e embaixo."""
    b0, b1 = bloco
    precisa = (b1 - b0) + 2 * folga
    atual = altura_caixa(p)
    q = dict(p)
    if precisa > atual:
        q["pad_y"] = min(120, p["pad_y"] + -(-(precisa - atual) // 2))
    q["y"] = int((b0 + b1) / 2)
    return q


def altura_caixa(p):
    bb = cam.caixa_png(p).getbbox()
    return (bb[3] - bb[1]) if bb else 0


def escolher_y(posicao, video, p):
    if posicao == "cima": return Y_CIMA
    if posicao == "peito": return Y_PEITO
    topo = topo_da_cabeca(video) if video else None  # auto: sem rosto ou sem espaço em cima -> peito
    if topo is not None and topo > LIMITE_CABECA and topo - 40 >= Y_CIMA + altura_caixa({**p, "y": Y_CIMA}) / 2:
        return Y_CIMA
    return Y_PEITO


def cliente_do_caminho(sb):
    """Nome do cliente a partir de clientes/<Nome>/... (nunca um nome fixo)."""
    partes = sb.parts
    return partes[partes.index("clientes") + 1] if "clientes" in partes else "Avulso"


def bordas(sb, video, saida, extra=80):
    """qa/caixa-bordas.jpg: recorte da caixa com `extra` px a mais em cima e embaixo, em 3 instantes (10%, 50%, 90%)."""
    import subprocess, tempfile
    from PIL import Image
    c = json.loads((Path(sb) / "camada.json").read_text(encoding="utf-8"))
    h = altura_caixa(c)
    y0 = max(0, int(c["y"] - h / 2 - extra)); alt = min(H - y0, int(h + 2 * extra))
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(video)]))
    tiras = []
    with tempfile.TemporaryDirectory() as td:
        for k, f in enumerate((0.1, 0.5, 0.9)):
            q = Path(td) / f"{k}.png"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur * f:.2f}", "-i", str(video), "-frames:v", "1", "-vf",
                            f"scale={W}:{H},crop={W}:{alt}:0:{y0}", str(q)], check=True)
            tiras.append(Image.open(q).convert("RGB"))
    folha = Image.new("RGB", (W, alt * 3 + 8), "#888")
    for k, t in enumerate(tiras): folha.paste(t, (0, k * (alt + 4)))
    folha.save(saida, quality=88)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--bordas":
        bordas(*sys.argv[2:5]); sys.exit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--frase", required=True)
    ap.add_argument("--estilo", default="preto", choices=list(ESTILOS))
    ap.add_argument("--posicao", default="auto", choices=["peito", "cima", "auto"])
    ap.add_argument("--cor-caixa"); ap.add_argument("--cor-texto"); ap.add_argument("--fonte")
    ap.add_argument("--tamanho", type=int); ap.add_argument("--y", type=float)
    ap.add_argument("--saida", required=True); ap.add_argument("--cliente"); ap.add_argument("--png")
    a = ap.parse_args()
    import os
    sb = Path(os.path.abspath(a.dir)); rel = lambda x: os.path.relpath(os.path.abspath(x), RAIZ)  # sem seguir symlink
    fundo, cor = ESTILOS[a.estilo]
    p = {"texto": a.frase, "fonte": a.fonte or "Barlow SemiBold", "cor_caixa": a.cor_caixa or fundo, "cor_texto": a.cor_texto or cor}
    p = cam.limpar(p)
    if a.tamanho:
        p["tamanho"] = a.tamanho
    else:  # encolhe de 60 até 48 pra caber em 2 linhas
        from PIL import Image, ImageDraw, ImageFont
        d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        for t in range(60, 47, -2):
            f = ImageFont.truetype(str(cam.PASTA_FONTES / cam.FONTES[p["fonte"]]), t)
            if len(cam._quebrar(d, p["texto"], f, p["largura"] - 2 * p["pad_x"])) <= 2: break
        p["tamanho"] = t
    p["y"] = int(a.y) if a.y is not None else escolher_y(a.posicao, sb / "work/joao.mp4", p)
    bloco = None
    if a.y is None:
        bloco = caixa_queimada(sb / "work/joao.mp4")
        if bloco:
            p = cobrir_bloco(p, bloco)
            print("o bruto já tem texto: aumentei a caixa", file=sys.stderr)
    c = {"video": rel(sb / "work/joao.mp4"), "saida": rel(a.saida), **p, "posicao": a.posicao, "estilo": a.estilo,
         "andamento": [a.cliente or cliente_do_caminho(sb), sb.name.removeprefix("_sandbox-")]}
    (sb / "camada.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.png: cam.caixa_png(c).save(a.png)
    print(json.dumps({"y": p["y"], "tamanho": p["tamanho"], "bruto_com_texto": bool(a.y is None and bloco)}))
