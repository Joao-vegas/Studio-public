#!/usr/bin/env python3
"""
acervo — biblioteca COMPARTILHADA de b-roll (acervo/itens/), usada por qualquer cliente.

Cada item = pasta acervo/itens/<slug>/ com:
    clip.<ext>   o vídeo/imagem
    thumb.jpg    frame de capa
    meta.json    título, tags, fonte (url), autor, licença/evidência, checklist de verificação,
                 onde já foi usado (cliente/modelo/job)

CLI:
    acervo.py add <arquivo> --titulo "..." --tags "a,b" [--fonte URL] [--autor X] [--licenca "..."]
    acervo.py url <url> --titulo "..." --tags "a,b" [--secao 30-45]
    acervo.py list [termo]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import (ACERVO, VIDEO_EXTS, IMAGEM_EXTS, ensure, ffprobe, hoje, agora, ler_json,
                    gravar_json, make_slug, now_slug, thumb, rel)
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
TIPOS = [("video", "Vídeos"), ("imagem", "Fotos / prints"), ("musica", "Músicas"), ("sfx", "Efeitos sonoros")]
# Música e efeito sonoro não são a mesma gaveta: um é cama que roda o vídeo todo, o outro é um
# estalo de 0,3s. Procurar "tensão" e receber whoosh no meio é o que atrapalhava.
SFX_PALAVRAS = ("sfx", "click", "clique", "whoosh", "swoosh", "boom", "impact", "impacto", "riser",
                "screech", "switch", "pop", "ding", "swipe", "transicao", "transition", "hit",
                "stinger", "beep", "cash", "money", "notification", "alerta")
SFX_DURACAO = 6.0   # áudio curto assim é efeito, não cama

CHECKLIST = [
    ("casa_com_a_fala", "Casa com a fala / ideia que ilustra"),
    ("sem_rosto_indevido", "Sem rosto de pessoa quando o conteúdo é de marca/produto"),
    ("sem_watermark", "Sem marca d'água / vinheta de canal"),
    ("sem_legenda_queimada", "Sem legenda queimada (ou já cortada)"),
    ("qualidade_ok", "Qualidade ≥ 720p, sem serrilhado"),
    ("dinamico", "Tem movimento / dinamismo (não é frame parado)"),
]


def _tags(txt) -> list[str]:
    if isinstance(txt, list):
        return [t.strip().lower() for t in txt if t.strip()]
    return [t.strip().lower() for t in str(txt or "").replace(";", ",").split(",") if t.strip()]


def _tipo(ext: str, caminho: Path | None = None, duracao: float | None = None) -> str:
    """Áudio vira `musica` ou `sfx`: decide pela duração e, se não souber, pelo nome do arquivo."""
    if ext not in AUDIO_EXTS:
        return "imagem" if ext in IMAGEM_EXTS else "video"
    nome = str(Path(caminho).as_posix()).lower() if caminho else ""
    if duracao is None and caminho and Path(caminho).is_file():
        duracao = (ffprobe(Path(caminho)) or {}).get("duracao")
    if duracao is not None and duracao > 0:
        return "sfx" if duracao <= SFX_DURACAO else "musica"
    return "sfx" if any(w in nome for w in SFX_PALAVRAS) else "musica"


def eh_audio(tipo: str) -> bool:
    return tipo in ("musica", "sfx", "audio")


def reclassificar_audios() -> dict:
    """Passa o acervo antigo (tudo era `audio`) pra `musica`/`sfx`, gravando no meta.json."""
    mudou = {"musica": [], "sfx": []}
    for d in sorted(ACERVO.iterdir()) if ACERVO.is_dir() else []:
        meta = ler_json(d / "meta.json")
        if not meta or not eh_audio(meta.get("tipo", "")):
            continue
        clip = next((p for p in d.iterdir() if p.stem == "clip"), None)
        if not clip:
            continue
        novo = _tipo(clip.suffix.lower(), clip, (meta.get("media") or {}).get("duracao"))
        if novo != meta.get("tipo"):
            meta["tipo"] = novo
            gravar_json(d / "meta.json", meta)
            mudou[novo].append(d.name)
    return mudou


def auto_de(meta: dict) -> dict:
    """Como o item SOA, derivado da análise técnica (sem IA). Calculado na hora se ainda não tem."""
    if meta.get("auto"):
        return meta["auto"]
    if not meta.get("analise"):
        return {}
    try:
        import musica as _mus
        return _mus.caracteristicas(meta["analise"])
    except Exception:
        return {}


def organizar(aplicar: bool = True) -> dict:
    """Passa o acervo a limpo: grava `auto` em cada item e tira as tags que não ajudam a escolher.

    Tag de procedência (nome do cliente, nome do modelo, "musica"/"sfx") virou ruído: são 58 tags
    distintas e as mais comuns só dizem de onde o arquivo veio — o que o campo `fonte` já guarda, e
    o tipo virou aba. Ficam as tags que descrevem o SOM.
    """
    import musica as _mus
    from _comum import clientes as _clientes
    procedencia = {"musica", "sfx", "audio", "video", "imagem"}
    for c in _clientes():
        procedencia.add(c["nome"].lower())
        procedencia.update(m.lower() for m in c["modelos"])
    try:                                   # modelo removido continua sendo procedência, não som
        from _comum import lixeira_listar
        for x in lixeira_listar():
            for chave in ("modelo", "cliente"):
                if x.get(chave):
                    procedencia.add(str(x[chave]).lower())
            procedencia.update(str(m).lower() for m in (x.get("modelos") or []))
    except Exception:
        pass
    mudou = {"auto": 0, "tags_removidas": 0, "itens": 0}
    for d in sorted(ACERVO.iterdir()) if ACERVO.is_dir() else []:
        meta = ler_json(d / "meta.json")
        if not meta:
            continue
        antes_tags = list(meta.get("tags", []))
        auto = _mus.caracteristicas(meta.get("analise") or {}) if meta.get("analise") else {}
        limpas = [t for t in antes_tags if t.lower() not in procedencia]
        if aplicar and (auto != meta.get("auto") or limpas != antes_tags):
            if auto:
                meta["auto"] = auto
            meta["tags"] = limpas
            gravar_json(d / "meta.json", meta)
            mudou["itens"] += 1
        mudou["auto"] += 1 if auto else 0
        mudou["tags_removidas"] += len(antes_tags) - len(limpas)
    return mudou


def facetas(tipo: str = "") -> dict:
    """Quantos itens em cada jeito de soar — é por aqui que ele filtra, não pela nuvem de tags."""
    import collections
    base = listar(tipo=tipo)
    out = {}
    for campo in ("clima", "andamento", "brilho", "formato"):
        c = collections.Counter((i.get("auto") or {}).get(campo) for i in base)
        c.pop(None, None)
        if c:
            out[campo] = c.most_common()
    return out


def resumo_curto(meta: dict, limite: int = 190) -> str:
    """Uma linha pro card. A descrição da IA passa de 1.500 caracteres — no card ela vira parede.

    Prefere a prosa (que diz pra que serve); sem ela, a primeira linha da análise técnica, que já
    entrega duração, BPM e loudness. O resto fica dobrado em "ler a análise completa".
    """
    texto = (meta.get("descricao") or "").strip()
    if not texto and meta.get("resumo_audio"):
        texto = (meta["resumo_audio"].strip().splitlines() or [""])[0]
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    if ponto > limite * 0.5:
        return corte[:ponto + 1]
    espaco = corte.rfind(" ")
    return (corte[:espaco] if espaco > 0 else corte).rstrip(" ,;:—-") + "…"


def listar(termo: str = "", tag: str = "", tipo: str = "", soa: str = "") -> list[dict]:
    itens = []
    if not ACERVO.is_dir():
        return itens
    termo = (termo or "").lower().strip()
    tag = (tag or "").lower().strip()
    for d in sorted(ACERVO.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = ler_json(d / "meta.json")
        if not d.is_dir() or not meta:
            continue
        meta["slug"] = d.name
        meta["pasta"] = d
        clip = next((p for p in d.iterdir() if p.stem == "clip"), None)
        meta["clip"] = clip
        meta["clip_rel"] = rel(clip) if clip else None
        meta["thumb_rel"] = rel(d / "thumb.jpg") if (d / "thumb.jpg").exists() else (rel(d / "thumb.png") if (d / "thumb.png").exists() else None)
        meta["e_imagem"] = bool(clip and clip.suffix.lower() in IMAGEM_EXTS)
        meta["thumb_curva"] = rel(d / "curva.png") if (d / "curva.png").exists() else None
        meta["descrevendo"] = bool(meta.get("descrevendo")) and _descrevendo(d.name)
        meta["auto"] = auto_de(meta)
        meta["como_soa"] = ""
        if meta["auto"]:
            try:
                import musica as _mus
                meta["como_soa"] = _mus.como_soa(meta["auto"])
            except Exception:
                pass
        meta["resumo_curto"] = resumo_curto(meta)
        meta["descricao_longa"] = bool(meta.get("descricao") and len(meta["descricao"]) > 190)
        meta["tipo"] = meta.get("tipo") or (_tipo(clip.suffix.lower(), clip,
                                            (meta.get("media") or {}).get("duracao")) if clip else "video")
        if meta["tipo"] == "audio":            # item antigo, de antes de separar música de efeito
            meta["tipo"] = _tipo(clip.suffix.lower() if clip else ".mp3", clip,
                                 (meta.get("media") or {}).get("duracao"))
        if tipo and meta["tipo"] != tipo and not (tipo == "audio" and eh_audio(meta["tipo"])):
            continue
        blob = " ".join([meta.get("titulo", ""), " ".join(meta.get("tags", [])), meta.get("fonte", "") or "",
                         meta.get("autor", "") or "", meta.get("observacao", "") or "", meta.get("descricao", "") or ""]).lower()
        if termo and termo not in blob:
            continue
        if tag and tag not in meta.get("tags", []):
            continue
        if soa and soa not in (meta.get("auto") or {}).values():
            continue
        itens.append(meta)
    return itens


def indice_hashes() -> dict:
    """{sha256 do arquivo: slug} — pra saber se algo já está no acervo sem depender do nome."""
    from _comum import sha_arquivo
    out = {}
    for it in listar():
        clip = it.get("clip")
        if clip and Path(clip).is_file():
            try:
                out[sha_arquivo(clip)] = it["slug"]
            except OSError:
                pass
    return out


def item(slug: str) -> dict | None:
    for it in listar():
        if it["slug"] == slug:
            return it
    return None


def todas_tags() -> list[tuple[str, int]]:
    c: dict = {}
    for it in listar():
        for t in it.get("tags", []):
            c[t] = c.get(t, 0) + 1
    return sorted(c.items(), key=lambda x: (-x[1], x[0]))


def adicionar_arquivo(origem: Path, titulo: str, tags="", fonte: str = "", autor: str = "",
                      licenca: str = "", observacao: str = "", origem_tipo: str = "manual",
                      checklist: dict | None = None, mover: bool = False, extra: dict | None = None,
                      descrever_auto: bool = True) -> dict:
    origem = Path(origem)
    if not origem.exists():
        raise FileNotFoundError(origem)
    ext = origem.suffix.lower()
    if ext not in VIDEO_EXTS | IMAGEM_EXTS | AUDIO_EXTS:
        raise ValueError(f"extensão não suportada: {ext}")
    base = make_slug(titulo or origem.stem) or now_slug()
    slug, n = base, 2
    while (ACERVO / slug).exists():
        slug = f"{base}-{n}"; n += 1
    pasta = ensure(ACERVO / slug)
    destino = pasta / f"clip{ext}"
    (shutil.move if mover else _clonar)(str(origem), str(destino))
    info = ffprobe(destino) if ext in VIDEO_EXTS | AUDIO_EXTS else {}
    tipo_item = _tipo(ext, origem, (info or {}).get("duracao"))
    if ext in VIDEO_EXTS:
        thumb(destino, pasta / "thumb.jpg", t=min(1.0, (info.get("duracao") or 2) / 2))
    elif ext in AUDIO_EXTS:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(destino), "-filter_complex",
                        "showwavespic=s=480x120:colors=#B4232C", "-frames:v", "1", str(pasta / "thumb.png")], capture_output=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(destino), "-vf", "scale=480:-2",
                        str(pasta / "thumb.jpg")], capture_output=True)
    meta = {
        "titulo": titulo or origem.stem, "tags": _tags(tags), "fonte": fonte or "", "autor": autor or "",
        "licenca": licenca or "", "observacao": observacao or "", "origem": origem_tipo,
        "arquivo_original": origem.name, "adicionado_em": agora(), "media": info, "tipo": tipo_item,
        "checklist": checklist or {}, "usos": [],
    }
    if eh_audio(tipo_item) and not (extra or {}).get("analise"):
        try:
            import musica as _mus
            meta["analise"] = _mus.analisar(destino, pasta)
            meta["resumo_audio"] = _mus.resumo(meta["analise"])
        except Exception as e:
            meta["analise_erro"] = str(e)[:200]
    if extra:
        meta.update(extra)
    gravar_json(pasta / "meta.json", meta)
    meta["slug"] = slug
    if descrever_auto:
        try:
            descrever(slug)
        except Exception:
            pass
    return meta


def adicionar_url(url: str, titulo: str, tags="", secao: str = "", autor: str = "", licenca: str = "",
                  observacao: str = "", so_audio: bool = False) -> dict:
    """Baixa com yt-dlp (trecho opcional 'ini-fim' em segundos) e guarda no acervo.
    so_audio=True baixa só o MP3 (música) e roda a análise de áudio."""
    if so_audio:
        import musica as _mus
        tmpd = ensure(ACERVO.parent / ".tmp" / (make_slug(titulo) or now_slug()))
        mp3, info = _mus.baixar(url, tmpd)
        if not mp3:
            raise RuntimeError("não consegui baixar o áudio")
        return adicionar_arquivo(mp3, titulo or info.get("titulo") or mp3.stem, tags, fonte=info.get("url") or url,
                                 autor=info.get("canal", "") or autor, licenca=licenca,
                                 observacao=observacao, origem_tipo="youtube-audio", mover=True,
                                 extra={"youtube": info})
    tmp = ensure(ACERVO.parent / ".tmp")
    nome = make_slug(titulo) or now_slug()
    saida = tmp / f"{nome}.%(ext)s"
    cmd = ["yt-dlp", "--no-update", "--no-playlist", "-f", "bv*[height<=1080]+ba/b[height<=1080]",
           "--merge-output-format", "mp4", "-o", str(saida)]
    if secao:
        cmd += ["--download-sections", f"*{secao}", "--force-keyframes-at-cuts"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    arqs = sorted(tmp.glob(f"{nome}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if r.returncode != 0 or not arqs:
        raise RuntimeError((r.stderr or r.stdout)[-1500:])
    return adicionar_arquivo(arqs[0], titulo, tags, fonte=url, autor=autor, licenca=licenca,
                             observacao=observacao + (f" (trecho {secao})" if secao else ""),
                             origem_tipo="yt-dlp", mover=True)


def atualizar(slug: str, campos: dict) -> dict | None:
    p = ACERVO / slug / "meta.json"
    meta = ler_json(p)
    if not meta:
        return None
    if "tags" in campos:
        campos["tags"] = _tags(campos["tags"])
    meta.update({k: v for k, v in campos.items() if v is not None})
    gravar_json(p, meta)
    return meta


def registrar_uso(slug: str, cliente: str, modelo: str, job: str) -> None:
    p = ACERVO / slug / "meta.json"
    meta = ler_json(p)
    if not meta:
        return
    if not any(u.get('cliente')==cliente and u.get('modelo')==modelo and u.get('job')==job for u in meta.get('usos',[])):
        meta.setdefault("usos", []).append({"cliente": cliente, "modelo": modelo, "job": job, "em": hoje()})
    gravar_json(p, meta)


# ── favoritos de música e efeito (marca no meta.json; o indice.json guarda só o resumo) ──

def _reescrever_favoritos() -> None:
    from semantica import INDICE
    resumo = {"musica": [], "sfx": []}
    for it in listar():
        if (it.get("favorito") or {}).get("geral") or (it.get("favorito") or {}).get("clientes"):
            resumo["sfx" if it.get("tipo") == "sfx" else "musica"].append(it["slug"])
    dados = ler_json(INDICE, {}) or {}
    dados["favoritos"] = resumo
    gravar_json(INDICE, dados)


def favoritar(slug: str, cliente: str | None = None, ligar: bool = True) -> dict | None:
    """Liga/desliga o ♥ de um item. Sem cliente = favorito geral; com cliente = só desse cliente."""
    meta = ler_json(ACERVO / slug / "meta.json")
    if not meta:
        return None
    fav = dict(meta.get("favorito") or {"geral": False, "clientes": []})
    fav.setdefault("clientes", [])
    if cliente:
        fav["clientes"] = [c for c in fav["clientes"] if c != cliente] + ([cliente] if ligar else [])
    else:
        fav["geral"] = bool(ligar)
    fav["em"] = agora()
    atualizar(slug, {"favorito": fav})
    _reescrever_favoritos()
    return fav


def favorito_de(item: dict, cliente: str | None = None) -> bool:
    f = item.get("favorito") or {}
    return bool(f.get("geral") or (cliente and cliente in (f.get("clientes") or [])))


def favoritos(tipo: str = "musica", cliente: str | None = None) -> list[dict]:
    """Itens favoritos (gerais e, se `cliente`, também os dele). tipo: musica | sfx."""
    return [it for it in listar(tipo="sfx" if tipo == "sfx" else "musica") if favorito_de(it, cliente)]


def favoritar_arquivo(arquivo: Path, titulo: str, tipo: str = "musica", cliente: str | None = None, ligar: bool = True,
                      fonte: str = "") -> dict | None:
    """♥ numa faixa que ainda não está no acervo: guarda (sem duplicar, por hash) e marca."""
    arquivo = Path(arquivo)
    from _comum import sha_arquivo
    slug = indice_hashes().get(sha_arquivo(arquivo))
    if not slug:
        slug = adicionar_arquivo(arquivo, titulo, tags=["favorito", tipo], fonte=fonte, origem_tipo="favorito",
                                 descrever_auto=False)["slug"]
    return {"slug": slug, "favorito": favoritar(slug, cliente, ligar)}


def remover(slug: str, de_vez: bool = False) -> bool:
    """Tira do acervo. Por padrão vai pra lixeira do Estúdio — `de_vez` apaga sem volta."""
    from _comum import lixeira_guardar
    p = ACERVO / slug
    if not (p.is_dir() and p.parent == ACERVO):
        return False
    if de_vez:
        shutil.rmtree(p)
        return True
    meta = ler_json(p / "meta.json", {}) or {}
    lixeira_guardar({"item": p}, {"tipo": "acervo", "rotulo": slug, "cliente": "(acervo)",
                                  "modelo": "acervo", "item": slug,
                                  "titulo": meta.get("titulo") or slug, "tipo_item": meta.get("tipo"),
                                  "motivo": "removido do acervo"})
    return True


def restaurar(ident: str) -> dict:
    """Devolve pro acervo um item que estava na lixeira."""
    from _comum import ensure as _ensure, lixeira_item
    d = lixeira_item(ident)
    info = ler_json(d / "info.json", {}) or {}
    destino = ACERVO / info["item"]
    if destino.exists():
        raise ValueError(f"já existe {info['item']} no acervo")
    _ensure(ACERVO)
    shutil.move(str(d / "item"), str(destino))
    shutil.rmtree(d, ignore_errors=True)
    return {"cliente": "(acervo)", "modelo": "acervo", "item": info["item"]}


def main():
    ap = argparse.ArgumentParser(description="Acervo compartilhado de b-roll")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("arquivo"); a.add_argument("--titulo", default="")
    a.add_argument("--tags", default=""); a.add_argument("--fonte", default=""); a.add_argument("--autor", default="")
    a.add_argument("--licenca", default=""); a.add_argument("--obs", default="")
    u = sub.add_parser("url"); u.add_argument("url"); u.add_argument("--titulo", required=True)
    u.add_argument("--tags", default=""); u.add_argument("--secao", default=""); u.add_argument("--autor", default="")
    u.add_argument("--licenca", default=""); u.add_argument("--obs", default="")
    l = sub.add_parser("list"); l.add_argument("termo", nargs="?", default="")
    args = ap.parse_args()
    if args.cmd == "add":
        m = adicionar_arquivo(Path(args.arquivo), args.titulo, args.tags, args.fonte, args.autor, args.licenca, args.obs)
        print(json.dumps({"slug": m["slug"], "pasta": str(ACERVO / m["slug"])}, ensure_ascii=False))
    elif args.cmd == "url":
        m = adicionar_url(args.url, args.titulo, args.tags, args.secao, args.autor, args.licenca, args.obs)
        print(json.dumps({"slug": m["slug"], "pasta": str(ACERVO / m["slug"])}, ensure_ascii=False))
    else:
        for it in listar(args.termo):
            print(f"{it['slug']:40s} {','.join(it.get('tags', [])):40s} {it.get('media', {}).get('duracao') or ''}s  {it.get('clip_rel')}")


if __name__ == "__main__":
    main()


# ═════════════ DESCRIÇÃO AUTOMÁTICA: título, tags, descrição e trecho ═════════════
# O João não quer preencher formulário: joga o arquivo ou o link e o resto vem pronto.
# Evidência por tipo: vídeo → frames; música → análise + curva/espectro; imagem → a própria.

def _evidencia(pasta: Path, meta: dict) -> list[str]:
    """Gera (e lista) os arquivos que a IA precisa OLHAR pra descrever o item."""
    clip = next((p for p in pasta.iterdir() if p.stem == "clip"), None)
    if not clip:
        return []
    tipo = meta.get("tipo") or _tipo(clip.suffix.lower())
    if tipo == "imagem":
        return [str(clip)]
    if eh_audio(tipo):
        return [str(pasta / n) for n in ("curva.png", "espectro.png", "waveform.png") if (pasta / n).exists()]
    dur = (meta.get("media") or {}).get("duracao") or ffprobe(clip).get("duracao") or 4
    saida = ensure(pasta / "frames")
    fs = []
    for i in range(6):
        t = max(0.2, dur * (i + 0.5) / 6)
        f = saida / f"f{i}.jpg"
        if not f.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(t), "-i", str(clip),
                            "-frames:v", "1", "-vf", "scale=640:-2", str(f)], capture_output=True, timeout=60)
        if f.exists():
            fs.append(str(f))
    return fs


def prompt_descrever(slug: str) -> str:
    pasta = ACERVO / slug
    meta = ler_json(pasta / "meta.json", {}) or {}
    ev = _evidencia(pasta, meta)
    tipo = meta.get("tipo", "video")
    contexto = []
    if meta.get("fonte"): contexto.append(f"fonte: {meta['fonte']}")
    if meta.get("autor"): contexto.append(f"autor/canal: {meta['autor']}")
    if meta.get("arquivo_original"): contexto.append(f"nome do arquivo: {meta['arquivo_original']}")
    if meta.get("observacao"): contexto.append(f"observação: {meta['observacao']}")
    y = meta.get("youtube") or {}
    if y.get("titulo"): contexto.append(f"título no YouTube: {y['titulo']}")
    if y.get("descricao"): contexto.append(f"descrição do YouTube: {y['descricao'][:600]}")
    if y.get("tags"): contexto.append(f"tags do YouTube: {', '.join(y['tags'][:15])}")
    a = meta.get("analise") or {}
    if a:
        contexto.append(f"medições: {a.get('bpm')} BPM, {a.get('lufs')} LUFS, {a.get('duracao_s')}s, "
                        f"timbre {a.get('bandas_geral')}, trechos detectados: "
                        + "; ".join(f"{t['tipo']} {t['inicio_s']}-{t['fim_s']}s" for t in a.get("trechos_usaveis", [])))
    olhar = ("Leia (ferramenta Read) CADA um destes arquivos antes de escrever:\n" + "\n".join("  " + e for e in ev)) if ev else "(sem evidência visual)"
    extra_musica = """
  "trecho_sugerido": {"inicio_s": 0, "fim_s": 0, "tipo": "cama|gancho|virada|pico|final", "motivo": "por que este trecho"},
  "clima": "duas ou três palavras: tenso, esperançoso, sombrio, corporativo, épico…",
  "papel": "cama (roda o vídeo todo) ou efeito pontual (marca um corte, um card, uma virada)",""" if eh_audio(tipo) else ""
    return f"""Você está no repositório producao-reels. DESCREVA um item do acervo de b-roll pra ele ser
encontrado depois por qualquer cliente (Joao, Cliente8, Cliente4, Cliente3, Cliente7, Cliente2…).

ITEM: acervo/itens/{slug}/  (tipo: {tipo})
CONTEXTO CONHECIDO:
{chr(10).join('  ' + c for c in contexto) or '  (nenhum)'}

{olhar}

O QUE FAZER:
1. Olhe a evidência de verdade. Para VÍDEO, descreva o que aparece nos frames (cena, quem/o quê, ação,
   enquadramento, se tem rosto, se tem texto/marca d'água na tela). Para MÚSICA, leia a curva de energia e
   o espectrograma e cruze com as medições. Para IMAGEM, o que ela mostra.
2. Reescreva acervo/itens/{slug}/meta.json MANTENDO todos os campos que já existem (fonte, autor, licenca,
   analise, usos, origem, media, arquivo_original…) e preenchendo/corrigindo:
{{
  "titulo": "curto, concreto, em português — o que a pessoa veria na lista (ex.: 'Relógio de bolso girando, close macro'). Nada de nome de arquivo nem id.",
  "tags": ["6 a 12 tags minúsculas, sem acento, uma palavra cada: tema, objeto, lugar, sensação, tipo de cena, nicho"],
  "descricao": "2 a 4 frases: o que aparece, que ritmo/movimento tem, PRA QUE TIPO DE FALA serve num reel, e o que evitar (ex.: 'depois de 6s entra o logo do canal').",{extra_musica}
  "checklist": {{"casa_com_a_fala": null, "sem_rosto_indevido": true/false, "sem_watermark": true/false, "sem_legenda_queimada": true/false, "qualidade_ok": true/false, "dinamico": true/false}},
  "descrito_em": "{hoje()}"
}}
   No checklist responda pelo que você VIU (sem_rosto_indevido = não tem rosto de pessoa; deixe
   casa_com_a_fala como null, isso depende do vídeo em que for usado). Remova o campo "descrevendo".
3. JSON válido, UTF-8, sem inventar o que não viu. Não mexa em nenhum outro arquivo. Sem pedir confirmação.
"""


def descrever(slug: str) -> bool:
    """Dispara a descrição automática em processo independente (motor ia.py: Claude ou GPT)."""
    pasta = ACERVO / slug
    if not (pasta / "meta.json").exists():
        return False
    if _descrevendo(slug):
        return True
    meta = ler_json(pasta / "meta.json", {}) or {}
    meta["descrevendo"] = True
    gravar_json(pasta / "meta.json", meta)
    pf = pasta / ".prompt-descrever.txt"
    pf.write_text(prompt_descrever(slug), encoding="utf-8")
    import sys as _sys
    subprocess.Popen([_sys.executable, str(Path(__file__).with_name("ia.py")), str(pf), str(pasta)],
                     cwd=str(ACERVO.parent.parent), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return True


def _descrevendo(slug: str) -> bool:
    pf = ACERVO / slug / ".runner.pid"
    try:
        import os as _os
        _os.kill(int(pf.read_text().strip()), 0)
        return True
    except Exception:
        return False
