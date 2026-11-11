#!/usr/bin/env python3
"""
getbrolls — wrapper fino sobre a skill get-brolls (~/.claude/skills/get-brolls).

Fluxo da skill (metodologia que CHECA antes de usar):
    search  → candidatos (YouTube via yt-dlp, Pexels/Pixabay com chave, Commons/NASA sem chave)
    preview → baixa mídia de trabalho e gera POSTER + CONTACT SHEET + GIF do intervalo
    approve → registra aprovação humana do intervalo
    permit  → registra as condições de uso (evidência real)
    fetch   → produz o corte final aprovado em brolls/clips/
    verify  → confere integridade

O Estúdio usa um projeto persistente (acervo/busca/) pra busca pela interface — o ledger
guarda histórico/memória de decisões. Na produção de um vídeo, o Claude usa a sandbox do job.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import GB_PROJECT, ensure, gb, ler_json, rel

PROVEDORES = [
    ("youtube", "YouTube (sem chave)"),
    ("pexels", "Pexels (stock, precisa PEXELS_API_KEY)"),
    ("pixabay", "Pixabay (stock, precisa PIXABAY_API_KEY)"),
    ("commons", "Wikimedia Commons (sem chave)"),
    ("nasa", "NASA (sem chave)"),
]


def projeto(p: Path | None = None) -> Path:
    return ensure(Path(p) if p else GB_PROJECT)


BANCOS_PAGOS = ("stock video", "motion array", "storyblocks", "stock pilots", "videokot", "envato", "pond5")   # prévia com marca d'água


def _banco_pago(item: dict) -> bool:
    texto = " ".join(str(item.get(k) or "") for k in ("title", "titulo", "channel", "canal", "uploader", "author")).lower()
    return any(b in texto for b in BANCOS_PAGOS)


def buscar(provider: str, query: str, limit: int = 8, intent: str = "literal", proj: Path | None = None) -> dict:
    d = gb(["search", "--provider", provider, "--query", query, "--limit", str(limit),
            "--intent", intent, "--project", str(projeto(proj))])
    if provider == "youtube" and isinstance(d, dict) and isinstance(d.get("items"), list):
        d["items"] = [i for i in d["items"] if not (isinstance(i, dict) and _banco_pago(i))]
    return d


def previa(candidate: str, start: float, end: float, reason: str, proj: Path | None = None) -> dict:
    d = gb(["preview", "--candidate", candidate, "--start", str(start), "--end", str(end),
            "--reason", reason or "prévia pelo Estúdio", "--project", str(projeto(proj))])
    files = d.get("files") or {}
    d["_rel"] = {k: rel(Path(v)) for k, v in files.items() if v}
    return d


def aprovar(candidate: str, by: str, start=None, end=None, proj: Path | None = None) -> dict:
    """Vídeo exige --start/--end (o intervalo da prévia); se não vier, usa o segment do ledger."""
    if start is None or end is None:
        seg = (candidato(candidate, proj) or {}).get("segment") or {}
        start = seg.get("start_s") if start is None else start
        end = seg.get("end_s") if end is None else end
    args = ["approve", "--candidate", candidate, "--by", by or "João", "--project", str(projeto(proj))]
    if start is not None and end is not None:
        args += ["--start", str(start), "--end", str(end)]
    return gb(args)


def permitir(candidate: str, evidence: str, proj: Path | None = None) -> dict:
    return gb(["permit", "--candidate", candidate, "--evidence", evidence, "--project", str(projeto(proj))])


def coletar(candidate: str, proj: Path | None = None) -> dict:
    return gb(["fetch", "--candidate", candidate, "--project", str(projeto(proj))])


def status(proj: Path | None = None) -> dict:
    return gb(["status", "--project", str(projeto(proj))])


def candidatos(proj: Path | None = None) -> list[dict]:
    """Lê os candidatos registrados no ledger do projeto (mais recentes primeiro)."""
    pasta = projeto(proj) / "brolls" / "candidates"
    itens = []
    if pasta.is_dir():
        for p in sorted(pasta.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            d = ler_json(p)
            if d:
                d["_arquivo"] = p.name
                itens.append(d)
    return itens


def candidato(candidate_id: str, proj: Path | None = None) -> dict | None:
    for c in candidatos(proj):
        if c.get("id") == candidate_id:
            return c
    return None


def caminho_clip(candidate_id: str, proj: Path | None = None) -> Path | None:
    c = candidato(candidate_id, proj)
    if not c:
        return None
    out = (c.get("output") or {}).get("path")
    if out:
        p = Path(out)
        if not p.is_absolute():
            p = projeto(proj) / "brolls" / out
        if p.exists():
            return p
    clips = projeto(proj) / "brolls" / "clips"
    if clips.is_dir():
        sid = (c.get("source_id") or "").replace(":", "-")
        for p in sorted(clips.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if sid and sid in p.name:
                return p
    return None


def providers() -> dict:
    return gb(["providers"])


def doctor() -> dict:
    return gb(["doctor"])
