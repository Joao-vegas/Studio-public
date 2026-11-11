#!/usr/bin/env python3
"""
MODELO: Faixa com cenas (Vegas). Só a câmera: o João fala e o vídeo alterna 3 jeitos de tela, com a frase em
faixas branca e vermelha na emenda (y=960).

  S = dividido: cena em cima (960 px), João embaixo seguindo o rosto, sombrinha na emenda
  C = cena em tela cheia
  (fora das janelas) = João em tela cheia

Dois estilos (PLANO.json → "estilo"):
  frase-fixa      a frase nas faixas o vídeo INTEIRO, sem legenda (ex.: 12 anos / medo de se expor)
  gancho-legenda  a frase só até "faixa_ate" (~9 s, fim da 1ª ideia); depois legenda de 2-3 palavras:
                  na emenda no S e no C, no peito (y=1420) com o João em tela cheia (ex.: anúncio repetido)

Frase fora do rosto (30-out-2026): com o João em tela cheia a frase (e a legenda do peito) nunca cobre o rosto. A posição de sempre (peito,
y=1180) fica se já está livre; senão a frase vai pra cima da cabeça (se couber abaixo do topo do Instagram) ou pro peito colada
abaixo do queixo. UMA posição por trecho de tela cheia (pior quadro do trecho, rosto do OpenCV a cada 0,25 s), a troca acompanha o
corte de layout. No dividido (S) e na cena cheia (C) segue na emenda. Grava work/gerado/texto-posicao.json (frase e legenda por trecho) (o conferir_video.py lê)
e work/gerado/rostos.json (cache). Código em app/ferramentas/texto_fora_do_rosto.py.

Punch-in: nas pausas da fala onde o João está em tela cheia (sem cena por cima) o quadro aproxima 12% num pulo de 0,04 s (punch-in seco: a medida de dinamismo só enxerga como troca o que muda
rápido; o suave de 0,28 s não passava) e volta, 3 a 6 s uma da outra
(camada.pontos_punch); grava work/gerado/punch.json. "punch": false no PLANO.json desliga.

Sandbox: <modelo>/_sandbox-<slug>/work/joao.mp4 (câmera já cortada) + PLANO.json:
  {"estilo": "gancho-legenda", "frase": "LINHA 1|LINHA 2|LINHA 3", "faixa_ate": 9.0,
   "janelas": [[0, 3, "S", "<clipe.mp4>", 2], [9, 12.3, "C", "<clipe.mp4>", 0.5], ...],   # início fim modo clipe início-no-clipe
   "trocas": {"manda": "queima"},
   "palavras_extra": [{"word": "semana,", "start": 51.0, "end": 51.6}]}  # opcional: palavra que a transcrição comeu   # opcional (gancho-legenda): palavra que a transcrição errou → a certa
Uso (de dentro da sandbox):  python3 ../gerar.py --dir . [--previa] [--saida <mp4>]
Saída padrão: vegasContent/output/faixa-com-cenas/<slug>.mp4 (render num arquivo -novo e troca no fim: o player não
pega arquivo pela metade).
"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

SELF = Path(__file__).resolve().parent
RAIZ = SELF.parents[4]
W, H, EMENDA = 1080, 1920, 960


def sh(*a, **k):
    return subprocess.run(a, check=True, **k)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "default=nk=1:nw=1", str(p)]))


def sombra(out, forca=0.8, alcance=220):
    from PIL import Image
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); px = im.load()
    for y in range(EMENDA - alcance, EMENDA + alcance):
        a = int(255 * forca * (1 - abs(y - EMENDA) / alcance) ** 1.3)
        for x in range(W):
            px[x, y] = (0, 0, 0, a)
    im.save(out)


def legenda(words, desde, trocas, pasta, legy, out, extra=()):
    """Legenda de 3 palavras (build-legenda.py) num .mov transparente, nos tempos absolutos da fala."""
    from PIL import Image
    ws = []
    base = json.load(open(words))["words"]   # ordem da transcrição (o start às vezes vem trocado; nunca ordenar)
    for e in extra:                           # palavra extra entra depois da última que começa antes dela
        i = max([n for n, w in enumerate(base) if w["start"] <= e["start"]], default=-1)
        base.insert(i + 1, e)
    for x in base:
        if x["start"] < desde - 0.05:
            continue
        chave = x["word"].strip().lower().strip(".,!?;:")
        if chave in trocas:
            x = {**x, "word": x["word"].lower().replace(chave, trocas[chave])}
        ws.append(x)
    pasta.mkdir(parents=True, exist_ok=True)
    wj = pasta / "words.json"; json.dump({"words": ws}, open(wj, "w"), ensure_ascii=False)
    sh(sys.executable, str(SELF / "build-legenda.py"), "--words", str(wj), "--t0", "0", "--out-dir", str(pasta),
       "--legy", str(legy), "--fontsize", "60", "--maxwords", "3", stdout=subprocess.DEVNULL)
    vazio = pasta / "vazio.png"; Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(vazio)
    t, linhas = 0.0, []
    for l in open(pasta / "manifest.txt"):
        p, s, e = l.strip().split("|"); s, e = float(s), float(e)
        if s > t:
            linhas.append((vazio, s - t))
        linhas.append((Path(p), e - max(s, t))); t = e
    linhas.append((vazio, 3))
    with open(pasta / "concat.txt", "w") as f:
        for p, d in linhas:
            f.write(f"file '{Path(p).resolve()}'\nduration {d:.3f}\n")
        f.write(f"file '{vazio.resolve()}'\n")
    sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(pasta / "concat.txt"),
       "-vf", "fps=30,format=argb", "-c:v", "qtrle", str(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--previa", action="store_true")
    ap.add_argument("--saida", default="")
    a = ap.parse_args()
    sb = Path(a.dir).resolve(); work = sb / "work"
    plano = json.load(open(sb / "PLANO.json"))
    estilo = plano.get("estilo", "frase-fixa")
    assert estilo in ("frase-fixa", "gancho-legenda"), "estilo: frase-fixa ou gancho-legenda"
    J = [tuple(j) for j in plano["janelas"]]
    cam = work / "joao.mp4"; D = dur(cam)
    faixa_ate = float(plano.get("faixa_ate", 9.0)) if estilo == "gancho-legenda" else D + 1
    g = work / "gerado"; g.mkdir(parents=True, exist_ok=True)

    # faixa na emenda (com sombrinha) e sombrinha sozinha; a faixa da tela cheia sai depois (acompanha o rosto); recorte do bloco de baixo
    sh(sys.executable, str(SELF / "build-faixa.py"), "--out", str(g / "faixa.png"), "--titulo", plano["frase"],
       stdout=subprocess.DEVNULL)
    sombra(g / "sombra.png")
    venv = RAIZ / "app/.venv/bin/python"
    if plano.get("crop_y_fixo") is not None:   # recorte parado: seguir o rosto fazia o João subir e descer na legenda
        cry = str(int(plano["crop_y_fixo"]))
    else:
        cry = subprocess.check_output([str(venv if venv.exists() else sys.executable), str(SELF / "seguir_rosto.py"),
                                       str(cam), "--joao-h", str(EMENDA)], text=True).strip()
    # punch-in suave nas pausas da fala onde o João fica em tela cheia (30-out-2026: 16 a 19 s sem troca na tese/CTA do teste da Faixa).
    # Só nos trechos sem cena por cima; as faixas, a legenda e a sombrinha ficam fixas (são camadas depois). "punch": false no PLANO desliga.
    punch = []
    sys.path.insert(0, str(RAIZ / "app/ferramentas"))
    import camada
    livres, t0 = [], 0.0   # trechos com o João em tela cheia (fora das janelas)
    for s_, e_, *_r in sorted(J):
        livres.append((t0, s_)); t0 = max(t0, e_)
    livres.append((t0, D))
    if plano.get("punch", True) and D > 7:
        try:
            punch = camada.pontos_punch(cam, D, [(a_, b_) for a_, b_ in livres if b_ - a_ > 0])
        except Exception:  # sem punch o vídeo ainda sai, só parado
            punch = []
    # onde a frase e a legenda ficam com o João em tela cheia: fora do rosto (texto_fora_do_rosto.py), uma posição por trecho
    import texto_fora_do_rosto as tfr
    from PIL import Image
    livres_t = [(a_, b_) for a_, b_ in livres if b_ - a_ > 0.05]
    rj = g / "rostos.json"; sig = [cam.stat().st_size, int(cam.stat().st_mtime), tfr.PASSO]
    rs = None
    if rj.is_file():
        try:
            c = json.load(open(rj)); rs = c["rostos"] if c.get("assinatura") == sig else None
        except Exception:
            rs = None
    if rs is None:
        try:
            rs = tfr.rostos(cam)
        except Exception as e:  # sem rosto achado o vídeo ainda sai, com a posição de sempre
            print("rostos:", e, file=sys.stderr); rs = []
        json.dump({"assinatura": sig, "rostos": rs}, open(rj, "w"))
    rs = tfr.com_zoom(rs, list(zip(punch[0::2], punch[1::2])))   # o rosto como aparece, com o zoom do punch
    medida = g / "faixa-medida.png"
    sh(sys.executable, str(SELF / "build-faixa.py"), "--out", str(medida), "--titulo", plano["frase"], "--sombra", "0", "--y", "960",
       stdout=subprocess.DEVNULL)
    bb = Image.open(medida).getbbox(); alt_faixa = (bb[3] - bb[1]) if bb else 216
    todos_livres = [r for r in rs if any(a_ - 0.05 <= r["t"] <= b_ + 0.05 for a_, b_ in livres_t)]
    pos_frase = []   # (início, fim, png) dos trechos de tela cheia com a frase
    posicoes = []
    for n_, (a_, b_) in enumerate(livres_t):
        if a_ >= faixa_ate:
            continue
        fim_ = min(b_, faixa_ate)
        r_ = [r for r in rs if a_ - 0.05 <= r["t"] <= fim_ + 0.05] or todos_livres
        d_ = tfr.decidir(r_, alt_faixa)
        png = g / f"faixa-livre-{n_}.png"
        sh(sys.executable, str(SELF / "build-faixa.py"), "--out", str(png), "--titulo", plano["frase"], "--sombra", "0", "--y", str(d_["y"]),
           stdout=subprocess.DEVNULL)
        pos_frase.append((a_, b_, png))
        posicoes.append({"t0": round(a_, 2), "t1": round(fim_, 2), "onde": d_["onde"], "y": d_["y"],
                         "y0": d_["y"] - alt_faixa // 2, "y1": d_["y"] - alt_faixa // 2 + alt_faixa, "cabe": d_["cabe"]})
        if not d_["cabe"]:
            print(f"AVISO: a frase não cabe fora do rosto em {a_:.1f}-{fim_:.1f} s (queixo em {d_.get('queixo')})", file=sys.stderr)
    legs = []   # legenda do peito: (início, fim, y do topo) por trecho de tela cheia, 1420 ou mais embaixo se o queixo pedir
    if estilo == "gancho-legenda":
        for a_, b_ in livres_t:
            if b_ <= faixa_ate:
                continue
            r_ = [r for r in rs if max(a_, faixa_ate) - 0.05 <= r["t"] <= b_ + 0.05] or todos_livres
            y_ = tfr.y_legenda(r_)
            legs.append((a_, b_, -(-y_ // 10) * 10))   # de 10 em 10 px: poucos arquivos de legenda
    json.dump({"frase": posicoes, "alt_faixa": alt_faixa, "legenda": [{"t0": round(a_, 2), "t1": round(b_, 2), "y0": y_, "y1": y_ + 70}
                                                                       for a_, b_, y_ in legs]}, open(g / "texto-posicao.json", "w"), indent=1)
    json.dump({"punch_s": punch}, open(g / "punch.json", "w"))
    if estilo == "gancho-legenda":
        words = work / "cortado/words.json"
        if not words.exists():
            sh(str(venv if venv.exists() else sys.executable), str(RAIZ / "app/ferramentas/corte.py"), "transcrever",
               str(cam), str(work / "cortado"), "--cliente", "Joao", stdout=subprocess.DEVNULL)
        tr = plano.get("trocas", {})
        ex = plano.get("palavras_extra", [])
        legenda(words, faixa_ate, tr, g / "leg", 925, g / "legenda.mov", ex)
        peitos = {}   # y → trechos; um .mov por y
        for a_, b_, y_ in legs:
            peitos.setdefault(y_, []).append((a_, b_))
        for y_ in peitos:
            legenda(words, faixa_ate, tr, g / f"leg-peito-{y_}", y_, g / f"legenda-peito-{y_}.mov", ex)

    S = "+".join(f"between(t,{s},{e})" for s, e, m, *_ in J if m == "S") or "0"
    TODAS = "+".join(f"between(t,{s},{e})" for s, e, *_ in J) or "0"
    ins = ["-i", str(cam)]
    def entra(*arq):
        ins.extend(arq); return sum(1 for x in ins if x == "-i") - 1
    zoom = camada.filtro_punch(punch, rampa=0.04, nivel=0.12, ancora_y=0.5) if punch else f"scale={W}:{H}:flags=lanczos"
    f = ["[0:v]split[c1][c2]", f"[c1]{zoom},setsar=1[full]",
         f"[c2]scale={W}:{H}:flags=lanczos,crop={W}:{EMENDA}:0:'{cry}',setsar=1[bot]",
         f"[full][bot]overlay=0:{EMENDA}:enable='{S}'[v0]"]
    for n, (s, e, m, clip, o) in enumerate(J):
        h = EMENDA if m == "S" else H
        k = entra("-ss", str(o), "-i", str(clip))
        f.append(f"[{k}:v]trim=0:{e - s:.3f},setpts=PTS-STARTPTS+{s}/TB,scale=w='if(gt(a,{W}/{h}),-2,{W})':"
                 f"h='if(gt(a,{W}/{h}),{h},-2)':flags=lanczos,crop={W}:{h},setsar=1[b{n}]")
        f.append(f"[v{n}][b{n}]overlay=0:0:eof_action=pass:enable='between(t,{s},{e})'[v{n + 1}]")
    v = f"v{len(J)}"
    k1 = entra("-loop", "1", "-i", str(g / "faixa.png"))
    k3 = entra("-loop", "1", "-i", str(g / "sombra.png"))
    f.append(f"[{v}][{k1}:v]overlay=0:0:shortest=1:enable='({TODAS})*lt(t,{faixa_ate})'[x1]")
    ant = "x1"
    for i_, (a_, b_, png) in enumerate(pos_frase):   # tela cheia: uma faixa por trecho, na posição que não cobre o rosto
        k2 = entra("-loop", "1", "-i", str(png))
        f.append(f"[{ant}][{k2}:v]overlay=0:0:shortest=1:enable='between(t,{a_:.3f},{b_:.3f})*lt(t,{faixa_ate})'[y{i_}]")
        ant = f"y{i_}"
    f.append(f"[{ant}][{k3}:v]overlay=0:0:shortest=1:enable='({S})*gte(t,{faixa_ate})'[x3]")
    ult = "x3"
    if estilo == "gancho-legenda":
        k4 = entra("-i", str(g / "legenda.mov"))
        f.append(f"[x3][{k4}:v]overlay=0:0:eof_action=pass:enable='{TODAS}'[x4]")
        ult = "x4"
        for i_, (y_, trs) in enumerate(peitos.items()):
            k5 = entra("-i", str(g / f"legenda-peito-{y_}.mov"))
            en = "+".join(f"between(t,{a_:.3f},{b_:.3f})" for a_, b_ in trs)
            f.append(f"[{ult}][{k5}:v]overlay=0:0:eof_action=pass:enable='{en}'[z{i_}]")
            ult = f"z{i_}"
    f.append(f"[{ult}]fps=30,tpad=stop_mode=clone:stop_duration=0.4,format=yuv420p[v]")
    F = ";".join(f)

    if a.previa:
        n = int(D * 30)
        quadros = [int(n * i / 12) + 15 for i in range(12)]
        sel = "+".join(f"eq(n\\,{q})" for q in quadros)
        sh("ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", F + f";[v]select='{sel}',scale=270:-2,tile=6x2",
           "-frames:v", "1", "-t", str(D), str(sb / "storyboard.jpg"))
        print(sb / "storyboard.jpg"); return

    slug = sb.name.removeprefix("_sandbox-")
    out = Path(a.saida) if a.saida else SELF.parents[1] / "output/faixa-com-cenas" / f"{slug}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + "-novo.mp4")
    sh("ffmpeg", "-y", "-v", "error", "-stats", *ins, "-filter_complex", F, "-map", "[v]", "-map", "0:a",
       "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,apad=pad_dur=0.4,afade=t=out:st={D - 0.05:.2f}:d=0.35",
       "-t", str(D + 0.4), "-c:v", "h264_videotoolbox", "-b:v", "12M", "-profile:v", "high", "-c:a", "aac",
       "-b:a", "192k", "-movflags", "+faststart", str(tmp))
    shutil.move(tmp, out)
    (sb / "qa").mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(RAIZ / "app/ferramentas/formatos.py"), "folha-video", str(out),
                    str(sb / "qa/folha.jpg")], stdout=subprocess.DEVNULL)
    print("✓", out)


if __name__ == "__main__":
    main()
