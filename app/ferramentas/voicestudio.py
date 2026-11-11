#!/usr/bin/env python3
"""
voicestudio — voz local e grátis (VoiceStudio, API compatível com a da OpenAI, porta 3900).

    python3 voicestudio.py falar "texto" --saida /tmp/v.mp3 [--voz default]
    python3 voicestudio.py vozes
    python3 voicestudio.py amostra <voz>

Lento (~8x o tempo real): o texto vai em blocos de ~800 caracteres e os áudios são colados com ffmpeg.
Sem rede de verdade: tudo é localhost.

UM VoiceStudio só: o aplicativo /Applications/VoiceStudio.app (Electron). Como ele sobe o backend (lido do app.asar, 29-out-2026):
  · porta 3900 (OMNIVOICE_PORT muda); backend = `<runtime>/project/.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1`,
    com <runtime> = ~/Library/Application Support/VoiceStudio/runtime (project/ tem backend, omnivoice, pyproject.toml, uv.lock e o .venv);
  · NÃO instala sozinho: no 1º uso fica em "setup_required" até clicar em Instalar na tela dele (baixa ~9 GB com o uv que vem no app:
    `uv sync --frozen --no-dev --managed-python --python 3.11`, depois grava .runtime-ready = sha256(schema+pyproject+uv.lock));
  · dados (perfis, vozes, omnivoice.db, outputs) ficam em ~/Library/Application Support/OmniVoice (OMNIVOICE_DATA_DIR só se mudar);
    a pasta VoiceStudio/ ao lado é só do Electron (cache, janela). Nunca apagar a OmniVoice/;
    (sem clicar na tela, o mesmo se repete por script: foi como a troca foi feita em 29-out-2026; depois disso o app sobe sozinho em ~10 s);
  · atualização: GitHub releases de debpalash/VoiceStudio (Resources/app-update.yml); o app tem o atualizador dele.
SEM JANELA (30-out-2026): o Estúdio NÃO abre mais o aplicativo. Se o 3900 não responder, `subir_sem_janela()` sobe só o backend
(Popen, sessão própria, log em ~/Library/Logs/voicestudio-sem-tela.log):
  cd <runtime>/project && OMNIVOICE_PORT=3900 .venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900
e espera o /health (até ~60 s). Fechar a janela do aplicativo não derruba a voz. `open -g -j -a VoiceStudio` só fica de plano B:
runtime sem `.runtime-ready` (nunca instalado: a tela diz "Abra o VoiceStudio uma vez pra instalar") ou backend sem janela que morre ao subir.
Medido em 30-out-2026: uvicorn parado ~60 MB (RSS); o motor (processo-filho) chega a ~2,6 GB só enquanto fala e se desfaz sozinho
depois de 5 min parado (SIDECAR_IDLE_TIMEOUT_S do próprio backend), então não precisa desligar o backend.
Abrir o aplicativo com o backend sem janela rodando: ele reaproveita o 3900 (não sobe outro) e fechar o aplicativo não mata o backend.
`estado()` diz a verdade pra tela Vozes: no_ar · ligando (503 "starting") · ocupado (Estúdio gerando agora, ou o 3900 não respondeu a tempo)
· fora (nada na porta) · instalar (runtime nunca instalado).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO

MAX_BLOCO = 800
FRASE_AMOSTRA = "Oi, essa é a voz que vai narrar o seu vídeo. Se gostou, é só escolher."
PASTA_AMOSTRAS = ESTUDIO / ".cache" / "vozes"


def url() -> str:
    return os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900").rstrip("/")


def _get(caminho: str, timeout: float = 5):
    with urllib.request.urlopen(url() + caminho, timeout=timeout) as r:
        return json.loads(r.read())


class VozOcupada(ValueError):
    """O backend está de pé mas gerando outra voz (503 com Retry-After ou sem responder a tempo)."""


class VozForaDoAr(ValueError):
    """Nada responde na porta da voz."""


MSG_OCUPADA = "Gerando outra voz, já volto."
MSG_LIGANDO = "Ligando a voz (uns 10 s)…"
MSG_FORA = "A voz está desligada."
MSG_INSTALAR = "Abra o VoiceStudio uma vez pra instalar a voz."

RUNTIME = Path(os.environ.get("VOICESTUDIO_RUNTIME") or Path.home() / "Library" / "Application Support" / "VoiceStudio" / "runtime")
LOG_SEM_TELA = Path(os.environ.get("VOICESTUDIO_LOG") or Path.home() / "Library" / "Logs" / "voicestudio-sem-tela.log")
EM_CURSO = ESTUDIO / ".cache" / "voz-em-curso"      # um arquivo por pedido de voz do Estúdio em andamento (pid-n)
APP = "VoiceStudio"
_ABRIU = {"quando": 0.0}
_SUBIU = {"quando": 0.0, "proc": None}
TESTANDO = {"forcar": False}   # rodando unittest, nunca abre o aplicativo de verdade (só o teste que simula o open)
_N = {"n": 0}


def _em_teste() -> bool:
    return "unittest" in sys.modules and not TESTANDO["forcar"]


def _health() -> str:
    """ok · ligando (503 starting) · ocupado (a porta atende mas não respondeu a tempo) · fora (nada na porta)."""
    try:
        with urllib.request.urlopen(url() + "/health", timeout=3) as r:
            return "ok" if json.loads(r.read()).get("status") == "ok" else "ligando"
    except urllib.error.HTTPError as e:
        e.close()
        return "ligando" if e.code == 503 else "fora"
    except (socket.timeout, TimeoutError):
        return "ocupado"
    except urllib.error.URLError as e:
        return "ocupado" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "fora"
    except Exception:  # noqa: BLE001
        return "fora"


def no_ar() -> bool:
    try:
        return _get("/health", 2).get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def _gerando_agora() -> bool:
    """Algum pedido de voz do Estúdio (esta tela, um vídeo em produção) está em andamento, ou o backend acabou de dizer
    que está ocupado (há menos de 60 s)?"""
    try:
        if time.time() - (EM_CURSO / "ocupada").stat().st_mtime < 60:
            return True
    except OSError:
        pass
    try:
        for f in EM_CURSO.glob("*-*"):
            pid = int(f.name.split("-")[0])
            try:
                os.kill(pid, 0)
                if time.time() - f.stat().st_mtime < 20 * 60:
                    return True
            except OSError:
                pass
    except (OSError, ValueError):
        pass
    return False


def runtime_pronto() -> bool:
    """O backend do VoiceStudio já foi instalado (o aplicativo grava .runtime-ready ao instalar)?"""
    p = RUNTIME / "project"
    return (p / ".runtime-ready").is_file() and (p / ".venv" / "bin" / "python").exists() and (p / "backend" / "main.py").is_file()


def _porta_local() -> str | None:
    """Porta do 3900 se a URL é desta máquina; senão None (URL apontando pra outro lugar: nunca sobe nada)."""
    from urllib.parse import urlparse
    u = urlparse(url())
    return str(u.port or 3900) if u.hostname in ("127.0.0.1", "localhost") else None


def estado() -> dict:
    """Pra tela Vozes: {estado: no_ar|ligando|ocupado|fora|instalar, texto, pode_ligar}."""
    h = _health()
    if h == "ok":
        if _gerando_agora():
            return {"estado": "ocupado", "texto": MSG_OCUPADA, "pode_ligar": False}
        return {"estado": "no_ar", "texto": "A voz está no ar.", "pode_ligar": False}
    if h == "ligando" or (_SUBIU["proc"] is not None and _SUBIU["proc"].poll() is None and time.time() - _SUBIU["quando"] < 90):
        return {"estado": "ligando", "texto": MSG_LIGANDO, "pode_ligar": False}
    if h == "ocupado":
        return {"estado": "ocupado", "texto": MSG_OCUPADA, "pode_ligar": False}
    if not runtime_pronto():
        return {"estado": "instalar", "texto": MSG_INSTALAR, "pode_ligar": False}
    return {"estado": "fora", "texto": MSG_FORA + _fim_do_log(), "pode_ligar": True}


def _fim_do_log() -> str:
    """Se o backend sem janela que ESTE processo lançou morreu, a última linha de erro do log (o motivo); senão vazio."""
    p = _SUBIU["proc"]
    if p is None or p.poll() is None:
        return ""
    try:
        linhas = [x.strip() for x in LOG_SEM_TELA.read_text(errors="replace").splitlines()[-30:]]
        uteis = [x for x in linhas if x and not x.startswith("INFO")]
        return " Motivo: " + uteis[-1][:160] if uteis else ""
    except OSError:
        return ""


def abrir_app() -> None:
    """Plano B: abre o aplicativo em segundo plano (sem roubar o foco). Não repete antes de 30 s."""
    if _em_teste() or time.time() - _ABRIU["quando"] < 30:
        return
    _ABRIU["quando"] = time.time()
    try:
        subprocess.run(["open", "-g", "-j", "-a", APP], capture_output=True, timeout=15)
    except Exception:  # noqa: BLE001
        pass


def subir_sem_janela() -> bool:
    """Sobe só o backend do VoiceStudio, sem janela, numa sessão própria (sobrevive ao Estúdio). True se lançou.
    Falso: runtime não instalado, URL de outra máquina, teste ou já lançado há menos de 90 s e ainda vivo."""
    porta = _porta_local()
    if _em_teste() or porta is None or not runtime_pronto():
        return False
    ant = _SUBIU["proc"]
    if ant is not None and ant.poll() is None and time.time() - _SUBIU["quando"] < 90:
        return True
    proj = RUNTIME / "project"
    try:
        LOG_SEM_TELA.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_SEM_TELA, "ab") as log:      # o filho herda o arquivo; o nosso descritor fecha aqui
            _SUBIU["proc"] = subprocess.Popen(
                [str(proj / ".venv" / "bin" / "python"), "-m", "uvicorn", "main:app", "--app-dir", "backend",
                 "--host", "127.0.0.1", "--port", porta],
                cwd=str(proj), env={**os.environ, "OMNIVOICE_PORT": porta}, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True)
        _SUBIU["quando"] = time.time()
        return True
    except OSError:
        return False


def garantir_no_ar(espera: float = 60) -> bool:
    """3900 respondendo? Senão sobe o backend sem janela e espera até `espera` s pelo /health.
    Runtime não instalado ou backend que morre ao subir: abre o aplicativo (plano B)."""
    if no_ar() or _em_teste():
        return no_ar()
    h = _health()
    if h == "ocupado":                     # a porta atende: está gerando, não é pra subir outro
        fim = time.time() + espera
        while time.time() < fim and not no_ar():
            time.sleep(2)
        return no_ar()
    if h != "ligando" and not subir_sem_janela():
        abrir_app()                        # plano B: nunca instalado (o João vê a janela e clica Instalar) ou URL de fora
        if not runtime_pronto():
            return False
    fim = time.time() + espera
    plano_b = False
    while time.time() < fim:
        if no_ar():
            return True
        p = _SUBIU["proc"]
        if not plano_b and p is not None and p.poll() is not None and not no_ar():   # morreu ao subir
            plano_b = True
            abrir_app()
        time.sleep(2)
    return no_ar()


def explicar(erro: Exception) -> str:
    """Texto pra tela quando um pedido de voz falhou: ocupado, ligando, desligada ou instalar; senão a mensagem do erro."""
    if isinstance(erro, VozOcupada):
        return MSG_OCUPADA
    e = estado()
    if e["estado"] in ("ocupado", "ligando", "instalar", "fora"):
        return e["texto"]
    return str(erro)


def ligar_em_segundo_plano() -> dict:
    """Botão "Ligar a voz": lança o backend sem janela (instantâneo) e devolve o estado; a tela consulta de novo a cada 2 s."""
    if estado()["estado"] == "fora":
        subir_sem_janela()
    return estado()


def vozes() -> list[dict]:
    """[{id, rotulo, idioma, tipo}] — perfis primeiro, depois a voz padrão. Fora do ar: liga a voz sem janela (espera até 8 s); não subiu, lista vazia."""
    out: list[dict] = []
    garantir_no_ar(8)
    try:
        for p in _get("/profiles") or []:
            out.append({"id": p["id"], "rotulo": p.get("name") or p["id"], "idioma": p.get("language") or "", "tipo": "perfil"})
    except Exception:  # noqa: BLE001
        pass
    if out or no_ar():
        out.append({"id": "default", "rotulo": "Voz padrão do VoiceStudio", "idioma": "", "tipo": "padrao"})
    return out


def blocos(texto: str, maximo: int = MAX_BLOCO) -> list[str]:
    """Quebra por parágrafo e, se preciso, por frase, sem passar de `maximo` caracteres."""
    pecas: list[str] = []
    for p in [x.strip() for x in re.split(r"\n\s*\n|\n", texto) if x.strip()]:
        if len(p) <= maximo:
            pecas.append(p)
            continue
        for f in re.split(r"(?<=[.!?…])\s+", p):
            while len(f) > maximo:
                corte = f.rfind(" ", 0, maximo) or maximo
                pecas.append(f[:corte].strip()); f = f[corte:].strip()
            if f:
                pecas.append(f)
    out, atual = [], ""
    for p in pecas:
        if atual and len(atual) + len(p) + 1 > maximo:
            out.append(atual); atual = ""
        atual = f"{atual} {p}".strip()
    if atual:
        out.append(atual)
    return out


def _marcar_em_curso() -> Path | None:
    """Anota (arquivo pid-n) que este processo está pedindo uma voz: é o que a tela Vozes lê pra dizer "gerando outra voz"."""
    try:
        _N["n"] += 1
        EM_CURSO.mkdir(parents=True, exist_ok=True)
        f = EM_CURSO / f"{os.getpid()}-{_N['n']}"
        f.write_text(str(time.time()))
        return f
    except OSError:
        return None


def _marcar_ocupada() -> None:
    try:
        EM_CURSO.mkdir(parents=True, exist_ok=True)
        (EM_CURSO / "ocupada").write_text(str(time.time()))
    except OSError:
        pass


def _soltar_em_curso(f: Path | None) -> None:
    try:
        if f:
            f.unlink()
    except OSError:
        pass


def _pedido(texto: str, voz: str, formato: str, timeout: float = 600) -> bytes:
    corpo = json.dumps({"model": "tts-1", "voice": voz or "default", "input": texto,
                        "response_format": formato, "language": "pt"}).encode()
    req = urllib.request.Request(url() + "/v1/audio/speech", data=corpo, method="POST",
                                 headers={"Content-Type": "application/json"})
    marca = _marcar_em_curso()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 503 and (e.headers.get("Retry-After") or e.headers.get("X-OmniVoice-Retryable")):
            _marcar_ocupada()
            raise VozOcupada(MSG_OCUPADA) from None
        raise ValueError(f"VoiceStudio respondeu {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}") from None
    except (socket.timeout, TimeoutError):
        _marcar_ocupada()
        raise VozOcupada(MSG_OCUPADA) from None
    except (urllib.error.URLError, OSError) as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            _marcar_ocupada()
            raise VozOcupada(MSG_OCUPADA) from None
        raise VozForaDoAr(f"VoiceStudio fora do ar ({e})") from None
    finally:
        _soltar_em_curso(marca)


def falar(texto: str, saida: Path, voz: str = "default", formato: str = "mp3") -> Path:
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    partes = blocos(texto)
    if not partes:
        raise ValueError("Sem texto pra narrar.")
    if not garantir_no_ar(60):
        e = estado()
        raise VozForaDoAr("VoiceStudio fora do ar. " + (MSG_INSTALAR if e["estado"] == "instalar" else "Abra o VoiceStudio (aplicativo) e tente de novo."))
    if (voz or "default") == "default" and len(partes) > 1:
        # a voz padrão não tem pessoa fixa: cada bloco saía com uma voz sorteada (homem até 44 s, mulher depois,
        # grupo-por-crenca 29-out-2026). Sem perfil, vai tudo num pedido só pra ser a mesma voz do começo ao fim.
        saida.write_bytes(_pedido(" ".join(partes), voz, formato, timeout=3600))
        return saida
    if len(partes) == 1:
        saida.write_bytes(_pedido(partes[0], voz, formato))
        return saida
    with tempfile.TemporaryDirectory() as tmp:
        arqs = []
        for i, p in enumerate(partes):
            a = Path(tmp) / f"{i:03d}.{formato}"
            a.write_bytes(_pedido(p, voz, formato))
            arqs.append(a)
        lista = Path(tmp) / "lista.txt"
        lista.write_text("".join(f"file '{a.name}'\n" for a in arqs))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                        "-c", "copy", str(saida)], check=True)
    return saida


def amostra(voz: str = "default") -> Path:
    """Frase curta cacheada em app/.cache/vozes/<voz>.mp3."""
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", voz or "default")
    alvo = PASTA_AMOSTRAS / f"{nome}.mp3"
    if alvo.exists() and alvo.stat().st_size > 0:
        return alvo
    return falar(FRASE_AMOSTRA, alvo, voz)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["falar"] and len(a) >= 2:
        saida = a[a.index("--saida") + 1] if "--saida" in a else "voz.mp3"
        voz = a[a.index("--voz") + 1] if "--voz" in a else "default"
        print(falar(a[1], Path(saida), voz))
    elif a[:1] == ["amostra"] and len(a) >= 2:
        print(amostra(a[1]))
    else:
        print(json.dumps({"no_ar": no_ar(), "vozes": vozes()}, ensure_ascii=False, indent=1))
