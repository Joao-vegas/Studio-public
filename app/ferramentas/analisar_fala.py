#!/usr/bin/env python3
"""Lê o bruto e o words.json e devolve o que a IA precisa pra montar uma lista/passos sem perguntar:
onde a pessoa está (rosto → esquerda|centro|direita), pausas, recomeços (falsas largadas) e pistas de passo/ordinal.
Uso: python3 app/ferramentas/analisar_fala.py <bruto> <words.json> [--saida analise.json]
Sai um JSON com: rosto, silencios, cortes_sugeridos (recomeços + pausas aparadas, no tempo do BRUTO), fim_sugerido, pistas.
A IA confere e decide; nada aqui é definitivo (storyboard fica na decisão dela, com a aprovação do João)."""
import argparse, json, os, re, statistics, subprocess, tempfile, unicodedata
import cv2

ORD = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5, "sexto": 6, "setimo": 7, "oitavo": 8,
       "nono": 9, "decimo": 10, "um": 1, "dois": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10}

def _n(s): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode())

def rosto(video, fim, tmp):
    caixas, dim = [], None
    for k in range(7):
        t = 0.3 + max(fim - 0.6, 0.1) * k / 6; p = os.path.join(tmp, f"r{k}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", "-vf", "scale=720:-2", p], check=True)
        im = cv2.imread(p); dim = im.shape[1], im.shape[0]
        r = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").detectMultiScale(
            cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), 1.1, 5, minSize=(40, 40))
        if len(r): caixas.append(max(r, key=lambda b: b[2] * b[3]))
    if not caixas: return {"achou": False, "lado_pessoa": "desconhecido", "aviso": "rosto não achado: olhe um quadro e decida"}
    m = [statistics.median(c[i] for c in caixas) / (dim[0] if i % 2 == 0 else dim[1]) for i in range(4)]
    cx, cy = m[0] + m[2] / 2, m[1] + m[3] / 2
    return {"achou": True, "cx": round(cx, 3), "cy": round(cy, 3), "largura_rosto": round(m[2], 3), "proporcao_bruto": round(dim[0] / dim[1], 3),
            "lado_pessoa": "esquerda" if cx < 0.4 else "direita" if cx > 0.6 else "centro"}

def silencios(video):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-vn", "-af", "silencedetect=noise=-32dB:d=0.3", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    ini = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", out)]; fim = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", out)]
    return [[a, b] for a, b in zip(ini, fim)]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("words"); ap.add_argument("--saida")
    a = ap.parse_args()
    d = json.load(open(a.words)); w = d["words"] if isinstance(d, dict) else d
    w = [x for x in w if x.get("word")]; fim_fala = w[-1]["end"]
    sil = silencios(a.video); tmp = tempfile.mkdtemp(prefix="analise-")
    cortes = []
    # recomeço: mesmo par de palavras com continuação diferente, colado (até 3 s e 6 palavras) → o trecho anterior é falsa largada
    for i in range(len(w) - 2):
        for j in range(i + 1, len(w) - 2):
            if w[j]["start"] - w[i]["start"] > 3.0 or j - i > 6: break
            if _n(w[i]["word"]) == _n(w[j]["word"]) and _n(w[i + 1]["word"]) == _n(w[j + 1]["word"]) and _n(w[i + 2]["word"]) != _n(w[j + 2]["word"]) \
               and len(_n(w[i]["word"])) + len(_n(w[i + 1]["word"])) >= 5:
                s = [e for _, e in sil if w[j]["start"] - 0.6 <= e <= w[j]["start"] + 0.05]
                ini_j = (s[-1] if s else w[j]["start"] - 0.05)
                if ini_j > w[i]["start"]: cortes.append([round(max(w[i]["start"] - 0.03, 0), 2), round(ini_j, 2)])
                break
    # pausas ≥ 0.3 s aparadas pra 0,12 s (sem tocar no começo, que já pode estar cortado)
    for s0, s1 in sil:
        if s1 - s0 >= 0.3 and s0 > 0.4 and s1 < fim_fala: cortes.append([round(s0 + 0.06, 2), round(s1 - 0.06, 2)])
    cortes.sort(); fund = []
    for c in cortes:
        if fund and c[0] <= fund[-1][1] + 0.05: fund[-1][1] = max(fund[-1][1], c[1])
        else: fund.append(c)
    info = [{"corte": c, "duracao": round(c[1] - c[0], 2),
             "palavras_cortadas": " ".join(x["word"] for x in w if x["start"] >= c[0] - 0.02 and x["end"] <= c[1] + 0.02) or "(só pausa)"} for c in fund]
    pistas = []
    for k, x in enumerate(w):
        n = _n(x["word"]); prox = _n(w[k + 1]["word"]) if k + 1 < len(w) else ""
        if (n in ORD and prox == "passo") or (n == "passo" and k + 1 < len(w) and _n(w[k + 1]["word"]) in ORD) or (n == "passo" and not pistas) or re.fullmatch(r"\d+", n) and prox in ("passo", "ideia", "estatico", "estaticos"):
            pistas.append({"t": round(x["start"], 2), "texto": " ".join(y["word"] for y in w[k:k + 3])})
    res = {"video": a.video, "duracao_fala": round(fim_fala, 2), "rosto": rosto(a.video, fim_fala, tmp), "silencios": [[round(x, 2), round(y, 2)] for x, y in sil],
           "cortes_sugeridos": fund, "cortes_conferir": info, "fim_sugerido": round(fim_fala + 0.25, 2), "pistas_de_passo": pistas,
           "uso": "cortes_sugeridos e pistas são propostas (confira \"palavras_cortadas\" de cada corte: pausa não leva palavra, recomeço leva só a fala errada): confira no words.json, escolha os itens/tempos e escreva o cenas.json do formato."}
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    if a.saida: open(a.saida, "w").write(txt)
    print(txt)

if __name__ == "__main__":
    main()
