"""Novo vídeo numa tela só (PLANO-2.0, item 5): 01 O vídeo · 02 Estilo (com Como funciona e o peso de cada referência) ·
03 História (Claude escreve ou eu tenho) · 04 Direção e qualidade. Manda os mesmos campos do /criar (o POST é o dele)."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import flash, jsonify, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import formatos as _fmt  # noqa: E402

QUALIDADES = [
    ("padrao", "Padrão", "Monta e entrega o storyboard; quem confere é você. O mais rápido, bom pra testar uma ideia."),
    ("conferido", "Conferido", "Depois de montar, o Claude olha 2 quadros de cada cena e conserta o que estiver fora: texto ilegível, rosto cortado, imagem que não casa com a fala."),
    ("ultra", "Ultra", "Conferido + uma segunda rodada nas cenas mais fracas, trocando a peça ou a imagem por uma mais forte. Mais lento e gasta mais do seu limite."),
]


# Força do Claude (controle de 0 a 100): cada faixa vira o modelo e o esforço que o POST já lê (ia_modelo, ia_esforco).
FORCAS = [   # (vai até, nome, modelo, esforço, o que muda)
    (20, "Rápido", "haiku", "low", "O mais rápido e barato. Bom pra testar uma ideia."),
    (45, "Bom", "sonnet", "medium", "Equilíbrio entre qualidade e velocidade."),
    (70, "Forte", "sonnet", "high", "Pensa mais em cada cena. É o ponto certo pra quase todo vídeo."),
    (90, "Muito forte", "opus", "high", "O modelo mais capaz. Roteiro e cenas mais cuidados; mais lento."),
    (101, "Ultra", "opus", "max", "Pensa o máximo. Só pra vídeo importante: demora e gasta mais do seu limite."),
]
FORCA_PADRAO = 58   # meio-forte: Sonnet · alto


def forca_de(valor: int) -> dict:
    """O valor do controle (0-100) -> {nome, modelo, esforco, desc}."""
    v = max(0, min(100, int(valor)))
    for ate, nome, modelo, esforco, desc in FORCAS:
        if v < ate:
            return {"nome": nome, "modelo": modelo, "esforco": esforco, "desc": desc}
    return {"nome": FORCAS[-1][1], "modelo": FORCAS[-1][2], "esforco": FORCAS[-1][3], "desc": FORCAS[-1][4]}


ROTULOS_ESTILO = {"falando": "Falando", "animacao": "Animação", "3d": "3D", "narracao": "Com narração", "gravado": "Vídeo gravado"}


def tags_estilo(f: dict) -> list[str]:
    """Etiquetas que filtram os estilos no Criar: tipo (falando/animação), de onde vem (vídeo gravado/narração) e 3D."""
    t = []
    if f.get("grupo") in ("falando", "animacao"):
        t.append(f["grupo"])
    if f.get("entrada") in ("video", "video-ou-roteiro", "filmagem"):
        t.append("gravado")
    if f.get("entrada") in ("roteiro", "video-ou-roteiro"):
        t.append("narracao")
    if "3d" in f.get("slug", "") or "3D" in f.get("titulo", ""):
        t.append("3d")
    return t



def _tem_escolha_musica(f: dict) -> bool:
    """O estilo mostra "Música de fundo" no Novo vídeo: usa música e é viral (Editorial) ou pede a escolha na tela (escolha_na_tela)."""
    m = ((f.get("som") or {}).get("musica") or {})
    return bool(m.get("usa", True) and (m.get("viral") or m.get("escolha_na_tela")))

def _estilo(f: dict) -> dict:
    ex = (f.get("exemplos") or [{}])[0]
    pasta = f"formatos/{f['slug']}"
    import re
    leg = lambda t: re.sub(r"\s+", " ", re.sub(r"\([^)]*\)|`[^`]*`|\S+\.(py|json|md|mp3|wav)\b", "", t or "")).strip(" ;,:")   # sem comando nem arquivo: o João lê
    def faz_leitura(e: dict) -> str:   # frase da receita só quando dá pra ler; instrução pra IA (comando, arquivo, número, MAIÚSCULA) fica de fora: sobra o título
        bruto = (e.get("faz") or "").split(". ")[0]
        limpo = leg(bruto)[:200]
        tecnico = ("`" in bruto or re.search(r"comando|briefing|sandbox|Groq|ffprobe|ducking|exit|\.|/|--|_|\d|\b[A-Z]{4,}\b", bruto)
                   or re.search(r"\b(em|de|do|da|com|a|o|e|,)\s*$|\s[,;:]|\+ \+|\(\s*\)", limpo))
        return "" if tecnico or not limpo or len(limpo) > 130 else limpo
    etapas = [{"titulo": e.get("titulo", ""), "faz": faz_leitura(e)}
              for e in ((f.get("esteira") or {}).get("etapas") or []) if e.get("id") != "briefing"]
    return {"slug": f["slug"], "titulo": f.get("titulo", f["slug"]), "frase": f.get("frase", ""), "entrada": f.get("entrada", "video"),
            "grupo": f.get("grupo", ""), "poster": f"{pasta}/{ex['poster']}" if ex.get("poster") else "",
            "video": f"{pasta}/{ex['arquivo']}" if ex.get("arquivo") else "", "etapas": etapas,
            "quadros_url": f"/api/storyboard/{f['slug']}", "tags": tags_estilo(f), "aparecer": bool(f.get("aparecer")),
            "musica": _tem_escolha_musica(f), "musica_padrao": "viral" if (((f.get("som") or {}).get("musica") or {}).get("viral") or "roteiro" in str(f.get("entrada", ""))) else "sem",   # "Música de fundo" na tela: estilo de roteiro (Editorial, Documentário) já abre com música; os gravados abrem sem
            "efeitos": bool((((f.get("som") or {}).get("efeitos") or {}).get("usa"))),   # "Efeitos sonoros" ligados/desligados só onde o estilo tem
            "refs_mistura": [{k: r[k] for k in ("nome", "titulo", "video", "principal")} for r in _fmt.referencias_mistura(f["slug"])],
            "usa": [{"oque": u.get("oque", ""), "quem": u.get("quem", ""), "tipo": u.get("tipo", "")} for u in (f.get("usa") or [])],
            "pede": [{k: c.get(k, "") for k in ("campo", "rotulo", "tipo", "dica", "padrao", "obrigatorio", "principal")} for c in (f.get("pede") or [])],
            "escolhas": [{k: c.get(k, "") for k in ("campo", "rotulo", "tipo", "opcoes", "padrao")} for c in (f.get("escolhas") or [])],
            "refs": [{"nome": e["nome"], "titulo": e["titulo"], "video": (e["videos"] or [""])[0], "principal": e["principal"]}
                     for e in _fmt.estudos(f["slug"])] if (f["pasta"] / "estudos").is_dir() else []}


def _forcas(ia) -> list[dict]:
    """As faixas com o nome real do modelo (Sonnet 5.5, Opus 5.5...) e o esforço em português."""
    esf = {v: r.split(" — ")[0] for v, r in ia.ESFORCOS}
    ini, out = 0, []
    for ate, nome, modelo, esforco, desc in FORCAS:
        out.append({"de": ini, "ate": min(ate, 100), "nome": nome, "modelo": modelo, "esforco": esforco, "desc": desc,
                    "rotulo": f"{ia.nome_claude(modelo).replace('Claude ', '')} · {esf.get(esforco, esforco).lower()}"})
        ini = ate
    return out


def forcas_config(ia) -> dict:
    """Pro controle "Força do Claude" de Configurações: as faixas e a posição que bate com o modelo/esforço gravados."""
    cfg = ia.config()
    modelo, esf = (cfg.get("modelo_claude") or "sonnet"), ("max" if cfg.get("ultra_mode") else (cfg.get("esforco") or "medium"))
    fx = _forcas(ia)
    achada = next((f for f in fx if f["modelo"] == modelo and f["esforco"] == esf), None)
    valor = FORCA_PADRAO if not achada else (achada["de"] + achada["ate"]) // 2
    return {"forcas": fx, "forca_valor": valor}


def register(app):
    import modelo_forca   # Jinja: modelo_forca_dados() do macro _modelo_forca.html (Novo vídeo, Editar vídeo, Configurações)
    modelo_forca.register(app)

    @app.post("/api/transcrever-audio")
    def api_transcrever_audio():
        """"Só a minha voz (MP3)": o Groq (grátis) transcreve o áudio pro João conferir antes de criar. Não grava nada."""
        import tempfile
        f = request.files.get("audio")
        if not f or not f.filename:
            return jsonify(ok=False, erro="Escolha o áudio primeiro."), 400
        try:
            from corte import chave_groq
            import fala
            chave = chave_groq(request.form.get("cliente") or "Joao")
            if not chave:
                raise ValueError("Falta a chave do Groq (Configurações > Conexões).")
            with tempfile.TemporaryDirectory() as tmp:
                arq = Path(tmp) / ("audio" + (Path(f.filename).suffix.lower() or ".mp3"))
                f.save(str(arq))
                r = fala.groq_transcrever(arq, chave, "", "pt")
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=str(e)[:300]), 400
        linhas = [(x.get("text") or "").strip() for x in (r.get("segments") or []) if (x.get("text") or "").strip()]
        texto = "\n".join(linhas) or (r.get("text") or "").strip()
        if not texto:
            return jsonify(ok=False, erro="Não ouvi fala nesse áudio."), 400
        return jsonify(ok=True, texto=texto, palavras=len(texto.split()))

    @app.get("/criar-agora")
    def novo_tela():
        import ia
        import vozes as _vz
        from _comum import clientes
        cls = [c["nome"] for c in clientes() if c["nome"] != _fmt.AVULSO]
        estilos = [_estilo(f) for f in _fmt.listar() if f.get("status") == "pronto"]
        # ?estilo=<slug>&cliente=<Nome>: quem manda o João pra cá (Usar este estilo, Criar vídeo pra X) já chega escolhido
        pre_estilo = (request.args.get("estilo") or request.args.get("formato") or "").strip()
        if pre_estilo not in {e["slug"] for e in estilos}:
            pre_estilo = ""
        pre_cliente = (request.args.get("cliente") or "").strip()
        if pre_cliente not in cls:
            pre_cliente = ""
        pre_conv, pre_direcao = None, ""   # ?briefing=<id>: o fim do "Conversar antes de criar" chega com tudo preenchido
        if request.args.get("briefing"):
            try:
                import simples as _sm
                pre_conv = _sm._pre_criar(request.args["briefing"])
                pre_direcao = pre_conv.get("texto") or ""
                if pre_conv.get("formato") in {e["slug"] for e in estilos}:
                    pre_estilo = pre_conv["formato"]
                if pre_conv.get("cliente") in cls:
                    pre_cliente = pre_conv["cliente"]
            except ValueError:
                flash("✗ Conversa não encontrada.")
        pre_roteiro = pre_titulo = ""   # ?variacao=<id>:<n> (variação aprovada em /variacoes) chega com a história e o título escritos
        try:
            import variacoes as _vr
            vid, n = (request.args.get("variacao") or "").split(":")
            v = _vr.roteiro_de(vid, int(n))
            pre_roteiro, pre_titulo = v["roteiro"], v["titulo"]
        except (ValueError, TypeError):
            pass
        if pre_conv and not pre_roteiro:
            pre_roteiro = pre_conv.get("roteiro") or ""
        try:
            vozes, arquetipos = _vz.cartoes(), _vz.cartoes_arquetipos()
        except Exception:  # noqa: BLE001
            vozes, arquetipos = [], []
        import elenco as _el   # Explicador 3D: a fileira "Personagem" (PLANO-2.0, item 7)
        return render_template("novo.html", elenco=_el.ler(_el.FORMATO), rotulos=_el.rotulos(_el.FORMATO), previa=_el.previa(_el.FORMATO), estilos=estilos, clientes=cls, vozes=vozes, arquetipos=arquetipos, rotulos_tags=_vz.ROTULOS_TAGS, rotulos_estilo=ROTULOS_ESTILO,
                               qualidades=QUALIDADES, pre_estilo=pre_estilo, pre_cliente=pre_cliente, pre_roteiro=pre_roteiro, pre_titulo=pre_titulo,
                               pre_conv=pre_conv, pre_direcao=pre_direcao)
