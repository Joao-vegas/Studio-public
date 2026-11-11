"""Estudo QUADRO A QUADRO de vídeo de referência: o padrão do Estúdio pra estudar qualquer referência (29-out-2026).

Nasceu do estudo do Loaded Dice feito pro Desenho 3D (formato removido em 29-out-2026): cortar em planos, medir a câmera em todo quadro, tempo por
palavra, quantos quadros a ação vem antes da palavra, tipo de cada transição, som medido, todo número falado com o
quadro dele, e cada afirmação citando o quadro de prova. Tudo grátis e local (OpenCV, ffmpeg, tesseract); a fala só
pelo Groq (sem chave, segue sem fala; nunca transcritor pago).

  estudo_quadros.py estudar <video> [<video> ...] --saida <pasta> [--nome X] [--sem-fala] [--idioma pt|en]
  estudo_quadros.py comparar <estudo_ref (pasta ou estudo.json)> <video_nosso> [--words words.json] [--saida pasta]
  estudo_quadros.py base <estudo (pasta ou estudo.json)>          (qual base de formato a referência pede)

Saída (pasta): estudo.json (métricas por vídeo + conjunto), ESTUDO-QUADROS.md (regras com número e quadro de prova),
folhas/ (folha geral com o segundo marcado + folhas a 30 fps em ±0,3 s de cada transição, movimento forte e número).
Comparar grava COMPARACAO.md + comparacao.json (régua ref × nosso)."""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ensure, ffprobe, gravar_json, hoje, ler_json  # noqa: E402

VERSAO = 1
FOLHAS_MAX = 40
JANELA_S = 0.3               # folha a 30 fps: ±0,3 s em volta do momento


# ───────────────────────────── utilidades ─────────────────────────────

def _np():
    import numpy as np
    return np


def _cv():
    import cv2
    return cv2


def _med(xs, nd=2):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    m = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    return round(float(m), nd)


def _media(xs, nd=2):
    xs = [x for x in xs if x is not None]
    return round(float(sum(xs) / len(xs)), nd) if xs else None


def _pct(a, b, nd=1):
    return round(100.0 * a / b, nd) if b else None


def br(x, nd=1) -> str:
    """Número no jeito do João: vírgula decimal."""
    if x is None:
        return "?"
    if isinstance(x, (int,)) or (isinstance(x, float) and float(x).is_integer() and nd == 0):
        return str(int(x))
    return f"{x:.{nd}f}".replace(".", ",")


def _seg(q: int, fps: float) -> str:
    return br(q / fps, 2) + " s"


def info(video: Path) -> dict:
    i = ffprobe(Path(video)) or {}
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames", "-of", "json", str(video)],
                       capture_output=True, text=True)
    try:
        st = json.loads(r.stdout or "{}").get("streams") or []
    except ValueError:
        st = []
    return {"duracao": float(i.get("duracao") or 0), "fps": float(i.get("fps") or 30) or 30.0,
            "largura": int(i.get("largura") or 0), "altura": int(i.get("altura") or 0),
            "som": any(s.get("codec_type") == "audio" for s in st)}


# ───────────────────────────── 1ª passada: todo quadro ─────────────────────────────

def _quadros(video: Path):
    cv2 = _cv()
    cap = cv2.VideoCapture(str(video))
    while True:
        ok, f = cap.read()
        if not ok:
            break
        yield f
    cap.release()


def medir_quadros(video: Path, fps: float) -> dict:
    """Por quadro: diferença pro anterior (d1), miniatura (pra transição), câmera (LK + afim: escala e translação) e o
    movimento que sobra depois de tirar a câmera (ação de personagem/objeto)."""
    np, cv2 = _np(), _cv()
    minis, d1, cam, acao, brilho, hists = [], [0.0], [None], [0.0], [], []
    ant = None
    ant_pts = None
    for f in _quadros(video):
        h, w = f.shape[:2]
        aw = 180
        ah = max(2, int(round(h * aw / w)))
        g = cv2.cvtColor(cv2.resize(f, (aw, ah), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        mini = cv2.resize(g, (60, max(2, int(round(ah / 3)))), interpolation=cv2.INTER_AREA)
        brilho.append(float(mini.mean()))
        hsv = cv2.cvtColor(cv2.resize(f, (60, max(2, int(round(ah / 3)))), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
        hh = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256])
        hists.append(cv2.normalize(hh, hh).flatten())
        if minis:
            d1.append(float(np.abs(mini.astype(np.float32) - minis[-1].astype(np.float32)).mean()))
        minis.append(mini)
        if ant is not None:
            m = None
            res = 0.0
            if ant_pts is not None and len(ant_pts) >= 12:
                p1, st, _err = cv2.calcOpticalFlowPyrLK(ant, g, ant_pts, None, winSize=(15, 15), maxLevel=2)
                ok = st.reshape(-1) == 1
                a, b = ant_pts.reshape(-1, 2)[ok], p1.reshape(-1, 2)[ok]
                if len(a) >= 10:
                    M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=1.0, maxIters=200)
                    if M is not None:
                        s = float(math.hypot(M[0, 0], M[1, 0]))
                        tx, ty = float(M[0, 2] + (M[0, 0] - 1) * 0), float(M[1, 2])
                        # translação no centro do quadro (tira o efeito da escala em volta da origem)
                        cx, cy = aw / 2, ah / 2
                        pc = M @ np.array([cx, cy, 1.0])
                        tx, ty = float(pc[0] - cx), float(pc[1] - cy)
                        prev = (np.hstack([a, np.ones((len(a), 1))]) @ M.T)
                        r = np.linalg.norm(b - prev, axis=1)
                        res = float(np.percentile(r, 90)) / aw * 100   # % da largura
                        m = {"s": s, "tx": tx / aw * 100, "ty": ty / aw * 100,   # % da largura por quadro
                             "inl": float(inl.mean()) if inl is not None else 0.0}
            cam.append(m)
            acao.append(res)
        ant = g
        ant_pts = cv2.goodFeaturesToTrack(g, maxCorners=220, qualityLevel=0.01, minDistance=6, blockSize=5)
    return {"minis": minis, "d1": d1, "cam": cam, "acao": acao, "brilho": brilho, "hists": hists, "n": len(minis),
            "w_ana": 180}


def _vel(c: dict | None, ah_sobre_aw: float = 16 / 9) -> float | None:
    """Velocidade da câmera em % da largura por quadro: translação + zoom (escala vezes meia diagonal)."""
    if not c:
        return None
    meia_diag = 50 * math.hypot(1, ah_sobre_aw)
    return math.hypot(c["tx"], c["ty"]) + abs(c["s"] - 1) * meia_diag


# ───────────────────────────── transições e planos ─────────────────────────────

def _hdist(q: dict, a: int, b: int) -> float:
    cv2 = _cv()
    return float(cv2.compareHist(q["hists"][a], q["hists"][b], cv2.HISTCMP_BHATTACHARYYA))


def _extensao_dissolve(q: dict, a: int, b: int, lim_a: int, lim_b: int, base=None) -> tuple[int, int]:
    """Onde a mistura começa e termina de verdade: pontas A e B fora da troca, alfa de cada quadro por mínimos quadrados
    (0 = plano velho, 1 = plano novo); conta os quadros com alfa entre 0,06 e 0,94 em volta do miolo."""
    np = _np()
    A, B = max(lim_a, a - 12), min(lim_b, b + 12)
    fA, fB = q["minis"][A].astype(np.float32).ravel(), q["minis"][B].astype(np.float32).ravel()
    d = fB - fA
    den = float(d @ d) or 1.0
    al = {k: float((q["minis"][k].astype(np.float32).ravel() - fA) @ d) / den for k in range(A, B + 1)}
    meio = (a + b) // 2
    ini = fim = meio
    d1 = q["d1"]
    sobe = (lambda k: base is None or d1[k] > max(1.5, 1.5 * float(base[k])))   # o quadro ainda está mudando além da câmera
    while ini - 1 > A and 0.06 < al[ini - 1] < 0.94 and sobe(ini - 1):
        ini -= 1
    while fim + 1 < B and 0.06 < al[fim + 1] < 0.94 and sobe(fim + 1):
        fim += 1
    return min(ini, a + 1), max(fim, b)


def transicoes(q: dict, fps: float) -> list[dict]:
    """Corte seco (1 quadro), dissolve (N quadros que são a mistura das pontas) ou especial (troca de cena em vários
    quadros que não é mistura: chicote, mergulho, zoom que atravessa). Movimento forte dentro do MESMO cenário (cor igual
    nas duas pontas) não é transição."""
    np = _np()
    d1 = np.array(q["d1"], dtype=np.float32)
    n = len(d1)
    minis = q["minis"]
    cand = []
    if n < 3:
        return cand
    base = np.array([np.median(d1[max(1, i - 20): min(n, i + 21)]) for i in range(n)], dtype=np.float32)
    alto = (d1 > np.maximum(3.5, 2.6 * base)) & (np.arange(n) > 0)
    i = 1
    while i < n:
        if not alto[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and alto[j + 1] and j - i < 24:
            j += 1
        a, b = i - 1, j                    # quadro antes da troca e último quadro da troca
        fa, fb = minis[a].astype(np.float32), minis[b].astype(np.float32)
        E = float(np.abs(fb - fa).mean())
        hd = _hdist(q, max(0, a - 1), min(n - 1, b + 1))
        L = j - i + 1
        tipo = None
        mids = []
        for k in range(a + 1, b):
            al = (k - a) / (b - a)
            mids.append(float(np.abs(minis[k].astype(np.float32) - ((1 - al) * fa + al * fb)).mean()))
        razao = (max(mids) / E) if mids and E else 1.0
        if L == 1 and E > 12 and (hd > 0.18 or E > 30):
            tipo = "corte"
        elif L >= 2 and E > 10:
            if L <= 3 and E > 18 and razao > .45 and (hd > 0.18 or E > 30):
                tipo = "corte"            # corte com 1-2 quadros borrados de compressão
            elif razao < 0.36 and hd > 0.12:
                tipo = "dissolve"
            elif E > 22 and hd > 0.3:
                tipo = "especial"
        if tipo:
            cand.append({"a": a, "b": b, "tipo": tipo, "E": E, "hd": hd})
        i = j + 1
    out = []
    for k, c in enumerate(cand):
        a, b = c["a"], c["b"]
        if c["tipo"] == "dissolve":
            lim_a = cand[k - 1]["b"] + 1 if k else 0
            lim_b = cand[k + 1]["a"] - 1 if k + 1 < len(cand) else n - 1
            ini, fim = _extensao_dissolve(q, a, b, lim_a, lim_b, base)
        else:
            ini, fim = a + 1, b
        out.append({"q": int(ini), "q_fim": int(fim), "quadros": int(fim - ini + 1), "tipo": c["tipo"], "s": round(ini / fps, 3),
                    "mudanca": round(c["E"], 1), "cor": round(c["hd"], 2)})
    junt = []
    for t in out:   # dissolve que o limiar partiu em dois pedaços colados: junta
        if junt and t["q"] - junt[-1]["q_fim"] <= 2 and t["tipo"] == junt[-1]["tipo"] == "dissolve":
            junt[-1]["q_fim"] = t["q_fim"]
            junt[-1]["quadros"] = t["q_fim"] - junt[-1]["q"] + 1
            continue
        junt.append(t)
    return junt


def planos(trans: list[dict], n: int, fps: float) -> list[dict]:
    bordas = [0] + [t["q"] for t in trans] + [n]
    out = []
    for k in range(len(bordas) - 1):
        a, b = bordas[k], bordas[k + 1]
        if b - a >= 2:
            out.append({"q": a, "q_fim": b - 1, "s": round(a / fps, 2), "dura_s": round((b - a) / fps, 2)})
    return out


def camera(q: dict, trans: list[dict], pls: list[dict], fps: float, prop: float) -> dict:
    np = _np()
    n = q["n"]
    fora = set()
    for t in trans:
        fora.update(range(t["q"] - 1, t["q_fim"] + 2))
    vel = [(_vel(c, prop) if i not in fora else None) for i, c in enumerate(q["cam"])]
    validos = [(i, v) for i, v in enumerate(vel) if v is not None]
    if not validos:
        return {}
    vs = np.array([v for _, v in validos])
    LIM = 0.012          # % da largura por quadro (~0,36 %/s a 30 fps): abaixo disso é câmera parada (ruído da medida)
    andando = vs > LIM
    zoom = [((c["s"] - 1) * fps * 100) for i, c in enumerate(q["cam"]) if c and i not in fora]
    # entrada do plano: 1ºs 10 quadros vs o resto
    ent, resto = [], []
    for p in pls:
        if p["q_fim"] - p["q"] < 20:
            continue
        e = [vel[i] for i in range(p["q"] + 1, p["q"] + 11) if i < n and vel[i] is not None]
        r = [vel[i] for i in range(p["q"] + 11, p["q_fim"]) if vel[i] is not None]
        if e and r:
            ent.append(float(np.mean(e)))
            resto.append(float(np.median(r)))
    # trecho parado mais longo (quadros seguidos sem câmera, fora de transição)
    maior, cur, ini_maior, ini = 0, 0, 0, 0
    for i, v in enumerate(vel):
        if v is not None and v <= LIM:
            if cur == 0:
                ini = i
            cur += 1
            if cur > maior:
                maior, ini_maior = cur, ini
        else:
            cur = 0
    # 5 momentos de movimento forte, separados por 1 s
    ordem = sorted(validos, key=lambda x: -x[1])
    fortes = []
    for i, v in ordem:
        if all(abs(i - f) > fps for f in fortes):
            fortes.append(i)
        if len(fortes) >= 5:
            break
    creep = [v * fps for v in vs[andando]]
    tipico_q = min(validos, key=lambda x: abs(x[1] * fps - (np.median(creep) if creep else 0)))[0] if creep else None
    return {"pct_quadros_andando": round(100 * float(andando.mean()), 1),
            "creep_pct_s": _med(creep, 2),                                        # % da largura por segundo
            "zoom_pct_s_mediana": _med([abs(z) for z in zoom], 2),
            "entrada_x_resto": round(float(np.median(ent)) / max(1e-6, float(np.median(resto))), 2) if ent else None,
            "parado_max_q": int(maior), "parado_max_em_q": int(ini_maior),
            "fortes_q": [int(i) for i in fortes], "creep_tipico_q": tipico_q,
            "vel_q": [None if v is None else round(v * fps, 2) for v in vel]}


def acao_antes_da_palavra(q: dict, palavras: list[dict], trans: list[dict], fps: float) -> dict:
    """Picos do movimento que sobra depois da câmera (gesto, troca de rosto, objeto) e a palavra que vem logo depois:
    quantos quadros a ação vem ANTES da palavra (positivo = antes)."""
    np = _np()
    if not palavras:
        return {}
    a = np.array(q["acao"], dtype=np.float32)
    n = len(a)
    fora = set()
    for t in trans:
        fora.update(range(t["q"] - 2, t["q_fim"] + 3))
    picos = []
    for i in range(2, n - 2):
        if i in fora:
            continue
        janela = a[max(0, i - 15): i + 16]
        if a[i] >= a[i - 1] and a[i] >= a[i + 1] and a[i] > max(0.6, 3 * float(np.median(janela))):
            if not picos or i - picos[-1] > 6:
                picos.append(i)
    inicios = sorted(int(round(p["start"] * fps)) for p in palavras)

    def casar(ps):
        ld, ex = [], []
        for i in ps:
            prox = next((w for w in inicios if w >= i - 4), None)
            if prox is not None and prox - i <= 12:
                ld.append(prox - i)
                ex.append([i, prox])
        return ld, ex
    leads, exemplos = casar(picos)
    acaso, _ = casar([i + 13 for i in picos if i + 13 < n])        # mesmos picos deslocados: o que daria por acaso
    frac = (lambda ld: sum(1 for x in ld if 1 <= x <= 6) / len(ld) if ld else 0)
    # troca de plano × palavra: quadros entre o começo da troca e o começo da palavra mais perto (+ = palavra depois)
    troca = []
    for tr in trans:
        w = min(inicios, key=lambda x: abs(x - tr["q"])) if inicios else None
        if w is not None and abs(w - tr["q"]) <= 15:
            troca.append(w - tr["q"])
    return {"picos": len(picos), "casados": len(leads), "quadros_antes_mediana": _med(leads, 1),
            "padrao": bool(leads) and frac(leads) - frac(acaso) >= 0.1, "frac_1a6": round(frac(leads), 2),
            "frac_acaso": round(frac(acaso), 2), "exemplos": exemplos[:12],
            "troca_palavra_q_mediana": _med(troca, 1), "troca_casadas": len(troca)}


# ───────────────────────────── fala ─────────────────────────────

def transcrever(video: Path, pasta: Path, idioma: str = "", cliente: str = "") -> list[dict]:
    """Só Groq (o que o Estúdio já usa: corte.py transcrever --groq). Sem chave ou erro: [] (segue sem fala)."""
    alvo = pasta / "words.json"
    if alvo.is_file():
        return _palavras_de(ler_json(alvo, []))
    try:
        import chaves
        from fala import groq_transcrever
        chave = chaves.chave("GROQ_API_KEY", cliente or None)
        if not chave:
            return []
        js = groq_transcrever(video, chave, "", idioma or "")
        gravar_json(alvo, js)
        return _palavras_de(js)
    except Exception as e:  # noqa: BLE001
        (pasta / "fala-erro.txt").write_text(str(e)[:500], encoding="utf-8")
        return []


def _palavras_de(js) -> list[dict]:
    ws = js.get("words") if isinstance(js, dict) else js
    out = []
    for w in ws or []:
        t = str(w.get("word", w.get("w", ""))).strip()
        s, e = w.get("start", w.get("s")), w.get("end", w.get("e"))
        if t and s is not None and e is not None:
            out.append({"word": t, "start": float(s), "end": float(e)})
    return out


def _fim_de_frase(js, palavras) -> list[int]:
    """Índices das palavras que fecham frase: pela pontuação da palavra ou, sem ela, pelo fim do segmento com . ? !"""
    idx = [i for i, w in enumerate(palavras) if re.search(r"[.!?…]$", w["word"])]
    if idx or not isinstance(js, dict):
        return idx
    for s in js.get("segments") or []:
        if re.search(r"[.!?…]\s*$", str(s.get("text", ""))):
            fim = float(s.get("end", 0))
            cand = [i for i, w in enumerate(palavras) if w["end"] <= fim + 0.05]
            if cand:
                idx.append(cand[-1])
    return sorted(set(idx))


def fala(palavras: list[dict], js, dur: float, fps: float) -> dict:
    if not palavras:
        return {}
    n = len(palavras)
    ints = []
    for w in palavras:
        if ints and w["start"] - ints[-1][1] < 0.25:
            ints[-1][1] = max(ints[-1][1], w["end"])
        else:
            ints.append([w["start"], w["end"]])
    voz = sum(b - a for a, b in ints)
    fins = _fim_de_frase(js, palavras)
    pausas = []
    for i in fins:
        if i + 1 < n:
            pausas.append((round(palavras[i + 1]["start"] - palavras[i]["end"], 3), i))
    gaps = [round(palavras[i + 1]["start"] - palavras[i]["end"], 3) for i in range(n - 1)]
    pv = [p for p, _ in pausas]
    tip = min(pausas, key=lambda x: abs(x[0] - (_med(pv, 3) or 0))) if pausas else None
    mx = max(pausas) if pausas else None
    return {"palavras": n, "ppm": round(n / dur * 60, 1) if dur else None,
            "ppm_falando": round(n / voz * 60, 1) if voz else None,
            "voz_pct": _pct(voz, dur), "primeira_palavra_s": round(palavras[0]["start"], 2),
            "pausa_frase_mediana_s": _med(pv, 2), "pausa_frase_max_s": round(mx[0], 2) if mx else None,
            "pausa_tipica_q": int(round(palavras[tip[1]]["end"] * fps)) if tip else None,
            "pausa_max_q": int(round(palavras[mx[1]]["end"] * fps)) if mx else None,
            "frases": len(fins), "pausa_qualquer_mediana_s": _med([g for g in gaps if g > 0.05], 2),
            "texto": " ".join(w["word"] for w in palavras)[:4000]}


def voz_audio(video: Path, palavras: list[dict], js, fps: float) -> dict:
    """Pausa e voz medidas no ÁUDIO (o tempo por palavra do Whisper cola uma palavra na outra e esconde a pausa):
    energia na faixa da voz (300-3400 Hz) a cada 20 ms; 17 dB abaixo do pico da voz (percentil 90) é pausa. Pausa pós-frase = o
    trecho de pausa mais longo logo depois da palavra que fecha a frase. Música = volume nesses trechos de pausa."""
    np = _np()
    if not palavras:
        return {}
    x, sr = _audio(video)
    if not len(x):
        return {}
    hop = int(sr * 0.02)
    nf = len(x) // hop
    fr = x[: nf * hop].reshape(nf, hop)
    S = np.abs(np.fft.rfft(fr * np.hanning(hop), n=512, axis=1)) ** 2
    f = np.fft.rfftfreq(512, 1 / sr)
    banda = 10 * np.log10(S[:, (f > 300) & (f < 3400)].sum(axis=1) + 1e-10)
    total = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-12)
    t = (np.arange(nf) + 0.5) * 0.02
    dentro = np.zeros(nf, dtype=bool)
    for w in palavras:
        dentro[(t >= w["start"]) & (t <= w["end"])] = True
    if dentro.sum() < 10:
        return {}
    vpico = float(np.percentile(banda[dentro], 90))
    fala_on = banda > vpico - 17      # 17 dB abaixo do pico da voz: acima da música (que fica 12-20 dB abaixo)
    # fecha buraco de < 0,1 s (entre sílabas não é pausa)
    on = fala_on.copy()
    k = 0
    while k < nf:
        if not on[k]:
            j = k
            while j < nf and not on[j]:
                j += 1
            if j - k < 5 and k > 0 and j < nf:
                on[k:j] = True
            k = j
        else:
            k += 1
    ini, fim = palavras[0]["start"], palavras[-1]["end"]
    span = (t >= ini) & (t <= fim)
    fins = _fim_de_frase(js, palavras)
    pausas = []
    for i in fins:
        if i + 1 >= len(palavras):
            continue
        te = palavras[i]["end"]
        a, b = int(max(0, (te - 0.3) / 0.02)), int(min(nf, (palavras[i + 1]["start"] + 0.6) / 0.02))
        melhor, cur, ini_m, ini_c = 0, 0, a, a
        for k in range(a, b):
            if not on[k]:
                if cur == 0:
                    ini_c = k
                cur += 1
                if cur > melhor:
                    melhor, ini_m = cur, ini_c
            else:
                cur = 0
        pausas.append((round(melhor * 0.02, 2), int(round(ini_m * 0.02 * fps))))
    pv = [p for p, _ in pausas]
    out = {"voz_pct": _pct(int(on[span].sum()), int(span.sum())), "pausa_frase_mediana_s": _med(pv, 2),
           "pausa_frase_max_s": max(pv) if pv else None, "fonte_pausa": "audio"}
    if pausas:
        tip = min(pausas, key=lambda x: abs(x[0] - (out["pausa_frase_mediana_s"] or 0)))
        out["pausa_tipica_q"] = tip[1]
        out["pausa_max_q"] = max(pausas)[1]
    vazio = span & ~on
    if vazio.sum() >= 10:
        out["musica_db"] = round(float(np.median(total[vazio])), 1)
        out["voz_db"] = round(float(np.median(total[span & on])), 1)
        out["musica_abaixo_da_voz_db"] = round(out["voz_db"] - out["musica_db"], 1)
        out["musica_variacao_db"] = round(float(np.percentile(total[vazio], 90) - np.percentile(total[vazio], 10)), 1)
    return out


# ───────────────────────────── fala × imagem (oração por oração) ─────────────────────────────

def oracoes(palavras: list[dict], js, fps: float) -> list[dict]:
    """Corta a fala em orações: pontuação (. , ; : ! ?), fim de segmento do Whisper ou pausa > 0,25 s."""
    if not palavras:
        return []
    fins = set(_fim_de_frase(js, palavras))
    segfim = []
    if isinstance(js, dict):
        segfim = [float(sg.get("end", 0)) for sg in js.get("segments") or []]
    out, cur = [], []
    for i, w in enumerate(palavras):
        cur.append(w)
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        corta = (prox is None or i in fins or re.search(r"[,;:]$", w["word"]) or prox["start"] - w["end"] > 0.25
                 or any(abs(w["end"] - f) < 0.03 for f in segfim))
        if corta and (len(cur) >= 2 or prox is None):
            out.append({"texto": " ".join(x["word"] for x in cur), "s": round(cur[0]["start"], 2), "e": round(cur[-1]["end"], 2),
                        "q": int(round(cur[0]["start"] * fps)), "q_fim": int(round(cur[-1]["end"] * fps))})
            cur = []
    return out


def fala_imagem(q: dict, trans: list[dict], ors: list[dict], fps: float) -> dict:
    """Para cada oração: a imagem muda com ela? (troca de plano ou evento visível perto da 1ª palavra) e com quantos
    quadros de antecedência (+ = a imagem muda ANTES da palavra). O quadro de prova é o da palavra (q + 2)."""
    np = _np()
    d1 = np.array(q["d1"], dtype=np.float32)
    ac = np.array(q["acao"], dtype=np.float32)
    n = len(d1)
    lin = []
    for o in ors:
        qa = o["q"]
        tr = [t for t in trans if qa - 12 <= t["q"] <= qa + 6]
        lead_tr = (qa - tr[0]["q"]) if tr else None
        j0, j1 = max(1, qa - 12), min(n, qa + 10)
        b0, b1 = max(1, qa - 45), min(n, qa + 45)
        base = float(np.median(d1[b0:b1])) if b1 > b0 else 0.0
        sinal = d1[j0:j1] + 0.5 * ac[j0:j1] if j1 > j0 else np.array([0.0])
        pico = int(j0 + int(np.argmax(sinal))) if j1 > j0 else qa
        ev = bool(sinal.max() > max(2.0, 2.2 * base))
        lin.append({**o, "troca": bool(tr), "troca_tipo": tr[0]["tipo"] if tr else "", "lead_troca_q": lead_tr,
                    "evento": ev, "lead_evento_q": (qa - pico) if ev else None, "imagem_nova": bool(tr) or ev,
                    "quadro_palavra": min(n - 1, qa + 2)})
    leads = [x["lead_troca_q"] if x["troca"] else x["lead_evento_q"] for x in lin if x["imagem_nova"]]
    return {"oracoes": lin, "n": len(lin), "com_troca_pct": _pct(sum(1 for x in lin if x["troca"]), len(lin)),
            "imagem_nova_pct": _pct(sum(1 for x in lin if x["imagem_nova"]), len(lin)),
            "lead_q_mediana": _med([x for x in leads if x is not None], 1),
            "oracao_s_mediana": _med([x["e"] - x["s"] for x in lin], 2)}


def folha_fala_imagem(video: Path, nome: str, fi: dict, pasta: Path, fps: float) -> list[str]:
    """Folha pra conferir fala × imagem: o quadro da palavra de cada oração com a oração escrita embaixo."""
    from PIL import Image, ImageDraw
    lin = fi.get("oracoes") or []
    if not lin:
        return []
    imgs = _pegar(video, {x["quadro_palavra"] for x in lin}, larg=200)
    out = []
    por = 30
    f = _fonte(14)
    for pg in range(0, len(lin), por):
        bloco = lin[pg:pg + por]
        cols = 6
        w, h = 200, 356
        cap = 62
        rows = math.ceil(len(bloco) / cols)
        folha = Image.new("RGB", (w * cols, 40 + rows * (h + cap)), (18, 18, 20))
        dr = ImageDraw.Draw(folha)
        dr.text((8, 8), f"{nome} · fala × imagem: o quadro da palavra (q da 1ª palavra + 2) de cada oração", fill=(255, 255, 255), font=_fonte(20))
        for k, x in enumerate(bloco):
            cx, cy = (k % cols) * w, 40 + (k // cols) * (h + cap)
            arr = imgs.get(x["quadro_palavra"])
            if arr is not None:
                folha.paste(Image.fromarray(arr).resize((w, h)), (cx, cy))
            cor = (120, 230, 120) if x["imagem_nova"] else (255, 120, 90)
            dr.rectangle([cx, cy, cx + w - 1, cy + h - 1], outline=cor, width=2)
            txt = f"{pg + k + 1}. q{x['quadro_palavra']} {br(x['s'], 1)}s " + x["texto"]
            linhas, atual = [], ""
            for pal in txt.split():
                if dr.textlength(atual + " " + pal, font=f) > w - 6:
                    linhas.append(atual)
                    atual = pal
                else:
                    atual = (atual + " " + pal).strip()
            linhas.append(atual)
            for li, l in enumerate(linhas[:3]):
                dr.text((cx + 3, cy + h + 2 + li * 19), l, fill=cor, font=f)
        d = ensure(pasta / "folhas") / f"{nome}-fala-imagem-{pg // por + 1}.jpg"
        folha.save(d, quality=82)
        out.append(f"folhas/{d.name}")
    return out


def tabela_fala_imagem(nome: str, fi: dict, folhas_: list[str], anot: dict | None = None) -> str:
    """Tabela oração por oração: fala · tempo · quadro · imagem muda? · o que aparece · bate. As duas últimas colunas
    vêm da conferência no olho (anot = {n: {"aparece", "bate"}}); sem anotação ficam pra preencher olhando a folha."""
    anot = anot or {}
    L = [f"# Fala × imagem: {nome}", "", f"Folha: {', '.join('`' + x + '`' for x in folhas_)} (verde = a imagem muda com a oração).", "",
         f"{fi['n']} orações · imagem nova em {br(fi['imagem_nova_pct'], 0)}% · troca de plano em {br(fi['com_troca_pct'], 0)}% · "
         f"a imagem muda {br(fi['lead_q_mediana'], 0)} quadro(s) antes da 1ª palavra (mediana).", "",
         "| # | Fala | Tempo | Quadro | Imagem muda (quadros antes) | O que aparece | Bate |", "|---|---|---|---|---|---|---|"]
    for i, x in enumerate(fi["oracoes"], 1):
        a = anot.get(str(i)) or anot.get(i) or {}
        mud = (f"{x['troca_tipo']} ({x['lead_troca_q']:+d})" if x["troca"] else
               (f"evento ({x['lead_evento_q']:+d})" if x["evento"] else "não"))
        L.append(f"| {i} | {x['texto']} | {br(x['s'], 2)} s | q{x['quadro_palavra']} | {mud} | {a.get('aparece', '')} | {a.get('bate', '')} |")
    return "\n".join(L) + "\n"


# ───────────────────────────── números falados ─────────────────────────────

_NUM_PT = ("dois duas tres quatro cinco seis sete oito nove dez onze doze treze quatorze catorze quinze dezesseis dezessete "
           "dezoito dezenove vinte trinta quarenta cinquenta sessenta setenta oitenta noventa cem cento duzentos duzentas "
           "trezentos quatrocentos quinhentos seiscentos setecentos oitocentos novecentos mil milhao milhoes bilhao bilhoes "
           "metade dobro triplo").split()
_NUM_EN = ("two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
           "nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million millions billion billions "
           "half double triple percent").split()
_NUM = set(_NUM_PT + _NUM_EN)
_LIGA = {"e", "and", "a", "por", "cento", "percent", "mil", "thousand", "hundred", "million", "milhoes", "reais"}


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def numeros(palavras: list[dict]) -> list[dict]:
    out = []
    i = 0
    while i < len(palavras):
        t = _sem_acento(re.sub(r"[^\w%$]", "", palavras[i]["word"]))
        if re.search(r"\d", t) or t in _NUM:
            j = i
            while j + 1 < len(palavras):
                u = _sem_acento(re.sub(r"[^\w%$]", "", palavras[j + 1]["word"]))
                if re.search(r"\d", u) or u in _NUM or (u in _LIGA and j + 2 < len(palavras)
                                                         and (re.search(r"\d", palavras[j + 2]["word"]) or
                                                              _sem_acento(re.sub(r"[^\w]", "", palavras[j + 2]["word"])) in _NUM)):
                    j += 1
                else:
                    break
            out.append({"texto": " ".join(w["word"] for w in palavras[i:j + 1]), "s": palavras[i]["start"],
                        "e": palavras[j]["end"]})
            i = j + 1
        else:
            i += 1
    return out


def evento_no_numero(q: dict, nums: list[dict], fps: float) -> None:
    """Cada número: tem mudança visível (objeto que aparece/rola/acende ou plano novo) perto do quadro da palavra?"""
    np = _np()
    d1 = np.array(q["d1"], dtype=np.float32)
    ac = np.array(q["acao"], dtype=np.float32)
    n = len(d1)
    for x in nums:
        qn = int(round(x["s"] * fps))
        x["q"] = qn
        j0, j1 = max(1, qn - 9), min(n, qn + 10)                  # ±0,3 s
        b0, b1 = max(1, qn - 45), min(n, qn + 45)
        base = float(np.median(d1[b0:b1])) if b1 > b0 else 0.0
        sinal = d1[j0:j1] + 0.5 * ac[j0:j1] if j1 > j0 else np.array([0.0])
        pico = int(j0 + int(np.argmax(sinal))) if j1 > j0 else qn
        x["evento"] = bool(sinal.max() > max(2.0, 2.2 * base))
        x["evento_q"] = pico
        x["evento_menos_palavra_q"] = pico - qn


# ───────────────────────────── som ─────────────────────────────

def _audio(video: Path, sr: int = 22050):
    np = _np()
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, timeout=600)
    return np.frombuffer(r.stdout, dtype=np.float32), sr


def lufs(video: Path) -> float | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr or "")
    return float(m[-1]) if m else None


def som(video: Path, palavras: list[dict], dur: float) -> dict:
    np = _np()
    out = {"lufs": lufs(video)}
    x, sr = _audio(video)
    if not len(x):
        return out
    win = int(sr * 0.1)
    nw = len(x) // win
    rms = np.sqrt(np.mean(x[: nw * win].reshape(nw, win) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    t = (np.arange(nw) + 0.5) * 0.1
    if palavras:
        voz = np.zeros(nw, dtype=bool)
        perto = np.zeros(nw, dtype=bool)
        for w in palavras:
            voz[(t >= w["start"] + .03) & (t <= w["end"] - .03)] = True
            perto[(t >= w["start"] - .12) & (t <= w["end"] + .12)] = True
        sem = ~perto & (db > -70)
        if voz.sum() > 5:
            out["voz_db"] = round(float(np.median(db[voz])), 1)
        if sem.sum() >= 3:
            out["pausa_db"] = round(float(np.median(db[sem])), 1)
            out["pausa_db_variacao"] = round(float(np.percentile(db[sem], 90) - np.percentile(db[sem], 10)), 1)
            out["pausa_janelas"] = int(sem.sum())
        if out.get("voz_db") is not None and out.get("pausa_db") is not None:
            out["musica_abaixo_da_voz_db"] = round(out["voz_db"] - out["pausa_db"], 1)
    # efeitos: picos de fluxo espectral largos e com agudo acima do da voz (estimativa)
    n_fft, hop = 1024, 256
    if len(x) > n_fft * 4:
        fr = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop] * np.hanning(n_fft)
        S = np.abs(np.fft.rfft(fr, axis=1)) + 1e-9
        f = np.fft.rfftfreq(n_fft, 1 / sr)
        L = np.log(S)
        fluxo = np.maximum(0, np.diff(L, axis=0))[:, (f > 1500) & (f < 10000)].mean(axis=1)
        agudo = S[1:, f > 5000].sum(axis=1) / (S[1:, (f > 300) & (f < 3000)].sum(axis=1) + 1e-9)
        tt = (np.arange(len(fluxo)) + 1) * hop / sr
        mad = float(np.median(np.abs(fluxo - np.median(fluxo)))) + 1e-9
        lim = float(np.median(fluxo)) + 6 * mad
        ag_lim = float(np.percentile(agudo, 85))
        picos = []
        for k in range(1, len(fluxo) - 1):
            if fluxo[k] > lim and fluxo[k] >= fluxo[k - 1] and fluxo[k] >= fluxo[k + 1] and agudo[k] > ag_lim:
                if not picos or tt[k] - picos[-1] > 0.35:
                    picos.append(float(tt[k]))
        out["efeitos_s"] = [round(p, 2) for p in picos]
        out["efeitos_por_min"] = round(len(picos) / dur * 60, 1) if dur else None
    return out


# ───────────────────────────── legenda (OCR barato) e cara do quadro ─────────────────────────────

def legenda_e_cara(video: Path, palavras: list[dict], dur: float, fps: float, altura: int) -> tuple[dict, dict]:
    """OCR (tesseract) em ~1 quadro a cada 1,5 s; conta só palavra que também foi FALADA (tira texto do cenário).
    Junto mede a cara do quadro (lisura, ruído, saturação, rosto) pra sugerir a base do formato."""
    np, cv2 = _np(), _cv()
    try:
        import pytesseract
    except Exception:  # noqa: BLE001
        pytesseract = None
    faladas = {_sem_acento(re.sub(r"[^\w]", "", w["word"])) for w in palavras}
    faladas.discard("")
    passo = max(1.0, dur / 50)
    alvos = [int(round(k * passo * fps)) for k in range(int(dur / passo)) if k * passo > 0.3]
    cap = cv2.VideoCapture(str(video))
    ys, hs, pv, conta = [], [], [], []
    lisura, ruido, sat, rostos = [], [], [], 0
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    for q in alvos:
        cap.set(cv2.CAP_PROP_POS_FRAMES, q)
        ok, f = cap.read()
        if not ok:
            continue
        H, W = f.shape[:2]
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        g2 = cv2.resize(g, (270, int(270 * H / W)))
        blocos = g2[: g2.shape[0] // 8 * 8, :264].reshape(g2.shape[0] // 8, 8, 33, 8).std(axis=(1, 3))
        lisura.append(float((blocos < 2.5).mean()))
        ruido.append(float(np.median(np.abs(cv2.Laplacian(g2, cv2.CV_32F)))))
        sat.append(float(cv2.cvtColor(cv2.resize(f, (270, int(270 * H / W))), cv2.COLOR_BGR2HSV)[..., 1].mean()))
        fs = face.detectMultiScale(g2, 1.15, 5, minSize=(24, 24))
        if len(fs) and max(w * h for (_, _, w, h) in fs) > 0.02 * g2.size:
            rostos += 1
        if pytesseract is None or not faladas:
            continue
        esc = 2 if H < 1200 else 1
        img = cv2.resize(f, (W * esc, H * esc), interpolation=cv2.INTER_CUBIC) if esc > 1 else f
        try:
            d = pytesseract.image_to_data(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), config="--psm 11",
                                          output_type=pytesseract.Output.DICT)
        except Exception:  # noqa: BLE001
            pytesseract = None
            continue
        achou = 0
        for k, txt in enumerate(d["text"]):
            t = _sem_acento(re.sub(r"[^\w]", "", txt or ""))
            if len(t) >= 2 and t in faladas and float(d["conf"][k]) > 55:
                ys.append((d["top"][k] + d["height"][k] / 2) / (H * esc))
                hs.append(d["height"][k] / (H * esc))
                achou += 1
        if achou:
            pv.append(q)
            conta.append(achou)
    cap.release()
    leg = {}
    if ys:
        leg = {"y_pct": round(100 * _med(ys, 4), 1), "altura_texto_px_1920": round(_med(hs, 4) * 1920, 0),
               "palavras_por_quadro": _med(conta, 1), "quadros_com_legenda_pct": _pct(len(pv), len(alvos)),
               "prova_q": pv[len(pv) // 2]}
    elif pytesseract is None and faladas:
        leg = {"aviso": "sem tesseract"}
    cara = {"lisura": _med(lisura, 3), "ruido": _med(ruido, 2), "saturacao": _med(sat, 1),
            "rosto_pct": _pct(rostos, len(alvos)) if alvos else None}
    return leg, cara


def sugerir_base(cara: dict, cam: dict | None = None) -> dict:
    """Regra de escolha da base (CONTRATO): animação sem pessoa estilo cartoon → sem base pronta (Desenho 3D saiu em 29-out-2026); animação 3D
    "realista feia" estilo jogo antigo (Loaded Dice) → formatos/explicador-3d/base; pessoa gravada → formatos gravados.
    Heurística barata nas medidas do quadro; quem decide de vez é a leitura da referência (IA ou o João)."""
    li, ru, sa, ro = cara.get("lisura"), cara.get("ruido"), cara.get("saturacao"), cara.get("rosto_pct")
    if li is None:
        return {"base": "", "tipo": "?", "porque": "sem quadros medidos"}
    if (ro or 0) >= 60:
        return {"base": "gravado", "tipo": "pessoa gravada",
                "porque": f"rosto de gente em {br(ro, 0)}% dos quadros (ruído de câmera {br(ru, 1)})"}
    if li >= 0.47 and (sa or 0) < 120:
        return {"base": "", "tipo": "animação cartoon (sem base pronta)",
                "porque": f"áreas chapadas de cor (lisura {br(li, 2)}) com cor moderada ({br(sa, 0)}): desenho"}
    return {"base": "formatos/explicador-3d/base", "tipo": "animação 3D realista",
            "porque": f"render 3D com textura e sombra (lisura {br(li, 2)}, ruído {br(ru, 1)}, saturação {br(sa, 0)}): jogo antigo/realista"}


# ───────────────────────────── folhas ─────────────────────────────

def _fonte(tam: int):
    from PIL import ImageFont
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _pegar(video: Path, indices: set[int], larg: int = 180) -> dict:
    cv2 = _cv()
    out = {}
    if not indices:
        return out
    mx = max(indices)
    for i, f in enumerate(_quadros(video)):
        if i in indices:
            h, w = f.shape[:2]
            out[i] = cv2.cvtColor(cv2.resize(f, (larg, int(round(h * larg / w))), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        if i >= mx:
            break
    return out


def _tile(imgs: list, titulo: str, destino: Path, marca: set[int], fps: float, colunas: int = 10) -> Path:
    from PIL import Image, ImageDraw
    if not imgs:
        return destino
    h, w = imgs[0][1].shape[:2]
    linhas = math.ceil(len(imgs) / colunas)
    topo = 34
    folha = Image.new("RGB", (w * colunas, h * linhas + topo + 18 * linhas), (18, 18, 20))
    dr = ImageDraw.Draw(folha)
    dr.text((8, 6), titulo, fill=(255, 255, 255), font=_fonte(20))
    f = _fonte(13)
    for k, (q, arr) in enumerate(imgs):
        x, y = (k % colunas) * w, topo + (k // colunas) * (h + 18)
        folha.paste(Image.fromarray(arr), (x, y))
        cor = (255, 70, 60) if q in marca else (200, 200, 200)
        if q in marca:
            dr.rectangle([x, y, x + w - 1, y + h - 1], outline=cor, width=3)
        dr.text((x + 3, y + h + 1), f"q{q} {br(q / fps, 2)}s", fill=cor, font=f)
    ensure(destino.parent)
    folha.save(destino, quality=82)
    return destino


def folhas(video: Path, nome: str, m: dict, pasta: Path, teto: int = FOLHAS_MAX) -> list[dict]:
    """Folha geral (1 quadro a cada N s, segundo marcado) + folhas a 30 fps (±0,3 s) nas transições, movimento forte e
    números. Devolve [{arquivo, tipo, q}]."""
    fps, n = m["fps"], m["quadros"]
    meia = int(round(JANELA_S * fps))
    pedidos = []          # (tipo, q_centro, titulo)
    nums = m.get("numeros") or []
    n_num, n_mov = max(2, teto // 4), max(1, min(5, teto // 6))
    n_tr = max(2, teto - 1 - n_num - n_mov)
    for x in nums[:n_num]:
        pedidos.append(("numero", x["q"], f"Número falado '{x['texto']}' na palavra q{x['q']} ({br(x['s'], 2)} s) · evento q{x.get('evento_q')}"))
    tr = m.get("transicoes") or []
    escolhidas = []
    for tipo in ("especial", "dissolve", "corte"):
        escolhidas += [t for t in tr if t["tipo"] == tipo][: max(1, n_tr // 3 + (1 if tipo == "corte" else 0))]
    for t in escolhidas[:n_tr]:
        pedidos.append(("transicao", t["q"], f"{t['tipo']} de {t['quadros']} quadro(s) em q{t['q']}-q{t['q_fim']} ({br(t['s'], 2)} s)"))
    for q in (m.get("camera") or {}).get("fortes_q", [])[:n_mov]:
        v = ((m.get("camera") or {}).get("vel_q") or [None] * (q + 1))[q]
        pedidos.append(("movimento", q, f"Câmera forte em q{q} ({br(q / fps, 2)} s): {br(v, 1)} % da largura/s"))
    pedidos = pedidos[: max(0, teto - 1)]
    precisa = set()
    for _, c, _ in pedidos:
        precisa.update(range(max(0, c - meia), min(n, c + meia + 1)))
    passo_g = max(1.0, m["duracao"] / 36)
    gerais = [int(round(k * passo_g * fps)) for k in range(int(m["duracao"] / passo_g) + 1) if int(round(k * passo_g * fps)) < n]
    precisa.update(gerais)
    imgs = _pegar(video, precisa)
    out = []
    g = _tile([(q, imgs[q]) for q in gerais if q in imgs], f"{nome} · 1 quadro a cada {br(passo_g, 1)} s (segundo marcado)",
              pasta / "folhas" / f"{nome}-geral.jpg", set(), fps, colunas=9)
    out.append({"arquivo": f"folhas/{g.name}", "tipo": "geral"})
    for k, (tipo, c, tit) in enumerate(pedidos, 1):
        qs = [q for q in range(max(0, c - meia), min(n, c + meia + 1)) if q in imgs]
        d = _tile([(q, imgs[q]) for q in qs], f"{nome} · {tit} · 30 fps, ±{br(JANELA_S, 1)} s",
                  pasta / "folhas" / f"{nome}-{k:02d}-{tipo}-q{c}.jpg", {c}, fps)
        out.append({"arquivo": f"folhas/{d.name}", "tipo": tipo, "q": c})
    # recorte do quadro de cada número (inteiro, pra ver o objeto)
    if nums:
        cv2 = _cv()
        cap = cv2.VideoCapture(str(video))
        for k, x in enumerate(nums[:max(3, teto // 2)], 1):
            cap.set(cv2.CAP_PROP_POS_FRAMES, x.get("evento_q", x["q"]))
            ok, f = cap.read()
            if ok:
                p = ensure(pasta / "folhas") / f"{nome}-numero-{k:02d}-q{x.get('evento_q', x['q'])}.jpg"
                cv2.imwrite(str(p), f, [cv2.IMWRITE_JPEG_QUALITY, 85])
                x["recorte"] = f"folhas/{p.name}"
        cap.release()
    return out


# ───────────────────────────── estudar um vídeo ─────────────────────────────

def estudar_video(video: Path, pasta: Path, nome: str = "", palavras_js=None, transcrever_fala: bool = True,
                  idioma: str = "", cliente: str = "", teto_folhas: int = FOLHAS_MAX, ors: list | None = None) -> dict:
    video = Path(video)
    nome = nome or re.sub(r"[^\w-]", "", video.stem)[:40] or "video"
    ensure(pasta)
    inf = info(video)
    q = medir_quadros(video, inf["fps"])
    fps, n = inf["fps"], q["n"]
    dur = n / fps if n else inf["duracao"]
    prop = (inf["altura"] / inf["largura"]) if inf["largura"] else 16 / 9
    tr = transicoes(q, fps)
    pls = planos(tr, n, fps)
    cam = camera(q, tr, pls, fps, prop)
    js = None
    if palavras_js is not None:
        js = palavras_js
    elif transcrever_fala and inf["som"]:
        pf = ensure(pasta / "videos" / nome)          # cada vídeo guarda a própria fala (e reaproveita na 2ª vez)
        transcrever(video, pf, idioma, cliente)
        js = ler_json(pf / "words.json", None)
    palavras = _palavras_de(js) if js else []
    fl = fala(palavras, js, dur, fps)
    nums = numeros(palavras)
    evento_no_numero(q, nums, fps)
    sm = som(video, palavras, dur) if inf["som"] else {}
    va = voz_audio(video, palavras, js, fps) if (inf["som"] and palavras) else {}
    if va:
        for k in ("voz_pct", "pausa_frase_mediana_s", "pausa_frase_max_s", "pausa_tipica_q", "pausa_max_q", "fonte_pausa"):
            if k in va:
                fl[k] = va[k]
        for k in ("musica_db", "voz_db", "musica_abaixo_da_voz_db", "musica_variacao_db"):
            if k in va:
                sm[k] = va[k]
    leg, cara = legenda_e_cara(video, palavras, dur, fps, inf["altura"])
    if ors:   # orações do próprio vídeo (o cenas.json: um plano = uma oração)
        ors = [{**o, "q": int(round(o["s"] * fps)), "q_fim": int(round(o["e"] * fps))} for o in ors]
    fi = fala_imagem(q, tr, ors or oracoes(palavras, js, fps), fps) if (palavras or ors) else {}
    durs = [p["dura_s"] for p in pls]
    tipos = {k: [t for t in tr if t["tipo"] == k] for k in ("corte", "dissolve", "especial")}
    d1 = q["d1"]
    loop = None
    if n > 10:
        np = _np()
        loop = round(float(np.abs(q["minis"][0].astype(np.float32) - q["minis"][-1].astype(np.float32)).mean()), 1)
    m = {"video": str(video), "nome": nome, "duracao": round(dur, 2), "fps": fps, "quadros": n,
         "largura": inf["largura"], "altura": inf["altura"], "som_no_arquivo": inf["som"],
         "planos": {"n": len(pls), "por_min": round(len(pls) / dur * 60, 1) if dur else None, "media_s": _media(durs),
                    "mediana_s": _med(durs), "min_s": min(durs) if durs else None, "max_s": max(durs) if durs else None,
                    "lista": pls},
         "transicoes": tr,
         "transicao_resumo": {"corte": len(tipos["corte"]), "dissolve": len(tipos["dissolve"]), "especial": len(tipos["especial"]),
                              "dissolve_quadros_mediana": _med([t["quadros"] for t in tipos["dissolve"]], 1),
                              "dissolve_pct": _pct(len(tipos["dissolve"]), len(tr))},
         "camera": cam,
         "acao": acao_antes_da_palavra(q, palavras, tr, fps),
         "fala": fl, "numeros": nums,
         "numeros_resumo": {"n": len(nums), "por_min": round(len(nums) / dur * 60, 1) if dur else None,
                            "com_evento_pct": _pct(sum(1 for x in nums if x.get("evento")), len(nums)),
                            "evento_menos_palavra_q_mediana": _med([x["evento_menos_palavra_q"] for x in nums if x.get("evento")], 1)},
         "som": sm, "legenda": leg, "cara": cara, "base_sugerida": sugerir_base(cara, cam), "fala_imagem": fi,
         "loop_diferenca_inicio_fim": loop, "brilho_medio": _med(q["brilho"], 1),
         "d1_mediana": _med(d1, 2)}
    m["folhas"] = folhas(video, nome, m, pasta, teto_folhas)
    if fi:
        fo = folha_fala_imagem(video, nome, fi, pasta, fps)
        m["folhas"] += [{"arquivo": x, "tipo": "fala-imagem"} for x in fo]
        d = ensure(pasta / "fala-imagem")
        anot = ler_json(d / f"{nome}.anotado.json", None)
        (d / f"{nome}.md").write_text(tabela_fala_imagem(nome, fi, fo, anot), encoding="utf-8")
    return m


# ───────────────────────────── conjunto + regras ─────────────────────────────

CHAVES = [  # (rotulo, caminho, unidade, casas, tolerancia relativa pra "ok" no comparar)
    ("Plano: mediana", "planos.mediana_s", "s", 2, 0.35),
    ("Plano: média", "planos.media_s", "s", 2, 0.4),
    ("Planos por minuto", "planos.por_min", "/min", 1, 0.35),
    ("Transição dissolve", "transicao_resumo.dissolve_pct", "% das trocas", 0, 0.3),
    ("Dissolve: quadros", "transicao_resumo.dissolve_quadros_mediana", "quadros", 1, 0.35),
    ("Câmera andando", "camera.pct_quadros_andando", "% dos quadros", 0, 0.2),
    ("Creep típico", "camera.creep_pct_s", "% da largura/s", 2, 0.6),
    ("Entrada do plano × resto", "camera.entrada_x_resto", "×", 2, 0.5),
    ("Maior trecho parado", "camera.parado_max_q", "quadros", 0, 1.0),
    ("Fala", "fala.ppm", "palavras/min", 0, 0.15),
    ("Voz no tempo", "fala.voz_pct", "%", 0, 0.1),
    ("Pausa pós-frase: mediana", "fala.pausa_frase_mediana_s", "s", 2, 0.5),
    ("Pausa pós-frase: máx", "fala.pausa_frase_max_s", "s", 2, 0.6),
    ("Troca de plano × palavra", "acao.troca_palavra_q_mediana", "quadros", 1, 1.0),
    ("Ação antes da palavra", "acao.quadros_antes_mediana", "quadros", 1, 0.6),
    ("Oração com imagem nova", "fala_imagem.imagem_nova_pct", "% das orações", 0, 0.2),
    ("Oração com troca de plano", "fala_imagem.com_troca_pct", "% das orações", 0, 0.35),
    ("Imagem muda antes da palavra", "fala_imagem.lead_q_mediana", "quadros", 1, 1.0),
    ("Números falados", "numeros_resumo.por_min", "/min", 1, 0.6),
    ("Número com evento visual", "numeros_resumo.com_evento_pct", "%", 0, 0.25),
    ("Volume (LUFS integrado)", "som.lufs", "LUFS", 1, 0.08),
    ("Música abaixo da voz", "som.musica_abaixo_da_voz_db", "dB", 1, 0.35),
    ("Efeitos (estimativa)", "som.efeitos_por_min", "/min", 1, 0.5),
    ("Legenda: altura do centro", "legenda.y_pct", "% da altura", 0, 0.08),
    ("Legenda: altura do texto", "legenda.altura_texto_px_1920", "px em 1920", 0, 0.35),
    ("Legenda: palavras na tela", "legenda.palavras_por_quadro", "palavras", 1, 0.5),
]


def _pega(m: dict, cam: str):
    v = m
    for k in cam.split("."):
        v = v.get(k) if isinstance(v, dict) else None
        if v is None:
            return None
    return v


def conjunto(vids: list[dict]) -> dict:
    out = {}
    for rot, cam, un, nd, _tol in CHAVES:
        vals = [_pega(m, cam) for m in vids]
        vals = [v for v in vals if isinstance(v, (int, float))]
        out[cam] = {"rotulo": rot, "unidade": un, "mediana": _med(vals, nd), "min": min(vals) if vals else None,
                    "max": max(vals) if vals else None, "n": len(vals)}
    bases = [m["base_sugerida"]["base"] for m in vids if m.get("base_sugerida", {}).get("base")]
    out["base_sugerida"] = max(set(bases), key=bases.count) if bases else ""
    return out


def _prova(vids: list[dict], cam: str, alvo) -> dict:
    """O vídeo cujo valor está mais perto da mediana do conjunto: é dele que sai o quadro de prova."""
    cand = [m for m in vids if isinstance(_pega(m, cam), (int, float))]
    if not cand or alvo is None:
        return vids[0]
    return min(cand, key=lambda m: abs(_pega(m, cam) - alvo))


def regras(estudo: dict) -> list[dict]:
    """Regras com número, cada uma com o quadro de prova. Só sai regra do que foi medido."""
    vids, cj = estudo["videos"], estudo["conjunto"]
    R = []

    def v(cam):
        return (cj.get(cam) or {}).get("mediana")

    def add(id_, titulo, texto, prova):
        R.append({"id": id_, "titulo": titulo, "texto": texto, "prova": prova})

    if v("planos.mediana_s") is not None:
        m = _prova(vids, "planos.mediana_s", v("planos.mediana_s"))
        pl = min(m["planos"]["lista"], key=lambda p: abs(p["dura_s"] - v("planos.mediana_s")))
        add("plano", "Duração do plano",
            f"Plano de {br(v('planos.mediana_s'), 2)} s na mediana (média {br(v('planos.media_s'), 2)} s; "
            f"{br(v('planos.por_min'), 0)} planos por minuto). Imagem nova a cada ~{br(v('planos.mediana_s'), 1)} s.",
            f"{m['nome']} q{pl['q']}-q{pl['q_fim']} ({br(pl['s'], 2)} s, {br(pl['dura_s'], 2)} s)")
    if v("transicao_resumo.dissolve_pct") is not None:
        m = _prova(vids, "transicao_resumo.dissolve_pct", v("transicao_resumo.dissolve_pct"))
        ds = [t for t in m["transicoes"] if t["tipo"] == "dissolve"]
        ct = [t for t in m["transicoes"] if t["tipo"] == "corte"]
        ex = ds[len(ds) // 2] if ds else (ct[0] if ct else None)
        tot = sum(x["transicao_resumo"]["corte"] + x["transicao_resumo"]["dissolve"] + x["transicao_resumo"]["especial"] for x in vids)
        esp = sum(x["transicao_resumo"]["especial"] for x in vids)
        txt = (f"{br(v('transicao_resumo.dissolve_pct'), 0)}% das trocas são dissolve"
               + (f" de {br(v('transicao_resumo.dissolve_quadros_mediana'), 0)} quadros" if v("transicao_resumo.dissolve_quadros_mediana") else "")
               + f"; o resto é corte seco. Especiais: {esp} em {tot} trocas ({br(esp / max(1, len(vids)), 1)} por vídeo).")
        add("transicao", "Tipo de transição", txt,
            f"{m['nome']} q{ex['q']}-q{ex['q_fim']} ({ex['tipo']}, {br(ex['s'], 2)} s)" if ex else m["nome"])
    if v("camera.pct_quadros_andando") is not None:
        m = _prova(vids, "camera.pct_quadros_andando", v("camera.pct_quadros_andando"))
        cq = (m.get("camera") or {}).get("creep_tipico_q")
        add("camera", "Câmera nunca para",
            f"Câmera andando em {br(v('camera.pct_quadros_andando'), 0)}% dos quadros; creep típico de "
            f"{br(v('camera.creep_pct_s'), 1)}% da largura por segundo; nos 10 primeiros quadros do plano ela anda "
            f"{br(v('camera.entrada_x_resto'), 1)}× o resto (impulso na entrada). Maior trecho parado: "
            f"{br(v('camera.parado_max_q'), 0)} quadros.",
            f"{m['nome']} q{cq} ({_seg(cq, m['fps'])})" if cq is not None else m["nome"])
    if v("fala.ppm") is not None:
        m = _prova(vids, "fala.pausa_frase_mediana_s", v("fala.pausa_frase_mediana_s"))
        pq = m["fala"].get("pausa_tipica_q")
        add("fala", "Ritmo da fala",
            f"{br(v('fala.ppm'), 0)} palavras por minuto, voz em {br(v('fala.voz_pct'), 0)}% do tempo; pausa depois de frase de "
            f"{br(v('fala.pausa_frase_mediana_s'), 2)} s na mediana (máx {br(v('fala.pausa_frase_max_s'), 2)} s).",
            f"{m['nome']} pausa típica no fim de frase em q{pq} ({_seg(pq, m['fps'])})" if pq is not None else m["nome"])
    if v("acao.troca_palavra_q_mediana") is not None:
        m = _prova(vids, "acao.troca_palavra_q_mediana", v("acao.troca_palavra_q_mediana"))
        tr0 = next((t for t in m["transicoes"]), None)
        tq = v("acao.troca_palavra_q_mediana")
        quando = ("junto do começo da palavra mais perto (±1 quadro, mediana)" if abs(tq) < 1 else
                  f"{br(abs(tq), 0)} quadro(s) {'ANTES' if tq > 0 else 'DEPOIS'} do começo da palavra mais perto (mediana)")
        add("troca_palavra", "Troca de plano presa à palavra",
            f"A troca de plano começa {quando}: imagem nova entra junto com a palavra nova.",
            f"{m['nome']} troca q{tr0['q']}" if tr0 else m["nome"])
    if v("acao.quadros_antes_mediana") is not None:
        m = _prova(vids, "acao.quadros_antes_mediana", v("acao.quadros_antes_mediana"))
        ex = (m["acao"].get("exemplos") or [[None, None]])[0]
        pad = sum(1 for x in vids if (x.get("acao") or {}).get("padrao"))
        if pad * 2 >= len(vids):
            add("acao", "Ação antes da palavra",
                f"O movimento dentro do quadro (gesto, troca de rosto, objeto) acontece {br(v('acao.quadros_antes_mediana'), 0)} "
                "quadros ANTES da palavra seguinte (mediana; picos de movimento sem a câmera, acima do acaso em "
                f"{pad} de {len(vids)} vídeos).",
                f"{m['nome']} pico q{ex[0]} → palavra q{ex[1]}" if ex[0] is not None else m["nome"])
        else:
            add("acao", "Ação × palavra",
                "Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não "
                "passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica).",
                f"{m['nome']} pico q{ex[0]} → palavra q{ex[1]}" if ex[0] is not None else m["nome"])
    if v("fala_imagem.imagem_nova_pct") is not None:
        m = _prova(vids, "fala_imagem.imagem_nova_pct", v("fala_imagem.imagem_nova_pct"))
        ex = next((x for x in (m.get("fala_imagem") or {}).get("oracoes", []) if x["troca"]), None)
        add("fala_imagem", "A imagem é o que a fala diz, no quadro da palavra",
            f"{br(v('fala_imagem.imagem_nova_pct'), 0)}% das orações trazem imagem nova (troca de plano em "
            f"{br(v('fala_imagem.com_troca_pct'), 0)}%, o resto é ação/objeto dentro do plano); a imagem muda "
            f"{br(v('fala_imagem.lead_q_mediana'), 0)} quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por "
            "oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito).",
            f"{m['nome']} '{ex['texto'][:40]}' troca q{ex['quadro_palavra'] - 2 - (ex['lead_troca_q'] or 0)} → palavra q{ex['q']}" if ex else m["nome"])
    if v("numeros_resumo.por_min") is not None and any(m["numeros"] for m in vids):
        m = next(x for x in vids if x["numeros"])
        x = next((y for y in m["numeros"] if y.get("evento")), m["numeros"][0])
        add("numero", "Fato vira objeto",
            f"{br(v('numeros_resumo.por_min'), 1)} números falados por minuto; {br(v('numeros_resumo.com_evento_pct'), 0)}% "
            "deles têm um evento visível (objeto que aparece, rola, acende ou plano novo) a ±0,3 s da palavra"
            + (f", em média {br(_med([y['numeros_resumo']['evento_menos_palavra_q_mediana'] for y in vids], 1), 0)} quadros da palavra" if
               _med([y['numeros_resumo']['evento_menos_palavra_q_mediana'] for y in vids]) is not None else "") + ".",
            f"{m['nome']} '{x['texto']}' palavra q{x['q']}, evento q{x.get('evento_q')}")
    if v("som.lufs") is not None:
        m = _prova(vids, "som.lufs", v("som.lufs"))
        txt = f"Volume integrado {br(v('som.lufs'), 1)} LUFS."
        if v("som.musica_abaixo_da_voz_db") is not None:
            txt += f" Música (medida nas pausas da fala) {br(v('som.musica_abaixo_da_voz_db'), 0)} dB abaixo da voz."
        if v("som.efeitos_por_min") is not None:
            txt += f" Picos de efeito: ~{br(v('som.efeitos_por_min'), 0)} por minuto (estimativa: conferir no ouvido)."
        add("som", "Som medido", txt, f"{m['nome']} (áudio inteiro)")
    if v("legenda.y_pct") is not None:
        m = _prova(vids, "legenda.y_pct", v("legenda.y_pct"))
        pq = (m.get("legenda") or {}).get("prova_q")
        add("legenda", "Legenda",
            f"Legenda com o centro a {br(v('legenda.y_pct'), 0)}% da altura, letra de ~{br(v('legenda.altura_texto_px_1920'), 0)} px "
            f"numa tela de 1920, ~{br(v('legenda.palavras_por_quadro'), 0)} palavras por vez.",
            f"{m['nome']} q{pq} ({_seg(pq, m['fps'])})" if pq is not None else m["nome"])
    lp = [m.get("loop_diferenca_inicio_fim") for m in vids if m.get("loop_diferenca_inicio_fim") is not None]
    if lp:
        m = min(vids, key=lambda x: x.get("loop_diferenca_inicio_fim") or 999)
        add("loop", "Fim que emenda no começo",
            f"Diferença entre o 1º e o último quadro: {br(_med(lp, 1), 1)} (0 = idêntico; abaixo de ~12 o fim emenda no começo). "
            f"Mais parecido: {m['nome']} ({br(m['loop_diferenca_inicio_fim'], 1)}).",
            f"{m['nome']} q0 × q{m['quadros'] - 1}")
    gancho = [m["planos"]["lista"][1]["s"] for m in vids if len(m["planos"]["lista"]) > 1]
    if gancho:
        add("gancho", "Gancho",
            f"A 1ª troca de imagem vem em {br(_med(gancho, 2), 2)} s na mediana; a primeira palavra em "
            f"{br(_med([m['fala'].get('primeira_palavra_s') for m in vids if m.get('fala')], 2), 2)} s.",
            f"{vids[0]['nome']} q{vids[0]['planos']['lista'][1]['q'] if len(vids[0]['planos']['lista']) > 1 else 0}")
    return R


def escrever_md(estudo: dict, pasta: Path) -> Path:
    vids, cj = estudo["videos"], estudo["conjunto"]
    L = [f"# Estudo quadro a quadro: {estudo['nome']}", "",
         "> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e",
         "> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.", "",
         f"{len(vids)} vídeo(s) · {hoje()} · prova = `<vídeo> q<quadro>` (quadro a {br(vids[0]['fps'], 0)} fps; folhas em `folhas/`)", "",
         "## Regras com número (siga os números)", ""]
    for i, r in enumerate(estudo["regras"], 1):
        L.append(f"{i}. **{r['titulo']}.** {r['texto']} Prova: {r['prova']}.")
    if (pasta / "TRANSICOES-E-POP.md").is_file():
        L += ["", "## Transições especiais e levantadinha", "", "Catálogo medido quadro a quadro (tipo, quadros, direção, prova) e o pop de reação: `TRANSICOES-E-POP.md`."]
    L += ["", "## Medidas (mediana do conjunto, com mínimo e máximo)", "", "| Medida | Mediana | Faixa | Unidade |", "|---|---|---|---|"]
    for rot, cam, un, nd, _ in CHAVES:
        c = cj.get(cam) or {}
        if c.get("mediana") is None:
            continue
        L.append(f"| {rot} | {br(c['mediana'], nd)} | {br(c['min'], nd)} a {br(c['max'], nd)} | {un} |")
    bs = [m["base_sugerida"] for m in vids]
    L += ["", "## Base sugerida pro formato", "",
          f"**{cj.get('base_sugerida') or '?'}** ({bs[0].get('tipo', '')}: {bs[0].get('porque', '')}). Regra: animação sem pessoa "
          "estilo cartoon → sem base pronta (o Desenho 3D saiu do catálogo); animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; "
          "vídeo com pessoa gravada → formato gravado.", "",
          "## Estilo × conteúdo", "",
          "- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, "
          "ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número "
          "virando evento na tela, fim que emenda no começo.",
          "- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os "
          "cenários específicos, marcas, nomes e o texto que aparece na tela.", "",
          "## Por vídeo", "", "| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |",
          "|---|---|---|---|---|---|---|---|---|"]
    for m in vids:
        L.append(f"| {m['nome']} | {br(m['duracao'], 1)} s | {m['planos']['n']} | {br(m['planos']['mediana_s'], 2)} s | "
                 f"{m['transicao_resumo']['dissolve']} ({br(m['transicao_resumo']['dissolve_quadros_mediana'], 0)} q) | "
                 f"{br((m.get('camera') or {}).get('pct_quadros_andando'), 0)}% | {br((m.get('fala') or {}).get('ppm'), 0)} | "
                 f"{br((m.get('som') or {}).get('lufs'), 1)} | {m['base_sugerida'].get('tipo', '')} |")
    fis = [m for m in vids if m.get("fala_imagem")]
    if fis:
        L += ["", "## Fala × imagem (oração por oração)", "",
              "Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a "
              "folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.", "",
              "| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |", "|---|---|---|---|---|"]
        for m in fis:
            f_ = m["fala_imagem"]
            L.append(f"| {m['nome']} | {f_['n']} | {br(f_['imagem_nova_pct'], 0)}% | {br(f_['com_troca_pct'], 0)}% | {br(f_['lead_q_mediana'], 0)} q |")
    L += ["", "## Folhas", ""]
    for m in vids:
        L.append(f"- {m['nome']}: " + ", ".join(f"`{f['arquivo']}`" for f in m["folhas"][:6]) + (f" (+{len(m['folhas']) - 6})" if len(m["folhas"]) > 6 else ""))
    p = pasta / "ESTUDO-QUADROS.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


def _enxuto(m: dict) -> dict:
    """estudo.json sem a velocidade de todo quadro (essa fica em quadros-<nome>.json)."""
    c = dict(m)
    c["camera"] = {k: v for k, v in (m.get("camera") or {}).items() if k != "vel_q"}
    return c


def conferido_no_olho(pasta: Path) -> dict:
    """Soma as tabelas fala × imagem anotadas no olho (fala-imagem/<vídeo>.anotado.json: {n: {aparece, bate: sim|parcial|não}})."""
    out = {"n": 0, "sim": 0, "parcial": 0, "nao": 0, "videos": []}
    for f in sorted((Path(pasta) / "fala-imagem").glob("*.anotado.json")):
        d = ler_json(f, {}) or {}
        out["videos"].append(f.name.replace(".anotado.json", ""))
        for v in d.values():
            b = _sem_acento(str(v.get("bate", "")))
            out["n"] += 1
            out["sim" if b == "sim" else "parcial" if b == "parcial" else "nao"] += 1
    return out if out["n"] else {}


def estudar(videos: list, saida: Path, nome: str = "", transcrever_fala: bool = True, idioma: str = "", cliente: str = "",
            words: dict | None = None, oracoes_de: dict | None = None) -> dict:
    """Estuda um ou vários vídeos do MESMO estilo. words: {caminho_do_video: words.json já feito} (não chama o Groq)."""
    saida = ensure(Path(saida))
    vids = []
    teto = max(3, FOLHAS_MAX // max(1, len(videos)))   # ~40 folhas no total, por mais vídeos que sejam
    for v in videos:
        v = Path(v)
        js = None
        if words and str(v) in words and Path(words[str(v)]).is_file():
            js = ler_json(Path(words[str(v)]), None)
        nm = re.sub(r"[^\w-]", "", v.stem)[:40] or "video"
        pv = ensure(saida / "videos" / nm)
        m = estudar_video(v, saida, nm, js, transcrever_fala, idioma, cliente, teto, (oracoes_de or {}).get(str(v)))
        gravar_json(pv / "quadros.json", {"vel_camera_q": (m.get("camera") or {}).get("vel_q")})
        vids.append(_enxuto(m))
    est = {"versao": VERSAO, "nome": nome or (Path(videos[0]).stem if len(videos) == 1 else f"{len(videos)} vídeos"),
           "criado_em": hoje(), "videos": vids}
    est["conjunto"] = conjunto(vids)
    est["regras"] = regras(est)
    olho = conferido_no_olho(saida)
    if olho:
        est["fala_imagem_olho"] = olho
        est["regras"].insert(next((i + 1 for i, r in enumerate(est["regras"]) if r["id"] == "fala_imagem"), len(est["regras"])), {
            "id": "fala_imagem_olho", "titulo": "Conferido no olho: a tela mostra o que é dito",
            "texto": f"{olho['sim']} de {olho['n']} orações ({br(100 * olho['sim'] / olho['n'], 0)}%) mostram literalmente o objeto, a ação, a pessoa "
                     f"ou o número da fala no quadro da palavra; {olho['parcial']} em parte e {olho['nao']} não (o plano genérico de cenário é a exceção, "
                     "não a regra). Cada oração ganha a imagem do que ela diz.",
            "prova": "; ".join(f"`fala-imagem/{n}.md`" for n in olho["videos"])})
    gravar_json(saida / "estudo.json", est)
    escrever_md(est, saida)
    return est


# ───────────────────────────── comparar (régua ref × nosso) ─────────────────────────────

def _carregar(estudo) -> dict:
    p = Path(estudo)
    if p.is_dir():
        p = p / "estudo.json"
    d = ler_json(p, None)
    if not d:
        raise ValueError(f"Estudo não encontrado: {estudo}")
    return d


def oracoes_do_cenas(cenas) -> list[dict]:
    d = ler_json(Path(cenas), {}) or {}
    if d.get("oracoes"):   # o gerador já gravou as orações com tempo
        return [{"texto": o["texto"], "s": round(float(o["s"]), 2), "e": round(float(o["e"]), 2)} for o in d["oracoes"]]
    out = []
    for c in d.get("cenas") or []:
        ps = c.get("palavras") or []
        if ps:
            out.append({"texto": c.get("fala") or " ".join(w["w"] for w in ps), "s": round(float(ps[0]["s"]), 2), "e": round(float(ps[-1]["e"]), 2)})
    return out


def comparar(estudo_ref, video_nosso, saida: Path | None = None, words: str | None = None, transcrever_fala: bool = True,
             idioma: str = "", cliente: str = "", cenas: str | None = None) -> dict:
    """cenas: o cenas.json do vídeo (cada plano = uma oração) pra tabela fala × imagem sair oração por oração."""
    ref = _carregar(estudo_ref)
    video_nosso = Path(video_nosso)
    saida = ensure(Path(saida) if saida else video_nosso.parent / "qa" / "estudo-quadros")
    js = ler_json(Path(words), None) if words else None
    nosso = estudar([video_nosso], saida, video_nosso.stem, transcrever_fala and js is None,
                    idioma, cliente, words={str(video_nosso): words} if words else None,
                    oracoes_de={str(video_nosso): oracoes_do_cenas(cenas)} if cenas else None)
    m = nosso["videos"][0]
    linhas = []
    for rot, cam, un, nd, tol in CHAVES:
        r = (ref["conjunto"].get(cam) or {}).get("mediana")
        n = _pega(m, cam)
        if r is None and n is None:
            continue
        lo, hi = (ref["conjunto"].get(cam) or {}).get("min"), (ref["conjunto"].get(cam) or {}).get("max")
        ok = None
        if isinstance(r, (int, float)) and isinstance(n, (int, float)):
            margem = max(abs(r) * tol, 0.05 if nd >= 2 else 0.5)
            ok = (abs(n - r) <= margem) or (lo is not None and hi is not None and lo <= n <= hi)
        linhas.append({"medida": rot, "chave": cam, "ref": r, "faixa_ref": [lo, hi], "nosso": n, "unidade": un, "ok": ok, "casas": nd})
    res = {"ref": ref["nome"], "nosso": str(video_nosso), "linhas": linhas,
           "ok": sum(1 for x in linhas if x["ok"]), "fora": sum(1 for x in linhas if x["ok"] is False)}
    gravar_json(saida / "comparacao.json", res)
    L = [f"# Régua: {ref['nome']} × {video_nosso.name}", "", f"{res['ok']} dentro, {res['fora']} fora (tolerância por medida; dentro da faixa "
         "dos vídeos de referência também conta).", "", "| Medida | Referência (faixa) | Nosso | Unidade | |", "|---|---|---|---|---|"]
    for x in linhas:
        lo, hi = x["faixa_ref"]
        L.append(f"| {x['medida']} | {br(x['ref'], x['casas'])} ({br(lo, x['casas'])} a {br(hi, x['casas'])}) | {br(x['nosso'], x['casas'])} | "
                 f"{x['unidade']} | {'ok' if x['ok'] else ('FORA' if x['ok'] is False else '?')} |")
    (saida / "COMPARACAO.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    res["tabela_md"] = "\n".join(L[4:])
    return res


# ───────────────────────────── usado pelo fluxo de referência ─────────────────────────────

def resumo_prompt(estudo: dict, pasta_rel: str = "") -> str:
    """Linhas curtas pra ir no pedido à IA (a régua medida)."""
    rs = estudo.get("regras") or []
    cab = f"RÉGUA MEDIDA QUADRO A QUADRO ({pasta_rel or 'estudo-quadros'}/ESTUDO-QUADROS.md):"
    return cab + "\n" + "\n".join(f"- {r['titulo']}: {r['texto']}" for r in rs)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estudar")
    e.add_argument("videos", nargs="+")
    e.add_argument("--saida", required=True)
    e.add_argument("--nome", default="")
    e.add_argument("--sem-fala", action="store_true")
    e.add_argument("--idioma", default="", help="pt, en... (vazio = o Groq descobre)")
    e.add_argument("--cliente", default="")
    c = sub.add_parser("comparar")
    c.add_argument("estudo")
    c.add_argument("video")
    c.add_argument("--words", default=None, help="words.json já feito (não chama o Groq)")
    c.add_argument("--saida", default=None)
    c.add_argument("--sem-fala", action="store_true")
    c.add_argument("--cenas", default=None, help="cenas.json do vídeo: a tabela fala × imagem sai plano a plano (uma oração por plano)")
    c.add_argument("--idioma", default="")
    b = sub.add_parser("base")
    b.add_argument("estudo")
    a = ap.parse_args(argv)
    if a.cmd == "estudar":
        est = estudar(a.videos, Path(a.saida), a.nome, not a.sem_fala, a.idioma, a.cliente)
        print(f"{a.saida}/ESTUDO-QUADROS.md · {len(est['regras'])} regras · base sugerida: {est['conjunto']['base_sugerida']}")
        for r in est["regras"]:
            print(f"- {r['titulo']}: {r['texto']} [{r['prova']}]")
        return 0
    if a.cmd == "comparar":
        r = comparar(a.estudo, a.video, Path(a.saida) if a.saida else None, a.words, not a.sem_fala, a.idioma, cenas=a.cenas)
        print(r["tabela_md"])
        print(f"\n{r['ok']} dentro, {r['fora']} fora")
        return 0
    if a.cmd == "base":
        d = _carregar(a.estudo)
        print(json.dumps({"base": d["conjunto"].get("base_sugerida"), "por_video": [m["base_sugerida"] for m in d["videos"]]},
                         ensure_ascii=False, indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
