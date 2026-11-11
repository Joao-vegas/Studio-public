# Passo "Preparar a fala" do Editorial FALADO (o João aparece / a voz é a dele): o equivalente do preparar-narracao.py quando a
# entrada é o vídeo gravado dele em vez de um roteiro. Tudo vai pra <sandbox>/work/fala/ (nunca mexe em work/words.json, que é
# do bruto e do corte dele):
#   work/fala/fala.mp4    o vídeo dele já cortado, 1080x1920 a 30 fps, sem som (as cenas "fala" pegam os quadros daqui)
#   work/fala/voz.wav     a voz dele (mono 48 kHz): é a narração do vídeo
#   work/fala/words.json  tempo por palavra (Groq, grátis); nome próprio corrigido pelo roteiro se ele veio (entrada c)
#   qa/words-saida.json   a mesma fala, pro conferir_video.py
#   work/fala/momentos.json  as frases, a conferência com o roteiro (se houver) e a SUGESTÃO de gancho, virada e fecho
# Uso (da raiz do Estúdio): python3 formatos/editorial/base/exemplos/preparar-fala.py <sandbox> [--cliente Nome] [--video caminho]
# Sem --video: work/joao.mp4 (o corte automático) e, sem ele, o primeiro vídeo de bruto/.
import argparse, difflib, json, re, subprocess, sys, unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))

norm = lambda s: re.sub(r"[^\w]", "", unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode())
VIRADA = re.compile(r"^(só que|mas\b|porém|agora\b|então\b|e aí|o problema|a verdade|na verdade|por isso|e se|imagina)", re.I)


def fonte(sb: Path, dado: str) -> Path:
    if dado:
        return Path(dado) if Path(dado).is_absolute() else RAIZ / dado
    for c in [sb / "work" / "joao.mp4", *sorted((sb / "bruto").glob("*"))]:
        if c.is_file() and c.suffix.lower() in (".mp4", ".mov", ".m4v", ".mkv", ".webm"):
            return c
    raise SystemExit("não achei o vídeo dele (work/joao.mp4 ou bruto/): passe --video")


def mais_novo(saida: Path, *entradas: Path) -> bool:
    return saida.is_file() and saida.stat().st_size > 0 and all(saida.stat().st_mtime >= e.stat().st_mtime for e in entradas)


def video_cortado(src: Path, saida: Path) -> None:
    """1080x1920 a 30 fps, sem som. Vertical entra inteiro; horizontal é cortado no centro (o enquadramento fino é da edição)."""
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p"
    for codec in (["-c:v", "h264_videotoolbox", "-b:v", "10M"], ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16"]):
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-an", "-vf", vf, *codec, "-pix_fmt", "yuv420p",
                            str(saida)], capture_output=True, text=True)
        if r.returncode == 0 and saida.is_file() and saida.stat().st_size:
            return
    raise SystemExit("não consegui preparar o vídeo dele: " + r.stderr[-300:])


def _parte(f: list[dict], limite: float = 6.5) -> list[list[dict]]:
    """Frase acima de `limite` s se parte na vírgula (ou na maior pausa) mais perto do meio, até caber."""
    if f[-1]["end"] - f[0]["start"] <= limite or len(f) < 8:
        return [f]
    meio = (f[0]["start"] + f[-1]["end"]) / 2
    cand = [k for k in range(3, len(f) - 3) if f[k]["word"].strip().endswith((",", ";", ":"))] or \
           [max(range(3, len(f) - 3), key=lambda k: f[k + 1]["start"] - f[k]["end"])]
    k = min(cand, key=lambda k: abs(f[k]["end"] - meio))
    return _parte(f[:k + 1], limite) + _parte(f[k + 1:], limite)


def frases_de(ws: list[dict], segmentos: list[dict] | None = None) -> list[dict]:
    """Frases da fala: fim de frase (. ? !) ou fim de segmento do Groq (a fala cortada quase não tem pausa, então só a pontuação não basta)."""
    fins = sorted(float(s["end"]) for s in segmentos or [])
    out, cur = [], []
    for w in ws:
        cur.append(w)
        if re.search(r"[.?!…]$", w["word"].strip()) or any(abs(w["end"] - e) < .12 for e in fins):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    # frase de 1-2 palavras ("Pronto.", "Olha.") gruda na seguinte
    fim = []
    for f in out:
        if fim and len(fim[-1]) < 3:
            fim[-1] = fim[-1] + f
        else:
            fim.append(f)
    fim = [p for f in fim for p in _parte(f)]
    return [{"i": i, "de": round(f[0]["start"], 2), "ate": round(f[-1]["end"], 2),
             "texto": " ".join(w["word"].strip() for w in f)} for i, f in enumerate(fim)]


def trecho(fr: list[dict], i0: int, minimo: float, maximo: float, sentido: int = 1) -> dict:
    """Junta frases a partir da i0 (pra frente ou pra trás) até passar de `minimo` s, sem passar de `maximo`."""
    ini = fim = i0
    while True:
        a, b = fr[ini], fr[fim]
        if b["ate"] - a["de"] >= minimo:
            break
        nxt = fim + 1 if sentido > 0 else ini - 1
        if not 0 <= nxt < len(fr):
            break
        cand = (fr[ini]["de"], fr[nxt]["ate"]) if sentido > 0 else (fr[nxt]["de"], fr[fim]["ate"])
        if cand[1] - cand[0] > maximo:
            break
        ini, fim = (ini, nxt) if sentido > 0 else (nxt, fim)
    return {"de": fr[ini]["de"], "ate": fr[fim]["ate"], "texto": " ".join(f["texto"] for f in fr[ini:fim + 1]), "frases": [ini, fim]}


def sugerir(fr: list[dict], dur: float) -> dict:
    if not fr:
        return {}
    gancho = trecho(fr, 0, 3.0, 6.5)
    fecho = trecho(fr, len(fr) - 1, 3.0, 7.0, -1)
    meio = [f for f in fr if .3 * dur <= f["de"] <= .85 * dur and f["de"] > gancho["ate"] and f["ate"] < fecho["de"]]
    v = next((f for f in meio if VIRADA.match(f["texto"].strip())), None) or min(meio or fr[len(fr) // 2:len(fr) // 2 + 1], key=lambda f: abs(f["de"] - .6 * dur))
    virada = trecho(fr, v["i"], 2.5, 6.0)
    if virada["ate"] > fecho["de"] or virada["de"] < gancho["ate"]:
        virada = None
    return {"gancho": gancho, **({"virada": virada} if virada else {}), "fecho": fecho}


def conferir_roteiro(ws: list[dict], roteiro: str) -> dict:
    """(c) roteiro + vídeo: o roteiro é o gabarito. Corrige a grafia de nome próprio no words.json e lista o que faltou/sobrou."""
    alvo = [t for t in roteiro.split() if norm(t)]
    a, b = [norm(w["word"]) for w in ws], [norm(t) for t in alvo]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    corrigidas, faltou, sobrou = [], [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                w, t = ws[i1 + k], alvo[j1 + k]
                if difflib.SequenceMatcher(None, a[i1 + k], b[j1 + k]).ratio() >= .6:
                    pont = re.search(r"[.,!?…:;]+$", w["word"].strip())
                    novo = re.sub(r"[.,!?…:;]+$", "", t) + (pont.group(0) if pont else "")
                    corrigidas.append([w["word"], novo]); w["word"] = novo
                else:
                    sobrou.append(w["word"]); faltou.append(t)
        elif op == "delete":
            sobrou += [ws[k]["word"] for k in range(i1, i2)]
        elif op == "insert":
            faltou += alvo[j1:j2]
        elif op == "replace":
            sobrou += [ws[k]["word"] for k in range(i1, i2)]; faltou += alvo[j1:j2]
    return {"parecido": round(sm.ratio(), 3), "corrigidas": corrigidas[:40], "faltou_no_video": faltou[:60], "sobrou_no_video": sobrou[:60]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sandbox", type=Path)
    ap.add_argument("--cliente", default="")
    ap.add_argument("--video", default="")
    a = ap.parse_args()
    sb = a.sandbox if a.sandbox.is_absolute() else RAIZ / a.sandbox
    src = fonte(sb, a.video)
    d = sb / "work" / "fala"; d.mkdir(parents=True, exist_ok=True)
    fala, voz = d / "fala.mp4", d / "voz.wav"
    if not mais_novo(fala, src):
        print(f"vídeo dele -> {fala.relative_to(sb)} (1080x1920, 30 fps)")
        video_cortado(src, fala)
    if not mais_novo(voz, src):
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(voz)], check=True)
    import corte
    cli = a.cliente or "Joao"
    if not (d / "words.json").is_file():
        print("tempo por palavra (Groq)...")
        corte.transcrever(voz, d, cli, motor="groq")
    js = json.loads((d / "words.json").read_text(encoding="utf-8"))
    ws = [w for w in js.get("words", []) if isinstance(w, dict) and w.get("word", "").strip()]
    if len(ws) < 5:
        raise SystemExit("a transcrição veio vazia ou curta: confira o áudio dele")
    conf = None
    rot = sb / "work" / "roteiro.txt"
    if rot.is_file() and rot.read_text(encoding="utf-8").strip():
        conf = conferir_roteiro(ws, rot.read_text(encoding="utf-8"))
        js["words"] = ws
        (d / "words.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    (sb / "qa").mkdir(exist_ok=True)   # a fala do vídeo ENTREGUE (conferir_video.py lê daqui): o vídeo do Editorial falado anda no mesmo tempo da fala dele
    (sb / "qa" / "words-saida.json").write_text(json.dumps({"words": ws}, ensure_ascii=False), encoding="utf-8")
    dur = round(ws[-1]["end"], 2)
    fr = frases_de(ws, js.get("segments"))
    (d / "momentos.json").write_text(json.dumps({"duracao": dur, "frases": fr, "sugestao": sugerir(fr, dur), "conferencia_roteiro": conf},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(ws)} palavras · {dur} s · {len(fr)} frases")
    for k, v in sugerir(fr, dur).items():
        print(f"  {k:7} {v['de']:6.2f}-{v['ate']:6.2f}  {v['texto'][:90]}")
    if conf:
        print(f"  roteiro: {conf['parecido']:.0%} parecido · {len(conf['corrigidas'])} grafias corrigidas · faltou {len(conf['faltou_no_video'])} · sobrou {len(conf['sobrou_no_video'])}")


if __name__ == "__main__":
    main()
