#!/usr/bin/env python3
"""
elenco: o elenco de cada ESTILO que tem personagens (PLANO-2.0, item 7). Não é do cliente: é do estilo.

Hoje só o Explicador 3D tem. Estilo novo com personagens entra no registro ELENCOS (abaixo) e a tela /elenco/<slug> já funciona:
a base dos personagens vem do formato (formatos/<slug>/base/), o que o João muda fica em formatos/<slug>/elenco.json, só o que mudou:

    {"dentista": {"base": "dentista", "camisa": {"cor": "#c0392b"}},          # mesmo nome = troca o figurino do original
     "dr_paulo": {"base": "dentista", "pele": "#9a5f3c", "bigode": true}}      # nome novo, nascido de um base

O render.py do formato mescla na ordem: elenco.js <- elenco do estilo <- roteiro. Um elenco.json por cliente
(clientes/<C>/.../modelos/explicador-3d/elenco.json), se existir de antes, continua valendo POR CIMA do estilo (só leitura).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ler_json, gravar_json  # noqa: E402

FORMATO = "explicador-3d"   # o estilo que tem elenco hoje (a fileira "Personagem" do Criar e o render ainda são dele)

# Registro: slug do estilo -> como a tela desenha e valida o elenco dele. Estilo novo = uma entrada aqui (+ a base dele em
# formatos/<slug>/base/). "previa" diz à tela (static/elenco-previa.js) quais módulos do formato carregar pra desenhar o personagem.
ELENCOS = {
    FORMATO: {
        "titulo": "Explicador 3D",
        "frase": "Gente feia estilo GTA 2000: dentista, executivo, vovó... com roupa, cabelo e pele editáveis.",
        "base_js": "elenco.js",                                   # em formatos/<slug>/base/: export const ELENCO = { nome: {...} }
        "previa": {"personagem": "gente.js", "elenco": "elenco.js"},   # módulos de formatos/<slug>/base/ que a prévia importa
        "editor": "pessoa",                                       # qual conjunto de controles a tela mostra (cores, roupa, cabelo...)
        "campos": {"pele", "olhos", "cabelo", "camisa", "calca", "sapato", "bone", "oculos", "barba", "bigode", "mulher", "idade",
                   "corpo", "semente", "cabeca", "cabeca_larga", "alt", "larg"},
        "rotulos": {"medica": "Médica", "garcom": "Garçom", "vovo": "Vovó", "gerente": "Gerente", "influencer": "Influenciador"},
    },
}


def _cfg(slug: str) -> dict:
    if slug not in ELENCOS:
        raise ValueError(f"O estilo '{slug}' não tem elenco.")
    return ELENCOS[slug]


def existe(slug: str) -> bool:
    return slug in ELENCOS


def bases(slug: str = FORMATO) -> list[str]:
    """Os nomes dos personagens prontos (lidos do elenco.js do formato, na ordem dele)."""
    txt = (RAIZ / "formatos" / slug / "base" / _cfg(slug)["base_js"]).read_text(encoding="utf-8")
    corpo = txt.split("export const ELENCO = {", 1)[1].split("\nexport function", 1)[0]
    return re.findall(r"^  (\w+):\s*\{", corpo, flags=re.M)


def rotulo(nome: str, slug: str = FORMATO) -> str:
    return _cfg(slug)["rotulos"].get(nome) or nome.replace("_", " ").capitalize()


def rotulos(slug: str = FORMATO) -> dict:
    return {n: rotulo(n, slug) for n in bases(slug)}


def previa(slug: str = FORMATO) -> dict:
    """O que o navegador precisa pra desenhar: onde estão os módulos do formato e quais são."""
    return {"slug": slug, "base": f"/arquivo/formatos/{slug}/base/", **_cfg(slug)["previa"], "editor": _cfg(slug)["editor"]}


def arquivo(slug: str = FORMATO) -> Path:
    _cfg(slug)
    return RAIZ / "formatos" / slug / "elenco.json"


def ler(slug: str = FORMATO) -> dict:
    """O elenco do estilo ({nome: {base, ...troca}}); vazio se ninguém mexeu ainda."""
    d = ler_json(arquivo(slug), {})
    return d if isinstance(d, dict) else {}


def ler_cliente(cli: dict) -> dict:
    """Só leitura, compatível com o que já existia: elenco.json antigo do cliente (vale por cima do estilo no render)."""
    d = ler_json(cli["content"] / "modelos" / FORMATO / "elenco.json", {})
    return d if isinstance(d, dict) else {}


def estilos() -> list[dict]:
    """Os estilos que têm elenco, pra lista da tela /elenco: [{slug, titulo, frase, total, alterados}]."""
    out = []
    for slug, c in ELENCOS.items():
        el = ler(slug)
        prontos = bases(slug)
        out.append({"slug": slug, "titulo": c["titulo"], "frase": c["frase"], "total": len(prontos) + sum(1 for n in el if n not in prontos),
                    "alterados": len(el)})
    return out


def nome_valido(nome: str) -> str:
    n = unicodedata.normalize("NFD", str(nome or "")).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z0-9]+", "_", n).strip("_")
    if not n:
        raise ValueError("Dê um nome pro personagem.")
    return n[:40]


def salvar(slug: str, nome: str, base: str, troca: dict) -> str:
    """Grava {nome: {base, ...só o que mudou}} no elenco do estilo. Devolve o nome usado."""
    cfg = _cfg(slug)
    nome = nome_valido(nome)
    if base not in bases(slug):
        raise ValueError(f"O personagem-base '{base}' não existe.")
    if not isinstance(troca, dict):
        raise ValueError("A troca precisa ser um objeto.")
    desconhecido = set(troca) - cfg["campos"]
    if desconhecido:
        raise ValueError("Campo que o personagem não tem: " + ", ".join(sorted(desconhecido)))
    dados = ler(slug)
    dados[nome] = {"base": base, **troca}
    gravar_json(arquivo(slug), dados)
    return nome


def remover(slug: str, nome: str) -> bool:
    """Volta o personagem ao original (tira do elenco do estilo). Não apaga o arquivo."""
    dados = ler(slug)
    if nome not in dados:
        return False
    del dados[nome]
    gravar_json(arquivo(slug), dados)
    return True
