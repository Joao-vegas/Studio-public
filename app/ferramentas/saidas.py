"""Saídas: tudo que existe em clientes/*/*Content/output/ (pasta de trabalho + .mp4 irmão), de qualquer origem (tela,
chat, teste). Apagar libera o disco de verdade; guardar como referência protege e vira exemplo do formato.

UM caminho só pra apagar (apagar / apagar_video): leva a pasta e o .mp4 em output/, miniatura e .json/.info do vídeo, o job
(app/jobs/<Cli>/<slug>), a sandbox _sandbox-<slug>, versões listadas no job, o registro do Em andamento, o briefing ligado e
temporários. NÃO leva: cópia exportada (Mac/iCloud), acervo, custos (app/custos é livro de gasto) nem aprendizado/regras.

Trava: só apaga dentro de clientes/<Nome>/<x>Content/output/<modelo>/ (e as peças do próprio vídeo, por nome exato), sem
'..', sem link simbólico (resolve antes de conferir). Vídeo rodando não apaga. Referência nunca sai em lote: só uma por vez,
com confirmar=True. O que sai fica em app/custos/apagados.jsonl (só registro do que saiu; o gasto continua nos livros).

  python3 app/ferramentas/saidas.py listar
  python3 app/ferramentas/saidas.py vazias        (só lista as pastas vazias; remover é limpar_pastas_vazias(dry_run=False))
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, VIDEO_EXTS, agora, append_jsonl, gravar_json, ler_json  # noqa: E402
import formatos as _formatos  # noqa: E402

REF = "REFERENCIA.json"


def _raiz() -> Path:
    return Path(RAIZ).resolve()


def _apagados() -> Path:
    return _raiz() / "app" / "custos" / "apagados.jsonl"


def _e_video(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in VIDEO_EXTS


def _bytes(p: Path) -> int:
    if p.is_symlink():
        return 0
    if p.is_file():
        return p.stat().st_size
    return sum(q.lstat().st_size for q in p.rglob("*") if q.is_file() and not q.is_symlink()) if p.is_dir() else 0


def _rel(p: Path) -> str:
    return str(p.relative_to(_raiz()))


def _par(p: Path) -> tuple[Path | None, Path | None]:
    """(pasta, vídeo) de uma saída: a pasta <slug>/ e o <slug>.mp4 ao lado, se existirem."""
    if p.is_dir():
        mp4 = next((p.with_name(p.name + e) for e in (".mp4", ".mov") if p.with_name(p.name + e).is_file()), None)
        return p, mp4
    pasta = p.with_suffix("")
    return (pasta if pasta.is_dir() and not pasta.is_symlink() else None), p


def conferir(caminho: str | Path) -> Path:
    """Trava de caminho. Devolve o caminho absoluto se for uma saída apagável; senão ValueError."""
    bruto = str(caminho or "").strip()
    if not bruto or ".." in Path(bruto).parts:
        raise ValueError("Caminho inválido.")
    base = _raiz()
    p = Path(bruto) if Path(bruto).is_absolute() else base / bruto
    p = Path(os.path.abspath(p))
    if p.is_symlink() or p.resolve() != p:   # link no próprio item ou em qualquer pasta do caminho
        raise ValueError("Esse caminho passa por um atalho (link). Não apago.")
    try:
        partes = p.relative_to(base / "clientes").parts
    except ValueError:
        raise ValueError("Só apago o que está na pasta output dos clientes.") from None
    # clientes/<Nome>/<x>Content/output/<modelo>/<slug>  (ou um vídeo solto direto em output/)
    if len(partes) < 4 or not partes[1].endswith("Content") or partes[2] != "output":
        raise ValueError("Só apago o que está na pasta output dos clientes.")
    if not p.exists():
        raise ValueError("Esse vídeo já não existe.")
    if p.is_dir() and len(partes) < 5:
        raise ValueError("Isso é a pasta inteira de um modelo. Apague um vídeo por vez.")
    if p.is_file() and not _e_video(p):
        raise ValueError("Isso não é um vídeo.")
    return p


def item(caminho: str | Path) -> dict:
    """Uma saída (pasta e/ou vídeo) com cliente, modelo, slug, tamanho, data e se é referência."""
    p = conferir(caminho)
    pasta, mp4 = _par(p)
    partes = p.relative_to(_raiz() / "clientes").parts
    principal = pasta or mp4
    datas = [q.stat().st_mtime for q in (pasta, mp4) if q]
    total = sum(_bytes(q) for q in (pasta, mp4) if q)
    ref = ler_json(pasta / REF) if pasta and (pasta / REF).is_file() else None
    folha = next((pasta / n for n in ("folha.jpg", "storyboard.jpg") if pasta and (pasta / n).is_file()), None)
    return {"caminho": _rel(principal), "pasta": _rel(pasta) if pasta else "", "video": _rel(mp4) if mp4 else "",
            "cliente": partes[0], "modelo": partes[3] if len(partes) > 4 else "", "slug": principal.stem if not pasta else pasta.name,
            "bytes": total, "mb": round(total / 1e6, 1), "data": datetime.fromtimestamp(max(datas)).strftime("%Y-%m-%d %H:%M"),
            "referencia": ref if isinstance(ref, dict) else ({"formato": "", "motivo": ""} if ref is not None else None),
            "folha": _rel(folha) if folha else ""}


def listar(cliente: str = "") -> list[dict]:
    """Toda saída de todos os clientes (ou de um), a mais nova primeiro. Pasta e .mp4 de mesmo nome contam como uma."""
    out, vistos = [], set()
    for saida in sorted((_raiz() / "clientes").glob("*/*Content/output")):
        if cliente and saida.parts[-3] != cliente:
            continue
        cands = []
        for x in sorted(saida.iterdir()):
            if x.name.startswith(".") or x.is_symlink():
                continue
            if x.is_dir():
                cands += [y for y in sorted(x.iterdir()) if not y.name.startswith(".") and not y.is_symlink()]
            else:
                cands.append(x)
        for c in cands:
            if not (c.is_dir() or _e_video(c)):
                continue
            pasta, mp4 = _par(c)
            chave = pasta or mp4
            if chave in vistos:
                continue
            vistos.add(chave)
            try:
                out.append(item(c))
            except ValueError:
                pass
    return sorted(out, key=lambda i: i["data"], reverse=True)


def total(itens: list[dict]) -> float:
    return round(sum(i["bytes"] for i in itens) / 1e6, 1)


ROTULOS = {"pasta": "pasta do vídeo", "video": "vídeo", "versao": "versões", "metadados": "miniatura e metadados",
           "job": "projeto", "sandbox": "rascunhos", "andamento": "registro do Em andamento", "briefing": "briefing",
           "temporarios": "temporários", "uploads": "arquivos enviados", "corte": "corte do bruto"}
META_FORA = {".mp4", ".mov", ".m4v"}      # o vídeo em si já é uma peça própria
FICA = "A cópia exportada, o acervo, os custos e o aprendizado ficam."
LIXEIRA_MAC = "Foi pra Lixeira do Mac (dá pra recuperar pelo Finder); o espaço volta quando você esvaziar a Lixeira."


def _vivo(pid_file: Path) -> bool:
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
        return True
    except Exception:
        return False


def _link(p: Path) -> bool:
    """True se o item ou qualquer pasta do caminho é um atalho (nunca apago por link)."""
    q = Path(os.path.abspath(p))
    return q.is_symlink() or q.resolve() != q


def _jobs_dir() -> Path:
    return _raiz() / "app" / "jobs"


def _jobs_do_video(cli: str, slug: str, modelo: str, it: dict | None) -> list[dict]:
    """Jobs (app/jobs/<cli>/<slug>) deste vídeo: o de mesmo slug e o que aponta pra essa saída."""
    achados = {}
    pasta = _jobs_dir() / cli
    cands = [pasta / slug] if slug else []
    if it and it["video"]:
        cands += [j.parent for j in pasta.glob("*/job.json") if (ler_json(j, {}) or {}).get("saida") == it["video"]]
    for d in cands:
        j = ler_json(d / "job.json") if (d / "job.json").is_file() else None
        if isinstance(j, dict) and j.get("cliente", cli) == cli and (not modelo or not j.get("modelo") or j["modelo"] == modelo):
            achados[d.name] = {**j, "_pasta": d}
    return list(achados.values())


def _andamentos(cli: str, slugs: set[str], it: dict | None) -> list[str]:
    import andamento as _and
    achados = []
    for d in _and.registros():
        if d.get("cliente") != cli:
            continue
        ligado = d["slug"] in slugs or (it and ((d.get("pasta") and d["pasta"] == it["pasta"]) or (d.get("video") and d["video"] == it["video"])))
        if ligado:
            achados.append(d)
    return achados


def _sandboxes(cli: str, modelo: str, slug: str, jobs: list[dict]) -> list[Path]:
    achados = {}
    base = _raiz() / "clientes" / cli
    for j in jobs:
        if j.get("sandbox"):
            achados[Path(os.path.abspath(_raiz() / j["sandbox"]))] = 1
    for p in base.glob(f"*Content/modelos/{modelo or '*'}/_sandbox-{slug}"):
        achados[Path(os.path.abspath(p))] = 1
    out = []
    for p in achados:
        try:
            partes = p.relative_to(base).parts
        except ValueError:
            continue
        # <x>Content/modelos/<modelo>/_sandbox-<slug>: o nome tem que ser exatamente o deste vídeo (nunca um _sandbox compartilhado)
        if len(partes) == 4 and partes[1] == "modelos" and partes[0].endswith("Content") and partes[3] == f"_sandbox-{slug}" \
                and (p.is_dir() or p.is_symlink()):
            out.append(p)
    return out


def _montar_pecas(cli: str, slug: str, modelo: str, it: dict | None, jobs: list[dict], ands: list[dict]) -> tuple[list, list[str]]:
    """Tudo que pertence a ESTE vídeo: [(tipo, Path)], conferido peça por peça, e os avisos do que ficou de fora."""
    pecas, avisos, vistos = [], [], set()

    def add(tipo: str, p: Path) -> None:
        p = Path(os.path.abspath(p))
        if p in vistos or not (p.exists() or p.is_symlink()):
            return
        if _link(p):
            avisos.append(f"{p.name}: passa por atalho, preservado")
            return
        vistos.add(p)
        pecas.append((tipo, p))

    slugs = {slug} | {j["slug"] for j in jobs}
    pasta_out = mp4 = None
    if it:
        pasta_out = conferir(it["pasta"]) if it["pasta"] else None
        mp4 = conferir(it["video"]) if it["video"] else None
        if pasta_out:
            add("pasta", pasta_out)
        if mp4:
            add("video", mp4)
        base = (mp4 or pasta_out).parent
        for q in sorted(base.iterdir()):     # miniatura e .json/.info do vídeo: <slug>.<qualquer coisa> que não é vídeo
            if q.is_file() and q.name.startswith(slug + ".") and q.suffix.lower() not in META_FORA:
                add("metadados", q)
        for j in jobs:                       # versões e renders que o job lista, só se forem <slug>.mp4 / <slug>-vN.mp4 da mesma pasta
            for r in [j.get("saida")] + [v.get("arquivo") for v in j.get("versoes", []) if isinstance(v, dict)]:
                if not r:
                    continue
                q = Path(os.path.abspath(_raiz() / r))
                if q.parent == base and re.fullmatch(re.escape(slug) + r"(?:-v\d+)?\.mp4", q.name):
                    add("video" if q == mp4 else "versao", q)
                elif q.exists() and not any(sb in q.parents for sb in _sandboxes(cli, modelo, slug, jobs)):
                    avisos.append(f"{q.name}: fica guardado (está fora das pastas deste vídeo)")   # a de dentro do rascunho vai junto com ele
    for j in jobs:
        add("job", j["_pasta"])
    for s in _sandboxes(cli, modelo, slug, jobs):
        add("sandbox", s)
    for d in ands:
        add("andamento", _andamento_arq(cli, d["slug"]))
    quem = {(j["cliente"], j["slug"]) for j in jobs}
    for j in jobs:
        bid = str(j.get("briefing_id") or "")
        if not bid or Path(bid).name != bid or bid in (".", ".."):
            continue
        outro = any(o.get("briefing_id") == bid and (o.get("cliente"), o.get("slug")) not in quem
                    for o in (ler_json(x, {}) or {} for x in _jobs_dir().glob("*/*/job.json")))
        if not outro:
            add("briefing", _raiz() / "app" / "briefings" / bid)
    cache = _raiz() / "app" / ".cache"
    if cache.is_dir():
        for q in cache.iterdir():
            if q.is_file() and any(q.name.startswith(s + c) for s in slugs for c in ("-", ".")):
                add("temporarios", q)
    return pecas, avisos


def _andamento_arq(cli: str, slug: str) -> Path:
    import andamento as _and
    return _and._arq(cli, slug)


def _resumo(pecas: list) -> str:
    tipos = list(dict.fromkeys(t for t, _ in pecas))
    return ", ".join(ROTULOS[t] for t in tipos)


def _apagar_alvo(cli: str, slug: str, modelo: str, it: dict | None, lote: bool, confirmar: bool, medir: bool = False) -> dict:
    """Caminho único: manda TUDO de um vídeo (saída, projeto, rascunhos, versões, uploads dele, corte do bruto, registro do
    Em andamento, briefing, miniatura e metadados) pra Lixeira do Mac (~/.Trash/<título>-<data>/, recuperável pelo Finder).
    Levanta ValueError com o motivo da recusa. Não toca no que foi exportado, no acervo, nos custos nem no aprendizado.
    `medir=True` só calcula o tamanho (pra confirmar antes), sem mexer em nada."""
    import andamento as _and
    jobs = _jobs_do_video(cli, slug, modelo, it)
    ands = _andamentos(cli, {slug} | {j["slug"] for j in jobs}, it)
    if it and it["referencia"] is not None and not medir and (lote or not confirmar):
        raise ValueError("É referência: só sai sozinha, com confirmação." if lote else "É referência: confirme pra apagar.")
    if any(_vivo(j["_pasta"] / "runner.pid") or j.get("status") == "na_fila" for j in jobs):
        raise ValueError("Esse vídeo está rodando agora. Espere terminar pra apagar.")
    if any(_and.esta_trabalhando(d) for d in ands):
        raise ValueError("Esse vídeo está sendo feito agora (passo novo há poucos minutos). Espere terminar pra apagar.")
    pecas, avisos = _montar_pecas(cli, slug, modelo, it, jobs, ands)
    import espaco
    ja = {p for _, p in pecas}
    for tipo, p in espaco.pecas_extras(jobs):          # os arquivos que ele enviou e o corte do bruto: nada fica pra trás
        p = Path(os.path.abspath(p))
        if p not in ja and not _link(p):
            pecas.append((tipo, p))
    if not pecas:
        raise ValueError("Esse vídeo já não existe.")
    medidas = [(t, p, _bytes(p)) for t, p in pecas]
    bytes_ = sum(b for _, _, b in medidas)
    titulo = (jobs[0].get("titulo") if jobs else "") or (ands[0].get("titulo") if ands else "") or slug
    if medir:
        # `itens`: peça por peça (tipo, caminho, bytes), pro painel "o que vai pra Lixeira" (espaco.previa)
        return {"bytes": bytes_, "mb": round(bytes_ / 1e6, 1), "titulo": titulo, "slug": slug, "cliente": cli, "modelo": modelo,
                "pecas": [], "resumo": _resumo(pecas), "avisos": avisos, "pasta": "", "video": "", "referencia": None,
                "itens": [{"tipo": t, "caminho": _rel(p), "bytes": b} for t, p, b in medidas]}
    feito = []
    for tipo, p in pecas:
        if tipo == "andamento":
            _and.remover(p.parent.name, p.stem)
        feito.append({"tipo": tipo, "caminho": _rel(p)})
    movidos = [p for tipo, p in pecas if tipo != "andamento"]
    lixo = espaco.para_lixeira_mac(movidos, f"{titulo}")       # recuperável pelo Finder até a Lixeira ser esvaziada
    base = dict(it) if it else {"caminho": "", "pasta": "", "video": "", "cliente": cli, "modelo": modelo, "slug": slug,
                                "referencia": None, "folha": ""}
    base.update(bytes=bytes_, mb=round(bytes_ / 1e6, 1), pecas=feito, resumo=_resumo(pecas), avisos=avisos,
                titulo=titulo, lixeira_mac=lixo["pasta"], lixeira_nome=lixo["nome"],
                exportado=next((j["pasta_mac"] for j in jobs if j.get("pasta_mac")), ""))
    append_jsonl(_apagados(), {"quando": agora(), "cliente": cli, "modelo": modelo, "slug": slug, "pasta": base["pasta"],
                               "video": base["video"], "mb": base["mb"], "referencia": base["referencia"] is not None,
                               "pecas": [f["caminho"] for f in feito], "avisos": avisos})
    return base


def apagar(caminhos: list[str], confirmar: bool = False, medir: bool = False) -> dict:
    """Apaga cada saída E tudo que a gente fez pra ela (veja _apagar_alvo). Mais de um caminho = lote: referência é pulada
    sempre. Um só: referência só sai com confirmar=True. Devolve {"apagados": [...], "recusados": [{"caminho", "motivo"}], "mb"}."""
    caminhos = [c for c in dict.fromkeys(caminhos or []) if str(c).strip()]
    lote = len(caminhos) > 1
    apagados, recusados = [], []
    for c in caminhos:
        try:
            it = item(c)
            apagados.append(_apagar_alvo(it["cliente"], it["slug"], it["modelo"], it, lote, confirmar, medir))
        except ValueError as e:
            recusados.append({"caminho": str(c), "motivo": str(e)})
    return {"apagados": apagados, "recusados": recusados, "mb": total(apagados)}


def apagar_video(cli: str, slug: str, lote: bool = False, confirmar: bool = False, medir: bool = False) -> dict:
    """O mesmo caminho único, pelo nome do vídeo (cliente + slug), pra quem parte do projeto ou do Em andamento. Acha a saída
    pelo job ou pelo registro; sem saída ainda, apaga o que existir (projeto, rascunhos, registro)."""
    jobs = _jobs_do_video(cli, slug, "", None)
    ands = _andamentos(cli, {slug}, None)
    if not jobs and not ands:
        return {"apagados": [], "recusados": [{"caminho": f"{cli}/{slug}", "motivo": "Esse vídeo já não existe."}], "mb": 0}
    modelo = next((j.get("modelo") for j in jobs if j.get("modelo")), "")
    it = None
    cands = [j.get("saida") for j in jobs] + [x for d in ands for x in (d.get("pasta"), d.get("video"))]
    for c in cands:
        if not c:
            continue
        try:
            it = item(c)
            break
        except ValueError:
            continue
    if it is None and modelo:     # sem .mp4 nem pasta ainda: a pasta <slug>/ pode existir mesmo assim
        for q in (_raiz() / "clientes" / cli).glob(f"*Content/output/{modelo}/{slug}"):
            try:
                it = item(q)
                break
            except ValueError:
                continue
    if it:
        modelo = it["modelo"] or modelo
    try:
        r = _apagar_alvo(cli, it["slug"] if it else slug, modelo, it, lote, confirmar, medir)
        return {"apagados": [r], "recusados": [], "mb": total([r])}
    except ValueError as e:
        return {"apagados": [], "recusados": [{"caminho": f"{cli}/{slug}", "motivo": str(e)}], "mb": 0}


def mensagem(r: dict) -> str:
    """O que mostrar na tela depois de apagar: o que saiu, quanto liberou, o que ficou."""
    partes = []
    for a in r["apagados"]:
        partes.append(f"“{a.get('titulo') or a['slug']}”: {a['resumo']}")
    if not partes:
        return ""
    onde = next((a["lixeira_nome"] for a in r["apagados"] if a.get("lixeira_nome")), "")
    return (f"✓ Apagado: {'; '.join(partes)}. {r['mb']} MB foram pra Lixeira do Mac"
            + (f" (pasta “{onde}”): dá pra recuperar pelo Finder, e o espaço volta quando você esvaziar a Lixeira. " if onde else ". ") + FICA)


def limpar_pastas_vazias(dry_run: bool = True) -> list[str]:
    """Diretórios TOTALMENTE vazios dentro de clientes/*/*Content/output/ (de baixo pra cima, nunca arquivo, nunca a própria
    output/ nem as outras 4 pastas do padrão do cliente: entrada, material, modelos, transcricoes). dry_run=True só lista; False remove. Devolve os caminhos relativos à raiz, na ordem em que saem."""
    base = _raiz()
    achadas: list[str] = []
    for saida in sorted((base / "clientes").glob("*/*Content/output")):
        if saida.is_symlink() or not saida.is_dir():
            continue
        # filhos antes dos pais; uma pasta que só tinha vazias vira vazia ao sair (conta no dry_run também)
        for pasta in sorted((p for p in saida.rglob("*") if p.is_dir() and not p.is_symlink()),
                            key=lambda p: len(p.parts), reverse=True):
            if pasta.parent.name.endswith("Content"):   # as 5 pastas padrão do cliente nunca saem, mesmo vazias
                continue
            try:
                if any(not (q.is_dir() and not q.is_symlink() and _rel(q) in achadas) for q in pasta.iterdir()):
                    continue
                conferir_pasta_vazia(pasta)
            except (ValueError, OSError):
                continue
            achadas.append(_rel(pasta))
            if not dry_run:
                pasta.rmdir()
    return achadas


def conferir_pasta_vazia(pasta: Path) -> Path:
    """Mesma trava do 'conferir', mas pra uma pasta qualquer abaixo de output/: sem '..', sem link, só dentro de
    clientes/<Nome>/<x>Content/output/<algo>/ (a própria output/ nunca)."""
    p = Path(os.path.abspath(pasta))
    if ".." in Path(str(pasta)).parts or p.is_symlink() or p.resolve() != p:
        raise ValueError("Caminho inválido.")
    try:
        partes = p.relative_to(_raiz() / "clientes").parts
    except ValueError:
        raise ValueError("Fora da pasta output dos clientes.") from None
    if len(partes) < 4 or not partes[1].endswith("Content") or partes[2] != "output":
        raise ValueError("Fora da pasta output dos clientes.")
    return p


def guardar_referencia(caminho: str, formato: str, motivo: str = "") -> dict:
    """Marca a saída como referência (REFERENCIA.json na pasta) e passa o vídeo pelo mesmo caminho do
    'formatos.py referencia' (vira exemplo do formato). Vídeo solto sem pasta ganha a pasta <slug>/ só pro REFERENCIA.json."""
    it = item(caminho)
    if not it["video"]:
        raise ValueError("Esse vídeo ainda não tem o arquivo final (.mp4). Termine antes de guardar.")
    ex = _formatos.referencia(formato, _raiz() / it["video"], legenda=(motivo or "").strip() or f"{it['cliente']} · {it['slug']}")
    pasta = _raiz() / (it["pasta"] or str(Path(it["video"]).with_suffix("")))
    pasta.mkdir(exist_ok=True)
    dados = {"formato": formato, "motivo": (motivo or "").strip(), "quando": agora(), "video": it["video"],
             "exemplo": f"formatos/{formato}/{ex.get('arquivo', '')}"}
    gravar_json(pasta / REF, dados)
    return {**item(_rel(pasta)), "exemplo": ex}


def formato_sugerido(modelo: str) -> str:
    """O formato de um modelo (dialogo-3d → dialogo-3d; dividido-mascara → fala-com-cenas)."""
    if _formatos.carregar(modelo):
        return modelo
    f = _formatos.de_modelo(modelo) if modelo else None
    return (f or {}).get("slug", "")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "vazias":
        achadas = limpar_pastas_vazias(dry_run=True)
        print("\n".join(achadas) + f"\n{len(achadas)} pastas vazias (só listei; nada foi removido)")
    elif len(sys.argv) > 1 and sys.argv[1] == "listar":
        itens = listar(sys.argv[2] if len(sys.argv) > 2 else "")
        for i in itens:
            print(f"{i['mb']:>8} MB  {i['data']}  {'REF ' if i['referencia'] is not None else '    '}{i['caminho']}")
        print(f"{len(itens)} saídas · {total(itens)} MB")
    else:
        print(json.dumps({"uso": "saidas.py listar [Cliente]"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
