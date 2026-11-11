#!/usr/bin/env python3
"""
emocao_joao — acha, nos vídeos brutos do próprio João, trechos de ~10 a 18 s em que ele fala com cada emoção, pra virarem as
variações da voz clonada dele ("João · animado"). É só PROPOSTA: o perfil só nasce quando o João ouve e clica "Usar" na tela
Vozes (gate "Aprovou?"). Sem trecho bom pra uma emoção, a tela pede "grave 15 s assim" com um texto sugerido.

Mede, em janelas de 14 s andando de 3 em 3 s: volume (dB), tom (semitons, média e variação), ritmo (sílabas/s), fração de
fala e quantas frases terminam subindo o tom (pergunta). Cada emoção é uma combinação dessas medidas contra a média dos
próprios vídeos dele (z-score). Grátis: ffmpeg + numpy + scipy; a transcrição do trecho escolhido vai pelo Groq (grátis).

    python3 emocao_joao.py procurar        # varre os brutos e grava os candidatos em app/.cache/vozes-emocao.json
    python3 emocao_joao.py usar <emocao> <candidato>   # (só depois do Aprovou?) cria o perfil "João · <emoção>"
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emocao as _em  # noqa: E402
from _comum import RAIZ  # noqa: E402

SR = 16000
HOP = 0.02          # s por quadro de análise
JANELA = 14.0       # s
PASSO = 3.0
MIN_FALA = 0.62     # fração mínima do trecho com voz (clonar precisa de fala contínua)
MIN_NOTA = 0.9      # z-score somado mínimo pra dizer "achei"
POR_EMOCAO = 3
SAIDA = _em.AMOSTRAS / "joao"


def brutos() -> list[Path]:
    return sorted((RAIZ / "clientes" / "Joao" / "vegasContent" / "modelos").glob("*/_sandbox-*/work/joao.mp4"))


def _pcm(video: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _quadros(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(dB por quadro, tom em semitons por quadro, NaN onde não tem voz). Tom por autocorrelação (FFT), 70 a 400 Hz."""
    h, n = int(SR * HOP), int(SR * 0.04)
    k = max(0, (len(x) - n) // h)
    if k < 10:
        return np.zeros(0), np.zeros(0)
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    f = x[idx] * np.hanning(n)[None, :]
    db = 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-9)
    corte = max(np.percentile(db, 30) + 6, -50)
    voz = db > corte
    f0 = np.full(k, np.nan)
    lo, hi = int(SR / 400), int(SR / 70)
    for a in range(0, k, 4096):
        b = min(k, a + 4096)
        esp = np.fft.rfft(f[a:b], 2 * n, axis=1)
        ac = np.fft.irfft(esp * np.conj(esp), axis=1)[:, :hi + 1]
        ac = ac / (ac[:, :1] + 1e-9)
        pico = ac[:, lo:hi + 1].argmax(axis=1) + lo
        forca = ac[np.arange(b - a), pico]
        ok = voz[a:b] & (forca > 0.45)
        f0[a:b][ok] = 12 * np.log2((SR / pico[ok]) / 100.0)
    return db, f0


def _janela(db: np.ndarray, f0: np.ndarray, a: int, b: int) -> dict | None:
    d, t = db[a:b], f0[a:b]
    fala = d > max(np.percentile(db, 30) + 6, -50)
    if fala.mean() < MIN_FALA:
        return None
    voz = ~np.isnan(t)
    if voz.sum() < 0.25 * len(t):
        return None
    env = np.convolve(np.where(fala, d, d.min()), np.ones(5) / 5, mode="same")
    from scipy.signal import find_peaks
    picos, _ = find_peaks(env, prominence=3, distance=int(0.12 / HOP))
    # frases terminam em pausa; vê se o tom subiu nos 0,4 s antes de cada pausa (>= 0,3 s)
    sobe, pausas = 0, 0
    parou = ~fala
    i, n = 0, len(fala)
    while i < n:
        if parou[i]:
            j = i
            while j < n and parou[j]:
                j += 1
            if (j - i) * HOP >= 0.3 and i > 25:
                fim = t[i - 20:i]
                fim = fim[~np.isnan(fim)]
                if len(fim) >= 8:
                    pausas += 1
                    sobe += int(np.polyfit(np.arange(len(fim)), fim, 1)[0] * 20 > 1.5)   # sobe > 1,5 semitom em 0,4 s
            i = j
        else:
            i += 1
    return {"fala": float(fala.mean()), "vol": float(d[fala].mean()), "tom": float(np.nanmean(t)), "var": float(np.nanstd(t)),
            "ritmo": float(len(picos) / (len(d) * HOP)), "subidas": sobe, "pausas": pausas,
            "taxa_sobe": sobe / pausas if pausas else 0.0}


def janelas(video: Path) -> list[dict]:
    db, f0 = _quadros(_pcm(video))
    if not len(db):
        return []
    w, p = int(JANELA / HOP), int(PASSO / HOP)
    out = []
    for a in range(0, len(db) - w, p):
        m = _janela(db, f0, a, a + w)
        if m:
            out.append({**m, "video": str(video.relative_to(RAIZ)), "ini": round(a * HOP, 1), "fim": round((a + w) * HOP, 1)})
    return out


# nota de cada emoção = soma ponderada dos z-scores das medidas
PESOS = {
    "animado": {"vol": 1.0, "tom": 1.0, "var": 1.0, "ritmo": 0.7},
    "indignado": {"vol": 1.4, "var": 1.0, "ritmo": 0.8},
    "firme": {"vol": 1.0, "var": -1.0, "ritmo": -0.3},
    "calmo": {"vol": -1.0, "var": -0.8, "ritmo": -0.9},
    "segredo": {"vol": -1.6, "ritmo": -0.7, "tom": -0.5},
    "pergunta": {"taxa_sobe": 1.8, "var": 0.6},
}


def candidatos(ws: list[dict], por_emocao: int = POR_EMOCAO) -> dict[str, list[dict]]:
    """{emocao: [janelas escolhidas, melhores primeiro]}; só as que passam da nota mínima. Um trecho não serve a duas emoções
    e dois trechos da mesma emoção não se sobrepõem."""
    if len(ws) < 6:
        return {}
    chaves = {k for p in PESOS.values() for k in p}
    mu = {k: np.mean([w[k] for w in ws]) for k in chaves}
    sd = {k: (np.std([w[k] for w in ws]) or 1.0) for k in chaves}
    notas = {e: [sum(c * (w[k] - mu[k]) / sd[k] for k, c in p.items()) for w in ws] for e, p in PESOS.items()}
    usados: list[tuple[str, float, float]] = []
    out: dict[str, list[dict]] = {}
    # a emoção mais "rara" primeiro (maior nota máxima), pra não perder o melhor trecho dela pra outra
    for e in sorted(PESOS, key=lambda e: -max(notas[e])):
        for i in sorted(range(len(ws)), key=lambda i: -notas[e][i]):
            w = ws[i]
            if notas[e][i] < MIN_NOTA or len(out.get(e, [])) >= por_emocao:
                break
            if any(v == w["video"] and not (w["fim"] <= a or w["ini"] >= b) for v, a, b in usados):
                continue
            usados.append((w["video"], w["ini"], w["fim"]))
            out.setdefault(e, []).append({**w, "nota": round(float(notas[e][i]), 2)})
    return out


def _cortar(video: str, ini: float, fim: float, destino: Path, wav: bool = False) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(ini), "-t", str(fim - ini), "-i", str(RAIZ / video), "-vn", "-ac", "1"]
    cmd += ["-ar", "24000", "-af", "highpass=f=70"] if wav else ["-b:a", "96k"]
    subprocess.run(cmd + [str(destino)], check=True)


def _transcrever(mp3: Path) -> str:
    """O texto do trecho pelo Groq (grátis); sem chave ou com erro, vazio."""
    try:
        from corte import chave_groq
        from fala import _groq_pedaco
        return (_groq_pedaco(str(mp3), chave_groq(None), "", "pt", 3).get("text") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def procurar(transcrever: bool = True, log=print) -> dict:
    """Varre os brutos, grava os candidatos de cada emoção no mapa (status 'candidato') e devolve {emocao: [candidatos]}."""
    ws: list[dict] = []
    for v in brutos():
        log(f"medindo {v.parent.parent.name}")
        try:
            ws += janelas(v)
        except Exception as e:  # noqa: BLE001
            log(f"  pulei ({e})")
    achados = candidatos(ws)
    d = _em.mapa()
    d["candidatos"][_em.VOZ_JOAO] = {}
    vistos: set[str] = set()   # o mesmo vídeo cortado em dois estilos aparece em duas pastas: o texto repetido sai
    for e, lista in achados.items():
        boas = []
        for c in lista:
            c["id"] = hashlib.sha1(f"{c['video']}{c['ini']}".encode()).hexdigest()[:8]
            c["status"] = "candidato"
            mp3 = SAIDA / f"{c['id']}.mp3"
            _cortar(c["video"], c["ini"], c["fim"], mp3)
            c["texto"] = _transcrever(mp3) if transcrever else ""
            c["audio"] = f"{c['id']}.mp3"
            chave = re.sub(r"\W+", " ", c["texto"].lower())[:40].strip()
            if chave and chave in vistos:
                continue
            if e == "pergunta" and c["texto"] and "?" not in c["texto"]:   # pergunta sem pergunta no texto não serve
                continue
            vistos.add(chave)
            boas.append(c)
        if boas:
            d["candidatos"][_em.VOZ_JOAO][e] = boas
    _em._salvar(d)
    return achados


def candidato(emocao: str, cid: str, voz_id: str = _em.VOZ_JOAO) -> dict:
    c = next((x for x in _em.mapa()["candidatos"].get(voz_id, {}).get(emocao, []) if x.get("id") == cid), None)
    if not c:
        raise ValueError("Esse trecho não está mais na lista. Procure de novo.")
    return c


def usar(emocao: str, cid: str, voz_id: str = _em.VOZ_JOAO, nome: str = "João", clonar=None) -> str:
    """O João OUVIU e aprovou o trecho: cria o perfil '<nome> · <emoção>' clonado dele e liga a variação. Devolve o id do perfil."""
    if emocao not in _em.EMOCOES:
        raise ValueError("Emoção desconhecida.")
    c = candidato(emocao, cid, voz_id)
    if clonar is None:
        import vozes
        clonar = vozes.clonar
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "trecho.wav"
        _cortar(c["video"], c["ini"], min(c["fim"], c["ini"] + 19.5), wav, wav=True)
        pid = clonar(_em._nome_variacao(nome, emocao), wav)
    _em.registrar_aprovada(voz_id, emocao, pid, c.get("texto", ""))
    d = _em.mapa()
    for x in d["candidatos"].get(voz_id, {}).get(emocao, []):
        if x.get("id") == cid:
            x["status"] = "usado"
    _em._salvar(d)
    return pid


# O que pedir quando não achou trecho: texto pra ele ler com a emoção, ~15 s
TEXTO_GRAVAR = {k: v["amostra"] for k, v in _em.EMOCOES.items()}


def usar_gravacao(emocao: str, audio: Path, voz_id: str = _em.VOZ_JOAO, nome: str = "João", clonar=None) -> str:
    """O João subiu uma gravação (15 s lendo o texto sugerido, ou qualquer fala com a emoção): vira a variação dele."""
    if emocao not in _em.EMOCOES:
        raise ValueError("Emoção desconhecida.")
    if clonar is None:
        import vozes
        clonar = vozes.clonar
    pid = clonar(_em._nome_variacao(nome, emocao), Path(audio))
    _em.registrar_aprovada(voz_id, emocao, pid, "")
    return pid


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["procurar"]:
        r = procurar()
        for e, l in r.items():
            for c in l:
                print(e, c["id"], c["video"].split("/")[-4:-2], c["ini"], c["nota"], (c["texto"] or "")[:70])
        print("sem trecho bom:", [e for e in _em.ORDEM if e not in r])
    elif a[:1] == ["usar"] and len(a) == 3:
        print(usar(a[1], a[2]))
    else:
        print(__doc__)
