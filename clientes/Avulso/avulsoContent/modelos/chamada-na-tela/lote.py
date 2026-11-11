"""Gera as configs das 20 combinações e renderiza (pula as já feitas)."""
import json, subprocess, sys
from pathlib import Path
AQUI = Path(__file__).parent
MASTER = AQUI.parent / "master"
MU = Path("/Users/joaomarcospiki/Projetos/Skill/Estúdio/clientes/Cliente1/cliente1Content/modelos/chamada-na-tela/assets/musica")
SAIDA = Path("/Users/joaomarcospiki/Projetos/Skill/Estúdio/clientes/Cliente1/cliente1Content/output/chamada-na-tela")
TITULOS = {
    "g01": ["ONDE O CLIENTE", "VAI PARAR?"], "g02": ["QUEM MAIS VENDE", "MAIS PERDE CLIENTE"],
    "g03": ["O CLIENTE NÃO VAI", "ENTRAR NA SUA FARMÁCIA"], "g04": ["BLACK EM FARMÁCIA", "VIROU BLACK FRAUD"],
    "g05": ["VAI RASGAR", "DESCONTO DE NOVO?"], "g06": ["BLACK PRA", "RASGAR DINHEIRO?"],
    "g07": ["VOCÊ JÁ VIU", "ESSA CENA?"], "g08": ["ATENDER BEM", "NÃO É VENDER"],
}
GANCHOS = ["bate", "brilho", "puxa", "luz", "sinal"]
cat = {m["id"]: m for m in json.load(open(MU / "catalogo.json"))}
MUSICAS = ["369", "876", "364", "260", "872", "1127"]
so = sys.argv[1:]
for j in sorted(MASTER.glob("[0-9][0-9]_combinacao_*.json")):
    nome = j.stem
    n = int(nome[:2])
    if (n - 1) % 4:   # chamada na tela = combinações 1, 5, 9, 13, 17 (as outras vão pros outros 3 modelos)
        continue
    k = (n - 1) // 4  # 0..4: cada uma começa com um gancho e uma legenda diferentes
    if so and nome[:2] not in so:
        continue
    g = nome.split("_")[2]
    mid = MUSICAS[k % len(MUSICAS)]
    cfg = {"video": str(MASTER / f"{nome}.mp4"), "words": str(j), "out": str(SAIDA / f"{nome}.mp4"),
           "titulo": TITULOS[g], "gancho": GANCHOS[k % len(GANCHOS)], "seed": n, "legenda": 1 + k % 2,
           "musica": str(MU / f"{mid}.mp3"), "musica_lufs": cat[mid]["lufs"],
           "destaques": ["estratégia", "fraud", "black", "farma", "lucrativa", "venda", "vender"]}
    (AQUI / "configs").mkdir(exist_ok=True)
    cp = AQUI / "configs" / f"{nome}.json"
    json.dump(cfg, open(cp, "w"), ensure_ascii=False, indent=1)
    if Path(cfg["out"]).exists() and not so:
        continue
    print("==", nome, cfg["gancho"], mid, flush=True)
    subprocess.run([sys.executable, str(AQUI / "tela.py"), str(cp)], check=True)
