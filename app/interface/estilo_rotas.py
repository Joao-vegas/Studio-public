"""Referência rápida (2.0): joga um vídeo ou link e o Estúdio entende o estilo. Lógica em ferramentas/estilo_ref.py."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from flask import abort, flash, redirect, render_template, request, send_file, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import estilo_ref as _er  # noqa: E402
import estilo_novo as _en  # noqa: E402
import ref_conjunto as _rc  # noqa: E402
import regua_tela as _rt  # noqa: E402
import variacoes as _vr  # noqa: E402
import frase_estilo as _fe  # noqa: E402
import formatos as _fmt  # noqa: E402
import ia  # noqa: E402
from _comum import clientes as _clientes  # noqa: E402


def register(app):
    def _estado(id_):
        st = _er.estado(id_)
        if not st:
            abort(404)
        return st

    @app.route("/referencia-rapida", methods=["GET", "POST"])
    def referencia_rapida():
        if request.method == "POST":
            cliente = request.form.get("cliente", "")
            novo = request.form.get("estilo_novo") == "1"
            tmp = Path(tempfile.mkdtemp(prefix="refrapida-"))
            fontes = []
            try:
                for i, arq in enumerate(request.files.getlist("video"), 1):
                    if arq and arq.filename:
                        dst = tmp / f"video-{i}{Path(arq.filename).suffix.lower()}"
                        arq.save(dst)
                        fontes.append(str(dst))
                for linha in (request.form.get("link", "") + "\n" + request.form.get("links", "")).splitlines():
                    if linha.strip():
                        fontes.append(linha.strip())
                if not fontes:
                    raise ValueError("Mande um vídeo ou cole um link.")
                if len(fontes) == 1:   # um só: a página de sempre; a IA copia o arquivo, então dá pra limpar o temporário
                    id_ = _er.entender(fontes[0], cliente, gate=True, auto=True, estilo_novo=novo)
                    destino = url_for("referencia_rapida_ver", id_=id_)
                else:                  # um SET: cada vídeo entendido + a régua conjunta
                    cid = _rc.criar(fontes, cliente, request.form.get("nome", ""), auto=True, estilo_novo=novo)
                    destino = url_for("referencia_rapida_set", cid=cid)
            except ValueError as e:
                flash("✗ " + str(e))
                return redirect(url_for("referencias") + "#jogar")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            return redirect(destino)
        return redirect(url_for("referencias") + "#jogar")   # a tela única de Referências tem o "Jogar um vídeo"

    @app.get("/referencia-rapida/<id_>")
    def referencia_rapida_ver(id_):
        st = _estado(id_)
        e = _er.estilo_de(id_) if st["estado"] in ("pronto", "confirmado") else {}
        fmts = _fmt.listar()
        titulos = {f["slug"]: f.get("titulo") or f["slug"] for f in fmts}
        fs = e.get("formato_sugerido") or {}
        perto = fs.get("perto") if fs.get("perto") in titulos else (fs.get("slug") if fs.get("slug") in titulos else "")
        return render_template("referencia_rapida_ver.html", st=st, e=e, formatos=fmts, titulos=titulos,
                               serve=bool(e) and _er.serve(e), perto=perto, nome_curto=_er.nome_curto(st),
                               tem_video=bool(_er.video_de(id_)), regua=_rt.resumo(_er.pasta(id_) / "quadros"),
                               variacoes=_vr.do_conjunto([id_]), frase_ensinou=_fe.da_referencia(e))

    @app.post("/referencia-rapida/<id_>/confirmar")
    def referencia_rapida_confirmar(id_):
        _estado(id_)
        try:
            r = _er.confirmar(id_, request.form.get("formato") or None, request.form.get("nome", ""),
                              request.form.get("principal") == "1")
            flash(("✓ Guardei no estilo " + (_fmt.carregar(r["formato"]) or {}).get("titulo", r["formato"]) + ".") if r["ok"] else r["aviso"])
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("referencia_rapida_ver", id_=id_))

    @app.post("/referencia-rapida/<id_>/criar-estilo")
    def referencia_rapida_criar_estilo(id_):
        """Estilo novo sem terminal: nasce EM TESTE (receita, oculto) com a referência como principal. Só vira pronto
        quando o João aprovar o 1º vídeo de teste (estilo_novo.py)."""
        st = _estado(id_)
        if st.get("estado") != "pronto":
            flash("✗ Esta referência ainda não está pronta.")
            return redirect(url_for("referencia_rapida_ver", id_=id_))
        try:
            slug = _en.criar(id_, request.form.get("nome", ""))
        except ValueError as e:
            flash("✗ " + str(e))
            return redirect(url_for("referencia_rapida_ver", id_=id_))
        flash("✓ Criei o estilo em TESTE e guardei a referência nele. Ele só vira pronto quando você aprovar o 1º vídeo de teste.")
        return redirect(url_for("estilo_novo_ver", slug=slug))

    @app.post("/referencia-rapida/<id_>/descartar")
    def referencia_rapida_descartar(id_):
        st = _estado(id_)
        if st.get("estado") == "confirmado":
            flash("✗ Esta referência já está guardada num estilo.")
            return redirect(url_for("referencia_rapida_ver", id_=id_))
        import remover
        remover.remover_pasta(f"app/.estilos/{id_}", "referência " + _er.nome_curto(st))
        flash("✓ Descartei a referência. Ela foi pra lixeira (Configurações → Lixeira → Restaurar).")
        return redirect(url_for("referencia_rapida"))

    # ───────────── set de referências (vários vídeos de uma vez) ─────────────

    def _set(cid):
        try:
            s = _rc.situacao(cid)
        except ValueError:
            abort(404)
        return s

    @app.get("/referencia-rapida/set/<cid>")
    def referencia_rapida_set(cid):
        s = _set(cid)
        c = s["conjunto"]
        fmts = _fmt.listar()
        regua = _rt.resumo(_rc.pasta(cid) / "quadros") if c.get("regua") else {}
        prontos = [i["id"] for i in s["itens"] if i.get("estado") in ("pronto", "confirmado")]
        return render_template("referencia_rapida_set.html", s=s, c=c, formatos=fmts, regua=regua,
                               estilos={i["id"]: _er.estilo_de(i["id"]) for i in s["itens"] if i.get("estado") in ("pronto", "confirmado")},
                               variacoes=_vr.do_conjunto(prontos) if prontos else [])

    @app.post("/referencia-rapida/set/<cid>/confirmar")
    def referencia_rapida_set_confirmar(cid):
        _set(cid)
        try:
            r = _rc.confirmar(cid, request.form.get("formato", ""), request.form.get("nome", ""), request.form.get("principal", ""))
            flash(f"✓ Guardei {len(r)} referência(s) no estilo.")
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("referencia_rapida_set", cid=cid))

    @app.post("/referencia-rapida/set/<cid>/descartar")
    def referencia_rapida_set_descartar(cid):
        _set(cid)
        n = _rc.descartar(cid)
        flash(f"✓ Descartei o set ({n} referência(s)). Foi pra lixeira (Configurações → Lixeira → Restaurar).")
        return redirect(url_for("referencia_rapida"))

    @app.post("/referencia-rapida/set/<cid>/estilo-novo")
    def referencia_rapida_set_estilo_novo(cid):
        s = _set(cid)
        prontos = [i["id"] for i in s["itens"] if i.get("estado") == "pronto"]
        if not prontos:
            flash("✗ Nenhuma referência pronta.")
            return redirect(url_for("referencia_rapida_set", cid=cid))
        try:
            slug = _en.criar(prontos[0], request.form.get("nome", ""))
            for extra in prontos[1:]:
                _er.confirmar(extra, slug, request.form.get("nome", "") or slug, False)
        except ValueError as e:
            flash("✗ " + str(e))
            return redirect(url_for("referencia_rapida_set", cid=cid))
        flash("✓ Criei o estilo em TESTE com as referências do set.")
        return redirect(url_for("estilo_novo_ver", slug=slug))

    # ───────────── o que o Estúdio decidiu sozinho: Tá bom / Desfazer ─────────────

    @app.post("/auto/<kind>/<id_>/<acao>")
    def auto_acao(kind, id_, acao):
        import auto_juntar as _aj
        if kind not in ("ref", "set", "estudo") or acao not in ("ok", "desfazer"):
            abort(404)
        try:
            if acao == "ok":
                _aj.ok(kind, id_)
                flash("✓ Fechado. Fica guardado onde coloquei.")
            else:
                flash(f"✓ Desfeito: tirei de “{_aj.desfazer(kind, id_)}” (foi pra lixeira) e voltou pra você escolher.")
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect("/aprovar")

    # ───────────── variações na mesma pegada ─────────────

    @app.post("/variacoes/propor")
    def variacoes_propor():
        refs = request.form.getlist("ref")
        try:
            vid = _vr.propor(refs, int(request.form.get("qtd") or 3), request.form.get("cliente", ""), request.form.get("estilo", ""))
        except (ValueError, TypeError) as e:
            flash("✗ " + str(e))
            return redirect(request.referrer or url_for("referencia_rapida"))
        return redirect(url_for("variacoes_ver", vid=vid))

    @app.get("/variacoes/<vid>")
    def variacoes_ver(vid):
        st = _vr.estado(vid)
        if not st:
            abort(404)
        refs = [{**(_er.estado(r) or {"id": r}), "nome_curto": _er.nome_curto(_er.estado(r) or {})} for r in st["refs"]]
        return render_template("variacoes.html", st=st, refs=refs, titulos={f["slug"]: f.get("titulo") or f["slug"] for f in _fmt.listar(ocultos=True)})

    @app.post("/variacoes/<vid>/<int:n>/<decisao>")
    def variacoes_decidir(vid, n, decisao):
        try:
            _vr.decidir(vid, n, "aprovar" if decisao == "aprovar" else "recusar")
            if decisao == "aprovar":   # o clique em "Fazer este vídeo" é o Aprovou?: abre o Criar já preenchido (o vídeo só sai no clique de lá)
                st = _vr.estado(vid) or {}
                flash("✓ Ótimo. Está preenchido: confira e clique em Criar.")
                return redirect(url_for("novo_tela", variacao=f"{vid}:{n}", **({"estilo": st["estilo"]} if st.get("estilo") else {}),
                                        **({"cliente": st["cliente"]} if st.get("cliente") and st["cliente"] != "Avulso" else {})))
            flash("✓ Deixei essa de fora.")
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("variacoes_ver", vid=vid))

    @app.post("/variacoes/<vid>/refazer")
    def variacoes_refazer(vid):
        st = _vr.estado(vid)
        if not st:
            abort(404)
        novo = _vr.propor(st["refs"], st["qtd"], st.get("cliente", ""), st.get("estilo", ""), st.get("origem", "variacoes"))
        return redirect(url_for("variacoes_ver", vid=novo))

    # ───────────── estilo novo em teste ─────────────

    def _em_teste(slug):
        e = _en.estado(slug)
        if not e:
            abort(404)
        return e

    @app.get("/estilo-novo/<slug>")
    def estilo_novo_ver(slug):
        e = _em_teste(slug)
        pv = e["primeiro_video"]
        prop = _vr.estado(pv.get("proposta") or "") if pv.get("proposta") else None
        refs = _fmt.estudos(slug)
        return render_template("estilo_novo.html", e=e, pv=pv, prop=prop, refs=refs, ordem=_en.ESTADOS)

    @app.post("/estilo-novo/<slug>/<acao>")
    def estilo_novo_acao(slug, acao):
        _em_teste(slug)
        try:
            if acao == "propor":
                _en.propor_primeiro(slug)
                flash("✓ Estou pensando no 1º vídeo de teste. A página atualiza sozinha.")
            elif acao == "aprovar-proposta":
                _en.aprovar_proposta(slug)
                flash("✓ Proposta aprovada. Falta montar o 1º vídeo de teste e mandar aqui.")
            elif acao == "video":
                up = request.files.get("video")
                if not up or not up.filename:
                    raise ValueError("Escolha o vídeo de teste.")
                tmp = Path(tempfile.mkdtemp(prefix="estilonovo-"))
                try:
                    dst = tmp / ("teste" + Path(up.filename).suffix.lower())
                    up.save(dst)
                    _en.registrar_video(slug, dst)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                flash("✓ Recebi o 1º vídeo de teste. Assista e responda: Aprovou?")
            elif acao == "aprovar":
                faltas = _en.aprovar_video(slug)
                flash("✓ Aprovado: o estilo agora está pronto e aparece no Criar." if not faltas
                      else "Aprovei o vídeo, mas o estilo ainda não fecha o contrato: " + " · ".join(faltas[:4]))
            elif acao == "ajustar":
                _en.pedir_ajuste(slug, request.form.get("texto", ""))
                flash("✓ Anotado. O estilo continua em teste até o vídeo ficar bom.")
            else:
                abort(404)
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("estilo_novo_ver", slug=slug))

    @app.post("/referencia-rapida/<id_>/refazer")
    def referencia_rapida_refazer(id_):
        _estado(id_)
        try:
            _er.refazer(id_, request.form.get("observacao", ""))
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("referencia_rapida_ver", id_=id_))

    @app.get("/referencia-rapida/<id_>/folha")
    def referencia_rapida_folha(id_):
        st = _estado(id_)
        p = _er.pasta(id_) / (st.get("medidas") or {}).get("folha", "folha.jpg")
        if not p.is_file():
            abort(404)
        return send_file(p, mimetype="image/jpeg")

    @app.get("/referencia-rapida/<id_>/video")
    def referencia_rapida_video(id_):
        _estado(id_)
        v = _er.video_de(id_)
        if not v:
            abort(404)
        return send_file(v, conditional=True)
