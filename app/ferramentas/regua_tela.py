"""regua_tela — o resumo do estudo quadro a quadro pra TELA (referência rápida, estudar, conjunto): os números que o João
lê (planos, cortes por minuto, câmera, música, palavras por minuto, legenda), as regras com o quadro de prova e as folhas."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ler_json, rel  # noqa: E402

DESTAQUES = [   # (chave em estudo.json → conjunto, rótulo curto)
    ("planos.por_min", "Cortes por minuto"), ("planos.mediana_s", "Plano (mediana)"),
    ("camera.pct_quadros_andando", "Câmera andando"), ("transicao_resumo.dissolve_pct", "Dissolve"),
    ("fala.ppm", "Palavras por minuto"), ("fala.voz_pct", "Voz no tempo"),
    ("som.lufs", "Volume"), ("som.musica_abaixo_da_voz_db", "Música abaixo da voz"), ("som.efeitos_por_min", "Efeitos por minuto"),
    ("legenda.y_pct", "Legenda: altura"), ("legenda.palavras_por_quadro", "Legenda: palavras"),
    ("numeros_resumo.por_min", "Números falados por minuto"),
]


def _fmt(v) -> str:
    if isinstance(v, float):
        return (f"{v:.1f}" if abs(v) < 100 else f"{v:.0f}").replace(".", ",")
    return str(v)


def resumo(pasta_estudo: Path | str) -> dict:
    """pasta_estudo = a pasta que tem estudo.json (…/quadros ou …/estudo-quadros). {} se ainda não existe."""
    d = Path(pasta_estudo)
    est = ler_json(d / "estudo.json", None)
    if not est:
        return {}
    conj = est.get("conjunto") or {}
    cards = []
    for chave, rot in DESTAQUES:
        m = conj.get(chave)
        if isinstance(m, dict) and m.get("mediana") is not None:
            v = _fmt(m["mediana"]) + (" " + m["unidade"] if m.get("unidade") and not str(m["unidade"]).startswith(("%", "/")) else m.get("unidade", ""))
            if m.get("n", 1) > 1 and m.get("min") != m.get("max"):
                v += f" ({_fmt(m['min'])} a {_fmt(m['max'])})"
            cards.append({"rotulo": rot, "valor": v})
    vids = est.get("videos") or []
    folhas = []
    for v in vids:
        for f in v.get("folhas") or []:
            p = d / f["arquivo"]
            if p.is_file():
                folhas.append({"rel": rel(p), "tipo": f.get("tipo", ""), "video": v.get("nome", "")})
    base = conj.get("base_sugerida")
    base = base.get("base") if isinstance(base, dict) else base
    return {"n_videos": len(vids), "duracao_s": round(sum(v.get("duracao", 0) for v in vids), 1), "cards": cards,
            "regras": [{"titulo": r.get("titulo", ""), "texto": r.get("texto", ""), "prova": r.get("prova", "")} for r in est.get("regras") or []],
            "folhas": folhas[:18], "n_folhas": len(folhas), "base": base or ""}
