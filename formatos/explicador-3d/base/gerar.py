#!/usr/bin/env python3
"""Explicador 3D · gerador genérico: DECUPAGEM (narrativa visual) → cenas.json. Serve pra qualquer roteiro.

  python3 gerar.py <sandbox>          (lê <sandbox>/decupagem.json; escreve cenas.json e DECUPAGEM.md)

A decupagem é o que a IA escreve na etapa "Narrativa visual" depois de ler o roteiro: elenco (da biblioteca elenco.js ou
completo), mundos (cenário + objetos dos números) e planos. Cada plano junta 1 ou mais orações do roteiro (Loaded Dice: plano
de ~2,2 s, a imagem nova dentro do plano vem por câmera, objeto ou ação). Campos de um plano:
  oracoes: ["começo da oração 1", "começo da oração 2"]   (texto do roteiro; o plano começa na 1ª palavra da 1ª)
  mundo, lugar {id: {pos [x,z] | "@marca", y, rot, pose, rosto, olha, senta, props}}, acoes [{quem, em "@palavra", pose, rosto,
  olha, pop}], obj {id: {...}}, cam {alvo [x,y,z] | "rosto:<id>", dist, az, alt, fov, push, lado, sobe, saida} ou cam pronta
  {de, para, olha, fov}; passos [{em "@palavra", alvo/dist/az/...}] (a câmera vai pro enquadramento da oração seguinte);
  trans: corte (padrão) | dissolve | moedas_caem | notas_sobem | wipe | chicote | flash; brilho "@palavra"; efeitos
  [{em, arquivo, rel}]; legenda_mostra: o que aparece (vai pra tabela DECUPAGEM.md).
"@palavra" = 1ª ocorrência da palavra dentro do plano; "@palavra#2" a 2ª; "@palavra+0.1" com deslocamento (s)."""
import difflib
import json
import math
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

S = Path(sys.argv[1]).resolve()
B = Path(__file__).resolve().parent
D = json.loads((S / "decupagem.json").read_text(encoding="utf-8"))
MARCAS = json.loads((B / "marcas.json").read_text(encoding="utf-8"))
FPS = 30

_n = lambda s: re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode())
NUMS = {"tres": "3", "dois": "2", "um": "1"}
norm = lambda s: NUMS.get(_n(s), _n(s))

# ── palavras do roteiro com o tempo da transcrição (difflib + interpolação + início encostado no fim do silêncio)
roteiro = (S / D.get("roteiro", "roteiro.txt")).read_text(encoding="utf-8").replace("\n", " ")
toks = [t for t in roteiro.split() if t.strip()]
js = json.loads((S / D.get("palavras", "work/tr2/words.json")).read_text())
ws = js if isinstance(js, list) else js.get("words", js)
tr = [{"w": w.get("word", w.get("w")), "s": float(w.get("start", w.get("s"))), "e": float(w.get("end", w.get("e")))} for w in ws]
A = [norm(t) for t in toks]
Bt = [norm(t["w"]) for t in tr]
tempo = [None] * len(toks)
for a, b, n in difflib.SequenceMatcher(a=A, b=Bt, autojunk=False).get_matching_blocks():
    for k in range(n):
        tempo[a + k] = [tr[b + k]["s"], tr[b + k]["e"]]
for i in range(len(toks)):
    if tempo[i] is None:
        j0 = max([j for j in range(i) if tempo[j]], default=None)
        j1 = next((j for j in range(i + 1, len(toks)) if tempo[j]), None)
        s0 = tempo[j0][1] if j0 is not None else 0.0
        s1 = tempo[j1][0] if j1 is not None else s0 + .4
        tempo[i] = [s0 + (s1 - s0) * .1, s0 + (s1 - s0) * .9]
VOZ = S / D.get("voz", "work/voz.wav")
log = subprocess.run(["ffmpeg", "-i", str(VOZ), "-af", "silencedetect=noise=-40dB:d=0.08", "-f", "null", "-"], capture_output=True, text=True).stderr
ONS = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
for i in range(1, len(toks)):
    perto = [o for o in ONS if tempo[i][0] - .05 <= o <= tempo[i][0] + .9 and o < tempo[i][1] - .05 and o > tempo[i - 1][0] + .1]
    if perto and tempo[i][0] < tempo[i - 1][1] + .05:
        tempo[i][0] = round(perto[0], 3)
    if tempo[i][0] < tempo[i - 1][0] + .06:
        tempo[i][0] = tempo[i - 1][0] + .06
PAL = [{"w": t, "s": round(a, 3), "e": round(b, 3)} for t, (a, b) in zip(toks, tempo)]
TOTAL = round(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(VOZ)],
                                   capture_output=True, text=True).stdout) + .45, 2)


def idx(frase, depois=0):
    f = [norm(x) for x in frase.split()]
    for i in range(depois, len(A) - len(f) + 1):
        if A[i:i + len(f)] == f:
            return i
    raise SystemExit(f"não achei no roteiro: {frase}")


# ── posições e câmera
def marca(mundo_tipo, v):
    if isinstance(v, str) and v.startswith("@"):
        m = MARCAS.get(mundo_tipo, {}).get(v[1:])
        if not m:
            raise SystemExit(f"marca {v} não existe em {mundo_tipo}: {list(MARCAS.get(mundo_tipo, {}))}")
        return m
    return None


def lugar_ok(mundo_tipo, lugar):
    out = {}
    for q, e in (lugar or {}).items():
        e = dict(e)
        m = marca(mundo_tipo, e.get("pos"))
        if m:
            e["pos"] = m[:2]
            e.setdefault("y", m[2])
            e.setdefault("rot", m[3])
        out[q] = e
    return out


def C(c, lug):
    if "de" in c:
        return c
    alvo = c["alvo"]
    if isinstance(alvo, str) and alvo.startswith("rosto:"):
        e = lug[alvo[6:]]
        alvo = [e["pos"][0], (e.get("y") or 0) + (1.0 if e.get("senta") else 1.55), e["pos"][1]]
    x, y, z = alvo
    a = math.radians(c.get("az", 0))
    dist, push, lado, sobe = c.get("dist", 3), c.get("push", .1), c.get("lado", 0), c.get("sobe", 0)
    de = [x + math.sin(a) * dist, y + c.get("alt", .2), z + math.cos(a) * dist]
    px, pz = math.cos(a), -math.sin(a)
    para = [de[0] + (x - de[0]) * push + px * lado, de[1] + (y - de[1]) * push + sobe, de[2] + (z - de[2]) * push + pz * lado]
    out = {"de": [round(v, 3) for v in de], "para": [round(v, 3) for v in para], "olha": [round(v, 3) for v in alvo], "fov": c.get("fov", 44)}
    for k in ("saida", "impulso", "rolo"):
        if k in c:
            out[k] = c[k]
    return out


# ── planos → cenas
MUN = D["mundos"]
CENAS, INI = [], []
p = 0
for pl in D["planos"]:
    i = idx(pl["oracoes"][0], p)
    INI.append(i)
    p = i + 1
for k, pl in enumerate(D["planos"]):
    i0, i1 = INI[k], (INI[k + 1] if k + 1 < len(INI) else len(PAL))
    tipo = MUN[pl["mundo"]].get("tipo", pl["mundo"])
    lug = lugar_ok(tipo, pl.get("lugar"))
    c = {"mundo": pl["mundo"], "de": 0.0 if k == 0 else PAL[i0]["s"], "fala": " ".join(w["w"] for w in PAL[i0:i1]),
         "palavras": [dict(w) for w in PAL[i0:i1]], "lugar": lug, "cam": C(pl["cam"], lug)}
    for key in ("acoes", "obj", "legenda", "brilho", "trans", "trans_q"):
        if key in pl:
            c[key] = pl[key]
    if pl.get("passos"):
        c["cam"]["passos"] = [{**C({kk: vv for kk, vv in ps.items() if kk not in ("em", "dura")}, lug), "em": ps["em"], "dura": ps.get("dura", .9)}   # 0,9 s: a câmera trabalha dentro do plano (mais rápido vira "chicote")
                              for ps in pl["passos"]]
    c["_oracoes"] = pl["oracoes"]
    c["_mostra"] = pl.get("mostra", "")
    CENAS.append(c)

# troca de plano pronta na palavra: corte 1 quadro antes; dissolve termina na palavra; especial com o meio 3 quadros antes
for k in range(1, len(CENAS)):
    c, a = CENAS[k], CENAS[k - 1]
    w0 = c["palavras"][0]["s"]
    tr_ = c.get("trans", "corte")
    c["trans"] = tr_
    novo = w0 - (6 / FPS if tr_ == "dissolve" else 3 / FPS if tr_ in ("moedas_caem", "notas_sobem", "wipe", "chicote", "flash") else 1 / FPS)
    c["de"] = round(max(a["de"] + .4, novo), 3)


def resolve(v, k):
    if not (isinstance(v, str) and v.startswith("@")):
        return v
    m = re.match(r"@([^+#]+?)(?:#(\d+))?([+-][\d.]+)?$", v)
    w, occ, off = m.group(1), int(m.group(2) or 1), float(m.group(3) or 0)
    c = CENAS[k]
    n = 0
    for x in c["palavras"]:
        if norm(x["w"]) == norm(w):
            n += 1
            if n == occ:
                return round(x["s"] - c["de"] + off, 3)
    raise SystemExit(f"plano {k + 1}: não achei a palavra {w} em: {c['fala']}")


def andar(o, k):
    if isinstance(o, dict):
        return {a: andar(b, k) for a, b in o.items()}
    if isinstance(o, list):
        return [andar(b, k) for b in o]
    return resolve(o, k)


for k, c in enumerate(CENAS):
    for key in ("acoes", "obj"):
        if key in c:
            c[key] = andar(c[key], k)
    if c["cam"].get("passos"):
        for ps in c["cam"]["passos"]:
            ps["em"] = resolve(ps["em"], k)
    if isinstance(c.get("brilho"), str):
        em = resolve(c["brilho"], k)
        c["brilho"] = {"cor": "#ffc83a", "de": em - .03, "ate": em + .5, "forca": .55}


# ── som: efeitos medidos contra a voz; música no nível pedido (rel_db abaixo da voz, integrado)
def lufs(arq):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(arq), "-af", "ebur128=peak=none", "-f", "null", "-"], capture_output=True, text=True).stderr
    ms = [float(x) for x in re.findall(r"M:\s*(-?[\d.]+)", r)]
    I_ = re.findall(r"I:\s*(-?[\d.]+) LUFS", r)
    return max(ms) if ms else -30.0, float(I_[-1]) if I_ else -30.0


VOZ_I = lufs(VOZ)[1]


def ganho(arq, rel, por="pico"):
    pico, integ = lufs(B / arq)
    return round(10 ** ((VOZ_I + rel - (pico if por == "pico" else integ)) / 20), 3)


EF = []
SOM_TRANS = {"moedas_caem": ("audio/sfx/extra/moedas.mp3", -10), "notas_sobem": ("audio/sfx/extra/mixkit-1490.mp3", -14),
             "wipe": ("audio/sfx/whoosh-short.mp3", -14), "chicote": ("audio/sfx/extra/mixkit-1491.mp3", -14)}
for k, c in enumerate(CENAS):
    pl = D["planos"][k]
    for e in pl.get("efeitos", []):
        arq = e["arquivo"] if e["arquivo"].startswith("audio/") else f"audio/sfx/{e['arquivo']}"
        EF.append({"t": round(c["de"] + resolve(e["em"], k) + e.get("adianta", 0), 3), "arquivo": arq, "volume": ganho(arq, e.get("rel", -10)),
                   **({"dura": e["dura"]} if "dura" in e else {})})
    if c.get("trans") in SOM_TRANS:
        arq, rel = SOM_TRANS[c["trans"]]
        EF.append({"t": round(c["de"] - .2, 3), "arquivo": arq, "volume": ganho(arq, rel)})
mus = D.get("musica", {})
MUS = mus.get("arquivo", "audio/musicas/876.mp3")
doc = {"titulo": D.get("titulo", "Explicador 3D"), "saida": D.get("saida", "video.mp4"), "largura": 1080, "altura": 1920, "fps": FPS,
       "duracao": TOTAL, "voz": D.get("voz", "work/voz.wav"), "estilo": D.get("estilo", {}),
       "musica": {"arquivo": MUS, "volume": mus.get("volume") or ganho(MUS, mus.get("rel_db", -10), por="integ"), "inicio_s": 0},
       "efeitos": sorted(EF, key=lambda e: e["t"]), "elenco": D["elenco"], "mundos": MUN,
       "cenas": [{k: v for k, v in c.items() if not k.startswith("_")} for c in CENAS]}
ORS = []   # as orações com tempo (a conferência fala × imagem sai oração por oração, não plano por plano)
for k, c in enumerate(CENAS):
    for j, o in enumerate(c["_oracoes"]):
        i = idx(o, INI[k]); fim = INI[k + 1] if k + 1 < len(INI) else len(PAL)
        nxt = idx(c["_oracoes"][j + 1], i + 1) if j + 1 < len(c["_oracoes"]) else fim
        ORS.append({"texto": " ".join(w["w"] for w in PAL[i:nxt]), "s": PAL[i]["s"], "e": PAL[nxt - 1]["e"], "plano": k + 1})
doc["oracoes"] = ORS
(S / "cenas.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

# ── a decupagem em tabela (vai pro João e pro relatório): oração · tempo · plano/cenário · quem · ação · rosto · objeto · transição
L = ["# Decupagem: " + doc["titulo"], "", "| Plano | Oração | Tempo | Cenário | Quem | Ação | Rosto | Objeto/número | Transição | O que aparece |",
     "|---|---|---|---|---|---|---|---|---|---|"]
for k, c in enumerate(CENAS):
    ors = c["_oracoes"]
    for j, o in enumerate(ors):
        i = idx(o, INI[k])
        fim = INI[k + 1] if k + 1 < len(INI) else len(PAL)
        nxt = idx(ors[j + 1], i + 1) if j + 1 < len(ors) else fim
        txt = " ".join(w["w"] for w in PAL[i:nxt])
        quem = ", ".join(sorted(c.get("lugar", {})))
        acs = c.get("acoes", [])
        acao = "; ".join(f"{a['quem']}: {a.get('pose', '')}".strip(": ") for a in acs if a.get("pose")) or "-"
        rosto = "; ".join(f"{a['quem']}: {a['rosto']}" for a in acs if a.get("rosto")) or "-"
        objs = ", ".join(k2 for k2, v in (c.get("obj") or {}).items() if not (isinstance(v, dict) and (v.get("em") in (-9, 99) or v.get("fora")))) or "-"
        L.append(f"| {k + 1 if j == 0 else ''} | {txt} | {PAL[i]['s']:.2f} s | {c['mundo'] if j == 0 else ''} | {quem if j == 0 else ''} | {acao if j == 0 else ''} | "
                 f"{rosto if j == 0 else ''} | {objs if j == 0 else ''} | {(c.get('trans') or 'início') if j == 0 else 'dentro do plano (câmera)'} | {c['_mostra'] if j == 0 else ''} |")
(S / "DECUPAGEM.md").write_text("\n".join(L) + "\n", encoding="utf-8")
dur = [(CENAS[k + 1]["de"] if k + 1 < len(CENAS) else TOTAL) - c["de"] for k, c in enumerate(CENAS)]
for k, c in enumerate(CENAS):
    print(f'{k + 1:2d} {c["de"]:6.2f} {dur[k]:4.2f}s {c["mundo"]:5s} {c.get("trans", ""):11s} {c["fala"]}')
sd = sorted(dur)
print("total", TOTAL, "· planos", len(CENAS), "· mediana", round(sd[len(sd) // 2], 2), "s · efeitos", len(EF))
