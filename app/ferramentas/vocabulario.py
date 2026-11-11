#!/usr/bin/env python3
"""Vocabulário do cliente pra transcrição (G5: nome próprio certo na legenda).

identidade.json → "palavras": ["Produto1", "Black Friday", "Produto"]. Duas coisas:
  prompt <Cliente|caminho>               imprime o texto (até ~200 letras) que vai no `-F prompt=` do Groq
  corrigir <words.json> <Cliente|caminho>  depois do Groq, troca a palavra em minúscula pela forma da lista ("black" → "Black")
O cliente pode ser o nome ou qualquer caminho dentro de clientes/<Nome>/ (o gerar.sh passa a própria pasta)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ler_json  # noqa: E402

LIMITE = 200


def cliente_de(x: str) -> str:
    p = Path(x)
    partes = p.parts
    return partes[partes.index("clientes") + 1] if "clientes" in partes and partes.index("clientes") + 1 < len(partes) else x


def palavras(cliente: str, raiz: Path | None = None) -> list[str]:
    d = ler_json((raiz or RAIZ) / "clientes" / cliente_de(cliente) / "identidade.json", {}) or {}
    return [str(p).strip() for p in (d.get("palavras") or []) if str(p).strip()]


def prompt(cliente: str, raiz: Path | None = None) -> str:
    out = ""
    for p in palavras(cliente, raiz):
        nova = (out + ", " if out else "") + p
        if len(nova) > LIMITE:
            break
        out = nova
    return out


def corrigir_lista(words: list[dict], vocab: list[str]) -> int:
    """Troca, em place, cada palavra (ou sequência de palavras) que casa com um termo do vocabulário sem diferença de caixa."""
    alvo = [(v.split(), v) for v in vocab]
    n = 0
    chave = lambda s: re.sub(r"[^\wÀ-ÿ]", "", str(s)).lower()  # noqa: E731
    for toks, _ in sorted(alvo, key=lambda a: -len(a[0])):
        k = len(toks)
        for i in range(len(words) - k + 1):
            if all(chave(words[i + j].get("word")) == chave(toks[j]) for j in range(k)):
                for j in range(k):
                    w = str(words[i + j].get("word"))
                    # mantém a pontuação que o Groq pôs, troca só as letras
                    novo = re.sub(r"[\wÀ-ÿ]+", toks[j], w, count=1)
                    if novo != w:
                        words[i + j]["word"] = novo
                        n += 1
    return n


def corrigir(arquivo: Path, cliente: str, raiz: Path | None = None) -> int:
    vocab = palavras(cliente, raiz)
    if not vocab or not Path(arquivo).is_file():
        return 0
    js = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    lista = js.get("words") if isinstance(js, dict) else js
    if not isinstance(lista, list):
        return 0
    n = corrigir_lista(lista, vocab)
    if n:
        Path(arquivo).write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    return n


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "prompt":
        print(prompt(a[1]), end="")
    elif len(a) >= 3 and a[0] == "corrigir":
        print(corrigir(Path(a[1]), a[2]), file=sys.stderr)
    else:
        sys.exit(__doc__)
