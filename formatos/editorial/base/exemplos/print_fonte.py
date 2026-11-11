# Print de página de fonte confiável pro Editorial (matéria, estudo, notícia): prints/<nome>.png + a origem em prints/origem.json.
#   python3 print_fonte.py <sandbox> <nome> <url> [--rolar PX] [--clicar "texto"]
# Recusa Wikipédia e site duvidoso (REGRAS.md G25). Quando a fala cita um estudo ou dado, a cena "print" leva
# "grifos": [{"frase": "<trecho exato que aparece no print>", "t": <s>}] e o render acha a linha pelo OCR (lupa).
import argparse, json, sys
from pathlib import Path

PROIBIDO = ("wikipedia", "wikimedia.org/wiki", "metropoles", "fofoca", "purepeople", "extra.globo.com/famosos", "quora", "pinterest", "reddit")

ap = argparse.ArgumentParser()
ap.add_argument("sandbox", type=Path); ap.add_argument("nome"); ap.add_argument("url")
ap.add_argument("--rolar", type=int, default=0, help="rola N px antes do print (pula o cabeçalho)")
ap.add_argument("--clicar", default="", help="texto de um botão pra clicar antes (aceitar cookies)")
a = ap.parse_args()
if any(b in a.url.lower() for b in PROIBIDO):
    raise SystemExit(f"Fonte recusada ({a.url}): use matéria de CNN, NYT, Estadão, Globo/G1, Folha, BBC, Reuters, revista científica...")
from playwright.sync_api import sync_playwright
pasta = a.sandbox / "prints"; pasta.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1500}, device_scale_factor=1,
                                              user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36")
    pg.goto(a.url, wait_until="domcontentloaded", timeout=45000); pg.wait_for_timeout(2500)
    for t in ([a.clicar] if a.clicar else []) + ["Aceitar", "Accept", "Concordo", "Aceito", "OK", "Entendi"]:
        try:
            pg.get_by_role("button", name=t).first.click(timeout=700); break
        except Exception:
            pass
    if a.rolar: pg.mouse.wheel(0, a.rolar); pg.wait_for_timeout(600)
    pg.screenshot(path=str(pasta / f"{a.nome}.png")); titulo = pg.title(); b.close()
org = pasta / "origem.json"
d = json.loads(org.read_text()) if org.exists() else {}
d[f"{a.nome}.png"] = {"pagina": a.url, "titulo": titulo}
org.write_text(json.dumps(d, ensure_ascii=False, indent=1))
print(f"prints/{a.nome}.png · {titulo[:70]}")
