"""Tela Vozes (PLANO-2.0, item 16): todas as vozes do VoiceStudio com prévia em português, quem usa cada uma, e criar
voz nova de graça (desenhar ou clonar). A lógica fica em app/ferramentas/vozes.py."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from flask import jsonify, render_template, request, send_file

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import emocao as _em  # noqa: E402
import voicestudio  # noqa: E402
import emocao_joao as _ej  # noqa: E402
import vozes as _vz  # noqa: E402
from _comum import RAIZ  # noqa: E402


def _emocoes_ui() -> list[dict]:
    try:
        return _em.painel(_vz.lista())
    except Exception:  # noqa: BLE001
        return []


def _comparacao() -> list[dict]:
    """Pares de mp3 da comparação de motores (app/.cache/vozes-comparacao/<nome>-<motor>.mp3)."""
    pasta = _em.ESTUDIO / ".cache" / "vozes-comparacao"
    return [{"nome": f.stem, "url": f"/vozes/comparacao/{f.name}"} for f in sorted(pasta.glob("*.mp3"))] if pasta.is_dir() else []


def register(app):
    @app.get("/api/voz/estado")
    def api_voz_estado():
        """Situação da voz pra tela: no_ar · ligando · ocupado · fora (com pode_ligar) · instalar."""
        r = jsonify(**voicestudio.estado())
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.post("/api/voz/ligar")
    def api_voz_ligar():
        """Botão "Ligar a voz" (e a abertura da tela Vozes): sobe o backend sem janela e devolve já o estado."""
        return jsonify(**voicestudio.ligar_em_segundo_plano())

    @app.get("/vozes")
    def vozes_lista():
        clientes = sorted(p.parent.name for p in (RAIZ / "clientes").glob("*/identidade.json"))
        return render_template("vozes.html", cartoes=_vz.cartoes(), arquetipos=_vz.cartoes_arquetipos(), rotulos_tags=_vz.ROTULOS_TAGS,
                               motor=_vz.motor(), no_ar=voicestudio.no_ar(), voz_estado=voicestudio.estado(),
                               clientes=clientes, prontas=_vz.PRONTAS, generos=list(_vz.GENEROS), idades=list(_vz.IDADES),
                               tons=list(_vz.TONS), frase=_vz.FRASE_PT, emocoes_ui=_emocoes_ui(), comparacao=_comparacao(),
                               emo_rotulos=_em.ROTULOS, texto_gravar=_ej.TEXTO_GRAVAR)

    @app.get("/vozes/previa")
    def vozes_previa():
        try:
            f = _vz.previa_de(request.args.get("id", "default"))
        except Exception as e:  # noqa: BLE001
            return jsonify(erro=voicestudio.explicar(e)), 503
        r = send_file(f, mimetype="audio/mpeg")
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.get("/api/vozes")
    def api_vozes():
        return jsonify(vozes=[{"id": c["id"], "nome": c["nome"], "descricao": c["descricao"]} for c in _vz.cartoes()])

    @app.post("/vozes/arquetipo")
    def vozes_arquetipo():
        """Escolher um arquétipo do VoiceStudio: cria (na 1ª vez) o perfil fixo dele em português e devolve o id do perfil."""
        try:
            voicestudio.garantir_no_ar(60)
            return jsonify(ok=True, id=_vz.perfil_do_arquetipo(request.form.get("id", "")))
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=voicestudio.explicar(e)), 503

    def _resp(fn):
        try:
            voicestudio.garantir_no_ar(60)       # fora do ar: liga a voz sem janela antes
            return jsonify(ok=True, id=fn())
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=voicestudio.explicar(e)), 400

    @app.post("/vozes/desenhar")
    def vozes_desenhar():
        f = request.form
        return _resp(lambda: _vz.desenhar(f.get("nome", ""), f.get("genero", ""), f.get("idade", ""), f.get("tom", "")))

    @app.post("/vozes/clonar")
    def vozes_clonar():
        up = request.files.get("audio")
        if not up or not up.filename:
            return jsonify(ok=False, erro="Escolha a gravação."), 400
        d = Path(tempfile.mkdtemp())
        alvo = d / ("ref" + Path(up.filename).suffix.lower())
        up.save(alvo)
        return _resp(lambda: _vz.clonar(request.form.get("nome", ""), alvo))

    @app.post("/vozes/usar")
    def vozes_usar():
        f = request.form
        vid = f.get("id", "")
        if vid.startswith("arq:"):
            return _resp(lambda: (lambda pid: (_vz.usar(pid, f.get("cliente", "")), pid)[1])(_vz.perfil_do_arquetipo(vid)))
        return _resp(lambda: (_vz.usar(vid, f.get("cliente", "")), vid)[1])
