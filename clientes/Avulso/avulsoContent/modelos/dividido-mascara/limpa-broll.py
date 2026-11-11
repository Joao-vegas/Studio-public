#!/usr/bin/env python3
"""Prepara UMA janela de b-roll pro bloco de baixo do dividido-por-video.

Por que existe: os clipes vêm do YouTube com letterbox/pillarbox que MUDA de
cena pra cena (barra preta em cima numa parte, nas laterais em outra). O
cropdetect de um frame só não pega — sobra preto dentro da faixa.

O que faz: amostra N frames DA JANELA, acha as bordas pretas comuns a TODOS
eles (interseção), corta, e devolve 1080x<h> em modo cover, com o conteúdo
CENTRALIZADO (ou na âncora pedida). Também reporta o brilho médio pra descartar
janela escura demais.
"""
import subprocess, sys, os, argparse, tempfile
import numpy as np
from PIL import Image

def sample(src, ss, dur, n=7):
    d = tempfile.mkdtemp()
    fps = max(n / max(dur, .1), 0.5)
    subprocess.run(["ffmpeg","-v","error","-ss",str(ss),"-t",str(dur),"-i",src,
                    "-vf",f"fps={fps},scale=480:-1,format=gray","-y",f"{d}/f%03d.png"],check=True)
    fs=sorted(os.listdir(d))[:n]
    return [np.asarray(Image.open(f"{d}/{x}"),dtype=np.float32) for x in fs]

def bars(arrs, thr=18):
    h,w = arrs[0].shape
    def run(vals):           # quantas linhas seguidas são pretas em TODOS os frames
        c=0
        for v in vals:
            if v: c+=1
            else: break
        return c
    rows=[np.all([a[i].mean()<thr for a in arrs]) for i in range(h)]
    cols=[np.all([a[:,j].mean()<thr for a in arrs]) for j in range(w)]
    top=run(rows); bot=run(rows[::-1]); left=run(cols); right=run(cols[::-1])
    return top/h, bot/h, left/w, right/w

ap=argparse.ArgumentParser()
ap.add_argument("--src",required=True); ap.add_argument("--ss",type=float,default=0)
ap.add_argument("--dur",type=float,required=True); ap.add_argument("--out",required=True)
ap.add_argument("--h",type=int,default=834); ap.add_argument("--cx",type=float,default=0.5)
ap.add_argument("--cy",type=float,default=0.5); ap.add_argument("--zoom",type=float,default=1.0)
ap.add_argument("--margem",type=int,default=4, help="px extra de segurança em cada borda cortada")
a=ap.parse_args()

W=1080; H=a.h
arrs=sample(a.src,a.ss,a.dur)
t,b,l,r = bars(arrs)
probe=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
                      "stream=width,height","-of","csv=p=0",a.src],capture_output=True,text=True).stdout.strip()
sw,sh=[int(x) for x in probe.split(",")[:2]]
x0=int(sw*l)+ (a.margem if l>0 else 0); x1=sw-int(sw*r)-(a.margem if r>0 else 0)
y0=int(sh*t)+ (a.margem if t>0 else 0); y1=sh-int(sh*b)-(a.margem if b>0 else 0)
cw=max(16,(x1-x0)//2*2); ch=max(16,(y1-y0)//2*2)
brilho=float(np.mean([x.mean() for x in arrs]))
print(f"  {os.path.basename(a.src)}@{a.ss}: barras t={t:.2f} b={b:.2f} l={l:.2f} r={r:.2f} -> crop {cw}x{ch}+{x0}+{y0}  brilho={brilho:.0f}")
vf=(f"crop={cw}:{ch}:{x0}:{y0},"
    f"scale={int(W*a.zoom)}:{int(H*a.zoom)}:force_original_aspect_ratio=increase,"
    f"crop={W}:{H}:(iw-{W})*{a.cx}:(ih-{H})*{a.cy},format=yuv420p,fps=30,setsar=1")
subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",str(a.ss),"-t",str(a.dur),"-i",a.src,
                "-vf",vf,"-an","-r","30","-c:v","libx264","-preset","veryfast","-crf","20",
                "-y",a.out],check=True)
