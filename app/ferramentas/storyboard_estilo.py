#!/usr/bin/env python3
"""
storyboard_estilo — a tira "Momento a momento" de cada estilo: TODOS os planos do vídeo de referência (ou os ~60 mais
didáticos, quando passa disso), cada um com o tempo, a duração, o quadro do MEIO do plano (nunca o instante do corte, que
sai preto/branco) e o que ele é de verdade ("corte seco", "dissolve de 5 quadros", "texto na tela: ...", "número falado",
"peça: frase" quando a referência é do próprio Estúdio e tem cenas.json). Em cima da tira vai o resumo "Cenas que esse
estilo usa" (tipo · contagem · miniatura, clicável pra filtrar) e 3 números da régua.

De onde vem (a primeira que existir):
  1. estudo quadro a quadro do estilo (`formatos/<slug>/estudos/NN-*/estudo-quadros/estudo.json`, o PRINCIPAL primeiro, ou
     `formatos/<slug>/estudo-quadros/estudo.json`): planos, transições e números falados, medidos no vídeo;
  2. sem estudo: o estudo LEVE (os mesmos planos/transições/câmera de `estudo_quadros`, sem fala, grátis), feito uma vez
     no exemplo do estilo e guardado em cache.
Quadros, OCR e estudo leve ficam em `app/.cache/storyboard/<slug>/<ref>/` (nunca em `formatos/`).

    python3 app/ferramentas/storyboard_estilo.py <slug> [ref]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO, RAIZ, ler_json  # noqa: E402

FORMATOS = RAIZ / "formatos"
CACHE = ESTUDIO / ".cache" / "storyboard"
MAX_QUADROS = 8
LARGURA = 360          # px do quadro guardado (a tela mostra ~180 px, o dobro pra tela retina)
NOME_OK = re.compile(r"^[A-Za-z0-9._-]+\.jpg$")


def tempo(s: float) -> str:
    """2.3 -> '2,3 s'."""
    return f"{s:.1f}".replace(".", ",") + " s"


def _duracao(video: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def _corte(texto: str, n: int = 44) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip(" ,;:-")
    return texto if len(texto) <= n else texto[: n - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


# ── onde está o vídeo e o estudo ─────────────────────────────────────────────────────────────────────────────────

def _exemplos(slug: str) -> list[Path]:
    """Os mp4 de exemplo do estilo; o principal (maior `principal_desde`) primeiro."""
    pasta = FORMATOS / slug
    f = ler_json(pasta / "formato.json", {}) or {}
    exs = [e for e in (f.get("exemplos") or []) if e.get("arquivo") and (pasta / e["arquivo"]).is_file()]
    exs.sort(key=lambda e: e.get("principal_desde") or "", reverse=True)   # estável: sem data mantém a ordem
    return [pasta / e["arquivo"] for e in exs]


def _ref_id(estudo_json: Path | None, mp4: Path) -> str:
    if estudo_json is not None and estudo_json.parent.parent.parent.name == "estudos":
        return estudo_json.parent.parent.name
    return re.sub(r"[^A-Za-z0-9._-]", "-", mp4.stem)[:60] or "video"


def fonte(slug: str, ref: str = "") -> dict | None:
    """{'video': Path, 'estudo': dict|None, 'video_estudo': dict|None, 'ref_id': str} ou None se o estilo não tem vídeo nenhum.
    `ref_id` nomeia a pasta do cache (a referência: `estudos/<ref>` ou o stem do exemplo) — o mesmo vídeo cai sempre na mesma."""
    pasta = FORMATOS / slug
    candidatos: list[tuple[Path, Path]] = []          # (estudo.json, mp4 que ele mediu)
    estudos = sorted((pasta / "estudos").glob("*/estudo-quadros/estudo.json")) if (pasta / "estudos").is_dir() else []
    estudos.sort(key=lambda p: not (p.parent.parent / "PRINCIPAL").exists())
    if ref:   # "Só esta" / a de maior peso no Criar: a prévia mostra ESSA referência (pasta de estudos/<ref>)
        estudos = [j for j in estudos if j.parent.parent.name == ref]
        if not estudos:
            return None
    for j in estudos:
        vid = sorted(j.parent.parent.glob("video-*.mp4"))
        if vid:
            candidatos.append((j, vid[0]))
    ex = [] if ref else _exemplos(slug)
    if not ref and (pasta / "estudo-quadros" / "estudo.json").is_file() and ex:
        candidatos.append((pasta / "estudo-quadros" / "estudo.json", ex[0]))
    for j, mp4 in candidatos:
        d = ler_json(j, {}) or {}
        vs = d.get("videos") or []
        dur = _duracao(mp4)
        for v in vs[:6]:   # o vídeo medido tem que ter a duração do mp4 que temos (±3%): senão o estudo é de outro vídeo
            if dur and v.get("duracao") and abs(v["duracao"] - dur) <= max(1.0, 0.03 * dur) and v.get("planos"):
                return {"video": mp4, "estudo": d, "video_estudo": v, "duracao": dur, "ref_id": _ref_id(j, mp4)}
    if ex:
        return {"video": ex[0], "estudo": None, "video_estudo": None, "duracao": _duracao(ex[0]), "ref_id": _ref_id(None, ex[0])}
    return None


# ── os momentos ──────────────────────────────────────────────────────────────────────────────────────────────────

def momentos_estudo(v: dict) -> list[dict]:
    """Candidatos tirados das medidas: {t, prio, legenda, fala}. Maior prio = mais didático."""
    fps = v.get("fps") or 25.0
    dur = v.get("duracao") or 0
    planos = (v.get("planos") or {}).get("lista") or []
    c: list[dict] = []
    if planos:
        p0 = planos[0]
        c.append({"t": 0.0, "prio": 100, "legenda": f"abertura: cena de {tempo(p0.get('dura_s') or 0)}", "fala": ""})
        longo = max(planos, key=lambda p: p.get("dura_s") or 0)
        if (longo.get("dura_s") or 0) >= 3 * ((v.get("planos") or {}).get("mediana_s") or 1) and longo.get("s", 0) > 1:
            c.append({"t": longo["s"], "prio": 50, "legenda": f"a cena que mais demora: {tempo(longo['dura_s'])}", "fala": ""})
    for t in v.get("transicoes") or []:
        if t.get("tipo") == "dissolve":
            c.append({"t": t["s"], "prio": 70, "legenda": f"dissolve de {t.get('quadros', 0)} quadros ({tempo(t.get('quadros', 0) / fps)})", "fala": ""})
        elif t.get("tipo") == "especial":
            c.append({"t": t["s"], "prio": 60, "legenda": f"transição especial ({t.get('quadros', 0)} quadros)", "fala": ""})
    for n in v.get("numeros") or []:
        ev = n.get("evento_menos_palavra_q")
        extra = ""
        if n.get("evento"):
            extra = " · aparece na tela junto" if ev is not None and abs(ev) <= 3 else " · aparece na tela"
        c.append({"t": n["s"], "prio": 80, "legenda": "número falado" + extra, "fala": _corte(n.get("texto", ""))})
    for o in (v.get("fala_imagem") or {}).get("oracoes") or []:
        partes = []
        if o.get("troca"):
            partes.append({"corte": "corte seco", "dissolve": "dissolve"}.get(o.get("troca_tipo"), "troca de cena"))
        if o.get("imagem_nova"):
            partes.append("imagem nova")
        if o.get("evento") and not o.get("imagem_nova"):
            partes.append("elemento novo na tela")
        if not partes or o.get("s") is None:
            continue
        c.append({"t": o["s"], "prio": 40 + (10 if o.get("troca") else 0), "legenda": " · ".join(partes), "fala": _corte(o.get("texto", ""))})
    return [m for m in c if 0 <= m["t"] <= max(dur - 0.2, 0.1)]


def cortes_do_video(video: Path, limiar: float = 0.32) -> list[float]:
    """Tempos de troca de cena achados pelo ffmpeg (sem estudo)."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", f"scale=160:-2,select='gt(scene,{limiar})',showinfo",
                            "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=240)
    except Exception:  # noqa: BLE001
        return []
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def momentos_sem_estudo(video: Path, dur: float) -> list[dict]:
    c = [{"t": 0.0, "prio": 100, "legenda": "abertura", "fala": ""}]
    for t in cortes_do_video(video):
        if 0.5 < t < dur - 0.3:
            c.append({"t": round(t, 2), "prio": 40, "legenda": "troca de cena", "fala": ""})
    if len(c) < 4 and dur:   # vídeo de uma cena só: quadros espaçados
        c += [{"t": round(dur * k / 6, 2), "prio": 30, "legenda": "um momento do vídeo", "fala": ""} for k in range(1, 6)]
    return c


def escolher(cands: list[dict], dur: float, n: int = MAX_QUADROS) -> list[dict]:
    """Espalha pelo vídeo: divide em n faixas de tempo e fica com o momento mais didático de cada uma (a 1ª faixa é a abertura)."""
    if not cands or dur <= 0:
        return []
    faixa = dur / n
    out: list[dict] = []
    for i in range(n):
        lo, hi = i * faixa, (i + 1) * faixa
        dentro = [m for m in cands if lo <= m["t"] < hi or (i == n - 1 and m["t"] == dur)]
        if not dentro:
            continue
        if i == 0:
            melhor = min(dentro, key=lambda m: m["t"]) if any(m["t"] == 0 for m in dentro) else max(dentro, key=lambda m: m["prio"])
        else:
            melhor = max(dentro, key=lambda m: (m["prio"], -m["t"]))
        out.append(melhor)
    out.sort(key=lambda m: m["t"])
    return out


# ── a tira nova: todos os planos, quadro do meio, rótulo de verdade ───────────────────────────────────────────────

VERSAO_CACHE = 4
LIMITE_TIRA = 60        # passou disso: todos os planos dos primeiros 20 s + os demais amostrados por tipo
PRIMEIROS_S = 20.0
RAJADA_S = 0.3          # plano mais curto que isso é rajada de cortes
LONGA_X = 3.0           # "cena longa": 3x a mediana e pelo menos 2 s
ENTRADA = {"corte": "corte seco", "dissolve": "dissolve", "especial": "transição especial"}
ROTULO_TIPO = {"abertura": "abertura", "numero": "número falado", "rajada": "rajada de cortes", "especial": "transição especial",
               "dissolve": "dissolve", "longa": "cena longa", "texto": "texto na tela", "corte": "corte seco"}


def virgula(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _nb(texto: str) -> str:
    return re.sub(r"(\d) (s|quadros|%)\b", "\\1\u00a0\\2", texto)


def rotulo_tipo(tipo: str) -> str:
    return "peça: " + tipo[5:] if tipo.startswith("peca:") else ROTULO_TIPO.get(tipo, tipo)


def meio(p: dict) -> int:
    """Índice do quadro do MEIO do plano (nunca o do corte, que sai preto/branco ou borrado)."""
    return (int(p["q"]) + int(p.get("q_fim", p["q"]))) // 2


def pecas_do_cenas(video: Path) -> list[tuple[float, str]]:
    """Referência do próprio Estúdio: o `cenas.json` ao lado do vídeo diz o tipo da peça de cada cena ([(de, tipo)])."""
    for c in (video.with_name("cenas.json"), video.with_suffix(".cenas.json")):
        d = ler_json(c, None) if c.is_file() else None
        cenas = d.get("cenas") if isinstance(d, dict) else d
        if isinstance(cenas, list):
            out = [(float(x["de"]), str(x.get("tipo") or x.get("mundo"))) for x in cenas
                   if isinstance(x, dict) and x.get("de") is not None and (x.get("tipo") or x.get("mundo"))]
            if out:
                return sorted(out)
    return []


def classificar(v: dict, pecas: list | None = None, ocr: dict | None = None) -> list[dict]:
    """Um item por plano, na ordem do vídeo: {i, q, qm, t, dura_s, tipo, entrada, legenda, fala}. Puro (sem arquivo nenhum).
    Tipo (o primeiro que valer): peça do motor (cenas.json) > abertura > número falado > rajada > transição especial >
    dissolve > cena longa > texto na tela (OCR) > corte seco. `ocr` = {índice do quadro do meio: texto}."""
    fps = v.get("fps") or 25.0
    pl = (v.get("planos") or {})
    lista = pl.get("lista") or []
    med = pl.get("mediana_s") or 0.5
    entradas = {int(t["q"]): t for t in v.get("transicoes") or []}
    nums = sorted(v.get("numeros") or [], key=lambda n: n.get("s", 0))
    ocr = ocr or {}
    pecas = pecas or []
    out: list[dict] = []
    for k, p in enumerate(lista):
        s, d = float(p.get("s", 0)), float(p.get("dura_s") or 0)
        qm = meio(p)
        ent = entradas.get(int(p["q"]))
        ent_tipo = ent["tipo"] if ent else ""
        num = next((n for n in nums if s - 0.02 <= n.get("s", -1) < s + d), None)
        txt = _corte(ocr.get(qm, ""), 40)
        nq = (ent or {}).get("quadros", 0)
        ent_txt = (f"dissolve de {nq} quadros ({tempo(nq / fps)})" if ent_tipo == "dissolve"
                   else f"transição especial ({nq} quadros)" if ent_tipo == "especial" else ENTRADA.get(ent_tipo, ""))
        peca = next((tp for de, tp in reversed(pecas) if de <= s + d / 2 + 1e-6), "") if pecas else ""
        if peca:
            tipo, base = f"peca:{peca}", f"peça {peca}"
        elif k == 0:
            tipo, base = "abertura", f"abertura: cena de {tempo(d)}"
        elif num:
            tipo, base = "numero", "número falado" + (" · aparece na tela" if num.get("evento") else "")
        elif d < RAJADA_S:
            tipo, base = "rajada", f"rajada de cortes ({tempo(d)})"
        elif ent_tipo in ("especial", "dissolve"):
            tipo, base = ent_tipo, ent_txt
        elif d >= 2.0 and d >= LONGA_X * med:
            tipo, base = "longa", f"cena longa: {tempo(d)}"
        elif txt:
            tipo, base = "texto", "texto na tela"
        else:
            tipo, base = "corte", "corte seco" if ent_tipo in ("", "corte") else ent_txt
        extra = [ent_txt] if ent_tipo in ("especial", "dissolve") and tipo not in ("especial", "dissolve", "abertura") else []
        out.append({"i": k, "q": int(p["q"]), "qm": qm, "t": round(s, 2), "dura_s": round(d, 2), "tipo": tipo, "entrada": ent_tipo,
                    "legenda": _nb(" · ".join([base] + extra)), "fala": _corte(num.get("texto", ""), 44) if num else txt})
    return out


def destacar(itens: list[dict], limite: int = LIMITE_TIRA, primeiros_s: float = PRIMEIROS_S) -> list[dict]:
    """Marca `destaque` nos que a tira mostra de cara. Até `limite` planos: todos. Acima: todos os dos primeiros `primeiros_s`
    segundos (é onde o estilo se apresenta) + os demais amostrados por tipo, os raros primeiro e cada tipo espalhado no tempo."""
    for it in itens:
        it["destaque"] = True
    if len(itens) <= limite:
        return itens
    ini = [it for it in itens if it["t"] < primeiros_s]
    resto = [it for it in itens if it["t"] >= primeiros_s]
    verba = max(limite - len(ini), min(20, len(resto)))
    grupos: dict[str, list[dict]] = {}
    for it in resto:
        grupos.setdefault(it["tipo"], []).append(it)
    cota = {t: min(len(g), max(1, round(verba * len(g) / len(resto)))) for t, g in grupos.items()}
    for t, g in grupos.items():      # os raros entram inteiros (até 4): é onde o estilo muda
        if len(g) <= 4:
            cota[t] = len(g)
    while sum(cota.values()) > verba:    # estourou: tira do maior grupo
        maior = max(cota, key=lambda t: cota[t])
        if cota[maior] <= 1:
            break
        cota[maior] -= 1
    escolhidos: set[int] = {it["i"] for it in ini}
    for t, g in grupos.items():
        n = cota[t]
        passo = len(g) / n
        escolhidos |= {g[min(len(g) - 1, int(passo * m + passo / 2))]["i"] for m in range(n)}
    for it in itens:
        it["destaque"] = it["i"] in escolhidos
    return itens


def frases_do_ritmo(pl: dict, cam: dict) -> list[str]:
    """Os números do ritmo em frase simples ("Corte rápido: troca de imagem a cada ~1 s"); os números ficam em Ver detalhes."""
    out = []
    m = pl.get("media_s")
    if m is None and pl.get("por_min"):
        m = 60 / pl["por_min"]
    if m is not None:
        seg = virgula(m, 0 if m >= 3 else 1)
        nome = "Corte rápido" if m <= 1.5 else "Ritmo médio" if m <= 3.5 else "Ritmo calmo"
        out.append(f"{nome}: troca de imagem a cada ~{seg} s")
    c = cam.get("pct_quadros_andando")
    if c is not None:
        out.append("A câmera quase não para" if c >= 60 else "A câmera se mexe em parte do tempo" if c >= 25
                   else "A câmera fica parada; quem muda é a cena")
    return out


def resumir(itens: list[dict], v: dict) -> dict:
    """'Cenas que esse estilo usa' (tipo · quantos · 1 miniatura) + 2-3 números da régua."""
    por: dict[str, list[dict]] = {}
    for it in itens:
        por.setdefault(it["tipo"], []).append(it)
    tipos = []
    for t, g in sorted(por.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        ex = g[len(g) // 2] if t != "abertura" else g[0]
        tipos.append({"tipo": t, "rotulo": rotulo_tipo(t), "n": len(g), "exemplo": ex.get("arquivo", "")})
    pl, cam = (v.get("planos") or {}), (v.get("camera") or {})
    nums = []
    if pl.get("por_min") is not None:
        nums.append({"valor": virgula(pl["por_min"], 0 if pl["por_min"] >= 20 else 1), "rotulo": "cortes por minuto"})
    if pl.get("media_s") is not None:
        nums.append({"valor": virgula(pl["media_s"], 1) + "\u00a0s", "rotulo": "duração média do plano"})
    if cam.get("pct_quadros_andando") is not None:
        nums.append({"valor": f"{cam['pct_quadros_andando']:.0f}%", "rotulo": "do tempo com a câmera andando"})
    return {"tipos": tipos, "numeros": nums, "frases": frases_do_ritmo(pl, cam)}


# ── OCR e quadros ────────────────────────────────────────────────────────────────────────────────────────────────

def _ocr_tokens(img_path: Path) -> list[tuple[str, float]]:
    """[(palavra, altura da palavra em % do quadro)] de um quadro, só o que o tesseract leu com confiança."""
    try:
        import pytesseract
        from PIL import Image
        with Image.open(img_path) as im:
            H = im.height
            d = pytesseract.image_to_data(im, lang="por+eng", config="--psm 11", output_type=pytesseract.Output.DICT)
    except Exception:  # noqa: BLE001   sem tesseract: a tira vive sem o texto da tela
        return []
    out = []
    for k, txt in enumerate(d["text"]):
        try:
            if float(d["conf"][k]) < 70:
                continue
        except (TypeError, ValueError):
            continue
        t = re.sub(r"[^\w%$]", "", txt or "").replace("_", "")
        if len(t) >= 3 and (sum(c.isalpha() for c in t) >= 2 or sum(c.isdigit() for c in t) >= 2):
            out.append((t, 100.0 * (d["top"][k] + d["height"][k] / 2) / H))
    return out


def limpar_ocr(lidos: dict[int, list[tuple[str, float]]]) -> dict[int, str]:
    """Texto da tela por quadro, SEM o que repete na mesma altura em muito plano (legenda da fala, marca d'água): isso não é
    peça da cena. Sobra só o que apareceu num lugar que não é fixo, com pelo menos duas palavras de 4 letras ou uma de 9."""
    com = {q: ts for q, ts in lidos.items() if ts}
    faixas: dict[int, set[int]] = {}
    for q, ts in com.items():
        for _, y in ts:
            faixas.setdefault(int(y // 4), set()).add(q)
    fixas = {b for b, qs in faixas.items() if len(qs) >= 6 and len(qs) >= 0.3 * len(com)}
    out = {}
    for q, ts in com.items():
        ok = [t for t, y in ts if int(y // 4) not in fixas and int(y // 4) - 1 not in fixas and int(y // 4) + 1 not in fixas]
        if sum(len(t) >= 4 for t in ok) >= 2 or sum(len(t) >= 9 for t in ok) >= 1:
            out[q] = " ".join(ok[:7])
    return out


def _assinatura(video: Path) -> str:
    st = video.stat()
    return hashlib.sha1(f"{video.name}:{st.st_size}:{int(st.st_mtime)}:{VERSAO_CACHE}".encode()).hexdigest()[:8]


def extrair_meios(video: Path, qms: list[int], pasta: Path, sig: str, tmp: Path | None = None) -> dict[int, str]:
    """Quadro do meio de cada plano, numa passada só (cv2): {qm: nome do jpg de 360 px em `pasta`}. Se `tmp`, grava lá também
    uma cópia de 640 px (a que o OCR lê)."""
    import cv2
    pasta.mkdir(parents=True, exist_ok=True)
    falta = {q for q in qms if not ((pasta / f"{sig}-{q:06d}.jpg").is_file() and (pasta / f"{sig}-{q:06d}.jpg").stat().st_size > 0)}
    if tmp is not None:
        falta = set(qms)
    out = {q: f"{sig}-{q:06d}.jpg" for q in qms if q not in falta}
    if falta:
        cap = cv2.VideoCapture(str(video))
        fim, i = max(falta), 0
        while i <= fim and cap.grab():
            if i in falta:
                ok, f = cap.retrieve()
                if ok:
                    h, w = f.shape[:2]
                    nome = f"{sig}-{i:06d}.jpg"
                    cv2.imwrite(str(pasta / nome), cv2.resize(f, (LARGURA, max(2, round(h * LARGURA / w))), interpolation=cv2.INTER_AREA),
                                [cv2.IMWRITE_JPEG_QUALITY, 82])
                    if tmp is not None:
                        cv2.imwrite(str(tmp / f"{i}.jpg"), cv2.resize(f, (640, max(2, round(h * 640 / w))), interpolation=cv2.INTER_AREA))
                    out[i] = nome
            i += 1
        cap.release()
    return out


def estudo_leve(video: Path, pasta: Path) -> dict:
    """O mesmo medidor do estudo quadro a quadro (planos, transições, câmera), sem fala nem folhas: grátis, ~0,4x o tempo do
    vídeo. Guardado em `estudo-leve.json`; devolve o dict no formato de um vídeo do `estudo.json`."""
    arq, sig = pasta / "estudo-leve.json", _assinatura(video)
    d = ler_json(arq, None) if arq.is_file() else None
    if d and d.get("sig") == sig:
        return d["v"]
    import estudo_quadros as eq
    inf = eq.info(video)
    q = eq.medir_quadros(video, inf["fps"])
    fps, n = inf["fps"], q["n"]
    tr = eq.transicoes(q, fps)
    pls = eq.planos(tr, n, fps)
    prop = (inf["altura"] / inf["largura"]) if inf["largura"] else 16 / 9
    durs = [p["dura_s"] for p in pls]
    dur = n / fps if n else inf["duracao"]
    v = {"nome": video.stem, "duracao": round(dur, 2), "fps": fps, "quadros": n, "leve": True,
         "planos": {"n": len(pls), "por_min": round(len(pls) / dur * 60, 1) if dur else None, "media_s": eq._media(durs),
                    "mediana_s": eq._med(durs), "lista": pls},
         "transicoes": tr, "camera": eq.camera(q, tr, pls, fps, prop), "numeros": []}
    pasta.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"sig": sig, "v": v}, ensure_ascii=False), encoding="utf-8")
    return v


def _construir(src: dict, pasta: Path, sig: str) -> dict:
    video = src["video"]
    v = src["video_estudo"] or estudo_leve(video, pasta)
    lista = (v.get("planos") or {}).get("lista") or []
    qms = [meio(p) for p in lista]
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")       # tesseract em 4 processos de 1 fio cada: mais rápido que 1 de 4
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        nomes = extrair_meios(video, qms, pasta, sig, tmp)
        alvos = [(meio(p), tmp / f"{meio(p)}.jpg") for p in lista if (p.get("dura_s") or 0) >= RAJADA_S and (tmp / f"{meio(p)}.jpg").is_file()]
        with ThreadPoolExecutor(max_workers=4) as ex:
            lidos = dict(zip([q for q, _ in alvos], ex.map(lambda a: _ocr_tokens(a[1]), alvos)))
    itens = classificar(v, pecas_do_cenas(video), limpar_ocr(lidos))
    itens = [dict(it, arquivo=nomes[it["qm"]], tempo=tempo(it["t"]), dura=tempo(it["dura_s"])) for it in itens if it["qm"] in nomes]
    destacar(itens)
    return {"sig": sig, "ref_id": src["ref_id"], "duracao": round(src["duracao"], 2), "fonte": "leve" if v.get("leve") else "estudo",
            "quadros": itens, "resumo": resumir(itens, v), "total": len(itens)}


_EM_CURSO: dict[str, threading.Thread] = {}
_ERRO: dict[str, str] = {}
_TRANCA = threading.Lock()


def tira(slug: str, ref: str = "", esperar: bool = False) -> dict:
    """{estado: 'pronto'|'preparando'|'erro'|'sem', quadros, resumo, total, fonte, ref_id}. O que falta (estudo leve, quadros do meio,
    OCR) é feito UMA vez, em segundo plano, e fica em app/.cache/storyboard/<slug>/<ref>/; `esperar=True` faz na hora (testes, CLI)."""
    if not re.fullmatch(r"[a-z0-9-]+", slug or "") or not (FORMATOS / slug).is_dir():
        return {"estado": "sem", "quadros": []}
    src = fonte(slug, ref)
    if not src or not src["duracao"]:
        return {"estado": "sem", "quadros": []}
    pasta = CACHE / slug / src["ref_id"]
    sig = _assinatura(src["video"])
    arq = pasta / f"tira-{sig}.json"
    d = ler_json(arq, None) if arq.is_file() else None
    if d and all((pasta / q["arquivo"]).is_file() for q in d.get("quadros") or []):
        return dict(d, estado="pronto")
    chave = f"{slug}/{src['ref_id']}/{sig}"

    def trabalho():
        try:
            r = _construir(src, pasta, sig)
            if r["quadros"]:
                pasta.mkdir(parents=True, exist_ok=True)
                arq.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
                _ERRO.pop(chave, None)
            else:
                _ERRO[chave] = "nenhum plano achado no vídeo"
        except Exception as e:  # noqa: BLE001   sem ffmpeg/cv2 ou vídeo ruim: a página vive sem a tira
            _ERRO[chave] = str(e)[:120]
        finally:
            _EM_CURSO.pop(chave, None)

    if esperar:
        trabalho()
        d = ler_json(arq, None) if arq.is_file() else None
        return dict(d, estado="pronto") if d else {"estado": "erro", "quadros": [], "erro": _ERRO.get(chave, "")}
    with _TRANCA:
        if chave in _ERRO and chave not in _EM_CURSO:
            return {"estado": "erro", "quadros": [], "erro": _ERRO[chave]}
        if chave not in _EM_CURSO:
            t = threading.Thread(target=trabalho, daemon=True)
            _EM_CURSO[chave] = t
            t.start()
    return {"estado": "preparando", "quadros": [], "ref_id": src["ref_id"]}


def quadros(slug: str, n: int = LIMITE_TIRA, ref: str = "") -> list[dict]:
    """Os planos que a tira mostra de cara (esperando o cache ficar pronto); [] se o estilo não tem vídeo."""
    return [q for q in tira(slug, ref, esperar=True).get("quadros") or [] if q.get("destaque")]


def caminho(slug: str, nome: str, ref: str = "") -> Path | None:
    """O jpg do cache, só se o nome for de um quadro nosso (sem barra, sem '..'). `ref` = pasta da referência (ref_id)."""
    if not re.fullmatch(r"[a-z0-9-]+", slug or "") or not NOME_OK.match(nome or "") or (ref and not re.fullmatch(r"[A-Za-z0-9._-]+", ref)) or ref in (".", ".."):
        return None
    p = CACHE / slug / ref / nome if ref else CACHE / slug / nome
    return p if p.is_file() else None


if __name__ == "__main__":
    r = tira(sys.argv[1] if len(sys.argv) > 1 else "editorial", sys.argv[2] if len(sys.argv) > 2 else "", esperar=True)
    print(f"{r.get('estado')}: {len(r['quadros'])} planos ({sum(1 for q in r['quadros'] if q.get('destaque'))} de cara) [{r.get('fonte')}]")
    print("  " + " · ".join(f"{t['rotulo']} {t['n']}" for t in (r.get("resumo") or {}).get("tipos", [])))
    print("  " + " · ".join(f"{n['valor']} {n['rotulo']}" for n in (r.get("resumo") or {}).get("numeros", [])))
    for q in r["quadros"]:
        print(f"{q['tempo']:>8} {q['dura']:>7}  {q['legenda']}  {('«' + q['fala'] + '»') if q['fala'] else ''}{'' if q['destaque'] else '  (fora da tira)'}")
