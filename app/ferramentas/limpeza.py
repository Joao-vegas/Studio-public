#!/usr/bin/env python3
"""
limpeza — não deixar lixo: candidatos/prévias do get-brolls e opções não escolhidas de um job
só existem enquanto estão em uso. O que foi aprovado e guardado vive no acervo; o resto some.

    limpar_gb_project()          apaga acervo/busca/brolls (ledger da busca pela interface)
    limpar_sandbox(job)          apaga opções NÃO escolhidas (brolls/, previews) da sandbox do job
    limpar_tudo()                os dois + caches do Estúdio
"""
from __future__ import annotations
import shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, GB_PROJECT, CACHE, ler_json


def limpar_gb_project() -> int:
    import producao
    if any(j['status'] != 'arquivado' for j in producao.listar()):
        return 0
    d = GB_PROJECT / "brolls"
    if d.is_dir():
        shutil.rmtree(d); return 1
    return 0


def limpar_sandbox(job: dict) -> int:
    sb = RAIZ / job["sandbox"]
    plano = ler_json(sb / "PLANO.json", {}) or {}
    manter = set()
    for b in plano.get("beats", []):
        for o in b.get("opcoes", []):
            if o.get("id") == b.get("escolha"):
                for k in ("arquivo", "sheet", "gif"):
                    if o.get(k): manter.add((sb / o[k]).resolve())
        if b.get("previa"): manter.add((sb / b["previa"]).resolve())
    n = 0
    for pasta in ("brolls", "previas"):
        d = sb / pasta
        if not d.is_dir(): continue
        for p in list(d.rglob("*")):
            if p.is_file() and p.resolve() not in manter and p.parent.name != "clips" and not any(m.name == p.name for m in manter):
                # apaga só o que é opção/prévia (sheet, gif, poster, candidatos, ledger) — nunca o clipe escolhido
                if p.suffix.lower() in (".jpg", ".gif", ".json", ".jsonl", ".lock", ".png") or "previews" in p.parts or p.parent.name == "candidates":
                    p.unlink(missing_ok=True); n += 1
        for sub in ("previews", "candidates"):
            s = d / sub
            if s.is_dir() and not any(s.iterdir()): s.rmdir()
    return n


def limpar_tudo() -> dict:
    import producao
    if any(j['status'] != 'arquivado' for j in producao.listar()):
        return {'preservado':'Há vídeos em produção. Os candidatos e caches foram preservados.'}
    n = {"gb_project": limpar_gb_project(), "cache": 0}
    if CACHE.is_dir():
        shutil.rmtree(CACHE); n["cache"] = 1
    return n


if __name__ == "__main__":
    print(limpar_tudo())
