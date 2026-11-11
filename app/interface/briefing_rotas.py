"""Botão "Me ajuda a pensar" do campo "O que você quer ver" (Criar vídeo, passo 4).

Recebe o formato, o cliente e o que o João já escreveu. Em formato de ROTEIRO (Diálogo 3D, motion...) devolve 3 roteiros
prontos, cada um com elenco, cenário e clima já escolhidos (o botão "Usar este roteiro" joga tudo nos campos da tela);
nos outros, 3 sugestões de briefing. Antes de chamar a IA, junta o contexto do cliente/produto do swipe-file do João
(contexto_cliente.py: oferta, preço, dor, anúncios que ele já tem) e o estilo de referência principal do formato.
Roda o Claude Code em modo texto (Sonnet, sem ferramentas). O custo cai no livro do Estúdio (custos.registrar_execucao).

Registrado no servidor com:
    from briefing_rotas import register as register_briefing
    register_briefing(app)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

from flask import jsonify, request

from _comum import claude_bin, cliente as _cliente, ler_json
import contexto_cliente as _ctx
import custos as _custos
import formatos as _fmt

MODELO = "sonnet"   # o João pediu o Sonnet: roteiro bom compensa os centavos a mais
TIMEOUT = 180
MAX_REGRAS = 15
MAX_TEXTO_REGRA = 380
MAX_IDEIA = 1500
MAX_IDENTIDADE = 900

SISTEMA = ("Você é o roteirista do João, que faz vídeos curtos de marketing: ajuda a decidir o briefing e escreve roteiros. "
           "Escreva como ele fala: direto, simples, sem guru, sem enrolação, sem emoji e sem ponto de exclamação. "
           "Responda SOMENTE com JSON válido, sem texto antes ou depois e sem bloco de código.")

ENTRADAS = {"video": "um vídeo gravado por ele", "roteiro": "um roteiro (texto pronto)",
            "filmagem": "vários clipes de um evento", "cortar": "um vídeo bruto só pra cortar"}


def _curto(txt, n: int) -> str:
    txt = re.sub(r"\s+", " ", str(txt or "")).strip()
    return txt if len(txt) <= n else txt[:n - 1].rstrip() + "…"


def _regras(slug: str, cliente_nome: str) -> tuple[list[str], list[str]]:
    """Só os textos: as do cliente primeiro (já vêm por peso), depois as do formato, no máximo MAX_REGRAS no total."""
    apr = _fmt.aprendizado(slug, cliente_nome)
    do_cli = [_curto(r.get("texto"), MAX_TEXTO_REGRA) for r in apr.get("cliente", []) if r.get("texto")]
    do_fmt = [_curto(r.get("texto"), MAX_TEXTO_REGRA) for r in apr.get("formato", []) if r.get("texto")]
    do_cli = do_cli[:6]
    return do_fmt[:MAX_REGRAS - len(do_cli)], do_cli


def _identidade(cliente_nome: str) -> str:
    c = _cliente(cliente_nome) if cliente_nome else None
    arq = c["pasta"] / "identidade.json" if c else None
    if not arq or not arq.is_file():
        return ""
    dados = ler_json(arq, None)
    if not dados:
        return ""
    return _curto(json.dumps(dados, ensure_ascii=False), MAX_IDENTIDADE)


def montar_prompt(slug: str, cliente_nome: str, ideia: str, entrada: str, roteiro: str = "") -> str | None:
    f = _fmt.carregar(slug)
    if not f:
        return None
    ideia = (ideia or "").strip()[:MAX_IDEIA]
    r_fmt, r_cli = _regras(slug, cliente_nome)
    linhas = [f"FORMATO: {f.get('titulo', slug)}", f"O que é: {_curto(f.get('frase'), 400)}"]
    if entrada in ENTRADAS:
        linhas.append(f"O João vai mandar: {ENTRADAS[entrada]}")
    if r_fmt:
        linhas += ["", "REGRAS DO FORMATO (valem pra todo cliente):"] + [f"- {t}" for t in r_fmt]
    if r_cli:
        linhas += ["", f"REGRAS DO CLIENTE {cliente_nome} (gosto dele neste formato):"] + [f"- {t}" for t in r_cli]
    ident = _identidade(cliente_nome)
    if ident:
        linhas += ["", f"CARA DO CLIENTE {cliente_nome} (identidade.json): {ident}"]
    linhas += ["", 'O QUE O JOÃO JÁ ESCREVEU NO CAMPO "O que você quer ver": '
               + (f"«{ideia}»" if ideia else "(vazio, ele ainda não sabe o que quer)")]
    ctx = _ctx.contexto(cliente_nome, ideia)
    if ctx:
        linhas += ["", "CONTEXTO DO CLIENTE E DO PRODUTO (do swipe-file do João; use só estes fatos):", ctx]
    modo_roteiro = f.get("entrada") == "roteiro" or entrada == "roteiro"
    if not modo_roteiro:
        linhas += ["", TAREFA_BRIEFING]
        return "\n".join(linhas)
    principal = next((e for e in _fmt.estudos(slug) if e.get("principal")), None)
    if principal:
        linhas += ["", "ESTILO DE REFERÊNCIA PRINCIPAL DO FORMATO (a edição já segue isso; use o ritmo das falas como modelo):",
                   _curto(principal.get("estudo"), 900),
                   "ROTEIRO DESSA REFERÊNCIA (estrutura que funcionou; não copie o tema):", _curto(principal.get("roteiros"), 1400)]
    esc = f.get("escolhas") or []
    if esc:
        linhas += ["", "OPÇÕES PRONTAS DA TELA (use o nome exato quando servir; se o negócio pedir outra coisa, descreva curto):"]
        linhas += [f"- {e.get('campo')}: " + " | ".join(e.get("opcoes") or []) for e in esc]
    roteiro = (roteiro or "").strip()[:4000]
    if roteiro:   # ele já tem o roteiro: só completa o que falta, sem reescrever as falas
        linhas += ["", "O ROTEIRO QUE O JOÃO JÁ TEM (não reescreva as falas):", roteiro, "", TAREFA_COMPLETAR]
    else:
        linhas += ["", TAREFA_ROTEIRO if f.get("roteiro_modo") == "dialogo" else TAREFA_ROTEIRO_NARRADO]   # hoje todo estilo de roteiro é narração em off (o diálogo "Nome: fala" saiu com o Diálogo 3D)
    return "\n".join(linhas)


TAREFA_BRIEFING = """TAREFA
O briefing é o que o João quer ver no vídeo: oferta, tema, o que mostrar, o que evitar. Ajude ele a decidir.
1. "perguntas": até 3 perguntas curtas, que mudariam o vídeo se ele respondesse. Se a ideia já está clara, mande menos (ou nenhuma).
2. "sugestoes": exatamente 3 briefings prontos pra ele colar no campo. Cada um tem "titulo" (até 5 palavras) e "texto" (2 a 5 linhas, na voz do João, em primeira pessoa, concreto).
   - Se ele já escreveu algo, as 3 desenvolvem essa ideia por ângulos diferentes. Se está vazio, são 3 ideias diferentes que cabem no formato e no cliente.
   - Respeite o formato e as regras acima: estrutura, fórmula do roteiro, tempo, elenco. Se as regras trazem uma fórmula ou duração, o texto já diz a ideia dentro dela.
   - Não invente número, preço, resultado nem fato do cliente que não esteja acima.

Devolva SOMENTE este JSON:
{"perguntas": ["..."], "sugestoes": [{"titulo": "...", "texto": "..."}]}"""

TAREFA_COMPLETAR = """TAREFA: o João já tem o roteiro acima. Complete só o que falta pra virar vídeo, numa sugestão só.
- "roteiro": as MESMAS falas, palavra por palavra; só ponha no formato "Nome: fala", uma por linha, se ainda não estiver (tire ponto de exclamação e aspas).
- "elenco": cada pessoa que fala no roteiro. Use o nome exato da lista da tela quando for ela (Humano (série), Claude, Astra...); senão descreva curto com gênero, idade e o que identifica (óculos, jaleco, uniforme, terno, cabelo).
- "cenario" e "clima": um da lista da tela ou o lugar descrito curto (ex.: "Palco de evento, telão com o nome Imersão Mentor").
- "titulo" (até 5 palavras) e "texto" (o briefing em 1 linha).
"perguntas": [].

Devolva SOMENTE este JSON:
{"perguntas": [], "sugestoes": [{"titulo": "...", "texto": "...", "elenco": ["..."], "cenario": "...", "clima": "...", "roteiro": "Nome: fala\\nNome: fala"}]}"""

TAREFA_ROTEIRO = """TAREFA: escreva 3 roteiros diferentes, prontos pra virar vídeo (ângulos diferentes do mesmo pedido).
Cada roteiro:
- "titulo": até 5 palavras.
- "texto": o briefing em 1 ou 2 linhas (a ideia + o produto/chamada), na voz do João.
- "elenco": lista de quem aparece (2 a 4). Use um nome da lista da tela quando servir. Pessoa que não está na lista: descreva curto com gênero, idade e o que identifica (ex.: "Dono de ótica, homem, 45 anos, camisa social, óculos"; "Atendente, mulher, 25 anos, uniforme, cabelo comprido").
  Siga o tema do pedido (o formato é 3D criativo, não só a série do Claudio). Se o tema é IA ou a série do Claudio: "Humano (série)" fazendo pedidos ao "Claude" (às vezes Astra ou Codex), na fórmula das regras.
  Personagem de IA (Claude/Claudio, GPT, Gemini, Astra, Codex, Robô) SÓ quando o tema do vídeo é IA. Anúncio de um negócio = gente do negócio (dono, cliente, atendente, sócio).
- "cenario" e "clima": um da lista da tela, ou descreva o lugar certo pro negócio (ex.: "Ótica de rua, balcão com armações").
- "roteiro": uma fala por linha, no formato "Nome: fala". 25 a 45 segundos (70 a 120 palavras). Falas curtas, conversa de verdade.
  Anúncio: a 1ª fala já é a dor do público; depois a virada; depois o produto com os fatos do contexto (nome, preço) e uma chamada curta no fim.
  Humor: problema na 1ª fala, escalada, punchline curta. Sem ponto de exclamação, sem aspas, sem emoji.
- Não invente número, preço, resultado nem fato que não esteja no contexto.
"perguntas": no máximo 2, só se faltar algo que mudaria o roteiro (senão []).

Devolva SOMENTE este JSON:
{"perguntas": [], "sugestoes": [{"titulo": "...", "texto": "...", "elenco": ["..."], "cenario": "...", "clima": "...", "roteiro": "Nome: fala\nNome: fala"}]}"""


TAREFA_ROTEIRO_NARRADO = """TAREFA: escreva 3 roteiros diferentes de NARRAÇÃO (uma voz só, em off), prontos pra virar vídeo (ângulos diferentes do mesmo pedido).
Cada roteiro:
- "titulo": até 5 palavras.
- "texto": o briefing em 1 ou 2 linhas (a ideia + pra onde o vídeo vira no fim), na voz do João.
- "roteiro": SÓ o que o narrador fala, uma oração por linha, SEM "Nome:" na frente, sem personagem, sem rubrica, sem aspas, sem ponto de exclamação, sem emoji.
  Língua do povo, frase curta, falada como gente fala. 40 a 60 segundos (100 a 150 palavras).
  Estrutura: gancho com uma PERGUNTA ou uma frase que prende na 1ª linha (nome conhecido ou situação que todo mundo já viveu) -> o caso real, com nome, lugar e data que dê pra achar em foto e matéria -> o mecanismo (estudo, livro, dado, só se você tiver certeza de que existe) -> vira pra você ou pro seu negócio -> fecho seco, curto.
  A ideia central usa sempre a MESMA palavra (ex.: fato x crença); não troque por sinônimo no meio. Nome difícil de falar vai pra tela, não pra fala.
- Não invente número, estudo, citação nem fato. Caso e estudo só se forem reais e você tiver certeza; senão fique no que todo mundo sabe.
"elenco": [], "cenario": "", "clima": "" (não usa).
"perguntas": no máximo 2, só se faltar algo que mudaria o roteiro (senão []).

Devolva SOMENTE este JSON:
{"perguntas": [], "sugestoes": [{"titulo": "...", "texto": "...", "elenco": [], "cenario": "", "clima": "", "roteiro": "Oração.\\nOração.\\nOração."}]}"""


def extrair_json(txt: str):
    """Pega o objeto JSON da resposta, mesmo que venha com bloco de código ou texto em volta."""
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.I)
    try:
        return json.loads(txt)
    except ValueError:
        pass
    a, b = txt.find("{"), txt.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(txt[a:b + 1])
        except ValueError:
            return None
    return None


def limpar(dados) -> dict | None:
    if not isinstance(dados, dict):
        return None
    perguntas = [_curto(p, 200) for p in (dados.get("perguntas") or []) if isinstance(p, str) and p.strip()][:3]
    sugestoes = []
    for s in dados.get("sugestoes") or []:
        if not isinstance(s, dict):
            continue
        texto = str(s.get("texto") or "").strip()
        if texto:
            item = {"titulo": _curto(s.get("titulo") or "Sugestão", 60), "texto": texto[:1200]}
            roteiro = str(s.get("roteiro") or "").replace("!", ".").strip()
            if roteiro:
                elenco = s.get("elenco") or []
                item.update(roteiro=roteiro[:3000],
                            elenco=[_curto(x, 80) for x in (elenco if isinstance(elenco, list) else [elenco]) if str(x).strip()][:4],
                            cenario=_curto(s.get("cenario") or "", 120), clima=_curto(s.get("clima") or "", 40))
            sugestoes.append(item)
    sugestoes = sugestoes[:3]
    return {"perguntas": perguntas, "sugestoes": sugestoes} if sugestoes else None


def chamar_claude(prompt: str) -> tuple[str | None, str]:
    """Roda o Claude Code só com texto. Devolve (resposta do modelo, mensagem de erro amigável)."""
    exe = claude_bin()
    if not exe:
        return None, "Não achei o Claude Code neste computador. Instale e entre na sua conta."
    cmd = [exe, "-p", "--model", MODELO, "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--disable-slash-commands", "--strict-mcp-config", "--system-prompt", SISTEMA]
    try:
        with tempfile.TemporaryDirectory(prefix="briefing-") as pasta:   # pasta vazia: não carrega contexto de projeto
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd=pasta,
                               env={**os.environ, "MAX_THINKING_TOKENS": "0"})   # sem "pensar" longo: mais rápido e barato
    except subprocess.TimeoutExpired:
        return None, "A IA demorou demais pra responder. Tenta de novo em um minuto."
    except OSError:
        return None, "Não consegui abrir o Claude Code. Veja se ele está instalado e logado."
    try:
        saida = json.loads(p.stdout)
    except ValueError:
        saida = None
    if isinstance(saida, list):                       # versões que devolvem a lista de eventos
        saida = next((e for e in reversed(saida) if isinstance(e, dict) and e.get("type") == "result"), None)
    if not isinstance(saida, dict):
        return None, "A IA não respondeu direito. Tenta de novo."
    try:                                              # o custo vai pro livro mesmo se a resposta vier torta
        _custos.registrar_execucao({"provedor": "claude", "modelo": MODELO}, saida.get("total_cost_usd"),
                                   saida.get("usage"), None)
    except Exception:
        pass
    if p.returncode != 0 or saida.get("is_error"):
        return None, "A IA não conseguiu responder agora. Confira se o Claude Code está logado e tenta de novo."
    return str(saida.get("result") or ""), ""


def register(app):
    @app.post("/api/briefing-ajuda", endpoint="briefing_ajuda")
    def briefing_ajuda():
        d = request.get_json(silent=True) or {}
        slug = str(d.get("formato") or "").strip()
        cliente_nome = str(d.get("cliente") or "").strip()
        if cliente_nome.lower() == _fmt.AVULSO.lower() or not _cliente(cliente_nome):
            cliente_nome = ""
        prompt = montar_prompt(slug, cliente_nome, str(d.get("ideia") or ""), str(d.get("entrada") or ""), str(d.get("roteiro") or ""))
        if not prompt:
            return jsonify(ok=False, erro="Escolha o formato antes de pedir ajuda."), 400
        texto, erro = chamar_claude(prompt)
        if erro:
            return jsonify(ok=False, erro=erro), 502
        resposta = limpar(extrair_json(texto))
        if not resposta:
            return jsonify(ok=False, erro="A IA respondeu em um formato estranho. Tenta de novo."), 502
        return jsonify(ok=True, **resposta)
