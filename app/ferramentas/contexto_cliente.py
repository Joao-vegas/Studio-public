"""Contexto do cliente/produto pro "Me ajuda a pensar": o que o João já tem guardado sobre a oferta.

Fonte principal: o swipe-file dele (~/Projetos/Sistema Próprios/swipe-file/biblioteca/<pessoa>/), que tem pessoa.md,
ofertas/<oferta>/oferta.md (preço, mecanismo, dor, na língua do cliente) e anuncios/<anuncio>/anuncio.md.
Acha a pessoa pelo nome do cliente do Estúdio (Cliente2 → cliente2-di-fiori) e a oferta pelas palavras do pedido
("marca3" → marca3-...). Tudo local, sem IA: é só leitura de arquivo, rápido e grátis.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

SWIPE = Path.home() / "Projetos" / "Sistema Próprios" / "swipe-file" / "biblioteca"
LIMITE = 6000
VAZIAS = {"para", "pra", "com", "sem", "uma", "uns", "que", "quero", "anuncio", "anúncio", "video", "vídeo", "roteiro",
          "ajude", "ajuda", "pensar", "personagem", "personagens", "fazer", "sobre", "cliente", "projeto", "isso", "esse",
          "essa", "tipo", "meio", "algo", "mais", "menos", "como", "onde", "quem", "qual", "pelo", "pela", "dele", "dela"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _palavras(s: str) -> set[str]:
    return {w for w in _norm(s).split() if len(w) >= 4 and w not in VAZIAS}


def _campo(md: str, nome: str) -> str:
    m = re.search(rf"^{nome}:\s*\"?(.+?)\"?\s*$", md, re.M)
    return m.group(1).strip() if m else ""


def _corpo_oferta(md: str, n: int = 3200) -> str:
    """Do arquivo de oferta, só o que serve pra roteiro: título, promessa e as seções 1 a 3 (oferta, mecanismo, dor)."""
    cab = [x for x in (_campo(md, "titulo_pagina") or _campo(md, "titulo"), _campo(md, "prego")) if x]
    a = md.find("### 1.")
    b = md.find("### 4.")
    trecho = md[a:b if b > a else a + n] if a >= 0 else re.sub(r"^---.*?---", "", md, flags=re.S)
    return ("\n".join(cab) + "\n" + trecho.strip())[:n]


def achar(cliente_nome: str, ideia: str) -> dict:
    """{"pessoa": Path|None, "ofertas": [Path], "anuncios": [titulos]} que casam com o cliente e o pedido."""
    out = {"pessoa": None, "ofertas": [], "anuncios": []}
    if not SWIPE.is_dir():
        return out
    termos = _palavras(ideia)
    cli = _norm(cliente_nome).split()
    melhor, nota_melhor = None, 0
    for p in sorted(x for x in SWIPE.iterdir() if x.is_dir()):
        nome = _palavras(p.name)
        nota = (3 if cli and cli[0] in _norm(p.name).split() else 0) + len(termos & nome)
        ofs = [(len(termos & _palavras(o.name)), o) for o in (p / "ofertas").iterdir() if o.is_dir()] if (p / "ofertas").is_dir() else []
        nota += max([n for n, _ in ofs] or [0])
        if nota > nota_melhor:
            melhor, nota_melhor = p, nota
    if not melhor:
        return out
    out["pessoa"] = melhor
    ofs = sorted(((len(termos & _palavras(o.name)), o) for o in (melhor / "ofertas").iterdir() if o.is_dir())
                 if (melhor / "ofertas").is_dir() else [], key=lambda x: -x[0])
    out["ofertas"] = [o for n, o in ofs if n > 0][:2] or [o for _, o in ofs][:1]
    for a in sorted((melhor / "anuncios").iterdir() if (melhor / "anuncios").is_dir() else []):
        md = a / "anuncio.md"
        if md.is_file():
            t = _campo(md.read_text(encoding="utf-8", errors="ignore"), "titulo")
            if t:
                out["anuncios"].append(t)
    out["anuncios"] = out["anuncios"][:8]
    return out


def contexto(cliente_nome: str, ideia: str, limite: int = LIMITE) -> str:
    """Texto pronto pra ir no prompt (vazio se não achou nada)."""
    a = achar(cliente_nome, ideia)
    if not a["pessoa"]:
        return ""
    partes = []
    pm = a["pessoa"] / "pessoa.md"
    if pm.is_file():
        md = pm.read_text(encoding="utf-8", errors="ignore")
        info = [f"{c}: {_campo(md, c)}" for c in ("nome", "nicho", "subnicho", "publico") if _campo(md, c)]
        partes.append("PESSOA (swipe-file): " + " · ".join(info))
    for o in a["ofertas"]:
        om = o / "oferta.md"
        if om.is_file():
            partes.append("OFERTA:\n" + _corpo_oferta(om.read_text(encoding="utf-8", errors="ignore")))
    if a["anuncios"]:
        partes.append("ANÚNCIOS QUE ELE JÁ TEM (pra variar o ângulo, não repetir): " + " | ".join(a["anuncios"]))
    return "\n\n".join(partes)[:limite]
