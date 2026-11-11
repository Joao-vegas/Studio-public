"""Tela Elenco (PLANO-2.0, item 7). /elenco lista os estilos que têm personagens (hoje só o Explicador 3D); /elenco/<slug> é a tela
de cada um: os personagens em 3D, com cor, roupa, cabelo e pele editáveis. O elenco é do ESTILO, não do cliente:
fica em formatos/<slug>/elenco.json. Estilo novo entra no registro ELENCOS de app/ferramentas/elenco.py, sem mexer aqui.
A prévia 3D roda no navegador (static/elenco-previa.js) com os módulos do formato."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import abort, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import elenco as _el  # noqa: E402


def register(app):
    @app.get("/elenco")
    def elenco_tela():
        return render_template("elenco.html", estilos=_el.estilos())

    @app.get("/elenco/<slug>")
    def elenco_estilo(slug):
        if not _el.existe(slug):
            abort(404)
        c = _el.ELENCOS[slug]
        return render_template("elenco_estilo.html", slug=slug, titulo=c["titulo"], elenco=_el.ler(slug), rotulos=_el.rotulos(slug),
                               previa=_el.previa(slug))

    @app.post("/elenco/<slug>/salvar")
    def elenco_salvar(slug):
        d = request.get_json(silent=True) or {}
        try:
            nome = _el.salvar(slug, d.get("nome", ""), d.get("base", ""), d.get("troca") or {})
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True, nome=nome)

    @app.post("/elenco/<slug>/voltar")
    def elenco_voltar(slug):
        d = request.get_json(silent=True) or {}
        if not _el.existe(slug):
            return jsonify(ok=False, erro=f"O estilo '{slug}' não tem elenco."), 400
        return jsonify(ok=True, havia=_el.remover(slug, d.get("nome", "")))
