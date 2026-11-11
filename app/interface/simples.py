"""Telas do Estúdio 03 (simples): Início, Criar vídeo, Formatos, Meus vídeos, Clientes, Custos."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import time
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from _comum import RAIZ, ESTUDIO, CACHE, IMAGEM_EXTS, VIDEO_EXTS, clientes, cliente as _cliente, ensure, thumb
import producao as _prod
import formatos as _fmt
import custos as _custos
import corte as _cortes
import corte_manual as _manual
import edicao
import conversa as _conv
import pastas as _pastas
import saidas as _saidas
import json as _json
from _comum import agora, ffprobe, gravar_json, ler_json, rel

UPLOADS = ensure(ESTUDIO / ".uploads")
ESPERANDO = ('plano', 'plano_aprovado', 'concluido', 'aprovado', 'erro', 'interrompido')
ACAO = {'plano': 'Aprovar o storyboard', 'plano_aprovado': 'Gerar prévias', 'concluido': 'Assistir e aprovar',
        'aprovado': 'Finalizar', 'erro': 'Ver o que houve', 'interrompido': 'Retomar'}


AUDIO_VOZ_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}


def _audio_para_video(arq):
    """Áudio solto (MP3...) vira um .mp4 com quadro preto 1080x1920 + o áudio: o resto do Estúdio só entende "vídeo gravado"."""
    arq = Path(arq)
    if arq.suffix.lower() not in AUDIO_VOZ_EXTS:
        return arq
    saida = arq.with_suffix(".mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30", "-i", str(arq), "-shortest",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(saida)],
                   check=True, capture_output=True)
    return saida


def _salvar_upload(f) -> Path:
    destino = UPLOADS / f"{_prod.now_slug()}-{Path(f.filename).name}"
    f.save(str(destino))
    return destino


def _baixar_link(url: str) -> Path:
    """Link de vídeo (Instagram, YouTube...) → arquivo na pasta de uploads, com yt-dlp. Erro vira mensagem pro João."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("O link do vídeo precisa começar com http.")
    modelo = str(UPLOADS / f"{_prod.now_slug()}-link.%(ext)s")
    r = subprocess.run(["yt-dlp", "-f", "mp4/best", "--no-playlist", "-o", modelo, "--print", "after_move:filepath", url],
                       capture_output=True, text=True, timeout=300)
    saida = (r.stdout or "").strip().splitlines()
    if r.returncode or not saida or not Path(saida[-1]).is_file():
        raise ValueError("Não consegui baixar esse link. Baixe o vídeo e envie o arquivo.")
    return Path(saida[-1])


def _cenas_da_chip(valor: str, quantidade: int | None = None) -> dict | None:
    """Chip "Cenas de apoio" da tela Criar → broll_config. Nada marcado: None (fica o padrão do job).
    `quantidade`: o teto que o formato declara (formatos.quantidade_cenas); sem ele, 3. Com ele, "do_formato": os
    intervalos seguem os passos do formato (a Tela dividida tem cena embaixo o tempo todo, não "mantém o bruto")."""
    v = (valor or "").lower()
    if not v.strip():
        return None
    if "sem cena" in v or v.strip() in ("sem", "nenhuma"):
        return {"origem": "nenhum", "quantidade": 0}
    real = "real" in v or "b-roll" in v or "banco" in v
    ia = bool(re.search(r"\bia\b", v)) or "gerada" in v
    extra = {"do_formato": True} if quantidade else {}
    q = quantidade or _fmt.QUANTIDADE_CENAS
    if "duas" in v or "ambas" in v or (real and ia):
        return {"origem": "misto", "quantidade": q, **extra}
    if ia:
        return {"origem": "ia", "quantidade": q, **extra}
    if real:
        return {"origem": "busca", "quantidade": q, **extra}
    return None


def _enfeitar(j: dict) -> dict:
    f = _fmt.de_modelo(j.get("modelo", ""))
    j["formato_titulo"] = f["titulo"] if f else j.get("modelo", "")
    j["acao"] = ACAO.get(j.get("status"), "Abrir")
    return j


def _titulo_regra(r: dict) -> str:
    """Na tela, a regra aparece pelo título (curto, sem termo técnico); sem título, o começo do texto."""
    return (r.get("titulo") or r.get("texto") or "")[:180]


# ───────────────────────── passo 0: Conversar (briefing em conversa) ─────────────────────────

ENTRADAS_CONVERSA = ("video", "roteiro", "filmagem", "cortar")


def _chips_pastas(cliente: str) -> list[dict]:
    return [{"nome": p["nome"], "tipo": p.get("tipo"), "nivel": p.get("nivel")} for p in _pastas.para_escolher(cliente)]


def _pastas_da_conversa(bid: str) -> dict:
    """Pastas que valem pra esta conversa (as do cliente + as marcadas), por nome em minúsculas."""
    est, b = _conv.estado(bid), _conv.briefing(bid)
    ativ = _pastas.ativas(b.get("cliente") or est.get("cliente", ""), est.get("pastas") or [])
    return {p["nome"].lower(): p for p in ativ["pastas"]}


def _texto_do_briefing(b: dict) -> str:
    """O briefing fechado em texto corrido pro campo 'O que você quer ver' do Criar (o João ainda pode editar)."""
    linhas = [b.get("objetivo") or ""]
    if b.get("peculiaridade"):
        linhas.append("Deste vídeo: " + b["peculiaridade"])
    if b.get("proibido"):
        linhas.append("Não usar: " + "; ".join(b["proibido"]))
    if b.get("perguntas_abertas"):
        linhas.append("Ainda em aberto: " + "; ".join(b["perguntas_abertas"]))
    return "\n".join(x for x in linhas if x).strip()


def _url_pasta(bid: str, pasta: str, arquivo: str, video: bool = False) -> str:
    return url_for("conversar_arquivo", bid=bid, pasta=pasta, arquivo=arquivo, **({"video": 1} if video else {}))


def _ref_do_briefing(bid: str, r: dict, ativas: dict) -> dict | None:
    """referencia.video do briefing: link, 'Pasta/arquivo' de pasta ligada ou caminho do Estúdio (referência do formato)."""
    v = (r.get("video") or "").strip()
    extra = {"segundo": r.get("segundo"), "copiar": r.get("o_que_copiar") or "", "layout": r.get("layout") or ""}
    if v.startswith(("http://", "https://")):
        return {"link": v, **extra}
    pasta, _, arq = v.partition("/")
    if v and pasta.lower() in ativas:
        nome = ativas[pasta.lower()]["nome"]
        return {"pasta": nome, "rel": arq, "nome": Path(arq).name, "video": _url_pasta(bid, nome, arq, True),
                "poster": _url_pasta(bid, nome, arq), **extra}
    alvo = (RAIZ / v).resolve() if v else None
    if alvo and RAIZ.resolve() in alvo.parents and alvo.is_file():
        return {"pasta": "", "rel": v, "nome": alvo.stem, "video": url_for("arquivo", caminho=v),
                "poster": url_for("thumb_rota", caminho=v), **extra}
    return {"copiar": extra["copiar"], "layout": extra["layout"]} if extra["copiar"] or extra["layout"] else None


def _pre_criar(bid: str) -> dict:
    """O que o Criar abre preenchido a partir do briefing da conversa."""
    b = _conv.briefing(bid)
    ativas = _pastas_da_conversa(bid)
    slug = (b.get("formato_sugerido") or {}).get("slug") or ""
    entrada = b.get("entrada") if b.get("entrada") in ENTRADAS_CONVERSA else ""
    if entrada == "cortar":
        slug = "so-cortar"
    f = _fmt.carregar(slug) if slug and slug != "so-cortar" else None
    if slug and slug != "so-cortar" and not f:
        slug = ""
    if f:   # o formato manda no tipo de entrada; "vídeo ou roteiro" respeita o que a conversa decidiu
        fe = f.get("entrada")
        if fe == "video-ou-roteiro":
            entrada = entrada if entrada in ("video", "roteiro") else ("roteiro" if b.get("roteiro") else "video")
        elif fe:
            entrada = fe
    nomes = {c["nome"].lower(): c["nome"] for c in clientes()}
    nomes.setdefault(_fmt.AVULSO.lower(), _fmt.AVULSO)
    mats = []
    for i, m in enumerate(b.get("material_liberado") or []):
        p = ativas.get((m.get("pasta") or "").lower())
        mats.append({"i": i, "nome": Path(m["arquivo"]).name, "pasta": m.get("pasta", ""), "papel": m.get("papel", ""),
                     "onde": m.get("onde", ""), "mini": _url_pasta(bid, p["nome"], m["arquivo"]) if p else "", "ok": bool(p)})
    return {"id": bid, "formato": slug, "cliente": nomes.get((b.get("cliente") or "").lower(), ""), "entrada": entrada,
            "roteiro": b.get("roteiro") or "", "texto": _texto_do_briefing(b), "material": mats,
            "ref": _ref_do_briefing(bid, b.get("referencia") or {}, ativas), "descartavel": bool(b.get("descartavel")),
            "avisos": _conv.avisos_material(b)}


def _seg(v) -> str:
    try:
        return f"{float(v):.1f}".replace(".", ",") + " s"
    except (TypeError, ValueError):
        return ""


def _aplicar_conversa(job: dict, form) -> list[str]:
    """Depois de criar o job: copia o material liberado e a referência marcada pro material/ (pastas.usar, com hash e
    usos.json; o original só é lido) e escreve no briefing do job o que entra onde. Devolve o que não deu pra copiar."""
    bid = (form.get("conversa") or "").strip()
    linhas, erros = [], []
    material = _prod.RAIZ / job["sandbox"] / "material"
    ativas = {}
    if bid:
        b = _conv.briefing(bid)
        ativas = _pastas_da_conversa(bid)
        job["conversa"] = bid
        job["briefing_conversa"] = b
        if job.get("legenda") is False:
            b["legenda"] = False   # o briefing que a esteira lê diz o mesmo que o job
        marcados = set(form.getlist("mat_conversa"))
        for i, m in enumerate(b.get("material_liberado") or []):
            if str(i) not in marcados:
                continue
            p = ativas.get((m.get("pasta") or "").lower())
            try:
                if not p:
                    raise ValueError("a pasta não está ligada a este vídeo")
                u = _pastas.usar(p, m["arquivo"], material, onde=m.get("onde") or m.get("papel") or "", cliente=job["cliente"])
            except ValueError as e:
                erros.append(f"{Path(m['arquivo']).name}: {e}")
                continue
            job.setdefault("materiais", []).append(f"material/{u['nome']}")
            linhas.append(f"- material/{u['nome']} → {m.get('papel') or 'onde couber'}" + (f" ({m['onde']})" if m.get("onde") else ""))
    ref, ref_pasta = (form.get("ref") or "").strip(), (form.get("ref_pasta") or "").strip()
    copiar, seg = (form.get("ref_copiar") or "").strip(), _seg(form.get("segundo"))
    onde_ref = ""
    if ref and ref_pasta:
        p = ativas.get(ref_pasta.lower())
        try:
            if not p:
                raise ValueError("a pasta não está ligada a este vídeo")
            u = _pastas.usar(p, ref, material, onde="referência", cliente=job["cliente"])
            job.setdefault("materiais", []).append(f"material/{u['nome']}")
            onde_ref = f"material/{u['nome']}"
        except ValueError as e:
            erros.append(f"{Path(ref).name}: {e}")
    elif ref:
        alvo = (_prod.RAIZ / ref).resolve()
        if _prod.RAIZ.resolve() in alvo.parents and alvo.is_file():
            onde_ref = ref
    if onde_ref:
        linhas.append(f"REFERÊNCIA DESTE VÍDEO: {onde_ref}" + (f", no segundo {seg}" if seg else "")
                      + (f". Estilo a aproveitar: {copiar}" if copiar else "")
                      + ". Siga o formato; da referência só o estilo (ritmo, enquadramento, legenda, clima), nunca roteiro, textos, pessoas ou cores. Extraia quadros dela antes de planejar.")
    if form.get("descartavel") == "1":
        job["descartavel"] = True
    if linhas:
        cab = "DO BRIEFING DA CONVERSA (vale só pra este vídeo, não vira regra):" if bid else ""
        job["briefing"] = "\n\n".join(x for x in [job.get("briefing", ""), "\n".join(([cab] if cab else []) + linhas)] if x)
    if linhas or bid or job.get("descartavel"):
        (_prod.RAIZ / job["sandbox"] / "BRIEF.md").write_text(_prod.brief_md(job), encoding="utf-8")
        _prod.salvar(job)
    return erros


def lugar(j: dict, andam: dict) -> str:
    """Em que tela o vídeo mora (nunca em duas): 'andamento' (em produção, esperando você ou pronto sem aprovar, com cartão na aba),
    'videos' (pronto e aprovado, ou exportado) ou 'producao' (job em produção sem cartão na aba: rede de segurança em Meus vídeos).
    andam: o que a aba Em andamento mostra agora, por 'Cliente/slug'."""
    st = j.get("status")
    if st in ("aprovado", "exportado", "arquivado"):
        return "videos"
    if f"{j['cliente']}/{j['slug']}" in andam:
        return "andamento"
    return "videos" if st == "concluido" else "producao"


def quadro() -> tuple[list[dict], dict]:
    """(jobs enfeitados, andamento visível por id), já com os jobs presos consertados."""
    import andamento as _and
    _prod.reconciliar()
    jobs = [_enfeitar(j) for j in _prod.listar() if j.get("status") != "arquivado"]
    return jobs, {d["id"]: d for d in _and.listar()}


ESPERA_ANDAMENTO = {"esperando": "Aprovar o storyboard", "pronto": "Ficou bom?", "erro": "Ver o que houve"}


def esperando_lista(jobs: list[dict], andam: dict) -> list[dict]:
    """Só o que de fato espera o João, um item por vídeo: storyboard pendente, 'Ficou bom?', erro, ou job parado esperando ação."""
    itens = []
    for d in andam.values():
        if d.get("estado") in ESPERA_ANDAMENTO:
            itens.append({"cliente": d["cliente"], "slug": d["slug"], "titulo": d["titulo"], "formato_titulo": d.get("formato_titulo", ""),
                          "saida": d.get("video", ""), "acao": ESPERA_ANDAMENTO[d["estado"]], "andamento": True})
    for j in jobs:
        if f"{j['cliente']}/{j['slug']}" not in andam and not j.get("rodando") and j.get("status") in ESPERANDO:
            itens.append({**j, "andamento": False})
    return itens


def register(app):
    @app.context_processor
    def _contagem():
        try:
            import andamento as _and
            import lotes as _lotes
            n = len(_lotes.esperando())   # mesma conta da tela /aprovar
        except Exception:
            n = 0
        try:
            import atualizar as _atu
            na = _atu.quantas_disponiveis()   # lê só o arquivo do último resultado (sem rede): selo discreto no menu
        except Exception:
            na = 0
        return {"n_esperando": n, "n_atualizacoes": na}

    @app.route("/", endpoint="home")
    def inicio():
        jobs, vis = quadro()
        import lotes as _lotes
        esperando = []   # UMA conta só: a mesma de /aprovar e do selo do menu (lotes.esperando)
        for i in _lotes.esperando():
            if i["tipo"] in ("storyboard", "video"):
                esperando.append({"cliente": i["cliente"], "slug": i["slug"], "titulo": i["titulo"], "formato_titulo": i["estilo"],
                                  "saida": i["video"], "andamento": True, "url": "",
                                  "acao": ESPERA_ANDAMENTO["esperando" if i["tipo"] == "storyboard" else "pronto"]
                                  + (f" · {i['n_versoes']} versões" if i.get("n_versoes", 1) > 1 else "") + (" · feito pelo chat" if i.get("chat") else "")})
            else:
                esperando.append({"cliente": "", "slug": "", "titulo": i.get("titulo", ""), "formato_titulo": i.get("sub", ""), "saida": "",
                                  "andamento": False, "url": i.get("url", ""), "acao": i.get("botao", "Ver")})
        rodando = [j for j in jobs if (j.get("rodando") or j.get("status") in ("na_fila", "analisando", "renderizando", "previas", "feedback", "rodando"))
                   and f"{j['cliente']}/{j['slug']}" not in vis]   # quem tem cartão em Em andamento não repete aqui
        andam = [d for d in vis.values() if d.get("estado") == "trabalhando"]   # esperando e pronto já estão em "Esperando você"
        com_exemplo = [f for f in _fmt.listar() if f["exemplos"]]
        prontos = [f for f in com_exemplo if f.get("na_tela") and f.get("status") == "pronto"]   # só o que roda pela tela
        fmts = (prontos or com_exemplo)[:8]
        n_esperando = len(esperando)   # a mesma lista: Início, selo do menu e /aprovar nunca discordam
        return render_template("inicio.html", esperando=esperando, rodando=rodando, andamento=andam, recentes=jobs[:8], formatos=fmts,
                               n_esperando=n_esperando)

    @app.route("/formatos")
    def formatos_lista():
        return render_template("formatos.html", formatos=_fmt.listar(), entradas=_fmt.ENTRADAS, catalogo=_fmt.catalogo(),
                               ocultos=_fmt.ocultos(), usados=_fmt.estilos_do_cliente(request.args.get("cliente", "")))

    def _storyboard(slug, ref=""):
        """A tira 'Momento a momento' (todos os planos + resumo por tipo): {estado, quadros, resumo, total, ...}. O que falta
        (estudo leve, quadro do meio, OCR) é feito em segundo plano; a tela pergunta de novo até ficar 'pronto'."""
        import storyboard_estilo as _sb
        try:
            r = _sb.tira(slug, ref)
        except Exception:  # noqa: BLE001   sem ffmpeg ou vídeo ruim: a página vive sem a tira
            return {"estado": "sem", "quadros": []}
        rid = r.get("ref_id", "")
        for q in r.get("quadros") or []:
            q["url"] = url_for("storyboard_quadro_ref", slug=slug, ref=rid, nome=q["arquivo"])
        if r.get("resumo"):
            for t in r["resumo"].get("tipos") or []:
                t["url"] = url_for("storyboard_quadro_ref", slug=slug, ref=rid, nome=t["exemplo"]) if t.get("exemplo") else ""
        return r

    def _tem_storyboard(slug):
        import storyboard_estilo as _sb
        try:
            return bool(_sb.fonte(slug))
        except Exception:  # noqa: BLE001
            return False

    @app.route("/formato/<slug>")
    def formato_detalhe(slug):
        f = _fmt.carregar(slug)
        if not f:
            abort(404)
        import elenco as _el   # Explicador 3D: o elenco do estilo em miniaturas
        import frase_estilo as _fe
        refs = _fmt.estudos(slug)
        for e in refs:   # uma frase por referência (o que ela ensina); os números ficam em "Ver detalhes"
            e["frase"] = _fe.da_pasta(_fmt.FORMATOS / slug / "estudos" / e["nome"])
        import melhoria as _mel   # as melhorias do motor deste estilo: abertas (Ver/Aplicar) e o histórico (Desfazer)
        mels = [dict(m, titulo_curto=((m.get("achados") or [{}])[0].get("o_que") or m.get("titulo") or "Melhoria")[:160])
                for m in _mel.listar() if m.get("formato") == slug]
        return render_template("formato.html", f=f, apr=_fmt.aprendizado(slug), prev=_fmt.previsao(slug), melhorias=mels,
                               estudos=refs, passos=_fmt.passos(f), storyboard=_tem_storyboard(slug),
                               elenco=_el.ler(slug) if _el.existe(slug) else None, rotulos=_el.rotulos(slug) if _el.existe(slug) else {},
                               previa=_el.previa(slug) if _el.existe(slug) else {})

    @app.route("/api/storyboard/<slug>")
    def api_storyboard(slug):
        ref = request.args.get("ref", "")
        if ref and not re.fullmatch(r"[a-z0-9-]+", ref):
            ref = ""
        return jsonify(_storyboard(slug, ref))

    @app.route("/storyboard/<slug>/<nome>")
    @app.route("/storyboard/<slug>/<ref>/<nome>", endpoint="storyboard_quadro_ref")
    def storyboard_quadro(slug, nome, ref=""):
        import storyboard_estilo as _sb
        p = _sb.caminho(slug, nome, ref)
        if not p:
            abort(404)
        r = send_file(p, mimetype="image/jpeg")
        r.headers["Cache-Control"] = "public, max-age=86400"
        return r

    @app.route("/formato/<slug>/remover", methods=["POST"])
    def formato_remover(slug):
        import remover as _rm
        try:
            _rm.remover_estilo(slug)
        except ValueError as e:
            flash("✗ " + str(e))
            return redirect(url_for("formato_detalhe", slug=slug))
        flash(f"✓ O estilo saiu do catálogo e foi pra lixeira. Volta em Configurações → Lixeira → Restaurar.")
        return redirect(url_for("formatos_lista"))

    @app.route("/formato/<slug>/estilo/<nome>", methods=["POST"])
    def formato_estilo(slug, nome):
        flash("✓ Novo estilo principal: " + nome if _fmt.definir_principal(slug, nome) else "✗ Referência não encontrada.")
        return redirect(url_for("formato_detalhe", slug=slug) + "#estudos")

    @app.route("/videos/<cli>/<slug>/virar-referencia", methods=["GET", "POST"])
    def job_virar_referencia(cli, slug):
        """Vídeo nosso vira referência do estilo. Aprovou? Primeiro mostra onde vai parar; só guarda no 2º clique (confirmar=1)."""
        job = _prod.carregar(cli, slug)
        if not job or not job.get("saida") or not job.get("formato") or not (_prod.RAIZ / job["saida"]).is_file():
            flash("✗ Este vídeo ainda não tem o arquivo final nem estilo; guarde pela tela Saídas.")
            return redirect(url_for("andamento_ver", cli=cli, slug=slug))
        if request.method == "GET" or request.form.get("confirmar") != "1":
            from _comum import make_slug
            f = _fmt.carregar(job["formato"]) or {}
            base = _fmt.FORMATOS / job["formato"] / "estudos"
            n = len([d for d in base.iterdir() if d.is_dir()]) + 1 if base.is_dir() else 1
            return render_template("confirmar_referencia.html", j=job, estilo=f.get("titulo") or job["formato"],
                                   destino=f"formatos/{job['formato']}/estudos/{n:02d}-{make_slug(job.get('titulo') or slug, 40)}/")
        d = _fmt.virar_referencia(job["formato"], _prod.RAIZ / job["saida"], job.get("titulo") or slug, origem=job["saida"])
        flash(f"✓ Guardado como referência do estilo ({d.name}). Escolha ele no Criar, em \"Qual referência seguir\".")
        volta = request.form.get("volta", "")   # veio da página do vídeo ("Aprovado — e agora?")
        return redirect(volta if volta.startswith("/andamento/") else url_for("job", cli=cli, slug=slug))

    @app.route("/formato/<slug>/referencia", methods=["POST"])
    def formato_referencia(slug):
        if not _fmt.carregar(slug):
            abort(404)
        arquivos = [_salvar_upload(f) for f in request.files.getlist("videos") if f and f.filename]
        links = [l.strip() for l in request.form.get("links", "").splitlines() if l.strip().startswith("http")]
        if not arquivos and not links:
            flash("✗ Mande um vídeo ou um link.")
            return redirect(url_for("formato_detalhe", slug=slug) + "#estudos")
        import threading
        threading.Thread(target=_fmt.adicionar_referencia, args=(slug, arquivos, links, request.form.get("nome", "")),
                         daemon=True).start()
        flash("✓ Referência entrando no formato. Em um minuto o storyboard aparece aqui.")
        return redirect(url_for("formato_detalhe", slug=slug) + "#estudos")

    @app.route("/api/formato/<slug>")
    def api_formato(slug):
        f = _fmt.carregar(slug)
        if not f:
            abort(404)
        a = _fmt.aprendizado(slug, request.args.get("cliente", ""))
        return jsonify(titulo=f["titulo"], usa=_fmt.previsao(slug)["usa"], escolhas=_fmt.escolhas(f),
                       n_formato=len(a["formato"]), n_cliente=len(a["cliente"]), cliente=a["cliente_nome"],
                       regras_cliente=[_titulo_regra(r) for r in a["cliente"][:4]],
                       regras_formato=[_titulo_regra(r) for r in a["formato"][:4]], legenda=_fmt.legenda_do(f))

    @app.route("/conversar")
    def conversar():
        """Passo 0 (opcional): conversa com a IA que olha as pastas ligadas e monta o briefing."""
        bid = request.args.get("id", "")
        conv = None
        if bid:
            try:
                conv = _conv.ver(bid)
            except ValueError:
                flash("✗ Conversa não encontrada.")
                return redirect(url_for("conversar"))
            if conv["estado"].get("fechado"):
                return redirect(url_for("novo_tela", briefing=bid))
        cliente = conv["briefing"].get("cliente", "") if conv else request.args.get("cliente", "")
        cls = [c["nome"] for c in clientes() if c["nome"] != _fmt.AVULSO]
        fmts = [{"slug": f["slug"], "titulo": f["titulo"]} for f in _fmt.listar() if f["slug"] != "so-cortar"]
        abertas = [c for c in _conv.listar() if not c["fechado"] and c["id"] != bid][:3]
        dados = {"conversa": conv, "cliente": cliente, "formato": request.args.get("formato", ""),
                 "modelo": conv["estado"].get("modelo") if conv else _conv.PADRAO, "tetos": _conv.TETOS,
                 "pastas": _chips_pastas(cliente), "avulso": _fmt.AVULSO}
        return render_template("briefing.html", dados=dados, clientes=cls, formatos=fmts, abertas=abertas,
                               cliente=cliente, formato=dados["formato"])

    @app.get("/conversar/pastas")
    def conversar_pastas():
        return jsonify(_chips_pastas(request.args.get("cliente", "")))

    @app.post("/conversar/ligar")
    def conversar_ligar():
        """＋ Ligar pasta: caminho colado ou, sem caminho, o seletor do Finder. Só registra; nada é gravado na pasta."""
        d = request.get_json(silent=True) or request.form.to_dict()
        cliente = (d.get("cliente") or "").strip()
        caminho = (d.get("caminho") or "").strip() or _pastas.escolher_no_finder()
        if not caminho:
            return jsonify(erro="Nenhuma pasta escolhida."), 400
        try:
            p = _pastas.ligar(caminho, nome=d.get("nome", ""), tipo=d.get("tipo") or "outro",
                              cliente=cliente if d.get("tipo") == "cliente" else "")
        except ValueError as e:
            return jsonify(erro=str(e)), 400
        return jsonify(pasta={"nome": p["nome"], "tipo": p.get("tipo")}, pastas=_chips_pastas(cliente),
                       tem_manifesto=_pastas.ler_manifesto(p["caminho"])["existe"])

    @app.get("/conversar/achar")
    def conversar_achar():
        """＋ Ligar pasta pelo nome ('marca3'): só procura nas raízes permitidas (pastas.raizes_busca)."""
        return jsonify(_pastas.achar(request.args.get("q", "")))

    @app.post("/conversar/manifesto/propor")
    def conversar_manifesto_propor():
        """Rascunho local do ESTUDIO.md de uma pasta já ligada. Não grava nada."""
        p = _pastas.pegar((request.get_json(silent=True) or {}).get("nome", ""))
        if not p:
            return jsonify(erro="Essa pasta não está ligada."), 400
        try:
            r = _pastas.propor_manifesto(p["caminho"])
        except ValueError as e:
            return jsonify(erro=str(e)), 400
        return jsonify(texto=r["texto"], existe=r["existe"], arquivo=r["arquivo"])

    @app.post("/conversar/manifesto/gravar")
    def conversar_manifesto_gravar():
        """Só grava o ESTUDIO.md dentro da pasta do João com o OK dele (aprovado=true, vindo do botão da tela)."""
        d = request.get_json(silent=True) or {}
        p = _pastas.pegar(d.get("nome", ""))
        if not p:
            return jsonify(erro="Essa pasta não está ligada."), 400
        try:
            _pastas.gravar_manifesto(p["caminho"], d.get("texto", ""), aprovado=d.get("aprovado") is True)
        except ValueError as e:
            return jsonify(erro=str(e)), 400
        return jsonify(ok=True)

    @app.get("/conversar/<bid>/arquivo")
    def conversar_arquivo(bid):
        """Miniatura (ou o próprio vídeo, com ?video=1) de um arquivo de pasta ligada A ESTA conversa. Travado nelas."""
        try:
            p = _pastas_da_conversa(bid).get(request.args.get("pasta", "").lower())
            arq = _pastas.resolver(p, request.args.get("arquivo", "")) if p else None
        except ValueError:
            arq = None
        tipo = _pastas.TIPO_DA_EXT.get(arq.suffix.lower()) if arq else None
        if tipo not in ("imagem", "video"):
            abort(404)
        if request.args.get("video") and tipo == "video":
            return send_file(str(arq), conditional=True)
        h = hashlib.sha1(f"{arq}|{arq.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        t = thumb(arq, CACHE / "conversa" / f"tela-{h}.jpg", t=1.0, largura=360)
        if not t:
            abort(404)
        return send_file(str(t), conditional=True)

    @app.get("/api/referencias/<formato>")
    def api_referencias(formato):
        """Vídeos de referência do formato pro seletor (o mesmo do 'Quero alterar')."""
        import andamento as _and
        return jsonify([{"video": url_for("arquivo", caminho=r["video"]), "rel": r["video"], "pasta": "",
                         "nome": r["nome"] + (" · principal" if r.get("principal") else ""),
                         "poster": url_for("arquivo", caminho=r["poster"]) if r.get("poster")
                         else url_for("thumb_rota", caminho=r["video"])} for r in _and.referencias(formato)])

    @app.get("/api/aviso-layout")
    def api_aviso_layout():
        """A referência pede um layout que o formato não sabe montar? A frase pro João (vazia se cabe)."""
        a = _fmt.aviso_layout({"o_que_copiar": request.args.get("copiar", ""), "layout": request.args.get("layout", "")},
                            request.args.get("formato", ""))
        return jsonify({"aviso": a["aviso"] if a else "", "layout": a["layout"] if a else ""})

    @app.route("/criar", methods=["GET", "POST"])
    def criar():
        cls = [c for c in clientes() if c["nome"] != _fmt.AVULSO]
        if request.method == "GET":
            pre = None
            if request.args.get("briefing"):
                try:
                    pre = _pre_criar(request.args["briefing"])
                except ValueError:
                    flash("✗ Briefing não encontrado.")
            import voicestudio as _vs
            vc = {c["nome"]: ((ler_json(c["pasta"] / "identidade.json", {}) or {}).get("voz") or {}).get("id", "") for c in cls}
            import ia as _ia
            ia_modelos = [("", "Modelo de Configurações")] + [(m, "Claude " + _ia.nome_claude(m)) for m in ("sonnet", "opus", "haiku")]
            ia_esforcos = [("", "Esforço de Configurações")] + [(v, r.split(" — ")[0]) for v, r in _ia.ESFORCOS]
            refs = {f["slug"]: _fmt.estudos(f["slug"]) for f in _fmt.listar() if (f["pasta"] / "estudos").is_dir()}
            return render_template("criar.html", formatos=_fmt.listar(), catalogo=_fmt.catalogo(), clientes=cls, entradas=_fmt.ENTRADAS, pre=pre,
                                   refs={k: v for k, v in refs.items() if len(v) > 1}, ia_modelos=ia_modelos, ia_esforcos=ia_esforcos,
                                   vozes=_vs.vozes(), voz_cliente=vc,
                                   pre_formato=pre["formato"] if pre else request.args.get("formato", ""),
                                   pre_cliente=pre["cliente"] if pre else request.args.get("cliente", ""))
        slug = request.form.get("formato", "")
        quem = request.form.get("cliente", "") or _fmt.AVULSO
        titulo = request.form.get("titulo", "").strip()
        briefing = request.form.get("briefing", "").strip()
        roteiro = request.form.get("roteiro", "").strip()
        arquivos = [f for f in request.files.getlist("videos") if f and f.filename]
        meu_audio = [f for f in request.files.getlist("audio_narracao") if f and f.filename] if request.form.get("voz") == "meu-audio" else []
        arquivos += meu_audio   # "Meu áudio (MP3 ou MP4)" da voz da narração: vira a fala gravada (só a voz) e as cenas vão por cima
        fmt_escolhido = _fmt.carregar(slug) or {}
        fotos = []   # evento: fotos (e a logo) entram junto dos vídeos e viram material próprio do vídeo
        if fmt_escolhido.get("entrada") == "filmagem":
            fotos = [f for f in arquivos if Path(f.filename).suffix.lower() in IMAGEM_EXTS]
            arquivos = [f for f in arquivos if f not in fotos]
        for f in arquivos:
            if Path(f.filename).suffix.lower() not in VIDEO_EXTS | (AUDIO_VOZ_EXTS if f in meu_audio else set()):
                flash(f"✗ Esse arquivo não é vídeo: {f.filename}")
                return redirect(url_for("novo_tela", estilo=slug, cliente=quem))
        try:
            if slug == "so-cortar":
                if not arquivos:
                    raise ValueError("Envie o vídeo que você quer cortar.")
                c = _cortes.avulso_criar(_salvar_upload(arquivos[0]), titulo)
                _cortes.avulso_montar(c["slug"], briefing, roteiro=roteiro)
                return redirect(url_for("corte_detalhe", slug=c["slug"]))
            link_principal = any(request.form.get(f"pede__{c['campo']}__link", "").strip()
                                 for c in (fmt_escolhido.get("pede") or []) if c.get("principal"))
            if not arquivos and not roteiro and not link_principal:
                raise ValueError("Envie o vídeo ou escreva o roteiro.")
            cli, mod = _fmt.usar(slug, quem)
            # chips do formato + texto livre ("Ou escreva..."): no campo de uma escolha só, o texto livre manda; no de vários, soma
            escolhas = []
            for k in request.form:
                if not k.startswith("escolha__") or k.endswith(("__livre", "__varios")):
                    continue
                livre = request.form.get(k + "__livre", "").strip()
                marcados = [v for v in request.form.getlist(k) if v.strip()]
                unico = len(marcados) <= 1 and request.form.get(k + "__varios") is None
                v = "; ".join(([] if (livre and unico) else marcados) + ([f"{livre} (escrito pelo João, não é preset: monte)"] if livre else []))
                escolhas.append((k[9:], v))
            for k in request.form:   # texto livre num campo sem nenhum chip marcado
                if k.startswith("escolha__") and k.endswith("__livre") and request.form[k].strip() and k[:-7] not in request.form:
                    escolhas.append((k[9:-7], f"{request.form[k].strip()} (escrito pelo João, não é preset: monte)"))
            if escolhas:
                briefing = "\n".join(f"{k}: {v}" for k, v in escolhas if v) + ("\n\n" + briefing if briefing else "")
            mats = [_salvar_upload(f) for f in fotos]
            ref = request.files.get("referencia")
            if ref and ref.filename:
                mats.append(_salvar_upload(ref))
                briefing += (f"\n\nREFERÊNCIA DESTE VÍDEO: material/{mats[-1].name}. Siga o formato; da referência só o "
                             "estilo (ritmo, enquadramento, legenda, clima), nunca roteiro, textos, pessoas ou cores. Extraia quadros dela antes de planejar.")
            link = request.form.get("referencia_link", "").strip()
            if link.startswith(("http://", "https://")):
                briefing += (f"\n\nREFERÊNCIA DESTE VÍDEO (link): {link}. Baixe com yt-dlp para a sandbox, extraia quadros e "
                             "siga o formato; da referência só o estilo, nunca roteiro, textos, pessoas ou cores.")
            salvos = [_audio_para_video(_salvar_upload(f)) if f in meu_audio else _salvar_upload(f) for f in arquivos]
            material_formato = {}
            for c_ in (fmt_escolhido.get("pede") or []):   # passo 4 específico do formato (formato.json → pede)
                n_, tipo_ = c_["campo"], c_["tipo"]
                if tipo_ == "voz":
                    continue
                link_ = request.form.get(f"pede__{n_}__link", "").strip()
                val_ = request.form.get(f"pede__{n_}", "").strip()
                up_ = request.files.get(f"pede__{n_}")
                if up_ and up_.filename:
                    m_ = _salvar_upload(up_)
                    mats.append(m_)
                    val_ = f"material/{m_.name}"
                elif c_.get("principal"):
                    if link_ and not salvos:
                        salvos.append(_baixar_link(link_))
                    val_ = f"vídeo principal ({'link ' + link_ if link_ else 'arquivo enviado'})" if (link_ or salvos) else ""
                elif link_:
                    val_ = link_
                if val_:
                    material_formato[n_] = val_
                elif c_.get("obrigatorio") and not (c_.get("principal") and (salvos or roteiro)):   # roteiro colado é o principal do estilo de roteiro
                    raise ValueError(f"Falta preencher: {c_['rotulo']}.")
            bruto = salvos[0] if salvos else None
            job = _prod.criar(cli, mod, bruto, titulo or (Path(arquivos[0].filename).stem if arquivos else "Roteiro"),
                              briefing, [], [], mats, request.form.get("cortar") == "1",
                              roteiro=roteiro if not bruto else "", extras=salvos[1:], formato=slug,
                              legenda=not (request.form.get("legenda") == "0" and _fmt.legenda_do(fmt_escolhido)["desligavel"]))
            if re.fullmatch(r"[a-z0-9_]{1,40}", request.form.get("personagem", "")):   # Explicador 3D: personagem escolhido no Criar
                job["personagem"] = request.form["personagem"]
                _prod.salvar(job)
            if request.form.get("direto_campo"):   # a chave "Seguir direto até o vídeo final" do Criar
                job["seguir_direto"] = request.form.get("direto") == "1"
                _prod.salvar(job)
            if request.form.get("ia_modelo") or request.form.get("ia_esforco"):   # modelo e esforço só deste vídeo (runner lê job["ia"])
                import ia as _ia
                sel_ = dict(_ia.selecao(), provedor="claude")
                if request.form.get("ia_modelo", "").startswith("gpt:"):   # GPT pelo Codex (cartão do Novo vídeo): "gpt:<id>", vazio = padrão da conta
                    sel_["provedor"], sel_["modelo"] = "openai", request.form["ia_modelo"][4:].strip()
                    sel_["cobranca"] = _ia.cobranca(dict(_ia.config(), provedor="openai"))
                elif request.form.get("ia_modelo"):
                    sel_["modelo"] = request.form["ia_modelo"]
                if request.form.get("ia_esforco"):
                    sel_["esforco"] = request.form["ia_esforco"]
                job["ia"] = sel_
                job["ia_escolhida"] = sel_   # a fila respeita (fila.enfileirar); sem isso o de Configurações passava por cima
                _prod.salvar(job)
            pesos_ = {k.split("__", 1)[1]: int(v or 0) for k, v in request.form.items() if k.startswith("ref_peso__") and (v or "0").isdigit()}
            pesos_ = {k: v for k, v in pesos_.items() if v > 0 and (_fmt.estudo_escolhido(slug, k) or _fmt.ref_caminho(slug, k))}
            mix_ = request.form.get("mix_estilo", "").strip()   # "Misturar com outro estilo": as referências dele entram com peso (ex.: Faixa com cenas no Editorial)
            pesos_mix = {k.split("__", 1)[1]: int(v or 0) for k, v in request.form.items() if k.startswith("mix_peso__") and (v or "0").isdigit()}
            pesos_mix = {k: v for k, v in pesos_mix.items() if v > 0 and _fmt.ref_caminho(mix_, k)} if mix_ and mix_ != slug and _fmt.carregar(mix_) else {}
            if pesos_ or pesos_mix:   # quanto cada referência pesa neste vídeo (tudo zero = a IA mistura)
                if pesos_mix and not pesos_:   # nenhum peso no estilo escolhido: a principal dele entra com 70% (o outro estilo é o 30%)
                    ref0 = next((r for r in _fmt.referencias_mistura(slug) if r["principal"]), None) or next(iter(_fmt.referencias_mistura(slug)), None)
                    if ref0:
                        pesos_ = {ref0["nome"]: max(1, round(sum(pesos_mix.values()) * 70 / 30))}
                itens = [(slug, k, v) for k, v in pesos_.items()] + [(mix_, k, v) for k, v in pesos_mix.items()]
                tot = sum(v for _, _, v in itens)
                job["estilo_refs"] = [{"nome": k, "peso": round(100 * v / tot), "formato": f_} for f_, k, v in sorted(itens, key=lambda x: -x[2])]
                job["estilo_ref"] = job["estilo_refs"][0]["nome"]
                _prod.salvar(job)
            if meu_audio and job.get("entrada") == "video":   # só a voz dele: sem ele na tela
                job["aparecer"] = "nao"
                _prod.salvar(job)
            elif request.form.get("aparecer") in ("sim", "nao") and job.get("entrada") == "video":   # Editorial falado: "Você aparece no vídeo?" (job["aparecer"])
                job["aparecer"] = request.form["aparecer"]
                _prod.salvar(job)
            if request.form.get("musica_modo") in ("viral", "sem", "procurar"):   # "Música de fundo" do Novo vídeo (job["musica"])
                job["musica"] = {"modo": "sem" if request.form["musica_modo"] == "sem" else "viral",
                                 "faixa": request.form.get("musica_faixa", "").strip()[:300] if request.form["musica_modo"] != "sem" else "",
                                 "titulo": request.form.get("musica_titulo", "").strip()[:120]}
                _prod.salvar(job)
            if request.form.get("efeitos_modo") in ("ligados", "desligados"):   # "Efeitos sonoros" do Novo vídeo (job["efeitos"])
                job["efeitos"] = {"modo": "sem" if request.form["efeitos_modo"] == "desligados" else "ligados"}
                _prod.salvar(job)
            voz_ = request.form.get("voz", "").strip()
            if voz_ == "meu-audio":
                voz_ = ""
            if voz_.startswith("arq:"):   # arquétipo do VoiceStudio: vira perfil fixo (na 1ª vez) pra voz não trocar de pessoa no meio do vídeo
                import vozes as _vozes
                try:
                    voz_ = _vozes.perfil_do_arquetipo(voz_)
                except Exception as e:  # noqa: BLE001
                    flash(f"✗ Não consegui fixar a voz escolhida ({e}). Usei a automática.")
                    voz_ = ""
            if material_formato or voz_:
                if material_formato:
                    job["material_formato"] = material_formato
                if voz_:
                    job["voz"] = voz_
                _prod.salvar(job)
            if bruto and roteiro:   # o roteiro é o gabarito do corte (corte.ler_roteiro lê da work)
                work = _prod.RAIZ / job["sandbox"] / "work"
                work.mkdir(parents=True, exist_ok=True)
                (work / "roteiro.txt").write_text(roteiro + "\n", encoding="utf-8")
                job["roteiro_corte"] = f"{job['sandbox']}/work/roteiro.txt"
                _prod.salvar(job)
            if roteiro and not bruto:   # roteiro vira narração: a emoção de cada frase (a do João na tela, ou o Claude marca agora) fica ao lado do roteiro.txt
                try:
                    import emocao as _emo
                    pasta_r = (_prod.RAIZ / job["bruto"]).parent
                    marcadas = _json.loads(request.form.get("emocoes") or "[]")
                    linhas_ = _emo.alinhar(roteiro, marcadas) if marcadas else _emo.marcar(roteiro)
                    _emo.gravar(pasta_r, linhas_)
                except Exception as e:  # noqa: BLE001   emoção é extra: sem ela a narração sai normal
                    flash(f"Não marquei a emoção das frases ({e}). A narração sai com a voz normal.")
            prefs = _cenas_da_chip(request.form.get("escolha__cenas", ""), _fmt.quantidade_cenas(fmt_escolhido))
            if prefs:                       # a chip "Cenas de apoio" já vira a preferência da edição (não só texto)
                edicao.aplicar(job, prefs)
                _prod.salvar(job)
            for erro in _aplicar_conversa(job, request.form):
                flash(f"✗ Não copiei {erro}")
        except Exception as e:
            flash(f"✗ {e}")
            return redirect(url_for("novo_tela", estilo=slug, cliente=quem))
        if request.form.get("direto_campo") and job.get("entrada") == "roteiro":   # Criar vídeo (tela nova): roteiro pronto já sai montando o storyboard
            try:
                _prod.analisar(job["cliente"], job["slug"])
                flash("✓ Vídeo criado. O Claude já está montando o storyboard: acompanhe em Em andamento; ele para pedindo a sua aprovação.")
                return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))
            except Exception as e:  # noqa: BLE001
                flash(f"✗ Criei o vídeo, mas não consegui começar o storyboard ({e}). Clique em Montar o storyboard.")
                return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))
        flash("✓ Vídeo criado. Clique em Montar o storyboard.")
        return redirect(url_for("job", cli=job["cliente"], slug=job["slug"]))

    _TAM_SANDBOX: dict = {}

    def _tamanho_mb(j) -> float:
        total = 0
        for r in [j.get("saida")] + [v.get("arquivo") for v in j.get("versoes", [])]:
            if r and (RAIZ / r).is_file():
                total += (RAIZ / r).stat().st_size
        sb = RAIZ / j.get("sandbox", "")
        if j.get("sandbox") and sb.is_dir():
            ag = time.time()
            guardado = _TAM_SANDBOX.get(str(sb))
            if guardado and ag - guardado[0] < 120:   # varrer a pasta toda a cada abertura da lista pesa; o tamanho vale por 2 min
                total += guardado[1]
            else:
                t = sum(p.stat().st_size for p in sb.rglob("*") if p.is_file())
                _TAM_SANDBOX[str(sb)] = (ag, t)
                total += t
        return round(total / 1e6, 1)

    def _apagar_e_avisar(cli, slug, lote=False):
        """O caminho único de apagar (producao.apagar → saidas.apagar_video). Devolve o resultado ou None se recusou (já avisou)."""
        try:
            r = _prod.apagar(cli, slug, lote=lote)
        except ValueError as e:
            motivo = str(e)
            flash("✗ Esse vídeo é referência. Pra apagar, use Saídas e confirme." if motivo.startswith("É referência") else f"✗ {motivo}")
            return None
        flash(_saidas.mensagem(r))
        return r

    @app.route("/videos/<cli>/<slug>/apagar", methods=["POST"])
    def video_apagar(cli, slug):
        if not _prod.carregar(cli, slug):
            abort(404)
        _apagar_e_avisar(cli, slug)
        return redirect(url_for("meus_videos"))

    @app.route("/videos/apagar-finalizados", methods=["POST"])
    def videos_apagar_finalizados():
        n, mb = 0, 0.0
        for j in _prod.listar():
            if j.get("status") in ("arquivado", "exportado") and not j.get("rodando"):
                try:
                    r = _prod.apagar(j["cliente"], j["slug"], lote=True)   # lote: referência e vídeo rodando ficam
                    n += 1
                    mb += r["mb"]
                except ValueError:
                    pass
        flash(f"✓ {n} vídeo(s) finalizado(s) apagado(s) por inteiro (saída, projeto, rascunhos e registro). Liberou {round(mb, 1)} MB. "
              f"As cópias exportadas pro Mac continuam onde estão.")
        return redirect(url_for("meus_videos"))

    @app.route("/videos")
    def meus_videos():
        quem = request.args.get("cliente", "")
        import andamento as _and
        _prod.reconciliar()
        vis = {d["id"]: d for d in _and.listar()}
        todos = [_enfeitar(j) for j in _prod.listar(quem or None)]
        for j in todos:
            j["mb"] = _tamanho_mb(j)
            j["pagina"] = url_for("andamento_ver", cli=j["cliente"], slug=j["slug"]) if _and.carregar(j["cliente"], j["slug"]) \
                else url_for("job", cli=j["cliente"], slug=j["slug"])   # a mesma tela do Início e do Esperando você
        onde = {id(j): lugar(j, vis) for j in todos}
        prontos = [j for j in todos if onde[id(j)] == "videos" and j.get("status") not in ("arquivado", "exportado")]
        em_producao = [j for j in todos if onde[id(j)] == "producao"]
        finalizados = [j for j in todos if j.get("status") in ("arquivado", "exportado")]
        return render_template("meus_videos.html", prontos=prontos, em_producao=em_producao, finalizados=finalizados,
                               clientes=clientes(), quem=quem)

    @app.route("/clientes")
    def clientes_lista():
        cls = clientes()
        for c in cls:
            c["formatos"] = sorted({(_fmt.de_modelo(m) or {}).get("titulo", m) for m in c["modelos"]})
        return render_template("clientes.html", clientes=cls)

    @app.route("/custos", methods=["GET", "POST"])
    def custos():
        if request.method == "POST":
            nomes = request.form.getlist("nome")
            lista = [{"nome": n, "plano": p, "valor": v, "moeda": m, "cobre": c} for n, p, v, m, c in
                     zip(nomes, request.form.getlist("plano"), request.form.getlist("valor"),
                         request.form.getlist("moeda"), request.form.getlist("cobre"))]
            _custos.salvar_assinaturas(lista)
            flash("✓ Assinaturas salvas.")
            return redirect(url_for("custos", periodo=request.args.get("periodo", "mes")))
        try:
            cot = float(request.args.get("cotacao", _custos.COTACAO_PADRAO))
        except ValueError:
            cot = _custos.COTACAO_PADRAO
        a = request.args
        r = _custos.resumo(a.get("periodo", "mes"), cot, a.get("de", ""), a.get("ate", ""), a.get("projeto", ""))
        mes_inteiro = a.get("periodo", "mes") == "mes" and not a.get("projeto")   # então o resumo já é o do mês: não calcula de novo
        return render_template("custos.html", r=r, v=_custos.visao(cot, r["equivalente_plano_usd"] if mes_inteiro else None))

    # ── corte manual: "corta daqui até aqui" quando o automático erra ──
    def _alvo_manual(tipo, a, b=None):
        if tipo == "avulso":
            c = _cortes.avulso_carregar(a)
            if not c:
                abort(404)
            pasta = c["pasta"]; saida = pasta / "cortado.mp4"
            # abre o ORIGINAL com os cortes da IA marcados: dá pra desfazer o que ela cortou errado (antes abria o já cortado)
            origem = RAIZ / c["original"] if (RAIZ / c["original"]).exists() else saida
            def depois(res):
                m = ler_json(pasta / "corte.json", {}) or {}
                m.update({"status": "cortado", "cortado_em": agora(), "manual": True,
                          "duracao_final": res["ficou_s"]})
                gravar_json(pasta / "corte.json", m)
            return dict(titulo=c["titulo"], voltar=url_for("corte_detalhe", slug=a), origem=origem,
                        saida=saida, pasta=pasta, depois=depois, work=[pasta, pasta / "work"],
                        ia_dir=pasta / "work", cliente=c.get("cliente") or "Joao")
        j = _prod.carregar(a, b)
        if not j:
            abort(404)
        work = ensure(RAIZ / j["sandbox"] / "work")
        saida = work / "joao.mp4"
        origem = RAIZ / j["bruto"]   # sempre o bruto original: os cortes da IA vêm marcados e dá pra desfazer
        if origem.suffix.lower() not in VIDEO_EXTS:
            abort(400)
        def depois(res):
            jj = _prod.carregar(a, b)
            jj["corte_aplicado"] = {"em": agora(), "arquivo": rel(saida), "manual": True,
                                    "segmentos_mantidos": "manual", "segmentos_total": res["trechos_tirados"],
                                    "duracao_s": res["ficou_s"]}
            if jj.get("status") in ("novo", "cortado", "erro"):
                jj["status"] = "cortado"
            _prod.salvar(jj)
            # o vídeo NÃO é refeito aqui: o João assiste o corte e aprova (acao=aprovar → _aprovar_corte)
        # formato sem corte automático (Frase fixa, Caixinha): o "Cortar com IA" propõe numa pasta à parte,
        # pra não mexer no CORTE.json nem fazer a tela achar que o vídeo precisa ser refeito
        return dict(titulo=j["titulo"], voltar=url_for("job", cli=a, slug=b), origem=origem, saida=saida,
                    pasta=work, depois=depois, work=[work, work / "corte-ia"], ia_dir=work / "corte-ia",
                    cliente=a)

    def _aprovar_corte(cli, slug) -> str:
        """O João assistiu o corte e aprovou: o vídeo segue sozinho com o corte novo.
        Formato com camada (Frase fixa, Caixinha): só queima a caixa de novo, em segundo plano (segundos).
        Os outros: o tempo da fala mudou, então o storyboard é montado de novo (e o vídeo sai dele)."""
        import threading
        import andamento as _and
        j = _prod.carregar(cli, slug)
        sb = RAIZ / j["sandbox"]
        if (sb / "camada.json").is_file():
            import camada as _cam
            _and.passo(cli, slug, "Corte aprovado: refazendo o vídeo", etapa="video", titulo=j.get("titulo", ""),
                       formato=j.get("formato") or "", origem="tela")

            def refaz():
                try:
                    saida = _cam.renderizar(sb)
                    _and.registrar(cli, slug, "Vídeo refeito com o corte novo", "pronto", video=rel(saida))
                except Exception as e:
                    _and.erro(cli, slug, f"Não consegui refazer o vídeo com o corte: {e}")
            threading.Thread(target=refaz, daemon=True).start()
            return "✓ Corte aprovado. O vídeo está sendo refeito (alguns segundos)."
        if j.get("rodando") or _prod.corte_rodando(j):
            return "✓ Corte aprovado. O vídeo já está sendo feito e usa este corte."
        _prod.analisar(cli, slug)
        return "✓ Corte aprovado. Montando o storyboard com o corte novo."

    def _cortes_da_ia(pastas):
        """Trechos que o corte automático tirou (CORTE.json: segmentos com manter=false) + pausas longas entre os que ficam,
        no tempo do vídeo ORIGINAL. Viram as marcas vermelhas iniciais do editor."""
        for p in pastas:
            d = ler_json(Path(p) / "CORTE.json", None) if p else None
            if not d or not d.get("segmentos"):
                continue
            segs = sorted(d["segmentos"], key=lambda x: x["t0"])
            fora = [[x["t0"], x["t1"]] for x in segs if not x.get("manter")]
            ficam = [x for x in segs if x.get("manter")]
            for a, b in zip(ficam, ficam[1:]):
                if b["t0"] - a["t1"] > 0.8:
                    fora.append([round(a["t1"] + 0.15, 2), round(b["t0"] - 0.15, 2)])
            fora.sort()
            junto = []
            for a, b in fora:
                if junto and a <= junto[-1][1] + 0.05:
                    junto[-1][1] = max(junto[-1][1], b)
                else:
                    junto.append([a, b])
            return junto
        return []

    @app.route("/corte-manual/<tipo>/<a>", methods=["GET", "POST"], defaults={"b": None})
    @app.route("/corte-manual/<tipo>/<a>/<b>", methods=["GET", "POST"])
    def corte_manual(tipo, a, b):
        if tipo not in ("avulso", "video"):
            abort(404)
        alvo = _alvo_manual(tipo, a, b)
        if request.method == "POST" and request.form.get("acao") == "ia":
            # corte pela IA antes da mão: transcreve, acha take refeito, erro assumido e pausa longa; vira marca vermelha
            try:
                if not _cortes.rodando(alvo["ia_dir"]):
                    _cortes.propor(alvo["origem"], alvo["ia_dir"], cliente=alvo["cliente"], refazer=True)
            except Exception as e:
                flash(f"✗ {e}")
            return redirect(request.path)
        if request.method == "POST" and request.form.get("acao") == "voltar":   # "Voltar ao corte anterior"
            try:
                _manual.voltar(alvo["saida"], alvo["pasta"], alvo["depois"])
                flash("↶ Voltei ao corte anterior. Assista e aprove, ou corrija de novo.")
            except Exception as e:
                flash(f"✗ {e}")
            return redirect(request.path)
        if request.method == "POST" and request.form.get("acao") == "aprovar":
            try:
                msg = ("Refazendo o vídeo com o corte novo. " + _aprovar_corte(a, b)) if tipo == "video" else "✓ Corte aprovado."
                gravar_json(alvo["pasta"] / ".manual.json", {**_manual.estado(alvo["pasta"]), "aprovado": agora()})
                flash(msg)
            except Exception as e:
                flash(f"✗ {e}")
                return redirect(request.path)
            return redirect(alvo["voltar"])
        if request.method == "POST":
            try:
                remover = [[float(x), float(y)] for x, y in _json.loads(request.form.get("remover") or "[]")]
                _manual.disparar(alvo["origem"], alvo["saida"], remover, alvo["pasta"], alvo["depois"])
            except Exception as e:
                flash(f"✗ {e}")
            return redirect(request.path)
        est = _manual.estado(alvo["pasta"])
        ia = _cortes_da_ia(alvo.get("work") or [])
        video = rel(alvo["origem"])   # a edição é sempre sobre o original; o resultado sai em outro arquivo
        d_ia = alvo["ia_dir"]
        if not ia and not _cortes.rodando(d_ia) \
                and not (d_ia / "CORTE.json").exists() and not (d_ia / ".log").exists():
            # o primeiro corte é sempre o da IA; o João só ajusta depois. Uma vez só: falhou, não repete sozinho
            try:
                _cortes.propor(alvo["origem"], d_ia, cliente=alvo["cliente"])
            except Exception as e:
                flash(f"✗ Não consegui começar o corte da IA: {e}")
        ia_rodando = _cortes.rodando(d_ia)
        # marca salva na mão só vale se for mais nova que o corte da IA; senão abre com o da IA
        cj = next((Path(q) / "CORTE.json" for q in alvo.get("work") or [] if (Path(q) / "CORTE.json").exists()), None)
        mj = alvo["pasta"] / ".manual.json"
        if cj and mj.exists() and cj.stat().st_mtime > mj.stat().st_mtime:
            est = {**est, "remover": None}
        ia_falhou = not ia and not ia_rodando and "✖" in ((d_ia / ".log").read_text(encoding="utf-8", errors="ignore") if (d_ia / ".log").exists() else "")
        return render_template("corte_manual.html", titulo=alvo["titulo"], voltar=alvo["voltar"],
                               video=video, estado=est, ia=ia, tipo=tipo, ia_rodando=ia_rodando, ia_falhou=ia_falhou,
                               ia_etapa=_cortes.etapa(alvo["ia_dir"]) if ia_rodando else "", pronto=rel(alvo["saida"]) if est.get("ok") and alvo["saida"].exists() else None)

    # ── referências: apagar e tentar de novo ──
    @app.route("/referencia/<slug>/apagar", methods=["POST"])
    def referencia_apagar(slug):
        import estudo
        estudo.remover(slug)
        flash("✓ Referência apagada.")
        return redirect(url_for("referencias"))

    @app.route("/referencia/<slug>/tentar", methods=["POST"])
    def referencia_tentar(slug):
        import estudo
        try:
            d = estudo.carregar(slug)
            fase = (d or {}).get("fase_erro", "analisar")
            estudo.iniciar(slug, fase, d.get("nome_aprovado") if fase == "construir" else None)
            flash("✓ Recomeçou. Acompanhe na página da referência.")
        except Exception as e:
            flash(f"✗ {e}")
        return redirect(url_for("referencias"))

