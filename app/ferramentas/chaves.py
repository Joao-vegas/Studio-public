"""Chaves de API: guardar, testar e mostrar onde cada uma mora. O VALOR nunca sai daqui (só '…xxxx', sim/não ou hash curto).

As chaves de "Cobrar da API" (Anthropic e OpenAI) ficam em ~/.config/estudio/<nome>_api_key (chmod 600).
O resto mora num .env só, app/.env: chave(nome, cliente) lê clientes/<Nome>/.env > app/.env > ambiente.

    python3 app/ferramentas/chaves.py listar              nomes, onde estão e hash curto
    python3 app/ferramentas/chaves.py juntar              traz pro app/.env as que só existiam espalhadas
    python3 app/ferramentas/chaves.py sincronizar         copia do app/.env pras skills get-brolls e Gerador
    python3 app/ferramentas/chaves.py limpar-clientes     lista as linhas repetidas nos clientes (--sim tira, com backup)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from _comum import ESTUDIO, GB_ENV, RAIZ

PASTA = Path.home() / ".config" / "estudio"
ARQUIVOS = {"anthropic": PASTA / "anthropic_api_key", "openai": PASTA / "openai_api_key"}   # reserva antiga
ENV_APP = RAIZ / "app" / ".env"   # a casa de todas as chaves
VARIAVEL = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
NOMES = {"anthropic": "Anthropic", "openai": "OpenAI"}
GERADOR_ENV = Path("/Users/joaomarcospiki/Projetos/Skill/Gerador de imagem e vídeo/.env")


def ler(prov: str) -> str:
    """Ambiente, depois app/.env (a casa de todas as chaves), depois o arquivo antigo em ~/.config/estudio."""
    v = os.environ.get(VARIAVEL[prov]) or ler_env(ENV_APP).get(VARIAVEL[prov], "") \
        or (ARQUIVOS[prov].read_text().strip() if ARQUIVOS[prov].is_file() else "")
    return (v or "").strip()


def configurada(prov: str) -> bool:
    return bool(ler(prov))


def final(prov: str) -> str:
    """Só os 4 últimos caracteres, pra João reconhecer qual chave é."""
    k = ler(prov)
    return ("…" + k[-4:]) if len(k) >= 8 else ("…" if k else "")


def salvar(prov: str, valor: str, arquivos: dict | None = None) -> str:
    """Grava a chave em app/.env (ou no arquivo dado, nos testes), permissão 600. Devolve '…xxxx'. Falha com mensagem simples, sem repetir o valor."""
    valor = (valor or "").strip().strip('"').strip("'")
    if prov not in ARQUIVOS: raise ValueError("Serviço desconhecido.")
    if not valor: raise ValueError("Cole a chave no campo antes de salvar.")
    if re.search(r"\s", valor): raise ValueError("A chave tem espaço ou quebra de linha. Cole só a chave, inteira.")
    if len(valor) < 20: raise ValueError("Essa chave parece curta demais. Confira se copiou inteira.")
    if arquivos is None:   # padrão: todas as chaves moram em app/.env
        gravar(ENV_APP, {VARIAVEL[prov]: valor})
        return "…" + valor[-4:]
    alvo = arquivos[prov]
    alvo.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(alvo.parent, 0o700)
    fd = os.open(alvo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(valor + "\n")
    os.chmod(alvo, 0o600)
    return "…" + valor[-4:]


def _limpa(texto: str, chave: str) -> str:
    return (texto or "").replace(chave, "…") if chave else (texto or "")


def usd(v) -> str:
    return "US$ " + f"{float(v or 0):.2f}".replace(".", ",")


def testar_claude(chave: str, rodar=None) -> dict:
    """O mesmo teste do via_api.testar (uma tarefa mínima no Claude Code), mas forçando a chave nova."""
    if rodar is None:
        import via_api
        rodar = via_api.testar_dados
    try:
        r = rodar(api_key=chave)
    except SystemExit as e:
        return {"ok": False, "texto": _limpa(str(e), chave), "custo": 0.0}
    custo = float(r.get("usd") or 0)
    if r.get("estado") == "ok":
        return {"ok": True, "texto": "Funcionou", "custo": custo}
    erro = _limpa(str(r.get("erro") or ""), chave)
    baixo = erro.lower()
    if "apikeysource" in baixo: msg = "O Claude não usou essa chave (ia gastar o plano). Nada foi cobrado."
    elif any(x in baixo for x in ("invalid api key", "401", "authentication", "unauthorized")):
        msg = "A Anthropic não aceitou essa chave. Confira se copiou inteira, sem espaço."
    elif any(x in baixo for x in ("credit", "balance", "billing")):
        msg = "A chave é válida, mas o crédito da Anthropic acabou. Ponha saldo no Console."
    else: msg = "Não deu pra testar: " + (erro[:160] or "o Claude não respondeu") + "."
    return {"ok": False, "texto": msg, "custo": custo}


def testar_openai(chave: str, abrir=None) -> dict:
    """Lista os modelos da conta: não gasta nada."""
    abrir = abrir or urllib.request.urlopen
    req = urllib.request.Request("https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + chave})
    try:
        with abrir(req, timeout=25) as r: dados = json.load(r)
    except urllib.error.HTTPError as e:
        msg = {401: "A OpenAI não aceitou essa chave. Confira se copiou inteira, sem espaço.",
               403: "A OpenAI bloqueou essa chave (sem permissão). Crie outra no painel.",
               429: "A chave existe, mas a OpenAI recusou por limite ou falta de crédito."}.get(e.code, f"A OpenAI respondeu com erro {e.code}.")
        return {"ok": False, "texto": msg, "custo": 0.0}
    except (urllib.error.URLError, OSError, TimeoutError):
        return {"ok": False, "texto": "Não consegui falar com a OpenAI. Veja a internet e tente de novo.", "custo": 0.0}
    except ValueError:
        return {"ok": False, "texto": "A OpenAI respondeu algo estranho. Tente de novo.", "custo": 0.0}
    return {"ok": True, "texto": f"Funcionou ({len(dados.get('data') or [])} modelos na conta)", "custo": 0.0}


def salvar_e_testar(prov: str, valor: str, rodar=None, abrir=None, arquivos=None) -> dict:
    """{ok, texto, custo, final}. O texto nunca leva a chave."""
    try: fim = salvar(prov, valor, arquivos)
    except ValueError as e: return {"ok": False, "texto": str(e), "custo": 0.0, "final": ""}
    chave = valor.strip().strip('"').strip("'")
    r = testar_claude(chave, rodar) if prov == "anthropic" else testar_openai(chave, abrir)
    return {**r, "final": fim}


# ───────────── Chaves e onde estão ─────────────

def _nomes_do_env(caminho: Path) -> dict:
    """{NOME: digest|None}. Só o hash do valor sai daqui, pra achar repetidas; vazia = None."""
    out = {}
    if not caminho.is_file(): return out
    for l in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=(.*)$", l)
        if not m: continue
        v = m.group(2).strip().strip('"').strip("'")
        out[m.group(1)] = hashlib.sha256(v.encode()).hexdigest() if v else None
    return out


def _rotulo(p: Path, raiz: Path | None = None) -> str:
    for base, pre in ((raiz or RAIZ, ""), (Path.home(), "~/")):
        try: return pre + str(Path(p).relative_to(base))
        except ValueError: pass
    return str(p)


def _fontes(raiz: Path = RAIZ, estudio: Path = ESTUDIO, gb_env: Path = GB_ENV, gerador: Path = GERADOR_ENV, pasta_chaves: Path = PASTA) -> list:
    """[(rótulo mostrado, [(nome, digest)])]: um item por arquivo que pode guardar chave."""
    casa = lambda p: _rotulo(p, raiz)
    fontes = [(casa(estudio / ".env"), _nomes_do_env(estudio / ".env")),
              (casa(gb_env), _nomes_do_env(gb_env)), (casa(gerador), _nomes_do_env(gerador))]
    for env in sorted((raiz / "clientes").glob("*/.env")):
        fontes.append((casa(env), _nomes_do_env(env)))
    for prov, arq in ARQUIVOS.items():
        arq = pasta_chaves / arq.name
        if arq.is_file():
            v = arq.read_text().strip()
            fontes.append((casa(arq), {VARIAVEL[prov]: hashlib.sha256(v.encode()).hexdigest() if v else None}))
    return fontes


# nome, variáveis (prefixo termina em *), pra que serve, custo, onde guardar se ainda não tem
SERVICOS = [
    ("Anthropic (Claude)", ["ANTHROPIC_API_KEY"], "Claude cobrando do seu crédito em vez do plano", "pago · só se ligar “cobrar da API”",
     "~/.config/estudio/anthropic_api_key (cartão acima)"),
    ("OpenAI (GPT)", ["OPENAI_API_KEY"], "Lista de modelos GPT (app/.env). Cobrar o Codex da API usa só a chave do cartão acima", "pago · só se ligar “cobrar da API”",
     "app/.env (cobrança: cartão acima)"),
    ("ElevenLabs", ["ELEVENLABS_API_KEY"], "Voz reserva, se o VoiceStudio fechar (opcional)", "pago", "app/.env (Configurações → Voz)"),
    ("Groq", ["GROQ_API_KEY"], "Transcrição das falas (Whisper)", "grátis com limite", "app/.env"),
    ("Pexels", ["PEXELS_API_KEY"], "B-roll em banco de vídeo", "grátis", "app/.env (cópia na skill get-brolls)"),
    ("Pixabay", ["PIXABAY_API_KEY"], "B-roll em banco de vídeo", "grátis", "app/.env (cópia na skill get-brolls)"),
    ("Freesound", ["FREESOUND_API_KEY"], "Efeitos sonoros", "grátis", "app/.env"),
    ("Jamendo", ["JAMENDO_CLIENT_ID"], "Músicas com licença livre", "grátis", "app/.env"),
    ("kie.ai", ["KIE_API_KEY"], "Imagem e vídeo por IA", "pago", "app/.env"),
]
SEM_CHAVE = "Mixkit · YouTube (yt-dlp) · SoundCloud · Wikimedia Commons · NASA"


def _casa_var(padrao: str, nome: str) -> bool:
    return nome.startswith(padrao[:-1]) if padrao.endswith("*") else nome == padrao


def inventario(**caminhos) -> dict:
    """{linhas: [...], sem_chave: str}. Nenhum valor: só sim/não, caminhos e avisos (repetida / vazia)."""
    fontes = _fontes(**caminhos)
    linhas = []
    for nome, variaveis, serve, custo, onde_guardar in SERVICOS:
        achados = [(rot, v, d) for rot, vs in fontes for v, d in vs.items() if any(_casa_var(p, v) for p in variaveis)]
        proprio = nome.startswith(("Anthropic", "OpenAI"))
        no_ambiente = proprio and bool(os.environ.get(variaveis[0]))
        cheios = [a for a in achados if a[2]]
        vazios = [a for a in achados if not a[2]]
        avisos = []
        sufixo = lambda v: v.rsplit("_", 1)[-1] if v[-1].isdigit() else v
        varios = len({a[1] for a in achados}) > 1
        if vazios: avisos.append("vazia: " + ", ".join(sorted({v if varios else rot for rot, v, _ in vazios})))
        grupos = {}
        for rot, v, d in cheios: grupos.setdefault(d, []).append((rot, v))
        for itens in grupos.values():
            if len(itens) > 1:
                nomes = sorted({i[1] for i in itens})
                if len(nomes) > 1: avisos.append("repetida: chaves " + " e ".join(sufixo(n) for n in nomes) + " são a mesma")
                else: avisos.append(f"repetida: {len(itens)} cópias iguais (conta como uma só)")
        # onde: arquivos que têm pelo menos uma variável do serviço, com clientes juntos numa linha
        onde = []
        clientes = [rot for rot, _, _ in achados if rot.startswith("clientes/")]
        for rot in dict.fromkeys(r for r, _, _ in achados):
            if not rot.startswith("clientes/"): onde.append(rot)
        if clientes:
            onde.append("clientes/<Nome>/.env (" + ", ".join(sorted({c.split("/")[1] for c in clientes})) + ")")
        if no_ambiente: onde.append("no ambiente do Estúdio")
        if proprio and not no_ambiente and not any(a[0].startswith("~/.config/estudio") for a in cheios):
            avisos.append("o Estúdio ainda não tem a sua chave pra essa conta (cole no cartão “Quem edita os vídeos”)")
        estado = "sim" if cheios or no_ambiente else ("vazia" if vazios else "não")
        linhas.append({"nome": nome, "configurada": estado, "onde": onde or [f"não configurada · colocar em {onde_guardar}"],
                       "serve": serve, "custo": custo, "avisos": avisos})
    return {"linhas": linhas, "sem_chave": SEM_CHAVE}


# ───────────── Um .env só: app/.env ─────────────

APP_ENV = ESTUDIO / ".env"
BACKUPS = PASTA / "backups"
# skills de fora que leem o próprio .env e precisam da cópia pra funcionar sem o Estúdio
COPIAS = (("gb", ["PEXELS_API_KEY", "PIXABAY_API_KEY"]), ("gerador", ["KIE_API_KEY"]))
_LINHA = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _par(linha: str):
    """(NOME, valor) de uma linha NOME=valor; None pra comentário e linha solta."""
    if linha.lstrip().startswith("#"): return None
    m = _LINHA.match(linha)
    return (m.group(1), m.group(2).strip().strip('"').strip("'")) if m else None


def ler_env(caminho) -> dict:
    """{NOME: valor} do arquivo. Só lê: nada vai pro os.environ, senão o codex/claude -p filhos herdam
    OPENAI_API_KEY e passam a cobrar da API sozinhos."""
    if not caminho or not Path(caminho).is_file(): return {}
    return dict(p for l in Path(caminho).read_text(encoding="utf-8", errors="ignore").splitlines() if (p := _par(l)))


def _env_cliente(cliente, raiz: Path):
    if not cliente: return None
    return Path(cliente) / ".env" if isinstance(cliente, Path) else raiz / "clientes" / str(cliente) / ".env"


def chave(nome: str, cliente=None, raiz: Path | None = None) -> str:
    """Valor da chave, na ordem clientes/<cliente>/.env > app/.env > ambiente; '' se não houver.
    cliente: o nome (Joao) ou a pasta dele. Vazia no cliente não esconde a do app/.env."""
    raiz = raiz or RAIZ
    for env in (_env_cliente(cliente, raiz), raiz / "app" / ".env"):
        v = ler_env(env).get(nome, "")
        if v: return v
    return os.environ.get(nome, "").strip()


def _hash(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:8] if v else ""


def mostrar(nome: str, cliente=None, raiz: Path | None = None) -> dict:
    """O que pode ir pra tela ou log: nome, de onde vem, configurada e hash curto. Nunca o valor."""
    raiz = raiz or RAIZ
    for env in (_env_cliente(cliente, raiz), raiz / "app" / ".env"):
        v = ler_env(env).get(nome, "")
        if v: return {"nome": nome, "configurada": True, "onde": _rotulo(env, raiz), "hash": _hash(v)}
    v = os.environ.get(nome, "").strip()
    return {"nome": nome, "configurada": bool(v), "onde": "ambiente" if v else "", "hash": _hash(v)}


def _escrever(caminho: Path, linhas: list) -> None:
    """Troca o arquivo de uma vez, mantendo a permissão que ele tinha (600 se for novo)."""
    modo = caminho.stat().st_mode & 0o777 if caminho.exists() else 0o600
    tmp = caminho.with_name(caminho.name + ".novo")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f: f.write("\n".join(linhas).rstrip("\n") + "\n")
    os.chmod(tmp, modo)
    os.replace(tmp, caminho)


def gravar(caminho, novos: dict) -> list:
    """Atualiza ou acrescenta NOME=valor sem mexer nas outras linhas. Devolve só os nomes que mudaram."""
    caminho = Path(caminho).resolve()
    atuais = ler_env(caminho)
    mudou = [k for k, v in novos.items() if v and atuais.get(k) != v]
    if not mudou: return []
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.is_file() else []
    feitos = set()
    for i, l in enumerate(linhas):
        p = _par(l)
        if p and p[0] in mudou:
            linhas[i] = f"{p[0]}={novos[p[0]]}"; feitos.add(p[0])
    _escrever(caminho, linhas + [f"{k}={novos[k]}" for k in mudou if k not in feitos])
    return mudou


# Qualquer chave conectada em Configurações cai em app/.env (a casa única). Só estes nomes são aceitos.
GRAVAVEIS = re.compile(r"^(ANTHROPIC_API_KEY|OPENAI_API_KEY|GROQ_API_KEY|KIE_API_KEY|FREESOUND_API_KEY"
                       r"|PEXELS_API_KEY|PIXABAY_API_KEY|ELEVENLABS_API_KEY|JAMENDO_CLIENT_ID|OPENROUTER_API_KEY)$")


def gravar_chave(nome: str, valor: str, espelhar: bool = True) -> str:
    """Grava NOME=valor em app/.env (permissão 600) e, se for Pexels/Pixabay/kie, espelha pras skills que as leem fora do Estúdio.
    Devolve '…xxxx'. Erro em português simples, sem repetir o valor."""
    nome = (nome or "").strip().upper()
    valor = (valor or "").strip().strip('"').strip("'")
    if not GRAVAVEIS.match(nome): raise ValueError("Esse nome de chave não é conhecido pelo Estúdio.")
    if not valor: raise ValueError("Cole a chave no campo antes de salvar.")
    if re.search(r"\s", valor): raise ValueError("A chave tem espaço ou quebra de linha. Cole só a chave, inteira.")
    if len(valor) < 8: raise ValueError("Essa chave parece curta demais. Confira se copiou inteira.")
    gravar(ENV_APP, {nome: valor})
    os.chmod(ENV_APP, 0o600)   # arquivo de segredo: só o João lê
    if espelhar and nome in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "KIE_API_KEY"):
        try: sincronizar()
        except Exception: pass   # a chave já está salva em app/.env; o espelho é só pras skills de fora
    return "…" + valor[-4:]


def juntar(raiz: Path | None = None, gb_env: Path | None = None, de_cliente: str = "Avulso") -> dict:
    """Traz pro app/.env OPENAI e GROQ (dos clientes, se todas as cópias forem iguais) e PEXELS e PIXABAY
    (da skill get-brolls). Não apaga nada da origem. {nome: o que aconteceu}."""
    raiz = raiz or RAIZ
    app = ler_env(raiz / "app" / ".env")
    clientes = [ler_env(e) for e in sorted((raiz / "clientes").glob("*/.env"))]
    base, gb = ler_env(raiz / "clientes" / de_cliente / ".env"), ler_env(gb_env or GB_ENV)
    novos, estado = {}, {}
    for nome, origem in (("OPENAI_API_KEY", base), ("GROQ_API_KEY", base), ("PEXELS_API_KEY", gb), ("PIXABAY_API_KEY", gb)):
        if app.get(nome): estado[nome] = "já estava"; continue
        if not origem.get(nome): estado[nome] = "não achei de onde trazer"; continue
        if origem is base and len({c[nome] for c in clientes if c.get(nome)}) > 1:
            estado[nome] = "os clientes têm valores diferentes: não trouxe"; continue
        novos[nome] = origem[nome]; estado[nome] = "adicionada"
    gravar(raiz / "app" / ".env", novos)
    return estado


def sincronizar(raiz: Path | None = None, gb_env: Path | None = None, gerador: Path | None = None) -> list:
    """Copia do app/.env pros .env das skills get-brolls (PEXELS, PIXABAY) e Gerador (KIE).
    Só troca o que mudou; o resto do arquivo fica igual. [(arquivo, nome, estado)]."""
    raiz = raiz or RAIZ
    app = ler_env(raiz / "app" / ".env")
    destinos = {"gb": Path(gb_env or GB_ENV), "gerador": Path(gerador or GERADOR_ENV)}
    out = []
    for qual, nomes in COPIAS:
        destino = destinos[qual]
        if not destino.parent.is_dir():
            out += [(_rotulo(destino, raiz), n, "skill não instalada") for n in nomes]; continue
        mudou = gravar(destino, {n: app[n] for n in nomes if app.get(n)})
        out += [(_rotulo(destino, raiz), n, "atualizada" if n in mudou else ("igual" if app.get(n) else "falta no app/.env"))
                for n in nomes]
    return out


def limpar_clientes(sim: bool = False, raiz: Path | None = None, backups: Path | None = None) -> list:
    """Linhas dos clientes/<Nome>/.env com o MESMO valor do app/.env. Sem sim=True só lista.
    Com sim: copia o arquivo pro backup antes e tira só essas linhas (valor diferente fica: é o cliente sobrescrevendo)."""
    raiz = raiz or RAIZ
    app = ler_env(raiz / "app" / ".env")
    pasta = Path(backups or BACKUPS) / ("limpar-clientes-" + datetime.now().strftime("%Y-%m-%d-%H%M%S"))
    out = []
    for env in sorted((raiz / "clientes").glob("*/.env")):
        linhas = env.read_text(encoding="utf-8").splitlines()
        rep = lambda l: (p := _par(l)) and p[1] and app.get(p[0]) == p[1]
        nomes = sorted({_par(l)[0] for l in linhas if rep(l)})
        if not nomes: continue
        out.append({"cliente": env.parent.name, "repetidas": nomes, "removidas": sim})
        if sim:
            pasta.mkdir(parents=True, exist_ok=True); os.chmod(pasta, 0o700)
            copia = pasta / f"{env.parent.name}.env"
            shutil.copy2(env, copia); os.chmod(copia, 0o600)
            if copia.read_bytes() != env.read_bytes(): raise SystemExit(f"backup de {env.parent.name} não conferiu: nada removido")
            _escrever(env.resolve(), [l for l in linhas if not rep(l)])
    return out


def listar(raiz: Path | None = None, gb_env: Path | None = None, gerador: Path | None = None) -> list:
    """Cada nome: estado no app/.env, hash curto e as outras cópias (igual ou diferente). Sem valores."""
    raiz = raiz or RAIZ
    arquivos = [raiz / "app" / ".env", *sorted((raiz / "clientes").glob("*/.env")), Path(gb_env or GB_ENV), Path(gerador or GERADOR_ENV)]
    app, por = ler_env(arquivos[0]), {}
    for arq in arquivos[1:]:
        for n, v in ler_env(arq).items(): por.setdefault(n, []).append((_rotulo(arq, raiz), _hash(v)))
    out = []
    for n in sorted(set(app) | set(por)):
        h = _hash(app.get(n, ""))
        out.append({"nome": n, "app": "configurada" if h else ("vazia" if n in app else "não está"), "hash": h,
                    "copias": [(rot, hc, "vazia" if not hc else "igual" if hc == h else "diferente" if h else "só fora")
                               for rot, hc in por.get(n, [])]})
    return out


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Chaves do Estúdio. Mostra só nomes e hash curto, nunca o valor.")
    sub = ap.add_subparsers(dest="cmd")
    for c in ("listar", "juntar", "sincronizar"): sub.add_parser(c)
    sub.add_parser("limpar-clientes").add_argument("--sim", action="store_true", help="tira as linhas (com backup antes)")
    a = ap.parse_args(argv)
    if a.cmd == "juntar":
        for n, e in juntar().items(): print(f"{n:<22} {e}  {_hash(ler_env(APP_ENV).get(n, ''))}")
    elif a.cmd == "sincronizar":
        for arq, n, e in sincronizar(): print(f"{n:<22} {e:<18} {arq}")
    elif a.cmd == "limpar-clientes":
        r = limpar_clientes(a.sim)
        for i in r: print(f"{i['cliente']:<10} {'tirei' if a.sim else 'podem sair'}: {', '.join(i['repetidas'])}")
        if not r: print("Nenhuma linha repetida nos clientes.")
        elif not a.sim: print("Nada foi mudado. Pra tirar (com backup em ~/.config/estudio/backups/): limpar-clientes --sim")
    else:
        for i in listar():
            grupos = {}
            for rot, hc, e in i["copias"]: grupos.setdefault((hc, e), []).append(rot.replace("clientes/", "").replace("/.env", ""))
            copias = " · ".join(f"{e} {hc}: {', '.join(rots)}".replace("  ", " ") for (hc, e), rots in grupos.items())
            print(f"{i['nome']:<20} app/.env: {i['app']:<11} {i['hash']:<8}  {copias}")


if __name__ == "__main__":
    main()
