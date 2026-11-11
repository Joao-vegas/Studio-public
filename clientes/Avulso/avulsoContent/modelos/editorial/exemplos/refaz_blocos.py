# refaz o bloco que engoliu palavra: troca a semente até a transcrição (Groq, sem dica) ter o começo e o fim certos
import re, sys, urllib.request, uuid
from pathlib import Path
AQUI = Path(__file__).parent
sys.path.insert(0, str(Path.home() / "Projetos/Skill/Estúdio/app/ferramentas"))
import fala, chaves
from _comum import RAIZ
K = chaves.chave("GROQ_API_KEY", "Joao", RAIZ)
norm = lambda s: re.sub(r"[^\wçãõáéíóúâêô ]", "", s.lower()).split()

def gerar(txt, seed, alvo):
    b = uuid.uuid4().hex; campos = {"text": txt, "language": "pt", "profile_id": "8800a992", "class_temperature": "0.6", "effect_preset": "raw", "seed": str(seed)}
    corpo = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in campos.items()) + f"--{b}--\r\n".encode()
    alvo.write_bytes(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:3900/generate", corpo, {"Content-Type": f"multipart/form-data; boundary={b}"}), timeout=900).read())

frases = [l.strip() for l in (AQUI / "roteiro.txt").read_text().splitlines() if l.strip()]
BLOCOS = [frases[0:5], frases[5:11], frases[11:18], frases[18:25], frases[25:31], frases[31:]]
for b in map(int, sys.argv[1:]):
    txt = " ".join(BLOCOS[b]); esp = norm(txt)
    for seed in (11, 23, 31, 47, 5):
        a = AQUI / f"work/tenta-{b:02d}-{seed}.wav"
        if not a.exists(): gerar(txt, seed, a)
        got = norm(" ".join(w["word"] for w in fala.groq_transcrever(a, K, dica="")["words"]))
        ok = (got[:3] == esp[:3] or (b == 0 and got[:3] == esp[1:4])) and got[-3:] == esp[-3:] and abs(len(got) - len(esp)) <= 2
        print(b, seed, "ok" if ok else "não", "|", " ".join(got[:5]), "...", " ".join(got[-4:]), flush=True)
        if ok:
            a.replace(AQUI / f"work/bloco-{b:02d}.wav"); break
