"""Editar o vídeo por cena (PLANO-2.0, item 1): player, linha do tempo das cenas e o Claude do lado com alcance
(elemento · cena · vídeo todo) e print anexado. O motor do editor é app/ferramentas/editor.py."""
from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

from flask import abort, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import editor as _ed  # noqa: E402
import gerar_ia as _gia  # noqa: E402
from _comum import RAIZ  # noqa: E402


def _propor_aprendi(p, texto: str) -> None:
    """REGRA Nº 2 com gate, também no editor por cena: propõe o "Aprendi: <regra>" do pedido e espera o OK (nunca derruba o pedido)."""
    try:
        import aprendi as _ap
        job = _ed.job_da_pasta(p)
        if not job:
            return
        _ap.propor(job["cliente"], job["slug"], texto, formato=job.get("formato") or "", modelo=job.get("modelo") or "",
                   titulo=job.get("titulo") or job["slug"])
    except Exception as e:  # noqa: BLE001
        print(f"(aprendi não propôs: {e})", file=sys.stderr)


def register(app):
    app.add_template_global(lambda rel: bool(_ed.pasta(rel)), "tem_cenas")

    def _gia_erro(fn):
        try:
            return jsonify(ok=True, **fn())
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400

    def _pasta():
        p = _ed.pasta(request.values.get("pasta"))
        if not p:
            abort(404)
        return p

    @app.get("/editar")
    def editor_lista():
        return render_template("editor_lista.html", videos=_ed.videos(), ainda_nao=_ed.ainda_nao())

    @app.post("/editar/tirar")
    def editor_tirar():
        import remover as _rm
        from flask import flash, redirect, url_for
        p = _ed.pasta(request.form.get("pasta"))
        try:
            _rm.remover_pasta(_ed.rel(p) if p else "", request.form.get("rotulo", ""))
            flash("✓ Saiu da lista e foi pra lixeira (Configurações → Lixeira → Restaurar).")
        except ValueError as e:
            flash("✗ " + str(e))
        return redirect(url_for("editor_lista"))

    def contexto_editor(p):
        """Tudo que o miolo do editor (_editor_miolo.html) precisa, pra pasta p. Usado em /editar/video e na página do vídeo pronto."""
        import ia
        doc = _ed._doc(p)
        vid = _ed._video(p, doc)
        spec = _ed.spec(p)
        modelos = [("", "Claude Sonnet (padrão da alteração)")] + [(m, "Claude " + ia.nome_claude(m)) for m in ("opus", "haiku")]
        return dict(pasta_ed=_ed.rel(p), titulo=doc.get("titulo") or p.name, cenas=_ed.cenas(p),
                    video=_ed.rel(vid) if vid.is_file() else "", sugestoes=spec["sugestoes"], tem_material=spec.get("material", True), tem_gerar=_gia.tem_gerar(p), tem_narracao=spec.get("narracao", True),
                    modelos=modelos, esforcos=[("", "Esforço alto (padrão)")] + [(v, r.split(" — ")[0]) for v, r in ia.ESFORCOS if v != "high"],
                    versoes=_ed.versoes(p), estado=_ed.estado(p), narr=_ed.narracao(p), vozes=_ed._vozes(), etapas=_ed.etapas(p), musica=_ed.musica(p))
    app.config["contexto_editor"] = contexto_editor   # a página do vídeo (andamento_rotas) usa o mesmo miolo

    @app.get("/editar/video")
    def editor_video():
        return render_template("editor.html", **contexto_editor(_pasta()))

    @app.get("/editar/material")
    def editor_material():
        return jsonify(grupos=_ed.material(_pasta()))

    @app.post("/editar/material")
    def editor_usar_material():
        p = _pasta()
        try:
            _ed.usar_material(p, int(request.form.get("n") or 0), request.form.get("arquivo", ""))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True)

    @app.post("/editar/refazer")
    def editor_refazer():
        p = _pasta()
        try:
            _ed.refazer(p, request.form.get("desde", ""))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True)

    @app.post("/editar/narracao")
    def editor_narracao():
        p = _pasta()
        f = request.form
        try:
            import json as _json
            _ed.trocar_narracao(p, f.get("voz", ""), f.get("roteiro"), _json.loads(f.get("emocoes") or "null"))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True)

    @app.get("/editar/musica")
    def editor_musica():
        return jsonify(ok=True, **_ed.musica(_pasta()))

    @app.post("/editar/musica")
    def editor_musica_trocar():
        """Troca a música de fundo: faixa (id das virais ou link), entrada (segundo da faixa), abaixo_db (volume) ou sem=1."""
        p = _pasta()
        f = request.form
        try:
            num = lambda k: float(f[k]) if f.get(k) not in (None, "") else None  # noqa: E731
            _ed.trocar_musica(p, f.get("faixa", "").strip(), num("entrada"), num("abaixo_db"), f.get("sem") in ("1", "true", "sim"))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True)

    @app.get("/editar/miniaturas")
    def editor_miniaturas():
        p = _pasta()
        if not _ed.miniaturas_prontas(p):   # 1ª vez pesa (~10 s): vai pra segundo plano e a tela mostra "preparando…" e pergunta de novo
            import preparar
            preparar.miniaturas(p)
            if preparar.fazendo("mini:" + str(p)):
                return jsonify(preparando=True, minis=[], cenas=_ed.cenas(p))
        return jsonify(preparando=False, minis=_ed.miniaturas(p), cenas=_ed.cenas(p))

    @app.post("/editar/pedir")
    def editor_pedir():
        p = _pasta()
        f = request.form
        print_rel = ""
        up = request.files.get("print")
        cola = f.get("print_colado", "")
        if (up and up.filename) or cola.startswith("data:image"):
            d = p / "editor" / "prints"
            d.mkdir(parents=True, exist_ok=True)
            alvo = d / f"print-{time.strftime('%Y%m%d-%H%M%S')}.png"
            if up and up.filename:
                up.save(alvo)
            else:
                alvo.write_bytes(base64.b64decode(cola.split(",", 1)[1]))
            print_rel = _ed.rel(alvo)
        try:
            n = int(f.get("n") or 0) or None
            pid = _ed.novo_pedido(p, f.get("escopo", "cena"), n, f.get("campo", ""), f.get("texto", ""), print_rel,
                                  f.get("modelo", ""), f.get("esforco", ""), int(f.get("n_fim") or 0) or None)
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        _propor_aprendi(p, f.get("texto", ""))
        return jsonify(ok=True, pedido=pid)

    @app.get("/editar/estado")
    def editor_estado():
        p = _pasta()
        e = _ed.estado(p)
        cauda = ""
        if e.get("log") and (RAIZ / e["log"]).is_file():
            linhas = [l for l in (RAIZ / e["log"]).read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
            cauda = "\n".join(linhas[-6:])
        doc = _ed._doc(p)
        vid = _ed._video(p, doc)
        return jsonify(estado=e, cauda=cauda, versoes=_ed.versoes(p),
                       video=_ed.rel(vid) if vid.is_file() else "", mtime=int(vid.stat().st_mtime) if vid.is_file() else 0)

    @app.post("/editar/voltar")
    def editor_voltar():
        p = _pasta()
        if _ed.estado(p).get("rodando"):
            return jsonify(ok=False, erro="Espere o pedido terminar."), 400
        try:
            v = _ed.voltar(p, request.form.get("v", ""))
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400
        return jsonify(ok=True, versao=v)

    # ── Gerar com IA (kie.ai) por cena: custo antes, só com o clique do João. Nada daqui gasta até o /confirmar. ──
    @app.get("/editar/gerar/opcoes")
    def editor_gerar_opcoes():
        p = _pasta()
        return _gia_erro(lambda: {"opcoes": _gia.cardapio(p, int(request.args.get("n") or 0))})

    @app.get("/editar/gerar/orcamento")
    def editor_gerar_orcamento():
        p = _pasta()
        return _gia_erro(lambda: {"orcamento": _gia.orcar(p, request.args.to_dict())})

    @app.post("/editar/gerar/rascunho")
    def editor_gerar_rascunho():
        p = _pasta()
        return _gia_erro(lambda: {"geracao": _gia.rascunho(p, request.form.to_dict())})

    @app.post("/editar/gerar/confirmar")
    def editor_gerar_confirmar():
        p = _pasta()
        return _gia_erro(lambda: {"geracao": _gia.confirmar(p, request.form.get("id", ""), request.form.get("nonce", ""))})

    @app.get("/editar/gerar/estado")
    def editor_gerar_estado():
        p = _pasta()
        return _gia_erro(lambda: {"geracao": _gia.atualizar(p, request.args.get("id", ""))})

    @app.get("/editar/gerar/lista")
    def editor_gerar_lista():
        p = _pasta()
        return jsonify(ok=True, geracoes=_gia.lista(p))

    @app.get("/editar/gerar/sugestoes")
    def editor_gerar_sugestoes():
        p = _pasta()
        return jsonify(ok=True, sugestoes=_gia.sugestoes(p))

    @app.post("/editar/gerar/dispensar")
    def editor_gerar_dispensar():
        p = _pasta()
        _gia.dispensar(p, request.form.get("id", ""))
        return jsonify(ok=True)
