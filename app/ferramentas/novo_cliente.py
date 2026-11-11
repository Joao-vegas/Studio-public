#!/usr/bin/env python3
"""
novo_cliente — cria um cliente novo AUTOCONTIDO no padrão do repo (o mesmo dos outros; confere com
`python3 app/ferramentas/clientes_padrao.py`):

    <Nome>/identidade.json                   (cores, fontes e tom: a pele do cliente; valores padrão sensatos)
    <Nome>/<nome>Content/{entrada, material, modelos, output, transcricoes}/   (cada uma com .gitkeep)

E NADA além disso: sem README, .env, automacao, documentacao nem banco-* (chave só em app/.env; banco de imagem,
vídeo e música só no acervo/). Dentro de modelos/ nasce <modelo>/ (aprendizado) quando o formato é usado
pela primeira vez, e dentro de output/ nasce <formato>/ com o primeiro vídeo.

Portar um modelo = copiar a pasta do modelo de outro cliente SEM sandboxes/outputs/brolls e com
o aprendizado ZERADO (regras.json novo + historico.jsonl vazio). Regra de um modelo não vale
automaticamente pra outro — o CLAUDE.md é claro nisso. A linha do modelo entra no mapa do CLAUDE.md.

Também faz o INVERSO: `remover_modelo` tira um modelo da frente (vai pra lixeira do Estúdio, volta
inteiro com `restaurar_modelo`) — testar formato e desistir é normal, e sem isso a lista de modelos
vira cemitério.

CLI: novo_cliente.py <Nome> [--portar Joao/dividido-mascara]
     novo_cliente.py --completar        (cria só o que faltar das 5 pastas padrão nos clientes existentes)
     novo_cliente.py --remover <Cliente>/<modelo>\n     novo_cliente.py --remover-projeto <Cliente>
     novo_cliente.py --lixeira | --restaurar <id> | --apagar <id>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, agora, cliente as _cliente, clientes, ensure, gravar_json, hoje, make_slug

PASTAS_CONTENT = ("entrada", "material", "modelos", "output", "transcricoes")   # as 5 do padrão (clientes_padrao.py)
IDENTIDADE_PADRAO = {
    "cores": ["#d4af37", "#f4efe6", "#0a0b0d"],          # dourado, marfim, preto: neutro, a tela troca pelas do cliente
    "fontes": ["Bebas Neue", "Barlow"],
    "tom": "direto e curto, sem enrolação",
}

IGNORAR = {"_sandbox", "acervo", "_sb-", "node_modules", "output", ".DS_Store", "__pycache__", "qa", "aprendizado", "referencia", "demos"}


def _ignora(dir_, nomes):
    out = []
    for n in nomes:
        if n in IGNORAR or n.startswith(("_sandbox", "_sb-", "acervo")) or n.endswith((".mp4", ".mov", ".mkv")):
            out.append(n)
    return out


def portar_modelo(cli_destino: dict, origem_cliente: str, origem_modelo: str, novo_nome: str | None = None) -> Path:
    ori = _cliente(origem_cliente)
    if not ori:
        raise ValueError(f"cliente de origem não existe: {origem_cliente}")
    src = ori["content"] / "modelos" / origem_modelo
    if not src.is_dir():
        raise ValueError(f"modelo de origem não existe: {origem_cliente}/{origem_modelo}")
    nome = novo_nome or origem_modelo
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', nome) or Path(origem_modelo).name != origem_modelo:
        raise ValueError('Use um nome de modelo em letras minúsculas e hífens.')
    dst = cli_destino["content"] / "modelos" / nome
    if dst.exists():
        raise ValueError(f"o modelo {nome} já existe em {cli_destino['nome']}")
    shutil.copytree(src, dst, ignore=_ignora)
    if nome != origem_modelo:   # nome novo: a saída do render (OUT_DIR="$VC/output/<modelo>") acompanha, senão cai na do outro
        padrao = re.compile(r"(output/)" + re.escape(origem_modelo) + r"(?=[\"'/\s]|$)", re.M)
        for arq in [p for p in dst.iterdir() if p.is_file() and p.suffix in (".sh", ".py", ".js", ".mjs")]:
            try:
                txt = arq.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            novo = padrao.sub(lambda m: m.group(1) + nome, txt)
            if novo != txt:
                arq.write_text(novo, encoding="utf-8")
    apr = ensure(dst / "aprendizado")
    regras_ori = {}
    try:
        regras_ori = json.loads((src / "aprendizado" / "regras.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    gravar_json(apr / "regras.json", {
        "modelo": nome,
        "cliente": cli_destino["nome"],
        "descricao": (f"Portado de {origem_cliente}/{origem_modelo} em {hoje()} pelo Estúdio, AUTOCONTIDO em "
                      f"{cli_destino['nome']}/. As regras do modelo de origem NÃO herdam automaticamente — "
                      f"o que vale aqui é o que o João aprovar/corrigir neste cliente."),
        "portado_de": f"{origem_cliente}/{origem_modelo}",
        "descricao_origem": regras_ori.get("descricao", ""),
        "regras": [],
    })
    (apr / "historico.jsonl").write_text("", encoding="utf-8")
    _registrar_no_claude_md(cli_destino, nome, origem_cliente, origem_modelo)
    return dst


def _registrar_no_claude_md(cli: dict, modelo: str, origem_cliente: str, origem_modelo: str) -> None:
    md = RAIZ / "CLAUDE.md"
    if not md.exists():
        return
    txt = md.read_text(encoding="utf-8")
    caminho = f"clientes/{cli['nome']}/{cli['content'].name}/modelos/{modelo}/aprendizado/"
    if caminho in txt:
        return
    linha = (f"| {cli['nome']} | `{modelo}` (portado de {origem_cliente}/{origem_modelo} pelo Estúdio em {hoje()}; "
             f"autocontido em `clientes/{cli['nome']}/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) "
             f"| `{caminho}` |")
    linhas = txt.splitlines()
    ultimo = max((i for i, l in enumerate(linhas) if l.startswith("|") and "aprendizado" in l), default=None)
    if ultimo is None:
        txt += "\n" + linha + "\n"
    else:
        linhas.insert(ultimo + 1, linha)
        txt = "\n".join(linhas) + "\n"
    md.write_text(txt, encoding="utf-8")


def _sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c))


def nome_do_cliente(nome: str) -> tuple[str, str]:
    """Valida o nome digitado e devolve (nome da pasta, nome da pasta Content). Erro em português simples (ValueError)."""
    bruto = (nome or "").strip()
    if not bruto:
        raise ValueError("Escreva o nome do cliente.")
    if "/" in bruto or "\\" in bruto or ".." in bruto or bruto.startswith("."):
        raise ValueError("Nome inválido: não use barra nem pontos. Escreva só o nome, por exemplo: Carla.")
    limpo = _sem_acento(bruto)
    if re.search(r"[^A-Za-z0-9 _-]", limpo):
        raise ValueError("Nome inválido: use só letras, números e espaço (sem símbolos).")
    pasta = re.sub(r"[^A-Za-z0-9]+", "", limpo)   # "Maria Teste" → MariaTeste; mantém o CamelCase digitado
    if not pasta:
        raise ValueError("Nome inválido: use pelo menos uma letra ou número.")
    if len(pasta) > 40:
        raise ValueError("Nome muito comprido: use até 40 letras.")
    pasta = pasta[0].upper() + pasta[1:]
    base = RAIZ / "clientes"
    if base.is_dir() and any(d.name.lower() == pasta.lower() for d in base.iterdir()):
        raise ValueError(f"Já existe um cliente chamado {pasta}. Escolha outro nome.")
    return pasta, pasta.lower() + "Content"


def completar_content(content: Path, marcar_todas: bool = False) -> list[str]:
    """Garante as 5 pastas do padrão dentro de <x>Content/, cada uma com .gitkeep. Só CRIA o que falta: pasta que já existe
    não é mexida (com marcar_todas=True ela só ganha o arquivo .gitkeep, que o Git precisa pra guardar a estrutura).
    Devolve o que criou, caminho relativo a clientes/."""
    content = Path(content)
    criadas = []
    for nome in PASTAS_CONTENT:
        p = content / nome
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            continue
        novo = not p.exists()
        ensure(p)
        kp = p / ".gitkeep"
        if (novo or marcar_todas or not any(p.iterdir())) and not kp.exists():
            kp.touch()
            criadas.append(f"{content.parent.name}/{content.name}/{nome}/.gitkeep")
    return criadas


def completar_todos() -> list[str]:
    """Roda completar_content em todos os clientes que existem (o que já está lá não é tocado)."""
    out = []
    for d in sorted((RAIZ / "clientes").iterdir()):
        if d.is_dir() and not d.name.startswith((".", "_")):
            for c in sorted(x for x in d.iterdir() if x.is_dir() and x.name.endswith("Content")):
                out += completar_content(c, marcar_todas=True)
    return out


def criar(nome: str, env_de: str | None = None, portar: str | None = None, descricao: str = "") -> dict:
    nome, content_nome = nome_do_cliente(nome)
    if portar:   # confere a origem ANTES de criar, pra não deixar cliente pela metade
        oc, _, om = portar.partition("/")
        if not om or not _cliente(oc) or not (_cliente(oc)["content"] / "modelos" / om).is_dir():
            raise ValueError(f"Não achei o modelo {portar} pra copiar.")
    pasta = RAIZ / "clientes" / nome
    # só a pele; sem .env (as chaves vêm do app/.env; env_de ficou só por compatibilidade da tela)
    gravar_json(pasta / "identidade.json", {"cliente": nome, "descricao": (descricao or "").strip(), **IDENTIDADE_PADRAO})
    completar_content(pasta / content_nome)
    cli = _cliente(nome)
    if portar:
        oc, om = portar.split("/", 1)
        portar_modelo(cli, oc, om)
        cli = _cliente(nome)
    return cli


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nome", nargs="?"); ap.add_argument("--env-de", default=None); ap.add_argument("--portar", default=None)
    ap.add_argument("--descricao", default="")
    ap.add_argument("--remover", default=None, metavar="Cliente/modelo")
    ap.add_argument("--remover-projeto", default=None, metavar="Cliente")
    ap.add_argument("--lixeira", action="store_true"); ap.add_argument("--restaurar", default=None)
    ap.add_argument("--apagar", default=None)
    ap.add_argument("--completar", action="store_true", help="cria o que faltar das 5 pastas padrão nos clientes que já existem")
    a = ap.parse_args()
    if a.completar:
        print(json.dumps({"criados": completar_todos()}, ensure_ascii=False, indent=1)); return
    if a.remover_projeto:
        print(json.dumps(remover_cliente(a.remover_projeto), ensure_ascii=False)); return
    if a.remover:
        cli, mod = a.remover.split("/", 1)
        print(json.dumps(remover_modelo(cli, mod), ensure_ascii=False)); return
    if a.lixeira:
        print(json.dumps(lixeira(), ensure_ascii=False, indent=1)); return
    if a.restaurar:
        print(json.dumps(restaurar_modelo(a.restaurar), ensure_ascii=False)); return
    if a.apagar:
        print(json.dumps({"apagado": apagar_da_lixeira(a.apagar)}, ensure_ascii=False)); return
    if not a.nome:
        ap.error("informe o nome do cliente (ou use --remover/--lixeira/--restaurar/--apagar)")
    c = criar(a.nome, a.env_de, a.portar, a.descricao)
    print(json.dumps({"cliente": c["nome"], "pasta": str(c["pasta"]), "modelos": c["modelos"]}, ensure_ascii=False))




# ═══════════════════ REMOVER MODELO (o inverso de portar) ═══════════════════
# O João testa formato: porta um modelo, tenta, não gosta. Sem um jeito de tirar, a lista de modelos
# vira um cemitério e o Estúdio fica ilegível. Remover aqui NÃO é apagar: o modelo vai pra lixeira do
# Estúdio (mover, não copiar — é instantâneo mesmo com os .mp4 de output juntos) e pode voltar inteiro.
# Apagar de vez é um segundo clique, explícito.

import _comum  # noqa: E402
from _comum import ler_json, lixeira_apagar, lixeira_guardar, lixeira_item, lixeira_listar  # noqa: E402


def _linhas_do_claude_md(cli: dict, modelo: str) -> list[str]:
    md = RAIZ / "CLAUDE.md"
    if not md.exists():
        return []
    alvo = f"{cli['nome']}/{cli['content'].name}/modelos/{modelo}/aprendizado/"
    return [l for l in md.read_text(encoding="utf-8").splitlines() if l.startswith("|") and alvo in l]


def _tirar_do_claude_md(cli: dict, modelo: str) -> list[str]:
    md = RAIZ / "CLAUDE.md"
    fora = _linhas_do_claude_md(cli, modelo)
    if fora:
        linhas = md.read_text(encoding="utf-8").splitlines()
        md.write_text("\n".join(l for l in linhas if l not in fora) + "\n", encoding="utf-8")
    return fora


def _devolver_ao_claude_md(linhas: list[str]) -> None:
    md = RAIZ / "CLAUDE.md"
    if not linhas or not md.exists():
        return
    txt = md.read_text(encoding="utf-8")
    faltando = [l for l in linhas if l not in txt]
    if not faltando:
        return
    corpo = txt.splitlines()
    ultimo = max((i for i, l in enumerate(corpo) if l.startswith("|") and "aprendizado" in l), default=None)
    pos = (ultimo + 1) if ultimo is not None else len(corpo)
    corpo[pos:pos] = faltando
    md.write_text("\n".join(corpo) + "\n", encoding="utf-8")


def _jobs_do_modelo(cliente_nome: str, modelo: str) -> list[dict]:
    out = []
    for j in sorted(_comum.JOBS.glob(f"{cliente_nome}/*/job.json")):
        d = ler_json(j, {}) or {}
        if d.get("modelo") == modelo:
            out.append(d)
    return out


def pasta_do_modelo(cliente_nome: str, modelo: str) -> tuple[dict, Path]:
    """Valida cliente + nome de modelo e devolve a pasta — usado por quem mexe no modelo."""
    cli = _cliente(cliente_nome)
    if not cli:
        raise ValueError(f"cliente não encontrado: {cliente_nome}")
    if Path(modelo).name != modelo or modelo in (".", "..") or not modelo.strip():
        raise ValueError("nome de modelo inválido")
    pasta = cli["content"] / "modelos" / modelo
    if not pasta.is_dir():
        raise ValueError(f"modelo não encontrado: {cliente_nome}/{modelo}")
    if pasta.resolve().parent != (cli["content"] / "modelos").resolve():
        raise ValueError("caminho fora da pasta de modelos deste cliente")
    return cli, pasta


def remover_modelo(cliente_nome: str, modelo: str, motivo: str = "") -> dict:
    """Move o modelo (e os vídeos dele) pra lixeira do Estúdio. Recusa se houver vídeo em aberto."""
    cli, pasta = pasta_do_modelo(cliente_nome, modelo)
    abertos = [j for j in _jobs_do_modelo(cli["nome"], modelo) if j.get("status") != "arquivado"]
    if abertos:
        raise ValueError("há vídeo em aberto com este modelo (" +
                         ", ".join(j.get("slug", "?") for j in abertos[:4]) +
                         "). Feche ou apague o vídeo antes de remover o modelo.")
    info = {"tipo": "modelo", "rotulo": f"{cli['nome']}-{modelo}", "cliente": cli["nome"], "modelo": modelo,
            "motivo": motivo, "content": cli["content"].name,
            "linhas_claude_md": _tirar_do_claude_md(cli, modelo),
            "jobs": [j.get("slug") for j in _jobs_do_modelo(cli["nome"], modelo)]}
    ident = lixeira_guardar({"modelo": pasta, "output": cli["content"] / "output" / modelo}, info)
    return {"id": ident, **info}


def restaurar_modelo(ident: str) -> dict:
    """Traz o modelo de volta, com os vídeos e a linha dele no mapa do CLAUDE.md."""
    d = lixeira_item(ident)
    info = ler_json(d / "info.json", {}) or {}
    cli = _cliente(info.get("cliente", ""))
    if not cli:
        raise ValueError(f"o cliente {info.get('cliente')} não existe mais")
    destino = cli["content"] / "modelos" / info["modelo"]
    if destino.exists():
        raise ValueError(f"já existe um modelo {info['modelo']} em {cli['nome']} — renomeie antes de restaurar")
    ensure(destino.parent)
    shutil.move(str(d / "modelo"), str(destino))
    if (d / "output").is_dir() and any((d / "output").iterdir()):   # output/<formato>/ só volta se havia vídeo
        saidas = cli["content"] / "output" / info["modelo"]
        ensure(saidas.parent)
        if not saidas.exists():
            shutil.move(str(d / "output"), str(saidas))
    _devolver_ao_claude_md(info.get("linhas_claude_md") or [])
    shutil.rmtree(d, ignore_errors=True)
    return {"cliente": cli["nome"], "modelo": info["modelo"], "pasta": str(destino)}


def remover_cliente(cliente_nome: str, motivo: str = "") -> dict:
    """Remove o PROJETO inteiro: modelos, aprendizado, templates, automação e o registro dos vídeos.

    Vai tudo pra lixeira num item só — inclusive `app/jobs/<Cliente>/`, senão o histórico dos
    vídeos ficaria apontando pra um cliente que não existe mais. Restaurar devolve o conjunto.
    """
    cli = _cliente(cliente_nome)
    if not cli:
        raise ValueError(f"cliente não encontrado: {cliente_nome}")
    pasta = Path(cli["pasta"]).resolve()
    if pasta.parent != (RAIZ / "clientes").resolve() or pasta == RAIZ.resolve():
        raise ValueError("a pasta do cliente não está em clientes/")
    abertos = [j for j in _jobs_do_cliente(cli["nome"]) if j.get("status") != "arquivado"]
    if abertos:
        raise ValueError("há vídeo em aberto neste projeto (" +
                         ", ".join(j.get("slug", "?") for j in abertos[:4]) +
                         "). Feche ou apague os vídeos antes de remover o projeto.")
    linhas = []
    for m in cli["modelos"]:
        linhas += _tirar_do_claude_md(cli, m)
    info = {"tipo": "cliente", "rotulo": cli["nome"], "cliente": cli["nome"], "modelo": "(projeto inteiro)",
            "motivo": motivo, "modelos": list(cli["modelos"]), "n_videos": cli.get("n_videos", 0),
            "linhas_claude_md": linhas}
    ident = lixeira_guardar({"cliente": pasta, "jobs": _comum.JOBS / cli["nome"]}, info)
    return {"id": ident, **info}


def _jobs_do_cliente(cliente_nome: str) -> list[dict]:
    return [ler_json(j, {}) or {} for j in sorted(_comum.JOBS.glob(f"{cliente_nome}/*/job.json"))]


def restaurar_cliente(ident: str) -> dict:
    d = lixeira_item(ident)
    info = ler_json(d / "info.json", {}) or {}
    destino = RAIZ / "clientes" / info["cliente"]
    if destino.exists():
        raise ValueError(f"já existe a pasta {info['cliente']}/ — renomeie antes de restaurar")
    shutil.move(str(d / "cliente"), str(destino))
    if (d / "jobs").is_dir():
        alvo = _comum.JOBS / info["cliente"]
        if not alvo.exists():
            ensure(alvo.parent); shutil.move(str(d / "jobs"), str(alvo))
    _devolver_ao_claude_md(info.get("linhas_claude_md") or [])
    shutil.rmtree(d, ignore_errors=True)
    return {"cliente": info["cliente"], "modelo": "", "pasta": str(destino)}


def lixeira() -> list[dict]:
    """O que dá pra trazer de volta. `pode_voltar` diz se o lugar de origem ainda está livre."""
    import ficha as _ficha, material as _material
    out = []
    for x in lixeira_listar():
        if x.get("tipo") == "acervo":
            import acervo as _ac
            x["pode_voltar"] = not (_ac.ACERVO / x.get("item", "")).exists()
        elif x.get("tipo") == "cliente":
            x["pode_voltar"] = not (RAIZ / "clientes" / x.get("cliente", "")).exists()
        elif x.get("tipo") == "asset":
            x["pode_voltar"] = _ficha.asset_pode_voltar(x)
        elif x.get("tipo") == "material":
            x["pode_voltar"] = _material.pode_voltar(x)
        else:
            cli = _cliente(x.get("cliente", ""))
            x["pode_voltar"] = bool(cli) and not (cli["content"] / "modelos" / x.get("modelo", "")).exists()
        out.append(x)
    return out


def restaurar(ident: str) -> dict:
    """Restaura qualquer item da lixeira (modelo ou asset), pelo tipo guardado no info.json."""
    info = ler_json(lixeira_item(ident) / "info.json", {}) or {}
    if info.get("tipo") == "asset":
        import ficha as _ficha
        return _ficha.restaurar_asset(ident)
    if info.get("tipo") == "material":
        import material as _material
        return _material.restaurar(ident)
    if info.get("tipo") == "acervo":
        import acervo as _ac
        return _ac.restaurar(ident)
    if info.get("tipo") == "cliente":
        return restaurar_cliente(ident)
    if info.get("tipo") == "pasta":   # estilo, pasta de vídeo ou estudo (remover.py)
        import remover as _rm
        return _rm.restaurar_pasta(ident, info)
    return restaurar_modelo(ident)


def apagar_da_lixeira(ident: str) -> bool:
    """Apaga de vez (irreversível) — só depois do João confirmar na tela."""
    return lixeira_apagar(ident)


if __name__ == "__main__":
    main()
