#!/usr/bin/env python3
"""texto_fora_do_rosto: com o João em tela cheia, a frase (e qualquer texto) nunca cobre o rosto (30-out-2026, Faixa com cenas).

O gerar.py do modelo usa `rostos` + `decidir` pra escolher UMA posição por trecho de tela cheia (acima da cabeça se couber,
senão no peito abaixo do queixo) e grava work/gerado/texto-posicao.json. O conferir_video.py usa `checar` (faixa branca e vermelha
achada no próprio quadro + rosto do OpenCV) pra reprovar texto em cima de olhos, nariz ou boca.

Medidas (caixa do Haar em 1080x1920; ela oscila ±15% de um quadro pro outro): olhos a partir de y+0,25h; queixo em y+1,05h; cabelo em y-0,35h.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

W, H = 1080, 1920
PASSO = 0.25                     # s entre os quadros onde procura o rosto (gerar.py)
OLHOS, QUEIXO, CABELO = 0.25, 1.05, 0.35
FOLGA_CIMA, FOLGA_BAIXO, FOLGA_PADRAO = 24, 36, 24   # px entre o texto e a cabeça, o queixo e o rosto (pra manter a posição de sempre)
TOPO_SEGURO, BASE_SEGURA = 230, 1700                 # fora do perfil (topo) e da legenda do post (base) do Instagram
PADRAO_Y = 1180                                      # centro da frase no peito (a posição de sempre, a do exemplo)
PUNCH_NIVEL, ANCORA_Y = 0.12, 0.5                    # camada.filtro_punch no gerar.py: zoom de 12% em torno do meio do quadro, do ponto de entrada ao de saída
BOCA = 0.90                                          # a conferência cobra até aqui (fundo da boca); só o queixo encostar é tolerado (exemplo-1 a 58 s)
SOBRA_MIN = 12                                       # px de faixa dentro do rosto que reprova (conferência)


def rostos(video: Path, passo: float = PASSO) -> list[dict]:
    """Rosto maior de cada quadro, a cada `passo` s: [{t, x, y, w, h}] em 1080x1920 (o João em tela cheia é o quadro escalado, sem corte)."""
    import cv2
    import numpy as np
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    lw, lh = 360, 640
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={1 / passo},scale={lw}:{lh}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    out, i, k = [], 0, W / lw
    while True:
        b = p.stdout.read(lw * lh)
        if len(b) < lw * lh:
            break
        g = np.frombuffer(b, np.uint8).reshape(lh, lw)
        fs = casc.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
        if len(fs):
            x, y, w, h = max(fs, key=lambda r: r[2])
            out.append({"t": round(i * passo, 2), "x": int(x * k), "y": int(y * k), "w": int(w * k), "h": int(h * k)})
        i += 1
    p.stdout.close()
    p.wait()
    return limpar(out)


def limpar(rs: list[dict]) -> list[dict]:
    """Tira achado fora de escala (estante, livro): tamanho entre 0,5 e 1,8 da mediana."""
    if len(rs) < 3:
        return rs
    hs = sorted(r["h"] for r in rs)
    med = hs[len(hs) // 2]
    return [r for r in rs if 0.5 * med <= r["h"] <= 1.8 * med]


def com_zoom(rs: list[dict], spans: list[tuple[float, float]], nivel: float = PUNCH_NIVEL, ancora_y: float = ANCORA_Y) -> list[dict]:
    """Rostos como aparecem no vídeo: nos quadros dentro de um punch (entrada, saída) o quadro tem zoom em torno de (meio, ancora_y)
    e o rosto cresce. Margem de 0,1 s na rampa."""
    z, ay = 1 + nivel, ancora_y * H
    return [({**r, "x": int(540 + z * (r["x"] - 540)), "y": int(ay + z * (r["y"] - ay)), "w": int(r["w"] * z), "h": int(r["h"] * z)}
             if any(a - 0.1 <= r["t"] <= b + 0.1 for a, b in spans) else r) for r in rs]


def limites(rs: list[dict]) -> dict | None:
    """Pior caso do trecho: cabelo mais alto, olhos mais altos e queixo mais baixo entre os quadros."""
    if not rs:
        return None
    return {"cabelo": round(min(r["y"] - CABELO * r["h"] for r in rs)), "olhos": round(min(r["y"] + OLHOS * r["h"] for r in rs)),
            "queixo": round(max(r["y"] + QUEIXO * r["h"] for r in rs)),
            "x0": min(r["x"] for r in rs), "x1": max(r["x"] + r["w"] for r in rs)}


def decidir(rs: list[dict], alt: int, padrao_y: int = PADRAO_Y) -> dict:
    """Onde a faixa de altura `alt` fica num trecho com o João em tela cheia. Ordem: a posição de sempre (peito, `padrao_y`) se ela
    já está livre do rosto; senão acima da cabeça, se couber abaixo do topo do Instagram; senão no peito, colada abaixo do queixo.
    Devolve {onde: padrao|cima|peito, y: centro, cabe: bool, ...limites}. Sem rosto achado: a posição de sempre."""
    lim = limites(rs)
    if not lim:
        return {"onde": "padrao", "y": padrao_y, "cabe": True, "rosto": False}
    meio = alt // 2
    topo_p, base_p = padrao_y - meio, padrao_y - meio + alt
    if topo_p >= lim["queixo"] + FOLGA_PADRAO or base_p <= lim["olhos"] - FOLGA_PADRAO:
        return {"onde": "padrao", "y": padrao_y, "cabe": True, "rosto": True, **lim}
    base_c = lim["cabelo"] - FOLGA_CIMA
    if base_c - alt >= TOPO_SEGURO:
        return {"onde": "cima", "y": base_c - meio, "cabe": True, "rosto": True, **lim}
    topo_b = lim["queixo"] + FOLGA_BAIXO
    return {"onde": "peito", "y": topo_b + meio, "cabe": topo_b + alt <= BASE_SEGURA, "rosto": True, **lim}


def y_legenda(rs: list[dict], padrao: int = 1420, folga: int = FOLGA_BAIXO, teto: int = 1640) -> int:
    """Topo da legenda do peito: a de sempre (1420), mais embaixo só se o queixo mais baixo pedir."""
    lim = limites(rs)
    return padrao if not lim else int(min(teto, max(padrao, lim["queixo"] + folga)))


# ---------- conferência ----------

def faixa_no_quadro(rgb) -> tuple[int, int, int, int] | None:
    """Caixa (y0, y1, x0, x1) da frase em faixas branca e vermelha (#DE1C21) num quadro RGB de qualquer tamanho; None se não tem.
    Âncora: a faixa vermelha (linha com 12% da largura ou mais de vermelho, 12 linhas seguidas) com faixa branca colada em cima ou embaixo."""
    import numpy as np
    h, w = rgb.shape[:2]
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    verm = (abs(r - 222) <= 22) & (abs(g - 28) <= 26) & (abs(b - 33) <= 26)
    cols = verm.sum(axis=1)
    linhas = cols >= 0.12 * w
    mi = max(6, int(h * 0.012))                                  # altura mínima da faixa vermelha
    ini, y = None, 0
    for y in range(h + 1):
        if y < h and linhas[y]:
            ini = y if ini is None else ini
            continue
        if ini is not None and y - ini >= mi:
            xs = np.where(verm[ini:y].sum(axis=0) >= (y - ini) * 0.15)[0]
            if len(xs) >= 0.18 * w:
                x0, x1 = int(xs.min()), int(xs.max())
                alt = y - ini
                meio = slice(x0 + (x1 - x0) // 5, x1 - (x1 - x0) // 5)
                def branco(yy):
                    if not 0 <= yy < h:
                        return False
                    seg = rgb[yy, meio]
                    return float((seg.min(axis=1) >= 225).mean()) >= 0.85
                sup, inf = branco(ini - 3), branco(y + 2)
                if sup or inf:
                    y0, y1 = ini - (alt if sup else 0), y + (alt if inf else 0)
                    return (max(0, y0), min(h, y1), x0, x1)
        ini = None
    return None


def _quadros(video: Path, passo: float, lw: int = 540, lh: int = 960):
    """(t, quadro RGB lw x lh) a cada `passo` s, em fluxo (um ffmpeg só)."""
    import numpy as np
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={1 / passo},scale={lw}:{lh}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    i, n = 0, lw * lh * 3
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n:
                break
            yield round(i * passo, 2), np.frombuffer(b, np.uint8).reshape(lh, lw, 3)
            i += 1
    finally:
        p.stdout.close()
        p.wait()


def livres_do_plano(plano: dict, dur: float) -> list[tuple[float, float]]:
    """Trechos com o João em tela cheia: o que as janelas (S e C) não cobrem."""
    livres, t0 = [], 0.0
    for j in sorted(plano.get("janelas") or [], key=lambda j: j[0]):
        if j[0] > t0:
            livres.append((t0, float(j[0])))
        t0 = max(t0, float(j[1]))
    if dur > t0:
        livres.append((t0, dur))
    return livres


def checar(video: Path, sandbox: Path, dur: float, passo: float = 0.25) -> tuple[list[str], dict]:
    """Texto em cima do rosto: nos trechos de tela cheia (PLANO.json), a cada `passo` s acha o rosto (OpenCV) e a faixa branca e
    vermelha (no quadro; é o que o João vê) e reprova se ela cobre olhos, nariz ou boca. Legenda do peito: a posição que o gerar.py
    gravou em work/gerado/texto-posicao.json. Sem PLANO.json de Faixa com cenas, não confere."""
    import cv2
    pl = sandbox / "PLANO.json"
    if not pl.is_file():
        return [], {}
    plano = json.loads(pl.read_text(encoding="utf-8"))
    if not (plano.get("frase") and plano.get("janelas")):
        return [], {}
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    leg = []
    pj = sandbox / "work/gerado/texto-posicao.json"
    if pj.is_file():
        try:
            leg = json.loads(pj.read_text(encoding="utf-8")).get("legenda") or []
        except Exception:
            leg = []
    faixa_ate = float(plano.get("faixa_ate", 9.0)) if plano.get("estilo") == "gancho-legenda" else None
    livres = [(a + 0.15, b - 0.15) for a, b in livres_do_plano(plano, dur) if b - a > 0.4]   # fora dos 0,15 s de cada corte de layout
    cobre, medidos = [], 0
    for t, q in _quadros(video, passo):
        if not any(a <= t <= b for a, b in livres):
            continue
        g = cv2.resize(cv2.cvtColor(q, cv2.COLOR_RGB2GRAY), (360, 640), interpolation=cv2.INTER_AREA)   # mesma escala do gerar.py
        fs = casc.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
        if not len(fs):
            continue
        x, y, w, h = max(fs, key=lambda r: r[2])
        k = W / 360
        rosto = (y * k + OLHOS * h * k, y * k + BOCA * h * k, x * k, (x + w) * k)   # y0 (olhos), y1 (fundo da boca), x0, x1
        caixas = []
        fx = faixa_no_quadro(q) if faixa_ate is None or t < faixa_ate else None
        if fx:
            kq = W / q.shape[1]
            caixas.append(("frase", fx[0] * kq, fx[1] * kq, fx[2] * kq, fx[3] * kq))
        for lg in leg:
            if faixa_ate is not None and t >= faixa_ate and lg["t0"] <= t <= lg["t1"]:
                caixas.append(("legenda", lg["y0"], lg["y1"], 90, W - 90))
        medidos += 1
        for nome, y0, y1, x0, x1 in caixas:
            vert = min(y1, rosto[1]) - max(y0, rosto[0])
            horiz = min(x1, rosto[3]) - max(x0, rosto[2])
            if vert > SOBRA_MIN and horiz > 0:
                cobre.append((t, nome))
    av = []
    if cobre:
        por_nome = {}
        for t, nome in cobre:
            por_nome.setdefault(nome, []).append(t)
        for nome, tt in por_nome.items():
            av.append(f"Texto em cima do rosto: a {'frase' if nome == 'frase' else 'legenda'} cobre olhos, nariz ou boca em {tt[0]:.0f} s"
                      + (f" (e mais {len(tt) - 1} quadro(s))" if len(tt) > 1 else ""))
    return av, {"quadros_medidos": medidos, "quadros_cobrindo": len(cobre), "em_s": [t for t, _ in cobre][:12]}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Texto em cima do rosto (Faixa com cenas)")
    ap.add_argument("video", type=Path)
    ap.add_argument("--sandbox", type=Path, required=True)
    a = ap.parse_args()
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(a.video)]))
    av, num = checar(a.video, a.sandbox, d)
    print(json.dumps({"avisos": av, **num}, ensure_ascii=False))
    raise SystemExit(1 if av else 0)


if __name__ == "__main__":
    main()
