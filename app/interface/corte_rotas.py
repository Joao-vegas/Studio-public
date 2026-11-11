"""Rotas do editor de corte: a forma de onda do vídeo (pra ver onde está a fala) e o botão "Corrigir o corte"."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import abort, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import corte_manual as _manual  # noqa: E402
from _comum import RAIZ, VIDEO_EXTS  # noqa: E402


def video_dentro(rel: str | None) -> Path | None:
    """O vídeo (relativo à raiz) se existe, está dentro do Estúdio e tem extensão de vídeo; senão None."""
    if not rel:
        return None
    p = (RAIZ / rel).resolve()
    if RAIZ.resolve() not in p.parents or p.suffix.lower() not in VIDEO_EXTS or not p.is_file():
        return None
    return p


def register(app):
    @app.get("/corte-manual/onda")
    def corte_onda():
        p = video_dentro(request.args.get("video"))
        if not p:
            abort(404)
        return jsonify({"por_segundo": 50, "picos": _manual.picos(p, 50)})

    def tem_bruto_video(cli, slug):
        """True se o vídeo tem um bruto gravado (aí o editor de corte faz sentido)."""
        try:
            import producao as _prod
            j = _prod.carregar(cli, slug)
        except Exception:
            return False
        return bool(j and j.get("bruto") and Path(j["bruto"]).suffix.lower() in VIDEO_EXTS)

    def tem_corte(cli, slug):
        """True se o vídeo passou por um corte (CORTE.json): só aí o "Corrigir o corte" faz sentido."""
        try:
            import producao as _prod
            j = _prod.carregar(cli, slug)
            if not (j and j.get("sandbox")):
                return False
            # Frase fixa copia o bruto direto pra work/joao.mp4 (sem CORTE.json): o editor também vale aí
            return bool(_prod.corte_json(j) or (RAIZ / j["sandbox"] / "work" / "joao.mp4").is_file())
        except Exception:
            return False

    def corte_mexido(cli, slug):
        """True se o corte (CORTE.json ou o bruto da camada) foi salvo DEPOIS de o vídeo ser gerado: só aí vale avisar que falta refazer."""
        try:
            import producao as _prod
            j = _prod.carregar(cli, slug)
            saida = RAIZ / (j.get("saida") or "")
            if not (j and j.get("sandbox") and saida.is_file()):
                return False
            work = RAIZ / j["sandbox"] / "work"
            return any(q.is_file() and q.stat().st_mtime > saida.stat().st_mtime + 1 for q in (work / "CORTE.json", work / "joao.mp4"))
        except Exception:
            return False

    def video_cortado(cli, slug):
        """O bruto já cortado (work/joao.mp4), relativo à raiz, ou "": o Em andamento mostra ele enquanto o storyboard não sai."""
        try:
            import producao as _prod
            j = _prod.carregar(cli, slug)
            q = RAIZ / j["sandbox"] / "work" / "joao.mp4" if j and j.get("sandbox") else None
            return str(q.relative_to(RAIZ)) if q and q.is_file() else ""
        except Exception:
            return ""

    def mtime(rel):
        """Versão do arquivo pra URL (?v=): o vídeo refeito no mesmo caminho não fica preso no cache do navegador."""
        try:
            return int((RAIZ / rel).stat().st_mtime)
        except Exception:
            return 0

    app.add_template_global(mtime)
    app.add_template_global(video_cortado)
    app.add_template_global(corte_mexido)
    app.add_template_global(tem_bruto_video)
    app.add_template_global(tem_corte)
