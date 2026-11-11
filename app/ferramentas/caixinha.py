#!/usr/bin/env python3
"""
caixinha — a caixa de pergunta do Stories do Instagram (formato Caixinha de perguntas), como camada do editor.

Faixa escura com o título + parte branca com a pergunta, em SF Pro (a fonte do iPhone, /System/Library/Fonts/SFNS.ttf).
Medidas tiradas pixel a pixel do print que o João aprovou (22-out-2026, caixa de 599 px) e escaladas pra caixa de
708 px em 1080x1920. Só o texto e a altura mudam: fonte, tamanho e margens são fixos. Texto longo ganha linha e a
caixa cresce pra baixo, com as mesmas margens.

    camada.json do formato: {"tipo": "caixinha", "texto": <pergunta>, "titulo": <faixa escura>, "y": <topo da caixa>, ...}
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SF = "/System/Library/Fonts/SFNS.ttf"   # eixos: largura, tamanho óptico, GRAD, peso
CAIXA_L, RAIO = 708, 24
TEXTO_MAX = 600                         # largura máxima de cada linha (título e pergunta)
TITULO_PADRAO = "O que você quer saber?"
TOPO_CIMA, CENTRO_PEITO = 255, 1430     # em cima: logo abaixo da zona de topo do Instagram; peito: abaixo do queixo
COR_FAIXA, COR_TITULO = (38, 38, 38), (250, 250, 250)      # #262626, #FAFAFA
COR_FUNDO, COR_PERGUNTA = (255, 255, 255), (38, 38, 38)
# (tamanho px, tamanho óptico, peso, até a 1ª linha de base, entre linhas, da última linha de base ao fim do bloco)
TITULO = (35.6, 24, 700, 58, 45, 45)
PERGUNTA = (47.2, 20, 680, 98, 64, 59)


def _fonte(px, opsz, peso):
    f = ImageFont.truetype(SF, px)
    f.set_variation_by_axes([100, opsz, 400, peso])
    return f


def quebrar(d, texto: str, f, largura: int = TEXTO_MAX) -> list[str]:
    linhas = []
    for bloco in (texto or "").splitlines() or [""]:   # Enter = quebra escolhida
        atual = ""
        for p in bloco.split():
            t = f"{atual} {p}".strip()
            if atual and d.textlength(t, font=f) > largura:
                linhas.append(atual)
                atual = p
            else:
                atual = t
        linhas.append(atual)
    return linhas


def _bloco(n: int, spec) -> int:
    return round(spec[3] + spec[4] * (n - 1) + spec[5])


def medir(pergunta: str, titulo: str = TITULO_PADRAO):
    """(linhas do título, linhas da pergunta, altura da faixa, altura total)."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    lt = quebrar(d, titulo, _fonte(*TITULO[:3]))
    lp = quebrar(d, pergunta, _fonte(*PERGUNTA[:3]))
    faixa = _bloco(len(lt), TITULO)
    return lt, lp, faixa, faixa + _bloco(len(lp), PERGUNTA)


def topo_padrao(posicao: str, pergunta: str, titulo: str = TITULO_PADRAO) -> int:
    return TOPO_CIMA if posicao != "peito" else int(CENTRO_PEITO - medir(pergunta, titulo)[3] / 2)


def png(p: dict) -> Image.Image:
    """A camada RGBA 1080x1920: p["texto"] = pergunta, p["titulo"], p["y"] = topo da caixa."""
    pergunta, titulo = str(p.get("texto") or "").strip(), str(p.get("titulo") or TITULO_PADRAO).strip()
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not pergunta:
        return img
    topo = int(float(p.get("y") or TOPO_CIMA))
    lt, lp, faixa, h = medir(pergunta, titulo)
    k = 4   # desenha a caixa em 4x e reduz: canto liso como no print
    m = Image.new("RGBA", (CAIXA_L * k, h * k), (0, 0, 0, 0))
    dm = ImageDraw.Draw(m)
    dm.rounded_rectangle([0, 0, CAIXA_L * k - 1, h * k - 1], RAIO * k, fill=COR_FUNDO + (255,))
    dm.rounded_rectangle([0, 0, CAIXA_L * k - 1, (faixa + RAIO) * k], RAIO * k, fill=COR_FAIXA + (255,),
                         corners=(True, True, False, False))
    dm.rectangle([0, faixa * k, CAIXA_L * k, (faixa + RAIO) * k + 2], fill=COR_FUNDO + (255,))
    img.alpha_composite(m.resize((CAIXA_L, h), Image.LANCZOS), ((W - CAIXA_L) // 2, topo))
    d = ImageDraw.Draw(img)
    for linhas, spec, cor, y0 in ((lt, TITULO, COR_TITULO, topo), (lp, PERGUNTA, COR_PERGUNTA, topo + faixa)):
        f = _fonte(*spec[:3])
        for i, l in enumerate(linhas):
            d.text((W / 2, y0 + spec[3] + spec[4] * i), l, font=f, fill=cor, anchor="ms")
    return img
