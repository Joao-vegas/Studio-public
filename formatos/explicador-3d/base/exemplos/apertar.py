# aperta as pausas da narração. Padrão do Explicador 3D (Loaded Dice: pausa pós-frase 0,11 s na mediana): silêncio > 0,20 s vira
# 0,14 s (0,06 depois da fala + 0,08 antes da próxima). Uso: python3 apertar.py bruta.mp3 voz.wav [maximo depois antes]
import subprocess, re, sys, numpy as np, json
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
MAX, DEP, ANT = (float(v) for v in (sys.argv[3:6] if len(sys.argv) >= 6 else (.20, .06, .08)))
sr = 48000
x = np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",str(src),"-f","f32le","-ac","1","-ar",str(sr),"-"],capture_output=True,check=True).stdout, np.float32)
log = subprocess.run(["ffmpeg","-i",str(src),"-af","silencedetect=noise=-40dB:d=0.1","-f","null","-"],capture_output=True,text=True).stderr
ini = [float(v) for v in re.findall(r"silence_start: ([0-9.]+)", log)]; fim = [float(v) for v in re.findall(r"silence_end: ([0-9.]+)", log)]
cortes = []
for a, b in zip(ini, fim):
    if a <= 0.01: cortes.append((0, max(0, b - .06))); continue
    if b - a > MAX: cortes.append((a + DEP, b - ANT))
out, p, mapa = [], 0, []
fade = int(.006 * sr)
for a, b in cortes:
    A, B = int(a * sr), int(b * sr)
    seg = x[p:A].copy()
    if len(seg) > 2 * fade: seg[-fade:] *= np.linspace(1, 0, fade)
    out.append(seg); mapa.append([a, b]); p = B
out.append(x[p:])
y = np.concatenate(out)
subprocess.run(["ffmpeg","-v","error","-y","-f","f32le","-ac","1","-ar",str(sr),"-i","-","-af","loudnorm=I=-16:TP=-1.5:LRA=7",str(dst)], input=y.tobytes(), check=True)
json.dump(mapa, open(dst.with_suffix(".cortes.json"),"w"))
print(f"{len(x)/sr:.2f}s -> {len(y)/sr:.2f}s, {len(cortes)} pausas apertadas")
