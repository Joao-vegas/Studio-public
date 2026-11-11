# aperta as pausas da narração: silêncio > 0,33 s vira 0,22 s (0,10 depois da fala + 0,12 antes da próxima)
import subprocess, re, sys, numpy as np, json
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
sr = 48000
x = np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",str(src),"-f","f32le","-ac","1","-ar",str(sr),"-"],capture_output=True,check=True).stdout, np.float32)
log = subprocess.run(["ffmpeg","-i",str(src),"-af","silencedetect=noise=-40dB:d=0.12","-f","null","-"],capture_output=True,text=True).stderr
ini = [float(v) for v in re.findall(r"silence_start: ([0-9.]+)", log)]; fim = [float(v) for v in re.findall(r"silence_end: ([0-9.]+)", log)]
cortes = []
for a, b in zip(ini, fim):
    if a <= 0.01: cortes.append((0, max(0, b - .06))); continue
    if b - a > .33: cortes.append((a + .10, b - .12))
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
