"""Conversa de briefing (passo 0 do Criar vídeo): criar, mandar mensagem (resposta em partes, SSE), ver e editar o
rascunho, ajustar modelo/pastas/teto e fechar. O motor é app/ferramentas/conversa.py.

Registrado no servidor com:
    from conversa_rotas import register as register_conversa
    register_conversa(app)
"""
from __future__ import annotations

import json

from flask import Response, jsonify, request

import conversa as _c


def _dados() -> dict:
    return request.get_json(silent=True) or request.form.to_dict() or {}


def _lista(v) -> list[str]:
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    return [x for x in (v or []) if x]


def _sim(v) -> bool:
    return v in (True, 1) or str(v).lower() in ("1", "true", "sim", "on")


def _erro(e: Exception, status: int = 400):
    return jsonify({"erro": str(e)}), status


def register(app):
    @app.get("/conversa/lista")
    def conversa_lista():
        return jsonify(_c.listar())

    @app.post("/conversa/nova")
    def conversa_nova():
        d = _dados()
        try:
            return jsonify(_c.criar(d.get("cliente", ""), d.get("formato", ""), _lista(d.get("pastas")),
                                    d.get("modelo") or _c.PADRAO, _sim(d.get("descartavel"))))
        except ValueError as e:
            return _erro(e)

    @app.get("/conversa/<bid>")
    def conversa_ver(bid):
        try:
            return jsonify(_c.ver(bid))
        except ValueError as e:
            return _erro(e, 404)

    @app.post("/conversa/<bid>/mensagem")
    def conversa_mensagem(bid):
        """SSE (uma linha 'data: {...}' por evento). Com ?inteiro=1 devolve tudo de uma vez em JSON."""
        d = _dados()
        try:
            _c.estado(bid)
        except ValueError as e:
            return _erro(e, 404)
        if _sim(request.args.get("inteiro")):
            return jsonify(_c.responder(bid, d.get("texto", "")))

        def partes():
            for ev in _c.enviar(bid, d.get("texto", "")):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return Response(partes(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/conversa/<bid>/briefing")
    def conversa_briefing(bid):
        try:
            return jsonify(_c.briefing(bid))
        except ValueError as e:
            return _erro(e, 404)

    @app.post("/conversa/<bid>/briefing")
    def conversa_editar(bid):
        try:
            return jsonify(_c.editar_briefing(bid, _dados()))
        except ValueError as e:
            return _erro(e)

    @app.post("/conversa/<bid>/ajustar")
    def conversa_ajustar(bid):
        d = _dados()
        try:
            return jsonify(_c.ajustar(bid, d.get("modelo") or None,
                                      _lista(d["pastas"]) if "pastas" in d else None, _sim(d.get("liberar"))))
        except ValueError as e:
            return _erro(e)

    @app.post("/conversa/<bid>/fechar")
    def conversa_fechar(bid):
        try:
            return jsonify(_c.fechar(bid))
        except ValueError as e:
            return _erro(e)
