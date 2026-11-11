"""Chamada na tela (Cliente1): gancho que chama atenção logo no t=0 (o Cliente1 já em cor, falando), título neon
laranja, legenda de uma palavra por vez no peito, motion limpo de vez em quando (palavra neon, riscado, etiqueta),
cama musical baixa e a voz nivelada trecho a trecho.

uso: python3 tela.py <config.json>
config: video, words (json do v2.py master), out, titulo [linha1, linha2], gancho (bate|puxa|luz|sinal),
        musica (mp3), musica_lufs, destaques [palavras em laranja], titulo_fim (s, opcional)
        motions (opcional): lista [{tipo, txt, ini, fim, entrada, itens}] que troca os motions automáticos dos gatilhos; é como o
        Editar vídeo por cena fixa o que entra em cada trecho
"""
import json, random, re, subprocess, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
LARANJA = (0xFF, 0x98, 0x00)
NUCLEO = (0xFF, 0xD0, 0x7A)
FONTES = Path.home() / "Library/Fonts"
F_TITULO = str(FONTES / "BebasNeue-Regular.ttf")
F_LEGENDA = str(FONTES / "Poppins-Bold.ttf")
RNNN = "/Users/joaomarcospiki/Projetos/Skill/Estúdio/acervo/audio-modelos/std.rnnn"
SFX = Path("/Users/joaomarcospiki/Projetos/Skill/Estúdio/clientes/Cliente1/cliente1Content/modelos/chamada-na-tela/assets/sfx")
Y_TITULO, Y_LEGENDA, Y_ETIQUETA = 1150, 1150, 1150   # no peito, abaixo do queixo
VOZ_LUFS, MUSICA_LUFS = -16.0, -35.0                 # cada trecho da voz vai pra -16 antes do -14 final

# motion: (padrão no começo de "palavra + 2 seguintes", tipo, texto na tela). Tipos: neon, riscado, etiqueta,
# contador (número subindo), x (X que se desenha atrás do texto), empilha (itens entram um por um na palavra de cada um)
GATILHOS = [
    # remarketing (20/10): quem já viu a página e não comprou
    (r"^desculpa", "neon", "QUAL A DESCULPA?"),
    (r"^tempo\? é dinheiro", "empilha", "TEMPO?|DINHEIRO?:^dinheiro"),
    (r"^dinheiro r\$ 97|^r\$ 97", "contador", "R$ 97"),
    (r"^semana", "etiqueta", "TUDO PRONTO EM 1 SEMANA"),
    (r"^prático", "neon", "PRÁTICO"),
    (r"^fraud", "neon", "BLACK FRAUD"),
    (r"^80 ", "contador", "-80%"),
    (r"^desconto", "riscado", "DESCONTO"),
    (r"^não é assim", "x", "NÃO É ASSIM"),
    (r"^não fica", "x", "NÃO FICA"),
    (r"^não quer dizer", "x", "NÃO É VENDA"),
    (r"^não adianta", "x", "NÃO ADIANTA"),
    (r"^estratégia do produto", "empilha", "PRODUTO|TEMPO:^tempo|TIME:^time"),
    (r"^estratégia", "neon", "ESTRATÉGIA"),
    (r"^depois\?", "neon", "E DEPOIS?"),
    (r"^converter", "neon", "CONVERTER"),
    (r"^preço\.?( |$)", "riscado", "SÓ PREÇO"),
    (r"^dinheiro", "riscado", "DINHEIRO"),
    (r"^varejo", "neon", "TODO ANO"),
    (r"^combinação", "neon", "COMBINAÇÃO"),
    (r"^decisão", "neon", "DECISÃO"),
    (r"^cidade", "neon", "CIDADE"),
    (r"^vendas", "neon", "VENDAS"),
    (r"^bonzinho", "neon", "BONZINHO"),
    (r"^remédio", "neon", "SÓ O REMÉDIO"),
    (r"^vender\.", "neon", "SABE VENDER"),
    (r"^rotatória", "neon", "ROTATÓRIA"),
    (r"^estacionar", "neon", "ESTACIONAR"),
    (r"^placa", "neon", "A PLACA"),
    (r"^oportunidade", "neon", "OPORTUNIDADE"),
    (r"^certo\?", "neon", "PRODUTO CERTO"),
    (r"^atendimento", "neon", "ATENDIMENTO"),
    (r"^farmácias", "neon", "VÁRIAS FARMÁCIAS"),
    (r"^lucrativa", "neon", "MAIS LUCRATIVA"),
    (r"^abril", "empilha", "JANEIRO:^janeiro|FEVEREIRO:^fevereiro|MARÇO:^março|ABRIL:^abril"),
    (r"^janeiro", "empilha", "JANEIRO|FEVEREIRO:^fevereiro|MARÇO:^março|ABRIL:^abril"),
    (r"^2027", "contador", "2027"),
    (r"^pizzas", "etiqueta", "MENOS QUE 2 PIZZAS"),
    (r"^aulão", "etiqueta", "AULÃO AO VIVO · 27/10"),
    (r"^27 ", "etiqueta", "27/10 · 19H · AO VIVO"),
    (r"^sete |^7 ", "etiqueta", "PRONTO EM 7 DIAS"),
    (r"^97|^,97", "contador", "R$ 97"),
    (r"^história", "neon", "DA HISTÓRIA"),
    (r"^esperando", "etiqueta", "PRODUTO1 · 27/10"),
]
DUR = {"neon": 1.5, "riscado": 1.8, "etiqueta": 2.4, "contador": 1.6, "x": 1.7}
ESPACO = 2.4  # mínimo entre dois motions


def suave(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def sai(x):  # ease-out
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def volta(x):  # ease-out com um passinho pra trás (etiqueta)
    x = min(max(x, 0.0), 1.0)
    c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


# ---------- texto ----------
def texto_rgba(linhas, fonte, tam, max_w, cor, brilho):
    """Linhas centradas; brilho=True = neon laranja igual ao do título. Devolve (rgba float, faixas por linha)."""
    while True:
        f = ImageFont.truetype(fonte, tam)
        larg = [f.getlength(l) for l in linhas]
        if max(larg) <= max_w or tam < 36:
            break
        tam -= 4
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 0.92)
    pad = 60
    cw, ch = int(max(larg)) + 2 * pad, lh * len(linhas) + 2 * pad
    mask = Image.new("L", (cw, ch), 0)
    d = ImageDraw.Draw(mask)
    faixas = []
    for i, l in enumerate(linhas):
        x = (cw - larg[i]) / 2
        d.text((x, pad + i * lh), l, font=f, fill=255)
        faixas.append((x, x + larg[i], pad + i * lh, pad + (i + 1) * lh))
    m = np.asarray(mask, np.float32) / 255
    if brilho:
        r = max(6, tam // 5)
        g1 = np.asarray(mask.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255 * 1.6
        g2 = np.asarray(mask.filter(ImageFilter.GaussianBlur(max(3, r // 3))), np.float32) / 255 * 1.4
        borda = np.asarray(mask.filter(ImageFilter.MaxFilter(5)), np.float32) / 255
        a = np.clip(np.maximum.reduce([g1 * 0.75, g2, borda, m]), 0, 1)
        rgb = np.zeros((ch, cw, 3), np.float32)
        rgb[:] = LARANJA
        nuc = np.asarray(mask.filter(ImageFilter.MinFilter(3)), np.float32)[..., None] / 255
        rgb = rgb * (1 - nuc * 0.75) + np.array(NUCLEO, np.float32) * nuc * 0.75
    else:
        sombra = np.asarray(mask.filter(ImageFilter.GaussianBlur(10)), np.float32) / 255 * 0.85
        a = np.clip(np.maximum(m, sombra), 0, 1)
        rgb = np.zeros((ch, cw, 3), np.float32)
        rgb[:] = cor
        rgb = rgb * m[..., None]
    return np.dstack([rgb, a * 255]).astype(np.float32), faixas


def etiqueta_rgba(txt):
    f = ImageFont.truetype(F_LEGENDA, 64)
    tw = f.getlength(txt)
    asc, desc = f.getmetrics()
    pw, ph = int(tw) + 76, asc + desc + 30
    pad = 40
    img = Image.new("RGBA", (pw + 2 * pad, ph + 2 * pad), (0, 0, 0, 0))
    sombra = Image.new("L", img.size, 0)
    ImageDraw.Draw(sombra).rounded_rectangle((pad, pad + 8, pad + pw, pad + ph + 8), ph // 2, fill=150)
    sombra = sombra.filter(ImageFilter.GaussianBlur(14))
    img.putalpha(sombra)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, pad + pw, pad + ph), ph // 2, fill=LARANJA + (255,))
    d.text((pad + 38, pad + 15), txt, font=f, fill=(17, 17, 17, 255))
    a = np.asarray(img, np.float32).copy()
    a[..., :3] *= (a[..., 3:] > 0)
    return a


def cola(frame, rgba, cx, cy, alpha=1.0, escala=1.0, dx=0):
    if alpha <= 0.01:
        return
    if escala != 1.0:
        rgba = cv2.resize(rgba, None, fx=escala, fy=escala, interpolation=cv2.INTER_LINEAR)
    h, w = rgba.shape[:2]
    x0, y0 = int(cx - w / 2 + dx), int(cy - h / 2)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xa >= xb or ya >= yb:
        return
    s = rgba[ya - y0:yb - y0, xa - x0:xb - x0]
    a = s[..., 3:4] / 255 * alpha
    reg = frame[ya:yb, xa:xb].astype(np.float32)
    frame[ya:yb, xa:xb] = (reg * (1 - a) + s[..., :3] * a).clip(0, 255).astype(np.uint8)


def zoom(fr, s, cy=0.34, blur=False):
    """Zoom centrado (cy = altura do rosto, fração da tela). blur: média de 3 escalas = borrão de movimento."""
    def w(sc):
        M = np.float32([[sc, 0, W / 2 * (1 - sc)], [0, sc, H * cy * (1 - sc)]])
        return cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if not blur:
        return w(s)
    return ((w(s * 0.97).astype(np.float32) + w(s) + w(s * 1.03)) / 3).astype(np.uint8)


def glitch(img, forca, rng):
    out = img.copy()
    k = int(16 * forca)
    if k:
        out[..., 0] = np.roll(img[..., 0], k, axis=1)
        out[..., 2] = np.roll(img[..., 2], -k, axis=1)
    for _ in range(int(9 * forca)):
        y = rng.randrange(0, img.shape[0] - 60)
        h = rng.randrange(10, 60)
        out[y:y + h] = np.roll(out[y:y + h], rng.randrange(-60, 60), axis=1)
    return out


def norm(w):
    return w.lower().strip(" .,!?;:\"'") if not w.endswith("?") else w.lower().strip(" .,!;:\"'")


def planejar_motions(ws, ini, dur, rng):
    """Motion onde a fala tem a palavra forte, um por vez, no mínimo ESPACO s entre eles, sem repetir texto."""
    out, livre, usados = [], ini, set()
    lim = lambda x: x.lower().strip(" .,;:!\"'")
    for k, w in enumerate(ws):
        if w["s"] < livre or w["s"] > dur - 1.4:
            continue
        janela = " ".join(lim(x["w"]) for x in ws[k:k + 3])
        for rx, tipo, txt in GATILHOS:
            if not re.search(rx, janela) or txt in usados:
                continue
            m = {"tipo": tipo, "txt": txt, "ini": w["s"], "entrada": rng.choice(["pop", "desliza", "pisca"])}
            if tipo == "empilha":   # cada item entra na própria palavra (procura nos 8 s seguintes)
                itens = []
                for parte in txt.split("|"):
                    rot, _, rxi = parte.partition(":")
                    if not rxi:
                        itens.append((rot, w["s"]))
                        continue
                    achou = next((x["s"] for x in ws[k + 1:] if w["s"] < x["s"] < w["s"] + 8 and re.search(rxi, lim(x["w"]))), None)
                    if achou:
                        itens.append((rot, achou))
                if len(itens) < 2:
                    continue
                m["itens"] = itens
                m["fim"] = min(itens[-1][1] + 1.3, dur - 0.2)
            else:
                m["fim"] = min(w["s"] + DUR[tipo], dur - 0.2)
            out.append(m)
            usados.add(txt)
            livre = m["fim"] + ESPACO * 0.4 if tipo == "empilha" else w["s"] + ESPACO
            break
    return out


def main(cfg):
    words = json.load(open(cfg["words"]))
    dur, ws, pecas = words["dur"], words["words"], words["pecas"]
    t_tit_fim = cfg.get("titulo_fim", min(max(pecas[0]["fim"], 2.2), 3.0))  # texto não fica preso na tela (João, 19/10: no máx. 3 s)
    gancho = cfg.get("gancho", "bate")
    destaques = {d.lower() for d in cfg.get("destaques", [])}
    rng = random.Random(cfg.get("seed", 7))

    tit, faixas = texto_rgba([l.upper() for l in cfg["titulo"]], F_TITULO, 132, 860, LARANJA, True)
    larg_total = sum(f[1] - f[0] for f in faixas)
    motions = planejar_motions(ws, t_tit_fim + 0.8, dur, rng)
    if cfg.get("motions") is not None:   # lista escrita pelo Editar vídeo por cena: troca a automática (o sorteio acima já rodou, então o resto do vídeo não muda)
        motions = [dict(m) for m in cfg["motions"]]
    for m in motions:
        if m["tipo"] == "etiqueta":
            m["img"] = etiqueta_rgba(m["txt"])
        elif m["tipo"] == "empilha":
            m["imgs"] = [texto_rgba([r], F_TITULO, 150, 860, LARANJA, True)[0] for r, _ in m["itens"]]
        elif m["tipo"] != "contador":
            m["img"] = texto_rgba([m["txt"]], F_TITULO, 210, 860, LARANJA, True)[0]
    print("motions:", [(round(m["ini"], 1), m["tipo"], m["txt"]) for m in motions])
    cont_cache = {}

    def contador(txt, k):
        """Número subindo até o valor (0 → 97, 2000 → 2027, 0 → 80)."""
        num = int(re.sub(r"\D", "", txt))
        base = 2000 if num > 1000 else 0
        v = int(base + (num - base) * sai(k))
        rot = re.sub(r"\d+", str(v), txt, count=1)
        if rot not in cont_cache:
            cont_cache[rot] = texto_rgba([rot], F_TITULO, 230, 860, LARANJA, True)[0]
        return cont_cache[rot]

    # legenda: estilo 1 = uma palavra; estilo 2 = bloco de até 3 palavras com a falada em neon (varia por vídeo)
    estilo_leg = cfg.get("legenda", 1)
    blocos = []
    if estilo_leg == 2:
        atual = []
        for w in ws:
            if w["s"] < t_tit_fim + 0.1:
                continue
            atual.append(w)
            if len(atual) == 3 or re.search(r"[.?!,]$", w["w"]):
                blocos.append(atual); atual = []
        if atual:
            blocos.append(atual)
    bloco_cache = {}

    def bloco_img(bi, ativa):
        if (bi, ativa) not in bloco_cache:
            pal = [x["w"].upper().strip(" .,;:\"'") for x in blocos[bi]]
            imgs = [texto_rgba([p_], F_LEGENDA, 62, 860, (255, 255, 255), False)[0] if i != ativa
                    else texto_rgba([p_], F_LEGENDA, 66, 860, LARANJA, True)[0] for i, p_ in enumerate(pal)]
            gap = -96   # as imagens têm 60 px de respiro de cada lado
            wt = sum(im.shape[1] for im in imgs) + gap * (len(imgs) - 1)
            ht = max(im.shape[0] for im in imgs)
            can = np.zeros((ht, wt, 4), np.float32)
            x = 0
            for im in imgs:
                y = (ht - im.shape[0]) // 2
                reg = can[y:y + im.shape[0], x:x + im.shape[1]]
                a_ = im[..., 3:] / 255
                reg[..., :3] = reg[..., :3] * (1 - a_) + im[..., :3] * a_
                reg[..., 3:] = np.maximum(reg[..., 3:], im[..., 3:])
                x += im.shape[1] + gap
            if wt > 980:
                can = cv2.resize(can, None, fx=980 / wt, fy=980 / wt)
            bloco_cache[(bi, ativa)] = can
        return bloco_cache[(bi, ativa)]
    emendas = [p["ini"] for p in pecas[1:]]
    sons = [(max(0, b_ - 0.22), "whoosh-short.mp3", 0.30) for b_ in emendas]
    for m in motions:
        if m["tipo"] == "empilha":
            sons += [(ts, "click-soft.mp3", 0.45) for _, ts in m["itens"]]
        else:
            sons.append((m["ini"], "pop.mp3", 0.28))
    if gancho in ("bate", "sinal"):
        sons.append((0.12 if gancho == "bate" else 0.35, "pop.mp3", 0.4))
    cfg["_sons"] = sons

    leg_cache = {}

    def legenda(w):
        k = w.lower().strip(" .,!?;:\"'")
        if k not in leg_cache:
            txt = w.upper().strip(" .,;:\"'")
            if k in destaques or re.fullmatch(r"[\d%,$]+", k):
                leg_cache[k] = texto_rgba([txt], F_LEGENDA, 66, 860, LARANJA, True)[0]
            else:
                leg_cache[k] = texto_rgba([txt], F_LEGENDA, 64, 860, (255, 255, 255), False)[0]
        return leg_cache[k]

    janelas = []
    for i, w in enumerate(ws):
        if w["s"] < t_tit_fim + 0.1:
            continue
        fim = ws[i + 1]["s"] if i + 1 < len(ws) else w["e"] + 0.3
        janelas.append((w["s"], min(fim, w["e"] + 0.7), w["w"]))

    def mascara_titulo(rev):
        m = np.zeros(tit.shape[:2], np.float32)
        for i, (x0, x1, y0, y1) in enumerate(faixas):
            lw = x1 - x0
            cut = min(max(rev, 0), lw)
            rev -= lw
            if cut > 0:  # cada linha só mexe na faixa dela
                ya = 0 if i == 0 else int(y0)
                yb = m.shape[0] if i == len(faixas) - 1 else int(y1)
                xx = np.arange(m.shape[1], dtype=np.float32)
                m[ya:yb] = np.maximum(m[ya:yb], np.clip((x0 + cut - xx) / 30 + 0.5, 0, 1)[None, :])
        return m

    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", cfg["video"], "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-"], stdout=subprocess.PIPE)
    tmp = cfg["out"] + ".video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "17", "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-colorspace", "bt709", tmp], stdin=subprocess.PIPE)
    n = 0
    while True:
        raw = dec.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            break
        t = n / FPS
        fr = np.frombuffer(raw, np.uint8).reshape(H, W, 3).copy()
        tit_alpha, tit_escala, tit_rev, tit_dx = 1.0, 1.0, larg_total, 0
        tremor = (0, 0)

        # ---- gancho: o Cliente1 em cor desde o t=0, com um golpe de atenção ----
        if gancho == "bate":        # título bate na tela, tremor e clarão curto
            if t < 0.6:
                fr = zoom(fr, 1.12 - 0.12 * sai(t / 0.6))
            ti = 0.12
            if t < ti:
                tit_alpha = 0
            elif t < ti + 0.16:
                k = sai((t - ti) / 0.16)
                tit_escala, tit_alpha = 1.7 - 0.7 * k, k
            if ti + 0.16 <= t < ti + 0.45:
                a = 1 - (t - ti - 0.16) / 0.29
                tremor = (int(rng.uniform(-14, 14) * a), int(rng.uniform(-10, 10) * a))
            if ti + 0.16 <= t < ti + 0.22:
                fr = (fr.astype(np.float32) * 0.75 + 255 * 0.25).astype(np.uint8)
        elif gancho == "puxa":      # abre num close do rosto e puxa a câmera pra trás
            if t < 0.8:
                fr = zoom(fr, 1.5 - 0.5 * sai(t / 0.8), cy=0.30, blur=t < 0.45)
            tit_rev = suave((t - 0.25) / 1.0) * larg_total
        elif gancho == "luz":       # feixe de luz laranja atravessa e revela o título
            fr = zoom(fr, 1.0 + 0.05 * suave(t / max(t_tit_fim, 1)))
            if t < 0.9:
                x = -300 + (W + 600) * sai(t / 0.9)
                xx = np.arange(W, dtype=np.float32)[None, :]
                yy = np.arange(H, dtype=np.float32)[:, None]
                d = np.abs((xx - x) + (yy - H / 2) * 0.35)
                faixa = np.exp(-(d / 130) ** 2)[..., None]
                luz = np.array([255, 190, 90], np.float32)
                fr = (fr.astype(np.float32) * (1 - 0.55 * faixa) + luz * 0.55 * faixa).clip(0, 255).astype(np.uint8)
                # o título aparece onde o feixe já passou (em coordenadas do título)
                tit_rev = max(0.0, (x - (W / 2 - tit.shape[1] / 2)) / tit.shape[1]) * larg_total * 1.15
        elif gancho == "brilho":    # abre estourado num brilho laranja que assenta e revela o Cliente1 e o título
            if t < 0.9:
                k = sai(t / 0.9)
                f32 = fr.astype(np.float32)
                bloom = cv2.GaussianBlur(cv2.resize(f32, (W // 6, H // 6)), (0, 0), 8)
                bloom = cv2.resize(bloom, (W, H))
                xx = np.arange(W, dtype=np.float32)[None, :]
                yy = np.arange(H, dtype=np.float32)[:, None]
                fx, fy = W * (0.15 + 0.7 * k), H * 0.30
                flare = np.exp(-(((xx - fx) / 260) ** 2 + ((yy - fy) / 260) ** 2))[..., None]
                f32 = f32 * (1.0 + 0.9 * (1 - k)) + bloom * 0.8 * (1 - k) + np.array([255, 170, 60], np.float32) * flare * (1.2 - k)
                fr = f32.clip(0, 255).astype(np.uint8)
            tit_rev = suave((t - 0.35) / 0.8) * larg_total
        elif gancho == "sinal":     # falha de sinal nos primeiros instantes, título entra piscando
            if t < 0.4:
                fr = glitch(fr, 1.0 - t / 0.5, rng)
            if t < 0.35:
                tit_alpha = 0
            elif t < 0.75:
                tit_alpha = 1.0 if n % 3 else 0.35
                tit_dx = rng.randrange(-16, 16)

        # ---- um motion por vez (e um empurrãozinho de câmera junto do neon) ----
        motion = next((m for m in motions if m["ini"] <= t < m["fim"]), None)
        if t >= 0.9:
            # câmera viva: cada trecho vai aproximando ou afastando devagar (alterna de um trecho pro outro)
            pi = max(i for i, p in enumerate(pecas) if p["ini"] <= t + 1e-6) if t >= pecas[0]["ini"] else 0
            p = pecas[pi]
            prog = suave((t - p["ini"]) / max(p["fim"] - p["ini"], 0.5))
            esc = 1.0 + 0.05 * (prog if pi % 2 == 0 else 1 - prog)
            if motion and motion["tipo"] in ("neon", "contador", "x", "riscado"):   # empurrão junto do motion
                k = (t - motion["ini"]) / (motion["fim"] - motion["ini"])
                esc *= 1.0 + 0.06 * suave(min(k * 4, 1)) * (1 - suave((k - 0.85) / 0.15))
            borra = False
            for b_ in emendas:   # emenda: zoom rápido com borrão e clarão (esconde o corte)
                d_ = abs(t - b_)
                if d_ < 0.15:
                    esc *= 1.0 + 0.13 * (1 - d_ / 0.15)
                    borra = True
                    if d_ < 0.034:
                        fr = (fr.astype(np.float32) * 0.8 + 255 * 0.2).astype(np.uint8)
            for b_, dd in cfg.get("borrao", []):   # câmera girando no bruto: vira chicote borrado em vez de congelar (João, 20/10)
                if b_ <= t < b_ + dd:
                    esc *= 1.0 + 0.12 * (1 - suave((t - b_) / dd))
                    borra = True
            if esc > 1.001:
                fr = zoom(fr, esc, blur=borra)

        # ---- título neon ----
        if t < t_tit_fim + 0.3:
            t_r = tit.copy()
            t_r[..., 3] *= mascara_titulo(tit_rev)
            if t >= t_tit_fim:      # sai com falha de sinal
                k = (t - t_tit_fim) / 0.3
                tit_alpha = (1 - k) * (0.3 if n % 2 else 1.0)
                tit_dx = rng.randrange(-18, 18)
            cola(fr, t_r, W / 2, Y_TITULO, tit_alpha, escala=tit_escala, dx=tit_dx)

        # ---- motion ----
        neon_na_tela = bool(motion)   # etiqueta e neon ocupam o lugar da legenda enquanto estão na tela
        if motion:
            k0, k1 = t - motion["ini"], motion["fim"] - t
            img = motion.get("img")
            if motion["tipo"] == "etiqueta":
                e = volta(k0 / 0.35)
                a = min(1.0, k0 / 0.15) * min(1.0, k1 / 0.2)
                cola(fr, img, W / 2, Y_ETIQUETA + 70 * (1 - e), a)
            elif motion["tipo"] == "empilha":   # itens entram um por um, de cima pra baixo, centrados no peito
                vis = [i for i, (_, ts) in enumerate(motion["itens"]) if ts <= t]
                n_it = len(motion["itens"])
                passo = 128
                y0 = Y_TITULO - passo * (n_it - 1) / 2
                a = min(1.0, k1 / 0.2)
                for i in vis:
                    ki = t - motion["itens"][i][1]
                    e = sai(ki / 0.2)
                    cola(fr, motion["imgs"][i], W / 2 - 120 * (1 - e), y0 + i * passo, a * e, escala=1.0)
            else:
                ent = motion["entrada"]
                dx, esc = 0, 1.0
                a = min(1.0, k0 / 0.12) * min(1.0, k1 / 0.15)
                if ent == "pop":
                    esc = 1.35 - 0.35 * sai(k0 / 0.18) if k0 < 0.18 else 1.0
                elif ent == "desliza":
                    dx = -W * 0.6 * (1 - sai(k0 / 0.22))
                elif ent == "pisca" and k0 < 0.3:
                    a *= 1.0 if (int(k0 * FPS) % 3) else 0.25
                if k1 < 0.15:
                    esc *= 1.0 + 0.08 * (1 - k1 / 0.15)
                if motion["tipo"] == "contador":
                    img = contador(motion["txt"], k0 / 0.6)
                if motion["tipo"] == "x" and k0 > 0.05:   # X laranja que se desenha atrás do texto
                    ov = fr.copy()
                    r_ = 230
                    p1 = sai((k0 - 0.05) / 0.18)
                    p2 = sai((k0 - 0.2) / 0.18)
                    cx_, cy_ = W // 2, Y_TITULO
                    for (pa, (xa, ya, xb, yb)) in ((p1, (-r_, -r_, r_, r_)), (p2, (r_, -r_, -r_, r_))):
                        if pa > 0:
                            xe, ye = int(cx_ + xa + (xb - xa) * pa), int(cy_ + ya + (yb - ya) * pa)
                            cv2.line(ov, (cx_ + xa, cy_ + ya), (xe, ye), LARANJA, 34, cv2.LINE_AA)
                            cv2.line(ov, (cx_ + xa, cy_ + ya), (xe, ye), (255, 225, 170), 12, cv2.LINE_AA)
                    fr = cv2.addWeighted(ov, 0.55 * a, fr, 1 - 0.55 * a, 0)
                cola(fr, img, W / 2, Y_TITULO, a, escala=esc, dx=dx)
                if motion["tipo"] == "riscado" and k0 > 0.35:   # risco atravessa a palavra
                    p = sai((k0 - 0.35) / 0.25)
                    ih, iw = img.shape[:2]
                    lw = int((iw - 120) * p)
                    if lw > 4:
                        ov = fr.copy()
                        x0 = int(W / 2 - (iw - 120) / 2)
                        cv2.line(ov, (x0, Y_TITULO + 6), (x0 + lw, Y_TITULO - 6), (255, 235, 200), 16, cv2.LINE_AA)
                        cv2.line(ov, (x0, Y_TITULO + 6), (x0 + lw, Y_TITULO - 6), LARANJA, 26, cv2.LINE_AA)
                        cv2.line(ov, (x0, Y_TITULO + 6), (x0 + lw, Y_TITULO - 6), (255, 235, 200), 10, cv2.LINE_AA)
                        fr = cv2.addWeighted(ov, a, fr, 1 - a, 0)

        # ---- legenda palavra a palavra (some quando a palavra neon está na tela: a fala escrita uma vez só) ----
        if not neon_na_tela and estilo_leg == 2:
            for bi, bl in enumerate(blocos):
                fim_b = blocos[bi + 1][0]["s"] if bi + 1 < len(blocos) else bl[-1]["e"] + 0.4
                if bl[0]["s"] <= t < min(fim_b, bl[-1]["e"] + 0.7):
                    ativa = max(i for i, x in enumerate(bl) if x["s"] <= t)
                    cola(fr, bloco_img(bi, ativa), W / 2, Y_LEGENDA, 1.0,
                         escala=0.9 + 0.1 * suave((t - bl[0]["s"]) / 0.08))
                    break
        elif not neon_na_tela:
            for (a0, a1, w) in janelas:
                if a0 <= t < a1:
                    cola(fr, legenda(w), W / 2, Y_LEGENDA, 1.0, escala=0.86 + 0.14 * suave((t - a0) / 0.08))
                    break

        if tremor != (0, 0):
            fr = np.roll(fr, tremor, axis=(1, 0))
        enc.stdin.write(fr.tobytes())
        n += 1
    enc.stdin.close(); enc.wait(); dec.wait()
    audio(cfg, tmp, pecas, dur)
    Path(tmp).unlink()
    print("ok", cfg["out"], f"{n} quadros")


def medir(arq, ini=None, fim=None):
    cmd = ["ffmpeg", "-hide_banner"]
    if ini is not None:
        cmd += ["-ss", f"{ini:.3f}", "-to", f"{fim:.3f}"]
    r = subprocess.run(cmd + ["-i", arq, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return json.loads(r[r.rindex("{"):r.rindex("}") + 1])


def audio(cfg, video_mudo, pecas, dur):
    """Voz: limpa (arnndn sozinho e em mono: em estéreo ele solta NaN no ffmpeg 9), cada trecho (gancho, corpo,
    CTA, que vêm de gravações diferentes) nivelado em -16 LUFS e o todo em -14. Música por baixo, com ducking."""
    wav = cfg["out"] + ".voz.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", cfg["video"], "-vn", "-af",
                    f"aresample=48000,pan=mono|c0=0.5*c0+0.5*c1,arnndn=m={RNNN}:mix=1.0,highpass=f=80,lowpass=f=15000",
                    "-c:a", "pcm_s24le", wav], check=True)
    ganhos = []
    for p in pecas:
        i = float(medir(wav, p["ini"], p["fim"])["input_i"])
        ganhos.append((p["ini"], p["fim"], max(-12.0, min(12.0, VOZ_LUFS - i)) if i > -70 else 0.0))
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})*{10 ** (g / 20):.4f}" for a, b, g in ganhos)
    print("voz por trecho (dB):", [round(g, 1) for *_, g in ganhos])
    wav2 = cfg["out"] + ".voz2.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-af", f"volume='{expr}':eval=frame",
                    "-c:a", "pcm_s24le", wav2], check=True)
    med = medir(wav2)
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={med['input_i']}:measured_TP={med['input_tp']}"
          f":measured_LRA={med['input_lra']}:measured_thresh={med['input_thresh']}:offset={med['target_offset']}:linear=true")
    ent = ["-i", video_mudo, "-i", wav2]
    sons = cfg.get("_sons", [])
    for t0, arq, g in sons:
        ent += ["-i", str(SFX / arq)]
    base = 3 if cfg.get("musica") else 2
    sfx_fc = "".join(f"[{base + i}:a]aformat=channel_layouts=stereo,volume={g},adelay={int(t0 * 1000)}|{int(t0 * 1000)}[s{i}];"
                     for i, (t0, arq, g) in enumerate(sons))
    sfx_mix = "".join(f"[s{i}]" for i in range(len(sons)))
    if cfg.get("musica"):
        g = MUSICA_LUFS - float(cfg.get("musica_lufs", -14))
        ent = ent[:4] + ["-stream_loop", "-1", "-i", cfg["musica"]] + ent[4:]
        fc = (f"[1:a]{ln},asplit=2[voz][sc];"
              f"[2:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo,volume={g:.1f}dB,"
              f"afade=t=in:d=0.4,afade=t=out:st={max(0, dur - 1.2):.3f}:d=1.2[m];"
              f"[m][sc]sidechaincompress=threshold=0.15:ratio=2.5:attack=20:release=300[md];"
              f"{sfx_fc}[voz]aformat=channel_layouts=stereo[v2];[v2][md]{sfx_mix}amix=inputs={2 + len(sons)}:duration=first:normalize=0,"
              f"alimiter=limit=0.89[a]")
    else:
        fc = f"[1:a]{ln},aformat=channel_layouts=stereo[a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ent, "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
                    "-t", f"{dur:.3f}", cfg["out"]], check=True)
    Path(wav).unlink(); Path(wav2).unlink()


if __name__ == "__main__":
    main(json.load(open(sys.argv[1])))
