#!/usr/bin/env python3
"""
ficha — a FICHA TÉCNICA de um modelo: o que faz, quando usar, estrutura, paleta, fontes, áudio,
b-roll, entrada, como usar, QA, templates. Mostrada na página do modelo no Estúdio.

Fonte da verdade = <modelo>/ficha.json (escrita a partir de README/regras/scripts, revisada).
O que der pra extrair automaticamente dos scripts (cores #hex, fontes, assets, flags do gerar.sh,
motor) entra como complemento — a ficha.json manda quando os dois existem.

CLI:  ficha.py <Cliente> <modelo>      imprime a ficha consolidada
      ficha.py --validar               lista modelos sem ficha ou com campos faltando
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, clientes, cliente as _cliente, ler_json

# Campos que toda ficha deve ter (o validador cobra)
OBRIGATORIOS = ["titulo", "resumo", "quando_usar", "estrutura", "entrada", "como_usar", "qa"]

ESQUEMA = {
    "titulo": "Nome bonito do modelo (ex.: 'Dividido-Máscara (beats)')",
    "resumo": "1-2 frases: o que o vídeo final É e pra que serve (tom profissional, sem jargão interno)",
    "quando_usar": "Quando escolher este modelo e não outro (tipo de conteúdo, objetivo, duração)",
    "formato": {"resolucao": "1080x1920", "proporcao": "9:16", "duracao_tipica": "30-60s"},
    "estrutura": ["lista ordenada do que aparece na tela, de cima pra baixo / no tempo"],
    "paleta": [{"cor": "#DC2626", "uso": "palavra de destaque na legenda"}],
    "fontes": [{"nome": "Barlow-Black", "uso": "legenda"}],
    "audio": {"musica": "qual/como (volume, LUFS)", "sfx": ["click", "whoosh"], "voz": "áudio original do bruto"},
    "broll": "política de b-roll deste modelo (fonte permitida, proibições, ritmo)",
    "entrada": "o que o bruto precisa ter: enquadramento, duração, áudio, o que evitar",
    "como_usar": ["passo 1", "passo 2", "..."],
    "comando": "./gerar.sh --dir _sandbox ... (o comando de referência aprovado)",
    "qa": ["o que conferir antes de entregar"],
    "templates": ["assets/… que são parte da identidade (música, sfx, logos, fontes)"],
    "motor": "ffmpeg + PIL + GROQ | Remotion <Composição>",
    "origem": "de onde foi portado / evolução de quê",
    "tempo_producao": "quanto tempo leva em média",
}

FONTES_CONHECIDAS = r"(Barlow[-\w]*|Bebas[-\w]*|Poppins[-\w]*|Playfair[-\w]*|Inter[-\w]*|Montserrat[-\w]*|Roboto[-\w]*|Anton|Oswald[-\w]*|Impact|Helvetica[-\w]*|Arial[-\w]*|DejaVu[-\w]*|Liberation[-\w]*)"


def _auto(pasta: Path) -> dict:
    """Extrai o que dá dos scripts do modelo."""
    cores, fontes, flags, motor = {}, {}, [], set()
    for p in sorted(pasta.glob("*")):
        if not p.is_file() or p.suffix not in (".sh", ".py", ".js", ".ts", ".tsx", ".json", ".md") or p.name == "ficha.json":
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r"#([0-9A-Fa-f]{6})\b", t):
            c = "#" + m.group(1).upper()
            if c in ("#000000", "#FFFFFF"):
                continue
            cores[c] = cores.get(c, 0) + 1
        for m in re.finditer(FONTES_CONHECIDAS, t):
            f = m.group(1).rstrip("-_")
            fontes[f] = fontes.get(f, 0) + 1
        if p.name == "gerar.sh":
            flags = sorted(set(re.findall(r"^\s*(--[a-z][a-z0-9-]*)\)", t, re.M)))
        low = t.lower()
        if "ffmpeg" in low: motor.add("ffmpeg")
        if "from pil" in low or "import pil" in low or "pillow" in low: motor.add("PIL")
        if "groq" in low: motor.add("GROQ (whisper)")
        if "remotion" in low: motor.add("Remotion")
        if "yt-dlp" in low: motor.add("yt-dlp")
        if "rembg" in low: motor.add("rembg")
        if "openai" in low: motor.add("OpenAI")
    assets = []
    if (pasta / "assets").is_dir():
        for a in sorted((pasta / "assets").rglob("*")):
            if a.is_file() and not a.name.startswith(".") and a.suffix.lower() in (".mp3", ".wav", ".png", ".jpg", ".jpeg", ".ttf", ".otf", ".mp4", ".webp"):
                assets.append(str(a.relative_to(pasta)))
    return {
        "cores_auto": [c for c, _ in sorted(cores.items(), key=lambda x: -x[1])[:8]],
        "fontes_auto": [f for f, _ in sorted(fontes.items(), key=lambda x: -x[1])[:6]],
        "flags": flags, "motor_auto": " + ".join(sorted(motor)), "assets": assets,
    }


def carregar(pasta: Path) -> dict:
    ficha = ler_json(pasta / "ficha.json", {}) or {}
    auto = _auto(pasta)
    out = dict(ficha)
    out["_auto"] = auto
    if not out.get("motor") and auto["motor_auto"]:
        out["motor"] = auto["motor_auto"]
    # paleta: ficha manda; cores só nos scripts entram como "outras cores nos scripts"
    fixas = {c["cor"].upper() for c in out.get("paleta", []) if isinstance(c, dict) and c.get("cor")}
    out["cores_extra"] = [c for c in auto["cores_auto"] if c not in fixas]
    fixas_f = {f["nome"].split("-")[0].lower() for f in out.get("fontes", []) if isinstance(f, dict) and f.get("nome")}
    out["fontes_extra"] = [f for f in auto["fontes_auto"] if f.split("-")[0].lower() not in fixas_f]
    out["tem_ficha"] = bool(ficha)
    out["faltando"] = [k for k in OBRIGATORIOS if not out.get(k)]
    return out


def validar() -> list[tuple[str, str, list[str]]]:
    probs = []
    for c in clientes():
        for m in c["modelos"]:
            f = carregar(c["content"] / "modelos" / m)
            if f["faltando"]:
                probs.append((c["nome"], m, f["faltando"]))
    return probs



# ═══════════════════ ASSETS DO MODELO ═══════════════════
# `<modelo>/assets/` é o material FIXO do modelo: a cama de música que ele sempre usa, a fonte, o
# logo, a capa do produto, o card de preço. Não é acervo (aquele é compartilhado entre todos): isso
# aqui é a identidade daquele modelo, e é o que entra por padrão quando o João não pede outra coisa.
# Ele precisa poder trocar, renomear, tirar da frente — e promover uma música pro acervo pra reusar
# em qualquer cliente.

AUDIO_EXTS_ASSET = {".mp3", ".wav", ".m4a", ".aac"}
FONTE_EXTS = {".ttf", ".otf", ".woff", ".woff2"}
EXTS_ASSET = AUDIO_EXTS_ASSET | FONTE_EXTS | {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".json", ".svg"}


def tipo_de_arquivo(p: Path) -> str:
    e = p.suffix.lower()
    return ("audio" if e in AUDIO_EXTS_ASSET else "imagem" if e in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
            else "video" if e in {".mp4", ".mov"} else "fonte" if e in FONTE_EXTS else "arquivo")


def caminho_asset(pasta_modelo: Path, nome: str) -> Path:
    """Resolve `nome` dentro de <modelo>/assets/ — recusa qualquer coisa que saia de lá."""
    base = (Path(pasta_modelo) / "assets").resolve()
    alvo = (base / nome).resolve()
    if not str(alvo).startswith(str(base) + "/") or ".." in Path(nome).parts:
        raise ValueError("caminho de asset inválido")
    return alvo


def _citado_por(pasta_modelo: Path, nome: str) -> list[str]:
    """Scripts do modelo que citam este arquivo — remover sem olhar isso quebra o gerar.sh."""
    alvo = Path(nome).name
    out = []
    for p in sorted(Path(pasta_modelo).iterdir()):
        if p.is_file() and p.suffix in (".sh", ".py", ".js", ".ts", ".tsx", ".json") and not p.name.startswith("."):
            try:
                if alvo in p.read_text(encoding="utf-8", errors="ignore"):
                    out.append(p.name)
            except OSError:
                pass
    return out


def assets(pasta_modelo: Path, com_acervo: bool = True) -> list[dict]:
    """Tudo que está em <modelo>/assets/, com tipo, tamanho, quem usa e se já está no acervo."""
    from _comum import rel as _rel, sha_arquivo
    base = Path(pasta_modelo) / "assets"
    if not base.is_dir():
        return []
    indice = {}
    if com_acervo:
        try:
            import acervo
            indice = acervo.indice_hashes()
        except Exception:
            indice = {}
    out = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in EXTS_ASSET:
            continue
        nome = str(p.relative_to(base))
        item = {"nome": nome, "rel": _rel(p), "tipo": tipo_de_arquivo(p),
                "mb": round(p.stat().st_size / 1e6, 2), "usado_por": _citado_por(pasta_modelo, nome),
                "no_acervo": None}
        if indice:
            try:
                item["no_acervo"] = indice.get(sha_arquivo(p))
            except OSError:
                pass
        out.append(item)
    return out


def subir_asset(pasta_modelo: Path, origem: Path, nome_final: str = "", subpasta: str = "") -> dict:
    """Põe um arquivo em <modelo>/assets/[subpasta]/ (substitui manda o antigo pra lixeira)."""
    from _comum import ensure, make_slug
    origem = Path(origem)
    ext = origem.suffix.lower()
    if ext not in EXTS_ASSET:
        raise ValueError(f"tipo de arquivo não suportado em assets: {ext}")
    nome = (nome_final or origem.stem).strip()
    nome = f"{make_slug(Path(nome).stem) or 'asset'}{ext}"
    rel_nome = f"{make_slug(subpasta)}/{nome}" if subpasta.strip() else nome
    destino = caminho_asset(pasta_modelo, rel_nome)
    substituiu = None
    if destino.exists():
        substituiu = remover_asset(pasta_modelo, rel_nome, motivo="substituído por um arquivo novo")["id"]
    ensure(destino.parent)
    shutil.move(str(origem), str(destino))
    return {"nome": rel_nome, "substituiu": substituiu}


def renomear_asset(pasta_modelo: Path, nome: str, novo: str) -> dict:
    """Renomear é seguro só enquanto nenhum script cita o nome antigo — senão ele avisa."""
    from _comum import make_slug
    atual = caminho_asset(pasta_modelo, nome)
    if not atual.is_file():
        raise ValueError("asset não encontrado")
    destino = caminho_asset(pasta_modelo, str(Path(nome).parent / f"{make_slug(Path(novo).stem) or 'asset'}{atual.suffix.lower()}")
                            if str(Path(nome).parent) != "." else f"{make_slug(Path(novo).stem) or 'asset'}{atual.suffix.lower()}")
    if destino.exists():
        raise ValueError("já existe um asset com esse nome")
    citado = _citado_por(pasta_modelo, nome)
    if citado:
        raise ValueError("este arquivo é citado por " + ", ".join(citado) +
                         " — renomear quebraria o render. Ajuste o script antes (ou suba o novo com o mesmo nome).")
    atual.rename(destino)
    return {"de": nome, "para": str(destino.relative_to(Path(pasta_modelo) / "assets"))}


def remover_asset(pasta_modelo: Path, nome: str, motivo: str = "", cliente: str = "", modelo: str = "") -> dict:
    """Tira o asset da frente — vai pra lixeira do Estúdio e volta inteiro."""
    from _comum import lixeira_guardar
    alvo = caminho_asset(pasta_modelo, nome)
    if not alvo.is_file():
        raise ValueError("asset não encontrado")
    info = {"tipo": "asset", "rotulo": f"{cliente or Path(pasta_modelo).parents[2].name}-{modelo or Path(pasta_modelo).name}-{Path(nome).name}",
            "cliente": cliente or Path(pasta_modelo).parents[2].name, "modelo": modelo or Path(pasta_modelo).name,
            "asset": nome, "pasta_modelo": str(Path(pasta_modelo)), "motivo": motivo,
            "usado_por": _citado_por(pasta_modelo, nome), "arquivo": alvo.name}
    return {"id": lixeira_guardar({alvo.name: alvo}, info), **info}


def asset_pode_voltar(info: dict) -> bool:
    try:
        pm = Path(info.get("pasta_modelo", ""))
        return pm.is_dir() and not caminho_asset(pm, info.get("asset", "")).exists()
    except ValueError:
        return False


def restaurar_asset(ident: str) -> dict:
    from _comum import ensure, ler_json as _ler, lixeira_item
    d = lixeira_item(ident)
    info = _ler(d / "info.json", {}) or {}
    pm = Path(info.get("pasta_modelo", ""))
    if not pm.is_dir():
        raise ValueError("a pasta do modelo não existe mais")
    destino = caminho_asset(pm, info["asset"])
    if destino.exists():
        raise ValueError("já existe um asset com esse nome — renomeie antes de restaurar")
    ensure(destino.parent)
    shutil.move(str(d / info["arquivo"]), str(destino))
    shutil.rmtree(d, ignore_errors=True)
    return {"cliente": info.get("cliente"), "modelo": info.get("modelo"), "asset": info["asset"]}


def tags_automaticas(nome: str, tipo: str, cliente: str, modelo: str, caminho: Path | None = None) -> str:
    """Tags sem ele digitar: o que é, de quem veio e a gaveta em que estava (musica/, sfx/…).

    Música e efeito sonoro entram com a tag certa — quem decide é o mesmo classificador do acervo
    (duração curta = efeito), não o nome da pasta, senão um whoosh solto viraria "musica".
    """
    if tipo == "audio":
        try:
            import acervo
            tipo = acervo._tipo(Path(nome).suffix.lower(), caminho or Path(nome))
        except Exception:
            tipo = "sfx" if "sfx" in nome.lower() else "musica"
    partes = [t for t in (tipo, cliente, modelo) if t]
    gaveta = Path(nome).parent.name
    if gaveta and gaveta not in partes:
        partes.append(gaveta)
    return ", ".join(dict.fromkeys(partes))


def asset_pro_acervo(pasta_modelo: Path, nome: str, titulo: str = "", tags: str = "",
                     cliente: str = "", modelo: str = "") -> dict:
    """COPIA o asset pro acervo compartilhado (o modelo continua com o dele).

    É o caminho de promover a cama de música de um modelo pra qualquer cliente usar. Copia, não move:
    tirar o arquivo daqui quebraria o gerar.sh deste modelo. Não dispara a descrição automática (é
    uma sessão de IA por item) — no acervo tem o botão "Descrever" pra quando ele quiser.
    """
    import acervo
    from _comum import sha_arquivo
    alvo = caminho_asset(pasta_modelo, nome)
    if not alvo.is_file():
        raise ValueError("asset não encontrado")
    cli = cliente or Path(pasta_modelo).parents[2].name
    mod = modelo or Path(pasta_modelo).name
    ja = acervo.indice_hashes().get(sha_arquivo(alvo))
    if ja:
        return {**(acervo.item(ja) or {"slug": ja, "titulo": ja}), "ja_estava": True}
    m = acervo.adicionar_arquivo(
        alvo, titulo or Path(nome).stem,
        tags=tags or tags_automaticas(nome, tipo_de_arquivo(alvo), cli, mod, alvo),
        fonte=f"{cli}/{mod}",
        observacao=f"Promovido do arquivo {nome} do motor de {mod} pelo Estúdio.",
        origem_tipo="asset-de-modelo", mover=False, descrever_auto=False)
    return m


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--validar":
        ps = validar()
        for c, m, falt in ps:
            print(f"{c}/{m}: faltam {', '.join(falt)}")
        print(f"{len(ps)} modelo(s) com pendência")
    elif len(sys.argv) == 3:
        c = _cliente(sys.argv[1])
        print(json.dumps(carregar(c["content"] / "modelos" / sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(ESQUEMA, ensure_ascii=False, indent=2))
