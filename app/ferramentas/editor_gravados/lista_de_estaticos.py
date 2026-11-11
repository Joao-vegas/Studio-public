#!/usr/bin/env python3
"""
editor_gravados.lista_de_estaticos — "Editar vídeo por cena" da Lista de estáticos (formatos/lista-de-estaticos/base/render_lista.py).

A pessoa fica num canto, o título tem uma palavra forte, a lista numerada se preenche conforme ela fala e, a cada item, aparece a
estática daquele tipo de anúncio. Tudo sai do cenas.json da pasta (video, titulo, lado, estilo, itens {nome, imagem, t}, cortes, fim).
A "cena" é um trecho do vídeo JÁ CORTADO: a abertura (título) e um item por vez. O `t` de cada item (tempo do bruto) nunca muda no
editor; só o nome, a imagem e, no topo, o título, o lado e o estilo.

    python3 lista_de_estaticos.py refazer <sandbox>    # roda o render_lista.py e troca o vídeo só se der certo (o editor chama)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import RAIZ, com_venv, gravar_json, ler_json, rodar_com_limite  # noqa: E402

SLUG = "lista-de-estaticos"
MOTOR = RAIZ / "formatos" / "lista-de-estaticos" / "base" / "render_lista.py"
TIPOS = {"abertura": "Abertura (título)", "item": "Item da lista"}
ROTULOS = {"nome": "Nome do item", "imagem": "Estática do item", "titulo": "Título da tela",
           "lado": "Lado da lista", "estilo": "Estilo"}
GLOBAIS = {"titulo": ["titulo_tela"], "lado": ["lado"], "estilo": ["estilo"]}
LADOS = ("direita", "esquerda", "centro")


def saida(p: Path) -> Path:
    return p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def _abs(p: Path, c) -> Path:
    return Path(c) if str(c).startswith("/") else p / str(c)


def _tempo(cortes: list):
    """t do bruto → t do vídeo cortado (o mesmo T do render_lista.py)."""
    cs = sorted(cortes or [])
    return lambda t: t - sum(min(max(t - i, 0), f - i) for i, f in cs)


def _texto_titulo(titulo) -> str:
    """O título (linhas de trechos [texto, 'forte'|'normal']) como uma frase só."""
    partes = []
    for linha in titulo or []:
        if linha and isinstance(linha[0], str):
            linha = [linha]
        partes.append("".join(t[0] for t in linha if t))
    return " ".join(x.strip() for x in partes).strip()


def ler(p: Path) -> dict:
    """cenas.json → a abertura + um item por cena, nos tempos do vídeo já cortado."""
    c = json.loads((p / "cenas.json").read_text(encoding="utf-8"))
    T = _tempo(c.get("cortes"))
    fim = T(float(c["fim"]))
    cs = [{"de": 0.0, "tipo": "abertura"}]
    for it in c.get("itens") or []:
        cs.append({"de": round(T(float(it["t"])), 3), "tipo": "item", "nome": it["nome"], "imagem": it["imagem"]})
    pal = []   # a fala no tempo do vídeo cortado (as palavras dentro de um corte somem)
    wf = c.get("palavras") or ("work/words.json" if (p / "work" / "words.json").is_file() else None)
    if wf and _abs(p, wf).is_file():
        d = json.loads(_abs(p, wf).read_text(encoding="utf-8"))
        cortes = sorted(c.get("cortes") or [])
        for w in (d.get("words", d) if isinstance(d, dict) else d):
            if isinstance(w, dict) and "start" in w and not any(i <= float(w["start"]) < f for i, f in cortes):
                pal.append({"word": w.get("word", w.get("w", "")), "start": round(T(float(w["start"])), 3),
                            "end": round(T(float(w.get("end", w["start"]))), 3)})
    ed = p / "editor"
    ed.mkdir(parents=True, exist_ok=True)
    if ler_json(ed / "palavras.json", None) != pal:
        gravar_json(ed / "palavras.json", pal)
    doc = {"titulo": _texto_titulo(c.get("titulo")) or p.name, "duracao": round(fim, 3), "saida": str(saida(p)), "palavras": "editor/palavras.json",
           "titulo_tela": c.get("titulo") or [], "lado": c.get("lado", "auto"), "estilo": c.get("estilo", "lista")}
    doc["cenas"] = cs
    return doc


def gravar(p: Path, doc: dict) -> None:
    """Lista de cenas → cenas.json: nome e imagem de cada item (pela ordem), o título, o lado e o estilo. O `t` e os cortes ficam."""
    f = p / "cenas.json"
    c = json.loads(f.read_text(encoding="utf-8"))
    itens = c.get("itens") or []
    cs = [x for x in doc.get("cenas") or [] if isinstance(x, dict)]
    novos = [x for x in cs if x.get("tipo") == "item"]
    for it, x in zip(itens, novos):
        if str(x.get("nome") or "").strip():
            it["nome"] = str(x["nome"]).strip()
        if x.get("imagem"):
            it["imagem"] = str(x["imagem"])
    if doc.get("titulo_tela"):
        c["titulo"] = doc["titulo_tela"]
    if doc.get("lado") and doc["lado"] != c.get("lado", "auto"):
        c["lado"] = doc["lado"]
    if doc.get("estilo") in ("lista", "ao-lado") and doc["estilo"] != c.get("estilo", "lista"):
        c["estilo"] = doc["estilo"]
    f.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def refazer(p: Path) -> int:
    """Roda o render_lista.py nesta pasta (saída ao lado) e só troca o vídeo se der certo. 0 = ok."""
    p = Path(p).resolve()
    c = json.loads((p / "cenas.json").read_text(encoding="utf-8"))
    destino = saida(p)
    destino.parent.mkdir(parents=True, exist_ok=True)
    novo = destino.with_name(destino.name + ".novo.mp4")
    args = [sys.executable, str(MOTOR), "--pasta", str(p), "--out", str(novo)]
    if c.get("lado") in LADOS:   # o render só lê o lado da linha de comando
        args += ["--lado", c["lado"]]
    r = rodar_com_limite(args, 3600, cwd=p, env=com_venv(), capture_output=True, text=True)
    if r.returncode or not novo.is_file():
        print((r.stderr or r.stdout)[-600:])
        novo.unlink(missing_ok=True)
        return r.returncode or 1
    os.replace(novo, destino)
    print("ok", destino)
    return 0


def cmd(p: Path) -> tuple[list[str], Path]:
    return [sys.executable, str(Path(__file__).resolve()), "refazer", str(p)], p


def cmd_txt(p: Path) -> str:
    return f"python3 {MOTOR} --pasta {p} --out <saida>"


def achar(p: Path) -> bool:
    return (p / "cenas.json").is_file() and "itens" in (p / "cenas.json").read_text(encoding="utf-8", errors="ignore") and MOTOR.is_file()


SPEC = {
    "gravado": True, "fonte": "cenas.json", "ler": ler, "gravar": gravar,
    "arquivos": ["cenas.json"], "precisa": ["cenas.json"],
    "achar": achar, "cmd": cmd, "cmd_txt": cmd_txt, "saida": saida, "timeout": 3600,
    "rotulos": ROTULOS, "tipos": TIPOS, "tipo_padrao": "item",
    "juntos": {"nome": [], "imagem": []}, "sempre": (), "globais": GLOBAIS,
    "sugestoes": ["Troca a estática desse item por uma que mostre melhor o que ele diz", "Troca o nome desse item por um mais curto",
                  "Passa a lista pro outro lado", "Deixa o título mais forte"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "render_lista.py",
    "motivo_narracao": "Neste formato a voz é a pessoa gravada: a fala só muda trocando o vídeo gravado.",
    "onde": ("O vídeo é a pessoa gravada num canto com um título, uma lista numerada que se preenche conforme ela fala e a estática de cada item, "
             "desenhado pelo render_lista.py do formato a partir do cenas.json. Você NÃO mexe no cenas.json: edite só a lista de cenas (a "
             "\"abertura\" e um \"item\" por cena, com \"de\" = segundo do vídeo em que o item entra; ela termina onde a próxima começa)."),
    "conferir": ("Pra conferir uma estática nova, abra a imagem (Read) e OLHE: é a caixa de ~480x520 ao lado da pessoa, então precisa ler de longe. "
                 "O vídeo todo é feito pelo Estúdio depois."),
    "dicas": ("Cada cena \"item\" tem o \"nome\" (curto, em minúsculo, como aparece na lista) e a \"imagem\" (a estática daquele tipo de anúncio: caminho "
              "de um PNG/JPG, relativo a esta pasta ou absoluto). Estática nova: use as imagens que já estão em material/ desta pasta, ou crie um PNG "
              "simples (PIL, vertical ou quadrado, texto grande e legível, fundo liso) e salve em material/ — nada de banco de imagem posando e nada "
              "pago. O nome e a estática têm de combinar com o que a pessoa fala naquele momento. A \"abertura\" não tem item. No topo: "
              "\"titulo_tela\" (linhas de trechos [texto, \"forte\"|\"normal\"]; só uma palavra forte), \"lado\" (direita, esquerda ou centro; "
              "a lista vai pro lado oposto ao da pessoa) e \"estilo\" (lista ou ao-lado). Não mude o \"de\" nem o número de itens."),
}
SPECS = {SLUG: SPEC}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "refazer":
        sys.exit(refazer(Path(sys.argv[2])))
    print(__doc__)
    sys.exit(2)
