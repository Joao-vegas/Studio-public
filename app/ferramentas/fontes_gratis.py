#!/usr/bin/env python3
"""fontes_gratis: fontes GRÁTIS de imagem, vídeo e ícone com licença clara, ao lado do get-brolls (que fica do jeito que o autor
entrega: o clone dele só atualiza por git pull, então fonte nova entra aqui, no Estúdio).

  python3 app/ferramentas/fontes_gratis.py imagem "<consulta em inglês>" --saida <pasta> [--fontes commons,openverse,nasa,archive,pexels,pixabay] [--n 4]
      baixa as candidatas (miniatura grande), grava/junta `origem.json` (mesmo formato do commons.py: consulta → lista com
      titulo, arquivo, pagina, licenca, autor, w, h, fonte) e a folha `folha-<consulta>.jpg` pra OLHAR antes de usar.
  python3 app/ferramentas/fontes_gratis.py video "<consulta>" [--fontes archive,commons,pexels,pixabay] [--n 6]
      lista candidatas (JSON): titulo, pagina, licenca, duracao, arquivo (link direto do vídeo).
  python3 app/ferramentas/fontes_gratis.py cortar <link-direto> <ini> <fim> <saida.mp4> [--vertical]
      baixa só o trecho (ffmpeg com range), 30 fps; --vertical recorta 9:16 1080x1920.
  python3 app/ferramentas/fontes_gratis.py icone "<consulta>" --saida <pasta> [--n 6] [--cor "#ffffff"]
      SVG do Iconify (inclui os animados line-md) com a licença da coleção; origem.json junto.
  python3 app/ferramentas/fontes_gratis.py fontes     # situação de cada fonte (chave, licença)

Licença: só entra o que o próprio site declara livre pra uso comercial (CC0, domínio público, CC BY, CC BY-SA, NASA, Pexels/
Pixabay License). Nada de ND/NC. Prints de notícia/estudo NÃO vêm daqui: ficam com a regra G25 (fonte confiável, nunca Wikipédia).
Sem chave: Commons, Openverse, NASA, Internet Archive, Iconify. Com a chave do app/.env: Pexels, Pixabay (stock: pessoa posando
é proibida no Editorial). Library of Congress testada em 29/10: bloqueada por Cloudflare, fora. Unsplash exige chave pessoal
(UNSPLASH_ACCESS_KEY), sem ela não entra.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

UA = "EstudioJoao/1.0 (seu-email@exemplo.com) fontes-gratis"
LIC_OK = ("cc0", "pdm", "by", "by-sa")            # Openverse: livres pra uso comercial com edição
SO_IMAGEM = ("commons", "openverse", "nasa", "archive", "pexels", "pixabay")
SO_VIDEO = ("archive", "commons", "nasa", "pexels", "pixabay")


def _get(url: str, timeout: int = 60, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def _json(url: str, timeout: int = 60, headers: dict | None = None) -> dict:
    return json.loads(_get(url, timeout, headers).decode("utf-8", "replace"))


def _chave(nome: str) -> str:
    try:
        import chaves
        return chaves.chave(nome) or ""
    except Exception:
        return ""


def _limpa(txt: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", txt or "")).strip()


def _item(fonte, titulo, pagina, arquivo, licenca, autor="", w=None, h=None, dur=None, thumb="", tipo="imagem") -> dict:
    return {"fonte": fonte, "titulo": _limpa(titulo)[:140], "pagina": pagina, "arquivo_url": arquivo, "thumb": thumb or arquivo,
            "licenca": licenca, "autor": _limpa(autor)[:120], "w": w, "h": h, "duracao": dur, "tipo": tipo}


# ───────────────────────── imagem ─────────────────────────

def img_commons(q: str, n: int) -> list[dict]:
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6,
         "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1400}
    d = _json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p))
    out = []
    for pg in sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
        ii = pg["imageinfo"][0]; m = ii.get("extmetadata", {})
        lic = (m.get("LicenseShortName") or {}).get("value", "")
        if re.search(r"\b(nc|nd)\b", lic.lower()):
            continue
        out.append(_item("commons", pg["title"].replace("File:", ""), ii.get("descriptionurl"), ii.get("url"), lic,
                         (m.get("Artist") or {}).get("value", ""), ii.get("width"), ii.get("height"), thumb=ii.get("thumburl")))
    return out


def img_openverse(q: str, n: int) -> list[dict]:
    p = {"q": q, "page_size": n, "license": ",".join(LIC_OK), "mature": "false", "extension": "jpg,png"}
    d = _json("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(p), timeout=75)
    out = []
    for r in d.get("results") or []:
        lic = f"{(r.get('license') or '').upper()} {r.get('license_version') or ''}".strip()
        out.append(_item("openverse/" + (r.get("source") or r.get("provider") or "?"), r.get("title") or "", r.get("foreign_landing_url"),
                         r.get("url"), lic, r.get("creator") or "", r.get("width"), r.get("height"), thumb=r.get("url")))
    return out


def _nasa_lista(q: str, n: int, media: str) -> list[dict]:
    d = _json("https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": q, "media_type": media, "page_size": n}))
    out = []
    for it in (d.get("collection") or {}).get("items", [])[:n]:
        dd = (it.get("data") or [{}])[0]
        nid = dd.get("nasa_id", "")
        pagina = f"https://images.nasa.gov/details/{urllib.parse.quote(nid)}"
        thumb = next((l["href"] for l in it.get("links", []) if l.get("render") == "image"), "")
        out.append({"id": nid, "titulo": dd.get("title", ""), "pagina": pagina, "autor": dd.get("photographer") or dd.get("secondary_creator") or dd.get("center") or "NASA",
                    "thumb": thumb, "manifesto": it.get("href")})
    return out


def img_nasa(q: str, n: int) -> list[dict]:
    out = []
    for r in _nasa_lista(q, n, "image"):
        orig = re.sub(r"~thumb\.jpg$", "~large.jpg", r["thumb"]) if r["thumb"] else ""
        out.append(_item("nasa", r["titulo"], r["pagina"], orig or r["thumb"], "NASA (domínio público, sem endosso)", r["autor"], thumb=r["thumb"]))
    return out


def _archive_docs(q: str, n: int, midia: str) -> list[dict]:
    """Só itens com licença declarada: domínio público / CC0 / CC BY / CC BY-SA (a busca do Archive não aceita wildcard
    composto, então pede `publicdomain` OU `licenses/by*` e o filtro fino é feito aqui)."""
    docs = []
    for lic in ("licenseurl:*publicdomain*", "licenseurl:*creativecommons.org*licenses*by*"):
        p = {"q": f"({q}) AND mediatype:{midia} AND {lic}", "fl[]": ["identifier", "title", "creator", "licenseurl", "year"],
             "rows": n * 3, "output": "json", "sort[]": "downloads desc"}
        try:
            docs += (_json("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(p, doseq=True)).get("response") or {}).get("docs", [])
        except Exception:
            pass
    ok = []
    for d in docs:
        u = d.get("licenseurl")
        u = u[0] if isinstance(u, list) and u else (u or "")
        if "publicdomain" in u or re.search(r"licenses/by(-sa)?/", u):
            ok.append(d)
    return ok[:n * 2]


def _lic_url(u) -> str:
    u = u[0] if isinstance(u, list) and u else (u or "")
    if "publicdomain/zero" in u:
        return "CC0"
    if "publicdomain" in u:
        return "Domínio público"
    m = re.search(r"licenses/([a-z\-]+)/([\d.]+)", u)
    return f"CC {m.group(1).upper()} {m.group(2)}" if m else u


def img_archive(q: str, n: int) -> list[dict]:
    out = []
    for doc in _archive_docs(q, n, "image"):
        ident = doc["identifier"]
        try:
            files = _json(f"https://archive.org/metadata/{ident}").get("files", [])
        except Exception:
            continue
        jpgs = [f for f in files if f.get("name", "").lower().endswith((".jpg", ".jpeg")) and "thumb" not in f.get("name", "").lower()
                and "_itemimage" not in f.get("name", "").lower()]
        jpg = max(jpgs, key=lambda f: int(f.get("size") or 0), default=None)
        if not jpg:
            continue
        url = f"https://archive.org/download/{ident}/{urllib.parse.quote(jpg['name'])}"
        out.append(_item("archive", doc.get("title", ident), f"https://archive.org/details/{ident}", url, _lic_url(doc.get("licenseurl")),
                         doc.get("creator", "") if isinstance(doc.get("creator"), str) else ", ".join(doc.get("creator") or [])))
    return out


def img_pexels(q: str, n: int) -> list[dict]:
    k = _chave("PEXELS_API_KEY")
    if not k:
        return []
    d = _json("https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": q, "per_page": n}), headers={"Authorization": k})
    return [_item("pexels", p.get("alt") or "foto Pexels", p.get("url"), p["src"]["large2x"], "Pexels License", p.get("photographer", ""),
                  p.get("width"), p.get("height"), thumb=p["src"]["large"]) for p in d.get("photos", [])]


def img_pixabay(q: str, n: int) -> list[dict]:
    k = _chave("PIXABAY_API_KEY")
    if not k:
        return []
    d = _json("https://pixabay.com/api/?" + urllib.parse.urlencode({"key": k, "q": q, "per_page": max(3, n), "image_type": "photo", "safesearch": "true"}))
    return [_item("pixabay", p.get("tags") or "foto Pixabay", p.get("pageURL"), p.get("largeImageURL"), "Pixabay License", p.get("user", ""),
                  p.get("imageWidth"), p.get("imageHeight"), thumb=p.get("webformatURL")) for p in d.get("hits", [])[:n]]


IMG = {"commons": img_commons, "openverse": img_openverse, "nasa": img_nasa, "archive": img_archive, "pexels": img_pexels, "pixabay": img_pixabay}


def buscar_imagens(q: str, fontes=SO_IMAGEM, n: int = 4) -> tuple[list[dict], dict]:
    """Todas as fontes em paralelo. Devolve (itens, erros por fonte); uma fonte que cai não derruba as outras."""
    itens, erros = [], {}
    with cf.ThreadPoolExecutor(len(fontes) or 1) as ex:
        fut = {f: ex.submit(IMG[f], q, n) for f in fontes if f in IMG}
        for f, fu in fut.items():
            try:
                itens += fu.result(timeout=120)
            except Exception as e:
                erros[f] = str(e)[:120]
    return itens, erros


def _slug(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")[:40] or "busca"


def baixar_imagens(q: str, saida: Path, fontes=SO_IMAGEM, n: int = 4) -> dict:
    saida.mkdir(parents=True, exist_ok=True)
    itens, erros = buscar_imagens(q, fontes, n)
    k = _slug(q)
    ok = []
    for i, it in enumerate(itens):
        ordem = [it["thumb"], it["arquivo_url"]] if it["fonte"] == "commons" else [it["arquivo_url"], it["thumb"]]   # Commons: original pode ter 40 MB
        for url in dict.fromkeys(ordem):
            if not url:
                continue
            try:
                dados = _get(url, 60)
                if len(dados) < 5000:
                    continue
                nome = f"{k}-{it['fonte'].split('/')[0]}-{i}.jpg"
                (saida / nome).write_bytes(dados)
                it["arquivo"] = nome
                ok.append(it)
                break
            except Exception:
                continue
    # tamanho real do que baixou (a folha e o upscale precisam)
    try:
        from PIL import Image
        for it in list(ok):
            with Image.open(saida / it["arquivo"]) as im:
                it["baixada_w"], it["baixada_h"] = im.size
            if it["baixada_w"] < 400:                       # miniatura, não serve nem com upscale
                (saida / it["arquivo"]).unlink(missing_ok=True)
                ok.remove(it)
                continue
            it["pequena"] = it["baixada_w"] < 1000
    except Exception:
        pass
    origem_p = saida / "origem.json"
    origem = json.loads(origem_p.read_text()) if origem_p.exists() else {}
    origem[k] = [{kk: vv for kk, vv in it.items() if kk not in ("thumb", "arquivo_url")} | {"original": it["arquivo_url"]} for it in ok]
    origem_p.write_text(json.dumps(origem, ensure_ascii=False, indent=1))
    folha = folha_imagens(saida, ok, saida / f"folha-{k}.jpg") if ok else None
    return {"consulta": q, "baixadas": len(ok), "erros": erros, "origem": str(origem_p), "folha": str(folha) if folha else None,
            "itens": [{kk: it.get(kk) for kk in ("arquivo", "fonte", "licenca", "autor", "pagina", "baixada_w", "baixada_h", "pequena")} for it in ok]}


def folha_imagens(pasta: Path, itens: list[dict], saida: Path, colunas: int = 4, cel: int = 360) -> Path:
    """Folha de contato com fonte · licença · tamanho em cada célula (pra OLHAR antes de usar)."""
    from PIL import Image, ImageDraw
    from folha import _fonte
    f = _fonte(15)
    linhas = (len(itens) + colunas - 1) // colunas
    alt_txt = 44
    img = Image.new("RGB", (colunas * cel, linhas * (cel + alt_txt)), (24, 24, 24))
    d = ImageDraw.Draw(img)
    for i, it in enumerate(itens):
        x, y = (i % colunas) * cel, (i // colunas) * (cel + alt_txt)
        try:
            with Image.open(pasta / it["arquivo"]) as im:
                im = im.convert("RGB"); im.thumbnail((cel - 6, cel - 6))
                img.paste(im, (x + 3, y + 3))
        except Exception:
            pass
        d.text((x + 6, y + cel), f"{i + 1}. {it['fonte']} · {it['licenca']}"[:48], fill=(255, 255, 255), font=f)
        d.text((x + 6, y + cel + 20), f"{it.get('baixada_w', '?')}x{it.get('baixada_h', '?')} {'(pequena: upscale)' if it.get('pequena') else ''}", fill=(255, 200, 80), font=f)
    img.save(saida, quality=88)
    return saida


# ───────────────────────── vídeo ─────────────────────────

def vid_archive(q: str, n: int) -> list[dict]:
    out = []
    for doc in _archive_docs(q, n, "movies"):
        ident = doc["identifier"]
        try:
            meta = _json(f"https://archive.org/metadata/{ident}")
        except Exception:
            continue
        mp4 = [f for f in meta.get("files", []) if f.get("name", "").lower().endswith(".mp4") and int(f.get("size") or 0) > 200_000]
        if not mp4:
            continue
        mp4.sort(key=lambda f: int(f.get("size") or 0))
        pick = mp4[len(mp4) // 2] if len(mp4) > 2 else mp4[-1]
        out.append(_item("archive", doc.get("title", ident), f"https://archive.org/details/{ident}",
                         f"https://archive.org/download/{ident}/{urllib.parse.quote(pick['name'])}", _lic_url(doc.get("licenseurl")),
                         doc.get("creator", "") if isinstance(doc.get("creator"), str) else "", int(pick.get("width") or 0) or None,
                         int(pick.get("height") or 0) or None, float(pick.get("length") or 0) or None, tipo="video"))
    return out


def vid_commons(q: str, n: int) -> list[dict]:
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:video {q}", "gsrnamespace": 6,
         "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime"}
    d = _json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p))
    out = []
    for pg in sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
        ii = pg["imageinfo"][0]; m = ii.get("extmetadata", {})
        lic = (m.get("LicenseShortName") or {}).get("value", "")
        if re.search(r"\b(nc|nd)\b", lic.lower()):
            continue
        out.append(_item("commons", pg["title"].replace("File:", ""), ii.get("descriptionurl"), ii.get("url"), lic,
                         (m.get("Artist") or {}).get("value", ""), ii.get("width"), ii.get("height"), tipo="video"))
    return out


def vid_nasa(q: str, n: int) -> list[dict]:
    out = []
    for r in _nasa_lista(q, n, "video"):
        try:
            arqs = _json(r["manifesto"])
        except Exception:
            continue
        mp4 = [a for a in arqs if isinstance(a, str) and a.lower().endswith(".mp4") and "preview" not in a.lower()]
        mp4.sort(key=lambda a: ("orig" in a, "large" in a, "medium" in a), reverse=True)
        if mp4:
            out.append(_item("nasa", r["titulo"], r["pagina"], mp4[0].replace(" ", "%20"), "NASA (domínio público, sem endosso)", r["autor"], tipo="video"))
    return out


def vid_pexels(q: str, n: int) -> list[dict]:
    k = _chave("PEXELS_API_KEY")
    if not k:
        return []
    d = _json("https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": q, "per_page": n}), headers={"Authorization": k})
    out = []
    for v in d.get("videos", []):
        arq = sorted([f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"], key=lambda f: f.get("width") or 0)
        arq = [f for f in arq if (f.get("width") or 0) >= 1080] or arq
        if arq:
            out.append(_item("pexels", v.get("url", "").rsplit("/", 2)[-2] if v.get("url") else "vídeo Pexels", v.get("url"), arq[0]["link"],
                             "Pexels License", (v.get("user") or {}).get("name", ""), arq[0].get("width"), arq[0].get("height"), v.get("duration"), tipo="video"))
    return out


def vid_pixabay(q: str, n: int) -> list[dict]:
    k = _chave("PIXABAY_API_KEY")
    if not k:
        return []
    d = _json("https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": k, "q": q, "per_page": max(3, n)}))
    out = []
    for v in d.get("hits", [])[:n]:
        t = (v.get("videos") or {}).get("large") or (v.get("videos") or {}).get("medium") or {}
        if t.get("url"):
            out.append(_item("pixabay", v.get("tags", ""), v.get("pageURL"), t["url"], "Pixabay License", v.get("user", ""),
                             t.get("width"), t.get("height"), v.get("duration"), tipo="video"))
    return out


VID = {"archive": vid_archive, "commons": vid_commons, "nasa": vid_nasa, "pexels": vid_pexels, "pixabay": vid_pixabay}


def buscar_videos(q: str, fontes=SO_VIDEO, n: int = 6) -> tuple[list[dict], dict]:
    itens, erros = [], {}
    with cf.ThreadPoolExecutor(len(fontes) or 1) as ex:
        fut = {f: ex.submit(VID[f], q, n) for f in fontes if f in VID}
        for f, fu in fut.items():
            try:
                itens += fu.result(timeout=120)
            except Exception as e:
                erros[f] = str(e)[:120]
    return itens, erros


def cortar(url: str, ini: float, fim: float, saida: Path, vertical: bool = False) -> Path:
    """Baixa só o trecho (o servidor aceita range). Sem áudio perdido: copia o áudio se existir."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    vf = "crop=ih*9/16:ih,scale=1080:1920,fps=30" if vertical else "fps=30"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-user_agent", UA, "-ss", str(ini), "-i", url, "-t", str(fim - ini),
           "-vf", vf, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(saida)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode or not saida.exists():
        raise RuntimeError("não consegui cortar: " + (r.stderr or "")[-300:])
    return saida


# ───────────────────────── ícone (Iconify) ─────────────────────────

def icones(q: str, saida: Path, n: int = 6, cor: str = "#ffffff") -> dict:
    saida.mkdir(parents=True, exist_ok=True)
    d = _json("https://api.iconify.design/search?" + urllib.parse.urlencode({"query": q, "limit": max(n * 3, 12)}))
    nomes = d.get("icons") or []
    nomes.sort(key=lambda s: (not s.startswith("line-md:"), ))      # os animados (line-md, MIT) primeiro
    prefixos = sorted({s.split(":")[0] for s in nomes[:n * 2]})
    cols = _json("https://api.iconify.design/collections?prefixes=" + ",".join(prefixos)) if prefixos else {}
    ok, origem = [], {}
    for s in nomes:
        if len(ok) >= n:
            break
        pre, nome = s.split(":", 1)
        lic = ((cols.get(pre) or {}).get("license") or {})
        if not lic.get("spdx"):
            continue
        svg = _get(f"https://api.iconify.design/{pre}/{nome}.svg?color={urllib.parse.quote(cor)}&height=512").decode()
        arq = f"{_slug(q)}-{pre}-{nome}.svg"
        (saida / arq).write_text(svg)
        ok.append(arq)
        origem[arq] = {"icone": s, "licenca": lic.get("spdx"), "autor": ((cols.get(pre) or {}).get("author") or {}).get("name", ""),
                       "pagina": f"https://icon-sets.iconify.design/{pre}/{nome}/", "animado": "<animate" in svg}
    op = saida / "origem-icones.json"
    antigo = json.loads(op.read_text()) if op.exists() else {}
    antigo.update(origem)
    op.write_text(json.dumps(antigo, ensure_ascii=False, indent=1))
    return {"consulta": q, "salvos": ok, "origem": str(op)}


def situacao() -> list[dict]:
    return [
        {"fonte": "commons", "chave": "não precisa", "licenca": "livre (CC BY, CC BY-SA, CC0; ND/NC filtrados)"},
        {"fonte": "openverse", "chave": "não precisa", "licenca": "CC0, domínio público, CC BY, CC BY-SA (Flickr, Smithsonian, NASA...)"},
        {"fonte": "nasa", "chave": "não precisa", "licenca": "domínio público, sem endosso"},
        {"fonte": "archive", "chave": "não precisa", "licenca": "só itens com licenseurl domínio público / CC BY / CC BY-SA"},
        {"fonte": "iconify", "chave": "não precisa", "licenca": "a da coleção (MIT, Apache, CC BY...) registrada no origem-icones.json"},
        {"fonte": "pexels", "chave": "ok" if _chave("PEXELS_API_KEY") else "falta PEXELS_API_KEY", "licenca": "Pexels License"},
        {"fonte": "pixabay", "chave": "ok" if _chave("PIXABAY_API_KEY") else "falta PIXABAY_API_KEY", "licenca": "Pixabay License"},
        {"fonte": "unsplash", "chave": "fora: exige chave pessoal (UNSPLASH_ACCESS_KEY), não testada", "licenca": "Unsplash License"},
        {"fonte": "loc.gov", "chave": "fora: Cloudflare bloqueia (403) em 29/10", "licenca": "-"},
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("imagem"); a.add_argument("consulta"); a.add_argument("--saida", required=True)
    a.add_argument("--fontes", default=",".join(SO_IMAGEM)); a.add_argument("--n", type=int, default=4)
    v = sub.add_parser("video"); v.add_argument("consulta"); v.add_argument("--fontes", default=",".join(SO_VIDEO)); v.add_argument("--n", type=int, default=6)
    c = sub.add_parser("cortar"); c.add_argument("url"); c.add_argument("ini", type=float); c.add_argument("fim", type=float)
    c.add_argument("saida"); c.add_argument("--vertical", action="store_true")
    i = sub.add_parser("icone"); i.add_argument("consulta"); i.add_argument("--saida", required=True); i.add_argument("--n", type=int, default=6)
    i.add_argument("--cor", default="#ffffff")
    sub.add_parser("fontes")
    a = ap.parse_args(argv)
    if a.cmd == "imagem":
        r = baixar_imagens(a.consulta, Path(a.saida), [f for f in a.fontes.split(",") if f], a.n)
    elif a.cmd == "video":
        itens, erros = buscar_videos(a.consulta, [f for f in a.fontes.split(",") if f], a.n)
        r = {"consulta": a.consulta, "erros": erros, "itens": itens}
    elif a.cmd == "cortar":
        r = {"saida": str(cortar(a.url, a.ini, a.fim, Path(a.saida), a.vertical))}
    elif a.cmd == "icone":
        r = icones(a.consulta, Path(a.saida), a.n, a.cor)
    else:
        r = situacao()
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
