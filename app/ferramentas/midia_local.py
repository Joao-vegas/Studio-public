#!/usr/bin/env python3
"""midia_local: 3 ferramentas GRÁTIS que rodam no Mac e melhoram o material antes do motor (nada sai da máquina).

  python3 app/ferramentas/midia_local.py upscale <foto> <saida> [--largura 1400]
      Real-ESRGAN (ncnn-vulkan, GPU do Mac, em processo separado e com limite de tempo). Só amplia o que está abaixo da largura
      pedida; foto de 500 px do Flickr/Openverse vira ~2000 px e entra no 1080x1920 sem borrar. Já grande: copia sem mexer.
      Travou, estourou o limite ou falhou: amplia no processador (Lanczos + nitidez leve) e segue. O vídeo nunca para por isso.
  python3 app/ferramentas/midia_local.py parallax <foto> <pasta-quadros> --dur 1.2 [--mov dir|esq|cima|baixo|in] [--forca 1]
      Depth Anything v2 (ONNX, onnxruntime) tira o mapa de profundidade e a câmera "anda" dentro da foto: o que está perto desliza
      mais que o fundo (o corte 3D). Sai uma pasta de JPG a 30 fps = o mesmo formato do `clipe` do Editorial.
  python3 app/ferramentas/midia_local.py so-voz <áudio> <saida.mp3>
      Demucs (htdemucs): fica só a voz do clipe real, sem a música dele, pra não brigar com a trilha do vídeo.
  python3 app/ferramentas/midia_local.py baixar        # baixa os modelos que faltam (Real-ESRGAN, Depth Anything) em app/modelos-locais/

No Editorial (cenas.json): `foto` com `"parallax": true` e efeito de som com `"so_voz": true` (render.py chama esta ferramenta).
Modelos ficam em app/modelos-locais/ferramentas/ (fora do git; o `baixar` e o atualizar.py refazem). Licenças: Real-ESRGAN BSD-3,
Depth Anything V2 Small Apache-2.0, Demucs MIT.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from _comum import rodar_com_limite  # noqa: E402
PASTA = AQUI.parent / "modelos-locais" / "ferramentas"
ESRGAN = PASTA / "realesrgan" / "realesrgan-ncnn-vulkan"
PROF = PASTA / "depth-anything-v2-small-q.onnx"
TRAVOU = PASTA / ".esrgan-travou"      # marca de quando a GPU travou: por um tempo as fotos vão direto pro processador
PAUSA_TRAVOU = 6 * 3600                # s (a GPU presa em UE só solta no reinício: tentar de novo só gasta o limite à toa)
URL_ESRGAN = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip"
URL_PROF = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_quantized.onnx"


def _baixa(url: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "EstudioJoao/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)


def baixar_modelos() -> dict:
    feito = {}
    if not ESRGAN.exists():
        z = PASTA / "realesrgan.zip"
        _baixa(URL_ESRGAN, z)
        subprocess.run(["unzip", "-oq", str(z), "-d", str(PASTA / "realesrgan")], check=True)
        z.unlink(missing_ok=True)
        ESRGAN.chmod(0o755)
        feito["realesrgan"] = "baixado"
    if not PROF.exists():
        _baixa(URL_PROF, PROF)
        feito["depth-anything"] = "baixado"
    return feito or {"tudo": "já estava"}


# ───────────────────────── upscale ─────────────────────────

def _limite_esrgan(w: int, h: int) -> float:
    """Segundos que o Real-ESRGAN pode levar: 120 pra foto comum (~1 Mpx), mais pra maior, no máximo 300."""
    return min(300.0, max(120.0, 120.0 * w * h / 1e6))


def _ampliar_cpu(im, alvo: tuple[int, int]):
    """Ampliação no processador: Lanczos + nitidez leve (sem GPU, não trava)."""
    from PIL import Image, ImageFilter
    return im.convert("RGB").resize(alvo, Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=2))


def _esrgan(entrada: Path, tmp: Path, limite: float) -> str | None:
    """Roda o Real-ESRGAN (GPU) em processo separado e com limite. Devolve None se deu certo, senão o motivo da falha
    (travou, estourou o tempo, erro). Quando trava de vez, deixa a marca TRAVOU pra não repetir nas fotos seguintes."""
    from _comum import RenderTravou
    try:
        if TRAVOU.exists() and time.time() - TRAVOU.stat().st_mtime < PAUSA_TRAVOU:
            return "GPU travou há pouco, nem tentei"
        if not ESRGAN.exists():
            baixar_modelos()
        # sem o -m/cwd ele fica parado procurando os modelos
        r = rodar_com_limite([str(ESRGAN), "-i", str(entrada), "-o", str(tmp), "-m", str(ESRGAN.parent / "models"),
                              "-n", "realesrgan-x4plus", "-s", "4", "-f", "png"],
                             limite, capture_output=True, text=True, cwd=str(ESRGAN.parent))
        if r.returncode or not tmp.exists():
            return "Real-ESRGAN falhou: " + (r.stderr or "")[-200:].strip()
        return None
    except RenderTravou:
        try:
            TRAVOU.write_text(str(int(time.time())))
        except OSError:
            pass
        return f"Real-ESRGAN travou (passou de {limite:.0f} s e foi abandonado)"
    except subprocess.TimeoutExpired:
        return f"Real-ESRGAN passou de {limite:.0f} s"
    except Exception as e:  # noqa: BLE001  (sem binário, sem rede pra baixar...: o vídeo não pode parar)
        return f"Real-ESRGAN indisponível ({type(e).__name__}: {str(e)[:120]})"


def upscale(entrada: Path, saida: Path, largura: int = 1400) -> dict:
    from PIL import Image
    with Image.open(entrada) as im:
        w, h = im.size
    saida.parent.mkdir(parents=True, exist_ok=True)
    if w >= largura:
        if entrada.resolve() != saida.resolve():
            shutil.copy2(entrada, saida)
        return {"ampliada": False, "de": [w, h], "para": [w, h]}
    esc = 2 if w * 2 >= largura else 4
    alvo_w = max(largura, w * esc) if esc == 4 else max(largura, w * 2)
    # x4plus é o modelo de foto; para x2 amplia 4x e volta (mais limpo que o modelo de anime)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / "up.png"
        motivo = _esrgan(entrada, tmp, _limite_esrgan(w, h))
        if motivo is None:
            with Image.open(tmp) as up:
                alvo = (alvo_w, round(up.height * alvo_w / up.width))
                up = up.convert("RGB").resize(alvo, Image.LANCZOS)
        else:
            print(f"aviso: upscale de {Path(entrada).name} no processador: {motivo}", file=sys.stderr, flush=True)
            with Image.open(entrada) as orig:
                alvo = (alvo_w, round(h * alvo_w / w))
                up = _ampliar_cpu(orig, alvo)
        up.save(saida, quality=94) if saida.suffix.lower() in (".jpg", ".jpeg") else up.save(saida)
    r = {"ampliada": True, "de": [w, h], "para": list(alvo)}
    if motivo is not None:
        r.update(motor="cpu", motivo=motivo)
    return r


# ───────────────────────── profundidade + parallax ─────────────────────────

_sess = None


def profundidade(foto: Path):
    """Mapa 0..1 (1 = perto) do tamanho da foto, com cache ao lado (<foto>.prof.npy)."""
    import numpy as np
    from PIL import Image
    cache = foto.with_suffix(foto.suffix + ".prof.npy")
    if cache.exists():
        return np.load(cache)
    global _sess
    if not PROF.exists():
        baixar_modelos()
    import onnxruntime as ort
    if _sess is None:
        _sess = ort.InferenceSession(str(PROF), providers=["CPUExecutionProvider"])
    im = Image.open(foto).convert("RGB")
    x = np.asarray(im.resize((518, 518), Image.BICUBIC), dtype=np.float32) / 255.0
    x = ((x - np.array([.485, .456, .406], dtype=np.float32)) / np.array([.229, .224, .225], dtype=np.float32)).transpose(2, 0, 1)[None]
    nome = _sess.get_inputs()[0].name
    d = _sess.run(None, {nome: x.astype(np.float32)})[0][0]
    d = (d - d.min()) / max(1e-6, d.max() - d.min())
    d = np.asarray(Image.fromarray((d * 255).astype("uint8")).resize(im.size, Image.BICUBIC), dtype=np.float32) / 255.0
    np.save(cache, d)
    return d


def parallax(foto: Path, pasta: Path, dur: float, mov: str = "dir", forca: float = 1.0, fps: int = 30,
             largura: int = 1080, altura: int = 1920) -> int:
    """Quadros JPG (00001.jpg...) de uma câmera que anda dentro da foto, com a profundidade deslocando mais o que está perto."""
    import cv2
    import numpy as np
    prof = profundidade(foto)
    img = cv2.imread(str(foto))
    if img is None:
        raise RuntimeError(f"não abri a foto: {foto}")
    h0, w0 = img.shape[:2]
    # cobre o quadro 1080x1920 com folga (1,22x) pra câmera andar sem mostrar borda
    esc = max(largura / w0, altura / h0) * 1.22
    W, H = round(w0 * esc), round(h0 * esc)
    img = cv2.resize(img, (W, H), interpolation=cv2.INTER_CUBIC if esc > 1 else cv2.INTER_AREA)
    p = cv2.GaussianBlur(cv2.resize(prof, (W, H)), (0, 0), 6)       # borra a profundidade: borda de objeto sem rasgar
    p = (p - np.percentile(p, 3)) / max(1e-6, np.percentile(p, 97) - np.percentile(p, 3))
    p = np.clip(p, 0, 1) - .5
    gx, gy = np.meshgrid(np.arange(largura, dtype=np.float32), np.arange(altura, dtype=np.float32))
    pasta.mkdir(parents=True, exist_ok=True)
    n = max(2, int(round(dur * fps)) + 1)
    amp = 0.03 * W * forca                                           # deslocamento do primeiro plano ao longo do plano
    dx, dy, ent = {"dir": (1, 0, 0), "esq": (-1, 0, 0), "cima": (0, -1, 0), "baixo": (0, 1, 0), "in": (0, 0, 1)}.get(mov, (1, 0, 0))
    for i in range(n):
        u = i / (n - 1)
        s = u - .5                                                    # -0,5..0,5: a câmera atravessa o centro
        zoom = 1 + (.10 if ent else .04) * u                          # sempre entra um pouco: nunca fica parada
        mx = ((gx - largura / 2) / zoom + W / 2).astype(np.float32)
        my = ((gy - altura / 2) / zoom + H / 2).astype(np.float32)
        pr = cv2.remap(p, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)   # profundidade de cada pixel da saída
        # perto (pr>0) desliza mais que o fundo (pr<0): é isso que dá o relevo; o resto anda junto
        mx = mx - dx * s * amp * (1.0 + 2.0 * pr)
        my = my - dy * s * amp * (1.0 + 2.0 * pr)
        quadro = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        cv2.imwrite(str(pasta / f"{i + 1:05d}.jpg"), quadro, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return n


# ───────────────────────── só a voz ─────────────────────────

def so_voz(audio: Path, saida: Path) -> dict:
    """Demucs (htdemucs, 2 trilhas): guarda o stem da voz. Se o clipe não tem voz (torcida, bumbo), o stem sai quase mudo:
    o chamador deve olhar `rms_voz_db` e manter o áudio original nesse caso."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    demucs = shutil.which("demucs") or "/opt/homebrew/bin/demucs"
    with tempfile.TemporaryDirectory() as t:
        wav = Path(t) / "entrada.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-vn", "-ac", "2", "-ar", "44100", str(wav)], check=True)
        r = rodar_com_limite([demucs, "--two-stems=vocals", "-n", "htdemucs", "-o", t, str(wav)], 1800, capture_output=True, text=True)   # torch: nunca preso
        voz = Path(t) / "htdemucs" / "entrada" / "vocals.wav"
        if r.returncode or not voz.exists():
            raise RuntimeError("Demucs falhou: " + (r.stderr or "")[-300:])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(voz), "-c:a", "libmp3lame", "-q:a", "2", str(saida)], check=True)
    v = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(saida), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    import re
    m = re.search(r"mean_volume: (-?[\d.]+) dB", v)
    return {"saida": str(saida), "rms_voz_db": float(m.group(1)) if m else None}


def so_voz_cache(audio: Path) -> Path:
    """<audio>.voz.mp3 ao lado (feito uma vez). Sem voz no clipe (< -45 dB), devolve o próprio áudio."""
    alvo = audio.with_name(audio.stem + ".voz.mp3")
    if not alvo.exists():
        r = so_voz(audio, alvo)
        if r["rms_voz_db"] is not None and r["rms_voz_db"] < -45:
            alvo.unlink(missing_ok=True)
            return audio
    return alvo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("upscale"); u.add_argument("entrada", type=Path); u.add_argument("saida", type=Path); u.add_argument("--largura", type=int, default=1400)
    p = sub.add_parser("parallax"); p.add_argument("foto", type=Path); p.add_argument("pasta", type=Path); p.add_argument("--dur", type=float, default=1.2)
    p.add_argument("--mov", default="dir"); p.add_argument("--forca", type=float, default=1.0)
    s = sub.add_parser("so-voz"); s.add_argument("audio", type=Path); s.add_argument("saida", type=Path)
    sub.add_parser("baixar")
    a = ap.parse_args(argv)
    import json
    if a.cmd == "upscale":
        r = upscale(a.entrada, a.saida, a.largura)
    elif a.cmd == "parallax":
        r = {"quadros": parallax(a.foto, a.pasta, a.dur, a.mov, a.forca), "pasta": str(a.pasta)}
    elif a.cmd == "so-voz":
        r = so_voz(a.audio, a.saida)
    else:
        r = baixar_modelos()
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
