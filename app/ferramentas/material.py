#!/usr/bin/env python3
"""
material — o ACERVO PRÓPRIO DE CADA CLIENTE, organizado em coleções.

São três lugares de material no repositório, e eles não se misturam:

  1. ACERVO (`acervo/itens/`)            compartilhado por TODOS os clientes — b-roll, música, SFX
                                           que serve pro Cliente2 e pro Cliente8 igual.
  2. MATERIAL DO CLIENTE (aqui)            `<Cliente>/<x>Content/material/<colecao>/` — o que é DELE:
                                           fotos do produto, prints de prova, logo, depoimento.
                                           Serve qualquer modelo daquele cliente, em qualquer vídeo.
  3. ASSETS DO MODELO                      `<modelo>/assets/` — a identidade fixa de UM modelo:
                                           a cama de música, a fonte, o card de preço.

Coleção = uma pasta com um assunto ("Marca3", "Depoimentos 2026"), com `meta.json` (título,
descrição, tags) e os arquivos dentro. Ao criar um vídeo, marcar a coleção copia os arquivos dela
pro `material/` daquele job — que é o que a produção lê com prioridade máxima.

CLI:  material.py <Cliente>                       lista as coleções
      material.py <Cliente> --criar "Marca3" [--descricao "..."] [--tags produto,prova]
      material.py <Cliente> --colecao <slug> --subir <arquivo>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import (agora, cliente as _cliente, ensure, gravar_json, ler_json, lixeira_guardar,
                    lixeira_item, make_slug, now_slug, rel)
import ficha as _ficha

EXTS = _ficha.EXTS_ASSET


def base(cli: dict) -> Path:
    return cli["content"] / "material"


def _pasta(cli: dict, slug: str) -> Path:
    if Path(slug).name != slug or slug in (".", "..") or not slug.strip():
        raise ValueError("coleção inválida")
    d = base(cli) / slug
    if d.resolve().parent != base(cli).resolve():
        raise ValueError("caminho fora do material deste cliente")
    return d


def caminho(cli: dict, slug: str, nome: str) -> Path:
    raiz = _pasta(cli, slug).resolve()
    alvo = (raiz / nome).resolve()
    if not str(alvo).startswith(str(raiz) + "/") or ".." in Path(nome).parts:
        raise ValueError("caminho de arquivo inválido")
    return alvo


def itens(cli: dict, slug: str) -> list[dict]:
    d = _pasta(cli, slug)
    out = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name in ("meta.json",) or p.name.startswith(".") or p.suffix.lower() not in EXTS:
            continue
        out.append({"nome": str(p.relative_to(d)), "rel": rel(p), "tipo": _ficha.tipo_de_arquivo(p),
                    "mb": round(p.stat().st_size / 1e6, 2)})
    return out


def colecoes(cli: dict) -> list[dict]:
    b = base(cli)
    if not b.is_dir():
        return []
    out = []
    for d in sorted(b.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta = ler_json(d / "meta.json", {}) or {}
        its = itens(cli, d.name)
        out.append({"slug": d.name, "titulo": meta.get("titulo") or d.name, "descricao": meta.get("descricao", ""),
                    "tags": meta.get("tags", []), "criado_em": meta.get("criado_em", ""), "itens": its,
                    "n": len(its), "mb": round(sum(i["mb"] for i in its), 1),
                    "capa": next((i for i in its if i["tipo"] == "imagem"), its[0] if its else None)})
    return out


def criar(cli: dict, titulo: str, descricao: str = "", tags: str = "") -> dict:
    slug = make_slug(titulo) or now_slug()
    d = base(cli) / slug
    n = 2
    while d.exists():
        d = base(cli) / f"{slug}-{n}"; n += 1
    ensure(d)
    gravar_json(d / "meta.json", {"titulo": titulo.strip() or d.name, "descricao": descricao.strip(),
                                  "tags": [t.strip() for t in tags.split(",") if t.strip()],
                                  "criado_em": agora()})
    return {"slug": d.name, "pasta": str(d)}


def editar(cli: dict, slug: str, titulo: str = "", descricao: str = "", tags: str = "") -> dict:
    d = _pasta(cli, slug)
    meta = ler_json(d / "meta.json", {}) or {}
    if titulo.strip():
        meta["titulo"] = titulo.strip()
    meta["descricao"] = descricao.strip()
    meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    meta["atualizado_em"] = agora()
    gravar_json(d / "meta.json", meta)
    return meta


def subir(cli: dict, slug: str, origem: Path, nome_final: str = "") -> dict:
    """Move o arquivo enviado pra dentro da coleção (substitui manda o antigo pra lixeira)."""
    origem = Path(origem)
    ext = origem.suffix.lower()
    if ext not in EXTS:
        raise ValueError(f"tipo de arquivo não suportado: {ext}")
    nome = f"{make_slug(Path(nome_final or origem.stem).stem) or 'arquivo'}{ext}"
    destino = caminho(cli, slug, nome)
    substituiu = None
    if destino.exists():
        substituiu = remover_item(cli, slug, nome, motivo="substituído por um arquivo novo")["id"]
    ensure(destino.parent)
    shutil.move(str(origem), str(destino))
    return {"nome": nome, "substituiu": substituiu}


def mover_item(cli: dict, de: str, nome: str, para: str) -> dict:
    """Passa um arquivo de um template pro outro — organizar é isso, não reenviar arquivo."""
    origem = caminho(cli, de, nome)
    if not origem.is_file():
        raise ValueError("arquivo não encontrado")
    destino = caminho(cli, para, Path(nome).name)
    if destino.exists():
        raise ValueError(f"já existe {Path(nome).name} em {para}")
    ensure(destino.parent)
    shutil.move(str(origem), str(destino))
    return {"de": de, "para": para, "arquivo": Path(nome).name}


def remover_item(cli: dict, slug: str, nome: str, motivo: str = "") -> dict:
    alvo = caminho(cli, slug, nome)
    if not alvo.is_file():
        raise ValueError("arquivo não encontrado")
    info = {"tipo": "material", "alvo": "item", "rotulo": f"{cli['nome']}-{slug}-{Path(nome).name}",
            "cliente": cli["nome"], "colecao": slug, "item": nome, "motivo": motivo, "arquivo": alvo.name}
    return {"id": lixeira_guardar({alvo.name: alvo}, info), **info}


def remover_colecao(cli: dict, slug: str, motivo: str = "") -> dict:
    d = _pasta(cli, slug)
    if not d.is_dir():
        raise ValueError("coleção não encontrada")
    meta = ler_json(d / "meta.json", {}) or {}
    info = {"tipo": "material", "alvo": "colecao", "rotulo": f"{cli['nome']}-{slug}",
            "cliente": cli["nome"], "colecao": slug, "titulo": meta.get("titulo", slug), "motivo": motivo}
    return {"id": lixeira_guardar({"colecao": d}, info), **info}


def pode_voltar(info: dict) -> bool:
    cli = _cliente(info.get("cliente", ""))
    if not cli:
        return False
    try:
        if info.get("alvo") == "colecao":
            return not (base(cli) / info["colecao"]).exists()
        return _pasta(cli, info["colecao"]).is_dir() and not caminho(cli, info["colecao"], info["item"]).exists()
    except (ValueError, KeyError):
        return False


def restaurar(ident: str) -> dict:
    d = lixeira_item(ident)
    info = ler_json(d / "info.json", {}) or {}
    cli = _cliente(info.get("cliente", ""))
    if not cli:
        raise ValueError(f"o cliente {info.get('cliente')} não existe mais")
    if info.get("alvo") == "colecao":
        destino = base(cli) / info["colecao"]
        if destino.exists():
            raise ValueError("já existe uma coleção com esse nome")
        ensure(destino.parent)
        shutil.move(str(d / "colecao"), str(destino))
    else:
        destino = caminho(cli, info["colecao"], info["item"])
        if destino.exists():
            raise ValueError("já existe um arquivo com esse nome na coleção")
        ensure(destino.parent)
        shutil.move(str(d / info["arquivo"]), str(destino))
    shutil.rmtree(d, ignore_errors=True)
    return {"cliente": cli["nome"], "colecao": info["colecao"], "item": info.get("item")}


def pro_acervo(cli: dict, slug: str, nome: str, titulo: str = "", tags: str = "") -> dict:
    """COPIA um item da coleção pro acervo compartilhado (o cliente continua com o dele)."""
    import acervo
    from _comum import sha_arquivo
    alvo = caminho(cli, slug, nome)
    if not alvo.is_file():
        raise ValueError("arquivo não encontrado")
    ja = acervo.indice_hashes().get(sha_arquivo(alvo))
    if ja:
        return {**(acervo.item(ja) or {"slug": ja, "titulo": ja}), "ja_estava": True}
    return acervo.adicionar_arquivo(alvo, titulo or Path(nome).stem,
                                    tags=tags or _ficha.tags_automaticas(nome, _ficha.tipo_de_arquivo(alvo), cli["nome"], slug, alvo),
                                    fonte=f"{cli['nome']}/material/{slug}",
                                    observacao=f"Promovido do material do cliente ({slug}) pelo Estúdio.",
                                    origem_tipo="material-do-cliente", mover=False, descrever_auto=False)


def copiar_para(cli: dict, slugs: list[str], destino: Path) -> list[Path]:
    """Cópias temporárias das coleções marcadas, pra virarem o material próprio de um vídeo."""
    saida = []
    for slug in slugs or []:
        try:
            d = _pasta(cli, slug)
        except ValueError:
            continue
        for it in itens(cli, slug):
            origem = d / it["nome"]
            tmp = ensure(Path(destino)) / f"{now_slug()}-{slug}-{Path(it['nome']).name}"
            _clonar(str(origem), str(tmp))
            saida.append(tmp)
    return saida


# ───────────── migração: tirar o material de dentro do modelo ─────────────
# O modelo é o MOTOR (scripts). Material é do PROJETO: música/SFX vão pro acervo compartilhado,
# imagem/vídeo/template viram assets do cliente. Os arquivos continuam fisicamente em
# <modelo>/assets/ porque o gerar.sh lê aquele caminho — o que muda é onde o João gerencia.

def _sha(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def migrar_assets_dos_modelos(aplicar: bool = False) -> list[dict]:
    """Música vira item do acervo; imagem/vídeo viram assets do cliente. Copia, nunca move."""
    import acervo
    from _comum import clientes as _clientes, modelos as _modelos
    import ficha as _f
    ja_no_acervo = {}
    if aplicar:
        for it in acervo.listar():
            if it.get("clip") and Path(it["clip"]).is_file():
                ja_no_acervo[_sha(it["clip"])] = it["slug"]
    saida = []
    for cli in _clientes():
        for mod in _modelos(cli):
            for a in _f.assets(mod["pasta"]):
                origem = mod["pasta"] / "assets" / a["nome"]
                destino = ("acervo" if a["tipo"] == "audio" else
                           "cliente" if a["tipo"] in ("imagem", "video") else None)
                if not destino:
                    continue
                reg = {"cliente": cli["nome"], "modelo": mod["nome"], "arquivo": a["nome"],
                       "tipo": a["tipo"], "para": destino}
                if aplicar:
                    if destino == "acervo":
                        h = _sha(origem)
                        if h in ja_no_acervo:
                            reg["ja_existia"] = ja_no_acervo[h]
                        else:
                            m = acervo.adicionar_arquivo(
                                origem, Path(a["nome"]).stem, tags=f"musica, {cli['nome']}, {mod['nome']}",
                                fonte=f"{cli['nome']}/{mod['nome']}",
                                observacao=f"Cama/SFX que era asset do modelo {mod['nome']}.",
                                origem_tipo="asset-de-modelo", mover=False, descrever_auto=False)
                            ja_no_acervo[h] = m["slug"]; reg["slug"] = m["slug"]
                    else:
                        col = next((c for c in colecoes(cli) if c["slug"] == mod["nome"]), None)
                        if not col:
                            criar(cli, mod["nome"], f"Imagens e vídeos que o modelo {mod['nome']} usa.",
                                  f"{mod['nome']}, template")
                            d = _pasta(cli, mod["nome"])
                        else:
                            d = _pasta(cli, col["slug"])
                        alvo = d / Path(a["nome"]).name
                        if alvo.exists():
                            reg["ja_existia"] = str(alvo.relative_to(cli["content"]))
                        else:
                            _clonar(str(origem), str(alvo))
                            reg["destino"] = str(alvo.relative_to(cli["content"]))
                saida.append(reg)
    return saida


def main():
    ap = argparse.ArgumentParser(description="Material próprio de um cliente, em coleções")
    ap.add_argument("cliente", nargs="?"); ap.add_argument("--criar"); ap.add_argument("--descricao", default="")
    ap.add_argument("--tags", default=""); ap.add_argument("--colecao"); ap.add_argument("--subir")
    ap.add_argument("--migrar", action="store_true"); ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()
    if a.migrar:
        for r in migrar_assets_dos_modelos(a.aplicar):
            estado = (r.get("slug") or r.get("destino") or
                      (f"já estava lá ({r['ja_existia']})" if r.get("ja_existia") else "— simulação, use --aplicar"))
            print(f"{r['para']:<8} {r['cliente']}/{r['modelo']:<28} {r['arquivo']:<38} {estado}")
        return
    cli = _cliente(a.cliente)
    if not cli:
        raise SystemExit(f"cliente não encontrado: {a.cliente}")
    if a.criar:
        print(json.dumps(criar(cli, a.criar, a.descricao, a.tags), ensure_ascii=False)); return
    if a.colecao and a.subir:
        print(json.dumps(subir(cli, a.colecao, Path(a.subir)), ensure_ascii=False)); return
    for c in colecoes(cli):
        print(f"{c['n']:>3} arquivos · {c['mb']:>5} MB  {c['slug']:<28} {c['titulo']}")


if __name__ == "__main__":
    main()
