"""Editor da camada de texto (formato Frase fixa): o vídeo fica limpo e a caixa com a frase é editada por cima,
com prévia na hora; só ao salvar a caixa é queimada no vídeo. A pasta é a do vídeo (tem camada.json)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from flask import abort, flash, redirect, render_template, request, send_file, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import camada as _cam  # noqa: E402
from _comum import RAIZ  # noqa: E402


def pasta_da_camada(rel: str | None) -> Path | None:
    """A pasta (relativa à raiz) se ela tem camada.json e está dentro do Estúdio; senão None."""
    if not rel:
        return None
    p = (RAIZ / rel).resolve()
    if RAIZ.resolve() not in p.parents or not (p / "camada.json").is_file():
        return None
    return p


def register(app):
    app.add_template_global(lambda rel: bool(pasta_da_camada(rel)), "tem_camada")

    def _pasta():
        p = pasta_da_camada(request.values.get("pasta"))
        if not p:
            abort(404)
        return p

    @app.get("/camada")
    def camada_editor():
        p = _pasta()
        c = _cam.carregar(p)
        y_peito = None
        if c.get("tipo") == "caixinha":   # "No peito": abaixo do queixo, pela altura da pergunta atual
            import caixinha as _cx
            y_peito = _cx.topo_padrao("peito", c.get("texto", ""), c.get("titulo") or _cx.TITULO_PADRAO)
        return render_template("camada.html", c={**_cam.PADRAO, **c}, y_peito=y_peito, pasta=str(p.relative_to(RAIZ.resolve())),
                               fontes=_cam.fontes(), voltar=request.args.get("voltar") or url_for("andamento_lista"))

    @app.get("/camada/previa.png")
    def camada_previa():
        p = _pasta()
        args = request.args.to_dict()
        if _cam.carregar(p).get("tipo") == "caixinha":   # o tipo vem do camada.json, não da tela
            args["tipo"] = "caixinha"
        img = _cam.caixa_png(args)
        b = io.BytesIO()
        img.save(b, "PNG")
        b.seek(0)
        r = send_file(b, mimetype="image/png")
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.post("/camada/salvar")
    def camada_salvar():
        p = _pasta()
        dados = {k: request.form.get(k) for k in (*_cam.PADRAO, "titulo")}
        if _cam.carregar(p).get("tipo") == "caixinha":
            dados["tipo"] = "caixinha"
        _cam.salvar(p, dados)
        volta = redirect(url_for("camada_editor", pasta=request.form.get("pasta"), voltar=request.form.get("voltar")))
        if request.form.get("acao") != "video":
            flash("✓ Texto salvo. O vídeo ainda não mudou: clique em Gerar o vídeo quando estiver bom.")
            return volta
        try:
            saida = _cam.renderizar(p)
        except Exception as e:
            flash(f"✗ Não consegui gerar o vídeo: {e}")
            return volta
        c = _cam.carregar(p)
        if c.get("andamento"):
            try:
                import andamento as _and
                cli, slug = c["andamento"]
                _and.registrar(cli, slug, "Texto editado na camada: vídeo gerado de novo", "pronto",
                               video=str(saida.relative_to(RAIZ)))
            except Exception:
                pass
        flash("✓ Vídeo gerado com o texto novo. Assista e baixe aqui embaixo.")
        return volta
