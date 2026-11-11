#!/usr/bin/env python3
"""
Motor genérico do Estúdio (nasce do formatos/_modelo: o que o motor do Documentário tem de genérico, sem as regras dele).
O index.html desenha a cena do segundo t (window.seek(t)); este arquivo só captura quadro a quadro (Playwright) e junta
com ffmpeg, com a voz, a música e os efeitos do cenas.json. O formato troca o index.html (o visual) e põe as medidas
dele em checar(); o resto não precisa mexer.

Roda de dentro da pasta copiada (base do formato, modelo do cliente ou sandbox). Tudo que ele grava fica ao lado do
cenas.json (ou em --out): storyboard.jpg, previa-som.m4a, quadros/, qa/ e o vídeo.

  python3 render.py --cenas cenas.json --storyboard    storyboard.jpg (um quadro por cena, com o tempo e a fala) +
                                                       qa/checagem.json + previa-som.m4a; exit 1 com o motivo
  python3 render.py --cenas cenas.json                 o vídeo ("saida" do cenas.json ou video.mp4)
  python3 render.py --cenas cenas.json --quadro 3.5,10 PNGs soltos em quadros/ ("cenas" = um no meio de cada cena)
  python3 render.py --cenas cenas.json --ate 4         só os 4 primeiros segundos (teste.mp4)
  python3 render.py --cenas cenas.json --conferir      qa/folha-comparacao.jpg (exemplo principal em cima, este vídeo
                                                       embaixo) + qa/conferir.json; exit 1 com o motivo em pt-BR
Esquema do cenas.json: README.md (exemplo: cenas-modelo.json).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FORMATO = "editorial"   # o formatos.py novo troca pelo slug: é daí que vem o exemplo principal da conferência


def _raiz() -> Path:
    for p in (AQUI, *AQUI.parents):
        if (p / "REGRAS.md").is_file() and (p / "formatos").is_dir():
            return p
    return Path.home() / "Projetos" / "Skill" / "Estúdio"


ESTUDIO = _raiz()
W, H, FPS = 1080, 1920, 30
FALA_PADRAO = "work/fala/fala.mp4"   # o vídeo do João (cortado, 1080x1920, 30 fps) das cenas "fala": preparar-fala.py grava


# ───────────────────────────── leitura e plano (sem navegador) ─────────────────────────────

def achar(caminho: str | None, pasta: Path) -> Path | None:
    """Arquivo citado no cenas.json: ao lado dele, no motor, na base do formato (música e efeitos) ou na raiz do Estúdio."""
    if not caminho:
        return None
    p = Path(str(caminho)).expanduser()
    for c in ([p] if p.is_absolute() else [pasta / p, AQUI / p, ESTUDIO / "formatos/editorial/base" / p, ESTUDIO / p]):
        if c.exists():
            return c.resolve()
    return None


def br(x: float) -> str:
    return f"{float(x):.1f}".replace(".", ",")


def duracao_midia(p: Path | None) -> float:
    if not p or not p.exists():
        return 0.0
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip() or 0)
    except ValueError:
        return 0.0


def planejar(doc: dict, pasta: Path) -> dict:
    """Cenas com de/ate (sem "ate": vai até o "de" da próxima; a última até a voz ou "duracao") e o que a página recebe."""
    largura, altura = int(doc.get("largura") or W), int(doc.get("altura") or H)
    brutas = sorted((c for c in doc.get("cenas") or [] if isinstance(c, dict)), key=lambda c: float(c.get("de", 0)))
    voz = achar(doc.get("voz"), pasta)
    fim = float(doc.get("duracao") or 0) or duracao_midia(voz)
    cenas = []
    for i, c in enumerate(brutas):
        de = float(c.get("de", 0))
        prox = float(brutas[i + 1].get("de", de)) if i + 1 < len(brutas) else (fim or de + 3)
        cenas.append({**c, "n": i + 1, "tipo": str(c.get("tipo") or "cena"), "de": round(de, 3),
                      "ate": round(float(c.get("ate") or prox), 3)})
    total = max([c["ate"] for c in cenas] + [fim, 0.0])
    pal = achar(doc.get("palavras"), pasta) if isinstance(doc.get("palavras"), str) else None
    palavras = []
    if pal:   # tempo por palavra (Groq {"words": [...]} ou lista): a legenda curta e o texto que acende
        bruto = json.loads(pal.read_text(encoding="utf-8"))
        palavras = [{"w": w.get("word", w.get("w", "")).strip(), "s": float(w.get("start", w.get("s", 0))), "e": float(w.get("end", w.get("e", 0)))}
                    for w in (bruto.get("words", bruto) if isinstance(bruto, dict) else bruto) if isinstance(w, dict)]
    aplicar_fundo_vivo(cenas, pasta)
    return {"total": round(total, 3), "cenas": cenas, "largura": largura, "altura": altura,
            "fps": int(doc.get("fps") or FPS), "voz": voz, "palavras": palavras, "legenda": doc.get("legenda", True),
            "legenda_y": doc.get("legenda_y"), "marca": doc.get("marca"), "fala": doc.get("fala") or FALA_PADRAO}


# ───────────────────────────── fundo vivo (30-out-2026) ─────────────────────────────
# João, no print do ícone 🎵 "Spotify" (anúncio-repetido-so-a-voz 0:03) e do 🌎 (blockbuster 0:23): "quando eu só tenho o fundo cinza, essas
# coisas meio broxantes". Peça que só desenhava no degradê (ícone, texto sem imagem, Venn, contador, pílulas, linha, conversa, colagem) ganha
# a imagem real mais próxima do vídeo, desfocada, escura e andando devagar. Fundo liso só com `"fundo": "liso"` na cena.
SEM_FUNDO = ("texto", "icone", "venn", "contador", "chips", "linha", "zap", "colagem", "fala")


def imagem_da_cena(c: dict) -> str | None:
    """Uma imagem real que esta cena mostra (a que o espectador acabou de ver), pra virar fundo da vizinha. Só o caminho, como no cenas.json."""
    if c.get("tipo") in ("fala", "recorte") and not c.get("imagem"):
        return None
    if isinstance(c.get("imagem"), str) and c["imagem"]:
        return c["imagem"]
    ims = [x for x in c.get("imagens") or [] if isinstance(x, str) and x]
    if ims:
        return ims[0]
    if isinstance(c.get("quadros_de"), str) and c["quadros_de"]:
        return c["quadros_de"] + "#meio"   # clipe: o quadro do meio (resolvido em _fundo_arquivo)
    return None


def _fundo_arquivo(ref: str, pasta: Path) -> Path | None:
    """Caminho do arquivo da imagem de fundo; clipe ("pasta#meio") vira o quadro do meio da pasta."""
    if ref.endswith("#meio"):
        d = achar(ref[:-5], pasta)
        jpgs = sorted(d.glob("*.jpg")) if d and d.is_dir() else []
        return jpgs[len(jpgs) // 2] if jpgs else None
    return achar(ref, pasta)


def precisa_fundo(c: dict) -> bool:
    """A peça desenha só no degradê? (texto/contador/linha/chips/conversa com imagem própria já têm fundo)"""
    if c.get("tipo") not in SEM_FUNDO or c.get("fundo") == "liso":
        return False
    if c["tipo"] in ("icone", "venn", "colagem"):
        return True                                  # nunca desenham fundo: sempre dependem de uma imagem atrás
    if c["tipo"] == "fala":
        return c.get("modo") == "canto" and not c.get("imagem")
    return not (isinstance(c.get("imagem"), str) and c["imagem"])


def aplicar_fundo_vivo(cenas: list[dict], pasta: Path) -> None:
    """Põe `fundo_vivo` (caminho da imagem) nas cenas que precisam: a imagem da cena mais próxima no tempo, a anterior no empate
    (a foto "continua" desfocada atrás da peça); foto vale mais que print (print é página branca, estraga o escuro) e acima de ~6 cenas
    de distância já não é "vizinha". Sem nenhuma imagem no vídeo, fica sem e o --conferir reprova."""
    for i, c in enumerate(cenas):
        if c.get("fundo_vivo") or not precisa_fundo(c):
            continue
        melhor = None
        for d in range(1, 7):
            for j in (i - d, i + d):
                if not 0 <= j < len(cenas):
                    continue
                ref = imagem_da_cena(cenas[j])
                if not ref or not _fundo_arquivo(ref, pasta):
                    continue
                custo = d + (2.5 if cenas[j].get("tipo") == "print" else 0) + (0.1 if j > i else 0)
                if melhor is None or custo < melhor[0]:
                    melhor = (custo, ref)
        if melhor is None and c.get("tipo") == "colagem":   # sem vizinha: a própria colagem desfocada atrás
            ref = imagem_da_cena(c)
            melhor = (0, ref) if ref and _fundo_arquivo(ref, pasta) else None
        if melhor:
            c["fundo_vivo"] = melhor[1]


def aplicar_locais(plano: dict, pasta: Path, avisos: list[str] | None = None) -> dict:
    """Ferramentas grátis do Mac (app/ferramentas/midia_local.py), só quando o cenas.json pede e sempre com cache em work/locais/:
    · foto abaixo de 1000 px de largura sobe pra ~1400+ com Real-ESRGAN antes de entrar (`"ampliar": false` desliga);
    · `foto`/`titulo` com `"parallax": true` vira um `clipe` de quadros a 30 fps com a câmera andando DENTRO da foto (profundidade
      Depth Anything: o que está perto desliza mais que o fundo). `mov` e `forca` valem. Falhou? a foto segue como foto e avisa."""
    avisos = avisos if avisos is not None else []
    try:
        sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
        import midia_local as ml
    except Exception as e:
        avisos.append(f"midia_local indisponível ({e}): fotos seguem como estão")
        return plano
    cache = pasta / "work" / "locais"
    for c in plano["cenas"]:
        if c.get("tipo") not in ("foto", "titulo") or not isinstance(c.get("imagem"), str):
            continue
        img = achar(c["imagem"], pasta)
        if not img:
            continue
        try:
            from PIL import Image
            with Image.open(img) as im:
                larg = im.width
            if larg < 1000 and c.get("ampliar") is not False:
                dst = cache / f"{img.stem}-x.jpg"
                if not dst.exists():
                    ml.upscale(img, dst, 1400)
                img = dst
                c["imagem"] = str(dst)
            if c.get("parallax"):
                dur = c["ate"] - c["de"]
                pq = cache / f"par-{img.stem}-{c.get('mov', 'dir')}-{dur:.2f}-{c.get('forca', 1)}"
                if not (pq.is_dir() and len(list(pq.glob("*.jpg"))) >= int(dur * FPS)):
                    ml.parallax(img, pq, dur, {"out": "in"}.get(c.get("mov"), c.get("mov") or "dir"), float(c.get("forca") or 1), FPS)
                c.update(tipo="clipe", quadros_de=str(pq), inicio=0)
                c.pop("imagem", None)
        except Exception as e:
            avisos.append(f"cena {c['n']}: ferramenta local falhou ({str(e)[:80]}), segue como foto")
    return plano


# Print de fonte (João, 29/10): "nunca, nunca use Wikipédia"; notícia de fonte confiável, nunca site duvidoso.
FONTE_PROIBIDA = ("wikipedia.org", "wiki", "metropoles", "terra.com.br/diversao", "fofoca")
FONTE_CONFIAVEL = ("cnn", "nytimes", "estadao", "globo", "g1.", "folha", "bbc", "reuters", "apnews", "valor", "exame",
                   "uol.com.br", "theguardian", "washingtonpost", "wsj", "bloomberg", "economist", "nature.com", "science.org",
                   "ihu.unisinos", "jove.com")


def _origens(pasta: Path) -> dict:
    """{arquivo: url} de prints/origem.json e fotos/origem.json (o que cada imagem é e de onde veio)."""
    import json as _j
    out = {}
    for f in (pasta / "prints" / "origem.json", pasta / "fotos" / "origem.json"):
        try:
            d = _j.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k, v in d.items():
            out[f"{f.parent.name}/{k}"] = (v.get("pagina") or v.get("url") or "") if isinstance(v, dict) else str(v)
    return out


def checar_fontes(doc: dict, pasta: Path) -> tuple[list[str], list[str]]:
    """(reprova, avisa): print da Wikipédia ou de site duvidoso reprova; print sem origem anotada só avisa."""
    orig = _origens(pasta)
    reprova, avisa = [], []
    for i, c in enumerate(doc.get("cenas") or [], 1):
        imgs = [c.get("imagem")] + list(c.get("imagens") or []) + [m.get("imagem") for m in c.get("msgs") or [] if isinstance(m, dict)]
        for x in [x for x in imgs if isinstance(x, str) and x]:
            url = orig.get(x, "")
            nome = (x + " " + url).lower()
            if x.startswith("prints/") and any(b in nome for b in FONTE_PROIBIDA):
                reprova.append(f"A cena {i} usa print da Wikipédia ou de site duvidoso ({x}). Use matéria de fonte confiável (CNN, NYT, Estadão, Globo...)")
            elif x.startswith("prints/") and url and not any(b in url.lower() for b in FONTE_CONFIAVEL):
                avisa.append(f"A cena {i}: o print vem de {url.split('/')[2] if '//' in url else url}; confira se a fonte é confiável")
            elif x.startswith("prints/") and not url:   # sem origem pode ser Wikipédia com outro nome (v4: grupo-minimo.png)
                reprova.append(f"A cena {i}: o print {x} não diz de onde veio. Anote a página em prints/origem.json (só fonte confiável)")
    return reprova, avisa


def checar_repeticao(doc: dict) -> tuple[list[str], list[str]]:
    """(reprova, avisa) — João, 29/10: "muito vídeo repetido"; "editorial precisa de dinamismo, novidade, entregar dopamina".
    Clipe real só uma vez no vídeo; a mesma foto no máximo 2 vezes; 3 cenas seguidas da mesma peça (fora foto) cansam."""
    from collections import Counter
    cs = doc.get("cenas") or []
    reprova, avisa = [], []
    clipes = Counter(c["quadros_de"] for c in cs if isinstance(c.get("quadros_de"), str))
    reprova += [f"O vídeo real {k} aparece {n} vezes: cada clipe entra uma vez só (busque outro)" for k, n in clipes.items() if n > 1]
    fotos = Counter(c["imagem"] for c in cs if isinstance(c.get("imagem"), str))
    reprova += [f"A imagem {k} aparece {n} vezes: no máximo 2 (a 2ª com outro enquadramento)" for k, n in fotos.items() if n > 2]
    seq = 1
    for i in range(1, len(cs)):
        seq = seq + 1 if cs[i].get("tipo") == cs[i - 1].get("tipo") else 1
        if seq == 3 and cs[i].get("tipo") not in ("foto", "titulo"):
            avisa.append(f"As cenas {i - 1} a {i + 1} são todas \"{cs[i].get('tipo')}\": troque uma por outra peça (dinamismo)")
    tipos = {c.get("tipo") for c in cs}
    if len(cs) >= 20 and len(tipos) < 7:
        avisa.append(f"Só {len(tipos)} tipos de peça em {len(cs)} cenas: use mais da biblioteca (clipe, recorte, print com grifo, contador...)")
    return reprova, avisa


def checar_fundo(cenas: list[dict]) -> tuple[list[str], list[str]]:
    """(reprova, avisa) — João, 30/10 ("fundo cinza... coisas meio broxantes"): nenhuma cena fica no degradê liso.
    · ícone sem `imagem` (emoji ou símbolo) reprova: use a logo real ou a foto da coisa citada (site oficial, Commons, fontes_gratis.py);
    · cena que só desenha no degradê e não achou imagem pra fundo vivo reprova (o vídeo não tem imagem nenhuma por perto);
    · `"fundo": "liso"` na cena é o único jeito de pedir fundo liso: avisa, não reprova."""
    reprova, avisa = [], []
    for c in cenas:
        if c.get("tipo") == "icone" and not (isinstance(c.get("imagem"), str) and c["imagem"]):
            reprova.append(f"A cena {c['n']} (ícone) usa {'o emoji ' + str(c['simbolo']) if c.get('simbolo') else 'um símbolo'} no lugar de uma imagem: "
                           "emoji não vale. Ponha em \"imagem\" a logo real (site oficial, press kit, Wikimedia Commons) ou a foto da coisa citada")
        elif c.get("fundo") == "liso" and c.get("tipo") in SEM_FUNDO:
            avisa.append(f"A cena {c['n']} ({c['tipo']}) está em fundo liso (pedido na cena): só vale se a ideia pede vazio")
        elif precisa_fundo(c) and not c.get("fundo_vivo"):
            reprova.append(f"A cena {c['n']} ({c['tipo']}) está em fundo liso sem imagem: o vídeo não tem nenhuma imagem perto pra desfocar atrás. "
                           "Ponha uma imagem real na cena (\"imagem\") ou em \"fundo_vivo\"")
    return reprova, avisa


def checar_resolucao(doc: dict, pasta: Path) -> tuple[list[str], list[str]]:
    """(reprova, avisa) — foto de tela cheia pequena vira borrão (30-out, Theranos: o cérebro a 1,6 s era uma miniatura esticada).
    Reprova lado maior abaixo de 800 px em foto/título (tela cheia); avisa abaixo de 1100."""
    from PIL import Image
    reprova, avisa = [], []
    for i, c in enumerate(doc.get("cenas") or [], 1):
        if c.get("tipo") not in ("foto", "titulo", "texto", "recorte") or not isinstance(c.get("imagem"), str) or not c["imagem"]:
            continue
        p = achar(c["imagem"], pasta)
        if not p:
            continue
        try:
            with Image.open(p) as im:
                lado = max(im.size)
        except Exception:
            continue
        if c["tipo"] == "recorte":   # o fundo do recorte também enche a tela; a pessoa recortada é menor e não conta
            pass
        if lado < 800:
            reprova.append(f"A cena {i}: {c['imagem']} tem só {lado} px: em tela cheia vira borrão. Troque por uma foto maior (Commons: iiurlwidth maior ou outra consulta)")
        elif lado < 1100:
            avisa.append(f"A cena {i}: {c['imagem']} tem {lado} px; em tela cheia fica mole")
    return reprova, avisa


def checar_dinamismo(cenas: list[dict]) -> tuple[list[str], list[str]]:
    """(reprova, avisa) — João, 29/10: "buscar o dinamismo, tem coisas muito paradas, as pessoas querem dopamina".
    Plano de imagem acima de 2,5 s reprova (dividir: outro enquadramento, outra peça, clipe, rajada); acima de 1,8 s avisa;
    tela de texto passa de 4 s avisa. Trocas por minuto abaixo de 40 avisa (régua das referências: 60 a 90)."""
    reprova, avisa = [], []
    for c in cenas:
        d = c["ate"] - c["de"]
        if c.get("tipo") == "texto":
            if d > 4: avisa.append(f"A cena {c['n']} (texto) dura {d:.1f} s: divida a frase em duas telas")
            elif d > 1.4 and len(c.get("tempos") or c.get("texto", "").split()) <= 2:   # card de 1-2 palavras acende rápido e fica parado (o conferir_video reprova "imagem parada" depois do render)
                avisa.append(f"A cena {c['n']} (texto de 1-2 palavras) dura {d:.1f} s e fica parada: encurte ou entre com imagem logo depois")
        elif c.get("tipo") in ("zap", "linha", "contador"):
            if d > 3.5: avisa.append(f"A cena {c['n']} ({c['tipo']}) dura {d:.1f} s: está parada demais")
        elif c.get("tipo") == "fala":   # o João falando: se mexe, mas gancho/virada/fecho longos demais cansam
            if d > 10: reprova.append(f"A cena {c['n']} (você falando) dura {d:.1f} s: corte pra uma cena do Editorial no meio dela")
            elif d > 7: avisa.append(f"A cena {c['n']} (você falando) dura {d:.1f} s: o momento forte é curto (até ~6 s)")
        elif c.get("tipo") == "clipe":   # vídeo real já se mexe sozinho
            if d > 3: avisa.append(f"A cena {c['n']} (clipe) dura {d:.1f} s: corte o clipe ou entre com outra peça")
        elif d > 2.5:
            reprova.append(f"A cena {c['n']} ({c.get('tipo')}) dura {d:.1f} s sem trocar nada: muito parada, divida (dinamismo)")
        elif d > 1.8:
            avisa.append(f"A cena {c['n']} ({c.get('tipo')}) dura {d:.1f} s: divida ou troque a peça")
    if cenas:
        total = cenas[-1]["ate"] - cenas[0]["de"]
        if total > 15 and len(cenas) * 60 / total < 40:
            avisa.append(f"Só {len(cenas) * 60 / total:.0f} trocas por minuto (as referências têm 60 a 90): falta imagem nova")
    return reprova, avisa


def checar(doc: dict, pasta: Path, plano: dict) -> dict:
    """O que já dá pra reprovar antes do render. As medidas do formato (do exemplo e das regras) entram aqui."""
    motivos = []
    cenas = plano["cenas"]
    if not cenas:
        motivos.append("O cenas.json não tem nenhuma cena")
    for a, b in zip(cenas, cenas[1:]):
        if b["de"] < a["ate"] - .01:
            motivos.append(f"A cena {b['n']} começa antes da cena {a['n']} terminar")
    for c in cenas:
        if c["ate"] <= c["de"]:
            motivos.append(f"A cena {c['n']} termina antes de começar ({br(c['de'])} s → {br(c['ate'])} s)")
        for k in ("imagem", "video"):
            if isinstance(c.get(k), str) and c[k] and not achar(c[k], pasta):
                motivos.append(f"A cena {c['n']} pede {k} que não existe: {c[k]}")
        for x in (c.get("imagens") or []) + [m.get("imagem") for m in c.get("msgs") or [] if isinstance(m, dict) and m.get("imagem")]:
            if isinstance(x, str) and not achar(x, pasta):
                motivos.append(f"A cena {c['n']} pede imagem que não existe: {x}")
    if any(c.get("tipo") == "fala" for c in cenas) and not achar(plano.get("fala"), pasta):
        motivos.append(f"As cenas \"fala\" precisam do vídeo dele: {plano.get('fala')} (rode preparar-fala.py)")
    if doc.get("voz") and not plano["voz"]:
        motivos.append(f"A voz não foi encontrada: {doc['voz']}")
    mus = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    if mus.get("arquivo") and not achar(mus["arquivo"], pasta):
        motivos.append(f"A música não foi encontrada: {mus['arquivo']}")
    for e in doc.get("efeitos") if isinstance(doc.get("efeitos"), list) else []:
        if isinstance(e, dict) and not achar(e.get("arquivo"), pasta):
            motivos.append(f"O efeito não foi encontrado: {e.get('arquivo')}")
    reprova, avisa = checar_fontes(doc, pasta)
    r2, a2 = checar_repeticao(doc)
    r3, a3 = checar_dinamismo(cenas)
    r4, a4 = checar_resolucao(doc, pasta)
    r5, a5 = checar_fundo(cenas)
    motivos += reprova + r2 + r3 + r4 + r5
    avisa += a2 + a3 + a4 + a5
    numeros = {"cenas": len(cenas), "total_s": plano["total"], "fontes": avisa,
               "musica": {"sem": not mus.get("arquivo"), "faixas": [mus["arquivo"]] if mus.get("arquivo") else []},
               "efeitos": {"total": len([e for e in doc.get("efeitos") or [] if isinstance(e, dict)])}}
    return {"ok": not motivos, "motivos": motivos, "numeros": numeros}


def _gravar(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────────── som: voz + música (baixa) + efeitos, -14 LUFS ─────────────────────────────

VOZ_LUFS = -16          # a voz é nivelada aqui antes da mistura
MUSICA_ABAIXO = 17      # música constante 17 LU abaixo da voz, o vídeo inteiro, sem abaixar e subir (régua: refs 13-18 LU; João 29/10: "a música tá sobressaindo sobre a minha voz")
CLIPE_ABAIXO = 10       # som de clipe real (torcida, gente falando) fica por baixo da voz


def _lufs(arq: Path, ini: float = 0, dur: float | None = None) -> float | None:
    """Volume integrado (LUFS) de um trecho; None se não deu pra medir (silêncio ou arquivo ruim)."""
    import json as _j
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{ini:.3f}", *(["-t", f"{dur:.3f}"] if dur else []), "-i", str(arq),
                        "-af", "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    try:
        v = float(_j.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])["input_i"])
    except (ValueError, KeyError):
        return None
    return v if v > -70 else None


def _ganho(arq: Path, alvo: float, ini: float = 0, dur: float | None = None, reserva: float = .1) -> float:
    """Multiplicador que leva o trecho medido até `alvo` LUFS (sem medida: o volume de reserva do cenas.json)."""
    m = _lufs(arq, ini, dur)
    return reserva if m is None else round(10 ** ((alvo - m) / 20), 4)


def montar_som(doc: dict, plano: dict, pasta: Path, dur: float, saida: Path) -> Path | None:
    """Mistura voz, música (volume do cenas.json, padrão 0,12) e efeitos ({"t", "arquivo", "volume"}). None = sem som."""
    entradas, filtros, rotulos = [], [], []
    if plano["voz"]:
        entradas += ["-i", str(plano["voz"])]
        filtros.append(f"[{len(rotulos)}:a]aresample=48000,loudnorm=I={VOZ_LUFS}:TP=-2:LRA=9[a{len(rotulos)}]")   # voz nivelada antes da mistura
        rotulos.append(f"[a{len(rotulos)}]")
    mus = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    arq = achar(mus.get("arquivo"), pasta)
    if arq:
        entradas += ["-ss", str(float(mus.get("inicio_s") or 0)), "-i", str(arq)]
        k = len(rotulos)
        # medida, não no ouvido: o trecho da música que toca vai pra voz - MUSICA_ABAIXO, constante do 1º ao último quadro
        g = _ganho(arq, VOZ_LUFS - float(mus.get("abaixo_db") or MUSICA_ABAIXO), float(mus.get("inicio_s") or 0), dur,
                   float(mus.get("volume") or .1)) if plano["voz"] else float(mus.get("volume") or .12)
        filtros.append(f"[{k}:a]aresample=48000,volume={g},afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 1.5):.2f}:d=1.5[a{k}]")
        rotulos.append(f"[a{k}]")
    for e in doc.get("efeitos") if isinstance(doc.get("efeitos"), list) else []:
        f = achar(e.get("arquivo"), pasta) if isinstance(e, dict) else None
        if not f:
            continue
        if e.get("so_voz"):   # clipe real com música de fundo: fica só a voz dele (Demucs), pra não brigar com a trilha
            try:
                sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
                import midia_local as _ml
                f = _ml.so_voz_cache(f)
            except Exception as ex:
                print(f"aviso: so_voz falhou em {f.name} ({str(ex)[:80]}); ficou o som inteiro")
        k = len(rotulos)
        ms = int(float(e.get("t", 0)) * 1000)
        entradas += ["-i", str(f)]
        corta = f"atrim=0:{float(e['dur']):.3f},afade=t=out:st={max(0, float(e['dur']) - .12):.3f}:d=0.12," if e.get("dur") else ""
        vol = float(e.get("volume") or .3)
        if "clipes/" in str(e.get("arquivo")) and plano["voz"]:   # som de clipe real: medido e posto por baixo da voz
            vol = min(vol, _ganho(f, VOZ_LUFS - CLIPE_ABAIXO, 0, float(e.get("dur") or 0) or None, vol))
        filtros.append(f"[{k}:a]aresample=48000,{corta}volume={vol},adelay={ms}|{ms}[a{k}]")   # dur: som do clipe acaba com o plano
        rotulos.append(f"[a{k}]")
    if not rotulos:
        return None
    filtros.append("".join(rotulos) + f"amix=inputs={len(rotulos)}:normalize=0:duration=longest,"
                   f"apad,atrim=0:{dur:.3f},loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:curve=exp:st={max(0, dur - .6):.3f}:d=0.6[out]")
    saida.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", ";".join(filtros), "-map", "[out]",
                        "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(saida)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("o som não saiu: " + (r.stderr or "").strip()[-300:])
    return saida


# ───────────────────────────── navegador ─────────────────────────────

class _Servidor(http.server.SimpleHTTPRequestHandler):
    """/ = pasta do motor (index.html); /f/<caminho absoluto> = mídia (só dentro das pastas liberadas)."""
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


class _Http(http.server.ThreadingHTTPServer):
    request_queue_size = 512   # vários navegadores pedindo quadros ao mesmo tempo
    daemon_threads = True


def url(p: Path) -> str:
    return "/f" + urllib.parse.quote(str(Path(p).resolve()))


def servir(*raizes: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    _Servidor.raizes = tuple(Path(r).resolve() for r in raizes)
    srv = _Http(("127.0.0.1", 0), functools.partial(_Servidor, directory=str(AQUI)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def achar_frase(img: Path, frase: str) -> list[dict]:
    """Onde a frase está no print (OCR do tesseract, grátis): uma caixa por linha, em % do print. Cache em <img>.ocr.json."""
    import json as _j, re, unicodedata
    cache = img.with_suffix(img.suffix + ".ocr.json")
    if cache.is_file() and cache.stat().st_mtime >= img.stat().st_mtime:
        pal = _j.loads(cache.read_text())
    else:
        r = subprocess.run(["tesseract", str(img), "-", "--psm", "3", "-l", "por+eng", "tsv"], capture_output=True, text=True)
        pal = []
        for l in r.stdout.splitlines()[1:]:
            c = l.split("\t")
            if len(c) >= 12 and c[11].strip():
                pal.append({"b": int(c[2]), "p": int(c[3]), "l": int(c[4]), "x": int(c[6]), "y": int(c[7]), "w": int(c[8]), "h": int(c[9]), "t": c[11]})
        cache.write_text(_j.dumps(pal))
    from PIL import Image
    W, H = Image.open(img).size
    norm = lambda t: unicodedata.normalize("NFKD", re.sub(r"[^\w]", "", t.lower())).encode("ascii", "ignore").decode()
    alvo = [norm(w) for w in frase.split() if norm(w)]
    ws = [dict(w, n=norm(w["t"])) for w in pal if norm(w["t"])]
    for i in range(len(ws) - len(alvo) + 1):
        if all(ws[i + j]["n"] == alvo[j] for j in range(len(alvo))):
            linhas: dict = {}
            for w in ws[i:i + len(alvo)]:
                linhas.setdefault((w["b"], w["p"], w["l"]), []).append(w)
            out = []
            for ws_ in linhas.values():
                x0, y0 = min(w["x"] for w in ws_), min(w["y"] for w in ws_)
                x1, y1 = max(w["x"] + w["w"] for w in ws_), max(w["y"] + w["h"] for w in ws_)
                pad = (y1 - y0) * .25
                out.append({"x": round(100 * (x0 - pad) / W, 2), "y": round(100 * (y0 - pad) / H, 2),
                            "w": round(100 * (x1 - x0 + 2 * pad) / W, 2), "h": round(100 * (y1 - y0 + 2 * pad) / H, 2)})
            return out
    return []


def _quadros_fala(c: dict, plano: dict, pasta: Path) -> list[Path]:
    """Os JPG do vídeo do João de `de` a `ate` (30 fps), em <pasta>/work/fala-quadros/<de>_<ate>_<versão do vídeo>/. Cena nova ou vídeo
    trocado extrai de novo; o resto vem do cache. Quadro k = segundo de + k/fps, o mesmo que a página mostra no seek."""
    v = achar(plano.get("fala"), pasta)
    if not v:
        return []
    fps, n = plano["fps"], max(1, round((c["ate"] - c["de"]) * plano["fps"]))
    d = pasta / "work" / "fala-quadros" / f"{c['de']:.3f}_{c['ate']:.3f}_{int(v.stat().st_mtime)}"
    fez = sorted(d.glob("*.jpg"))
    if len(fez) < n:
        d.mkdir(parents=True, exist_ok=True)
        for x in fez:
            x.unlink()
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{c['de']:.3f}", "-i", str(v), "-t", f"{n / fps + .05:.3f}",
                        "-vf", f"fps={fps}", "-q:v", "4", str(d / "%05d.jpg")], check=True)
        fez = sorted(d.glob("*.jpg"))
    return fez[:n]


def _luminancia(arq: Path) -> float:
    """Brilho médio da parte de dentro da imagem (o fundo vivo faz zoom de 1,3 a 1,4 e a borda sai) de 0 a 1, miniatura 48 px."""
    try:
        from PIL import Image
        with Image.open(arq) as im:
            w, h = im.size
            g = im.convert("L").crop((int(w * .18), int(h * .18), int(w * .82), int(h * .82))).resize((48, 48))
        px = g.tobytes()
        return round(sum(px) / len(px) / 255, 3)
    except Exception:
        return .4


def _estilo_icone(c: dict, arq: Path) -> dict:
    """Ícone com a LOGO real (PNG com transparência ou arquivo "logo" no nome) entra colorido, inteiro e sobre um disco: claro se a logo é
    escura, escuro se é clara. Foto da coisa segue em P&B preenchendo o círculo. `logo: true|false` no cenas.json manda."""
    try:
        from PIL import Image
        with Image.open(arq) as im:
            rgba = im.convert("RGBA")
        a = rgba.getchannel("A")
        transparente = a.getextrema()[0] < 200
        logo = c["logo"] if "logo" in c else (transparente or "logo" in arq.stem.lower())
        if not logo:
            return {"logo": False}
        rgba.thumbnail((160, 160))
        d = rgba.tobytes()
        px = [(d[i], d[i + 1], d[i + 2]) for i in range(0, len(d), 4) if d[i + 3] > 128]
        lum = sum(.3 * r + .59 * g + .11 * b for r, g, b in px) / max(1, len(px)) if px else 255
        return {"logo": True, "disco": "claro" if lum < 95 else "escuro"}
    except Exception:
        return {"logo": bool(c.get("logo"))}


def _pagina(plano: dict, pasta: Path) -> dict:
    """O que a página recebe em window.PLANO: as cenas com a mídia já em /f/... (imagem, video)."""
    cenas = []
    for c in plano["cenas"]:
        c = dict(c)
        if isinstance(c.get("grifos"), list) and c.get("imagem") and achar(c["imagem"], pasta):   # grifo pela frase: o OCR acha a linha
            gs = []
            for g in c["grifos"]:
                if isinstance(g, dict) and g.get("frase") and "x" not in g:
                    caixas = achar_frase(achar(c["imagem"], pasta), g["frase"])
                    t0 = g.get("t")
                    for k, cx in enumerate(caixas):
                        gs.append(dict(cx, t=(t0 + .3 * k) if t0 is not None else None))
                elif isinstance(g, dict) and "x" in g:
                    gs.append(g)
            c["grifos"] = gs
        if c.get("fundo_vivo"):   # fundo vivo: a imagem (ou o quadro do meio de um clipe) que a página desfoca atrás da peça
            f = _fundo_arquivo(c["fundo_vivo"], pasta) if isinstance(c["fundo_vivo"], str) else None
            c["fundo_vivo"] = url(f) if f else None
            if f:   # a página acerta o brilho pela imagem: foto escura sobe, print branco desce (média ~0,27, texto branco sempre lê)
                c["fundo_lum"] = _luminancia(f)
        if c.get("tipo") == "icone" and c.get("imagem") and achar(c["imagem"], pasta):
            c.update(_estilo_icone(c, achar(c["imagem"], pasta)))
        for k in ("imagem", "video"):
            if k in c:   # mídia que não existe sai da página (senão o 404 derruba o motor); a checagem avisa
                f = achar(c[k], pasta) if isinstance(c[k], str) else None
                c[k] = url(f) if f else None
        if c.get("tipo") == "fala":   # o João: quadros do fala.mp4 no tempo desta cena (um por quadro do vídeo), a página troca o src a cada seek
            c["quadros"] = [url(x) for x in _quadros_fala(c, plano, pasta)]
        if isinstance(c.get("quadros_de"), str) and not c.get("imagens"):   # clipe: pasta com os quadros do vídeo a 30 fps
            d = achar(c["quadros_de"], pasta)
            c["imagens"] = [str(x) for x in sorted(d.glob("*.jpg"))] if d and d.is_dir() else []
        if isinstance(c.get("pessoas"), list):   # recorte: PNG sem fundo de cada pessoa
            c["pessoas"] = [dict(x, imagem=url(achar(x["imagem"], pasta))) for x in c["pessoas"]
                            if isinstance(x, dict) and isinstance(x.get("imagem"), str) and achar(x["imagem"], pasta)]
        if isinstance(c.get("imagens"), list):   # rajada, colagem, dividido, clipe
            c["imagens"] = [url(f) for f in (achar(x, pasta) for x in c["imagens"] if isinstance(x, str)) if f]
        if isinstance(c.get("msgs"), list):      # zap: imagem dentro da mensagem
            c["msgs"] = [dict(m, imagem=url(achar(m["imagem"], pasta))) if isinstance(m, dict) and m.get("imagem") and achar(m["imagem"], pasta)
                         else {k: v for k, v in m.items() if k != "imagem"} for m in c["msgs"] if isinstance(m, dict)]
        cenas.append(c)
    return {"total": plano["total"], "cenas": cenas, "largura": plano["largura"], "altura": plano["altura"],
            "fps": plano["fps"], "palavras": plano.get("palavras", []), "legenda": plano.get("legenda", True),
            "legenda_y": plano.get("legenda_y"), "marca": plano.get("marca")}


def abrir(p, porta: int, pagina: dict):
    nav = p.chromium.launch()
    pg = nav.new_page(viewport={"width": pagina["largura"], "height": pagina["altura"]}, device_scale_factor=1)
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pg.add_init_script("window.PLANO = " + json.dumps(pagina, ensure_ascii=False) + ";")
    # Muitos clipes = milhares de quadros <img>: o evento "load" do goto estourava (30 s) com a máquina carregada. Espera só o HTML
    # (domcontentloaded), tenta de novo uma vez e dá a "pronto" (fontes + quadros decodificados) um prazo que cresce com a imagem (31-out-2026).
    n_img = sum(len(c.get("imagens") or []) for c in pagina.get("cenas", []))
    for tentativa in (1, 2):
        try:
            pg.goto(f"http://127.0.0.1:{porta}/index.html", wait_until="domcontentloaded", timeout=120000)
            break
        except Exception:
            if tentativa == 2:
                raise SystemExit("o motor não abriu a página (2 tentativas): " + " | ".join(erros[:3]))
    try:
        pg.wait_for_function("window.seek && window.pronto", timeout=min(900000, 90000 + n_img * 40))
    except Exception:
        raise SystemExit("o motor não carregou: " + " | ".join(erros[:3]))
    if erros:
        raise SystemExit("erro no motor: " + erros[0])
    return nav, pg


def _codec() -> list[str]:
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "h264_videotoolbox" in enc:
        return ["-c:v", "h264_videotoolbox", "-b:v", "14M", "-maxrate", "18M", "-bufsize", "28M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]


def _trecho(porta: int, pagina_json: str, f0: int, f1: int, fps: int, saida: str, codec: list[str]) -> str:
    """Um processo: abre o motor e grava os quadros [f0, f1) num mp4 parcial."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            nav, pg = abrir(p, porta, json.loads(pagina_json))
        except SystemExit as e:   # SystemExit num processo filho mata o processo sem avisar o pai
            raise RuntimeError(str(e)) from None
        ff = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps),
                               "-c:v", "mjpeg", "-i", "-", *codec, "-pix_fmt", "yuv420p", "-r", str(fps), saida],
                              stdin=subprocess.PIPE)
        for f in range(f0, f1):
            pg.evaluate("t => seek(t)", f / fps)
            ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
        ff.stdin.close()
        ff.wait()
        nav.close()
    return saida


# ───────────────────────────── storyboard e conferência ─────────────────────────────

def _fonte(tam: int):
    from PIL import ImageFont
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if Path(f).exists():
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}".replace(".", ",")


def _quebrar(txt: str, fonte, largura: int, draw) -> list[str]:
    linhas, cur = [], ""
    for w in txt.split():
        if cur and draw.textlength(cur + " " + w, font=fonte) > largura:
            linhas.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return linhas + [cur] if cur else linhas


def storyboard(pg, plano: dict, out: Path, rodape: list[str], falta: list[str]) -> Path:
    """Um quadro por cena (no fim dela, quando tudo já entrou), 4 colunas: 'N. tipo · 0:12,3' e a fala embaixo.
    Rodapé: o som e, em vermelho, o que a checagem reprova."""
    from io import BytesIO
    from PIL import Image, ImageDraw
    vertical = plano["altura"] >= plano["largura"]
    cw, ch = (360, round(360 * plano["altura"] / plano["largura"])) if vertical else (480, round(480 * plano["altura"] / plano["largura"]))
    faixa, f1, f2 = 150, _fonte(24), _fonte(21)
    cols = max(1, min(4 if vertical else 3, len(plano["cenas"])))
    cel = []
    for c in plano["cenas"]:
        pg.evaluate("t => seek(t)", round(max(c["de"] + .7 * (c["ate"] - c["de"]), c["ate"] - .12), 3))
        im = Image.open(BytesIO(pg.screenshot(type="png"))).convert("RGB").resize((cw, ch), Image.LANCZOS)
        cx = Image.new("RGB", (cw, ch + faixa), (250, 247, 242))
        cx.paste(im, (0, 0))
        d = ImageDraw.Draw(cx)
        d.text((12, ch + 10), f"{c['n']}. {c['tipo']} · {mmss(c['de'])}", font=f1, fill=(30, 30, 30))
        for k, l in enumerate(_quebrar("“" + str(c.get("fala") or c.get("texto") or "(respiro)") + "”", f2, cw - 24, d)[:4]):
            d.text((12, ch + 44 + k * 25), l, font=f2, fill=(70, 60, 60))
        cel.append(cx)
    larg = cols * (cw + 12) + 12
    med = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    fr = _fonte(26)
    linhas = [(l, (240, 236, 228)) for r in rodape for l in _quebrar(r, fr, larg - 32, med)]
    linhas += [(l, (255, 120, 110)) for m in falta[:4] for l in _quebrar("Falta: " + m, fr, larg - 32, med)]
    rod = 30 + 36 * len(linhas)
    n_l = max(1, -(-len(cel) // cols))
    folha = Image.new("RGB", (larg, n_l * (ch + faixa + 12) + 12 + rod), (40, 36, 44))
    for i, cx in enumerate(cel):
        folha.paste(cx, (12 + (i % cols) * (cw + 12), 12 + (i // cols) * (ch + faixa + 12)))
    for k, (l, cor) in enumerate(linhas):
        ImageDraw.Draw(folha).text((16, folha.height - rod + 16 + 36 * k), l, font=fr, fill=cor)
    dst = out / "storyboard.jpg"
    folha.save(dst, quality=88)
    return dst


def som_txt(doc: dict, plano: dict) -> str:
    mus = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    efe = [e for e in doc.get("efeitos") or [] if isinstance(e, dict)] if isinstance(doc.get("efeitos"), list) else []
    return (f"{len(plano['cenas'])} cenas · {mmss(plano['total'])} · voz: {'sim' if plano['voz'] else 'não'} · "
            f"música: {Path(mus['arquivo']).name if mus.get('arquivo') else 'sem'} · efeitos: {len(efe)}")


def exemplo_principal() -> Path | None:
    """O 1º de "exemplos" no formatos/<FORMATO>/formato.json."""
    pasta = ESTUDIO / "formatos" / FORMATO
    try:
        exs = json.loads((pasta / "formato.json").read_text(encoding="utf-8")).get("exemplos") or []
    except (OSError, ValueError):
        return None
    v = pasta / str((exs[0] if exs and isinstance(exs[0], dict) else {}).get("arquivo") or "")
    return v if exs and v.is_file() else None


def _folha(video: Path, destino: Path) -> Path | None:
    """A mesma folha do exemplo (1 quadro a cada 4 s, segundo marcado): formatos.py fazer_folha; sem ele, ffmpeg puro."""
    try:
        sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
        from formatos import fazer_folha
        return fazer_folha(video, destino)
    except Exception:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", "fps=1/4,scale=216:-2,tile=6x4",
                            "-frames:v", "1", str(destino)], capture_output=True)
        return destino if not r.returncode and destino.is_file() else None


def folha_comparacao(video: Path, qa: Path) -> Path | None:
    """Exemplo principal em cima, este vídeo embaixo: o João compara os dois de uma vez."""
    from PIL import Image, ImageDraw
    partes = []
    for rot, v in (("EXEMPLO PRINCIPAL", exemplo_principal()), ("ESTE VÍDEO", video)):
        f = _folha(v, qa / f"_folha-{len(partes)}.jpg") if v else None
        if f:
            partes.append((rot, Image.open(f).convert("RGB")))
            f.unlink()
    if not partes:
        return None
    larg = max(im.width for _, im in partes)
    folha = Image.new("RGB", (larg, sum(im.height + 56 for _, im in partes)), (24, 22, 26))
    y = 0
    for rot, im in partes:
        ImageDraw.Draw(folha).text((14, y + 12), rot, font=_fonte(30), fill=(245, 240, 230))
        folha.paste(im, (0, y + 56))
        y += im.height + 56
    dst = qa / "folha-comparacao.jpg"
    folha.save(dst, quality=86)
    return dst


def conferir(doc: dict, pasta: Path, out: Path, video: Path) -> dict:
    """Reprova sozinho (tamanho, duração, som) e grava qa/conferir.json e qa/folha-comparacao.jpg. O olho no lado a
    lado com o exemplo continua obrigatório: pior que o exemplo não sai."""
    qa = out / "qa"
    plano = planejar(doc, pasta)
    ch = checar(doc, pasta, plano)
    motivos, num = list(ch["motivos"]), dict(ch["numeros"])
    if video.is_file():
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True)
        pr = json.loads(r.stdout or "{}")
        st = next((s for s in pr.get("streams") or [] if s.get("codec_type") == "video"), {})
        tem_som = any(s.get("codec_type") == "audio" for s in pr.get("streams") or [])
        dur = round(float((pr.get("format") or {}).get("duration") or 0), 2)
        num["video"] = {"arquivo": str(video), "largura": st.get("width"), "altura": st.get("height"), "duracao_s": dur}
        if (st.get("width"), st.get("height")) != (plano["largura"], plano["altura"]):
            motivos.append(f"O vídeo tem {st.get('width')}x{st.get('height')}: tem que ser {plano['largura']}x{plano['altura']}")
        if abs(dur - plano["total"]) > .5:
            motivos.append(f"O vídeo tem {br(dur)} s e as cenas somam {br(plano['total'])} s")
        if (plano["voz"] or (doc.get("musica") or {}).get("arquivo")) and not tem_som:
            motivos.append("O vídeo saiu sem som")
        try:   # dinamismo medido no mp4 final (REGRAS.md G26): parado demais reprova, o resto vira número + aviso
            sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
            import conferir_video as _cv
            av_d, num_d = _cv.checar_dinamismo(video, FORMATO)
            num["dinamismo"] = num_d
            motivos += [a for a in av_d if a.startswith("Parado demais")]
            num["avisos_dinamismo"] = [a for a in av_d if not a.startswith("Parado demais")]
        except Exception as e:
            num["dinamismo_erro"] = str(e)[:120]
        qa.mkdir(parents=True, exist_ok=True)
        f = folha_comparacao(video, qa)
        num["folha"] = str(f) if f else None
        if not exemplo_principal():
            num["aviso"] = "o formato ainda não tem exemplo principal: a folha mostra só este vídeo"
    else:
        num["video"] = None
        motivos.append(f"Vídeo não encontrado: {video} (rode o render antes do --conferir)")
    res = {"ok": not motivos, "motivos": motivos, "numeros": num}
    _gravar(qa / "conferir.json", res)
    return res


# ───────────────────────────── principal ─────────────────────────────

def _cenas_padrao() -> Path:
    for p in (Path.cwd() / "cenas.json", AQUI / "cenas.json"):
        if p.exists():
            return p
    raise SystemExit("cenas.json não encontrado: rode de dentro da pasta do vídeo ou passe --cenas <arquivo> (exemplo: cenas-modelo.json)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Motor do formato (genérico do Estúdio)")
    ap.add_argument("--cenas", type=Path)
    ap.add_argument("--out", type=Path, help="pasta de saída (padrão: a do cenas.json)")
    ap.add_argument("--saida", type=Path, help="mp4 final (padrão: <out>/<saida do cenas.json ou video.mp4>)")
    ap.add_argument("--ate", type=float, help="só os N primeiros segundos (teste.mp4)")
    ap.add_argument("--quadro", help="segundos separados por vírgula ou 'cenas' (um PNG no meio de cada cena)")
    ap.add_argument("--storyboard", action="store_true")
    ap.add_argument("--conferir", action="store_true")
    ap.add_argument("--video", type=Path, help="mp4 a conferir (padrão: o vídeo final)")
    ap.add_argument("--sem-som", action="store_true", help="no --storyboard, não monta a previa-som.m4a")
    ap.add_argument("--processos", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    a = ap.parse_args()
    arq = (a.cenas or _cenas_padrao()).resolve()
    pasta = arq.parent
    out = (a.out or pasta).resolve()
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(arq.read_text(encoding="utf-8"))
    final = (a.saida or out / str(doc.get("saida") or "video.mp4")).resolve()
    if a.conferir:
        r = conferir(doc, pasta, out, (a.video or final).resolve())
        print(f"conferência: {out / 'qa' / 'conferir.json'}" + (f" · folha: {r['numeros'].get('folha')}" if r["numeros"].get("folha") else ""))
        if r["ok"]:
            print("APROVADO pela conferência (agora olhe a folha lado a lado: pior que o exemplo não sai)")
            return
        print("REPROVADO:\n- " + "\n- ".join(r["motivos"]))
        sys.exit(1)
    t_ini = time.time()
    plano = planejar(doc, pasta)
    avisos_locais: list[str] = []
    aplicar_locais(plano, pasta, avisos_locais)
    for av in avisos_locais:
        print("aviso:", av)
    pagina = _pagina(plano, pasta)
    srv, porta = servir(AQUI, pasta, out, ESTUDIO)
    print(f"duração {plano['total']:.2f}s · {len(plano['cenas'])} cenas")
    if a.quadro or a.storyboard:
        from playwright.sync_api import sync_playwright
        ch = checar(doc, pasta, plano) if a.storyboard else None
        if ch is not None and not a.sem_som:
            try:
                p_som = montar_som(doc, plano, pasta, plano["total"], out / "previa-som.m4a")
                if p_som:
                    print(f"prévia do som: {p_som}")
            except SystemExit as e:
                ch["motivos"].append(f"A prévia do som não saiu: {e}")
        with sync_playwright() as p:
            nav, pg = abrir(p, porta, pagina)
            if ch is not None:
                print(f"storyboard: {storyboard(pg, plano, out, [som_txt(doc, plano)], ch['motivos'])}")
                _gravar(out / "qa" / "checagem.json", {**ch, "ok": not ch["motivos"]})
            if a.quadro:
                d = out / "quadros"
                d.mkdir(exist_ok=True)
                alvos = ([((c["de"] + c["ate"]) / 2, f"{c['n']:02d}-{c['tipo']}") for c in plano["cenas"]] if a.quadro == "cenas"
                         else [(float(x), f"{float(x):06.2f}") for x in a.quadro.split(",") if x.strip()])
                for t, nome in alvos:
                    pg.evaluate("t => seek(t)", t)
                    pg.screenshot(path=str(d / f"{nome}.png"))
                print(f"quadros: {len(alvos)} em {d}")
            nav.close()
        srv.shutdown()
        if ch is not None:
            if ch["motivos"]:
                print("REPROVADO na checagem (corrija o cenas.json e rode o --storyboard de novo):\n- " + "\n- ".join(ch["motivos"]))
                sys.exit(1)
            print("APROVADO na checagem: pode mostrar o storyboard")
        return
    dur = plano["total"] if a.ate is None else min(a.ate, plano["total"])
    if a.ate is not None:
        final = out / "teste.mp4"
    fps = plano["fps"]
    n = max(1, int(round(dur * fps)))
    k = max(1, min(a.processos, n // (fps * 3) or 1))
    lim = [round(n * j / k) for j in range(k + 1)]
    partes = [str(out / f"_parte{j}.mp4") for j in range(k)]
    pagina_json, codec = json.dumps(pagina, ensure_ascii=False), _codec()
    from concurrent.futures import ProcessPoolExecutor
    try:
        with ProcessPoolExecutor(k, mp_context=mp.get_context("spawn")) as ex:
            list(ex.map(_trecho, *zip(*[(porta, pagina_json, lim[j], lim[j + 1], fps, partes[j], codec) for j in range(k)])))
    except Exception as e:
        raise SystemExit(f"o render parou: {e}")
    finally:
        srv.shutdown()
    lista = out / "_partes.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes))
    mudo = out / "_mudo.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo)], check=True)
    trilha = montar_som(doc, plano, pasta, dur, out / "_trilha.m4a")
    if trilha:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mudo), "-i", str(trilha), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mudo), "-c", "copy", "-movflags", "+faststart", str(final)], check=True)
    for p in partes + [str(mudo), str(lista)] + ([str(trilha)] if trilha else []):
        Path(p).unlink(missing_ok=True)
    print(f"quadros: {n} ({k} processos) · total {time.time() - t_ini:.0f}s")
    print(f"pronto: {final}")


if __name__ == "__main__":
    main()
