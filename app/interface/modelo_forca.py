"""Modelo + esforço num componente só (Novo vídeo, Editar vídeo, Configurações): o modelo é quem pensa, o esforço é quanto ele pensa
antes de agir. A tela chama `modelo_forca_dados(gpt=True)` (Jinja) e o macro `_modelo_forca.html` desenha os cartões e o deslizante.
Valores que vão no POST: modelo = apelido do Claude ('opus' | 'sonnet' | 'haiku') ou 'gpt:<id>' (só se o Codex existir); esforço = low…max."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))

# nome em inglês (o que o Claude/Codex entendem) em cima, português embaixo
NIVEIS = [
    ("low", "Rápido", "O mais rápido e barato. Bom pra testar uma ideia."),
    ("medium", "Bom", "Equilíbrio entre qualidade e velocidade."),
    ("high", "Forte", "Pensa mais em cada cena. O ponto certo pra quase todo vídeo."),
    ("xhigh", "Muito forte", "Cuidado extra em cada cena. Bem mais lento."),
    ("max", "Ultra", "Pensa o máximo. Só pra vídeo importante: demora e gasta mais do seu limite."),
]
ORDEM = [n[0] for n in NIVEIS]
PADRAO_MODELO, PADRAO_ESFORCO = "sonnet", "high"


def dados(gpt: bool = True) -> dict:
    """{modelos: [{v, nome, serve, custo, esforcos:[...]}], niveis: [{v, pt, desc}], gpt: bool}."""
    import ia
    ms = [{"v": m["apelido"], "nome": "Claude " + ia.nome_claude(m["apelido"]), "serve": m["serve"], "custo": m["custo"],
           "esforcos": list(ORDEM), "marca": "claude"} for m in ia.MODELOS_CLAUDE]
    tem_gpt = False
    if gpt and ia.codex_bin():
        cfg = ia.config()
        atual = cfg.get("modelo_gpt") or ""
        cat = ia.catalogo()
        m = next((x for x in cat if x["id"] == atual), None) or next((x for x in cat if x.get("visivel")), None)
        niveis = [e for e in ORDEM if e in (m or {}).get("esforcos", [])] or ["low", "medium", "high"]
        ms.append({"v": "gpt:" + atual, "nome": "GPT pelo Codex", "serve": (m or {}).get("nome") or "Modelo padrão da sua conta",
                   "custo": "", "esforcos": niveis, "marca": "gpt"})
        tem_gpt = True
    return {"modelos": ms, "niveis": [{"v": v, "pt": pt, "desc": d} for v, pt, d in NIVEIS], "gpt": tem_gpt,
            "padrao": {"modelo": PADRAO_MODELO, "esforco": PADRAO_ESFORCO}}


def register(app):
    app.jinja_env.globals["modelo_forca_dados"] = dados
