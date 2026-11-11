# gera o cenas.json do "Ninguém entra num grupo por fato" v2: roteiro simples (só fato × crença), voz fixa,
# clipes reais com o som deles, pessoas recortadas em camadas, prints reais do estudo e corte na batida da música
import json, re, sys
from pathlib import Path

AQUI = Path(__file__).parent
W = json.loads((AQUI / "work/words.json").read_text())["words"]
norm = lambda s: re.sub(r"[^\wçãõáéíóúâêô]", "", s.lower())


def t(palavra, apos=0.0, n=1):
    """início da n-ésima palavra igual a `palavra` depois do segundo `apos`"""
    for w in W:
        if w["start"] >= apos - .01 and norm(w["word"]) == norm(palavra):
            n -= 1
            if n == 0:
                return round(w["start"], 3)
    # a voz às vezes engole ou troca palavra: vai na mais parecida logo depois, avisa e segue (o vídeo não para por 1 palavra)
    import difflib
    cand = [w for w in W if w["start"] >= apos - .01][:12]
    if not cand:
        raise SystemExit(f"palavra não achada: {palavra} depois de {apos}")
    m = max(cand, key=lambda w: difflib.SequenceMatcher(None, norm(w["word"]), norm(palavra)).ratio())
    print(f"aviso: \"{palavra}\" não está na fala depois de {apos:.1f} s; usei \"{m['word']}\" em {m['start']:.2f} s", file=sys.stderr)
    return round(m["start"], 3)


def tempos(texto, de):
    out, ap = [], de
    for p in texto.split():
        x = t(p, ap)
        out.append(x)
        ap = x + .01
    return out


def texto(de, txt, forte=(), **k):
    return {"tipo": "texto", "de": de, "texto": txt, "forte": list(forte), "tempos": tempos(txt, de), **k}


def clipe(de, nome, som=.32, desde=0, **k):
    """vídeo real: quadros em clipes/q-<nome>/, o som dele entra baixo por baixo da voz"""
    return {"tipo": "clipe", "de": de, "quadros_de": f"clipes/q-{nome}", "inicio": desde, "_som": (nome, som, desde), **k}


F = lambda n: f"fotos/{n}.jpg"
F2 = lambda n: f"fotos2/{n}.jpg"
R = lambda n: f"recortes/{n}.png"
P = lambda n: f"prints/{n}.png"
CUR = [0.0]


def a(palavra):
    """próxima palavra igual na ordem da fala (cursor anda): o tempo não depende da voz"""
    x = t(palavra, CUR[0])
    CUR[0] = x + .01
    return x


c = []
c.append(clipe(a("pensa"), "torcida", som=.42))
c.append({"tipo": "cartao", "de": a("defende,"), "imagem": F("multidao-1"), "mov": "esq"})
c.append(clipe(a("o"), "bumbo", som=.35, entrada="chicote"))
a("seu"); a("time,")
c.append({"tipo": "recorte", "de": a("o"), "imagem": F("bandeira2-1"), "pb": True, "escuro": .45, "entrada": "chicote",
          "pessoas": [{"imagem": R("bolsonaro-0"), "x": 25, "altura": 58, "t": 0}, {"imagem": R("lula-1"), "x": -25, "altura": 54, "t": .14}]})
a("partido,")
c.append({"tipo": "foto", "de": a("a"), "imagem": F2("fiel-0"), "mov": "in", "entrada": "zoom"})
c.append(texto(a("agora"), "Agora responde rápido:", ["rápido:"], entrada="flash"))
v = a("você")
c.append({"tipo": "chips", "de": v, "imagem": F("olho-2"), "mov": "in",
          "itens": [{"texto": "fato", "t": a("fato")}, {"texto": "ou crença?", "t": a("crença?")}]})
n = a("ninguém")
c.append(texto(n, "Ninguém lembra do fato que fez entrar.", ["fato"]))
CUR[0] = n + .01; a("entrar.")
c.append(clipe(a("lembra"), "lula", som=.4, texto="Lembra do que sentiu.", forte=["sentiu."], y=46, entrada="negativo"))
c.append({"tipo": "contador", "de": a("em"), "imagem": F("escola2-1"), "de_n": 1900, "ate_n": 1971, "ano": True, "rotulo": "Bristol, Inglaterra"})
c.append({"tipo": "print", "de": a("psicólogo"), "imagem": P("estudo-jove"), "giro": -2, "largura": 84, "texto": "Henri Tajfel", "tam": "p", "y": 12})
c.append({"tipo": "rajada", "de": a("teste"), "imagens": [F("escola2-0"), F("escola2-1"), F("escola2-2"), F("escola2-3")], "quadros": 6})
c.append({"tipo": "dividido", "de": a("separou"), "imagens": [F("escola2-3"), F("escola2-2")], "rotulos": ["grupo A", "grupo B"], "entrada": "chicote"})
a("grupos")
c.append({"tipo": "icone", "de": a("por"), "imagem": F("dados-0"), "rotulo": "por sorteio", "forte": ["sorteio"], "entrada": "zoom"})   # emoji não vale (30-out): foto real dos dados (commons.py "dice") ou a logo real
c.append(texto(a("sem"), "Sem motivo nenhum.", ["nenhum."]))
c.append({"tipo": "foto", "de": a("poucos"), "imagem": F("escola2-3"), "pb": True, "ponto": True, "mov": "in", "texto": "em poucos minutos", "tam": "p", "y": 80, "escuro": .15})
c.append({"tipo": "foto", "de": a("cada"), "imagem": F("escola2-2"), "pb": True, "mov": "dir", "texto": "o próprio grupo", "forte": ["próprio"], "tam": "m"})
d_ = a("dava")
c.append({"tipo": "chips", "de": d_, "imagem": F2("dinheiro-0"), "mov": "in", "escuro": .5,
          "itens": [{"texto": "+ pros seus", "t": a("mais")}, {"texto": "− pros outros", "t": a("menos")}]})
c.append(texto(a("não"), "Não tinha fato nenhum ali.", ["fato"]))
c.append({"tipo": "foto", "de": a("só"), "imagem": F("camisa2-3"), "mov": "in", "texto": "Só uma camisa.", "forte": ["camisa."], "entrada": "negativo", "tam": "m"})
c.append(clipe(a("agora"), "lula2", som=.38, etiqueta="Brasil", nota="ninguém aqui está olhando dado", entrada="chicote"))
v = a("você")
c.append({"tipo": "zap", "de": v, "grupo": "Família 💛", "msgs": [
    {"eu": True, "texto": "Olha o dado aí 👇", "t": t("dado", v), "altura": 110},
    {"eu": True, "imagem": F("grafico-0"), "t": t("dado", v) + .3, "altura": 520},
    {"de": "Tio", "texto": "Isso aí é tudo manipulado.", "t": t("tio", v), "altura": 160},
    {"de": "Tio", "texto": "Agora que eu tenho certeza 💪", "t": t("convicto", v)}]})
pq = a("porque")
c.append(texto(pq, "Ninguém troca de crença por causa de um fato.", ["crença", "fato."]))
CUR[0] = pq + .01; a("fato,")
c.append({"tipo": "print", "de": a("o"), "imagem": P("materia-politica"), "giro": -1.6, "largura": 86})
c.append(clipe(a("time"), "torcida", som=.3, desde=30, etiqueta="O torcedor", nota="não escolheu o time pela tabela"))
c.append({"tipo": "foto", "de": a("fiel"), "imagem": F("culto2-1"), "mov": "esq", "foco": [.3, .6], "pb": True, "entrada": "chicote"})
c.append({"tipo": "print", "de": a("lendo"), "imagem": F("grafico-3"), "giro": 2, "largura": 76})
cl = a("cliente")
c.append({"tipo": "chips", "de": cl, "imagem": F("multidao-3"), "pb": True, "mov": "in", "escuro": .55,
          "itens": [{"texto": "preço", "t": t("lista", cl)}, {"texto": "prazo", "t": t("de", t("lista", cl))}, {"texto": "certificado", "t": t("fatos.", cl)}]})
a("fatos.")
c.append(clipe(a("ele"), "torcida", som=.35, desde=8, texto="daquilo que ele já acredita", forte=["acredita."], y=48, entrada="chicote"))
c.append(texto(a("essa"), "Essa é a técnica.", ["técnica."], entrada="flash", tam=96))
te = a("primeiro")
c.append({"tipo": "linha", "de": te, "marcos": [{"texto": "1º crença", "nota": "o que ele já acredita", "t": t("crença,", te)},
                                                {"texto": "2º fato", "nota": "a prova vem depois", "t": t("fato.", te)}]})
c.append(texto(a("ninguém"), "Ninguém entra num grupo por um fato.", ["fato."], tam=78))
a("fato."); c.append(clipe(a("entra"), "lula", som=.42, desde=10, texto="Entra porque acredita no mesmo que você.", forte=["acredita"], y=46, tam="m", entrada="zoom"))

DUR = round(W[-1]["end"] + .8, 2)
BAT = json.loads((AQUI / "work/batida.json").read_text())   # grade da música (periodo, primeiro batido no arquivo)
INI = BAT["primeiro"] - .15                                 # o drop cai em t=0,15 do vídeo

# plano longo vira dois (régua: mediana ~0,5-0,8 s), na palavra mais perto do meio
fim = lambda i: c[i + 1]["de"] if i + 1 < len(c) else DUR
novos = []
for i, x in enumerate(c):
    novos.append(x)
    d = fim(i) - x["de"]
    if x["tipo"] in ("foto", "cartao", "print") and d > 1.15 and not x.get("texto"):
        meio = x["de"] + d / 2
        cand = [w["start"] for w in W if x["de"] + .45 < w["start"] < fim(i) - .45]
        if cand:
            m = min(cand, key=lambda v: abs(v - meio))
            fo = x.get("foco", [.5, .5])
            novos.append(dict(x, de=round(m, 3), mov={"in": "out", "out": "in", "esq": "dir", "dir": "esq"}.get(x.get("mov"), "in"),
                              foco=[min(.8, max(.2, fo[0] + (.18 if i % 2 else -.18))), fo[1]], forca=1.3, entrada="corte"))
c = novos

# corte na batida: cena que começa até 0,12 s depois ou 0,06 s antes de um meio-tempo da música vai pra ele
meio_tempo = BAT["periodo"] / 2
grade = [.15 + k * meio_tempo for k in range(int(DUR / meio_tempo) + 2)]
for i, x in enumerate(c[1:], 1):
    b = min(grade, key=lambda g: abs(g - x["de"]))
    if -.12 <= b - x["de"] <= .06 and b > c[i - 1]["de"] + .3:
        x["de"] = round(b, 3)
na_batida = sum(1 for x in c if min(abs(g - x["de"]) for g in grade) < .02)

# clipe: o som dele por baixo da voz, do tamanho do plano (nunca o vídeo inteiro)
fx = []
for i, x in enumerate(c):
    so = x.pop("_som", None)
    if so:
        nome, vol, _ = so
        dur = min(fim(i) - x["de"], (len(list((AQUI / x["quadros_de"]).glob("*.jpg"))) - x["inicio"]) / 30)
        fx.append({"t": x["de"], "arquivo": f"clipes/som-{nome}.mp3", "volume": vol, "dur": round(dur, 2)})
    if x.get("entrada") in ("negativo", "flash", "zoom", "chicote"):
        fx.append({"t": max(0, x["de"] - .05), "arquivo": "audio/sfx/whoosh-short.mp3", "volume": .22})
    if x["tipo"] == "chips":
        fx += [{"t": it["t"], "arquivo": "audio/sfx/pop.mp3", "volume": .18} for it in x["itens"]]
    if x["tipo"] == "contador":
        fx.append({"t": x["de"] + .9, "arquivo": "audio/sfx/tique.mp3", "volume": .25})
    if x["tipo"] == "zap":
        fx += [{"t": m["t"], "arquivo": "audio/sfx/notificacao.mp3", "volume": .14} for m in x["msgs"] if not m.get("imagem")]
    if x["tipo"] == "icone":
        fx.append({"t": x["de"], "arquivo": "audio/sfx/click-soft.mp3", "volume": .22})
    if x["tipo"] == "recorte":
        fx += [{"t": x["de"] + p.get("t", 0), "arquivo": "audio/sfx/whoosh-short.mp3", "volume": .14} for p in x["pessoas"]]

doc = {"titulo": "Ninguém entra num grupo por fato", "saida": "grupo-por-crenca-v3.mp4", "largura": 1080, "altura": 1920, "fps": 30,
       "voz": "work/voz.wav", "palavras": "work/words.json", "duracao": DUR, "marca": "@soujoaovegas",
       "musica": {"arquivo": "audio/musicas/metamorphosis-interworld.mp3", "volume": .08, "inicio_s": round(INI, 3)},
       "efeitos": fx, "cenas": c}
(AQUI / "cenas.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
print(len(c), "cenas ·", len(fx), "efeitos ·", DUR, "s ·", na_batida, "cortes na batida")
