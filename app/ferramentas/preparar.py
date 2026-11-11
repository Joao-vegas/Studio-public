"""Deixa pronto, em segundo plano, o que a tela vai pedir: a capa do vídeo e as miniaturas das cenas (30-out-2026).

Sem isto, a 1ª abertura da lista pagava 5 ffmpeg por vídeo (capa) e ~10 s de render (miniaturas). Agora o vídeo pronto (fim do
render, `andamento.pronto`) e a edição entregue (`editor.entregar`) chamam `depois(...)`: uma thread de fundo faz a conta, a tela
já abre com tudo. Quem pede antes de ficar pronto recebe "preparando…" (`pronto()` False) em vez de travar.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

_fazendo: set[str] = set()
_trava = threading.Lock()


def fazendo(chave: str) -> bool:
    with _trava:
        return chave in _fazendo


def _capa_pronta(video: Path) -> bool:
    import _comum
    import re
    key = re.sub(r"[^a-zA-Z0-9]+", "_", _comum.rel(video))[-150:]
    d = _comum.CACHE / "thumbs" / f"{key}-capa.jpg"
    return d.exists() and d.stat().st_mtime >= Path(video).stat().st_mtime


def capa_pronta(video: Path) -> bool:
    try:
        return _capa_pronta(Path(video))
    except OSError:
        return False


def _tarefa(chave: str, fn) -> bool:
    """Roda `fn` numa thread, uma vez por chave de cada vez. False se já estava rodando."""
    with _trava:
        if chave in _fazendo:
            return False
        _fazendo.add(chave)

    def _vai():
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — preparar nunca derruba nada
            print(f"(preparar {chave}: {e})", file=sys.stderr)
        finally:
            with _trava:
                _fazendo.discard(chave)
    threading.Thread(target=_vai, daemon=True, name="preparar").start()
    return True


def capa(video: Path) -> bool:
    """Gera a capa do vídeo (thumb_cache) em segundo plano."""
    import _comum
    video = Path(video)
    if not video.is_file() or capa_pronta(video):
        return False
    return _tarefa("capa:" + str(video), lambda: _comum.thumb_cache(video))


def miniaturas(pasta: Path) -> bool:
    """Gera as miniaturas de cenas do editor (editor.miniaturas) em segundo plano."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return False

    def _f():
        import editor
        editor.miniaturas(pasta)
    return _tarefa("mini:" + str(pasta), _f)


def depois(video: Path | str | None = None, pasta: Path | str | None = None) -> None:
    """Chamado quando o vídeo fica pronto ou é editado: capa e (se for pasta de edição por cena) miniaturas."""
    try:
        if video:
            capa(Path(video) if Path(video).is_absolute() else _raiz() / video)
        if pasta:
            p = Path(pasta) if Path(pasta).is_absolute() else _raiz() / pasta
            import editor
            if (p / "cenas.json").is_file() or not editor.motivo_sem_edicao(p):
                miniaturas(p)
    except Exception as e:  # noqa: BLE001
        print(f"(preparar: {e})", file=sys.stderr)


def _raiz() -> Path:
    import _comum
    return _comum.RAIZ
