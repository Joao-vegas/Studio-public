#!/usr/bin/env python3
"""
fala — acha o SEGUNDO EXATO em que alguém diz algo, dentro de vídeos da internet.

O problema que resolve: buscar "Lula três refeições por dia" devolve um vídeo de 2 horas da posse.
O trecho útil são 6 segundos lá pelos 47 minutos. Sem isso, o b-roll vira "pessoa genérica no plenário".

Como funciona (tudo sem baixar o vídeo inteiro):
  1. yt-dlp pega a LEGENDA do vídeo (manual ou automática, pt/en/es) com tempo em cada linha
  2. procura a frase/tema na legenda (normalizando acento, com busca aproximada por palavras-chave)
  3. devolve os momentos: t0, t1, o texto dito e um link direto (youtu.be/ID?t=...)
  4. `cortar` baixa só aquele intervalo (yt-dlp --download-sections) com folga

Sem legenda disponível, `--whisper` baixa só o áudio e transcreve com GROQ (chave no app/.env).

CLI:
  fala.py buscar "lula três refeições por dia" --limite 6        procura vídeos candidatos
  fala.py achar <url> "três refeições" [--whisper]                momentos exatos naquele vídeo
  fala.py missao "lula" "promessa das três refeições" --limite 5  busca + acha em todos, de uma vez
  fala.py cortar <url> 2830 2838 saida.mp4 [--folga 1]            baixa só o trecho
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ensure, make_slug

LINGUAS = ["pt", "pt-BR", "pt-orig", "en", "en-orig", "es"]
STOP = {"de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "que", "em", "um", "uma", "por",
        "com", "no", "na", "para", "pra", "se", "the", "of", "and", "to", "in", "is", "it"}


from _comum import _norm  # noqa: E402  (uma cópia só)


def buscar(termo: str, limite: int = 6) -> list[dict]:
    """Candidatos no YouTube, com duração e canal (sem baixar nada)."""
    r = subprocess.run(["yt-dlp", "--no-update", "--flat-playlist", "--print",
                        "%(id)s\t%(title)s\t%(channel)s\t%(duration)s",
                        f"ytsearch{limite}:{termo}"], capture_output=True, text=True, timeout=180)
    out = []
    for l in (r.stdout or "").strip().splitlines():
        p = l.split("\t")
        if len(p) >= 4 and p[0]:
            out.append({"id": p[0], "titulo": p[1], "canal": p[2],
                        "duracao_s": int(float(p[3])) if p[3] not in ("NA", "None", "") else None,
                        "url": f"https://youtu.be/{p[0]}"})
    return out


def _vtt(texto: str) -> list[dict]:
    """Parser de VTT/SRT → [{t0, t1, texto}] sem duplicar as linhas roladas da legenda automática."""
    linhas, atual = [], None
    for l in texto.splitlines():
        m = re.match(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})", l)
        if m:
            g = [int(x) for x in m.groups()]
            atual = {"t0": g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                     "t1": g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000, "texto": ""}
            linhas.append(atual)
        elif atual is not None and l.strip() and not l.strip().isdigit() and "WEBVTT" not in l:
            t = re.sub(r"<[^>]+>", "", l).strip()
            if t and t not in atual["texto"]:
                atual["texto"] = (atual["texto"] + " " + t).strip()
    # junta blocos e remove repetição da legenda rolante
    saida, ultimo = [], ""
    for b in linhas:
        t = b["texto"].strip()
        if not t or t == ultimo:
            continue
        if ultimo and t.startswith(ultimo):
            t = t[len(ultimo):].strip()
        if t:
            saida.append({"t0": round(b["t0"], 1), "t1": round(b["t1"], 1), "texto": t})
            ultimo = b["texto"].strip()
    return saida


def transcricao(url: str, whisper: bool = False, cliente: str = "Joao") -> list[dict]:
    """Legenda do vídeo com tempos. Tenta legenda oficial/automática; --whisper baixa o áudio e transcreve."""
    d = Path(tempfile.mkdtemp(prefix="fala-"))
    if not whisper:
        subprocess.run(["yt-dlp", "--no-update", "--skip-download", "--write-subs", "--write-auto-subs",
                        "--sub-langs", ",".join(LINGUAS), "--sub-format", "vtt/srt",
                        "-o", str(d / "leg"), url], capture_output=True, text=True, timeout=300)
        for lg in LINGUAS:
            for p in sorted(d.glob(f"leg*{lg}*.vtt")) + sorted(d.glob(f"leg*{lg}*.srt")):
                segs = _vtt(p.read_text(encoding="utf-8", errors="ignore"))
                if segs:
                    return segs
        for p in sorted(d.glob("leg*.vtt")) + sorted(d.glob("leg*.srt")):
            segs = _vtt(p.read_text(encoding="utf-8", errors="ignore"))
            if segs:
                return segs
    # fallback: áudio + GROQ
    subprocess.run(["yt-dlp", "--no-update", "-x", "--audio-format", "mp3", "--audio-quality", "5",
                    "-o", str(d / "a.%(ext)s"), url], capture_output=True, timeout=900)
    mp3 = next(iter(d.glob("a.mp3")), None)
    if not mp3:
        return []
    import chaves
    chave = chaves.chave("GROQ_API_KEY", cliente, RAIZ)
    if not chave:
        return []
    r = subprocess.run(["curl", "-s", "https://api.groq.com/openai/v1/audio/transcriptions",
                        "-H", f"Authorization: Bearer {chave}", "-F", "model=whisper-large-v3",
                        "-F", "response_format=verbose_json", "-F", f"file=@{mp3}"],
                       capture_output=True, text=True, timeout=900)
    try:
        js = json.loads(r.stdout)
        return [{"t0": round(s["start"], 1), "t1": round(s["end"], 1), "texto": s["text"].strip()}
                for s in js.get("segments", [])]
    except Exception:
        return []


def achar(segs: list[dict], alvo: str, minimo: float = 0.34) -> list[dict]:
    """Momentos em que o alvo é dito. Casa frase exata e, se não houver, por palavras-chave."""
    alvo_n = _norm(alvo)
    chaves = [p for p in alvo_n.split() if p and p not in STOP and len(p) > 2]
    if not chaves:
        return []
    achados = []
    for i, s in enumerate(segs):
        # janela de 3 blocos: a frase costuma quebrar entre linhas da legenda
        ctx = " ".join(x["texto"] for x in segs[i:i + 3])
        n = _norm(ctx)
        if alvo_n and alvo_n in n:
            nota = 1.0
        else:
            nota = sum(1 for k in chaves if k in n) / len(chaves)
        if nota >= minimo:
            achados.append({"t0": s["t0"], "t1": segs[min(i + 2, len(segs) - 1)]["t1"],
                            "texto": ctx[:300], "nota": round(nota, 2)})
    # funde achados colados e ordena por nota
    fundidos = []
    for a in sorted(achados, key=lambda x: x["t0"]):
        if fundidos and a["t0"] - fundidos[-1]["t1"] < 5:
            fundidos[-1]["t1"] = max(fundidos[-1]["t1"], a["t1"])
            fundidos[-1]["nota"] = max(fundidos[-1]["nota"], a["nota"])
        else:
            fundidos.append(a)
    return sorted(fundidos, key=lambda x: -x["nota"])[:8]


def missao(quem: str, oque: str, limite: int = 5, whisper: bool = False) -> list[dict]:
    """Busca vídeos de `quem` e acha onde `oque` é dito em cada um. É a 'missão' do briefing."""
    out = []
    for v in buscar(f"{quem} {oque}", limite):
        segs = transcricao(v["url"], whisper=whisper)
        if not segs:
            out.append({**v, "erro": "sem legenda disponível (use --whisper)"})
            continue
        ms = achar(segs, oque)
        out.append({**v, "momentos": [{**m, "link": f"{v['url']}?t={int(m['t0'])}"} for m in ms],
                    "blocos_legenda": len(segs)})
    return sorted(out, key=lambda v: -(v.get("momentos") or [{"nota": 0}])[0]["nota"] if v.get("momentos") else 0)


def cortar(url: str, t0: float, t1: float, saida: Path, folga: float = 1.0) -> Path | None:
    """Baixa SÓ o intervalo (com folga), em 1080p quando houver."""
    a, b = max(0, t0 - folga), t1 + folga
    saida = Path(saida); ensure(saida.parent)
    subprocess.run(["yt-dlp", "--no-update", "--no-playlist", "-f", "bv*[height<=1080]+ba/b[height<=1080]",
                    "--merge-output-format", "mp4", "--download-sections", f"*{a}-{b}",
                    "--force-keyframes-at-cuts", "-o", str(saida.with_suffix(".%(ext)s")), url],
                   capture_output=True, timeout=900)
    return saida if saida.exists() else next(iter(saida.parent.glob(saida.stem + ".*")), None)


def main():
    ap = argparse.ArgumentParser(description="Acha o segundo exato em que alguém diz algo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buscar"); b.add_argument("termo"); b.add_argument("--limite", type=int, default=6)
    a = sub.add_parser("achar"); a.add_argument("url"); a.add_argument("alvo"); a.add_argument("--whisper", action="store_true")
    m = sub.add_parser("missao"); m.add_argument("quem"); m.add_argument("oque")
    m.add_argument("--limite", type=int, default=5); m.add_argument("--whisper", action="store_true")
    c = sub.add_parser("cortar"); c.add_argument("url"); c.add_argument("t0", type=float)
    c.add_argument("t1", type=float); c.add_argument("saida"); c.add_argument("--folga", type=float, default=1.0)
    args = ap.parse_args()
    if args.cmd == "buscar":
        for v in buscar(args.termo, args.limite):
            print(f"{v['url']}  {v['duracao_s']}s  {v['titulo'][:70]} :: {v['canal']}")
    elif args.cmd == "achar":
        segs = transcricao(args.url, args.whisper)
        if not segs:
            print("✗ sem legenda; tente --whisper"); sys.exit(1)
        print(f"({len(segs)} blocos de legenda)")
        for m_ in achar(segs, args.alvo):
            print(f"  {m_['t0']}–{m_['t1']}s (nota {m_['nota']}) {args.url}?t={int(m_['t0'])}\n    “{m_['texto'][:200]}”")
    elif args.cmd == "missao":
        print(json.dumps(missao(args.quem, args.oque, args.limite, args.whisper), ensure_ascii=False, indent=2))
    else:
        p = cortar(args.url, args.t0, args.t1, Path(args.saida), args.folga)
        print(p or "✗ falhou")


if __name__ == "__main__":
    main()


def groq_transcrever(video, chave: str, dica: str = "", idioma: str = "pt", pedaco_s: int = 600, tentativas: int = 3) -> dict:
    """Transcreve com o Groq em pedaços de MP3 mono 16 kHz 64k (cabe nos 25 MB) e soma o início de cada pedaço
    nos tempos. Tenta de novo em 429/5xx/rede (espera o "try again in Xs", teto 60 s). Devolve
    {"words": [...], "segments": [...], "text": "..."}."""
    import math
    import time
    from _comum import ffprobe, MSG_GROQ_LIMITE
    dur = float(ffprobe(video).get("duracao") or 0)
    saida = {"words": [], "segments": [], "text": ""}
    with tempfile.TemporaryDirectory() as tmp:
        for ini in range(0, max(1, math.ceil(dur)), pedaco_s):
            mp3 = Path(tmp) / f"voz-{ini}.mp3"
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(ini), "-i", str(video), "-t", str(pedaco_s),
                            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(mp3)], capture_output=True, timeout=600)
            if not mp3.exists() or not mp3.stat().st_size:
                continue
            js = _groq_pedaco(mp3, chave, dica, idioma, tentativas)
            for k in ("words", "segments"):
                for row in js.get(k) or []:
                    saida[k].append({**row, "start": row["start"] + ini, "end": row["end"] + ini})
            saida["text"] = (saida["text"] + " " + (js.get("text") or "")).strip()
    return saida


def _groq_pedaco(mp3, chave, dica, idioma, tentativas):
    import time
    from _comum import MSG_GROQ_LIMITE
    cmd = ["curl", "-s", "-A", "Estudio/2.0", "--max-time", "300", "-w", "\n%{http_code}", "https://api.groq.com/openai/v1/audio/transcriptions",
           "-H", f"Authorization: Bearer {chave}", "-F", "model=whisper-large-v3", *(["-F", f"language={idioma}"] if idioma else []),
           "-F", "response_format=verbose_json", *(["-F", f"prompt={dica}"] if dica else []),
           "-F", "timestamp_granularities[]=word", "-F", "timestamp_granularities[]=segment", "-F", f"file=@{mp3}"]
    for n in range(tentativas):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=330)
        corpo, _, codigo = (r.stdout or "").rpartition("\n")
        repetir = r.returncode != 0 or codigo.strip() == "429" or codigo.strip().startswith("5")
        if not repetir:
            try:
                js = json.loads(corpo)
            except ValueError:
                raise RuntimeError("GROQ não devolveu transcrição: " + (corpo or r.stderr or "")[:300])
            if js.get("error"):
                raise RuntimeError("GROQ: " + str(js["error"])[:300])
            return js
        if n < tentativas - 1:
            m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", corpo or "")
            espera = (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else 5 * (n + 1)
            time.sleep(min(60, espera))
    raise RuntimeError(MSG_GROQ_LIMITE)
