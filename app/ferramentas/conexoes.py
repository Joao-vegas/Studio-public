"""Conexões: os aplicativos que o Estúdio usa, numa lista só (Configurações, topo).

Cada app tem ícone, nome, pra quê, custo (Grátis · Assinatura · Pago só com seu clique), a situação MEDIDA de verdade
(ligado · falta chave · fora do ar), o link de onde se pega a chave e um teste que NUNCA gasta (só consulta chave/saldo).
O valor de uma chave nunca sai daqui: só sim/não e os 4 últimos caracteres.

    python3 app/ferramentas/conexoes.py            situação de todos
    python3 app/ferramentas/conexoes.py testar groq
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chaves
from _comum import ESTUDIO, claude_bin, gravar_json, ler_json

TESTES = ESTUDIO / ".cache" / "conexoes-testes.json"   # último teste de cada app: {id: {ok, texto, quando, hash}}
LIGADO, FALTA, FORA = "ligado", "falta", "fora"
ROTULO = {LIGADO: "ligado", FALTA: "falta chave", FORA: "fora do ar"}
BOLA = {LIGADO: "●", FALTA: "○", FORA: "✖"}
GRATIS, ASSINATURA, PAGO = "Grátis", "Assinatura", "Pago, só com seu clique"

# id, nome, ícone, pra que serve (1 frase), custo, variável da chave, link de onde pega, como fazer (1 linha)
APPS = [
    dict(id="voicestudio", nome="VoiceStudio", icone="🎙️", serve="Narra os vídeos feitos por roteiro, com voz local no seu Mac.",
         custo=GRATIS, var="", link="", como=""),
    dict(id="claude", nome="Claude", icone="✦", serve="Cria e altera os vídeos. Usa a sua assinatura ou, se você ligar, o crédito da API.",
         custo=ASSINATURA, var="ANTHROPIC_API_KEY", link="https://console.anthropic.com/settings/keys",
         como="Entre no Console da Anthropic, clique em Create Key e copie na hora (ela só aparece uma vez). Ponha crédito em Billing."),
    dict(id="codex", nome="Codex / GPT", icone="◎", serve="Alternativa ao Claude para criar e alterar os vídeos.",
         custo=ASSINATURA, var="OPENAI_API_KEY", link="https://platform.openai.com/api-keys",
         como="Entre na OpenAI, clique em Create new secret key e copie (começa com sk-). A chave só serve para cobrar do crédito."),
    dict(id="kie", nome="kie.ai", icone="🎬", serve="Gera imagem e vídeo por IA. Só gera com a sua aprovação.",
         custo=PAGO, var="KIE_API_KEY", link="https://kie.ai/api-key",
         como="Entre na kie.ai, abra API Key e copie a chave. Os créditos são recarregados na mesma conta."),
    dict(id="groq", nome="Groq", icone="⚡", serve="Transcreve a fala dos vídeos (Whisper).",
         custo=GRATIS, var="GROQ_API_KEY", link="https://console.groq.com/keys",
         como="Entre com o Google, clique em Create API Key, dê um nome e copie (começa com gsk_)."),
    dict(id="elevenlabs", nome="ElevenLabs", icone="🔊", serve="Voz reserva: só entra se o VoiceStudio estiver fechado.",
         custo=PAGO, var="ELEVENLABS_API_KEY", link="https://elevenlabs.io/app/settings/api-keys",
         como="Entre na ElevenLabs, clique em Create API Key e copie. A voz dela é escolhida em “Voz dos vídeos por roteiro”."),
    dict(id="pexels", nome="Pexels", icone="📷", serve="Banco de cenas de vídeo e foto para o b-roll.",
         custo=GRATIS, var="PEXELS_API_KEY", link="https://www.pexels.com/api/new/",
         como="Crie a conta, peça a chave em Your API Key e copie."),
    dict(id="pixabay", nome="Pixabay", icone="🖼️", serve="Outro banco de cenas de vídeo e foto para o b-roll.",
         custo=GRATIS, var="PIXABAY_API_KEY", link="https://pixabay.com/api/docs/",
         como="Entre na conta e abra a página: a chave aparece em Parameters, já preenchida."),
    dict(id="freesound", nome="Freesound", icone="🔔", serve="Efeitos sonoros com licença livre.",
         custo=GRATIS, var="FREESOUND_API_KEY", link="https://freesound.org/apiv2/apply",
         como="Entre na conta, preencha o formulário Apply for an API key e copie a chave (Client secret/API key)."),
    dict(id="jamendo", nome="Jamendo", icone="🎵", serve="Músicas com licença livre.",
         custo=GRATIS, var="JAMENDO_CLIENT_ID", link="https://devportal.jamendo.com/",
         como="Crie a conta de desenvolvedor, registre um app e copie o Client ID."),
]
POR_ID = {a["id"]: a for a in APPS}
# nome do serviço em chaves.SERVICOS → link de onde pega a chave (a lista "Chaves e onde estão" usa)
LINK_POR_SERVICO = {"Anthropic (Claude)": POR_ID["claude"]["link"], "OpenAI (GPT)": POR_ID["codex"]["link"], "ElevenLabs": POR_ID["elevenlabs"]["link"],
                    "Groq": POR_ID["groq"]["link"], "Pexels": POR_ID["pexels"]["link"], "Pixabay": POR_ID["pixabay"]["link"],
                    "Freesound": POR_ID["freesound"]["link"], "Jamendo": POR_ID["jamendo"]["link"], "kie.ai": POR_ID["kie"]["link"]}
SEM_CHAVE = "Mixkit · YouTube (yt-dlp) · SoundCloud · Wikimedia Commons · NASA"

_CACHE: dict = {}


def _cache(chave: str, fazer, segundos: float = 45.0):
    """Login do Claude/Codex mudam raramente: lembra 45 s pra tela de Configurações abrir rápido."""
    t, v = _CACHE.get(chave, (0.0, None))
    if time.time() - t > segundos:
        v = fazer()
        _CACHE[chave] = (time.time(), v)
    return v


def esquecer() -> None:
    _CACHE.clear()


# ───────────── medições (sem custo) ─────────────

def _rodar(cmd: list, tempo: float = 8) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def claude_login() -> dict:
    """{binario, logado, plano}: binário do Claude Code + `claude auth status`."""
    def fazer():
        b = claude_bin()
        if not b: return {"binario": False, "logado": False, "plano": ""}
        rc, out = _rodar([b, "auth", "status"])
        try: d = json.loads(out)
        except ValueError: d = {}
        return {"binario": True, "logado": bool(d.get("loggedIn")) and rc == 0, "plano": str(d.get("subscriptionType") or "")}
    return _cache("claude", fazer)


def codex_login() -> dict:
    def fazer():
        import ia
        b = ia.codex_bin()
        if not b: return {"binario": False, "logado": False, "texto": ""}
        rc, out = _rodar([b, "login", "status"])
        return {"binario": True, "logado": rc == 0 and "logged in" in out.lower(), "texto": out.strip()[:80]}
    return _cache("codex", fazer)


def _valor(app: dict) -> str:
    """O valor da chave (só pra medir/testar aqui dentro). Claude e OpenAI também olham o arquivo antigo em ~/.config/estudio."""
    if not app["var"]: return ""
    return chaves.ler({"claude": "anthropic", "codex": "openai"}[app["id"]]) if app["id"] in ("claude", "codex") else chaves.chave(app["var"])


def _teste_salvo(app: dict) -> dict:
    t = (ler_json(TESTES, {}) or {}).get(app["id"]) or {}
    # teste de outra chave não vale: se a chave mudou, o resultado antigo some
    return t if t and t.get("hash") == chaves._hash(_valor(app)) else {}


def _guardar_teste(app: dict, r: dict) -> None:
    todos = ler_json(TESTES, {}) or {}
    todos[app["id"]] = {"ok": bool(r["ok"]), "texto": r["texto"], "quando": datetime.now().strftime("%d/%m %H:%M"),
                        "hash": chaves._hash(_valor(app))}
    TESTES.parent.mkdir(parents=True, exist_ok=True)
    gravar_json(TESTES, todos)


def _final(app: dict) -> str:
    k = _valor(app)
    return ("…" + k[-4:]) if len(k) >= 8 else ""


def situacao(app: dict, cfg: dict | None = None) -> dict:
    """{estado, rotulo, texto, final, teste}: a medida de verdade, não um palpite."""
    import ia, voz as _voz, voicestudio
    cfg = cfg or ia.config()
    i, tem = app["id"], bool(_valor(app))
    out = {"estado": FALTA, "texto": "", "final": _final(app), "teste": _teste_salvo(app) if app["var"] else {}, "rotulo": ""}
    if i == "voicestudio":
        if voicestudio.no_ar():
            escolhida = _voz.status()["voicestudio"]["voz"]
            nome = next((v["rotulo"] for v in voicestudio.vozes() if v["id"] == escolhida), escolhida)
            out.update(estado=LIGADO, texto="No ar na porta 3900. Voz escolhida: " + nome + ".")
        else:
            out.update(estado=FORA, texto="Fechado. Abra o VoiceStudio: sem ele os vídeos por roteiro não têm voz.")
    elif i == "claude":
        c = claude_login()
        api = ia.cobranca(cfg) == "api" and cfg.get("provedor") == "claude"
        out["custo"] = "Pago (crédito da API)" if api else ASSINATURA
        if not c["binario"]:
            out.update(estado=FORA, texto="O Claude Code não está instalado neste Mac.")
        elif api:
            out.update(estado=LIGADO, texto="Cobrando do crédito da API (chave " + out["final"] + ").")
        elif c["logado"]:
            out.update(estado=LIGADO, texto="Pela assinatura" + (f" (plano {c['plano'].capitalize()})" if c["plano"] else "") + ". A chave da API é opcional.")
        elif tem:
            out.update(estado=LIGADO, texto="Chave da API salva, mas a cobrança está no plano e você não entrou nele. Ligue “crédito da API” abaixo.")
        else:
            out.update(estado=FALTA, texto="Entre no Claude Code (rode claude e faça login) ou cole uma chave da API.")
    elif i == "codex":
        x = codex_login()
        api = ia.cobranca(cfg) == "api" and cfg.get("provedor") == "openai"
        out["custo"] = "Pago (crédito da API)" if api else ASSINATURA
        if not x["binario"]:
            out.update(estado=FALTA, texto="O Codex não está instalado. É só uma alternativa ao Claude.")
        elif api:
            out.update(estado=LIGADO, texto="Cobrando do crédito da OpenAI (chave " + out["final"] + ").")
        elif x["logado"]:
            out.update(estado=LIGADO, texto="Pelo login do ChatGPT. Alternativa: só entra se você escolher um modelo GPT.")
        else:
            out.update(estado=FALTA, texto="Instalado, mas sem login. Rode codex login.")
    elif i == "elevenlabs":
        vid = _voz.status()["elevenlabs"]["voice_id"]
        if tem and vid:
            out.update(estado=LIGADO, rotulo="reserva pronta", texto="Entra se o VoiceStudio estiver fechado. Voz: " + (_voz.status()["elevenlabs"]["nome_voz"] or vid) + ".")
        else:
            out.update(estado=FALTA, rotulo="reserva, desligada", texto=("Chave salva, mas sem voz escolhida" if tem else "Sem chave e sem voz")
                       + ": hoje o VoiceStudio narra sozinho e, se fechar, o Estúdio avisa em vez de gastar.")
    else:
        if not tem:
            out.update(estado=FALTA, texto="Cole a chave em “Trocar chave”.")
        else:
            t = out["teste"]
            if t and not t.get("ok"): out.update(estado=FORA, texto="A chave não passou no teste (" + t["quando"] + "): " + t["texto"])
            else: out.update(estado=LIGADO, texto="Chave " + out["final"] + (f". Testada em {t['quando']}." if t else ". Ainda não testada."))
    if app["var"] and out["teste"] and i in ("claude", "codex", "elevenlabs") and not out["teste"].get("ok"):
        out["texto"] += " Último teste da chave falhou: " + out["teste"]["texto"]
    out["rotulo"] = out["rotulo"] or ROTULO[out["estado"]]
    out["bola"] = BOLA[out["estado"]]
    out.setdefault("custo", app["custo"])
    return out


# app da conexão -> item do MANIFESTO de atualizar.py (a linha mostra "Atualização disponível" com o resultado do último check)
ATUALIZACAO = {"voicestudio": "VoiceStudio", "claude": "Claude Code", "codex": "Codex"}


def atualizacao(app_id: str) -> dict | None:
    nome = ATUALIZACAO.get(app_id)
    if not nome:
        return None
    try:
        import atualizar
        d = atualizar.ler_json(atualizar.ESTADO, {}) or {}
        i = next((x for x in d.get("itens", []) if x.get("nome") == nome), None)
        return i if i and i.get("estado") in ("disponível", "segurada", "na fila") and i.get("nova") else None
    except Exception:
        return None


def lista(cfg: dict | None = None) -> list[dict]:
    import ia
    cfg = cfg or ia.config()
    return [{**a, **situacao(a, cfg), "tem_chave": bool(_valor(a)), "atualizacao": atualizacao(a["id"]),
             "em_uso": (a["id"] == "claude" and cfg.get("provedor") == "claude") or (a["id"] == "codex" and cfg.get("provedor") == "openai"),
             "testavel": True} for a in APPS]


# ───────────── testes (só consultam; nada gera nem cobra) ─────────────

def _consultar(url: str, headers: dict | None, nome: str, abrir=None, ok_texto=None) -> dict:
    abrir = abrir or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": "Estudio/1.3", **(headers or {})})
    try:
        with abrir(req, timeout=25) as r:
            corpo = r.read()
        try: dados = json.loads(corpo)
        except ValueError: dados = {}
    except urllib.error.HTTPError as e:
        msg = {401: f"A {nome} não aceitou essa chave. Confira se copiou inteira, sem espaço.",
               403: f"A {nome} bloqueou essa chave (sem permissão). Crie outra no painel.",
               429: f"A chave existe, mas a {nome} recusou por limite ou falta de crédito."}.get(e.code, f"A {nome} respondeu com erro {e.code}.")
        return {"ok": False, "texto": msg}
    except (urllib.error.URLError, OSError, TimeoutError):
        return {"ok": False, "texto": f"Não consegui falar com a {nome}. Veja a internet e tente de novo."}
    return {"ok": True, "texto": ok_texto(dados) if ok_texto else "Funcionou", "dados": dados}


def testar(app_id: str, abrir=None, cfg: dict | None = None) -> dict:
    """{ok, texto}. Custo sempre zero: lista modelos, consulta saldo ou o login; nunca gera imagem, vídeo ou voz."""
    app = POR_ID.get(app_id)
    if not app: return {"ok": False, "texto": "Aplicativo desconhecido."}
    esquecer()
    chave = _valor(app)
    if app_id == "voicestudio":
        import voicestudio
        r = {"ok": True, "texto": "No ar e respondendo."} if voicestudio.no_ar() else {"ok": False, "texto": "Fechado. Abra o VoiceStudio e teste de novo."}
    elif app_id == "claude":
        c = claude_login()
        if not c["binario"]: r = {"ok": False, "texto": "O Claude Code não está instalado."}
        elif chave:
            k = _consultar("https://api.anthropic.com/v1/models", {"x-api-key": chave, "anthropic-version": "2023-06-01"}, "Anthropic", abrir,
                           lambda d: f"Chave da API aceita ({len(d.get('data') or [])} modelos)")
            r = {"ok": k["ok"], "texto": (("Login do plano ok e " if c["logado"] else "") + k["texto"][0].lower() + k["texto"][1:]) if k["ok"] else k["texto"]}
        elif c["logado"]: r = {"ok": True, "texto": "Login do plano funcionando (sem chave da API, sem custo)."}
        else: r = {"ok": False, "texto": "Sem login e sem chave. Rode claude e entre."}
    elif app_id == "codex":
        x = codex_login()
        if chave:
            r = chaves.testar_openai(chave, abrir)
        elif x["logado"]: r = {"ok": True, "texto": "Login do ChatGPT funcionando (sem custo)."}
        elif not x["binario"]: r = {"ok": False, "texto": "O Codex não está instalado."}
        else: r = {"ok": False, "texto": "Instalado, mas sem login. Rode codex login."}
    elif not chave:
        r = {"ok": False, "texto": "Falta a chave. Cole em “Trocar chave”."}
    elif app_id == "kie":
        r = _consultar("https://api.kie.ai/api/v1/chat/credit", {"Authorization": "Bearer " + chave}, "kie.ai", abrir,
                       lambda d: "Chave aceita. Saldo: " + _creditos(d))
        if r["ok"] and r["dados"].get("code") not in (None, 200):
            r = {"ok": False, "texto": "A kie.ai não aceitou essa chave (" + str(r["dados"].get("msg") or r["dados"].get("code")) + ")."}
    elif app_id == "groq":
        r = _consultar("https://api.groq.com/openai/v1/models", {"Authorization": "Bearer " + chave}, "Groq", abrir,
                       lambda d: f"Funcionou ({len(d.get('data') or [])} modelos, a transcrição está liberada)")
    elif app_id == "elevenlabs":
        r = _consultar("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": chave}, "ElevenLabs", abrir,
                       lambda d: f"Plano {d.get('tier', '?')}: {d.get('character_count', 0)} de {d.get('character_limit', 0)} caracteres usados no mês")
    elif app_id == "pexels":
        r = _consultar("https://api.pexels.com/v1/search?query=mar&per_page=1", {"Authorization": chave}, "Pexels", abrir)
    elif app_id == "pixabay":
        r = _consultar("https://pixabay.com/api/?" + urllib.parse.urlencode({"key": chave, "q": "mar", "per_page": 3}), None, "Pixabay", abrir)
    elif app_id == "freesound":
        r = _consultar("https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode({"query": "click", "page_size": 1, "token": chave}), None, "Freesound", abrir)
    elif app_id == "jamendo":
        r = _consultar("https://api.jamendo.com/v3.0/tracks/?" + urllib.parse.urlencode({"client_id": chave, "format": "json", "limit": 1}), None, "Jamendo", abrir)
        if r["ok"] and (r["dados"].get("headers") or {}).get("status") == "failed":
            r = {"ok": False, "texto": "O Jamendo não aceitou esse Client ID."}
    else:
        r = {"ok": False, "texto": "Sem teste para esse aplicativo."}
    r = {"ok": bool(r["ok"]), "texto": chaves._limpa(r["texto"], chave)}
    if app["var"] or app_id in ("voicestudio",):
        try: _guardar_teste(app, r)
        except OSError: pass
    return r


def _creditos(d: dict) -> str:
    try:
        cr = float(d.get("data"))
        return f"{cr:,.0f} créditos".replace(",", ".") + f" (~US$ {cr * 0.005:.2f})".replace(".", ",")
    except (TypeError, ValueError):
        return "não consegui ler o saldo"


def salvar_chave(app_id: str, valor: str) -> dict:
    """Guarda a chave em app/.env e testa (de graça). {ok, texto, final}. O valor nunca volta no texto."""
    app = POR_ID.get(app_id)
    if not app or not app["var"]: return {"ok": False, "texto": "Esse aplicativo não usa chave.", "final": ""}
    try:
        if app_id in ("claude", "codex"):
            chaves.salvar("anthropic" if app_id == "claude" else "openai", valor)
            fim = "…" + valor.strip()[-4:]
        else:
            fim = chaves.gravar_chave(app["var"], valor)
    except ValueError as e:
        return {"ok": False, "texto": str(e), "final": ""}
    r = testar(app_id)
    return {**r, "final": fim}


def main(argv=None) -> None:
    a = list(argv if argv is not None else sys.argv[1:])
    if a[:1] == ["testar"] and len(a) > 1:
        print(json.dumps(testar(a[1]), ensure_ascii=False))
        return
    for x in lista():
        print(f"{x['bola']} {x['nome']:<12} {x['rotulo']:<18} {x['custo']:<24} {x['texto']}")


if __name__ == "__main__":
    main()
