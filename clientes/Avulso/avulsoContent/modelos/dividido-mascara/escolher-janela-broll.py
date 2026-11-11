import subprocess, sys, os, numpy as np
from PIL import Image
FPS=5; W=160
def frames(path):
    d=f"/tmp/est_{os.path.basename(path)}"; os.makedirs(d,exist_ok=True)
    subprocess.run(["ffmpeg","-i",path,"-vf",f"fps={FPS},scale={W}:-1,format=gray","-y",f"{d}/f%04d.png","-loglevel","error"],check=True)
    fs=sorted(os.listdir(d))
    return [np.asarray(Image.open(f"{d}/{x}"),dtype=np.float32) for x in fs]
def score(path, win=4.5):
    a=frames(path)
    diffs=np.array([np.abs(a[i+1]-a[i]).mean() for i in range(len(a)-1)])
    n=int(win*FPS)
    best=[]
    for s in range(0,len(diffs)-n):
        w=diffs[s:s+n]
        if w.max()>28: continue          # corte de cena
        best.append((w.mean()+w.max()*0.3, s/FPS, w.mean(), w.max()))
    best.sort()
    print(f"\n== {os.path.basename(path)}")
    for sc,t,m,mx in best[:4]:
        print(f"   t={t:5.1f}s  mov={m:5.1f} pico={mx:5.1f}")
    if not best: print("   (só cortes/movimento forte)")
for p in sys.argv[1:]: score(p)
