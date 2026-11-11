#!/usr/bin/env python3
"""conferir_video: conferência automática de um vídeo gravado pronto (a IA não consegue pular: ela roda e o Estúdio cobra).

    python3 app/ferramentas/conferir_video.py <mp4> --sandbox <sandbox>

Grava <sandbox>/qa/conferir.json ({"ok", "avisos", "checagens"}) e sai com 1 se reprovar. Confere:
  formato 1080x1920 com áudio · fim de frase (words.json) · cauda sem ruído (G10) · tela preta e imagem congelada fora do fim ·
  fala entre -17 e -11 LUFS (G9) · folha de 1 quadro por segundo (G16) · sobra de legenda antiga junto da caixa (frase-fixa) ·
  texto em cima do rosto (G3, Faixa com cenas: com o João em tela cheia a faixa branca e vermelha não cobre olhos, nariz nem boca) ·
  dinamismo (G26): maior trecho PARADO (sem corte nem movimento), maior trecho sem TROCA visual e trocas por minuto, contra a régua do estilo.
Os avisos saem em português curto, do jeito que o Em andamento mostra.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ffprobe  # noqa: E402

LUFS_MIN, LUFS_MAX = -17.0, -11.0
PRETO_MAX, CONGELADO_MAX, FIM_LIVRE = 0.4, 0.6, 1.0   # segundos; o último segundo pode escurecer/congelar de propósito
ESCURO_YAVG, ESCURO_MIN = 40, 1.5   # luminância média (0-255) abaixo disso por 1,5 s seguidos = plano escuro demais, quase vazio


def _ff(args: list[str]) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True).stderr


def tem_audio(video: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def tamanho_do_formato(formato: str | None) -> tuple[int, int]:
    """1080x1920 (9:16) é o padrão; formato com "proporcao": "16:9" (ex.: legenda-no-lado) pede 1920x1080."""
    try:
        if formato:
            f = json.loads((Path(__file__).resolve().parents[2] / "formatos" / formato / "formato.json").read_text())
            if str(f.get("proporcao", "")).strip() == "16:9":
                return (1920, 1080)
    except Exception:  # noqa: BLE001
        pass
    return (1080, 1920)


def checar_formato(info: dict, audio: bool = True, tamanho: tuple[int, int] = (1080, 1920)) -> list[str]:
    av = []
    if (info.get("largura"), info.get("altura")) != tamanho:
        av.append(f"Tamanho {info.get('largura')}x{info.get('altura')}, o certo é {tamanho[0]}x{tamanho[1]}")
    if not audio:
        av.append("Vídeo sem áudio")
    return av


def checar_fim_de_frase(words: list[dict]) -> list[str]:
    """Só cobra se a transcrição tem pontuação (sem ela não dá pra saber onde a frase acaba)."""
    palavras = [str(w.get("word") or w.get("palavra") or "").strip() for w in words]
    palavras = [p for p in palavras if p]
    if not palavras:
        return []
    ultima = palavras[-1]
    if ultima.endswith(("...", "…")):
        return ["Termina no meio da frase"]
    if any(p.endswith((".", "!", "?")) for p in palavras) and not ultima.endswith((".", "!", "?")):
        return ["Termina no meio da frase"]
    return []


def _quadro_cinza(video: Path, t: float):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=270:480,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8)


TEXTO_MIN, FUNDO_LISO, DESVIO_FUNDO, DESVIO_TEXTO = 0.0015, 0.80, 14, 40   # 0,15% dos pontos longe do fundo = texto ou figura; 80% no fundo = cartão liso


def cartao_de_texto(video: Path, t0: float, t1: float) -> bool:
    """Cartão de texto do documentário: fundo liso (escuro ou claro) com letras ou figura. O blackdetect o chama de 'tela preta' e o
    freezedetect de 'imagem parada' (30-out-2026). Olha 3 quadros do trecho; preta de verdade não tem ponto fora do fundo e imagem
    congelada de cena real não tem 80% do quadro no mesmo tom."""
    import numpy as np
    try:
        for t in (t0 + 0.05, (t0 + t1) / 2, t1 - 0.08):
            q = _quadro_cinza(video, t).astype(np.int16)
            if not q.size:
                continue
            desvio = np.abs(q - int(np.median(q)))
            if float((desvio <= DESVIO_FUNDO).mean()) >= FUNDO_LISO and float((desvio > DESVIO_TEXTO).mean()) >= TEXTO_MIN:
                return True
    except Exception:
        pass
    return False


def trechos_escuros(video: Path) -> list[tuple[float, float]]:
    """(início, fim) dos trechos de ESCURO_MIN s ou mais com luminância média baixa: o blackdetect só pega preto total e deixa passar
    o plano com fundo quase preto e uma imagem mal visível (30-out-2026). Amostra 2 quadros por segundo, em miniatura."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf",
                        "fps=2,scale=96:-1,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    pontos = [(float(t), float(y)) for t, y in re.findall(r"pts_time:([\d.]+)\s+lavfi\.signalstats\.YAVG=([\d.]+)", r.stdout)]
    trechos, ini, ult = [], None, None
    for t, y in pontos + [(-1.0, 255.0)]:
        if y < ESCURO_YAVG:
            ini = t if ini is None else ini
            ult = t
        elif ini is not None:
            if ult - ini + 0.5 >= ESCURO_MIN:
                trechos.append((ini, ult + 0.5))
            ini = None
    return trechos


def checar_tela(video: Path, dur: float) -> list[str]:
    av = []
    log = _ff(["-i", str(video), "-an", "-vf", f"blackdetect=d={PRETO_MAX}:pix_th=0.10,freezedetect=n=0.003:d={CONGELADO_MAX}", "-f", "null", "-"])
    for ini, fim, d in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", log):
        if float(ini) < dur - FIM_LIVRE and not cartao_de_texto(video, float(ini), float(fim)):
            av.append(f"Tela preta em {float(ini):.0f} s")
    for ini, d in re.findall(r"freeze_start: ([\d.]+)(?:.*?freeze_duration: ([\d.]+))?", log, re.S):
        if float(ini) < dur - FIM_LIVRE and not cartao_de_texto(video, float(ini), float(ini) + float(d or CONGELADO_MAX)):
            av.append(f"Imagem parada em {float(ini):.0f} s")
    try:
        for ini, fim in trechos_escuros(video):
            if ini < dur - FIM_LIVRE and not cartao_de_texto(video, ini, fim):
                av.append(f"Plano escuro demais em {ini:.0f} s (quase vazio)")
    except Exception:
        pass
    return av[:4]


NITIDEZ_MIN, CONTRASTE_MIN, RUIM_MIN = 6.0, 20.0, 2   # variância do laplaciano e desvio da luminância (quadro 270x480); segundos seguidos


def checar_nitidez(video: Path, dur: float) -> list[str]:
    """B-roll borrado ou lavado (foco perdido, cartão azul sem imagem) passa pela conferência de som e tela preta: olha 1 quadro por
    segundo e avisa trecho de RUIM_MIN s ou mais com pouca nitidez ou pouco contraste. Cartão liso de texto não conta."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf", "fps=1,scale=270:480,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    n = 270 * 480
    av, ini, motivo = [], None, ""
    quadros = np.frombuffer(r.stdout, np.uint8)
    quadros = quadros[:len(quadros) // n * n].reshape(-1, 480, 270).astype(np.float32)
    for i, q in enumerate(list(quadros) + [None]):
        ruim = ""
        if q is not None and i < dur - FIM_LIVRE:
            lap = q[1:-1, 1:-1] * 4 - q[:-2, 1:-1] - q[2:, 1:-1] - q[1:-1, :-2] - q[1:-1, 2:]
            ruim = "desfocado" if lap.var() < NITIDEZ_MIN else "baixo contraste" if q.std() < CONTRASTE_MIN else ""
        if ruim and ini is None:
            ini, motivo = i, ruim
        elif not ruim and ini is not None:
            if i - ini >= RUIM_MIN and not cartao_de_texto(video, ini, i):
                av.append(f"Imagem {motivo} em {ini} s (b-roll que não mostra nada?)")
            ini = None
    return av[:2]


def medir_lufs(video: Path) -> float | None:
    log = _ff(["-i", str(video), "-vn", "-af", "ebur128=peak=none", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    return float(m[-1]) if m else None


# ───────────────────────── dinamismo (REGRAS.md G26) ─────────────────────────
# Medido na diferença entre quadros (15 amostras por segundo, 108x192, cinza): imagem congelada dá 0,00; câmera andando sobre foto
# ~2; corte seco 15 a 60+ (calibrado em 29/10 em vídeos nossos: Editorial, faixa-com-cenas, frase-fixa, caixinha).
FPS_DIN, DIFF_PARADO, DIFF_CORTE = 15, 0.8, 14.0
PIXELS_MEXENDO = 0.0005   # quadro com ao menos 0,05% dos pixels mudando mais de 10 níveis (texto acendendo, mensagem entrando) NÃO está parado
RITMO_V = 2               # versão da medida: muda quando o jeito de medir muda (invalida o cache das referências)
PARADO_MAX_S = 2.0        # G26: nenhum trecho sem corte nem movimento por mais de 2 s (régua: maior parado das 15 referências 0,2 a 1,9 s)
SEM_TROCA_PADRAO_S = 12.0  # estilo gravado com cena de apoio, sem régua medida: uma troca visual a cada 12 s no máximo


def medir_dinamismo(video: Path, fps: int = FPS_DIN) -> dict:
    """{duracao_s, trocas, trocas_por_min, parado_max_s, parado_em_s, sem_troca_max_s, sem_troca_em_s, andando_pct}.
    O último segundo fica de fora (pode parar de propósito, como no resto da conferência)."""
    import numpy as np
    w, h = 108, 192
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf", f"fps={fps},scale={w}:{h},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    q = np.frombuffer(r.stdout, np.uint8)
    n = len(q) // (w * h)
    if n < fps * 2:
        return {"duracao_s": round(n / fps, 2), "trocas": 0, "trocas_por_min": 0.0, "parado_max_s": 0.0, "parado_em_s": 0.0,
                "sem_troca_max_s": 0.0, "sem_troca_em_s": 0.0, "andando_pct": 100.0}
    q = q[: n * w * h].reshape(n, h, w).astype(np.float32)
    dif = np.abs(np.diff(q, axis=0))
    d = dif.mean(axis=(1, 2))
    local = (dif > 10).mean(axis=(1, 2))               # fração de pixels que mudaram de verdade (pega o texto que acende)
    d, local = d[: max(1, len(d) - fps)], local[: max(1, len(d) - fps)]   # sem o último segundo
    dur = (len(d) + 1) / fps
    cortes = d > DIFF_CORTE
    parado = (d < DIFF_PARADO) & (local < PIXELS_MEXENDO)

    def maior(mascara):                               # (tamanho, início) da maior sequência True
        best = (0, 0); run = 0
        for i, v in enumerate(mascara):
            run = run + 1 if v else 0
            if run > best[0]:
                best = (run, i - run + 1)
        return best

    # parado: sequência sem movimento (um corte no meio quebra a sequência: corte é troca)
    p_n, p_i = maior(parado & ~cortes)
    idx = [-1] + [int(i) for i in np.where(cortes)[0]] + [len(d)]
    t_n, t_i = max(((b - a - 1, a + 1) for a, b in zip(idx, idx[1:])), default=(0, 0))
    return {"duracao_s": round(dur, 1), "trocas": int(cortes.sum()), "trocas_por_min": round(float(cortes.sum()) * 60 / dur, 1),
            "parado_max_s": round(p_n / fps, 1), "parado_em_s": round(p_i / fps, 1),
            "sem_troca_max_s": round((t_n + 1) / fps, 1), "sem_troca_em_s": round(t_i / fps, 1),
            "andando_pct": round(float((~parado).mean()) * 100, 1)}


def regua_dinamismo(formato: str | None) -> dict:
    """Limites do estilo, tirados das réguas medidas (formatos/<slug>/estudo-quadros/estudo.json): sem troca por no máximo
    5 planos de mediana (entre 2,5 e 10 s) e metade dos planos/min medidos (corte seco subconta o dissolve). Sem régua:
    estilo com cena de apoio ganha o padrão; estilo sem apoio (caixinha, frase-fixa, análise de tela) só é cobrado do parado."""
    r = {"sem_troca_max_s": None, "trocas_min": None, "origem": "estilo sem cena de apoio: só o trecho parado é cobrado"}
    if not formato:
        return r
    base = RAIZ / "formatos" / formato
    try:
        est = json.loads((base / "estudo-quadros" / "estudo.json").read_text(encoding="utf-8")).get("conjunto") or {}
        med, pm = est["planos.mediana_s"]["mediana"], est["planos.por_min"]["mediana"]
        return {"sem_troca_max_s": round(min(10.0, max(2.5, 5 * med)), 1), "trocas_min": round(pm * 0.5, 1),
                "origem": f"régua do estilo: {pm:.0f} planos/min, plano mediano de {med:.1f} s"}
    except Exception:
        pass
    try:
        f = json.loads((base / "formato.json").read_text(encoding="utf-8"))
        if (f.get("apoio") or {}).get("usa"):
            return {"sem_troca_max_s": SEM_TROCA_PADRAO_S, "trocas_min": round(60 / SEM_TROCA_PADRAO_S, 1),
                    "origem": "estilo com cena de apoio (sem régua medida): uma troca a cada 12 s no máximo"}
    except Exception:
        pass
    return r


def _sha_video(video: Path) -> str:
    import hashlib
    h = hashlib.sha1()
    with open(video, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def medidas_das_referencias(formato: str | None) -> list[dict]:
    """A mesma medir_dinamismo em cada formatos/<slug>/exemplo-*.mp4 (as referências SÃO a régua). Cache por sha do vídeo e versão da
    medida em app/.cache/ritmo-referencias.json: só mede de novo o que mudou."""
    if not formato:
        return []
    exs = sorted((RAIZ / "formatos" / formato).glob("exemplo-*.mp4"))
    if not exs:
        return []
    from _comum import CACHE
    arq = CACHE / "ritmo-referencias.json"
    try:
        cache = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    out, mudou = [], False
    for v in exs:
        try:
            k = f"{_sha_video(v)}:{RITMO_V}"
            if k not in cache:
                cache[k] = medir_dinamismo(v)
                mudou = True
            out.append(cache[k])
        except Exception:  # noqa: BLE001  (referência que não abre não calibra)
            continue
    if mudou:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            arq.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        except OSError:
            pass
    return out


def calibrar_pelas_referencias(reg: dict, formato: str | None) -> dict:
    """Toda checagem de ritmo tem de passar em todo exemplo do PRÓPRIO estilo (29-30/out: a régua reprovava as referências).
    Os limites sobem até o pior valor medido nas referências + 10% (nunca descem do que já valia): parado, sem troca e trocas/min."""
    ms = [m for m in medidas_das_referencias(formato) if m.get("duracao_s", 0) > 6]
    reg = {**reg, "parado_max_s": PARADO_MAX_S}
    if not ms:
        return reg
    folga = lambda x: round(x * 1.1 + 0.1, 1)
    reg["parado_max_s"] = max(PARADO_MAX_S, folga(max(m["parado_max_s"] for m in ms)))
    if reg["sem_troca_max_s"]:
        reg["sem_troca_max_s"] = max(reg["sem_troca_max_s"], folga(max(m["sem_troca_max_s"] for m in ms)))
    if reg["trocas_min"]:
        reg["trocas_min"] = min(reg["trocas_min"], round(min(m["trocas_por_min"] for m in ms) * 0.8, 1))
    if (reg["parado_max_s"], reg["sem_troca_max_s"], reg["trocas_min"]) != (PARADO_MAX_S, None, None):
        reg["origem"] += f" · limites calibrados nas {len(ms)} referência(s) do estilo"
    return reg


def checar_dinamismo(video: Path, formato: str | None = None, medida: dict | None = None) -> tuple[list[str], dict]:
    """(avisos, números). "Parado demais" = trecho sem corte nem movimento acima de 2 s; "Sem troca" e "Poucas trocas" contra a
    régua do estilo. Os números vão em checagens.dinamismo do qa/conferir.json."""
    m = medida or medir_dinamismo(Path(video))
    reg = calibrar_pelas_referencias(regua_dinamismo(formato), formato)
    av = []
    if m["parado_max_s"] > reg["parado_max_s"]:
        av.append(f"Parado demais: {m['parado_max_s']:.1f} s sem corte nem movimento em {m['parado_em_s']:.0f} s (o limite é {reg['parado_max_s']:.1f} s)")
    if reg["sem_troca_max_s"] and m["duracao_s"] > 6 and m["sem_troca_max_s"] > reg["sem_troca_max_s"]:
        av.append(f"Sem troca visual por {m['sem_troca_max_s']:.1f} s em {m['sem_troca_em_s']:.0f} s (o estilo aguenta {reg['sem_troca_max_s']:.1f} s)")
    if reg["trocas_min"] and m["duracao_s"] > 15 and m["trocas_por_min"] < reg["trocas_min"]:
        av.append(f"Poucas trocas: {m['trocas_por_min']:.0f}/min (a régua pede ao menos {reg['trocas_min']:.0f}/min)")
    return av, {**m, "regua": reg}


def _quadros(video: Path, dur: float, td: Path, tag: str):
    import numpy as np
    from PIL import Image
    out = []
    for k, f in enumerate((0.1, 0.5, 0.9)):
        q = td / f"{tag}{k}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur * f:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=1080:1920", str(q)], check=True)
        out.append(np.asarray(Image.open(q).convert("L")))
    return out


def sobra_de_legenda(sb: Path, video: Path, dur: float) -> list[str]:
    """frase-fixa: pixel branco parado, igual no bruto e no final, na faixa de 40 px acima e abaixo da caixa nova."""
    cj = sb / "camada.json"
    if not cj.is_file():
        return []
    import numpy as np
    import camada
    c = json.loads(cj.read_text(encoding="utf-8"))
    bruto = RAIZ / str(c.get("video") or "")
    if not bruto.is_file():
        return []
    bb = camada.caixa_png(c).getbbox()
    h = (bb[3] - bb[1]) if bb else 0
    if c.get("tipo") == "caixinha":   # na caixinha o y é o TOPO da caixa (caixinha.py), não o centro
        topo, base = int(c["y"]), int(c["y"] + h)
    else:
        topo, base = int(c["y"] - h / 2), int(c["y"] + h / 2)
    faixas = [(max(0, topo - 40), topo), (base, min(1920, base + 40))]
    dur_b = float(ffprobe(bruto).get("duracao") or dur)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        fin, bru = _quadros(video, dur, td, "f"), _quadros(bruto, dur_b, td, "b")
    for y0, y1 in faixas:
        if y1 - y0 < 10:
            continue
        parado = np.ones((y1 - y0, 1080), bool)
        for q in fin + bru:
            parado &= q[y0:y1] > 200
        frac = parado.mean()
        if 0.0005 < frac < 0.08:   # parede ou camisa branca ocupa muito mais que letra
            return ["Sobrou letra da legenda antiga perto da caixa"]
    return []


def checar_cenas_repetidas(sb: Path) -> list[str]:
    """Cenas seguidas com o mesmo texto ou a mesma mídia (ex.: fecho em duas telas iguais): junte numa só."""
    cj = sb / "cenas.json"
    if not cj.is_file():
        return []
    cenas = json.loads(cj.read_text(encoding="utf-8")).get("cenas") or []
    avisos = []
    for a, b in zip(cenas, cenas[1:]):
        for k in ("texto", "frase", "titulo", "imagem", "clipe", "arquivo"):
            va, vb = a.get(k), b.get(k)
            if isinstance(va, str) and va.strip() and va.strip().lower() == str(vb or "").strip().lower():
                avisos.append(f"Cenas seguidas repetem o mesmo {k} em {float(b.get('de') or 0):.0f} s: junte numa cena só")
                break
    return avisos


def _ler_palavras(p: Path) -> list[dict]:
    w = json.loads(p.read_text(encoding="utf-8"))
    return (w.get("words", w) if isinstance(w, dict) else w) or []


def fala_do_video(sandbox: Path, dur: float) -> tuple[list[dict], float | None]:
    """A fala do vídeo ENTREGUE (não a do bruto): qa/words-saida.json e work/legenda/words.json já estão nos tempos dele.
    work/words.json é do bruto: com work/CORTE.json fica só o que foi mantido e o fim vira a soma dos trechos mantidos.
    Nunca devolve fim_fala maior que a duração do vídeo."""
    for rel in ("qa/words-saida.json", "work/legenda/words.json"):
        p = sandbox / rel
        if p.is_file():
            words = _ler_palavras(p)
            fim = float(words[-1].get("end") or 0) if words else None
            return words, (min(fim, dur) if fim is not None and dur else fim)
    p = next((q for q in (sandbox / "work/words.json", sandbox / "words.json") if q.is_file()), None)
    if not p:
        return [], None
    words = _ler_palavras(p)
    corte = sandbox / "work/CORTE.json"
    if words and corte.is_file():
        segs = [s for s in (json.loads(corte.read_text(encoding="utf-8")).get("segmentos") or []) if s.get("manter")]
        if segs:
            dentro = [w for w in words if any(float(s["t0"]) - 0.05 <= float(w.get("start") or 0) < float(s["t1"]) for s in segs)]
            words = dentro or words
            return words, min(sum(float(s["t1"]) - float(s["t0"]) for s in segs), dur) if dur else None
    fim = float(words[-1].get("end") or 0) if words else None
    return words, (min(fim, dur) if fim is not None and dur else fim)


def dur_do_render(m: dict) -> float:
    return float(m.get("duracao_s") or 0)


def checar_cartoes(sandbox: Path) -> tuple[list[str], dict]:
    """Só pro formato imagens-na-fala (e qualquer outro que grave `qa/medidas.json` com `media_na_tela`): confere o que o render fez contra a
    régua medida na referência. Sem esse arquivo não faz nada (os outros formatos não mudam). Reprova: média de cartões na tela < 2,3;
    < 26 cartões por minuto; rosto com mais de 42% da largura (bruto de perto demais); cartão deitado ou estreito (largura < 370 px, C < 420 px,
    altura/largura fora de 1,10 a 1,80); legenda sobre fundo claro (> 120) sem contorno de 5 px; imagem sem nota do casar_imagem ou sem a técnica
    em origem.json; r3: saturação mediana dos cartões < 60 ou menos da metade com >= 60, luminância mediana fora de 80 a 130, borda > 30, texto legível,
    sujeito < 35% da área, gravura acima de 1/3, mais de 2 momentos com 2+ cartões saindo juntos, intervalo mediano de entradas fora de 1,5 a 2,5 s,
    < 30% dos cartões atravessando uma virada, < 80% com a palavra dita casada, rosto p95 > 46% ou a < 2,5% de um cartão; 2 cartões do mesmo
    artista na tela ao mesmo tempo.
    """
    f = Path(sandbox) / "qa" / "medidas.json"
    if not f.is_file():
        return [], {}
    m = json.loads(f.read_text(encoding="utf-8"))
    if "media_na_tela" not in m:
        return [], {}
    av: list[str] = []
    if m["media_na_tela"] < 2.3:
        av.append(f"Poucos cartões na tela: média {m['media_na_tela']} (a referência tem 2,77; o piso é 2,3)")
    if m["cartoes_por_min"] < 26:
        av.append(f"Poucos cartões: {m['cartoes_por_min']} por minuto (a referência tem 30; o piso é 26)")
    rq = m.get("rosto_no_quadro")
    if rq and rq["w"] > 0.42 * 1080:
        av.append(f"Rosto grande demais: {rq['w']} px = {rq['w'] / 10.8:.0f}% da largura (a referência tem 39%; o teto é 42%). Grave a câmera mais longe")
    for c in m.get("cartoes_lista", []):
        x, y, w, h = c["box"]
        minimo = 420 if c["slot"] == "C" else 370
        if w < minimo or not 1.095 <= h / w <= 1.805:
            av.append(f"Cartão {c['imagem']} fora da régua: {w}x{h} (largura mínima {minimo}, altura/largura de 1,10 a 1,80)")
    lum = m.get("legenda_fundo_lum")
    if lum is not None and lum > 120 and (m.get("legenda_contorno_px") or 0) < 5:
        av.append(f"Legenda sobre fundo claro (luminância {lum:.0f}) sem contorno de 5 px")
    num: dict = {"media_na_tela": m["media_na_tela"], "cartoes_por_min": m["cartoes_por_min"], "rosto_w": rq["w"] if rq else None}
    cs = m.get("cartoes_lista", [])
    org_f = Path(sandbox) / "imagens" / "origem.json"
    org = {Path(o["arquivo"]).name: o for o in json.loads(org_f.read_text(encoding="utf-8"))} if org_f.is_file() else {}
    # r3: paleta, texto e borda do CARTÃO (do render; sem isso, da imagem em origem.json), tempo próprio de cada posição, palavra casada, rosto
    uni: dict = {}
    for c in cs:
        n = Path(c["imagem"]).name
        o = org.get(n, {})
        uni.setdefault(n, {k: c.get(k, o.get(k)) for k in ("sat", "lum", "borda", "sujeito_pct", "palavras_texto")})
    import statistics as st
    # v2 "Vegas literal" (05-nov-2026): peça própria (papel de jornal, post, caixa de texto) não é pintura nem foto, então fica fora das medianas de saturação e luminância
    sat = [v["sat"] for n_, v in uni.items() if v["sat"] is not None and not org.get(n_, {}).get("propria")]
    lum = [v["lum"] for n_, v in uni.items() if v["lum"] is not None and not org.get(n_, {}).get("propria")]
    if sat:
        ms = st.median(sat)
        num["sat_mediana"] = round(ms, 1)
        if ms < 60:
            av.append(f"Paleta apagada: saturação mediana dos cartões {ms:.0f} (a referência é pintura em cor; o piso é 60)")
        if sum(1 for x in sat if x >= 60) < len(sat) / 2:
            av.append(f"Só {sum(1 for x in sat if x >= 60)} de {len(sat)} cartões com saturação >= 60 (o mínimo é metade)")
    if lum:
        ml = st.median(lum)
        num["lum_mediana"] = round(ml, 1)
        if not 80 <= ml <= 130:
            av.append(f"Cartões {'claros' if ml > 130 else 'escuros'} demais: luminância mediana {ml:.0f} (a faixa é 80 a 130)")
    for n, v in uni.items():
        # 05-nov-2026 (reel da nutri): peça PRÓPRIA (`"propria": true` em imagens/origem.json: o anúncio e a legenda do anúncio, feitos com texto de
        # propósito pra o público LER) não é pintura: borda, texto e sujeito não valem pra ela. Só essas 3 checagens, só pra quem tem a marca;
        # paleta, casar_imagem, mesmo artista e todo o resto seguem valendo, e nenhuma pintura é afrouxada.
        if org.get(n, {}).get("propria"):
            continue
        teto_borda = 38 if org.get(n, {}).get("tecnica") == "fotografia" else 30   # variante Vegas literal: foto editorial tem textura natural (comida, tecido), a pintura não; teto 38 só pra tecnica "fotografia"
        if v["borda"] is not None and v["borda"] > teto_borda:
            av.append(f"Cartão {n} cheio de traço fino: densidade de borda {v['borda']:.0f} (o teto é {teto_borda}; a 400 px vira textura)")
        if v["palavras_texto"]:
            av.append(f"Cartão {n} tem texto legível ({v['palavras_texto']} palavra(s)): disputa com a legenda")
        if v["sujeito_pct"] is not None and v["sujeito_pct"] < 35:
            av.append(f"Cartão {n} sem um sujeito que se leia: ocupa {v['sujeito_pct']:.0f}% da área (o mínimo é 35%)")
    saem = sorted(round(c["sai"], 2) for c in cs if c["sai"] < dur_do_render(m) - 0.05)
    juntas = {t for t in saem if sum(1 for u in saem if abs(u - t) <= 0.05) >= 2}
    num["saidas_juntas"] = len(juntas)
    teto = max(2, round(dur_do_render(m) * 3 / 49))
    if len(juntas) > teto:
        av.append(f"{len(juntas)} momentos com 2 ou mais cartões saindo no mesmo quadro (o teto é {teto}): cada posição tem o seu tempo, não troca em trio")
    iv = m.get("intervalo_novo_mediano_s")
    if iv is not None:
        num["intervalo_entradas_mediano_s"] = iv
        if not 1.5 <= iv <= 2.5:
            av.append(f"Entradas de cartão em rajada ou espaçadas demais: intervalo mediano {iv} s (a faixa é 1,5 a 2,5 s)")
    atr = m.get("cartoes_atravessam_virada_pct")
    if atr is not None and atr < 30:
        av.append(f"Só {atr}% dos cartões atravessam uma virada de ideia (o mínimo é 30%)")
    com_pal = [c for c in cs if c.get("palavra")]
    ok_pal = [c for c in cs if c.get("palavra_ok")]
    num["palavra_casada"] = f"{len(ok_pal)}/{len(cs)}"
    if cs and len(ok_pal) < 0.8 * len(cs):
        av.append(f"Só {len(ok_pal)} de {len(cs)} cartões com a palavra dita casada (o cartão nomeia a palavra e ela cai até 2,5 s depois dele; o mínimo é 80%)")
    if m.get("rosto_p95_w_pct") is not None:
        num["rosto_p95_w_pct"] = m["rosto_p95_w_pct"]
        if m["rosto_p95_w_pct"] > 46:
            av.append(f"Rosto chega a {m['rosto_p95_w_pct']}% da largura (p95; o teto é 46%): a pessoa se inclina pra câmera")
        if m.get("rosto_amostras_com_folga_menor_2_5"):
            av.append(f"Rosto a menos de 2,5% da largura de um cartão em {m['rosto_amostras_com_folga_menor_2_5']} de {m['rosto_amostras']} amostras (folga mínima {m['rosto_folga_min_pct']}%)")
    if org:
        usadas = [Path(c["imagem"]).name for c in cs]
        sem = [n for n in dict.fromkeys(usadas) if "casar" not in org.get(n, {}) or "tecnica" not in org.get(n, {})]
        if sem:
            av.append("Imagem sem nota do casar_imagem ou sem técnica em origem.json: " + ", ".join(sem))
        fracas = [n for n in dict.fromkeys(usadas) if org.get(n, {}).get("casar") is not None and (org[n]["casar"] < 0.19 or org[n].get("casa") is False)]
        if fracas:
            av.append("Imagem que não casa com o que o cartão ilustra (casar_imagem < 0,19 ou fala errada): " + ", ".join(fracas))
        gravura = [n for n in dict.fromkeys(usadas) if org.get(n, {}).get("tecnica") in ("gravura", "xilogravura", "litografia", "desenho")]
        if usadas and len(gravura) > len(set(usadas)) / 3 + 0.01:
            av.append(f"{len(gravura)} de {len(set(usadas))} imagens em gravura: a referência é pintura em cor, gravura entra no máximo em 1/3")
        num["imagens_em_gravura"] = f"{len(gravura)}/{len(set(usadas))}"
        for i, a in enumerate(cs):
            for b in cs[i + 1:]:
                ea, eb = org.get(Path(a["imagem"]).name, {}), org.get(Path(b["imagem"]).name, {})
                if a["t"] < b["sai"] and b["t"] < a["sai"] and ea.get("artista") and ea.get("artista") == eb.get("artista") and not str(ea["artista"]).startswith("anonimo"):
                    av.append(f"Dois cartões do mesmo artista juntos na tela: {a['imagem']} e {b['imagem']} ({ea['artista']})")
    return av, num


def conferir(video: Path, sandbox: Path, formato: str | None = None) -> dict:
    video, sandbox = Path(video), Path(sandbox)
    if not video.is_file() or not sandbox.is_dir():   # caminho partido por espaço criava pasta lixo (30-out-2026): agora é erro
        raise FileNotFoundError(f"conferir_video: não achei {'o vídeo ' + str(video) if not video.is_file() else 'a pasta ' + str(sandbox)} "
                                "(caminho com espaço? ponha entre aspas)")
    avisos: list[str] = []
    checagens: dict = {}
    info = ffprobe(video)
    dur = float(info.get("duracao") or 0)
    avisos += checar_formato(info, tem_audio(video), tamanho_do_formato(formato))
    try:
        words, fim_fala = fala_do_video(sandbox, dur)
        if words:
            avisos += checar_fim_de_frase(words)
            checagens["fim_fala"] = fim_fala
    except Exception as e:  # noqa: BLE001
        checagens["words_erro"] = str(e)
    import checar_cauda
    ok_c, msg_c = checar_cauda.checar(video, checagens.get("fim_fala"))
    checagens["cauda"] = msg_c
    if not ok_c:
        avisos.append("Ruído no fim do áudio")
    avisos += checar_tela(video, dur)
    try:
        avisos += checar_nitidez(video, dur)
    except Exception as e:  # noqa: BLE001
        checagens["nitidez_erro"] = str(e)
    try:
        av_d, num_d = checar_dinamismo(video, formato)
        avisos += av_d
        checagens["dinamismo"] = num_d
    except Exception as e:  # noqa: BLE001
        checagens["dinamismo_erro"] = str(e)
    try:
        av_c, num_c = checar_cartoes(sandbox)
        avisos += av_c
        if num_c:
            checagens["cartoes"] = num_c
    except Exception as e:  # noqa: BLE001
        checagens["cartoes_erro"] = str(e)
    lufs = medir_lufs(video)
    checagens["lufs"] = lufs
    if lufs is not None and not LUFS_MIN <= lufs <= LUFS_MAX:
        avisos.append(f"Voz em {lufs:.0f} LUFS (o certo é entre -17 e -11)")
    try:
        avisos += sobra_de_legenda(sandbox, video, dur)
    except Exception as e:  # noqa: BLE001
        checagens["sobra_erro"] = str(e)
    try:
        avisos += checar_cenas_repetidas(sandbox)
    except Exception as e:  # noqa: BLE001
        checagens["cenas_repetidas_erro"] = str(e)
    try:
        import texto_fora_do_rosto
        av_r, num_r = texto_fora_do_rosto.checar(video, sandbox, dur)
        avisos += av_r
        if num_r:
            checagens["texto_no_rosto"] = num_r
    except Exception as e:  # noqa: BLE001
        checagens["texto_no_rosto_erro"] = str(e)
    try:
        import folha
        qa = sandbox / "qa"
        qa.mkdir(parents=True, exist_ok=True)
        folha.folha(video, qa / "folha-1s.jpg", passo=1.0)
        checagens["folha"] = "qa/folha-1s.jpg"
    except Exception as e:  # noqa: BLE001
        checagens["folha_erro"] = str(e)
    res = {"ok": not avisos, "avisos": avisos, "checagens": checagens, "video": str(video)}
    (sandbox / "qa").mkdir(parents=True, exist_ok=True)
    (sandbox / "qa/conferir.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--sandbox", type=Path, required=True)
    ap.add_argument("--formato", default=None, help="slug do estilo (a régua de dinamismo vem de formatos/<slug>)")
    a = ap.parse_args()
    try:
        r = conferir(a.video.expanduser(), a.sandbox.expanduser(), a.formato)
    except FileNotFoundError as e:
        sys.exit(str(e))
    print("OK" if r["ok"] else "REPROVADO: " + "; ".join(r["avisos"]))
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
