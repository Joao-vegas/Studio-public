# Troca no cenas.json as fotos de tela cheia pequenas demais (< 800 px: viram borrão; o render.py reprova) por uma maior do MESMO assunto:
# 1º outra foto da mesma chave já baixada (fotos/<chave>-N.jpg), 2º nova busca no Commons com a consulta da chave (work/consultas.json
# ou fotos/origem.json). Uso (da raiz do Estúdio): python3 formatos/editorial/base/exemplos/trocar_pequenas.py <sandbox>
# Depois rode o --storyboard de novo e OLHE a foto nova (tem que casar com a fala). Nada é apagado: a foto pequena fica na pasta.
import json, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

sb = Path(sys.argv[1]); cenas_p = sb / "cenas.json"
doc = json.loads(cenas_p.read_text(encoding="utf-8"))
lado = lambda p: max(Image.open(p).size) if p.is_file() else 0
TELA = ("foto", "titulo", "texto", "recorte")
consultas = {}
for f in (sb / "consultas.json", sb / "work" / "consultas.json"):
    if f.is_file(): consultas.update(json.loads(f.read_text()))
from collections import Counter
usos = Counter(x for c in doc["cenas"] for x in [c.get("imagem")] if isinstance(x, str))   # a mesma foto no máximo 2 vezes (checar_repeticao)
cache, novos, trocas = {}, 0, []
for c in doc["cenas"]:
    x = c.get("imagem")
    if c.get("tipo") not in TELA or not isinstance(x, str) or not (sb / x).is_file() or lado(sb / x) >= 800:
        continue
    if x not in cache:
        pasta = (sb / x).parent; chave = re.sub(r"-\d+$", "", (sb / x).stem)
        cands = sorted([p for p in pasta.glob(f"{chave}-*.jpg") if lado(p) >= 1100], key=lambda p: -lado(p))
        if len([p for p in cands if usos[str(p.relative_to(sb))] < 2]) < 2 and chave in consultas:
            with tempfile.TemporaryDirectory() as tmp:
                q = Path(tmp) / "q.json"; q.write_text(json.dumps({chave: consultas[chave]}))
                subprocess.run([sys.executable, str(Path(__file__).with_name("commons.py")), tmp + "/o", str(q)], capture_output=True, text=True)
                o1 = Path(tmp) / "o" / "origem.json"
                org = json.loads(o1.read_text()) if o1.is_file() else {}
                for i, r in enumerate(org.get(chave, [])):
                    novo = pasta / f"{chave}-g{i}.jpg"
                    if not novo.is_file(): shutil.copy(Path(tmp) / "o" / r["arquivo"], novo)
                    r["arquivo"] = novo.name
                    if lado(novo) >= 1100 and novo not in cands: cands.append(novo)
                    o2 = pasta / "origem.json"; d = json.loads(o2.read_text()) if o2.is_file() else {}
                    d.setdefault(chave, []).append(r); o2.write_text(json.dumps(d, ensure_ascii=False, indent=1)); novos += 1
        cache[x] = cands
    livre = [p for p in cache[x] if usos[str(p.relative_to(sb))] < 2]
    if not livre:
        print(f"sem foto maior e livre pra {x}: peça outra consulta pro commons.py"); continue
    novo = str(livre[0].relative_to(sb)); usos[novo] += 1; usos[x] -= 1
    c["imagem"] = novo; trocas.append((x, novo))
if trocas:
    cenas_p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(trocas)} cena(s) com foto trocada, {novos} foto(s) nova(s) baixada(s):", trocas)
