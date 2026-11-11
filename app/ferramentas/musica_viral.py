#!/usr/bin/env python3
"""
musica_viral — "Virais do momento": a música de fundo vem do que está viralizando no Brasil e no mundo, não de banco de trilha.

Paradas públicas, grátis e sem chave (conferidas em 30-out-2026):
    shazam   O que as pessoas estão descobrindo (CSV oficial, Brasil e Mundo).
    spotify  Spotify diário Brasil e Global (kworb.net lê a parada pública; traz a subida e há quantos dias está nela).
    apple    Apple Music mais tocadas (rss.marketingtools.apple.com, JSON livre), Brasil e EUA.
    deezer   Deezer mundo (api.deezer.com/chart).
  TikTok Creative Center pede login e o Spotify Viral 50 também: ficaram de fora (não dá sem conta).
Cache de 1 dia em app/.cache/virais.json. O áudio vem pelo yt-dlp (YouTube, depois SoundCloud): "artista - título" oficial
(canal "- Topic", "official audio"), nunca remix, ao vivo, slowed nem type beat.

O TRECHO que entra no vídeo é o conhecido: o refrão ou o drop, achado pela curva de energia (a subida que fica alta) e
encaixado na batida mais forte perto dele; o arquivo da sandbox já começa 0,15 s antes dele, e a grade de batida
(work/batida.json) nasce desse ponto, então o corte na batida do Editorial segue valendo.

Toda faixa nova passa por `checar` antes de virar opção: voz falada que não é a letra (tag de produtor "type beat", "prod. by",
locutor), bip e silêncio no meio do trecho. Mixkit e viral do YouTube oficial são as fontes preferidas.

CLI:
    musica_viral.py virais [-n 10] [--forcar]                      (a lista de hoje)
    musica_viral.py direcao "tensa de suspense, sem voz" [--formato documentario] [--texto "fala"]   (3 opções sem voz cantada, com o motivo)
    musica_viral.py opcoes --formato editorial [--cliente X] [--texto "fala"] [-n 3]
    musica_viral.py escolher <sandbox> --dur 75 [--faixa <chave|url>] [--entrada s] [--cliente X]   (prepara work/musica/)
    musica_viral.py checar <mp3> [--esperado letra|instrumental] [--ini s] [--dur s]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402

RAIZ = _comum.RAIZ
CACHE = RAIZ / "app" / ".cache" / "virais"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
VALIDADE_S = 24 * 3600                 # as paradas valem 1 dia
SR = 22050
ATRASO_GANCHO = 0.15                   # o trecho conhecido cai em t=0,15 s do vídeo (igual ao batida.py)
AVISO_DIREITOS = "Música famosa: o Instagram pode silenciar se não for a do app (a mesma faixa, no app, entra no lugar)."

# o peso de cada parada: o que está sendo DESCOBERTO pesa mais que o que só é muito tocado
PARADAS = [   # (id, rótulo, peso, tamanho da lista)
    ("shazam-br", "Shazam Brasil", 1.0, 50), ("shazam-mundo", "Shazam Mundo", 1.0, 50),
    ("spotify-br", "Spotify Brasil", 0.8, 50), ("spotify-mundo", "Spotify Global", 0.8, 50),
    ("apple-br", "Apple Music Brasil", 0.6, 50), ("apple-us", "Apple Music EUA", 0.5, 50),
    ("deezer-mundo", "Deezer Mundo", 0.4, 50),
]


# ───────────────────────── rede (um ponto só, fácil de trocar nos testes) ─────────────────────────

def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _limpa_titulo(t: str) -> str:
    """Sem '(feat. X)', '(Ao Vivo)', '- Remastered', 'Long Version': a mesma música em versões diferentes vira uma só."""
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", t or "")
    t = re.sub(r"\s[-–]\s(?:ao vivo|live|remaster\w*|extended|long version|radio edit|\d{4}).*$", " ", t, flags=re.I)
    t = re.sub(r"\b(?:feat|ft|with|w/)\.?\s.*$", " ", t, flags=re.I)
    t = re.sub(r"[^\w\s'’!?.,&$-]", " ", t)   # emoji e enfeite fora ("Flash 💠")
    return re.sub(r"\s+", " ", t).strip()


def chave_musica(artista: str, titulo: str) -> str:
    return (_norm(re.split(r",|&| e | x |feat|ft\.", artista or "")[0]) + "|" + _norm(_limpa_titulo(titulo))).strip("|")


def slug_faixa(artista: str, titulo: str) -> str:
    return "viral-" + (_comum.make_slug(f"{artista} {_limpa_titulo(titulo)}") or "faixa")[:60]


# ───────────────────────── as paradas ─────────────────────────

def _shazam(url: str) -> list[dict]:
    linhas = _get(url).lstrip("﻿").splitlines()
    i = next((k for k, l in enumerate(linhas) if l.startswith("Rank,")), None)
    if i is None:
        return []
    out = []
    for r in csv.DictReader(io.StringIO("\n".join(linhas[i:]))):
        try:
            out.append({"pos": int(r["Rank"]), "artista": r["Artist"].strip(), "titulo": r["Title"].strip()})
        except (KeyError, ValueError):
            continue
    return out


def _kworb(url: str) -> list[dict]:
    html = _get(url)
    out = []
    for m in re.finditer(r'<tr><td class="np">(\d+)</td>\s*<td class="np">([^<]*)</td>\s*<td class="text mp"><div>(.*?)</div></td>\s*<td>(\d+)</td>',
                         html, re.S):
        partes = re.findall(r">([^<]+)</a>", m.group(3))
        if len(partes) < 2:
            continue
        mov = m.group(2).strip()
        sub = int(mov[1:].replace(",", "")) if re.fullmatch(r"\+\d+", mov) else 0
        out.append({"pos": int(m.group(1)), "artista": partes[0].strip(), "titulo": partes[1].strip(),
                    "dias": int(m.group(4)), "subiu": sub, "novo": mov in ("NEW", "RE")})
    return out


def _apple(loja: str) -> list[dict]:
    d = json.loads(_get(f"https://rss.marketingtools.apple.com/api/v2/{loja}/music/most-played/50/songs.json"))
    return [{"pos": i, "artista": r["artistName"], "titulo": r["name"], "apple_id": r.get("id", "")}
            for i, r in enumerate(d["feed"]["results"], 1)]


def _deezer() -> list[dict]:
    d = json.loads(_get("https://api.deezer.com/chart/0/tracks?limit=50"))
    return [{"pos": r.get("position") or i, "artista": (r.get("artist") or {}).get("name", ""), "titulo": r.get("title_short") or r.get("title", "")}
            for i, r in enumerate(d.get("data") or [], 1)]


BUSCADORES = {
    "shazam-br": lambda: _shazam("https://www.shazam.com/services/charts/csv/top-50-country/brazil"),
    "shazam-mundo": lambda: _shazam("https://www.shazam.com/services/charts/csv/top-50-country/world"),
    "spotify-br": lambda: _kworb("https://kworb.net/spotify/country/br_daily.html"),
    "spotify-mundo": lambda: _kworb("https://kworb.net/spotify/country/global_daily.html"),
    "apple-br": lambda: _apple("br"),
    "apple-us": lambda: _apple("us"),
    "deezer-mundo": _deezer,
}


def _arq_paradas() -> Path:
    return CACHE.parent / "virais.json"


def paradas(forcar: bool = False) -> dict:
    """{"em": epoch, "listas": {id: [{pos, artista, titulo, ...}]}, "erros": {id: motivo}}. Cache de 1 dia; uma parada que
    cai não derruba as outras (e a que já estava no cache velho continua valendo se a internet falhar)."""
    arq = _arq_paradas()
    velho = _comum.ler_json(arq, {}) or {}
    if not forcar and velho.get("listas") and time.time() - float(velho.get("em") or 0) < VALIDADE_S:
        return velho
    listas, erros = {}, {}

    def uma(pid):
        try:
            return pid, BUSCADORES[pid](), ""
        except Exception as e:  # noqa: BLE001
            return pid, [], f"{type(e).__name__}: {str(e)[:120]}"

    with ThreadPoolExecutor(max_workers=len(PARADAS)) as ex:
        for pid, lista, erro in ex.map(uma, [p[0] for p in PARADAS]):
            if lista:
                listas[pid] = lista
            else:
                erros[pid] = erro or "vazia"
                if (velho.get("listas") or {}).get(pid):
                    listas[pid] = velho["listas"][pid]
    if not listas:
        return velho
    novo = {"em": time.time(), "listas": listas, "erros": erros}
    arq.parent.mkdir(parents=True, exist_ok=True)
    _comum.gravar_json(arq, novo)
    return novo


def virais(n: int = 30, forcar: bool = False) -> list[dict]:
    """As músicas de hoje, uma linha por música (versões juntas), da mais viral pra menos. `score` soma o lugar em cada parada
    (peso da parada × quão no alto), mais bônus por estar em mais de uma e por ter subido/entrado há pouco no Spotify."""
    dados = paradas(forcar)
    por: dict[str, dict] = {}
    for pid, rotulo, peso, tam in PARADAS:
        for r in (dados.get("listas") or {}).get(pid, []):
            k = chave_musica(r["artista"], r["titulo"])
            if not k or k == "|":
                continue
            m = por.setdefault(k, {"chave": k, "artista": r["artista"], "titulo": _limpa_titulo(r["titulo"]) or r["titulo"], "titulo_cheio": r["titulo"],
                                   "score": 0.0, "fontes": [], "bonus": 0.0, "apple_id": ""})
            if any(f["parada"] == pid for f in m["fontes"]):   # a mesma música em 2 versões na mesma parada conta uma vez (a melhor posição)
                continue
            m["score"] += peso * max(0.0, 1 - (r["pos"] - 1) / max(1, tam)) ** 1.5
            m["fontes"].append({"parada": pid, "rotulo": rotulo, "pos": r["pos"]})
            if r.get("apple_id") and not m["apple_id"]:
                m["apple_id"] = r["apple_id"]
            if pid.startswith("spotify"):   # viral = chegou agora ou subiu muito, não o hit de 3 anos que nunca sai da parada
                m["bonus"] += (0.45 if r.get("novo") or r.get("dias", 99) <= 14 else 0) + min(0.4, r.get("subiu", 0) / 60)
    for m in por.values():
        m["score"] = round(m["score"] + m["bonus"] + 0.25 * (len(m["fontes"]) - 1), 3)
    lista = sorted(por.values(), key=lambda m: -m["score"])
    for m in lista:
        m["slug"] = slug_faixa(m["artista"], m["titulo"])
        m["id"] = m["slug"]
    return lista[:n]


def resumo_fontes(m: dict) -> str:
    return " · ".join(f"{f['rotulo']} #{f['pos']}" for f in sorted(m["fontes"], key=lambda f: f["pos"])[:3])


# ───────────────────────── som: leitura e medidas ─────────────────────────

def _pcm(arq, ini: float = 0.0, dur: float | None = None, sr: int = SR):
    import numpy as np
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{ini:.3f}", *(["-t", f"{dur:.3f}"] if dur else []), "-i", str(arq),
           "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype="<f4")


def _duracao(arq) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arq)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _ataque(x):
    """Envoltória de ataque dos graves e médios (a mesma do batida.py do Editorial): (ataque, quadros por segundo)."""
    import numpy as np
    hop, n = 256, (len(x) - 1024) // 256
    if n < 50:
        return np.zeros(1), SR / hop
    w = np.hanning(1024)
    esp = np.array([np.abs(np.fft.rfft(x[i * hop:i * hop + 1024] * w))[:60] for i in range(n)])
    env = np.log1p(esp * 20).sum(1)
    at = np.maximum(0, np.diff(env, prepend=env[0]))
    at = at - np.convolve(at, np.ones(43) / 43, "same")
    at[at < 0] = 0
    return at, SR / hop


def _periodo(at, fps: float) -> float:
    import numpy as np
    ac = np.correlate(at, at, "full")[len(at) - 1:]
    lo, hi = int(fps * 60 / 180), min(int(fps * 60 / 60), len(ac) - 2)
    if hi <= lo:
        return 0.0
    k = lo + int(np.argmax(ac[lo:hi]))
    if 0 < k < len(ac) - 1:
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        k = k + .5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else k
    return k / fps


def achar_trecho(mp3, dur_video: float = 75.0) -> dict:
    """O refrão ou o drop: a subida de energia que FICA alta (nada de intro parada). Devolve {t0, bpm, periodo, motivo, dur}.
    Mede a energia a cada 0,5 s; o candidato é o começo cujos 12 s seguintes são bem mais altos que os 6 s antes e entre os
    mais altos da faixa; o 1º candidato quase tão bom quanto o melhor ganha (o conhecido costuma vir cedo). Depois encaixa
    no ataque mais forte (kick) até 0,5 s em volta. Só considera inícios de onde ainda cabe o vídeo (a não ser que a faixa seja curta)."""
    import numpy as np
    x = _pcm(mp3)
    dur = len(x) / SR
    if dur < 15:
        return {"t0": 0.0, "bpm": 0, "periodo": 0.0, "dur": round(dur, 2), "motivo": "faixa curta: do começo"}
    h = SR // 2
    n = len(x) // h
    e = 20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-6)
    limite = max(4, int((dur - dur_video - 1) / .5)) if dur > dur_video + 6 else max(4, n - 24)
    teto = np.percentile(e, 70)
    cand = []
    for i in range(0, min(limite, n - 24)):
        depois = float(e[i:i + 24].mean())
        antes = float(e[max(0, i - 12):i].mean()) if i >= 4 else depois - 0.0
        cand.append((i, depois - antes, depois))
    boas = [c for c in cand if c[2] >= teto]
    if not boas:
        boas = cand or [(0, 0.0, 0.0)]
    melhor = max(c[1] for c in boas)
    i0 = next(c[0] for c in boas if c[1] >= melhor - 1.5)
    # afina: a entrada mais seca (1 s depois contra 2 s antes) nos próximos 5 s, pra não cair 2 s antes do drop
    fino = [(float(e[j:j + 2].mean() - e[max(0, j - 4):j].mean()) if j >= 2 else -99.0, j) for j in range(max(0, i0 - 2), min(n - 3, i0 + 11))]
    if fino and max(fino)[0] > 3:
        i0 = max(fino)[1]
    t0 = i0 * .5
    # encaixa no ataque (kick/drop) mais forte em ±0,5 s
    jan0 = max(0.0, t0 - 0.5)
    at, fps = _ataque(_pcm(mp3, jan0, 1.3))
    if len(at) > 8 and at.max() > 0:
        t0 = jan0 + float(np.argmax(at)) / fps
    seg = _pcm(mp3, t0, 40)
    at2, fps2 = _ataque(seg)
    per = _periodo(at2, fps2)
    if t0 < 3:
        motivo = "a faixa já abre no ponto forte"
    elif melhor < 3.0:
        motivo = "sem subida clara: o 1º ponto alto da faixa"
    else:
        motivo = f"o refrão/drop: a energia sobe {melhor:.1f} dB e fica alta"
    return {"t0": round(t0, 3), "bpm": round(60 / per, 1) if per else 0, "periodo": round(per, 4), "dur": round(dur, 2), "motivo": motivo}


def cortar(origem, saida, t0: float, dur: float, lead: float = ATRASO_GANCHO) -> Path:
    """Corta a partir de t0 - lead; se a faixa acaba antes de `dur`, repete o trecho (rara; faixa curta)."""
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    ini = max(0.0, t0 - lead)
    tem = _duracao(origem) - ini
    base = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    if tem >= dur:
        cmd = base + ["-ss", f"{ini:.3f}", "-i", str(origem), "-t", f"{dur:.3f}", "-c:a", "libmp3lame", "-q:a", "2", str(saida)]
    else:
        cmd = base + ["-stream_loop", "-1", "-ss", f"{ini:.3f}", "-i", str(origem), "-t", f"{dur:.3f}", "-c:a", "libmp3lame", "-q:a", "2", str(saida)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not saida.is_file() or saida.stat().st_size < 2000:
        raise RuntimeError("não consegui cortar o trecho: " + (r.stderr or "")[-200:])
    return saida


# ───────────────────────── checagem: marca d'água, bip, silêncio ─────────────────────────

# Tag de produtor, locutor e vitrine: o que NÃO é a letra. Em faixa com letra só estes padrões reprovam (letra tem palavra solta).
PADROES_MARCA = [
    r"type\s*beat", r"\bprod(?:uced|\.)?\s*(?:by|por)\b", r"\bproduzid[oa]\s+por\b", r"\bfree\s+(?:for|beat|download|dl|instrumental)\b",
    r"\bbeat\s*stars\b", r"\bbeatstars\b", r"\bair\s?bit\b", r"\bsubscribe\b", r"\binscreva[\s-]*se\b", r"\bwww\b", r"\bdot\s?com\b",
    r"\.com\b", r"you(?:'re| are) listening", r"\bmixed\s+by\b", r"\bmastered\s+by\b", r"\bfor\s+sale\b", r"\bunlicensed\b",
    r"\bwatermark\b", r"\bpreview\b", r"\bdemo\s+(?:beat|version)\b", r"\bexclusive\s+beat\b", r"\bbeat\s+by\b", r"\bleasing\b",
    r"\bsoundcloud\b", r"\bpurchase\b", r"\bbuy\s+(?:this|the)\b", r"\bon\s+the\s+(?:beat|track)\b",
]
IGNORAR_FALA = {"obrigado", "thank you", "thanks for watching", "legendas pela comunidade", "amara org", "subtitles by", "tchau", "musica"}
TITULO_RUIM = r"type\s*beat|free\s*beat|prod\.|\bfree\s+download|\bslowed|\bsped\s*up|speed\s*up|\bnightcore|\b8d\b|karaok|\bcover\b|remix|\bmashup|\binstrumental\b|ao vivo|\blive\b|reaction|tutorial|\bshorts?\b|reverb|ac[uú]stic"


def _groq(mp3, ini: float, dur: float | None) -> dict | None:
    """Transcrição do trecho pelo Groq (grátis, a chave do Estúdio). None = sem chave ou sem rede (a checagem segue sem ela)."""
    try:
        import corte
        import fala
        chave = corte.chave_groq("Avulso")
        if not chave:
            return None
        tmp = CACHE / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        alvo = tmp / f"chk-{hashlib.sha1((str(mp3) + str(ini)).encode()).hexdigest()[:10]}.mp3"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{ini:.2f}", *(["-t", f"{dur:.2f}"] if dur else []), "-i", str(mp3),
                        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(alvo)], capture_output=True, timeout=120)
        return fala._groq_pedaco(alvo, chave, "", "", 2)
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)[:160]}


def _fala_real(js: dict) -> list[str]:
    """Segmentos que são mesmo fala (o whisper inventa 'Obrigado.' em cima de música: no_speech_prob alto ou texto de praxe)."""
    out = []
    for s in (js or {}).get("segments") or []:
        t = (s.get("text") or "").strip()
        n = _norm(t)
        if not n or any(k in n for k in IGNORAR_FALA):
            continue
        if float(s.get("no_speech_prob") or 0) > 0.6 and float(s.get("avg_logprob") or 0) < -0.9:
            continue
        out.append(t)
    return out


def _bip(x, sr: int = 16000) -> list[float]:
    """Instantes (s) de tom puro sustentado (bip de censura ou de marca d'água), mesmo por cima da música: um pico estreito na mesma
    frequência (±2 compartimentos) que concentra >= 93% da energia da janela e fica 45 dB acima da mediana do espectro, por >= 0,25 s.
    Música com sintetizador sustentado passa (medido em 52 faixas do Estúdio: nenhum falso); bip BAIXO por cima de música cheia
    não é pego: aí quem pega é a voz/silêncio ou o ouvido do João na prévia."""
    import numpy as np
    n, hop = 1024, 256
    if len(x) < n * 4:
        return []
    w = np.hanning(n)
    seguidos, achados, ini, k0 = 0, [], 0, -99
    need = int(0.25 * sr / hop)
    for i in range(0, len(x) - n, hop):
        q = x[i:i + n]
        if np.sqrt((q ** 2).mean()) < 0.005:
            seguidos = 0
            continue
        esp = np.abs(np.fft.rfft(q * w)) ** 2
        k = int(np.argmax(esp[10:]) + 10)
        f = k * sr / n
        perto = esp[max(0, k - 3):k + 4].sum() / (esp.sum() + 1e-12)
        sobe = 10 * np.log10((esp[k] + 1e-12) / (np.median(esp[10:]) + 1e-12))
        if 400 <= f <= 3500 and perto > 0.93 and sobe > 45 and (seguidos == 0 or abs(k - k0) <= 2):
            if seguidos == 0:
                ini = i
            k0 = k
            seguidos += 1
            if seguidos == need:
                achados.append(round(ini / sr, 2))
        else:
            seguidos = 0
    return achados


def _silencios(mp3, ini: float, dur: float) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-ss", f"{ini:.2f}", "-t", f"{dur:.2f}", "-i", str(mp3),
                        "-af", "silencedetect=noise=-48dB:d=0.6", "-f", "null", "-"], capture_output=True, text=True)
    ini_s = [float(v) for v in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    dur_s = [float(v) for v in re.findall(r"silence_duration: ([\d.]+)", r.stderr)]
    return [(a, d) for a, d in zip(ini_s, dur_s) if a > 0.4 and a + d < dur - 0.4]


def checar(mp3, esperado: str = "letra", ini: float = 0.0, dur: float | None = None, titulo: str = "", usar_groq: bool = True) -> dict:
    """A faixa (ou o trecho ini..ini+dur) pode virar opção? {ok, motivos, fala, groq}. `esperado`: 'letra' (música cantada: só tag de
    produtor, locutor ou vitrine reprova) ou 'instrumental' (qualquer fala real reprova). Bip e silêncio estranho reprovam sempre."""
    mp3 = Path(mp3)
    dur = dur or max(5.0, _duracao(mp3) - ini)
    motivos, fala = [], ""
    if titulo and re.search(TITULO_RUIM, titulo, re.I) and esperado == "letra" and re.search(r"type\s*beat|free\s*beat|prod\.", titulo, re.I):
        motivos.append(f"título de beat de vitrine ('{titulo[:50]}')")
    x = _pcm(mp3, ini, dur, 16000)
    for t in _bip(x)[:2]:
        motivos.append(f"bip (tom puro) em {t:.1f} s do trecho")
    for a, d in _silencios(mp3, ini, dur)[:2]:
        motivos.append(f"silêncio de {d:.1f} s no meio do trecho (em {a:.1f} s)")
    js = _groq(mp3, ini, dur) if usar_groq else None
    groq_ok = bool(js) and "erro" not in js
    if groq_ok:
        falas = _fala_real(js)
        fala = " ".join(falas)
        achou = [p for p in PADROES_MARCA if re.search(p, fala, re.I)]
        if achou:
            motivos.append(f"voz falando por cima ('{fala[:70]}')")
        elif esperado == "instrumental" and len(fala.split()) >= 2:
            motivos.append(f"tem voz falada numa faixa que devia ser só instrumental ('{fala[:70]}')")
    return {"ok": not motivos, "motivos": motivos, "fala": fala[:300], "groq": groq_ok, "esperado": esperado}


# ───────────────────────── o que cada música soa (prévia de 30 s da Apple, grátis) ─────────────────────────

def _arq_perfis() -> Path:
    return CACHE / "perfis.json"


def _perfil(m: dict) -> dict:
    """Andamento e timbre medidos na prévia de 30 s do iTunes (grátis): {bpm, grave, agudo, forte_db, dinamica}. {} se não achou."""
    perfis = _comum.ler_json(_arq_perfis(), {}) or {}
    if m["chave"] in perfis and "genero" in perfis[m["chave"]]:
        return perfis[m["chave"]]
    p: dict = {}
    try:
        q = urllib.parse.quote(f"{m['artista']} {m['titulo']}")
        ok = None
        for loja in ("br", "us"):
            d = json.loads(_get(f"https://itunes.apple.com/search?term={q}&entity=song&limit=4&country={loja}"))
            ok = next((r for r in d.get("results", []) if r.get("previewUrl") and _norm(_limpa_titulo(r.get("trackName", ""))) == _norm(m["titulo"])), None) \
                or next((r for r in d.get("results", []) if r.get("previewUrl")), None)
            if ok:
                break
        if ok:
            destino = CACHE / "previas-itunes" / (m["slug"] + ".m4a")
            destino.parent.mkdir(parents=True, exist_ok=True)
            if not destino.is_file():
                destino.write_bytes(urllib.request.urlopen(urllib.request.Request(ok["previewUrl"], headers={"User-Agent": UA}), timeout=30).read())
            import musica as _mus
            x = _mus._pcm(destino)
            rms, onset = _mus._envelope(x)
            bpm, _conf = _mus._bpm(onset)
            b = _mus._bandas(x, 0, len(x) / _mus.SR)
            lig = rms[rms > 1e-4]
            p = {"bpm": round(bpm), "grave": b.get("grave", 0), "agudo": b.get("agudo", 0),
                 "forte_db": round(float(20 * math.log10(float(lig.mean()) + 1e-9)), 1) if len(lig) else -60.0,
                 "dinamica": round(float(20 * math.log10(float(lig.max() / (lig.mean() + 1e-9)) + 1e-9)), 1) if len(lig) else 0.0,
                 "duracao_s": round((ok.get("trackTimeMillis") or 0) / 1000), "genero": ok.get("primaryGenreName", "")}
    except Exception as e:  # noqa: BLE001
        p = {"erro": str(e)[:100]}
    perfis[m["chave"]] = p
    _comum.gravar_json(_arq_perfis(), perfis)
    return p


# ───────────────────────── o clima que o vídeo pede ─────────────────────────

CLIMA_PALAVRAS = (("sombri", "sombria"), ("escur", "sombria"), ("tens", "tensa"), ("suspen", "tensa"), ("epic", "épica"),
                  ("cinemat", "épica"), ("animad", "animada"), ("alegr", "animada"), ("calm", "calma"), ("corporativ", "corporativa"))
CLIMA_FALA = {"dark tense": ["tensa", "sombria"], "uplifting": ["épica", "animada"], "corporate": ["corporativa", "calma"],
              "playful": ["animada"], "news": ["tensa", "corporativa"]}


def clima_pedido(texto: str = "", clima_formato: str = "") -> tuple[list[str], str]:
    """(climas em ordem de preferência, de onde vieram). O clima do estilo manda, a fala completa."""
    ordem, origem = [], []
    cf = _norm(clima_formato)
    for pref, c in CLIMA_PALAVRAS:
        if pref in cf and c not in ordem:
            ordem.append(c)
            origem.append("clima do estilo")
    try:
        import musica_busca as _mb
        for clima, termo in _mb.termos_da_fala(texto)[:2]:
            for c in CLIMA_FALA.get(clima, []):
                if c not in ordem:
                    ordem.append(c)
                    origem.append("tom da fala" if texto.strip() else "")
    except Exception:  # noqa: BLE001
        pass
    return ordem or ["tensa", "sombria"], next((o for o in origem if o), "clima do estilo")


def _rank01(v: float, todos: list[float]) -> float:
    """Posição (0 a 1) de v entre os valores do grupo: o clima é relativo às outras virais de hoje, não a um número fixo."""
    ordenados = sorted(todos)
    return (sum(1 for t in ordenados if t < v) + 0.5 * sum(1 for t in ordenados if t == v)) / max(1, len(ordenados))


def climas_do_perfil(pf: dict, pool: list[dict]) -> dict[str, float]:
    """Nota de 0 a 1 de cada clima pro jeito dessa música, comparada com o grupo: escuro = grave alto e pouco agudo; rápido = BPM;
    forte = volume médio. Sem medida (prévia não achada): neutro (0,4) em tudo."""
    if not pf or "grave" not in pf:
        return _prior_genero((pf or {}).get("genero", ""))
    medidos = [q for q in pool if q and "grave" in q]
    esc = _rank01(pf["grave"] - pf["agudo"], [q["grave"] - q["agudo"] for q in medidos])
    rap = _rank01(pf["bpm"], [q["bpm"] for q in medidos])
    forte = _rank01(pf["forte_db"], [q["forte_db"] for q in medidos])
    din = _rank01(pf["dinamica"], [q["dinamica"] for q in medidos])
    medida = {"sombria": .6 * esc + .25 * (1 - rap) + .15 * forte, "tensa": .5 * esc + .3 * rap + .2 * forte,
              "épica": .5 * forte + .3 * din + .2 * esc, "animada": .5 * (1 - esc) + .4 * rap + .1 * forte,
              "calma": .5 * (1 - forte) + .3 * (1 - rap) + .2 * (1 - esc), "corporativa": .5 * (1 - abs(rap - .5) * 2) + .3 * (1 - esc) + .2 * (1 - din)}
    prior = _prior_genero(pf.get("genero", ""))
    return {c: .5 * prior[c] + .5 * medida[c] for c in medida}


# o gênero que o iTunes declara diz o clima melhor que o espectro de 30 s (que acha tudo "brilhante"): vale metade da nota
GENERO_CLIMA = (   # (pedaços do nome do gênero, {clima: 0-1})
    (("hip", "rap", "trap", "funk", "phonk", "drill"), {"sombria": .8, "tensa": .9, "épica": .5, "animada": .4, "calma": .2, "corporativa": .3}),
    (("electro", "eletr", "dance", "house", "techno", "edm"), {"sombria": .5, "tensa": .8, "épica": .7, "animada": .8, "calma": .2, "corporativa": .4}),
    (("alternative", "rock", "indie", "metal", "punk"), {"sombria": .7, "tensa": .6, "épica": .8, "animada": .4, "calma": .4, "corporativa": .3}),
    (("soundtrack", "classical", "score", "trilha"), {"sombria": .7, "tensa": .7, "épica": .9, "animada": .3, "calma": .5, "corporativa": .5}),
    (("r&b", "soul"), {"sombria": .6, "tensa": .4, "épica": .3, "animada": .4, "calma": .7, "corporativa": .4}),
    (("country", "sertanej", "forr", "pagode", "samba", "mpb", "axé", "brazil"), {"sombria": .1, "tensa": .1, "épica": .2, "animada": .7, "calma": .6, "corporativa": .3}),
    (("pop", "latin", "latino", "reggaeton", "urbano"), {"sombria": .3, "tensa": .3, "épica": .4, "animada": .9, "calma": .3, "corporativa": .5}),
)
PESO_ORDEM = (1.0, .6, .35, .2)


def _prior_genero(genero: str) -> dict[str, float]:
    g = _norm(genero)
    for chaves, notas in GENERO_CLIMA:
        if any(c in g for c in chaves):
            return notas
    return {c: .4 for c in ("sombria", "tensa", "épica", "animada", "calma", "corporativa")}


def _pontua(m: dict, perfil: dict, ordem: list[str], pool: list[dict], pool_max: float = 1.0) -> tuple[float, str]:
    """Nota = o quanto está viral + o quanto o jeito dela casa com o clima pedido (a ordem de preferência pesa). O motivo sai em uma linha."""
    cl = climas_do_perfil(perfil, pool)
    casa = sum(PESO_ORDEM[i] * cl[c] for i, c in enumerate(ordem[:4])) / sum(PESO_ORDEM[:len(ordem[:4])])
    melhor = max(cl, key=cl.get)
    bpm = perfil.get("bpm")
    soa = ", ".join(v for v in (perfil.get("genero", ""), f"{bpm} BPM" if bpm else "") if v)
    quanto = "casa bem" if cl[ordem[0]] >= .6 else "é a mais próxima que está viral hoje"
    return m["score"] / max(0.1, pool_max) + 6.0 * casa, (f"{quanto} com {ordem[0]}" + (f" (o jeito dela é mais {melhor})" if melhor != ordem[0] else "")
                                     + (f"; {soa}" if soa else "") + f"; na parada: {resumo_fontes(m)}")


# ───────────────────────── baixar, escolher o trecho, checar ─────────────────────────

def _score_yt(r: dict, artista: str, titulo: str, esperado_s: float | None) -> float:
    t, canal = _norm(r.get("title", "")), _norm(r.get("channel") or r.get("uploader") or "")
    if re.search(TITULO_RUIM, r.get("title", ""), re.I):
        return -99
    chaves = [w for w in _norm(_limpa_titulo(titulo)).split() if len(w) > 2]
    if chaves and sum(w in t for w in chaves) / len(chaves) < 0.6:
        return -99
    pontos = 0.0
    if canal.endswith("topic"):
        pontos += 3
    art = _norm(re.split(r",|&| e | x |feat", artista)[0])
    if art and art in canal:
        pontos += 2
    if re.search(r"official audio|audio oficial|visuali[sz]er|\bofficial\b|oficial", r.get("title", ""), re.I):
        pontos += 1.5
    d = r.get("duration") or 0
    if esperado_s and d:
        erro = abs(d - esperado_s) / esperado_s
        pontos += 2 if erro < .08 else 1 if erro < .2 else -2 if erro < .4 else -99
    elif d and not 90 <= d <= 420:
        pontos -= 3
    pontos += min(1.0, math.log10(max(10, r.get("view_count") or 10)) / 9)
    return pontos


def _ytdlp() -> list[str]:
    import musica_busca as _mb
    yt = _mb._ytdlp()
    if not yt:
        raise RuntimeError("o yt-dlp não está instalado neste Mac")
    return yt + ["--no-update", "--no-warnings"]


def achar_audio(m: dict) -> dict:
    """O vídeo/áudio oficial de 'artista - título' no YouTube (ou SoundCloud): {url, titulo, canal, duracao, fonte}. Ou ValueError."""
    yt = _ytdlp()
    esperado = (m.get("duracao_s") or _perfil(m).get("duracao_s") or 0) or None
    melhor, nota = None, -50.0
    for busca in (f"ytsearch6:{m['artista']} - {m['titulo']} official audio", f"scsearch4:{m['artista']} {m['titulo']}"):
        r = subprocess.run(yt + ["--flat-playlist", "--dump-json", busca], capture_output=True, text=True, timeout=90)
        for linha in r.stdout.splitlines():
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            p = _score_yt(d, m["artista"], m["titulo"], esperado)
            if p > nota:
                nota, melhor = p, {"url": d.get("webpage_url") or d.get("url"), "titulo": d.get("title", ""), "canal": d.get("channel") or d.get("uploader") or "",
                                   "duracao": d.get("duration") or 0, "fonte": "youtube" if busca.startswith("yt") else "soundcloud"}
        if melhor and nota >= 2:
            break
    if not melhor or nota < 0:
        raise ValueError(f"não achei o áudio oficial de {m['artista']} - {m['titulo']}")
    return melhor


def baixar(m: dict, url: str = "") -> Path:
    """A faixa inteira em app/.cache/virais/faixas/<slug>.mp3 (uma vez; as próximas usam o arquivo)."""
    pasta = CACHE / "faixas"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{m['slug']}.mp3"
    if alvo.is_file() and alvo.stat().st_size > 50_000:
        return alvo
    info = {"url": url, "titulo": "", "canal": "", "duracao": 0, "fonte": "youtube"} if url else achar_audio(m)
    r = subprocess.run(_ytdlp() + ["-f", "bestaudio", "-x", "--audio-format", "mp3", "--audio-quality", "0", "--no-playlist",
                                   "-o", str(pasta / f"{m['slug']}.%(ext)s"), info["url"]], capture_output=True, text=True, timeout=600)
    if not alvo.is_file():
        raise RuntimeError("não consegui baixar o áudio: " + (r.stderr or "")[-200:])
    _comum.gravar_json(pasta / f"{m['slug']}.json", {**info, "artista": m["artista"], "titulo_musica": m["titulo"]})
    return alvo


def _meta_faixa(slug: str) -> dict:
    return _comum.ler_json(CACHE / "faixas" / f"{slug}.json", {}) or {}


def _arq_checagens() -> Path:
    return CACHE / "checagens.json"


def _checada(m: dict, t0: float, dur: float, esperado: str = "letra") -> dict:
    """checar() com memória: a mesma faixa e o mesmo trecho não vão de novo ao Groq."""
    mem = _comum.ler_json(_arq_checagens(), {}) or {}
    k = f"{m['slug']}|{round(t0)}|{round(dur)}|{esperado}"
    if k in mem:
        return mem[k]
    arq = _baixar_cand(m)
    r = checar(arq, esperado, max(0.0, t0 - ATRASO_GANCHO), dur, titulo=_meta_faixa(m["slug"]).get("titulo", ""))
    mem[k] = r
    _comum.gravar_json(_arq_checagens(), mem)
    return r


def _trecho_da(m: dict, dur_video: float, entrada: float | None = None) -> dict:
    """O trecho conhecido (ou o ponto de entrada que o João escolheu) + o corte já feito em app/.cache/virais/trechos/."""
    arq = _baixar_cand(m)
    memo = CACHE / "faixas" / f"{m['slug']}.trecho.json"
    t = _comum.ler_json(memo, None)
    if not t:
        t = achar_trecho(arq, dur_video)
        _comum.gravar_json(memo, t)
    if entrada is not None:
        t = dict(t, t0=round(float(entrada), 3), motivo="o ponto de entrada que você escolheu")
        jan0 = max(0.0, float(entrada) - 0.5)   # encaixa no kick mais forte em ±0,5 s, pro corte na batida não cair fora de tempo
        a0, f0 = _ataque(_pcm(arq, jan0, 1.3))
        if len(a0) > 8 and a0.max() > 0:
            t["t0"] = round(jan0 + float(a0.argmax()) / f0, 3)
        at, fps = _ataque(_pcm(arq, max(0.0, t["t0"]), 40))
        per = _periodo(at, fps)
        t["periodo"], t["bpm"] = round(per, 4), round(60 / per, 1) if per else 0
    return t


def previa(m: dict, entrada: float | None = None, seg: float = 10.0) -> str:
    """Prévia de 10 s do trecho (a partir do ponto conhecido ou do que o João marcou). Caminho relativo à raiz, pro player."""
    t = _trecho_da(m, 75.0, entrada)
    alvo = CACHE / "previas" / f"{m['slug']}-{round(t['t0'])}.mp3"
    if not alvo.is_file():
        cortar(_baixar_cand(m), alvo, t["t0"], seg)
    return str(alvo.relative_to(RAIZ))


def _recentes(cliente: str, n: int = 8) -> set[str]:
    try:
        import uso_midia as _uso
        return {Path(u.get("arquivo") or u.get("titulo") or "").stem for u in _uso.recentes(cliente, "musica", n)} if cliente else set()
    except Exception:  # noqa: BLE001
        return set()


def _reprovadas(cliente: str) -> set[str]:
    try:
        import musica_busca as _mb
        return _mb.reprovadas(cliente)[0]
    except Exception:  # noqa: BLE001
        return set()


def opcoes(cliente: str = "", texto: str = "", clima_formato: str = "", n: int = 3, job: str = "", ignorar: tuple = (),
           dur_video: float = 75.0, esperado: str = "letra") -> dict:
    """As `n` virais que casam com o clima, JÁ conferidas (baixadas, trecho achado, sem marca d'água). Fora o que o cliente usou
    nos últimos vídeos e o que o João mandou "não usar mais". {opcoes: [...], clima, recusadas: [{titulo, motivos}], paradas_ok}.
    Cada opção: id, titulo, artista, motivo, previa (caminho p/ tocar 10 s), t0, bpm, fontes, aviso."""
    ordem, de_onde = clima_pedido(texto, clima_formato)
    rec, rep = _recentes(cliente), _reprovadas(cliente)
    lista = [m for m in virais(40) if m["slug"] not in rec and ("viral:" + m["slug"]) not in rep and m["id"] not in ignorar]
    ranque = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        perfis = list(ex.map(_perfil, lista[:40]))
    for m, pf in zip(lista[:40], perfis):
        nota, motivo = _pontua(m, pf, ordem, perfis, max(x["score"] for x in lista[:40]))
        ranque.append((nota, m, pf, motivo))
    ranque.sort(key=lambda r: -r[0])
    boas, recusadas = [], []

    def preparar_opcao(item):
        _nota, m, pf, motivo = item
        try:
            t = _trecho_da(m, dur_video)
            chk = _checada(m, t["t0"], min(dur_video, 60.0), esperado)
            if not chk["ok"]:
                return None, {"titulo": f"{m['artista']} - {m['titulo']}", "motivos": chk["motivos"]}
            return {"id": m["id"], "titulo": m["titulo"], "artista": m["artista"], "motivo": f"{motivo[0].upper() + motivo[1:]}. Clima pedido pelo {de_onde}: {' > '.join(ordem[:2])}.",
                    "previa": previa(m), "t0": t["t0"], "bpm": t["bpm"], "trecho": t["motivo"], "fontes": resumo_fontes(m), "aviso": AVISO_DIREITOS,
                    "checagem": "sem voz falada, bip nem silêncio" if chk.get("groq") else "sem bip nem silêncio (voz não conferida: sem Groq)"}, None
        except Exception as e:  # noqa: BLE001
            return None, {"titulo": f"{m['artista']} - {m['titulo']}", "motivos": [f"não deu pra baixar: {str(e)[:90]}"]}

    for i in range(0, len(ranque), 4):   # de 4 em 4, na ordem do ranque, até fechar `n` aprovadas
        with ThreadPoolExecutor(max_workers=4) as ex:
            for ok, ruim in ex.map(preparar_opcao, ranque[i:i + 4]):
                if ok and len(boas) < n:
                    boas.append(ok)
                elif ruim:
                    recusadas.append(ruim)
        if len(boas) >= n:
            break
    return {"opcoes": boas, "clima": ordem, "recusadas": recusadas, "paradas_ok": sorted((paradas().get("listas") or {}).keys())}


def preparar(sandbox, faixa: dict | str, dur: float, entrada: float | None = None, cliente: str = "", esperado: str = "letra") -> dict:
    """Põe a música viral na sandbox: work/musica/<slug>.mp3 (o trecho, 0,15 s antes do ponto conhecido, com `dur` + 3 s), a grade da
    batida em work/batida.json e o ponteiro work/musica/escolhida.json (o gera_lib lê). `faixa` = uma opção de `opcoes()`/`virais()`
    (dict com id/artista/titulo) ou o id/chave 'viral-...'/URL do YouTube. Reprovada na checagem = ValueError com o motivo."""
    sb = Path(sandbox)
    sb = sb if sb.is_absolute() else RAIZ / sb
    url = ""
    if isinstance(faixa, str):
        if faixa.startswith("http"):
            url = faixa
            info = _info_link(url)
            m = {"artista": info["artista"], "titulo": info["titulo"], "url": url}
        else:
            m = next((x for x in virais(80) if x["id"] == faixa or x["chave"] == faixa), None)
            if not m:
                raise ValueError(f"não achei {faixa} nas virais de hoje")
    else:
        m = faixa
    m = dict(m)
    m.setdefault("slug", slug_faixa(m["artista"], m["titulo"]))
    m.setdefault("chave", chave_musica(m["artista"], m["titulo"]))
    arq = _baixar_cand(m) if (url or m.get("url")) else baixar(m, url)
    t = _trecho_da(m, dur, entrada)
    saida = sb / "work" / "musica" / f"{m['slug']}.mp3"
    cortar(arq, saida, t["t0"], dur + 3)
    chk = checar(saida, esperado, 0.0, min(dur, 75.0), titulo=_meta_faixa(m["slug"]).get("titulo", ""))
    if not chk["ok"]:
        raise ValueError("Essa música não serve: " + "; ".join(chk["motivos"]))
    per = t.get("periodo") or 0.0
    _comum.gravar_json(sb / "work" / "batida.json", {"periodo": per, "primeiro": ATRASO_GANCHO, "bpm": t.get("bpm"), "drop": ATRASO_GANCHO, "viral": m["slug"]})
    ponteiro = {"arquivo": str(saida.relative_to(sb)), "titulo": m["titulo"], "artista": m["artista"], "slug": m["slug"], "chave": "viral:" + m["slug"],
                "fonte": "viral", "origem": _meta_faixa(m["slug"]).get("url", url), "t0": t["t0"], "bpm": t.get("bpm"), "trecho": t["motivo"],
                "aviso": AVISO_DIREITOS, "checagem": chk, "em": time.strftime("%Y-%m-%d %H:%M")}
    _comum.gravar_json(sb / "work" / "musica" / "escolhida.json", ponteiro)
    return ponteiro


def _ytinfo(url: str) -> dict:
    r = subprocess.run(_ytdlp() + ["--dump-json", "--no-playlist", url], capture_output=True, text=True, timeout=90)
    try:
        d = json.loads(r.stdout.splitlines()[0])
    except (ValueError, IndexError):
        raise ValueError("não consegui ler esse link") from None
    tit = d.get("track") or d.get("title", "")
    art = d.get("artist") or d.get("channel") or d.get("uploader") or ""
    if not d.get("track") and " - " in tit:
        art, tit = [s.strip() for s in tit.split(" - ", 1)]
    return {"artista": re.sub(r"\s*-\s*Topic$", "", art), "titulo": tit}


def procurar(q: str, n: int = 6) -> list[dict]:
    """"Procurar" na tela: primeiro dentro das virais de hoje, depois uma busca no YouTube (só metadados). Cada item serve pro `preparar`."""
    alvo = _norm(q)
    ach = [m for m in virais(80) if alvo and all(w in _norm(m["artista"] + " " + m["titulo"]) for w in alvo.split())]
    out = [{"id": m["id"], "titulo": m["titulo"], "artista": m["artista"], "motivo": "viral hoje: " + resumo_fontes(m), "viral": True} for m in ach[:n]]
    if len(out) < n and alvo:
        r = subprocess.run(_ytdlp() + ["--flat-playlist", "--dump-json", f"ytsearch{n}:{q} official audio"], capture_output=True, text=True, timeout=90)
        for linha in r.stdout.splitlines():
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            if re.search(TITULO_RUIM, d.get("title", ""), re.I) or (d.get("duration") or 0) > 600:
                continue
            out.append({"id": d.get("webpage_url") or f"https://www.youtube.com/watch?v={d.get('id')}", "titulo": d.get("title", ""),
                        "artista": d.get("channel") or "", "motivo": "do YouTube: confira a prévia", "viral": False})
    return out[:n]


# ───────────────────────── "Procurar" é a direção em palavras: o João diz o clima, o Estúdio acha ─────────────────────────
# Por baixo da narração a música é SEM voz cantada. A voz é medida de verdade (Demucs separa a voz do trecho e compara com a mistura).

LIMITE_VOZ_DB = -20.0     # voz − mistura, em dB: acima disso tem voz cantada (calibrado em 30-out-2026: ver CALIBRACAO_VOZ)
# medido em 30-out-2026 (voz − mistura no trecho de 20 s): Sombr "back to friends" -6,5 · funk "Postinho de Gasolina" -5,2 · instrumental Mixkit 1154 -42,6
CALIBRACAO_VOZ = {"com_voz": (-6.5, -5.2), "instrumental": -42.6}
JANELA_VOZ_S = 20.0
_TRAVA_DEMUCS = __import__("threading").Lock()    # o Demucs usa a CPU toda: uma faixa por vez

# gêneros que brigam com o estilo investigativo/documental quando a música fica por baixo de uma narração
GENEROS_QUE_BRIGAM = {
    "funk": ("funk", "baile", "mandelao", "brega funk", "mc "), "sertanejo": ("sertanej", "arrocha", "modao"),
    "piseiro": ("piseiro", "forro", "pisadinha"), "pagode": ("pagode", "samba", "axe"), "pop": ("pop",),
}
# palavras do pedido em português → termo em inglês pra buscar (Mixkit e YouTube)
TERMOS_EN = (("tens", "tense"), ("suspen", "suspense"), ("misteri", "mystery"), ("investig", "investigation"), ("sombri", "dark"),
             ("escur", "dark"), ("dark", "dark"), ("triste", "sad"), ("melanc", "melancholic"), ("epic", "epic"), ("cinemat", "cinematic"),
             ("anim", "upbeat"), ("alegr", "happy"), ("calm", "calm"), ("relax", "relaxing"), ("corporativ", "corporate"), ("motiv", "motivational"),
             ("document", "documentary"), ("drama", "dramatic"), ("piano", "piano"), ("cordas", "strings"), ("eletron", "electronic"),
             ("trap", "trap"), ("phonk", "phonk"), ("lofi", "lofi"), ("lo-fi", "lofi"), ("ambient", "ambient"), ("grave", "deep bass"),
             ("batida", "beat"), ("hip hop", "hip hop"), ("noticia", "news"), ("urgent", "urgent"), ("espera", "hopeful"))
TITULO_RUIM_DIRECAO = TITULO_RUIM.replace(r"\binstrumental\b|", "")   # na busca por direção "instrumental" é bem-vindo
TITULO_RUIM_DIRECAO += r"|sound\s*effects?|\bsfx\b|ringtone|toque de celular|game\s*show|\balarm|\bcompilation|\bhours?\b|\b\d+\s*horas?"
# o Mixkit só tem página pra algumas tags: pra cada clima, as tags que existem
MIXKIT_POR_CLIMA = {"tensa": ("dark", "cinematic", "documentary"), "sombria": ("dark", "cinematic"), "épica": ("cinematic", "epic"),
                    "animada": ("upbeat", "happy"), "calma": ("relaxing", "ambient"), "corporativa": ("corporate", "documentary")}


def entender_direcao(q: str) -> dict:
    """"tensa de suspense, sem voz" → {climas: ['tensa'], termos_en: ['tense', 'suspense'], sem_voz: True, generos: []}.
    Sem voz é o padrão; só vira "com voz" se o pedido disser (com voz, cantada, com letra)."""
    n = _norm(q)
    com_voz = bool(re.search(r"\bcom (voz|letra)\b|cantad|\bvocal\b", n)) and not re.search(r"\bsem (voz|letra)\b", n)
    climas = []
    for pref, c in CLIMA_PALAVRAS:
        if pref in n and c not in climas:
            climas.append(c)
    termos = list(dict.fromkeys(en for pref, en in TERMOS_EN if pref in n))
    pedidos = [g for g, chaves in GENEROS_QUE_BRIGAM.items() if any(k in n for k in chaves)]
    return {"climas": climas, "termos_en": termos[:4], "sem_voz": not com_voz, "generos": pedidos, "texto": q.strip()}


def genero_briga(m: dict, perfil: dict, pedido: str = "", texto: str = "") -> str:
    """O gênero que briga ('funk', 'sertanejo'...) quando a faixa é dele e ninguém o pediu; '' se pode. O roteiro falar do gênero, do
    artista ou da cena libera (um vídeo sobre o funk pode usar funk)."""
    alvo = _norm(f"{m.get('artista', '')} {m.get('titulo', '')} {perfil.get('genero', '')}")
    livre = _norm(f"{pedido} {texto}")
    for g, chaves in GENEROS_QUE_BRIGAM.items():
        if any(re.search(r"\b" + k, alvo) for k in chaves) and not any(re.search(r"\b" + k, livre) for k in chaves) \
                and _norm(m.get("artista", "")) not in livre:
            return g
    return ""


def _volume_db(arq) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(arq), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    mm = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(mm.group(1)) if mm else -91.0


def voz_na_faixa(arq, ini: float = 0.0, dur: float = JANELA_VOZ_S) -> dict:
    """Mede a voz cantada: o Demucs (midia_local.so_voz) tira a voz de `dur` s do trecho e compara com a mistura.
    {rel_db (voz − mistura; perto de 0 = voz domina, abaixo de -30 = instrumental), tem_voz, voz_db, mistura_db}. Com cache por faixa+trecho."""
    arq = Path(arq)
    mem_arq = CACHE / "vozes.json"
    k = f"{arq.stem}|{round(ini)}|{round(dur)}"
    mem = _comum.ler_json(mem_arq, {}) or {}
    if k in mem:
        return mem[k]
    tmp = CACHE / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    clip = tmp / f"voz-{hashlib.sha1(k.encode()).hexdigest()[:10]}.mp3"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0.0, ini):.2f}", "-t", f"{dur:.2f}", "-i", str(arq), "-vn", "-ac", "2",
                    "-ar", "44100", str(clip)], capture_output=True, timeout=120)
    import midia_local as _ml
    with _TRAVA_DEMUCS:
        r = _ml.so_voz(clip, tmp / (clip.stem + "-voz.mp3"))
    mix = _volume_db(clip)
    voz = float(r.get("rms_voz_db") if r.get("rms_voz_db") is not None else -91.0)
    out = {"rel_db": round(voz - mix, 1), "tem_voz": (voz - mix) > LIMITE_VOZ_DB, "voz_db": round(voz, 1), "mistura_db": round(mix, 1)}
    mem = _comum.ler_json(mem_arq, {}) or {}
    mem[k] = out
    _comum.gravar_json(mem_arq, mem)
    return out


def _info_link(url: str) -> dict:
    """{artista, titulo} de um link do YouTube/SoundCloud ou de um mp3 do Mixkit."""
    if "mixkit.co" in url and url.lower().split("?")[0].endswith(".mp3"):
        return {"artista": "Mixkit", "titulo": Path(urllib.parse.urlparse(url).path).stem.replace("-", " ")}
    return _ytinfo(url)


def _baixar_mp3_direto(url: str, alvo: Path) -> Path:
    import musica_busca as _mb
    alvo.parent.mkdir(parents=True, exist_ok=True)
    _mb._baixar(url, alvo)
    return alvo


def _cand_link(url: str, titulo: str = "") -> dict:
    info = _info_link(url)
    m = {"artista": info["artista"], "titulo": titulo or info["titulo"], "url": url}
    m["slug"], m["chave"] = slug_faixa(m["artista"], m["titulo"]), chave_musica(m["artista"], m["titulo"])
    m["id"] = url
    return m


def _baixar_cand(m: dict) -> Path:
    url = m.get("url") or ""
    if "mixkit.co" in url and url.lower().split("?")[0].endswith(".mp3"):
        return _baixar_mp3_direto(url, CACHE / "faixas" / f"{m['slug']}.mp3")
    return baixar(m, url)


def _opcao_de(m: dict, motivo: str, voz: dict | None, chk: dict, t: dict, fonte: str) -> dict:
    return {"id": m["id"], "titulo": m["titulo"], "artista": m["artista"], "motivo": motivo, "previa": previa(m) if not m.get("url") else _previa_cand(m, t),
            "t0": t["t0"], "bpm": t.get("bpm"), "trecho": t["motivo"], "fonte": fonte, "aviso": AVISO_DIREITOS if fonte.startswith("viral") else "",
            "voz": voz, "checagem": (f"sem voz cantada (voz {voz['rel_db']:+.0f} dB da mistura)" if voz else "instrumental por natureza (Mixkit)" if fonte == "mixkit" else "sem bip nem silêncio") if not (voz and voz["tem_voz"]) else "tem voz cantada"}


def _previa_cand(m: dict, t: dict, seg: float = 10.0) -> str:
    alvo = CACHE / "previas" / f"{m['slug']}-{round(t['t0'])}.mp3"
    if not alvo.is_file():
        cortar(_baixar_cand(m), alvo, t["t0"], seg)
    return str(alvo.relative_to(RAIZ))


def _avaliar(m: dict, d: dict, dur_video: float, fonte: str, motivo: str, medir_voz: bool = True) -> tuple[dict | None, dict | None]:
    """Baixa, acha o trecho, confere marca d'água e mede a voz. (opção, None) ou (None, {titulo, motivos})."""
    nome = f"{m['artista']} - {m['titulo']}"
    try:
        arq = _baixar_cand(m)
        memo = CACHE / "faixas" / f"{m['slug']}.trecho.json"
        t = _comum.ler_json(memo, None)
        if not t:
            t = achar_trecho(arq, dur_video)
            _comum.gravar_json(memo, t)
        voz = voz_na_faixa(arq, t["t0"]) if medir_voz else None
        if voz and d["sem_voz"] and voz["tem_voz"]:
            return None, {"titulo": nome, "motivos": [f"tem voz cantada (voz {voz['rel_db']:+.0f} dB da mistura; o limite é {LIMITE_VOZ_DB:+.0f})"]}
        chk = checar(arq, "instrumental" if d["sem_voz"] else "letra", max(0.0, t["t0"] - ATRASO_GANCHO), min(dur_video, 60.0), titulo=_meta_faixa(m["slug"]).get("titulo", ""))
        if not chk["ok"]:
            return None, {"titulo": nome, "motivos": chk["motivos"]}
        return _opcao_de(m, motivo, voz, chk, t, fonte), None
    except Exception as e:  # noqa: BLE001
        return None, {"titulo": nome, "motivos": [f"não deu pra baixar: {str(e)[:90]}"]}


def _versao_instrumental(m: dict, d: dict, dur_video: float, motivo: str, vistos: set) -> tuple[dict | None, list[dict]]:
    """A viral `m` (cantada) → a versão instrumental dela no YouTube ("instrumental", "official instrumental", "karaoke", "beat"): baixa, mede a voz
    (Demucs, limite LIMITE_VOZ_DB) e confere marca d'água. (opção, recusadas). Entra como viral: "a viral X, versão instrumental"."""
    ruins, vistas = [], 0
    nome = f"{m['artista']} - {m['titulo']}"
    for sufixo in ("instrumental", "official instrumental", "karaoke", "beat"):
        if vistas >= 2:
            break
        try:
            r = subprocess.run(_ytdlp() + ["--flat-playlist", "--dump-json", f"ytsearch4:{m['artista']} {m['titulo']} {sufixo}"],
                               capture_output=True, text=True, timeout=90)
        except Exception:  # noqa: BLE001
            continue
        for linha in r.stdout.splitlines():
            try:
                x = json.loads(linha)
            except ValueError:
                continue
            tit = x.get("title", "")
            nt = _norm(tit)
            if not re.search(r"instrumental|karaok|\bbeat\b|sem voz|sin voz", nt) or re.search(TITULO_RUIM_DIRECAO, tit, re.I) \
                    or not 60 <= (x.get("duration") or 0) <= 420:
                continue
            # tem de ser dessa música: o título cita a música (ou o artista)
            if _norm(_limpa_titulo(m["titulo"])).split()[0] not in nt and _norm(m["artista"]).split()[0] not in nt:
                continue
            url = x.get("webpage_url") or f"https://www.youtube.com/watch?v={x.get('id')}"
            if url in vistos or vistas >= 2:
                continue
            vistas += 1
            v = {"artista": m["artista"], "titulo": m["titulo"] + " (versão instrumental)", "url": url, "id": url}
            # slug próprio (com o id do vídeo): o "(versão instrumental)" some na limpeza do título e a faixa cairia no mp3 da original
            v["slug"], v["chave"] = slug_faixa(v["artista"], f"{m['titulo']} instr {x.get('id') or vistas}"), chave_musica(v["artista"], v["titulo"] + " instrumental")
            op, ruim = _avaliar(v, d, dur_video, "viral-instrumental", f"a viral {nome}, versão instrumental ({x.get('channel') or 'YouTube'}); {motivo.split(';')[0]}")
            if op:
                return op, ruins
            if ruim:
                ruim["titulo"] = f"{nome} (instrumental: {tit[:50]})"
                ruins.append(ruim)
    return None, ruins


def _termo_busca(d: dict, climas_ord: list[str]) -> str:
    termos = d["termos_en"] or [dict((c, e) for c, e in (("tensa", "tense"), ("sombria", "dark"), ("épica", "epic"), ("animada", "upbeat"), ("calma", "calm"),
                                                         ("corporativa", "corporate"))).get(c, c) for c in climas_ord[:2]][0:2]
    return " ".join(termos[:3]) or "tense dark"


def por_direcao(q: str = "", cliente: str = "", texto: str = "", clima_formato: str = "", n: int = 3, ignorar: tuple = (),
                dur_video: float = 75.0, job: str = "") -> dict:
    """O "Procurar" e o "Viral do momento" numa coisa só. `q` = a direção em palavras ("tensa de suspense, sem voz"); vazio = o clima do estilo
    + o tom do roteiro. Procura sozinho, nesta ordem: virais de hoje (sem o gênero que briga e sem voz cantada), áudio oficial no YouTube
    e Mixkit. Devolve até `n` opções com prévia e o MOTIVO. {opcoes, clima, recusadas, direcao, entendi}. Nome ou link também valem."""
    q = (q or "").strip()
    out_link = []
    if re.match(r"https?://", q):   # link colado: vale esse, conferido
        m = _cand_link(q)
        op, ruim = _avaliar(m, {"sem_voz": False}, dur_video, "link", "o link que você colou", medir_voz=False)
        return {"opcoes": [op] if op else [], "clima": [], "recusadas": [ruim] if ruim else [], "direcao": q, "entendi": "link"}
    d = entender_direcao(q)
    base_ordem, de_onde = clima_pedido(texto + " " + q, clima_formato)
    ordem = d["climas"] + [c for c in base_ordem if c not in d["climas"]]
    rec, rep = _recentes(cliente), _reprovadas(cliente)
    boas, recusadas, vistos = [], [], set(ignorar)

    def vale(o):
        return o and o["id"] not in vistos and len(boas) < n

    # 0) o nome de uma viral de hoje que ele digitou (ainda funciona)
    if q and len(q.split()) >= 1 and not d["climas"] and not d["termos_en"]:
        for m in [x for x in virais(80) if all(w in _norm(x["artista"] + " " + x["titulo"]) for w in _norm(q).split())][:2]:
            op, ruim = _avaliar(m, {"sem_voz": False}, dur_video, "viral", "viral hoje: " + resumo_fontes(m), medir_voz=False)
            if vale(op):
                boas.append(op); vistos.add(op["id"])
            elif ruim:
                recusadas.append(ruim)
    # 1) virais de hoje: casa com o clima, sem o gênero que briga, sem voz cantada
    if len(boas) < n:
        lista = [m for m in virais(40) if m["slug"] not in rec and ("viral:" + m["slug"]) not in rep and m["id"] not in vistos]
        with ThreadPoolExecutor(max_workers=6) as ex:
            perfis = list(ex.map(_perfil, lista[:40]))
        ranque, ranque_instr, por_genero = [], [], {}
        for m, pf in zip(lista[:40], perfis):
            g = genero_briga(m, pf, q, texto)
            if g:
                por_genero.setdefault(g, []).append(f"{m['artista']} - {m['titulo']}")
                if g != "pop":   # a versão instrumental de um pop não tem o problema do pop (a voz); funk, sertanejo etc. seguem de fora
                    continue
                nota, motivo = _pontua(m, pf, ordem, perfis, max(x["score"] for x in lista[:40]))
                ranque_instr.append((nota, m, motivo))
                continue
            nota, motivo = _pontua(m, pf, ordem, perfis, max(x["score"] for x in lista[:40]))
            ranque.append((nota, m, motivo))
            ranque_instr.append((nota, m, motivo))
        for g, nomes in por_genero.items():
            recusadas.append({"titulo": f"{len(nomes)} viral(is) de {g}", "motivos": [f"{g} briga com o estilo e com o assunto (nem o pedido nem o roteiro falam disso); ex.: {nomes[0]}"]})
        ranque.sort(key=lambda r: -r[0])
        for _nota, m, motivo in ranque[:4]:   # 1) a viral que já é instrumental (trilha que viralizou). O Demucs é lento: só as que mais casam
            if len(boas) >= n:
                break
            op, ruim = _avaliar(m, d, dur_video, "viral", f"viral hoje ({resumo_fontes(m)}); {motivo.split(';')[0]}")
            if vale(op):
                boas.append(op); vistos.add(op["id"])
            elif ruim:
                recusadas.append(ruim)
        ranque_instr.sort(key=lambda r: -r[0])
        if d["sem_voz"]:   # 1b) a viral cantada que casa com o clima: procura a VERSÃO INSTRUMENTAL dela no YouTube, mede e confere
            for _nota, m, motivo in ranque_instr[:6]:
                if len(boas) >= n:
                    break
                if m["id"] in vistos:   # essa viral já entrou como ela mesma (já é instrumental): não repete
                    continue
                op, ruins = _versao_instrumental(m, d, dur_video, motivo, vistos)
                if op:
                    boas.append(op); vistos.add(op["id"])
                recusadas.extend(ruins)
    # 2) áudio oficial do YouTube pelo clima pedido
    termo = _termo_busca(d, ordem)
    if len(boas) < n:
        try:
            r = subprocess.run(_ytdlp() + ["--flat-playlist", "--dump-json", f"ytsearch8:{termo} music instrumental official audio no copyright"],
                               capture_output=True, text=True, timeout=90)
            cont = 0
            for linha in r.stdout.splitlines():
                try:
                    x = json.loads(linha)
                except ValueError:
                    continue
                if re.search(TITULO_RUIM_DIRECAO, x.get("title", ""), re.I) or not 60 <= (x.get("duration") or 0) <= 420:
                    continue
                url = x.get("webpage_url") or f"https://www.youtube.com/watch?v={x.get('id')}"
                if url in vistos or cont >= 3 or len(boas) >= n:
                    continue
                cont += 1
                m = {"artista": re.sub(r"\s*-\s*Topic$", "", x.get("channel") or ""), "titulo": x.get("title", ""), "url": url, "id": url}
                m["slug"], m["chave"] = slug_faixa(m["artista"], m["titulo"]), chave_musica(m["artista"], m["titulo"])
                op, ruim = _avaliar(m, d, dur_video, "youtube", f"áudio do YouTube achado pela direção “{termo}”")
                if vale(op):
                    boas.append(op); vistos.add(op["id"])
                elif ruim:
                    recusadas.append(ruim)
        except Exception as e:  # noqa: BLE001
            recusadas.append({"titulo": "YouTube", "motivos": [f"a busca não respondeu: {str(e)[:80]}"]})
    # 3) Mixkit: instrumental por natureza (a checagem confere de qualquer jeito)
    if len(boas) < n:
        try:
            import musica_busca as _mb
            tags = list(d["termos_en"]) + [t for c in ordem[:2] for t in MIXKIT_POR_CLIMA.get(c, ())]
            for tag in dict.fromkeys(tags):
                for it in (_mb.buscar_mixkit(tag, 8).get("itens") or []):
                    if len(boas) >= n:
                        break
                    if it["baixar"] in vistos or _norm(it["titulo"]) in {_norm(b["titulo"]) for b in boas}:
                        continue
                    m = {"artista": "Mixkit", "titulo": it["titulo"], "url": it["baixar"], "id": it["baixar"]}
                    m["slug"], m["chave"] = slug_faixa("Mixkit", it["titulo"]), chave_musica("Mixkit", it["titulo"])
                    op, ruim = _avaliar(m, d, dur_video, "mixkit", ("nenhuma viral instrumental passou na checagem; ficou o Mixkit, grátis e sem voz" + (f" (tag “{tag}”)" if tag in d["termos_en"] else f" (“{tag}” é a tag do Mixkit mais próxima do que você pediu)")), medir_voz=False)
                    if vale(op):
                        boas.append(op); vistos.add(op["id"])
                    elif ruim:
                        recusadas.append(ruim)
                if len(boas) >= n:
                    break
        except Exception as e:  # noqa: BLE001
            recusadas.append({"titulo": "Mixkit", "motivos": [f"a busca não respondeu: {str(e)[:80]}"]})
    ent = ", ".join(d["climas"] or ordem[:2]) + (" · sem voz cantada" if d["sem_voz"] else " · pode ter voz") + (f" · {', '.join(d['termos_en'])}" if d["termos_en"] else "")
    return {"opcoes": boas, "clima": ordem, "recusadas": recusadas, "direcao": q, "entendi": ent, "de_onde": de_onde}


# ───────────────────────── corte na batida (a mesma conta do gera_lib.fechar) ─────────────────────────

def casar_cortes(doc: dict, periodo: float, primeiro: float = ATRASO_GANCHO) -> int:
    """Depois de trocar a música: cena que começa até 0,12 s depois ou 0,06 s antes de um meio-tempo da NOVA grade vai pra ele
    (os efeitos que estavam no corte vão junto). Devolve quantas cenas se moveram."""
    cs, fx = doc.get("cenas") or [], doc.get("efeitos") or []
    if not periodo or len(cs) < 2:
        return 0
    dur = float(doc.get("duracao") or cs[-1]["de"] + 2)
    meio = periodo / 2
    grade = [primeiro + k * meio for k in range(int(dur / meio) + 2)]
    mov = 0
    for i, x in enumerate(cs[1:], 1):
        b = min(grade, key=lambda g: abs(g - x["de"]))
        if -.12 <= b - x["de"] <= .06 and b > cs[i - 1]["de"] + .3 and abs(b - x["de"]) > 1e-6:
            antigo, novo = x["de"], round(b, 3)
            for e in fx:
                if isinstance(e, dict) and abs(float(e.get("t", -9)) - antigo) <= .07 + .05:
                    e["t"] = round(float(e["t"]) + (novo - antigo), 3)
            x["de"] = novo
            mov += 1
    return mov


def nivelar(mp3) -> dict:
    """Tira os picos da faixa e a deixa num volume constante (compressor + limitador + loudnorm -22 LUFS): trap e 808 têm batida bem
    mais alta que o resto e passavam por cima da voz (João, 05-nov-2026: "tem alguns pontos mais altos do que o normal"). Guarda o original ao lado."""
    mp3 = Path(mp3)
    orig = mp3.with_name(mp3.stem + ".original.mp3")
    if not orig.exists():
        shutil.copy2(mp3, orig)
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(orig), "-af",
                        "acompressor=threshold=0.06:ratio=8:attack=3:release=150:makeup=1,alimiter=limit=0.35:attack=2:release=60,loudnorm=I=-22:TP=-3:LRA=5",
                        "-ar", "44100", str(mp3)], capture_output=True, text=True)
    return {"ok": r.returncode == 0, "original": orig.name, **({"erro": r.stderr[-200:]} if r.returncode else {})}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("virais"); a.add_argument("-n", type=int, default=10); a.add_argument("--forcar", action="store_true")
    a = sp.add_parser("opcoes"); a.add_argument("--formato", default=""); a.add_argument("--cliente", default=""); a.add_argument("--texto", default="")
    a.add_argument("-n", type=int, default=3)
    a = sp.add_parser("escolher"); a.add_argument("sandbox"); a.add_argument("--dur", type=float, required=True); a.add_argument("--faixa", default="")
    a.add_argument("--entrada", type=float); a.add_argument("--cliente", default=""); a.add_argument("--formato", default="editorial"); a.add_argument("--texto", default="")
    a.add_argument("--direcao", default=""); a.add_argument("--nivelar", action="store_true")
    a = sp.add_parser("direcao"); a.add_argument("direcao", nargs="?", default=""); a.add_argument("--formato", default=""); a.add_argument("--cliente", default="")
    a.add_argument("--texto", default=""); a.add_argument("-n", type=int, default=3)
    a = sp.add_parser("checar"); a.add_argument("mp3"); a.add_argument("--esperado", default="letra"); a.add_argument("--ini", type=float, default=0.0)
    a.add_argument("--dur", type=float)
    c = ap.parse_args()
    if c.cmd == "virais":
        d = paradas(c.forcar)
        print("paradas:", ", ".join(f"{k} ({len(v)})" for k, v in d["listas"].items()), "| falharam:", d.get("erros") or "nenhuma")
        for i, m in enumerate(virais(c.n, False), 1):
            print(f"{i:2}. {m['artista']} - {m['titulo']}  [{m['score']}]  {resumo_fontes(m)}")
    elif c.cmd == "opcoes":
        clima = ""
        try:
            f = _comum.ler_json(RAIZ / "formatos" / c.formato / "formato.json", {}) or {}
            clima = ((f.get("som") or {}).get("musica") or {}).get("clima", "")
        except Exception:  # noqa: BLE001
            pass
        print(json.dumps(opcoes(c.cliente, c.texto, clima, c.n), ensure_ascii=False, indent=1))
    elif c.cmd == "direcao":
        f = _comum.ler_json(RAIZ / "formatos" / c.formato / "formato.json", {}) or {}
        print(json.dumps(por_direcao(c.direcao, c.cliente, c.texto, ((f.get("som") or {}).get("musica") or {}).get("clima", ""), c.n), ensure_ascii=False, indent=1))
    elif c.cmd == "escolher":
        faixa, nivelar_ = c.faixa, c.nivelar
        padrao = ((_comum.ler_json(_comum.RAIZ / "clientes" / c.cliente / "identidade.json", {}) or {}).get("musica_padrao") or {}) if c.cliente else {}
        if not faixa and padrao.get("faixa") and not c.direcao:   # música padrão do cliente (João, 05-nov-2026)
            faixa, nivelar_ = padrao["faixa"], nivelar_ or bool(padrao.get("nivelar"))
        if not faixa:   # sem faixa: a 1ª da busca por direção (sem voz cantada, sem o gênero que briga)
            f = _comum.ler_json(RAIZ / "formatos" / c.formato / "formato.json", {}) or {}
            r = por_direcao(c.direcao, c.cliente, c.texto, ((f.get("som") or {}).get("musica") or {}).get("clima", ""), 1, dur_video=c.dur)
            if not r["opcoes"]:
                sys.exit("nenhuma viral passou na checagem: " + json.dumps(r["recusadas"], ensure_ascii=False))
            faixa = r["opcoes"][0]["id"]
        res = preparar(c.sandbox, faixa, c.dur, c.entrada, c.cliente)
        if nivelar_:
            res["nivelada"] = nivelar(Path(c.sandbox) / res["arquivo"])
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif c.cmd == "checar":
        print(json.dumps(checar(c.mp3, c.esperado, c.ini, c.dur), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
