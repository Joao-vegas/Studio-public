"""Revisão do Estúdio (revisao.py), Melhoria sugerida (melhoria.py) e Recarregar agora (recarregar.py)."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import melhoria as _mel  # noqa: E402
import recarregar as _rec  # noqa: E402
import revisao as _rev  # noqa: E402


def _volta(padrao: str):
    v = request.form.get("volta", "")
    return redirect(v if v.startswith("/") and not v.startswith("//") else padrao)


def revisao_do_video(cli: str, slug: str) -> dict | None:
    """A revisão do vídeo + a melhoria de cada achado (pra o cartão mostrar o botão certo). None se nunca rodou."""
    r = _rev.carregar(cli, slug)
    if not r:
        return None
    r = dict(r)
    r["rodando"] = r.get("estado") == "rodando" and _rev._vivo(r.get("pid"))
    if r.get("estado") == "rodando" and not r["rodando"]:
        r["estado"] = "erro"
        r["erro"] = "A revisão parou no meio (o Estúdio reiniciou). Clique em Revisar de novo."
    r["melhorias"] = {a["id"]: _mel.carregar(a["melhoria"]) for a in r.get("achados", []) if a.get("melhoria")}
    return r


def _cor_diff(diff: str) -> str:
    import html
    out = []
    for ln in (diff or "").splitlines():
        e = html.escape(ln)
        cls = "arq" if ln.startswith(("+++", "---", "@@")) else ("mais" if ln.startswith("+") else ("menos" if ln.startswith("-") else ""))
        out.append(f'<span class="{cls}">{e}</span>' if cls else e)
    return "\n".join(out)


def register(app):
    app.add_template_global(revisao_do_video, name="revisao_do_video")

    @app.get("/api/recarregar")
    def recarregar_estado():
        return jsonify(_rec.estado())

    @app.post("/api/recarregar")
    def recarregar_pedir():
        return jsonify(_rec.pedir())

    @app.get("/api/revisao/<cli>/<slug>")
    def revisao_api(cli, slug):
        return jsonify(revisao_do_video(cli, slug) or {"estado": "nunca"})

    @app.post("/revisao/<cli>/<slug>/rodar")
    def revisao_rodar(cli, slug):
        import producao as P
        j = P.carregar(cli, slug)
        if not j or not j.get("saida"):
            flash("✗ Esse vídeo ainda não tem o final pra revisar.")
        elif _rev.disparar(cli, slug):
            flash("✓ Revisando o vídeo. O resultado aparece aqui em alguns minutos.")
        else:
            flash("A revisão já está rodando.")
        return _volta(url_for("andamento_ver", cli=cli, slug=slug))

    @app.get("/melhoria/<id_>")
    def melhoria_ver(id_):
        rec = _mel.carregar(id_)
        if not rec:
            abort(404)
        pasta = _mel.pasta_melhorias() / id_
        imgs = {k: _rel_ou_vazio(pasta / f"{k}.jpg") for k in ("antes", "depois")}
        return render_template("melhoria.html", m=rec, diff_html=_cor_diff(rec.get("diff", "")), imgs=imgs)

    @app.get("/api/melhoria/<id_>")
    def melhoria_api(id_):
        rec = _mel.carregar(id_)
        return jsonify({k: rec.get(k) for k in ("id", "estado", "motivo")} if rec else {"estado": "nao_existe"})

    @app.post("/melhoria/<id_>/<acao>")
    def melhoria_acao(id_, acao):
        mapa = {"ver": "ver", "aplicar": "aplicar", "desfazer": "desfazer", "agora-nao": "agora_nao"}
        if acao not in mapa:
            abort(404)
        try:
            rec = _mel.pedir(mapa[acao], id_)
            flash({"ver": "✓ Preparando a mudança numa cópia. Nada foi alterado ainda.",
                   "aplicar": "✓ Aplicando: preparo, testo e só grava se passar.",
                   "desfazer": "✓ Desfeito: o arquivo voltou como estava antes.",
                   "agora_nao": "✓ Deixei pra depois. Não pergunto de novo por um tempo."}[mapa[acao]])
        except ValueError as e:
            flash("✗ " + str(e))
        return _volta(url_for("melhoria_ver", id_=id_))

    @app.get("/melhorias")
    def melhorias_lista():
        return render_template("melhorias.html", itens=_mel.listar())


def _rel_ou_vazio(p: Path) -> str:
    import _comum
    return _comum.rel(p) if p.is_file() else ""
