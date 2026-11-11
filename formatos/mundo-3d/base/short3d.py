#!/usr/bin/env python3
"""Mundo 3D (formato mundo-3d do Estúdio): monta as props e renderiza a composição Short3D do Remotion.

A sandbox (pasta do vídeo) tem:
  short3d.json         cenas em segundos: {"musica": "audio/musica.mp3"|null, "musica_vol": 0.09,
                       "cenas": [{"de": 0.0, "tipo": "3d", "cena": "<nome no Registro3D>"} | {"de":..,"tipo":"img","img":"img/x.jpg","mov":"in"}]}
  audio/voz.wav        a narração (limpa, sem ruído depois da última palavra)
  audio/palavras.json  [{"w","s","e"}] tempo de cada palavra; se faltar, o whisper do Mac (mlx) gera sozinho
O "de" de cada cena é o tempo da palavra dita (olhe palavras.json); o fim de uma cena é o início da seguinte.

Uso:
  python3 short3d.py <sandbox>                      storyboard: um quadro por cena (storyboard.jpg + qa/cena-NN.jpg)
  python3 short3d.py <sandbox> --still 12.5         um quadro (qa/still-012.5.jpg), para conferir UMA cena
  python3 short3d.py <sandbox> --final --saida X.mp4   render completo 1080x1920 + loudnorm -14 LUFS
Opções: --json outro.json (um json por grupo de cenas; ele só usa as cenas dele) · --ate S (renderiza só até o segundo S)
NUNCA rode dois renders ao mesmo tempo (a máquina engasga e os quadros saem errados). Stills podem ser em paralelo de grupos.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REMOTION = BASE / "remotion"
FPS = 30
CAUDA = 0.8   # segundos depois da última palavra
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
ESTUDIO = BASE.parents[2]
PY = ESTUDIO / "app" / ".venv" / "bin" / "python"
WHISPER = "mlx-community/whisper-large-v3-turbo"
LINGUA = os.environ.get("MOTION_LINGUA", "en")   # idioma da fala para o whisper (pt, en...)


def py() -> str:
    return str(PY if PY.exists() else sys.executable)


def link(alvo: Path, nome: Path) -> None:
    """Cria o link; tolera dois processos criando ao mesmo tempo."""
    try:
        if nome.is_symlink() and nome.resolve() == Path(alvo).resolve():
            return
        if nome.is_symlink() or nome.exists():
            nome.unlink()
        nome.symlink_to(alvo)
    except FileExistsError:
        pass


def garantir_npm() -> None:
    if (REMOTION / "node_modules" / "remotion").is_dir():
        return
    print("primeira vez: npm install do Remotion (alguns minutos)…")
    subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=REMOTION, check=True)


def palavras_whisper(voz: Path, saida: Path) -> list:
    cod = ("import json,sys,mlx_whisper\n"
           f"r=mlx_whisper.transcribe(sys.argv[1],path_or_hf_repo='{WHISPER}',language='{LINGUA}',word_timestamps=True)\n"
           "print(json.dumps([{'w':w['word'].strip(),'s':w['start'],'e':w['end']} for s in r['segments'] for w in s.get('words',[])]))")
    r = subprocess.run([py(), "-c", cod, str(voz)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("o whisper não rodou: " + r.stderr[-600:])
    ws = json.loads(r.stdout.strip().splitlines()[-1])
    saida.write_text(json.dumps(ws))
    return ws


def palavras_legenda(ws: list) -> list:
    """Junta os pedaços que o whisper separa ("2" ",800", "all" "-electric", "2" ".26")."""
    out = []
    for w in ws:
        t = w["w"].strip()
        if out and re.match(r"^[,.\-]\S", t):
            out[-1]["t"] += t
            out[-1]["ate"] = w["e"]
        else:
            out.append({"t": t, "de": w["s"], "ate": w["e"]})
    return [{"t": x["t"], "de": round(x["de"] * FPS), "ate": round(x["ate"] * FPS)} for x in out]


def montar(sb: Path, nome_json: str, ate: float | None):
    cfg = json.loads((sb / nome_json).read_text())
    voz = sb / "audio" / "voz.wav"
    pal = sb / "audio" / "palavras.json"
    if not voz.is_file():
        raise SystemExit("falta audio/voz.wav na sandbox (gere a narração antes)")
    ws = json.loads(pal.read_text()) if pal.is_file() else palavras_whisper(voz, pal)
    total_s = ate if ate else ws[-1]["e"] + CAUDA
    f = lambda s: round(s * FPS)  # noqa: E731
    cenas = [c for c in cfg["cenas"] if c["de"] < total_s]   # --ate: descarta as cenas que começam depois do corte
    for i, c in enumerate(cenas):
        c["ate"] = cenas[i + 1]["de"] if i + 1 < len(cenas) else total_s
    pub = sb / ".publico"
    pub.mkdir(exist_ok=True)
    link(REMOTION / "public" / "fontes", pub / "fontes")
    link(REMOTION / "public" / "mapas", pub / "mapas")
    link(sb, pub / "v")
    props = {
        "fps": FPS, "total": f(total_s), "voz": "v/audio/voz.wav",
        "musica": {"src": f"v/{cfg['musica']}", "vol": cfg.get("musica_vol", 0.09)} if cfg.get("musica") else None,
        "cenas": [{**c, "de": f(c["de"]), "ate": f(c["ate"]), **({"img": f"v/{c['img']}"} if c.get("img") else {})} for c in cenas],
        "legendas": palavras_legenda(ws),
    }
    arq = sb / f"{Path(nome_json).stem}-props.json"
    arq.write_text(json.dumps(props))
    opc = [f"--props={arq}", f"--public-dir={pub}", "--timeout=120000", "--log=error"]
    if CHROME.is_file():
        opc.append(f"--browser-executable={CHROME}")
    return cfg, cenas, total_s, f, opc


def still(sb: Path, opc: list, quadro: int, out: Path) -> None:
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["npx", "remotion", "still", "src/index.ts", "Short3D", str(out), *opc, f"--frame={quadro}", "--gl=angle"],
                   cwd=REMOTION, check=True)


def storyboard(sb: Path, cenas: list, f, opc: list) -> Path:
    from PIL import Image, ImageDraw
    qa = sb / "qa"
    qa.mkdir(exist_ok=True)
    fotos = []
    for i, c in enumerate(cenas, 1):
        seg = c["de"] + min(1.5, max(0.2, (c["ate"] - c["de"]) / 2))   # 1,5 s depois do início (a câmera já andou)
        out = qa / f"cena-{i:02d}.jpg"
        still(sb, opc, f(seg), out)
        fotos.append((i, seg, c, out))
    cols, w, h = 6, 270, 480
    linhas = (len(fotos) + cols - 1) // cols
    folha = Image.new("RGB", (cols * w, linhas * (h + 22)), "#111")
    d = ImageDraw.Draw(folha)
    for k, (i, seg, c, out) in enumerate(fotos):
        x, y = (k % cols) * w, (k // cols) * (h + 22)
        folha.paste(Image.open(out).resize((w, h)), (x, y + 22))
        d.text((x + 4, y + 5), f"{i}  {seg:.1f}s  {c.get('cena') or c.get('img', '')}", fill="#fff")
    dest = sb / "storyboard.jpg"
    folha.save(dest, quality=88)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sandbox"); ap.add_argument("--still", type=float)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--json", default="short3d.json", help="arquivo de cenas dentro da sandbox")
    ap.add_argument("--ate", type=float, help="renderiza só do início até esse segundo")
    ap.add_argument("--saida", default="short-final.mp4", help="nome (ou caminho) do mp4 final")
    a = ap.parse_args()
    sb = Path(a.sandbox).resolve()
    garantir_npm()
    cfg, cenas, total_s, f, opc = montar(sb, a.json, a.ate)
    if a.still is not None:
        out = sb / "qa" / f"still-{Path(a.json).stem}-{a.still:05.1f}.jpg"
        still(sb, opc, f(a.still), out)
        return print(out)
    if not a.final:
        return print(storyboard(sb, cenas, f, opc))
    bruto = sb / f"bruto-{Path(a.saida).stem}.mp4"
    extra = [f"--frames=0-{f(total_s) - 1}"] if a.ate else []
    subprocess.run(["npx", "remotion", "render", "src/index.ts", "Short3D", str(bruto), *opc, "--gl=angle", "--concurrency=6", *extra],
                   cwd=REMOTION, check=True)
    final = Path(a.saida) if Path(a.saida).is_absolute() else sb / a.saida
    final.parent.mkdir(parents=True, exist_ok=True)
    corte = ["-t", f"{total_s:.3f}"] if a.ate else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto), *corte, "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(final)], check=True)
    print(f"ok: {final} · {total_s:.1f} s")


if __name__ == "__main__":
    main()
