"""
Documentário · motor: index.html (seek(t)) quadro a quadro com Playwright → ffmpeg. O áudio sai daqui, não da IA:
voz + música do cenas.json com ducking (sidechain) + efeitos suaves nos eventos da timeline, -14 LUFS em duas passadas.

Roda de dentro da pasta copiada (formato, modelo do cliente ou sandbox). Tudo que ele grava fica ao lado do cenas.json
(ou em --out): quadros/, storyboard.jpg, qa/, _cache/ e o vídeo.

  python3 render.py                                       vídeo final (cenas.json da pasta atual)
  python3 render.py --cenas X/cenas.json --quadro 3.5,10  PNGs soltos em quadros/ (cenas = um por cena; tipos = um por tipo)
  python3 render.py --cenas X/cenas.json --storyboard     storyboard.jpg: um quadro por cena, pra aprovar antes do render;
                                                          confere as cenas antes (exit 1 com o motivo, que sai também
                                                          no rodapé) e grava previa-som.m4a (voz + música + efeitos)
  python3 render.py --cenas X/cenas.json --ate 6          só os 6 primeiros segundos (teste.mp4)
  python3 render.py --cenas X/cenas.json --conferir       reprova sozinho (exit 1) com o motivo em pt-BR;
                                                          grava qa/conferir.json e qa/folha-comparacao.jpg;
                                                          lê o PLANO.json ao lado: "Sem música"/efeitos desligados
                                                          pelo João na tela não reprovam
  python3 render.py --rostos work/joao.mp4                qa/rostos.jpg: o rosto do bruto a cada 0,5 s (quadro_s do jornal)
Legenda da pessoa: no peito, abaixo do queixo (o motor acha o rosto e sobe com o zoom). Efeitos: no ritmo do exemplo (16 em 1:23).
Cores: as do cliente (clientes/<Nome>/identidade.json → "papeis") quando houver; "cores" no cenas.json só sem cliente.
Esquema do cenas.json: README.md (exemplo completo: cenas-modelo.json).
Efeitos: "efeitos": true (todos) | false (nenhum) | ["typing", "whoosh-short", ...] (só esses sons; os outros não tocam).
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import multiprocessing as mp
import os
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")   # Mac: OpenCL roda no Metal e pode travar a saída do processo
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import wave
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _raiz() -> Path:
    for p in (AQUI, *AQUI.parents):
        if (p / "REGRAS.md").is_file() and (p / "formatos").is_dir():
            return p
    return Path.home() / "Projetos" / "Skill" / "Estúdio"


ESTUDIO = _raiz()
EXEMPLO = ESTUDIO / "formatos" / "documentario" / "exemplo-1.mp4"
BASE_FORMATO = ESTUDIO / "formatos" / "documentario" / "base"   # demo/ e audio/ de reserva pra cópia que não os tem
W, H, FPS, SR = 1080, 1920, 30, 48000

# números da conferência (vêm do exemplo-1 e das regras do formato)
TELA_MAX = 2.5        # M5: nenhuma tela parada mais de 2,5 s
ROSTO_MAX = 0.35      # pessoa falando em no máximo 35% do tempo (exemplo: ~27%)
PESSOA_TELA_MAX = 0.40  # a pessoa na tela somando tudo (falando, recorte, jornal, relógio com silhueta, polaroid/filme
                        # dela): exemplo ~35%. O Vídeo 1 V2 do Cliente4 tinha 52% e o rosto dele cansava
FORA_A_CADA_S = 21.0  # uma cena de fora (polaroid/filme com b-roll, nunca a própria pessoa) a cada ~21 s: exemplo 4 em 83 s.
                      # Com 30 s o Vídeo 1 V2 do Cliente4 (2 min) só pedia as 4 que o João já tinha escolhido e ninguém buscou cena nova
FORA_POLAROID_MIN = 1 / 3  # cenas de fora alternam filme (tira no jornal) e polaroid, como no exemplo (2 + 2). Na prova das 22h
                           # do V2 do Cliente4, 13 das 14 eram filme: a mesma tira de jornal a cada 8 s
RECORTE_A_CADA_S = 30.0  # recorte do bruto: no máximo 1 a cada ~30 s (o exemplo tem só a silhueta do relógio em 1:23). Selfie
                         # dá recorte igual: no mesmo V2, 6 recortes de frente e de camisa branca pareciam a mesma imagem
TIPOS_MIN = 6        # pelo menos 6 construções diferentes (exemplo: 8)
FRASE_MAX = 0.30      # frase em fundo liso em até 30% do tempo (exemplo: ~29%). O V2 refeito do Cliente4 tinha 43%: pra baixar a
                      # pessoa na tela, o agente trocou polaroid e relógio por frase, o caminho mais fácil
FRASE_SEGUIDAS_MAX = 2  # no máximo 2 frases em sequência (o V2 refeito tinha 4: CAIXA, TURNOVER, EXTREMAMENTE, DANOSO)
OBJETOS = ("polaroid", "caderno", "traco", "jornal", "filme", "relogio")   # construções de objeto: o que faz ser documentário
OBJETOS_MIN = 0.30    # objetos em pelo menos 30% do tempo (exemplo: ~45%; o V2 refeito tinha 19%)
QUADRO_PERTO_S = 2.0  # dois recortes (ou polaroids, ou filmes) do mesmo arquivo a menos de 2 s = a mesma imagem duas vezes
# palavra que pede a seguinte: cena que termina nela corta a ideia no meio ("BARGANHA o", "área do" + "LIVRE-MERCADO,")
PEDE_A_SEGUINTE = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "num",
    "numa", "pra", "pro", "pras", "pros", "para", "por", "pelo", "pela", "pelos", "pelas", "com", "sem", "ao", "aos", "ate",
    "entre", "sobre", "contra", "desde", "e", "ou", "nem", "que", "se", "mas", "porque", "pois", "como", "quando", "onde",
    "esse", "essa", "esses", "essas", "este", "esta", "estes", "estas", "desse", "dessa", "desses", "dessas", "deste",
    "desta", "nesse", "nessa", "neste", "nesta", "seu", "sua", "seus", "suas", "meu", "minha", "nosso", "nossa", "muito",
    "muita", "muitos", "muitas", "tao", "mais", "menos", "extremamente", "aquele", "aquela", "aqueles", "aquelas", "daquele",
    "daquela", "daqueles", "daquelas", "naquele", "naquela", "naqueles", "naquelas", "nesse", "dum", "duma"}
# palavra-chave fraca: não carrega a ideia sozinha. O storyboard do V2 do Cliente4 (nota 7,5) pôs em letra grande "muitas VEZES",
# "o tempo TODO", "muito GRANDE", "DIRETAMENTE com ele". Quantidade, intensidade, tempo genérico e pronome; advérbio em -mente também
PALAVRA_FRACA = PEDE_A_SEGUINTE | {
    "vez", "vezes", "todo", "toda", "todos", "todas", "grande", "grandes", "pequeno", "pequena", "inteiro", "inteira",
    "maior", "menor", "pouco", "pouca", "poucos", "poucas", "bem", "mal", "so", "sempre", "nunca", "ja", "ainda", "agora",
    "coisa", "coisas", "isso", "isto", "aquilo", "ele", "ela", "eles", "elas", "dele", "dela", "assim", "tipo", "ne", "ai",
    "entao", "aqui", "ali", "la", "sim", "nao", "e", "foi", "era", "ser", "ter", "tem", "fazer", "faz", "vai", "vou", "ta",
    "mesmo", "mesma", "maioria", "minoria"}
# palavra que abre outra ideia: a tela de texto pode fechar logo antes dela, mesmo sem vírgula ("quer TRABALHAR | e muitas vezes")
ABRE_IDEIA = {"e", "mas", "porem", "porque", "pois", "entao", "ou", "nem", "que", "quando", "se", "enquanto", "embora", "so"}
# a última tela não fecha pendurada ("DIRETAMENTE com ele", V2 do Cliente4): a última palavra dela não é uma destas
FIM_FRACO = PEDE_A_SEGUINTE | {"ele", "ela", "eles", "elas", "dele", "dela", "isso", "isto", "aquilo", "ne", "ai", "entao",
                               "assim", "tipo", "la", "aqui", "ali", "lo", "la", "los", "las", "lhe", "lhes"}
GANCHO_S = 3.0        # os 3 primeiros segundos numa construção (não precisa ser fundo preto)
# efeitos: medidos no exemplo-1.mp4 (espectro acima de 17 kHz, onde só os cliques do teclado chegam): 16 trechos de digitação em
# 82,8 s (≈ 11,6 por minuto), um por tela de texto, o mais perto um do outro a 2,4 s; passagem, pop e clique não aparecem.
# O V2 do Cliente4 tinha 108 em 2 min (46 teclados, 41 passagens), 7 vezes o ritmo do exemplo (prova nota 7,5). Teto = o exemplo
EFEITOS_POR_MIN = 12.0
EFEITO_ESPACO_S = 2.4
# fundo: o exemplo alterna papel claro (polaroid no papel, caderno quadriculado) e escuro: 2 telas claras em 1:23. A regra
# "fundo sempre escuro" do Cliente4 foi inventada (o João não pediu) e deixou o V2 todo escuro. Cliente que recusou papel
# claro (a Vegas recusou papel claro + azul na Cartilha) manda: "estilo": {"papel_claro": false} tira esta checagem
CLARO_A_CADA_S = 42.0
# cena de fora de banco de imagem (ator posando): o João odeia "banco de dados de vídeo". Vale cena de filme ou de arquivo real
BANCO = ("pexels", "pixabay", "shutterstock", "istock", "gettyimages", "storyblocks", "envato", "adobestock", "videvo",
         "coverr", "bancodeimagem", "bancodeimagens", "bancodevideo", "bancodevideos", "stockfootage")
MUSICA_MIN_DB = -35.0  # música audível nas pausas depois do ducking
MUSICA_ALVO_DB = -33.0  # onde o motor põe a música nas pausas (G9: ~-35 nas pausas, ~-40 sob a fala; 2 dB de folga)
DRONE_MAX = 0.20      # médio+agudo abaixo disso = drone/pad

CONSTRUCOES = ("frase", "recorte", "polaroid", "caderno", "relogio", "traco", "jornal", "filme")
TIPOS = ("pessoa",) + CONSTRUCOES
NOME = {"frase": "Frase", "pessoa": "Pessoa", "recorte": "Recorte", "polaroid": "Polaroid", "caderno": "Caderno",
        "relogio": "Relógio", "traco": "Traço", "jornal": "Jornal", "filme": "Filme"}
# efeitos suaves (Pixabay, base/audio/sfx): arquivo, volume. Passa-alta em 200 Hz: nada de grave nem golpe.
SONS = {"typing": ("typing.mp3", .10), "key-press": ("key-press.mp3", .14), "whoosh-short": ("whoosh-short.mp3", .12),
        "click-soft": ("click-soft.mp3", .18), "pop": ("pop.mp3", .12), "tique": ("key-press.mp3", .12)}
# nome curto de cada som pro João (rodapé do storyboard e motivos do --conferir)
ROTULO = {"typing": "teclado", "whoosh-short": "passagem", "click-soft": "clique", "tique": "tique do relógio",
          "pop": "pop", "key-press": "tecla"}
GOLPES = {"hit", "impacto", "impact", "impact-bass", "boom", "thud", "golpe", "slam", "soco", "bass"}
CORES = {"marca": "#D4AF37", "dor": "#E23A3A", "fundo": "#0c0c0e", "texto": "#F4EFE6", "caneta": "#2747b8", "ok": "#2fa36b"}
# Cor do cliente: clientes/<Nome>/identidade.json ("papeis") ganha do padrão do motor; o "cores" do cenas.json ganha das
# duas. O Cliente4 saiu dourado e vermelho (o padrão) com a cor dele já no identidade.json: o João pediu "usa a cor dele".
PAPEIS = {"marca": "destaque", "dor": "dor", "empresa": "empresa_lideranca", "fundo": "fundo", "texto": "texto",
          "etiqueta": "destaque_escuro", "ok": "destaque_escuro"}
IMAGEM = (".jpg", ".jpeg", ".png", ".webp")


# ───────────────────────────── leitura e planejamento (sem navegador) ─────────────────────────────

def identidade(pasta: Path) -> tuple[dict, Path | None]:
    """O identidade.json do cliente dono da pasta (clientes/<Nome>/identidade.json) e o caminho dele; ({}, None) se não houver."""
    for p in (pasta.resolve(), *pasta.resolve().parents):
        if p.parent.name == "clientes":
            arq = p / "identidade.json"
            try:
                return json.loads(arq.read_text(encoding="utf-8")), arq
            except (OSError, ValueError):
                return {}, None
    return {}, None


def cores_do_cliente(pasta: Path) -> dict:
    """As cores do motor que o identidade.json do cliente define ("papeis", só as que são #hex)."""
    papeis = identidade(pasta)[0].get("papeis") or {}
    return {k: papeis[v] for k, v in PAPEIS.items()
            if isinstance(papeis.get(v), str) and re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", papeis[v].strip())}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def achar(caminho: str | None, pasta: Path) -> Path | None:
    """Caminho do cenas.json: absoluto, ou relativo à pasta do cenas.json, ao motor, à base do formato ou à raiz do Estúdio."""
    if not caminho:
        return None
    p = Path(caminho).expanduser()
    if p.is_absolute():
        return p
    for base in (pasta, AQUI, BASE_FORMATO, ESTUDIO):
        if (base / p).exists():
            return (base / p).resolve()
    return (pasta / p).resolve()


def ler_palavras(arq: Path | None) -> list[dict]:
    """words.json do Groq/Scribe ({"words": [{word, start, end}]}) ou lista [{w, s, e}]."""
    if not arq or not arq.is_file():
        return []
    d = json.loads(arq.read_text(encoding="utf-8"))
    ws = d.get("words") if isinstance(d, dict) else d
    out = []
    for w in ws or []:
        txt = str(w.get("word") or w.get("w") or w.get("text") or "").strip()
        s = w.get("start", w.get("s"))
        e = w.get("end", w.get("e"))
        if txt and s is not None:
            out.append({"w": txt, "s": float(s), "e": float(e if e is not None else float(s) + .25)})
    return out


def duracao_midia(p: Path | None) -> float:
    if not p or not p.exists():
        return 0.0
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _frases(lista) -> list[list[str]]:
    return [[norm(w) for w in str(x).split() if norm(w)] for x in (lista or []) if str(x).strip()]


def _marcar(toks: list[dict], destaque, dor, empresa=()) -> None:
    """Palavra-chave: cor da marca (bom), de dor ou de empresa/liderança (a 3ª cor do cliente; sem ela, a da marca).
    Aceita expressão de várias palavras."""
    ns = [norm(t["txt"]) for t in toks]
    for k, frases in (("marca", _frases(destaque)), ("dor", _frases(dor)), ("empresa", _frases(empresa))):
        for f in frases:
            for i in range(len(ns) - len(f) + 1):
                if ns[i:i + len(f)] == f:
                    for j in range(i, i + len(f)):
                        toks[j]["k"] = k


def tokens_cena(c: dict, ws: list[dict], de: float, ate: float, destaque, dor, empresa=()) -> list[dict]:
    """A fala literal daquele trecho, palavra por palavra no tempo em que é falada. "texto" corrige o que a
    transcrição errou (mesma contagem de palavras = mesmos tempos; senão espalha no trecho)."""
    falados = [w for w in ws if de - .05 <= w["s"] < ate - .05]
    if c.get("texto"):
        pal = str(c["texto"]).split()
        if c.get("seco"):   # entra seco (abertura em cortes rápidos): todas as palavras nos primeiros 0,3 s da cena
            base = [(p, de + i * .1, de + i * .1 + .08) for i, p in enumerate(pal)]
        elif len(pal) == len(falados):
            base = [(p, w["s"], w["e"]) for p, w in zip(pal, falados)]
        else:
            t0 = falados[0]["s"] if falados else de + .1
            t1 = falados[-1]["e"] if falados else max(t0 + .3, ate - .35)
            passo = max(.08, (t1 - t0) / max(1, len(pal)))
            base = [(p, t0 + i * passo, t0 + (i + 1) * passo - .02) for i, p in enumerate(pal)]
    else:
        base = [(w["w"], w["s"], w["e"]) for w in falados]
    toks = [{"txt": t, "s": round(s, 3), "e": round(max(s + .06, min(e, ate - .02)), 3), "k": ""} for t, s, e in base]
    _marcar(toks, destaque, dor, empresa)
    return toks


def blocos_legenda(toks: list[dict], ate: float) -> list[dict]:
    """Pessoa: legenda em blocos curtos (até 5 palavras), quebrando na pontuação e nas pausas."""
    grupos, cur = [], []
    for i, tk in enumerate(toks):
        cur.append(tk)
        prox = toks[i + 1] if i + 1 < len(toks) else None
        if not prox or len(cur) >= 5 or tk["txt"][-1:] in ".?!,;:" or prox["s"] - tk["e"] > .35:
            grupos.append(cur)
            cur = []
    out = []
    for k, g in enumerate(grupos):
        prox = grupos[k + 1][0]["s"] if k + 1 < len(grupos) else ate
        out.append({"s": g[0]["s"], "fim": round(max(g[0]["s"] + .25, min(prox, g[-1]["e"] + .8)), 3), "tokens": g})
    return out


def ancora(ws: list[dict], texto: str, de: float, ate: float, padrao: float) -> float:
    """Quando a primeira palavra de `texto` é falada dentro da cena (senão, o tempo padrão)."""
    alvo = norm((str(texto or "").split() or [""])[0])
    if alvo:
        for w in ws:
            if de - .1 <= w["s"] < ate and norm(w["w"]).startswith(alvo):
                return round(w["s"], 3)
    return round(padrao, 3)


def som_do_motor(x) -> str | None:
    """'whoosh-short', 'Whoosh' ou 'whoosh_short' → 'whoosh-short'; som que o motor não tem → None."""
    s = str(x or "").strip().lower().replace("_", "-").replace(" ", "-")
    if s in SONS:
        return s
    return next((k for k in SONS if k.split("-")[0] == s), None)


def arquivo_sfx(nome: str) -> Path:
    """audio/sfx/<nome> da cópia (modelo do cliente ou sandbox); som que a cópia não tem vem da base do formato
    (a sandbox do Vídeo 1 V2 do Cliente4 foi copiada antes do tique.mp3 existir)."""
    papel = Path(nome).stem
    for pasta in (AQUI, BASE_FORMATO):                  # 2 ou mais variantes em audio/sfx/<papel>/: a menos usada do cliente (rodízio)
        v = _variante_sfx(pasta / "audio" / "sfx", papel)
        if v:
            return v
    p = AQUI / "audio" / "sfx" / nome
    return p if p.exists() else BASE_FORMATO / "audio" / "sfx" / nome


def _variante_sfx(sfx_dir: Path, papel: str):
    if len(list((sfx_dir / papel).glob("*.mp3"))) < 2:   # sem variante de verdade: vale o arquivo solto de sempre
        return None
    try:
        sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
        import musica_busca
        partes = AQUI.parts
        cliente = partes[partes.index("clientes") + 1] if "clientes" in partes else ""
        return musica_busca.sfx_do_papel(papel, cliente, AQUI.name, sfx_dir)
    except Exception:
        return next(iter(sorted((sfx_dir / papel).glob("*.mp3"))), None)


def sons_ligados(valor) -> set[str]:
    """O "efeitos" do cenas.json → os sons que tocam. true = todos; false, null ou [] = nenhum;
    lista = só esses sons (nomes do motor; também aceita os itens do PLANO.json, {som|id, ligado})."""
    if valor is True:
        return set(SONS)
    if not valor:
        return set()
    if isinstance(valor, dict) and not {"som", "id"} & set(valor):   # {"typing": true, "pop": false}
        valor = [k for k, v in valor.items() if v]
    if isinstance(valor, (str, dict)):
        valor = [valor]
    if not isinstance(valor, (list, tuple, set)):
        return set(SONS)
    out = set()
    for x in valor:
        if isinstance(x, dict):
            if x.get("ligado", True) is False:
                continue
            x = x.get("som") or x.get("id")
        s = som_do_motor(x)
        if s:
            out.add(s)
    return out


def planejar(doc: dict, pasta: Path) -> dict:
    """cenas.json → plano com todos os tempos (cada palavra, item, marca, rótulo) e os eventos de efeito.
    O index.html só desenha o que o plano manda; a conferência usa o mesmo plano."""
    ws = ler_palavras(achar(doc.get("palavras"), pasta))
    cenas = sorted((dict(c) for c in doc.get("cenas") or []), key=lambda c: float(c.get("de", 0)))
    erros = [f"cena {i + 1}: tipo '{c.get('tipo')}' não existe (use {', '.join(TIPOS)})" for i, c in enumerate(cenas) if c.get("tipo") not in TIPOS]
    if erros:
        raise SystemExit("\n".join(erros))
    total = float(doc.get("duracao") or 0)
    if not total:
        total = max([float(c["ate"]) for c in cenas if c.get("ate") is not None] or [0])
        if not cenas or cenas[-1].get("ate") is None:
            fonte = achar(doc.get("voz") or doc.get("video"), pasta)
            total = max(total, duracao_midia(fonte) if fonte and fonte.suffix.lower() not in IMAGEM else 0,
                        (ws[-1]["e"] + .8) if ws else 0)
    est = doc.get("estilo") or {}
    maiusc = est.get("maiusculas", True)
    foco = est.get("foco", [.5, .4])
    plano_ant = "close"
    out = []
    for i, c in enumerate(cenas):
        de = round(float(c["de"]), 3)
        ate = round(float(c["ate"]) if c.get("ate") is not None else (float(cenas[i + 1]["de"]) if i + 1 < len(cenas) else total), 3)
        c.update({"i": i, "n": i + 1, "de": de, "ate": ate})
        if est.get("sem_legenda"):   # "Sem legenda": nenhuma cena escreve a fala (a mesma `legenda: false` de cada cena)
            c["legenda"] = False
        dest = list(doc.get("destaque") or []) + list(c.get("destaque") or [])
        dor = list(doc.get("dor") or []) + list(c.get("dor") or [])
        emp = list(doc.get("empresa") or []) + list(c.get("empresa") or [])
        toks = tokens_cena(c, ws, de, ate, dest, dor, emp)
        tipo = c["tipo"]
        if tipo in ("frase", "traco") and maiusc:
            for tk in toks:
                if tk["k"]:
                    tk["txt"] = tk["txt"].upper()
        if tipo in ("frase", "traco") and toks and toks[-1]["txt"].rstrip(",;:"):
            toks[-1]["txt"] = toks[-1]["txt"].rstrip(",;:")   # tela que termina em vírgula parece pedaço ("LIVRE-MERCADO,")
        c["tokens"] = toks
        c["fala"] = " ".join(w["w"] for w in ws if de - .05 <= w["s"] < ate - .05) or (c.get("texto") or "")
        dur = ate - de
        if tipo == "pessoa":
            if not c.get("plano"):
                c["plano"] = "aberto" if plano_ant == "close" else "close"
            plano_ant = c["plano"]
            c["foco"] = c.get("foco") or foco
            c["blocos"] = [] if est.get("sem_legenda") else blocos_legenda(toks, ate)
        elif tipo == "relogio":
            c["relogio"] = {"de": str(c.get("de_hora", "23:00")), "ate": str(c.get("ate_hora", "05:00")),
                            "t0": round(de + .15, 3), "t1": round(max(de + .5, ate - .35), 3)}
        elif tipo == "caderno":
            itens = c.get("itens") or []
            for k, it in enumerate(itens):
                it = it if isinstance(it, dict) else {"texto": str(it)}
                t = ancora(ws, it.get("em") or it.get("texto"), de, ate, de + .5 + k * (dur - 1.2) / max(1, len(itens)))
                # o X/✓ termina de desenhar dentro da cena (fala no fim da cena puxa a marca pra mais perto)
                it.update({"t": t, "tm": round(max(t + .1, min(t + .45, ate - .35)), 3), "marca": it.get("marca")})
                itens[k] = it
            c["itens"] = itens
            if c.get("circulo"):
                ci = dict(c["circulo"]) if isinstance(c["circulo"], dict) else {"texto": str(c["circulo"])}
                ult = max([it["tm"] + .3 for it in itens] or [de + .6])
                ci["t"] = min(ancora(ws, ci.get("em") or ci.get("texto"), de, ate, min(ult, ate - .7)), round(ate - .55, 3))
                c["circulo"] = ci
        elif tipo == "traco":
            chave = next((tk["s"] for tk in toks if tk["k"]), None)
            c["traco_t"] = round(min(max(de + .2, min(chave if chave is not None else 99, de + .3 * dur)), ate - 1.0), 3)
            rot = {}
            for lado, extra in (("esquerda", .55), ("direita", .95)):
                r = (c.get("rotulos") or {}).get(lado)
                if r:
                    r = dict(r) if isinstance(r, dict) else {"texto": str(r)}
                    r["t"] = min(ancora(ws, r.get("em") or r.get("texto"), de, ate, min(c["traco_t"] + extra, ate - .3)), round(ate - .3, 3))
                    rot[lado] = r
            c["rotulos"] = rot
        elif tipo == "jornal":
            c["etiqueta_t"] = round(de + .35, 3)
        out.append(c)
    # buracos e sobreposições entre cenas
    avisos = []
    for a, b in zip(out, out[1:]):
        if b["de"] - a["ate"] > .02:
            avisos.append(f"buraco de {br(b['de'] - a['ate'], 2)} s entre a cena {a['n']} e a {b['n']} (tela preta)")
        if a["ate"] - b["de"] > .02:
            avisos.append(f"cena {a['n']} invade a cena {b['n']} ({br(a['ate'] - b['de'], 2)} s)")
    if out and out[0]["de"] > .02:
        avisos.append(f"o vídeo começa com {br(out[0]['de'], 2)} s de tela preta")
    liga = sons_ligados(doc.get("efeitos", True))
    cores = {**CORES, **cores_do_cliente(pasta), **(doc.get("cores") or {})}
    cores.setdefault("empresa", cores["marca"])
    cores.setdefault("etiqueta", cores["marca"])
    cores["etiqueta-txt"] = "#111111" if _luz(cores["etiqueta"]) > .5 else "#ffffff"
    total = round(total or (out[-1]["ate"] if out else 0), 3)
    return {"total": total, "cenas": out, "palavras": ws,
            "eventos": eventos(out, liga, total), "sons": sorted(liga),
            "avisos": avisos, "cores": cores, "estilo": est}


def _luz(hexa: str) -> float:
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 1.0
    return .2126 * r + .7152 * g + .0722 * b


def mundo(c: dict) -> str:
    """O "mundo" da tela: pessoa, papel claro, jornal ou escuro. Passagem (whoosh) só quando o mundo muda."""
    t = c.get("tipo")
    if t == "pessoa":
        return "pessoa"
    if (t == "caderno" and c.get("tom") != "escuro") or c.get("fundo") == "papel":
        return "claro"
    if t in ("polaroid", "filme", "jornal") and c.get("fundo") in (None, "jornal"):
        return "jornal"
    return "escuro"


def tela_clara(c: dict) -> bool:
    return mundo(c) == "claro"


def candidatos_de_efeito(cenas: list[dict]) -> list[dict]:
    """Onde cabe um efeito suave, com a prioridade (p: 1 primeiro). Como no exemplo-1, o som principal é o teclado da tela
    de texto; o resto é um toque por construção (tique no fim do relógio, clique no círculo ou na última marca do caderno,
    tecla no rótulo do traço, pop na polaroid e na etiqueta) e a passagem só quando o mundo muda. Nunca golpe."""
    ev = []
    ant = None
    for c in cenas:
        i, tipo = c["i"], c["tipo"]
        toks = c.get("tokens") or []
        if tipo in CONSTRUCOES and tipo != "caderno" and toks and c.get("legenda", True) is not False:
            ev.append({"t": toks[0]["s"], "som": "typing", "dur": round(min(1.5, max(.25, toks[-1]["e"] - toks[0]["s"])), 3),
                       "cena": i, "p": 1 if tipo in ("frase", "traco", "relogio") else 3})
        if tipo == "relogio":
            ev.append({"t": c["relogio"]["t1"], "som": "tique", "cena": i, "p": 2})
        if tipo == "caderno":
            marcas = [it["tm"] for it in c["itens"] if it.get("marca")]
            t = c["circulo"]["t"] if c.get("circulo") else (marcas[-1] if marcas else None)
            if t is not None:
                ev.append({"t": t, "som": "click-soft", "cena": i, "p": 2})
        if tipo == "traco":
            r = c["rotulos"].get("direita") or c["rotulos"].get("esquerda")
            if r:
                ev.append({"t": r["t"], "som": "key-press", "cena": i, "p": 2})
        if tipo == "polaroid":
            ev.append({"t": round(c["de"] + .3, 3), "som": "pop", "cena": i, "p": 4})
        if tipo == "jornal":
            ev.append({"t": c["etiqueta_t"], "som": "pop", "cena": i, "p": 4})
        if tipo in CONSTRUCOES and (ant is None or mundo(ant) != mundo(c)):
            ev.append({"t": round(max(0, c["de"] - .06), 3), "som": "whoosh-short", "cena": i, "p": 5})
        ant = c
    return sorted(ev, key=lambda e: e["t"])


def teto_efeitos(total: float) -> int:
    """Quantos efeitos o vídeo pode ter: o ritmo do exemplo (EFEITOS_POR_MIN)."""
    return max(1, round(total / 60 * EFEITOS_POR_MIN)) if total > 0 else 0


def eventos(cenas: list[dict], liga: set[str] | None = None, total: float | None = None) -> list[dict]:
    """Os efeitos que tocam: dos candidatos (só os sons ligados), pela prioridade e depois pelo tempo, um de cada vez, no
    máximo teto_efeitos(total) e com folga entre eles (EFEITO_ESPACO_S, ou mais quando o vídeo é longo: o teto se espalha
    pelo vídeo todo em vez de acabar no começo). Suave e espaçado como no exemplo; o V2 do Cliente4 tocava 108 em 2 min."""
    liga = set(SONS) if liga is None else set(liga)
    cands = [e for e in candidatos_de_efeito(cenas) if e["som"] in liga]
    if total is None:
        total = max([c["ate"] for c in cenas] or [0])
    teto = teto_efeitos(total)
    folga = max(EFEITO_ESPACO_S, .8 * total / teto) if teto else EFEITO_ESPACO_S
    escolhidos: list[dict] = []
    for e in sorted(cands, key=lambda e: (e["p"], e["t"])):
        if len(escolhidos) >= teto:
            break
        if all(abs(e["t"] - x["t"]) >= folga for x in escolhidos):
            escolhidos.append(e)
    return sorted(({k: v for k, v in e.items() if k != "p"} for e in escolhidos), key=lambda e: e["t"])


# ───────────────────────────── mídia: quadros, stills e recortes ─────────────────────────────

def _hash(*partes) -> str:
    return hashlib.sha1("|".join(map(str, partes)).encode()).hexdigest()[:12]


def _ff(*args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True, **kw)


def _autocorte(src: Path, ss: float, dur: float) -> tuple[float, float, float, float]:
    """Tira barras pretas (cenas de filme vêm letterbox): caixa útil em frações (x, y, w, h)."""
    import numpy as np
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
                       capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(r[0]), int(r[1])
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(ss), "-t", str(min(dur, 4)), "-i", str(src),
                          "-vf", "fps=3,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    q = np.frombuffer(raw, np.uint8)
    if len(q) < w * h:
        return (0, 0, 1, 1)
    q = q[: len(q) // (w * h) * w * h].reshape(-1, h, w).max(axis=0)
    linhas = np.where(q.mean(axis=1) > 20)[0]
    cols = np.where(q.mean(axis=0) > 20)[0]
    if not len(linhas) or not len(cols):
        return (0, 0, 1, 1)
    y0, y1, x0, x1 = linhas[0], linhas[-1] + 1, cols[0], cols[-1] + 1
    return (x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h)


def _quadros(src: Path, ss: float, dur: float, pasta: Path, filtro: str, k0: int) -> int:
    """Extrai quadros JPEG a 30 fps (numerados a partir de k0). Devolve quantos existem."""
    pasta.mkdir(parents=True, exist_ok=True)
    n = int(round(dur * FPS)) + 2
    if not ((pasta / f"{k0:06d}.jpg").exists() and (pasta / f"{k0 + n - 3:06d}.jpg").exists()):
        _ff("-ss", f"{ss:.3f}", "-t", f"{dur + .1:.3f}", "-i", src, "-an", "-vf", f"fps={FPS},{filtro}", "-q:v", 3,
            "-start_number", k0, pasta / "%06d.jpg")
    return len([p for p in pasta.glob("*.jpg") if k0 <= int(p.stem) < k0 + n])


def _still(src: Path, t: float | None, destino: Path, filtro: str) -> Path:
    if not destino.exists():
        if src.suffix.lower() in IMAGEM:
            _ff("-i", src, "-vf", filtro, "-q:v", 3, destino)
        else:
            _ff("-ss", f"{t or 0:.3f}", "-i", src, "-frames:v", 1, "-vf", filtro, "-q:v", 3, destino)
    return destino


_SESSOES: dict = {}


def _sessao(nome: str):
    from rembg import new_session
    if nome not in _SESSOES:
        _SESSOES[nome] = new_session(nome)
    return _SESSOES[nome]


def _so_gente(im, a):
    """Corta do recorte o que não é gente. O u2net pega o que se destaca, e o abajur grudado na cabeça do Cliente4 (quadro
    111 do Vídeo 1 V2) saiu junto, porque encosta na cabeça e o filtro de pedaço solto não separa. O u2net_human_seg só
    pega gente: a máscara dele (alargada só uns 6 px; com 20 px ainda sobrava uma tira do abajur) limita a do u2net, que
    tem a borda mais fina. Sem esse modelo (1ª vez sem rede) ou com máscara de gente quase vazia, fica só o u2net."""
    import numpy as np
    from PIL import Image, ImageFilter
    from rembg import remove
    try:
        h = remove(im, session=_sessao("u2net_human_seg"), only_mask=True)
    except Exception as e:   # noqa: BLE001 — sem o modelo de gente o recorte sai mesmo assim
        print(f"aviso: recorte sem o filtro de gente ({e})", file=sys.stderr)
        return a
    h = h.convert("L") if hasattr(h, "convert") else Image.fromarray(np.asarray(h).astype(np.uint8))
    hm = h.point(lambda v: 255 if v > 60 else 0)
    if np.asarray(hm).sum() < .3 * (a > 0).sum() * 255:
        return a
    hm = hm.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(3))
    return np.minimum(a, np.asarray(hm, dtype=np.uint8))


def _tirar_fundo(src: Path, out: Path) -> None:
    """Recorte P&B com borda branca (rembg u2net no Mac + PIL), só da pessoa (_so_gente). A borda não aparece onde o
    corpo encosta na moldura."""
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps
    from rembg import remove
    im = Image.open(src).convert("RGB")
    if im.height < 1500:
        im = im.resize((round(im.width * 1500 / im.height), 1500), Image.LANCZOS)
    corte = remove(im, session=_sessao("u2net"))
    a = np.array(corte.split()[-1]).astype(np.uint8)
    a[a < 40] = 0
    a = _so_gente(im, a)
    try:   # só a pessoa: pedaço solto que o rembg pegou do fundo (abajur, quadro) sai
        from scipy import ndimage
        rot, n = ndimage.label(a > 0)
        if n > 1:
            tam = ndimage.sum(np.ones_like(a), rot, range(1, n + 1))
            a[(rot > 0) & (rot != 1 + int(np.argmax(tam)))] = 0
    except ImportError:
        pass
    b = max(10, int(im.height * .011))
    pa = np.pad(a, b * 2, mode="edge")
    m = Image.fromarray(pa)
    for _ in range(max(1, b // 2)):
        m = m.filter(ImageFilter.MaxFilter(5))
    borda = np.array(m)[b * 2:-b * 2, b * 2:-b * 2]
    cinza = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
    cinza = Image.eval(cinza, lambda v: int(min(255, max(0, (v - 128) * 1.12 + 128))))
    pessoa = Image.merge("RGBA", (cinza, cinza, cinza, Image.fromarray(a)))
    fundo = Image.new("RGBA", im.size, (255, 255, 255, 0))
    fundo.putalpha(Image.fromarray(borda))
    fundo.alpha_composite(pessoa)
    caixa = fundo.getbbox()
    (fundo.crop(caixa) if caixa else fundo).save(out)


def recortar(src: Path, t: float | None, cache: Path) -> Path:
    out = cache / f"recorte-{_hash(src, t, 'v3')}.png"   # v3: só gente (o v2 levava o abajur junto)
    if out.exists():
        return out
    q = _still(src, t, cache / f"quadro-{_hash(src, t)}.png", "null")
    try:
        _tirar_fundo(q, out)
    except ImportError:   # rembg só no .venv do Estúdio
        py = ESTUDIO / "app" / ".venv" / "bin" / "python"
        subprocess.run([str(py), str(Path(__file__).resolve()), "--_recortar", str(q), str(out)], check=True)
    return out


# ───────────────────────────── rosto: legenda abaixo do queixo e quadro bom do rosto ─────────────────────────────
# No storyboard do V2 do Cliente4 (selfie 576x1024, rosto grande) a legenda das cenas de pessoa caiu em cima da boca e da barba
# em metade das cenas: ela ficava num y fixo (1290) e o close crescia em volta do foco, empurrando o queixo pra baixo dela.
# No exemplo-1 a legenda fica no peito, abaixo do queixo. Agora o motor acha o rosto (haar do OpenCV, sem rede) em cada cena
# de pessoa e põe a legenda abaixo do queixo; o --conferir confere no vídeo pronto.
QUEIXO_H = 1.2       # o queixo (com barba) fica ~1,2 altura da caixa do rosto abaixo do topo dela (medido no bruto do Cliente4)
LEG_MARGEM = 30      # px entre o queixo e o topo da legenda, no mínimo
# Folga queixo → legenda em alturas do rosto na tela. Com 30 px fixos a legenda do V2 do Cliente4 (selfie, rosto grande) colou
# na ponta da barba (cenas 4, 8 e 10 do storyboard: folga de 0,09 a 0,18 rosto). No exemplo-1 ela fica no peito, ~1,5 rosto
# abaixo do queixo; na selfie não cabe tanto, então o motor sobe o rosto com o zoom até sobrar LEG_FOLGA, e o --storyboard e o
# --conferir medem no quadro pronto e reprovam abaixo de LEG_FOLGA_MIN (a diferença é a folga pra caixa do rosto que oscila).
LEG_FOLGA = .35
LEG_FOLGA_MIN = .22
LEG_MAX_Y = 1500     # topo da legenda no máximo aqui: o exemplo tem texto até ~1490; abaixo é a zona da legenda do post (G3)
ZOOM = {"aberto": (1.0, 1.035), "close": (1.36, 1.40)}
MOV_MAX = 20.0       # mexida do rosto entre quadros a 0,2 s (média da diferença em 0-255): acima disso o quadro sai borrado
                     # (bruto do Cliente4: mediana 12, o quarto que mais mexe passa de 19; o jornal do V2, com a mão borrada, 34)
_CASCATAS: dict = {}
_TRECHOS: dict = {}


def _cascata(nome: str):
    import cv2
    if nome not in _CASCATAS:
        _CASCATAS[nome] = cv2.CascadeClassifier(cv2.data.haarcascades + f"haarcascade_{nome}.xml")
    return _CASCATAS[nome]


def _quadros_cinza(src: Path, ss: float, dur: float, fps: float) -> list[tuple[float, object]]:
    """[(tempo, quadro em cinza até 720 px de largura)] do trecho do vídeo, ou a foto uma vez. [] se não der pra ler."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if src.suffix.lower() in IMAGEM:
        g = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
        if g is None:
            return []
        if g.shape[1] > 720:
            g = cv2.resize(g, (720, round(g.shape[0] * 720 / g.shape[1])))
        return [(float(ss), g)]
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, ss):.3f}", "-t", f"{max(.05, dur):.3f}", "-i", str(src),
                        "-an", "-vf", f"fps={fps},scale='min(720,iw)':-2,format=gray", "-f", "image2pipe", "-c:v", "pgm", "-"],
                       capture_output=True).stdout
    out, pos, k = [], 0, 0
    while pos < len(r):   # PGM um atrás do outro: "P5\n<w> <h>\n255\n" + w*h bytes
        m = re.match(rb"P5\s+(\d+)\s+(\d+)\s+(\d+)\s", r[pos:pos + 64])
        if not m:
            break
        w_, h_ = int(m.group(1)), int(m.group(2))
        ini = pos + m.end()
        if ini + w_ * h_ > len(r):
            break
        out.append((round(max(0.0, ss) + k / fps, 3), np.frombuffer(r, np.uint8, w_ * h_, ini).reshape(h_, w_).copy()))
        pos, k = ini + w_ * h_, k + 1
    return out


def _rosto(g) -> dict | None:
    """O maior rosto de frente no quadro: caixa em frações, olhos (0 a 3; 0 = fechados, fora ou tapados), nitidez e aspecto."""
    import cv2
    h_, w_ = g.shape[:2]
    eq = cv2.equalizeHist(g)
    fs = _cascata("frontalface_default").detectMultiScale(eq, 1.1, 5, minSize=(max(24, w_ // 8),) * 2)
    if not len(fs):
        return None
    x, y, w, h = (int(v) for v in max(fs, key=lambda f: f[2] * f[3]))
    roi = eq[y + int(.2 * h): y + int(.55 * h), x: x + w]
    olhos = 0
    if roi.size:
        roi = cv2.resize(roi, (400, max(1, round(400 * roi.shape[0] / max(1, roi.shape[1])))))
        # dois detectores de olho aberto (calibrados em quadros do Cliente4: olho fechado quase nunca soma 3)
        olhos = sum(min(cap, len(_cascata(n).detectMultiScale(roi, 1.05, 3, minSize=(40, 40), maxSize=(160, 160))))
                    for n, cap in (("eye_tree_eyeglasses", 2), ("righteye_2splits", 1)))
    nit = float(cv2.Laplacian(cv2.resize(g[y:y + h, x:x + w], (200, 200)), cv2.CV_64F).var())
    return {"x": round(x / w_, 4), "y": round(y / h_, 4), "w": round(w / w_, 4), "h": round(h / h_, 4),
            "olhos": int(olhos), "nitidez": round(nit, 1), "aspecto": round(w_ / h_, 4)}


def rostos_no_trecho(src: Path, ss: float, dur: float, fps: float = 2.0) -> list[dict]:
    """[{t, rosto, mov}] dos quadros do trecho: o rosto (ou None) e o quanto ele mexeu desde o quadro anterior."""
    import numpy as np
    try:
        chave = (str(src.resolve()), src.stat().st_mtime, round(ss, 2), round(dur, 2), fps)
    except OSError:
        return []
    if chave in _TRECHOS:
        return _TRECHOS[chave]
    try:
        import cv2
        quadros = _quadros_cinza(src, ss, dur, fps)
        out, ant = [], None
        for t, g in quadros:
            r = _rosto(g)
            mov = None
            if r and ant is not None and ant.shape == g.shape:
                h_, w_ = g.shape[:2]
                x, y, w, h = int(r["x"] * w_), int(r["y"] * h_), int(r["w"] * w_), int(r["h"] * h_)
                a = cv2.resize(ant[y:y + h, x:x + w], (100, 100)).astype(np.int16)
                b = cv2.resize(g[y:y + h, x:x + w], (100, 100)).astype(np.int16)
                mov = round(float(np.abs(a - b).mean()), 2)
            out.append({"t": t, "rosto": r, "mov": mov})
            ant = g
    except ImportError:   # sem OpenCV: o motor segue como antes (legenda no estilo.legenda_y, quadro_s como veio)
        out = []
    _TRECHOS[chave] = out
    return out


def _origem_que_sobe(queixo: float, s: float, alvo: float) -> float:
    """Origem do zoom (y) que leva o queixo pra `alvo` com a escala s (origem abaixo do queixo: o zoom sobe o rosto)."""
    return (queixo * s - alvo) / (s - 1)


def folga_legenda(rosto_px: float, minima: bool = False) -> float:
    """Px entre o queixo e o topo da legenda pra um rosto de rosto_px de altura na tela (LEG_FOLGA; minima: LEG_FOLGA_MIN)."""
    return max(LEG_MARGEM, (LEG_FOLGA_MIN if minima else LEG_FOLGA) * rosto_px)


def enquadrar_pessoa(c: dict, rostos: list[dict], estilo: dict) -> None:
    """Cena de pessoa: zoom, origem do zoom e topo da legenda, com a legenda ABAIXO DO QUEIXO, no peito, como no exemplo-1
    (folga_legenda). Close: o zoom cresce em volta do queixo (ele não desce). Queixo baixo demais pra legenda caber até
    LEG_MAX_Y: a origem vai pra baixo do queixo e o zoom sobe o rosto (no aberto, entra um zoom leve; selfie de rosto grande
    sobe mais). Sem rosto achado: como antes."""
    plano = c.get("plano") if c.get("plano") in ZOOM else "aberto"
    s0, s1 = ZOOM[plano]
    fx, fy = (c.get("foco") or [.5, .4])[:2]
    oy = fy * H
    base = float(c.get("legenda_y") or estilo.get("legenda_y") or 1250)
    validos = [r["rosto"] for r in rostos if r.get("rosto")]
    c["zoom"], c["zoom_origem"], c["leg_y"], c["queixo_y"] = [s0, s1], [fx, round(oy)], round(base), None
    if not validos:
        return
    asp = validos[0]["aspecto"]
    alt = H if asp >= W / H else W / asp            # object-fit: cover no palco 1080x1920
    y0 = (H - alt) / 2
    queixo = max(y0 + min(1.0, r["y"] + QUEIXO_H * r["h"]) * alt for r in validos)
    rosto = max(r["h"] for r in validos) * alt      # altura do rosto no palco sem zoom
    alvo = lambda s: LEG_MAX_Y - folga_legenda(rosto * s)
    if plano == "close":
        oy = queixo if queixo <= alvo(s1) else min(H, _origem_que_sobe(queixo, s0, alvo(s1)))
    elif oy + (queixo - oy) * s1 > alvo(s1):
        for s in (1.12, 1.2, 1.28, 1.36, 1.44):
            o = _origem_que_sobe(queixo, s - .035, alvo(s))
            if o <= H:
                s0, s1, oy = s - .035, s, o
                break
        else:
            s0, s1, oy = 1.405, 1.44, H
    oy = min(max(oy, 0.0), float(H))
    q = max(oy + (queixo - oy) * s for s in (s0, s1))
    folga = folga_legenda(rosto * s1)
    leg = max(base, q + folga)
    if leg > LEG_MAX_Y:   # rosto baixo demais pra folga toda: a maior que couber (o checar reprova abaixo da mínima)
        leg = max(q + LEG_MARGEM, LEG_MAX_Y)
    c["zoom"], c["zoom_origem"] = [round(s0, 3), round(s1, 3)], [fx, round(oy)]
    c["queixo_y"], c["rosto_px"], c["leg_folga"] = round(q), round(rosto * s1), round(folga)
    c["leg_y"] = round(leg)


def escolher_quadro(src: Path, t: float, janela: float = .6, evitar: list[float] | tuple = ()) -> dict:
    """O melhor quadro do rosto perto de t (até ±janela): de frente, olhos achados, parado (sem borrão), longe dos quadros
    das outras cenas (`evitar`, a QUADRO_PERTO_S ou mais: cada imagem uma vez só). Devolve {t, rosto, olhos, mov}.
    O jornal do V2 do Cliente4 saiu com o olho fechado e a mão borrada (quadro 9)."""
    if src.suffix.lower() in IMAGEM:
        rs = rostos_no_trecho(src, 0, 0, 1)
        r = rs[0]["rosto"] if rs else None
        return {"t": None, "rosto": bool(r), "olhos": (r or {}).get("olhos", 0), "mov": 0.0}
    rs = rostos_no_trecho(src, max(0.0, t - janela - .2), 2 * janela + .4, 5)
    cands = [x for x in rs if max(0.0, t - janela) - .01 <= x["t"] <= t + janela + .01] or rs
    cands = [x for x in cands if all(abs(x["t"] - e) >= QUADRO_PERTO_S for e in evitar)] or \
        [x for x in cands if abs(x["t"] - t) < .11] or cands[:1]
    if not cands:
        return {"t": round(t, 2), "rosto": None, "olhos": None, "mov": None}   # não deu pra ler: não julga

    def nota(x):
        r = x["rosto"]
        if not r:
            return (-1, 0, 0)
        mov = x["mov"] if x["mov"] is not None else MOV_MAX / 2
        return (1, round(r["olhos"] - mov / 8, 2), -abs(x["t"] - t))   # olho achado e parado; no empate, o mais perto
    b = max(cands, key=nota)
    r = b["rosto"]
    return {"t": round(b["t"], 2), "rosto": bool(r), "olhos": (r or {}).get("olhos", 0),
            "mov": b["mov"] if b["mov"] is not None else None}


def ajustar_midia(plano: dict, doc: dict, pasta: Path) -> dict:
    """Olha o rosto no bruto: legenda e zoom de cada cena de pessoa (enquadrar_pessoa) e o quadro do jornal e do recorte
    (escolher_quadro, até 1,5 s do quadro_s no jornal e 0,6 s no recorte). Roda uma vez por plano; o --storyboard, o render e
    o --conferir usam."""
    if plano.get("ajustado"):
        return plano
    bruto = achar(doc.get("video"), pasta)
    est = plano.get("estilo") or {}
    quadros = {c["i"]: imagem_da_cena(c, doc, pasta) for c in plano["cenas"]}   # o quadro de cada cena, pra não repetir
    for c in plano["cenas"]:
        if c["tipo"] == "pessoa":
            f = achar(c.get("video"), pasta) if c.get("video") else bruto
            rs = rostos_no_trecho(f, c["de"], c["ate"] - c["de"], 2) if f and f.exists() else []
            enquadrar_pessoa(c, rs, est)
        elif c["tipo"] in ("jornal", "recorte"):
            f = achar(c.get("fonte"), pasta) if c.get("fonte") else bruto
            if f and f.exists() and f.suffix.lower() not in IMAGEM:
                t = float(c["quadro_s"]) if c.get("quadro_s") is not None else c["de"] + .4 * (c["ate"] - c["de"])
                evitar = [im[1] for k, im in quadros.items() if k != c["i"] and im and im[1] is not None
                          and im[0] == str(f.resolve())]
                q = escolher_quadro(f, t, 1.5 if c["tipo"] == "jornal" else .6, evitar)   # o jornal é retrato: procura mais
                c["rosto_q"] = q
                if q.get("t") is not None:
                    c["quadro_usado"] = q["t"]
                    quadros[c["i"]] = (str(f.resolve()), q["t"])
    plano["ajustado"] = True
    return plano


# ───────────── resolução do b-roll na tela (30-out-2026, João no Kodak: "muito borrada e pixelada") ─────────────
# O filme enche 1080 px de largura (com zoom de até 1,10) e a polaroid mostra a mídia numa janela de 772x620. Clipe de 640-712 px de
# largura (comercial de 1971 do YouTube) era esticado 1,6-1,9x pelo ffmpeg e saía em blocos. Agora o motor mede a ampliação e, acima de
# UPSCALE_MAX, trata a mídia antes de montar: FOTO e quadro de polaroid passam pelo Real-ESRGAN x4plus (app/ferramentas/midia_local.py);
# CLIPE de vídeo passa por denoise (hqdn3d) + Lanczos 2x + nitidez, em P&B suave. Testado no Kodak: o Real-ESRGAN de vídeo deixava o clipe
# de 1971 com cara de cartoon (sombras chapadas, rosto de massinha) e o x4plus leva ~9 s por quadro (200 quadros = 30 min); o filtro do
# ffmpeg tira o bloco e o ruído do h264 e mantém o grão de filme antigo, em ~1 s por quadro.
UPSCALE_MAX = 1.3        # px da moldura na tela ÷ px do arquivo (já com o zoom da cena): acima disso a mídia passa pelo upscale local
UPSCALE_FINAL_MAX = 1.25  # depois do upscale (2x no vídeo, 4x na foto) ainda acima disso = arquivo pequeno demais, a conferência reprova
ZOOM_FILME, ZOOM_POL = 1.10, 1.08


def moldura(c: dict) -> tuple[int, int]:
    """Tamanho em px da janela onde a mídia de fora aparece (filme: faixa de ponta a ponta; polaroid: a janela da foto)."""
    if c.get("tipo") == "filme":
        return 1080, int(c.get("altura") or 800) - 24
    return 772, 620


def _tam_midia(f: Path) -> tuple[int, int] | None:
    if f.suffix.lower() in IMAGEM:
        try:
            from PIL import Image
            with Image.open(f) as im:
                return im.size
        except Exception:
            return None
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(f)],
                       capture_output=True, text=True).stdout.strip().split(",")
    try:
        return int(r[0]), int(r[1])
    except (ValueError, IndexError):
        return None


def escala_na_tela(c: dict, f: Path, corte: tuple[float, float, float, float]) -> float | None:
    """Quantas vezes o arquivo (depois do corte) é esticado pra encher a moldura da cena, com o zoom. None = não deu pra medir."""
    t = _tam_midia(f)
    if not t:
        return None
    cw, ch = max(1.0, t[0] * corte[2]), max(1.0, t[1] * corte[3])
    mw, mh = moldura(c)
    return round(max(mw / cw, mh / ch) * (ZOOM_FILME if c.get("tipo") == "filme" else ZOOM_POL), 2)


def _ampliacao_local(c: dict) -> int:
    """Quanto o tratamento local multiplica o arquivo: 2 (clipe: denoise + Lanczos 2x) ou 4 (foto: Real-ESRGAN x4plus); 1 se a cena desliga (`"ampliar": false`)."""
    return 1 if c.get("ampliar") is False else (4 if c.get("imagem") or c["tipo"] == "polaroid" else 2)


def filtro_clipe_ampliado(w: float, h: float, largura_px: int) -> str:
    """Filtro do ffmpeg pro clipe de baixa resolução: corte -> P&B suave (gamma 1,3, contraste 0,95: o `hue=s=0 + contrast 1,12` chapava a sombra de
    filme colorido de 1971) -> denoise temporal/espacial -> Lanczos até `largura_px` (o dobro, no mínimo) -> nitidez."""
    return (f"format=gray,eq=gamma=1.3:contrast=0.95,hqdn3d=4:4:6:6,scale={largura_px}:-2:flags=lanczos,unsharp=7:7:0.9")


def avaliar_resolucao(c: dict, f: Path | None, corte: tuple) -> dict | None:
    """{esticado, depois_do_upscale, ampliada, upscale, tam} de uma mídia de fora: quanto ela é esticada na tela e quanto fica depois do
    Real-ESRGAN (2x no clipe, 4x na foto). Sem arquivo ou sem medir: None."""
    esc = escala_na_tela(c, f, corte) if f else None
    if not esc:
        return None
    amp = _ampliacao_local(c)
    ampliada = esc > UPSCALE_MAX and amp > 1
    return {"esticado": esc, "depois_do_upscale": round(esc / amp, 2) if esc > UPSCALE_MAX else esc, "ampliada": ampliada,
            "upscale": amp, "tam": _tam_midia(f)}


def _autocorte_seguro(f: Path | None, c: dict, pasta: Path) -> tuple[float, float, float, float]:
    """A caixa útil do filme (tira as barras pretas) pra medir a escala na checagem; sem arquivo ou sem ler, o quadro inteiro."""
    if not f or f.suffix.lower() in IMAGEM:
        return (0, 0, 1, 1)
    try:
        return _autocorte(f, float(c.get("inicio_s", 0)), c["ate"] - c["de"])
    except Exception:   # noqa: BLE001
        return (0, 0, 1, 1)


def preparar(plano: dict, doc: dict, pasta: Path, cache: Path) -> None:
    """Resolve a mídia de cada cena: quadros JPEG do bruto e do b-roll, stills, recortes do próprio bruto."""
    cache.mkdir(parents=True, exist_ok=True)
    bruto = achar(doc.get("video"), pasta)
    def fonte_de(c, chave="video"):
        f = achar(c.get(chave), pasta) if c.get(chave) else bruto
        if not f or not f.exists():
            raise SystemExit(f"cena {c['n']} ({c['tipo']}): mídia não encontrada: {c.get(chave) or doc.get('video')}")
        return f
    for c in plano["cenas"]:
        tipo, dur = c["tipo"], c["ate"] - c["de"]
        if tipo == "pessoa":
            f = fonte_de(c)
            if f.suffix.lower() in IMAGEM:
                c["midia"] = {"img": url(_still(f, None, cache / f"pessoa-{_hash(f)}.jpg", "scale='min(1440,iw)':-2"))}
            else:
                d = cache / f"pessoa-{_hash(f)}"
                k0 = int(round(c["de"] * FPS))
                n = _quadros(f, c["de"], dur, d, "scale='min(1080,iw)':-2", k0)
                c["midia"] = {"base": url(d) + "/", "fps": FPS, "n0": k0, "n1": k0 + max(0, n - 1), "t0": 0, "k0": 0}
        elif tipo == "filme":
            f = fonte_de(c, "video" if c.get("video") else "imagem")
            pb = "hue=s=0,eq=contrast=1.12:brightness=-0.02"
            if f.suffix.lower() in IMAGEM:
                esc = escala_na_tela(c, f, (0, 0, 1, 1))
                if esc and esc > UPSCALE_MAX and _ampliacao_local(c) > 1:   # foto pequena pra faixa de 1080 px: Real-ESRGAN (x4plus)
                    try:
                        sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
                        import midia_local as ml
                        up = cache / f"filme-x4-{_hash(f)}.jpg"
                        if not up.exists():
                            ml.upscale(f, up, int(1080 * ZOOM_FILME * 1.6))
                        c["midia"], c["ampliada"] = {"img": url(_still(up, None, cache / f"filme-{_hash(up)}.jpg", f"scale='min(1900,iw)':-2,{pb}"))}, True
                        continue
                    except Exception as e:   # noqa: BLE001
                        plano.setdefault("avisos", []).append(f"cena {c['n']}: upscale local falhou ({str(e)[:90]}); segue com a foto esticada")
                c["midia"] = {"img": url(_still(f, None, cache / f"filme-{_hash(f)}.jpg", f"scale='min(1280,iw)':-2,{pb}"))}
            else:
                ss = float(c.get("inicio_s", 0))
                x, y, w, h = c.get("corte") or _autocorte(f, ss, dur)
                filtro = f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},scale=1100:-2,{pb}"
                d = cache / f"filme-{_hash(f, ss, dur, x, y, w, h)}"
                esc = escala_na_tela(c, f, (x, y, w, h))
                if esc and esc > UPSCALE_MAX and _ampliacao_local(c) > 1:   # clipe pequeno demais pra tela: denoise + Lanczos 2x + nitidez
                    tam = _tam_midia(f) or (712, 480)
                    filtro = f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f}," + filtro_clipe_ampliado(tam[0] * w, tam[1] * h, int(max(1100, tam[0] * w * 2) // 2 * 2))
                    d = cache / f"filme-r-{_hash(f, ss, dur, x, y, w, h)}"
                    c["ampliada"] = True
                n = _quadros(f, ss, dur, d, filtro, 0)
                c["midia"] = {"base": url(d) + "/", "fps": FPS, "n0": 0, "n1": max(0, n - 1), "t0": c["de"], "k0": 0}
        elif tipo == "polaroid":
            chave = "imagem" if c.get("imagem") else "video"
            f = fonte_de(c, chave)
            t = float(c.get("quadro_s", 1.0 if c.get(chave) else (c["de"] + c["ate"]) / 2))
            x, y, w, h = c.get("corte") or (0, 0, 1, 1)   # corte [x, y, w, h] em frações: tira logo/tarja do canto
            filtro = f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},scale='min(1100,iw)':-2"
            esc = escala_na_tela(c, f, (x, y, w, h))
            if esc and esc > UPSCALE_MAX and _ampliacao_local(c) > 1:   # foto/quadro pequeno pra janela da polaroid: Real-ESRGAN (x4plus, 1 quadro só)
                nat = _still(f, t, cache / f"pol-nat-{_hash(f, t, x, y, w, h)}.png", f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f}")
                try:
                    sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
                    import midia_local as ml
                    up = cache / f"pol-x4-{_hash(f, t, x, y, w, h)}.jpg"
                    if not up.exists():
                        ml.upscale(nat, up, int(772 * ZOOM_POL * 1.6))
                    c["midia"] = {"img": url(up)}
                    c["ampliada"] = True
                    continue
                except Exception as e:   # noqa: BLE001
                    plano.setdefault("avisos", []).append(f"cena {c['n']}: upscale local falhou ({str(e)[:90]}); segue com a foto esticada")
            c["midia"] = {"img": url(_still(f, t, cache / f"pol-{_hash(f, t, x, y, w, h)}.jpg", filtro))}
        elif tipo in ("recorte", "jornal") or (tipo == "relogio" and (c.get("recorte") or c.get("quadro_s") is not None)):
            f = fonte_de(c, "fonte")
            t = None if f.suffix.lower() in IMAGEM else float(c.get("quadro_usado", c.get("quadro_s", c["de"] + .4 * dur)))
            c["midia"] = {"recorte": url(recortar(f, t, cache))}


# ───────────────────────────── navegador ─────────────────────────────

class _Servidor(http.server.SimpleHTTPRequestHandler):
    """/ = pasta do motor (index.html, fontes/); /f/<caminho absoluto> = mídia (só dentro das pastas liberadas)."""
    raizes: tuple[Path, ...] = ()

    def translate_path(self, path):
        p = urllib.parse.unquote(path.split("?")[0].split("#")[0])
        if p.startswith("/f/"):
            alvo = Path(p[2:]).resolve()
            if any(alvo == r or r in alvo.parents for r in self.raizes):
                return str(alvo)
            return str(AQUI / "__negado__")
        return super().translate_path(path)

    def log_message(self, *a):
        pass


def url(p: Path) -> str:
    return "/f" + urllib.parse.quote(str(Path(p).resolve()))


class _Http(http.server.ThreadingHTTPServer):
    # vários navegadores pedindo quadros ao mesmo tempo: com a fila padrão (5) a conexão era recusada
    # (net::ERR_SOCKET_NOT_CONNECTED) e o processo do trecho morria
    request_queue_size = 512
    daemon_threads = True


def servir(*raizes: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    _Servidor.raizes = tuple(Path(r).resolve() for r in raizes)
    h = functools.partial(_Servidor, directory=str(AQUI))
    srv = _Http(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _pagina(plano: dict) -> dict:
    return {k: plano[k] for k in ("total", "cenas", "cores", "estilo")}


def abrir(p, porta: int, plano: dict):
    nav = p.chromium.launch()
    pg = nav.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pg.add_init_script("window.PLANO = " + json.dumps(_pagina(plano), ensure_ascii=False) + ";")
    pg.goto(f"http://127.0.0.1:{porta}/index.html")
    try:
        pg.wait_for_function("window.seek && window.pronto", timeout=60000)
        pg.evaluate("window.pronto")
    except Exception:
        raise SystemExit("o motor não carregou: " + " | ".join(erros[:3]))
    if erros:
        raise SystemExit("erro no motor: " + erros[0])
    return nav, pg


def _trecho(porta: int, plano_json: str, f0: int, f1: int, fps: int, saida: str, codec: list[str]) -> str:
    """Um processo: abre o motor e grava os quadros [f0, f1) num mp4 parcial."""
    from playwright.sync_api import sync_playwright
    plano = json.loads(plano_json)
    with sync_playwright() as p:
        try:
            nav, pg = abrir(p, porta, plano)
        except SystemExit as e:   # SystemExit num processo filho mata o processo sem avisar o pai
            raise RuntimeError(str(e)) from None
        ff = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg",
                               "-i", "-", *codec, "-pix_fmt", "yuv420p", "-r", str(fps), saida], stdin=subprocess.PIPE)
        for f in range(f0, f1):
            pg.evaluate("t => seek(t)", f / fps)
            ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
        ff.stdin.close()
        ff.wait()
        nav.close()
    return saida


def _codec() -> list[str]:
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "h264_videotoolbox" in enc:
        return ["-c:v", "h264_videotoolbox", "-b:v", "14M", "-maxrate", "18M", "-bufsize", "28M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]


def _fonte(tam: int, estilo: str = "Bold"):
    from PIL import ImageFont
    for f in (AQUI / "fontes" / f"Tinos-{estilo}.ttf", Path(f"/System/Library/Fonts/Supplemental/Times New Roman {estilo}.ttf"),
              Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"), Path("/System/Library/Fonts/Supplemental/Arial.ttf")):
        if f.exists():
            return ImageFont.truetype(str(f), tam)
    return ImageFont.load_default()


def br(x: float, casas: int = 1) -> str:
    """Número no jeito do Brasil: 2,5 (vírgula)."""
    return f"{x:.{casas}f}".replace(".", ",")


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}".replace(".", ",")


def _musica_txt(doc: dict, plano: dict | None = None) -> str:
    """Rodapé do storyboard: cada faixa com de e até (o que o render toca) e o número real de efeitos."""
    if not doc.get("musica"):
        return "Sem música" + _efeitos_txt(doc, plano)
    total = (plano or {}).get("total") or 0
    segs = segmentos_musica(doc, total) if total else [dict(s) for s in (doc["musica"] if isinstance(doc["musica"], list) else [doc["musica"]])]
    return "Música (Mixkit): " + _trechos_txt(segs) + _efeitos_txt(doc, plano)


def _efeitos_txt(doc: dict, plano: dict | None = None) -> str:
    liga = sons_ligados(doc.get("efeitos", True))
    if not liga:
        return " · sem efeitos"
    if plano is not None:   # o número real, que o João ouve (o V2 dizia "5 sons" e tocava 108)
        ev = plano.get("eventos") or []
        por = [f"{ROTULO[s]} {sum(1 for e in ev if e['som'] == s)}" for s in SONS if any(e["som"] == s for e in ev)]
        return f" · efeitos: {len(ev)} em {mmss(plano.get('total') or 0)}" + (f" ({', '.join(por)})" if por else "")
    if liga == set(SONS):
        return " · efeitos suaves ligados"
    return " · efeitos: " + ", ".join(ROTULO[s] for s in SONS if s in liga)


def instante_storyboard(c: dict) -> float:
    """Quando tirar o quadro da cena: no fim (0,12 s antes da troca; nunca antes de 70%), e depois que a última palavra
    terminou de digitar (ela acaba até 0,02 s antes da troca). Antes saía a 70% e o João via "D▌" e "BARG▌" no lugar da
    palavra-chave; com 0,12 s ainda sobrava "PLANO DE CARREI▌"."""
    t = max(c["de"] + .7 * (c["ate"] - c["de"]), c["ate"] - .12)
    toks = c.get("tokens") or []
    if toks:
        t = max(t, min(max(tk["e"] for tk in toks) + .01, c["ate"] - .02))
    return round(t, 3)


def _quebrar(txt: str, fonte, largura: int, draw) -> list[str]:
    linhas, cur = [], ""
    for w in txt.split():
        if cur and draw.textlength(cur + " " + w, font=fonte) > largura:
            linhas.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return linhas + [cur] if cur else linhas


def storyboard(pg, plano: dict, doc: dict, out: Path, falta: list[str] | tuple = ()) -> Path:
    """Um quadro por cena, 360x640 + faixa clara de 170 px, 4 colunas: 'N. Tipo · 0:12,3' e a fala. O quadro sai no fim da
    cena (instante_storyboard): a frase já foi digitada inteira e a construção já montou (lista com os X, bifurcação com
    os rótulos). Rodapé: a música e os efeitos e, em vermelho, o que a checagem ainda reprova ("Falta: ...").
    Nas cenas de pessoa mede o rosto no quadro pronto: legenda colada na barba entra na lista `falta` (a do chamador)."""
    from io import BytesIO
    from PIL import Image, ImageDraw
    cw, ch, faixa, cols = 360, 640, 170, 4
    f1, f2 = _fonte(26), _fonte(23, "Regular")
    cel, coladas = [], []
    for c in plano["cenas"]:
        pg.evaluate("t => seek(t)", instante_storyboard(c))
        im = Image.open(BytesIO(pg.screenshot(type="png"))).convert("RGB")
        if c["tipo"] == "pessoa" and (c.get("blocos") or c.get("tokens")) and not (plano.get("estilo") or {}).get("sem_legenda"):
            try:
                import numpy as np
                q = legenda_colada(c, plano, np.asarray(im.convert("L").resize((720, 1280))))
            except ImportError:   # sem OpenCV: fica só a conferência do plano
                q = None
            if q is not None:
                coladas.append(motivo_legenda(c, q, "No storyboard"))
        im = im.resize((cw, ch), Image.LANCZOS)
        cx = Image.new("RGB", (cw, ch + faixa), (250, 247, 242))
        cx.paste(im, (0, 0))
        d = ImageDraw.Draw(cx)
        d.text((12, ch + 10), f"{c['n']}. {NOME[c['tipo']]} · {mmss(c['de'])}", font=f1, fill=(30, 30, 30))
        linhas = _quebrar("“" + (c.get("fala") or "(respiro)") + "”", f2, cw - 24, d)
        for k, l in enumerate(linhas[:4]):
            d.text((12, ch + 48 + k * 28), l, font=f2, fill=(70, 60, 60))
        cel.append(cx)
    if isinstance(falta, list):
        falta.extend(coladas)
    else:
        falta = list(falta) + coladas
    n_l = -(-len(cel) // cols)
    larg, fr = cols * (cw + 12) + 12, _fonte(28)
    med = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    # rodapé (música e efeitos) quebra em linhas: antes passava da borda e cortava "efeitos suaves lig"
    rodape = [(l, (240, 236, 228)) for l in _quebrar(_musica_txt(doc, plano), fr, larg - 32, med)]
    for m in list(falta)[:4]:
        rodape += [(l, (255, 120, 110)) for l in _quebrar("Falta: " + m, fr, larg - 32, med)]
    if len(falta) > 4:
        rodape.append((f"... e mais {len(falta) - 4} (qa/checagem.json)", (255, 120, 110)))
    rod = 34 + 38 * len(rodape)
    folha = Image.new("RGB", (larg, n_l * (ch + faixa + 12) + 12 + rod), (40, 36, 44))
    for i, cx in enumerate(cel):
        folha.paste(cx, (12 + (i % cols) * (cw + 12), 12 + (i // cols) * (ch + faixa + 12)))
    for k, (l, cor) in enumerate(rodape):
        ImageDraw.Draw(folha).text((16, folha.height - rod + 18 + 38 * k), l, font=fr, fill=cor)
    dst = out / "storyboard.jpg"
    folha.save(dst, quality=88)
    return dst


# ───────────────────────────── áudio ─────────────────────────────

def ler_audio(p: Path, ss: float = 0, dur: float | None = None, filtro: str | None = None):
    import numpy as np
    cmd = ["ffmpeg", "-nostdin", "-v", "error"]
    if ss:
        cmd += ["-ss", f"{ss:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", str(p), "-vn", "-ac", "1", "-ar", str(SR)]
    if filtro:
        cmd += ["-af", filtro]
    r = subprocess.run(cmd + ["-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(r, "<f4").copy()


def gravar_wav(p: Path, x) -> None:
    import numpy as np
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def lufs(p: Path) -> float:
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(p), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.findall(r"I:\s*(-?[\d.]+) LUFS", r)
    return float(m[-1]) if m else -70.0


def db(x) -> float:
    import numpy as np
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-9)) if len(x) else -120.0


def segmentos_musica(doc: dict, dur: float) -> list[dict]:
    m = doc.get("musica")
    if not m:
        return []
    segs = sorted((dict(s) for s in (m if isinstance(m, list) else [m])), key=lambda s: float(s.get("de", 0)))
    segs[0]["de"] = 0
    segs = [s for s in segs if float(s["de"]) < dur] or segs[:1]   # --ate curto: a 2ª faixa nem começa
    for k, s in enumerate(segs):
        s["ate"] = float(segs[k + 1]["de"]) if k + 1 < len(segs) else dur
    return segs


def montar_audio(doc: dict, plano: dict, pasta: Path, dur: float, saida: Path, qa: Path) -> dict:
    """Voz (do bruto ou do arquivo de voz) + música do cenas.json com ducking + efeitos suaves → -14 LUFS (2 passadas).
    Grava também a trilha sem voz (música + efeitos, no volume final) em qa/trilha-sem-voz.wav, pra conferência."""
    import numpy as np
    n = int(round(dur * SR))
    tmp = qa / "_audio"
    tmp.mkdir(parents=True, exist_ok=True)
    fv = achar(doc.get("voz") or doc.get("video"), pasta)
    voz = np.zeros(n, np.float32)
    if fv and fv.exists() and fv.suffix.lower() not in IMAGEM:
        v = ler_audio(fv, 0, dur)[:n]
        voz[:len(v)] = v
    gravar_wav(tmp / "voz.wav", voz)
    lv = lufs(tmp / "voz.wav")
    if lv > -60:   # voz em -16 LUFS: o ducking reage igual em qualquer bruto
        # pico no máximo 11 dB acima do volume (limitador com lookahead, latência compensada): sem isso a voz de pico alto
        # estourava, o mix inteiro baixava e o loudnorm caía no modo dinâmico (-15 LUFS e música abafada nas pausas)
        voz *= 10 ** ((-16 - lv) / 20)
        pk = max(1.0, float(np.abs(voz).max()) / .98)   # o WAV de 16 bits não passa de 1: grava baixo e o ffmpeg devolve o ganho
        gravar_wav(tmp / "voz-bruta.wav", voz / pk)
        _ff("-i", tmp / "voz-bruta.wav", "-af", f"volume={pk:.4f},alimiter=limit={10 ** (-5 / 20):.4f}:attack=3:release=60:level=0:latency=1",
            "-ar", SR, "-ac", 1, tmp / "voz.wav")
        voz = ler_audio(tmp / "voz.wav")[:n]
        voz = np.pad(voz, (0, n - len(voz)))
    # música: um trecho por segmento, crossfade de 1,2 s, mesmo volume percebido em todos
    mus = np.zeros(n, np.float32)
    info_m = []
    alvo = 10 ** ((MUSICA_ALVO_DB + float(doc.get("musica_db", 0))) / 20)
    xf = int(1.2 * SR)
    segs = segmentos_musica(doc, dur)
    for k, s in enumerate(segs):
        arq = achar(s.get("arquivo"), pasta)
        if not arq or not arq.exists():
            raise SystemExit(f"música não encontrada: {s.get('arquivo')}")
        a, b = int(s["de"] * SR), int(s["ate"] * SR)
        a0, b0 = max(0, a - (xf // 2 if k else 0)), min(n, b + (xf // 2 if k < len(segs) - 1 else 0))
        x = ler_audio(arq, float(s.get("inicio_s", 0)))
        while len(x) < b0 - a0:
            x = np.concatenate([x, ler_audio(arq)])
        x = x[: b0 - a0].copy()
        x *= alvo / (np.sqrt(np.mean(np.square(x))) + 1e-9)
        if k:
            x[:xf] *= np.linspace(0, 1, min(xf, len(x)))[:len(x[:xf])]
        if k < len(segs) - 1:
            x[-xf:] *= np.linspace(1, 0, min(xf, len(x)))[-len(x[-xf:]):]
        mus[a0:a0 + len(x)] += x
        info_m.append({"arquivo": str(s.get("arquivo")), "inicio_s": float(s.get("inicio_s", 0)), "de": s["de"], "ate": s["ate"]})
    if segs:
        t = np.arange(n) / SR
        mus *= np.clip(t / .6, 0, 1) * np.clip((dur - t) / 1.5, 0, 1)
        gravar_wav(tmp / "musica.wav", mus)
        # ducking por sidechain (G9: threshold .15, ratio 2,5); a voz entra +9,5 dB no detector pra baixar ~8 dB sob a fala
        _ff("-i", tmp / "musica.wav", "-i", tmp / "voz.wav", "-filter_complex",
            "[1:a]volume=3[sc];[0:a][sc]sidechaincompress=threshold=0.15:ratio=2.5:attack=20:release=400[m]",
            "-map", "[m]", "-ar", SR, "-ac", 1, tmp / "musica-duck.wav")
        mus = ler_audio(tmp / "musica-duck.wav")[:n]
        mus = np.pad(mus, (0, n - len(mus)))
    # efeitos
    fx = np.zeros(n, np.float32)
    cache_sfx = {}
    for e in plano["eventos"]:
        arq, vol = SONS[e["som"]]
        if arq not in cache_sfx:
            x = ler_audio(arquivo_sfx(arq), filtro="highpass=f=200,highpass=f=200")
            cache_sfx[arq] = x / (np.abs(x).max() + 1e-9) * .9
        x = cache_sfx[arq]
        if e.get("dur"):
            m = int(e["dur"] * SR)
            x = x[:m].copy()
            f = min(len(x), int(.06 * SR))
            if f:
                x[-f:] *= np.linspace(1, 0, f)
        if e["som"] == "tique":
            x = x[:int(.12 * SR)]
        i = int(e["t"] * SR)
        if 0 <= i < n:
            fx[i:i + len(x)] += (x * vol)[: n - i]
    # loudnorm -14 LUFS em duas passadas (pico -1,5 dBTP), sempre LINEAR (ganho fixo, não mexe na dinâmica nem no ducking):
    # o modo linear exige LRA alvo >= LRA medido e pico + ganho <= -1,5 dBTP; se o pico não couber, um limitador antes.
    def medir(arq: Path) -> dict:
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(arq), "-af",
                            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
        return json.loads(r[r.rindex("{"):r.rindex("}") + 1])

    def mixar() -> tuple[float, dict]:
        mix = voz + mus + fx
        pk = max(1.0, float(np.abs(mix).max()) / .98)
        gravar_wav(tmp / "mix.wav", mix / pk)
        return pk, medir(tmp / "mix.wav")
    pico, m1 = mixar()
    # música medida, não no ouvido (G9): nas pausas da fala ela fica em MUSICA_ALVO_DB no volume final (o ducking não depende
    # do volume da música, então corrigir depois dele é exato). Ajusta até 8 dB pra cima ou pra baixo.
    jan = pausas(plano["palavras"], dur)
    if segs and jan:
        q = int(.1 * SR)
        ganho_prev = -14 - float(m1["input_i"]) - 20 * np.log10(pico)
        niv = [db(mus[int(t * SR):int(t * SR) + q]) for a, b in jan for t in np.arange(a, b - .1, .1)]
        if niv:
            corr = float(np.clip(MUSICA_ALVO_DB + float(doc.get("musica_db", 0)) - (float(np.median(niv)) + ganho_prev), -8, 8))
            if abs(corr) > .5:
                mus *= 10 ** (corr / 20)
                pico, m1 = mixar()
    mix_arq = tmp / "mix.wav"
    sobra = float(m1["input_tp"]) + (-14 - float(m1["input_i"])) - (-2.0)
    if sobra > 0:
        lim = 10 ** ((float(m1["input_tp"]) - sobra - .3) / 20)
        _ff("-i", mix_arq, "-af", f"alimiter=limit={max(.0625, min(1, lim)):.4f}:attack=2:release=80:level=0:latency=1",
            "-ar", SR, "-ac", 1, tmp / "mix-lim.wav")
        mix_arq = tmp / "mix-lim.wav"
        m1 = medir(mix_arq)
    lra = min(50, max(11, float(m1["input_lra"]) + 1))
    af = (f"loudnorm=I=-14:TP=-1.5:LRA={lra:.1f}:measured_I={m1['input_i']}:measured_TP={m1['input_tp']}:measured_LRA={m1['input_lra']}:"
          f"measured_thresh={m1['input_thresh']}:offset={m1['target_offset']}:linear=true:print_format=json")
    r2 = subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-i", str(mix_arq), "-af", af, "-ar", str(SR), str(saida)],
                        capture_output=True, text=True).stderr
    m2 = json.loads(r2[r2.rindex("{"):r2.rindex("}") + 1])
    ganho = float(m2["output_i"]) - float(m2["input_i"])
    gravar_wav(qa / "trilha-sem-voz.wav", (mus + fx) / pico * 10 ** (ganho / 20))
    shutil.rmtree(tmp, ignore_errors=True)
    info = {"musica": info_m, "efeitos": len(plano["eventos"]), "ganho_final_db": round(ganho, 2), "lufs_final": float(m2["output_i"]),
            "normalizacao": m2.get("normalization_type")}
    (qa / "audio.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    (qa / "eventos.json").write_text(json.dumps(plano["eventos"], ensure_ascii=False, indent=0), encoding="utf-8")
    return info


def previa_som(doc: dict, plano: dict, pasta: Path, out: Path) -> Path:
    """O som do vídeo antes do render (voz + música com ducking + efeitos, a mesma mixagem do vídeo): previa-som.m4a ao
    lado do storyboard. Dá pra ouvir a música e os efeitos antes de aprovar, e o volume nas pausas já é medido."""
    qa = out / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    wav = out / "_previa-som.wav"
    m4a = out / "previa-som.m4a"
    try:
        montar_audio(doc, plano, pasta, plano["total"], wav, qa)
        _ff("-i", wav, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", m4a)
    finally:
        wav.unlink(missing_ok=True)
    return m4a


# ───────────────────────────── conferência ─────────────────────────────

_CAT: dict | None = None


def _catalogo() -> dict:
    global _CAT
    if _CAT is None:
        p = AQUI / "audio" / "catalogo.json"
        _CAT = {m["id"]: m for m in json.loads(p.read_text(encoding="utf-8")).get("musicas", [])} if p.exists() else {}
    return _CAT


def _bandas(x) -> dict:
    import numpy as np
    if len(x) < 4096:
        return {}
    seg = x[: SR * 30]
    esp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    fr = np.fft.rfftfreq(len(seg), 1 / SR)
    tot = esp.sum() + 1e-12
    return {"grave": round(float(esp[fr < 250].sum() / tot), 2), "medio": round(float(esp[(fr >= 250) & (fr < 4000)].sum() / tot), 2),
            "agudo": round(float(esp[fr >= 4000].sum() / tot), 2)}


def pausas(ws: list[dict], total: float, minimo: float = .5) -> list[tuple[float, float]]:
    """Janelas sem fala (≥ 0,5 s), pulando os 0,25 s em que a música ainda volta do ducking."""
    out, ini = [], 0.0
    for w in ws + [{"s": total, "e": total}]:
        if w["s"] - ini >= minimo:
            out.append((ini + .25, w["s"] - .05))
        ini = max(ini, w["e"])
    return [(a, b) for a, b in out if b - a > .15]


def _parada_max(video: Path) -> float:
    """Maior trecho em que a imagem não muda nada (amostra a 5 quadros/s)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vf", "fps=5,scale=108:192,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    q = np.frombuffer(raw, np.uint8)
    q = q[: len(q) // (108 * 192) * 108 * 192].reshape(-1, 192, 108).astype(np.int16)
    if len(q) < 2:
        return 0.0
    mudou = np.abs(np.diff(q, axis=0)).max(axis=(1, 2)) > 3
    maior = cur = 0
    for m in mudou:
        cur = 0 if m else cur + 1
        maior = max(maior, cur)
    return round(maior / 5, 2)


def _folha(video: Path, destino: Path) -> Path | None:
    if not video or not video.exists():
        return None
    _ff("-i", video, "-vf", "fps=1/4,scale=200:-1,tile=10x3", "-frames:v", 1, destino)
    return destino


def folha_comparacao(video: Path, qa: Path) -> Path:
    """Exemplo-1 em cima, este vídeo embaixo: um quadro a cada 4 s (fps=1/4, scale=200:-1, tile=10x3)."""
    from PIL import Image, ImageDraw
    partes = []
    for rot, v in (("EXEMPLO (Correria · Cliente3)", EXEMPLO), ("ESTE VÍDEO", video)):
        f = _folha(v, qa / f"_folha-{len(partes)}.jpg")
        if f:
            partes.append((rot, Image.open(f).convert("RGB")))
            f.unlink()
    larg = max(im.width for _, im in partes)
    alt = sum(im.height + 60 for _, im in partes)
    folha = Image.new("RGB", (larg, alt), (24, 22, 26))
    y = 0
    for rot, im in partes:
        ImageDraw.Draw(folha).text((14, y + 14), rot, font=_fonte(34), fill=(245, 240, 230))
        folha.paste(im, (0, y + 60))
        y += im.height + 60
    dst = qa / "folha-comparacao.jpg"
    folha.save(dst, quality=86)
    return dst


def folha_broll(video: Path, destino: Path, marcado: float | None = None, n: int = 12) -> Path:
    """Folha de um b-roll: n quadros espalhados pelo clipe, cada um com o segundo dele (o quadro_s da polaroid, o inicio_s
    do filme). É por ela que se escolhe o quadro: o que a fala diz (gente quando ela fala de gente) e sem marca d'água ou
    logo de canal (sobrou no canto: tire com "corte"). A polaroid da fábrica do V2 refeito do Cliente4 saiu só com a máquina
    e o "British Pathé" no canto porque o quadro foi escolhido às cegas (quadro_s 3)."""
    from io import BytesIO
    from PIL import Image, ImageDraw
    dur = duracao_midia(video) if video.suffix.lower() not in IMAGEM else 0
    tempos = [round(dur * (k + .5) / n, 1) for k in range(n)] if dur > .5 else [0.0]
    if marcado is not None and dur and all(abs(t - marcado) > .3 for t in tempos):
        tempos = sorted(tempos + [round(float(marcado), 1)])
    cw, cols = 320, 4
    cel = []
    for t in tempos:
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", *(["-ss", f"{t:.2f}"] if dur else []), "-i", str(video),
                            "-frames:v", "1", "-vf", f"scale={cw}:-2", "-f", "image2", "-c:v", "mjpeg", "-"], capture_output=True)
        if not r.stdout:
            continue
        im = Image.open(BytesIO(r.stdout)).convert("RGB")
        d = ImageDraw.Draw(im)
        alvo = marcado is not None and abs(t - marcado) <= .3
        rot = f"{br(t)} s" + (" · usado" if alvo else "")
        d.rectangle((0, 0, 24 + int(d.textlength(rot, font=_fonte(26))), 40), fill=(212, 175, 55) if alvo else (0, 0, 0))
        d.text((10, 6), rot, font=_fonte(26), fill=(0, 0, 0) if alvo else (255, 255, 255))
        cel.append(im)
    if not cel:
        raise SystemExit(f"não deu pra ler quadros de {video}")
    ch = max(im.height for im in cel)
    folha = Image.new("RGB", (cols * (cw + 8) + 8, -(-len(cel) // cols) * (ch + 8) + 8), (40, 36, 44))
    for i, im in enumerate(cel):
        folha.paste(im, (8 + (i % cols) * (cw + 8), 8 + (i // cols) * (ch + 8)))
    destino.parent.mkdir(parents=True, exist_ok=True)
    folha.save(destino, quality=86)
    return destino


def folha_rostos(video: Path, destino: Path, passo: float = .5) -> Path:
    """Folha dos rostos do bruto: o rosto a cada `passo` s, com o segundo. Em vermelho: sem rosto de frente ou olho não
    achado (fechado ou tapado). É por ela que se escolhe o quadro_s do jornal e do recorte, olhando: olho aberto, sem
    borrão, sem a mão no rosto. O detector de olho erra às vezes: quem decide é o olho de quem monta."""
    import cv2
    from PIL import Image, ImageDraw
    dur = duracao_midia(video) if video.suffix.lower() not in IMAGEM else 0
    rs = rostos_no_trecho(video, 0, max(.1, dur), 1 / passo)
    quadros = dict(_quadros_cinza(video, 0, max(.1, dur), 1 / passo))
    cel, cw = [], 150
    for x in rs:
        g = quadros.get(x["t"])
        if g is None:
            continue
        h_, w_ = g.shape[:2]
        r = x["rosto"]
        if r:
            x0, y0, ww, hh = int(r["x"] * w_), int(r["y"] * h_), int(r["w"] * w_), int(r["h"] * h_)
            m = int(.25 * ww)
            crop = g[max(0, y0 - m): min(h_, y0 + hh + m), max(0, x0 - m): min(w_, x0 + ww + m)]
        else:
            crop = g
        im = Image.fromarray(cv2.resize(crop, (cw, round(cw * 1.2)))).convert("RGB")
        ruim = "sem rosto" if not r else "olho?" if not r["olhos"] else ""
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, cw, 26), fill=(190, 30, 30) if ruim else (0, 0, 0))
        d.text((6, 3), f"{br(x['t'])} s {ruim}".strip(), font=_fonte(20), fill=(255, 255, 255))
        cel.append(im)
    if not cel:
        raise SystemExit(f"não deu pra ler rostos de {video}")
    cols = 12
    ch = cel[0].height
    folha = Image.new("RGB", (cols * (cw + 4) + 4, -(-len(cel) // cols) * (ch + 4) + 4), (40, 36, 44))
    for i, im in enumerate(cel):
        folha.paste(im, (4 + (i % cols) * (cw + 4), 4 + (i // cols) * (ch + 4)))
    destino.parent.mkdir(parents=True, exist_ok=True)
    folha.save(destino, quality=86)
    return destino


def folhas_de_fora(plano: dict, doc: dict, pasta: Path, out: Path) -> list[Path]:
    """No --storyboard: uma folha por b-roll de vídeo das polaroids e filmes (qa/folha-<arquivo>.jpg), com o quadro usado
    marcado em dourado. Nunca levanta erro."""
    feitas, vistos = [], set()
    for c in plano["cenas"]:
        if not midia_de_fora(c, doc, pasta):
            continue
        f = achar(c.get("video"), pasta) if c.get("video") else None
        if not f or not f.exists() or f in vistos:
            continue
        vistos.add(f)
        t = c.get("quadro_s", 1.0) if c["tipo"] == "polaroid" else c.get("inicio_s", 0)
        try:
            feitas.append(folha_broll(f, out / "qa" / f"folha-{f.stem}.jpg", float(t)))
        except (Exception, SystemExit) as e:   # noqa: BLE001
            print(f"aviso: folha de {f.name} não saiu ({e})", file=sys.stderr)
    return feitas


def escolha_da_tela(pasta: Path) -> dict:
    """O que o João escolheu na tela, lido do PLANO.json ao lado do cenas.json (a tela grava nele):
    musica.sem = sem música; sfx_ligado = false (ou todo som desmarcado) = sem efeitos. Sem PLANO (ou sem a escolha)
    vale o padrão: os dois."""
    p = _plano_tela(pasta)
    m = p.get("musica")
    sem = m == "sem" or (isinstance(m, dict) and (bool(m.get("sem")) or m.get("escolha") in ("sem", {"sem": True})))
    itens = [o for o in p.get("sfx") or [] if isinstance(o, dict)] if isinstance(p.get("sfx"), list) else []
    nenhum = bool(itens) and all(o.get("ligado", True) is False for o in itens)
    w = pasta / "work"   # a escolha do Novo vídeo (arquivos marcadores) vale como a da tela
    return {"sem_musica": sem or (w / "musica" / "sem").is_file(), "sem_efeitos": p.get("sfx_ligado") is False or nenhum or (w / "efeitos" / "sem").is_file()}


def _plano_tela(pasta: Path) -> dict:
    try:
        p = json.loads((pasta / "PLANO.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        p = {}
    return p if isinstance(p, dict) else {}


def sons_desligados_na_tela(pasta: Path) -> set[str]:
    """Sons que o João desmarcou um por um na tela (sfx do PLANO.json, um por tipo de som). Som que ainda tem
    algum item ligado não conta como desligado."""
    p = _plano_tela(pasta)
    liga, desl = set(), set()
    for o in p.get("sfx") if isinstance(p.get("sfx"), list) else []:
        if isinstance(o, dict):
            s = som_do_motor(o.get("som") or o.get("id"))
            if s:
                (desl if o.get("ligado", True) is False else liga).add(s)
    return desl - liga


HORA_PAL = {"hora", "horas", "madrugada", "meianoite", "meiodia", "manha", "noite", "tarde", "relogio", "minuto", "minutos",
            "amanhecer", "anoitecer", "expediente"}


def hora_na_fala(txt: str) -> bool:
    """A fala diz uma hora ou um momento do dia ('onze da noite', '23h', 'de madrugada', 'até tarde')? Relógio só assim:
    em 'o tempo inteiro' o relógio do Vídeo 1 V2 do Cliente4 inventou 08:00 → 18:00."""
    return any(norm(w) in HORA_PAL or re.search(r"\d", w) for w in str(txt or "").split())


def midia_de_fora(c: dict, doc: dict, pasta: Path) -> bool:
    """Polaroid ou filme com imagem/vídeo que não é o bruto da pessoa (b-roll, cena de filme, foto)."""
    if c.get("tipo") not in ("polaroid", "filme"):
        return False
    m = c.get("imagem") or c.get("video")
    if not m:
        return False
    a, b = achar(m, pasta), achar(doc.get("video"), pasta)
    return not (a and b and a.resolve() == b.resolve())


def mostra_pessoa(c: dict, doc: dict, pasta: Path) -> bool:
    """A cena mostra a própria pessoa: falando, recorte, jornal, relógio com a silhueta, polaroid/filme do bruto."""
    t = c.get("tipo")
    if t in ("pessoa", "recorte", "jornal"):
        return True
    if t == "relogio":
        return bool(c.get("recorte") or c.get("quadro_s") is not None)
    if t in ("polaroid", "filme"):
        return not midia_de_fora(c, doc, pasta)
    return False


def fora_minimo(total: float) -> int:
    """Quantas cenas de fora o vídeo precisa (exemplo: 4 em 83 s): 1 até 45 s, depois uma a cada ~21 s."""
    return 1 if total < 45 else max(2, round(total / FORA_A_CADA_S))


def imagem_da_cena(c: dict, doc: dict, pasta: Path) -> tuple[str, float | None] | None:
    """(arquivo, segundo) da imagem que a cena mostra: recorte/jornal/relógio com silhueta (quadro do bruto), polaroid
    (quadro do b-roll) e filme (início do trecho). None = cena sem mídia, ou a mídia é a foto única do bruto (roteiro
    narrado com uma foto só: todo recorte sai dela)."""
    t = c.get("tipo")
    if t in ("recorte", "jornal") or (t == "relogio" and (c.get("recorte") or c.get("quadro_s") is not None)):
        f = achar(c.get("fonte") or doc.get("video"), pasta)
        q = c.get("quadro_usado", c.get("quadro_s", c["de"] + .4 * (c["ate"] - c["de"])))
    elif t == "polaroid":
        chave = "imagem" if c.get("imagem") else "video"
        f = achar(c.get(chave) or doc.get("video"), pasta)
        q = c.get("quadro_s", 1.0 if c.get(chave) else (c["de"] + c["ate"]) / 2)
    elif t == "filme":
        f = achar(c.get("video") or c.get("imagem"), pasta)
        q = c.get("inicio_s", 0)
    else:
        return None
    if not f:
        return None
    if f.suffix.lower() in IMAGEM:
        bruto = achar(doc.get("video"), pasta)
        return None if bruto and bruto.resolve() == f.resolve() else (str(f.resolve()), None)
    try:
        return (str(f.resolve()), float(q))
    except (TypeError, ValueError):   # "quadro_s": null → o motor usa o meio da cena
        return (str(f.resolve()), float(c["de"] + .4 * (c["ate"] - c["de"])))


def imagens_repetidas(cenas: list[dict], doc: dict, pasta: Path) -> list[list[dict]]:
    """Grupos de cenas que mostram a mesma imagem: mesmo arquivo e a menos de QUADRO_PERTO_S (ou a mesma foto).
    No V2 refeito do Cliente4, 9 recortes saíram de só 5 quadros (72, 105 e 111 duas vezes; o 21 no jornal e num recorte)."""
    vistos: list[tuple[tuple, list[dict]]] = []
    for c in cenas:
        im = imagem_da_cena(c, doc, pasta)
        if not im:
            continue
        g = next((g for (arq, q), g in vistos if arq == im[0] and (q is None or im[1] is None or abs(q - im[1]) < QUADRO_PERTO_S)), None)
        if g is None:
            vistos.append((im, [c]))
        else:
            g.append(c)
    return [g for _, g in vistos if len(g) > 1]


def termina_no_meio(fala: str) -> str | None:
    """A última palavra da fala da cena pede a seguinte ("barganha o", "área do", "trabalhar e"): devolve a palavra.
    Com ponto, vírgula ou interrogação no fim, a ideia fechou ali."""
    pal = str(fala or "").split()
    if not pal or pal[-1][-1:] in ".,;:!?…":
        return None
    return pal[-1] if norm(pal[-1]) in PEDE_A_SEGUINTE else None


PONTUACAO = ",.;:!?…"
PAUSA_IDEIA_S = .35   # pausa na fala que fecha a ideia, como a pontuação


def oracoes(ws: list[dict]) -> list[tuple[int, int]]:
    """As ideias da fala: [(i0, i1)] das palavras entre uma pontuação (ou pausa) e a próxima (a transcrição traz vírgula
    e ponto)."""
    out, i0 = [], 0
    for i, w in enumerate(ws):
        pausa = i + 1 < len(ws) and ws[i + 1]["s"] - w["e"] >= PAUSA_IDEIA_S
        if w["w"][-1:] in PONTUACAO or pausa or i == len(ws) - 1:
            out.append((i0, i))
            i0 = i + 1
    return out


def _indices(c: dict, ws: list[dict]) -> list[int]:
    return [k for k, w in enumerate(ws) if c["de"] - .05 <= w["s"] < c["ate"] - .05]


def comeca_no_meio(c: dict, ws: list[dict]) -> str | None:
    """A tela começa no meio da ideia? Devolve a palavra de antes, que pede esta ("uma habilidade" + "muito GRANDE").
    No exemplo-1 toda tela de frase começa onde a ideia começa: depois de pontuação ou de uma pausa."""
    idx = _indices(c, ws)
    if not idx or idx[0] == 0:
        return None
    a, b = ws[idx[0] - 1], ws[idx[0]]
    if a["w"][-1:] in PONTUACAO or b["s"] - a["e"] >= PAUSA_IDEIA_S:
        return None
    return a["w"]


def segue_na_proxima(c: dict, ws: list[dict]) -> str | None:
    """A tela termina no meio da ideia? Devolve a palavra seguinte, que completa esta ("mas também envolve" + "uma carga
    emocional", V2 do Cliente4). Fecha bem com vírgula, ponto, pausa ou antes de palavra que abre outra ideia (e, mas, que)."""
    idx = _indices(c, ws)
    if not idx or idx[-1] + 1 >= len(ws):
        return None
    a, b = ws[idx[-1]], ws[idx[-1] + 1]
    if a["w"][-1:] in PONTUACAO or b["s"] - a["e"] >= PAUSA_IDEIA_S or norm(b["w"].strip(PONTUACAO)) in ABRE_IDEIA:
        return None
    return b["w"]


def recorte_maximo(total: float) -> int:
    """Quantos recortes do bruto o vídeo leva: 1 a cada ~30 s (o mesmo bruto dá recortes parecidos)."""
    return max(1, round(total / RECORTE_A_CADA_S))


def chave_fraca(frase: str) -> bool:
    """Palavra-chave que não carrega a ideia: "VEZES", "TODO", "GRANDE", "DIRETAMENTE" (todas as palavras fracas)."""
    ns = [norm(w) for w in str(frase).split() if norm(w)]
    return bool(ns) and all(n in PALAVRA_FRACA or (n.endswith("mente") and len(n) > 6) for n in ns)


def chaves_da_cena(c: dict) -> list[str]:
    """As palavras-chave como aparecem na tela (tokens coloridos seguidos viram uma expressão)."""
    out, cur = [], []
    for tk in (c.get("tokens") or []) + [{"k": "", "txt": ""}]:
        if tk["k"]:
            cur.append(tk["txt"])
        elif cur:
            out.append(" ".join(cur).strip(PONTUACAO + "\"'“”"))
            cur = []
    return out


def claro_minimo(total: float) -> int:
    """Quantas telas claras (caderno de papel, polaroid no papel) o vídeo pede: o exemplo tem 2 em 1:23."""
    return 0 if total < 40 else max(1, round(total / CLARO_A_CADA_S))


def clipe_de_fora(c: dict, doc: dict, pasta: Path) -> str | None:
    if not midia_de_fora(c, doc, pasta):
        return None
    f = achar(c.get("video") or c.get("imagem"), pasta)
    return str(f.resolve()) if f else str(c.get("video") or c.get("imagem"))


def _continua(a: dict, b: dict) -> bool:
    """b é o mesmo plano de filme seguindo a (cena seguinte, trecho emendado): conta como um uso só do clipe."""
    if a["tipo"] != "filme" or b["tipo"] != "filme" or b["i"] != a["i"] + 1 or not (a.get("video") and b.get("video")):
        return False
    try:
        return abs(float(b.get("inicio_s", 0)) - (float(a.get("inicio_s", 0)) + a["ate"] - a["de"])) <= .6
    except (TypeError, ValueError):
        return False


def usos_de_clipe(cenas: list[dict], doc: dict, pasta: Path) -> dict[str, list[list[dict]]]:
    """{clipe: [[cenas de um uso], ...]} das cenas de fora. O V2 do Cliente4 pôs a caixa FIRED (Pexels) 3 vezes."""
    usos: dict[str, list[list[dict]]] = {}
    for c in cenas:
        p = clipe_de_fora(c, doc, pasta)
        if not p:
            continue
        g = usos.setdefault(p, [])
        if g and _continua(g[-1][-1], c):
            g[-1].append(c)
        else:
            g.append([c])
    return usos


def musica_da_tela(pasta: Path) -> dict | None:
    """A faixa que o João escolheu na tela (PLANO.json: musica.escolha → a opção). None = sem escolha ou sem música."""
    m = _plano_tela(pasta).get("musica")
    if not isinstance(m, dict) or m.get("sem"):
        return None
    esc = m.get("escolha") if isinstance(m.get("escolha"), str) else ""
    ops = [o for o in m.get("opcoes") or [] if isinstance(o, dict)]
    if esc:
        return next((o for o in ops if o.get("id") == esc), m if m.get("id") == esc or m.get("arquivo") else None)
    return m if (m.get("arquivo") or m.get("trechos")) else None


def _faixas(trechos: list[dict]) -> list[tuple[str, float]]:
    return [(Path(str(t.get("arquivo") or t.get("opcao") or "")).stem, float(t.get("de") or 0)) for t in trechos]


def _trechos_txt(segs: list[dict]) -> str:
    cat = _catalogo()
    return " → ".join(f"{Path(str(s.get('arquivo'))).stem}"
                      f"{' ' + cat[Path(str(s.get('arquivo'))).stem]['nome'] if Path(str(s.get('arquivo'))).stem in cat and cat[Path(str(s.get('arquivo'))).stem].get('nome') else ''}"
                      f" de {mmss(float(s.get('de', 0)))}" + (f" até {mmss(float(s['ate']))}" if s.get("ate") is not None else "")
                      for s in segs)


def _tem_palavra(toks: list[dict], frase: str) -> bool:
    alvo = [norm(w) for w in str(frase).split() if norm(w)]
    ns = [norm(t["txt"]) for t in toks]
    return bool(alvo) and any(ns[i:i + len(alvo)] == alvo for i in range(len(ns) - len(alvo) + 1))


def checar(doc: dict, pasta: Path, plano: dict | None = None, tela: dict | None = None) -> dict:
    """O que dá pra conferir só com o cenas.json, antes de renderizar (o --storyboard roda isto e o --conferir também):
    telas longas, rosto, a pessoa na tela somando tudo, tipos, gancho, cenas de fora, relógio sem hora na fala,
    música (falta, rejeitada, drone) e efeitos. Devolve {"motivos", "numeros", "plano", "tela"}."""
    tela = tela or escolha_da_tela(pasta)
    plano = ajustar_midia(plano or planejar(doc, pasta), doc, pasta)
    cenas, total = plano["cenas"], plano["total"]
    motivos = list(plano["avisos"])
    num: dict = {"duracao_s": total, "cenas": len(cenas)}
    # 1. telas acima de 2,5 s (a última vai até o fim do vídeo: a sobra depois da última palavra conta)
    longas = [c for c in cenas if c["ate"] - c["de"] > TELA_MAX + .05]
    num["tela_mais_longa_s"] = round(max([c["ate"] - c["de"] for c in cenas] or [0]), 2)
    for c in longas[:6]:
        fim = " (a última cena vai até o fim do vídeo)" if c is cenas[-1] else ""
        motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}) fica {br(c['ate'] - c['de'])} s na tela{fim}: "
                       f"o máximo é {br(TELA_MAX)} s (divida em duas)")
    if len(longas) > 6:
        motivos.append(f"Mais {len(longas) - 6} cenas passam de {br(TELA_MAX)} s")
    # 2. rosto: falando e somando tudo em que a pessoa aparece
    rosto = sum(c["ate"] - c["de"] for c in cenas if c["tipo"] == "pessoa") / total if total else 0
    num["rosto_pct"] = round(rosto * 100, 1)
    if rosto > ROSTO_MAX:
        motivos.append(f"A pessoa falando ocupa {rosto * 100:.0f}% do vídeo: o máximo é {ROSTO_MAX * 100:.0f}% (troque trechos por construções)")
    na_tela = sum(c["ate"] - c["de"] for c in cenas if mostra_pessoa(c, doc, pasta)) / total if total else 0
    num["pessoa_na_tela_pct"] = round(na_tela * 100, 1)
    if na_tela > PESSOA_TELA_MAX:
        motivos.append(f"A pessoa aparece em {na_tela * 100:.0f}% do vídeo somando falando, recorte, jornal, relógio e polaroid: "
                       f"o máximo é {PESSOA_TELA_MAX * 100:.0f}% (exemplo: 35%). Troque recortes por caderno, traço ou cena de fora "
                       f"(frase só até {FRASE_MAX * 100:.0f}%)")
    # 3. tipos de construção, e o peso de cada um: frase demais vira "texto no preto"; objeto é o que faz ser documentário
    tipos = sorted({c["tipo"] for c in cenas if c["tipo"] in CONSTRUCOES})
    num["construcoes"] = tipos
    tipos_min = int((doc.get("estilo") or {}).get("tipos_min") or TIPOS_MIN)   # o modelo do cliente pode baixar (Cliente4: foco em b-roll, sem recorte/jornal)
    if len(tipos) < tipos_min:
        motivos.append(f"Só {len(tipos)} tipo(s) de construção ({', '.join(NOME[t] for t in tipos) or 'nenhum'}): o mínimo é {tipos_min}")
    frase = sum(c["ate"] - c["de"] for c in cenas if c["tipo"] == "frase") / total if total else 0
    num["frase_pct"] = round(frase * 100, 1)
    if frase > FRASE_MAX:
        motivos.append(f"Frase em fundo liso ocupa {frase * 100:.0f}% do vídeo: o máximo é {FRASE_MAX * 100:.0f}% (exemplo: ~29%). "
                       "Troque frases por caderno (lista, contraste), traço (dois caminhos), jornal ou cena de fora")
    objetos = sum(c["ate"] - c["de"] for c in cenas if c["tipo"] in OBJETOS) / total if total else 0
    num["objetos_pct"] = round(objetos * 100, 1)
    if objetos < OBJETOS_MIN:
        motivos.append(f"Construções de objeto (polaroid, caderno, traço, jornal, filme, relógio) só em {objetos * 100:.0f}% do vídeo: "
                       f"o mínimo é {OBJETOS_MIN * 100:.0f}% (exemplo: ~45%). Lista ou contraste na fala vira caderno; lugar, gente "
                       "ou situação vira polaroid ou filme com cena de fora")
    corridas, cur = [], []
    for c in cenas + [{"tipo": ""}]:
        if c["tipo"] == "frase":
            cur.append(c)
            continue
        if cur:
            corridas.append(cur)
        cur = []
    num["frases_seguidas_max"] = max([len(g) for g in corridas] or [0])
    for g in [g for g in corridas if len(g) > FRASE_SEGUIDAS_MAX][:3]:
        chaves = [next((tk["txt"] for tk in c["tokens"] if tk["k"]), (c["fala"].split() or ["…"])[0]).strip(",.;:!?") for c in g]
        motivos.append(f"{len(g)} frases seguidas (cenas {g[0]['n']} a {g[-1]['n']}, {mmss(g[0]['de'])}: {', '.join(chaves)}): "
                       f"no máximo {FRASE_SEGUIDAS_MAX}. Ponha um objeto ou a pessoa no meio")
    # 3b. a mesma imagem duas vezes (recorte do mesmo quadro, a mesma polaroid ou o mesmo trecho de filme)
    rep = imagens_repetidas(cenas, doc, pasta)
    num["imagens_repetidas"] = [[c["n"] for c in g] for g in rep]
    for g in rep[:4]:
        im = imagem_da_cena(g[0], doc, pasta)
        onde = f"quadro {mmss(im[1])} de {Path(im[0]).name}" if im and im[1] is not None else Path(im[0]).name if im else ""
        motivos.append(f"A mesma imagem aparece {len(g)} vezes: cenas {', '.join(str(c['n']) for c in g)} ({onde}). Cada cena mostra "
                       f"uma imagem diferente: recorte de outro quadro com o gesto daquele trecho (a {br(QUADRO_PERTO_S, 0)} s ou mais), "
                       "outra cena de fora")
    recortes = [c for c in cenas if c["tipo"] == "recorte"]
    num["recortes"] = len(recortes)
    if len(recortes) > recorte_maximo(total):
        motivos.append(f"{len(recortes)} recortes do bruto (cenas {', '.join(str(c['n']) for c in recortes)}): o vídeo de {mmss(total)} "
                       f"leva no máximo {recorte_maximo(total)} (1 a cada ~{br(RECORTE_A_CADA_S, 0)} s; o exemplo tem só a silhueta do "
                       "relógio em 1:23). Recortes da mesma gravação parecem a mesma imagem: troque os outros por caderno, traço, "
                       "polaroid ou cena de fora")
    # 3c. a tela de texto termina no fim da ideia, com a palavra-chave dela, e o vídeo fecha forte
    abre_rapido = bool((doc.get("estilo") or {}).get("abre_com_pessoa"))   # abertura em cortes rápidos (pedido do João): os 3 primeiros s não cobram ideia inteira
    for a, b in zip(cenas, cenas[1:]):
        if "frase" not in (a["tipo"], b["tipo"]) and "traco" not in (a["tipo"], b["tipo"]):
            continue
        if abre_rapido and b["de"] < GANCHO_S + .01:
            continue
        p = termina_no_meio(a["fala"])
        if p:
            motivos.append(f"Cena {a['n']} ({NOME[a['tipo']]}, {mmss(a['de'])}) termina em \"{p}\" (\"{a['fala']}\") e a frase continua "
                           f"na cena {b['n']}: a ideia fica cortada. Mude o \"de\" da cena {b['n']} pra cortar no fim da ideia")
        elif a["tipo"] in ("frase", "traco") and not a.get("texto"):
            seg = segue_na_proxima(a, plano["palavras"])
            if seg:
                motivos.append(f"Cena {a['n']} ({NOME[a['tipo']]}, {mmss(a['de'])}) para em \"{a['fala']}\" e a ideia segue na cena "
                               f"{b['n']} (\"{seg} …\"): a tela de texto mostra a ideia inteira. Mude o \"de\" da cena {b['n']} pra "
                               "cortar na vírgula, no ponto ou na pausa")
    for c in cenas:
        for k in ("destaque", "dor", "empresa"):
            for kw in c.get(k) or []:
                if c["tokens"] and not _tem_palavra(c["tokens"], kw):
                    motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}): a palavra-chave \"{kw}\" não está na fala dela "
                                   f"(\"{c['fala']}\"). Mude o \"de\" da cena ou a palavra")
    fim = next((c for c in reversed(cenas) if c["tokens"]), None)
    if fim and not any(tk["k"] for tk in fim["tokens"]):
        motivos.append(f"O fim é fraco: a última tela com fala (cena {fim['n']}, \"{fim['fala']}\") não tem palavra-chave. Feche numa "
                       "construção com a palavra-chave da última ideia (junte o fim da fala numa cena só)")
    elif fim:
        ult = fim["tokens"][-1]["txt"]   # o que a tela mostra por último
        if norm(ult) in FIM_FRACO:
            na_tela = " ".join(tk["txt"] for tk in fim["tokens"])
            motivos.append(f"O fim fica pendurado: a última tela (cena {fim['n']}, \"{na_tela}\") fecha em \"{ult.strip(PONTUACAO)}\". "
                           "Feche na palavra-chave: a última tela termina nela (ou corte a sobra do fim da fala com \"duracao\")")
    # 3d. palavra-chave forte: em letra grande ela carrega a ideia ("muitas VEZES", "o tempo TODO", "muito GRANDE",
    # "DIRETAMENTE com ele" no V2 do Cliente4 eram palavras vazias)
    for c in cenas:
        grandes = chaves_da_cena(c) if c["tipo"] in ("frase", "traco") or c is fim else []
        if c["tipo"] == "traco":
            grandes += [str(r.get("texto") or "") for r in (c.get("rotulos") or {}).values() if r.get("texto")][-1:]
        if c["tipo"] == "caderno" and c.get("circulo"):
            grandes.append(str(c["circulo"].get("texto") or ""))
        fracas = [g for g in grandes if chave_fraca(g)]
        if fracas:
            motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}): \"{fracas[0].upper()}\" é palavra-chave fraca "
                           f"(\"{c['fala']}\"). A palavra grande carrega a ideia: o substantivo ou o verbo forte da fala "
                           "(BARGANHA, PREJUÍZO, TURNOVER), nunca quantidade, intensidade ou pronome (VEZES, TODO, GRANDE, -MENTE)")
    # 3e. a tela de texto começa onde a ideia começa, e uma ideia curta não se espalha por 3 telas
    ws = plano["palavras"]
    meio = []
    for c in cenas:
        if c["tipo"] in ("frase", "traco") and not c.get("texto"):
            p = comeca_no_meio(c, ws)
            if p:
                meio.append(c)
                if len(meio) <= 4:
                    motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}) começa no meio da ideia (\"{c['fala']}\" vem "
                                   f"depois de \"{p}\"): a tela de texto mostra a ideia inteira. Comece a cena onde "
                                   "a ideia começa (depois da vírgula ou do ponto) ou ponha esse trecho na pessoa ou num objeto")
    if len(meio) > 4:
        motivos.append(f"Mais {len(meio) - 4} telas de texto começam no meio da ideia")
    quebradas = []
    for i0, i1 in oracoes(ws):
        if ws[i1]["e"] - ws[i0]["s"] > 2 * TELA_MAX:
            continue   # ideia longa não cabe em 2 telas: pode passar por 3
        telas = sorted({c["n"] for c in cenas for w in ws[i0:i1 + 1] if c["de"] - .05 <= w["s"] < c["ate"] - .05})
        if len(telas) >= 3 and not (abre_rapido and ws[i0]["s"] < GANCHO_S):
            quebradas.append((telas, " ".join(w["w"] for w in ws[i0:i1 + 1]), ws[i0]["s"]))
    num["ideias_quebradas"] = [t for t, _, _ in quebradas]
    for telas, txt, t0 in quebradas[:3]:
        motivos.append(f"A ideia \"{txt}\" ({mmss(t0)}) está quebrada em {len(telas)} telas (cenas {', '.join(map(str, telas))}): "
                       "ideia curta cabe em 1 ou 2 telas. Junte numa construção só")
    if len(quebradas) > 3:
        motivos.append(f"Mais {len(quebradas) - 3} ideias quebradas em 3 telas ou mais")
    # 3f. caderno é lista: 2 itens ou mais. Só o círculo ("NÃO É A MAIORIA", "SENSO COMUM") é frase disfarçada de caderno
    for c in cenas:
        if c["tipo"] == "caderno" and len(c.get("itens") or []) < 2:
            motivos.append(f"Cena {c['n']} (Caderno, {mmss(c['de'])}) tem {len(c.get('itens') or [])} item: caderno é lista, com 2 "
                           "itens ou mais (ex.: revisar cada peça, responder cada cliente, aprovar cada detalhe → TUDO). "
                           "Sem lista na fala, use outra construção")
    # 3g. papel claro e escuro se alternam, como no exemplo (2 telas claras em 1:23)
    claras = [c for c in cenas if tela_clara(c)]
    num["telas_claras"] = len(claras)
    sem_papel = (doc.get("estilo") or {}).get("papel_claro") is False   # o modelo do cliente recusou papel claro
    if sem_papel:
        num["telas_claras_dispensadas"] = "regra do cliente (estilo.papel_claro: false)"
    if not sem_papel and len(claras) < claro_minimo(total):
        motivos.append(f"Só {len(claras)} tela(s) clara(s): o exemplo alterna papel claro (caderno quadriculado, polaroid no papel) e "
                       f"escuro, 2 em 1:23; o vídeo de {mmss(total)} pede {claro_minimo(total)}. Caderno sem \"tom\": \"escuro\" ou "
                       "\"fundo\": \"papel\"")
    # 3h. legenda abaixo do queixo nas cenas de pessoa (G3; o V2 do Cliente4 tinha legenda em cima da boca/barba em metade delas)
    pessoas = [c for c in cenas if c["tipo"] == "pessoa" and c.get("legenda") is not False and not (doc.get("estilo") or {}).get("sem_legenda")]   # sem legenda: nada a cobrar
    num["legenda"] = {"cenas_pessoa": len(pessoas), "rosto_achado": sum(1 for c in pessoas if c.get("queixo_y") is not None),
                      "y": [c.get("leg_y") for c in pessoas]}
    for c in pessoas:
        if c.get("queixo_y") is None:
            continue
        minima = round(folga_legenda(c.get("rosto_px") or 0, minima=True))
        if c["leg_y"] < c["queixo_y"] + minima - 2 or c["leg_y"] > LEG_MAX_Y:
            motivos.append(f"Cena {c['n']} (Pessoa, {mmss(c['de'])}): a legenda não cabe no peito, abaixo do queixo (queixo em "
                           f"y={c['queixo_y']}, legenda em y={c['leg_y']}; ela vai {minima} px ou mais abaixo do queixo e acima de "
                           f"y={LEG_MAX_Y}). Use outro trecho, plano aberto ou outra construção")
    # 3h2. cor do cliente: a do identidade.json vale (João, 09-out: "usa a cor dele"); o cenas.json não põe outra por cima
    cli_cores = cores_do_cliente(pasta)
    if cli_cores:
        arq = identidade(pasta)[1]
        num["cores"] = {"do_cliente": str(arq), **{k: plano["cores"].get(k) for k in cli_cores}}
        outras = {k: v for k, v in (doc.get("cores") or {}).items() if k in cli_cores and str(v).strip().lower() != cli_cores[k].lower()}
        if outras:
            onde = arq.relative_to(ESTUDIO) if arq and arq.is_relative_to(ESTUDIO) else arq
            motivos.append(f"Cores do cenas.json que não são as do cliente ({', '.join(f'{k} {v}' for k, v in outras.items())}): a cor "
                           f"dele está em {onde} e o motor já usa. Tire esses \"cores\" do cenas.json")
    # 3i. jornal com o rosto bom: de frente, olho aberto, sem borrão
    for c in cenas:
        q = c.get("rosto_q") if c["tipo"] == "jornal" else None
        if not q or q.get("rosto") is None and q.get("olhos") is None:
            continue
        ruim = ("o rosto não aparece de frente" if not q.get("rosto") else "o olho sai fechado ou tapado" if not q.get("olhos")
                else "o rosto sai borrado (ele se mexe)" if (q.get("mov") or 0) > MOV_MAX else "")
        if ruim:
            motivos.append(f"Cena {c['n']} (Jornal, {mmss(c['de'])}): {ruim} no quadro {mmss(float(q.get('t') or 0))} do bruto. Escolha "
                           "outro quadro_s, de frente, olho aberto e parado (python3 render.py --rostos <bruto> mostra os rostos)")
    # 3j. b-roll com resolução pra tela (30-out-2026, Kodak: o clipe de 712 px esticado 1,7x saiu borrado e em blocos e NENHUMA checagem pegou:
    #     a 3i acima só olha o rosto do `jornal`, e a mídia de fora do `filme`/`polaroid` nunca era medida)
    for c in cenas:
        if c["tipo"] not in ("polaroid", "filme") or not midia_de_fora(c, doc, pasta):
            continue
        f = achar(c.get("video") or c.get("imagem"), pasta)
        corte = tuple(c.get("corte") or ((0, 0, 1, 1) if c["tipo"] == "polaroid" else _autocorte_seguro(f, c, pasta)))
        r = avaliar_resolucao(c, f, corte)
        if not r:
            continue
        c["escala_tela"] = {k: r[k] for k in ("esticado", "depois_do_upscale", "ampliada")}
        if r["depois_do_upscale"] > UPSCALE_FINAL_MAX:
            motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}): {f.name} tem {r['tam'][0]}x{r['tam'][1]} px e é esticado {r['esticado']:.1f}x pra encher a tela"
                           + (f" (ainda {r['depois_do_upscale']:.1f}x mesmo com o upscale)" if r["upscale"] > 1 else " (upscale desligado na cena)")
                           + ": sai borrado e em blocos. Troque por um clipe ou foto maior (1080 px de largura ou mais) ou outro trecho")
    num["b_roll_escala"] = {str(c["n"]): c["escala_tela"] for c in cenas if c.get("escala_tela")}
    # 4. gancho
    gancho = [c for c in cenas if c["de"] < GANCHO_S]
    num["gancho"] = [c["tipo"] for c in gancho]
    if not gancho or (any(c["tipo"] == "pessoa" for c in gancho) and not (doc.get("estilo") or {}).get("abre_com_pessoa")):
        motivos.append("Os 3 primeiros segundos não estão numa construção: o gancho abre com frase, recorte, relógio… (não precisa ser fundo preto)")
    # 5. cenas de fora: polaroid e filme mostram uma cena (escritório, gente, fábrica), nunca a própria pessoa
    da_pessoa = [c for c in cenas if c["tipo"] in ("polaroid", "filme") and not midia_de_fora(c, doc, pasta)]
    usos = usos_de_clipe(cenas, doc, pasta)
    fora = list(usos)   # clipes diferentes: o mesmo plano de filme emendado em duas cenas conta uma vez
    num["cenas_de_fora"] = len(fora)
    for c in da_pessoa[:4]:
        motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}) mostra a própria pessoa: polaroid e filme mostram uma "
                       "cena de fora (b-roll do acervo ou do get-brolls); sem cena boa, troque por frase, caderno ou traço")
    num["clipes_repetidos"] = {Path(p).name: [[c["n"] for c in g] for g in gs] for p, gs in usos.items() if len(gs) > 1}
    for p, gs in list(usos.items()):
        if len(gs) > 1:
            motivos.append(f"O clipe {Path(p).name} entra {len(gs)} vezes (cenas {', '.join(str(g[0]['n']) for g in gs)}): cada cena de "
                           "fora é um clipe diferente. Busque outro no acervo ou no get-brolls")
    de_fora = sorted((g[0] for gs in usos.values() for g in gs), key=lambda c: c["i"])
    sem_origem = [c for c in de_fora if not str(c.get("origem") or "").strip()]
    if sem_origem:
        motivos.append(f"Cenas de fora sem \"origem\" (cenas {', '.join(str(c['n']) for c in sem_origem)}): diga de onde veio cada uma "
                       "(o filme ou o arquivo, o acervo ou o link). É por ela que se vê se é cena real ou banco de imagem")
    for c in de_fora:
        o = str(c.get("origem") or "").strip()
        if o and any(b in norm(o) for b in BANCO):
            motivos.append(f"Cena {c['n']} ({NOME[c['tipo']]}, {mmss(c['de'])}) é de banco de imagem ({o}): ator posando é o \"banco de "
                           "dados de vídeo\" que o João odeia. Use cena de filme ou de arquivo real, como as que ele escolheu (The "
                           "Office, A Grande Aposta, fábrica de 1950, Joey), sem marca d'água")
    pol = [c for c in de_fora if c["tipo"] == "polaroid"]
    num["cenas_de_fora_polaroid"] = len(pol)
    pede = -(-len(de_fora) * FORA_POLAROID_MIN // 1) if len(de_fora) >= 3 else 0
    if len(pol) < pede:
        motivos.append(f"Das {len(de_fora)} cenas de fora, {len(de_fora) - len(pol)} são filme na tira de jornal e {len(pol)} "
                       f"polaroid: a mesma moldura toda hora. Alterne filme e polaroid: pelo menos "
                       f"{int(pede)} polaroids (o mesmo clipe vira polaroid com \"video\" e o \"quadro_s\" da --folha-broll; com "
                       "\"fundo\": \"papel\" ela conta como tela clara)")
    if len(fora) < fora_minimo(total):
        motivos.append(f"Só {len(fora)} cena(s) de fora: o vídeo de {mmss(total)} pede {fora_minimo(total)} (polaroid ou filme com "
                       "b-roll do que a fala descreve: escritório, equipe, fábrica, dinheiro). O exemplo tem 4 em 1:23. Busque "
                       "novas no acervo e no get-brolls: as que o João já escolheu entram, mas não bastam")
    # 6. relógio só quando a fala diz a hora
    for c in cenas:
        if c["tipo"] == "relogio":
            perto = " ".join(w["w"] for w in plano["palavras"] if c["de"] - 1.5 <= w["s"] < c["ate"])
            if not hora_na_fala(perto or c.get("texto") or ""):
                motivos.append(f"Cena {c['n']} (Relógio, {mmss(c['de'])}): a fala não diz hora (\"{c['fala'] or perto}\"), então o "
                               f"relógio inventa {c['relogio']['de']}. Relógio só quando ela fala a hora; troque por outra construção")
    # 7. música (o volume nas pausas é medido no áudio: previa-som do --storyboard ou o vídeo no --conferir)
    segs = segmentos_musica(doc, total)
    mus: dict = {"faixas": [s.get("arquivo") for s in segs]}
    if tela["sem_musica"]:
        mus = {"sem": True, "por": "escolha do João"}
        if segs:
            motivos.append("O João escolheu \"Sem música\" na tela, mas o cenas.json tem música: tire (\"musica\": null)")
    elif not segs:
        motivos.append("Sem música: o documentário leva uma faixa do Mixkit audível nas pausas")
    else:
        for s in segs:
            idm = Path(str(s.get("arquivo"))).stem
            if (_catalogo().get(idm) or {}).get("status") == "rejeitada":
                motivos.append(f"Música {idm} foi rejeitada pelo João ({_catalogo()[idm].get('motivo', 'S4')})")
            arq = achar(s.get("arquivo"), pasta)
            if not (arq and arq.exists()):
                motivos.append(f"Música não encontrada: {s.get('arquivo')}")
                continue
            b = _bandas(ler_audio(arq, float(s.get("inicio_s", 0)), min(30, s["ate"] - s["de"] + 1)))
            ma = round(b.get("medio", 0) + b.get("agudo", 0), 2)
            mus.setdefault("banda_media_aguda", []).append(ma)
            if ma < DRONE_MAX:
                motivos.append(f"A música {idm} é drone/pad: só {ma * 100:.0f}% do som em médio+agudo (mínimo {DRONE_MAX * 100:.0f}%)")
        # cada trecho com de e até: é o que a tela mostra e o que o render toca
        mus["trechos"] = [{"arquivo": s.get("arquivo"), "inicio_s": float(s.get("inicio_s", 0)), "de": round(float(s["de"]), 2),
                           "ate": round(float(s["ate"]), 2)} for s in segs]
        # a música que o João aprovou na tela (PLANO.json) é a do vídeo: com 2 faixas, a opção guarda os trechos. No V2 do
        # Cliente4 o cenas.json tocava 364 → 1154 e a opção era uma faixa só: aprovar renderizaria só a 1ª
        op = musica_da_tela(pasta)
        if op:
            tr = [t for t in op.get("trechos") or [] if isinstance(t, dict) and (t.get("arquivo") or t.get("opcao"))]
            aprovada = _faixas(tr) if len(tr) > 1 else [(Path(str(op.get("arquivo") or op.get("opcao") or "")).stem, 0.0)]
            daqui = _faixas(segs)
            if len(daqui) > 1 and len(tr) < 2:
                motivos.append(f"A música troca de faixa ({_trechos_txt(mus['trechos'])}), mas a opção escolhida na tela "
                               f"({op.get('id') or 'm1'}) guarda só a 1ª: grave nela os \"trechos\" (arquivo, inicio_s, de) iguais aos do "
                               "cenas.json, senão a tela mostra uma faixa só e o vídeo sai só com ela")
            elif [a for a, _ in aprovada] != [a for a, _ in daqui] or any(abs(x - y) > .6 for (_, x), (_, y) in zip(aprovada[1:], daqui[1:])):
                motivos.append(f"A música do cenas.json ({_trechos_txt(mus['trechos'])}) não é a que o João aprovou na tela "
                               f"({' → '.join(f'{a} de {mmss(d)}' for a, d in aprovada)}): o \"musica\" do cenas.json é a lista inteira "
                               "dos trechos da opção escolhida")
    num["musica"] = mus
    # 8. efeitos: suaves e espaçados, no máximo o ritmo do exemplo (16 em 1:23); o V2 do Cliente4 tinha 108 em 2 min
    ev = plano["eventos"]
    golpes = [e for e in ev if e["som"] in GOLPES or e["som"] not in SONS]
    golpes += [{"cena": c["i"], "som": k} for c in cenas for k in ("golpe", "slam", "impacto") if c.get(k)]
    teto = teto_efeitos(total)
    num["efeitos"] = {"total": len(ev), "teto": teto, "por_minuto": round(len(ev) / total * 60, 1) if total else 0,
                      "exemplo": "16 em 1:23 (11,6 por minuto)",
                      "por_som": {s: sum(1 for e in ev if e["som"] == s) for s in sorted({e["som"] for e in ev})},
                      # os sons que as cenas pedem, ligados ou não: a tela só mostra chip desses (o V2 mostrava "Tique do
                      # relógio" num vídeo sem relógio)
                      "sons_das_cenas": [s for s in SONS if any(e["som"] == s for e in candidatos_de_efeito(cenas))]}
    if len(ev) > teto:
        motivos.append(f"{len(ev)} efeitos sonoros em {mmss(total)}: o teto é {teto} (o exemplo tem 16 em 1:23). Suave e espaçado")
    colados = [(a, b) for a, b in zip(ev, ev[1:]) if b["t"] - a["t"] < EFEITO_ESPACO_S - .01]
    if colados:
        a, b = colados[0]
        motivos.append(f"{len(colados)} efeito(s) colado(s) no anterior (ex.: {mmss(a['t'])} e {mmss(b['t'])}): no exemplo o mais perto "
                       f"é {br(EFEITO_ESPACO_S)} s")
    desl = sons_desligados_na_tela(pasta)
    if desl:
        num["efeitos"]["sons_desligados_na_tela"] = sorted(desl)
    if tela["sem_efeitos"]:
        num["efeitos"]["desligados_por"] = "escolha do João"
        if ev:
            motivos.append(f"O João desligou os efeitos sonoros na tela, mas o vídeo tem {len(ev)}: use \"efeitos\": false")
    elif not ev:
        motivos.append("Sem efeitos sonoros: o documentário leva efeitos suaves (o teclado da tela de texto)")
    elif desl & sons_ligados(doc.get("efeitos", True)):
        # o motor escolhe os efeitos entre os sons ligados no cenas.json: som que o João desmarcou não pode estar ligado
        # (mesmo que desta vez não tenha sido escolhido, ele pode entrar no lugar de outro)
        voltou = [s for s in SONS if s in desl and s in sons_ligados(doc.get("efeitos", True))]
        motivos.append(f"O João desmarcou na tela: {', '.join(ROTULO[s] for s in voltou)}; mas o cenas.json ainda liga esse som: "
                       f"use \"efeitos\": {json.dumps([s for s in SONS if s not in desl])} no cenas.json")
    if golpes:
        motivos.append(f"Efeito de impacto/golpe no vídeo ({', '.join(sorted({str(g['som']) for g in golpes}))}): documentário tem zero golpe")
    return {"motivos": motivos, "numeros": num, "plano": plano, "tela": tela}


def medir_musica(plano: dict, fonte: Path | None) -> tuple[dict, list[str]]:
    """Volume da música nas pausas da fala (e sob a fala), medido na trilha sem voz ou no vídeo. Devolve (números, motivos)."""
    import numpy as np
    jan = pausas(plano["palavras"], plano["total"])
    if not (fonte and fonte.exists()) or not jan:
        return {}, []
    x = ler_audio(fonte)
    q = int(.1 * SR)
    niveis = [db(x[int(t * SR):int(t * SR) + q]) for a, b in jan for t in np.arange(a, b - .1, .1)]
    fala = [db(x[int(w["s"] * SR):int(w["e"] * SR)]) for w in plano["palavras"] if w["e"] - w["s"] > .1]
    num = {"pausas_db": round(float(np.median(niveis)), 1) if niveis else None,
           "sob_fala_db": round(float(np.median(fala)), 1) if fala else None}
    if niveis and np.median(niveis) < MUSICA_MIN_DB:
        return num, [f"Música inaudível nas pausas: {br(float(np.median(niveis)))} dB (mínimo {MUSICA_MIN_DB:.0f} dB)"]
    return num, []


def queixo_no_quadro(g) -> tuple[int, int] | None:
    """Num quadro pronto do palco (cinza, 9:16): (y do queixo, altura do rosto) em px do palco 1080x1920, ou None."""
    r = _rosto(g)
    return (round((r["y"] + QUEIXO_H * r["h"]) * H), round(r["h"] * H)) if r else None


def legenda_colada(c: dict, plano: dict, g) -> int | None:
    """Cena de pessoa, quadro pronto: o y do queixo se a legenda não ficou no peito (folga abaixo de LEG_FOLGA_MIN rosto)."""
    m = queixo_no_quadro(g)
    if not m:
        return None
    queixo, rosto = m
    leg = c.get("leg_y") or (plano.get("estilo") or {}).get("legenda_y") or 1250
    return queixo if leg < queixo + folga_legenda(rosto, minima=True) else None


def motivo_legenda(c: dict, queixo: int, onde: str) -> str:
    return (f"{onde}, a legenda da cena {c['n']} (Pessoa, {mmss(c['de'])}) cola na boca/barba (queixo em y={queixo}, legenda em "
            f"y={c.get('leg_y')}): ela vai no peito, bem abaixo do queixo. Use outro trecho, plano aberto ou "
            "outra construção")


def legenda_na_boca(video: Path, plano: dict) -> list[tuple[dict, int]]:
    """No vídeo pronto: as cenas de pessoa em que a legenda ficou em cima da boca/barba ou colada nela. Olha o rosto em 3
    quadros da cena (ele se mexe; no fim o zoom está no máximo) e compara o queixo com o topo da legenda. [(cena, y do queixo)]."""
    out = []
    for c in plano["cenas"]:
        if c["tipo"] != "pessoa" or not (c.get("blocos") or c.get("tokens")):
            continue
        piores = []
        for u in (.3, .6, .9):
            qs = _quadros_cinza(video, c["de"] + u * (c["ate"] - c["de"]), .04, 25)
            q = legenda_colada(c, plano, qs[0][1]) if qs else None
            if q is not None:
                piores.append(q)
        if piores:
            out.append((c, max(piores)))
    return out


def conferir(doc: dict, pasta: Path, out: Path, video: Path | None) -> dict:
    """Reprova sozinho com os números do exemplo. Devolve {"ok", "motivos", "numeros"} e grava qa/conferir.json.
    Música e efeitos: se o João tirou na tela (PLANO.json), a falta deles não reprova; o que reprova é pôr de volta."""
    qa = out / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    ch = checar(doc, pasta)
    motivos, num, plano = ch["motivos"], ch["numeros"], ch["plano"]
    mus = num["musica"]
    if not mus.get("sem") and mus.get("faixas"):
        stem = qa / "trilha-sem-voz.wav"
        fonte = stem if stem.exists() else video
        if fonte and fonte.exists():
            medido, falta = medir_musica(plano, fonte)
            if medido:
                mus.update(medido, medido_em="trilha sem voz" if fonte == stem else "vídeo")
            motivos += falta
        else:
            motivos.append("Não deu pra medir a música: falta o vídeo renderizado (rode o render antes do --conferir)")
    # o mp4
    if video and video.exists():
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True)
        pr = json.loads(r.stdout or "{}")
        st = (pr.get("streams") or [{}])[0]
        num["video"] = {"arquivo": str(video), "largura": st.get("width"), "altura": st.get("height"),
                        "duracao_s": round(float((pr.get("format") or {}).get("duration", 0)), 2), "parada_max_s": _parada_max(video)}
        if (st.get("width"), st.get("height")) != (W, H):
            motivos.append(f"O vídeo tem {st.get('width')}x{st.get('height')}: tem que ser {W}x{H}")
        if num["video"]["parada_max_s"] > TELA_MAX + .1:
            motivos.append(f"Tem um trecho de {br(num['video']['parada_max_s'])} s com a imagem parada (máximo {br(TELA_MAX)} s)")
        boca = legenda_na_boca(video, plano)
        num["legenda"]["na_boca_no_video"] = [c["n"] for c, _ in boca]
        for c, queixo in boca[:4]:
            motivos.append(motivo_legenda(c, queixo, "No vídeo"))
        num["folha"] = str(folha_comparacao(video, qa))
    else:
        num["video"] = None
        motivos.append(f"Vídeo não encontrado: {video}")
    res = {"ok": not motivos, "motivos": motivos, "numeros": num}
    (qa / "conferir.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def checagem_storyboard(doc: dict, plano: dict, pasta: Path, out: Path, som: bool = True) -> dict:
    """A checagem do --storyboard: tudo que o --conferir reprova e dá pra saber antes do render (checar), mais a prévia do
    som (previa-som.m4a) com a música medida nas pausas. Grava qa/checagem.json. Nunca levanta erro: falha vira motivo."""
    ch = checar(doc, pasta, plano)
    mus = ch["numeros"]["musica"]
    if som:
        try:
            print(f"prévia do som: {previa_som(doc, plano, pasta, out)}")
            if not mus.get("sem") and mus.get("faixas"):
                medido, falta = medir_musica(plano, out / "qa" / "trilha-sem-voz.wav")
                mus.update(medido)
                ch["motivos"] += falta
        except (Exception, SystemExit) as e:
            ch["motivos"].append(f"A prévia do som não saiu: {e}")
    gravar_checagem(out, ch)
    return ch


def gravar_checagem(out: Path, ch: dict) -> None:
    qa = out / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "checagem.json").write_text(json.dumps({"ok": not ch["motivos"], "motivos": ch["motivos"], "numeros": ch["numeros"]},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────────── principal ─────────────────────────────

def _cenas_padrao() -> Path:
    for p in (Path.cwd() / "cenas.json", AQUI / "cenas.json"):
        if p.exists():
            return p
    raise SystemExit("cenas.json não encontrado: rode de dentro da pasta do vídeo ou passe --cenas <arquivo> (exemplo: cenas-modelo.json)")


def escolha_do_joao_som(doc: dict, pasta: Path) -> dict:
    """O que ele escolheu no Novo vídeo manda sobre o cenas.json: work/musica/sem = sem música; work/musica/escolhida.json = a faixa dele
    (musica_viral.py já cortou o refrão: entra em 0); work/efeitos/sem = nenhum efeito sonoro."""
    w = pasta / "work"
    if (w / "musica" / "sem").is_file():
        doc["musica"] = None
    elif (w / "musica" / "escolhida.json").is_file():
        try:
            arq = json.loads((w / "musica" / "escolhida.json").read_text(encoding="utf-8")).get("arquivo")
        except ValueError:
            arq = None
        if arq and (pasta / arq).is_file():
            doc["musica"] = [{"arquivo": arq, "inicio_s": 0, "de": 0}]
    if (w / "efeitos" / "sem").is_file():
        doc["efeitos"] = False
    return doc


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--_recortar":   # chamado pelo próprio render quando o rembg está só no .venv
        _tirar_fundo(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    ap = argparse.ArgumentParser(description="Motor do Documentário")
    ap.add_argument("--cenas", type=Path)
    ap.add_argument("--out", type=Path, help="pasta de saída (padrão: a do cenas.json)")
    ap.add_argument("--saida", type=Path, help="mp4 final (padrão: <out>/<saida do cenas.json ou video.mp4>)")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--ate", type=float)
    ap.add_argument("--quadro", help="segundos separados por vírgula, 'cenas' (um PNG no meio de cada cena) ou 'tipos' (um por tipo)")
    ap.add_argument("--storyboard", action="store_true")
    ap.add_argument("--conferir", action="store_true")
    ap.add_argument("--video", type=Path, help="mp4 a conferir (padrão: o vídeo final)")
    ap.add_argument("--sem-som", action="store_true", help="no --storyboard, não monta a previa-som.m4a")
    ap.add_argument("--folha-broll", type=Path, help="folha de um b-roll (12 quadros com o segundo de cada) pra escolher o "
                                                     "quadro_s da polaroid ou o inicio_s do filme: grava <sandbox>/qa/folha-<arquivo>.jpg")
    ap.add_argument("--rostos", type=Path, help="folha dos rostos do bruto (um a cada 0,5 s, com o segundo; em vermelho sem "
                                                "rosto ou olho não achado) pra escolher o quadro_s do jornal e do recorte: grava "
                                                "<out ou a pasta da sandbox>/qa/rostos.jpg")
    ap.add_argument("--processos", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    a = ap.parse_args()
    if a.rostos:
        v = a.rostos.expanduser().resolve()
        if not v.exists():
            raise SystemExit(f"vídeo não encontrado: {v}")
        casa = v.parent.parent if v.parent.name in ("work", "bruto") else v.parent
        print(f"rostos: {folha_rostos(v, (a.out or casa).resolve() / 'qa' / 'rostos.jpg')}")
        return
    if a.folha_broll:
        v = a.folha_broll.expanduser().resolve()
        if not v.exists():
            raise SystemExit(f"b-roll não encontrado: {v}")
        casa = v.parent.parent if v.parent.name == "brolls" else v.parent   # brolls/x.mp4 da sandbox → <sandbox>/qa/
        print(f"folha: {folha_broll(v, (a.out or casa).resolve() / 'qa' / f'folha-{v.stem}.jpg')}")
        return
    arq = (a.cenas or _cenas_padrao()).resolve()
    pasta = arq.parent
    out = (a.out or pasta).resolve()
    out.mkdir(parents=True, exist_ok=True)
    doc = escolha_do_joao_som(json.loads(arq.read_text(encoding="utf-8")), pasta)
    final = (a.saida or out / str(doc.get("saida") or "video.mp4")).resolve()
    if a.conferir:
        r = conferir(doc, pasta, out, (a.video or final).resolve())
        n = r["numeros"]
        mus = n.get("musica") or {}
        mus_txt = "sem música (escolha do João)" if mus.get("sem") else f"música nas pausas {mus.get('pausas_db')} dB"
        efe = n.get("efeitos") or {}
        efe_txt = ("efeitos desligados (escolha do João)" if efe.get("desligados_por")
                   else f"efeitos {efe.get('total')} (teto {efe.get('teto')}; exemplo 16 em 1:23)")
        print(f"rosto {n.get('rosto_pct')}% · pessoa na tela {n.get('pessoa_na_tela_pct')}% · frase {n.get('frase_pct')}% · "
              f"objetos {n.get('objetos_pct')}% · cenas de fora {n.get('cenas_de_fora')} · "
              f"construções {len(n.get('construcoes', []))} · tela mais longa {n.get('tela_mais_longa_s')} s · {mus_txt} · {efe_txt}")
        print(f"conferência: {out / 'qa' / 'conferir.json'}")
        if r["ok"]:
            print("APROVADO pela conferência")
            return
        print("REPROVADO:\n- " + "\n- ".join(r["motivos"]))
        sys.exit(1)
    t_ini = time.time()
    plano = ajustar_midia(planejar(doc, pasta), doc, pasta)   # legenda abaixo do queixo, quadro bom do rosto
    for av in plano["avisos"]:
        print("aviso:", av)
    cache = out / "_cache"
    preparar(plano, doc, pasta, cache)
    srv, porta = servir(AQUI, pasta, out, ESTUDIO)
    total = plano["total"]
    print(f"duração {total:.2f}s · {len(plano['cenas'])} cenas · {len(plano['eventos'])} efeitos · preparo {time.time() - t_ini:.0f}s")
    ch = checagem_storyboard(doc, plano, pasta, out, som=not a.sem_som) if a.storyboard else None
    from playwright.sync_api import sync_playwright
    if a.quadro or a.storyboard:
        with sync_playwright() as p:
            nav, pg = abrir(p, porta, plano)
            if a.storyboard:
                print(f"storyboard: {storyboard(pg, plano, doc, out, falta=ch['motivos'])}")
                gravar_checagem(out, ch)   # o storyboard mediu a legenda no quadro pronto
                folhas = folhas_de_fora(plano, doc, pasta, out)
                if folhas:
                    print("cenas de fora, quadro usado em dourado (olhe: o que a fala diz, gente quando ela fala de gente, "
                          "sem marca d'água): " + " · ".join(str(f) for f in folhas))
            if a.quadro:
                d = out / "quadros"
                d.mkdir(exist_ok=True)
                meio = [((c["de"] + c["ate"]) / 2, f"{c['n']:02d}-{c['tipo']}", c["tipo"]) for c in plano["cenas"]]
                if a.quadro == "tipos":   # um PNG por tipo de cena (a primeira de cada), perto do fim da cena: tudo já entrou
                    vistos = set()
                    alvos = [(c["de"] + .85 * (c["ate"] - c["de"]), c["tipo"]) for c in plano["cenas"]
                             if not (c["tipo"] in vistos or vistos.add(c["tipo"]))]
                elif a.quadro == "cenas":
                    alvos = [(t, nome) for t, nome, _ in meio]
                else:
                    alvos = [(float(x), f"{float(x):06.2f}") for x in a.quadro.split(",")]
                for t, nome in alvos:
                    pg.evaluate("t => seek(t)", t)
                    pg.screenshot(path=str(d / f"{nome}.png"))
                print(f"quadros: {len(alvos)} em {d}")
            nav.close()
        srv.shutdown()
        if ch is not None:
            n = ch["numeros"]
            print(f"checagem: pessoa falando {n.get('rosto_pct')}% · pessoa na tela {n.get('pessoa_na_tela_pct')}% · "
                  f"frase {n.get('frase_pct')}% · objetos {n.get('objetos_pct')}% · "
                  f"cenas de fora {n.get('cenas_de_fora')} · tipos {len(n.get('construcoes', []))} · "
                  f"música nas pausas {(n.get('musica') or {}).get('pausas_db')} dB · "
                  f"efeitos {(n.get('efeitos') or {}).get('total')} (teto {(n.get('efeitos') or {}).get('teto')}) · "
                  f"{out / 'qa' / 'checagem.json'}")
            print("pro João (use estes números no ANALISE.md): " + _musica_txt(doc, plano))
            if ch["motivos"]:
                print("REPROVADO na checagem (corrija o cenas.json e rode o --storyboard de novo):\n- " + "\n- ".join(ch["motivos"]))
                sys.exit(1)
            print("APROVADO na checagem: pode mostrar o storyboard")
        return
    dur = total if a.ate is None else min(a.ate, total)
    if a.ate is not None:
        final = out / "teste.mp4"
    n = int(round(dur * a.fps))
    k = max(1, min(a.processos, n // (a.fps * 3) or 1))
    lim = [round(n * j / k) for j in range(k + 1)]
    partes = [str(out / f"_parte{j}.mp4") for j in range(k)]
    plano_json = json.dumps(plano, ensure_ascii=False)
    codec = _codec()
    t0 = time.time()
    # ProcessPoolExecutor: se um trecho falha, o erro sobe aqui (o Pool antigo ficava esperando pra sempre)
    from concurrent.futures import ProcessPoolExecutor
    try:
        with ProcessPoolExecutor(k, mp_context=mp.get_context("spawn")) as ex:
            list(ex.map(_trecho, *zip(*[(porta, plano_json, lim[j], lim[j + 1], a.fps, partes[j], codec) for j in range(k)])))
    except Exception as e:
        raise SystemExit(f"o render parou: {e}")
    finally:
        srv.shutdown()
    t_q = time.time() - t0
    lista = out / "_partes.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes))
    mudo = out / "_mudo.mp4"
    _ff("-f", "concat", "-safe", 0, "-i", lista, "-c", "copy", mudo)
    qa = out / "qa"
    qa.mkdir(exist_ok=True)
    trilha = out / "_trilha.wav"
    info = montar_audio(doc, plano, pasta, dur, trilha, qa)
    _ff("-i", mudo, "-i", trilha, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", 2, "-shortest", "-movflags", "+faststart", final)
    for p in partes + [str(mudo), str(trilha), str(lista)]:
        Path(p).unlink(missing_ok=True)
    print(f"quadros: {n} em {t_q:.0f}s ({k} processos) · áudio {info['lufs_final']} LUFS · total {time.time() - t_ini:.0f}s")
    print(f"pronto: {final}")


if __name__ == "__main__":
    main()
