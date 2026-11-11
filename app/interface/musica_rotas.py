"""Busca de música e efeito sonoro (Biblioteca → Jamendo/Freesound → YouTube), sem repetir o que o cliente usou.

Registrado no servidor com:
    from musica_rotas import register as register_musica
    register_musica(app)
"""
from __future__ import annotations

import re
from pathlib import Path

from flask import flash, redirect, render_template, request, url_for

from _comum import clientes
import musica_busca as _mb

CAMPOS_GUARDAR = ("fonte", "url", "audio", "titulo", "autor", "licenca", "tipo", "termo", "duracao", "aviso_licenca")


def register(app):
    @app.context_processor
    def _musica_ctx():
        # `musica_busca_ok` liga o botão na Biblioteca; `musica_status` alimenta o bloco _config_musica.html
        if request.endpoint in ("config", "musica_busca"):
            try:
                return {"musica_busca_ok": True, "musica_status": _mb.status()}
            except Exception:
                pass
        return {"musica_busca_ok": True}

    def _job_do_link(valor: str):
        """'Cliente/slug' (vindo do botão "Buscar outra" do vídeo) → o job, ou None."""
        cli, _, slug = (valor or "").strip().partition("/")
        if not cli or not slug or "/" in slug:
            return None
        import producao as _prod
        return _prod.carregar(cli, slug)

    @app.route("/musica", endpoint="musica_busca")
    def musica_busca():
        a = request.args
        termo = a.get("q", "").strip()
        tipo = "sfx" if a.get("tipo") == "sfx" else "musica"
        job = _job_do_link(a.get("job", ""))
        cliente = a.get("cliente", "").strip() or (job or {}).get("cliente", "")
        if job:
            cliente = job["cliente"]                     # escolhendo pro vídeo: só as músicas desse cliente
        job_info = None
        do_cliente, do_formato = [], []
        formato = (job or {}).get("formato") or None
        recentes_job = _mb.usadas_recentemente(cliente, ignorar=(job or {}).get("slug", "")) if cliente else []
        if cliente:                                      # ordem da tela: cliente, Biblioteca, formato, Mixkit e outras
            do_cliente = _mb.marcar(_mb.do_cliente(cliente, None, tipo), recentes_job, cliente)
        do_formato = _mb.marcar(_mb.do_formato(formato, tipo), recentes_job, cliente)
        if job:
            job_info = {"id": f"{job['cliente']}/{job['slug']}", "titulo": job.get("titulo") or job["slug"],
                        "cliente": job["cliente"], "slug": job["slug"]}
        try:
            pagina = max(1, min(10, int(a.get("pagina") or 1)))
        except ValueError:
            pagina = 1
        instrumental = a.get("instrumental") == "1" or "q" not in a      # ligado por padrão
        recentes = _mb.usadas_recentemente(cliente) if cliente else []
        biblioteca, grupos, visto = [], [], []
        biblioteca = _mb.marcar(_mb.na_biblioteca(termo, tipo) if termo else _mb.da_biblioteca(12, tipo), recentes, cliente)
        if termo:
            visto = [v for v in a.get("visto", "").split(",") if re.fullmatch(r"[\w-]{11}", v)][:200]
            grupos = _mb.buscar(termo, tipo, pagina=pagina, instrumental=instrumental and tipo == "musica",
                                excluir_yt=visto if pagina > 1 else ())
            for g in grupos:
                _mb.marcar(g["itens"], recentes, cliente)
        varias = []
        if job and not termo:                            # escolhendo pro vídeo sem digitar: variadas pela fala do job
            try:
                fala = " ".join(str(job.get(k) or "") for k in ("briefing", "titulo"))
                varias = _mb.buscar_varias(_mb.termos_da_fala(fala, formato), tipo, cliente=cliente, job=job.get("slug", ""),
                                           pagina=pagina)
                for g in varias:
                    _mb.marcar(g["itens"], recentes, cliente)
            except Exception:
                varias = []
        try:
            virais = _mb.buscar_virais(termo, 10) if tipo == "musica" else None
        except Exception:  # noqa: BLE001
            virais = None
        return render_template("musica_busca.html", virais=virais, varias=varias, termo=termo, tipo=tipo, cliente=cliente, pagina=pagina,
                               instrumental=instrumental, recentes=recentes, biblioteca=biblioteca, grupos=grupos,
                               clientes=[c["nome"] for c in clientes()], sites=_mb.sites_manuais(termo, tipo),
                               texto_uso=_mb.texto_uso, job_info=job_info, do_cliente=do_cliente, do_formato=do_formato,
                               visto=",".join(visto + [i["id"] for g in grupos if g["fonte"] == "youtube" for i in g["itens"]]))

    @app.route("/musica/usar", methods=["POST"])
    def musica_usar():
        """'Usar neste vídeo': a faixa vira a música do vídeo (no PLANO) e volta pro bloco Música do storyboard."""
        import producao as _prod
        from _comum import RAIZ
        f = request.form
        j = _job_do_link(f.get("job", ""))
        if not j:
            flash("✗ Vídeo não encontrado.")
            return redirect(url_for("musica_busca"))
        voltar = url_for("job", cli=j["cliente"], slug=j["slug"]) + "#musica"
        try:
            if j.get("rodando") or j.get("status") in ("na_fila", "exportado", "arquivado"):
                raise ValueError("Espere a etapa em andamento terminar pra trocar a música.")
            p = _prod.plano(j)
            if not p:
                raise ValueError("Monte o storyboard primeiro: a música entra nele.")
            arquivo = f.get("arquivo", "").strip()
            fonte = f.get("fonte", "").strip()
            if arquivo:                                   # faixa que já está no computador
                caminho = (RAIZ / arquivo).resolve()
                permitidos = [RAIZ / "clientes" / j["cliente"], RAIZ / "acervo", RAIZ / "formatos"]
                if (not caminho.is_file() or caminho.suffix.lower() not in _mb.AUDIO_EXTS
                        or not any(caminho.is_relative_to(x.resolve()) for x in permitidos)):
                    raise ValueError("Essa faixa não é deste cliente nem da Biblioteca.")
                arquivo = _mb._rel(caminho)
            elif fonte == "virais":
                import musica_viral as _mv
                pt = _mv.preparar(j["sandbox"], f.get("url") or f.get("titulo_id") or f.get("audio", ""), 75.0, cliente=j["cliente"])
                arquivo = str(Path(j["sandbox"]) / pt["arquivo"])
            elif fonte in ("mixkit", "jamendo", "freesound", "openverse"):
                arquivo = _mb._rel(_mb.baixar_externa(f.get("audio", ""), j["sandbox"], fonte, f.get("titulo", ""),
                                                      pagina=f.get("url", "")))
            else:
                raise ValueError("Essa faixa não tem um mp3 pra baixar. Guarde na Biblioteca e escolha de lá.")
            op = {"id": _mb.id_faixa(arquivo), "titulo": f.get("titulo", "").strip() or _mb._titulo_arquivo(Path(arquivo)),
                  "arquivo": arquivo, "fonte": fonte or "cliente", "url": f.get("url", "").strip(),
                  "autor": f.get("autor", "").strip(), "licenca": f.get("licenca", "").strip(),
                  "motivo": "Você escolheu na busca de música"}
            _prod.salvar_plano(j, _mb.aplicar_no_plano(p, musica=op))
            flash(f"✓ “{op['titulo']}” é a música deste vídeo. Confira e aprove o storyboard.")
        except Exception as e:
            flash(f"✗ {e}")
            return redirect(request.referrer or voltar)
        return redirect(voltar)

    # ── Virais do momento: as 3 opções (com prévia de 10 s) do Novo vídeo e do Editar vídeo, e o "Procurar" ──
    @app.get("/musica/viral/opcoes", endpoint="musica_viral_opcoes")
    def musica_viral_opcoes():
        """?formato=editorial&cliente=Avulso&texto=<fala ou roteiro>&dur=75&n=3 → as virais que casam com o clima, já conferidas
        (sem marca d'água). Leva uns 20 s na 1ª vez (baixa e confere); depois sai do cache."""
        from flask import jsonify
        import musica_viral as _mv
        from _comum import RAIZ, ler_json
        a = request.args
        formato = re.sub(r"[^a-z0-9-]", "", a.get("formato", "editorial"))
        f = ler_json(RAIZ / "formatos" / formato / "formato.json", {}) or {}
        clima = ((f.get("som") or {}).get("musica") or {}).get("clima", "")
        try:
            dur = max(20.0, min(180.0, float(a.get("dur") or 75)))
            r = _mv.opcoes(a.get("cliente", ""), a.get("texto", "")[:4000], clima, max(1, min(6, int(a.get("n") or 3))), dur_video=dur,
                           ignorar=tuple(x for x in a.get("ignorar", "").split(",") if x))
            return jsonify(ok=True, **r)
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=f"Não consegui montar as virais agora ({str(e)[:140]}). Tente de novo ou use Procurar."), 502

    @app.get("/musica/viral/direcao", endpoint="musica_viral_direcao")
    def musica_viral_direcao():
        """?direcao=tensa de suspense, sem voz&formato=&cliente=&texto=&dur=&ignorar=id,id → 3 opções com prévia e o motivo.
        Direção vazia = o clima do estilo + o tom do roteiro. O Estúdio procura sozinho (virais, YouTube, Mixkit); sem voz cantada por padrão."""
        from flask import jsonify
        import musica_viral as _mv
        from _comum import RAIZ, ler_json
        a = request.args
        formato = re.sub(r"[^a-z0-9-]", "", a.get("formato", "editorial"))
        f = ler_json(RAIZ / "formatos" / formato / "formato.json", {}) or {}
        clima = ((f.get("som") or {}).get("musica") or {}).get("clima", "")
        try:
            dur = max(20.0, min(180.0, float(a.get("dur") or 75)))
            r = _mv.por_direcao(a.get("direcao", "")[:300], a.get("cliente", ""), a.get("texto", "")[:4000], clima, max(1, min(6, int(a.get("n") or 3))),
                                tuple(x for x in a.get("ignorar", "").split(",") if x), dur)
            return jsonify(ok=True, **r)
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=f"Não consegui procurar agora ({str(e)[:140]}). Tente de novo."), 502

    @app.get("/musica/viral/procurar", endpoint="musica_viral_procurar")
    def musica_viral_procurar():
        from flask import jsonify
        import musica_viral as _mv
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify(ok=True, itens=[])
        try:
            return jsonify(ok=True, itens=_mv.procurar(q, 6))
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=str(e)[:160]), 502

    @app.get("/musica/viral/previa", endpoint="musica_viral_previa")
    def musica_viral_previa():
        """?faixa=<id viral | link do YouTube>&entrada=<segundo da faixa> → {previa: caminho de 10 s, t0, bpm}. Baixa na 1ª vez."""
        from flask import jsonify
        import musica_viral as _mv
        faixa = request.args.get("faixa", "").strip()
        try:
            entrada = float(request.args["entrada"]) if request.args.get("entrada") not in (None, "") else None
            if faixa.startswith("http"):
                if not _mb._host_ok(faixa, "youtube") and not _mb._host_ok(faixa, "soundcloud") and "mixkit.co" not in faixa:
                    raise ValueError("Só link do YouTube, do SoundCloud ou do Mixkit.")
                m = _mv._cand_link(faixa)
                _mv._baixar_cand(m)
            else:
                m = next((x for x in _mv.virais(80) if x["id"] == faixa), None)
                if not m:
                    raise ValueError("Essa música não está mais nas virais de hoje.")
            t = _mv._trecho_da(m, 75.0, entrada)
            chk = _mv._checada(m, t["t0"], 60.0, "letra")
            return jsonify(ok=True, previa=_mv.previa(m, entrada), t0=t["t0"], bpm=t["bpm"], trecho=t["motivo"], id=faixa, titulo=m["titulo"],
                           artista=m["artista"], confere=chk["ok"], motivos=chk["motivos"], duracao=_mv._duracao(_mv._baixar_cand(m)))
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=str(e)[:200]), 400

    @app.post("/musica/reprovar", endpoint="musica_reprovar")
    def musica_reprovar():
        """"Não usar mais": {arquivo | chave, titulo}. A faixa vai pra acervo/musicas-reprovadas.jsonl e nunca mais volta como opção."""
        from flask import jsonify
        d = request.get_json(silent=True) or request.form
        try:
            r = _mb.reprovar(arquivo=(d.get("arquivo") or "").strip(), titulo=(d.get("titulo") or "").strip(), chave=(d.get("chave") or "").strip())
            return jsonify(ok=True, titulo=r["titulo"])
        except ValueError as e:
            return jsonify(ok=False, erro=str(e)), 400

    @app.route("/musica/favorito", methods=["POST"])
    def musica_favorito():
        """♥ numa faixa/efeito: {arquivo (relativo à raiz) | slug, tipo, cliente?, geral?, desligar?, titulo?}."""
        from flask import jsonify
        import acervo as _ac
        from _comum import RAIZ
        d = request.get_json(silent=True) or request.form
        tipo = "sfx" if d.get("tipo") == "sfx" else "musica"
        cliente = (d.get("cliente") or "").strip() or None
        if str(d.get("geral", "")).lower() in ("1", "true", "sim"):
            cliente = None
        ligar = str(d.get("desligar", "")).lower() not in ("1", "true", "sim")
        try:
            if d.get("slug"):
                fav = _ac.favoritar(d["slug"].strip(), cliente, ligar)
                return jsonify({"ok": fav is not None, "slug": d["slug"], "favorito": fav})
            arq = (RAIZ / (d.get("arquivo") or "")).resolve()
            if not d.get("arquivo") or RAIZ.resolve() not in arq.parents or not arq.is_file():
                return jsonify({"ok": False, "erro": "arquivo inválido"}), 400
            r = _ac.favoritar_arquivo(arq, d.get("titulo") or arq.stem, tipo, cliente, ligar)
            return jsonify({"ok": True, **(r or {})})
        except Exception as e:
            return jsonify({"ok": False, "erro": str(e)}), 400

    @app.route("/musica/favoritos")
    def musica_favoritos():
        from flask import jsonify
        import acervo as _ac
        tipo = "sfx" if request.args.get("tipo") == "sfx" else "musica"
        its = _ac.favoritos(tipo, request.args.get("cliente") or None)
        return jsonify([{"slug": i["slug"], "titulo": i.get("titulo"), "arquivo": i.get("clip_rel"),
                         "favorito": i.get("favorito")} for i in its])

    @app.route("/musica/guardar", methods=["POST"])
    def musica_guardar():
        f = request.form
        dados = {k: f.get(k, "").strip() for k in CAMPOS_GUARDAR}
        dados["tags"] = ", ".join(p for p in dados.get("termo", "").lower().split() if len(p) >= 3)
        voltar = url_for("musica_busca", q=f.get("q", ""), tipo=f.get("tipo_busca", dados["tipo"]),
                         cliente=f.get("cliente", ""), pagina=f.get("pagina", 1),
                         instrumental=f.get("instrumental", ""))
        try:
            if dados["fonte"] not in _mb.HOSTS:
                raise ValueError("Fonte desconhecida.")
            if dados["fonte"] in _mb.VIA_YTDLP:
                if not _mb._host_ok(dados["url"], dados["fonte"]):
                    raise ValueError("Esse link não é do " + ("YouTube." if dados["fonte"] == "youtube" else "SoundCloud."))
                try:
                    longo = float(dados.get("duracao") or 0) > _mb.LIMITE_YT_S
                except ValueError:
                    longo = False
                if longo:
                    raise ValueError("Esse vídeo é longo demais (compilação de uma hora). Abra no YouTube e escolha uma faixa curta.")
            elif not _mb._host_ok(dados["audio"], dados["fonte"]):
                raise ValueError("Essa faixa não tem um arquivo de áudio que dê pra baixar.")
            _mb.disparar_guardar(dados)
            flash(f"✓ Guardando “{dados['titulo'] or 'a faixa'}” na Biblioteca. Leva um ou dois minutos: "
                  "o Estúdio baixa, mede o BPM, acha os trechos e descreve sozinho.")
        except Exception as e:
            flash(f"✗ {e}")
        return redirect(voltar)

    @app.route("/musica/chaves", methods=["POST"])
    def musica_chaves():
        salvas = _mb.salvar_chaves(request.form.get("JAMENDO_CLIENT_ID", ""), request.form.get("FREESOUND_API_KEY", ""))
        if not salvas:
            flash("Nenhuma chave nova pra salvar.")
        for nome in salvas:                    # testa na hora com uma busca de 1 resultado (grátis)
            g = _mb.buscar_jamendo("piano", n=1) if nome == "Jamendo" else _mb.buscar_freesound("click", n=1)
            if g["itens"]:
                flash(f"✓ Chave do {nome} salva e funcionando.")
            else:
                flash(f"✗ Chave do {nome} salva, mas o teste falhou: {g['aviso']}")
        try:
            destino = url_for("config")
        except Exception:
            destino = url_for("musica_busca")
        return redirect(destino + "#musica-fontes")
