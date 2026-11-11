#!/usr/bin/env python3
"""Confere cada clientes/<Nome>/ contra o padrão e lista os desvios (só leitura, nunca mexe em nada).

Padrão: cliente é só a pele.
  clientes/<Nome>/identidade.json
  clientes/<Nome>/<x>Content/{entrada, material, modelos, output, transcricoes}   (as que ainda não nasceram podem faltar)
Fora disso é desvio: .env, README, automacao, documentacao, banco-* etc. Chave mora em app/.env; banco de imagem,
vídeo e música moram em acervo/.

Uso: python3 app/ferramentas/clientes_padrao.py [Cliente ...] [--json]   (sai com 1 se houver desvio)"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comum import RAIZ

PASTAS_CONTENT = ("entrada", "material", "modelos", "output", "transcricoes")
LIXO_TOLERADO = {".DS_Store", ".gitkeep"}

# nome (minúsculo) → explicação curta, pra falar em português simples
_CONHECIDOS = {
    ".env": "tem chave solta; as chaves ficam só em app/.env",
    ".env.example": "tem exemplo de chave; as chaves ficam só em app/.env",
    ".gitignore": "cliente não tem .gitignore próprio",
    "automacao": "tem scripts; os scripts moram em app/automacao/",
    "documentacao": "tem documentação; texto de cliente vira regra no modelo, não pasta",
    "readme.md": "tem README; a identidade do cliente fica no identidade.json",
    "aprendizado": "tem aprendizado solto; aprendizado fica no modelo (modelos/<modelo>/aprendizado/)",
    "remotion": "tem Remotion próprio; Remotion saiu do Estúdio (29-out-2026), animação nova é HTML próprio",
}


def _explica(nome: str, onde: str) -> str:
    baixo = nome.lower()
    if baixo.startswith("banco-"):
        return f"{onde}{nome}: tem banco de imagem/vídeo/música; isso mora só no acervo/"
    if baixo in _CONHECIDOS:
        return f"{onde}{nome}: {_CONHECIDOS[baixo]}"
    if baixo.startswith("readme"):
        return f"{onde}{nome}: {_CONHECIDOS['readme.md']}"
    if nome.startswith("."):
        return f"{onde}{nome}: arquivo/pasta escondido que não faz parte do padrão"
    return f"{onde}{nome}: não faz parte do padrão"


def conferir(pasta: Path) -> list[str]:
    """Desvios de UM cliente (lista vazia = dentro do padrão)."""
    pasta = Path(pasta)
    nome = pasta.name
    desvios: list[str] = []
    contents = [d for d in sorted(pasta.iterdir()) if d.is_dir() and d.name.endswith("Content")]
    if not (pasta / "identidade.json").is_file():
        desvios.append("falta o identidade.json")
    if not contents:
        desvios.append("falta a pasta <x>Content (ex.: vegasContent)")
    elif len(contents) > 1:
        desvios.append("tem mais de uma pasta Content: " + ", ".join(c.name for c in contents))
    for item in sorted(pasta.iterdir()):
        if item.name in LIXO_TOLERADO or item.name == "identidade.json" or item in contents:
            continue
        desvios.append(_explica(item.name, ""))
    for content in contents:
        if content.name == "Content":
            desvios.append("a pasta Content precisa de prefixo (ex.: vegasContent)")
        for item in sorted(content.iterdir()):
            if item.name in LIXO_TOLERADO:
                continue
            if item.name in PASTAS_CONTENT and item.is_dir():
                continue
            desvios.append(_explica(item.name, content.name + "/"))
    return desvios


def conferir_todos(raiz: Path | None = None, so: list[str] | None = None) -> dict[str, list[str]]:
    base = Path(raiz) if raiz else RAIZ / "clientes"
    res: dict[str, list[str]] = {}
    pastas = [d for d in sorted(base.iterdir(), key=lambda x: x.name.lower())
              if d.is_dir() and not d.name.startswith((".", "_"))] if base.is_dir() else []
    for d in pastas:
        if so and d.name.lower() not in {s.lower() for s in so}:
            continue
        res[d.name] = conferir(d)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clientes", nargs="*", help="só estes clientes (padrão: todos)")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    a = ap.parse_args()
    res = conferir_todos(so=a.clientes or None)
    if a.json:
        print(json.dumps({"ok": not any(res.values()), "clientes": res}, ensure_ascii=False, indent=1))
    else:
        for nome, desvios in res.items():
            if desvios:
                print(f"✗ {nome}")
                for d in desvios:
                    print(f"    - {d}")
            else:
                print(f"✓ {nome}")
        n = sum(1 for d in res.values() if d)
        print(f"\n{len(res)} cliente(s) conferido(s), {n} fora do padrão." if n else f"\n{len(res)} cliente(s) conferido(s), todos dentro do padrão.")
    return 1 if any(res.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
