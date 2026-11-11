"""Tela Saídas: tudo que está em output/ dos clientes, com Apagar (um ou vários) e Guardar como referência.
Também os botões do "Ficou bom?" da tela Em andamento (Guardar como referência · Apagar · Deixar por enquanto)."""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

import andamento as _and
import formatos as _fmt
import reuso as _reuso
import saidas as _s


def saida_do_andamento(d: dict) -> dict | None:
    """A saída (pasta/.mp4 em output/) de um vídeo da aba Em andamento, se existir."""
    pasta = _and.pasta_do_episodio(d) if d else None
    for c in (d.get("pasta"), pasta, d.get("video")) if d else ():
        if not c:
            continue
        try:
            return _s.item(str(c))
        except ValueError:
            continue
    return None


def _avisar(r: dict) -> None:
    if r["apagados"]:
        flash(_s.mensagem(r))
        for a in r["apagados"]:
            for av in a.get("avisos", []):
                flash(f"Ficou: {av}")
    refs = [x for x in r["recusados"] if x["motivo"].startswith("É referência")]
    if refs:
        flash(f"{len(refs)} referência(s) ficaram. Referência só sai sozinha, no botão Apagar dela.")
    for x in r["recusados"]:
        if x not in refs:
            flash(f"✗ {x['motivo']}")


def register(app):
    app.add_template_global(saida_do_andamento)

    @app.route("/saidas")
    def saidas_lista():
        quem = request.args.get("cliente", "")
        itens = _s.listar(quem)
        for i in itens:
            i["formato"] = (i["referencia"] or {}).get("formato") or _s.formato_sugerido(i["modelo"])
        clientes = sorted({p.parts[-3] for p in (_s._raiz() / "clientes").glob("*/*Content/output")})
        return render_template("saidas.html", itens=itens, total=_s.total(itens), quem=quem, clientes=clientes,
                               formatos=_fmt.listar(ocultos=True))

    @app.route("/saidas/apagar", methods=["POST"])
    def saidas_apagar():
        caminhos = request.form.getlist("caminho")
        if not caminhos:
            flash("Marque pelo menos um vídeo.")
        else:
            _avisar(_s.apagar(caminhos, confirmar=request.form.get("confirmar") == "1" and len(caminhos) == 1))
        return redirect(url_for("saidas_lista", cliente=request.form.get("cliente") or None))

    @app.route("/reusar", methods=["GET", "POST"])
    def reusar():
        """'Usar em outro formato': escolha curta dos formatos que recebem vídeo gravado; cria o job com a cópia do mp4."""
        dados = request.form if request.method == "POST" else request.args
        caminho = dados.get("caminho", "")
        try:
            it = _s.item(caminho)
            if request.method == "POST":
                job = _reuso.usar(caminho, dados.get("formato", ""), dados.get("titulo", ""))
                flash("✓ Vídeo novo criado com a cópia. Clique em Montar o storyboard.")
                return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))
            return render_template("reusar.html", caminho=caminho, nome=dados.get("titulo") or it["slug"],
                                   opcoes=_reuso.opcoes(_s.formato_sugerido(it["modelo"])))
        except ValueError as e:
            flash(f"✗ {e}")
            return redirect(url_for("saidas_lista"))

    @app.route("/saidas/referencia", methods=["POST"])
    def saidas_referencia():
        try:
            _s.guardar_referencia(request.form.get("caminho", ""), request.form.get("formato", ""), request.form.get("motivo", ""))
            flash("✓ Guardado como referência. Virou exemplo do formato e não sai em \"Apagar marcados\".")
        except ValueError as e:
            flash(f"✗ {e}")
        return redirect(url_for("saidas_lista", cliente=request.form.get("cliente") or None))

    @app.route("/andamento/<cli>/<slug>/saida", methods=["POST"])
    def andamento_saida(cli, slug):
        d = _and.carregar(cli, slug)
        if not d:
            abort(404)
        volta = redirect(url_for("andamento_ver", cli=cli, slug=slug))
        acao = request.form.get("acao", "")
        if acao == "deixar":
            flash("Ok, fica guardado. Dá pra apagar depois em Meus vídeos → Saídas.")
            return volta
        s = saida_do_andamento(d)
        if not s and acao != "apagar":
            flash("✗ Não achei o vídeo na pasta output.")
            return volta
        if acao == "referencia":
            if request.form.get("confirmar") != "1":   # Aprovou? Mostra onde vai e pergunta antes de guardar
                return redirect(url_for("job_virar_referencia", cli=cli, slug=slug))
            try:
                _s.guardar_referencia(s["caminho"], d.get("formato") or _s.formato_sugerido(s["modelo"]), "Aprovado na tela Em andamento")
                flash("✓ Guardado como referência. Virou exemplo do formato.")
            except ValueError as e:
                flash(f"✗ {e}")
            return volta
        if acao == "apagar":   # o caminho único: some tudo (saída, projeto, rascunhos, registro daqui)
            confirmar = request.form.get("confirmar") == "1"
            r = _s.apagar([s["caminho"]], confirmar=confirmar) if s else _s.apagar_video(cli, slug, confirmar=confirmar)
            _avisar(r)
            return redirect(url_for("andamento_lista")) if r["apagados"] else volta
        abort(400)
