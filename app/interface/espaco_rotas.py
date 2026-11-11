"""Liberar espaço (/espaco): o que dá pra tirar do disco sem perder o vídeo pronto, tudo pra Lixeira do Mac (recuperável pelo
Finder). Também o tamanho de um vídeo pra confirmar antes de apagar e o Apagar da tela Editar vídeo. O motor é
app/ferramentas/espaco.py."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import espaco as _es  # noqa: E402


def register(app):
    @app.get("/espaco", endpoint="espaco_tela")
    def espaco_tela():
        x = _es.itens_liberaveis()
        import shutil
        from _comum import RAIZ
        livre = shutil.disk_usage(RAIZ).free
        return render_template("espaco.html", x=x, livre=_es.fmt_bytes(livre), ultima=_es.ultima_limpeza())

    @app.post("/espaco/desfazer", endpoint="espaco_desfazer")
    def espaco_desfazer():
        """Devolve pelo Finder o que a última limpeza levou (manifesto em app/.cache/limpezas). Nunca troca o que já existe."""
        try:
            d = _es.desfazer_limpeza(request.form.get("arquivo", ""))
            msg = f"✓ Devolvi {d['devolvidos']} item(ns) da limpeza pro lugar de origem."
            if d["ficaram"]:
                msg += f" {d['ficaram']} já existiam no lugar e ficaram na Lixeira (nada foi trocado)."
            if d["sumiram"]:
                msg += f" {d['sumiram']} não estavam mais na Lixeira (já devolvidos ou esvaziada)."
            flash(msg)
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("espaco_tela"))

    @app.post("/espaco/liberar", endpoint="espaco_liberar")
    def espaco_liberar():
        try:
            r = _es.liberar(request.form.getlist("item"))
            flash(f"✓ {r['itens']} item(ns), {_es.fmt_bytes(r['bytes'])}, foram pra Lixeira do Mac (pasta “{r['nome']}”). "
                  f"Dá pra devolver pelo botão “Desfazer a última limpeza”; o espaço só volta quando você esvaziar a Lixeira. "
                  f"Depois da limpeza esses vídeos não dá mais pra editar nem refazer; o vídeo pronto continua.")
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("espaco_tela"))

    @app.route("/espaco/previa", methods=["GET", "POST"], endpoint="espaco_previa")
    def espaco_previa():
        """O painel "o que vai pra Lixeira" (static/studio.js · templates/_apagar_ui.html). Só olha, nunca apaga. Pedidos:
        ?video=cliente/slug · ?caminho=<mp4 em output> · ?rascunho=<pasta> · ?corte=<slug> (podem repetir) · &aviso=<texto no topo> · ?arquivo=<caminho no Estúdio>&explica=<texto>
        (qualquer outro arquivo) · ?musica=<caminho do áudio> (podem repetir) ou JSON {grupos:[{titulo, rotulo, explica, caminhos:[...]}]} (a tela monta, o servidor mede)."""
        j = request.get_json(silent=True) or {}
        v = request.values
        grupos = list(j.get("grupos") or [])
        for slug in v.getlist("corte"):
            d = Path(_es._comum.ESTUDIO) / "cortes" / Path(slug).name
            if d.is_dir():
                grupos.append({"titulo": slug, "rotulo": "Corte do bruto", "explica": _es.EXPLICA["corte"], "caminhos": [str(d)]})
        try:
            r = _es.previa(v.getlist("video"), v.getlist("caminho"), v.getlist("rascunho"), v.getlist("arquivo"), v.get("explica", ""), grupos, v.getlist("musica"))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e))
        if r["grupos"] and v.get("aviso"):
            r["grupos"][0]["avisos"] = [v["aviso"][:300]] + r["grupos"][0].get("avisos", [])
        if not r["ok"]:
            r["erro"] = (r["recusados"][0]["motivo"] if r["recusados"] else "Não achei nada pra mostrar: pode já ter saído.")
        return jsonify(r)

    @app.get("/espaco/arquivo", endpoint="espaco_arquivo")
    def espaco_arquivo():
        """Serve um vídeo, imagem ou áudio de dentro do Estúdio pra prévia do painel (aceita Range, então o vídeo toca e pula)."""
        try:
            p = _es.dentro_do_estudio(request.args.get("c", ""))
        except ValueError:
            abort(404)
        if not p.is_file() or p.suffix.lower() not in _es.SERVE:
            abort(404)
        r = send_file(p, conditional=True)
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.post("/espaco/finder", endpoint="espaco_finder")
    def espaco_finder():
        """"Mostrar no Finder": `open -R` no caminho. Só de dentro do Estúdio (sem “..”, resolve() dentro da raiz)."""
        try:
            _es.mostrar_no_finder(request.form.getlist("caminho") or (request.get_json(silent=True) or {}).get("caminho", ""))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True)

    @app.get("/espaco/tamanho", endpoint="espaco_tamanho")
    def espaco_tamanho():
        """Quanto vai pra Lixeira do Mac: ?corte=<slug> · ?video=<cliente>/<slug> · ?caminho=<mp4 em output> · ?rascunho=<pasta> (pode repetir)."""
        try:
            if request.args.get("corte"):
                r = _es.tamanho_corte(request.args["corte"])
                return jsonify(ok=True, bytes=r["bytes"], texto=r["texto"], titulo=r["titulo"])
            r = _es.lote(request.args.getlist("video"), request.args.getlist("caminho"), request.args.getlist("rascunho"), medir=True,
                         musicas=request.args.getlist("musica"))
            if not r["apagados"] and r["recusados"]:
                return jsonify(ok=False, erro=r["recusados"][0][1])
            return jsonify(ok=True, bytes=r["bytes"], texto=r["texto"], titulo="", n=r["apagados"])
        except ValueError as e:
            return jsonify(ok=False, erro=str(e))

    @app.post("/espaco/apagar", endpoint="espaco_apagar")
    def espaco_apagar():
        """O Apagar de toda grade de vídeos (página do cliente, Meus vídeos, Editar vídeo, Esperando você): leva tudo do vídeo pra
        Lixeira do Mac. Um ou vários: video (cliente/slug), caminho (mp4 em output/), rascunho (pasta do Editar vídeo)."""
        f = request.form
        r = _es.lote(f.getlist("video"), f.getlist("caminho"), f.getlist("rascunho"), musicas=f.getlist("musica"))
        if r["apagados"] > 1:
            flash(f"✓ {r['apagados']} vídeos apagados: {r['texto']} foram pra Lixeira do Mac. Dá pra recuperar pelo Finder; "
                  f"o espaço volta quando você esvaziar a Lixeira.")
        else:
            for m in r["mensagens"]:
                flash(m)
        for nome, motivo in r["recusados"]:
            flash(f"✗ {nome}: {motivo}")
        if not r["apagados"] and not r["recusados"]:
            flash("Marque pelo menos um item.")
        volta = f.get("volta", "")
        return redirect(volta if volta.startswith("/") and not volta.startswith("//") else url_for("meus_videos"))

    @app.post("/editar/apagar", endpoint="editor_apagar")
    def editor_apagar():
        try:
            flash(_es.apagar_rascunho(request.form.get("pasta", ""))["mensagem"])
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("editor_lista"))
