"""Tela Estudar um vídeo (PLANO-2.0, item 13): link ou arquivo → estudo quadro a quadro a 30 fps → vira referência
de um estilo. A lógica fica em app/ferramentas/estudos_tela.py."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import estudos_tela as _et  # noqa: E402


def register(app):
    @app.get("/estudar")
    def estudar_lista():
        return redirect(url_for("referencias") + "#jogar")   # Referências é a porta única; o estudo quadro a quadro roda dentro do "Jogar um vídeo"

    @app.post("/estudar")
    def estudar_novo():
        arqs = []
        for up in request.files.getlist("videos"):
            if up and up.filename:
                alvo = Path(tempfile.mkdtemp()) / Path(up.filename).name
                up.save(alvo)
                arqs.append(alvo)
        try:
            sid = _et.novo(request.form.get("links", "").splitlines(), arqs, request.form.get("nome", ""), auto=True)
        except ValueError as e:
            flash("✗ " + str(e))
            return redirect(url_for("estudar_lista"))
        return redirect(url_for("estudar_ver", sid=sid))

    @app.get("/estudar/<sid>")
    def estudar_ver(sid):
        import formatos
        try:
            e = _et.ver(sid)
        except (ValueError, StopIteration):
            abort(404)
        import regua_tela
        confirmando = request.args.get("juntar", "")
        alvo = _et.destino_previsto(confirmando, e["nome"]) if confirmando and formatos.carregar(confirmando) else ""
        return render_template("estudar_ver.html", e=e, formatos=formatos.listar(), regua=regua_tela.resumo(_et.PASTA / sid / "estudo-quadros"),
                               confirmando=confirmando if alvo else "", alvo=alvo, titulo_estilo=(formatos.carregar(confirmando) or {}).get("titulo", confirmando))

    @app.get("/estudar/<sid>/estado")
    def estudar_estado(sid):
        try:
            return jsonify(_et.ver(sid)["estado"])
        except (ValueError, StopIteration):
            abort(404)

    @app.post("/estudar/<sid>/tirar")
    def estudar_tirar(sid):
        import remover as _rm
        try:
            _rm.remover_pasta(str((_et.PASTA / Path(sid).name).relative_to(_et.RAIZ)), "estudo " + sid)
            flash("✓ O estudo foi pra lixeira (Configurações → Lixeira → Restaurar).")
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("estudar_lista"))

    @app.post("/estudar/<sid>/juntar")
    def estudar_juntar(sid):
        if request.form.get("confirmar") != "1":   # Aprovou? Primeiro mostra onde vai parar; só junta no segundo clique
            return redirect(url_for("estudar_ver", sid=sid, juntar=request.form.get("formato", "")) + "#aprovou")
        try:
            onde = _et.juntar(sid, request.form.get("formato", ""))
        except ValueError as e:
            flash("✗ " + str(e))
            return redirect(url_for("estudar_ver", sid=sid))
        flash(f"✓ Virou referência do estilo ({onde}). Ela aparece em Estilos e no Criar, em \"Qual referência seguir\".")
        return redirect(url_for("formato_detalhe", slug=request.form.get("formato", "")) + "#estudos")
