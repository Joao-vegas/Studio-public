#!/usr/bin/env python3
"""
musica_busca — procura música e efeito sonoro FORA da Biblioteca, sem repetir o que o cliente já usou.

Ordem (a mesma pra IA e pra tela): 1) a música do PRÓPRIO cliente (assets/musica dos modelos dele); 2) a Biblioteca (acervo); 3) a do formato (base/audio/musicas); 4) fora: Mixkit, Jamendo,
SoundCloud/YouTube. Freesound só pra efeito. Nada é copiado pra Biblioteca: `fontes_estudio` só LÊ as pastas.

Fontes de fora:
    mixkit     grátis, sem chave, licença livre até pra anúncio (página de tag do site, mp3 direto).
    jamendo    músicas com licença Creative Commons. Chave grátis JAMENDO_CLIENT_ID (developer.jamendo.com)
    freesound  efeitos sonoros Creative Commons. Chave grátis FREESOUND_API_KEY (freesound.org/apiv2/apply)
    soundcloud grátis, sem chave (yt-dlp, só metadados). A maioria tem direitos autorais: referência e teste.
    youtube    grátis, sem chave (yt-dlp, só metadados). Tem direitos autorais: serve pra referência e teste.
    pagas      Artlist, Musicbed, Epidemic… não têm API pública: baixe com a sua conta e arraste pra Biblioteca.

As chaves moram só no app/.env (lidas e gravadas pelas funções do voz.py). Nunca vão pro navegador.

Regra de variedade: `recentes` diz quais músicas o cliente usou nos últimos vídeos — essas NÃO se repetem.

CLI:
    python3 musica_busca.py do-cliente Cliente4 [--formato documentario]   (só lê; nunca mostra outro cliente)
    python3 musica_busca.py fontes [--tipo musica|sfx]                    (tudo que o Estúdio já tem, por fonte)
    python3 musica_busca.py buscar "documentary" --fonte mixkit           (uma fonte só; sem --fonte = todas)
    python3 musica_busca.py buscar "dark cinematic" --fonte soundcloud
    python3 musica_busca.py baixar <url do mp3> --sandbox <sandbox> --fonte mixkit   (só a faixa escolhida)
    python3 musica_busca.py opcoes Cliente4 --clima documentary [--formato documentario] [--ignorar <slug>]
    python3 musica_busca.py youtube "trilha tensa investigativa"
    python3 musica_busca.py jamendo "tense investigation"
    python3 musica_busca.py freesound "whoosh"
    python3 musica_busca.py buscar "tense" [--tipo musica|sfx] [--cliente Cliente3]
    python3 musica_busca.py recentes "Cliente3" [--n 5] [--ignorar <slug do vídeo atual>]
    python3 musica_busca.py status
    python3 musica_busca.py guardar --fonte jamendo --url ... --audio ... --titulo ...   (usado pela tela)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zlib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ACERVO, JOBS, ensure, gravar_json, ler_json, make_slug, now_slug, agora  # noqa: E402
import voz as _voz  # noqa: E402  (_env / _gravar_env: chaves no app/.env)

UA = "Mozilla/5.0 (Estudio local; musica_busca)"
TMP = ACERVO.parent / ".tmp" / "musica-busca"       # estado do "guardando…" e downloads temporários
LIMITE_YT_S = 15 * 60          # compilação de 1 hora não dá pra baixar e medir inteira
LIMITE_MB = 80                 # tamanho máximo de um mp3 baixado
SFX_DURACAO = 6.0              # mesmo corte do acervo.py: áudio curto assim é efeito, não música

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac")

FONTES = [
    {"id": "virais", "nome": "Virais do momento", "serve": "O PADRÃO do Editorial: o que está viralizando hoje (Shazam, Spotify, Apple Music, Deezer), áudio oficial pelo yt-dlp, só o refrão/drop. Música famosa: o Instagram pode silenciar.",
     "env": None, "onde": None, "onde_txt": None},
    {"id": "mixkit", "nome": "Mixkit", "serve": "Músicas e efeitos grátis, liberados até pra anúncio, sem dar crédito.",
     "env": None, "onde": None, "onde_txt": None},
    {"id": "youtube", "nome": "YouTube", "serve": "Música e efeitos. Tem direitos autorais: bom pra referência e teste.",
     "env": None, "onde": None, "onde_txt": None},
    {"id": "soundcloud", "nome": "SoundCloud", "serve": "Músicas. A maioria tem direitos autorais: referência e teste.",
     "env": None, "onde": None, "onde_txt": None},
    {"id": "jamendo", "nome": "Jamendo", "serve": "Músicas com licença Creative Commons (prévia e download).",
     "env": "JAMENDO_CLIENT_ID", "onde": "https://developer.jamendo.com/v3.0", "onde_txt": "developer.jamendo.com"},
    {"id": "openverse", "nome": "Openverse", "serve": "Músicas (Jamendo) e efeitos (Freesound, Wikimedia) com licença livre, SEM chave: o plano B quando falta a chave.",
     "env": None, "onde": None, "onde_txt": None},
    {"id": "freesound", "nome": "Freesound", "serve": "Efeitos sonoros com licença Creative Commons.",
     "env": "FREESOUND_API_KEY", "onde": "https://freesound.org/apiv2/apply", "onde_txt": "freesound.org/apiv2/apply"},
]

# Sites sem API pública: o João abre, baixa com a conta dele e arrasta pra Biblioteca.
# {q} só onde o formato do link de busca foi conferido; os outros abrem a página de música.
SITES_MANUAIS = [
    {"nome": "Artlist", "paga": True, "musica": "https://artlist.io/royalty-free-music", "sfx": "https://artlist.io/sfx"},
    {"nome": "Epidemic Sound", "paga": True, "musica": "https://www.epidemicsound.com/music/search/?term={q}",
     "sfx": "https://www.epidemicsound.com/sound-effects/"},
    {"nome": "Musicbed", "paga": True, "musica": "https://www.musicbed.com/", "sfx": None},
    {"nome": "Envato Elements", "paga": True, "musica": "https://elements.envato.com/royalty-free-music/{q}",
     "sfx": "https://elements.envato.com/sound-effects/{q}"},
    {"nome": "Motion Array", "paga": True, "musica": "https://motionarray.com/browse/royalty-free-music/",
     "sfx": "https://motionarray.com/browse/sound-effects/"},
    {"nome": "Soundstripe", "paga": True, "musica": "https://www.soundstripe.com/", "sfx": "https://www.soundstripe.com/"},
    {"nome": "Pixabay Música", "paga": False, "musica": "https://pixabay.com/music/search/{q}/",
     "sfx": "https://pixabay.com/sound-effects/search/{q}/"},
    {"nome": "Biblioteca de áudio do YouTube", "paga": False, "musica": "https://studio.youtube.com/channel/UC/music",
     "sfx": "https://studio.youtube.com/channel/UC/music"},
    {"nome": "Free Music Archive", "paga": False, "musica": "https://freemusicarchive.org/search?quicksearch={q}", "sfx": None},
    {"nome": "Mixkit", "paga": False, "musica": "https://mixkit.co/free-stock-music/", "sfx": "https://mixkit.co/free-sound-effects/"},
]

HOSTS = {
    "youtube": ("youtube.com", "youtu.be"),
    "jamendo": ("jamendo.com", "jamen.do"),
    "freesound": ("freesound.org",),
    "mixkit": ("mixkit.co",),
    "openverse": ("jamendo.com", "freesound.org", "wikimedia.org", "archive.org", "openverse.org"),
    "soundcloud": ("soundcloud.com", "snd.sc"),
}
VIA_YTDLP = ("youtube", "soundcloud")      # baixar = yt-dlp (só o áudio); as outras têm link direto do mp3


# ───────────────────────── utilidades ─────────────────────────

def _chave_env(nome: str) -> str:
    return (_voz._env().get(nome) or "").strip()


def _dur_txt(s) -> str:
    try:
        s = int(round(float(s)))
    except (TypeError, ValueError):
        return ""
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _norm(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _chave(url: str) -> str:
    """Identidade de uma faixa independente do formato do link (pra saber se já foi usada/guardada)."""
    u = (url or "").strip()
    if not u:
        return ""
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})", u)
    if m:
        return "yt:" + m.group(1)
    m = re.search(r"jamendo\.com/(?:[a-z]{2}/)?track/(\d+)|jamen\.do/t/(\d+)|jamendo\.com/.*?trackid=(\d+)"
                  r"|jamendo\.com/download/track/(\d+)", u)
    if m:
        return "jamendo:" + next(g for g in m.groups() if g)
    m = re.search(r"freesound\.org/(?:people/[^/]+/)?sounds/(\d+)|freesound\.org/previews/\d+/(\d+)_", u)
    if m:
        return "freesound:" + next(g for g in m.groups() if g)
    m = re.search(r"mixkit\.co/(?:active_storage/)?(music|sfx)/(\d+)/", u)
    if m:
        return f"mixkit:{m.group(1)}:{m.group(2)}"
    m = re.search(r"soundcloud\.com/([\w-]+/[\w-]+)", u)
    if m:
        return "soundcloud:" + m.group(1).lower()
    return u.lower().rstrip("/")


def _chave_meta(meta: dict) -> str:
    return ((meta.get("busca") or {}).get("chave") or _chave(meta.get("fonte", ""))
            or _chave((meta.get("youtube") or {}).get("url", "")))


def _host_ok(url: str, fonte: str) -> bool:
    try:
        p = urllib.parse.urlparse(url or "")
    except ValueError:
        return False
    h = (p.hostname or "").lower()
    return p.scheme in ("http", "https") and any(h == d or h.endswith("." + d) for d in HOSTS.get(fonte, ()))


def _get_json(url: str, params: dict, timeout: int = 20) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _licenca(url: str) -> dict:
    """'http://creativecommons.org/licenses/by-nc-sa/3.0/' → nome curto, se pode uso comercial e o que cuidar."""
    u = (url or "").lower()
    if not u:
        return {"licenca": "", "comercial": None, "aviso_licenca": ""}
    if "publicdomain/zero" in u or "cc0" in u:
        return {"licenca": "CC0 (domínio público)", "comercial": True,
                "aviso_licenca": "Domínio público: pode usar até em anúncio, sem precisar dar crédito."}
    m = re.search(r"licenses/([a-z+\-]+)/([\d.]+)", u)
    if not m:
        return {"licenca": url, "comercial": None, "aviso_licenca": "Confira a licença no site antes de publicar."}
    partes = m.group(1).split("-")
    nome = f"CC {m.group(1).upper()} {m.group(2)}"
    if "nc" in partes:
        return {"licenca": nome, "comercial": False,
                "aviso_licenca": "Não comercial: não use em anúncio nem em vídeo pago de cliente."}
    if partes[0] == "by":
        av = "Pode usar, inclusive comercial, dando crédito ao autor na descrição do vídeo."
        if "nd" in partes:
            av += " ND: não pode modificar a música."
        return {"licenca": nome, "comercial": True, "aviso_licenca": av}
    return {"licenca": nome, "comercial": None, "aviso_licenca": "Confira a licença no site antes de publicar."}


def _grupo(fonte: str, itens=None, aviso: str = "", precisa_chave: bool = False, procurei: str = "") -> dict:
    f = next(x for x in FONTES if x["id"] == fonte)
    return {"fonte": fonte, "nome": f["nome"], "itens": itens or [], "aviso": aviso,
            "precisa_chave": precisa_chave, "procurei": procurei}


def _ytdlp() -> list[str] | None:
    p = shutil.which("yt-dlp") or next((c for c in ("/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp")
                                        if Path(c).exists()), None)
    if p:
        return [p]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return None


# ───────────────────────── fontes ─────────────────────────

AVISO_YT = ("Música do YouTube pode ter direitos autorais: boa pra referência e teste. "
            "Pra publicar, prefira Jamendo, Freesound ou a sua conta paga (Artlist, Epidemic…).")


def buscar_youtube(termo: str, n: int = 8, pagina: int = 1, tipo: str = "musica", excluir=()) -> dict:
    """Só metadados (título, canal, duração, link): não baixa nada. Grátis e sem chave.

    O YouTube muda a ordem a cada busca, então "trazer outras" passa `excluir` (ids já mostrados)
    em vez de confiar só no número da página."""
    termo = (termo or "").strip()
    if not termo:
        return _grupo("youtube", aviso="Digite o que procurar.")
    yt = _ytdlp()
    if not yt:
        return _grupo("youtube", aviso="O yt-dlp não está instalado neste Mac (rode o setup do Estúdio).")
    pagina = max(1, int(pagina or 1))
    try:
        excluir = {x for x in (excluir or ()) if x}
        total = n * pagina + (n if excluir else 0)
        r = subprocess.run(yt + ["--no-update", "--no-warnings", "--flat-playlist", "--dump-json",
                                 f"ytsearch{total}:{termo}"], capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return _grupo("youtube", aviso="O YouTube demorou demais pra responder. Tente de novo.", procurei=termo)
    itens = []
    linhas = r.stdout.splitlines() if excluir else r.stdout.splitlines()[(pagina - 1) * n:]
    for linha in linhas:
        if len(itens) >= n:
            break
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        vid = d.get("id") or ""
        if not re.fullmatch(r"[\w-]{11}", vid) or vid in excluir:
            continue
        dur = d.get("duration")
        url = f"https://www.youtube.com/watch?v={vid}"
        itens.append({
            "fonte": "youtube", "id": vid, "chave": "yt:" + vid, "tipo": tipo,
            "titulo": d.get("title") or vid, "autor": d.get("channel") or d.get("uploader") or "",
            "duracao": dur, "duracao_txt": _dur_txt(dur), "url": url, "youtube_id": vid,
            "previa": None, "baixar": None, "capa": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "licenca": "Direitos do autor (YouTube)", "comercial": False, "aviso_licenca": AVISO_YT,
            "longa": bool(dur and dur > LIMITE_YT_S), "tags": [],
        })
    aviso = "" if itens else ("Nada encontrado." if r.returncode == 0 else
                              "O YouTube não respondeu (sem internet?). " + (r.stderr or "")[-200:])
    return _grupo("youtube", itens, aviso, procurei=termo)


def buscar_jamendo(termo: str, n: int = 8, pagina: int = 1, instrumental: bool = False) -> dict:
    """Músicas Creative Commons, com prévia em mp3. Precisa de JAMENDO_CLIENT_ID (grátis)."""
    termo = (termo or "").strip()
    cid = _chave_env("JAMENDO_CLIENT_ID")
    if not cid:
        return _grupo("jamendo", aviso="Falta a chave do Jamendo (grátis). Cole em Configurações → Música e efeitos.",
                      precisa_chave=True, procurei=termo)
    if not termo:
        return _grupo("jamendo", aviso="Digite o que procurar.")
    params = {"client_id": cid, "format": "json", "limit": n, "offset": (max(1, int(pagina or 1)) - 1) * n,
              "search": termo, "include": "musicinfo", "audioformat": "mp32"}
    if instrumental:
        params["vocalinstrumental"] = "instrumental"
    try:
        d = _get_json("https://api.jamendo.com/v3.0/tracks/", params)
    except urllib.error.HTTPError as e:
        return _grupo("jamendo", aviso=f"O Jamendo respondeu erro {e.code}. Tente de novo daqui a pouco.", procurei=termo)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return _grupo("jamendo", aviso=f"Não consegui falar com o Jamendo (sem internet?): {e}", procurei=termo)
    h = d.get("headers") or {}
    if h.get("status") != "success":
        msg = h.get("error_message") or "erro desconhecido"
        if h.get("code") == 5 or "client id" in msg.lower():
            return _grupo("jamendo", aviso="O Jamendo não aceitou a chave. Confira o Client ID em Configurações.",
                          precisa_chave=True, procurei=termo)
        return _grupo("jamendo", aviso=f"O Jamendo respondeu: {msg}", procurei=termo)
    itens = []
    for t in d.get("results") or []:
        tid = str(t.get("id") or "")
        lic = _licenca(t.get("license_ccurl", ""))
        info = t.get("musicinfo") or {}
        tags = info.get("tags") or {}
        baixar = t.get("audiodownload") if t.get("audiodownload_allowed", True) and t.get("audiodownload") else t.get("audio")
        itens.append({
            "fonte": "jamendo", "id": tid, "chave": "jamendo:" + tid, "tipo": "musica",
            "titulo": t.get("name") or tid, "autor": t.get("artist_name") or "",
            "duracao": t.get("duration"), "duracao_txt": _dur_txt(t.get("duration")),
            "url": t.get("shareurl") or f"https://www.jamendo.com/track/{tid}",
            "previa": t.get("audio") or None, "baixar": baixar or None,
            "capa": t.get("album_image") or t.get("image") or None, "licenca_url": t.get("license_ccurl", ""),
            "tags": (tags.get("genres") or [])[:3] + (tags.get("vartags") or [])[:3],
            "longa": False, **lic,
        })
    return _grupo("jamendo", itens, "" if itens else "Nada encontrado no Jamendo. Tente em inglês (tense, epic, corporate).",
                  procurei=termo + (" · só instrumental" if instrumental else ""))


def buscar_freesound(termo: str, n: int = 8, pagina: int = 1) -> dict:
    """Efeitos sonoros Creative Commons, com prévia em mp3. Precisa de FREESOUND_API_KEY (grátis)."""
    termo = (termo or "").strip()
    token = _chave_env("FREESOUND_API_KEY")
    if not token:
        return _grupo("freesound", aviso="Falta a chave do Freesound (grátis). Cole em Configurações → Música e efeitos.",
                      precisa_chave=True, procurei=termo)
    if not termo:
        return _grupo("freesound", aviso="Digite o que procurar.")
    params = {"query": termo, "token": token, "page_size": n, "page": max(1, int(pagina or 1)),
              "fields": "id,name,duration,license,previews,username,url,tags"}
    try:
        d = _get_json("https://freesound.org/apiv2/search/text/", params)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return _grupo("freesound", aviso="O Freesound não aceitou a chave. Confira em Configurações.",
                          precisa_chave=True, procurei=termo)
        if e.code == 404:
            return _grupo("freesound", aviso="Acabaram os resultados do Freesound pra essa busca.", procurei=termo)
        return _grupo("freesound", aviso=f"O Freesound respondeu erro {e.code}. Tente de novo daqui a pouco.", procurei=termo)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return _grupo("freesound", aviso=f"Não consegui falar com o Freesound (sem internet?): {e}", procurei=termo)
    itens = []
    for s in d.get("results") or []:
        sid = str(s.get("id") or "")
        prev = (s.get("previews") or {}).get("preview-hq-mp3") or (s.get("previews") or {}).get("preview-lq-mp3")
        itens.append({
            "fonte": "freesound", "id": sid, "chave": "freesound:" + sid, "tipo": "sfx",
            "titulo": s.get("name") or sid, "autor": s.get("username") or "",
            "duracao": s.get("duration"), "duracao_txt": _dur_txt(s.get("duration")),
            "url": s.get("url") or f"https://freesound.org/s/{sid}/",
            "previa": prev, "baixar": prev, "capa": None, "licenca_url": s.get("license", ""),
            "tags": (s.get("tags") or [])[:5], "longa": False, **_licenca(s.get("license", "")),
        })
    return _grupo("freesound", itens, "" if itens else "Nada encontrado no Freesound. Tente em inglês (whoosh, impact, riser).",
                  procurei=termo)


def buscar_openverse(termo: str, n: int = 8, tipo: str = "musica", pagina: int = 1) -> dict:
    """Música e efeito de licença livre pela API do Openverse (sem chave): traz Jamendo, Freesound, Wikimedia e Internet Archive.
    Só CC0, domínio público, CC BY e CC BY-SA (nunca NC nem ND, que não servem pra anúncio nem pra cortar)."""
    termo = (termo or "").strip()
    if not termo:
        return _grupo("openverse", aviso="Digite o que procurar.")
    params = {"q": termo, "page_size": n * 2, "page": max(1, int(pagina or 1)), "license_type": "commercial", "mature": "false"}
    if tipo != "sfx":
        params["category"] = "music"      # a categoria de efeito do Openverse vem vazia: efeito é busca sem categoria
    try:
        d = _get_json("https://api.openverse.org/v1/audio/", params, timeout=75)
    except urllib.error.HTTPError as e:
        return _grupo("openverse", aviso=f"O Openverse respondeu erro {e.code}. Tente de novo daqui a pouco.", procurei=termo)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return _grupo("openverse", aviso=f"Não consegui falar com o Openverse (sem internet?): {e}", procurei=termo)
    itens = []
    for r in d.get("results") or []:
        rid = str(r.get("id") or "")
        dur = (r.get("duration") or 0) / 1000 or None
        url = r.get("foreign_landing_url") or ""
        audio = r.get("url") or ""
        if (r.get("license") or "") not in ("cc0", "pdm", "by", "by-sa"):      # sem ND (não pode cortar) nem NC
            continue
        if not (_host_ok(url, "openverse") and _host_ok(audio, "openverse")):
            continue
        lic_url = r.get("license_url") or f"https://creativecommons.org/licenses/{r.get('license')}/{r.get('license_version') or '4.0'}/"
        itens.append({
            "fonte": "openverse", "id": rid, "chave": "openverse:" + rid, "tipo": "sfx" if (dur and dur <= SFX_DURACAO) or tipo == "sfx" else "musica",
            "titulo": r.get("title") or rid, "autor": r.get("creator") or "",
            "duracao": dur, "duracao_txt": _dur_txt(dur), "url": url, "previa": audio, "baixar": audio,
            "capa": r.get("thumbnail") or None, "licenca_url": lic_url, "tags": [t.get("name") for t in (r.get("tags") or [])[:5] if t.get("name")],
            "longa": False, "origem": r.get("provider") or r.get("source") or "", **_licenca(lic_url),
        })
    itens = itens[:n]
    return _grupo("openverse", itens, "" if itens else "Nada encontrado no Openverse. Tente em inglês (dark ambient, whoosh, riser).",
                  procurei=termo)


LICENCA_MIXKIT = "Mixkit (grátis, pode usar comercial)"
AVISO_MIXKIT = "Licença grátis do Mixkit: pode usar em vídeo de cliente e em anúncio, sem dar crédito."
AVISO_SC = ("Música do SoundCloud quase sempre tem direitos autorais: boa pra referência e teste. "
            "Pra publicar, prefira Mixkit, Jamendo ou a sua conta paga.")


def _iso_dur(txt: str) -> float | None:
    """'PT1M53S' → 113.0"""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", str(txt or "").strip())
    if not m or not any(m.groups()):
        return None
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def _mixkit_itens(html: str, tipo: str, pagina_url: str) -> list[dict]:
    """As faixas de uma página do Mixkit. O site traz a lista em JSON-LD (nome, autor, duração e o mp3)."""
    achados = []

    def andar(x):
        if isinstance(x, dict):
            u = str(x.get("url") or x.get("contentUrl") or "")
            if u.lower().endswith(".mp3") and "mixkit.co" in u:
                achados.append(x)
            for v in x.values():
                andar(v)
        elif isinstance(x, list):
            for v in x:
                andar(v)

    for bloco in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            andar(json.loads(bloco))
        except ValueError:
            continue
    if not achados:                               # sem JSON-LD: ao menos os mp3 da página
        achados = [{"url": u} for u in dict.fromkeys(re.findall(r'https://assets\.mixkit\.co/[^"\'\s]+?\.mp3', html))]
    itens, vistos = [], set()
    for x in achados:
        mp3 = str(x.get("url") or x.get("contentUrl"))
        chave = _chave(mp3)
        if chave in vistos:
            continue
        vistos.add(chave)
        dur = _iso_dur(x.get("duration"))
        autor = x.get("byArtist")
        autor = autor.get("name", "") if isinstance(autor, dict) else str(autor or "")
        num = (re.search(r"/(\d+)/[^/]*\.mp3$", mp3) or re.search(r"(\d+)", mp3))
        itens.append({
            "fonte": "mixkit", "id": num.group(1) if num else chave, "chave": chave, "tipo": tipo,
            "titulo": str(x.get("name") or (f"Mixkit {num.group(1)}" if num else "Faixa do Mixkit")),
            "autor": autor, "duracao": dur, "duracao_txt": _dur_txt(dur), "url": pagina_url,
            "previa": mp3, "baixar": mp3, "capa": None, "licenca": LICENCA_MIXKIT, "comercial": True,
            "aviso_licenca": AVISO_MIXKIT, "tags": [g for g in [x.get("genre")] if g][:3], "longa": False,
        })
    return itens


def buscar_mixkit(termo: str, n: int = 8, tipo: str = "musica", pagina: int = 1) -> dict:
    """Mixkit não tem API: lê a página da tag (ex.: /free-stock-music/tag/documentary/) e, se não existir,
    a página de busca. Grátis, sem chave, sem baixar nada (o mp3 só desce quando o João escolhe)."""
    termo = (termo or "").strip()
    if not termo:
        return _grupo("mixkit", aviso="Digite o que procurar.")
    secao = "free-sound-effects" if tipo == "sfx" else "free-stock-music"
    slug = "-".join(_norm(termo).split())
    ultimo = ""
    extra = f"?page={int(pagina)}" if pagina and int(pagina) > 1 else ""      # página 2-3: não cair sempre nas 8 primeiras
    for url in (f"https://mixkit.co/{secao}/tag/{slug}/", f"https://mixkit.co/{secao}/discover/{slug}/"):
        try:
            req = urllib.request.Request(url + extra, headers={"User-Agent": "Mozilla/5.0 (Macintosh) Estudio", "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            ultimo = f"o Mixkit respondeu erro {e.code}"
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            return _grupo("mixkit", aviso=f"Não consegui falar com o Mixkit (sem internet?): {e}", procurei=termo)
        itens = _mixkit_itens(html, "sfx" if tipo == "sfx" else "musica", url)
        if itens:
            return _grupo("mixkit", itens[:n], procurei=termo)
    return _grupo("mixkit", aviso="Nada encontrado no Mixkit. Tente uma palavra em inglês (documentary, cinematic, "
                                  "corporate, suspense)." + (f" ({ultimo})" if ultimo else ""), procurei=termo)


def buscar_soundcloud(termo: str, n: int = 8) -> dict:
    """Só metadados via yt-dlp (`scsearchN:`). Grátis e sem chave. Direitos autorais: referência e teste."""
    termo = (termo or "").strip()
    if not termo:
        return _grupo("soundcloud", aviso="Digite o que procurar.")
    yt = _ytdlp()
    if not yt:
        return _grupo("soundcloud", aviso="O yt-dlp não está instalado neste Mac (rode o setup do Estúdio).")
    try:
        r = subprocess.run(yt + ["--no-update", "--no-warnings", "--flat-playlist", "--dump-json",
                                 f"scsearch{max(1, int(n))}:{termo}"], capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return _grupo("soundcloud", aviso="O SoundCloud demorou demais pra responder. Tente de novo.", procurei=termo)
    itens = []
    for linha in r.stdout.splitlines():
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        url = d.get("webpage_url") or d.get("url") or ""
        if not _host_ok(url, "soundcloud"):
            continue
        dur = d.get("duration")
        itens.append({
            "fonte": "soundcloud", "id": str(d.get("id") or _chave(url)), "chave": _chave(url), "tipo": "musica",
            "titulo": d.get("title") or url.rsplit("/", 1)[-1], "autor": d.get("uploader") or d.get("channel") or "",
            "duracao": dur, "duracao_txt": _dur_txt(dur), "url": url, "previa": None, "baixar": None, "capa": None,
            "licenca": "Direitos do autor (SoundCloud)", "comercial": False, "aviso_licenca": AVISO_SC,
            "longa": bool(dur and dur > LIMITE_YT_S), "tags": [],
        })
    aviso = AVISO_SC if itens else ("Nada encontrado." if r.returncode == 0 else
                                    "O SoundCloud não respondeu (sem internet?). " + (r.stderr or "")[-200:])
    return _grupo("soundcloud", itens[:n], aviso, procurei=termo)


def buscar_virais(termo: str = "", n: int = 10) -> dict:
    """As virais de hoje (ou as que casam com `termo`), só metadados: o áudio só baixa quando a faixa é escolhida (musica_viral.preparar)."""
    import musica_viral as _mv
    try:
        lista = _mv.procurar(termo, n) if termo.strip() else [
            {"id": m["id"], "titulo": m["titulo"], "artista": m["artista"], "motivo": "viral hoje: " + _mv.resumo_fontes(m), "viral": True}
            for m in _mv.virais(n)]
    except Exception as e:
        return _grupo("virais", aviso=f"Não consegui ler as paradas agora ({e}).", procurei=termo)
    itens = [{"fonte": "virais", "id": x["id"], "chave": "viral:" + x["id"], "tipo": "musica", "titulo": x["titulo"], "autor": x["artista"],
              "duracao": None, "duracao_txt": "", "url": x["id"] if str(x["id"]).startswith("http") else "", "previa": None, "baixar": None,
              "motivo": x["motivo"], "licenca": "Música famosa (direitos do autor)", "comercial": False, "aviso_licenca": _mv.AVISO_DIREITOS,
              "tags": ["viral"], "viral": x.get("viral", True)} for x in lista]
    return _grupo("virais", [it for it in itens if not reprovada(it)], _mv.AVISO_DIREITOS if itens else "Nada encontrado.", procurei=termo)


def buscar_fonte(fonte: str, termo: str, tipo: str = "musica", n: int = 8, pagina: int = 1) -> dict:
    """Uma fonte só (CLI `buscar --fonte`)."""
    if fonte == "virais":
        return buscar_virais(termo, n)
    if fonte == "mixkit":
        return buscar_mixkit(termo, n, tipo, pagina)
    if fonte == "soundcloud":
        return buscar_soundcloud(termo, n)
    if fonte == "jamendo":
        return buscar_jamendo(termo, n, pagina)
    if fonte == "openverse":
        return buscar_openverse(termo, n, tipo, pagina)
    if fonte == "freesound":
        return buscar_freesound(termo, n, pagina)
    if fonte == "youtube":
        return buscar_youtube(termo, n, pagina, tipo)
    raise ValueError(f"fonte desconhecida: {fonte}")


def buscar(termo: str, tipo: str = "musica", n: int = 8, pagina: int = 1, instrumental: bool = False,
           excluir_yt=()) -> list[dict]:
    """Todas as fontes de uma vez, na ordem da política: livres primeiro (Mixkit), YouTube por último."""
    tipo = "sfx" if tipo == "sfx" else "musica"
    termo_yt = termo
    if tipo == "musica" and instrumental and "instrumental" not in termo.lower():
        termo_yt = f"{termo} instrumental"
    if tipo == "sfx" and not re.search(r"efeito|sound|sfx", termo, re.I):
        termo_yt = f"{termo} sound effect"
    tarefas = [("mixkit", lambda: buscar_mixkit(termo, n, tipo))] if pagina == 1 else []
    tarefas += ([("jamendo", lambda: buscar_jamendo(termo, n, pagina, instrumental))] if tipo == "musica"
                else [("freesound", lambda: buscar_freesound(termo, n, pagina))])
    tarefas.append(("openverse", lambda: buscar_openverse(termo, n, tipo, pagina)))     # livre e sem chave (Jamendo/Freesound/Wikimedia)
    tarefas.append(("youtube", lambda: buscar_youtube(termo_yt, n, pagina, tipo, excluir_yt)))
    with ThreadPoolExecutor(max_workers=len(tarefas)) as ex:
        futuros = [(nome, ex.submit(fn)) for nome, fn in tarefas]
        out = []
        for nome, fut in futuros:
            try:
                out.append(fut.result())
            except Exception as e:                       # uma fonte com problema não derruba as outras
                out.append(_grupo(nome, aviso=f"Erro inesperado: {e}"))
    return out


# ───────────────────────── busca variada pela fala (sem IA paga) ─────────────────────────

CLIMAS_FALA = (   # (clima, palavras da fala em português, termos de busca em inglês)
    ("dark tense", ("dor", "medo", "perd", "fracass", "erro", "problema", "crise", "golpe", "fraude", "mentira", "risco", "quebr"),
     ("thriller", "mystery", "drama")),
    ("uplifting", ("virada", "conquist", "vitoria", "sucesso", "cresc", "resultado", "venc", "realiz", "mudou", "mudanca"),
     ("motivational", "epic-drama", "hero")),
    ("corporate", ("dado", "prova", "numero", "estudo", "pesquisa", "metodo", "process", "empresa", "negocio", "lucro", "venda"),
     ("corporate", "technology", "background")),
    ("playful", ("humor", "engracad", "piada", "absurd", "maluc", "louco"), ("comedy", "slapstick")),
    ("news", ("noticia", "urgente", "agora", "governo", "lei ", "mercado", "polit"), ("news", "investigation", "documentary")),
)


def termos_da_fala(texto: str, formato: str | None = None) -> list[tuple[str, str]]:
    """De 3 a 5 termos de busca [(clima, termo em inglês)] a partir da fala, de 3 climas diferentes quando possível:
    o clima que a fala pede primeiro, depois o do formato e os que complementam. Sem IA paga."""
    t = " " + _norm(texto or "") + " "
    pontos = sorted(((sum(t.count(p) for p in pal), clima, termos) for clima, pal, termos in CLIMAS_FALA), key=lambda x: -x[0])
    fmt = CLIMA_FORMATO.get(formato or "", "")
    sel = []
    for ordem, (pts, clima, termos) in enumerate(pontos):
        if pts == 0 and ordem >= 3 and len(sel) >= 3:
            break
        sel.append((clima, termos))
    sel = sel[:3]
    out, vistos = [], set()
    for rodada in (0, 1):                                # 1 termo por clima, depois o 2º termo de cada um
        for clima, termos in sel:
            if rodada < len(termos) and termos[rodada] not in vistos:
                vistos.add(termos[rodada])
                out.append((clima, termos[rodada]))
    if fmt and fmt not in vistos:
        out.insert(1, ("formato", fmt))
    return out[:6] if len(out) >= 3 else out + [("corporate", "background"), ("motivational", "motivational")][:3 - len(out)]


def buscar_varias(termos: list[tuple[str, str]], tipo: str = "musica", n: int = 12, cliente: str = "", job: str = "",
                  pagina: int = 1) -> list[dict]:
    """Mixkit (+ Jamendo e Freesound se houver chave) pelos termos, sem duplicata, SEM o que o cliente já usou, no mínimo
    6 opções de 3 climas quando as fontes derem. Devolve [{clima, itens}] (um grupo por clima). `pagina` 2-3 traz mais."""
    tipo = "sfx" if tipo == "sfx" else "musica"
    termos = list(termos)[:6]
    if pagina == 1 and job:                              # dois vídeos não veem as mesmas faixas
        pagina = 1 + zlib.crc32(str(job).encode()) % 3

    def uma(par):
        clima, termo = par
        itens = []
        try:
            itens += buscar_mixkit(termo, n, tipo, pagina).get("itens", [])
            if not itens and pagina > 1:
                itens += buscar_mixkit(termo, n, tipo, 1).get("itens", [])
            if not itens:                                # termo vazio: tenta o próximo do mesmo clima
                irmaos = next((list(ts) for c, _p, ts in CLIMAS_FALA if c == clima), [])
                for outro in irmaos:
                    if outro != termo and not itens:
                        itens += buscar_mixkit(outro, n, tipo, 1).get("itens", [])
            if tipo == "musica" and _chave_env("JAMENDO_CLIENT_ID"):
                itens += buscar_jamendo(termo, 4, pagina, True).get("itens", [])
            if tipo == "sfx" and _chave_env("FREESOUND_API_KEY"):
                itens += buscar_freesound(termo, 4, pagina).get("itens", [])
        except Exception:
            pass
        return clima, termo, itens

    with ThreadPoolExecutor(max_workers=max(1, len(termos))) as ex:
        achados = list(ex.map(uma, termos))
    rec = usadas_recentemente(cliente, JANELA_CLIENTE[tipo]) if cliente else []
    usados = {(r.get("chave") or "") for r in rec if r.get("chave")}
    ids_usados = {re.sub(r"\D", "", str(x)) for r in rec for x in (Path(r.get("arquivo") or "").stem, r.get("titulo")) if re.search(r"\d{3,}", str(x))}
    vistos, grupos = set(), []
    import random
    for clima, termo, itens in achados:
        bons = []
        for it in itens:
            if it.get("chave") in vistos or it.get("chave") in usados or (it.get("fonte") == "mixkit" and it.get("id") in ids_usados):
                continue
            vistos.add(it.get("chave"))
            it["clima"], it["termo"] = clima, termo
            bons.append(it)
        random.Random(f"{job}|{termo}|{pagina}").shuffle(bons)
        if bons:
            grupos.append({"clima": clima, "termo": termo, "itens": bons[:max(2, n // max(1, len(termos)) + 1)]})
    return grupos


# ───────────────────────── Biblioteca (acervo) ─────────────────────────

def _metas():
    if not ACERVO.is_dir():
        return
    for d in sorted(ACERVO.iterdir()):
        m = ler_json(d / "meta.json") if d.is_dir() else None
        if m:
            yield d.name, m


def _e_musica(meta: dict) -> bool:
    tipo = meta.get("tipo") or ""
    if tipo == "musica":
        return True
    if tipo == "audio":                                  # item antigo, antes de separar música de efeito
        dur = (meta.get("media") or {}).get("duracao") or (meta.get("analise") or {}).get("duracao_s") or 0
        return dur > SFX_DURACAO
    return False


def indice_biblioteca() -> dict:
    """{chave da faixa: slug} de tudo que já está guardado (pra marcar 'já está na Biblioteca')."""
    return {c: slug for slug, m in _metas() if (c := _chave_meta(m))}


def na_biblioteca(termo: str, tipo: str = "musica", limite: int = 6) -> list[dict]:
    """Itens da Biblioteca que batem com as palavras da busca — a política manda olhar aqui primeiro."""
    import acervo as _acervo
    palavras = [p for p in _norm(termo).split() if len(p) >= 3]
    if not palavras:
        return []
    achados = []
    for it in _acervo.listar(tipo="sfx" if tipo == "sfx" else "musica"):
        blob = _norm(" ".join([it.get("titulo", ""), " ".join(it.get("tags", [])), it.get("descricao", "") or "",
                               it.get("clima", "") or "", it.get("como_soa", "") or "", it.get("observacao", "") or ""]))
        nota = sum(1 for p in palavras if p in blob)
        if nota:
            dur = (it.get("media") or {}).get("duracao")
            achados.append((nota, {
                "fonte": "biblioteca", "id": it["slug"], "slug": it["slug"], "chave": "acervo:" + it["slug"],
                "tipo": it.get("tipo"), "titulo": it.get("titulo") or it["slug"], "autor": it.get("autor", ""),
                "duracao": dur, "duracao_txt": _dur_txt(dur), "url": it.get("fonte") or "",
                "clip_rel": it.get("clip_rel"), "licenca": it.get("licenca", ""), "aviso_licenca": "",
                "como_soa": it.get("como_soa", ""), "bpm": (it.get("analise") or {}).get("bpm"),
                "resumo": it.get("resumo_curto", ""), "n_usos": len(it.get("usos") or []), "tags": it.get("tags", [])[:5],
            }))
    achados.sort(key=lambda x: -x[0])
    return [a for _, a in achados[:limite]]


# ───────────────────────── regra de variedade ─────────────────────────

def _musica_do_plano(job: dict) -> dict | None:
    """O campo `musica` do PLANO.json (a política pede opcao, origem, acervo_slug…)."""
    from _comum import RAIZ
    if not job.get("sandbox"):
        return None
    p = ler_json(RAIZ / job["sandbox"] / "PLANO.json") or {}
    m = p.get("musica")
    if isinstance(m, list):
        m = next((x for x in m if isinstance(x, dict)), None)
    if isinstance(m, str) and m.strip():
        m = {"opcao": m.strip()}
    if isinstance(m, dict) and m.get("sem"):                # o João tirou a música desse vídeo
        return None
    return m if isinstance(m, dict) and any(m.get(k) for k in ("acervo_slug", "opcao", "titulo", "url", "fonte", "arquivo")) else None


def usadas_recentemente(cliente: str, n: int = 5, ignorar: str = "") -> list[dict]:
    """Músicas que esse cliente usou nos últimos `n` vídeos (que tinham música). Essas não se repetem.

    Junta duas pistas: os `usos` gravados no meta.json de cada item da Biblioteca (acervo.registrar_uso)
    e o campo `musica` do PLANO.json de cada vídeo do cliente (pega também música que veio de fora).
    `ignorar` = slug do vídeo que está sendo feito agora (a música dele não conta como repetição).
    """
    alvo = (cliente or "").strip().lower()
    if not alvo:
        return []
    metas = dict(_metas())
    jobs = {}
    if JOBS.is_dir():
        pasta = next((p for p in JOBS.iterdir() if p.is_dir() and p.name.lower() == alvo), None)
        for pj in (pasta.iterdir() if pasta else []):
            j = ler_json(pj / "job.json") if pj.is_dir() else None
            if j:
                jobs[pj.name] = j
    usos = []
    try:                                           # histórico confiável (acervo/usos.jsonl) primeiro; o resto fica de reserva
        import uso_midia as _uso
        for u in _uso.recentes(cliente, "musica", max(1, int(n or 5))):
            if ignorar and u.get("job") == ignorar:
                continue
            usos.append({"slug": "", "titulo": u.get("titulo") or "?", "fonte": u.get("fonte", ""), "chave": "",
                         "chave_uso": u.get("chave", ""), "arquivo": u.get("arquivo", ""), "job": u["job"],
                         "job_titulo": u["job"], "modelo": u.get("modelo", ""), "data": u.get("em", ""), "origem": "usos"})
    except Exception:
        pass
    for slug, meta in metas.items():
        if not _e_musica(meta):
            continue
        for u in meta.get("usos") or []:
            if str(u.get("cliente", "")).lower() != alvo or (ignorar and u.get("job") == ignorar):
                continue
            j = jobs.get(u.get("job"), {})
            usos.append({"slug": slug, "titulo": meta.get("titulo") or slug, "fonte": meta.get("fonte", ""),
                         "chave": _chave_meta(meta), "job": u.get("job", ""), "job_titulo": j.get("titulo") or u.get("job", ""),
                         "modelo": u.get("modelo", ""), "data": j.get("criado_em") or u.get("em", ""), "origem": "biblioteca"})
    for js, j in jobs.items():
        if ignorar and js == ignorar:
            continue
        m = _musica_do_plano(j)
        if not m:
            continue
        slug = m.get("acervo_slug") or ""
        if slug and any(x["job"] == js and x["slug"] == slug for x in usos):
            continue
        meta = metas.get(slug) or {}
        fonte = m.get("url") or m.get("fonte") or meta.get("fonte", "")
        fonte = fonte if str(fonte).startswith("http") else meta.get("fonte", "")
        usos.append({"slug": slug, "titulo": meta.get("titulo") or m.get("titulo") or m.get("opcao") or m.get("arquivo") or "?",
                     "fonte": fonte, "chave": (_chave_meta(meta) if meta else "") or _chave(fonte),
                     "arquivo": str(m.get("opcao") or m.get("arquivo") or ""),
                     "job": js, "job_titulo": j.get("titulo") or js, "modelo": j.get("modelo", ""),
                     "data": j.get("criado_em", ""), "origem": m.get("origem") or "plano"})
    usos.sort(key=lambda x: x["data"], reverse=True)
    ordem = []
    for x in usos:
        if x["job"] not in ordem:
            ordem.append(x["job"])
    ordem = ordem[:max(1, int(n or 5))]
    out = []
    for x in usos:
        if x["job"] in ordem:
            x["posicao"] = ordem.index(x["job"]) + 1
            out.append(x)
    return out


def texto_uso(r: dict, cliente: str) -> str:
    return (f"usada no último vídeo do {cliente}" if r.get("posicao") == 1
            else f"usada no {r.get('posicao')}º vídeo mais recente do {cliente}")


def marcar(itens: list[dict], recentes: list[dict], cliente: str = "") -> list[dict]:
    """Marca o que o cliente usou há pouco (e manda pro fim), o que já está guardado e o que está guardando."""
    por_chave = {r["chave"]: r for r in recentes if r.get("chave")}
    por_slug = {r["slug"]: r for r in recentes if r.get("slug")}
    por_titulo = {_norm(r["titulo"]): r for r in recentes if len(_norm(r["titulo"])) >= 6}
    bib = indice_biblioteca()
    guard = guardando()
    for it in itens:
        r = (por_slug.get(it.get("slug")) if it.get("slug") else None) or por_chave.get(it.get("chave")) \
            or por_titulo.get(_norm(it.get("titulo", "")))
        if not r and it.get("chave") in bib:
            r = por_slug.get(bib[it["chave"]])
        it["usada"] = r
        it["usada_txt"] = texto_uso(r, cliente) if r else ""
        it["na_biblioteca"] = it.get("slug") or bib.get(it.get("chave"))
        it["guardando"] = guard.get(it.get("chave"))
    itens.sort(key=lambda i: bool(i.get("usada")))
    return itens


# ───────────────────────── música que já é do cliente e do formato ─────────────────────────
# "A gente tem vários repositórios": cada modelo do cliente guarda faixas em assets/musica e o formato pode trazer
# as dele (banco de música por cliente não existe mais: o que o João gosta vai pro acervo). Antes de procurar fora, isso aparece pra escolher.

def _raiz() -> Path:
    import _comum                                    # lido na hora: os testes trocam a raiz
    return _comum.RAIZ


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(_raiz().resolve()))
    except ValueError:
        return str(p)


def id_faixa(caminho: str) -> str:
    return "m-" + hashlib.sha1(str(caminho).encode("utf-8")).hexdigest()[:10]


def _titulo_arquivo(p: Path) -> str:
    t = re.sub(r"[-_]+", " ", p.stem).strip()
    return (t[:1].upper() + t[1:]) if t else p.name


def _pasta_cliente(cliente: str) -> Path | None:
    nome = (cliente or "").strip()
    base = _raiz() / "clientes"
    if not nome or Path(nome).name != nome or nome.startswith(".") or not base.is_dir():
        return None
    return next((d for d in base.iterdir() if d.is_dir() and d.name.lower() == nome.lower()), None)


def _audios(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.rglob("*") if p.is_file() and p.suffix.lower() in (".mp3", ".wav")
                  and not any(x.startswith((".", "_sandbox")) for x in p.relative_to(pasta).parts))


CLIMAS_NOME = (("tens", "tensa"), ("suspen", "suspense"), ("epic", "épica"), ("cine", "cinematográfica"),
               ("hope", "esperançosa"), ("happ", "animada"), ("calm", "calma"), ("minimal", "calma"),
               ("pulse", "pulsante"), ("build", "crescente"), ("doc", "documental"), ("corp", "corporativa"),
               ("sad", "triste"), ("dark", "sombria"))


def _clima_do_nome(p: Path) -> str:
    """Clima que o nome do arquivo entrega (bed-tensao → tensa). Vazio quando o nome não diz nada."""
    nome = _norm(p.stem)
    return next((c for k, c in CLIMAS_NOME if k in nome), "")


def _faixa_local(p: Path, fonte: str, motivo: str, **extra) -> dict:
    r = _rel(p)
    return {"fonte": fonte, "id": id_faixa(r), "chave": "arquivo:" + r, "tipo": "musica", "titulo": _titulo_arquivo(p),
            "autor": "", "arquivo": r, "clip_rel": r, "inicio_s": None, "fim_s": None, "motivo": motivo,
            "licenca": "", "aviso_licenca": "", "tags": [], "clima": _clima_do_nome(p), **extra}


def do_formato(formato: str | None, tipo: str = "musica") -> list[dict]:
    """formatos/<f>/base/audio/musicas (ou audio/sfx, pra efeito): as faixas que o formato traz. O catalogo.json
    (nessa pasta ou em audio/) diz nome, clima, energia, BPM e status; rejeitada pelo João ou drone não aparece."""
    if not formato or Path(formato).name != formato:
        return []
    sfx = tipo == "sfx"
    base = _raiz() / "formatos" / formato / "base"
    pasta = base / "audio" / ("sfx" if sfx else "musicas")
    if not pasta.is_dir():
        solto = base / "audio"                  # formato com o mp3 direto em audio/ (sem subpasta de música)
        if sfx or not solto.is_dir() or not any(f.suffix.lower() in (".mp3", ".wav") for f in solto.iterdir() if f.is_file()):
            return []
        pasta = solto
    cat = ler_json(pasta / "catalogo.json", None) or ler_json(base / "audio" / "catalogo.json", {}) or {}
    lista = cat if isinstance(cat, list) else (cat.get("musicas") or cat.get("faixas") or [])
    licenca = cat.get("licenca", "") if isinstance(cat, dict) else ""
    por = {}
    for x in lista:
        if isinstance(x, dict):
            arq = str(x.get("arquivo") or "").strip()
            for k in (arq, Path(arq).name, str(x.get("id") or "")):
                if k:
                    por.setdefault(k, x)
    out = []
    achados = [p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in (".mp3", ".wav")] if pasta.name == "audio" else _audios(pasta)
    for p in sorted(achados):
        c = {} if sfx else (por.get(str(p.relative_to(base))) or por.get(p.name) or por.get(p.stem) or {})
        if c.get("status") == "rejeitada" or c.get("drone") is True:
            continue
        sobre = ", ".join(str(v) for v in (c.get("clima"), f"energia {c['energia']}" if c.get("energia") else "",
                                            f"{round(c['bpm'])} BPM" if isinstance(c.get("bpm"), (int, float)) else "") if v)
        it = _faixa_local(p, "formato", c.get("motivo") or ("Do formato" + (f": {sobre}" if sobre else "")),
                          tipo="sfx" if sfx else "musica", inicio_s=c.get("inicio_s"), fim_s=c.get("fim_s"),
                          licenca=c.get("licenca") or licenca, formato=formato)
        if c.get("clima"):
            it["clima"] = c["clima"]
        if isinstance(c.get("duracao_s"), (int, float)):
            it["duracao_txt"] = _dur_txt(c["duracao_s"])
        nome = c.get("titulo") or c.get("nome")
        it["titulo"] = nome or (f"Mixkit {p.stem}" if p.stem.isdigit() and not sfx else it["titulo"])
        it["tags"] = [t for t in [c.get("clima"), c.get("energia"), *(c.get("tags") or [])] if t][:5]
        out.append(it)
    return sem_reprovadas(out, tipo)


def do_cliente(cliente: str, formato: str | None = None, tipo: str = "musica") -> list[dict]:
    """Músicas (ou efeitos, com tipo="sfx") que já são do cliente: clientes/<C>/*Content/modelos/*/assets/musica/**
    (assets/sfx). Só leitura e só desse cliente (nunca devolve faixa de outro).
    Com `formato`, as do formato vêm depois das dele."""
    sfx = tipo == "sfx"
    out, vistos = [], set()
    cdir = _pasta_cliente(cliente)
    for content in sorted(d for d in (cdir.iterdir() if cdir else []) if d.is_dir() and d.name.endswith("Content")):
        modelos = sorted(m for m in (content / "modelos").glob("*") if m.is_dir() and not m.name.startswith(("_", ".")))
        pastas = [(m / "assets" / ("sfx" if sfx else "musica"), m.name, f"Do {cdir.name}, modelo {m.name}") for m in modelos]
        for pasta, onde, motivo in pastas:
            for p in _audios(pasta):
                try:
                    k = (p.name.lower(), p.stat().st_size)
                except OSError:
                    continue
                if k not in vistos:                   # a mesma faixa copiada em dois modelos aparece uma vez
                    vistos.add(k)
                    out.append(_faixa_local(p, "cliente", motivo, tipo="sfx" if sfx else "musica", modelo=onde,
                                            cliente=cdir.name))
    return sem_reprovadas(out, tipo) + do_formato(formato, tipo)


def da_biblioteca(limite: int | None = 60, tipo: str = "musica") -> list[dict]:
    """As músicas (ou efeitos) da Biblioteca (acervo/itens), no mesmo formato de opção."""
    import acervo as _acervo
    out = []
    for it in _acervo.listar(tipo="sfx" if tipo == "sfx" else "musica")[:limite]:
        if not it.get("clip_rel"):
            continue
        out.append({"fonte": "biblioteca", "id": "acervo-" + it["slug"], "slug": it["slug"], "chave": "acervo:" + it["slug"],
                    "tipo": "sfx" if tipo == "sfx" else "musica", "titulo": it.get("titulo") or it["slug"], "autor": it.get("autor", ""),
                    "arquivo": it["clip_rel"], "clip_rel": it["clip_rel"], "inicio_s": None, "fim_s": None,
                    "clima": it.get("clima") or "",
                    "duracao_txt": _dur_txt((it.get("media") or {}).get("duracao")),
                    "motivo": "Da Biblioteca" + (f": {it['como_soa']}" if it.get("como_soa") else ""),
                    "licenca": it.get("licenca", ""), "aviso_licenca": "", "tags": (it.get("tags") or [])[:5],
                    "como_soa": it.get("como_soa", ""), "acervo_slug": it["slug"]})
    return sem_reprovadas(out, tipo)


def fontes_estudio(tipo: str = "musica", termo: str = "") -> dict:
    """TUDO que o Estúdio já tem, por fonte, sem copiar nada: {biblioteca, formatos, clientes}.
    `formatos` e `clientes` são listas planas; cada faixa traz `origem_nome` (o formato ou o cliente), então a tela
    agrupa. A cópia do formato dentro da pasta do cliente (mesmo nome e tamanho) aparece só no formato.
    `termo` filtra pelo nome, clima e tags."""
    tipo = "sfx" if tipo == "sfx" else "musica"
    palavras = [w for w in _norm(termo).split() if w]

    def bate(it):
        blob = _norm(" ".join([it.get("titulo", ""), it.get("clima", "") or "", it.get("motivo", ""),
                               " ".join(it.get("tags") or []), it.get("arquivo", "") or "", it.get("como_soa", "") or ""]))
        return all(w in blob for w in palavras)

    def chave(it):
        try:
            return (Path(it["arquivo"]).name.lower(), (_raiz() / it["arquivo"]).stat().st_size)
        except OSError:
            return (it["arquivo"], 0)

    base = _raiz()
    formatos, vistos = [], set()
    pasta_f = base / "formatos"
    for d in (sorted(pasta_f.iterdir()) if pasta_f.is_dir() else []):
        if d.is_dir() and not d.name.startswith(("_", ".")):
            for it in do_formato(d.name, tipo):
                vistos.add(chave(it))
                formatos.append({**it, "origem_nome": d.name})
    clientes = []
    pasta_c = base / "clientes"
    for d in (sorted(pasta_c.iterdir()) if pasta_c.is_dir() else []):
        if d.is_dir() and not d.name.startswith((".", "_")):
            for it in do_cliente(d.name, None, tipo):
                if chave(it) not in vistos:
                    clientes.append({**it, "origem_nome": d.name})
    return {"biblioteca": [b for b in da_biblioteca(None, tipo) if bate(b)],
            "formatos": [f for f in formatos if bate(f)], "clientes": [c for c in clientes if bate(c)]}


SINONIMOS = {"documentary": "documental sombria tensa", "dark": "sombria escura", "tense": "tensa tensao suspense",
             "calm": "calma", "corporate": "corporativa", "epic": "epica", "upbeat": "animada", "happy": "animada",
             "cinematic": "epica cinematografica", "sad": "triste", "suspense": "tensa", "investigation": "investigativo"}


def _nota(it: dict, clima: str) -> int:
    """Quantas palavras do clima aparecem no nome/tags (pelo começo da palavra: documentary ≈ documental;
    em inglês também vale o sinônimo em português do catálogo: dark ≈ sombria)."""
    palavras = _norm(clima).split()
    palavras += [s for p in palavras for s in SINONIMOS.get(p, "").split()]
    ps = {p[:5] for p in palavras if len(p) >= 3}
    if not ps:
        return 0
    blob = _norm(" ".join([it.get("titulo", ""), it.get("arquivo", ""), " ".join(it.get("tags") or []),
                           it.get("motivo", ""), it.get("como_soa", "") or ""]))
    toks = {t[:5] for t in blob.split()}
    return len(ps & toks)


JANELA_CLIENTE = {"musica": 8, "sfx": 4}      # entregas do mesmo cliente em que a faixa/efeito não se repete
JANELA_GERAL_DIAS = 30                         # uso em OUTROS clientes nesse prazo desce a nota (−2 por uso)


def _chave_do_item(it: dict) -> str:
    try:
        import uso_midia as _uso
        return _uso.chave_de(_raiz() / it["arquivo"]) if it.get("arquivo") else ""
    except Exception:
        return ""


ARQ_REPROVADAS = "acervo/musicas-reprovadas.jsonl"


def _linhas_reprovadas() -> list[dict]:
    arq = _raiz() / ARQ_REPROVADAS
    out = []
    if arq.is_file():
        for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(linha)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
    return out


def reprovadas(cliente: str = "") -> tuple[set, set]:
    """(chaves, nomes de arquivo) das músicas que o João mandou "não usar mais" (acervo/musicas-reprovadas.jsonl): as de cliente "*"
    valem pra todo cliente, as com cliente valem só pra ele. A chave de uma viral é "viral:<slug>"."""
    chaves, nomes = set(), set()
    for r in _linhas_reprovadas():
        if r.get("cliente") in ("*", "", None) or (cliente and r.get("cliente") == cliente):
            chaves.add(r.get("chave")); nomes.add(r.get("arquivo"))
    return chaves - {None, ""}, nomes - {None, ""}


def sem_reprovadas(lista: list[dict], tipo: str = "musica", cliente: str = "") -> list[dict]:
    """Tira da lista as faixas do "Não usar mais" (só música; efeito não tem isso)."""
    if tipo == "sfx" or not lista:
        return lista
    chaves, nomes = reprovadas(cliente)
    if not chaves and not nomes:
        return lista
    return [it for it in lista if not ((str(it.get("arquivo") or it.get("clip_rel") or "") in nomes)
                                       or (Path(str(it.get("arquivo") or it.get("clip_rel") or "x")).name in nomes)   # registro antigo: só o nome do arquivo
                                       or (it.get("chave") and it["chave"] in chaves))]


def reprovada(it: dict, cliente: str = "") -> bool:
    """Essa faixa (opção da tela) está na lista do "Não usar mais"? Compara pelo caminho, pelo nome do arquivo e pela chave."""
    chaves, nomes = reprovadas(cliente)
    arq = str(it.get("arquivo") or it.get("clip_rel") or "")
    return bool((arq and (arq in nomes or Path(arq).name in nomes))
                or (it.get("chave_uso") and it["chave_uso"] in chaves) or (it.get("chave") and it["chave"] in chaves)
                or (it.get("id") and ("viral:" + str(it["id"])) in chaves))


def reprovar(arquivo: str = "", titulo: str = "", chave: str = "", cliente: str = "*", motivo: str = "o João mandou não usar mais") -> dict:
    """"Não usar mais": a faixa nunca mais aparece como opção (uma linha em acervo/musicas-reprovadas.jsonl). O arquivo NÃO é apagado
    (isso é o "Apagar", que manda pra Lixeira do Mac). Pra faixa que está no disco grava também a chave do conteúdo (a mesma faixa
    copiada em outra pasta some junto)."""
    arq = (_raiz() / arquivo) if arquivo else None
    linha = {"cliente": cliente or "*", "chave": chave, "arquivo": arquivo, "titulo": titulo or (Path(arquivo).stem if arquivo else chave),
             "motivo": motivo, "em": agora()}
    if arq and arq.is_file() and not chave:
        try:
            import uso_midia as _uso
            linha["chave"] = _uso.chave_de(arq)
        except Exception:
            pass
    if not (linha["chave"] or linha["arquivo"]):
        raise ValueError("faltou qual faixa")
    if (linha["chave"] and linha["chave"] in reprovadas(cliente)[0]) or (linha["arquivo"] and linha["arquivo"] in reprovadas(cliente)[1]):
        return linha   # já estava na lista
    dest = _raiz() / ARQ_REPROVADAS
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


RAIZES_APAGAR_MUSICA = ("acervo/itens", "formatos", "clientes")


def caminho_apagavel(arquivo: str) -> Path:
    """O arquivo de música que o "Apagar" pode mandar pra Lixeira do Mac: dentro de acervo/itens (leva o item inteiro), formatos/ ou
    clientes/, de áudio, sem atalho. Ou ValueError. Item da Biblioteca (acervo/itens/<slug>/...) vira a pasta do item."""
    raiz = _raiz().resolve()
    p = (raiz / arquivo).resolve() if arquivo else None
    if not p or not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
        raise ValueError("Esse arquivo de música não existe mais.")
    rel = p.relative_to(raiz) if raiz in p.parents else None
    if not rel or not any(str(rel).startswith(r + "/") for r in RAIZES_APAGAR_MUSICA) or "_sandbox-" in str(rel):
        raise ValueError("Só apago música da Biblioteca, dos estilos e dos clientes.")
    if str(rel).startswith("acervo/itens/"):
        return raiz / "acervo" / "itens" / rel.parts[2]
    return p


def apagar_musica(arquivos: list[str], medir: bool = False) -> dict:
    """Manda pra Lixeira do Mac (nunca rm). Devolve {bytes, apagados, recusados: [(nome, motivo)], titulos, lixeiras}. medir=True só mede."""
    import espaco as _es
    r = {"bytes": 0, "apagados": 0, "recusados": [], "titulos": [], "lixeiras": []}
    alvos = {}
    for a in dict.fromkeys(arquivos or []):
        try:
            alvos[caminho_apagavel(a)] = a
        except ValueError as e:
            r["recusados"].append((Path(str(a)).name, str(e)))
    for caminho, a in alvos.items():
        r["bytes"] += _es.tamanho(caminho)
        r["apagados"] += 1
        r["titulos"].append(_titulo_arquivo(_raiz() / a))
    if alvos and not medir:
        res = _es.para_lixeira_mac(list(alvos), "musica-" + (make_slug(r["titulos"][0]) or "faixa"))
        r["lixeiras"].append(res["nome"])
    return r


def _rodizio(cands: list[dict], tipo: str, cliente: str, clima: str, n: int, job: str, ignorar: str = "",
             pedidas: tuple = ()) -> list[dict]:
    """Escolhe `n`: favoritos primeiro; tira o que o cliente usou nas últimas JANELA_CLIENTE[tipo] entregas
    (só a faixa pedida passa; favorito usado na janela vai pro fim, depois das faixas novas); nota do clima − 2 × usos em outros clientes; desempate por sorteio estável do job."""
    import random
    try:
        import uso_midia as _uso
        rec = {u["chave"] for u in _uso.recentes(cliente, tipo, JANELA_CLIENTE[tipo]) if u.get("job") != ignorar} if cliente else set()
        geral = _uso.contagem_geral(tipo, JANELA_GERAL_DIAS, excluir_cliente=cliente)
    except Exception:
        rec, geral = set(), {}
    try:
        import acervo as _acervo
        favs = {i["slug"] for i in _acervo.favoritos(tipo, cliente or None)}
    except Exception:
        favs = set()
    usadas_legado = {Path(r["arquivo"]).name for r in (usadas_recentemente(cliente, ignorar=ignorar) if tipo == "musica" and cliente else [])
                     if r.get("arquivo")}
    rep_chaves, rep_nomes = reprovadas(cliente) if tipo == "musica" else (set(), set())
    pool = []
    for it in cands:
        k = _chave_do_item(it)
        it["chave_uso"] = k
        if tipo == "musica" and ((k and k in rep_chaves) or Path(it.get("arquivo") or "").name in rep_nomes):
            continue   # o João reprovou essa faixa pra esse cliente: nunca volta (nem favorita)
        it["favorita"] = bool(it.get("slug") in favs or it.get("acervo_slug") in favs)
        pedida = bool(k and k in pedidas) or bool(it.get("arquivo") and Path(it["arquivo"]).name in pedidas)
        it["_janela"] = bool(k in rec and not pedida)
        if it["_janela"] and not it["favorita"]:
            continue
        it["nota"] = _nota(it, clima) - 2 * geral.get(k, 0)
        if it["favorita"]:
            it["motivo"] = "♥ favorita. " + (it.get("motivo") or "")
        pool.append(it)
    sorte = lambda c: random.Random(f"{job}|{c.get('chave_uso') or c.get('arquivo')}").random()  # noqa: E731
    ordenar = lambda g: sorted(g, key=lambda c: (-c["nota"], sorte(c)))  # noqa: E731
    fav_na_frente = lambda c: c["favorita"] and not c["_janela"]  # noqa: E731
    out = ordenar([c for c in pool if fav_na_frente(c)])[:n]
    grupos = [ordenar([c for c in pool if c["fonte"] == f and not fav_na_frente(c) and not c["_janela"] and not c.get("usada")])
              for f in ("cliente", "biblioteca", "formato")]
    while any(grupos) and len(out) < n:
        for g in grupos:
            if g and len(out) < n:
                out.append(g.pop(0))
    resto = [c for c in pool if (c.get("usada") or c["_janela"]) and not fav_na_frente(c) and c not in out]
    out += ordenar(resto)[:max(0, n - len(out))]
    return out[:max(0, int(n))]


def opcoes(cliente: str, clima: str = "", n: int = 3, ignorar: str = "", formato: str | None = None,
           job: str = "", pedidas: tuple = ()) -> list[dict]:
    """Até `n` músicas pra um vídeo, sem sair do computador: cliente → Biblioteca → formato, as que batem
    com o clima primeiro (o Mixkit fica pra busca da tela, que precisa de internet).
    Rodízio (G12): favoritas primeiro (se fora da janela); some o que o cliente usou nas últimas 8 entregas (acervo/usos.jsonl);
    o uso em outros clientes desce a nota; o empate é sorteado por vídeo, pra não sair sempre a mesma."""
    cands = do_cliente(cliente, formato) + da_biblioteca()
    recentes = usadas_recentemente(cliente, ignorar=ignorar) if cliente else []
    por_nome = {Path(r["arquivo"]).name: r for r in recentes if r.get("arquivo")}
    marcar(cands, recentes, cliente)
    for it in cands:
        r = it.get("usada") or por_nome.get(Path(it.get("arquivo") or "").name)
        it["usada"] = r
        it["usada_txt"] = f"já usada em “{r.get('job_titulo') or r.get('job')}”" if r else ""
    return _rodizio(cands, "musica", cliente, clima, int(n), job or ignorar, ignorar, tuple(pedidas))


def sfx_do_papel(papel: str, cliente: str = "", job: str = "", base: Path | None = None) -> Path | None:
    """Pro motor que põe efeito sozinho: a variante menos usada em `base/audio/sfx/<papel>/` (a 1ª da pasta é a original;
    sem subpasta, vale o arquivo solto antigo `<papel>.mp3`)."""
    import random
    pasta = Path(base) if base else None
    if not pasta:
        return None
    var = sorted(p for p in (pasta / papel).glob("*") if p.suffix.lower() in AUDIO_EXTS) if (pasta / papel).is_dir() else []
    solto = next((pasta / f"{papel}{e}" for e in AUDIO_EXTS if (pasta / f"{papel}{e}").is_file()), None)
    if not var:
        return solto
    try:
        import uso_midia as _uso
        usos = [u["chave"] for u in _uso.recentes(cliente, "sfx", JANELA_CLIENTE["sfx"])] if cliente else []
        def peso(p):
            try:
                return usos.count(_uso.chave_de(p))
            except OSError:
                return 0
    except Exception:
        peso = lambda p: 0  # noqa: E731
    return sorted(var, key=lambda p: (peso(p), random.Random(f"{job}|{p.name}").random()))[0]


# ───────────────────────── a música de UM vídeo (tela do job) ─────────────────────────

CLIMA_FORMATO = {"documentario": "documentary", "fala-com-cenas": "cinematic"}
CAMPOS_OPCAO = ("id", "titulo", "motivo", "arquivo", "previa", "inicio_s", "fim_s", "fonte", "url", "autor",
                "licenca", "acervo_slug", "usada_txt", "trechos", "favorita")


def _local(caminho, sandbox: str) -> str:
    """Caminho de uma faixa do plano → relativo à raiz, se o arquivo existir (o plano grava às vezes
    relativo à sandbox, às vezes à raiz)."""
    c = str(caminho or "").strip()
    if not c or c.startswith(("http://", "https://")):
        return ""
    raiz = _raiz().resolve()
    for base in ([raiz / sandbox] if sandbox else []) + [raiz]:
        p = (base / c).resolve()
        try:
            p.relative_to(raiz)
        except ValueError:
            continue
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            return _rel(p)
    return ""


def _opcao_do_plano(o: dict, sandbox: str, padrao: str) -> dict | None:
    arq = _local(o.get("arquivo") or o.get("opcao") or o.get("clip_rel"), sandbox)
    previa = next((str(o[k]) for k in ("previa", "baixar") if str(o.get(k) or "").startswith("https://")), "")
    if not arq and not previa:
        return None
    titulo = o.get("titulo") or (_titulo_arquivo(Path(arq)) if arq else "Faixa sugerida")
    trechos = [t for t in o.get("trechos") or [] if isinstance(t, dict) and t.get("arquivo")]
    return {"id": str(o.get("id") or padrao), "titulo": titulo, "motivo": o.get("motivo") or "",
            "arquivo": arq, "previa": previa, "inicio_s": o.get("inicio_s"), "fim_s": o.get("fim_s"),
            "fonte": o.get("fonte") or o.get("origem") or "plano", "url": o.get("url") or "",
            "autor": o.get("autor") or "", "licenca": o.get("licenca") or "", "acervo_slug": o.get("acervo_slug"),
            "usada_txt": "", "trechos": trechos if len(trechos) > 1 else None}


def _trechos_do_motor(job: dict) -> list[dict]:
    """A música do cenas.json da sandbox (formato com motor, ex.: documentário) quando ela troca de faixa no meio:
    [{arquivo, inicio_s, de}, ...] com 2 trechos ou mais; senão []. É o que toca na previa-som.m4a.
    Se o qa/checagem.json do --storyboard tiver os mesmos trechos, cada um ganha também o "ate" (pra tela mostrar
    "de 0:00 até 1:17"); o "ate" é só pra mostrar, nunca vai pro PLANO."""
    sb = _raiz() / job.get("sandbox", "")
    try:
        cenas = json.loads((sb / "cenas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    m = cenas.get("musica") if isinstance(cenas, dict) else None
    segs = [t for t in m if isinstance(t, dict) and t.get("arquivo")] if isinstance(m, list) else []
    if len(segs) < 2:
        return []
    out = [{k: t[k] for k in ("arquivo", "inicio_s", "de") if k in t} for t in segs]
    try:
        ch = json.loads((sb / "qa" / "checagem.json").read_text(encoding="utf-8"))
        tr = [x for x in ((ch.get("numeros") or {}).get("musica") or {}).get("trechos") or [] if isinstance(x, dict)]
    except (OSError, ValueError, AttributeError):
        tr = []
    try:
        mesmos = len(tr) == len(out) and all(
            Path(str(a.get("arquivo"))).stem == Path(str(b.get("arquivo"))).stem
            and abs(float(a.get("de") or 0) - float(b.get("de") or 0)) <= .6 for a, b in zip(tr, out))
        if mesmos and all(a.get("ate") is not None for a in tr):
            for a, b in zip(tr, out):
                b["ate"] = float(a["ate"])
    except (TypeError, ValueError):
        pass
    return out


def _mmss(s) -> str:
    s = int(round(float(s or 0)))
    return f"{s // 60}:{s % 60:02d}"


def _amarrar_trechos(job: dict, lista: list[dict], nomes: dict | None = None) -> None:
    """O PLANO do Vídeo 1 V2 do Cliente4 tinha m1 = 364 até 1:17, m2 = 1154 como alternativa, e o cenas.json tocava as
    duas (364 → 1154). Na tela era uma escolha só, e aprovar m1 renderizaria só a 364. A opção cuja faixa é a do
    primeiro trecho do cenas.json leva os trechos (e a tela mostra a troca, com de e até quando o motor já mediu)."""
    segs = _trechos_do_motor(job)
    if not segs:
        return
    stem = Path(str(segs[0]["arquivo"])).stem
    op = next((x for x in lista if not x.get("trechos") and x.get("arquivo") and Path(x["arquivo"]).stem == stem), None)
    if op:
        op["trechos"] = [{k: t[k] for k in ("arquivo", "inicio_s", "de") if k in t} for t in segs]
    ates = [t["ate"] for t in segs] if all("ate" in t for t in segs) else None
    for x in lista:
        if x.get("trechos"):
            nome = lambda st: ((next((y for y in lista if y.get("arquivo") and Path(y["arquivo"]).stem == st), None) or {}).get("titulo")
                               or (nomes or {}).get(st) or st)
            tr = x["trechos"]
            if ates and len(tr) == len(segs) and all(Path(str(a.get("arquivo"))).stem == Path(str(b["arquivo"])).stem
                                                     for a, b in zip(tr, segs)):
                partes = [f"de {_mmss(tr[0].get('de'))} até {_mmss(ates[0])}"]
                partes += [f"{nome(Path(str(t['arquivo'])).stem)} de {_mmss(t.get('de'))} até {_mmss(a)}"
                           for t, a in zip(tr[1:], ates[1:])]
                x["troca_txt"] = "toca " + partes[0] + ", depois " + ", depois ".join(partes[1:])
            else:
                trocas = [f"{nome(Path(str(t['arquivo'])).stem)} em {_mmss(round(float(t.get('de') or 0)))}" for t in tr[1:]]
                x["troca_txt"] = "troca pra " + ", depois ".join(trocas)


def _musica(plano: dict | None) -> dict:
    m = (plano or {}).get("musica")
    if isinstance(m, list):
        m = next((x for x in m if isinstance(x, dict)), {})
    if isinstance(m, str):
        m = {"opcao": m} if m.strip() else {}
    return m if isinstance(m, dict) else {}


def opcoes_do_plano(job: dict, plano: dict | None, n: int = 3, formato: str | None = None) -> dict:
    """O bloco Música da tela: as faixas do plano (a da IA e as alternativas dela) e, até completar `n`,
    as do formato/cliente/Biblioteca. Devolve {opcoes, escolha ('sem' | id), clima}."""
    m = _musica(plano)
    sb = job.get("sandbox", "")
    lista = []
    sem = bool(m.get("sem")) or m.get("escolha") == {"sem": True}
    esc = m.get("escolha") if isinstance(m.get("escolha"), str) else ""
    principal = None if sem else _opcao_do_plano(m, sb, esc or "plano")
    if principal:
        principal["motivo"] = principal["motivo"] or "A escolha da IA pra este vídeo"
        lista.append(principal)
    for i, o in enumerate(m.get("opcoes") or [], 1):
        x = _opcao_do_plano(o, sb, f"plano-{i}") if isinstance(o, dict) else None
        if x and not any(x["id"] == y["id"] or (x["arquivo"] and x["arquivo"] == y["arquivo"]) for y in lista):
            lista.append(x)
    escolha = "sem" if sem else (esc or (principal or {}).get("id") or "")
    clima = str(m.get("clima") or "").strip() or CLIMA_FORMATO.get(formato or "", "cinematic")
    if len(lista) < n:
        pedidas = tuple(str(x) for x in (m.get("arquivo"), m.get("opcao")) if x and m.get("pedida_pelo_joao"))
        for e in opcoes(job.get("cliente", ""), clima, n=n + 6, ignorar=job.get("slug", ""), formato=formato,
                        job=job.get("slug", ""), pedidas=pedidas):
            if len(lista) >= n:
                break
            if not any(e["arquivo"] == y["arquivo"] or e["id"] == y["id"] for y in lista):
                lista.append({k: e.get(k) for k in CAMPOS_OPCAO})
    if len(lista) > n:                                   # a escolhida nunca some da tela
        fica = lista[:n]
        esc = next((x for x in lista if x["id"] == escolha), None)
        if esc and esc not in fica:
            fica[-1] = esc
        lista = fica
    for x in lista:
        x.setdefault("previa", "")
    # faixa do catálogo do formato com o nome dela, não o número do arquivo ("1154" → "Reaching Out")
    nomes = {Path(f["arquivo"]).stem: f["titulo"] for f in do_formato(formato)} if formato else {}
    for x in lista:
        st = Path(str(x.get("arquivo") or "")).stem
        if st in nomes and x.get("titulo") in (st, f"Mixkit {st}"):
            x["titulo"] = nomes[st]
    _amarrar_trechos(job, lista, nomes)
    return {"opcoes": lista, "escolha": escolha, "clima": clima}


def aplicar_no_plano(plano: dict, musica: dict | None = None, sfx: dict | None = None) -> dict:
    """Grava no PLANO a escolha da tela.
    musica: {'sem': True} ou a opção escolhida (vira a música do vídeo; a anterior fica nas alternativas).
    sfx: {'ligado': bool, 'ativos': [ids]} — chave geral e cada efeito.
    Mesmo formato do producao.aprovar_plano: musica.escolha = id (ou {'sem': True}), musica.opcoes = todas."""
    if musica is not None:
        velho = _musica(plano)
        guardadas = [o for o in velho.get("opcoes") or [] if isinstance(o, dict)]
        esc = velho.get("escolha") if isinstance(velho.get("escolha"), str) else ""
        if not velho.get("sem") and any(velho.get(k) for k in ("opcao", "arquivo", "previa", "url", "titulo")):
            atual = {k: v for k, v in velho.items() if k not in ("opcoes", "escolha", "sem", "clima")}
            atual["id"] = atual.get("id") or esc or "plano"
            if not any(o.get("id") == atual["id"] for o in guardadas):
                guardadas.insert(0, atual)
        extra = {"clima": velho["clima"]} if velho.get("clima") else {}
        if musica.get("sem"):
            plano["musica"] = {"sem": True, "escolha": {"sem": True}, "opcoes": guardadas, **extra}
        else:
            nova = {k: v for k, v in musica.items() if k not in ("opcoes", "sem", "usada_txt") and v not in (None, "")}
            if nova.get("arquivo"):
                nova.setdefault("opcao", nova["arquivo"])
            nova["escolha"] = nova.get("id")
            outras = [o for o in guardadas if o.get("id") != nova.get("id")]
            item = {k: v for k, v in nova.items() if k != "escolha"}
            plano["musica"] = {**nova, "opcoes": [item] + outras, **extra}
    if sfx is not None:
        ativos = set(sfx.get("ativos") or [])
        for i, o in enumerate(plano.get("sfx") if isinstance(plano.get("sfx"), list) else []):
            if isinstance(o, dict):
                o["ligado"] = (o.get("id") or f"sfx-{i}") in ativos
        plano["sfx_ligado"] = bool(sfx.get("ligado", True))
    return plano


MOTOR_SONS = {"typing", "key-press", "whoosh-short", "click-soft", "pop", "tique"}   # os sons do motor do documentário


def _sfx_do_motor(job: dict, o: dict) -> str:
    """O som pelo nome do motor ("tique", "whoosh-short"): audio/sfx/<som>.mp3 da sandbox ou da base do formato.
    O PLANO do Vídeo 1 V2 do Cliente4 apontava audio/sfx/tique.mp3, que a sandbox não tinha, e o ▶ sumia."""
    formato = str(job.get("formato") or "")
    for som in (o.get("som"), o.get("id")):
        som = str(som or "").strip()
        if not re.fullmatch(r"[\w-]+", som):
            continue
        cands = [(f"audio/sfx/{som}.mp3", job.get("sandbox", ""))]
        if re.fullmatch(r"[\w-]+", formato):
            cands.append((f"formatos/{formato}/base/audio/sfx/{som}.mp3", ""))
        for cand, base in cands:
            achado = _local(cand, base)
            if achado:
                return achado
    return ""


def _sons_das_cenas(job: dict) -> set[str] | None:
    """Os sons que as cenas do motor pedem (qa/checagem.json do --storyboard → efeitos.sons_das_cenas), ligados ou não.
    None = não dá pra saber (formato sem motor, storyboard antigo): a tela mostra todos."""
    try:
        d = json.loads((_raiz() / job.get("sandbox", "") / "qa" / "checagem.json").read_text(encoding="utf-8"))
        sons = ((d.get("numeros") or {}).get("efeitos") or {}).get("sons_das_cenas")
    except (OSError, ValueError, AttributeError):
        return None
    return set(sons) if isinstance(sons, list) else None


def efeitos_do_plano(job: dict, plano: dict | None) -> dict:
    """O bloco Efeitos: {ligado, itens: [{id, titulo, arquivo, em, ligado}]}. Com o motor, só os sons que as cenas
    usam: o V2 do Cliente4 mostrava "Tique do relógio" num vídeo sem relógio."""
    p = plano or {}
    itens = []
    usados = _sons_das_cenas(job)
    for i, o in enumerate(p.get("sfx") if isinstance(p.get("sfx"), list) else []):
        if not isinstance(o, dict):
            continue
        if usados is not None and str(o.get("som") or o.get("id") or "") in MOTOR_SONS and str(o.get("som") or o.get("id")) not in usados:
            continue
        arq = _local(o.get("arquivo") or o.get("opcao") or o.get("clip_rel"), job.get("sandbox", "")) or _sfx_do_motor(job, o)
        nome = (o.get("titulo") or o.get("nome") or o.get("som")
                or (_titulo_arquivo(Path(arq)) if arq else f"Efeito {i + 1}"))
        em = next((o[k] for k in ("em", "t", "inicio_s", "inicio") if isinstance(o.get(k), (int, float))), None)
        itens.append({"id": o.get("id") or f"sfx-{i}", "titulo": nome, "arquivo": arq, "em": em,
                      "motivo": o.get("motivo") or o.get("onde") or "", "ligado": o.get("ligado", True) is not False})
    return {"ligado": p.get("sfx_ligado", True) is not False, "itens": itens}


def baixar_externa(audio: str, sandbox: str, fonte: str, titulo: str = "", pagina: str = "") -> Path:
    """Baixa SÓ a faixa escolhida pra <sandbox>/work/musica/externa (não passa pela Biblioteca)."""
    raiz = _raiz().resolve()
    destino = (raiz / sandbox / "work" / "musica" / "externa").resolve()
    try:
        destino.relative_to(raiz)
    except ValueError:
        raise ValueError("sandbox fora do Estúdio") from None
    ensure(destino)
    nome = make_slug(titulo or "") if titulo else re.sub(r"[^\w-]+", "-", _chave(audio or pagina))[:60]
    final = destino / f"{nome or now_slug()}.mp3"
    if final.is_file() and final.stat().st_size > 1024:
        return final
    final = _conferida(_baixar_externa_sem_checar(audio, fonte, pagina, final), fonte, titulo)
    return final


def _conferida(arq: Path, fonte: str, titulo: str = "") -> Path:
    """Toda faixa nova passa pela checagem antes de virar opção (marca d'água: voz falada que não é a letra, bip, silêncio no meio).
    Mixkit é instrumental: qualquer fala reprova. Reprovada: o arquivo vai pra .lixeira do Estúdio e o João vê o motivo."""
    import musica_viral as _mv
    try:
        r = _mv.checar(arq, "instrumental" if fonte == "mixkit" else "letra", 0.0, 75.0, titulo=titulo)
    except Exception:
        return arq   # sem checador (rede, ffmpeg): não trava, e a faixa fica sem o selo
    if not r["ok"]:
        try:
            from _comum import lixeira_guardar
            lixeira_guardar({"item": arq}, {"tipo": "musica-reprovada", "rotulo": arq.name, "cliente": "(música)", "modelo": "checagem",
                                           "item": arq.name, "titulo": titulo or arq.stem, "motivo": "; ".join(r["motivos"])})
        except Exception:
            pass
        raise ValueError("Essa faixa tem marca d'água ou defeito e não vira opção: " + "; ".join(r["motivos"]))
    return arq


def _baixar_externa_sem_checar(audio: str, fonte: str, pagina: str, final: Path) -> Path:
    if fonte in VIA_YTDLP:
        if not _host_ok(pagina, fonte):
            raise ValueError(f"link do {fonte} inválido")
        import musica as _mus
        tmpd = ensure(TMP / "baixando" / now_slug())
        mp3, _ = _mus.baixar(pagina, tmpd)
        if not mp3:
            raise RuntimeError(f"não consegui baixar o áudio do {fonte}")
        shutil.move(str(mp3), str(final))
        shutil.rmtree(tmpd, ignore_errors=True)
        return final
    if fonte not in HOSTS or not _host_ok(audio, fonte):
        raise ValueError(f"link de áudio inválido para {fonte}")
    return _baixar(audio, final)


# ───────────────────────── guardar na Biblioteca ─────────────────────────

def _arq_estado(chave: str) -> Path:
    return ensure(TMP) / (re.sub(r"[^\w.-]+", "_", chave)[:120] + ".json")


def _estado(chave: str, **campos) -> None:
    if chave:
        p = _arq_estado(chave)
        d = ler_json(p, {}) or {}
        d.update(campos, chave=chave, em=agora())
        gravar_json(p, d)


def _vivo(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def guardando() -> dict:
    """{chave: estado} das faixas sendo baixadas agora ou que deram erro na última hora."""
    out = {}
    if not TMP.is_dir():
        return out
    for p in TMP.glob("*.json"):
        d = ler_json(p, {}) or {}
        if d.get("estado") == "baixando" and d.get("pid") and not _vivo(d["pid"]):
            d.update(estado="erro", erro="parou no meio (o Estúdio foi reiniciado?)")
        if d.get("estado") == "baixando" or (d.get("estado") == "erro" and time.time() - p.stat().st_mtime < 3600):
            out[d.get("chave", "")] = d
    return out


def _baixar(url: str, destino: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    total = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        while True:
            bloco = r.read(1 << 16)
            if not bloco:
                break
            total += len(bloco)
            if total > LIMITE_MB * 1024 * 1024:
                raise ValueError(f"arquivo maior que {LIMITE_MB} MB")
            f.write(bloco)
    if total < 1024:
        raise ValueError("o arquivo baixado veio vazio")
    return destino


def guardar(fonte: str, url: str, audio: str = "", titulo: str = "", autor: str = "", licenca: str = "",
            tags: str = "", tipo: str = "musica", termo: str = "", duracao: float | None = None,
            aviso_licenca: str = "") -> dict:
    """Baixa a faixa e guarda na Biblioteca pelo caminho de sempre (acervo.adicionar_arquivo):
    mede BPM/LUFS/trechos e a IA descreve. YouTube baixa só o áudio (musica.baixar)."""
    import acervo as _acervo
    if fonte not in HOSTS:
        raise ValueError("fonte desconhecida")
    chave = _chave(url) or _chave(audio)
    _estado(chave, estado="baixando", titulo=titulo, fonte=fonte, pid=os.getpid())
    try:
        tipo = "sfx" if tipo == "sfx" else "musica"
        busca = {"fonte": fonte, "chave": chave, "termo": termo, "url": url, "guardado_em": agora()}
        obs = f"Achada na busca de música ({fonte}, termo: “{termo}”)." + (f" {aviso_licenca}" if aviso_licenca else "")
        credito = f"{titulo} — {autor} ({url})" if autor else f"{titulo} ({url})"
        extra = {"tipo": tipo, "busca": busca, "credito": credito}
        tmpd = ensure(TMP / "baixando" / (make_slug(titulo) or now_slug()))
        if fonte in VIA_YTDLP:
            nome_fonte = "YouTube" if fonte == "youtube" else "SoundCloud"
            if not _host_ok(url, fonte):
                raise ValueError(f"link do {nome_fonte} inválido")
            if duracao and float(duracao) > LIMITE_YT_S:
                raise ValueError(f"faixa longa demais (compilação): abra no {nome_fonte} e escolha uma faixa curta")
            import musica as _mus
            mp3, info = _mus.baixar(url, tmpd)
            if not mp3:
                raise RuntimeError(f"não consegui baixar o áudio do {nome_fonte}")
            extra[fonte] = info
            if tipo == "musica":
                mp3 = _conferida(mp3, fonte, titulo or info.get("titulo") or "")
            meta = _acervo.adicionar_arquivo(mp3, titulo or info.get("titulo") or mp3.stem, tags,
                                             fonte=info.get("url") or url, autor=info.get("canal") or autor,
                                             licenca=licenca or f"Direitos do autor ({nome_fonte}): referência e teste",
                                             observacao=obs, origem_tipo=f"{fonte}-audio", mover=True, extra=extra)
        else:
            if not _host_ok(audio, fonte):
                raise ValueError(f"link de áudio inválido para {fonte}")
            arq = _baixar(audio, tmpd / "audio.mp3")
            if tipo == "musica":
                arq = _conferida(arq, fonte, titulo)
            meta = _acervo.adicionar_arquivo(arq, titulo or arq.stem, tags, fonte=url, autor=autor, licenca=licenca,
                                             observacao=obs, origem_tipo=fonte, mover=True, extra=extra)
        shutil.rmtree(tmpd, ignore_errors=True)
        _estado(chave, estado="pronto", slug=meta["slug"])
        return meta
    except Exception as e:
        _estado(chave, estado="erro", erro=str(e)[:300])
        raise


def disparar_guardar(dados: dict) -> str:
    """Roda o `guardar` em processo separado (baixar + medir leva um ou dois minutos). Devolve a chave."""
    chave = _chave(dados.get("url", "")) or _chave(dados.get("audio", ""))
    cmd = [sys.executable, str(Path(__file__).resolve()), "guardar"]
    for k in ("fonte", "url", "audio", "titulo", "autor", "licenca", "tags", "tipo", "termo", "duracao", "aviso_licenca"):
        if dados.get(k) not in (None, ""):
            cmd += [f"--{k}", str(dados[k])]
    _estado(chave, estado="baixando", titulo=dados.get("titulo", ""), fonte=dados.get("fonte", ""), pid=None)
    log = open(ensure(TMP) / "ultimo.log", "ab")
    proc = subprocess.Popen(cmd, cwd=str(ACERVO.parent.parent), start_new_session=True,
                            stdout=log, stderr=subprocess.STDOUT)
    log.close()
    _estado(chave, pid=proc.pid)
    return chave


# ───────────────────────── status e chaves ─────────────────────────

def status() -> dict:
    e = _voz._env()
    fontes = []
    for f in FONTES:
        x = dict(f)
        if f["env"]:
            x["chave_salva"] = bool((e.get(f["env"]) or "").strip())
            x["ligado"] = x["chave_salva"]
            x["estado"] = "ligado" if x["ligado"] else "falta a chave"
        elif f["id"] in ("mixkit", "openverse"):
            x["chave_salva"] = None
            x["ligado"] = True
            x["estado"] = "ligado, sem chave"
        else:
            x["chave_salva"] = None
            x["ligado"] = bool(_ytdlp())
            x["estado"] = "ligado, sem chave" if x["ligado"] else "yt-dlp não instalado"
        fontes.append(x)
    try:
        locais = {k: {n: len(v) for n, v in fontes_estudio(k).items()} for k in ("musica", "sfx")}
    except Exception:
        locais = {}
    return {"fontes": fontes, "por_id": {f["id"]: f for f in fontes}, "ligadas": sum(1 for f in fontes if f["ligado"]),
            "locais": locais}


def salvar_chaves(jamendo: str = "", freesound: str = "") -> list[str]:
    novos = {}
    if (jamendo or "").strip():
        novos["JAMENDO_CLIENT_ID"] = jamendo.strip()
    if (freesound or "").strip():
        novos["FREESOUND_API_KEY"] = freesound.strip()
    if novos:
        _voz._gravar_env(novos)
    return ["Jamendo" if k.startswith("JAMENDO") else "Freesound" for k in novos]


def sites_manuais(termo: str = "", tipo: str = "musica") -> list[dict]:
    q = urllib.parse.quote(termo.strip()) if termo else ""
    out = []
    for s in SITES_MANUAIS:
        link = s.get("sfx" if tipo == "sfx" else "musica") or s["musica"]
        if "{q}" in link:
            link = link.replace("{q}", q) if q else re.sub(r"(search/?\?[^=]+=|search/)?\{q\}/?$", "", link)
        out.append({"nome": s["nome"], "paga": s["paga"], "link": link})
    return out


# ───────────────────────── CLI ─────────────────────────

def _imprimir(g: dict) -> None:
    print(f"── {g['nome']}" + (f" (procurei: {g['procurei']})" if g.get("procurei") else ""))
    if g.get("aviso"):
        print("   aviso:", g["aviso"])
    for i, it in enumerate(g["itens"], 1):
        print(f" {i:2d}. {it['titulo']} — {it.get('autor') or '?'} · {it.get('duracao_txt') or '?'} · {it.get('licenca') or ''}")
        print(f"     página: {it.get('url')}")
        if it.get("baixar"):
            print(f"     mp3:    {it['baixar']}")
        if it.get("aviso_licenca"):
            print(f"     licença: {it['aviso_licenca']}")


def main():
    ap = argparse.ArgumentParser(description="Busca música e efeito sonoro (YouTube, Jamendo, Freesound)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("youtube", "jamendo", "freesound"):
        p = sub.add_parser(nome)
        p.add_argument("termo")
        p.add_argument("--n", type=int, default=8)
        p.add_argument("--pagina", type=int, default=1)
    b = sub.add_parser("buscar")
    b.add_argument("termo"); b.add_argument("--tipo", default="musica", choices=["musica", "sfx"])
    b.add_argument("--cliente", default=""); b.add_argument("--pagina", type=int, default=1)
    b.add_argument("--instrumental", action="store_true")
    b.add_argument("--fonte", default="", choices=["", "virais", "mixkit", "soundcloud", "jamendo", "freesound", "youtube", "openverse"])
    b.add_argument("--n", type=int, default=8)
    dc = sub.add_parser("do-cliente")
    dc.add_argument("cliente"); dc.add_argument("--formato", default="")
    fe = sub.add_parser("fontes")
    fe.add_argument("--tipo", default="musica", choices=["musica", "sfx"]); fe.add_argument("--termo", default="")
    op = sub.add_parser("opcoes")
    op.add_argument("cliente"); op.add_argument("--clima", default=""); op.add_argument("--n", type=int, default=3)
    op.add_argument("--ignorar", default=""); op.add_argument("--formato", default="")
    bx = sub.add_parser("baixar")
    bx.add_argument("audio", help="link direto do mp3 (Mixkit/Jamendo/Freesound) ou a página (YouTube/SoundCloud)")
    bx.add_argument("--sandbox", required=True); bx.add_argument("--fonte", required=True)
    bx.add_argument("--titulo", default="")
    r = sub.add_parser("recentes")
    r.add_argument("cliente"); r.add_argument("--n", type=int, default=5); r.add_argument("--ignorar", default="")
    sub.add_parser("status")
    g = sub.add_parser("guardar")
    for k in ("fonte", "url", "audio", "titulo", "autor", "licenca", "tags", "tipo", "termo", "aviso_licenca"):
        g.add_argument(f"--{k}", default="")
    g.add_argument("--duracao", type=float, default=None)
    a = ap.parse_args()

    if a.cmd == "youtube":
        _imprimir(buscar_youtube(a.termo, a.n, a.pagina))
    elif a.cmd == "jamendo":
        _imprimir(buscar_jamendo(a.termo, a.n, a.pagina))
    elif a.cmd == "freesound":
        _imprimir(buscar_freesound(a.termo, a.n, a.pagina))
    elif a.cmd == "buscar" and a.fonte:
        rec = usadas_recentemente(a.cliente) if a.cliente else []
        g = buscar_fonte(a.fonte, a.termo, a.tipo, a.n, a.pagina)
        marcar(g["itens"], rec, a.cliente)
        for it in g["itens"]:
            if it.get("usada"):
                it["titulo"] += f"  ⚠ {it['usada_txt']}"
        _imprimir(g)
    elif a.cmd == "do-cliente":
        itens = do_cliente(a.cliente, a.formato or None)
        if not itens:
            print(f"Nenhuma música guardada no {a.cliente} (assets/musica dos modelos).")
        for it in itens:
            print(f"  · {it['titulo']}  [{it.get('modelo') or it['fonte']}]  {it['arquivo']}")
    elif a.cmd == "fontes":
        f = fontes_estudio(a.tipo, a.termo)
        for nome in ("biblioteca", "formatos", "clientes"):
            print(f"── {nome} ({len(f[nome])})")
            for it in f[nome]:
                print(f"  · {it['titulo']}  [{it.get('origem_nome') or 'Biblioteca'}]  {it.get('clima') or ''}  {it['arquivo']}")
    elif a.cmd == "opcoes":
        for it in opcoes(a.cliente, a.clima, a.n, a.ignorar, a.formato or None):
            print(f"  · {it['titulo']} ({it['fonte']}) {it['arquivo']}" + (f"  ⚠ {it['usada_txt']}" if it["usada_txt"] else ""))
    elif a.cmd == "baixar":
        fonte = a.fonte
        print(baixar_externa(a.audio if fonte not in VIA_YTDLP else "", a.sandbox, fonte, a.titulo,
                             pagina=a.audio if fonte in VIA_YTDLP else ""))
    elif a.cmd == "buscar":
        rec = usadas_recentemente(a.cliente) if a.cliente else []
        bib = marcar(na_biblioteca(a.termo, a.tipo), rec, a.cliente)
        print("── Na Biblioteca")
        for it in bib:
            print(f"  · {it['titulo']} ({it['slug']}){'  ⚠ ' + it['usada_txt'] if it.get('usada') else ''}")
        if not bib:
            print("  (nada com essas palavras)")
        for grupo in buscar(a.termo, a.tipo, pagina=a.pagina, instrumental=a.instrumental):
            marcar(grupo["itens"], rec, a.cliente)
            for it in grupo["itens"]:
                if it.get("usada"):
                    it["titulo"] += f"  ⚠ {it['usada_txt']}"
            _imprimir(grupo)
    elif a.cmd == "recentes":
        rec = usadas_recentemente(a.cliente, a.n, a.ignorar)
        if not rec:
            print(f"Nenhuma música registrada nos últimos {a.n} vídeos do {a.cliente}. Pode escolher à vontade "
                  "(e registre no PLANO.json qual usou).")
        else:
            print(f"NÃO REPITA — músicas dos últimos {a.n} vídeos do {a.cliente}:")
            for x in rec:
                print(f"  {x['posicao']}. {x['titulo']}" + (f"  [acervo: {x['slug']}]" if x["slug"] else "")
                      + (f"  {x['fonte']}" if x["fonte"] else "") + f"  — vídeo “{x['job_titulo']}” ({x['data'][:10]})")
    elif a.cmd == "status":
        s = status()
        for f in s["fontes"]:
            print(f"{f['nome']:10s} {f['estado']}" + (f"  (chave grátis: {f['onde']})" if f["env"] and not f["ligado"] else ""))
    elif a.cmd == "guardar":
        m = guardar(a.fonte, a.url, a.audio, a.titulo, a.autor, a.licenca, a.tags, a.tipo, a.termo, a.duracao,
                    a.aviso_licenca)
        print("acervo:", m["slug"])


if __name__ == "__main__":
    main()
