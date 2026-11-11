#!/usr/bin/env python3
"""
recarregar — "Atualização pronta" vira um botão: o Estúdio reinicia o PRÓPRIO servidor, sem o João abrir terminal.

  pedir()   o clique em "Recarregar agora". Com algo rodando que o recarregar mataria, NÃO reinicia: marca o pedido e o vigia
            (vigiar(), um fio do servidor) reinicia sozinho quando acabar ("Recarrega sozinho quando o vídeo terminar").
  ocupado() o que o recarregar mataria: etapa na fila/rodando (a fila roda em processo próprio e sobrevive, mas o João não quer
            trocar o código no meio de uma produção) e os trabalhos que moram DENTRO do servidor (fio): entender referência,
            variações, estudo, pedido do editor, corte manual. Revisão e melhoria rodam em processo próprio e não contam.
  reiniciar() sai do processo: o launchd (com.joao.estudio, KeepAlive) sobe o servidor de novo com o código novo.
            Sem launchd, deixa um vigia solto que sobe um servidor novo se a porta ficar livre.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import agora, ler_json  # noqa: E402

ROTULO_LAUNCHD = "com.joao.estudio"
JANELA_FIO_H = 3          # estado "analisando/rodando" mais velho que isso = morreu junto com um servidor antigo; não segura


def _flag() -> Path:
    return _comum.ESTUDIO / ".recarregar-pendente"


def agendado() -> bool:
    return _flag().is_file()


def _recente(p: Path, horas: float = JANELA_FIO_H) -> bool:
    try:
        return time.time() - p.stat().st_mtime < horas * 3600
    except OSError:
        return False


def ocupado() -> list[str]:
    """Frases curtas do que está rodando e seria perdido. Lista vazia = pode recarregar."""
    out = []
    try:
        import fila
        n = [x for x in fila.ler() if x.get("estado") in ("na_fila", "rodando")]
        if n:
            out.append(f"{len(n)} etapa(s) de vídeo na fila ou rodando")
    except Exception:  # noqa: BLE001
        pass
    base = _comum.ESTUDIO
    achados = (
        ("referência sendo entendida", ".estilos/*/estado.json", lambda d: d.get("estado") == "analisando"),
        ("referências em conjunto sendo entendidas", ".estilos/_conjuntos/*/conjunto.json", lambda d: d.get("estado") == "analisando"),
        ("variações sendo montadas", ".variacoes/*/*.json", lambda d: d.get("estado") == "analisando"),
        ("estudo de vídeo rodando", ".estudos/*/estado.json", lambda d: bool(d.get("rodando"))),
    )
    for rot, padrao, teste in achados:
        for p in base.glob(padrao):
            d = ler_json(p, {}) or {}
            if isinstance(d, dict) and teste(d) and _recente(p):
                out.append(rot)
                break
    for p in _comum.RAIZ.glob("clientes/*/*/modelos/*/_sandbox*/editor/estado.json"):   # pedido do editor (Claude no meio da cena)
        d = ler_json(p, {}) or {}
        if isinstance(d, dict) and d.get("rodando") and _recente(p, 1):
            out.append("pedido do editor de vídeo rodando")
            break
    for p in base.glob("jobs/*/*/job.json"):   # corte manual roda em fio do servidor
        try:
            d = ler_json(p, {}) or {}
            if d.get("status") in ("analisando", "renderizando", "previas", "feedback", "rodando") and _recente(p, 6):
                import producao as P
                if P._vivo(p.parent / "runner.pid"):
                    out.append("vídeo sendo produzido")
                    break
        except Exception:  # noqa: BLE001
            continue
    return list(dict.fromkeys(out))


def gerenciado_pelo_launchd() -> bool:
    return os.environ.get("XPC_SERVICE_NAME") == ROTULO_LAUNCHD


def estado() -> dict:
    oc = ocupado()
    ag = ler_json(_flag(), {}) if agendado() else {}
    return {"ocupado": oc, "agendado": agendado(), "pedido_em": (ag or {}).get("em", "")}


def pedir() -> dict:
    """O clique do João. Livre: reinicia já. Ocupado: agenda e o vigia reinicia quando acabar."""
    oc = ocupado()
    if oc:
        _comum.gravar_json(_flag(), {"em": agora(), "motivo": oc})
        return {"ok": True, "recarregando": False, "agendado": True, "motivo": oc}
    _flag().unlink(missing_ok=True)
    agendar_saida()
    return {"ok": True, "recarregando": True, "agendado": False, "motivo": []}


def cancelar() -> None:
    _flag().unlink(missing_ok=True)


def agendar_saida(espera: float = 1.0) -> None:
    """Responde a página primeiro (1 s) e então sai. O launchd sobe a versão nova."""
    threading.Timer(espera, reiniciar).start()


def reiniciar() -> None:
    if not gerenciado_pelo_launchd():
        # sem launchd (iniciar.command): um vigia solto sobe o servidor novo quando a porta liberar
        py = _comum.ESTUDIO / ".venv" / "bin" / "python"
        servidor = _comum.ESTUDIO / "interface" / "servidor.py"
        logs = _comum.ensure(_comum.ESTUDIO / "servico" / "logs")
        cmd = f'sleep 3; lsof -tiTCP:7655 -sTCP:LISTEN >/dev/null || exec "{py if py.exists() else sys.executable}" "{servidor}"'
        with (logs / "manual.log").open("a") as f:
            subprocess.Popen(["/bin/sh", "-c", cmd], cwd=str(_comum.RAIZ), start_new_session=True, stdout=f, stderr=subprocess.STDOUT)
    os._exit(0)


def vigiar(intervalo: float = 10.0) -> None:
    """Fio do servidor: com pedido agendado, reinicia assim que não houver mais nada rodando."""
    while True:
        time.sleep(intervalo)
        try:
            if agendado() and not ocupado():
                _flag().unlink(missing_ok=True)
                reiniciar()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    import json
    print(json.dumps(estado(), ensure_ascii=False))
