# Passo "Preparar a narração" do Editorial, de uma vez e do mesmo jeito em todo vídeo:
#   roteiro.txt -> número por extenso -> voz fixa em blocos de ~5 frases (cada bloco conferido pelo Groq SEM dica: começo,
#   fim e tamanho têm que bater; senão refaz, até 5 vezes) -> colar com respiro -> apertar pausas -> work/voz.wav + work/words.json
# Uso (da raiz do Estúdio): python3 formatos/editorial/base/exemplos/preparar-narracao.py <sandbox> --voz <perfil> --cliente <Nome>
# Sem --voz: a voz do cliente ou a de Configurações (nunca a "default": ela sorteia uma pessoa por bloco).
# Saída: <sandbox>/work/voz.wav, words.json, narracao.json (o que foi falado, tentativas por bloco, duração, problemas).
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))

UN = "zero um dois três quatro cinco seis sete oito nove dez onze doze treze quatorze quinze dezesseis dezessete dezoito dezenove".split()
DZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
CT = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _ate999(n: int) -> str:
    if n == 100: return "cem"
    c, r = divmod(n, 100)
    partes = [CT[c]] if c else []
    if r:
        partes.append(UN[r] if r < 20 else DZ[r // 10] + (f" e {UN[r % 10]}" if r % 10 else ""))
    return " e ".join(partes)


def extenso(n: int) -> str:
    if n < 1000: return _ate999(n) if n else "zero"
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        topo = "mil" if m == 1 else f"{_ate999(m)} mil"
        return topo + (f" e {_ate999(r)}" if r and (r < 100 or r % 100 == 0) else (f" {_ate999(r)}" if r else ""))
    m, r = divmod(n, 1_000_000)
    topo = "um milhão" if m == 1 else f"{extenso(m)} milhões"
    return topo + (f" e {extenso(r)}" if r and r < 1000 else (f" {extenso(r)}" if r else ""))


def por_extenso(txt: str) -> str:
    """"9 bilhões" -> "nove bilhões", "em 2003" -> "em dois mil e três", "30%" -> "trinta por cento". Decimal e moeda ficam pra quem escreveu o roteiro."""
    txt = re.sub(r"(\d+)\s*%", lambda m: extenso(int(m.group(1))) + " por cento", txt)
    txt = re.sub(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+|\d+)(?!\d|,\d)", lambda m: extenso(int(m.group(1).replace(".", ""))), txt)
    return txt


norm = lambda s: re.sub(r"[^\wçãõáéíóúâêôà ]", "", s.lower()).split()


def blocos_de(frases: list[str], por_bloco: int = 5, maximo: int = 520) -> list[list[str]]:
    out, atual = [], []
    for f in frases:
        if atual and (len(atual) >= por_bloco or len(" ".join(atual + [f])) > maximo):
            out.append(atual); atual = []
        atual.append(f)
    if atual:
        out.append(atual)
    if len(out) > 1 and len(out[-1]) == 1:   # frase de fecho sozinha vai com a anterior (a entonação do fecho nasce do contexto)
        ult = out.pop(); out[-1] += ult
    return out


def confere(esperado: list[str], got: list[str]) -> tuple[bool, str]:
    if len(got) < 3: return False, "transcrição vazia"
    if got[:3] != esperado[:3]: return False, "começo diferente: " + " ".join(got[:4])
    if got[-3:] != esperado[-3:]: return False, "fim diferente: " + " ".join(got[-4:])
    if abs(len(got) - len(esperado)) > 2: return False, f"{len(got)} palavras em vez de {len(esperado)}"
    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sandbox", type=Path)
    ap.add_argument("--voz", default="")
    ap.add_argument("--cliente", default="")
    ap.add_argument("--tentativas", type=int, default=5)
    a = ap.parse_args()
    sb = a.sandbox if a.sandbox.is_absolute() else RAIZ / a.sandbox
    work = sb / "work"; (work / "blocos").mkdir(parents=True, exist_ok=True)
    import voz as V, corte, fala
    originais = [l.strip() for l in (sb / "roteiro.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    frases = [por_extenso(l) for l in originais]   # o que a voz lê; o Groq escreve número em algarismo, então a conferência compara com o ORIGINAL
    (work / "roteiro-falado.txt").write_text("\n".join(frases) + "\n", encoding="utf-8")
    chave = corte.chave_groq(a.cliente or "Joao")
    voz_id = a.voz or (V.voz_do_cliente(a.cliente).get("id") if a.cliente else "") or V.status()["voicestudio"]["voz"]
    if not voz_id or voz_id == "default":
        raise SystemExit("Sem perfil de voz fixo: escolha uma voz no Criar (a 'default' troca de pessoa por bloco).")
    log = {"voz": voz_id, "blocos": [], "problemas": []}
    pecas = []
    ini = 0
    for i, fr in enumerate(blocos_de(frases)):
        txt = " ".join(fr); esp = norm(" ".join(originais[ini:ini + len(fr)])); ini += len(fr); alvo = work / "blocos" / f"bloco-{i:02d}.mp3"
        melhor, info = None, {"bloco": i, "frases": len(fr), "tentativas": []}
        for t in range(1, a.tentativas + 1):
            try:
                V.falar(txt, alvo, voz_id, a.cliente or None)
            except ValueError as e:   # VoiceStudio fora do ar e afins: para com a mensagem em português, sem inventar outra voz
                raise SystemExit(f"Não consegui gerar a voz: {e}")
            ws = fala.groq_transcrever(alvo.with_suffix(".mp3"), chave, dica="")["words"]
            got = norm(" ".join(w["word"] for w in ws))
            ok, motivo = confere(esp, got)
            if not ok and len(got) > 3 and got[1:4] == esp[:3] and ws[0]["end"] <= .45:
                # o modelo solta um "é"/"e" curto antes da 1ª palavra (visto 29/10 com o 3ed4b3ea): apara até onde ele acaba e confere de novo
                ap_ = alvo.with_name(alvo.stem + "-ap.mp3")
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ws[0]['end'] - .03:.3f}", "-i", str(alvo), "-c:a", "libmp3lame", "-q:a", "2", str(ap_)], check=True)
                ap_.replace(alvo)
                ws = fala.groq_transcrever(alvo, chave, dica="")["words"]
                got = norm(" ".join(w["word"] for w in ws)); ok, motivo = confere(esp, got)
                print(f"bloco {i}: aparei a palavra extra do começo", flush=True)
            info["tentativas"].append("ok" if ok else motivo)
            print(f"bloco {i} tentativa {t}: {'ok' if ok else motivo}", flush=True)
            if ok: melhor = alvo; break
            keep = work / "blocos" / f"bloco-{i:02d}-t{t}.mp3"; alvo.replace(keep); melhor = melhor or keep
        if not info["tentativas"][-1] == "ok":
            log["problemas"].append(f"bloco {i} não bateu com o roteiro em {a.tentativas} tentativas ({info['tentativas'][-1]}); usei a última")
            melhor = work / "blocos" / f"bloco-{i:02d}-t{a.tentativas}.mp3"
        pecas.append(melhor); log["blocos"].append(info)
    # cola com 0,3 s de respiro e aperta as pausas longas (apertar.py: >0,33 s vira ~0,22 s)
    with tempfile.TemporaryDirectory() as tmp:
        lista = Path(tmp) / "l.txt"; sil = Path(tmp) / "sil.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "0.3", str(sil)], check=True)
        ws = []
        for i, p in enumerate(pecas):
            w = Path(tmp) / f"p{i}.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(p), "-ac", "1", "-ar", "48000", str(w)], check=True)
            ws += [w] + ([sil] if i < len(pecas) - 1 else [])
        lista.write_text("".join(f"file '{w}'\n" for w in ws))
        bruta = work / "voz-bruta.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista), str(bruta)], check=True)
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("apertar.py")), str(bruta), str(work / "voz.wav")], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()[-300:], flush=True)
    # tempo por palavra (Groq; se parar no meio o corte.transcrever refaz sem a lista de nomes)
    for f in ("words.json", "segmentos.json", "segmentos-whisper.json", "medidas.json"):
        (work / f).unlink(missing_ok=True)
    # nome próprio do caso (Theranos, Holmes, Hastings) vai de dica pro Groq: sem ela ele escrevia "Isabel" e "Teranos" (30-out, Theranos)
    nomes = sorted({w.strip(".,;:!?\"'()") for l in originais for w in l.split() if w[:1].isupper() and len(w.strip(".,;:!?\"'()")) >= 3})
    dica = ("Nomes citados: " + ", ".join(nomes) + ".") if nomes else ""
    import vocabulario
    from _comum import gravar_json
    js = fala.groq_transcrever(work / "voz.wav", chave, dica)
    if dica and corte._parou_no_meio(work / "voz.wav", js):   # com a lista o Groq às vezes para no meio: refaz sem ela
        js = fala.groq_transcrever(work / "voz.wav", chave, "")
    vocabulario.corrigir_lista(js.get("words") or [], vocabulario.palavras(a.cliente or "Joao"))
    js["motor"] = "groq-whisper"; js["fonte"] = corte._fonte(work / "voz.wav")
    gravar_json(work / "words.json", js)
    corte.transcrever(work / "voz.wav", work, a.cliente or "Joao", motor="groq")   # só monta segmentos.json a partir do words.json gravado
    words = json.loads((work / "words.json").read_text())["words"]
    esp = norm(" ".join(originais)); got = norm(" ".join(w["word"] for w in words))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(work / "voz.wav")], capture_output=True, text=True).stdout.strip())
    if got[-3:] != esp[-3:]: log["problemas"].append("a transcrição não termina como o roteiro (" + " ".join(got[-4:]) + "): confira a última frase")
    if dur - words[-1]["end"] > 2: log["problemas"].append("a transcrição acaba antes do áudio: transcreva o resto à parte e junte")
    log.update(duracao_s=round(dur, 2), palavras=len(words), frases=len(frases))
    (work / "narracao.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(f"voz.wav {dur:.1f} s · {len(words)} palavras · problemas: {log['problemas'] or 'nenhum'}")
    sys.exit(1 if log["problemas"] else 0)


if __name__ == "__main__":
    main()
