#!/usr/bin/env python3
"""
uso_midia — histórico confiável de música e efeito usados em cada entrega (base do rodízio).

Arquivo append-only `acervo/usos.jsonl` (fora de app/jobs: o "limpar" não apaga). Uma linha por faixa/efeito
distinto de cada vídeo: {em, cliente, formato, modelo, job, tipo: musica|sfx, chave, titulo, arquivo, fonte}.
`chave` = sha1 dos primeiros 2 MB + tamanho: a mesma faixa copiada em 3 pastas é a mesma chave.
Caminhos sempre relativos à raiz do Estúdio.

CLI:
    python3 uso_midia.py semear                       (lê as sandboxes que já existem e grava o histórico; idempotente)
    python3 uso_midia.py recentes <Cliente> [--tipo musica|sfx] [--n 8]
    python3 uso_midia.py geral [--tipo musica|sfx] [--dias 60]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac")
SFX_DO_MOTOR = ("pop", "click-soft", "tique", "whoosh-short", "typing")   # o que o render.py do documentário põe sozinho


def arquivo_usos() -> Path:
    return _comum.RAIZ / "acervo" / "usos.jsonl"


def chave_de(arquivo) -> str:
    p = Path(arquivo)
    h = hashlib.sha1()
    with open(p, "rb") as f:
        h.update(f.read(2 * 1024 * 1024))
    return f"{h.hexdigest()[:20]}-{p.stat().st_size}"


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(_comum.RAIZ.resolve()))
    except ValueError:
        return Path(p).name


def ler() -> list[dict]:
    p = arquivo_usos()
    if not p.is_file():
        return []
    out = []
    for linha in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(linha))
        except ValueError:
            continue
    return out


def _gravar(linhas: list[dict]) -> int:
    existentes = {(u.get("job"), u.get("cliente"), u.get("chave")) for u in ler()}
    novas = []
    for u in linhas:
        k = (u["job"], u["cliente"], u["chave"])
        if k in existentes:
            continue
        existentes.add(k)
        novas.append(u)
    if novas:
        p = arquivo_usos()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            for u in novas:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
    return len(novas)


def _achar(sandbox: Path, nome) -> Path | None:
    if not nome or not isinstance(nome, str):
        return None
    modelo = sandbox.parent                    # o sandbox some com a música; ela fica no modelo do cliente ou no formato
    bases = (sandbox, sandbox / "assets", sandbox / "audio", modelo, modelo / "assets",
             _comum.RAIZ / "formatos" / modelo.name / "base", _comum.RAIZ / "formatos" / modelo.name / "base" / "audio")
    for base in bases:
        c = base / nome
        if c.is_file() and c.suffix.lower() in AUDIO_EXTS:
            return c
    return None


def _musicas_do_sandbox(sandbox: Path) -> list[Path]:
    out: list[Path] = []
    plano = _comum.ler_json(sandbox / "PLANO.json") or {}
    cenas = _comum.ler_json(sandbox / "cenas.json") or {}
    for fonte in (plano.get("musica"), cenas.get("musica")):
        for m in (fonte if isinstance(fonte, list) else [fonte]):
            if isinstance(m, dict) and m.get("sem"):
                continue
            nome = m.get("arquivo") or m.get("opcao") if isinstance(m, dict) else m
            p = _achar(sandbox, nome)
            if p and p not in out:
                out.append(p)
    if not out and (sandbox / "assets").is_dir():                  # dividido-máscara: assets/musica-*.mp3
        out += sorted((sandbox / "assets").glob("musica-*.mp3"))
    return out


def _sfx_do_sandbox(sandbox: Path) -> list[Path]:
    out: list[Path] = []
    cenas = _comum.ler_json(sandbox / "cenas.json") or {}
    pasta = sandbox / "audio" / "sfx"
    if cenas.get("efeitos") and pasta.is_dir():
        for nome in SFX_DO_MOTOR:
            p = pasta / f"{nome}.mp3"
            if p.is_file():
                out.append(p)
    plano = _comum.ler_json(sandbox / "PLANO.json") or {}
    for s in plano.get("sfx") or []:
        p = _achar(sandbox, s if isinstance(s, str) else (s or {}).get("arquivo"))
        if p and p not in out:
            out.append(p)
    pasta2 = sandbox / "assets" / "sfx"
    if pasta2.is_dir():
        out += [p for p in sorted(pasta2.iterdir()) if p.suffix.lower() in AUDIO_EXTS and p not in out]
    return out


def _linhas(cliente, formato, modelo, job, sandbox: Path, em: str) -> list[dict]:
    out = []
    for tipo, arqs in (("musica", _musicas_do_sandbox(sandbox)), ("sfx", _sfx_do_sandbox(sandbox))):
        for a in arqs:
            try:
                chave = chave_de(a)
            except OSError:
                continue
            out.append({"em": em, "cliente": cliente, "formato": formato, "modelo": modelo, "job": job, "tipo": tipo,
                        "chave": chave, "titulo": a.stem, "arquivo": _rel(a), "fonte": ""})
    return out


def registrar_entrega(cliente: str, formato: str, modelo: str, job: str, sandbox) -> int:
    """Grava música e efeitos usados na entrega. Idempotente. Nunca derruba quem chamou."""
    try:
        sb = Path(sandbox)
        if not sb.is_absolute():
            sb = _comum.RAIZ / sb
        if not sb.is_dir():
            return 0
        return _gravar(_linhas(cliente, formato or modelo, modelo, job, sb, datetime.now().isoformat(timespec="seconds")))
    except Exception as e:  # noqa: BLE001
        print(f"(uso de mídia não registrado: {e})", file=sys.stderr)
        return 0


def semear() -> dict:
    """Varre clientes/*/*Content/modelos/*/_sandbox-*/ (só leitura) e grava o histórico que já existe."""
    novas = total = 0
    for sb in sorted(_comum.RAIZ.glob("clientes/*/*Content/modelos/*/_sandbox-*")):
        if not sb.is_dir():
            continue
        cliente, modelo = sb.parts[-5], sb.parts[-2]
        em = datetime.fromtimestamp(sb.stat().st_mtime).isoformat(timespec="seconds")
        ls = _linhas(cliente, modelo, modelo, sb.name, sb, em)
        total += len(ls)
        novas += _gravar(ls)
    return {"lidas": total, "novas": novas}


def recentes(cliente: str, tipo: str = "musica", n: int = 8) -> list[dict]:
    """Usos do cliente nas últimas `n` entregas (que tinham esse tipo), mais recente primeiro; `posicao` = 1 é a última."""
    alvo = (cliente or "").strip().lower()
    us = sorted((u for u in ler() if u.get("tipo") == tipo and str(u.get("cliente", "")).lower() == alvo),
                key=lambda u: u.get("em", ""), reverse=True)
    ordem: list[str] = []
    for u in us:
        if u["job"] not in ordem:
            ordem.append(u["job"])
    ordem = ordem[:max(1, int(n))]
    out = []
    for u in us:
        if u["job"] in ordem:
            out.append({**u, "posicao": ordem.index(u["job"]) + 1})
    return out


def contagem_geral(tipo: str = "musica", dias: int = 60, excluir_cliente: str = "") -> dict:
    """{chave: nº de usos nos últimos `dias`}, opcionalmente só em OUTROS clientes."""
    corte = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    ex = (excluir_cliente or "").strip().lower()
    cont: dict[str, int] = {}
    for u in ler():
        if u.get("tipo") != tipo or u.get("em", "") < corte:
            continue
        if ex and str(u.get("cliente", "")).lower() == ex:
            continue
        cont[u["chave"]] = cont.get(u["chave"], 0) + 1
    return cont


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("semear")
    r = sub.add_parser("recentes")
    r.add_argument("cliente")
    r.add_argument("--tipo", default="musica")
    r.add_argument("--n", type=int, default=8)
    g = sub.add_parser("geral")
    g.add_argument("--tipo", default="musica")
    g.add_argument("--dias", type=int, default=60)
    a = ap.parse_args()
    if a.cmd == "semear":
        print(json.dumps(semear(), ensure_ascii=False))
    elif a.cmd == "recentes":
        for u in recentes(a.cliente, a.tipo, a.n):
            print(u["posicao"], u["job"], u["titulo"], u["chave"])
    else:
        for k, v in sorted(contagem_geral(a.tipo, a.dias).items(), key=lambda x: -x[1])[:20]:
            print(v, k)


if __name__ == "__main__":
    main()
