"""Página "O que aprendemos": o que vale pra todos os clientes de um formato e o que é só de um cliente.

Duas camadas de regra:
    formatos/<slug>/aprendizado/regras.json (+ regras.md)    → vale pra todo cliente que usa o formato
    clientes/<C>/<c>Content/modelos/<modelo>/aprendizado/    → o gosto e a identidade daquele cliente

"Vale pra todos" copia a regra do cliente pro formato e marca `promovida` na do cliente.
"Apagar" nunca perde de vez: guarda uma cópia em <aprendizado>/arquivo/removidas.jsonl.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, flash, redirect, render_template, request, url_for

from _comum import agora, append_jsonl, cliente as _cliente, gravar_json, hoje, ler_json, ler_jsonl
import formatos as _fmt


def _contexto(cli: str, mod: str) -> dict:
    """Onde ficam as duas camadas de regra deste cliente neste modelo."""
    c = _cliente(cli)
    if not c or not mod or Path(mod).name != mod or mod in (".", ".."):
        abort(404)
    pasta = c["content"] / "modelos" / mod
    if not pasta.is_dir():
        abort(404)
    f = _fmt.de_modelo(mod)
    return {"c": c, "nome": c["nome"], "mod": mod, "f": f,
            "titulo": f["titulo"] if f else mod,
            "apr_cli": pasta / "aprendizado",
            "apr_fmt": f["pasta"] / "aprendizado" if f else None}


def _ler(p: Path) -> dict:
    d = ler_json(p, {}) or {}
    if isinstance(d, list):
        d = {"regras": d}
    d["regras"] = [r for r in (d.get("regras") or []) if isinstance(r, dict)]
    return d


def _linha(r: dict) -> dict:
    return {"id": str(r.get("id", "")), "texto": str(r.get("texto", "")).strip(),
            "evitar": str(r.get("evitar", "") or "").strip()}


def _volta(ctx):
    return redirect(url_for("aprendizado_ver", cli=ctx["nome"], mod=ctx["mod"]))


# ───────────────────────── o que muda nos arquivos ─────────────────────────

def subir(ctx: dict, rid: str) -> str:
    """Copia a regra do cliente pro formato (funde se o id já existir lá) e marca `promovida` no cliente."""
    if not ctx["apr_fmt"]:
        raise ValueError("Este modelo não está em nenhum formato do catálogo, então não há 'todos os clientes' pra subir.")
    pc = ctx["apr_cli"] / "regras.json"
    dc = _ler(pc)
    regra = next((r for r in dc["regras"] if str(r.get("id", "")) == rid), None)
    if not regra:
        raise ValueError("Essa regra não está mais aqui (talvez já tenha sido mudada). Recarregue a página.")
    pf = ctx["apr_fmt"] / "regras.json"
    df = _ler(pf)
    origem = f"{ctx['nome']}/{rid}"
    existente = next((r for r in df["regras"] if str(r.get("id", "")) == rid), None)
    if existente:
        texto_novo = str(regra.get("texto", "")).strip()
        if texto_novo and texto_novo not in str(existente.get("texto", "")):
            existente["texto"] = (str(existente.get("texto", "")).strip() + "\n\n" + texto_novo).strip()
        evitar_novo = str(regra.get("evitar", "") or "").strip()
        if evitar_novo and evitar_novo not in str(existente.get("evitar", "") or ""):
            existente["evitar"] = "; ".join(x for x in (str(existente.get("evitar", "") or "").strip(), evitar_novo) if x)
        for k, v in regra.items():
            if k not in ("promovida", "origem") and k not in existente:
                existente[k] = v
        pesos = [x.get("peso") for x in (existente, regra) if isinstance(x.get("peso"), (int, float))]
        if pesos:
            existente["peso"] = max(pesos)
        orig = existente.get("origem")
        orig = [orig] if isinstance(orig, str) else list(orig or [])
        if origem not in orig:
            orig.append(origem)
        existente["origem"] = orig
    else:
        nova = {k: v for k, v in regra.items() if k not in ("promovida", "origem")}
        nova["origem"] = [origem]
        nova.setdefault("desde", hoje())
        df["regras"].append(nova)
    gravar_json(pf, df)
    regra["promovida"] = rid
    gravar_json(pc, dc)
    append_jsonl(ctx["apr_cli"] / "historico.jsonl", {
        "tipo": "promocao", "categoria": regra.get("categoria", "geral"),
        "texto": f"Regra {rid} passou a valer pra todos os clientes do formato",
        "origem": "usuario", "createdAt": hoje()})
    return "Pronto: essa regra agora vale pra todos os clientes de " + ctx["titulo"] + "."


def apagar(ctx: dict, rid: str, camada: str) -> str:
    """Tira a regra do arquivo da camada e guarda uma cópia em arquivo/removidas.jsonl."""
    pasta = {"cliente": ctx["apr_cli"], "formato": ctx["apr_fmt"]}.get(camada)
    if not pasta:
        raise ValueError("Não sei de onde apagar essa regra.")
    p = pasta / "regras.json"
    d = _ler(p)
    i = next((n for n, r in enumerate(d["regras"]) if str(r.get("id", "")) == rid), None)
    if i is None:
        raise ValueError("Essa regra não está mais aqui. Recarregue a página.")
    regra = d["regras"][i]
    append_jsonl(pasta / "arquivo" / "removidas.jsonl", {
        "removida_em": agora(), "camada": camada, "cliente": ctx["nome"], "modelo": ctx["mod"], "regra": regra})
    del d["regras"][i]
    gravar_json(p, d)
    if camada == "cliente":
        return "Regra apagada. Guardamos uma cópia, então nada se perde."
    # Saiu de "vale pra todos": quem tinha subido essa regra volta a vê-la como só dele.
    for v in (ctx["f"] or {}).get("variantes") or []:
        c = _cliente(v["cliente"])
        if not c:
            continue
        pc = c["content"] / "modelos" / v["modelo"] / "aprendizado" / "regras.json"
        dc = _ler(pc)
        mexeu = False
        for r in dc["regras"]:
            if r.get("promovida") == rid:
                r.pop("promovida")
                mexeu = True
        if mexeu:
            gravar_json(pc, dc)
    return "Regra tirada de 'Vale pra todos'. Guardamos uma cópia, então nada se perde."


# ───────────────────────── rotas ─────────────────────────

def register(app):
    @app.route("/aprendizado/<cli>/<mod>", endpoint="aprendizado_ver")
    def aprendizado_ver(cli, mod):
        ctx = _contexto(cli, mod)
        do_formato, ids_formato = [], set()
        if ctx["apr_fmt"]:
            for r in _ler(ctx["apr_fmt"] / "regras.json")["regras"]:
                if r.get("texto"):
                    do_formato.append({**_linha(r), "apagavel": True})
            for r in _fmt._regras_md(ctx["apr_fmt"] / "regras.md"):
                do_formato.append({**_linha(r), "apagavel": False})
            ids_formato = {r["id"] for r in do_formato}
        do_cliente, n_subidas = [], 0
        for r in _ler(ctx["apr_cli"] / "regras.json")["regras"]:
            if not r.get("texto"):
                continue
            if r.get("promovida") and r["promovida"] in ids_formato:
                n_subidas += 1
            else:
                do_cliente.append(_linha(r))
        historico = []
        for h in reversed(ler_jsonl(ctx["apr_cli"] / "historico.jsonl")):
            if str(h.get("texto", "")).strip():
                historico.append({"data": str(h.get("createdAt", ""))[:10], "texto": str(h["texto"]).strip()})
            if len(historico) == 10:
                break
        return render_template("aprendizado.html", cli=ctx["nome"], mod=mod, titulo=ctx["titulo"],
                               tem_formato=bool(ctx["apr_fmt"]), do_formato=do_formato, do_cliente=do_cliente,
                               n_subidas=n_subidas, historico=historico)

    @app.route("/aprendizado/<cli>/<mod>/subir", methods=["POST"], endpoint="aprendizado_subir")
    def aprendizado_subir(cli, mod):
        ctx = _contexto(cli, mod)
        try:
            flash("✓ " + subir(ctx, request.form.get("id", "").strip()))
        except ValueError as e:
            flash(f"✗ {e}")
        return _volta(ctx)

    @app.route("/aprendizado/<cli>/<mod>/apagar", methods=["POST"], endpoint="aprendizado_apagar")
    def aprendizado_apagar(cli, mod):
        ctx = _contexto(cli, mod)
        try:
            flash("✓ " + apagar(ctx, request.form.get("id", "").strip(), request.form.get("camada", "").strip()))
        except ValueError as e:
            flash(f"✗ {e}")
        return _volta(ctx)
