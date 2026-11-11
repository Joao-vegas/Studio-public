# Clipe real (rua, torcida, comício, podcast) pro Editorial: baixa só o trecho, corta em 9:16 a 30 fps e tira o som.
#   python3 clipe.py busca "<consulta>" [N] [--fontes youtube,archive,nasa,commons,pexels,pixabay]
#                                                                -> lista N candidatos por fonte (título, duração, licença, link), sem baixar.
#                                                                   YouTube pelo get-brolls (filtra banco pago com marca d'água); as outras pelo
#                                                                   app/ferramentas/fontes_gratis.py (Internet Archive = domínio público/CC, NASA, Commons)
#   python3 clipe.py baixa <sandbox> <nome> <url> <ini_s> <dur_s> -> clipes/q-<nome>/0001.jpg... + clipes/som-<nome>.mp3 + clipes/origem.json
# O `baixa` aceita link de qualquer fonte da busca e grava clipes/folha-<nome>.jpg (6 quadros): OLHE antes de usar.
# Cada clipe entra UMA vez no vídeo (render.py checar_repeticao): use nomes diferentes e busque outro. Depois olhe a folha:
#   python3 app/ferramentas/folha.py clipes/q-<nome>/ ... ou abra 3 quadros. Sem marca d'água, sem legenda queimada, rosto certo.
import json, subprocess, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
FONTES_PADRAO = "youtube,archive,nasa,commons"

def busca(q: str, n: int = 6, fontes: str = FONTES_PADRAO):
    sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
    for f in [x for x in fontes.split(",") if x]:
        try:
            if f == "youtube":
                try:
                    import getbrolls as gb      # get-brolls: mesma busca da tela, já sem banco pago com marca d'água
                    itens = [(i.get("title", ""), (i.get("media") or {}).get("duration_s") or 0, "ver o canal", i.get("source_url", ""))
                             for i in (gb.buscar("youtube", q, n).get("items") or [])]
                except Exception:
                    itens = []
                    r = subprocess.run(["yt-dlp", "--flat-playlist", "-j", f"ytsearch{n}:{q}"], capture_output=True, text=True, timeout=120)
                    for l in r.stdout.splitlines():
                        try:
                            d = json.loads(l)
                        except ValueError:
                            continue
                        itens.append((d.get("title", ""), d.get("duration") or 0, "ver o canal", d.get("url") or "https://youtu.be/" + d.get("id", "")))
            else:
                import fontes_gratis as fg
                itens = [(i["titulo"], i.get("duracao") or 0, i["licenca"], i["arquivo_url"]) for i in fg.buscar_videos(q, [f], n)[0]]
        except Exception as e:
            print(f"[{f}] sem resposta: {str(e)[:80]}"); continue
        for t, dur, lic, url in itens:
            print(f"[{f}] {float(dur or 0):>6.0f}s  {lic[:22]:<22}  {t[:70]}  {url}")

def baixa(sb: Path, nome: str, url: str, ini: float, dur: float):
    pasta = sb / "clipes"; q = pasta / f"q-{nome}"
    if q.is_dir() and any(q.glob("*.jpg")):
        print("já existe:", q); return
    pasta.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        bruto = Path(tmp) / "c.%(ext)s"
        r = subprocess.run(["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--download-sections", f"*{ini}-{ini + dur}", "--force-keyframes-at-cuts",
                            "--merge-output-format", "mp4", "-o", str(bruto), "--no-simulate", "--print", "title", url], capture_output=True, text=True, timeout=600)
        achou = list(Path(tmp).glob("c.*"))
        if not achou:
            raise SystemExit("yt-dlp não baixou: " + (r.stderr or r.stdout)[-300:])
        titulo = (r.stdout.strip().splitlines() or [""])[0]
        arq = achou[0]; q.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(arq), "-vf", "crop=ih*9/16:ih,scale=1080:1920,fps=30", "-q:v", "3", str(q / "%04d.jpg")], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(arq), "-vn", "-ac", "2", "-ar", "44100", "-b:a", "128k", str(pasta / f"som-{nome}.mp3")], check=False)   # clipe sem áudio (Pexels/Pixabay) não derruba: fica sem o mp3
    try:   # folha de 6 quadros: o "olhar antes de usar" da skill broll
        from PIL import Image
        qs = sorted(q.glob("*.jpg")); pick = [qs[int(i * (len(qs) - 1) / 5)] for i in range(6)] if len(qs) >= 6 else qs
        folha = Image.new("RGB", (6 * 180, 320))
        for k, f in enumerate(pick):
            folha.paste(Image.open(f).resize((180, 320)), (k * 180, 0))
        folha.save(pasta / f"folha-{nome}.jpg", quality=85)
        print(f"folha: {pasta / f'folha-{nome}.jpg'} (olhe: marca d'água, legenda queimada, rosto certo)")
    except Exception:
        pass
    org = pasta / "origem.json"
    d = json.loads(org.read_text()) if org.exists() else {}
    d[nome] = {"url": url, "titulo": titulo, "inicio_s": ini, "dur_s": dur}
    org.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    print(f"{nome}: {len(list(q.glob('*.jpg')))} quadros · {titulo[:60]}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["busca"] and len(a) >= 2:
        fontes = a[a.index("--fontes") + 1] if "--fontes" in a else FONTES_PADRAO
        num = [x for x in a[2:] if x.isdigit()]
        busca(a[1], int(num[0]) if num else 6, fontes)
    elif a[:1] == ["baixa"] and len(a) == 6:
        baixa(Path(a[1]), a[2], a[3], float(a[4]), float(a[5]))
    else:
        raise SystemExit(__doc__)
