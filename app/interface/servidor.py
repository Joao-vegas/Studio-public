#!/usr/bin/env python3
"""
servidor — ESTÚDIO, app LOCAL do producao-reels (http://localhost:7655).

Mesmo espírito do Swipe File (Flask, markdown/JSON em pasta, nada na nuvem), só que de VÍDEO:

    CLIENTES  (Joao, Cliente8, Cliente4, ...)           ← pastas do repo
      └── MODELOS  (dividido-mascara, legenda-simples...)  ← explicação + regras aprendidas
            └── VÍDEOS  (jobs: bruto → produção pelo Claude → feedback → aprendizado)
    ACERVO de b-roll compartilhado (acervo/itens) + BUSCA com a skill get-brolls

Rodar:  python3 app/interface/servidor.py   (ou app/iniciar.command)
Dep:    flask
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
from pathlib import Path

FERRAMENTAS = Path(__file__).resolve().parent.parent / "ferramentas"
sys.path.insert(0, str(FERRAMENTAS))

from _comum import memo_curto as _clonar_memo  # noqa: E402
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import (RAIZ, ESTUDIO, CACHE, ACERVO, GB_PROJECT, GB_ROOT, VIDEO_EXTS, IMAGEM_EXTS,  # noqa: E402
                    clientes, cliente as _cliente, modelo as _modelo, modelos as _modelos, md_para_html,
                    ensure, gb_env, gb_env_gravar, gb_instalado, ler_json, rel, thumb_cache, thumb_rapida, claude_bin, dentro_da_raiz)
import acervo as _acervo  # noqa: E402
import getbrolls as _gb  # noqa: E402
import producao as _prod  # noqa: E402
import novo_cliente as _nc  # noqa: E402
import saidas as _saidas  # noqa: E402
import material as _material  # noqa: E402
import ficha as _ficha  # noqa: E402
import corte as _cortes  # noqa: E402  (mesma ferramenta: motor + corte avulso)
import ia, regras, arquivo as _arquivo, semantica, fila, edicao, pipeline, takes
import demos as _demos  # noqa: E402
import musica_busca as _mb  # noqa: E402
import storyboard as _sbd  # noqa: E402  (folha de storyboard)
import recarregar as _recarregar  # noqa: E402  (botão "Recarregar agora")

try:
    from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,  # noqa: E402
                       request, send_file, session, url_for)
except ImportError:
    print("Flask não instalado. Rode:  python3 -m pip install flask  (ou bash app/setup.sh)")
    sys.exit(1)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "estudio-local"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024 * 1024  # 6 GB (bruto de iPhone)
PORTA = 7655
from iniciar import versao as versao_build
BUILD = versao_build()
VERSAO = "2.2.1"
import time as _time
INICIO = _time.time()   # hora em que este servidor subiu: .py de app/ mais novo = código velho no ar


def atualizacao_pendente() -> bool:
    """Algum .py de app/ mudou depois que o servidor subiu: a tela está rodando código velho (e pode dar erro 500)."""
    base = Path(__file__).resolve().parent.parent
    try:
        return any(p.stat().st_mtime > INICIO + 1 for pasta in ("ferramentas", "interface") for p in (base / pasta).glob("*.py"))
    except OSError:
        return False


@app.get("/api/health")
def health():
    return jsonify(ok=True, versao=VERSAO, build=BUILD, inicio=int(INICIO))

# The review is enforced on the server too, including when JavaScript is unavailable.
@app.before_request
def revisar_execucao():
    if request.method != "POST":
        return
    endpoint = request.endpoint
    titulos = {
        "job_corte": "Preparar o corte do bruto",
        "job_corte_revisar": "Revisar o corte com IA",
        "job_analisar": "Planejar a edição",
        "job_previas": "Produzir prévias dos trechos",
        "job_renderizar": "Renderizar a edição aprovada",
        "job_rodar": "Produzir o vídeo",
    }
    titulo = titulos.get(endpoint)
    if endpoint == "job_plano":
        titulo = {"buscar": "Buscar novas opções de b-roll", "previas": "Produzir prévias dos trechos",
                  "recuperar": "Preparar e analisar as prévias deste trecho", "avaliar": "Analisar visualmente seu take", "render": "Renderizar a edição aprovada"}.get(request.form.get("acao", "").split(":")[0])
    if endpoint == "job_feedback" and (request.form.get("decisao") == "ajustar" or request.form.get("texto", "").strip()):
        titulo = "Aplicar feedback com IA"
    if not titulo:
        return
    args = request.view_args
    j = _prod.carregar(args["cli"], args["slug"])
    if not j:
        abort(404)
    voltar = url_for("job", cli=args["cli"], slug=args["slug"])
    if j.get("rodando") or j.get("status") == "na_fila" or _prod.corte_rodando(j):
        flash("Uma etapa já está em execução. Aguarde terminar antes de iniciar outra.")
        return redirect(voltar)
    if endpoint == "job_analisar" and j.get("cortar_bruto") and not j.get("corte_aplicado"):
        flash("Revise e aplique o corte do bruto antes de planejar a edição.")
        return redirect(voltar)
    if endpoint == "job_analisar":
        edicao.preferencias(request.form)
    if request.form.get("confirmar_execucao") != "1":
        tipo_exec = {"job_corte": "corte", "job_corte_revisar": "corte", "job_analisar": "analise", "job_previas": "previas",
                     "job_feedback": "feedback"}.get(endpoint, "producao")
        if endpoint == "job_plano":
            tipo_exec = {"buscar": "rebusca", "previas": "previas", "recuperar": "previas"}.get(request.form.get("acao", "").split(":")[0], "producao")
        return render_template("revisar_execucao.html", titulo_acao=titulo, j=j, voltar=voltar, estimativa=_prod.estimativa_etapa(tipo_exec, j),
                               campos=list(request.form.items(multi=True)))


@app.before_request
def _memo_do_pedido():
    """Pedido de leitura (GET): clientes/ e formatos/ são varridos 1 vez só durante a tela (ver _comum.memo_curto)."""
    if request.method == "GET":
        g._memo = _clonar_memo()
        g._memo.__enter__()


@app.teardown_request
def _memo_fim(exc):
    m = g.pop("_memo", None)
    if m is not None:
        m.__exit__(None, None, None)


@app.after_request
def cache_local(response):
    if response.mimetype in ("text/css", "application/javascript", "text/javascript") and request.args.get("v") and request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # o ?v= muda quando o arquivo muda (_versao_estatico)
    elif response.mimetype in ("text/html", "application/json", "text/css", "application/javascript"):
        response.headers["Cache-Control"] = "no-store"
    return response

UPLOADS = ensure(ESTUDIO / ".uploads")


@app.context_processor
def _versao_estatico():
    """Carimbo de versão nos estáticos: o navegador nunca serve CSS/JS velho."""
    try:
        d = Path(app.static_folder)
        v = str(int(max(p.stat().st_mtime for p in d.glob("*"))))
    except Exception:
        v = "0"
    return {"vstatic": v}


@app.errorhandler(404)
def _pagina_nao_existe(e):
    """Tela própria pro 404 (em vez do "Not Found" branco do Flask). Rotas /api/ seguem com o erro cru."""
    if request.path.startswith("/api/"):
        return e
    return render_template("erro.html", codigo=404, titulo="Essa página não existe", frase="O link pode ter mudado ou o item foi removido."), 404


@app.errorhandler(500)
def _deu_erro(e):
    """500 em português (o erro original vai pro log). Se o template também falhar, cai em HTML puro."""
    app.logger.exception("Erro 500 em %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify(ok=False, erro="Algo deu errado."), 500
    velho = atualizacao_pendente()
    frase = "O Estúdio foi atualizado. Clique em Recarregar agora no aviso amarelo (no topo da tela), sem abrir terminal." if velho else "Tente de novo. Se continuar, avise o João."
    try:
        return render_template("erro.html", codigo=500, titulo="Algo deu errado nesta tela.", frase=frase), 500
    except Exception:
        return ('<!doctype html><meta charset="utf-8"><title>Algo deu errado</title>'
                '<body style="font-family:sans-serif;max-width:480px;margin:15vh auto;text-align:center">'
                f'<h1>Algo deu errado nesta tela.</h1><p>{frase}</p><a href="/">Voltar ao início</a></body>'), 500


@app.template_filter("md")
def _md(txt):
    return md_para_html(txt or "")


@app.context_processor
def _globais():
    return {"rel": rel, "versao_app": VERSAO, "atualizacao_pronta": atualizacao_pendente(), "recarga_agendada": _recarregar.agendado(), "gb_ok": gb_instalado(), "claude_ok": bool(claude_bin()),
            "existe": lambda caminho: bool(caminho) and (RAIZ / caminho).exists()}


# ───────────────────────── arquivos do repo (vídeos, thumbs, prévias) ─────────────────────────

@app.route("/arquivo/<path:caminho>")
def arquivo(caminho):
    p = (RAIZ / caminho).resolve()
    if not dentro_da_raiz(p) or not p.is_file():
        abort(404)
    if p.suffix.lower() == ".md":   # ESTUDO.md, COMO-FAZER.md: abre como texto no navegador em vez de baixar
        return send_file(str(p), conditional=True, mimetype="text/plain; charset=utf-8")
    return send_file(str(p), conditional=True)


@app.route("/frame/<path:caminho>")
def frame_rota(caminho):
    """Um frame do vídeo num instante (t em segundos) — usado pra mostrar o take escolhido no vídeo final."""
    p = (RAIZ / caminho).resolve()
    if not dentro_da_raiz(p) or not p.is_file():
        abort(404)
    try:
        tt = max(0.0, float(request.args.get("t", 1)))
    except ValueError:
        tt = 1.0
    from _comum import thumb, CACHE
    import re as _re
    key = _re.sub(r"[^a-zA-Z0-9]+", "_", rel(p))[-140:] + f"-{tt:.1f}.jpg"
    out = thumb(p, CACHE / "frames" / key, t=tt, largura=540)
    if not out:
        abort(404)
    return send_file(str(out), conditional=True)


@app.route("/thumb/<path:caminho>")
def thumb_rota(caminho):
    p = (RAIZ / caminho).resolve()
    if not dentro_da_raiz(p) or not p.is_file():
        abort(404)
    import preparar as _prep
    if not _prep.capa_pronta(p):
        # capa boa (5 quadros) ainda não nasceu: vai pra segundo plano e a tela recebe já um quadro simples (1 ffmpeg), sem cache
        _prep.capa(p)
        rapido = thumb_rapida(p)
        if rapido:
            r = send_file(str(rapido), mimetype="image/jpeg")
            r.headers["Cache-Control"] = "no-store"
            return r
    t = thumb_cache(p)
    if not t:
        abort(404)
    return send_file(str(t), conditional=True)


# ───────────────────────── home / clientes ─────────────────────────

@app.route("/cliente/<nome>")
def cliente(nome):
    c = _cliente(nome)
    if not c:
        abort(404)
    mods = _modelos(c)
    import formatos as _fmt
    for m in mods:
        m["ficha"] = _ficha.carregar(m["pasta"])
        # nome do estilo em linguagem simples + o exemplo dele (o cartão da página do cliente)
        f = _fmt.de_modelo(m["nome"]) or {}
        ex = (f.get("exemplos") or [None])[0]
        m["estilo"] = f.get("titulo") or (m["ficha"] or {}).get("titulo") or m["nome"]
        m["estilo_frase"] = f.get("frase") or ""
        m["exemplo"] = ex["video"] if ex else None
        m["exemplo_poster"] = ex.get("poster_rel") if ex else None
        m["n_regras"] = len(m.get("lista_regras") or [])
    jobs = [j for j in _prod.listar(c["nome"]) if j["status"] != "arquivado"]
    titulos = {j["slug"]: j["titulo"] for j in jobs if j.get("titulo")}
    videos = []
    for it in _saidas.listar(c["nome"]):
        if not it["video"]:
            continue   # pasta de trabalho sem .mp4 ainda não é vídeo entregue
        f = _fmt.carregar(_saidas.formato_sugerido(it["modelo"])) if it["modelo"] else None
        videos.append({"rel": it["video"], "nome": titulos.get(it["slug"]) or it["slug"].replace("-", " "),
                       "data": it["data"], "formato": f["titulo"] if f else it["modelo"]})
    opcoes = [(f"{oc['nome']}/{m}", f"{oc['nome']} → {m}") for oc in clientes() for m in oc["modelos"]
              if oc["nome"] != c["nome"] or m not in c["modelos"]]
    ajustes = []   # só formatos que ele já ensinou algo; sem regra nem correção, não aparece
    for m in mods:
        f = _fmt.de_modelo(m["nome"])
        a = _fmt.aprendizado(f["slug"], c["nome"]) if f else {"formato": [], "cliente": m["lista_regras"]}
        if not (a["cliente"] or m["historico"]):
            continue
        ajustes.append({"modelo": m["nome"], "formato": f["slug"] if f and not f.get("oculto") else "",
                        "titulo": f["titulo"] if f else (m["ficha"].get("titulo") or m["nome"]),
                        "do_formato": len(a["formato"]), "do_cliente": len(a["cliente"]),
                        "feedbacks": len(m["historico"])})
    import acervo as _acv, voicestudio as _vs
    from _comum import ler_json as _lj
    voz_c = (_lj(c["pasta"] / "identidade.json", {}) or {}).get("voz") or {}
    favs = {t: [{"slug": i["slug"], "titulo": i.get("titulo") or i["slug"], "rel": i.get("clip_rel"),
                 "so_dele": bool(c["nome"] in ((i.get("favorito") or {}).get("clientes") or []))}
                for i in _acv.favoritos(t, c["nome"])] for t in ("musica", "sfx")}
    return render_template("cliente.html", c=c, modelos=mods, videos=videos, jobs=jobs, opcoes=opcoes,
                           material=_material.colecoes(c), ajustes=ajustes, identidade=_identidade(c),
                           voz_cliente=voz_c, vozes=_vs.vozes(), favs=favs)


def _identidade(c: dict) -> dict:
    """A cara do cliente: clientes/<C>/identidade.json; sem ele, junta cores e fontes das fichas dos formatos."""
    from _comum import ler_json
    d = ler_json(c["pasta"] / "identidade.json", None)
    if d:
        fontes = d.get("fontes") or []
        if isinstance(fontes, str):   # alguns identidade.json guardam as fontes numa frase só
            fontes = [x.strip() for x in fontes.split(";") if x.strip()]
        return {"cores": d.get("cores") or [], "fontes": fontes, "tom": d.get("tom") or d.get("uso") or ""}
    cores, fontes = [], []
    for m in _modelos(c):
        f = _ficha.carregar(m["pasta"]) or {}
        for p in f.get("paleta") or []:
            cor = (p.get("cor") if isinstance(p, dict) else str(p)).strip()
            if cor.startswith("#") and cor.upper() not in [x.upper() for x in cores]:
                cores.append(cor)
        for ft in f.get("fontes") or []:
            nome = (ft.get("nome") if isinstance(ft, dict) else str(ft)).split("-")[0].strip()
            if nome and nome not in fontes:
                fontes.append(nome)
    return {"cores": cores[:8], "fontes": fontes[:4], "tom": ""}


@app.route("/cliente/<nome>/identidade", methods=["POST"])
def cliente_identidade(nome):
    from _comum import gravar_json, ler_json
    c = _cliente(nome)
    if not c:
        abort(404)
    cores = [x.strip() for x in request.form.get("cores", "").split(",") if x.strip().startswith("#")]
    fontes = [x.strip() for x in re.split(r"[;,]", request.form.get("fontes", "")) if x.strip()]
    atual = ler_json(c["pasta"] / "identidade.json", {}) or {}   # mantém o resto (papéis das cores, uso...)
    gravar_json(c["pasta"] / "identidade.json", {**atual, "cores": cores, "fontes": fontes, "tom": request.form.get("tom", "").strip()})
    flash("✓ A cara do cliente foi salva. Vale nos próximos vídeos dele.")
    return redirect(url_for("cliente", nome=nome))


@app.route("/cliente/<nome>/voz", methods=["POST"])
def cliente_voz(nome):
    """Voz preferida do cliente: identidade.json → "voz": {"motor", "id"}. Vazio = vale a de Configurações."""
    from _comum import gravar_json, ler_json
    c = _cliente(nome)
    if not c:
        abort(404)
    atual = ler_json(c["pasta"] / "identidade.json", {}) or {}
    vid = request.form.get("voz", "").strip()
    if vid:
        atual["voz"] = {"motor": "voicestudio", "id": vid}
    else:
        atual.pop("voz", None)
    gravar_json(c["pasta"] / "identidade.json", atual)
    flash("✓ Voz do cliente salva." if vid else "✓ Voz do cliente limpa: vale a de Configurações.")
    return redirect(url_for("cliente", nome=nome) + "#voz")


@app.route("/voz/amostra")
def voz_amostra():
    """▶ ouvir: frase curta na voz pedida (VoiceStudio, grátis, cacheada em app/.cache/vozes)."""
    import voicestudio as _vs
    if not _vs.no_ar():
        abort(503, "O VoiceStudio está fora do ar. Abra o app VoiceStudio e tente de novo.")
    try:
        return send_file(str(_vs.amostra(request.args.get("voz", "default"))), mimetype="audio/mpeg", conditional=True)
    except ValueError as e:
        abort(502, str(e))


@app.route("/cliente/<nome>/modelo/<mod>")
def modelo(nome, mod):
    c = _cliente(nome)
    if not c:
        abort(404)
    m = _modelo(c, mod)
    if not m:
        abort(404)
    jobs = [j for j in _prod.listar(c["nome"]) if j["modelo"] == mod]
    for r in m['lista_regras']:
        r['antigas'] = regras.originais(m['pasta']/'aprendizado/regras.json', r)
    hist = list(reversed(m["historico"]))[:60]
    f = _ficha.carregar(m["pasta"])
    from visual_modelo import esquema
    visual = esquema(f, m['nome'])
    assets = _ficha.assets(m["pasta"])
    return render_template("modelo.html", c=c, m=m, jobs=jobs, historico=hist, f=f, assets=assets, visual=visual,
                           demos=_demos.listar(m["pasta"]), frames=_demos.frames_reais(m["outputs"]),
                           demos_rodando=_demos.rodando(m["pasta"]), demos_log=_demos.log(m["pasta"]))


# ───── material do cliente: o acervo próprio dele, em coleções (fotos do produto, provas…) ─────

def _cliente_ou_404(nome):
    c = _cliente(nome)
    if not c:
        abort(404)
    return c


@app.route("/cliente/<nome>/material/criar", methods=["POST"])
def material_criar(nome):
    c = _cliente_ou_404(nome)
    titulo = request.form.get("titulo", "").strip()
    if not titulo:
        flash("✗ Dê um nome pra coleção (ex.: Marca3, Depoimentos).")
        return redirect(url_for("cliente", nome=nome) + "#material")
    col = _material.criar(c, titulo, request.form.get("descricao", ""), request.form.get("tags", ""))
    n = 0
    for f in request.files.getlist("arquivos"):
        if f and f.filename:
            tmp = ensure(ESTUDIO / ".uploads") / f"{_prod.now_slug()}-{Path(f.filename).name}"
            f.save(str(tmp))
            try:
                _material.subir(c, col["slug"], tmp, ""); n += 1
            except Exception as e:
                flash(f"✗ {f.filename}: {e}"); tmp.unlink(missing_ok=True)
    flash(f"✓ Coleção “{titulo}” criada com {n} arquivo(s).")
    return redirect(url_for("cliente", nome=nome) + "#material")


@app.route("/cliente/<nome>/material/<slug>/subir", methods=["POST"])
def material_subir(nome, slug):
    c = _cliente_ou_404(nome)
    n = 0
    for f in request.files.getlist("arquivos"):
        if f and f.filename:
            tmp = ensure(ESTUDIO / ".uploads") / f"{_prod.now_slug()}-{Path(f.filename).name}"
            f.save(str(tmp))
            try:
                _material.subir(c, slug, tmp, ""); n += 1
            except Exception as e:
                flash(f"✗ {f.filename}: {e}"); tmp.unlink(missing_ok=True)
    flash(f"✓ {n} arquivo(s) na coleção.")
    return redirect(url_for("cliente", nome=nome) + "#material")


@app.route("/cliente/<nome>/material/<slug>/editar", methods=["POST"])
def material_editar(nome, slug):
    c = _cliente_ou_404(nome)
    try:
        _material.editar(c, slug, request.form.get("titulo", ""), request.form.get("descricao", ""),
                         request.form.get("tags", ""))
        flash("✓ Coleção atualizada.")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("cliente", nome=nome) + "#material")


@app.route("/cliente/<nome>/material/<slug>/remover", methods=["POST"])
def material_remover(nome, slug):
    c = _cliente_ou_404(nome)
    try:
        item = request.form.get("item", "").strip()
        if item:
            _material.remover_item(c, slug, item, request.form.get("motivo", ""))
            flash(f"✓ {item} foi pra lixeira (restaura em Configurações).")
        else:
            _material.remover_colecao(c, slug, request.form.get("motivo", ""))
            flash("✓ Coleção inteira foi pra lixeira (restaura em Configurações).")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("cliente", nome=nome) + "#material")


@app.route("/cliente/<nome>/material/<slug>/acervo", methods=["POST"])
def material_pro_acervo(nome, slug):
    c = _cliente_ou_404(nome)
    try:
        r = _material.pro_acervo(c, slug, request.form.get("item", ""), request.form.get("titulo", "").strip(),
                                 request.form.get("tags", "").strip())
        if r.get("ja_estava"):
            flash(f"• Já estava no acervo como “{r['titulo']}” ({r['slug']}) — não dupliquei.")
        else:
            flash(f"✓ Copiado pro acervo compartilhado como “{r['titulo']}” ({r['slug']}). "
                  f"O {nome} continua com o arquivo dele.")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("cliente", nome=nome) + "#material")


# ───── assets do modelo: o material fixo (música, capa, fonte) que entra por padrão ─────

def _modelo_ou_404(nome, mod):
    c = _cliente(nome)
    m = _modelo(c, mod) if c else None
    if not m:
        abort(404)
    return c, m


@app.route("/cliente/<nome>/modelo/<mod>/assets/subir", methods=["POST"])
def asset_subir(nome, mod):
    c, m = _modelo_ou_404(nome, mod)
    enviados, erros = 0, []
    for f in request.files.getlist("arquivos"):
        if not f or not f.filename:
            continue
        tmp = ensure(ESTUDIO / ".uploads") / f"{_prod.now_slug()}-{Path(f.filename).name}"
        f.save(str(tmp))
        try:
            _ficha.subir_asset(m["pasta"], tmp, request.form.get("nome", "").strip() if len(request.files.getlist("arquivos")) == 1 else "",
                               request.form.get("subpasta", "").strip())
            enviados += 1
        except Exception as e:
            erros.append(f"{f.filename}: {e}"); tmp.unlink(missing_ok=True)
    flash((f"✓ {enviados} asset(s) no modelo. " if enviados else "") + (" · ".join(f"✗ {x}" for x in erros)))
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#assets")


@app.route("/cliente/<nome>/modelo/<mod>/assets/renomear", methods=["POST"])
def asset_renomear(nome, mod):
    c, m = _modelo_ou_404(nome, mod)
    try:
        r = _ficha.renomear_asset(m["pasta"], request.form.get("nome", ""), request.form.get("novo", ""))
        flash(f"✓ {r['de']} → {r['para']}")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#assets")


@app.route("/cliente/<nome>/modelo/<mod>/assets/remover", methods=["POST"])
def asset_remover(nome, mod):
    c, m = _modelo_ou_404(nome, mod)
    try:
        r = _ficha.remover_asset(m["pasta"], request.form.get("nome", ""), request.form.get("motivo", "").strip(),
                                 cliente=c["nome"], modelo=m["nome"])
        aviso = (" ⚠ ele era citado por " + ", ".join(r["usado_por"]) + " — confira o render.") if r["usado_por"] else ""
        flash(f"✓ {r['asset']} foi pra lixeira (dá pra restaurar em Configurações).{aviso}")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#assets")


@app.route("/cliente/<nome>/modelo/<mod>/assets/acervo", methods=["POST"])
def asset_pro_acervo(nome, mod):
    c, m = _modelo_ou_404(nome, mod)
    try:
        r = _ficha.asset_pro_acervo(m["pasta"], request.form.get("nome", ""), request.form.get("titulo", "").strip(),
                                    request.form.get("tags", "").strip(), cliente=c["nome"], modelo=m["nome"])
        if r.get("ja_estava"):
            flash(f"• Esse arquivo já estava no acervo como “{r['titulo']}” ({r['slug']}) — não dupliquei.")
        else:
            flash(f"✓ Copiado pro acervo como “{r['titulo']}” ({r['slug']}), tags: {', '.join(r.get('tags') or [])}. "
                  f"O motor continua com o arquivo dele — no acervo tem o botão Descrever se quiser a análise da IA.")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#assets")


@app.route("/cliente/<nome>/modelo/<mod>/assets/acervo-lote", methods=["POST"])
def assets_pro_acervo_lote(nome, mod):
    """Manda pro acervo, de uma vez, tudo que ainda não está lá — nome e tags automáticos."""
    c, m = _modelo_ou_404(nome, mod)
    novos, erros = [], []
    for a in _ficha.assets(m["pasta"]):
        if a["no_acervo"] or a["tipo"] not in ("audio", "imagem", "video"):
            continue
        try:
            r = _ficha.asset_pro_acervo(m["pasta"], a["nome"], cliente=c["nome"], modelo=m["nome"])
            if not r.get("ja_estava"):
                novos.append(r["slug"])
        except Exception as e:
            erros.append(f"{a['nome']}: {e}")
    flash((f"✓ {len(novos)} arquivo(s) no acervo: {', '.join(novos[:6])}{'…' if len(novos) > 6 else ''}. " if novos else "")
          + ("Nada novo pra mandar. " if not novos and not erros else "")
          + " · ".join(f"✗ {x}" for x in erros))
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#assets")


@app.route("/cliente/<nome>/modelo/<mod>/remover", methods=["POST"])
def modelo_remover(nome, mod):
    """Tira o modelo da frente. Não apaga: vai pra lixeira do Estúdio e pode voltar inteiro."""
    try:
        r = _nc.remover_modelo(nome, mod, request.form.get("motivo", "").strip())
        flash(f"✓ Modelo {mod} removido de {nome}. Está na lixeira ({r['id']}) — dá pra restaurar "
              f"em Configurações enquanto você não apagar de vez.")
        return redirect(url_for("cliente", nome=nome))
    except Exception as e:
        flash(f"✗ {e}")
        return redirect(url_for("modelo", nome=nome, mod=mod))


@app.route("/cliente/<nome>/remover", methods=["POST"])
def cliente_remover(nome):
    """Remove o projeto inteiro. Vai pra lixeira com os modelos, templates e o registro dos vídeos."""
    try:
        r = _nc.remover_cliente(nome, request.form.get("motivo", "").strip())
        flash(f"✓ Projeto {nome} removido ({len(r['modelos'])} modelo(s)). Está na lixeira — "
              f"dá pra restaurar em Configurações enquanto você não apagar de vez.")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"✗ {e}")
        return redirect(url_for("cliente", nome=nome))


@app.route("/lixeira/<ident>/restaurar", methods=["POST"])
def lixeira_restaurar(ident):
    try:
        r = _nc.restaurar(ident)
        flash(f"✓ {r.get('asset') or r.get('item') or r.get('modelo') or 'Projeto'} de volta" + (f" em {r['cliente']}." if r.get("cliente") else "."))
        if not r.get("cliente"):
            return redirect(url_for("config"))
        if r.get("modelo"):
            return redirect(url_for("modelo", nome=r["cliente"], mod=r["modelo"]))
        return redirect(url_for("cliente", nome=r["cliente"]))
    except Exception as e:
        flash(f"✗ {e}")
        return redirect(url_for("config"))


@app.route("/lixeira/esvaziar", methods=["POST"])
def lixeira_esvaziar():
    n, erros = 0, 0
    for x in _nc.lixeira():
        try:
            _nc.apagar_da_lixeira(x["id"]); n += 1
        except Exception:
            erros += 1
    flash(f"✓ {n} item(ns) apagado(s) de vez." + (f" {erros} falharam." if erros else ""))
    return redirect(url_for("config"))


@app.route("/lixeira/<ident>/apagar", methods=["POST"])
def lixeira_apagar(ident):
    try:
        _nc.apagar_da_lixeira(ident)
        flash("✓ Apagado de vez.")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("config"))


@app.route("/cliente/<nome>/modelo/<mod>/ficha", methods=["GET", "POST"])
def ficha_editar(nome, mod):
    c = _cliente(nome)
    m = _modelo(c, mod) if c else None
    if not m:
        abort(404)
    f = _ficha.carregar(m["pasta"])
    if request.method == "POST":
        g = request.form.get
        linhas = lambda k: [x.strip() for x in g(k, "").splitlines() if x.strip()]
        nova = {k: v for k, v in (ler_json(m["pasta"] / "ficha.json", {}) or {}).items()}
        nova.update({
            "titulo": g("titulo", "").strip(), "tipo": g("tipo", "completo"), "resumo": g("resumo", "").strip(),
            "quando_usar": g("quando_usar", "").strip(),
            "formato": {"resolucao": g("formato_resolucao", "").strip(), "proporcao": g("formato_proporcao", "").strip(),
                        "duracao_tipica": g("formato_duracao", "").strip()},
            "estrutura": linhas("estrutura"),
            "paleta": [{"cor": cor.strip().upper(), "uso": uso.strip()} for cor, uso in
                       zip(request.form.getlist("paleta_cor"), request.form.getlist("paleta_uso")) if cor.strip()],
            "fontes": [{"nome": n.strip(), "uso": u.strip()} for n, u in
                       zip(request.form.getlist("fonte_nome"), request.form.getlist("fonte_uso")) if n.strip()],
            "audio": {"voz": g("audio_voz", "").strip(), "musica": g("audio_musica", "").strip(),
                      "sfx": [s.strip() for s in g("audio_sfx", "").split(",") if s.strip()]},
            "broll": g("broll", "").strip(), "entrada": g("entrada", "").strip(), "como_usar": linhas("como_usar"),
            "comando": g("comando", "").strip(), "qa": linhas("qa"), "templates": linhas("templates"),
            "motor": g("motor", "").strip(), "origem": g("origem", "").strip(), "tempo_producao": g("tempo_producao", "").strip(),
        })
        from _comum import gravar_json, append_jsonl, hoje
        gravar_json(m["pasta"] / "ficha.json", nova)
        motivo = g("motivo", "").strip()
        append_jsonl(m["pasta"] / "aprendizado" / "historico.jsonl", {
            "tipo": "ficha", "categoria": "identidade", "origem": "usuario", "createdAt": hoje(),
            "texto": "Ficha do modelo editada pelo João no Estúdio" + (f": {motivo}" if motivo else "") +
                     f". Paleta: {', '.join(p['cor'] + ' (' + p['uso'] + ')' for p in nova['paleta'])}. Fontes: {', '.join(x['nome'] for x in nova['fontes'])}.",
        })
        flash("✓ Ficha salva e registrada no histórico do modelo")
        return redirect(url_for("modelo", nome=c["nome"], mod=mod))
    return render_template("ficha_editar.html", c=c, m=m, f=f)


@app.route("/cliente/<nome>/modelo/<mod>/demos/gerar", methods=["POST"])
def demos_gerar(nome, mod):
    c = _cliente(nome)
    m = _modelo(c, mod) if c else None
    if not m:
        abort(404)
    _demos.gerar(c, m, _ficha.carregar(m["pasta"]), _prod.modelo_claude())
    flash("Gerando demonstrações com o Claude — leva alguns minutos; recarregue a página.")
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#estrutura")


@app.route("/cliente/<nome>/modelo/<mod>/demos/upload", methods=["POST"])
def demos_upload(nome, mod):
    c = _cliente(nome)
    m = _modelo(c, mod) if c else None
    if not m:
        abort(404)
    d = ensure(m["pasta"] / "demos")
    idx = ler_json(d / "index.json", []) or []
    n = 0
    for f in request.files.getlist("arquivos"):
        if f and f.filename:
            nome_arq = f"{_prod.now_slug()}-{Path(f.filename).name}"
            f.save(str(d / nome_arq))
            idx.append({"arquivo": nome_arq, "titulo": request.form.get("titulo") or Path(f.filename).stem,
                        "descricao": request.form.get("descricao", "")})
            n += 1
    from _comum import gravar_json
    gravar_json(d / "index.json", idx)
    flash(f"✓ {n} demonstração(ões) adicionada(s)")
    return redirect(url_for("modelo", nome=nome, mod=mod) + "#estrutura")


@app.route("/novo-cliente", methods=["GET", "POST"])
def novo_cliente():
    cls = clientes()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        portar = request.form.get("portar", "").strip() or None
        try:
            c = _nc.criar(nome, env_de=request.form.get("env_de") or None, portar=portar,
                          descricao=request.form.get("descricao", ""))
        except Exception as e:
            flash(f"✗ {e}")
            return redirect(url_for("novo_cliente"))
        flash(f"✓ Cliente {c['nome']} criado" + (f" com o modelo portado de {portar}" if portar else ""))
        return redirect(url_for("cliente", nome=c["nome"]))
    opcoes = [(f"{c['nome']}/{m}", f"{c['nome']} → {m}") for c in cls for m in c["modelos"]]
    return render_template("novo_cliente.html", clientes=cls, opcoes=opcoes)


@app.route("/cliente/<nome>/portar", methods=["POST"])
def portar(nome):
    c = _cliente(nome)
    if not c:
        abort(404)
    origem = request.form.get("portar", "")
    try:
        oc, om = origem.split("/", 1)
        _nc.portar_modelo(c, oc, om, request.form.get("novo_nome") or None)
        flash(f"✓ Modelo {om} portado de {oc} pra {c['nome']} (aprendizado zerado)")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("cliente", nome=c["nome"]))


# ───────────────────────── novo vídeo / jobs ─────────────────────────

def _materiais_do_form(cli_nome: str) -> list:
    """Material próprio deste vídeo: o que ele subiu agora + as coleções do cliente que ele marcou."""
    mats = []
    for mf in request.files.getlist("materiais"):
        if mf and mf.filename:
            mp = UPLOADS / f"{_prod.now_slug()}-{Path(mf.filename).name}"
            mf.save(str(mp)); mats.append(mp)
    c = _cliente(cli_nome)
    if c:
        mats += _material.copiar_para(c, request.form.getlist("material_cliente"), UPLOADS)
    return mats


@app.route("/novo-video", methods=["GET", "POST"])
def novo_video():
    cls = clientes()
    if request.method == "POST":
        cli = request.form.get("cliente", "")
        mod = request.form.get("modelo", "")
        titulo = request.form.get("titulo", "").strip()
        f = request.files.get("bruto")
        escolhido = session.pop("bruto_escolhido", "")
        if escolhido and cli and mod and not (f and f.filename):
            src = Path(escolhido)
            if src.is_file():
                tmp = UPLOADS / f"{_prod.now_slug()}-{src.name}"
                import shutil as _sh; _clonar(str(src), str(tmp))
                mats = _materiais_do_form(cli)
                job = _prod.criar(cli, mod, tmp, titulo or src.stem, request.form.get("briefing", ""),
                                  request.form.getlist("brolls"), request.form.getlist("camadas"), mats,
                                  request.form.get("cortar_bruto") == "1")
                return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))
        vindo_do_corte = request.form.get("do_corte", "").strip()
        if vindo_do_corte and cli and mod:
            cc = _cortes.avulso_carregar(vindo_do_corte)
            if cc and cc.get("cortado"):
                tmp = UPLOADS / f"{_prod.now_slug()}-{cc['titulo']}.mp4"
                import shutil as _sh; _clonar(str(RAIZ / cc["cortado"]), str(tmp))
                job = _prod.criar(cli, mod, tmp, titulo or cc["titulo"], request.form.get("briefing", ""),
                                  request.form.getlist("brolls"), request.form.getlist("camadas"),
                                  _materiais_do_form(cli), False)
                return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))
        if not (cli and mod and f and f.filename):
            flash("✗ Escolha cliente, modelo e o vídeo bruto.")
            return redirect(url_for("novo_video", cliente=cli))
        ext = Path(f.filename).suffix.lower()
        if ext not in VIDEO_EXTS:
            flash(f"✗ Formato não suportado: {ext}")
            return redirect(url_for("novo_video", cliente=cli))
        tmp = UPLOADS / f"{_prod.now_slug()}-{Path(f.filename).name}"
        f.save(str(tmp))
        mats = _materiais_do_form(cli)
        try:
            job = _prod.criar(cli, mod, tmp, titulo or Path(f.filename).stem,
                              request.form.get("briefing", ""), request.form.getlist("brolls"),
                              request.form.getlist("camadas"), mats,
                              request.form.get("cortar_bruto") == "1")
        except Exception as e:
            flash(f"✗ {e}")
            return redirect(url_for("novo_video", cliente=cli))
        return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))
    pre_corte = request.args.get("corte", "")
    pre_cliente = request.args.get("cliente", "")
    pre_modelo = request.args.get("modelo", "")
    if not pre_corte:   # o jeito novo de criar vídeo é o /criar; esta página só fica pro "Usar num vídeo novo" do corte
        import formatos as _fmt
        fm = _fmt.de_modelo(pre_modelo) if pre_modelo else None
        return redirect(url_for("novo_tela", **{k: v for k, v in (("cliente", pre_cliente), ("estilo", fm["slug"] if fm else "")) if v}))
    mapa = {}
    for c in cls:
        lst = []
        for m in _modelos(c):
            f = _ficha.carregar(m["pasta"])
            desc = f.get("resumo") or (m["descricoes"][0]["descricao"] if m["descricoes"] else "")
            lst.append({"nome": m["nome"], "desc": desc[:260], "titulo": f.get("titulo") or m["nome"], "tipo": f.get("tipo") or "completo"})
        mapa[c["nome"]] = lst
    material_por_cliente = {x["nome"]: _material.colecoes(x) for x in cls}
    return render_template("novo_video.html", clientes=cls, mapa=mapa, material_por_cliente=material_por_cliente,
                           pre_cliente=pre_cliente, pre_modelo=pre_modelo, pre_corte=pre_corte,
                           bruto_escolhido=session.get("bruto_escolhido", ""),
                           acervo=_acervo.listar(), tags=_acervo.todas_tags())


def _formato_do_job(j: dict) -> dict:
    import formatos as _fmt
    return _fmt.carregar(j.get("formato") or "") or _fmt.de_modelo(j.get("modelo", "")) or {}


def _esteira(j: dict) -> bool:
    """Formato de motor com esteira (passos fixos do próprio formato): a tela só mostra o storyboard pra aprovar.
    O de vídeo gravado segue a tela de vídeo gravado (com a escolha das cenas), mesmo declarando os passos."""
    import formatos as _fmt
    return _fmt.segue_esteira(_formato_do_job(j))


def _capas(j: dict, plano: dict | None) -> None:
    """Capa de cada opção de cena: GIF → poster → um quadro do clipe (rota /frame) → nada.
    Nunca a folha de contato (-sheet): ela vira miniatura repetida, em mosaico."""
    sb = RAIZ / j["sandbox"]
    for b in (plano or {}).get("beats", []):
        for o in b.get("opcoes") or []:
            o["capa"], o["capa_frame"] = "", None
            gif = _sbd._dentro(sb, o.get("gif"))
            poster = next((p for p in (_sbd._dentro(sb, x) for x in (o.get("poster"), f"brolls/{o.get('id')}-poster.jpg"))
                           if p and p.suffix.lower() in IMAGEM_EXTS), None)
            m = None if (gif or poster) else _sbd.midia_opcao(sb, b, o)
            if gif or poster:
                o["capa"] = rel(gif or poster)
            elif m and m["tipo"] in ("imagem", "gif"):
                o["capa"] = rel(m["arquivo"])
            elif m:
                o["capa_frame"] = {"caminho": rel(m["arquivo"]), "t": round(m["t"], 1)}
            elif b.get("escolha") == o.get("id") and j.get("saida") and (RAIZ / j["saida"]).is_file():
                o["capa_frame"] = {"caminho": j["saida"], "t": round(float(b.get("inicio") or 0) + 0.8, 1)}


def _storyboard_em_dia(j: dict, esteira: bool) -> None:
    """Formato sem esteira: a folha sai sempre da ferramenta fixa (storyboard.py). Refaz quando o plano mudou,
    só enquanto o plano está esperando aprovação (vídeo pronto não é mexido)."""
    sb = RAIZ / j["sandbox"]
    if esteira or j.get("rodando") or j.get("status") not in ("plano", "plano_aprovado"):
        return
    if not ((_prod.plano(j) or {}).get("beats")):
        return
    import formatos as _fmt
    if _fmt.storyboard_proprio(_formato_do_job(j)):   # vídeo gravado com storyboard do formato (Cinematográfico): não escrever por cima
        return
    try:
        if _sbd.desatualizado(sb):
            _sbd.gerar(sb)
    except Exception as e:                     # sem fonte, sem vídeo, plano vazio: a tela abre mesmo assim
        print(f"storyboard de {j['cliente']}/{j['slug']}: {e}", file=sys.stderr)


def _cor_destaque(c: dict | None) -> str:
    for cor in (_identidade(c).get("cores") if c else []) or []:
        h = cor.lstrip("#")
        if len(h) == 6:
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            if 0.08 < (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.8:
                return "#" + h
    return ""


@app.route("/job/<cli>/<slug>")
def job(cli, slug):
    _prod.reconciliar(cli)   # vídeo pronto pelo chat não pode abrir no storyboard
    j = _prod.carregar(cli, slug)
    if not j:
        abort(404)
    c = _cliente(cli)
    m = _modelo(c, j["modelo"]) if c else None
    sb = RAIZ / j["sandbox"]
    def _txt(nome):
        p = sb / nome
        return p.read_text(encoding="utf-8") if p.exists() else ""
    fmt = _formato_do_job(j)
    esteira = _esteira(j)   # só formato de motor; o de vídeo gravado mantém a tela de vídeo gravado
    if _prod.plano(j):
        _storyboard_em_dia(j, esteira)
    plano = takes.preparar_tela(j, _prod.plano(j))
    _capas(j, plano)
    musica = efeitos = None
    if plano:
        try:
            musica = _mb.opcoes_do_plano(j, plano, formato=fmt.get("slug"))
        except Exception as e:
            print(f"música de {cli}/{slug}: {e}", file=sys.stderr)
            musica = {"opcoes": [], "escolha": "", "clima": ""}
        efeitos = _mb.efeitos_do_plano(j, plano)
        som = fmt.get("som") if isinstance(fmt.get("som"), dict) else {}
        nao_usa = lambda k: isinstance(som.get(k), dict) and som[k].get("usa") is False
        if nao_usa("musica"):   # formato sem música: a tela não oferece faixa nem efeito
            musica = efeitos = None
        elif nao_usa("efeitos"):
            efeitos = None
    storyboard = rel(sb / 'storyboard.jpg') if (sb / 'storyboard.jpg').is_file() else ''
    previa_som = rel(sb / 'previa-som.m4a') if storyboard and (sb / 'previa-som.m4a').is_file() else ''   # o som do storyboard (motor)
    import formatos as _fmt
    est_fmt = _fmt.esteira(fmt) if esteira else None   # o arquivo do vídeo do formato (padrão cenas.json)
    cenas_ok = (sb / ((est_fmt or {}).get('cenas') or 'cenas.json')).is_file()   # sem ele: vídeo feito antes da esteira
    roteiro_txt = (RAIZ / j['bruto']).read_text(encoding='utf-8') if j.get('entrada') == 'roteiro' and (RAIZ / j['bruto']).is_file() else ''
    import andamento as _and
    return render_template("job.html", andamento=_and.carregar(cli, slug), storyboard=storyboard, previa_som=previa_som, roteiro_txt=roteiro_txt, j=j, c=c, m=m, pipeline=pipeline.etapas(j), log=_prod.log_atual(j), plano=plano,
                           esteira=esteira, cenas_ok=cenas_ok, musica=musica, efeitos=efeitos, cor_destaque=_cor_destaque(c),
                           cenas_qtd=(edicao.quantidade(j) if (j.get('broll_config') or {}).get('origem') not in (None, 'nenhum') else None),
                           corte=_prod.corte_json(j), corte_rodando=_prod.corte_rodando(j), corte_etapa=__import__("corte").etapa(RAIZ / j["sandbox"] / "work"),
                           checagem_corte=(__import__("corte").verificar(RAIZ / j["sandbox"] / "work") if _prod.corte_json(j) else None),
                           para_acervo=_prod.itens_para_acervo(j) if j.get("saida") else [],
                           destino_padrao=str(_prod.destino_padrao(cli)), pasta_prevista=str(_prod.pasta_destino(j)),
                           pasta_configurada=bool((_prod.config().get("destinos") or {}).get(cli)),
                           resultado=_txt("RESULTADO.md"), analise=_txt("ANALISE.md"), previas_md=_txt("PREVIAS.md"),
                           prompt="" if j["status"]=="arquivado" else (_prod.prompt_analise(j) if not plano else _prod._prompt_producao_com_plano(j)),
                           modelo_claude=ia.rotulo(j.get("ia")), comando_final=_arquivo.comando_final(j))


# ───────────────────────── corte avulso (só arrumar um vídeo) ─────────────────────────

@app.route("/cortes")
def cortes():
    return render_template("cortes.html", cortes=_cortes.avulso_listar())


@app.route("/novo-video/finder", methods=["POST"])
def novo_video_finder():
    """Finder nativo no Novo vídeo: devolve o caminho escolhido pra sessão e volta pro formulário."""
    caminho = _cortes.avulso_escolher_no_finder("Escolha o vídeo bruto")
    if caminho:
        session["bruto_escolhido"] = caminho
        flash(f"✓ Escolhido: {Path(caminho).name}")
    return redirect(url_for("novo_video", cliente=request.form.get("cliente", ""), modelo=request.form.get("modelo", "")))


@app.route("/cortes/finder", methods=["POST"])
def cortes_finder():
    """Abre o Finder do macOS pelo servidor e usa o arquivo escolhido."""
    caminho = _cortes.avulso_escolher_no_finder("Escolha o vídeo pra recortar")
    if not caminho:
        flash("Nenhum arquivo escolhido.")
        return redirect(url_for("cortes"))
    try:
        c = _cortes.avulso_criar_do_mac(caminho, request.form.get("titulo", "").strip())
        _cortes.avulso_montar(c["slug"], request.form.get("briefing", ""),
                              roteiro=request.form.get("roteiro", ""))
        return redirect(url_for("corte_detalhe", slug=c["slug"]))
    except Exception as e:
        flash(f"✗ {e}")
        return redirect(url_for("cortes"))


@app.route("/cortes/do-mac", methods=["POST"])
def cortes_do_mac():
    try:
        c = _cortes.avulso_criar_do_mac(request.form.get("caminho", ""), request.form.get("titulo", "").strip())
        _cortes.avulso_montar(c["slug"], request.form.get("briefing", ""),
                              roteiro=request.form.get("roteiro", ""))
        return redirect(url_for("corte_detalhe", slug=c["slug"]))
    except Exception as e:
        flash(f"✗ {e}")
        return redirect(url_for("cortes"))


@app.route("/cortes/<slug>/revisar", methods=["POST"])
def corte_revisar(slug):
    import corte as _c
    c = _cortes.avulso_carregar(slug)
    fb = request.form.get("feedback", "").strip()
    if not c or not fb:
        flash("✗ escreva o que ficou errado"); return redirect(url_for("corte_detalhe", slug=slug))
    _c.revisar(RAIZ / c["original"], c["work"], fb)
    flash("Revisando o corte com o seu apontamento — e registrando o aprendizado.")
    return redirect(url_for("corte_detalhe", slug=slug))


@app.route("/cortes/novo", methods=["POST"])
def cortes_novo():
    f = request.files.get("video")
    if not f or not f.filename:
        flash("✗ Escolha um vídeo."); return redirect(url_for("cortes"))
    ext = Path(f.filename).suffix.lower()
    if ext not in VIDEO_EXTS:
        flash(f"✗ Formato não suportado: {ext}"); return redirect(url_for("cortes"))
    tmp = UPLOADS / f"{_prod.now_slug()}-{Path(f.filename).name}"
    f.save(str(tmp))
    c = _cortes.avulso_criar(tmp, request.form.get("titulo", "").strip())
    _cortes.avulso_montar(c["slug"], request.form.get("briefing", ""),
                              roteiro=request.form.get("roteiro", ""))
    return redirect(url_for("corte_detalhe", slug=c["slug"]))


@app.route("/cortes/<slug>")
def corte_detalhe(slug):
    c = _cortes.avulso_carregar(slug)
    if not c:
        abort(404)
    import corte as _c
    return render_template("corte_detalhe.html", c=c, checagem=_c.verificar(c["work"]) if c.get("proposta") else None,
                           regras_corte=_c.regras().get("regras", []), hist_corte=_c.historico(12),
                           roteiro=_cortes.avulso_roteiro(slug), ia_rotulo=ia.rotulo())


@app.route("/cortes/<slug>/propor", methods=["POST"])
def corte_propor(slug):
    com_ia = request.form.get("acao") == "ia"
    refazer = bool(request.form.get("refazer"))
    _cortes.avulso_montar(slug, request.form.get("briefing", ""), com_ia=com_ia, refazer=refazer,
                          roteiro=request.form.get("roteiro", ""))
    flash("Pedindo ajuda da IA pra revisar o corte." if com_ia
          else ("Refazendo a transcrição e montando o corte." if refazer
                else "Transcrevendo e montando o corte (sem IA)."))
    return redirect(url_for("corte_detalhe", slug=slug))


@app.route("/cortes/<slug>/salvar", methods=["POST"])
def corte_salvar(slug):
    _cortes.avulso_salvar(slug, request.form.getlist("manter"), request.form.get("obs", ""))
    if request.form.get("acao") == "aplicar":
        try:
            _cortes.avulso_render(slug, float(request.form.get("respiro") or 0.30),
                                  float(request.form.get("aperto") or 0.70))
            flash("✂︎ Cortando o vídeo — a página avisa quando terminar (pode fechar, ele continua).")
        except Exception as e:
            flash(f"✗ {e}")
    else:
        flash("✓ Escolhas salvas.")
    return redirect(url_for("corte_detalhe", slug=slug))


@app.route("/cortes/<slug>/exportar", methods=["POST"])
def corte_exportar(slug):
    import shutil as _sh
    c = _cortes.avulso_carregar(slug)
    if not c or not c.get("cortado"):
        flash("✗ ainda não há vídeo cortado"); return redirect(url_for("corte_detalhe", slug=slug))
    dst = Path.home() / "Downloads" / f"{c['titulo']}.mp4"
    n = 2
    while dst.exists():
        dst = Path.home() / "Downloads" / f"{c['titulo']} ({n}).mp4"; n += 1
    _clonar(str(RAIZ / c["cortado"]), str(dst))
    subprocess.run(["open", "-R", str(dst)])
    flash(f"✓ Salvo em {dst}")
    return redirect(url_for("corte_detalhe", slug=slug))


@app.route("/cortes/<slug>/remover", methods=["POST"])
def corte_remover(slug):
    _cortes.avulso_remover(slug)
    flash("Corte apagado.")
    return redirect(url_for("cortes"))


@app.route("/job/<cli>/<slug>/corte", methods=["POST"])
def job_corte(cli, slug):
    _prod.propor_corte(cli, slug, com_ia=request.form.get("acao") == "ia")
    flash("Transcrevendo e montando o corte — acompanhe abaixo.")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/corte/revisar", methods=["POST"])
def job_corte_revisar(cli, slug):
    import corte as _c
    j = _prod.carregar(cli, slug)
    fb = request.form.get("feedback", "").strip()
    if fb:
        _c.revisar(RAIZ / j["bruto"], RAIZ / j["sandbox"] / "work", fb, job_id=f"{cli}/{slug}")
        flash("Revisando o corte e registrando o aprendizado.")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/corte/salvar", methods=["POST"])
def job_corte_salvar(cli, slug):
    _prod.salvar_corte(cli, slug, request.form.getlist("manter"), request.form.get("obs", ""))
    if request.form.get("acao") == "aplicar":
        try:
            _prod.aplicar_corte(cli, slug, float(request.form.get("respiro") or 0.16),
                                float(request.form.get("aperto") or 0.55))
            flash("✓ Corte aplicado. O vídeo cortado virou o bruto da edição.")
        except Exception as e:
            flash(f"✗ {e}")
    else:
        flash("✓ Escolhas do corte salvas.")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/analisar", methods=["POST"])
def job_analisar(cli, slug):
    j = _prod.carregar(cli, slug)
    if "usar_broll" in request.form or not _esteira(j):   # formato com esteira não tem a pergunta das cenas
        edicao.aplicar(j, edicao.preferencias(request.form))
    _prod.salvar(j)
    _prod.analisar(cli, slug)
    return redirect(url_for("job", cli=cli, slug=slug))


@app.post('/job/<cli>/<slug>/preferencias')
def job_preferencias(cli, slug):
    j = _prod.carregar(cli, slug)
    if not j:
        abort(404)
    if j.get('rodando') or j['status'] in ('na_fila', 'exportado', 'arquivado'):
        raise ValueError('Aguarde a edição terminar antes de mudar as preferências.')
    prefs = edicao.preferencias(request.form)
    p = _prod.plano(j)
    if p:
        selected = edicao.selecionados(p)
        if prefs['origem'] == 'nenhum':
            for b in selected:
                b['escolha'] = None
        elif len(selected) > prefs['quantidade']:
            raise ValueError('Há mais cenas selecionadas que esse limite. Desmarque as cenas extras primeiro.')
        p.pop('aprovado_em', None)
        _prod.salvar_plano(j, p)
        j['edicao_alterada'] = bool(j.get('saida'))
        j['status'] = 'plano'
    edicao.aplicar(j, prefs)
    _prod.salvar(j)
    flash('Preferências salvas. Nenhuma busca ou geração foi iniciada.')
    return redirect(url_for('job', cli=cli, slug=slug) + '#preferencias-edicao')


def _audio_do_form(cli: str, slug: str) -> tuple[dict | None, dict | None]:
    """Blocos Música e Efeitos do storyboard → (musica, sfx) pro aprovar_plano. None = o form não trouxe o bloco."""
    f = request.form
    musica = sfx = None
    if "musica" in f:
        v = f.get("musica", "")
        if v == "sem":
            musica = {"sem": True}
        elif v:
            j = _prod.carregar(cli, slug)
            p = _prod.plano(j)
            op = next((o for o in _mb.opcoes_do_plano(j, p, formato=_formato_do_job(j).get("slug"))["opcoes"]
                       if o["id"] == v), None)
            if op:
                musica = {k: op[k] for k in _mb.CAMPOS_OPCAO if op.get(k) not in (None, "") and k != "usada_txt"}
    if f.get("sfx_bloco") == "1":
        sfx = {"ligado": f.get("sfx_ligado") == "1", "ativos": f.getlist("sfx")}
    return musica, sfx


def _aprovar(cli, slug, escolhas, comentarios, obs, musica=None, sfx=None):
    """aprovar_plano com música e efeitos. Se a versão do producao ainda não recebe esses dois, grava aqui."""
    import inspect
    try:
        params = inspect.signature(_prod.aprovar_plano).parameters
        aceita = "musica" in params or any(p.kind == p.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        aceita = True
    if aceita:
        return _prod.aprovar_plano(cli, slug, escolhas, comentarios, obs, musica=musica, sfx=sfx)
    j = _prod.aprovar_plano(cli, slug, escolhas, comentarios, obs)
    if musica is not None or sfx is not None:
        p = _prod.plano(j) or {}
        _prod.salvar_plano(j, _mb.aplicar_no_plano(p, musica, sfx))
    return j


@app.route("/job/<cli>/<slug>/plano", methods=["POST"])
def job_plano(cli, slug):
    acao, _, alvo = request.form.get("acao", "salvar").partition(":")
    if acao == "buscar" and _prod.carregar(cli, slug).get('broll_config', {}).get('origem') == 'nenhum':
        raise ValueError('Ative as cenas de apoio nas preferências da edição antes de buscar.')
    escolhas = {k[len("escolha_"):]: v for k, v in request.form.items() if k.startswith("escolha_")}
    comentarios = {k[len("coment_"):]: v for k, v in request.form.items() if k.startswith("coment_")}
    if alvo:
        j = _prod.carregar(cli, slug)
        if not any(b['id']==alvo for b in (_prod.plano(j) or {}).get('beats',[])):
            raise ValueError('Trecho não encontrado.')
    musica, sfx = _audio_do_form(cli, slug)
    _aprovar(cli, slug, escolhas, comentarios, request.form.get("obs", ""), musica=musica, sfx=sfx)
    if acao in ('avaliar', 'recuperar'):
        j = _prod.carregar(cli, slug)
        j['take_em_analise'] = alvo
        _prod.salvar(j)
        _prod._disparar(j, takes.prompt(j, alvo, acao=='avaliar'), 'takes', 'plano')
    elif acao == "buscar":
        j = _prod.carregar(cli, slug)
        j["escopo_edicao"] = "busca"
        if j.get('broll_config') and j['broll_config']['origem'] == 'ia':
            j['broll_config']['origem'] = 'misto'
            flash('Você tinha escolhido só imagem por IA. Pra buscar cenas reais, mudei as cenas para "As duas" '
                  '(dá pra voltar em Preferências da edição).')
        _prod.salvar(j)
        _prod.rebuscar(cli, slug, alvo or None)
    elif acao == "previas":
        _prod.gerar_previas(cli, slug)
    elif acao == "render":
        _prod.renderizar(cli, slug)
    return redirect(url_for("job", cli=cli, slug=slug))


@app.post("/job/<cli>/<slug>/take")
def job_take(cli, slug):
    j = _prod.carregar(cli, slug)
    if not j: abort(404)
    upload=request.files.get('take')
    if not upload or not upload.filename: raise ValueError('Escolha um arquivo.')
    beat=request.form.get('beat','')
    takes.anexar(j, beat, upload)
    flash('Take anexado. Clique em Analisar meu take para conferir se combina com a fala; ele ainda não foi selecionado.')
    return redirect(url_for('job',cli=cli,slug=slug)+'#'+beat)


@app.route("/job/<cli>/<slug>/material", methods=["POST"])
def job_material(cli, slug):
    j = _prod.carregar(cli, slug)
    d = ensure(RAIZ / j["sandbox"] / "material")
    n = 0
    for mf in request.files.getlist("materiais"):
        if mf and mf.filename:
            mf.save(str(d / Path(mf.filename).name)); j.setdefault("materiais", []).append(f"material/{Path(mf.filename).name}"); n += 1
    _prod.salvar(j)
    (RAIZ / j["sandbox"] / "BRIEF.md").write_text(_prod.brief_md(j), encoding="utf-8")
    flash(f"✓ {n} arquivo(s) de material próprio adicionados — na próxima análise/rebusca eles entram como prioridade")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/finalizar", methods=["POST"])
def job_finalizar(cli, slug):
    from _comum import gravar_json
    destino = request.form.get("destino", "").strip()
    if destino:
        cfg = _prod.config(); cfg.setdefault("destinos", {})[cli] = destino; gravar_json(_prod.CONFIG, cfg)
    try:
        j = _prod.finalizar(cli, slug, Path(destino).expanduser() if destino else None, apagar=request.form.get("apagar") == "1", exemplo=request.form.get("exemplo") == "1")
        flash(f"✓ Exportado pra {j['pasta_mac']}" + (" e sandbox/renders apagados" if j["status"] == "arquivado" else ""))
    except Exception as e:
        flash(f"✗ {e}")
    volta = request.form.get("volta", "")   # a página do vídeo ("Aprovado — e agora?") pede pra voltar pra ela
    return redirect(volta if volta.startswith("/andamento/") else url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/apagar-tudo", methods=["POST"])
def job_apagar_tudo(cli, slug):
    try:
        _prod.apagar_apos_export(cli, slug)
        flash("✓ Sandbox, renders e candidatos apagados. Job arquivado. "
              "O aprendizado deste modelo está sendo passado a limpo: o que você ensinou vira regra "
              "e o histórico cru vai pro arquivo.")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/acervo-opcao", methods=["POST"])
def job_acervo_opcao(cli, slug):
    m = _prod.guardar_opcao_no_acervo(cli, slug, request.form.get("beat", ""), request.form.get("op", ""), request.form.get("tags", ""))
    flash(f"✓ Guardado no acervo como {m['slug']}" if m else "✗ arquivo dessa opção não existe mais")
    return redirect(url_for("job", cli=cli, slug=slug) + "#" + request.form.get("beat", ""))


@app.route("/job/<cli>/<slug>/acervo", methods=["POST"])
def job_acervo(cli, slug):
    j = _prod.carregar(cli, slug)
    ids = request.form.getlist("guardar")
    tags = {k[len("tags_"):]: v for k, v in request.form.items() if k.startswith("tags_")}
    titulos={k[7:]:v for k,v in request.form.items() if k.startswith('titulo_')}
    descricoes={k[10:]:v for k,v in request.form.items() if k.startswith('descricao_')}
    n = _prod.guardar_no_acervo(j, ids, tags, titulos, descricoes)
    flash(f"✓ {n} item(ns) guardado(s) no acervo")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/apagar", methods=["POST"])
def job_apagar(cli, slug):
    import saidas as _saidas
    try:
        flash(_saidas.mensagem(_prod.apagar(cli, slug)))
    except ValueError as e:
        flash(f"✗ {e}")
        return redirect(url_for("job", cli=cli, slug=slug))
    return redirect(url_for("cliente", nome=cli))


@app.route("/job/<cli>/<slug>/tentar", methods=["POST"])
def job_tentar(cli, slug):
    try:
        _prod.tentar_de_novo(cli, slug)
        flash("✓ Tentando de novo.")
    except Exception as e:
        flash(f"✗ {e}")
    volta = request.form.get("volta") or ""
    return redirect(volta if volta.startswith("/") and not volta.startswith("//") else url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/previas", methods=["POST"])
def job_previas(cli, slug):
    _prod.gerar_previas(cli, slug)
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/renderizar", methods=["POST"])
def job_renderizar(cli, slug):
    _prod.renderizar(cli, slug)
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/rodar", methods=["POST"])
def job_rodar(cli, slug):
    _prod.rodar(cli, slug)
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/parar", methods=["POST"])
def job_parar(cli, slug):
    _prod.parar(cli, slug)
    flash("Execução interrompida.")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/job/<cli>/<slug>/feedback", methods=["POST"])
def job_feedback(cli, slug):
    decisao = request.form.get("decisao", "ajustar")
    texto = request.form.get("texto", "")
    categoria = request.form.get("categoria", "geral")
    try:
        _prod.feedback(cli, slug, decisao, texto, categoria)
        if texto.strip():   # REGRA Nº 2 com gate: propõe o "Aprendi:" e só grava no OK do João (tela Em andamento / Esperando você)
            try:
                import aprendi as _ap
                j = _prod.carregar(cli, slug) or {}
                _ap.propor(cli, slug, texto, formato=j.get("formato") or "", modelo=j.get("modelo") or "", titulo=j.get("titulo") or slug)
            except Exception as e_:  # noqa: BLE001
                print(f"(aprendi não propôs: {e_})", file=sys.stderr)
        flash("✓ Feedback registrado no aprendizado do modelo" + (" — o Claude está consolidando a regra"
                                                                  + (" e refazendo o vídeo" if decisao == "ajustar" else "") if texto.strip() or decisao == "ajustar" else ""))
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("job", cli=cli, slug=slug))


@app.route("/api/job/<cli>/<slug>/log")
def api_job_log(cli, slug):
    j = _prod.carregar(cli, slug)
    if not j:
        abort(404)
    import andamento as _and
    a = _and.carregar(cli, slug)
    return jsonify({"status": j["status"], "rodando": j["rodando"], "log": _prod.log_atual(j, 12000),
                    "saida": j.get("saida"), "versao": j.get("versao"), "pipeline": pipeline.etapas(j),
                    "andamento": {"texto": a["atual"].get("texto", ""), "ha": a["ha"], "estado": a["estado"]} if a else None})


# ───────────────────────── acervo ─────────────────────────

@app.route("/acervo")
def acervo():
    termo = request.args.get("q", "")
    tag = request.args.get("tag", "")
    tipo = request.args.get("tipo", "") if "tipo" in request.args else ("" if request.args.get("tag") or request.args.get("q") else "video")   # 4 abas: abre em Vídeos (tipo= vazio = Tudo)
    modo=request.args.get('modo','texto')
    soa = request.args.get("soa", "")
    itens=semantica.consultar(termo,top=100,tipo=tipo,tag=tag) if termo and modo=='fala' else _acervo.listar(termo,tag,tipo,soa)
    uso=request.args.get('uso','')
    if uso=='fav':itens=[i for i in itens if _acervo.favorito_de(i, request.args.get('cliente') or None) or (not request.args.get('cliente') and (i.get('favorito') or {}).get('clientes'))]
    if uso=='nunca':itens=[i for i in itens if not i.get('usos')]
    _fora = {id(x) for x in itens if x.get('tipo') == 'musica'} - {id(x) for x in _mb.sem_reprovadas([x for x in itens if x.get('tipo') == 'musica'])}   # "Não usar mais" some da Biblioteca (o arquivo fica)
    itens=[x for x in itens if id(x) not in _fora]
    if uso=='mais':itens.sort(key=lambda x:len(x.get('usos',[])),reverse=True)
    # música e efeito: além da Biblioteca, tudo que o Estúdio já tem nos formatos e nos clientes (só lê, não copia)
    fonte = request.args.get("fonte", "")
    fonte = fonte if fonte in ("biblioteca", "formatos", "clientes") else ""
    por_fonte = {k: _mb.fontes_estudio(k) for k, _ in _acervo.TIPOS if k in ("musica", "sfx")}
    de_fora = None
    if tipo in por_fonte and not (tag or soa or uso):
        de_fora = _mb.fontes_estudio(tipo, termo) if termo else por_fonte[tipo]
    contagem = {k: len(_acervo.listar(tipo=k)) for k, _ in _acervo.TIPOS}
    for k, f in por_fonte.items():                       # a aba mostra o total, não só o que está na Biblioteca
        contagem[k] += len(f["formatos"]) + len(f["clientes"])
    return render_template("acervo.html", itens=itens, modo=modo, uso=uso, indice=ler_json(semantica.INDICE,{}) or {}, tags=_acervo.todas_tags(),
                           termo=termo, tag=tag, tipo=tipo, soa=soa, tipos=_acervo.TIPOS, checklist=_acervo.CHECKLIST,
                           facetas=_acervo.facetas(tipo), fonte=fonte, de_fora=de_fora,
                           resumo_audio={k: {n: len(v) for n, v in f.items()} for k, f in por_fonte.items()},
                           contagem=contagem)


@app.route("/acervo/adicionar", methods=["POST"])
def acervo_adicionar():
    titulo = request.form.get("titulo", "").strip()
    tags = request.form.get("tags", "")
    url = request.form.get("url", "").strip()
    check = {k: bool(request.form.get(f"chk_{k}")) for k, _ in _acervo.CHECKLIST}
    try:
        n = 0
        if url:
            _acervo.adicionar_url(url, titulo or url, tags, request.form.get("secao", "").strip(),
                                  request.form.get("autor", ""), request.form.get("licenca", ""),
                                  request.form.get("observacao", ""), so_audio=request.form.get("so_audio") == "1")
            n = 1
        for f in request.files.getlist("arquivos"):
            if not f or not f.filename:
                continue
            tmp = UPLOADS / f"{_prod.now_slug()}-{Path(f.filename).name}"
            f.save(str(tmp))
            _acervo.adicionar_arquivo(tmp, titulo if (titulo and n == 0) else Path(f.filename).stem, tags,
                                      fonte=request.form.get("fonte", ""), autor=request.form.get("autor", ""),
                                      licenca=request.form.get("licenca", ""),
                                      observacao=request.form.get("observacao", ""), origem_tipo="upload",
                                      checklist=check, mover=True, extra={k:request.form.get(k, "") for k in ("descricao","movimento","emocao","serve_para","evitar")})
            n += 1
        flash(f"✓ {n} item(ns) no acervo")
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("acervo"))


@app.route("/acervo/<slug>/editar", methods=["POST"])
def acervo_editar(slug):
    check = {k: bool(request.form.get(f"chk_{k}")) for k, _ in _acervo.CHECKLIST}
    _acervo.atualizar(slug, {"titulo": request.form.get("titulo"), "tags": request.form.get("tags", ""),
                             "fonte": request.form.get("fonte"), "autor": request.form.get("autor"),
                             "licenca": request.form.get("licenca"), "observacao": request.form.get("observacao"),
                             "checklist": check, **{k:request.form.get(k, "") for k in ("descricao","movimento","emocao","serve_para","evitar")}})
    flash("✓ Atualizado")
    return redirect(url_for("acervo"))


@app.route("/acervo/<slug>/descrever", methods=["POST"])
def acervo_descrever(slug):
    _acervo.descrever(slug)
    flash("Descrevendo com IA — leva alguns segundos; recarregue a página.")
    return redirect(request.referrer or url_for("acervo"))


@app.route("/acervo/<slug>/remover", methods=["POST"])
def acervo_remover(slug):
    _acervo.remover(slug)
    flash("Removido do acervo")
    return redirect(url_for("acervo"))


# ───────────────────────── busca de b-roll (get-brolls) ─────────────────────────

@app.route("/broll", methods=["GET", "POST"])
def broll():
    env = gb_env()
    ctx = {"provedores": _gb.PROVEDORES, "pexels": bool(env.get("PEXELS_API_KEY")),
           "pixabay": bool(env.get("PIXABAY_API_KEY")), "resultado": None, "previa": None, "erro": None,
           "query": request.form.get("query", ""), "provider": request.form.get("provider", "youtube"),
           "checklist": _acervo.CHECKLIST}
    if request.method == "POST" and request.form.get("acao") == "buscar":
        q = request.form.get("query", "").strip()
        if q:
            r = _gb.buscar(request.form.get("provider", "youtube"), q, int(request.form.get("limit", 8) or 8),
                           request.form.get("intent", "literal"))
            ctx["resultado"] = r.get("items") or []
            ctx["erro"] = r.get("erro")
            ctx["resumo"] = r.get("summary")
    return render_template("broll.html", **ctx)


@app.route("/broll/previa", methods=["POST"])
def broll_previa():
    cand = request.form.get("candidate", "")
    ini = float(request.form.get("start", 0) or 0)
    fim = float(request.form.get("end", 5) or 5)
    r = _gb.previa(cand, ini, fim, request.form.get("reason", "prévia pelo Estúdio"))
    c = _gb.candidato(cand)
    return render_template("previa.html", r=r, c=c, cand=cand, ini=ini, fim=fim, checklist=_acervo.CHECKLIST,
                           erro=r.get("erro"))


@app.route("/broll/aprovar", methods=["POST"])
def broll_aprovar():
    cand = request.form.get("candidate", "")
    titulo = request.form.get("titulo", "").strip() or cand
    tags = request.form.get("tags", "")
    evid = request.form.get("evidence", "").strip() or "Aprovado pelo João no Estúdio após ver o contact sheet"
    check = {k: bool(request.form.get(f"chk_{k}")) for k, _ in _acervo.CHECKLIST}
    passos = []
    ini = request.form.get("start") or None
    fim = request.form.get("end") or None
    r1 = _gb.aprovar(cand, "João", ini, fim); passos.append(("approve", r1.get("summary") or r1.get("erro") or r1.get("error")))
    r2 = _gb.permitir(cand, evid); passos.append(("permit", r2.get("summary") or r2.get("erro") or r2.get("error")))
    r3 = _gb.coletar(cand); passos.append(("fetch", r3.get("summary") or r3.get("erro") or r3.get("error")))
    clip = _gb.caminho_clip(cand)
    if not clip:
        out = (r3.get("output") or {}).get("path") or (r3.get("files") or {}).get("clip")
        if out and Path(out).exists():
            clip = Path(out)
    if clip:
        c = _gb.candidato(cand) or {}
        meta = _acervo.adicionar_arquivo(clip, titulo, tags, fonte=c.get("source_url", ""),
                                         autor=((c.get("creator") or {}).get("name") or ""),
                                         licenca=evid, observacao=request.form.get("observacao", ""),
                                         origem_tipo=f"get-brolls:{c.get('provider')}", checklist=check,
                                         extra={"getbrolls_id": cand, "segmento": c.get("segment")})
        flash(f"✓ Guardado no acervo como {meta['slug']}")
        return redirect(url_for("acervo", q=meta["slug"]))
    flash("✗ Não achei o corte final. Passos: " + "; ".join(f"{k}: {v}" for k, v in passos))
    return redirect(url_for("broll"))


# ───────────────────────── configurações ─────────────────────────

@app.route("/config/limpar", methods=["POST"])
def config_limpar():
    import limpeza
    r = limpeza.limpar_tudo()
    flash(f"✓ Limpeza feita: {r}")
    return redirect(url_for("config"))


@app.route("/config", methods=["GET", "POST"])
def config():
    if request.method == "POST":
        from _comum import gravar_json
        if request.form.get('secao') == 'ia':
            cfg=ia.config()
            for k in ('provedor','modelo_claude','modelo_gpt','destino_mac','analises_simultaneas','renders_simultaneos'):
                cfg[k]=request.form.get(k, cfg.get(k,''))
            ia.aplicar_modelo(cfg, request.form.get('modelo'))   # escolher o modelo define o provedor
            cfg['esforco']=request.form.get('esforco') or cfg.get('esforco') or 'medium'
            cfg['ultra_mode']=cfg['esforco']=='max'
            if request.form.get('cobranca_enviada'): cfg['cobranca']='api' if request.form.get('cobrar_api') else 'assinatura'
            if request.form.get('cobranca_gpt_enviada'): cfg['cobranca_gpt']='api' if request.form.get('cobrar_api_gpt') else 'assinatura'
            if request.form.get('fila_cobranca_enviada'): cfg['fila_cobranca']='api' if request.form.get('fila_cobrar_api') else 'assinatura'
            try: cfg.setdefault('teto_usd_etapa',dict(ia.TETO_ETAPA))['analise']=max(0.0,float(request.form['teto_storyboard'].replace(',','.')))
            except (KeyError,ValueError): pass
            ia.validar(cfg)
            for c in clientes():
                field='destino_'+c['nome']
                if field in request.form:
                    v=request.form[field].strip()
                    if v: cfg.setdefault('destinos',{})[c['nome']]=v
                    else: cfg.setdefault('destinos',{}).pop(c['nome'],None)
            gravar_json(ia.CONFIG,cfg)
            flash('✓ Preferências salvas. As próximas etapas usarão '+ia.rotulo()+'.')
        if request.form.get('secao') == 'voz':
            import voz as _voz
            _voz.salvar(request.form.get('voz_padrao'), request.form.get('eleven_chave', ''),
                        request.form.get('eleven_voice_id'), voz_voicestudio=request.form.get('voz_voicestudio', ''))
            flash('✓ Voz salva.')
            return redirect(url_for("config") + "#voz")
        upd = {}
        for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
            v = request.form.get(k, "").strip()
            if v:
                upd[k] = v
        if upd:
            gb_env_gravar(upd)
            flash("✓ Chaves salvas em " + str(GB_ROOT / ".env"))
        return redirect(url_for("config"))
    env = gb_env()
    doc = _gb.doctor() if gb_instalado() and request.args.get("doctor") else None
    import voz as _voz, atualizar as _atu
    import custos as _cst, chaves as _chv, conexoes as _cx
    import voicestudio as _vs
    return render_template("config.html", vs_no_ar=_vs.no_ar(), vs_vozes=_vs.vozes(), cartoes_cobranca=_cst.onde_e_cobrado(ia.config()), conexoes=_cx.lista(), sem_chave=_cx.SEM_CHAVE, link_servico=_cx.LINK_POR_SERVICO, voz=_voz.status(), atualizacoes=_atu.estado(), repositorios=__import__("repositorios").cartoes(), regra_motor=__import__("repositorios").REGRA_MOTOR, lixeira=_nc.lixeira(), esforcos=__import__("ia").ESFORCOS, grupos_modelo=ia.opcoes_modelo_enxuto(), **__import__('novo_rotas').forcas_config(ia), agora=ia.agora(), cob=ia.estado_cobranca(), chaves_final={p: _chv.final(p) for p in _chv.ARQUIVOS}, inventario=_chv.inventario(), cfg=ia.config(), codex=ia.codex_bin(), clientes=clientes(), env=env, gb_root=GB_ROOT, doc=doc, claude=claude_bin(),
                           destinos=(_prod.config().get("destinos") or {}),
                           acervo=ACERVO, gb_project=GB_PROJECT)


@app.route("/config/voz/verificar", methods=["POST"])
def voz_verificar():
    import voz as _voz
    try:
        flash("✓ " + _voz.verificar())
    except Exception as e:
        flash(f"✗ {e}")
    return redirect(url_for("config") + "#voz")


@app.route("/config/voz/clonar", methods=["POST"])
def voz_clonar():
    import voz as _voz
    arquivos = []
    for f in request.files.getlist("audios"):
        if f and f.filename:
            p = UPLOADS / f"{_prod.now_slug()}-{Path(f.filename).name}"
            f.save(str(p)); arquivos.append(p)
    try:
        vid = _voz.clonar(request.form.get("nome", "").strip(), arquivos)
        flash(f"✓ Voz clonada e escolhida como padrão (ID {vid}).")
    except Exception as e:
        flash(f"✗ {e}")
    finally:
        for p in arquivos:
            p.unlink(missing_ok=True)
    return redirect(url_for("config") + "#voz")


@app.route("/config/atualizar", methods=["POST"])
def atualizar_agora():
    import atualizar as _atu
    _atu.disparar()
    flash("✓ Conferência de atualizações iniciada. O resultado aparece aqui em alguns minutos.")
    return redirect(url_for("config") + "#atualizacoes")


@app.route("/config/atualizar/item", methods=["POST"])
def atualizar_item():
    import atualizar as _atu
    msg = _atu.disparar_item(request.form.get("nome", ""))
    flash(("✓ " if msg.startswith("Atualizando") else "") + msg)
    return redirect(url_for("config") + "#atualizacoes")


from v2 import register
register(app)
from broll_studio import register as register_brolls
register_brolls(app)
from simples import register as register_simples
register_simples(app)
from aprendizado_rotas import register as register_aprendizado
register_aprendizado(app)
from musica_rotas import register as register_musica
register_musica(app)
from chaves_rotas import register as register_chaves
register_chaves(app)
from briefing_rotas import register as register_briefing
register_briefing(app)
from andamento_rotas import register as register_andamento
register_andamento(app)
from saidas_rotas import register as register_saidas
register_saidas(app)
from conversa_rotas import register as register_conversa
register_conversa(app)
from camada_rotas import register as register_camada
register_camada(app)
from corte_rotas import register as register_corte
register_corte(app)
from estilo_rotas import register as register_estilo
register_estilo(app)
from editor_rotas import register as register_editor
register_editor(app)
from espaco_rotas import register as register_espaco
register_espaco(app)
from vozes_rotas import register as register_vozes
register_vozes(app)
from emocao_rotas import register as register_emocao
register_emocao(app)
from estudos_rotas import register as register_estudos
register_estudos(app)
from novo_rotas import register as register_novo
register_novo(app)
from elenco_rotas import register as register_elenco
register_elenco(app)
from aprendi_rotas import register as register_aprendi
register_aprendi(app)
from revisao_rotas import register as register_revisao
register_revisao(app)

if __name__ == "__main__":
    if any(x["estado"] in ("na_fila","rodando") for x in fila.ler()): fila.iniciar()
    _recarregar.cancelar()   # pedido de recarga de antes de subir: este servidor JÁ é o novo
    import threading, recarregar as _rec_vigia   # "Recarregar agora" pedido com vídeo rodando: reinicia sozinho quando acabar
    threading.Thread(target=_rec_vigia.vigiar, daemon=True, name="recarregar-vigia").start()
    import atualizar as _atu_vigia   # confere atualização 1x por dia ao abrir e toca a fila (sem travar a tela)
    threading.Thread(target=_atu_vigia.vigiar, daemon=True, name="atualizar-vigia").start()
    print(f"ESTÚDIO · http://localhost:{PORTA}  (raiz: {RAIZ})")
    app.run(host="127.0.0.1", port=PORTA, debug=False, threaded=True)
