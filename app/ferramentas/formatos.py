#!/usr/bin/env python3
"""
formatos — o CATÁLOGO do Estúdio. Um formato é a receita; o cliente é a pele.

    formatos/<slug>/formato.json        título, frase, entrada, motor, modelos (variantes), base, exemplos
    formatos/<slug>/exemplo-N.mp4/.jpg  vídeo leve pra dar play na tela
    formatos/<slug>/aprendizado/        regras que valem pra esse formato em qualquer cliente
    formatos/<slug>/base/               ponto de partida quando o formato não nasceu num cliente

Variante = o modelo já calibrado de um cliente (clientes/<C>/<c>Content/modelos/<modelo>/).
Usar um formato pra um cliente que ainda não tem a variante copia a base pra ele (aprendizado zerado).
"Avulso" é um cliente como os outros, com a pele neutra.
"""
from __future__ import annotations

import json
import re

import shutil
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import (RAIZ, memoizado, append_jsonl, cliente as _cliente, clientes as _clientes, ensure, ffprobe, gravar_json, hoje,
                    ler_json, rel, thumb)

FORMATOS = RAIZ / "formatos"
AVULSO = "Avulso"
ENTRADAS = {
    "video": "Vídeo gravado",
    "roteiro": "Roteiro (voz de IA ou a sua)",
    "video-ou-roteiro": "Vídeo gravado ou roteiro",
    "filmagem": "Vários vídeos de um evento",
}


def _exemplos(pasta: Path, dados: dict) -> list[dict]:
    """Exemplos com arquivo de verdade. O PRIMEIRO é o exemplo principal (a régua de qualidade do formato)."""
    out = []
    for e in dados.get("exemplos") or []:
        v = pasta / e.get("arquivo", "")
        if v.is_file():
            p = pasta / e.get("poster", "")
            fo = _arq_folha(v)
            out.append({**e, "video": rel(v), "poster_rel": rel(p) if p.is_file() else None,
                        "folha_rel": rel(fo) if fo.is_file() else None})
    return out


# ───────────────────── esteira: os passos que a tela segue ─────────────────────

ANDAMENTOS = ("preparar", "storyboard", "aprovacao", "video", "conferencia", "pronto")   # as etapas do Em andamento
COMANDOS_PADRAO = {   # o motor HTML do Estúdio (render.py + cenas.json na sandbox); o formato pode trocar em "esteira" → "comandos"
    "storyboard": "python3 <sandbox>/render.py --storyboard --cenas <sandbox>/cenas.json",
    "render": "python3 <sandbox>/render.py --cenas <sandbox>/cenas.json",
    "conferir": "python3 <sandbox>/render.py --conferir --cenas <sandbox>/cenas.json",
}
# Vídeo gravado: o storyboard é o do fluxo de vídeo gravado; o render (e a conferência, se tiver comando) o formato declara.
COMANDOS_GRAVADO = {"storyboard": "python3 app/ferramentas/storyboard.py <sandbox>",
                    "conferir": "python3 app/ferramentas/conferir_video.py <saida> --sandbox <sandbox>"}   # <saida>: o mp4 renderizado (ainda na sandbox, se não copiou)
NAO_PRONTO = "Este formato ainda não está pronto pra usar pela tela."
# O que cada formato de motor declara sobre o próprio vídeo (formato.json → "esteira"); sem o campo vale o motor HTML do Estúdio:
CENAS_PADRAO = "cenas.json"                      # "cenas": arquivo do vídeo na sandbox (padrão cenas.json; animação em HTML: index.html)
FOLHA_PADRAO = "qa/folha-comparacao.jpg"         # "folha": a folha que a conferência gera (render lado a lado com o exemplo)
VOZES = ("narracao", "motor", "sem")             # "voz": narracao_tts (padrão) | o próprio motor gera | sem narração

# O CONTRATO (formatos/CONTRATO.md): os dois tipos de formato e os dois status.
TIPOS = {
    "motor": "animação construída, com motor próprio em formatos/<slug>/base (render.py)",
    "gravado": "vídeo gravado com corte, cenas e cards por cima (ffmpeg ou composição Remotion que já existe)",
}
STATUS = ("pronto", "receita")
MOTOR_PADRAO = ("render.py", "index.html")
TIPOS_PEDE = ("arquivo", "link", "arquivo_ou_link", "tempo", "texto", "voz", "foto")   # formato.json → pede[].tipo
MARCA_MODELO = "TROQUE:"        # texto do formatos/_modelo que ainda não foi trocado: formato pronto não pode ter
COMO_FAZER_MAX_LINHAS = 90      # COMO-FAZER curto: uma página

# Passo 0 de todo formato (CONTRATO): o briefing fechado com o João na conversa (ou no Criar). Ele aprova lá, antes da
# esteira rodar, então essa aprovação não é a parada: a tela continua parando no storyboard.
BRIEFING = "briefing"
# O material que o formato sabe usar (formato.json → "material_aceito"): o "papel" de cada arquivo liberado no briefing.
MATERIAIS = {
    "cena-produto": "imagem do produto que entra como cena (capa, embalagem, tela da oferta)",
    "mockup": "o produto montado numa cena (livro na mesa, tela no celular)",
    "logo": "a marca do cliente",
    "foto-pessoa": "foto real de gente (o cliente, um aluno, um depoimento)",
    "print": "print de post, notícia, conversa ou página (a prova)",
    "video-curto": "trecho curto de vídeo próprio (bastidor, prova, cena do cliente)",
    "musica": "música do próprio cliente",
}
# Como o formato ocupa a tela (formato.json → "layouts"): só o que o motor já sabe montar. O nome é o que o João lê.
LAYOUTS = {
    "cheio": "tela cheia",
    "dividido": "tela dividida (um enquadramento em cima e outro embaixo)",
    "faixa": "cena numa faixa embaixo da pessoa",
    "cantinho": "pessoa num quadradinho no canto",
    "janela": "cena numa janela menor (com fundo em volta)",
}
# Palavras do "o que copiar" (ditado pelo João) que pedem um layout, quando a conversa não marcou o "layout".
_PALAVRAS_LAYOUT = (
    ("dividido", r"divid|split|empilhad|em cima e (?:outr[oa] )?embaixo|metade de cima|dois enquadramentos"),
    ("cantinho", r"cantinho|quadradinho|picture.in.picture|\bpip\b"),
    ("faixa", r"faixa (?:de )?(?:baixo|embaixo)"),
    ("janela", r"moldura|\b(?:numa|em|na) janela\b"),
    ("cheio", r"tela (?:cheia|toda|inteira)"),
)


def tipo(f: dict | None) -> str:
    """motor | gravado (formato.json → "tipo"). Sem o campo vale motor: é como a esteira sempre funcionou."""
    t = (f or {}).get("tipo")
    return t if t in TIPOS else "motor"


def segue_esteira(f: dict | None) -> bool:
    """A TELA segue a esteira do formato (storyboard do motor, sem a escolha das cenas de apoio)? No formato de motor e no
    de filmagem de evento (vários vídeos soltos, ex.: Cinematográfico): o fluxo de vídeo gravado transcreve e planeja em
    cima da fala de UM vídeo só, o que não serve pra montagem de evento (o João mandou 20 takes e a tela usou o 1º).
    O gravado de fala também declara os passos, mas roda no fluxo de vídeo gravado (com a escolha das cenas): a IA segue
    os passos dele por dentro (producao.camadas_de_regra)."""
    return bool(f and f.get("esteira")) and (tipo(f) == "motor" or f.get("entrada") == "filmagem")


def motor_itens(f: dict | None) -> list[str]:
    """Arquivos do motor (esteira.motor_arquivos; sem a lista, render.py + index.html)."""
    e = (f or {}).get("esteira")
    itens = e.get("motor_arquivos") if isinstance(e, dict) else None
    return [str(x) for x in (itens or MOTOR_PADRAO) if str(x).strip() and ".." not in str(x)]


def _andamento_padrao(e: dict, depois: bool) -> str:
    if e.get("id") == BRIEFING:
        return "preparar"
    if e.get("aprovar"):
        return "storyboard"
    nome = f"{e.get('id', '')} {e.get('titulo', '')}".lower()
    if "storyboard" in nome:
        return "storyboard"
    if "confer" in nome:
        return "conferencia"
    return "video" if depois else "preparar"


def esteira(f: dict | None) -> dict | None:
    """A ESTEIRA do formato (formato.json → "esteira"): os passos da receita, na ordem, que a tela roda sozinha.

    Aceita {"etapas": [...], "comandos": {...}} ou só a lista de etapas. Cada etapa:
        {"id", "titulo", "andamento": preparar|storyboard|video|conferencia, "faz": "o que fazer", "aprovar": bool}
    Pelo menos uma etapa tem "aprovar": true; a primeira delas é onde a tela PARA pro João aprovar (storyboard). A etapa
    "briefing" (o passo 0) não conta: ele aprova o briefing na conversa, antes da esteira.
    Comandos do motor: "comandos" {storyboard, render, conferir} ou o "comando" da etapa (--storyboard, --conferir,
    o render da etapa de vídeo); "<sandbox>" vira a pasta do vídeo e comando sem ela roda de dentro da sandbox.
    Campos opcionais (sem eles vale o motor HTML do Estúdio, render.py + cenas.json, como o Documentário):
        "cenas"         arquivo do vídeo na sandbox, onde ficam as cenas (padrão cenas.json)
        "copiar_motor"  false: o motor roda da base do formato, sem cópia pro cliente nem pra sandbox (padrão true)
        "voz"           narracao (narracao_tts, padrão) | motor (o comando do motor gera a voz) | sem (sem narração)
        "folha"         a folha que a conferência gera (padrão qa/folha-comparacao.jpg); duas versões: a lista das duas
    "som.musica.usa" e "som.efeitos.usa" (formato.json → "som") dizem se o vídeo tem música e efeitos.
    Devolve a esteira normalizada ({"etapas", "parada", "antes", "depois", "comandos", "cenas", "copiar_motor", "voz",
    "folha", "musica", "efeitos"}) ou None se o formato não declara esteira ou ela está malformada (aí a tela não deixa
    usar o formato: ver usar())."""
    if not f or not f.get("esteira"):
        return None
    bruto = f["esteira"]
    if isinstance(bruto, list):
        bruto = {"etapas": bruto}
    if not isinstance(bruto, dict) or not isinstance(bruto.get("etapas"), list):
        return None
    etapas, ids, parada = [], set(), None
    for i, e in enumerate(bruto["etapas"]):
        if not isinstance(e, dict):
            return None
        ident, titulo = str(e.get("id") or "").strip(), str(e.get("titulo") or "").strip()
        aprovar = e.get("aprovar", False)
        if not ident or not titulo or ident in ids or not isinstance(aprovar, bool):
            return None
        andamento = e.get("andamento") or _andamento_padrao(e, parada is not None)
        if andamento not in ANDAMENTOS:
            return None
        ids.add(ident)
        if aprovar and parada is None and ident != BRIEFING:
            parada = i
        faz = next((str(e[k]).strip() for k in ("faz", "instrucao", "descricao", "como") if e.get(k)), "")
        etapas.append({**e, "id": ident, "titulo": titulo, "andamento": andamento, "aprovar": aprovar, "faz": faz})
    if not etapas or parada is None:
        return None
    cmds = dict(COMANDOS_GRAVADO if tipo(f) == "gravado" else COMANDOS_PADRAO)
    for e in etapas:   # o "comando" de uma etapa também vale: --storyboard, --conferir ou o render da etapa de vídeo
        c = str(e.get("comando") or "").strip()
        nome = ("storyboard" if "--storyboard" in c else "conferir" if "--conferir" in c else
                "render" if c and e["andamento"] == "video" else "")
        if nome:
            cmds[nome] = c
    cmds.update({k: str(v) for k, v in (bruto.get("comandos") or {}).items() if isinstance(v, str) and v.strip()})
    cenas = str(bruto.get("cenas") or bruto.get("arquivo_do_video") or CENAS_PADRAO).strip()
    if Path(cenas).is_absolute() or ".." in Path(cenas).parts:
        cenas = CENAS_PADRAO
    folhas = bruto.get("folha") or FOLHA_PADRAO
    folhas = [str(x).strip() for x in (folhas if isinstance(folhas, list) else [folhas]) if str(x).strip()]
    folhas = [x for x in folhas if not Path(x).is_absolute() and ".." not in Path(x).parts] or [FOLHA_PADRAO]
    som = f.get("som") if isinstance(f.get("som"), dict) else {}
    usa = lambda k: not (isinstance(som.get(k), dict) and som[k].get("usa") is False)   # sem o campo: usa (como sempre foi)
    # o "de_onde" que o formato declara vai pro pedido à IA (antes só o validar lia); texto do _modelo não trocado não vai
    de_onde = lambda k: "" if not isinstance(som.get(k), dict) or MARCA_MODELO in str(som[k].get("de_onde") or "") \
        else str(som[k].get("de_onde") or "").strip()
    return {"etapas": etapas, "parada": parada, "antes": etapas[:parada + 1], "depois": etapas[parada + 1:], "comandos": cmds,
            "tipo": tipo(f), "cenas": cenas, "copiar_motor": bruto.get("copiar_motor") is not False,
            "voz": bruto.get("voz") if bruto.get("voz") in VOZES else "narracao", "folha": folhas[0], "folhas": folhas,
            "musica": usa("musica"), "efeitos": usa("efeitos"),
            "musica_de_onde": de_onde("musica"), "efeitos_de_onde": de_onde("efeitos")}


def motor_padrao(est: dict | None) -> bool:
    """O formato usa o motor HTML do Estúdio (render.py + cenas.json, --storyboard com a checagem e a previa-som.m4a,
    --conferir com a folha lado a lado)? É o contrato que o Documentário segue. Os outros dizem o próprio caminho."""
    return bool(est) and est.get("cenas", CENAS_PADRAO) == CENAS_PADRAO


def na_sandbox(c: str, sandbox: str, saida: str = "") -> str:
    """<sandbox> vira a pasta do vídeo e <modelo> a pasta do modelo do cliente (a sandbox mora dentro dela); com `saida`,
    <saida> vira o caminho ABSOLUTO do mp4 final. Comando sem <sandbox> nem <modelo> roda de dentro da sandbox (aí
    ../x é o arquivo x do modelo)."""
    lugar = any(m in c for m in ("<sandbox>", "{sandbox}", "<modelo>"))
    c = c.replace("<sandbox>", sandbox).replace("{sandbox}", sandbox).replace("<modelo>", str(Path(sandbox).parent))
    if saida:
        c = c.replace("<saida>", str(saida if Path(saida).is_absolute() else RAIZ / saida))
    return c if lugar else f'cd "{sandbox}" && {c}'


def comando(est: dict, nome: str, sandbox: str, saida: str = "") -> str:
    """Comando do motor (storyboard | render | conferir) pronto pra rodar da raiz do Estúdio."""
    return na_sandbox((est or {}).get("comandos", {}).get(nome) or COMANDOS_PADRAO[nome], sandbox, saida)


def _formato_json_do_modelo(nome_modelo: str) -> tuple[str, dict] | None:
    """Leitura leve (só os formato.json): qual formato tem esse modelo como variante."""
    if not nome_modelo or not FORMATOS.is_dir():
        return None
    for d in sorted(FORMATOS.iterdir()):
        dados = ler_json(d / "formato.json") if d.is_dir() else None
        if dados and nome_modelo in (dados.get("modelos") or []):
            return d.name, dados
    return None


def _dono_do_modelo(nome_modelo: str, fora: str = "") -> str:
    """O formato (tirando o `fora`) que já tem esse modelo como variante ("" se nenhum)."""
    if not nome_modelo or not FORMATOS.is_dir():
        return ""
    for d in sorted(FORMATOS.iterdir()):
        dados = ler_json(d / "formato.json") if d.is_dir() and d.name != fora else None
        if dados and nome_modelo in (dados.get("modelos") or []):
            return d.name
    return ""


def esteira_do_job(job: dict) -> dict | None:
    """Esteira que a TELA segue no vídeo (job["formato"]; vídeo antigo sem formato: pelo modelo). Nunca levanta erro.
    Formato de vídeo gravado devolve None: a tela é a do vídeo gravado (ver segue_esteira)."""
    try:
        dados = do_job(job)
        if not dados or not segue_esteira(dados):
            return None
        est = esteira(dados)
        if est:
            est["slug"] = dados["slug"]
        return est
    except Exception:
        return None


def _motor_pronto(base: Path, f: dict | None = None) -> bool:
    """Todos os arquivos do motor (esteira.motor_arquivos; sem a lista, render.py + index.html) estão na base."""
    return all((base / i).exists() for i in motor_itens(f))


def _vazia(p: Path) -> bool:
    return not any(x.is_file() and not x.name.startswith(".") for x in p.rglob("*"))


def variantes(f: dict) -> list[dict]:
    nomes = set(f.get("modelos") or [])
    out = []
    for c in _clientes():
        for m in c["modelos"]:
            if m in nomes:
                out.append({"cliente": c["nome"], "modelo": m})
    return out


def carregar(slug: str) -> dict | None:
    if not slug or Path(slug).name != slug:
        return None
    pasta = FORMATOS / slug
    dados = ler_json(pasta / "formato.json")
    if not dados:
        return None
    f = {**dados, "slug": slug, "pasta": pasta}
    f["exemplos"] = _exemplos(pasta, dados)
    f["previa"] = None
    if not f["exemplos"]:
        sbs = sorted((p for m in dados.get("modelos") or [] for p in (RAIZ / "clientes").glob(f"*/*Content/output/{m}/*/storyboard.jpg")),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        f["previa"] = rel(sbs[0]) if sbs else None
    f["variantes"] = variantes(f)
    f["entrada_label"] = ENTRADAS.get(f.get("entrada", ""), f.get("entrada", ""))
    f["na_tela"] = roda_pela_tela(f)   # False: a tela Criar avisa "peça pelo chat" em vez de dar erro na hora de criar
    regras = ler_json(pasta / "aprendizado" / "regras.json", {}) or {}
    f["n_regras"] = len(regras.get("regras") or [])
    f["estudo"] = estudo_estado(slug)   # "" (sem), "branco" (falta responder) ou "feito"
    f["regras_md"] = (pasta / "aprendizado" / "regras.md").exists()
    return f


@memoizado
def listar(ocultos: bool = False) -> list[dict]:
    """Formatos do catálogo. Os marcados "oculto" (sem exemplo ainda) só aparecem com ocultos=True."""
    if not FORMATOS.is_dir():
        return []
    out = [carregar(d.name) for d in FORMATOS.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))]
    out = [f for f in out if f and (ocultos or not f.get("oculto"))]
    return sorted(out, key=lambda f: (f.get("ordem", 99), f.get("titulo", "")))


def legenda_do(f: dict | None) -> dict:
    """O que o formato diz da legenda (formato.json → "legenda"): {"desligavel": bool, "como": str, "motivo": str}.
    Sem o campo (formato antigo) vale não desligável, que é o jeito seguro: o interruptor não aparece ligável."""
    d = (f or {}).get("legenda")
    if not isinstance(d, dict) or not isinstance(d.get("desligavel"), bool):
        return {"desligavel": False, "como": "", "motivo": "Este formato ainda não diz como desligar a legenda."}
    return {"desligavel": d["desligavel"], "como": str(d.get("como") or ""), "motivo": str(d.get("motivo") or "")}


def aceitam_video() -> list[dict]:
    """Os formatos que recebem um vídeo gravado como entrada (formato.json → "entrada" video ou video-ou-roteiro): a escolha
    do 'Usar em outro formato'. Fora: roteiro puro e filmagem de evento."""
    return [f for f in listar() if f.get("entrada") in ("video", "video-ou-roteiro")]


def de_modelo(nome_modelo: str) -> dict | None:
    """Qual formato um modelo de cliente pertence (pra mostrar o título amigável)."""
    for f in listar(ocultos=True):
        if nome_modelo in (f.get("modelos") or []):
            return f
    return None


GRUPOS = (("falando", "Pessoa falando"), ("animacao", "Animação"))   # formato.json → "grupo"


def grupo_de(f: dict) -> str:
    """O grupo do formato no catálogo. Sem o campo: vídeo gravado vai pra "falando", o resto (roteiro, motor) pra "animacao"."""
    g = f.get("grupo")
    if g in dict(GRUPOS):
        return g
    return "falando" if f.get("tipo") == "gravado" or f.get("entrada") == "video" else "animacao"


def catalogo() -> list[dict]:
    """O catálogo visual: [{"grupo", "titulo", "formatos": [...]}] na ordem, sem os ocultos. Cada formato traz
    slug, titulo, frase, video_exemplo (url do exemplo principal), poster, estilos (referências salvas, a principal primeiro)
    e formato (o dict completo de carregar, pra tela desenhar o cartão)."""
    por = {k: [] for k, _ in GRUPOS}
    for f in listar():
        ex = f["exemplos"][0] if f.get("exemplos") else None
        por[grupo_de(f)].append({
            "slug": f["slug"], "titulo": f.get("titulo", f["slug"]), "frase": f.get("frase", ""),
            "video_exemplo": ("/arquivo/" + quote(ex["video"])) if ex else None,
            "poster": ("/arquivo/" + quote(ex["poster_rel"])) if ex and ex.get("poster_rel") else None,
            "estilos": estudos(f["slug"]), "formato": f})
    return [{"grupo": k, "titulo": t, "formatos": por[k]} for k, t in GRUPOS]


def ocultos() -> list[dict]:
    """Os formatos escondidos (formato.json → "oculto": true), pra seção "Mais formatos (em teste)"."""
    return [f for f in listar(ocultos=True) if f.get("oculto")]


def estilos_do_cliente(cliente_nome: str) -> list[str]:
    """Os slugs dos formatos em que o cliente já tem modelo (pra mostrar "já usado por este cliente")."""
    c = _cliente(cliente_nome) if cliente_nome else None
    mods = set(c["modelos"]) if c else set()
    return [f["slug"] for f in listar(ocultos=True) if mods & set(f.get("modelos") or [])]


def garantir_avulso() -> dict:
    c = _cliente(AVULSO)
    if c:
        return c
    import novo_cliente
    return novo_cliente.criar(AVULSO, descricao="Vídeos sem cliente definido: identidade neutra, "
                                                "serve pra testar um formato ou fazer uma peça solta.")


# Ficam só na base do formato: o motor (render.py) acha música e demo lá quando a cópia do cliente não tem.
# Copiar dava 154 MB (38 músicas) + a demo/ por cliente.
SO_NA_BASE = ("audio/musicas", "demo")


def _ignora_da_base(base: Path, ignora_padrao):
    def ignora(dir_, nomes):
        out = list(ignora_padrao(dir_, nomes))
        try:
            pasta = Path(dir_).relative_to(base)
        except ValueError:
            return out
        for n in nomes:
            if (pasta / n).as_posix() in SO_NA_BASE and n not in out:
                out.append(n)
        return out
    return ignora


def usar(slug: str, cliente_nome: str) -> tuple[str, str]:
    """Garante que o cliente tem a variante deste formato e devolve (cliente, modelo)."""
    f = carregar(slug)
    if not f:
        raise ValueError("Formato não encontrado.")
    if not f.get("modelos"):
        raise ValueError("Este formato não precisa de modelo.")
    base = RAIZ / (f.get("base") or "")
    # Formato de motor com esteira só roda pela tela com a receita completa: status pronto e o motor inteiro na base.
    # O de vídeo gravado segue o fluxo de vídeo gravado (como antes da esteira): a base é o modelo, copiado abaixo.
    if segue_esteira(f) and (esteira(f) is None or f.get("status") != "pronto" or not f.get("base") or not _motor_pronto(base, f)):
        raise ValueError(NAO_PRONTO)
    c = garantir_avulso() if cliente_nome in ("", AVULSO) else _cliente(cliente_nome)
    if not c:
        raise ValueError(f"Cliente não encontrado: {cliente_nome}")
    for m in c["modelos"]:
        if m in f["modelos"]:
            return c["nome"], m
    nome = f["modelos"][0]
    if not f.get("base") or not base.is_dir():
        raise ValueError(f"O formato {f['titulo']} ainda não tem base pra copiar.")
    if _vazia(base):   # copiar pasta vazia criava um modelo sem motor (o vídeo saía genérico)
        raise ValueError(NAO_PRONTO)
    import novo_cliente
    partes = Path(f["base"]).parts
    # esteira.copiar_motor = false: o motor acha a raiz do Estúdio pelo próprio caminho e só roda da base.
    # O cliente ganha só a pasta do modelo (aprendizado e ficha); nada do motor é copiado.
    copiar = not (segue_esteira(f) and (esteira(f) or {}).get("copiar_motor") is False)
    if copiar and partes[0] == "clientes" and "modelos" in partes:
        novo_cliente.portar_modelo(c, partes[1], partes[partes.index("modelos") + 1], nome)
    else:
        dst = c["content"] / "modelos" / nome
        if copiar:
            shutil.copytree(base, dst, ignore=_ignora_da_base(base, novo_cliente._ignora))
        else:
            ensure(dst)
        apr = ensure(dst / "aprendizado")
        gravar_json(apr / "regras.json", {
            "modelo": nome, "cliente": c["nome"], "formato": slug, "regras": [],
            "descricao": f"Criado a partir do formato {f['titulo']} em {hoje()}. As regras do formato "
                         f"(formatos/{slug}/aprendizado/) valem junto com as deste cliente.",
        })
        (apr / "historico.jsonl").write_text("", encoding="utf-8")
        if not (dst / "ficha.json").exists():
            gravar_json(dst / "ficha.json", {"titulo": f["titulo"], "resumo": f.get("frase", ""),
                                             "motor": f.get("motor", ""), "tipo": "completo",
                                             "formato": slug, **({} if copiar else {"roda_da_base": f["base"]})})
        novo_cliente._registrar_no_claude_md(c, nome, "formato", slug)
    return c["nome"], nome


# ───────────────────── o que já aprendemos / o que vai acontecer ─────────────────────

def _regras_md(p: Path) -> list[dict]:
    """Lê a tabela de regras em Markdown (| ID | Regra | Origem | Checagem |)."""
    import re
    out = []
    titulos = ler_json(p.with_name("titulos.json"), {}) or {}
    for l in p.read_text(encoding="utf-8").splitlines() if p.exists() else []:
        cols = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cols) >= 2 and re.fullmatch(r"[A-Z]\d+[a-z]?", cols[0]):
            txt = re.sub(r"\*\*|`", "", cols[1])
            out.append({"id": cols[0], "titulo": titulos.get(cols[0]) or titulo_regra({"texto": txt}), "texto": txt, "categoria": ""})
    return out


def titulo_regra(r: dict) -> str:
    """Título curto pra tela: o da regra, senão a 1ª frase do texto (cortada em ~70 letras)."""
    t = (r.get("titulo") or "").strip()
    if t:
        return t
    txt = re.sub(r"[🔴🟡🟢⚠️✅❌]\s*", "", str(r.get("texto") or "")).strip()
    frase = re.split(r"(?<=[.:;])\s", txt, maxsplit=1)[0].rstrip(".:;")
    return frase if len(frase) <= 72 else frase[:70].rsplit(" ", 1)[0] + "…"


def _regras_json(p: Path) -> list[dict]:
    d = ler_json(p, {}) or {}
    out = [{"id": r.get("id", ""), "titulo": titulo_regra(r), "texto": r.get("texto", ""), "evitar": r.get("evitar", ""),
            "peso": r.get("peso", 1), "categoria": r.get("categoria", ""), "promovida": r.get("promovida", "")}
           for r in d.get("regras") or [] if r.get("texto")]
    return sorted(out, key=lambda r: -float(r.get("peso") or 1))


def _com_origem(regras: list[dict], hist: Path) -> None:
    """Cada regra ganha "origem": as correções do histórico que a criaram ou mudaram (mais recentes primeiro, até 2)."""
    if not hist.is_file():
        return
    por_regra: dict[str, list[dict]] = {}
    for l in hist.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("regra"):
            por_regra.setdefault(e["regra"], []).append({"texto": e.get("texto", ""), "data": str(e.get("createdAt", ""))[:10],
                                                          "video": e.get("job", "")})
    for r in regras:
        r["origem"] = list(reversed(por_regra.get(r["id"], [])))[:2]


def definir_principal(slug: str, nome: str) -> bool:
    """Troca o estilo que o formato segue: só a pasta escolhida em estudos/ fica com o arquivo PRINCIPAL."""
    base = FORMATOS / slug / "estudos"
    alvo = base / nome
    if not alvo.is_dir() or Path(nome).name != nome:
        return False
    for d in base.iterdir():
        if d.is_dir() and (d / "PRINCIPAL").exists():
            (d / "PRINCIPAL").unlink()
    (alvo / "PRINCIPAL").write_text("")
    return True


def aprendizado(slug: str, cliente_nome: str = "") -> dict:
    """Regras em camadas: as do formato (valem pra todo cliente) e as do cliente nesse formato."""
    f = carregar(slug)
    if not f:
        return {"formato": [], "cliente": [], "cliente_nome": cliente_nome}
    apr = f["pasta"] / "aprendizado"
    do_formato = _regras_json(apr / "regras.json") + _regras_md(apr / "regras.md")
    _com_origem(do_formato, apr / "historico.jsonl")
    do_cliente = []
    c = _cliente(cliente_nome) if cliente_nome else None
    if c:
        for m in c["modelos"]:
            if m in (f.get("modelos") or []):
                ids_formato = {r["id"] for r in do_formato}
                do_cliente = sorted((r for r in _regras_json(c["content"] / "modelos" / m / "aprendizado" / "regras.json")
                                     if not (r.get("promovida") and r["promovida"] in ids_formato)),
                                    key=lambda r: -float(r.get("peso") or 1))
    return {"formato": do_formato, "cliente": do_cliente, "cliente_nome": cliente_nome}


TIPOS_USO = ("gratis", "pago", "assinatura")


def _usd(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _usos_declarados(f: dict) -> list[dict]:
    """Itens de "usa" do formato.json: {"oque", "quem", "tipo": gratis|pago|assinatura, "usd" (só no pago, opcional)}.
    Ignora o que vier incompleto ou com tipo desconhecido, pra uma linha errada não derrubar a tela."""
    return [u for u in f.get("usa") or []
            if isinstance(u, dict) and u.get("oque") and u.get("quem") and u.get("tipo") in TIPOS_USO]


PASSOS_PADRAO = {
    "roteiro": ["Escreva a ideia, ou clique em Me ajuda a pensar: sai um roteiro pronto.", "Confira o roteiro e mande criar.",
                "Você aprova o storyboard (os quadros, um por cena).", "O vídeo fica pronto. Seu comentário vira regra pro próximo."],
    "video": ["Envie o vídeo gravado.", "O Estúdio monta o plano das cenas e você aprova.",
              "Prévias das partes mais difíceis.", "O vídeo fica pronto. Seu comentário vira regra pro próximo."],
}


def material_fora(briefing: dict | None, f: dict | str | None = None) -> list[dict]:
    """Aviso cedo (a conversa do passo 0 usa): o material liberado no briefing que o formato não aceita
    (formato.json → "material_aceito"). Sem `f` vale o formato sugerido no briefing. Cada item volta com "aviso".
    Formato que ainda não declara a lista não tem lugar garantido pra nada: tudo volta."""
    b = briefing or {}
    if f is None or isinstance(f, str):
        slug = f if isinstance(f, str) else str((b.get("formato_sugerido") or {}).get("slug") or "")
        f = carregar(slug) if slug else None
    if not f:
        return []
    aceito = f.get("material_aceito") if isinstance(f.get("material_aceito"), list) else None
    nome = f.get("titulo") or f.get("slug") or "este formato"
    fora = []
    for m in b.get("material_liberado") or []:
        if not isinstance(m, dict) or not m.get("arquivo"):
            continue
        papel = str(m.get("papel") or "").strip()
        if aceito is not None and papel in aceito:
            continue
        aviso = (f"O {nome} ainda não diz que material aceita: onde entra {m['arquivo']}?" if aceito is None else
                 f"{m['arquivo']} está sem papel: diga onde ele entra." if not papel else
                 f"O {nome} ainda não tem lugar pra {papel}: uso de outro jeito ou troco de formato?")
        fora.append({**m, "aviso": aviso})
    return fora


def layout_pedido(ref) -> list[str]:
    """Os layouts que a referência pede: o "layout" que a conversa marcou ou, sem ele, as palavras do "o que copiar"
    ("tela dividida", "quadradinho no canto"...). Aceita o briefing inteiro, a referência dele ou só o texto."""
    if isinstance(ref, dict) and isinstance(ref.get("referencia"), dict):
        ref = ref["referencia"]
    if isinstance(ref, dict):
        marcado = ref.get("layout")
        achou = [str(x).strip().lower() for x in (marcado if isinstance(marcado, list) else [marcado]) if x]
        achou = [x for x in achou if x in LAYOUTS]
        if achou:
            return list(dict.fromkeys(achou))
        ref = ref.get("o_que_copiar") or ""
    t = str(ref or "").lower()
    return [k for k, rx in _PALAVRAS_LAYOUT if re.search(rx, t)]


def aviso_layout(ref, f: dict | str | None = None) -> dict | None:
    """Aviso cedo (a conversa do passo 0 e o Criar usam, antes de gastar): a referência pede um layout que o formato não
    sabe montar (formato.json → "layouts")? None se não pede nenhum ou se o formato tem. Senão: {"layout", "tem",
    "outros" (formatos à mostra que já fazem), "aviso"}, a frase pro João escolher entre trocar de formato e o formato
    ganhar o layout. Sem `f` vale o formato sugerido no briefing."""
    b = ref if isinstance(ref, dict) else {}
    if f is None or isinstance(f, str):
        slug = f if isinstance(f, str) else str((b.get("formato_sugerido") or {}).get("slug") or "")
        f = carregar(slug) if slug else None
    if not f:
        return None
    tem = [x for x in f.get("layouts") or [] if x in LAYOUTS] if isinstance(f.get("layouts"), list) else []
    falta = [x for x in layout_pedido(ref) if x not in tem]
    if not falta:
        return None
    lay, nome = falta[0], f.get("titulo") or f.get("slug")
    outros = [g for g in listar() if g.get("slug") != f.get("slug") and lay in (g.get("layouts") or [])]
    faz = " ou ".join(LAYOUTS[x].split(" (")[0] for x in tem) or "outro jeito"
    pede = LAYOUTS[lay].split(" (")[0]
    if outros:
        aviso = (f"A referência usa {pede} e o formato {nome} só faz {faz}. Quer trocar pro formato "
                 f"{' ou '.join(g['titulo'] for g in outros[:2])}, que já faz assim, ou ensinar o {nome} a fazer {pede} "
                 "(vira uma tarefa nova, antes deste vídeo)?")
    else:
        aviso = (f"A referência usa {pede} e nenhum formato faz isso ainda (o {nome} só faz {faz}). Quer ensinar o "
                 f"{nome} a fazer {pede} (vira uma tarefa nova, antes deste vídeo) ou seguir com {faz}?")
    return {"layout": lay, "tem": tem, "outros": [g["slug"] for g in outros], "aviso": aviso}


def passos(f: dict) -> list[str]:
    """Como funciona, em 4 passos curtos (formato.json → "passos"; senão o padrão pelo que o João manda)."""
    ent = f.get("entrada", "video")
    return f.get("passos") or PASSOS_PADRAO.get("roteiro" if ent == "roteiro" else "video")


SEM_CENAS = ("frase-fixa", "documentario")
ESCOLHA_CENAS = {"campo": "cenas", "rotulo": "Cenas de apoio", "tipo": "um",
                 "opcoes": ["B-roll real (grátis)", "Gerada por IA (pago, centavos)", "Sem cenas de apoio"], "padrao": ""}
QUANTIDADE_CENAS = 3   # teto de cenas de apoio quando o formato não diz outro (escolhas → "cenas" → "quantidade")


def quantidade_cenas(f: dict | None) -> int | None:
    """O teto de cenas de apoio que o PRÓPRIO formato declara (formato.json → escolhas → a de campo "cenas" →
    "quantidade", de 1 a 12), ou None. A Tela dividida tem cena embaixo o tempo todo: o teto genérico de 3 não serve."""
    for e in (f or {}).get("escolhas") or []:
        if isinstance(e, dict) and e.get("campo") == "cenas":
            q = e.get("quantidade")
            if isinstance(q, int) and not isinstance(q, bool) and 1 <= q <= 12:
                return q
    return None


def roda_pela_tela(f: dict | None) -> bool:
    """A tela Criar consegue usar este formato? Formato de motor com esteira só roda com a receita completa (status
    pronto, esteira válida e o motor inteiro na base), a mesma conta do usar(). Os outros seguem o fluxo de sempre."""
    if not f:
        return False
    if not segue_esteira(f):
        return True
    base = RAIZ / (f.get("base") or "")
    return bool(esteira(f) and f.get("status") == "pronto" and f.get("base") and _motor_pronto(base, f))


def storyboard_proprio(f: dict | None) -> bool:
    """Formato de vídeo gravado com storyboard próprio (esteira.comandos.storyboard diferente da ferramenta padrão, ex.:
    o storyboard.py do Cinematográfico): a ferramenta genérica não pode refazer o storyboard.jpg por cima do dele."""
    if not f or tipo(f) != "gravado" or not f.get("esteira"):
        return False
    est = esteira(f)
    return bool(est) and est["comandos"].get("storyboard", "").strip() != COMANDOS_GRAVADO["storyboard"]


def do_job(job: dict) -> dict | None:
    """formato.json (com "slug") do vídeo: job["formato"] ou, no vídeo antigo, o formato que tem o modelo. Leve e sem erro."""
    try:
        slug = (job or {}).get("formato") or ""
        dados = ler_json(FORMATOS / slug / "formato.json") if slug and Path(slug).name == slug else None
        if dados:
            return {**dados, "slug": slug}
        achado = _formato_json_do_modelo((job or {}).get("modelo", ""))
        return {**achado[1], "slug": achado[0]} if achado else None
    except Exception:
        return None


def escolhas(f: dict) -> list[dict]:
    """O que a tela Criar pergunta pra esse formato: as do formato.json + "Cenas de apoio" pra quem usa b-roll.
    Formato de motor com esteira não ganha a pergunta: as cenas são da receita dele."""
    out = list(f.get("escolhas") or [])
    if f.get("slug") not in SEM_CENAS and not segue_esteira(f) and not any(e.get("campo") == "cenas" for e in out):
        out.append(ESCOLHA_CENAS)
    return out


def previsao(slug: str) -> dict:
    """O que o formato usa e quanto costuma custar.

    Se o formato.json declara "usa" (e "estimativa"), vale o que ele declara: é o que o formato USA DE VERDADE.
    Sem isso, cai numa lista genérica pela entrada (reserva). Só afirma o que o catálogo sabe.
    Devolve {"usa": [(oque, quem, tipo)], "pago_minimo", "total"} (a tela usa "usa" e "total").
    """
    f = carregar(slug) or {}
    ent = f.get("entrada", "video")
    tabela = []
    try:
        import producao as _p
        for j in _p.listar():
            if j.get("modelo") in (f.get("modelos") or []):
                t = sum(float(e.get("custo_usd") or 0) for e in j.get("execucoes", []))
                if t:
                    tabela.append(t)
    except Exception:
        pass
    est = (f.get("estimativa") or "").strip().rstrip(".")
    media = (f" Média dos vídeos já feitos: equivale a ~US$ {_usd(sum(tabela) / len(tabela))} por vídeo (incluso na assinatura)." if tabela else
             f" Estimativa até termos média: {est or 'equivale a ~US$ 1 a 4 por vídeo no Opus (incluso na assinatura); bem menos no Sonnet'}.")
    edicao = ("Edição e conferência (IA)", "Claude Code: gasta tokens da sua assinatura. Não sai do bolso, mas consome sua cota." + media, "assinatura")
    real = f" Real (média): equivale a ~US$ {_usd(sum(tabela) / len(tabela))} (incluso na assinatura)." if tabela else ""
    declarados = _usos_declarados(f)
    if declarados:
        pagos = [u for u in declarados if u["tipo"] == "pago"]
        tipico = sum(float(u.get("usd") or 0) for u in pagos)
        if tipico:
            pago = (f"Pago de verdade: US$ 0 se você não aprovar nada pago; ~US$ {_usd(tipico)} com "
                    + " + ".join(u["oque"] for u in pagos if u.get("usd")) + ".")
        elif pagos:
            pago = "Pago de verdade: US$ 0 por padrão; " + ", ".join(u["oque"] for u in pagos) + " só se você pedir."
        else:
            pago = "Pago de verdade: US$ 0 (nada neste estilo sai do bolso)."
        return {"usa": [edicao] + [(u["oque"], u["quem"], u["tipo"]) for u in declarados],
                "pago_minimo": 0.0, "pago_tipico": round(tipico, 4),
                "total": f"IA: {est or 'equivale a ~US$ 0,50 a 2 no Opus (incluso na assinatura)'}.{real} {pago}"}
    usa = [edicao]
    if ent == "roteiro":
        usa.append(("Narração", "VoiceStudio (grátis, no seu Mac) ou ElevenLabs/sua voz", "gratis"))
    if ent in ("video", "video-ou-roteiro"):
        usa.append(("Transcrição", "Groq (cota grátis)", "gratis"))
    sem_cenas = slug in SEM_CENAS
    if not sem_cenas:
        usa.append(("Cenas reais (b-roll)", "YouTube, Pexels, Pixabay, Wikimedia (grátis)", "gratis"))
        usa.append(("Cenas geradas por IA", "kie.ai, só se você pedir numa cena: ~US$ 0,004 a 0,05 por imagem, ~US$ 0,12 a 0,70 por animação", "pago"))
    usa.append(("Montagem e render", (f.get("motor", "") + " no seu Mac").strip(), "gratis"))
    voz = 0.03 if ent in ("roteiro", "video-ou-roteiro") else 0.0
    total = (f"IA: {est or 'equivale a ~US$ 0,50 a 2 no Opus (incluso na assinatura)'}.{real} "
             f"Pago de verdade: ~US$ {_usd(voz)}{' (voz)' if voz else ''}" + (" + cenas por IA só se você pedir." if not sem_cenas else "."))
    return {"usa": usa, "pago_minimo": voz, "total": total}


def copia_leve(src: Path, dst: Path) -> bool:
    """Cópia leve pra tocar na tela (540 px no vertical) + capa .jpg."""
    import subprocess
    if dst.exists() or not Path(src).exists():
        return dst.exists()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "scale='if(gt(iw,ih),960,540)':-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", str(dst)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(dst), "-frames:v", "1",
                    str(dst.with_suffix(".jpg"))], check=False)
    return dst.exists()


MODELO_DIR = "_modelo"   # formatos/_modelo: todo formato novo nasce dele (já cumpre o CONTRATO)


def _ignora_modelo(dir_, nomes):
    return [n for n in nomes if n == "__pycache__" or n.endswith(".pyc") or n == ".DS_Store"]


def novo_formato(slug: str, titulo: str = "", frase: str = "", tipo_: str = "motor", base: str = "",
                 modelo: str = "", render: str = "", motor: str = "", entrada: str = "") -> Path:
    """Formato novo a partir de formatos/_modelo (formato.json, COMO-FAZER.md, aprendizado/ zerado e, se for de motor,
    base/ com o esqueleto do motor). Nasce "receita": vira "pronto" quando o validar() não acusar falta.

    tipo_ "gravado": a base/ do modelo sai, "base" aponta o modelo do cliente e "render" é o comando do render dele."""
    from _comum import make_slug
    slug = (slug or "").strip()
    if not slug or make_slug(slug, 60) != slug or slug.startswith(("_", ".")):
        dica = make_slug(slug, 60) if re.search(r"[A-Za-z0-9]", slug) else ""
        raise ValueError("Nome do formato: só letras minúsculas, números e hífen, sem acento nem espaço (ex.: papel-recortado)."
                         + (f" Tente: {dica}" if dica and dica != slug else ""))
    if tipo_ not in TIPOS:
        raise ValueError("Tipo do formato: motor ou gravado.")
    src, d = FORMATOS / MODELO_DIR, FORMATOS / slug
    if not (src / "formato.json").is_file():
        raise ValueError("Falta o formatos/_modelo pra copiar.")
    if (d / "formato.json").exists():
        raise ValueError(f"O formato {slug} já existe (formatos/{slug}/). Escolha outro nome.")
    titulo = titulo or slug.replace("-", " ").capitalize()   # sem título, a tela mostrava "TROQUE: nome do formato"
    if tipo_ == "gravado" and base:   # a base é o modelo do cliente: o render do gerar.sh vem dela
        base = str(base).strip().rstrip("/")
        if Path(base).is_absolute():
            try:
                base = str(Path(base).resolve().relative_to(RAIZ.resolve()))
            except ValueError:
                raise ValueError(f"A base precisa estar dentro do Estúdio (clientes/<Nome>/<x>Content/modelos/<modelo>): {base}")
        if not (RAIZ / base).is_dir() or _vazia(RAIZ / base):
            raise ValueError(f"A base {base} não existe ou está vazia. Use a pasta de um modelo que já funciona: "
                             "clientes/<Nome>/<x>Content/modelos/<modelo>.")
        render = render or render_do_gerar(RAIZ / base / "gerar.sh")
        # O nome do modelo vem da base só se nenhum outro formato já usa esse modelo: dois formatos com o mesmo modelo
        # faziam o vídeo antigo (sem "formato") cair no formato errado. Usado: o formato ganha modelo próprio (o slug),
        # que o usar() copia da base pro cliente com o aprendizado zerado.
        if not modelo:
            modelo = Path(base).name if not _dono_do_modelo(Path(base).name) else slug
    modelo = modelo or slug
    dono = _dono_do_modelo(modelo)
    if dono:
        raise ValueError(f"O modelo {modelo} já é do formato {dono}. Escolha outro nome com --modelo.")
    shutil.copytree(src, d, ignore=_ignora_modelo, dirs_exist_ok=True)
    dados = ler_json(d / "formato.json", {}) or {}
    dados.update({"tipo": tipo_, "status": "receita", "modelos": [modelo]})
    for k, v in (("titulo", titulo), ("frase", frase), ("motor", motor), ("entrada", entrada)):
        if v:
            dados[k] = v
    est = dados.get("esteira") if isinstance(dados.get("esteira"), dict) else {}
    if tipo_ == "motor":
        dados["base"] = f"formatos/{slug}/base"
        motor_py = d / "base" / "render.py"   # o motor genérico acha o exemplo principal pelo slug do formato
        if motor_py.is_file():
            motor_py.write_text(motor_py.read_text(encoding="utf-8").replace(
                f'FORMATO = "{MODELO_DIR}"', f'FORMATO = "{slug}"', 1), encoding="utf-8")
    else:
        shutil.rmtree(d / "base", ignore_errors=True)
        dados["base"] = base
        dados["motor"] = motor or "ffmpeg + PIL (scripts do modelo)"
        est.pop("motor_arquivos", None)
        est.pop("motor", None)
        est["comandos"] = {**COMANDOS_GRAVADO, **({"render": render} if render else {})}
    dados["esteira"] = est
    gravar_json(d / "formato.json", dados)
    cf = d / "COMO-FAZER.md"
    if cf.is_file() and titulo:
        cf.write_text(cf.read_text(encoding="utf-8").replace(f"{MARCA_MODELO} nome do formato", titulo, 1), encoding="utf-8")
    gravar_json(d / "aprendizado" / "regras.json", {"formato": slug, "regras": []})
    return d


def render_do_gerar(gerar: Path) -> str:
    """Comando de render pro gerar.sh de um modelo de vídeo gravado, visto de dentro da sandbox (<modelo>/_sandbox-<slug>):
    a sandbox não tem cópia do script, então é ../gerar.sh; zsh quando o script é zsh (os do dividido usam ${=VAR},
    typeset -A, e quebram no bash); --dir . quando o script aceita a pasta do vídeo. "" se não há gerar.sh."""
    gerar = Path(gerar)
    if not gerar.is_file():
        return ""
    try:
        txt = gerar.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        txt = ""
    shell = "zsh" if "zsh" in (txt.splitlines() or [""])[0] else "bash"
    return f"{shell} ../gerar.sh" + (" --dir ." if "--dir" in txt else "")


def registrar_de_referencia(nome: str, ficha: dict, cliente_nome: str, pasta_modelo: Path, video_ref: Path) -> Path:
    """Formato criado a partir de uma referência entra no catálogo, nascido de formatos/_modelo (tipo gravado, base =
    o modelo construído, render = o gerar.sh dele), com o vídeo que inspirou de exemplo principal (com folha).
    Fica "receita" até alguém escrever os passos dele no COMO-FAZER e o validar() não acusar falta."""
    d = FORMATOS / nome
    if not (d / "formato.json").is_file():
        novo_formato(nome, titulo=ficha.get("titulo") or nome.replace("-", " ").capitalize(), frase=ficha.get("resumo", ""),
                     tipo_="gravado", base=rel(pasta_modelo), modelo=nome, motor=ficha.get("motor", ""), entrada="video",
                     render=render_do_gerar(Path(pasta_modelo) / "gerar.sh"))
    ensure(d / "aprendizado")
    dados = ler_json(d / "formato.json", {}) or {}
    exs = []
    try:
        if copia_leve(video_ref, d / "exemplo-1.mp4"):
            ex = {"arquivo": "exemplo-1.mp4", "poster": "exemplo-1.jpg", "legenda": "Referência que inspirou"}
            if fazer_folha(d / "exemplo-1.mp4", _arq_folha(d / "exemplo-1.mp4")):
                ex["folha"] = _arq_folha(d / "exemplo-1.mp4").name
            exs.append(ex)
    except Exception:
        pass
    dados.update({"ordem": 40, "modelos": [nome], "base": rel(pasta_modelo), "exemplos": exs,
                  "origem": f"referência ({cliente_nome})"})
    gravar_json(d / "formato.json", dados)
    if not (d / "aprendizado" / "regras.json").exists():
        gravar_json(d / "aprendizado" / "regras.json", {"regras": []})
    return d


# ───────────────────── estudos de referência: a base de ideias do formato ─────────────────────

def estudos(slug: str) -> list[dict]:
    pasta = FORMATOS / slug / "estudos"
    out = []
    for d in sorted(pasta.iterdir()) if pasta.is_dir() else []:
        if not d.is_dir():
            continue
        # só o 1º nível: estudo-quadros/folhas tem dezenas de folhas a 30 fps que não são storyboard
        imgs = sorted(p for p in d.glob("*") if p.suffix.lower() in (".jpg", ".png") and p.is_file() and not p.name.startswith("capa"))
        vids = sorted(p for p in d.glob("*") if p.suffix.lower() in (".mp4", ".mov") and p.is_file())
        md = d / "ESTUDO.md"
        roteiros = [x.read_text(encoding="utf-8") for x in sorted(d.glob("ROTEIRO*.md"))]
        principal = (d / "PRINCIPAL").exists()   # arquivo vazio PRINCIPAL = é o estilo de edição que manda no formato
        out.append({"principal": principal, "roteiros": "\n\n".join(roteiros), "nome": d.name, "titulo": d.name.split("-", 1)[-1].replace("-", " ").capitalize(),
                    "storyboards": [rel(p) for p in imgs], "videos": [rel(p) for p in vids],
                    "estudo": md.read_text(encoding="utf-8") if md.exists() else ""})
    out.sort(key=lambda e: not e["principal"])   # o principal vai primeiro (sort estável: o resto fica em ordem)
    return out


def virar_referencia(slug: str, video: Path, titulo: str, origem: str = "") -> Path:
    """Vídeo nosso que o João gostou vira mais uma referência do estilo (estudos/NN-titulo/, como as de fora).
    É base pra escolher no Criar, não molde: o próximo vídeo pega o jeito, nunca o conteúdo."""
    import shutil
    from _comum import make_slug
    base = ensure(FORMATOS / slug / "estudos")
    for d in base.iterdir():   # a mesma origem não entra duas vezes
        if d.is_dir() and origem and origem in ((d / "ESTUDO.md").read_text(encoding="utf-8") if (d / "ESTUDO.md").exists() else ""):
            return d
    n = len([d for d in base.iterdir() if d.is_dir()]) + 1
    d = ensure(base / f"{n:02d}-{make_slug(titulo or 'nosso', 40)}")
    _clonar(video, d / f"video-1{Path(video).suffix.lower()}")
    _storyboard(d / f"video-1{Path(video).suffix.lower()}", d / "storyboard-1.jpg")
    (d / "ESTUDO.md").write_text(f"# {titulo}\n\nVídeo nosso aprovado, guardado como referência em {hoje()}"
                                 + (f" (de {origem})" if origem else "") + ". Base de estilo, não molde.\n", encoding="utf-8")
    return d


def estudo_escolhido(slug: str, nome: str) -> dict | None:
    """A referência que o João escolheu no Criar pra este vídeo (nome da pasta em estudos/)."""
    return next((e for e in estudos(slug) if e["nome"] == nome), None) if nome else None


def referencias_mistura(slug: str) -> list[dict]:
    """As referências de um estilo que dá pra pôr na mistura de estilos do Criar: as estudadas (estudos/<NN-nome>/) e, se o estilo
    não tem nenhuma, os exemplos dele (nome "exemplo-N"). Cada uma: {nome, titulo, video, principal, caminho}."""
    est = estudos(slug)
    if est:
        return [{"nome": e["nome"], "titulo": e["titulo"], "video": (e["videos"] or [""])[0], "principal": e["principal"],
                 "caminho": f"formatos/{slug}/estudos/{e['nome']}"} for e in est]
    f = carregar(slug) or {}
    return [{"nome": f"exemplo-{i}", "titulo": (x.get("legenda") or f"Exemplo {i}")[:70], "video": f"formatos/{slug}/{x['arquivo']}",
             "principal": i == 1, "caminho": f"formatos/{slug}/{x['arquivo']}"}
            for i, x in enumerate(f.get("exemplos") or [], 1) if x.get("arquivo")]


def ref_caminho(slug: str, nome: str) -> str | None:
    """Onde está a referência `nome` do estilo `slug` (estudo ou exemplo), relativo à raiz; None se não existe."""
    return next((r["caminho"] for r in referencias_mistura(slug) if r["nome"] == nome), None)


def _storyboard(video: Path, destino: Path) -> None:
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    dur = max(1.0, float((r.stdout or "1").strip() or 1))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps=12/{dur:.2f},scale=-2:300,tile=6x2",
                    "-frames:v", "1", str(destino)], check=False)


def adicionar_referencia(slug: str, arquivos: list[Path], links: list[str], nome: str = "") -> Path:
    """Guarda vídeos de referência no formato e faz o storyboard de cada um (local, sem IA)."""
    import shutil, subprocess
    base = ensure(FORMATOS / slug / "estudos")
    n = len([d for d in base.iterdir() if d.is_dir()]) + 1
    from _comum import make_slug
    d = ensure(base / f"{n:02d}-{make_slug(nome or 'referencia', 40)}")
    vids = []
    for i, a in enumerate(arquivos, 1):
        dst = d / f"video-{i}{Path(a).suffix.lower()}"
        shutil.move(str(a), str(dst)); vids.append(dst)
    for j, url in enumerate(links, len(vids) + 1):
        dst = d / f"video-{j}.mp4"
        subprocess.run(["yt-dlp", "-q", "-f", "mp4/best", "-o", str(dst), url], check=False, timeout=300)
        if dst.exists():
            vids.append(dst)
    for v in vids:
        _storyboard(v, d / f"storyboard-{v.stem.split('-')[-1]}.jpg")
    (d / "ESTUDO.md").write_text(f"# {nome or 'Referência'}\n\nAdicionada em {hoje()}. Fontes: "
                                 + ", ".join(links or [v.name for v in vids]) +
                                 "\n\nAinda sem estudo escrito: olhe os storyboards. Na próxima produção deste formato, "
                                 "a IA pode resumir aqui o que dá pra aproveitar.\n", encoding="utf-8")
    return d


# ───────────────────── referência em passos: estuda UMA vez, sem IA ─────────────────────
# formatos.py referencia <slug> <video>: o vídeo vira exemplo do formato (cópia leve, capa e folha de quadros com o
# segundo marcado) e o formato ganha um ESTUDO.md com perguntas curtas, respondido UMA vez. Depois disso cada vídeo
# só LÊ o ESTUDO.md: ninguém reestuda a referência (era o que mais gastava IA num formato novo).

ESTUDO = "ESTUDO.md"
_RESPOSTA = re.compile(r"^\s*R:\s*(.*)$")
PERGUNTAS_ESTUDO = (
    ("Ritmo", ("Quanto dura cada cena, em segundos? Como é a troca (corte seco, zoom, passagem)?",
               "O que aparece nos 3 primeiros segundos (o gancho)?")),
    ("Legenda", ("Tem legenda? Onde fica (peito, meio, embaixo), quantas palavras por vez, que cor e que destaque?",)),
    ("Enquadramento", ("Como a pessoa ou o assunto aparece (rosto, peito, tela cheia, dividida, recortada)?",
                       "O que entra por cima (card, foto, cena de filme, número)?")),
    ("Som", ("Música: tem? Que clima e que volume (baixa sob a fala)?", "Efeitos: quais e em que momento?")),
    ("Não copiar", ("O que é só do conteúdo desta referência e não vale pro formato?",)),
)


def _medir_referencia(video: Path) -> dict:
    """O que o ffmpeg mede sozinho (grátis): duração, tamanho, cortes de cena e se tem som."""
    import subprocess
    info = ffprobe(video) or {}
    dur = float(info.get("duracao") or 0)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(video)],
                       capture_output=True, text=True)
    try:
        streams = json.loads(r.stdout or "{}").get("streams") or []
    except ValueError:
        streams = []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    cortes = None
    tempos: list = []
    try:
        c = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vf",
                            "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=300)
        tempos = [round(float(x), 1) for x in re.findall(r"pts_time:([\d.]+)", c.stderr)]
        cortes = len(tempos)
    except Exception:
        pass
    w, h = v.get("width") or 0, v.get("height") or 0
    return {"duracao": round(dur, 1), "largura": w, "altura": h,
            "proporcao": "9:16" if h > w else "16:9" if w > h else "1:1" if w else "",
            "cortes": cortes, "cortes_s": tempos, "a_cada_s": round(dur / (cortes + 1), 1) if cortes is not None and dur else None,
            "som": any(s.get("codec_type") == "audio" for s in streams)}


def _texto_estudo(titulo: str, ex: dict, origem: str, m: dict) -> str:
    medido = [f"{str(m['duracao']).replace('.', ',')} s"] if m.get("duracao") else []
    if m.get("largura"):
        medido.append(f"{m['largura']}x{m['altura']} ({m['proporcao']})")
    if m.get("cortes") is not None:
        medido.append(f"{m['cortes']} cortes de cena" + (f" (1 a cada {str(m['a_cada_s']).replace('.', ',')} s)"
                                                         if m.get("a_cada_s") else ""))
    medido.append("com som" if m.get("som") else "sem som")
    linhas = [f"# Estudo da referência: {titulo}", "",
              "> Isto é estilo. Roteiro, textos, pessoas e cores de outro cliente não vêm daqui.", "",
              f"Responda UMA vez, olhando a folha `{ex.get('folha') or ex['arquivo']}` (o segundo está em cada quadro) e o "
              "vídeo. Resposta curta, com número, na linha que começa com R.",
              "Depois disso cada vídeo deste formato só LÊ este arquivo: ninguém reestuda a referência. O que valer pra "
              "todo vídeo vira passo no COMO-FAZER.md ou regra em aprendizado/regras.json.", "",
              f"Referência: `{ex['arquivo']}` · fonte: {origem} · {hoje()}",
              f"Medido sozinho (ffmpeg): {' · '.join(medido)}"]
    for tit, perguntas in PERGUNTAS_ESTUDO:
        linhas += ["", f"## {tit}"]
        for q in perguntas:
            linhas += [f"- {q}", "  R:"]
    return "\n".join(linhas) + "\n"


def estudo_estado(slug: str) -> str:
    """ "" = o formato não tem ESTUDO.md · "branco" = nenhuma resposta (R:) preenchida · "feito"."""
    p = FORMATOS / str(slug or "") / ESTUDO
    if not slug or not p.is_file():
        return ""
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return ""
    respostas = [m.group(1).strip() for l in txt.splitlines() if (m := _RESPOSTA.match(l))]
    return "feito" if any(respostas) else "branco"


def estudo_txt(slug: str) -> str:
    """O que o pedido à IA diz do ESTUDO.md: lê o feito (sem reestudar), responde UMA vez o em branco. "" sem estudo."""
    e = estudo_estado(slug)
    if e == "feito":
        return (f"formatos/{slug}/{ESTUDO} já resume o ESTILO da referência (ritmo, legenda, enquadramento, som): use como estilo; "
                "o conteúdo vem do vídeo novo. Não reestude a referência nem extraia quadros dela.")
    if e == "branco":
        return (f"formatos/{slug}/{ESTUDO} está em branco: responda UMA vez cada linha R: (curto, com número), olhando a "
                "folha do exemplo principal; os próximos vídeos só leem.")
    return ""


def e_video(p: Path) -> bool:
    """O ffprobe acha imagem e duração? (arquivo de texto, áudio solto ou vídeo quebrado: não)."""
    info = ffprobe(Path(p)) or {}
    return bool(info.get("largura") and info.get("altura") and (info.get("duracao") or 0) > 0)


ESTUDO_QUADROS = "estudo-quadros"   # formatos/<slug>/estudo-quadros/: a régua medida quadro a quadro (estudo_quadros.py)


def estudar_quadros(slug: str, video: Path, fala: bool | None = None) -> dict:
    """Estudo quadro a quadro da referência (o padrão do Estúdio). O 1º vira a régua do formato em
    formatos/<slug>/estudo-quadros/; os seguintes ficam em estudo-quadros/<exemplo-N>/ sem trocar a régua.
    A fala só pelo Groq e só em vídeo com som de 10 s ou mais (nunca transcritor pago)."""
    import estudo_quadros
    pasta = FORMATOS / slug / ESTUDO_QUADROS
    destino = pasta if not (pasta / "estudo.json").is_file() else pasta / Path(video).stem
    if fala is None:
        i = ffprobe(Path(video)) or {}
        fala = float(i.get("duracao") or 0) >= 10
    est = estudo_quadros.estudar([Path(video)], destino, nome=Path(video).stem, transcrever_fala=bool(fala))
    return {"pasta": rel(destino), "regras": len(est["regras"]), "base_sugerida": est["conjunto"].get("base_sugerida", ""),
            "regua": destino == pasta}


def estudo_quadros_txt(slug: str) -> str:
    """O que o pedido à IA diz da régua medida quadro a quadro do formato (se houver)."""
    p = FORMATOS / str(slug or "") / ESTUDO_QUADROS / "ESTUDO-QUADROS.md"
    if not slug or not p.is_file():
        return ""
    return (f"RÉGUA MEDIDA QUADRO A QUADRO: formatos/{slug}/{ESTUDO_QUADROS}/ESTUDO-QUADROS.md (+ estudo.json): siga os números "
            "(plano, transição, câmera, fala, pausa, som, legenda, número como evento) como estilo, nunca o conteúdo. Na conferência, "
            f"meça o vídeo pronto: `python3 app/ferramentas/estudo_quadros.py comparar formatos/{slug}/{ESTUDO_QUADROS} <mp4> "
            "--words <words.json da narração>` e corrija o que sair FORA antes de entregar.")


def referencia(slug: str, video: str | Path, legenda: str = "", principal: bool = False, quadros: bool = True) -> dict:
    """Estudo de referência em passos, sem IA. O vídeo (arquivo ou link) vira exemplo do formato: cópia leve
    exemplo-N.mp4, capa exemplo-N.jpg e folha exemplo-N-folha.jpg (1 quadro a cada 4 s, segundo marcado). Formato sem
    exemplo: ele vira o principal (a régua até sair um vídeo aprovado melhor); com exemplo, entra no fim (principal=True
    põe na frente). Cria o ESTUDO.md em branco (o que já existe não é tocado) e anota no historico.jsonl."""
    import subprocess
    import tempfile
    pasta = FORMATOS / str(slug or "")
    dados = ler_json(pasta / "formato.json") if slug and Path(slug).name == slug else None
    if not dados:
        raise ValueError(f"Formato não encontrado: formatos/{slug}/")
    origem = str(video)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(str(video)).expanduser()
        if origem.startswith(("http://", "https://")):
            src = Path(tmp) / "ref.mp4"
            subprocess.run(["yt-dlp", "-q", "-f", "mp4/best", "-o", str(src), origem], check=False, timeout=600)
        if not src.is_file():
            raise ValueError(f"Não consegui baixar o vídeo deste link: {video}" if origem.startswith(("http://", "https://"))
                             else f"Vídeo não encontrado: {video}")
        if not e_video(src):   # antes: copiava qualquer arquivo como exemplo-N.mp4 e dizia "ok"
            raise ValueError(f"Esse arquivo não é um vídeo que dê pra abrir: {video}")
        exs = [e for e in dados.get("exemplos") or [] if isinstance(e, dict)]
        usados = {int(m.group(1)) for x in pasta.glob("exemplo-*") if (m := re.fullmatch(r"exemplo-(\d+)(?:-folha)?\.\w+", x.name))}
        dst = pasta / f"exemplo-{max(usados, default=0) + 1}.mp4"
        try:
            ok = copia_leve(src, dst)
        except Exception:
            ok = False
        if not ok:
            _clonar(src, dst)
    poster = dst.with_suffix(".jpg")
    if not poster.is_file():
        thumb(dst, poster, t=1.0, largura=540)
    ex = {"arquivo": dst.name, "poster": poster.name, "legenda": legenda or "Referência", "origem": origem}
    fo = fazer_folha(dst, _arq_folha(dst))
    if fo:
        ex["folha"] = fo.name
    vira_principal = principal or not exs
    if vira_principal:
        ex["principal_desde"] = hoje()
    dados["exemplos"] = [ex] + exs if vira_principal else exs + [ex]
    gravar_json(pasta / "formato.json", dados)
    medidas = _medir_referencia(dst)
    est = pasta / ESTUDO
    novo_estudo = not est.is_file()
    if novo_estudo:
        est.write_text(_texto_estudo(dados.get("titulo") or slug, ex, origem, medidas), encoding="utf-8")
    append_jsonl(pasta / "aprendizado" / "historico.jsonl", {
        "tipo": "referencia", "categoria": "referencia", "origem": "usuario", "createdAt": hoje(), "job": "",
        "texto": f"Referência {ex['arquivo']} ({ex['legenda']})" + (" virou o exemplo principal." if vira_principal else "."),
        "video": origem})
    eq = {}
    if quadros:   # o estudo padrão: quadro a quadro, regra com número e quadro de prova
        try:
            eq = estudar_quadros(slug, dst)
        except Exception as e:  # noqa: BLE001
            eq = {"erro": str(e)[:200]}
    return {**ex, "principal": vira_principal, "estudo": rel(est), "estudo_novo": novo_estudo, "medidas": medidas,
            "estudo_quadros": eq}


def marcar_pronto(slug: str) -> list[str]:
    """Passa o formato pra "pronto" se ele cumprir o CONTRATO como pronto (com exemplo, sem TROQUE:, estudo respondido).
    Devolve as faltas (lista vazia = virou pronto). Nada é gravado se faltar algo."""
    pasta = FORMATOS / str(slug or "")
    dados = ler_json(pasta / "formato.json") if slug and Path(slug).name == slug else None
    if not dados:
        return [f"formato não encontrado: formatos/{slug}/"]
    antes = dados.get("status")
    gravar_json(pasta / "formato.json", {**dados, "status": "pronto"})
    faltas = validar(slug)
    if faltas:
        gravar_json(pasta / "formato.json", {**dados, "status": antes})
    return faltas


# ───────────────────── exemplo vivo: o melhor vídeo aprovado vira a régua ─────────────────────

FOLHA_PASSO_S = 4      # um quadro a cada 4 s
FOLHA_COLUNAS = 6


def _arq_folha(video: Path) -> Path:
    return video.with_name(video.stem + "-folha.jpg")


def _marcar_segundos(img: Path, colunas: int, linhas: int, n: int, passo: float) -> None:
    """Escreve o segundo de cada quadro no canto (o João lê a folha "por segundos")."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(img).convert("RGB")
    d = ImageDraw.Draw(im)
    cw, ch = im.width / colunas, im.height / linhas
    try:
        fonte = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(14, int(cw / 9)))
    except Exception:
        fonte = ImageFont.load_default()
    for k in range(n):
        s = int(k * passo)
        txt = f"{s // 60}:{s % 60:02d}"
        x, y = int((k % colunas) * cw) + 6, int((k // colunas) * ch) + 6
        caixa = d.textbbox((x, y), txt, font=fonte)
        d.rectangle((caixa[0] - 4, caixa[1] - 3, caixa[2] + 4, caixa[3] + 3), fill=(0, 0, 0))
        d.text((x, y), txt, fill=(255, 220, 0), font=fonte)
    im.save(img, quality=88)


def fazer_folha(video: Path, destino: Path, passo: float = FOLHA_PASSO_S, colunas: int = FOLHA_COLUNAS) -> Path | None:
    """Folha de quadros de um vídeo: 1 quadro a cada `passo` s (0, 4, 8…), lado a lado (tile), com o segundo marcado.
    Usa select em vez de fps=1/passo: o fps pega o quadro ~passo/2 depois e o segundo escrito ficaria errado."""
    import math
    import subprocess
    dur = ffprobe(video).get("duracao") or 0
    n = max(1, math.ceil(dur / passo))
    cols = min(colunas, n)
    linhas = math.ceil(n / cols)
    ensure(destino.parent)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                        f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{passo})',scale=216:-2,tile={cols}x{linhas}",
                        "-frames:v", "1", str(destino)], capture_output=True, timeout=300)
    if r.returncode or not destino.is_file():
        return None
    try:
        _marcar_segundos(destino, cols, linhas, n, passo)
    except Exception:
        pass   # sem PIL a folha fica sem os segundos, mas fica
    return destino


def folha_exemplo(slug: str, i: int = 0) -> Path | None:
    """formatos/<slug>/exemplo-N-folha.jpg do exemplo i (0 = o PRINCIPAL). Gera só se ainda não existir."""
    f = carregar(slug)
    exs = (f or {}).get("exemplos") or []
    if not 0 <= i < len(exs):
        return None
    v = f["pasta"] / exs[i]["arquivo"]
    fo = _arq_folha(v)
    if fo.is_file():
        return fo
    try:
        return fazer_folha(v, fo)
    except Exception:
        return None


def promover_exemplo(slug: str, mp4: Path, legenda: str, origem: str = "", job: str = "") -> dict:
    """Exemplo vivo: o vídeo aprovado vira o exemplo PRINCIPAL do formato (o primeiro de "exemplos"); os antigos ficam.

    Copia leve como exemplo-N.mp4, com poster (exemplo-N.jpg) e folha (exemplo-N-folha.jpg), e registra uma linha
    no historico.jsonl do formato. O mesmo vídeo (mesma origem) promovido de novo só volta pro topo."""
    pasta = FORMATOS / slug
    dados = ler_json(pasta / "formato.json") if slug and Path(slug).name == slug else None
    if not dados:
        raise ValueError("Formato não encontrado.")
    mp4 = Path(mp4)
    if not mp4.is_file():
        raise ValueError(f"Vídeo não encontrado: {mp4}")
    if not e_video(mp4):
        raise ValueError(f"Esse arquivo não é um vídeo que dê pra abrir: {mp4}")
    origem = str(origem or mp4)
    exs = [e for e in dados.get("exemplos") or [] if isinstance(e, dict)]
    ja = next((e for e in exs if e.get("origem") == origem and (pasta / e.get("arquivo", "")).is_file()), None)
    if ja:
        exs.remove(ja)
        novo = {**ja, "legenda": legenda or ja.get("legenda", "")}
    else:
        usados = {int(m.group(1)) for p in pasta.glob("exemplo-*")
                  if (m := re.fullmatch(r"exemplo-(\d+)(?:-folha)?\.\w+", p.name))}
        dst = pasta / f"exemplo-{max(usados, default=0) + 1}.mp4"
        try:
            ok = copia_leve(mp4, dst)
        except Exception:
            ok = False
        if not ok:   # sem ffmpeg pra fazer a cópia leve: vai o arquivo como está
            _clonar(mp4, dst)
        poster = dst.with_suffix(".jpg")
        if not poster.is_file():
            thumb(dst, poster, t=1.0, largura=540)
        novo = {"arquivo": dst.name, "poster": poster.name, "legenda": legenda, "origem": origem}
    fo = _arq_folha(pasta / novo["arquivo"])
    if not fo.is_file():
        fo = fazer_folha(pasta / novo["arquivo"], fo) or fo
    if fo.is_file():
        novo["folha"] = fo.name
    novo["principal_desde"] = hoje()
    dados["exemplos"] = [novo] + exs
    gravar_json(pasta / "formato.json", dados)
    append_jsonl(pasta / "aprendizado" / "historico.jsonl", {
        "tipo": "exemplo", "categoria": "referencia", "origem": "usuario", "createdAt": hoje(), "job": job,
        "texto": f"Novo exemplo principal: {legenda or novo['arquivo']} ({novo['arquivo']}). Os próximos vídeos deste "
                 "formato são comparados com ele.", "video": origem})
    return novo


# ───────────────────── o CONTRATO: o que todo formato cumpre (formatos/CONTRATO.md) ─────────────────────

_PASSO_MD = re.compile(r"^\s*(?:\d+[.)]|#{2,4})\s+(.*)$")   # linha de passo no COMO-FAZER: "1. ..." ou "## ..."
_ARQ_CMD = re.compile(r"(<sandbox>/|\{sandbox\}/|<modelo>/|\.\./)?((?:[\w-][\w.-]*/)*[\w-][\w.-]*\.(?:py|sh|js|mjs|cjs|html))(?![\w.])")


def _norm(s: str) -> str:
    return re.sub(r"[*_`]+", "", str(s or "")).strip().lower()


def _arquivos_do_comando(c: str) -> list[tuple[str, str]]:
    """Arquivos citados num comando: ("base", x) pra <sandbox>/x (a sandbox é cópia da base), <modelo>/x e ../x (o
    script do modelo visto de dentro da sandbox, que mora em <modelo>/_sandbox-<slug>; o modelo é a base) e ("raiz", x)
    pra app/, formatos/, clientes/, acervo/ (roda da raiz do Estúdio). O resto (npx, python3, flags) não é conferido."""
    out = []
    for m in _ARQ_CMD.finditer(c or ""):
        if m.group(1):
            out.append(("base", m.group(2)))
        elif m.group(2).startswith(("app/", "formatos/", "clientes/", "acervo/")):
            out.append(("raiz", m.group(2)))
    return out


def _tem_marca(p: Path) -> bool:
    try:
        return p.is_file() and MARCA_MODELO in p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def validar(slug: str) -> list[str]:
    """O que falta pro formato cumprir o CONTRATO (formatos/CONTRATO.md), em português. Lista vazia = cumpre.
    Só lê: não gera folha, não grava nada. Vale pros dois tipos (motor e gravado) e pros futuros."""
    pasta = FORMATOS / str(slug or "")
    if not slug or Path(slug).name != slug or not pasta.is_dir():
        return [f"formato não encontrado: formatos/{slug}/"]
    try:
        dados = json.loads((pasta / "formato.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["falta o formato.json"]
    except ValueError as e:
        return [f"o formato.json não é JSON válido ({e})"]
    if not isinstance(dados, dict):
        return ["o formato.json tem que ser um objeto { }"]
    faltas: list[str] = []
    falta = faltas.append

    # 1. básico, status e tipo
    for campo, o_que in (("titulo", "o nome do formato"), ("frase", "uma frase dizendo como o vídeo fica"),
                         ("proporcao", "a proporção, ex.: 9:16"), ("motor", "com o que ele renderiza, em texto")):
        if not str(dados.get(campo) or "").strip():
            falta(f"formato.json sem \"{campo}\" ({o_que})")
    if dados.get("entrada") not in ENTRADAS:
        falta(f"\"entrada\" tem que ser uma de: {', '.join(ENTRADAS)}")
    status, t = dados.get("status"), dados.get("tipo")
    if status not in STATUS:
        falta("\"status\" tem que ser pronto ou receita")
    if t not in TIPOS:
        falta("\"tipo\" tem que ser motor (animação construída, motor em base/) ou gravado (vídeo gravado com corte, "
              "cenas e cards por cima)")
    for m in dados.get("modelos") or []:   # dois formatos com o mesmo modelo: o vídeo antigo cai no formato errado
        dono = _dono_do_modelo(m, fora=slug)
        if dono:
            falta(f"o modelo {m} também é do formato {dono}: cada modelo é de um formato só (troque em \"modelos\")")

    # 2. os passos, na ordem, e onde para pro João aprovar
    bruto = dados.get("esteira")
    est = esteira({**dados, "slug": slug}) if bruto else None
    if not bruto:
        falta("falta a \"esteira\": os passos do formato na ordem (id, titulo, andamento, faz) e qual tem \"aprovar\": true")
    elif est is None:
        falta("a \"esteira\" está malformada: cada etapa precisa de id único, titulo, andamento ("
              + ", ".join(ANDAMENTOS) + ") e pelo menos uma com \"aprovar\": true")
    else:
        crus = bruto["etapas"] if isinstance(bruto, dict) else bruto
        for e, cru in zip(est["etapas"], crus):
            if not cru.get("andamento"):
                falta(f"a etapa \"{e['titulo']}\" sem \"andamento\" ({', '.join(ANDAMENTOS)})")
            if not e["faz"]:
                falta(f"a etapa \"{e['titulo']}\" sem \"faz\" (o que fazer nela, em uma ou duas frases)")
        etapas, k = est["etapas"], est["parada"]
        if etapas[0]["id"] != BRIEFING or not etapas[0]["aprovar"]:
            falta(f"falta o passo 0 \"{BRIEFING}\" no começo da esteira (\"andamento\": \"preparar\", \"aprovar\": true): "
                  "o briefing que o João aprova na conversa, antes de tudo")
        p = etapas[k]
        if p["andamento"] != "storyboard" and "storyboard" not in _norm(f"{p['id']} {p['titulo']}"):
            falta(f"a 1ª etapa com \"aprovar\" é \"{p['titulo']}\": tem que ser o storyboard (a tela para na 1ª; "
                  "roteiro e elenco se aprovam antes, na tela Criar)")
        depois = etapas[k + 1:]
        if not any(e["andamento"] == "video" for e in depois):
            falta("falta a etapa do vídeo (andamento \"video\") depois do storyboard")
        if not depois or depois[-1]["andamento"] != "conferencia":
            falta("a última etapa tem que ser a conferência (andamento \"conferencia\"): comparar com o exemplo "
                  "principal e nunca entregar pior que ele")

    # 3. o caminho do render
    base_rel = str(dados.get("base") or "").strip()
    base = RAIZ / base_rel if base_rel else None
    if t == "motor":
        esperado = f"formatos/{slug}/base"
        if base_rel != esperado:
            falta(f"formato de motor: \"base\" tem que ser {esperado} (o motor mora no formato)")
        elif not base.is_dir():
            falta(f"falta a pasta do motor: {esperado}/")
        else:
            sem = [i for i in motor_itens(dados) if not (base / i).exists()]
            if sem:
                falta(f"o motor em {esperado}/ está incompleto: falta {', '.join(sem)} (esteira.motor_arquivos)")
    elif t == "gravado":
        if dados.get("modelos"):
            if not base_rel:
                falta("\"base\" vazio: aponte o modelo que serve de ponto de partida (clientes/<Nome>/<x>Content/modelos/<modelo>)")
            elif not base.is_dir() or _vazia(base):
                falta(f"a base {base_rel} não existe ou está vazia")
        if est and not est["comandos"].get("render"):
            falta("formato de vídeo gravado: declare o render em esteira.comandos.render, visto de dentro da sandbox (ex.: zsh ../gerar.sh --dir .)")
    if est:
        cmds = list(est["comandos"].items()) + [(e["id"], str(e["comando"])) for e in est["etapas"] if e.get("comando")]
        for nome, c in cmds:
            for onde, arq in _arquivos_do_comando(c):
                if onde == "base" and not (base and (base / arq).exists()):
                    falta(f"o comando \"{nome}\" usa <sandbox>/{arq}, que não está na base ({base_rel or 'sem base'})")
                elif onde == "raiz" and not (RAIZ / arq).exists():
                    falta(f"o comando \"{nome}\" usa {arq}, que não existe")

    # 4. exemplo principal (o 1º) com folha de quadros marcados no tempo
    exs = dados.get("exemplos") or []
    if not isinstance(exs, list):
        falta("\"exemplos\" tem que ser uma lista")
        exs = []
    for i, e in enumerate(exs, 1):
        arq = e.get("arquivo") if isinstance(e, dict) else None
        if not arq or not (pasta / arq).is_file():
            falta(f"o exemplo {i} ({arq or 'sem arquivo'}) não está na pasta do formato")
    if exs and isinstance(exs[0], dict) and exs[0].get("arquivo") and (pasta / exs[0]["arquivo"]).is_file():
        if not _arq_folha(pasta / exs[0]["arquivo"]).is_file():
            falta(f"o exemplo principal ({exs[0]['arquivo']}) sem folha de quadros: python3 app/ferramentas/formatos.py folha {slug}")
        if not str(exs[0].get("legenda") or "").strip():
            falta("o exemplo principal sem \"legenda\" (o que ele é, ex.: Correria · Cliente3)")

    if status == "pronto" and not exs and not dados.get("oculto"):
        falta("formato \"pronto\" sem exemplo: fica receita até ter um (python3 app/ferramentas/formatos.py referencia "
              f"{slug} <video> ou exemplo {slug} <mp4>)")
    if status == "pronto" and estudo_estado(slug) == "branco":
        falta(f"o {ESTUDO} está em branco: responda as linhas R: uma vez (os vídeos leem dele em vez de reestudar a referência)")

    # 5. música e efeitos: se usa e de onde vêm
    som = dados.get("som")
    if not isinstance(som, dict):
        falta("falta \"som\": {\"musica\": {\"usa\": true|false, \"de_onde\": \"...\"}, \"efeitos\": {\"usa\": ..., \"de_onde\": ...}}")
    else:
        for k_, o_que in (("musica", "música"), ("efeitos", "efeitos sonoros")):
            s = som.get(k_)
            if not isinstance(s, dict) or not isinstance(s.get("usa"), bool):
                falta(f"som.{k_}: diga se o formato usa {o_que} (\"usa\": true ou false) e de onde vêm (\"de_onde\")")
            elif s["usa"] and not str(s.get("de_onde") or "").strip():
                falta(f"som.{k_}: usa {o_que}, mas não diz de onde vêm (\"de_onde\")")
            elif s["usa"]:
                cobrados = ("clima",) if k_ == "musica" else ("quais",)
                for campo in cobrados + ("volume", "quando_nao"):
                    v = s.get(campo)
                    vazio = not (v if isinstance(v, list) else str(v or "").strip())
                    modelo_ = str(v).strip() in ("...", "['...']") and status == "pronto"   # "..." do _modelo: receita pode, pronto não
                    if vazio or modelo_:
                        falta(f"som.{k_}.{campo}: o formato usa {o_que}; diga o {campo} (\"...\" não vale; veja formatos/CONTRATO.md item 7)")
    apoio = dados.get("apoio")
    if not isinstance(apoio, dict) or not isinstance(apoio.get("usa"), bool):
        falta("falta \"apoio\": a cena de apoio do formato ({\"usa\": true|false, \"tipo\", \"fontes\", \"duracao_s\", \"quando_nao\"}); "
              "sem b-roll nem print: {\"usa\": false, \"quando_nao\": \"sempre\"}")
    elif apoio["usa"]:
        for campo in ("tipo", "fontes", "duracao_s", "quando_nao"):
            v = apoio.get(campo)
            if (not (v if isinstance(v, list) else str(v or "").strip())) or (str(v).strip() in ("...", "['...']") and status == "pronto"):
                falta(f"apoio.{campo}: o formato usa cena de apoio; diga o {campo} (\"...\" não vale)")
    pede = dados.get("pede")
    if not isinstance(pede, list) or not pede:
        falta("falta \"pede\": o que o passo 4 do Criar pergunta pra este formato (lista de {campo, rotulo, tipo, obrigatorio, dica}); "
              "veja formatos/CONTRATO.md item 8b")
    else:
        for i_, c_ in enumerate(pede, 1):
            if not isinstance(c_, dict) or not all(str(c_.get(k) or "").strip() for k in ("campo", "rotulo", "tipo")):
                falta(f"pede[{i_}]: precisa de campo, rotulo e tipo")
            elif c_["tipo"] not in TIPOS_PEDE:
                falta(f"pede[{i_}] ({c_['campo']}): tipo \"{c_['tipo']}\" não existe; use um de {', '.join(TIPOS_PEDE)}")
    cf_ = pasta / "COMO-FAZER.md"
    if cf_.is_file() and "## Som e cena de apoio" not in cf_.read_text(encoding="utf-8"):
        falta("o COMO-FAZER.md não tem a seção \"## Som e cena de apoio\" (música, efeitos e cena de apoio em prosa curta)")

    # 5b. o material que o formato sabe usar (o aviso cedo da conversa lê daqui)
    aceito = dados.get("material_aceito")
    if not isinstance(aceito, list):
        falta("falta \"material_aceito\": a lista do material que o formato sabe usar (" + ", ".join(MATERIAIS)
              + "); [] se não usa nenhum")
    else:
        sem = [str(x) for x in aceito if x not in MATERIAIS]
        if sem:
            falta(f"\"material_aceito\" com material que o Estúdio não conhece: {', '.join(sem)} (vale: {', '.join(MATERIAIS)})")

    # 5c. como o formato ocupa a tela (a referência que pede outro layout é avisada cedo)
    lays = dados.get("layouts")
    if not isinstance(lays, list) or not lays:
        falta("falta \"layouts\": como o formato ocupa a tela (" + ", ".join(LAYOUTS) + "); no mínimo um")
    else:
        sem = [str(x) for x in lays if x not in LAYOUTS]
        if sem:
            falta(f"\"layouts\" com layout que o Estúdio não conhece: {', '.join(sem)} (vale: {', '.join(LAYOUTS)})")

    # 5d. a legenda dá pra desligar? (o interruptor do Criar e a linha SEM LEGENDA do pedido leem daqui)
    leg = dados.get("legenda")
    if not isinstance(leg, dict) or not isinstance(leg.get("desligavel"), bool):
        falta("falta \"legenda\": {\"desligavel\": true|false, \"como\": \"<passo ou parâmetro exato que desliga>\"} "
              "(desligavel=false leva \"motivo\" em vez de \"como\")")
    elif leg["desligavel"] and not str(leg.get("como") or "").strip():
        falta("\"legenda\" desligável sem \"como\": diga o passo ou o parâmetro exato que desliga a legenda")
    elif not leg["desligavel"] and not str(leg.get("motivo") or "").strip():
        falta("\"legenda\" não desligável sem \"motivo\": diga em uma frase por que o interruptor fica desligado")

    # 6. aprendizado: regras com título
    apr = pasta / "aprendizado"
    rj = ler_json(apr / "regras.json") if (apr / "regras.json").is_file() else None
    if not (apr / "regras.json").is_file():
        falta("falta aprendizado/regras.json (pode começar com \"regras\": [])")
    elif not isinstance(rj, dict) or not isinstance(rj.get("regras"), list):
        falta("o aprendizado/regras.json tem que ter \"regras\": [ ... ]")
    else:
        ids = set()
        for i, r in enumerate(rj["regras"], 1):
            if not isinstance(r, dict):
                falta(f"a regra nº {i} não é um objeto {{ }}")
                continue
            rid = str(r.get("id") or "").strip()
            nome = rid or f"nº {i}"
            if not rid:
                falta(f"a regra nº {i} sem \"id\"")
            elif rid in ids:
                falta(f"a regra \"{rid}\" aparece duas vezes")
            ids.add(rid)
            if not str(r.get("titulo") or "").strip():
                falta(f"a regra \"{nome}\" sem \"titulo\" (o nome curto que a tela mostra)")
            if not str(r.get("texto") or "").strip():
                falta(f"a regra \"{nome}\" sem \"texto\"")
    if (apr / "regras.md").is_file():
        titulos = ler_json(apr / "titulos.json", {}) or {}
        sem = [r["id"] for r in _regras_md(apr / "regras.md") if not str(titulos.get(r["id"]) or "").strip()]
        if sem:
            falta(f"aprendizado/regras.md: {len(sem)} regra(s) sem título em aprendizado/titulos.json ("
                  + ", ".join(sem[:6]) + ("…" if len(sem) > 6 else "") + ")")

    # 7. COMO-FAZER.md curto, escrito como o passo a passo (os passos da esteira, na mesma ordem)
    cf = pasta / "COMO-FAZER.md"
    if not cf.is_file():
        falta("falta o COMO-FAZER.md (o passo a passo, curto)")
    else:
        linhas = cf.read_text(encoding="utf-8").splitlines()
        if len(linhas) > COMO_FAZER_MAX_LINHAS:
            falta(f"o COMO-FAZER.md tem {len(linhas)} linhas: até {COMO_FAZER_MAX_LINHAS} (o detalhe vai no base/README.md ou nas regras)")
        if est:
            passos = [_norm(m.group(1)) for l in linhas if (m := _PASSO_MD.match(l))]
            j = 0
            for e in est["etapas"]:
                if e["id"] == BRIEFING:   # o passo 0 é igual em todo formato: mora no CONTRATO, não no COMO-FAZER
                    continue
                achou = next((i for i in range(j, len(passos)) if passos[i].startswith(_norm(e["titulo"]))), None)
                if achou is None:
                    falta(f"o COMO-FAZER.md não traz o passo \"{e['titulo']}\" na ordem da esteira (linha \"N.\" ou "
                          "\"##\" começando com o título da etapa)")
                else:
                    j = achou + 1

    # 8. pronto não pode ter sobra do _modelo
    if status == "pronto":
        onde = [n for n, p in (("formato.json", pasta / "formato.json"), ("COMO-FAZER.md", cf)) if _tem_marca(p)]
        if t == "motor" and base and base.is_dir():
            onde += [f"base/{i}" for i in motor_itens(dados) if _tem_marca(base / i)]
        if onde:
            falta(f"ainda tem texto do _modelo (\"{MARCA_MODELO}\") em: {', '.join(onde)}")
    return list(dict.fromkeys(faltas))


def validar_todos() -> dict[str, dict]:
    """{slug: {"status", "faltas"}} de todo formato do catálogo (inclusive os ocultos) e do _modelo."""
    out = {}
    for d in sorted(FORMATOS.iterdir()) if FORMATOS.is_dir() else []:
        if d.is_dir() and not d.name.startswith(".") and (d / "formato.json").exists():
            out[d.name] = {"status": (ler_json(d / "formato.json", {}) or {}).get("status", ""), "faltas": validar(d.name)}
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Catálogo de formatos do Estúdio (sem argumento: lista os formatos).")
    sub = ap.add_subparsers(dest="acao")
    v = sub.add_parser("validar", help="confere o CONTRATO (formatos/CONTRATO.md) de um formato ou de todos")
    v.add_argument("slug", nargs="?", default="")
    v.add_argument("--todos", action="store_true", help="todos os formatos (é o padrão sem slug)")
    sub.add_parser("lista", help="slug · título · frase de cada formato (oculto marcado)")
    n = sub.add_parser("novo", help="formato novo a partir de formatos/_modelo (nasce como receita)")
    n.add_argument("slug")
    n.add_argument("--titulo", default="")
    n.add_argument("--frase", default="")
    qual = n.add_mutually_exclusive_group()
    qual.add_argument("--motor", dest="tipo", action="store_const", const="motor",
                      help="animação construída: base/ com o motor genérico (render.py --storyboard/--conferir/--quadro)")
    qual.add_argument("--gravado", dest="tipo", action="store_const", const="gravado",
                      help="vídeo gravado: a base é o modelo de um cliente (--base) e o render é o gerar.sh dele")
    qual.add_argument("--tipo", choices=tuple(TIPOS))
    n.add_argument("--base", default="", help="gravado: pasta do modelo do cliente (clientes/<Nome>/<x>Content/modelos/<modelo>)")
    n.add_argument("--modelo", default="", help="gravado: nome do modelo (padrão: o nome da pasta da base; se outro formato já usa esse modelo, o nome do formato)")
    n.add_argument("--render", default="", help="gravado: comando do render, visto de dentro da sandbox (padrão: o gerar.sh da base)")
    rf = sub.add_parser("referencia", help="estudo de referência sem IA: o vídeo vira exemplo (com folha marcada no tempo) "
                                           "e o formato ganha um ESTUDO.md em branco pra responder UMA vez")
    rf.add_argument("slug")
    rf.add_argument("video", help="arquivo de vídeo ou link (yt-dlp)")
    rf.add_argument("--legenda", default="", help="o que ele é (padrão: Referência)")
    rf.add_argument("--principal", action="store_true", help="vira o exemplo principal mesmo se o formato já tiver um")
    rf.add_argument("--sem-quadros", action="store_true", help="pula o estudo quadro a quadro (estudo_quadros.py)")
    pr = sub.add_parser("pronto", help="passa o formato pra pronto se cumprir o contrato (com exemplo, sem TROQUE:, estudo respondido)")
    pr.add_argument("slug")
    e = sub.add_parser("exemplo", help="o vídeo vira o exemplo PRINCIPAL do formato (os antigos ficam)")
    e.add_argument("slug")
    e.add_argument("mp4")
    e.add_argument("--legenda", default="")
    e.add_argument("--origem", default="")
    fo = sub.add_parser("folha", help="folha de quadros (1 a cada 4 s) de um exemplo; 0 = o principal")
    fo.add_argument("slug")
    fo.add_argument("--i", type=int, default=0)
    fv = sub.add_parser("folha-video", help="folha de quadros de QUALQUER vídeo, igual à do exemplo (1 a cada 4 s, segundo marcado)")
    fv.add_argument("mp4")
    fv.add_argument("saida", help="o .jpg da folha (ex.: <sandbox>/qa/folha-video.jpg)")
    fv.add_argument("--passo", type=float, default=FOLHA_PASSO_S)
    a = ap.parse_args(argv)
    if a.acao == "lista":
        for f in listar(ocultos=True):
            print(f"{f['slug']} · {f.get('titulo', f['slug'])}{' · oculto' if f.get('oculto') else ''} · {(f.get('frase') or '')[:110]}")
        return 0
    if a.acao == "validar":
        # um formato: sai 1 se faltar algo. --todos: sai 1 se algum PRONTO tiver falta (receita só aparece na lista).
        todos = a.todos or not a.slug
        res = validar_todos() if todos else {a.slug: {"status": (carregar(a.slug) or {}).get("status", ""),
                                                      "faltas": validar(a.slug)}}
        ruim = False
        for slug, r in res.items():
            if not r["faltas"]:
                print(f"ok    {slug} ({r['status'] or 'sem status'})")
                continue
            conta = r["status"] == "pronto" or not todos
            ruim |= conta
            print(f"{'FALTA' if conta else 'aviso'} {slug} ({r['status'] or 'sem status'}): {len(r['faltas'])} falta(s)")
            for x in r["faltas"]:
                print(f"      - {x}")
        return 1 if ruim else 0
    if a.acao == "novo":
        tipo_ = a.tipo or "motor"
        if tipo_ == "gravado" and not a.base:
            print("vídeo gravado: diga a base, o modelo do cliente que serve de ponto de partida "
                  "(--base clientes/<Nome>/<x>Content/modelos/<modelo>)", file=sys.stderr)
            return 1
        try:
            d = novo_formato(a.slug, titulo=a.titulo, frase=a.frase, tipo_=tipo_, base=a.base, modelo=a.modelo, render=a.render)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        faltas = validar(a.slug)
        print(f"ok · {rel(d)} criado ({tipo_}, receita)" + (" · validar sem falta" if not faltas else ""))
        for x in faltas:
            print(f"      - {x}")
        print("Próximos passos:\n"
              f"  1. python3 app/ferramentas/formatos.py referencia {a.slug} <video>   (vira exemplo + ESTUDO.md em branco)\n"
              f"  2. responda o ESTUDO.md e troque o que tem \"{MARCA_MODELO}\" (formato.json, COMO-FAZER.md"
              + (", base/index.html, base/README.md" if tipo_ == "motor" else "") + ")\n"
              + (f"     teste o motor: cd {rel(d)}/base && python3 render.py --storyboard --cenas cenas-modelo.json\n"
                 if tipo_ == "motor" else "")
              + f"  3. python3 app/ferramentas/formatos.py pronto {a.slug}")
        return 1 if faltas else 0
    elif a.acao == "referencia":
        try:
            r = referencia(a.slug, a.video, legenda=a.legenda, principal=a.principal, quadros=not a.sem_quadros)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        m = r["medidas"]
        print(f"ok · formatos/{a.slug}/{r['arquivo']}" + (" (exemplo principal)" if r["principal"] else "")
              + (f" · folha {r['folha']}" if r.get("folha") else " · a folha não saiu"))
        print(f"medido: {m.get('duracao')} s · {m.get('largura')}x{m.get('altura')} · "
              + (f"{m['cortes']} cortes · " if m.get("cortes") is not None else "") + ("com som" if m.get("som") else "sem som"))
        print(f"{r['estudo']}: " + ("em branco, responda UMA vez as linhas R: olhando a folha" if r["estudo_novo"]
                                    else "já existia (não mexi): acrescente o que esta referência traz de novo"))
        eq = r.get("estudo_quadros") or {}
        if eq.get("pasta"):
            print(f"quadro a quadro: {eq['pasta']}/ESTUDO-QUADROS.md · {eq['regras']} regras com número"
                  + (" (é a régua do formato)" if eq.get("regua") else "") + f" · base sugerida: {eq.get('base_sugerida') or '?'}")
        elif eq.get("erro"):
            print(f"quadro a quadro falhou: {eq['erro']}")
    elif a.acao == "pronto":
        if not carregar(a.slug):
            print(f"Formato não encontrado: formatos/{a.slug}/", file=sys.stderr)
            return 1
        faltas = marcar_pronto(a.slug)
        if not faltas:
            print(f"ok · {a.slug} está pronto (aparece no Criar e roda pela tela)")
            return 0
        print(f"{a.slug} continua receita. Falta:")
        for x in faltas:
            print(f"      - {x}")
        return 1
    elif a.acao == "exemplo":
        v = Path(a.mp4).expanduser().resolve()
        try:
            novo = promover_exemplo(a.slug, v, a.legenda or v.stem, a.origem or str(v))
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"ok · exemplo principal de {a.slug}: formatos/{a.slug}/{novo['arquivo']}"
              + (f" (folha {novo['folha']})" if novo.get("folha") else ""))
    elif a.acao == "folha":
        if not carregar(a.slug):
            print(f"Formato não encontrado: formatos/{a.slug}/", file=sys.stderr)
            return 1
        p = folha_exemplo(a.slug, a.i)
        if not p:
            print(f"{a.slug} ainda não tem esse exemplo (ou a folha não saiu). Pra pôr um: "
                  f"python3 app/ferramentas/formatos.py referencia {a.slug} <video>", file=sys.stderr)
            return 1
        print(rel(p))
    elif a.acao == "folha-video":
        v = Path(a.mp4).expanduser()
        if not v.is_file():
            print(f"vídeo não encontrado: {v}", file=sys.stderr)
            return 1
        p = fazer_folha(v, Path(a.saida).expanduser(), passo=a.passo)
        if not p:
            print(f"a folha não saiu: {v}", file=sys.stderr)
            return 1
        print(p)
    else:
        for f in listar():
            print(f"{f['slug']:22} {f['titulo']:24} exemplos={len(f['exemplos'])} variantes="
                  + ", ".join(f"{v['cliente']}" for v in f["variantes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
