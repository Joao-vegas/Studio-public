"""Utilitários de áudio da skill motion-design: whisper com tempo por palavra, corte da direção lida, nivelamento."""
from __future__ import annotations

import re
import unicodedata
import wave
from pathlib import Path

WHISPER = "mlx-community/whisper-large-v3-turbo"
# Idioma da fala: português por padrão; vídeo em inglês roda com MOTION_LINGUA=en (canal Real Life Verdict, 29-set).
LINGUA = __import__("os").environ.get("MOTION_LINGUA", "pt")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9@]", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def palavras(arq: Path) -> list[dict]:
    import mlx_whisper

    r = mlx_whisper.transcribe(str(arq), path_or_hf_repo=WHISPER, language=LINGUA, word_timestamps=True)
    return [{"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3)}
            for s in r["segments"] for w in s["words"]]


def inicio_do_texto(arq: Path, texto: str) -> float:
    """Segundo em que as 3 primeiras palavras do texto começam. O Gemini 3.8 lê a direção
    em voz alta antes do texto; o 2.5 não. Sem direção na fala, devolve 0."""
    inicio = [norm(w) for w in texto.split()[:3]]
    ws = palavras(arq)
    nw = [norm(w["w"]) for w in ws]
    # Às vezes o 3.8 lê a 1ª frase, depois a direção e só então o texto (28-set, v9):
    # o texto de verdade é o que vem DEPOIS da ÚLTIMA leitura da direção ("leia o texto...").
    d = max((i for i in range(len(nw) - 2) if nw[i:i + 3] == ["leia", "o", "texto"]), default=-1)
    # direção em inglês (MOTION_LINGUA=en): termina em "...on the last sentence." (Binge Files 003, 05/10)
    d = max([d] + [i + 2 for i in range(min(len(nw) - 2, 400)) if nw[i:i + 3] == ["the", "last", "sentence"]])
    i = next((i for i in range(d + 1, len(nw) - 2) if nw[i:i + 3] == inicio), None)
    # A direção lida em voz alta dura segundos. Se as 3 palavras só aparecem lá na frente, o Whisper escreveu
    # o começo de outro jeito ("Gail" por "Gale") e achou a frase repetida no meio: cortava 2 min (Binge Files 003, 05/10).
    if i is not None and ws[i]["s"] > 45 and d < 0:
        return 0.0
    if (i is None or ws[i]["s"] > ws[min(d + 1, len(ws) - 1)]["s"] + 5) and d >= 0:  # início escrito diferente: corta logo depois da direção
        return max(0.0, ws[min(d + 1, len(ws) - 1)]["s"] - 0.12)
    return max(0.0, ws[i]["s"] - 0.12) if i is not None and i > 3 else 0.0


def fim_do_texto(arq: Path, texto: str) -> float | None:
    """Segundo logo depois da última palavra do texto. O TTS solta um estalo de ruído depois dela
    ("TV falhando"): em vídeo de vários blocos ele ficava no meio do vídeo, em cada emenda (Binge Files 002, 01/10)."""
    ultima = norm(texto.split()[-1])
    ws = palavras(arq)
    fins = [w for w in ws if norm(w["w"]) == ultima]
    return fins[-1]["e"] + 0.12 if fins else None


def tom_mediano(arq: Path) -> float:
    """Altura mediana da voz (Hz), pra pegar bloco que saiu com outra voz (002: um bloco 20 Hz mais grave)."""
    import numpy as np

    with wave.open(str(arq)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32).reshape(-1, ch).mean(1) / 32768
    lo, hi, f0 = int(sr / 300), int(sr / 70), []
    for k in range(0, len(x) - 2048, sr // 10):
        fr = x[k:k + 2048]
        if np.sqrt((fr ** 2).mean()) < 0.03:
            continue
        c = np.correlate(fr, fr, "full")[2047:]
        f0.append(sr / (lo + int(np.argmax(c[lo:hi]))))
    return float(np.median(f0)) if f0 else 0.0


def nivelar(arq: Path) -> None:
    """Iguala o volume da fala ao longo do vídeo (o TTS sobe o volume no final). Não mexe no tempo."""
    import numpy as np

    with wave.open(str(arq)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32).reshape(-1, ch).mean(1) / 32768
    jan = int(sr * 3)
    fala = np.abs(x) > 0.02

    def media(v, k):  # média móvel "same" por soma acumulada: O(n). O np.convolve era O(n·k) e travava em narração de 10 min
        c = np.concatenate([[0.0], np.cumsum(v, dtype=np.float64)])
        i = np.arange(len(v))
        a, b = np.clip(i - k // 2, 0, len(v)), np.clip(i - k // 2 + k, 0, len(v))
        return ((c[b] - c[a]) / k).astype(np.float32)

    e2 = media(x * x * fala, jan)
    cnt = media(fala.astype(np.float32), jan)
    rms = np.sqrt(e2 / np.maximum(cnt, 1e-3))
    alvo = np.median(rms[: int(sr * 60)][cnt[: int(sr * 60)] > .05])
    g = np.clip(alvo / np.maximum(rms, 1e-4), .5, 1.6)
    g = media(g, int(sr * .8))
    y = np.clip(x * g, -1, 1)
    with wave.open(str(arq), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


# G10: nada de ruído depois da última palavra. O TTS solta uma rajada curta (estalo, "TV falhando") no fim,
# separada da fala por uma pausa. Janelas de 10 ms; silêncio = abaixo de -45 dB.
LIM_SILENCIO_DB = -45.0
LIM_CAUDA_DB = -60.0   # nos últimos 0,2 s qualquer sinal acima disso já é cauda suja
JANELA_S = 0.01
LACUNA_S = 0.2         # pausa mínima entre a fala e a rajada
RAJADA_MAX_S = 0.6     # rajada mais longa que isso é fala, não estalo


def _db_janelas(x, sr: int):
    import numpy as np

    x = np.asarray(x, dtype=np.float64)
    e = (x ** 2).mean(1) if x.ndim == 2 else x ** 2
    w = max(1, int(sr * JANELA_S))
    n = max(1, -(-len(e) // w))  # a sobra do fim vira uma janela própria (média só sobre as amostras que existem)
    cont = np.full(n, w, dtype=np.float64)
    cont[-1] = max(1, len(e) - (n - 1) * w)
    soma = np.add.reduceat(np.concatenate([e, [0.0]]), np.arange(0, n * w, w)[:n]) if len(e) else np.zeros(n)
    return 20 * np.log10(np.maximum(np.sqrt(soma / cont), 1e-9)), w


def analisar_cauda(x, sr: int) -> dict:
    """Mede o fim do áudio. Devolve: rajada_ini (s) e rajada_dur (s) se há rajada curta isolada depois de pausa
    (senão None), e ultimos_db (pico de janela de 10 ms nos últimos 0,2 s)."""
    import numpy as np

    db, w = _db_janelas(x, sr)
    ativo = db > LIM_SILENCIO_DB
    segs, i = [], 0
    while i < len(ativo):  # trechos ativos; pausa < 0,2 s não separa (é a mesma fala)
        if ativo[i]:
            j = i
            while j < len(ativo) and ativo[j]:
                j += 1
            if segs and i - segs[-1][1] < LACUNA_S / JANELA_S:
                segs[-1][1] = j
            else:
                segs.append([i, j])
            i = j
        else:
            i += 1
    r = {"rajada_ini": None, "rajada_dur": None,
         "ultimos_db": float(db[-max(1, int(round(LACUNA_S / JANELA_S))):].max()) if len(db) else -120.0}
    if len(segs) >= 2:
        (_, fim_fala), (ini, fim) = segs[-2], segs[-1]
        if (ini - fim_fala) * JANELA_S >= LACUNA_S - 1e-9 and (fim - ini) * JANELA_S < RAJADA_MAX_S:
            r["rajada_ini"], r["rajada_dur"] = ini * w / sr, (fim - ini) * JANELA_S
    return r


def limpar_cauda(x, sr: int):
    """Tira do fim a rajada curta (< 0,6 s) que vem depois de uma pausa >= 0,2 s abaixo de -45 dB e deixa os
    últimos 0,2 s em silêncio. Mesmo tamanho de entrada (o tempo não muda). Fala colada no fim, sem pausa
    antes da rajada, não é tocada: no máximo um fade de 10 ms no último sopro, pra não estalar."""
    import numpy as np

    inteiro = np.issubdtype(np.asarray(x).dtype, np.integer)
    y = np.array(x, dtype=np.float32) / (32768.0 if inteiro else 1.0)
    a = analisar_cauda(y, sr)
    if a["rajada_ini"] is not None:
        y[int(a["rajada_ini"] * sr):] = 0
    n02 = int(round(LACUNA_S * sr))
    if len(y) and analisar_cauda(y, sr)["ultimos_db"] <= LIM_SILENCIO_DB:
        y[-n02:] = 0
    elif len(y):  # fala ainda toca nos últimos 0,2 s: não corta, só fecha com fade curto
        k = min(len(y), int(sr * 0.01))
        y[-k:] *= np.linspace(1, 0, k, dtype=np.float32).reshape((-1,) + (1,) * (y.ndim - 1))
    return np.clip(np.round(y * 32768), -32768, 32767).astype(x.dtype) if inteiro else y


def limpar_cauda_arquivo(arq: Path) -> float:
    """limpar_cauda num wav 16 bits no próprio arquivo. Devolve os segundos de rajada removidos (0 = nada)."""
    import numpy as np

    with wave.open(str(arq)) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), np.int16).reshape(-1, ch)
    x = x[:, 0] if ch == 1 else x
    rajada = analisar_cauda(x.astype(np.float32) / 32768, sr)["rajada_dur"] or 0.0
    y = limpar_cauda(x, sr)
    if not np.array_equal(x, y):
        with wave.open(str(arq), "wb") as w:
            w.setnchannels(ch); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(np.asarray(y, np.int16).tobytes())
    return rajada
