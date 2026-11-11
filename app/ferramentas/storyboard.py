#!/usr/bin/env python3
"""
storyboard — a folha de storyboard de um vídeo, no mesmo padrão do Diálogo 3D
(formatos/dialogo-3d/base/render.py: quadro 360x640, faixa de 170 px embaixo, 4 colunas).

Lê <sandbox>/PLANO.json e grava <sandbox>/storyboard.jpg (+ storyboard.json dizendo de onde veio cada quadro).
Local e grátis (PIL + ffmpeg). A linha do tempo vai inteira, sem buraco: os beats em ordem e, nos intervalos,
quadros da pessoa falando.

Cada quadro:
    pessoa falando / zoom   quadro do meio do trecho (work/joao.mp4 ou o bruto)
    cena de apoio           quadro do meio do clipe ESCOLHIDO; sem escolha, a 1ª opção com a marca "sugestão".
                            Nunca a folha de contato (-sheet). Recorta pra caber, nunca estica.
    frase na tela           desenhada com o texto do card; *destaque* na cor da identidade do cliente (ou da ficha)

Embaixo de cada quadro: "N. Cena de apoio · 0:21–0:27" e a fala (fonte com acento: Arial ou Barlow).
No rodapé da folha: a música e os efeitos.

CLI:
    python3 app/ferramentas/storyboard.py <sandbox> [--saida arquivo.jpg]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from functools import lru_cache
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import IMAGEM_EXTS, VIDEO_EXTS, ler_json, gravar_json  # noqa: E402

CW, CH, FAIXA, COLS, GAP = 360, 640, 170, 4, 12
FUNDO_FOLHA = (40, 36, 44)
FUNDO_QUADRO = (250, 247, 242)
TINTA = (30, 30, 30)
TINTA_FALA = (70, 60, 60)
CORES_PADRAO = ["#C8102E", "#C8961E"]          # vermelho na dor, dourado na virada (o documentário do exemplo)
TIPOS = {"broll": "Cena de apoio", "citacao": "Cena de apoio", "card": "Frase na tela", "impacto": "Frase na tela",
         "punch": "Zoom no rosto", "insert": "Imagem inserida", "fala": "falando"}
INTERVALO_MIN = 1.5          # buraco menor que isso não vira quadro (o beat vizinho cobre)
INTERVALO_MAX = 15.0         # fala longa vira mais de um quadro (cada um com até ~12 s)

PASTAS_FONTES = [Path("/System/Library/Fonts/Supplemental"), Path.home() / "Library" / "Fonts", Path("/Library/Fonts")]


# ───────────────────────── fontes (com acento, nunca a fonte padrão do PIL) ─────────────────────────

@lru_cache(maxsize=None)
def fonte(tam: int, negrito: bool = False, serifa: bool = False):
    from PIL import ImageFont
    nomes = []
    if serifa:
        nomes += ["Georgia Bold.ttf", "Times New Roman Bold.ttf"]
    if negrito:
        nomes += ["Arial Bold.ttf", "Barlow-SemiBold.ttf", "Barlow-Black.ttf"]
    nomes += ["Arial.ttf", "Barlow-Regular.ttf", "Barlow-Medium.ttf"]
    for nome in nomes:
        for pasta in PASTAS_FONTES:
            if (pasta / nome).is_file():
                return ImageFont.truetype(str(pasta / nome), tam)
    raise RuntimeError("Não achei a fonte Arial nem a Barlow neste Mac. O storyboard precisa de uma fonte com acento "
                       "(instale a Barlow em ~/Library/Fonts) — não uso a fonte padrão, que troca 'você' por quadradinho.")


# ───────────────────────── vídeo ─────────────────────────

def duracao(video: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip() or 0)
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0


def quadro(video: Path, t: float):
    """Um quadro do vídeo no instante t (PIL RGB) ou None."""
    from PIL import Image
    for tt in (max(0.0, t), max(0.0, t - 1.0), 0.0):
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tt:.2f}", "-i", str(video), "-frames:v", "1",
                                "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if r.returncode == 0 and r.stdout:
            try:
                return Image.open(BytesIO(r.stdout)).convert("RGB")
            except Exception:
                return None
    return None


def _meio_do_gif(p: Path):
    from PIL import Image
    try:
        im = Image.open(p)
        im.seek(max(0, getattr(im, "n_frames", 1) // 2))
        return im.convert("RGB")
    except Exception:
        return None


def pessoa(sb: Path) -> Path | None:
    """O vídeo da pessoa falando: o corte (work/joao.mp4) ou o bruto."""
    if (sb / "work" / "joao.mp4").is_file():
        return sb / "work" / "joao.mp4"
    brutos = sorted(p for p in (sb / "bruto").glob("*") if p.suffix.lower() in VIDEO_EXTS) if (sb / "bruto").is_dir() else []
    return brutos[0] if brutos else None


# ───────────────────────── de onde vem a imagem de uma opção de b-roll ─────────────────────────

def _e_sheet(p: Path) -> bool:
    return "-sheet" in p.name.lower() or p.stem.lower().endswith("sheet")


def _trecho(o: dict) -> tuple[float, float] | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", str(o.get("trecho") or ""))
    return (float(m.group(1)), float(m.group(2))) if m else None


def _id_video(o: dict) -> str:
    u = str(o.get("url") or "")
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})", u) or re.search(r"(\d{5,})/?$", u.split("?")[0])
    return m.group(1) if m else ""


def _dentro(sb: Path, valor) -> Path | None:
    if not valor:
        return None
    p = (sb / str(valor)).resolve()
    try:
        p.relative_to(sb.resolve())
    except ValueError:
        return None
    return p if p.is_file() and not _e_sheet(p) else None


def midia_opcao(sb: Path, beat: dict, o: dict) -> dict | None:
    """A melhor mídia pra mostrar uma opção: {'arquivo': Path, 'tipo': 'video'|'imagem'|'gif', 't': segundos}.

    Ordem: o arquivo da opção → o clipe limpo do beat → o vídeo baixado (work/src) no trecho → poster → GIF.
    Nunca a folha de contato."""
    escolhida = beat.get("escolha") == o.get("id")
    cands = []
    a = _dentro(sb, o.get("arquivo"))
    if a:
        cands.append(a)
    if escolhida:
        cands.append(_dentro(sb, f"brolls/clips/{beat.get('id')}-clean.mp4"))
    for ext in (".mp4", ".mov", ".webm"):
        cands.append(_dentro(sb, f"brolls/clips/{o.get('id')}{ext}"))
    vid = _id_video(o)
    if vid:
        for pasta in ("work/src", "brolls/clips", "brolls"):
            d = sb / pasta
            if d.is_dir():
                cands += [p for p in sorted(d.glob(f"*{vid}*")) if p.suffix.lower() in VIDEO_EXTS]
    for c in cands:
        if c and c.is_file() and c.suffix.lower() in VIDEO_EXTS:
            tr = _trecho(o)
            cortado = c == a or c.parent.name == "clips"       # clipe já cortado: o meio dele; vídeo inteiro: o meio do trecho
            t = (tr[0] + tr[1]) / 2 if tr and not cortado else duracao(c) / 2
            return {"arquivo": c, "tipo": "video", "t": t}
        if c and c.is_file() and c.suffix.lower() in IMAGEM_EXTS:
            return {"arquivo": c, "tipo": "imagem", "t": 0}
    for valor in (o.get("poster"), f"brolls/{o.get('id')}-poster.jpg", f"brolls/{o.get('id')}.jpg",
                  f"brolls/{o.get('id')}.png"):
        p = _dentro(sb, valor)
        if p and p.suffix.lower() in IMAGEM_EXTS:
            return {"arquivo": p, "tipo": "imagem", "t": 0}
    g = _dentro(sb, o.get("gif"))
    if g:
        return {"arquivo": g, "tipo": "gif", "t": 0}
    return None


def opcao_do_beat(beat: dict) -> tuple[dict | None, bool]:
    """(opção que aparece no storyboard, é só sugestão?)"""
    ops = [o for o in beat.get("opcoes") or [] if isinstance(o, dict) and not o.get("registro_busca")]
    esc = next((o for o in ops if o.get("id") == beat.get("escolha")), None)
    if esc:
        return esc, False
    return (ops[0], True) if ops else (None, False)


def imagem_da_midia(m: dict | None):
    if not m:
        return None
    from PIL import Image
    if m["tipo"] == "video":
        return quadro(m["arquivo"], m["t"])
    if m["tipo"] == "gif":
        return _meio_do_gif(m["arquivo"])
    try:
        return Image.open(m["arquivo"]).convert("RGB")
    except Exception:
        return None


# ───────────────────────── cores e textos ─────────────────────────

def _hex(c: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(c or "").strip())
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else None


def cores(sb: Path) -> list[tuple[int, int, int]]:
    """Cores de destaque: identidade.json do cliente → paleta da ficha do modelo → vermelho/dourado.
    Fica só cor que aparece em papel claro (nem quase branca, nem quase preta)."""
    lista = []
    for up in [sb, *sb.parents][:5]:
        d = ler_json(up / "identidade.json", None)
        if d:
            lista += [x for x in d.get("cores") or []]
            break
    f = ler_json(sb.parent / "ficha.json", {}) or {}
    for p in f.get("paleta") or []:
        lista.append(p.get("cor") if isinstance(p, dict) else p)
    out = []
    for c in lista:
        rgb = _hex(c)
        if not rgb:
            continue
        lum = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
        if 0.08 < lum < 0.8 and rgb not in out:
            out.append(rgb)
    return out or [_hex(c) for c in CORES_PADRAO]


def mmss(t: float) -> str:
    t = max(0, int(round(float(t or 0))))
    return f"{t // 60}:{t % 60:02d}"


def quebrar(d, txt: str, f, largura: int) -> list[str]:
    linhas, cur = [], ""
    for w in str(txt or "").split():
        if cur and d.textlength(cur + " " + w, font=f) > largura:
            linhas.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        linhas.append(cur)
    return linhas


def fala_entre(transcricao: list, t0: float, t1: float) -> str:
    partes = []
    for tr in transcricao or []:
        try:
            a, b = float(tr.get("t0", 0)), float(tr.get("t1", tr.get("t0", 0)))
        except (TypeError, ValueError):
            continue
        if b > t0 + 0.2 and a < t1 - 0.2:
            partes.append(str(tr.get("texto", "")).strip())
    return " ".join(p for p in partes if p)


# ───────────────────────── desenho de cada quadro ─────────────────────────

def _caber(im, w: int, h: int):
    from PIL import ImageOps, Image
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.42))


def _tirar_tarja(im):
    """Filme com tarja preta (letterbox): corta as faixas pretas antes de recortar pro quadro em pé."""
    caixa = im.convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
    if not caixa:
        return im
    l, t, r, b = caixa
    if (r - l) > im.width * 0.3 and (b - t) > im.height * 0.3 and ((r - l) < im.width * 0.96 or (b - t) < im.height * 0.96):
        return im.crop(caixa)
    return im


def _sem_previa(titulo: str):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (CW, CH), (214, 207, 196))
    d = ImageDraw.Draw(im)
    for y in range(0, CH, 24):
        d.line((0, y, CW, y + 60), fill=(205, 198, 186), width=2)
    f, f2 = fonte(26, True), fonte(21)
    d.text((CW / 2, CH / 2 - 30), "Sem prévia desta cena", font=f, fill=(90, 80, 72), anchor="mm")
    for k, l in enumerate(quebrar(d, titulo, f2, CW - 60)[:3]):
        d.text((CW / 2, CH / 2 + 12 + k * 28), l, font=f2, fill=(110, 100, 92), anchor="mm")
    return im


def desenhar_card(texto: str, paleta: list) -> "Image":
    """Frase na tela: papel claro, serifa, *destaque* colorido (1ª cor na 1ª palavra destacada, 2ª na seguinte…)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (CW, CH), (244, 238, 226))
    d = ImageDraw.Draw(im)
    d.rectangle((14, 14, CW - 15, CH - 15), outline=(208, 198, 182), width=2)
    d.text((CW / 2, 52), "FRASE NA TELA", font=fonte(17, True), fill=(150, 138, 120), anchor="mm")
    # palavras = listas de pedaços (texto, cor): "*compromisso*." é UMA palavra com o ponto colado, em duas cores
    palavras, k, colar = [], 0, False
    for i, parte in enumerate(str(texto or "").split("*")):
        cor = None
        if i % 2 == 1:
            cor = paleta[k % len(paleta)]
            k += 1
        ws = parte.split()
        if ws and colar and palavras and not parte[:1].isspace():
            palavras[-1].append((ws.pop(0), cor))
        palavras += [[(w, cor)] for w in ws]
        colar = bool(parte) and not parte[-1:].isspace()
    larg_palavra = lambda p, f: sum(d.textlength(t, font=f) for t, _ in p)
    for tam in (46, 42, 38, 34, 30, 27, 24):
        f = fonte(tam, True, serifa=True)
        esp = d.textlength(" ", font=f)
        linhas, cur, larg = [], [], CW - 56
        for p in palavras:
            w_cur = sum(larg_palavra(x, f) for x in cur) + esp * len(cur)
            if cur and w_cur + larg_palavra(p, f) > larg:
                linhas.append(cur)
                cur = [p]
            else:
                cur.append(p)
        if cur:
            linhas.append(cur)
        alt = len(linhas) * int(tam * 1.28)
        if alt <= CH - 180 and all(larg_palavra(p, f) <= larg for p in palavras):
            break
    y = (CH - alt) / 2 + 10
    for linha in linhas:
        total = sum(larg_palavra(p, f) for p in linha) + esp * (len(linha) - 1)
        x = (CW - total) / 2
        for p in linha:
            for t, cor in p:
                d.text((x, y), t, font=f, fill=cor or (34, 30, 28))
                x += d.textlength(t, font=f)
            x += esp
        y += int(tam * 1.28)
    return im


def _etiqueta(im, txt: str):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    f = fonte(19, True)
    w = d.textlength(txt, font=f)
    d.rounded_rectangle((10, 10, 10 + w + 20, 44), radius=10, fill=(255, 214, 10))
    d.text((20, 27), txt, font=f, fill=(20, 20, 20), anchor="lm")


# ───────────────────────── tela dividida: o quadro montado ─────────────────────────
# Formato de tela dividida (o modelo tem build-band.py e o plano traz "manchete"): cada quadro mostra o vídeo
# como vai sair — a pessoa em cima, a faixa vermelha com a manchete no meio, a cena embaixo — e não só a cena.
DIV_TOPO, DIV_FAIXA = 1056, 270      # proporção do formato (COMO-FAZER da Tela dividida)


def faixa_dividida(sb: Path, plano: dict):
    """band.png 1080x1920 (transparente + faixa) gerada pelo build-band.py do modelo, ou None se não for tela dividida."""
    from PIL import Image
    bb = sb.parent / "build-band.py"
    titulo = str(plano.get("manchete") or "").strip()
    if not bb.is_file() or not titulo:
        return None
    out = sb / "qa" / "storyboard-faixa.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(bb), "--out", str(out), "--titulo", titulo, "--top-h", str(DIV_TOPO)],
                       capture_output=True, timeout=60)
    if r.returncode or not out.is_file():
        return None
    return Image.open(out).convert("RGBA")


def recorte_rosto(sb: Path, video: Path):
    """O recorte do bloco de cima igual ao do render: seguir_rosto.py do modelo (rosto no meio, desliza sem corte seco).
    Devolve f(quadro, t) → imagem 1080xDIV_TOPO, ou None (modelo sem seguir_rosto: recorte central)."""
    sr = sb.parent / "seguir_rosto.py"
    if not sr.is_file():
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("seguir_rosto", sr)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        zoom = float((ler_json(video.parent / "enquadramento.json", {}) or {}).get("zoom") or 1.0)
        ch = m.calcular(video, DIV_TOPO, zoom)["chaves"]
    except Exception:
        return None

    def f(q, t):
        from PIL import Image
        w, h = q.size
        cw = int(h * 9 / 16)
        q = q.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h)).resize((int(1080 * zoom + .5), int(1920 * zoom + .5)), Image.LANCZOS)
        x = (q.width - 1080) // 2
        y = int(round(m.y_em(ch, t)))
        return q.crop((x, y, x + 1080, y + DIV_TOPO))
    return f


def montar_dividida(faixa, topo, baixo):
    """Pessoa (topo, já recortada ou não) + cena (baixo) + faixa por cima, em 1080x1920, reduzido pro quadro da folha."""
    from PIL import Image
    tela = Image.new("RGB", (1080, 1920), (20, 20, 20))
    if topo is not None:
        tela.paste(topo if topo.size == (1080, DIV_TOPO) else _caber(topo, 1080, DIV_TOPO), (0, 0))
    if baixo is not None:
        y = DIV_TOPO + DIV_FAIXA
        tela.paste(_caber(baixo, 1080, 1920 - y), (0, y))
    tela.paste(faixa, (0, 0), faixa)
    return tela.resize((CW, CH), Image.LANCZOS)


def celula(n: int, rotulo: str, t0: float, t1: float, fala: str, im):
    from PIL import Image, ImageDraw
    c = Image.new("RGB", (CW, CH + FAIXA), FUNDO_QUADRO)
    c.paste(im, (0, 0))
    d = ImageDraw.Draw(c)
    f2 = fonte(22)
    cab = f"{n}. {rotulo} · {mmss(t0)}–{mmss(t1)}"
    for tam in (24, 22, 20, 18):                         # cabeçalho longo diminui antes de cortar
        f1 = fonte(tam, True)
        if d.textlength(cab, font=f1) <= CW - 20:
            break
    while d.textlength(cab, font=f1) > CW - 20 and len(rotulo) > 4:
        rotulo = rotulo[:-2].rstrip() + "…"
        cab = f"{n}. {rotulo} · {mmss(t0)}–{mmss(t1)}"
    d.text((12, CH + 10), cab, font=f1, fill=TINTA)
    linhas = quebrar(d, fala, f2, CW - 24) if fala else []
    if len(linhas) > 4:
        linhas = linhas[:4]
        while linhas[3] and d.textlength(linhas[3] + "…", font=f2) > CW - 24:
            linhas[3] = linhas[3].rsplit(" ", 1)[0] if " " in linhas[3] else linhas[3][:-1]
        linhas[3] += "…"
    for k, l in enumerate(linhas):
        d.text((12, CH + 46 + k * 28), l, font=f2, fill=TINTA_FALA)
    if not linhas:
        d.text((12, CH + 46), "(sem fala)", font=f2, fill=(120, 110, 110))
    return c


# ───────────────────────── a linha do tempo ─────────────────────────

def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def linha_do_tempo(plano: dict, total: float) -> list[dict]:
    """Os beats em ordem e, entre eles, trechos de fala: nada fica de fora."""
    beats = sorted((b for b in plano.get("beats") or [] if isinstance(b, dict)
                    and _num(b.get("inicio")) is not None and _num(b.get("fim")) is not None),
                   key=lambda b: _num(b["inicio"]))
    trechos, cursor = [], 0.0

    def fala(a, b):
        partes = math.ceil((b - a) / 12) if b - a > INTERVALO_MAX else 1
        passo = (b - a) / partes
        for i in range(partes):
            trechos.append({"tipo": "fala", "t0": a + i * passo, "t1": a + (i + 1) * passo})

    for b in beats:
        ini, fim = _num(b["inicio"]), _num(b["fim"])
        if ini - cursor >= INTERVALO_MIN:
            fala(cursor, ini)
        elif ini > cursor:                     # sobra pequena: o beat começa um pouco antes, sem buraco
            ini = cursor
        trechos.append({"tipo": b.get("tipo") or "fala", "t0": ini, "t1": fim, "beat": b})
        cursor = max(cursor, fim)
    if total - cursor >= INTERVALO_MIN:
        fala(cursor, total)
    elif trechos and total > cursor:
        trechos[-1]["t1"] = total
    return trechos


def _rel_sb(p: Path, sb: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(sb))
    except ValueError:
        return str(p)


def _nome_pessoa(sb: Path) -> str:
    partes = sb.resolve().parts
    if "clientes" in partes and len(partes) > partes.index("clientes") + 1:
        nome = partes[partes.index("clientes") + 1]
        if nome.lower() != "avulso":
            return nome
    return "Pessoa"


def texto_musica(plano: dict) -> str:
    m = plano.get("musica")
    if isinstance(m, list):
        m = next((x for x in m if isinstance(x, dict)), None)
    if isinstance(m, str):
        m = {"opcao": m}
    if isinstance(m, dict) and m.get("sem"):
        txt = "Música: sem música"
    elif isinstance(m, dict) and (m.get("titulo") or m.get("opcao") or m.get("arquivo")):
        nome = m.get("titulo") or Path(str(m.get("opcao") or m.get("arquivo"))).stem.replace("-", " ")
        txt = f"Música: {nome}"
        if _num(m.get("inicio_s")) is not None and _num(m.get("fim_s")) is not None:
            txt += f" · trecho {mmss(m['inicio_s'])}–{mmss(m['fim_s'])}"
        if m.get("fonte"):
            txt += f" · {m['fonte']}"
    else:
        txt = "Música: ainda não escolhida"
    sfx = [s for s in plano.get("sfx") or [] if isinstance(s, dict)]
    if plano.get("sfx_ligado") is False:
        txt += "   ·   Efeitos: desligados"
    elif sfx:
        ativos = [s for s in sfx if s.get("ligado", True)]
        txt += f"   ·   Efeitos: {len(ativos)} de {len(sfx)} ligados"
    return txt


def gerar(sandbox, saida: Path | None = None) -> dict:
    """Monta a folha. Devolve {'saida': Path, 'quadros': [{n, tipo, rotulo, t0, t1, fonte}]}."""
    from PIL import Image, ImageDraw
    sb = Path(sandbox).resolve()
    plano = ler_json(sb / "PLANO.json", None)
    if not isinstance(plano, dict):
        raise FileNotFoundError(f"Não achei o PLANO.json em {sb}")
    fonte(22)                                            # sem fonte com acento, para aqui com erro claro
    video = pessoa(sb)
    fim_plano = max([_num(b.get("fim")) or 0 for b in plano.get("beats") or [] if isinstance(b, dict)] +
                    [_num(t.get("t1")) or 0 for t in plano.get("transcricao") or [] if isinstance(t, dict)] + [0])
    total = (duracao(video) if video else 0) or fim_plano
    paleta = cores(sb)
    quem = _nome_pessoa(sb)
    trans = plano.get("transcricao") or []
    cels, quadros = [], []
    faixa = faixa_dividida(sb, plano)
    rec = recorte_rosto(sb, video) if faixa is not None and video else None
    for n, tr in enumerate(linha_do_tempo(plano, total), 1):
        b = tr.get("beat") or {}
        tipo = tr["tipo"]
        rotulo = f"{quem} falando" if tipo == "fala" else TIPOS.get(tipo, tipo.capitalize())
        meio = (tr["t0"] + tr["t1"]) / 2
        fala = b.get("fala") or fala_entre(trans, tr["t0"], tr["t1"])
        origem, im, cru = "", None, None
        if tipo in ("card", "impacto"):
            im, origem = desenhar_card(b.get("texto_card") or b.get("fala") or "", paleta), "desenho"
        elif tipo in ("broll", "citacao") or (tipo == "insert" and b.get("opcoes")):
            op, sugestao = opcao_do_beat(b)
            m = midia_opcao(sb, b, op) if op else None
            im = imagem_da_midia(m)
            if im is not None:
                cru = _tirar_tarja(im)
                im = _caber(cru, CW, CH)
                origem = _rel_sb(m["arquivo"], sb)
                if sugestao:
                    _etiqueta(im, "sugestão")
            else:
                im = _sem_previa((op or {}).get("titulo") or b.get("intencao") or "")
                origem = "sem-previa"
        if im is None:                                   # fala, zoom no rosto e o que mais não tiver mídia
            q = quadro(video, meio) if video else None
            if q is not None:
                if tipo == "punch":                      # o zoom: corta 18% em volta do rosto
                    w, h = q.size
                    q = q.crop((int(w * .09), int(h * .06), int(w * .91), int(h * .88)))
                im, origem = _caber(q, CW, CH), _rel_sb(video, sb)
            else:
                im, origem = _sem_previa("Vídeo da fala não encontrado"), "sem-previa"
        if faixa is not None and video:                  # tela dividida: o quadro como vai sair
            cena = cru if cru is not None else (im if origem == "sem-previa" else None)
            q = quadro(video, meio)
            im = montar_dividida(faixa, rec(q, meio) if (rec and q is not None) else q, cena)
            if tipo in ("broll", "citacao") and origem != "sem-previa" and opcao_do_beat(b)[1]:
                _etiqueta(im, "sugestão")
        cels.append(celula(n, rotulo, tr["t0"], tr["t1"], fala, im))
        quadros.append({"n": n, "tipo": tipo, "rotulo": rotulo, "t0": round(tr["t0"], 2), "t1": round(tr["t1"], 2),
                        "beat": b.get("id", ""), "fonte": origem})
    if not cels:
        raise ValueError("O PLANO.json não tem trechos pra mostrar.")
    linhas_n = -(-len(cels) // COLS)
    rodape = 74
    folha = Image.new("RGB", (COLS * (CW + GAP) + GAP, linhas_n * (CH + FAIXA + GAP) + GAP + rodape), FUNDO_FOLHA)
    for i, c in enumerate(cels):
        folha.paste(c, (GAP + (i % COLS) * (CW + GAP), GAP + (i // COLS) * (CH + FAIXA + GAP)))
    d = ImageDraw.Draw(folha)
    d.text((GAP + 6, folha.height - rodape / 2 - 2), texto_musica(plano) + f"   ·   {len(cels)} quadros · {mmss(total)}",
           font=fonte(26, True), fill=(240, 232, 220), anchor="lm")
    out = Path(saida) if saida else sb / "storyboard.jpg"
    folha.save(out, quality=88)
    try:
        plano_mtime = (sb / "PLANO.json").stat().st_mtime
    except OSError:
        plano_mtime = 0
    if not saida:
        gravar_json(sb / "storyboard.json", {"ferramenta": "storyboard.py", "plano_mtime": plano_mtime,
                                             "quadros": quadros})
    return {"saida": out, "quadros": quadros}


def desatualizado(sandbox) -> bool:
    """True se a folha não existe, não saiu desta ferramenta ou o PLANO mudou depois dela."""
    sb = Path(sandbox)
    if not (sb / "PLANO.json").is_file():
        return False
    meta = ler_json(sb / "storyboard.json", None)
    if not (sb / "storyboard.jpg").is_file() or not isinstance(meta, dict) or meta.get("ferramenta") != "storyboard.py":
        return True
    return (sb / "PLANO.json").stat().st_mtime > float(meta.get("plano_mtime") or 0) + 0.001


def main():
    ap = argparse.ArgumentParser(description="Folha de storyboard a partir do PLANO.json (padrão do Diálogo 3D)")
    ap.add_argument("sandbox")
    ap.add_argument("--saida", default="")
    a = ap.parse_args()
    r = gerar(a.sandbox, Path(a.saida) if a.saida else None)
    print(r["saida"])
    print(json.dumps({"quadros": len(r["quadros"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
