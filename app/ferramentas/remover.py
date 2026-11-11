#!/usr/bin/env python3
"""
remover — apagar simples (PLANO-2.0, item 14): estilo, pasta de vídeo de teste ou estudo saem com um botão e vão pra
lixeira do Estúdio (app/.lixeira/), de onde voltam com Restaurar em Configurações. Nada é apagado de vez por aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, lixeira_guardar  # noqa: E402

PROTEGIDOS = {"_modelo", "editorial"}   # a base dos formatos novos e o estilo em construção da 2.0


def remover_estilo(slug: str) -> str:
    """Tira o estilo do catálogo (formatos/<slug>). Os modelos dos clientes ficam onde estão."""
    p = (RAIZ / "formatos" / Path(slug).name)
    if slug in PROTEGIDOS or not (p / "formato.json").is_file():
        raise ValueError("Esse estilo não pode sair por aqui.")
    return lixeira_guardar({"formato": p}, {"tipo": "pasta", "rotulo": f"estilo {slug}", "volta": {"formato": f"formatos/{slug}"}})


def remover_pasta(rel: str, rotulo: str) -> str:
    """Tira uma pasta de trabalho (sandbox de vídeo ou estudo) da lista. Só pasta dentro do Estúdio e de tipo conhecido."""
    p = (RAIZ / rel).resolve()
    ok = RAIZ.resolve() in p.parents and p.is_dir() and (p.name.startswith("_sandbox-") or p.parent.name in (".estudos", ".estilos", ".variacoes") or (p.parent.name == "_conjuntos" and p.parent.parent.name == ".estilos") or (p.parent.name == "estudos" and p.parent.parent.parent.name == "formatos"))
    if not ok:
        raise ValueError("Essa pasta não pode sair por aqui.")
    return lixeira_guardar({"pasta": p}, {"tipo": "pasta", "rotulo": rotulo or p.name,
                                          "volta": {"pasta": str(p.relative_to(RAIZ.resolve()))}})


def restaurar_pasta(ident: str, info: dict) -> dict:
    import shutil
    from _comum import lixeira_item
    d = lixeira_item(ident)
    for apelido, destino in (info.get("volta") or {}).items():
        alvo = RAIZ / destino
        if alvo.exists():
            raise ValueError(f"já existe {destino}: renomeie antes de restaurar")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d / apelido), str(alvo))
    shutil.rmtree(d, ignore_errors=True)
    return {"cliente": "", "item": info.get("rotulo") or "item"}
