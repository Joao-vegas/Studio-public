"""Peças comuns dos motores de lista (lista-de-estaticos; o passos-numerados saiu em 15-out-2026): storyboard e conferência."""
import json, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

def _folha(imgs, legendas, saida, colunas=4, larg=270):
    h = int(larg * 16 / 9); f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 16)
    lin = (len(imgs) + colunas - 1) // colunas; fo = Image.new("RGB", (colunas * larg, lin * (h + 26)), (20, 20, 20)); d = ImageDraw.Draw(fo)
    for i, (p, l) in enumerate(zip(imgs, legendas)):
        x, y = (i % colunas) * larg, (i // colunas) * (h + 26)
        fo.paste(Image.open(p).convert("RGB").resize((larg, h)), (x, y + 26)); d.text((x + 6, y + 4), l, font=f, fill=(255, 214, 10))
    fo.save(saida, quality=88)

def storyboard(script, video, cenas, saida_dir, tempos_saida, legendas, maximo=12):
    """Um quadro por beat (até `maximo`, espaçados) chamando o próprio motor com --quadro; grava <saida_dir>/storyboard.jpg."""
    os.makedirs(saida_dir, exist_ok=True)
    idx = list(range(len(tempos_saida))) if len(tempos_saida) <= maximo else [round(i * (len(tempos_saida) - 1) / (maximo - 1)) for i in range(maximo)]
    imgs, leg = [], []
    for k in idx:
        p = os.path.join(saida_dir, f"_sb{k}.png")
        subprocess.run([sys.executable, script, "--video", video, "--cenas", cenas, "--out", p, "--quadro", str(tempos_saida[k])], check=True, capture_output=True)
        imgs.append(p); leg.append(f"{tempos_saida[k]:.1f}s · {legendas[k]}")
    _folha(imgs, leg, os.path.join(saida_dir, "storyboard.jpg"))
    for p in imgs: os.remove(p)
    print("storyboard:", os.path.join(saida_dir, "storyboard.jpg"))

def conferir(mp4, saida_dir, cada=3.0):
    """Folha do vídeo pronto (1 quadro a cada `cada` s) em <saida_dir>/folha.jpg pra comparar com a do exemplo."""
    os.makedirs(saida_dir, exist_ok=True); tmp = os.path.join(saida_dir, "_c%03d.jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", f"fps=1/{cada},scale=270:480", tmp], check=True)
    fs = sorted(p for p in os.listdir(saida_dir) if p.startswith("_c")); imgs = [os.path.join(saida_dir, p) for p in fs]
    _folha(imgs, [f"{i * cada:.0f}s" for i in range(len(imgs))], os.path.join(saida_dir, "folha.jpg"), colunas=6)
    for p in imgs: os.remove(p)
    print("folha:", os.path.join(saida_dir, "folha.jpg"))


# ── legenda de uma palavra por vez (faixa 1080x120 mandada ao ffmpeg pelo pipe; o ffmpeg daqui não tem drawtext) ──
W = 1080

def palavras_legenda(caminho, cortes, T, fim):
    """Lista (texto, ini, fim) no tempo do vídeo cortado. Só saem as palavras dentro de cortes LONGOS (> 1 s: falsa largada);
    palavra que caiu num corte de pausa fica (o tempo do Whisper escorrega) e aparece na emenda. Nunca sobrepõe a próxima."""
    d = json.load(open(caminho)); w = [x for x in (d["words"] if isinstance(d, dict) else d) if x.get("word")]
    longos = [(ci, cf) for ci, cf in cortes if cf - ci > 1.0]
    fora = [x["word"] for x in w if any(ci - 0.02 <= x["start"] < cf for ci, cf in longos)]
    w = [x for x in w if not any(ci - 0.02 <= x["start"] < cf for ci, cf in longos)]; ini = []
    for x in w:
        t = re.sub(r"[.,;:!?…\"“”()]", "", x["word"]).lower().strip()
        if t: ini.append((t, T(x["start"]), T(x["end"])))
    out = []
    for k, (t, i0, f0) in enumerate(ini):
        f1 = max(f0, i0 + 0.2)
        if k + 1 < len(ini): f1 = min(f1, max(ini[k + 1][1], i0 + 0.04))
        if i0 < fim: out.append((t, i0, min(f1, fim)))
    print("legenda: %d palavras; fora (falsa largada): %s" % (len(out), " ".join(fora) or "nenhuma"))
    return out

def faixa_legenda(palavras, fim, cx_px, fps=30):
    """Gera os quadros RGBA da faixa 1080x120 (uma palavra por vez) pro ffmpeg ler pelo pipe."""
    f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 54); vazio = bytes(W * 120 * 4); cache = {}
    def quadro(t):
        if t not in cache:
            im = Image.new("RGBA", (W, 120), (0, 0, 0, 0)); d = ImageDraw.Draw(im); w = d.textlength(t, font=f)
            d.text((min(max(cx_px - w / 2, 20), W - w - 20), 22), t, font=f, fill=(255, 214, 10, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255)); cache[t] = im.tobytes()
        return cache[t]
    k = 0
    for q in range(int((fim + 0.5) * fps)):
        t = q / fps
        while k < len(palavras) and palavras[k][2] <= t: k += 1
        yield quadro(palavras[k][0]) if k < len(palavras) and palavras[k][1] <= t < palavras[k][2] else vazio
