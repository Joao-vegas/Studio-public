#!/usr/bin/env python3
"""
camada — o texto do vídeo como CAMADA editável por cima do vídeo limpo (formatos Frase fixa e Caixinha de perguntas;
a caixinha é desenhada pelo caixinha.py, com "tipo": "caixinha" no camada.json).

O vídeo fica sem texto (o corte); a caixa com a frase mora em <pasta>/camada.json. Na tela (/camada) o João troca
o texto, a fonte, o tamanho, as cores e a posição, vê a prévia na hora e só então salva: aí a caixa é queimada no vídeo.
A prévia e o vídeo usam o MESMO desenho (caixa_png), então o que ele vê é o que sai.

    camada.json: {"video": <vídeo limpo, relativo à raiz>, "saida": <mp4 final>, "texto", "fonte", "tamanho",
                  "cor_caixa", "cor_texto", "y", "largura", "pad_x", "pad_y", "raio"}

    python3 camada.py renderizar <pasta>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, agora  # noqa: E402

W, H = 1080, 1920
PASTA_FONTES = Path.home() / "Library" / "Fonts"
FONTES = {   # nome na tela → arquivo (só as que estão instaladas aparecem)
    "Barlow SemiBold": "Barlow-SemiBold.ttf", "Barlow Black": "Barlow-Black.ttf", "Bebas Neue": "BebasNeue-Regular.ttf",
    "Anton": "Anton-Regular.ttf", "Gotham Bold": "Gotham-Bold.otf", "Gotham Black": "Gotham-Black.otf",
    "Inter Bold": "Inter-Bold.otf", "Helvetica Bold": "Helvetica-Bold.ttf", "League Spartan": "LeagueSpartan-Bold.otf",
    "Playfair Bold": "PlayfairDisplay-Bold.ttf", "Futura Condensed": "Futura Condensed Extra Bold.otf",
}
PADRAO = {"texto": "", "fonte": "Barlow SemiBold", "tamanho": 60, "cor_caixa": "#000000", "cor_texto": "#FFFFFF",
          "y": 1430, "largura": 928, "pad_x": 34, "pad_y": 20, "raio": 22}


def fontes() -> list[str]:
    return [n for n, f in FONTES.items() if (PASTA_FONTES / f).is_file()]


def _int(v, lo, hi, padrao):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return padrao


def _cor(v, padrao):
    v = str(v or "").strip()
    if v == "transparente":
        return v
    v = v if v.startswith("#") else "#" + v
    try:
        int(v[1:], 16)
        return v.upper() if len(v) == 7 else padrao
    except ValueError:
        return padrao


def limpar(p: dict) -> dict:
    """Parâmetros da tela → valores válidos (nada de fora dos limites chega no desenho)."""
    p = {**PADRAO, **{k: v for k, v in (p or {}).items() if v not in (None, "")}}
    if p.get("tipo") == "caixinha":   # Caixinha de perguntas: só a pergunta, o título e a altura mudam
        return {"tipo": "caixinha", "texto": str(p["texto"]).strip()[:400],
                "titulo": str(p.get("titulo") or "").strip()[:120], "y": _int(p["y"], 200, 1720, 255)}
    return {"texto": str(p["texto"]).strip()[:400],
            "fonte": p["fonte"] if p["fonte"] in FONTES else PADRAO["fonte"],
            "tamanho": _int(p["tamanho"], 28, 140, 60), "cor_caixa": _cor(p["cor_caixa"], "#000000"),
            "cor_texto": _cor(p["cor_texto"], "#FFFFFF"), "y": _int(p["y"], 200, 1720, 1430),
            "largura": _int(p["largura"], 360, 1040, 928), "pad_x": _int(p["pad_x"], 0, 120, 34),
            "pad_y": _int(p["pad_y"], 0, 120, 20), "raio": _int(p["raio"], 0, 80, 22)}


def _hex(c: str, a: int = 255):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (a,)


def _quebrar(d, txt: str, fonte, largura: int) -> list[str]:
    linhas, atual = [], ""
    for p in txt.split():
        t = (atual + " " + p).strip()
        if d.textlength(t, font=fonte) <= largura or not atual:
            atual = t
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) == 2:   # 2 linhas: equilibra pra não sobrar uma palavra sozinha embaixo
        palavras = txt.split()
        melhor = None
        for i in range(1, len(palavras)):
            a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
            la, lb = d.textlength(a, font=fonte), d.textlength(b, font=fonte)
            if la <= largura and lb <= largura and (melhor is None or abs(la - lb) < melhor[0]):
                melhor = (abs(la - lb), [a, b])
        if melhor:
            linhas = melhor[1]
    return linhas


def caixa_png(p: dict):
    """A camada (RGBA 1080x1920): caixa do tamanho do texto, centrada em x, com o centro em y."""
    from PIL import Image, ImageDraw, ImageFont
    p = limpar(p)
    if p.get("tipo") == "caixinha":
        import caixinha
        return caixinha.png(p)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not p["texto"]:
        return img
    d = ImageDraw.Draw(img)
    fonte = ImageFont.truetype(str(PASTA_FONTES / FONTES[p["fonte"]]), p["tamanho"])
    util = p["largura"] - 2 * p["pad_x"]
    linhas = []
    for bloco in p["texto"].splitlines():          # Enter na tela = quebra de linha que ele escolheu
        linhas += _quebrar(d, bloco, fonte, util) if bloco.strip() else [""]
    alt = int(p["tamanho"] * 1.18)
    larg = max(d.textlength(l, font=fonte) for l in linhas)
    bw, bh = larg + 2 * p["pad_x"], alt * len(linhas) + 2 * p["pad_y"]
    x0, y0 = (W - bw) / 2, p["y"] - bh / 2
    if p["cor_caixa"] != "transparente":
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], p["raio"], fill=_hex(p["cor_caixa"]))
    for i, l in enumerate(linhas):
        d.text((W / 2, y0 + p["pad_y"] + alt * i + alt / 2), l, font=fonte, fill=_hex(p["cor_texto"]), anchor="mm")
    return img


def carregar(pasta: Path) -> dict:
    return json.loads((Path(pasta) / "camada.json").read_text(encoding="utf-8"))


def salvar(pasta: Path, dados: dict) -> dict:
    atual = carregar(pasta)
    atual.update(limpar({**atual, **dados}))
    (Path(pasta) / "camada.json").write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    return atual


PUNCH_NIVEL = 0.08      # quanto o quadro se aproxima no punch (8%); a caixa não mexe e o cabelo não encosta nela
PUNCH_MIN_S, PUNCH_MAX_S, PUNCH_RAMPA_S = 3.0, 6.0, 0.28


def pontos_punch(video: Path, dur: float, livres: list[tuple[float, float]] | None = None) -> list[float]:
    """Onde o quadro troca (aproxima/volta): nas pausas da fala (fim de frase), 3 a 6 s uma da outra, pro vídeo nunca ficar
    parado (João, 29-out-2026: "as pessoas querem dopamina"). Sem pausa boa por perto, troca no meio do trecho, sem cortar a voz.
    `livres` (Faixa com cenas, 30-out-2026): só dentro destes trechos [(de, ate)] (o João em tela cheia, sem cena por cima); em cada
    trecho os pontos vêm em número par (o que abriu fecha antes da cena entrar), porque o filtro alterna aproxima/volta."""
    import re
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "silencedetect=noise=-32dB:d=0.18", "-f", "null", "-"],
                       capture_output=True, text=True)
    pausas = []
    ini = None
    for m in re.finditer(r"silence_(start|end): ([0-9.]+)", r.stderr):
        if m.group(1) == "start":
            ini = float(m.group(2))
        elif ini is not None:
            pausas.append((ini + float(m.group(2))) / 2)   # meio da pausa: troca "respirando"
            ini = None

    def corrida(de: float, ate: float) -> list[float]:
        pts, ultimo = [], de
        while ultimo < ate - PUNCH_MIN_S:
            bons = [x for x in pausas if ultimo + PUNCH_MIN_S <= x <= ultimo + PUNCH_MAX_S and x < ate - 1.0]
            prox = bons[0] if bons else ultimo + PUNCH_MAX_S - 1.0
            if prox >= ate - 1.0:
                break
            pts.append(round(prox, 2))
            ultimo = prox
        return pts

    if livres is None:
        return corrida(0.0, dur)
    pts = []
    for de, ate in livres:
        if ate - de < PUNCH_MIN_S + 1.0:
            continue
        g = corrida(de, ate)
        if len(g) % 2:   # fecha o que abriu; se sobrou menos de 2 s, o último ponto nem abre (pulso curto pisca)
            g.append(round(ate - PUNCH_RAMPA_S - 0.05, 2)) if ate - g[-1] >= 2.0 else g.pop()
        pts += g
    return pts


def filtro_punch(pts: list[float], rampa: float | None = None, nivel: float | None = None, ancora_y: float | None = None) -> str:
    """scale que cresce/volta a cada ponto + crop 1080x1920; sem pontos, o scale simples de sempre. `rampa` e `nivel` trocam
    o padrão (0,28 s e 8%, suave): a Faixa com cenas usa 0,04 s e 12%, que a medida de dinamismo enxerga como troca.
    `ancora_y` (0 a 1, fração da altura): zoom em torno desse ponto e do centro na horizontal. Sem ele vale o recorte de sempre, que o
    ffmpeg lê com iw/ih do início (1080x1920), então na prática ancora no canto de cima à esquerda e o rosto DESCE 12%: a Faixa com
    cenas usa 0,5 pra frase do peito não ficar em cima do queixo (30-out-2026)."""
    rampa = PUNCH_RAMPA_S if rampa is None else rampa
    nivel = PUNCH_NIVEL if nivel is None else nivel
    if not pts:
        return "scale=1080:1920:flags=lanczos"
    soma = "0" + "".join(f"{'+' if i % 2 == 0 else '-'}min(max((t-{t})/{rampa},0),1)" for i, t in enumerate(pts))
    z = f"(1+{nivel}*({soma}))"
    if ancora_y is not None:
        return (f"scale=w='trunc(1080*{z}/2)*2':h='trunc(1920*{z}/2)*2':eval=frame:flags=lanczos,"
                f"crop=1080:1920:'540*({z}-1)':'{ancora_y}*1920*({z}-1)'")
    return f"scale=w='trunc(1080*{z}/2)*2':h='trunc(1920*{z}/2)*2':eval=frame:flags=lanczos,crop=1080:1920:(iw-1080)/2:(ih-1920)*0.85"


def renderizar(pasta: Path) -> Path:
    """Queima a camada no vídeo limpo → a saída (1080x1920, h264 + aac)."""
    pasta = Path(pasta)
    c = carregar(pasta)
    video, saida = RAIZ / c["video"], RAIZ / c["saida"]
    png = pasta / "camada.png"
    caixa_png(c).save(png)
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp = saida.with_name(saida.stem + ".renderizando.mp4")
    from _comum import ffprobe
    dur = float(ffprobe(video).get("duracao") or 0)
    # voz nivelada, fade curto sem estalo e 0,3 s de silêncio com o último quadro parado no fim: a conferência (G10)
    # quer os últimos 0,2 s abaixo de -60 dB, e o bruto costuma acabar colado na última palavra
    punch = []
    if c.get("tipo") == "caixinha" and c.get("punch", True) and dur > PUNCH_MIN_S * 2:
        try:
            livres = c.get("punch_livres")   # "Editar vídeo" (30-out-2026): as cenas sem zoom ficam de fora; ausente = o vídeo todo
            punch = pontos_punch(video, dur, [(float(a), float(b)) for a, b in livres] if livres is not None else None)
        except Exception:  # noqa: BLE001  (sem punch o vídeo ainda sai, só parado)
            punch = []
    c["punch_s"] = punch   # pra constar no camada.json onde o quadro trocou (conferência e "Editar o texto")
    af = "loudnorm=I=-14:TP=-1.5:LRA=11" + (f",afade=t=out:st={max(dur - 0.08, 0):.3f}:d=0.08" if dur > 0.5 else "") + ",apad=pad_dur=0.3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(png), "-filter_complex",
                    f"[0:v]{filtro_punch(punch)},fps=30,tpad=stop_mode=clone:stop_duration=0.3[b];[b][1:v]overlay=0:0", "-c:v", "h264_videotoolbox",
                    "-b:v", "12M", "-af", af, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(saida)
    c["renderizado_em"] = agora()
    (pasta / "camada.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return saida


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "renderizar":
        print(renderizar(Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
