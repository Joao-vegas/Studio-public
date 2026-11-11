"""frase_estilo — o que um vídeo de referência ensinou, em UMA frase simples pra tela (lista de Referências).
Os números (cortes por minuto, plano médio, legenda) ficam em "Ver detalhes"; aqui só a ideia."""
from __future__ import annotations


def ritmo(seg) -> str:
    """Segundos entre uma troca de imagem e outra → "corte rápido (troca a cada ~1 s)"."""
    try:
        s = float(seg)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    n = f"{s:.0f}" if s >= 3 else f"{s:.1f}".replace(".", ",")
    nome = "corte rápido" if s <= 1.5 else "ritmo médio" if s <= 3.5 else "ritmo calmo"
    return f"{nome} (troca a cada ~{n} s)"


def da_referencia(estilo: dict | None) -> str:
    """estilo.json da referência rápida → "Corte rápido (troca a cada ~2 s), legenda de 1 palavra por vez, com música." """
    e = estilo or {}
    partes = []
    r = ritmo((e.get("ritmo") or {}).get("corte_a_cada_s"))
    if r:
        partes.append(r)
    leg = e.get("legenda") or {}
    if isinstance(leg, dict) and leg:
        pv = leg.get("palavras_por_vez")
        partes.append(f"legenda de {pv} palavra{'s' if pv and int(pv) > 1 else ''} por vez" if pv else "sem legenda")
    som = e.get("som") or {}
    if isinstance(som, dict) and "musica" in som:
        partes.append("com música" if som.get("musica") else "sem música")
    if not partes:
        return ""
    txt = ", ".join(partes)
    return txt[0].upper() + txt[1:] + "."


def da_pasta(pasta) -> str:
    """Pasta de uma referência guardada (formatos/<estilo>/estudos/NN-nome): lê o estilo.json ou a régua e devolve a frase."""
    from pathlib import Path
    from _comum import ler_json
    d = Path(pasta)
    est = ler_json(d / "estilo.json", None)
    if est:
        return da_referencia(est)
    conj = (ler_json(d / "estudo-quadros" / "estudo.json", {}) or {}).get("conjunto") or {}
    med = (conj.get("planos.mediana_s") or {}).get("mediana")
    r = ritmo(med)
    cam = (conj.get("camera.pct_quadros_andando") or {}).get("mediana")
    partes = [r] if r else []
    if cam is not None:
        partes.append("câmera quase sempre andando" if cam >= 60 else "câmera se mexe em parte do tempo" if cam >= 25 else "câmera parada")
    if not partes:
        return ""
    t = ", ".join(partes)
    return t[0].upper() + t[1:] + "."
