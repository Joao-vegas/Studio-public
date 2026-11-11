#!/usr/bin/env python3
"""casar_imagem: mede o quanto uma imagem mostra o que a fala diz (REGRAS.md, G6). Local e grátis: CLIP.

  python3 app/ferramentas/casar_imagem.py baixar
      baixa os 2 modelos pro cache (app/modelos-locais, fora do git; ~1,1 GB, só na 1ª vez).
  python3 app/ferramentas/casar_imagem.py pontuar <imagem> "<frase>" [--outras "<frase>" ...]
      nota da imagem contra a frase (cosseno do CLIP) e, com --outras, a posição dela entre as falas do vídeo.
  python3 app/ferramentas/casar_imagem.py melhores <video> "<frase>" [-n 5] [--de S] [--ate S] [--passo 0.5] [--saida <pasta>]
      procura DENTRO do vídeo os quadros que mais casam com a frase (amostra de 1 quadro a cada --passo s); com --saida
      grava os JPG em tamanho cheio e a ordem. É assim que se acha "o quadro da câmera" num vídeo oficial.
  python3 app/ferramentas/casar_imagem.py conferir <sandbox> [--json]
      dá a nota de cada cena com imagem contra a fala do trecho e acha a mesma pessoa ou a mesma imagem (mesmo de arquivo diferente) perto
      no tempo, imagem clichê de banco e fala com ação sem vídeo da ação.
  python3 app/ferramentas/casar_imagem.py cliche <imagem> [--banco pexels]
      nota de clichê de banco (foto posando, pilha de dinheiro genérica); a fonte de banco soma na nota.
  python3 app/ferramentas/casar_imagem.py acao "<frase>"
      mostra a ação filmável da fala ("manda dinheiro"), se tiver: ela pede um clipe, não foto parada.

Modelo: CLIP ViT-B/32 (imagem) + o texto multilíngue que fala português direto (sentence-transformers, mesmo espaço do CLIP):
`clip-ViT-B-32` (580 MB) e `clip-ViT-B-32-multilingual-v1` (520 MB); a mesma pessoa vem do rosto (YuNet + SFace do OpenCV, 38 MB). Roda no PROCESSADOR (device="cpu", 30-out-2026): a GPU do Mac (MPS/Metal) dentro do Python às vezes
trava na saída (estado UE, nem kill -9 mata) e este código roda na revisão, na conferência e na produção.
Não usa open_clip: ele troca o torch da venv (2.10 → 2.15) e arrisca o Demucs e o rembg; a conta do sentence-transformers dá
o mesmo CLIP. SigLIP2 base (1,5 GB) foi testado e não saiu melhor nas referências (AUC 0,64 contra 0,67): fora.

Como ler a nota: CLIP mostra pouca diferença em número absoluto (0,20 a 0,30 é a faixa de tudo). Por isso o veredito é RELATIVO:
a imagem contra a fala dela e contra as outras falas do mesmo vídeo. "Não casa" = a fala dela não está entre as que a imagem
mais lembra (posição) E a margem é pequena (z). Limites e como foram calibrados: comentário das constantes.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO, RAIZ, ler_json  # noqa: E402

MODELO_IMG = "sentence-transformers/clip-ViT-B-32"
MODELO_TXT = "sentence-transformers/clip-ViT-B-32-multilingual-v1"
CACHE = ESTUDIO / "modelos-locais"
DEVICE = "cpu"             # nunca "mps": GPU só em processo separado e com limite (ver `_comum.rodar_com_limite`)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VID_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}
SEM_IMAGEM = {"pessoa", "fala", "texto", "frase", "caderno", "traco", "relogio", "zap", "linha", "venn", "jornal"}   # peças que não são uma foto da coisa (o fundo do texto é a imagem da vizinha)
CAMPOS_FOTO = ("imagem", "fonte", "foto")

# Limites (calibrados em 30-out-2026). Régua: (1) os 4 vídeos de referência do Editorial (227 orações com a imagem na janela da fala):
# com Z_NAO_CASA e POSICAO_NAO_CASA abaixo, 11% das orações cairiam em "não casa" (vídeo bom: até ~10%); (2) casos ruins conhecidos:
# Kodak cena 9 (comercial de 1957 sobre "pediu falência em 2012") z -0,64 e posição 80%; Blockbuster "a maior do mundo" com a loja da
# Blockbuster (fala sobre a Netflix) z -0,71 e posição 83%, contra z +4,07 e posição 0% com o logo da Netflix; (3) mesma pessoa:
# a mesma pessoa NÃO sai do CLIP (celular e trilho de trem passavam de 0,62 entre si): sai do rosto, com YuNet (acha) + SFace (identidade),
# os dois do OpenCV, ONNX locais (0,23 + 38 MB em app/modelos-locais/ferramentas). Sasson 0,55 a 0,81 entre foto, vídeo e recorte; Holmes 0,60 a 0,98;
# pessoas diferentes e imagem sem rosto ≤ 0,27.
Z_NAO_CASA = -0.5           # margem da fala própria sobre as outras falas do vídeo, em desvios; abaixo disso, suspeita
POSICAO_NAO_CASA = 0.6      # fração das falas que a imagem lembra MAIS que a dela; acima disso, suspeita
BRUTA_MIN = 0.19            # cosseno mínimo: abaixo é imagem que não lembra nada da frase
MESMA_IMAGEM = 0.93         # cosseno imagem×imagem: mesma foto (ou quase)
MESMA_PESSOA = 0.363        # cosseno SFace entre dois rostos = mesma pessoa (limiar do OpenCV; medido: Holmes 0,60 a 0,98, pessoas diferentes ≤ 0,27, Sasson 0,55 a 0,81)
MAX_PESSOA_NO_VIDEO = 2     # a mesma pessoa aparece no máximo 2 vezes, a não ser que a fala seja sobre ela ali
GENERICAS = ["uma pessoa sorrindo", "um retrato de um homem", "uma paisagem", "um prédio na cidade", "dinheiro", "um carro na rua",
             "um computador", "uma multidão", "um documento", "um celular", "uma sala de reunião", "uma loja", "uma máquina", "comida"]   # sem --outras: o "resto do vídeo" que falta
VIZINHA = 2                 # "cena vizinha" = até 2 cenas depois (uma de texto no meio não esconde a repetição)

# Clichê de banco (30-out-2026, pedido do João: "imagem tem de ser viral e real, não clichê"). Nota = margem do CLIP: quanto a imagem
# lembra MAIS "foto de banco posando" que "foto de notícia/documental" (cosseno máximo de um grupo de frases menos o do outro).
# Calibrado nas 289 fotos das 5 sandboxes de teste do Avulso, 23 marcadas à mão como clichê (pilha de dinheiro, sala de reunião vazia,
# gente rindo pra câmera, empresário no notebook): AUC 0,98. Pilha de dinheiro 0,09 a 0,12; "você riria?" (mulher rindo, Commons) 0,06;
# retrato real do Antioco -0,001; Holmes em palestra 0,036; sala de tribunal real 0,044; foto de arquivo P&B -0,003.
# A fonte conta: Pexels/Pixabay somam BONUS_BANCO (a imagem já nasceu de banco; só o CLIP duvidando basta).
CLICHE_NEG = ["a stock photo of a smiling model posing for the camera", "a stock photo of business people shaking hands in an office",
              "a stock photo of a businessman pointing at a chart", "a woman laughing, generic stock photo",
              "a generic pile of cash on a plain background, stock photo", "stock photo of a happy team in a meeting room",
              "a staged photo of actors posing", "a generic stock photo with a white background",
              "a photo of a person smiling at the camera, royalty free stock image", "a stock photo of people laughing and smiling together",
              "a stock photo of a woman laughing with her mouth open", "a stock photo of an office worker at a desk with a laptop",
              "a stock photo of a boardroom"]
CLICHE_POS = ["a news photograph of a real event", "a screenshot of a news website", "a candid documentary photograph",
              "an archival photograph of a historic moment", "a portrait of a real public figure at a conference",
              "a frame from a television broadcast", "a photograph of a real building or place", "a product photo of a real object",
              "a screenshot of an app or website"]
CLICHE_MIN = 0.05           # margem a partir da qual a imagem é clichê
BONUS_BANCO = 0.02          # soma na margem quando a fonte é banco (Pexels, Pixabay...)
BANCOS = ("pexels", "pixabay", "unsplash", "shutterstock", "istock", "gettyimages", "freepik", "depositphotos", "stock")
# Quase igual (mesmo com arquivo diferente): quanto mais perto no tempo, menor o cosseno que já conta como repetição. Calibrado no Kodak:
# o protótipo da câmera de 1975 em dois quadros do mesmo vídeo oficial (cenas 2 e 4, 5 s) = 0,889; o mesmo prédio da Netflix em 2 fotos
# (5 s) = 0,904; Holmes em 2 fotos 0,85; nota de dólar de perto × monte de notas (9 s) = 0,886 e passa porque é outro enquadramento.
QUASE_IGUAL = ((6.0, 0.88), (15.0, 0.92))   # (até quantos segundos de distância, cosseno mínimo)

_EMB: dict = {}             # cache de vetores por (arquivo, mtime, instante)
_MODELOS: tuple | None = None


class ModeloAusente(RuntimeError):
    pass


# ───────────────────────── modelo ─────────────────────────

def _carregar(baixar: bool = False):
    global _MODELOS
    if _MODELOS is not None:
        return _MODELOS
    try:
        from sentence_transformers import SentenceTransformer
        try:   # sem as barras "Loading weights" no meio da saída
            from transformers.utils import logging as _lg
            _lg.disable_progress_bar()
            _lg.set_verbosity_error()
        except Exception:  # noqa: BLE001
            pass
        # device="cpu" de propósito: nada de MPS/Metal dentro do Python do Estúdio (trava na saída)
        img = SentenceTransformer(MODELO_IMG, cache_folder=str(CACHE), local_files_only=not baixar, device=DEVICE)
        txt = SentenceTransformer(MODELO_TXT, cache_folder=str(CACHE), local_files_only=not baixar, device=DEVICE)
    except Exception as e:  # noqa: BLE001
        raise ModeloAusente("Faltam os modelos do CLIP: rode `app/.venv/bin/python app/ferramentas/casar_imagem.py baixar` "
                            f"(~1,1 GB, uma vez). ({type(e).__name__})") from e
    _MODELOS = (img, txt)
    return _MODELOS


def modelos_prontos() -> bool:
    """Os 2 modelos carregam do cache (sem rede)? Usado pelo teste do MANIFESTO do atualizar.py."""
    try:
        _carregar()
        return True
    except ModeloAusente:
        return False


def baixar() -> dict:
    _carregar(baixar=True)
    import urllib.request
    for f, url in URL_FACE.items():
        if not f.is_file():
            f.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, f)
    return {"modelos": [MODELO_IMG, MODELO_TXT, FACE_DET.name, FACE_REC.name], "pasta": str(CACHE)}


def _emb_imagens(imgs: list):
    """Vetores normalizados (n, 512) de imagens PIL. Os testes trocam esta função."""
    img, _ = _carregar()
    return img.encode(imgs, normalize_embeddings=True, batch_size=32, show_progress_bar=False)


def _emb_textos(txts: list[str]):
    """Vetores normalizados (n, 512) de frases em qualquer língua (português direto). Os testes trocam esta função."""
    _, txt = _carregar()
    return txt.encode(list(txts), normalize_embeddings=True, batch_size=32, show_progress_bar=False)


# ───────────────────────── imagem ─────────────────────────

def _abrir(imagem):
    """Caminho, PIL ou array → PIL RGB. PNG com transparência (recorte) cai sobre fundo cinza-claro, não preto."""
    from PIL import Image
    if hasattr(imagem, "convert"):
        im = imagem
    elif isinstance(imagem, (str, Path)):
        im = Image.open(imagem)
    else:
        im = Image.fromarray(imagem)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        fundo = Image.new("RGBA", im.size, (235, 235, 235, 255))
        fundo.alpha_composite(im)
        im = fundo
    return im.convert("RGB")


def quadro_de_video(video: Path, t: float, largura: int = 640):
    """Um quadro do vídeo no segundo t (PIL), ou None."""
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "q.jpg"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                            "-vf", f"scale={largura}:-2", "-q:v", "3", str(out)], capture_output=True, timeout=120)
        if r.returncode or not out.is_file():
            return None
        return Image.open(out).convert("RGB")


def quadros_do_video(video: Path, passo: float = 0.5, de: float | None = None, ate: float | None = None, largura: int = 320) -> list[tuple[float, object]]:
    """Amostra o vídeo: [(segundo, PIL)] a cada `passo` s entre `de` e `ate`. Uma passada só do ffmpeg."""
    from PIL import Image
    video = Path(video)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    ini = max(0.0, float(de or 0))
    if ini:
        cmd += ["-ss", f"{ini:.3f}"]
    cmd += ["-i", str(video)]
    if ate is not None:
        cmd += ["-t", f"{max(0.1, float(ate) - ini):.3f}"]
    with tempfile.TemporaryDirectory() as d:
        cmd += ["-vf", f"fps=1/{passo:g},scale={largura}:-2", "-q:v", "4", str(Path(d) / "f%05d.jpg")]
        r = subprocess.run(cmd, capture_output=True, timeout=900)
        if r.returncode:
            raise RuntimeError("ffmpeg não abriu o vídeo: " + r.stderr.decode("utf-8", "replace")[-200:])
        out = []
        for i, f in enumerate(sorted(Path(d).glob("f*.jpg"))):
            out.append((round(ini + i * passo + passo / 2, 3), Image.open(f).convert("RGB").copy()))
        return out


# ───────────────────────── pontuar ─────────────────────────

def pontuar(imagem, frase: str) -> float:
    """Cosseno do CLIP entre a imagem e a frase (0 a 1; 0,25 já é bom, abaixo de 0,19 não lembra nada). Pra decidir se casa,
    use `avaliar` (compara com as outras falas do vídeo): o número solto quase não diz nada."""
    return float(_emb_imagens([_abrir(imagem)])[0] @ _emb_textos([frase])[0])


def _estat(bruta: float, outras: list[float]) -> dict:
    """Posição e margem da fala própria entre as outras falas pra mesma imagem."""
    if not outras:
        return {"bruta": round(bruta, 4), "z": None, "posicao": None, "casa": bruta >= BRUTA_MIN}
    media = sum(outras) / len(outras)
    dp = math.sqrt(sum((x - media) ** 2 for x in outras) / len(outras)) or 0.01
    z = (bruta - media) / max(dp, 0.01)
    posicao = sum(1 for x in outras if x > bruta) / len(outras)   # 0 = a fala dela é a que a imagem mais lembra
    casa = bruta >= BRUTA_MIN and not (z < Z_NAO_CASA and posicao > POSICAO_NAO_CASA)
    return {"bruta": round(bruta, 4), "z": round(z, 2), "posicao": round(posicao, 2), "casa": casa}


def avaliar(imagem, frase: str, outras: list[str] | None = None) -> dict:
    """{bruta, z, posicao, casa}: a imagem contra a frase e contra `outras` (as demais falas do vídeo; sem elas, frases genéricas
    como "uma pessoa sorrindo": a imagem tem que lembrar a frase mais do que lembra "um retrato de um homem")."""
    e = _emb_imagens([_abrir(imagem)])[0]
    t = _emb_textos([frase] + (list(outras) if outras else GENERICAS))
    return _estat(float(e @ t[0]), [float(e @ x) for x in t[1:]])


def melhores_quadros(video, frase: str, n: int = 5, passo: float = 0.5, de: float | None = None, ate: float | None = None,
                     saida: Path | None = None, separacao: float = 2.0) -> list[dict]:
    """Os `n` quadros do vídeo que mais casam com a frase: [{t, nota, arquivo?}], do melhor pro pior, a `separacao` s um do outro
    (senão saem 5 quadros do mesmo instante). Com `saida`, grava cada um em tamanho cheio (jpg)."""
    qs = quadros_do_video(video, passo, de, ate)
    if not qs:
        return []
    E = _emb_imagens([q for _, q in qs])
    t = _emb_textos([frase])[0]
    notas = [float(x @ t) for x in E]
    ordem = sorted(range(len(qs)), key=lambda i: -notas[i])
    pegos: list[int] = []
    for i in ordem:
        if all(abs(qs[i][0] - qs[j][0]) >= separacao for j in pegos):
            pegos.append(i)
        if len(pegos) >= n:
            break
    out = []
    for r, i in enumerate(pegos, 1):
        item = {"t": qs[i][0], "nota": round(notas[i], 4)}
        if saida:
            saida = Path(saida)
            saida.mkdir(parents=True, exist_ok=True)
            full = quadro_de_video(Path(video), qs[i][0], largura=1280)
            if full is not None:
                f = saida / f"{r:02d}-t{qs[i][0]:07.2f}.jpg"
                full.save(f, quality=90)
                item["arquivo"] = str(f)
        out.append(item)
    return out


# ───────────────────────── rosto ─────────────────────────

FACE_DET = CACHE / "ferramentas" / "yunet.onnx"
FACE_REC = CACHE / "ferramentas" / "sface.onnx"
URL_FACE = {FACE_DET: "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            FACE_REC: "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"}
_FACE: dict = {}


def faces_prontas() -> bool:
    return FACE_DET.is_file() and FACE_REC.is_file()


def _rosto(imagem):
    """Vetor de identidade (SFace) do maior rosto da imagem, ou None (sem rosto, ou sem os modelos de rosto: o conferir só deixa de
    achar "mesma pessoa"). Os testes trocam esta função."""
    if not faces_prontas():
        return None
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    if "det" not in _FACE:
        _FACE["det"] = cv2.FaceDetectorYN.create(str(FACE_DET), "", (320, 320), 0.8)
        _FACE["rec"] = cv2.FaceRecognizerSF.create(str(FACE_REC), "")
    im = _abrir(imagem)
    im.thumbnail((640, 640))
    bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    _FACE["det"].setInputSize((bgr.shape[1], bgr.shape[0]))
    _, faces = _FACE["det"].detect(bgr)
    if faces is None or not len(faces):
        return None
    maior = faces[int(np.argmax(faces[:, 2] * faces[:, 3]))]
    return _FACE["rec"].feature(_FACE["rec"].alignCrop(bgr, maior))


def _cos_rosto(a, b) -> float:
    """Cosseno entre dois vetores de rosto (o mesmo que o `match` COSINE do SFace)."""
    import numpy as np
    a, b = np.ravel(a), np.ravel(b)
    return float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1.0))


# ───────────────────────── a fala de cada cena ─────────────────────────

def _palavras(sb: Path, doc: dict) -> list[dict]:
    f = sb / str(doc.get("palavras") or "work/words.json")
    if not f.is_file():
        return []
    d = ler_json(f, [])
    lista = d.get("words", d) if isinstance(d, dict) else d
    out = []
    for w in lista:
        if not isinstance(w, dict):
            continue
        txt = str(w.get("word", w.get("w", ""))).strip()
        ini = w.get("start", w.get("s"))
        fim = w.get("end", w.get("e", ini))
        if txt and ini is not None:
            out.append({"w": txt, "s": float(ini), "e": float(fim)})
    return out


def _segmentos(ws: list[dict], max_pal: int = 16) -> list[tuple[int, int]]:
    """Parte a fala em frases [(i0, i1)]: no ponto, na interrogação ou na exclamação; frase de mais de `max_pal` palavras também parte
    na vírgula ou numa pausa de 0,3 s (o Groq nem sempre põe ponto). A frase é o que a imagem deveria mostrar: o trecho de uma
    cena sozinho é só "do mundo. A"."""
    out, ini = [], 0
    for i, w in enumerate(ws):
        n = i - ini + 1
        pausa = i + 1 < len(ws) and ws[i + 1]["s"] - w["e"] >= 0.3
        if re.search(r"[.!?…]$", w["w"]) or (n >= max_pal and (w["w"].endswith((",", ";")) or pausa)) or n >= max_pal + 8:
            out.append((ini, i))
            ini = i + 1
    if ini < len(ws):
        out.append((ini, len(ws) - 1))
    return out


def _frase_de(ws: list[dict], segs: list[tuple[int, int]], de: float, ate: float) -> tuple[str, int | None, str]:
    """(fala do trecho, índice da frase que começa nele, texto da frase)."""
    idx = [i for i, w in enumerate(ws) if de - .02 <= w["s"] < ate - .02]
    if not idx:
        return "", None, ""
    fala = " ".join(ws[i]["w"] for i in idx)
    k = next(j for j, (a, b) in enumerate(segs) if a <= idx[0] <= b)
    a, b = segs[k]
    return fala, k, " ".join(w["w"] for w in ws[a:b + 1])


# ───────────────────────── de onde vem a imagem de cada cena ─────────────────────────

def _fontes_da_cena(sb: Path, c: dict, de: float, ate: float) -> list[dict]:
    """Imagens que a cena mostra: [{arquivo, t?, rotulo}]. Só o que o cenas.json aponta (foto, print, quadro de vídeo, pasta de
    quadros de clipe). Cena sem foto (texto, caderno, pessoa falando...) devolve []."""
    if str(c.get("tipo")) in SEM_IMAGEM:
        return []
    out: list[dict] = []
    for k in CAMPOS_FOTO:
        v = c.get(k)
        if isinstance(v, str) and v:
            out.append({"arquivo": sb / v, "rotulo": v})
    for v in (c.get("imagens") or []):
        if isinstance(v, str) and v:
            out.append({"arquivo": sb / v, "rotulo": v})
    v = c.get("video")
    if isinstance(v, str) and v and str(c.get("tipo")) not in ("pessoa", "fala"):
        ini = float(c["quadro_s"]) if c.get("quadro_s") is not None else float(c.get("inicio_s") or 0) + max(0.0, (ate - de)) / 2
        out.append({"arquivo": sb / v, "t": ini, "rotulo": f"{v} @{ini:.1f}s"})
    q = c.get("quadros_de")
    if isinstance(q, str) and q:
        fs = sorted((sb / q).glob("*.jpg"))
        if fs:
            for f in (fs[len(fs) // 4], fs[len(fs) // 2], fs[3 * len(fs) // 4]):
                out.append({"arquivo": f, "rotulo": f"{q}/{f.name}"})
    return [o for o in out if o["arquivo"].is_file() and (o["arquivo"].suffix.lower() in IMG_EXT | VID_EXT)]


def _imagem_da_fonte(o: dict):
    if o["arquivo"].suffix.lower() in VID_EXT:
        return quadro_de_video(o["arquivo"], o.get("t") or 0.0)
    return _abrir(o["arquivo"])


def _vetor_da_fonte(o: dict):
    chave = (str(o["arquivo"]), o["arquivo"].stat().st_mtime, o.get("t"))
    if chave not in _EMB:
        im = _imagem_da_fonte(o)
        _EMB[chave] = (_emb_imagens([im])[0], _rosto(im)) if im is not None else (None, None)
    return _EMB[chave]


# ───────────────────────── a conferência de um vídeo ─────────────────────────

def conferir_cenas(sandbox) -> dict:
    """Nota de cada cena com imagem contra a fala dela, e a mesma pessoa/imagem em cenas vizinhas.

    Devolve {cenas: [{n, de, ate, tipo, fala, frase, imagens, bruta, z, posicao, casa}], achados: [{cena, tipo, texto, conserto}],
    resumo}. Os `achados` já vêm em português simples (tipo: nao_casa | mesma_imagem | quase_igual | mesma_pessoa | pessoa_demais | cliche |
    acao_sem_video; os dois últimos olham o que a imagem É, não só se casa: REGRAS.md G6)."""
    sb = Path(sandbox)
    doc = ler_json(sb / "cenas.json", None)
    if not isinstance(doc, dict) or not doc.get("cenas"):
        return {"cenas": [], "achados": [], "resumo": "sem cenas.json", "sem_cenas": True}
    cs = doc["cenas"]
    ws = _palavras(sb, doc)
    segs = _segmentos(ws)
    dur = float(doc.get("duracao") or (ws[-1]["e"] if ws else (cs[-1].get("de", 0) + 2)))
    itens: list[dict] = []
    for i, c in enumerate(cs):
        de = float(c.get("de", 0))
        ate = float(c["ate"]) if c.get("ate") is not None else (float(cs[i + 1]["de"]) if i + 1 < len(cs) else dur)
        fala, k_frase, frase = _frase_de(ws, segs, de, ate)
        fontes = _fontes_da_cena(sb, c, de, ate)
        itens.append({"n": i + 1, "de": round(de, 2), "ate": round(ate, 2), "tipo": c.get("tipo", ""), "fala": fala, "frase": frase, "k": k_frase,
                      "acao": acao_da_fala(frase), "imagens": [f["rotulo"] for f in fontes], "_fontes": fontes, "_cena": c})
    falas = list(dict.fromkeys(it["frase"] for it in itens if it["frase"]))   # uma por frase (duas frases iguais contam uma)
    vetores = {}
    for it in itens:
        if it["_fontes"]:
            vs = [(o, _vetor_da_fonte(o)) for o in it["_fontes"]]
            vs = [(o, v) for o, v in vs if v[0] is not None]
            it["_fontes"] = [o for o, _v in vs]   # fonte e vetor sempre do mesmo tamanho e na mesma ordem
            vetores[it["n"]] = [v for _o, v in vs]
    TF = _emb_textos(falas) if falas else []
    achados: list[dict] = []
    # 1) casa com a fala? O veredito é da FRASE: vale a melhor imagem entre as cenas dela (o Editorial parte uma frase em 5 cenas)
    for fr in falas:
        do_trecho = [it for it in itens if it["frase"] == fr and vetores.get(it["n"])]
        if not do_trecho:
            continue
        i_f = falas.index(fr)
        melhor, melhor_it = None, None
        for it in do_trecho:
            for e, _r in vetores[it["n"]]:
                sims = [float(e @ t) for t in TF]
                st = _estat(sims[i_f], [s for k, s in enumerate(sims) if k != i_f])
                if melhor is None or st["bruta"] > melhor["bruta"]:
                    melhor, melhor_it = st, it
        for it in do_trecho:
            it.update(melhor)
        if not melhor["casa"]:
            ns = [it["n"] for it in do_trecho]
            quais = f"Cena {ns[0]}" if len(ns) == 1 else f"Cenas {ns[0]} a {ns[-1]}"
            achados.append({"cena": ns[0], "cenas": ns, "tipo": "nao_casa",
                            "texto": f"{quais} ({do_trecho[0]['de']:.1f} s): a imagem não mostra o que a fala diz (\"{fr}\"). "
                                     + (f"Ela lembra mais outras falas do vídeo (nota {melhor['bruta']:.2f}, {int(melhor['posicao'] * 100)}% das outras falas casam mais)."
                                        if melhor["posicao"] is not None else f"A nota dela com a fala é só {melhor['bruta']:.2f} (piso {BRUTA_MIN})."),
                            "conserto": "Troque por uma imagem do objeto, da ação ou do lugar que a fala cita: `casar_imagem.py melhores <vídeo> \"<fala>\"` "
                                        "acha o quadro certo dentro de um vídeo real; confira com `pontuar` antes de fechar a cena."})
    # 2) a mesma imagem ou a mesma pessoa em cenas vizinhas, e a mesma pessoa vezes demais
    comfoto = [it for it in itens if vetores.get(it["n"])]
    marcadas: set[tuple] = set()
    for a_i, a in enumerate(comfoto):
        for b in comfoto[a_i + 1:]:
            if b["n"] - a["n"] > VIZINHA:
                break
            r = _parecidas(vetores[a["n"]], vetores[b["n"]], a["_fontes"], b["_fontes"])
            if not r or (a["n"], b["n"]) in marcadas:
                continue
            if r["tipo"] == "mesma_imagem" and a["k"] == b["k"]:
                continue   # a mesma foto segurada durante uma frase só (o texto muda por cima): não é repetição
            if r["tipo"] == "mesma_pessoa" and (_fala_sobre_ela(a) and _fala_sobre_ela(b)):
                continue
            marcadas.add((a["n"], b["n"]))
            quem = "a mesma imagem" if r["tipo"] == "mesma_imagem" else "a mesma pessoa"
            achados.append({"cena": b["n"], "cenas": [a["n"], b["n"]], "tipo": r["tipo"],
                            "texto": f"Cenas {a['n']} e {b['n']} (vizinhas): {quem} (semelhança {r['cos']:.2f}). Repete a imagem em vez de mostrar o que a fala diz.",
                            "conserto": f"Troque a imagem da cena {b['n']} (ou da {a['n']}) por uma que mostre o objeto ou a ação da fala, sem repetir a pessoa."})
    achados += _pessoa_demais(comfoto, vetores)
    achados += _quase_iguais(comfoto, vetores, marcadas)
    achados += _cliches(comfoto, vetores)
    achados += _acao_sem_video(itens)
    notas = [it for it in itens if it.get("bruta") is not None]
    resumo = (f"{len(notas)} cenas com imagem; {sum(1 for it in notas if not it['casa'])} não casam com a fala; "
              f"{sum(1 for a in achados if a['tipo'] in ('mesma_imagem', 'quase_igual', 'mesma_pessoa', 'pessoa_demais'))} repetições; "
              f"{sum(1 for a in achados if a['tipo'] == 'cliche')} clichês de banco; "
              f"{sum(1 for a in achados if a['tipo'] == 'acao_sem_video')} ações sem vídeo")
    limpo = [{k: v for k, v in it.items() if not k.startswith("_")} for it in itens]
    return {"cenas": limpo, "achados": sorted(achados, key=lambda a: a["cena"]), "resumo": resumo, "falas": len(falas)}


def _parecidas(va: list, vb: list, fa: list[dict], fb: list[dict]) -> dict | None:
    """Duas cenas mostram a mesma imagem (arquivo igual ou cosseno ≥ MESMA_IMAGEM) ou a mesma pessoa (dois rostos, cosseno ≥ MESMA_PESSOA)?"""
    melhor = None
    for (ea, ra), oa in zip(va, fa):
        for (eb, rb), ob in zip(vb, fb):
            cos = float(ea @ eb)
            igual = oa["arquivo"] == ob["arquivo"] and (oa.get("t") is None or ob.get("t") is None or abs(oa["t"] - ob["t"]) < 2)
            cos_r = _cos_rosto(ra, rb) if (ra is not None and rb is not None) else 0.0
            tipo = "mesma_imagem" if (igual or cos >= MESMA_IMAGEM) else ("mesma_pessoa" if cos_r >= MESMA_PESSOA else None)
            cos = cos if tipo == "mesma_imagem" else cos_r
            if tipo and (melhor is None or cos > melhor["cos"]):
                melhor = {"tipo": tipo, "cos": cos}
    return melhor


# ───────────────────────── clichê de banco ─────────────────────────

_TXT_CLICHE: dict = {}


def _vetores_cliche():
    if "v" not in _TXT_CLICHE:
        _TXT_CLICHE["v"] = (_emb_textos(CLICHE_NEG), _emb_textos(CLICHE_POS))
    return _TXT_CLICHE["v"]


def margem_cliche(e) -> float:
    """Margem do CLIP: quanto o vetor `e` da imagem lembra mais "foto de banco posando" que "foto real de notícia ou documental"."""
    neg, pos = _vetores_cliche()
    return float((e @ neg.T).max() - (e @ pos.T).max())


def fonte_banco(arquivo, cena: dict | None = None) -> str:
    """"pexels", "pixabay"... se a imagem veio de banco (nome do arquivo, `origem.json` da pasta ou o campo `origem` da cena); senão ""."""
    arquivo = Path(arquivo)
    partes = [arquivo.name.lower(), str((cena or {}).get("origem") or "").lower()]
    chave = arquivo.parent.name[2:] if arquivo.parent.name.startswith("q-") else ""
    for pasta in (arquivo.parent, arquivo.parent.parent):
        d = ler_json(pasta / "origem.json", None)
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            for it in (v if isinstance(v, list) else [v]):
                if isinstance(it, dict) and (it.get("arquivo") == arquivo.name or (chave and k == chave)):
                    partes.append(" ".join(str(x).lower() for x in it.values()))
    blob = " ".join(partes)
    for nome in BANCOS:
        if re.search(rf"(?<![a-z]){nome}(?![a-z])", blob):
            return nome
    return ""


def avaliar_cliche(imagem=None, banco: str = "", e=None) -> dict:
    """{margem, banco, nota, cliche}: `nota` = margem + BONUS_BANCO se a fonte é banco; clichê quando a nota passa de CLICHE_MIN.
    Aceita o vetor `e` já calculado (a conferência dos vídeos) ou a imagem (arquivo, PIL)."""
    if e is None:
        e = _emb_imagens([_abrir(imagem)])[0]
    m = margem_cliche(e)
    nota = m + (BONUS_BANCO if banco else 0.0)
    return {"margem": round(m, 3), "banco": banco, "nota": round(nota, 3), "cliche": nota >= CLICHE_MIN}


# ───────────────────────── ação na fala ─────────────────────────

# Verbos que se FILMAM (REGRAS.md G6: ação = vídeo da ação). Raiz + terminações comuns; só o que alguém faz com o corpo ou com um objeto.
ACOES = [r"mand(a|o|ou|am|aram|ar|ando)\b.{0,12}\b(dinheiro|grana|pix|transfer\w+|mensagem|email|e-mail)", r"transfer(e|iu|em|ir|indo)\b",
         r"pag(a|o|ou|am|aram|ar|ando)\b", r"digit(a|ou|am|aram|ar|ando)\b", r"corr(e|eu|em|eram|er|endo)\b", r"ca(i|iu|em|íram|iram|ir|indo)\b",
         r"lig(a|ou|am|aram|ar|ando)\b", r"assin(a|ou|am|aram|ar|ando)\b", r"(ri|riu|riem|rir|rindo|riria|riam|gargalh\w+)\b", r"compr(a|ou|am|aram|ar|ando)\b",
         r"entreg(a|ou|am|aram|ar|ando)\b", r"aperta(m|r|ndo|ou)?\b", r"escrev(e|eu|em|eram|er|endo)\b",
         r"saca(m|r|ndo|ou)?\b", r"gast(a|ou|am|aram|ar|ando)\b", r"fug(iu|iram|ir|indo)\b", r"demit(e|iu|em|iram|ir|indo)\b",
         r"apont(a|ou|am|aram|ar|ando)\b", r"abra[çc](a|ou|am|aram|ar|ando)\b",
         r"dirig(e|iu|em|iram|ir|indo)\b", r"danç(a|ou|am|aram|ar|ando)\b", r"fech(a|ou|am|aram|ar|ando)\b.{0,10}\b(porta|loja|negócio|acordo)"]
CLIPE_TIPOS = ("clipe", "filme")   # peças que tocam vídeo (foto, print e polaroid são imagem parada)


def acao_da_fala(frase: str) -> str:
    """O trecho da fala que descreve uma ação filmável ("manda dinheiro", "assinou", "riria"), ou "". É o que pede CLIPE, não foto parada."""
    t = (frase or "").lower()
    for rx in ACOES:
        m = re.search(r"\b" + rx, t)
        if m:
            ini = max(0, t.rfind(" ", 0, max(0, m.start() - 1)) + 1)
            return t[ini:m.end()].strip()
    return ""


def _sem_acento(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


def _fala_sobre_ela(it: dict) -> bool:
    """A fala da cena cita o nome que está no arquivo da imagem (`fotos/reed-0.jpg` + "Reed Hastings")? Aí a pessoa pode aparecer."""
    nomes = {_sem_acento(p) for p in re.findall(r"\w{4,}", it["frase"] or "")}
    for o in it["_fontes"]:
        pedacos = set(re.findall(r"[a-z]{4,}", _sem_acento(Path(o["arquivo"]).stem)))
        if nomes & pedacos:
            return True
    return False


def _quase_iguais(comfoto: list[dict], vetores: dict, marcadas: set) -> list[dict]:
    """Imagem parecida demais com outra de FRASE diferente, mesmo de arquivo diferente (o protótipo da Kodak em 2 quadros do mesmo vídeo):
    quanto mais perto no tempo, menor o cosseno que já conta (QUASE_IGUAL). Duas cenas da mesma frase não contam: ali a foto segura."""
    out = []
    for a_i, a in enumerate(comfoto):
        for b in comfoto[a_i + 1:]:
            dt = b["de"] - a["de"]
            if dt > QUASE_IGUAL[-1][0]:
                break
            if (a["n"], b["n"]) in marcadas or (a["k"] is not None and a["k"] == b["k"]):
                continue
            minimo = next((c for janela, c in QUASE_IGUAL if dt <= janela), None)
            if minimo is None:
                continue
            melhor = None
            for (ea, _ra), oa in zip(vetores[a["n"]], a["_fontes"]):
                for (eb, _rb), ob in zip(vetores[b["n"]], b["_fontes"]):
                    igual = oa["arquivo"] == ob["arquivo"] and (oa.get("t") is None or ob.get("t") is None or abs(oa["t"] - ob["t"]) < 2)
                    cos = 1.0 if igual else float(ea @ eb)
                    if cos >= minimo and (melhor is None or cos > melhor):
                        melhor = cos
            if melhor is None:
                continue
            marcadas.add((a["n"], b["n"]))
            out.append({"cena": b["n"], "cenas": [a["n"], b["n"]], "tipo": "quase_igual", "cos": round(melhor, 3),
                        "texto": f"Cenas {a['n']} e {b['n']} ({dt:.0f} s uma da outra): "
                                 + ("a mesma foto reaproveitada" if melhor >= 1 else f"quase a mesma imagem (semelhança {melhor:.2f}, arquivos diferentes)")
                                 + ". O público vê a mesma coisa duas vezes.",
                        "conserto": f"Troque a imagem da cena {b['n']} por outra que mostre outra coisa da fala (outro ângulo, outro lugar, a ação em vídeo), "
                                    "real do caso; não reuse a mesma foto nem outro quadro do mesmo clipe."})
    return out


def _cliches(comfoto: list[dict], vetores: dict) -> list[dict]:
    """Imagem de banco posando (pilha de dinheiro genérica, aperto de mão, gente rindo pra câmera): um achado por imagem, com as cenas dela."""
    vistos: dict[tuple, dict] = {}
    for it in comfoto:
        for (e, _r), o in zip(vetores[it["n"]], it["_fontes"]):
            q = o["arquivo"].parent.name.startswith("q-")   # os quadros de um clipe contam como uma imagem só (a pior nota)
            chave = (str(o["arquivo"].parent if q else o["arquivo"]), 0 if q else round(o.get("t") or 0))
            r = vistos.get(chave)
            if r is None:
                banco = fonte_banco(o["arquivo"], it["_cena"])
                r = vistos[chave] = {**avaliar_cliche(banco=banco, e=e), "cenas": [], "rotulo": o["rotulo"], "de": it["de"]}
            r["cenas"].append(it["n"])
            if r["nota"] < avaliar_cliche(banco=r["banco"], e=e)["nota"]:
                r.update(avaliar_cliche(banco=r["banco"], e=e))
    out = []
    for r in vistos.values():
        if not r["cliche"]:
            continue
        ns = sorted(set(r["cenas"]))
        quais = f"Cena {ns[0]}" if len(ns) == 1 else f"Cenas {', '.join(map(str, ns))}"
        porque = (f"veio de banco ({r['banco']}) e " if r["banco"] else "") + f"parece foto de banco posando (nota {r['nota']:.2f}, limite {CLICHE_MIN:.2f})"
        out.append({"cena": ns[0], "cenas": ns, "tipo": "cliche", "nota": r["nota"],
                    "texto": f"{quais} ({r['de']:.1f} s): a imagem é clichê, {porque}: {r['rotulo']}.",
                    "conserto": "Troque, nesta ordem: o momento real do caso (notícia, vídeo oficial, foto da pessoa ou do lugar de verdade); um clipe viral ou famoso "
                                "que todo mundo reconhece; só então banco. Se a fala descreve uma ação, use o CLIPE da ação (`clipe.py busca`, `casar_imagem.py melhores`)."})
    return out


def _acao_sem_video(itens: list[dict]) -> list[dict]:
    """A fala descreve uma ação filmável ("manda dinheiro") e nenhuma cena dessa frase toca vídeo: aviso pra trocar por um clipe da ação."""
    por_frase: dict = {}
    for it in itens:
        if it["frase"] and it["acao"]:
            por_frase.setdefault(it["frase"], []).append(it)
    out = []
    for fr, its in por_frase.items():
        if any(str(i["tipo"]) in CLIPE_TIPOS or (i["_cena"].get("quadros_de")) for i in its):
            continue
        if not any(i["_fontes"] for i in its):
            continue   # frase só com texto/caderno: sem imagem pra trocar
        ns = [i["n"] for i in its if i["_fontes"]]
        out.append({"cena": ns[0], "cenas": ns, "tipo": "acao_sem_video",
                    "texto": f"Cena{'s' if len(ns) > 1 else ''} {', '.join(map(str, ns))} ({its[0]['de']:.1f} s): a fala descreve uma ação (\"{its[0]['acao']}\") "
                             "e a imagem é parada.",
                    "conserto": "Ação = vídeo da ação: busque um clipe real de quem faz isso (`clipe.py busca \"<a ação em inglês>\"`, get-brolls no YouTube/TikTok/Instagram) "
                                "e ache o trecho com `casar_imagem.py melhores <vídeo> \"<a ação>\"`."})
    return out


def _pessoa_demais(comfoto: list[dict], vetores: dict) -> list[dict]:
    """A mesma pessoa em mais de MAX_PESSOA_NO_VIDEO cenas do vídeo: agrupa os rostos parecidos e avisa o grupo grande."""
    rostos = [(it, vetores[it["n"]]) for it in comfoto if any(r is not None for _, r in vetores[it["n"]]) and not _fala_sobre_ela(it)]
    grupo = {it["n"]: it["n"] for it, _ in rostos}

    def raiz(x):
        while grupo[x] != x:
            x = grupo[x]
        return x
    for i, (a, va) in enumerate(rostos):
        for b, vb in rostos[i + 1:]:
            if any(ra is not None and rb is not None and _cos_rosto(ra, rb) >= MESMA_PESSOA for _, ra in va for _, rb in vb):
                grupo[raiz(b["n"])] = raiz(a["n"])
    por: dict[int, list[int]] = {}
    for n in grupo:
        por.setdefault(raiz(n), []).append(n)
    out = []
    for ns in por.values():
        if len(ns) > MAX_PESSOA_NO_VIDEO:
            ns.sort()
            out.append({"cena": ns[MAX_PESSOA_NO_VIDEO], "tipo": "pessoa_demais",
                        "texto": f"A mesma pessoa aparece em {len(ns)} cenas (as {', '.join(map(str, ns))}); o máximo é {MAX_PESSOA_NO_VIDEO}.",
                        "conserto": "Deixe a pessoa em 2 cenas no máximo e, nas outras, mostre o objeto, o lugar ou a ação que a fala cita."})
    return out


# ───────────────────────── linha de comando ─────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baixar")
    p = sub.add_parser("pontuar")
    p.add_argument("imagem")
    p.add_argument("frase")
    p.add_argument("--outras", action="append", default=[])
    m = sub.add_parser("melhores")
    m.add_argument("video")
    m.add_argument("frase")
    m.add_argument("-n", type=int, default=5)
    m.add_argument("--de", type=float)
    m.add_argument("--ate", type=float)
    m.add_argument("--passo", type=float, default=0.5)
    m.add_argument("--saida")
    c = sub.add_parser("conferir")
    c.add_argument("sandbox")
    c.add_argument("--json", action="store_true")
    k = sub.add_parser("cliche")
    k.add_argument("imagem")
    k.add_argument("--banco", default="", help="de onde veio (pexels, pixabay...): soma na nota")
    ac = sub.add_parser("acao")
    ac.add_argument("frase")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "baixar":
            print(json.dumps(baixar(), ensure_ascii=False))
        elif a.cmd == "pontuar":
            r = avaliar(a.imagem, a.frase, a.outras)
            print(json.dumps(r, ensure_ascii=False))
        elif a.cmd == "cliche":
            print(json.dumps(avaliar_cliche(a.imagem, a.banco or fonte_banco(a.imagem)), ensure_ascii=False))
        elif a.cmd == "acao":
            print(acao_da_fala(a.frase) or "(nenhuma ação filmável)")
        elif a.cmd == "melhores":
            for r in melhores_quadros(a.video, a.frase, a.n, a.passo, a.de, a.ate, a.saida):
                print(f"t={r['t']:7.2f}s  nota={r['nota']:.3f}  {r.get('arquivo', '')}")
        else:
            r = conferir_cenas(a.sandbox)
            if a.json:
                print(json.dumps(r, ensure_ascii=False, indent=1))
            else:
                print(r["resumo"])
                for it in r["cenas"]:
                    if it.get("bruta") is not None:
                        print(f"  cena {it['n']:>2} {it['tipo']:<9} {it['de']:6.1f}s  nota {it['bruta']:.3f}  z {it['z']!s:>5}  pos {it['posicao']!s:>4}  "
                              f"{'ok ' if it['casa'] else 'NÃO'}  {it['fala'][:50]}")
                for x in r["achados"]:
                    print("-", x["texto"])
        return 0
    except ModeloAusente as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
