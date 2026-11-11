#!/usr/bin/env python3
"""
emocao — voz com emoção, de graça (PLANO-2.0, item 6).

O motor ligado (OmniVoice) IMITA a emoção do áudio de referência; nenhum motor instalado aceita emoção por texto. Então a
emoção vem de variações FIXAS de cada voz, uma por emoção ("<voz> · animado"): perfis clonados de uma amostra falada com
aquela emoção. O Claude marca a emoção de cada frase do roteiro e a narração usa, bloco a bloco, o perfil daquela emoção
(sempre o mesmo timbre; o tempo das palavras continua vindo do Groq, depois).

    emocoes.json (ao lado do roteiro.txt)   {"linhas": [{"texto": "...", "emocao": "firme"}, ...]}   uma emoção por frase
    app/.cache/vozes-emocao.json            o mapa das variações:
        {"vozes": {<voz>: {<emocao>: {"status": "aguardando"|"aprovada", "perfil": "<id>", "semente": 7, "texto": "..."}}},
         "candidatos": {<voz>: {<emocao>: [{"id", "video", "ini", "fim", "texto", ...}]}}}     (trechos do João, ver emocao_joao.py)

Regra de ouro (Aprovou?): a amostra é gerada e fica "aguardando"; o PERFIL só nasce quando o João aprova na tela Vozes.
Sem variação aprovada, a frase sai com a voz normal (nada muda). Nunca apaga voz nem perfil.

    python3 emocao.py marcar <pasta>                     # marca a emoção de cada frase do roteiro.txt (Claude Sonnet)
    python3 emocao.py narrar <pasta> --voz <id> --saida voz.mp3
    python3 emocao.py amostras <voz>                     # gera as amostras (6 emoções) pra o João ouvir e aprovar
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO, RAIZ, gravar_json, ler_json  # noqa: E402

MAPA = ESTUDIO / ".cache" / "vozes-emocao.json"
AMOSTRAS = ESTUDIO / ".cache" / "vozes-emocao"
NORMAL = "normal"   # sem variação: a voz como ela é

# Emoções fixas e poucas. "amostra" é o texto que o VoiceStudio fala pra gerar a variação (pontuação e palavras que puxam a
# emoção; ~12 a 15 s); "velocidade" é o único botão de ritmo do /generate; "sussurro" só vale se a voz tem descrição conhecida.
EMOCOES: dict[str, dict] = {
    "calmo": {"rotulo": "Calmo", "velocidade": 0.94, "sussurro": False,
              "dica": "explica sem pressa, tom baixo",
              "amostra": "Respira. Não tem pressa nenhuma. A gente olha o que aconteceu com calma, passo a passo, "
                         "e entende o que realmente importa nessa história toda."},
    "firme": {"rotulo": "Firme", "velocidade": 0.97, "sussurro": False,
              "dica": "afirma, sem hesitar, frase curta",
              "amostra": "Isso não é opinião. É fato. Eu já vi acontecer, e vai acontecer de novo. "
                         "Quem ignora isso paga caro, e paga sozinho. Anota isso."},
    "indignado": {"rotulo": "Indignado", "velocidade": 1.08, "sussurro": False,
                  "dica": "revolta, voz mais forte e rápida",
                  "amostra": "Como assim? Isso é um absurdo! Cobram o dobro, entregam metade, e ainda dizem que a "
                             "culpa é sua. Não dá pra aceitar uma coisa dessas!"},
    "animado": {"rotulo": "Animado", "velocidade": 1.1, "sussurro": False,
                "dica": "empolgado, sobe o tom",
                "amostra": "Olha só que incrível! Em um mês, o resultado dobrou. Dobrou! E o melhor é que qualquer "
                           "pessoa consegue fazer isso, começando hoje mesmo!"},
    "segredo": {"rotulo": "Segredo", "velocidade": 0.9, "sussurro": True,
                "dica": "baixinho, perto do ouvido",
                "amostra": "Vem cá, chega mais perto. Vou te contar uma coisa que quase ninguém sabe. "
                           "Fica entre a gente, tá? Ninguém te conta isso."},
    "pergunta": {"rotulo": "Pergunta", "velocidade": 1.0, "sussurro": False,
                 "dica": "dúvida que sobe no fim",
                 "amostra": "Você já parou pra pensar nisso? Será que é coincidência? Ou será que alguém ganha com isso? "
                            "E se a resposta estiver bem na sua frente?"},
}
ORDEM = list(EMOCOES)
TODAS = ORDEM + [NORMAL]
ROTULOS = {**{k: v["rotulo"] for k, v in EMOCOES.items()}, NORMAL: "Normal"}
VOZ_JOAO = "8800a992"   # o perfil do VoiceStudio com a voz clonada do João (Editorial)


# ── frases e marcação ───────────────────────────────────────────────────────────────────────────────────────────────
def frases(roteiro: str) -> list[str]:
    """As frases do roteiro, na ordem: uma por linha, e a linha comprida quebra no ponto final/interrogação/reticências."""
    out: list[str] = []
    for linha in (roteiro or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        for f in re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ\"“(¿])", linha):
            if f.strip():
                out.append(f.strip())
    return out


_INDIGNADO = re.compile(r"absurd|inaceit|vergonh|mentira|roub|nojo|revolt|safad|descaso|palha[cç]|golpe|enganad|injust", re.I)
_SEGREDO = re.compile(r"^(psiu|vem c[aá]|chega mais|entre n[oó]s|vou te contar|segredo|ningu[eé]m te conta|fica entre)", re.I)
_ANIMADO = re.compile(r"incr[ií]vel|dobrou|triplic|bateu recorde|funcionou|consegu|explodiu|bomb", re.I)


def heuristica(frase: str) -> str:
    """Emoção de uma frase sem IA (rede de segurança quando o Claude não responde, e frase nova numa edição)."""
    f = frase.strip()
    if f.endswith("?"):
        return "pergunta"
    if _SEGREDO.search(f):
        return "segredo"
    if _INDIGNADO.search(f) or f.endswith("!") and len(f.split()) > 5:
        return "indignado"
    if _ANIMADO.search(f) or f.endswith("!"):
        return "animado"
    if len(f.split()) <= 7:
        return "firme"
    return "calmo"


def _prompt_marcar(fs: list[str]) -> str:
    lista = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(fs))
    opcoes = "\n".join(f"- {k}: {v['dica']}" for k, v in EMOCOES.items()) + f"\n- {NORMAL}: voz neutra, só informa"
    return (f"Você dirige a locução de um vídeo curto em português. Marque a emoção com que cada frase deve ser FALADA, "
            f"lendo o roteiro inteiro (a emoção segue o sentido e a virada do texto, não só a pontuação).\n\nEmoções permitidas:\n"
            f"{opcoes}\n\nRegras: use só essas palavras; varie quando o texto varia, mas sem trocar a cada frase sem motivo "
            f"(a mesma emoção por vários trechos seguidos é normal); pergunta de verdade é \"pergunta\"; revelação é \"segredo\" "
            f"ou \"firme\"; o gancho do começo costuma ser \"firme\" ou \"pergunta\".\n\nFRASES:\n{lista}\n\n"
            f"Responda SÓ com JSON, sem texto em volta: {{\"emocoes\": [\"firme\", \"calmo\", ...]}} com EXATAMENTE {len(fs)} itens, na ordem.")


def _chamar_claude(prompt: str, timeout: int = 120) -> str | None:
    """Uma chamada leve ao Claude Code (Sonnet, sem ferramentas, sem pensar longo). None se não deu."""
    from _comum import claude_bin
    exe = claude_bin()
    if not exe:
        return None
    cmd = [exe, "-p", "--model", "sonnet", "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--disable-slash-commands", "--strict-mcp-config"]
    try:
        import os
        with tempfile.TemporaryDirectory(prefix="emocao-") as pasta:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=pasta,
                               env={**os.environ, "MAX_THINKING_TOKENS": "0"})
        saida = json.loads(p.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    if isinstance(saida, list):
        saida = next((e for e in reversed(saida) if isinstance(e, dict) and e.get("type") == "result"), None)
    if not isinstance(saida, dict) or saida.get("is_error"):
        return None
    try:
        import custos
        custos.registrar_execucao({"provedor": "claude", "modelo": "sonnet"}, saida.get("total_cost_usd"), saida.get("usage"), None)
    except Exception:  # noqa: BLE001
        pass
    return str(saida.get("result") or "")


def _lista_da_resposta(txt: str | None, n: int) -> list[str] | None:
    if not txt:
        return None
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        lst = json.loads(m.group(0)).get("emocoes") if m else None
    except ValueError:
        return None
    if not isinstance(lst, list) or len(lst) != n:
        return None
    lst = [str(x).strip().lower() for x in lst]
    return [x if x in TODAS else "calmo" for x in lst]


def marcar(roteiro: str, chamar=None) -> list[dict]:
    """A emoção de cada frase: [{texto, emocao}]. O Claude (Sonnet) decide lendo o roteiro todo; sem resposta boa, a heurística."""
    fs = frases(roteiro)
    if not fs:
        return []
    chamar = chamar or _chamar_claude
    emos = _lista_da_resposta(chamar(_prompt_marcar(fs)), len(fs))
    if not emos:
        emos = [heuristica(f) for f in fs]
    return [{"texto": f, "emocao": e} for f, e in zip(fs, emos)]


def alinhar(roteiro: str, antigas: list[dict] | None) -> list[dict]:
    """Casa as emoções já marcadas com as frases ATUAIS do roteiro (por texto igual); frase nova ganha a heurística.
    Assim o roteiro editado não perde o que o João já trocou."""
    por_texto = {}
    for l in antigas or []:
        if isinstance(l, dict) and l.get("texto") and l.get("emocao") in TODAS:
            por_texto.setdefault(l["texto"].strip(), l["emocao"])
    return [{"texto": f, "emocao": por_texto.get(f) or heuristica(f)} for f in frases(roteiro)]


def arquivo(pasta: Path) -> Path:
    return Path(pasta) / "emocoes.json"


def ler(pasta: Path, roteiro: str | None = None) -> list[dict]:
    """As linhas {texto, emocao} desta pasta, alinhadas com o roteiro.txt de hoje. [] se nunca foi marcado."""
    pasta = Path(pasta)
    d = ler_json(arquivo(pasta), None)
    if not isinstance(d, dict) or not d.get("linhas"):
        return []
    if roteiro is None:
        r = pasta / "roteiro.txt"
        roteiro = r.read_text(encoding="utf-8") if r.is_file() else ""
    return alinhar(roteiro, d["linhas"]) if roteiro.strip() else list(d["linhas"])


def gravar(pasta: Path, linhas: list[dict]) -> list[dict]:
    limpas = [{"texto": str(l.get("texto", "")).strip(), "emocao": l.get("emocao") if l.get("emocao") in TODAS else "calmo"}
              for l in linhas if str(l.get("texto", "")).strip()]
    gravar_json(arquivo(pasta), {"linhas": limpas})
    return limpas


def trocar(pasta: Path, emocoes: list[str]) -> list[dict]:
    """O João trocou as etiquetas: `emocoes` é uma emoção por frase do roteiro de hoje. Grava e devolve as linhas."""
    pasta = Path(pasta)
    r = pasta / "roteiro.txt"
    fs = frases(r.read_text(encoding="utf-8") if r.is_file() else "")
    if len(emocoes) != len(fs):
        raise ValueError("A lista de emoções não bate com as frases do roteiro.")
    return gravar(pasta, [{"texto": f, "emocao": e} for f, e in zip(fs, emocoes)])


# ── o mapa de variações ─────────────────────────────────────────────────────────────────────────────────────────────
def mapa() -> dict:
    d = ler_json(MAPA, {}) or {}
    d.setdefault("vozes", {})
    d.setdefault("candidatos", {})
    return d


def _salvar(d: dict) -> None:
    MAPA.parent.mkdir(parents=True, exist_ok=True)
    gravar_json(MAPA, d)


def perfil_da_emocao(voz_id: str, emocao: str) -> str:
    """O perfil da variação APROVADA dessa voz nessa emoção; sem ela, a própria voz (a frase sai normal)."""
    e = (mapa()["vozes"].get(voz_id) or {}).get(emocao) or {}
    return e["perfil"] if e.get("status") == "aprovada" and e.get("perfil") else voz_id


def variacoes(voz_id: str) -> dict:
    """{emocao: {status, perfil, semente, texto}} só das que existem."""
    return dict(mapa()["vozes"].get(voz_id) or {})


def tem_variacao(voz_id: str) -> bool:
    return any(e.get("status") == "aprovada" for e in variacoes(voz_id).values())


# ── a narração por blocos de emoção ─────────────────────────────────────────────────────────────────────────────────
MIN_BLOCO = 40   # frase mais curta que isso gruda na anterior (um bloco de 2 palavras com perfil de emoção soa estranho)


def grupos(linhas: list[dict], voz_id: str) -> list[tuple[str, str]]:
    """[(perfil, texto)]: frases seguidas com o MESMO perfil viram um bloco só. Frase curtinha gruda na anterior."""
    out: list[list] = []
    for l in linhas:
        perfil = perfil_da_emocao(voz_id, l.get("emocao") or NORMAL)
        texto = l["texto"].strip()
        if out and (out[-1][0] == perfil or len(texto) < MIN_BLOCO):
            out[-1][1] += "\n" + texto
        else:
            out.append([perfil, texto])
    return [(p, t) for p, t in out]


def narrar(linhas: list[dict], voz_id: str, saida: Path, falar=None) -> Path:
    """Fala o roteiro bloco a bloco, cada um com o perfil da emoção das suas frases, e cola tudo num mp3. Se nenhuma emoção
    tem variação aprovada, é UM pedido só com a voz normal (igual ao de antes). `falar(texto, arquivo, voz)` é o VoiceStudio."""
    saida = Path(saida)
    if falar is None:
        import voicestudio
        falar = voicestudio.falar
    gs = grupos(linhas, voz_id)
    if not gs:
        raise ValueError("Sem texto pra narrar.")
    if all(p == voz_id for p, _ in gs):
        return falar("\n".join(t for _, t in gs), saida, voz_id)
    with tempfile.TemporaryDirectory() as tmp:
        arqs = []
        for i, (perfil, texto) in enumerate(gs):
            a = Path(tmp) / f"{i:03d}.mp3"
            try:
                falar(texto, a, perfil)
            except ValueError as e:
                if perfil == voz_id:
                    raise
                print(f"aviso: a variação {perfil} falhou ({e}); esse trecho sai com a voz normal", file=sys.stderr)
                falar(texto, a, voz_id)
            arqs.append(a)
        lista = Path(tmp) / "lista.txt"
        lista.write_text("".join(f"file '{a.name}'\n" for a in arqs))
        saida.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(saida)],
                       check=True)
    return saida


def narrar_pasta(pasta: Path, voz_id: str, saida: Path, falar=None) -> Path:
    """A narração desta pasta (roteiro.txt + emocoes.json). Sem emocoes.json, ou sem texto marcado, é a narração de sempre."""
    pasta = Path(pasta)
    r = pasta / "roteiro.txt"
    roteiro = r.read_text(encoding="utf-8") if r.is_file() else ""
    linhas = ler(pasta, roteiro)
    if not linhas:
        if falar is None:
            import voicestudio
            falar = voicestudio.falar
        return falar(roteiro, Path(saida), voz_id)
    return narrar(linhas, voz_id, saida, falar)


# ── amostras e aprovação das variações (vozes desenhadas e arquétipos) ──────────────────────────────────────────────
def _instruct_conhecido(nome: str) -> str:
    """A descrição de voz desenhada (PRONTAS) pelo nome; vazia pras outras. Só ela deixa pôr 'whisper' no segredo."""
    import vozes
    base = vozes._limpa_nome(nome).lower()
    for p in vozes.PRONTAS:
        if p["nome"].lower() == base:
            return ", ".join(x for x in (vozes.GENEROS.get(p["genero"]), vozes.IDADES.get(p["idade"]), vozes.TONS.get(p["tom"])) if x)
    return ""


def eh_voz_do_joao(voz_id: str, nome: str = "") -> bool:
    if voz_id == VOZ_JOAO or re.search(r"jo[aã]o", nome or "", re.I):
        return True
    v = (ler_json(RAIZ / "clientes" / "Joao" / "identidade.json", {}) or {}).get("voz") or {}
    return isinstance(v, dict) and v.get("id") == voz_id


def _pasta_voz(voz_id: str) -> Path:
    d = AMOSTRAS / re.sub(r"[^A-Za-z0-9_.-]", "_", voz_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def amostra_mp3(voz_id: str, emocao: str) -> Path:
    return _pasta_voz(voz_id) / f"{emocao}.mp3"


def gerar_amostra(voz_id: str, emocao: str, nome_voz: str = "", semente: int = 7) -> Path:
    """Fala a amostra da emoção COM A VOZ dela (perfil fixo, então é a mesma pessoa) e guarda como 'aguardando'.
    Não cria perfil: isso só acontece na aprovação. Segredo usa 'whisper' quando a descrição da voz é conhecida."""
    import vozes
    emo = EMOCOES[emocao]
    campos = {"text": emo["amostra"], "language": "pt", "seed": semente, "speed": emo["velocidade"]}
    instr = _instruct_conhecido(nome_voz)
    if emo["sussurro"] and instr:
        campos["instruct"] = instr + ", whisper"
    else:
        campos["profile_id"] = voz_id
    pasta = _pasta_voz(voz_id)
    wav = pasta / f"{emocao}.wav"
    wav.write_bytes(vozes._multipart("/generate", campos, timeout=900))
    if wav.stat().st_size < 20000:
        raise ValueError("O VoiceStudio não devolveu a amostra. Ele está aberto?")
    mp3 = amostra_mp3(voz_id, emocao)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-b:a", "96k", str(mp3)], check=True)
    d = mapa()
    atual = d["vozes"].setdefault(voz_id, {}).get(emocao) or {}
    if atual.get("status") != "aprovada":   # o que já foi aprovado não é sobrescrito: refazer só vale pra quem ainda aguarda
        d["vozes"][voz_id][emocao] = {"status": "aguardando", "perfil": "", "semente": semente, "texto": emo["amostra"]}
        _salvar(d)
    return mp3


def gerar_amostras(voz_id: str, emocoes: list[str] | None = None, nome_voz: str = "", log=print) -> dict:
    """As amostras das emoções (todas, ou as pedidas) pra o João ouvir. Voz do João é outro caminho (trechos dele)."""
    if eh_voz_do_joao(voz_id, nome_voz):
        raise ValueError("A voz do João não ganha emoção sintética: use trechos reais dele (Vozes → Emoção).")
    for e in emocoes or ORDEM:
        log(f"amostra: {e}")
        gerar_amostra(voz_id, e, nome_voz)
    return variacoes(voz_id)


def _nome_variacao(nome_voz: str, emocao: str) -> str:
    import vozes
    return f"{vozes._limpa_nome(nome_voz)} · {EMOCOES[emocao]['rotulo'].lower()}"


def _perfil_de(nome: str, wav: Path, texto: str, semente: int = 7) -> str:
    """Cria o perfil clonado (sem a prévia em português que o vozes._criar_perfil faz: a prévia aqui é a própria amostra)."""
    import vozes
    r = json.loads(vozes._multipart("/profiles", {"name": nome, "language": "Portuguese", "seed": semente, "ref_text": texto},
                                    {"ref_audio": wav}, timeout=120))
    return r["id"]


def aprovar(voz_id: str, emocao: str, nome_voz: str = "") -> str:
    """O João aprovou a amostra: nasce o perfil '<voz> · <emoção>' e a variação passa a valer. Devolve o id do perfil."""
    d = mapa()
    e = (d["vozes"].get(voz_id) or {}).get(emocao)
    wav = _pasta_voz(voz_id) / f"{emocao}.wav"
    if not e or not wav.is_file():
        raise ValueError("Essa emoção ainda não tem amostra. Gere a amostra primeiro.")
    if e.get("status") == "aprovada" and e.get("perfil"):
        return e["perfil"]
    pid = _perfil_de(_nome_variacao(nome_voz or voz_id, emocao), wav, e.get("texto") or EMOCOES[emocao]["amostra"], int(e.get("semente") or 7))
    e.update(status="aprovada", perfil=pid)
    _salvar(d)
    return pid


def recusar(voz_id: str, emocao: str, nome_voz: str = "") -> Path:
    """'Refazer': outra amostra (semente seguinte) no lugar da que aguarda. Variação aprovada não muda por aqui."""
    e = (mapa()["vozes"].get(voz_id) or {}).get(emocao) or {}
    if e.get("status") == "aprovada":
        raise ValueError("Essa já está aprovada e em uso.")
    return gerar_amostra(voz_id, emocao, nome_voz, semente=int(e.get("semente") or 7) + 1)


def registrar_aprovada(voz_id: str, emocao: str, perfil: str, texto: str = "") -> None:
    """Variação que já nasceu aprovada (trecho real do João que ele escolheu, ou gravação que ele subiu)."""
    d = mapa()
    d["vozes"].setdefault(voz_id, {})[emocao] = {"status": "aprovada", "perfil": perfil, "semente": 0, "texto": texto}
    _salvar(d)


def painel(vozes_lista: list[dict]) -> list[dict]:
    """Pra tela Vozes: uma linha por voz que tem (ou pode ter) emoção. [{id, nome, joao, emocoes: [{slug, rotulo, status, ...}]}]."""
    out = []
    for v in vozes_lista:
        if v.get("demo") or not v.get("pt"):
            continue
        var = variacoes(v["id"])
        joao = eh_voz_do_joao(v["id"], v["nome"])
        if not (var or v.get("padrao") or joao or v.get("clientes")):
            continue
        cand = mapa()["candidatos"].get(v["id"], {})
        out.append({"id": v["id"], "nome": v["nome"], "joao": joao, "padrao": v.get("padrao", False),
                    "emocoes": [{"slug": k, "rotulo": EMOCOES[k]["rotulo"], "dica": EMOCOES[k]["dica"],
                                 "status": (var.get(k) or {}).get("status", ""), "perfil": (var.get(k) or {}).get("perfil", ""),
                                 "amostra": amostra_mp3(v["id"], k).is_file(),
                                 "candidatos": [c for c in cand.get(k, []) if c.get("status") != "usado"]} for k in ORDEM]})
    return out


def _main(a: list[str]) -> int:
    if a[:1] == ["marcar"] and len(a) >= 2:
        p = Path(a[1])
        r = p / "roteiro.txt"
        linhas = gravar(p, marcar(r.read_text(encoding="utf-8")))
        print(json.dumps(linhas, ensure_ascii=False, indent=1))
    elif a[:1] == ["narrar"] and len(a) >= 2:
        voz = a[a.index("--voz") + 1] if "--voz" in a else "default"
        saida = Path(a[a.index("--saida") + 1] if "--saida" in a else "voz.mp3")
        print(narrar_pasta(Path(a[1]), voz, saida))
    elif a[:1] == ["amostras"] and len(a) >= 2:
        print(json.dumps(gerar_amostras(a[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
