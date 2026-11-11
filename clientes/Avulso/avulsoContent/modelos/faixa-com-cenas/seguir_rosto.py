#!/usr/bin/env python3
"""
seguir_rosto — o bloco de cima acompanha o rosto do João: rosto no meio do bloco o tempo todo.

Acha o rosto a cada 0,5 s (OpenCV), e o recorte só anda quando o rosto sai do centro de verdade (mais de
ZONA px por mais de 1 s): aí DESLIZA até recentralizar (EASE s, suave, nunca corte seco) e fica parado de novo.
Mesmo recorte no render (gerar.sh) e no storyboard (storyboard.py chama y_em()).

    python3 seguir_rosto.py <sandbox>/work/joao.mp4 --joao-h 1056 [--zoom 1.0]
        grava <sandbox>/work/enquadramento.json  {zoom, joao_h, chaves: [[t, y], ...]}
        e imprime a expressão do y do crop pro ffmpeg (t em segundos)
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

W, H = 1080, 1920
PASSO = 0.5      # de quanto em quanto tempo procura o rosto
ALVO = 0.55      # centro do rosto (a caixa do OpenCV centra no nariz) a 55% do bloco: cabelo com folga em cima, queixo longe da faixa
ZONA = 60        # px que o rosto pode sair do centro sem o recorte mexer
ESPERA = 1.0     # s fora da zona antes de recentralizar (mexida rápida não move o quadro)
EASE = 0.8       # s do deslize


def _detectar(video: Path, zoom: float) -> list[tuple[float, float | None]]:
    """[(t, centro_y do rosto no quadro escalado SCW x SCH)] a cada PASSO. None = não achou."""
    import cv2
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    sh = int(H * zoom + 0.5)
    lw, lh = 360, 640                                    # detecta em 1/3 do tamanho (rápido) e reescala
    vf = f"fps={1 / PASSO},crop=ih*9/16:ih:iw/2-ih*9/16/2:0,scale={lw}:{lh}"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf, "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    out, i = [], 0
    while True:
        b = p.stdout.read(lw * lh)
        if len(b) < lw * lh:
            break
        g = np.frombuffer(b, np.uint8).reshape(lh, lw)
        fs = casc.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
        cy = None
        if len(fs):
            x, y, w, h = max(fs, key=lambda r: r[2])
            cy = (y + h / 2) * sh / lh
        out.append((round(i * PASSO, 2), cy))
        i += 1
    p.wait()
    return out


def chaves(pontos, joao_h: int, zoom: float) -> list[list[float]]:
    """Pontos do rosto → chaves [t, y] do recorte: paradas, e rampas de EASE s quando precisa recentralizar."""
    sh = int(H * zoom + 0.5)
    ymax = max(0, sh - joao_h)
    alvo = ALVO * joao_h
    ts = [t for t, _ in pontos]
    cys, ult = [], None
    for _, c in pontos:                                  # buraco na detecção: segura o último
        ult = c if c is not None else ult
        cys.append(ult)
    if not any(c is not None for c in cys):
        return [[0.0, round(min(ymax, max(0, sh / 2 - alvo)))]]
    prim = next(c for c in cys if c is not None)
    cys = [c if c is not None else prim for c in cys]
    k = 5                                                # mediana de 2,5 s tira o tremido
    med = [float(np.median(cys[max(0, i - k // 2):i + k // 2 + 1])) for i in range(len(cys))]
    quer = [min(ymax, max(0.0, c - alvo)) for c in med]
    y = quer[0]
    ch = [[0.0, round(y)]]
    fora_desde = None
    for t, q in zip(ts, quer):
        if abs(q - y) > ZONA:
            fora_desde = t if fora_desde is None else fora_desde
            if t - fora_desde >= ESPERA and t >= ch[-1][0]:
                ch.append([round(t, 2), round(y)])
                y = q
                ch.append([round(t + EASE, 2), round(y)])
                fora_desde = None
        else:
            fora_desde = None
    return ch


def y_em(ch: list[list[float]], t: float) -> float:
    """O y do recorte no instante t (mesma conta da expressão do ffmpeg)."""
    if t <= ch[0][0]:
        return ch[0][1]
    for (t0, y0), (t1, y1) in zip(ch, ch[1:]):
        if t < t1:
            if y0 == y1 or t1 <= t0:
                return y0
            p = (t - t0) / (t1 - t0)
            return y0 + (y1 - y0) * p * p * (3 - 2 * p)
    return ch[-1][1]


def ffmpeg_y(ch: list[list[float]]) -> str:
    """Expressão do y pro crop do ffmpeg (if aninhado; smoothstep p*p*(3-2p) nas rampas, igual ao y_em)."""
    e = f"{ch[-1][1]}"
    for (t0, y0), (t1, y1) in reversed(list(zip(ch, ch[1:]))):
        P = f"((t-{t0})/{t1 - t0:.3f})"
        seg = f"{y0}" if y0 == y1 or t1 <= t0 else f"{y0}+({y1 - y0})*{P}*{P}*(3-2*{P})"
        e = f"if(lt(t,{t1}),{seg},{e})"
    return e


def calcular(video: Path, joao_h: int, zoom: float = 1.0) -> dict:
    """Lê do cache (work/enquadramento.json) se o vídeo e os parâmetros não mudaram; senão detecta e grava."""
    video = Path(video)
    cache = video.parent / "enquadramento.json"
    assinatura = [video.stat().st_size, int(video.stat().st_mtime), joao_h, zoom]
    try:
        d = json.loads(cache.read_text())
        if d.get("assinatura") == assinatura:
            return d
    except Exception:
        pass
    d = {"assinatura": assinatura, "zoom": zoom, "joao_h": joao_h,
         "chaves": chaves(_detectar(video, zoom), joao_h, zoom)}
    cache.write_text(json.dumps(d))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--joao-h", type=int, default=1056)
    ap.add_argument("--zoom", type=float, default=1.0)
    a = ap.parse_args()
    print(ffmpeg_y(calcular(Path(a.video), a.joao_h, a.zoom)["chaves"]))


if __name__ == "__main__":
    main()
