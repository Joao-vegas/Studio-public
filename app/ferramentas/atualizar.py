#!/usr/bin/env python3
"""
atualizar — mantém os motores e ferramentas do Estúdio em dia, sem quebrar o que funciona.

Sempre em busca: segunda 4h (LaunchAgent com.joao.estudio-atualizar), uma vez por dia quando o Estúdio abre
(`conferir_se_velho`, em segundo plano) e pelo botão "Conferir agora" em Configurações:
    1. confere a versão instalada e a mais nova de cada item do MANIFESTO
    2. versão pequena (mesmo número principal): instala e TESTA; se o teste falhar, volta pra anterior
       (item com "auto": False só avisa "disponível": bibliotecas do Python que mexem em muita coisa, Three.js, ffmpeg;
       VoiceStudio (aplicativo) nunca instala sozinho: "Atualizar" só abre o app, que tem o atualizador dele)
       Há vídeo sendo feito? Fica "na fila" e instala sozinho quando ele terminar (`tocar_fila`, a cada 30 min).
    3. versão grande (número principal mudou): não instala sozinho, fica "segurada" pro João decidir
    4. grava o resultado em app/motores/atualizacoes.json (é o que a tela mostra)
Botão Atualizar de cada item (disponível ou segurada): instala, testa e, se falhar, volta pra anterior
(pip: foto das três pastas de bibliotecas antes; brew não volta, por isso o botão do ffmpeg avisa antes).
Recusa se tiver vídeo sendo feito ou outra atualização rodando. Biblioteca do Python nova reinicia o Estúdio.

    python3 atualizar.py rodar          # confere e atualiza
    python3 atualizar.py item <nome>    # o botão Atualizar de um item
    python3 atualizar.py testar <nome>  # só roda o teste do item, sem instalar nada
    python3 atualizar.py estado         # só mostra o último resultado
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO, RAIZ, agora, com_venv, gravar_json, ler_json

ESTADO = ESTUDIO / "motores" / "atualizacoes.json"
TRAVA = ESTUDIO / "motores" / "atualizando.pid"
PY = ESTUDIO / ".venv" / "bin" / "python"
_CFG = ESTUDIO / ".venv" / "pyvenv.cfg"
_HOME = next((l.split("=", 1)[1].strip() for l in (_CFG.read_text().splitlines() if _CFG.exists() else [])
              if l.startswith("home")), "/opt/homebrew/bin")
PY_BASE = Path(_HOME) / f"python{sys.version_info.major}.{sys.version_info.minor}"   # o Python de onde o venv nasceu
NPM = shutil.which("npm") or "/opt/homebrew/bin/npm"
GB = Path.home() / ".claude" / "skills" / "get-brolls"
GERADOR = Path.home() / "Projetos" / "Skill" / "Gerador de imagem e vídeo"
TESTES = ESTUDIO / "tests"
_FT = "import sys; sys.path.insert(0, 'app/ferramentas'); "
# Importa tudo de uma vez: pega a biblioteca que quebrou outra ao subir junto (ex.: numpy novo derrubando o OpenCV).
IMPORTA_TUDO = [str(PY), "-c", "import flask, anthropic, numpy, PIL, yaml, requests, cv2, rembg, mlx_whisper, "
                "sentence_transformers, playwright.sync_api"]

# Tudo o que o README lista em "Ferramentas e repositórios". "auto": False = só avisa (versão nova
# disponível), nunca instala sozinho: é o caso das bibliotecas do Python e do Three.js (0.x muda o jeito de usar).
# "teste": comandos que provam que a versão nova funciona (rodados da raiz do projeto); "testes": arquivos de app/tests.
# "sem_volta": o botão avisa antes, porque se a versão nova falhar não dá pra voltar sozinho (brew).
MANIFESTO = [
    {"nome": "Claude Code", "tipo": "npm-global", "pacote": "@anthropic-ai/claude-code", "bin": "claude", "pra": "a IA que produz os vídeos"},
    {"nome": "Codex", "tipo": "npm-global", "pacote": "@openai/codex", "bin": "codex", "pra": "IA opcional (GPT) no lugar do Claude"},
    {"nome": "VoiceStudio", "tipo": "app", "app": "VoiceStudio", "repo": "debpalash/VoiceStudio",
     "pra": "a voz local dos vídeos (o aplicativo; ele mesmo instala a versão nova)", "auto": False},
    {"nome": "anthropic (SDK)", "tipo": "pip", "pacote": "anthropic", "pra": "chat de briefing", "auto": False,
     "testes": ["test_conversa.py", "test_briefing.py"]},
    {"nome": "HyperFrames", "tipo": "npm", "pasta": "app/motores/hyperframes", "pacotes": ["hyperframes"], "auto": False,
     "pra": "opcional, nenhum estilo usa hoje: HTML vira vídeo com checagem automática", "teste": ["npx", "hyperframes", "--version"]},
    {"nome": "Three.js", "tipo": "npm", "pasta": "app/motores/3d", "pacotes": ["three"], "pra": "Explicador 3D", "auto": False,
     "teste": ["node", "--input-type=module", "-e", "import * as T from 'three'; if (!T.WebGLRenderer) process.exit(1)"]},
    {"nome": "Playwright", "tipo": "pip", "pacote": "playwright", "pra": "captura os quadros do HTML e do 3D",
     "depois": [[str(PY), "-m", "playwright", "install", "chromium"]],
     "teste": [str(PY), "-c", "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n"
               " b = p.chromium.launch(); g = b.new_page(); g.set_content('<b>ok</b>'); assert g.screenshot(); b.close()"]},
    {"nome": "ffmpeg", "tipo": "brew", "pacote": "ffmpeg", "pra": "corta, junta, cor e áudio", "auto": False, "sem_volta": True,
     "teste": ["bash", "-c", "f=$(mktemp -d)/t.mp4 && ffmpeg -v error -f lavfi -i color=c=black:s=320x240:d=1 -f lavfi "
               "-i sine=d=1 -vf scale=160:-2 -c:v h264_videotoolbox -c:a aac -shortest -y $f && ffprobe -v error $f"]},
    {"nome": "auto-editor", "tipo": "pip", "pacote": "auto-editor", "pra": "medir silêncio no corte",
     "teste": [str(Path.home() / "Library/Python/3.14/bin/auto-editor"), "--version"], "testes": ["test_corte_qualidade.py"]},
    {"nome": "yt-dlp", "tipo": "brew", "pacote": "yt-dlp", "pra": "baixar por link: referência, fala, música (quebra se ficar velho)", "auto": True},
    {"nome": "tesseract", "tipo": "brew", "pacote": "tesseract", "pra": "lê o texto nos quadros (estudo de referência, grifo)", "auto": True,
     "teste": ["bash", "-c", "tesseract --version"]},
    {"nome": "get-brolls", "tipo": "git", "pasta": str(GB), "pra": "busca de b-roll (YouTube, Pexels, Pixabay, Commons, NASA); é do engenheirodevideo, atualiza do repositório dele"},
    {"nome": "Gerador de imagem e vídeo", "tipo": "git", "pasta": str(GERADOR), "pra": "skill da kie.ai (imagem e vídeo por IA, custo por projeto)"},
    {"nome": "mlx-whisper", "tipo": "pip", "pacote": "mlx-whisper", "pra": "transcreve a fala no próprio Mac"},
    {"nome": "rembg", "tipo": "pip", "pacote": "rembg", "pra": "recorta a pessoa do fundo"},
    {"nome": "Demucs", "tipo": "pip", "pacote": "demucs", "pra": "separa a voz da música num clipe real (so_voz do Editorial); mexe no torch, só avisa", "auto": False,
     "teste": [str(PY), "-c", "import demucs.separate"]},
    {"nome": "onnxruntime", "tipo": "pip", "pacote": "onnxruntime", "pra": "roda o mapa de profundidade do parallax (Depth Anything) e o rembg; confere também Real-ESRGAN (ampliar foto)", "auto": False,
     "teste": [str(PY), "-c", _FT + "import midia_local as m; assert m.PROF.exists() and m.ESRGAN.exists(), 'rode: python3 app/ferramentas/midia_local.py baixar'; import onnxruntime"]},
    {"nome": "OpenCV", "tipo": "pip", "pacote": "opencv-python-headless", "pra": "acha rosto e mede nitidez (documentário, 3D)", "auto": False,
     "teste": [str(PY), "-c", "import cv2, numpy as np; c = cv2.CascadeClassifier(cv2.data.haarcascades + "
               "'haarcascade_frontalface_default.xml'); assert not c.empty(); cv2.Laplacian(np.zeros((8, 8), np.uint8), cv2.CV_64F)"]},
    {"nome": "sentence-transformers", "tipo": "pip", "pacote": "sentence-transformers", "pra": "busca por significado no acervo e o CLIP que confere se a imagem casa com a fala (casar_imagem.py)", "auto": False,
     "teste": [str(PY), "-c", _FT + "import semantica as s; m = s.encoder(); assert m is not None; m.encode(['teste']); "
               "import casar_imagem as c; assert c.modelos_prontos(), 'rode: python3 app/ferramentas/casar_imagem.py baixar'"]},
    {"nome": "Flask", "tipo": "pip", "pacote": "flask", "pra": "as telas do Estúdio", "auto": False,
     "testes": ["test_tela_briefing.py", "test_telas_enxutas.py"]},
    {"nome": "Skills do HyperFrames", "tipo": "git", "pasta": str(RAIZ / "app/motores/hyperframes/skills-oficiais"),
     "pra": "documentação oficial do HyperFrames (cópia do fabricante) que a IA consulta"},
]


def _r(cmd, cwd=None, timeout=900):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=com_venv())
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def ambiente_python() -> tuple[bool, str]:
    """Depois de qualquer atualização pelo brew: o python da venv ainda importa flask, PIL, numpy e cv2? O `python3` que o Estúdio
    entrega aos filhos (PATH com a venv na frente) é o da venv? O tesseract abre? Devolve (ok, nota): `ok` False se algo quebrou;
    a nota também avisa (sem reprovar) quando o `python3` do sistema trocou de versão, como em 30-out-2026 (virou 3.15, sem as
    bibliotecas). Não mexe nos links do brew: só confere."""
    quebrou, avisos = [], []
    code, log = _r([str(PY), "-c", "import flask, PIL, numpy, cv2"], timeout=120)
    if code:
        quebrou.append("o Python do Estúdio (venv) não importa flask, PIL, numpy ou cv2: " + log.strip()[-120:])
    code, v = _r(["python3", "-c", "import sys; print(sys.prefix)"], timeout=30)
    if code or Path(v.strip()).resolve() != (ESTUDIO / ".venv").resolve():
        quebrou.append("o python3 que os filhos do Estúdio enxergam não é o da venv (" + v.strip()[-80:] + ")")
    code, sis = _r(["/opt/homebrew/bin/python3", "--version"], timeout=30)
    code2, mine = _r([str(PY), "--version"], timeout=30)
    if not code and not code2 and sis.split()[-1].rsplit(".", 1)[0] != mine.split()[-1].rsplit(".", 1)[0]:
        avisos.append(f"o python3 do sistema agora é {sis.split()[-1]} (sem as bibliotecas do Estúdio); o Estúdio usa o da venv "
                      f"({mine.split()[-1]}) e não depende dele")
    code, t = _r(["tesseract", "--version"], timeout=30)
    if code:
        quebrou.append("o tesseract não abre depois da atualização: " + t.strip()[-100:])
    return not quebrou, "; ".join(quebrou + avisos)


def _maior(v: str) -> str:
    return (v or "0").lstrip("v").split(".")[0]


def _video_rodando() -> bool:
    """Tem vídeo sendo feito agora? (instalar nada nesse momento: ferramenta trocada no meio quebra o vídeo)"""
    try:
        import producao
        return any(j.get("rodando") for j in producao.listar())
    except Exception:
        return False


def _na_fila(atual: str, nova: str) -> dict:
    return {"versao": atual, "nova": nova, "estado": "na fila",
            "nota": "tem vídeo sendo feito; instalo sozinha quando ele terminar (confere a cada 30 min)"}


AVISO = "versão nova disponível: aperte Atualizar (instala, testa e volta pra anterior se falhar)"


def _so_avisa(atual: str, nova: str, item: dict | None = None) -> dict:
    nota = ("versão nova disponível: o Atualizar testa, mas se falhar não volta sozinho"
            if (item or {}).get("sem_volta") else AVISO)
    return {"versao": atual, "nova": nova, "estado": "disponível", "nota": nota}


def _testar(item: dict) -> tuple[bool, str]:
    """Prova que a versão nova funciona: importa tudo (pip), o teste do item e os arquivos de app/tests dele."""
    cmds = [(IMPORTA_TUDO, RAIZ)] if item["tipo"] == "pip" else []
    if item.get("teste"):
        cmds.append((item["teste"], RAIZ / item["pasta"] if item["tipo"] == "npm" else RAIZ))
    cmds += [([str(PY), "-m", "unittest", t], TESTES) for t in item.get("testes", [])]
    for cmd, cwd in cmds:
        code, log = _r(cmd, cwd=cwd, timeout=600)
        if code != 0:
            return False, log[-300:]
    return True, ""


def _npm(item: dict, forcar: bool = False) -> dict:
    pasta = RAIZ / item["pasta"]
    principal = item["pacotes"][0]
    atual = (ler_json(pasta / "node_modules" / principal / "package.json", {}) or {}).get("version", "")
    code, nova = _r([NPM, "view", principal, "version"], cwd=pasta, timeout=60)
    nova = nova.strip().splitlines()[-1] if code == 0 and nova.strip() else ""
    out = {"versao": atual or "não instalado", "nova": ""}
    if not nova or nova == atual:
        return {**out, "estado": "em dia"}
    out["nova"] = nova
    if not forcar and not item.get("auto", True):
        return _so_avisa(atual, nova, item)
    if not forcar and atual and _maior(nova) != _maior(atual):
        return {**out, "estado": "segurada", "nota": "versão grande: pode mudar o jeito de usar. Aperte Atualizar pra testar."}
    if not forcar and _video_rodando():
        return _na_fila(atual, nova)
    code, log = _r([NPM, "install", "--save-exact", *[f"{p}@{nova}" for p in item["pacotes"]]], cwd=pasta)
    ok, log = _testar(item) if code == 0 else (False, log[-300:])
    if not ok:
        _r([NPM, "install", "--save-exact", *[f"{p}@{atual}" for p in item["pacotes"]]], cwd=pasta)
        return {**out, "estado": "segurada", "nota": "a versão nova falhou no teste; voltei pra anterior. " + log[-200:]}
    return {"versao": nova, "nova": "", "estado": "atualizada", "nota": f"de {atual} pra {nova}, teste ok"}


# ── Python: o app/.venv enxerga três pastas de bibliotecas; cada uma tem o seu pip ──

def _escopos() -> list[tuple[str, Path, list[str], list[str]]]:
    """(nome, pasta, pip, opções): o venv do Estúdio, a pasta do usuário e a do Homebrew."""
    _, txt = _r([str(PY_BASE), "-c", "import site, sysconfig; print(site.getusersitepackages()); "
                 "print(sysconfig.get_path('purelib'))"], timeout=30)
    usuario, sistema = (txt.strip().splitlines() + ["", ""])[:2]
    base = [str(PY_BASE), "-m", "pip"]
    venv = next((ESTUDIO / ".venv" / "lib").glob("python3*/site-packages"), ESTUDIO / ".venv")
    return [("venv", venv, [str(PY), "-m", "pip"], []),
            ("usuario", Path(usuario), base, ["--user", "--break-system-packages"]),
            ("sistema", Path(sistema), base, ["--break-system-packages"])]


def _nfc(p) -> str:
    return unicodedata.normalize("NFC", str(p))


def _foto() -> dict:
    """{escopo: {pacote: versão}} das três pastas: é o que volta se a versão nova falhar."""
    foto = {}
    for nome, pasta, _, _ in _escopos():
        _, txt = _r([str(PY), "-m", "pip", "freeze", "--path", str(pasta)], timeout=120)
        foto[nome] = dict(l.split("==", 1) for l in txt.splitlines() if "==" in l and not l.startswith("#"))
    return foto


def _voltar_pip(antes: dict) -> None:
    """Desfaz tudo o que mudou nas três pastas desde a foto (o pacote e as dependências que subiram junto)."""
    depois = _foto()
    for nome, _, pip, extra in _escopos():
        a, d = antes.get(nome, {}), depois.get(nome, {})
        novos = [p for p in d if p not in a]
        voltar = [f"{p}=={a[p]}" for p in a if d.get(p) != a[p]]
        if novos:
            _r(pip + ["uninstall", "-y", *[x for x in extra if x != "--user"], *novos], timeout=600)
        if voltar:
            _r(pip + ["install", "-q", "--no-deps", *extra, *voltar], timeout=1800)


def _pip(item: dict, forcar: bool = False) -> dict:
    code, txt = _r([str(PY), "-m", "pip", "show", item["pacote"]], timeout=60)
    campo = lambda k: next((l.split(":", 1)[1].strip() for l in txt.splitlines() if l.startswith(k + ":")), "")
    atual, onde = campo("Version"), campo("Location")
    if not atual:
        return {"versao": "não instalado", "nova": "", "estado": "não instalado"}
    code, txt = _r([str(PY), "-m", "pip", "index", "versions", item["pacote"]], timeout=60)
    nova = ""
    for l in txt.splitlines():
        if l.lower().startswith(item["pacote"].lower()) and "(" in l:
            nova = l.split("(", 1)[1].split(")", 1)[0]
    if not nova or nova == atual:
        return {"versao": atual, "nova": "", "estado": "em dia"}
    if not forcar and not item.get("auto", True):
        return _so_avisa(atual, nova, item)
    if not forcar and _maior(nova) != _maior(atual):
        return {"versao": atual, "nova": nova, "estado": "segurada", "nota": "versão grande: aperte Atualizar pra testar"}
    if not forcar and _video_rodando():
        return _na_fila(atual, nova)
    escopos = _escopos()
    _, _, pip, extra = next((e for e in escopos if onde and _nfc(onde).startswith(_nfc(e[1]))), escopos[0])
    antes = _foto()
    code, log = _r(pip + ["install", "-q", *extra, f"{item['pacote']}=={nova}"], timeout=1800)
    for cmd in item.get("depois", []):
        if code == 0:
            code, log = _r(cmd, timeout=1800)
    ok, log = _testar(item) if code == 0 else (False, log[-300:])
    if not ok:
        _voltar_pip(antes)
        for cmd in item.get("depois", []):
            _r(cmd, timeout=1800)
        return {"versao": atual, "nova": nova, "estado": "segurada", "nota": "a versão nova falhou no teste; voltei pra anterior. " + log[-200:]}
    return {"versao": nova, "nova": "", "estado": "atualizada", "nota": f"de {atual} pra {nova}, teste ok", "_reiniciar": True}


def _brew(item: dict, forcar: bool = False) -> dict:
    brew = shutil.which("brew") or "/opt/homebrew/bin/brew"
    code, txt = _r([brew, "info", "--json=v2", item["pacote"]], timeout=120)
    try:
        f = json.loads(txt)["formulae"][0]
        atual = (f.get("installed") or [{}])[0].get("version", "")
        nova = f["versions"]["stable"]
        if re.sub(r"_\d+$", "", atual) == nova:   # 9.0.2_1 → 9.0.2 é só a "revisão" da receita, não versão nova
            return {"versao": atual, "nova": "", "estado": "em dia"}
    except Exception:
        return {"versao": "?", "nova": "", "estado": "não conferido"}
    if not atual:
        return {"versao": "não instalado", "nova": nova, "estado": "não instalado"}
    if nova == atual:
        return {"versao": atual, "nova": "", "estado": "em dia"}
    if not forcar and not item.get("auto"):
        return _so_avisa(atual, nova, item)
    if not forcar and _maior(nova) != _maior(re.sub(r"_\d+$", "", atual)):
        return {"versao": atual, "nova": nova, "estado": "segurada", "nota": "versão grande: aperte Atualizar pra testar"}
    if not forcar and _video_rodando():
        return _na_fila(atual, nova)
    code, log = _r([brew, "upgrade", item["pacote"]], timeout=3600)
    ok, log = _testar(item) if code == 0 else (False, log[-300:])
    if ok:
        _, amb = ambiente_python()   # o brew pode ter trocado o python3 do sistema: fica escrito na nota
        return {"versao": nova, "nova": "", "estado": "atualizada",
                "nota": f"de {atual} pra {nova}, teste ok" + (f". Atenção: {amb}" if amb else "")}
    return {"versao": atual, "nova": nova, "estado": "segurada" if code else "falhou",
            "nota": ("o brew não conseguiu atualizar; nada mudou. " if code else
                     "a versão nova falhou no teste e o brew não volta sozinho: peça ajuda ao Claude. ") + log[-200:]}


def _npm_global(item: dict, forcar: bool = False) -> dict:
    """CLI instalada com `npm i -g` (Claude Code, Codex)."""
    _, txt = _r([NPM, "ls", "-g", item["pacote"], "--depth=0", "--json"], timeout=60)
    try:
        atual = json.loads(txt)["dependencies"][item["pacote"]]["version"]
    except Exception:
        atual = ""
    code, nova = _r([NPM, "view", item["pacote"], "version"], timeout=60)
    nova = nova.strip().splitlines()[-1] if code == 0 and nova.strip() else ""
    if not atual:
        return {"versao": "não instalado", "nova": nova, "estado": "não instalado"}
    if not nova or nova == atual:
        return {"versao": atual, "nova": "", "estado": "em dia"}
    if not forcar and not item.get("auto", True):
        return _so_avisa(atual, nova, item)
    if not forcar and _maior(nova) != _maior(atual):
        return {"versao": atual, "nova": nova, "estado": "segurada", "nota": "versão grande: aperte Atualizar pra testar"}
    if not forcar and _video_rodando():
        return _na_fila(atual, nova)
    code, log = _r([NPM, "install", "-g", f"{item['pacote']}@{nova}"], timeout=900)
    if code == 0:
        _, prefixo = _r([NPM, "prefix", "-g"], timeout=30)
        code, log = _r([str(Path(prefixo.strip()) / "bin" / item["bin"]), "--version"], timeout=60)
    if code != 0:
        _r([NPM, "install", "-g", f"{item['pacote']}@{atual}"], timeout=900)
        return {"versao": atual, "nova": nova, "estado": "segurada", "nota": "a versão nova falhou no teste; voltei pra anterior. " + log[-200:]}
    return {"versao": nova, "nova": "", "estado": "atualizada", "nota": f"de {atual} pra {nova}, teste ok"}


def _git(item: dict, forcar: bool = False) -> dict:
    pasta = Path(item["pasta"])
    if not (pasta / ".git").exists():
        return {"versao": "sem git", "nova": "", "estado": "não conferido"}
    _r(["git", "-C", str(pasta), "fetch", "-q"], timeout=120)
    _, atras = _r(["git", "-C", str(pasta), "rev-list", "--count", "HEAD..@{u}"], timeout=30)
    _, sujo = _r(["git", "-C", str(pasta), "status", "--porcelain"], timeout=30)
    _, versao = _r(["git", "-C", str(pasta), "log", "-1", "--format=%cd", "--date=short"], timeout=30)
    n = int(atras.strip() or 0) if atras.strip().isdigit() else 0
    if not n:
        return {"versao": versao.strip(), "nova": "", "estado": "em dia"}
    if sujo.strip():
        return {"versao": versao.strip(), "nova": f"{n} mudança(s)", "estado": "segurada", "nota": "tem alteração local; não mexi"}
    code, log = _r(["git", "-C", str(pasta), "pull", "--ff-only", "-q"], timeout=120)
    return ({"versao": "hoje", "nova": "", "estado": "atualizada", "nota": f"{n} mudança(s) puxadas"} if code == 0
            else {"versao": versao.strip(), "nova": f"{n} mudança(s)", "estado": "segurada", "nota": log[-200:]})


def _app(item: dict, forcar: bool = False) -> dict:
    """Aplicativo com atualizador próprio (VoiceStudio): confere a versão do Info.plist contra o último release do GitHub.
    Nunca instala: o botão Atualizar só abre o aplicativo, que baixa e instala a versão nova pelo atualizador dele."""
    plist = Path("/Applications") / f"{item['app']}.app" / "Contents" / "Info.plist"
    code, atual = _r(["/usr/bin/defaults", "read", str(plist), "CFBundleShortVersionString"], timeout=10)
    atual = atual.strip() if code == 0 else ""
    if not atual:
        return {"versao": "não instalado", "nova": "", "estado": "não instalado"}
    nova = ""
    try:
        import urllib.request
        req = urllib.request.Request(f"https://api.github.com/repos/{item['repo']}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "estudio"})
        with urllib.request.urlopen(req, timeout=15) as r:
            nova = (json.loads(r.read()).get("tag_name") or "").lstrip("v")
    except Exception:
        return {"versao": atual, "nova": "", "estado": "não conferido", "nota": "sem resposta do GitHub agora; tento de novo na próxima conferência"}
    if forcar:
        subprocess.run(["open", "-a", item["app"]], capture_output=True, timeout=15)
        return {"versao": atual, "nova": nova if nova and nova != atual else "",
                "estado": "disponível" if nova and nova != atual else "em dia",
                "nota": "abri o aplicativo: ele tem o atualizador próprio (pergunta e instala lá dentro)"}
    if not nova or nova == atual:
        return {"versao": atual, "nova": "", "estado": "em dia"}
    return {"versao": atual, "nova": nova, "estado": "disponível",
            "nota": "versão nova no GitHub: aperte Atualizar pra abrir o aplicativo, que instala por conta própria"}


FUNCOES = {"npm": _npm, "npm-global": _npm_global, "pip": _pip, "brew": _brew, "git": _git, "app": _app}


def rodar() -> dict:
    itens = []
    TRAVA.write_text(str(os.getpid()))
    try:
        return _rodar_tudo(itens)
    finally:
        TRAVA.unlink(missing_ok=True)


def _rodar_tudo(itens: list) -> dict:
    for item in MANIFESTO:
        try:
            r = FUNCOES[item["tipo"]](item)
        except Exception as e:
            r = {"versao": "?", "nova": "", "estado": "não conferido", "nota": str(e)[:200]}
        r.pop("_reiniciar", None)
        itens.append({"nome": item["nome"], "pra": item["pra"], **r})
    dados = {"quando": agora()[:16], "itens": itens, "rodando": False}
    gravar_json(ESTADO, dados)
    return dados


def _trava_viva() -> bool:
    """A trava só vale se o pid ainda é DESTE script (pid velho reaproveitado por outro programa não prende o botão)."""
    try:
        pid = int(TRAVA.read_text().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    _, cmd = _r(["ps", "-p", str(pid), "-o", "command="], timeout=10)
    if "atualizar.py" in cmd:
        return True
    TRAVA.unlink(missing_ok=True)
    return False


def estado() -> dict:
    """Último resultado, na ordem do MANIFESTO: item novo aparece já ("ainda não conferido"), item tirado some."""
    d = ler_json(ESTADO, None) or {"quando": ""}
    feitos = {i.get("nome"): i for i in d.get("itens", [])}
    vazio = {"versao": "", "nova": "", "estado": "ainda não conferido"}
    d["itens"] = [{**feitos.get(i["nome"], vazio), "nome": i["nome"], "pra": i["pra"], "tipo": i["tipo"],
                   "sem_volta": bool(i.get("sem_volta"))} for i in MANIFESTO]
    d["motivo_ocupado"] = ocupado()   # "" = o botão Atualizar pode ser apertado agora; senão a tela mostra o motivo
    if not _trava_viva():
        for i in d["itens"]:
            if i.get("estado") == "atualizando":
                i.update(estado="ainda não conferido", nota="a atualização parou no meio; aperte Conferir agora")
    return d


def disparar() -> None:
    d = estado(); d["rodando"] = True; gravar_json(ESTADO, d)
    subprocess.Popen([str(PY if PY.exists() else sys.executable), str(Path(__file__)), "rodar"],
                     cwd=str(RAIZ), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ── botão Atualizar de cada item (Config → Atualizações) ──

def ocupado() -> str:
    """Motivo pra não atualizar agora ("" = pode): outra atualização rodando ou vídeo sendo feito."""
    if _trava_viva():
        return "Atualizando…"
    if _video_rodando():
        return "Espere o vídeo terminar"
    return ""


def disparar_item(nome: str) -> str:
    item = next((i for i in MANIFESTO if i["nome"] == nome and i["tipo"] != "git"), None)
    if not item:
        return "Esse item não tem botão de atualizar."
    if item["tipo"] == "app":   # só abre o aplicativo (que tem o atualizador dele): não depende de vídeo nem de trava
        r = _app(item, forcar=True)
        d = estado()
        for i in d["itens"]:
            if i["nome"] == nome:
                i.update(r)
        gravar_json(ESTADO, d)
        return f"Atualizando {nome}: abri o aplicativo, a versão nova se instala lá dentro."
    motivo = ocupado()
    if motivo:
        return f"Não atualizei {nome}: {motivo.lower().rstrip('…')}" + (". Tente de novo quando terminar." if motivo.startswith("Espere") else ".")
    d = estado()
    for i in d["itens"]:
        if i["nome"] == nome:
            i.update(estado="atualizando", nota="instalando e testando; pode levar alguns minutos")
    gravar_json(ESTADO, d)
    p = subprocess.Popen([str(PY if PY.exists() else sys.executable), str(Path(__file__)), "item", nome],
                         cwd=str(RAIZ), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    TRAVA.write_text(str(p.pid))
    return f"Atualizando {nome}: instala, testa e só fica se passar. O resultado aparece aqui."


# ── sempre buscando: uma vez por dia quando o Estúdio abre, e a fila espera o vídeo terminar ──

ESTADO_QUANDO = "%Y-%m-%d %H:%M"


def _idade_horas() -> float:
    try:
        from datetime import datetime
        quando = (ler_json(ESTADO, {}) or {}).get("quando", "")
        return (datetime.now() - datetime.strptime(quando, ESTADO_QUANDO)).total_seconds() / 3600
    except Exception:
        return 9999.0


def conferir_se_velho(horas: float = 20) -> bool:
    """Chamado quando o Estúdio abre: se a última conferência tem mais de `horas`, confere em segundo plano (sem travar a tela)."""
    if _idade_horas() < horas or _trava_viva():
        return False
    disparar()
    return True


def tocar_fila() -> bool:
    """Tem item "na fila" (esperava vídeo terminar) e agora está livre? Roda a conferência, que instala o que pode."""
    d = ler_json(ESTADO, {}) or {}
    if not any(i.get("estado") == "na fila" for i in d.get("itens", [])):
        return False
    if _video_rodando() or _trava_viva():
        return False
    disparar()
    return True


def quantas_disponiveis() -> int:
    """Itens com versão nova esperando (disponível, segurada ou na fila), pelo último resultado gravado: o selo do menu."""
    d = ler_json(ESTADO, {}) or {}
    return sum(1 for i in d.get("itens", []) if i.get("estado") in ("disponível", "segurada", "na fila"))


def vigiar(intervalo: float = 1800) -> None:
    """Fio em segundo plano do servidor: confere se está velho agora e depois toca a fila a cada 30 min."""
    time.sleep(20)
    try:
        conferir_se_velho()
    except Exception:
        pass
    while True:
        time.sleep(intervalo)
        try:
            if not tocar_fila():
                conferir_se_velho()
        except Exception:
            pass


def rodar_item(nome: str) -> dict:
    item = next(i for i in MANIFESTO if i["nome"] == nome)
    try:
        r = FUNCOES[item["tipo"]](item, forcar=True)
    except Exception as e:
        r = {"estado": "segurada", "nota": "deu erro antes de terminar: " + str(e)[:200]}
    reiniciar = r.pop("_reiniciar", False)
    d = estado()
    for i in d["itens"]:
        if i["nome"] == nome:
            i.update(nova="", nota="")
            i.update(r)
    gravar_json(ESTADO, d)
    TRAVA.unlink(missing_ok=True)
    if reiniciar:
        _reiniciar_estudio()
    return r


def _reiniciar_estudio() -> None:
    """Biblioteca nova só vale com o Estúdio reiniciado: o servidor aberto ainda usa a antiga."""
    _, pids = _r(["lsof", "-tiTCP:7655", "-sTCP:LISTEN"], timeout=10)
    for pid in pids.split():
        _, cmd = _r(["ps", "-p", pid, "-o", "command="], timeout=10)
        if "servidor.py" in cmd:
            os.kill(int(pid), signal.SIGTERM)
    time.sleep(4)   # o LaunchAgent com.joao.estudio (KeepAlive) pode subir sozinho
    _, pids = _r(["lsof", "-tiTCP:7655", "-sTCP:LISTEN"], timeout=10)
    if not pids.strip():
        logs = ESTUDIO / "servico" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / "manual.log").open("a") as f:
            subprocess.Popen([str(PY), str(ESTUDIO / "interface" / "servidor.py")], cwd=str(RAIZ),
                             start_new_session=True, stdout=f, stderr=subprocess.STDOUT)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "item":
        print(json.dumps(rodar_item(sys.argv[2]), ensure_ascii=False, indent=1))
    elif len(sys.argv) > 2 and sys.argv[1] == "testar":
        print(_testar(next(i for i in MANIFESTO if i["nome"] == sys.argv[2])))
    elif len(sys.argv) > 1 and sys.argv[1] == "rodar":
        print(json.dumps(rodar(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(estado(), ensure_ascii=False, indent=1))
