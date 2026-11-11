"""Resumo curto das regras de um vídeo (formato + modelo do cliente + cores), pra embutir no pedido à IA.

Em vez de a IA dar cat no COMO-FAZER.md, em todo o aprendizado/ e no regras.json do modelo a cada storyboard, o pedido
já leva o essencial: a frase do formato, os passos (opcional), as regras ativas no formato "título: instrução" (as de
mais peso primeiro, sem histórico, sem "cobre"/"desde") e as cores do clientes/<Nome>/identidade.json.

  python3 app/ferramentas/resumo_regras.py <formato> [<cliente> [<modelo>]]     imprime o resumo e o tamanho
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ler_json  # noqa: E402

ALVO_PALAVRAS = 3400   # o nível 2 agora guarda título + medidas + evitar, então o alvo pode subir sem cortar o que importa


def _regras(p: Path) -> list[dict]:
    import formatos
    return formatos._regras_json(p) + (formatos._regras_md(p.with_name("regras.md")) if p.name == "regras.json" else [])


def _corta(txt: str, limite: int) -> str:
    if len(txt) <= limite:
        return txt
    frases = re.split(r"(?<=[.;!?])\s", txt)
    out = frases[0]
    for f in frases[1:]:
        if len(out) + len(f) + 1 > limite:
            break
        out += " " + f
    return (out if len(out) <= limite else out[:limite].rsplit(" ", 1)[0]) + " (…)"


def _linha(r: dict, nivel: int = 0) -> str:
    """nivel 0: regra inteira · 1: texto até ~320 letras e evitar até ~140 · 2: título + as medidas (números) + o "evitar"
    (o resto, com grep pelo id)."""
    txt = re.sub(r"\s+", " ", str(r.get("texto") or "")).strip()
    tit = (r.get("titulo") or "").strip()
    rid = f"[{r['id']}] " if r.get("id") else ""
    if nivel >= 2:
        medidas = list(dict.fromkeys(re.findall(r"-?\d[\d.,]*\s?(?:px|s\b|ms|%|LUFS|dB|vezes|x\b)?", txt)))[:8]
        ev = _corta(re.sub(r"\s+", " ", str(r.get("evitar") or "")).strip(), 100)
        return (f"- {rid}{tit or _corta(txt, 90)}" + (f" [medidas: {'; '.join(m.strip() for m in medidas)}]" if medidas else "")
                + (f" Evitar: {ev}" if ev else ""))
    if tit and txt.lower().startswith(tit.lower().rstrip("…")):
        tit = ""
    ev = re.sub(r"\s+", " ", str(r.get("evitar") or "")).strip()
    if nivel == 1:
        txt, ev = _corta(txt, 320), _corta(ev, 140)
    return f"- {rid}{tit + ': ' if tit else ''}{txt}" + (f" Evitar: {ev}" if ev else "")


def _raiz() -> Path:
    import formatos
    return getattr(formatos, "RAIZ", RAIZ)   # os testes trocam a raiz do formatos


def _reclamacoes(arquivos: list[Path], n: int = 5, limite: int = 120) -> list[str]:
    """Os n últimos `tipo: feedback` dos historico.jsonl (do mais antigo pro mais novo), com ~120 letras cada."""
    achados = []
    for a in arquivos:
        if not a.is_file():
            continue
        for linha in a.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(linha)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("tipo") == "feedback" and str(e.get("texto") or "").strip():
                achados.append((str(e.get("createdAt") or ""), re.sub(r"\s+", " ", str(e["texto"])).strip()))
    achados.sort(key=lambda x: x[0])
    vistos, out = set(), []
    for _, t in reversed(achados):
        if t not in vistos:
            vistos.add(t)
            out.append("- " + _corta(t, limite))
        if len(out) == n:
            break
    return out[::-1]


def _cores(cliente: str) -> str:
    d = ler_json(_raiz() / "clientes" / cliente / "identidade.json", {}) or {}
    if not d:
        return ""
    partes = []
    if d.get("papeis"):
        partes.append(", ".join(f"{k} {v}" for k, v in d["papeis"].items()))
    elif d.get("cores"):
        partes.append(", ".join(d["cores"]))
    if d.get("uso"):
        partes.append(str(d["uso"]))
    if d.get("fontes"):
        partes.append("Fontes: " + str(d["fontes"]))
    return f"CORES E FONTES DO CLIENTE (clientes/{cliente}/identidade.json): " + " ".join(partes)


def resumo(slug: str, cliente: str = "", modelo: str = "", com_passos: bool = True, alvo: int = ALVO_PALAVRAS) -> str:
    """Tenta inteiro; passou do alvo, encurta cada regra; ainda passou, as de menos peso viram só o título."""
    txt = ""
    for nivel in (0, 1, 2):
        txt = _resumo(slug, cliente, modelo, com_passos, nivel)
        if palavras(txt) <= alvo:
            break
    return txt


def _resumo(slug: str, cliente: str, modelo: str, com_passos: bool, nivel: int) -> str:
    import formatos
    f = formatos.carregar(slug)
    if not f:
        return ""
    out = [f"FORMATO {f.get('titulo') or slug}: {f.get('frase') or f.get('descricao') or ''}".rstrip(": ")]
    if com_passos:
        ps = formatos.passos(f)
        if ps:
            out.append("PASSOS: " + " → ".join(ps))
    apr = f["pasta"] / "aprendizado"
    do_formato = _regras(apr / "regras.json")
    if do_formato:
        out.append(f"REGRAS DO FORMATO (formatos/{slug}/aprendizado/regras.json, as de mais peso primeiro):")
        out += [_linha(r, min(nivel, 1) if i < 8 else nivel) for i, r in enumerate(do_formato)]
    if cliente and modelo:
        pm = _raiz() / "clientes" / cliente
        rj = next(iter(sorted(pm.glob(f"*Content/modelos/{modelo}/aprendizado/regras.json"))), None)
        do_cliente = _regras(rj) if rj else []
        if do_cliente:
            out.append(f"REGRAS DO CLIENTE NESTE MODELO ({rj.relative_to(_raiz())}; ganham das do formato):")
            out += [_linha(r, min(nivel, 1) if i < 8 else nivel) for i, r in enumerate(do_cliente)]
    recl = _reclamacoes([apr / "historico.jsonl"] + ([rj.parent / "historico.jsonl"] if cliente and modelo and rj else []))
    if recl:
        out.append("ÚLTIMAS RECLAMAÇÕES NESTE MODELO (não repetir):")
        out += recl
    cores = _cores(cliente) if cliente else ""
    if cores:
        out.append(cores)
    outros = sorted(p.name for p in apr.glob("*") if p.is_file() and p.name not in ("regras.json", "regras.md", "historico.jsonl", "titulos.json"))
    if outros:
        out.append(f"Mais detalhes (só se precisar, com grep na seção): formatos/{slug}/aprendizado/{{{','.join(outros)}}}.")
    return "\n".join(out)


def secoes(md: Path) -> str:
    """Os títulos (##) de um .md numa linha, pra IA abrir só a seção que precisa."""
    if not md.is_file():
        return ""
    return " · ".join(l.lstrip("#").strip() for l in md.read_text(encoding="utf-8").splitlines() if re.match(r"#{2,3} ", l))


def palavras(txt: str) -> int:
    return len(txt.split())


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    r = resumo(a[0], a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else "")
    print(r)
    print(f"\n({palavras(r)} palavras; alvo até {ALVO_PALAVRAS})", file=sys.stderr)
