"""Configurações → colar a chave de API e testar (Conexões e o resto). A chave nunca volta pra tela nem pro log."""
from __future__ import annotations

from flask import flash, redirect, request, url_for

import chaves as _chv
import conexoes as _cx


def registrar_resultado(r: dict, nome: str) -> str:
    if r["ok"]:
        return f"✓ {r['texto']}. Chave {nome} salva ({r['final']}). Custo do teste: {_chv.usd(r['custo'])}."
    guardada = " A chave ficou salva; confira se é a certa." if r.get("final") else ""
    return f"✗ {r['texto']}{guardada} Custo do teste: {_chv.usd(r['custo'])}."


def register(app):
    @app.post("/config/chave/<prov>")
    def config_chave(prov):
        if prov not in _chv.ARQUIVOS:
            flash("✗ Serviço desconhecido.")
            return redirect(url_for("config"))
        r = _chv.salvar_e_testar(prov, request.form.get("chave", ""))
        flash(registrar_resultado(r, _chv.NOMES[prov]))
        return redirect(url_for("config") + "#modelo")

    @app.post("/config/chaves/gravar")
    def config_chave_gravar():
        """Qualquer chave conhecida (kie.ai, Groq, Pexels...) cai em app/.env. O valor nunca volta pra tela."""
        nome = request.form.get("nome", "")
        try:
            fim = _chv.gravar_chave(nome, request.form.get("valor", ""))
            flash(f"✓ {nome.strip().upper()} salva em app/.env ({fim}).")
        except ValueError as e:
            flash(f"✗ {e}")
        return redirect(url_for("config") + "#chaves-onde")


    @app.post("/config/conexoes/<app_id>/testar")
    def conexao_testar(app_id):
        """O "Testar" de cada aplicativo: só consulta chave, saldo ou login. Nunca gera nada, nunca cobra."""
        a = _cx.POR_ID.get(app_id)
        if not a:
            flash("✗ Aplicativo desconhecido.")
        else:
            r = _cx.testar(app_id)
            flash(("✓ " if r["ok"] else "✗ ") + a["nome"] + ": " + r["texto"] + ". Custo do teste: R$ 0,00.")
        return redirect(url_for("config") + "#conexoes")

    @app.post("/config/conexoes/<app_id>/chave")
    def conexao_chave(app_id):
        """"Trocar chave" de um aplicativo: guarda em app/.env e testa de graça."""
        a = _cx.POR_ID.get(app_id)
        if not a or not a["var"]:
            flash("✗ Esse aplicativo não usa chave.")
        else:
            r = _cx.salvar_chave(app_id, request.form.get("chave", ""))
            if r["final"]:
                flash(("✓ " if r["ok"] else "✗ ") + f"{a['nome']}: {r['texto']}." + f" Chave salva ({r['final']})." + ("" if r["ok"] else " Confira se é a certa."))
            else:
                flash("✗ " + r["texto"])
        return redirect(url_for("config") + "#conexoes")
