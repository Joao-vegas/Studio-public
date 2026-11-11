"""Voz com emoção (PLANO-2.0, item 6): marcar a emoção de cada frase do roteiro (Criar e Editar vídeo), e na tela Vozes
ouvir e aprovar as variações por emoção de cada voz (e os trechos do João). A lógica fica em app/ferramentas/emocao.py e
emocao_joao.py."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from flask import jsonify, request, send_file

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import emocao as _em  # noqa: E402
import emocao_joao as _ej  # noqa: E402
import voicestudio  # noqa: E402
import vozes as _vz  # noqa: E402
from _comum import ESTUDIO  # noqa: E402

COMPARACAO = ESTUDIO / ".cache" / "vozes-comparacao"


def _nome(voz_id: str) -> str:
    return next((v["nome"] for v in _vz.lista() if v["id"] == voz_id), voz_id)


def register(app):
    @app.post("/api/emocoes/marcar")
    def api_emocoes_marcar():
        """O Claude (Sonnet, uma chamada leve) marca a emoção de cada frase do roteiro. Devolve [{texto, emocao}]."""
        d = request.get_json(silent=True) or {}
        roteiro = str(d.get("roteiro") or "").strip()
        if not roteiro:
            return jsonify(ok=False, erro="Escreva ou cole o roteiro primeiro."), 400
        return jsonify(ok=True, linhas=_em.marcar(roteiro), emocoes=[{"slug": k, "rotulo": _em.ROTULOS[k]} for k in _em.TODAS])

    def _resp(fn):
        try:
            voicestudio.garantir_no_ar(60)       # fora do ar: liga a voz sem janela antes
            return jsonify(ok=True, **(fn() or {}))
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, erro=voicestudio.explicar(e)), 400

    @app.post("/vozes/emocao/amostra")
    def vozes_emocao_amostra():
        f = request.form
        vid, emo = f.get("voz", ""), f.get("emocao", "")
        if emo not in _em.EMOCOES:
            return jsonify(ok=False, erro="Emoção desconhecida."), 400
        return _resp(lambda: (_em.gerar_amostra(vid, emo, _nome(vid)), {"emocao": emo})[1])

    @app.post("/vozes/emocao/aprovar")
    def vozes_emocao_aprovar():
        f = request.form
        return _resp(lambda: {"perfil": _em.aprovar(f.get("voz", ""), f.get("emocao", ""), _nome(f.get("voz", "")))})

    @app.post("/vozes/emocao/refazer")
    def vozes_emocao_refazer():
        f = request.form
        return _resp(lambda: (_em.recusar(f.get("voz", ""), f.get("emocao", ""), _nome(f.get("voz", ""))), {})[1])

    @app.get("/vozes/emocao/audio")
    def vozes_emocao_audio():
        """▶ da amostra de uma emoção (voz+emocao) ou de um trecho do João (cand=<id>)."""
        cand = request.args.get("cand", "")
        if cand:
            arq = _ej.SAIDA / (Path(cand).name + ".mp3")
        else:
            emo = request.args.get("emocao", "")
            if emo not in _em.EMOCOES:
                return jsonify(erro="Emoção desconhecida."), 404
            arq = _em.amostra_mp3(request.args.get("voz", ""), emo)
        if not arq.is_file():
            return jsonify(erro="Ainda não tem esse áudio."), 404
        r = send_file(arq, mimetype="audio/mpeg")
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.post("/vozes/emocao/procurar")
    def vozes_emocao_procurar():
        """Varre os brutos do João atrás de trechos com cada emoção (só propõe; nada é criado)."""
        return _resp(lambda: {"emocoes": {e: len(l) for e, l in _ej.procurar(log=lambda *_: None).items()}})

    @app.post("/vozes/emocao/usar")
    def vozes_emocao_usar():
        """O João ouviu o trecho e clicou 'Usar como João · <emoção>': só aqui nasce o perfil."""
        f = request.form
        return _resp(lambda: {"perfil": _ej.usar(f.get("emocao", ""), f.get("id", ""), f.get("voz") or _em.VOZ_JOAO)})

    @app.post("/vozes/emocao/gravacao")
    def vozes_emocao_gravacao():
        up = request.files.get("audio")
        if not up or not up.filename:
            return jsonify(ok=False, erro="Escolha a gravação."), 400
        d = Path(tempfile.mkdtemp())
        alvo = d / ("ref" + Path(up.filename).suffix.lower())
        up.save(alvo)
        return _resp(lambda: {"perfil": _ej.usar_gravacao(request.form.get("emocao", ""), alvo, request.form.get("voz") or _em.VOZ_JOAO)})

    @app.get("/vozes/comparacao/<nome>")
    def vozes_comparacao(nome):
        arq = COMPARACAO / Path(nome).name
        if not arq.is_file() or arq.suffix != ".mp3":
            return jsonify(erro="Sem esse áudio."), 404
        r = send_file(arq, mimetype="audio/mpeg")
        r.headers["Cache-Control"] = "no-store"
        return r
