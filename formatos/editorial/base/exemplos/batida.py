# mede a grade da música pra cortar na batida: grava <saida> (padrão work/batida.json) com {"periodo": s entre batidas,
# "primeiro": s (no arquivo) da 1ª batida forte}. Uso: python3 batida.py <musica.mp3> [work/batida.json]
# (sem librosa: envoltória de energia de graves/médios + autocorrelação; período confere com o do grupo-por-crenca: 0,6855)
import json, subprocess, sys
from pathlib import Path
import numpy as np

src = Path(sys.argv[1]); dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("work/batida.json")
SR = 22050; HOP = 256
x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                                 capture_output=True, check=True).stdout, np.float32)
# energia por janela (graves pesam mais: o kick é o que o corte persegue), derivada positiva = ataque
n = (len(x) - 1024) // HOP
w = np.hanning(1024)
esp = np.array([np.abs(np.fft.rfft(x[i * HOP:i * HOP + 1024] * w))[:60] for i in range(n)])   # ~0-1,3 kHz
env = np.log1p(esp * 20).sum(1)
ataque = np.maximum(0, np.diff(env, prepend=env[0]))
ataque = ataque - np.convolve(ataque, np.ones(43) / 43, "same")
ataque[ataque < 0] = 0
fps = SR / HOP
# período: autocorrelação entre 60 e 180 BPM
ac = np.correlate(ataque, ataque, "full")[len(ataque) - 1:]
lo, hi = int(fps * 60 / 180), int(fps * 60 / 60)
k = lo + int(np.argmax(ac[lo:hi]))
# refina com parábola
if 0 < k < len(ac) - 1:
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    k = k + .5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else k
periodo = k / fps
# a grade: a fase que mais ataque junta; o "drop" é o 1º salto grande de energia (intro baixa -> beat cheio) nos primeiros 60 s,
# e "primeiro" é a batida da grade mais perto dele (o vídeo começa 0,15 s antes dela: o drop cai no 1º quadro)
ini = int(2 * fps)
melhor, mf = -1, 0
for f in np.arange(0, int(periodo * fps)):
    idx = np.round(ini + f + np.arange(0, (n - ini - f) / (periodo * fps)) * periodo * fps).astype(int)
    idx = idx[idx < n]
    sm = ataque[idx].sum()
    if sm > melhor: melhor, mf = sm, f
grade = (ini + mf + np.arange(0, (n - ini - mf) / (periodo * fps)) * periodo * fps) / fps
h = int(SR * .01)
rms = np.array([np.sqrt((x[i:i + 2 * h] ** 2).mean()) for i in range(0, min(len(x), SR * 60) - 2 * h, h)])
drop = None
for i in range(300, len(rms)):
    antes = np.median(rms[i - 300:i - 5])
    if rms[i] > max(5 * antes, .25 * rms.max()) and rms[i:i + 100].mean() > 3 * antes:
        drop = i * .01; break
if drop is None:   # sem drop claro (faixa sem intro): a 1ª batida forte da grade
    forte = [g for g in grade if ataque[min(int(g * fps), n - 1)] > .6 * np.percentile(ataque, 99)]
    primeiro = float(forte[0] if forte else grade[0])
else:
    primeiro = float(grade[int(np.argmin(np.abs(grade - drop)))])
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps({"periodo": round(periodo, 4), "primeiro": round(primeiro, 3), "bpm": round(60 / periodo, 1), "drop": None if drop is None else round(float(drop), 2)}))
print(f"batida: {60 / periodo:.1f} BPM (período {periodo:.4f} s), drop em {'nenhum' if drop is None else round(float(drop), 2)} s -> batida de referência em {primeiro:.3f} s -> {dst}")
