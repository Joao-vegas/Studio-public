"""Aba Em andamento: o passo atual de cada vídeo (tela ou chat), com storyboard e linha do tempo. Atualiza sozinha."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import abort, flash, redirect, render_template, request, url_for

import andamento as _and
import editor as _ed
from _comum import RAIZ

FERRAMENTAS = Path(__file__).resolve().parents[1] / "ferramentas"


def ajustar_storyboard_da_tela(cli: str, slug: str, texto: str, segundo=None) -> bool:
    """Vídeo feito pela tela, em formato com esteira, parado no storyboard: refaz só as cenas que o João citou.
    Devolve True se disparou. Os testes trocam esta função."""
    import producao as _prod
    j = _prod.carregar(cli, slug)
    if not j or not _prod._esteira(j) or j.get("rodando") or j.get("status") != "plano":
        return False   # só storyboard esperando aprovação; vídeo já renderizado segue o caminho de sempre
    pedido = texto + (f" (marcado no segundo {segundo} do storyboard/vídeo)" if segundo not in (None, "") else "")
    _prod.analisar(cli, slug, ajuste=pedido)
    return True


def register(app):
    import producao as _prod
    app.add_template_global(_prod.referencia_storyboard)   # "Referência: usada / não usada porque…" no topo do storyboard
    @app.context_processor
    def _contagem_andamento():
        return {"n_andamento": _and.contagem()}

    @app.route("/andamento")
    def andamento_lista():
        _prod.reconciliar()
        itens = _and.listar()
        if request.args.get("parcial"):
            return render_template("_andamento.html", itens=itens, modo="lista")
        return render_template("andamento.html", itens=itens)

    @app.route("/andamento/<cli>/<slug>")
    def andamento_ver(cli, slug):
        _prod.reconciliar(cli, slug)
        d = _and.carregar(cli, slug)
        if not d:
            abort(404)
        pe = _pasta_editavel(d)
        if request.args.get("parcial"):
            return render_template("_andamento.html", d=d, modo="detalhe", sem_player=bool(pe))
        pv = pagina_video(d, pe)
        return render_template("andamento_ver.html", d=d, refs=_and.referencias(d.get("formato") or ""), pv=pv, **pv["editor"])

    def _pasta_editavel(d):
        """Vídeo pronto, com arquivo, que o editor por cena aceita: a pasta dele (Path). Senão None."""
        if d.get("estado") != "pronto" or not d.get("video"):
            return None
        return _ed.pasta(d.get("pasta") or pasta_do_video(d["cliente"], d["slug"]))

    def _referencia_do_video(job):
        """A pasta de formatos/<estilo>/estudos/ que já guarda ESTE vídeo como referência ('' = ainda não)."""
        if not job.get("saida") or not job.get("formato"):
            return ""
        base = RAIZ / "formatos" / job["formato"] / "estudos"
        if base.is_dir():
            for e in sorted(base.iterdir()):
                f = e / "ESTUDO.md"
                if f.is_file() and job["saida"] in f.read_text(encoding="utf-8", errors="ignore"):
                    return e.name
        return ""

    def pagina_video(d, pe):
        """O que a página do vídeo pronto precisa: modo ('editor' = editor por cena primeiro · 'motivo' = não edita, com o motivo ·
        'antigo' = vídeo ainda em produção ou sem arquivo), o estado "Aprovado — e agora?" e o contexto do miolo do editor."""
        pv = {"modo": "antigo", "motivo": "", "editor": {}, "aprovado": "", "pode_desfazer": False, "job": {}, "referencia": "",
              "pode_referencia": False, "pasta": ""}
        if d.get("estado") != "pronto":
            return pv
        pasta = d.get("pasta") or pasta_do_video(d["cliente"], d["slug"])
        pv["pasta"] = pasta
        job = _prod.carregar(d["cliente"], d["slug"]) or {}
        fechado = job.get("status") in _prod.FECHADOS
        pv["job"] = job
        pv["aprovado"] = _and.aprovado_em(d) or ("sim" if fechado else "")
        pv["pode_desfazer"] = bool(_and.aprovado_em(d)) and job.get("status") not in ("exportado", "arquivado")
        pv["referencia"] = _referencia_do_video(job)
        pv["pode_referencia"] = bool(job.get("saida") and job.get("formato") and (RAIZ / job["saida"]).is_file())
        if pe:
            pv.update(modo="editor", editor=app.config["contexto_editor"](pe))
        elif d.get("video") and pasta:
            try:
                pv["motivo"] = _ed.motivo_sem_edicao(RAIZ / pasta) or ""
            except Exception:  # noqa: BLE001
                pv["motivo"] = ""
            if pv["motivo"]:
                pv["modo"] = "motivo"
        return pv

    @app.route("/andamento/<cli>/<slug>/desfazer-aprovacao", methods=["POST"])
    def andamento_desfazer_aprovacao(cli, slug):
        """"Desfazer aprovação": o vídeo volta pro "Ficou bom?" e pro Esperando você (e o job, de aprovado pra concluído)."""
        volta = redirect(url_for("andamento_ver", cli=cli, slug=slug))
        job = _prod.carregar(cli, slug) or {}
        if job.get("status") in ("exportado", "arquivado"):
            flash("✗ Este vídeo já foi guardado no iCloud: a aprovação não volta mais.")
            return volta
        if not _and.desfazer_aprovacao(cli, slug):
            flash("Não havia aprovação valendo.")
            return volta
        if job.get("status") == "aprovado" and not job.get("rodando"):
            job["status"] = "concluido"
            _prod.salvar(job)
        flash("✓ Aprovação desfeita. O vídeo voltou pro \"Ficou bom?\".")
        return volta

    def pasta_do_video(cli, slug):
        """Pasta de trabalho do vídeo (a do job), pros botões Editar o texto / Editar por cena quando o registro do Em andamento não traz."""
        d = _and.carregar(cli, slug) or {}
        if d.get("pasta"):
            return d["pasta"]
        j = _prod.carregar(cli, slug) or {}
        return j.get("sandbox") or ""
    app.add_template_global(pasta_do_video)

    def cenas_do_storyboard(cli, slug):
        """Trechos com cena de apoio do storyboard esperando aprovação: a escolhida e as outras opções de cada um,
        pra o João trocar ali mesmo (sem abrir a página antiga do vídeo). [] quando não há o que trocar."""
        j = _prod.carregar(cli, slug)
        if not j or j.get("rodando") or j.get("status") != "plano":
            return []
        out = []
        for b in (_prod.plano(j) or {}).get("beats") or []:
            ops = [o for o in b.get("opcoes") or [] if not o.get("registro_busca")]
            if b.get("tipo") not in ("broll", "citacao") or not ops:
                continue
            for o in ops:
                capa = o.get("gif") or o.get("poster") or o.get("sheet")
                o["_capa"] = f"{j['sandbox']}/{capa}" if capa and (RAIZ / j["sandbox"] / capa).is_file() else ""
            out.append({**b, "opcoes": ops, "_escolha": b.get("escolha") or ops[0]["id"]})
        return out
    app.add_template_global(cenas_do_storyboard)

    def folhas_de_previa(cli, slug):
        """Folhas de prévia do b-roll (work/brolls/folha-<cena>.jpg, 3 opções por cena com fonte, link e tempo) do vídeo."""
        j = _prod.carregar(cli, slug)
        if not j or not j.get("sandbox"):
            return []
        import _comum                                   # lido na hora: os testes trocam a raiz
        pasta = _comum.RAIZ / j["sandbox"] / "work" / "brolls"
        return [{"cena": f.stem.replace("folha-", ""), "caminho": str(f.relative_to(_comum.RAIZ))} for f in sorted(pasta.glob("folha-*.jpg"))]

    app.add_template_global(folhas_de_previa)

    @app.route("/andamento/<cli>/<slug>/cena", methods=["POST"])
    def andamento_cena(cli, slug):
        """Troca a cena de um trecho no storyboard: grava a escolha no PLANO.json (sem aprovar) e refaz a folha."""
        volta = redirect(url_for("andamento_ver", cli=cli, slug=slug) + "#and-cenas")
        j = _prod.carregar(cli, slug)
        if not j or j.get("rodando") or j.get("status") != "plano":
            flash("Agora não dá pra trocar a cena: o vídeo não está parado no storyboard.")
            return volta
        p = _prod.plano(j) or {}
        bid, oid = request.form.get("beat", ""), request.form.get("opcao", "")
        b = next((x for x in p.get("beats") or [] if x.get("id") == bid), None)
        if not b or (oid != "nenhum" and not any(o.get("id") == oid for o in b.get("opcoes") or [])):
            abort(400)
        b["escolha"] = None if oid == "nenhum" else oid
        p.pop("aprovado_em", None)
        _prod.salvar_plano(j, p)
        try:
            sys.path.insert(0, str(FERRAMENTAS))
            import storyboard as _sb
            img = _sb.gerar(RAIZ / j["sandbox"])["saida"]
            _and.espera(cli, slug, "Cena trocada: confira o storyboard", etapa="aprovacao",
                        imagem=str(Path(img).resolve().relative_to(RAIZ)))
        except Exception as e:
            flash(f"Cena trocada, mas o storyboard não foi refeito: {e}")
            return volta
        flash("✓ Cena trocada. O storyboard já mostra a nova.")
        return volta

    @app.route("/andamento/<cli>/<slug>/esconder", methods=["POST"])
    def andamento_esconder(cli, slug):
        _and.esconder(cli, slug)
        flash("✓ Tirado da lista. Volta sozinho se o vídeo andar de novo.")
        return redirect(url_for("andamento_lista"))

    @app.route("/andamento/<cli>/<slug>/responder", methods=["POST"])
    def andamento_responder(cli, slug):
        d = _and.carregar(cli, slug)
        if not d:
            abort(404)
        decisao = request.form.get("decisao", "")
        texto = request.form.get("texto", "")
        volta = redirect(url_for("andamento_ver", cli=cli, slug=slug))
        if d.get("estado") not in ("esperando", "pronto"):
            flash("Ainda não dá pra responder: o vídeo está sendo feito.")
            return volta
        try:
            _, idx = _and.responder(cli, slug, decisao, texto, request.form.get("ref", ""), request.form.get("segundo"))
        except ValueError as e:
            flash(str(e))
            return volta
        if decisao == "ajustar" and d["estado"] == "esperando" and d.get("origem") == "tela" \
                and ajustar_storyboard_da_tela(cli, slug, texto, request.form.get("segundo")):
            _and.marcar_resposta(cli, slug, idx, "feito")
            flash("✓ Pedido enviado. Estou refazendo só as cenas que você citou.")
        elif decisao == "aprovar" and d["estado"] == "esperando" and d.get("origem") == "tela":
            # qualquer formato pela tela: o Aprovar faz o vídeo andar
            try:
                msg = _prod.avancar(cli, slug)
                _and.marcar_resposta(cli, slug, idx, "feito")
                flash(msg or "✓ Aprovado.")
            except Exception as e:
                _and.marcar_resposta(cli, slug, idx, "erro")
                flash(f"✗ Não consegui seguir: {e}")
        else:
            _and.marcar_resposta(cli, slug, idx, "feito")
            flash("✓ Aprovado. O vídeo passou pra Meus vídeos." if decisao == "aprovar" and d["estado"] == "pronto" else "✓ Anotado no aprendizado. Peça no chat pra aplicar.")
        if decisao == "aprovar" and d["estado"] == "pronto":
            _prod.reconciliar(cli, slug)   # aprovado: o job vira "aprovado" e o vídeo sai de Em andamento
        if decisao == "ajustar":   # REGRA Nº 2 com gate: propõe o "Aprendi: <regra> · vale pra ..." e espera o OK
            try:
                import aprendi as _ap
                j = _prod.carregar(cli, slug) or {}
                rec = _ap.propor(cli, slug, texto, formato=d.get("formato") or "", modelo=j.get("modelo") or "",
                                 titulo=d.get("titulo") or slug, ref=request.form.get("ref", ""), segundo=request.form.get("segundo"))
                if rec:
                    flash(_ap.frase(rec) + ". Confira abaixo: OK ou Não é isso.")
            except Exception as e:  # noqa: BLE001  nunca derruba a resposta do João
                print(f"(aprendi não propôs: {e})", file=sys.stderr)
        return volta
