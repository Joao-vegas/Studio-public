"""O "Aprendi:" do feedback (ferramentas/aprendi.py): OK grava a regra, "Não é isso" reescreve ou troca a camada."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import flash, redirect, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import aprendi as _ap  # noqa: E402


def _volta(rec=None):
    v = request.form.get("volta", "")
    if v.startswith("/") and not v.startswith("//"):
        return redirect(v)
    if rec and rec.get("cliente") and rec.get("slug"):
        return redirect(url_for("andamento_ver", cli=rec["cliente"], slug=rec["slug"]))
    return redirect("/aprovar")


def register(app):
    app.add_template_global(_ap.pendentes, name="aprendi_pendentes")
    app.add_template_global(_ap.frase, name="aprendi_frase")

    @app.post("/aprendi/<id_>/ok")
    def aprendi_ok(id_):
        rec = _ap.carregar(id_)
        try:
            rec = _ap.confirmar(id_)
            g = rec["gravada"]
            flash(("✓ Guardei a regra (" if g["acao"] == "criada" else "✓ Reescrevi a regra que já existia (")
                  + f"{g['id']}, {_ap.ROTULO[rec['camada']]}). " + (g.get("aviso") or "").capitalize())
        except ValueError as e:
            flash("✗ " + str(e))
        return _volta(rec)

    @app.post("/aprendi/<id_>/ajustar")
    def aprendi_ajustar(id_):
        rec = _ap.carregar(id_)
        try:
            rec = _ap.ajustar(id_, request.form.get("regra"), request.form.get("camada"))
            if request.form.get("guardar") == "1":
                rec = _ap.confirmar(id_)
                flash(f"✓ Guardei do seu jeito ({_ap.ROTULO[rec['camada']]}).")
            else:
                flash("✓ Ajustei. Confira e clique em OK.")
        except ValueError as e:
            flash("✗ " + str(e))
        return _volta(rec)

    @app.post("/aprendi/<id_>/descartar")
    def aprendi_descartar(id_):
        rec = _ap.carregar(id_)
        try:
            _ap.descartar(id_)
            flash("✓ Não virou regra. Ficou só no histórico.")
        except ValueError as e:
            flash("✗ " + str(e))
        return _volta(rec)
