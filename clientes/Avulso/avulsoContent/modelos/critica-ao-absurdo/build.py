#!/usr/bin/env python3
"""Crítica ao absurdo — Vegas. Monta o vídeo a partir da sandbox (chamado pelo gerar.sh).

Tela 1080x1920: o trecho do vídeo absurdo em cima (1080x1046) com legenda de 1 a 3 palavras (caixa roxa, texto branco,
palavra forte em amarelo, centro y=960) e a FOTO fixa embaixo (1080x874), parada do 1º ao último quadro do trecho.
Depois, se existir work/joao.mp4, a resposta do João em tela cheia.

Medidas tiradas da referência (reel DdXnhWBPmza do @soujoaovegas): divisão em y=1046.
"""
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SELF = Path(__file__).resolve().parent
RAIZ = SELF.parents[4]
CLIENTE = SELF.parents[2].name   # clientes/<Cliente>/<x>Content/modelos/<modelo>: o vocabulário é do cliente da pasta
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))

W, H, CORTE = 1080, 1920, 1046
LEG_Y = 960                       # centro da legenda (logo acima da divisão)
ROXO, BRANCO, AMARELO = (109, 40, 217), (255, 255, 255), (255, 229, 0)
FONTE = Path.home() / "Library/Fonts/Roboto-Black.ttf"
CURTAS = set("a o e é de da do das dos que em no na nos nas um uma pra pro por com se me te lhe eu tu ele ela "
             "eles elas a gente isso esse essa este esta ao aos às mas não ou já tá to tô".split())


FRACAS_FIM = re.compile(r"^(a|o|as|os|e|é|de|do|da|dos|das|seu|sua|seus|suas|ou|que|um|uma|em|no|na|pra|pro|por|com|se|me|te)$")


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("✗ " + " ".join(map(str, cmd[:6])) + "...\n" + r.stderr[-1500:])
    return r.stdout


def dur(p):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(p)]))


def tempo(s):
    """'1:23.5' ou '83.5' -> segundos."""
    if s in (None, ""):
        return None
    seg = 0.0
    for parte in str(s).split(":"):
        seg = seg * 60 + float(parte.replace(",", "."))
    return seg


def cobrir(w, h, fx=0.5, fy=0.5):
    """Filtro ffmpeg que preenche w x h cortando o que sobra, com o foco em (fx, fy)."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h}:(iw-{w})*{fx}:(ih-{h})*{fy},setsar=1")


def foto_png(foto, destino, fy):
    im = Image.open(foto).convert("RGB")
    esc = max(W / im.width, (H - CORTE) / im.height)
    im = im.resize((round(im.width * esc), round(im.height * esc)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = round((im.height - (H - CORTE)) * fy)
    im.crop((x, y, x + W, y + H - CORTE)).save(destino)


def grupos(palavras, maxp=3, maxc=18, pausa=0.35):
    """Junta palavras em blocos de 1 a 3 (quebra na pausa ou na pontuação)."""
    out, cur = [], []
    for w in palavras:
        p = w["p"].strip()
        if cur and (len(cur) >= maxp or len(" ".join(c["p"] for c in cur + [w])) > maxc
                    or w["t0"] - cur[-1]["t1"] > pausa or re.search(r"[.!?,;:]$", cur[-1]["p"])):
            out.append(cur); cur = []
        cur.append({**w, "p": p})
    if cur:
        out.append(cur)
    # grupo não fecha em artigo/preposição/pronome curto ("DO SEU", "O POTENCIAL DE"): a palavra fraca vai pro começo do próximo
    for i in range(len(out) - 1):
        while len(out[i]) > 1 and len(out[i + 1]) < maxp and FRACAS_FIM.match(re.sub(r"[^\wÀ-ÿ]", "", out[i][-1]["p"]).lower()) \
                and not re.search(r"[.!?,;:]$", out[i][-1]["p"]):
            out[i + 1].insert(0, out[i].pop())
    blocos = []
    for i, g in enumerate(out):
        fim = out[i + 1][0]["t0"] if i + 1 < len(out) else g[-1]["t1"] + 0.3
        blocos.append({"t0": g[0]["t0"], "t1": min(fim, g[-1]["t1"] + 0.6), "palavras": [x["p"] for x in g]})
    return blocos


def forte(p):
    base = re.sub(r"[^\wÀ-ÿ]", "", p).lower()
    return len(base) >= 6 and base not in CURTAS


def legenda_png(palavras, destino):
    txt = [re.sub(r"[.,;:]+$", "", p).upper() for p in palavras]
    fonte = ImageFont.truetype(str(FONTE), 50)
    esp = fonte.getlength(" ")
    larg = [fonte.getlength(t) for t in txt]
    tw = sum(larg) + esp * (len(txt) - 1)
    pad_x, alt = 20, 74
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0 = (W - tw) / 2
    d.rounded_rectangle((x0 - pad_x, LEG_Y - alt / 2, x0 + tw + pad_x, LEG_Y + alt / 2), radius=10, fill=ROXO)
    x = x0
    for t, l, p in zip(txt, larg, palavras):
        d.text((x, LEG_Y + 2), t, font=fonte, fill=AMARELO if forte(p) else BRANCO, anchor="lm")
        x += l + esp
    im.save(destino)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--video", help="vídeo absurdo (padrão: work/absurdo.mp4)")
    ap.add_argument("--de"); ap.add_argument("--ate")
    ap.add_argument("--foto", help="foto de baixo (padrão: work/foto.* ou assets/foto-padrao.png)")
    ap.add_argument("--foco-x", type=float, default=0.5, help="0 = esquerda, 1 = direita (corte do vídeo de cima)")
    ap.add_argument("--foco-y", type=float, default=0.3, help="0 = topo, 1 = base (corte do vídeo de cima)")
    ap.add_argument("--foto-y", type=float, default=0.35, help="corte vertical da foto")
    ap.add_argument("--sem-legenda", action="store_true")
    ap.add_argument("--sem-resposta", action="store_true", help="ignora work/joao.mp4")
    ap.add_argument("--previa", action="store_true")
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()

    sb = Path(a.dir).resolve(); work = sb / "work"; work.mkdir(exist_ok=True)
    video = Path(a.video) if a.video else work / "absurdo.mp4"
    if not video.exists():
        sys.exit(f"✗ não achei o vídeo absurdo: {video}")
    foto = Path(a.foto) if a.foto else next(iter(sorted(work.glob("foto.*"))), SELF / "assets" / "foto-padrao.png")
    foto_padrao_de_outro = not a.foto and foto == SELF / "assets" / "foto-padrao.png" and CLIENTE != "Joao"
    if not foto.exists():
        sys.exit(f"✗ não achei a foto: {foto}")
    de, ate = tempo(a.de) or 0.0, tempo(a.ate) or dur(video)
    if ate - de > 60:
        print(f"⚠ trecho de {ate - de:.0f} s: o formato pede uns 20 a 30 s")

    # 1. trecho do vídeo absurdo, já no tamanho da metade de cima, voz nivelada
    trecho = work / "trecho.mp4"
    sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{de:.3f}", "-to", f"{ate:.3f}", "-i", str(video),
        "-vf", cobrir(W, CORTE, a.foco_x, a.foco_y) + ",fps=30", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "h264_videotoolbox", "-b:v", "12M", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(trecho)])
    dt = dur(trecho)

    tmp = Path(tempfile.mkdtemp(prefix="critica-"))
    foto_png(foto, tmp / "foto.png", a.foto_y)

    # 2. legenda da fala do trecho (Groq, palavra por palavra)
    blocos = []
    if not a.sem_legenda:
        import corte
        leg = work / "legenda"; leg.mkdir(exist_ok=True)
        corte.transcrever(trecho, leg, cliente=CLIENTE, refazer=True, motor="groq")
        blocos = grupos(corte._palavras(leg))
        json.dump(blocos, open(work / "legenda.json", "w"), ensure_ascii=False, indent=1)

    if a.previa:
        t = dt * 0.4
        b = next((b for b in blocos if b["t0"] <= t < b["t1"]), blocos[len(blocos) // 3] if blocos else None)
        if b:
            t = (b["t0"] + b["t1"]) / 2
        quadro = tmp / "q.png"
        sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(trecho), "-frames:v", "1", str(quadro)])
        tela = Image.new("RGB", (W, H)); tela.paste(Image.open(quadro).convert("RGB"), (0, 0))
        tela.paste(Image.open(tmp / "foto.png"), (0, CORTE))
        if b:
            legenda_png(b["palavras"], tmp / "l.png"); tela.paste(l := Image.open(tmp / "l.png"), (0, 0), l)
        if foto_padrao_de_outro:
            d = ImageDraw.Draw(tela); f = ImageFont.truetype(str(FONTE), 38)
            d.rectangle((0, H - 120, W, H), fill=(0, 0, 0)); d.text((W // 2, H - 60), "Foto padrão (João): mande a sua", font=f, fill=AMARELO, anchor="mm")
            print("AVISO: foto padrão do João; peça a foto do cliente (work/foto.png)")
        tela.save(a.saida, quality=90); print(a.saida); return

    # 3. legenda vira uma faixa de PNGs (concat) por cima da metade de cima
    entradas = ["-i", str(trecho), "-loop", "1", "-t", f"{dt:.3f}", "-i", str(tmp / "foto.png")]
    filtro = f"[0:v]pad={W}:{H}:0:0[b];[b][1:v]overlay=0:{CORTE}:shortest=1[v0]"
    if blocos:
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(tmp / "vazio.png")
        linhas, t = [], 0.0
        for i, b in enumerate(blocos):
            if b["t0"] > t + 0.01:
                linhas += [f"file '{tmp / 'vazio.png'}'", f"duration {b['t0'] - t:.3f}"]
            legenda_png(b["palavras"], tmp / f"l{i:03d}.png")
            linhas += [f"file '{tmp / f'l{i:03d}.png'}'", f"duration {b['t1'] - b['t0']:.3f}"]
            t = b["t1"]
        linhas += [f"file '{tmp / 'vazio.png'}'", f"duration {max(dt - t, 0.1):.3f}", f"file '{tmp / 'vazio.png'}'"]
        (tmp / "leg.txt").write_text("\n".join(linhas))
        entradas += ["-f", "concat", "-safe", "0", "-i", str(tmp / "leg.txt")]
        filtro += ";[2:v]format=rgba,fps=30[lg];[v0][lg]overlay=0:0:shortest=1[v1]"
    else:
        filtro += ";[v0]null[v1]"
    parte1 = tmp / "parte1.mp4"
    sh(["ffmpeg", "-nostdin", "-y", "-v", "error", *entradas, "-filter_complex", filtro + ";[v1]format=yuv420p[v]",
        "-map", "[v]", "-map", "0:a", "-t", f"{dt:.3f}", "-r", "30", "-c:v", "h264_videotoolbox", "-b:v", "12M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(parte1)])

    # 4. a resposta do João em tela cheia (se tiver), emendada depois
    resp = work / "joao.mp4"
    if resp.exists() and not a.sem_resposta:
        sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(parte1), "-i", str(resp), "-filter_complex",
            f"[1:v]{cobrir(W, H)},fps=30,format=yuv420p[r];[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ra];"
            f"[0:v][0:a][r][ra]concat=n=2:v=1:a=1[v][ac];[ac]afade=t=out:st={max(dt + dur(resp) - 0.12, 0):.3f}:d=0.12[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "h264_videotoolbox", "-b:v", "12M", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", a.saida])
    else:
        sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(parte1), "-c:v", "copy", "-af", f"afade=t=out:st={max(dt - 0.12, 0):.3f}:d=0.12",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.saida])
    print(a.saida)


if __name__ == "__main__":
    main()
