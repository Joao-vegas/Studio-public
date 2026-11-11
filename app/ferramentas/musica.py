#!/usr/bin/env python3
"""
musica — analisa uma música SEM precisar escutar: mede números e transforma o som em IMAGEM.

O Claude não tem ouvido, mas tem olho e matemática. Então a análise é:
  NÚMEROS   duração, BPM (autocorrelação da energia), LUFS, pico, faixa dinâmica,
            energia por segundo, graves/médios/agudos por trecho
  IMAGENS   waveform (forma de onda) e espectrograma — o Claude LÊ essas imagens e enxerga
            a estrutura: onde entra o beat, onde tem build, onde cai, onde é só cama
  SEÇÕES    intro / build / drop / cama / final detectados pela curva de energia
  CONTEXTO  título, canal, descrição e capítulos do YouTube (quase sempre dizem o gênero)

Resultado: <destino>/analise.json + waveform.png + espectro.png + curva.png, e um resumo em texto
pronto pro acervo. O João escuta e confirma — a máquina só reduz de 50 candidatas pra 3.

CLI:
    musica.py <url-ou-arquivo> [--out pasta] [--titulo "..."] [--acervo] [--tags "a,b"]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ensure, ffprobe, make_slug, gravar_json, now_slug

SR = 22050          # taxa de amostragem da análise
HOP = 512           # ~23ms por quadro


def _pcm(mp3: Path):
    """Áudio mono float32 via ffmpeg (sem numpy externo além do já instalado)."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(mp3), "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype="<f4")


def _envelope(x):
    """Energia (RMS) por quadro + envelope de ataque (onset)."""
    import numpy as np
    n = len(x) // HOP
    q = x[: n * HOP].reshape(n, HOP)
    rms = np.sqrt((q ** 2).mean(axis=1) + 1e-12)
    onset = np.maximum(0, np.diff(rms, prepend=rms[0]))
    return rms, onset


def _bpm(onset) -> tuple[float, float]:
    """BPM por autocorrelação do envelope de ataque. Devolve (bpm, confiança 0-1)."""
    import numpy as np
    o = onset - onset.mean()
    if o.std() < 1e-9:
        return 0.0, 0.0
    ac = np.correlate(o, o, mode="full")[len(o) - 1:]
    ac /= (ac[0] + 1e-12)
    fps = SR / HOP
    lo, hi = int(fps * 60 / 200), int(fps * 60 / 55)      # 55–200 BPM
    janela = ac[lo:hi]
    if len(janela) < 3:
        return 0.0, 0.0
    i = int(np.argmax(janela)) + lo
    bpm = 60.0 * fps / i
    while bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm, 1), round(float(janela.max()), 2)


def _bandas(x, ini: float, fim: float) -> dict:
    """Proporção de grave/médio/agudo num trecho (FFT simples)."""
    import numpy as np
    a, b = int(ini * SR), int(fim * SR)
    seg = x[a:b]
    if len(seg) < 2048:
        return {}
    esp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freq = np.fft.rfftfreq(len(seg), 1 / SR)
    tot = esp.sum() + 1e-12
    return {
        "grave": round(float(esp[(freq < 250)].sum() / tot), 2),
        "medio": round(float(esp[(freq >= 250) & (freq < 4000)].sum() / tot), 2),
        "agudo": round(float(esp[freq >= 4000].sum() / tot), 2),
    }


def _por_segundo(rms):
    import numpy as np
    seg = int(SR / HOP)
    n = len(rms) // seg
    return np.array([rms[i * seg:(i + 1) * seg].mean() for i in range(n)]) if n else np.array([])


def _suave(v, janela=5):
    import numpy as np
    if len(v) < janela:
        return v
    k = np.ones(janela) / janela
    return np.convolve(v, k, mode="same")


def _secoes(rms, dur: float) -> list[dict]:
    """Seções por nível de energia, com a curva SUAVIZADA (senão vira picotado inútil)."""
    import numpy as np
    por_s = _por_segundo(rms)
    if len(por_s) < 8:
        return []
    norm = _suave(por_s / (por_s.max() + 1e-12))
    def nivel(v):
        return "alta" if v >= 0.7 else ("media" if v >= 0.4 else "cama")
    out, atual, ini = [], nivel(norm[0]), 0
    for i in range(1, len(norm)):
        nv = nivel(norm[i])
        if nv != atual:
            if i - ini >= 5:                       # ignora oscilação curta
                out.append({"t0": ini, "t1": i, "nivel": atual, "energia": round(float(norm[ini:i].mean()), 2)})
                ini = i
            atual = nv
    out.append({"t0": ini, "t1": len(norm), "nivel": atual, "energia": round(float(norm[ini:].mean()), 2)})
    return [s for s in out if s["t1"] - s["t0"] >= 4]


def _trechos(rms, onset, dur: float) -> list[dict]:
    """Propõe TRECHOS USÁVEIS com entrada e saída: 'do 20 ao 25 serve pra gancho', etc.
    Um reel usa 20-60s de uma música de 3 min — o que importa é ONDE cortar."""
    import numpy as np
    por_s = _por_segundo(rms)
    if len(por_s) < 20:
        return []
    norm = _suave(por_s / (por_s.max() + 1e-12))
    n = len(norm)
    out = []

    def add(tipo, t0, t1, motivo, nota):
        t0, t1 = int(max(0, t0)), int(min(n, t1))
        if t1 - t0 < 3:
            return
        if any(x["tipo"] == tipo and abs(x["inicio_s"] - t0) < 8 for x in out):
            return
        out.append({"tipo": tipo, "inicio_s": t0, "fim_s": t1, "duracao_s": t1 - t0,
                    "energia_media": round(float(norm[t0:t1].mean()), 2), "motivo": motivo, "nota": round(nota, 2)})

    # CAMA: janelas de 20s mais baixas e estáveis (fica embaixo da voz sem competir)
    jan = 20
    if n > jan + 2:
        med = np.array([norm[i:i + jan].mean() for i in range(n - jan)])
        des = np.array([norm[i:i + jan].std() for i in range(n - jan)])
        score = med + des * 2
        for i in np.argsort(score)[:3]:
            add("cama", int(i), int(i) + jan, "baixa energia e estável — não briga com a voz", float(1 - score[i]))

    # VIRADA / IMPACTO: maior salto de energia em ~4s (entra num card, num corte seco)
    if n > 10:
        salto = np.array([norm[i + 4:i + 8].mean() - norm[i:i + 4].mean() if i + 8 < n else -9 for i in range(n - 8)])
        for i in np.argsort(-salto)[:3]:
            if salto[i] > 0.12:
                add("virada", int(i) + 2, int(i) + 10, f"a música sobe {salto[i]:.2f} em 4s — bom pra card, corte ou revelação", float(salto[i]))

    # GANCHO: começa médio/alto já nos primeiros segundos do trecho (abertura do reel)
    if n > 12:
        for i in range(0, min(n - 8, 120)):
            if norm[i] > 0.55 and norm[i] - norm[max(0, i - 3)] > 0.08:
                add("gancho", i, i + 8, "entra forte — serve pros primeiros segundos do reel", float(norm[i]))
                break

    # PICO: trecho de maior energia sustentada (clímax, prova, oferta)
    if n > 12:
        jan2 = 8
        med2 = np.array([norm[i:i + jan2].mean() for i in range(n - jan2)])
        i = int(np.argmax(med2))
        add("pico", i, i + jan2, "maior energia sustentada — clímax, oferta, virada de argumento", float(med2[i]))

    # FINAL: últimos segundos se a energia cai (fecho natural)
    if n > 15 and norm[-5:].mean() < norm[:-5].mean() * 0.7:
        i = int(n - 12)
        add("final", i, n, "a música desce sozinha — fecho natural do reel", 0.5)

    return sorted(out, key=lambda x: x["inicio_s"])
def _loudness(mp3: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(mp3), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    t = r.stderr
    def g(p):
        m = re.findall(p + r":\s*(-?[\d.]+)", t)
        return float(m[-1]) if m else None
    return {"lufs": g("I"), "faixa_dinamica_lu": g("LRA"), "pico_true_db": g("Peak")}


def _imagens(mp3: Path, dest: Path, rms) -> dict:
    """Waveform e espectrograma: o Claude LÊ essas imagens pra ver a estrutura."""
    ensure(dest)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(mp3), "-filter_complex",
                    "showwavespic=s=1600x300:colors=#B4232C", "-frames:v", "1", str(dest / "waveform.png")],
                   capture_output=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(mp3), "-lavfi",
                    "showspectrumpic=s=1600x500:legend=1:color=intensity:scale=log",
                    "-frames:v", "1", str(dest / "espectro.png")], capture_output=True)
    # curva de energia por segundo, com marcas de 10 em 10s
    try:
        from PIL import Image, ImageDraw
        import numpy as np
        fps = SR / HOP
        seg = int(fps)
        n = len(rms) // seg
        por_s = np.array([rms[i * seg:(i + 1) * seg].mean() for i in range(n)])
        norm = por_s / (por_s.max() + 1e-12)
        W, H = max(600, n * 8), 220
        im = Image.new("RGB", (W, H), "#1d1b18"); d = ImageDraw.Draw(im)
        for i, v in enumerate(norm):
            x = int(i * W / n)
            d.rectangle([x, H - 30 - int(v * (H - 50)), x + max(2, W // n - 1), H - 30], fill="#B4232C")
        for s in range(0, n, 10):
            x = int(s * W / n)
            d.line([(x, 0), (x, H - 30)], fill="#555", width=1)
            d.text((x + 3, H - 24), f"{s}s", fill="#bbb")
        im.save(dest / "curva.png")
    except Exception:
        pass
    return {k: str(dest / f"{k}.png") for k in ("waveform", "espectro", "curva") if (dest / f"{k}.png").exists()}


def baixar(url: str, dest: Path) -> tuple[Path, dict]:
    """Baixa só o áudio + metadados do YouTube (título/canal/descrição dizem o gênero)."""
    ensure(dest)
    saida = dest / "musica.%(ext)s"
    subprocess.run(["yt-dlp", "--no-update", "--no-playlist", "-x", "--audio-format", "mp3",
                    "--audio-quality", "0", "--write-info-json", "-o", str(saida), url],
                   capture_output=True, text=True, timeout=900)
    mp3 = next((p for p in dest.glob("musica.mp3")), None)
    info = {}
    ij = dest / "musica.info.json"
    if ij.exists():
        d = json.loads(ij.read_text(encoding="utf-8"))
        info = {"titulo": d.get("title"), "canal": d.get("uploader"), "url": d.get("webpage_url"),
                "descricao": (d.get("description") or "")[:1500], "tags": (d.get("tags") or [])[:20],
                "capitulos": [{"t": c.get("start_time"), "nome": c.get("title")} for c in (d.get("chapters") or [])],
                "duracao": d.get("duration"), "licenca": d.get("license")}
        ij.unlink()
    return mp3, info


def analisar(mp3: Path, dest: Path, info: dict | None = None) -> dict:
    import numpy as np
    x = _pcm(mp3)
    rms, onset = _envelope(x)
    bpm, conf = _bpm(onset)
    dur = len(x) / SR
    secoes = _secoes(rms, dur)
    trechos = _trechos(rms, onset, dur)
    imgs = _imagens(mp3, dest, rms)
    # trecho mais "cama" (baixa energia, estável) — bom pra ficar embaixo da voz
    melhor_cama = None
    fps = SR / HOP
    seg = int(fps)
    n = len(rms) // seg
    if n > 20:
        por_s = np.array([rms[i * seg:(i + 1) * seg].mean() for i in range(n)])
        janela = 20
        medias = np.array([por_s[i:i + janela].mean() for i in range(n - janela)])
        desvios = np.array([por_s[i:i + janela].std() for i in range(n - janela)])
        score = medias + desvios * 2
        i = int(np.argmin(score))
        melhor_cama = {"inicio_s": i, "fim_s": i + janela, "motivo": "20s mais estáveis e de menor energia"}
    pico = int(np.argmax([rms[i * seg:(i + 1) * seg].mean() for i in range(n)])) if n else None
    d = {
        "duracao_s": round(dur, 1), "bpm": bpm, "bpm_confianca": conf,
        **_loudness(mp3),
        "bandas_geral": _bandas(x, 0, min(dur, 30)),
        "bandas_pico": _bandas(x, pico, pico + 10) if pico else {},
        "secoes": secoes, "trechos_usaveis": trechos, "pico_energia_s": pico, "melhor_trecho_cama": melhor_cama,
        "imagens": imgs, "youtube": info or {},
        "arquivo": str(mp3), "analisado_em": now_slug(),
    }
    gravar_json(dest / "analise.json", d)
    return d


def resumo(d: dict) -> str:
    y = d.get("youtube") or {}
    l = []
    if y.get("titulo"):
        l.append(f"{y['titulo']} — {y.get('canal','?')}")
    l.append(f"{d['duracao_s']}s · {d['bpm']} BPM (confiança {d['bpm_confianca']}) · {d.get('lufs')} LUFS · faixa dinâmica {d.get('faixa_dinamica_lu')} LU")
    b = d.get("bandas_geral") or {}
    if b:
        l.append(f"timbre: grave {b.get('grave')} · médio {b.get('medio')} · agudo {b.get('agudo')}")
    if d.get("trechos_usaveis"):
        l.append("TRECHOS USÁVEIS (corte aqui):")
    if d.get("secoes"):
        l.append("estrutura: " + " → ".join(f"{s['t0']}-{s['t1']}s {s['nivel']}" for s in d["secoes"][:8]))
    for tr in d.get("trechos_usaveis", []):
        l.append(f"  [{tr['tipo']}] {tr['inicio_s']}–{tr['fim_s']}s ({tr['duracao_s']}s) — {tr['motivo']}")
    if y.get("capitulos"):
        l.append("capítulos: " + ", ".join(f"{c['nome']} ({c['t']}s)" for c in y["capitulos"][:6]))
    return "\n".join(l)


def main():
    ap = argparse.ArgumentParser(description="Analisa uma música (link do YouTube ou arquivo)")
    ap.add_argument("alvo"); ap.add_argument("--out", default=""); ap.add_argument("--titulo", default="")
    ap.add_argument("--acervo", action="store_true"); ap.add_argument("--tags", default="")
    a = ap.parse_args()
    dest = Path(a.out).expanduser() if a.out else Path(tempfile.mkdtemp(prefix="musica-"))
    ensure(dest)
    info = {}
    if a.alvo.startswith("http"):
        mp3, info = baixar(a.alvo, dest)
        if not mp3:
            print("✗ não consegui baixar"); sys.exit(1)
    else:
        mp3 = Path(a.alvo).expanduser()
    d = analisar(mp3, dest, info)
    print(resumo(d))
    print("\nimagens:", " ".join(d["imagens"].values()))
    if a.acervo:
        import acervo
        m = acervo.adicionar_arquivo(mp3, a.titulo or (info.get("titulo") or mp3.stem), a.tags,
                                     fonte=info.get("url", ""), autor=info.get("canal", ""),
                                     observacao=resumo(d), origem_tipo="musica-analisada",
                                     extra={"analise": {k: v for k, v in d.items() if k != "imagens"}})
        print("acervo:", m["slug"])


if __name__ == "__main__":
    main()


# ───────────────────────── como a música SOA (sem IA) ─────────────────────────
# 70 arquivos chamados opF-coldcase e news-worldreport são impossíveis de escolher pelo nome, e
# mandar a IA ouvir todos custa cota. A análise que já roda (BPM, loudness, bandas, curva de energia)
# diz o suficiente pra classificar: é o que o ouvido notaria em dois segundos.

CLIMAS = ["tensa", "sombria", "épica", "corporativa", "animada", "calma"]


def caracteristicas(a: dict) -> dict:
    """Andamento, brilho, dinâmica, formato e um clima sugerido — tudo derivado da análise."""
    if not a:
        return {}
    bpm = a.get("bpm") or 0
    conf = a.get("bpm_confianca") or 0
    dur = a.get("duracao_s") or 0
    faixa = a.get("faixa_dinamica_lu") or 0
    b = a.get("bandas_geral") or {}
    grave, agudo = b.get("grave") or 0, b.get("agudo") or 0
    pico = a.get("pico_energia_s")

    # Limiares calibrados na distribuição real do acervo (quartis), não em teoria musical: o que
    # interessa é SEPARAR a biblioteca em grupos úteis, não acertar um rótulo de conservatório.
    andamento = "" if conf < 0.15 or not bpm else "lenta" if bpm < 95 else "média" if bpm <= 125 else "rápida"
    brilho = "grave" if grave >= 0.45 else "brilhante" if agudo >= 0.20 else "equilibrada"
    dinamica = "constante" if faixa < 3 else "respira" if faixa <= 9 else "muito variada"
    formato = "efeito" if dur <= 6 else "curta" if dur <= 45 else "média" if dur <= 150 else "longa"
    cresce = bool(pico and dur and pico >= dur * 0.6 and faixa >= 4)

    if formato == "efeito":
        clima = ""
    elif cresce and faixa >= 9:
        clima = "épica"                       # sobe de verdade ao longo da faixa
    elif brilho == "grave" and dinamica != "muito variada":
        clima = "tensa"
    elif brilho == "grave":
        clima = "sombria"
    elif brilho == "brilhante":
        clima = "animada"
    elif dinamica == "constante":
        clima = "calma" if andamento in ("lenta", "") else "corporativa"
    else:
        clima = "corporativa" if andamento == "média" else "calma"
    return {k: v for k, v in {"andamento": andamento, "brilho": brilho, "dinamica": dinamica,
                              "formato": formato, "clima": clima, "cresce": cresce}.items() if v not in ("", None)}


def como_soa(auto: dict) -> str:
    """Frase curta pro card, no lugar do nome que não diz nada."""
    if not auto:
        return ""
    partes = [auto.get("clima"), auto.get("andamento"), auto.get("brilho")]
    frase = ", ".join(p for p in partes if p)
    if auto.get("cresce"):
        frase += " · cresce no fim"
    return frase
