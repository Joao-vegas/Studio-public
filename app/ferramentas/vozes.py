#!/usr/bin/env python3
"""
vozes — as vozes do VoiceStudio na tela (PLANO-2.0, item 16): todas, com prévia em português, quem usa cada uma,
e criar voz nova de graça (desenhar por descrição ou clonar de uma gravação).

Voz desenhada vira perfil CLONADO da própria amostra: com perfil fixo ela não muda de pessoa no meio do vídeo
(a voz "default" sorteava uma pessoa por bloco; grupo-por-crenca, 29-out-2026).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voicestudio  # noqa: E402
from _comum import ESTUDIO, RAIZ, ler_json  # noqa: E402

FRASE_PT = ("Você entrou nesse grupo por um fato ou por uma crença? Pensa bem. "
            "A maioria das pessoas nunca parou pra pensar nisso, e é exatamente por isso que funciona.")
CACHE = ESTUDIO / ".cache" / "vozes-pt"
GENEROS = {"homem": "male", "mulher": "female"}
IDADES = {"jovem": "young adult", "adulto": "middle-aged", "mais velho": "elderly"}
TONS = {"grave": "low pitch", "médio": "moderate pitch", "agudo": "high pitch"}
PRONTAS = [   # sugestões de voz desenhada (o João cria com um clique)
    {"nome": "Narrador grave", "genero": "homem", "idade": "adulto", "tom": "grave"},
    {"nome": "Jovem animado", "genero": "homem", "idade": "jovem", "tom": "médio"},
    {"nome": "Narradora", "genero": "mulher", "idade": "adulto", "tom": "grave"},
    {"nome": "Jovem conversando", "genero": "mulher", "idade": "jovem", "tom": "médio"},
    {"nome": "Senhor contador de história", "genero": "homem", "idade": "mais velho", "tom": "grave"},
]


def _get(caminho: str, timeout: float = 8):
    with urllib.request.urlopen(voicestudio.url() + caminho, timeout=timeout) as r:
        return json.loads(r.read())


def _multipart(caminho: str, campos: dict, arquivos: dict | None = None, timeout: float = 900) -> bytes:
    b = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        if v is None:
            continue
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, f in (arquivos or {}).items():
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{Path(f).name}"\r\n'
                      f"Content-Type: application/octet-stream\r\n\r\n".encode() + Path(f).read_bytes() + b"\r\n")
    corpo = b"".join(partes) + f"--{b}--\r\n".encode()
    req = urllib.request.Request(voicestudio.url() + caminho, corpo, {"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def motor() -> str:
    try:
        d = _get("/engines/tts")
        ativo = next((x for x in d.get("backends") or [] if x.get("id") == d.get("active")), {})
        return (ativo.get("display_name") or d.get("active") or "").split(" (")[0]
    except Exception:  # noqa: BLE001
        return ""


def lista() -> list[dict]:
    """Toda voz do VoiceStudio com: é a padrão do Estúdio? quais clientes usam? tem prévia em português pronta?"""
    import voz as _voz
    padrao = _voz.status()["voicestudio"]["voz"]
    usos: dict[str, list[str]] = {}
    for f in (RAIZ / "clientes").glob("*/identidade.json"):
        v = (ler_json(f, {}) or {}).get("voz") or {}
        if isinstance(v, dict) and v.get("id"):
            usos.setdefault(v["id"], []).append(f.parent.name)
    try:
        perfis = _get("/profiles") or []
    except Exception:  # noqa: BLE001
        return []
    try:   # as variações por emoção ("<voz> · animado") são da própria voz: não aparecem como voz à parte nas listas
        import emocao
        de_emocao = {e.get("perfil") for v in emocao.mapa()["vozes"].values() for e in v.values() if e.get("perfil")}
    except Exception:  # noqa: BLE001
        de_emocao = set()
    out = []
    for p in perfis:
        if p["id"] in de_emocao:
            continue
        idioma = p.get("language") or ""
        out.append({"id": p["id"], "nome": p.get("name") or p["id"], "idioma": idioma,
                    "pt": idioma.lower().startswith(("portug", "pt")) or not idioma or idioma == "Auto",
                    "tipo": "clonada" if p.get("kind") == "clone" else (p.get("kind") or ""),
                    "demo": bool(p.get("is_demo")), "padrao": p["id"] == padrao, "clientes": usos.get(p["id"], []),
                    "previa": (CACHE / f"{p['id']}.mp3").exists()})
    out.sort(key=lambda x: (not x["padrao"], not x["clientes"], not x["pt"], x["demo"], x["nome"].lower()))
    return out


# Etiquetas que filtram as vozes na tela (busca + tags): slug -> como o João lê
ROTULOS_TAGS = {"homem": "Homem", "mulher": "Mulher", "jovem": "Jovem", "adulto": "Adulto", "mais-velho": "Mais velho", "grave": "Grave",
                "agudo": "Agudo", "narracao": "Narração", "noticia": "Notícia", "conversa": "Conversa", "historia": "História",
                "portugues": "Português", "clonada": "Clonada"}
USO_TAG = {"narration": "narracao", "conversational": "conversa", "informative": "explicacao", "social": "redes",
           "entertainment": "apresentacao", "advertisement": "propaganda", "characters": "personagem"}
TAGS_EXTRA = {"The Anchor": ["noticia"], "The Commentator": ["noticia"], "The Storyteller": ["historia"], "The Librarian": ["historia"]}
PALAVRAS_TAG = [   # trecho do nome da voz -> tags (as vozes criadas à mão não trazem características)
    ("narrador", ["homem", "narracao"]), ("narradora", ["mulher", "narracao"]), ("locutor", ["homem", "noticia"]), ("notícia", ["noticia"]),
    ("noticia", ["noticia"]), ("senhor", ["homem", "mais-velho", "historia"]), ("história", ["historia"]), ("conversando", ["conversa"]),
    ("jovem", ["jovem"]), ("grave", ["grave"]), ("editorial", ["narracao"]), ("joão", ["homem"]), ("calma", ["narracao"]),
]


def tags_perfil(nome: str, pt: bool, clonada: bool = True) -> list[str]:
    """Tags de um perfil: das vozes desenhadas (PRONTAS) quando o nome bate, do nome (Narradora, Locutor...) nas outras."""
    out: list[str] = []
    base = _limpa_nome(nome).lower()
    for p in PRONTAS:
        if p["nome"].lower() == base:
            out += ["mulher" if p["genero"] == "mulher" else "homem", {"jovem": "jovem", "adulto": "adulto", "mais velho": "mais-velho"}[p["idade"]],
                    {"grave": "grave", "médio": "medio", "agudo": "agudo"}[p["tom"]]]
    for trecho, ts in PALAVRAS_TAG:
        if trecho in base:
            out += ts
    if pt:
        out.append("portugues")
    if clonada:
        out.append("clonada")
    if "mulher" in out and "homem" in out:      # "Narradora" também tem "narrador" dentro: vale o feminino
        out.remove("homem")
    return list(dict.fromkeys(out))


def tags_arquetipo(item: dict, filtros: dict) -> list[str]:
    out = [filtros["genero"], filtros["idade"], filtros["tom"], USO_TAG.get(item.get("use_case") or "", "")] + TAGS_EXTRA.get(item.get("name") or "", []) + ["portugues"]
    return list(dict.fromkeys(t for t in out if t))



def _limpa_nome(nome: str) -> str:
    """'Narrador Editorial (pt)' -> 'Narrador Editorial'."""
    return re.sub(r"\s*\((pt|pt-br|portuguese|português)\)\s*", " ", nome or "", flags=re.I).strip() or nome


def _descricao(nome: str, padrao: bool) -> str:
    """Uma linha em português simples: 'masculina, adulta, grave'. Sai das vozes desenhadas (PRONTAS); as outras, de uma frase fixa."""
    for p in PRONTAS:
        if p["nome"].lower() == _limpa_nome(nome).lower():
            idade = {"jovem": "jovem", "adulto": "adulta", "mais velho": "mais velha"}[p["idade"]]   # "voz" é feminino
            tom = {"grave": "grave", "médio": "tom médio", "agudo": "aguda"}[p["tom"]]
            return ", ".join(["feminina" if p["genero"] == "mulher" else "masculina", tom, idade])
    if padrao:
        return "a voz padrão do Estúdio, pra narrar análise"
    return "voz clonada, em português"


def cartoes() -> list[dict]:
    """Voz da narração no Criar e na tela Vozes ("Prontas pra usar"): TODOS os perfis do VoiceStudio, português primeiro (a do João com selo),
    cada um com nome simples, descrição curta e a URL da prévia (que fala sempre a FRASE_PT em português).
    [{id, nome, descricao, selo, pt, previa_pronta, previa_url}]. VoiceStudio fora do ar: lista vazia."""
    out = []
    for v in lista():
        nome = _limpa_nome(v["nome"])
        selo = "voz do João" if "joão" in nome.lower() or "joao" in nome.lower() else ""
        if not selo and v["clientes"]:
            selo = "voz do " + v["clientes"][0]
        if selo == "voz do João":
            desc = "sua voz, clonada de uma gravação"
        elif not v["pt"]:
            desc = f"voz clonada em {IDIOMAS_PT.get(v['idioma'], v['idioma'].lower())}" + (" · exemplo do VoiceStudio" if v["demo"] else "")
        else:
            desc = _descricao(v["nome"], v["padrao"])
        out.append({"id": v["id"], "nome": nome, "descricao": desc, "selo": selo, "padrao": v["padrao"], "pt": v["pt"],
                    "tags": tags_perfil(v["nome"], v["pt"], v["tipo"] == "clonada"),
                    "previa_pronta": v["previa"], "previa_url": f"/vozes/previa?id={v['id']}"})
    out.sort(key=lambda c: (not c["pt"], c["selo"] != "voz do João"))   # português primeiro; a do João logo no começo (sort é estável)
    return out


def previa(vid: str) -> Path:
    """A frase de prévia em português (com pergunta, pra ouvir a entonação), guardada em app/.cache/vozes-pt/."""
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", vid or "default")
    alvo = CACHE / f"{nome}.mp3"
    if alvo.exists() and alvo.stat().st_size > 0:
        return alvo
    CACHE.mkdir(parents=True, exist_ok=True)
    return voicestudio.falar(FRASE_PT, alvo, vid)


def desenhar(nome: str, genero: str, idade: str, tom: str, semente: int = 7) -> str:
    """Desenha a voz pela descrição, gera a frase em português e cria um perfil clonado dessa amostra. Devolve o id."""
    instr = ", ".join(x for x in (GENEROS.get(genero), IDADES.get(idade), TONS.get(tom)) if x)
    if not instr:
        raise ValueError("Escolha pelo menos homem ou mulher.")
    return _perfil_de_instrucao(nome or "Voz desenhada", instr, semente)


def _amostra_wav(instruct: str, destino: Path, semente: int = 7) -> None:
    """A FRASE_PT falada em português com essa descrição de voz (o VoiceStudio gera na hora)."""
    destino.write_bytes(_multipart("/generate", {"text": FRASE_PT, "language": "pt", "instruct": instruct, "seed": semente}))
    if destino.stat().st_size < 20000:
        raise ValueError("O VoiceStudio não devolveu a amostra. Ele está aberto?")


def _perfil_de_instrucao(nome: str, instruct: str, semente: int = 7) -> str:
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "amostra.wav"
        _amostra_wav(instruct, wav, semente)
        return _criar_perfil(nome, wav, FRASE_PT)


def clonar(nome: str, audio: Path) -> str:
    """Clona de uma gravação (até 20 s, fala solta e com pergunta dá entonação melhor). O texto sai pela transcrição."""
    with tempfile.TemporaryDirectory() as d:
        ref = Path(d) / "ref.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-t", "19.5", "-ac", "1", "-ar", "24000",
                        "-af", "highpass=f=70", str(ref)], check=True)
        mp3 = Path(d) / "ref.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ref), "-ac", "1", "-ar", "16000", "-b:a", "64k", str(mp3)], check=True)
        from corte import chave_groq
        from fala import _groq_pedaco
        texto = (_groq_pedaco(str(mp3), chave_groq(None), "", "pt", 3).get("text") or "").strip()
        if len(texto.split()) < 8:
            raise ValueError("Não entendi a fala da gravação. Mande 10 a 20 s de você falando, sem música.")
        return _criar_perfil(nome or "Minha voz", ref, texto)


def _criar_perfil(nome: str, wav: Path, texto: str) -> str:
    r = json.loads(_multipart("/profiles", {"name": nome, "language": "Portuguese", "seed": 7, "ref_text": texto},
                              {"ref_audio": wav}, timeout=120))
    previa(r["id"])
    return r["id"]


# ── Arquétipos do VoiceStudio (vozes prontas dele, grátis) ───────────────────────────────────────────────────────
ARQ_MAPA = ESTUDIO / ".cache" / "vozes-arquetipos.json"          # {id do arquétipo: id do perfil fixo criado a partir dele}
ARQ_LISTA = ESTUDIO / ".cache" / "vozes-arquetipos-lista.json"   # cópia da lista, pra tela abrir mesmo com o VoiceStudio fechado
NOMES_PT = {
    "The Librarian": "A Bibliotecária", "The Documentarian": "O Documentarista", "The Calm Guide": "A Guia Calma",
    "The Storyteller": "O Contador de Histórias", "The Neighbor": "A Vizinha", "The Helpdesk": "A Atendente",
    "The Mate": "O Parceiro", "The Companion": "A Companheira", "Captain Crusty": "Capitão Casca-Grossa",
    "Junior Quacks": "Júnior Quacks", "The Champion": "O Campeão", "The Pixie": "A Fada", "The Ogre": "O Ogro",
    "The Podcaster": "A Podcaster", "The Hype Host": "O Apresentador Animado", "The Vlogger": "A Vlogueira",
    "The Anchor": "O Âncora", "The Commentator": "O Comentarista", "The Game Host": "O Apresentador de Game Show",
    "The Promo Voice": "A Voz de Propaganda", "The Luxe": "A Voz de Luxo", "The Upbeat": "A Animada",
    "The Teacher": "A Professora", "The Explainer": "O Explicador",
}
PAPEIS_PT = {"Narrator": "Narrador", "Explainer": "Explicador", "Companion": "Companheiro"}
IDIOMAS_PT = {"Spanish": "espanhol", "French": "francês", "German": "alemão", "Italian": "italiano", "Portuguese": "português",
              "Russian": "russo", "Hindi": "hindi", "Japanese": "japonês", "Korean": "coreano", "English": "inglês", "Chinese": "chinês"}
GENERO_PT = {"male": "masculina", "female": "feminina"}
IDADE_PT = {"child": "infantil", "teenager": "adolescente", "young adult": "jovem", "middle-aged": "adulta", "elderly": "mais velha"}
TOM_PT = {"very low pitch": "muito grave", "low pitch": "grave", "moderate pitch": "tom médio", "high pitch": "aguda", "very high pitch": "muito aguda"}
USO_PT = {"narration": "narração", "conversational": "conversa", "characters": "personagem", "social": "redes sociais",
          "entertainment": "apresentação", "advertisement": "propaganda", "informative": "explicação"}


def sem_sotaque(instruct: str) -> str:
    """Tira 'british accent', 'chinese dialect'... da descrição: a prévia e o perfil falam português puro, sem sotaque inglês nem chinês."""
    return ", ".join(p.strip() for p in (instruct or "").split(",") if p.strip() and not re.search(r"accent|dialect", p, re.I))


def nome_pt(item: dict) -> str:
    """Nome em português do arquétipo ('The Librarian' -> 'A Bibliotecária'; 'Spanish Narrator' -> 'Narradora (espanhol)')."""
    nome = item.get("name") or ""
    if nome in NOMES_PT:
        return NOMES_PT[nome]
    f = item.get("facets") or {}
    fem = f.get("gender") == "female"
    m = re.fullmatch(r"(\w+) (Narrator|Explainer|Companion)", nome)
    if m and m.group(1) in IDIOMAS_PT:
        papel = PAPEIS_PT[m.group(2)]
        if fem:   # Narrador -> Narradora, Explicador -> Explicadora, Companheiro -> Companheira
            papel = papel + "a" if papel.endswith("or") else papel[:-1] + "a"
        return f"{papel} ({IDIOMAS_PT[m.group(1)]})"
    # "American · Male · Child · Moderate" e parecidos: o nome sai das características
    base = {("child", "male"): "Menino", ("child", "female"): "Menina", ("teenager", None): "Adolescente",
            ("teenager", "male"): "Adolescente", ("teenager", "female"): "Adolescente"}.get((f.get("age"), f.get("gender")))
    if not base:
        base = {"young adult": "jovem", "middle-aged": "adulto", "elderly": "idoso"}.get(f.get("age"), "")
        pessoa = "Mulher" if fem else "Homem"
        base = f"{pessoa} {base}".strip() if base else pessoa
        if fem and base.endswith("adulto"):
            base = base[:-1] + "a"
        if fem and base.endswith("idoso"):
            base = base[:-1] + "a"
    tom = TOM_PT.get(f.get("pitch") or "", "")
    return f"{base}, {tom}" if tom else base


def descricao_arq(item: dict) -> str:
    """'feminina, grave, adulta · narração' a partir das características (facets) e do uso."""
    f = item.get("facets") or {}
    partes = [GENERO_PT.get(f.get("gender") or ""), TOM_PT.get(f.get("pitch") or ""), IDADE_PT.get(f.get("age") or "")]
    if f.get("whisper"):
        partes.append("sussurrada")
    txt = ", ".join(x for x in partes if x)
    uso = USO_PT.get(item.get("use_case") or "")
    return f"{txt} · {uso}" if txt and uso else (txt or uso or "voz pronta do VoiceStudio")


def _filtros_arq(item: dict) -> dict:
    """Valores pros filtros da tela: gênero (homem/mulher), idade (crianca/jovem/adulto/mais-velho), tom (grave/medio/agudo)."""
    f = item.get("facets") or {}
    idade = {"child": "crianca", "teenager": "jovem", "young adult": "jovem", "middle-aged": "adulto", "elderly": "mais-velho"}.get(f.get("age") or "", "")
    tom = {"very low pitch": "grave", "low pitch": "grave", "moderate pitch": "medio", "high pitch": "agudo", "very high pitch": "agudo"}.get(f.get("pitch") or "", "")
    return {"genero": {"male": "homem", "female": "mulher"}.get(f.get("gender") or "", ""), "idade": idade, "tom": tom}


def _itens_arquetipos() -> list[dict]:
    try:
        itens = _get("/archetypes", 10).get("items") or []
        ARQ_LISTA.parent.mkdir(parents=True, exist_ok=True)
        ARQ_LISTA.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
        return itens
    except Exception:  # noqa: BLE001
        return ler_json(ARQ_LISTA, []) or []


def mapa_arquetipos() -> dict:
    return ler_json(ARQ_MAPA, {}) or {}


def arquetipos() -> list[dict]:
    """Os arquétipos prontos do VoiceStudio em português, sem repetir timbre (as variantes só de sotaque ou idioma caem juntas,
    porque a gente fala sempre português sem sotaque). [{id, nome, descricao, genero, idade, tom, instruct, perfil}]"""
    visto, out = set(), []
    for it in _itens_arquetipos():
        instr = sem_sotaque(it.get("instruct") or "")
        if not instr or instr in visto:
            continue
        visto.add(instr)
        fl = _filtros_arq(it)
        out.append({"id": it["id"], "nome": nome_pt(it), "descricao": descricao_arq(it), **fl, "tags": tags_arquetipo(it, fl), "instruct": instr,
                    "perfil": mapa_arquetipos().get(it["id"], "")})
    return out


def _arquetipo(arq_id: str) -> dict:
    a = next((x for x in arquetipos() if x["id"] == arq_id), None)
    if not a:
        raise ValueError("Voz não encontrada no VoiceStudio.")
    return a


def perfil_do_arquetipo(arq_id: str) -> str:
    """Escolher um arquétipo cria, na 1ª vez, um perfil FIXO dele em português (perfil fixo é o que impede a voz de trocar de pessoa
    no meio do vídeo). O mapa arquétipo -> perfil fica em app/.cache/vozes-arquetipos.json. Devolve o id do perfil."""
    arq_id = arq_id.removeprefix("arq:")
    mapa = mapa_arquetipos()
    if mapa.get(arq_id) and any(v["id"] == mapa[arq_id] for v in lista()):
        return mapa[arq_id]
    a = _arquetipo(arq_id)
    pid = _perfil_de_instrucao(a["nome"], a["instruct"])
    mapa[arq_id] = pid
    ARQ_MAPA.parent.mkdir(parents=True, exist_ok=True)
    ARQ_MAPA.write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding="utf-8")
    return pid


def previa_arquetipo(arq_id: str) -> Path:
    """A FRASE_PT falada com a descrição do arquétipo (sem sotaque), guardada em app/.cache/vozes-pt/arq_<id>.mp3. Se ele já virou
    perfil, a prévia é a do perfil."""
    arq_id = arq_id.removeprefix("arq:")
    pid = mapa_arquetipos().get(arq_id)
    if pid:
        return previa(pid)
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", arq_id)
    alvo = CACHE / f"arq_{nome}.mp3"
    if alvo.exists() and alvo.stat().st_size > 0:
        return alvo
    a = _arquetipo(arq_id)
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "a.wav"
        _amostra_wav(a["instruct"], wav)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-b:a", "96k", str(alvo)], check=True)
    return alvo


def previa_de(vid: str) -> Path:
    """Prévia de um perfil ('3ed4b3ea', 'default') ou de um arquétipo ('arq:feat_00_the_librarian')."""
    return previa_arquetipo(vid) if (vid or "").startswith("arq:") else previa(vid)


def cartoes_arquetipos() -> list[dict]:
    """Os arquétipos que ainda não viraram perfil, no formato do cartão (id 'arq:<id>')."""
    return [{"id": "arq:" + a["id"], "nome": a["nome"], "descricao": a["descricao"], "tags": a["tags"],
             "previa_pronta": (CACHE / f"arq_{re.sub(r'[^A-Za-z0-9_.-]', '_', a['id'])}.mp3").exists(), "previa_url": f"/vozes/previa?id=arq:{a['id']}"}
            for a in arquetipos() if not a["perfil"]]


def usar(vid: str, cliente: str = "") -> None:
    """Padrão do Estúdio (sem cliente) ou a voz de um cliente (identidade.json → voz)."""
    if cliente:
        from _comum import gravar_json
        f = RAIZ / "clientes" / cliente / "identidade.json"
        if not f.is_file():
            raise ValueError("Cliente não encontrado.")
        d = ler_json(f, {}) or {}
        nome = next((v["nome"] for v in lista() if v["id"] == vid), vid)
        d["voz"] = {"motor": "voicestudio", "id": vid, "nome": nome}
        gravar_json(f, d)
        return
    import voz as _voz
    _voz.salvar(voz_voicestudio=vid)


if __name__ == "__main__":
    print(json.dumps({"motor": motor(), "vozes": lista()}, ensure_ascii=False, indent=1))
