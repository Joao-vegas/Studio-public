#!/usr/bin/env python3
"""
_comum — caminhos, varredura de clientes/modelos e utilidades do Estúdio.

Tudo é derivado da ESTRUTURA DE PASTAS do producao-reels (fonte da verdade):

    <Cliente>/<x>Content/modelos/<modelo>/           ← um modelo de edição
    <Cliente>/<x>Content/modelos/<modelo>/aprendizado/regras.json + historico.jsonl
    <Cliente>/<x>Content/output/<modelo>/*.mp4       ← vídeos produzidos
    acervo/itens/<slug>/{clip.mp4,thumb.jpg,meta.json}   ← acervo compartilhado
    acervo/busca/                              ← projeto do get-brolls (ledger/prévias)
    app/jobs/<cliente>/<slug>/job.json           ← cada vídeo produzido pelo Estúdio
"""
from __future__ import annotations

import html
import json
import os
import re
import signal
import subprocess
import threading
import unicodedata
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent          # producao-reels/
ESTUDIO = RAIZ / "app"
JOBS = ESTUDIO / "jobs"
CACHE = ESTUDIO / ".cache"
BROLLS = RAIZ / "acervo"
ACERVO = BROLLS / "itens"
GB_PROJECT = BROLLS / "busca"
SKILL_BROLL = RAIZ / ".claude" / "skills" / "broll" / "SKILL.md"

GB_ROOT = Path(os.environ.get("GB_ROOT", Path.home() / ".claude" / "skills" / "get-brolls"))
GB_PY = GB_ROOT / ".venv" / "bin" / "python"
GB_CLI = GB_ROOT / "scripts" / "gb.py"
GB_ENV = GB_ROOT / ".env"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
IMAGEM_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
IGNORAR_DIRS = {"node_modules", ".git", "__pycache__", ".venv", ".tools"}


def ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def hoje() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def make_slug(txt: str, maxlen: int = 60) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", txt).strip("-").lower()
    return txt[:maxlen] or now_slug()


def ler_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def gravar_json(p: Path, dados) -> None:
    ensure(p.parent)
    fd, tmp = tempfile.mkstemp(prefix=".json-", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        Path(tmp).unlink(missing_ok=True)


def ler_jsonl(p: Path) -> list:
    out = []
    if not p.exists():
        return out
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            out.append(json.loads(linha))
        except Exception:
            out.append({"tipo": "raw", "texto": linha})
    return out


def append_jsonl(p: Path, obj: dict) -> None:
    ensure(p.parent)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def rel(p: Path) -> str:
    """Caminho relativo à raiz do repo (pra servir via /arquivo/...)."""
    try:
        return str(Path(p).resolve().relative_to(RAIZ.resolve()))
    except ValueError:
        return str(p)


def dentro_da_raiz(p: Path) -> bool:
    try:
        Path(p).resolve().relative_to(RAIZ.resolve())
        return True
    except ValueError:
        return False


# ───────────────────────────── Python dos filhos ─────────────────────────────

VENV_BIN = ESTUDIO / ".venv" / "bin"
# OpenCV no Mac usa OpenCL por cima do Metal: o Python carrega a GPU e pode ficar preso na saída (estado UE, nem kill -9 mata).
# O Estúdio só faz detecção de rosto e nitidez em imagem pequena: CPU dá conta. Vale pra todo filho (com_venv) e pro próprio app.
SEM_OPENCL = {"OPENCV_OPENCL_RUNTIME": "disabled"}


def com_venv(env: dict | None = None) -> dict:
    """Cópia do ambiente (`env`, ou o de agora) com app/.venv/bin na FRENTE do PATH. Todo processo que o Estúdio abre
    (a IA que produz, o gerar.sh dos modelos, os scripts da esteira) chama `python3` pelo PATH: sem isto cai no python3 do
    brew, que pode ser outra versão (30-out-2026: virou 3.15, sem flask, PIL, numpy nem cv2) e quebra."""
    env = dict(os.environ if env is None else env)
    atual = [d for d in env.get("PATH", "").split(os.pathsep) if d and d != str(VENV_BIN)]
    if VENV_BIN.is_dir():
        atual.insert(0, str(VENV_BIN))
    env["PATH"] = os.pathsep.join(atual)
    env.update(SEM_OPENCL)
    return env


# o próprio Estúdio também: todo filho que ele abrir (zsh, ffmpeg, scripts) herda o PATH com o python da venv na frente
os.environ["PATH"] = com_venv()["PATH"]
os.environ.update(SEM_OPENCL)


# ───────────────────────────── Esperar um filho sem ficar preso ─────────────────────────────

class RenderTravou(subprocess.TimeoutExpired):
    """O filho passou do limite, foi morto e nem assim saiu: foi abandonado (30-out-2026: o Python com a GPU do Mac carregada
    ficava em UE na saída e o `subprocess.run(timeout=)` esperava o wait() pra sempre)."""

    def __str__(self) -> str:
        return f"o render travou e foi abandonado (passou de {self.timeout:g} s e não saiu): {' '.join(map(str, self.cmd))[:160]}"


def rodar_com_limite(cmd, timeout: float, espera_morte: float = 10, **kw) -> subprocess.CompletedProcess:
    """Como `subprocess.run(cmd, timeout=...)`, mas nunca fica preso. Estourou o tempo: mata o grupo inteiro (kill -9),
    espera no máximo `espera_morte` s ele sair e levanta `RenderTravou` (um `TimeoutExpired`, então os `except` que já
    existem seguem valendo) com o que já tinha saído. Aceita `capture_output`, `text`, `cwd`, `env`, `input`."""
    if kw.pop("capture_output", False):
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    entrada = kw.pop("input", None)
    if entrada is not None:
        kw["stdin"] = subprocess.PIPE
    p = subprocess.Popen(cmd, start_new_session=True, **kw)   # sessão própria: o kill leva os netos junto
    try:
        out, err = p.communicate(entrada, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        try:
            out, err = p.communicate(timeout=espera_morte)
        except subprocess.TimeoutExpired:
            out, err = e.output, e.stderr   # não saiu nem morto: larga o processo (sem wait) e segue
        raise RenderTravou(cmd, timeout, output=out, stderr=err) from None
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


# ───────────────────────────── ffmpeg ─────────────────────────────

def ffprobe(p: Path) -> dict:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(p)],
            capture_output=True, text=True, timeout=30)
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        fps = st.get("r_frame_rate", "0/1")
        try:
            n, m = fps.split("/")
            fps = round(float(n) / float(m), 2) if float(m) else 0
        except Exception:
            fps = 0
        return {
            "largura": st.get("width"), "altura": st.get("height"), "fps": fps,
            "duracao": round(float((d.get("format") or {}).get("duration") or 0), 2),
        }
    except Exception:
        return {"largura": None, "altura": None, "fps": None, "duracao": None}


def thumb(video: Path, destino: Path, t: float = 1.0, largura: int = 480) -> Path | None:
    """Gera um JPG de um frame do vídeo (cache simples; refaz se o vídeo for mais novo que a capa)."""
    if destino.exists() and destino.stat().st_mtime >= Path(video).stat().st_mtime:
        return destino
    ensure(destino.parent)
    for tt in (t, 0.0):
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(tt), "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={largura}:-2", str(destino)],
            capture_output=True, timeout=60)
        if r.returncode == 0 and destino.exists():
            return destino
    return None


def capa_boa(video: Path) -> float:
    """O segundo da capa: entre 5 quadros (15% a 75% do vídeo), o de mais contraste e cor, fora quase preto e quase branco.
    O quadro de 1 s costuma ser a abertura (texto começando no preto, tela branca), que não diz nada do vídeo (30-out-2026)."""
    try:
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "default=nk=1:nw=1", str(video)], text=True, timeout=30))
    except (subprocess.SubprocessError, ValueError, OSError):
        return 1.0
    if dur < 3:
        return min(1.0, dur / 2)
    from PIL import Image, ImageStat
    melhor, nota_melhor = 1.0, -1.0
    for f in (.15, .30, .45, .60, .75):
        t = round(dur * f, 2)
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf", "scale=96:-2",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=30)
        if r.returncode or not r.stdout:
            continue
        import io
        im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
        cinza = ImageStat.Stat(im.convert("L"))
        luz, contraste = cinza.mean[0], cinza.stddev[0]
        if luz < 28 or luz > 232:   # quase preto ou quase branco
            continue
        cor = ImageStat.Stat(im.convert("HSV")).mean[1]
        nota = contraste * (1 + cor / 255)
        if nota > nota_melhor:
            melhor, nota_melhor = t, nota
    return melhor


def thumb_rapida(video: Path) -> Path | None:
    """Capa provisória: 1 quadro a ~20% do vídeo (1 ffmpeg, ~0,2 s), guardada à parte até a capa boa (thumb_cache) ficar pronta."""
    key = re.sub(r"[^a-zA-Z0-9]+", "_", rel(video))[-150:]
    destino = CACHE / "thumbs" / f"{key}-rapida.jpg"
    try:
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                                             str(video)], text=True, timeout=15))
    except (subprocess.SubprocessError, ValueError, OSError):
        dur = 5.0
    return thumb(video, destino, t=round(dur * .2, 2), largura=360)


def thumb_cache(video: Path) -> Path | None:
    key = re.sub(r"[^a-zA-Z0-9]+", "_", rel(video))[-150:]
    destino = CACHE / "thumbs" / f"{key}-capa.jpg"   # "-capa": as antigas eram o quadro de 1 s
    if destino.exists() and destino.stat().st_mtime >= Path(video).stat().st_mtime:
        return destino
    return thumb(video, destino, t=capa_boa(Path(video)))


# ───────────────────────── CLAUDE.md (mapa de modelos) ─────────────────────────

def mapa_claude_md() -> dict:
    """Lê a tabela 'Mapa de modelos' do CLAUDE.md → {(cliente_dir, modelo): descricao}.
    A chave vem da 3ª coluna (caminho do aprendizado), que é o que identifica o modelo."""
    mapa: dict = {}
    md = RAIZ / "CLAUDE.md"
    if not md.exists():
        return mapa
    for linha in md.read_text(encoding="utf-8").splitlines():
        if not linha.startswith("|") or "aprendizado" not in linha:
            continue
        cols = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cols) < 3:
            continue
        pessoa, modelo_cell, caminho = cols[0], cols[1], cols[2]
        m = re.search(r"`([^`]+)`", modelo_cell)
        nome_modelo = m.group(1) if m else modelo_cell
        desc = modelo_cell[m.end():].strip() if m else modelo_cell
        desc = desc.strip("() ").strip()
        for mp in re.findall(r"`([^`]+)`", caminho):
            partes = mp.strip("/").split("/")
            if partes and partes[0] == "clientes": partes = partes[1:]
            if len(partes) >= 4 and partes[2] == "modelos":
                key = (partes[0], partes[3])
                mapa.setdefault(key, []).append({"pessoa": pessoa, "modelo": nome_modelo, "descricao": desc})
    return mapa


# ───────────────────────── clientes / modelos ─────────────────────────

def _content_dir(cliente_dir: Path) -> Path | None:
    for d in sorted(cliente_dir.iterdir()):
        if d.is_dir() and d.name.endswith("Content"):   # cliente novo só tem material/: modelos/ e output/ nascem quando precisam
            return d
    return None


# ───────────── memo curto (só enquanto um pedido da tela roda; 30-out-2026) ─────────────
# Varrer clientes/ e formatos/ custa ~30 ms; lista de vídeos chamava isso 6 mil vezes (10 s). Dentro de `with memo_curto():` o resultado
# vale até o bloco acabar (nunca entre pedidos, então criar cliente/modelo continua aparecendo na hora).
_memo = threading.local()


class memo_curto:
    def __enter__(self):
        self._antes = getattr(_memo, "d", None)
        if self._antes is None:
            _memo.d = {}
        return self

    def __exit__(self, *a):
        _memo.d = self._antes


def memoizado(fn):
    """Decorador: dentro de `memo_curto()` guarda o resultado por argumento (e por RAIZ, pros testes); fora dele chama sempre."""
    def _f(*args, **kw):
        d = getattr(_memo, "d", None)
        if d is None:
            return fn(*args, **kw)
        k = (fn.__module__, fn.__name__, str(RAIZ), args, tuple(sorted(kw.items())))
        if k not in d:
            d[k] = fn(*args, **kw)
        return d[k]
    _f.__name__, _f.__doc__, _f.__wrapped__ = fn.__name__, fn.__doc__, fn
    return _f


@memoizado
def clientes() -> list[dict]:
    out = []
    CLIENTES_DIR = RAIZ / "clientes"
    for d in sorted(CLIENTES_DIR.iterdir() if CLIENTES_DIR.is_dir() else [], key=lambda x: x.name.lower()):
        if not d.is_dir() or d.name.startswith((".", "_")) or d.name in IGNORAR_DIRS:
            continue
        content = _content_dir(d)
        if not content:
            continue
        mods = [m for m in sorted((content / "modelos").iterdir() if (content / "modelos").is_dir() else []) if m.is_dir() and not m.name.startswith((".", "_"))
                and any((m / n).exists() for n in ("README.md", "ficha.json", "gerar.sh")) or (m.is_dir() and any(m.glob("*.py")))]
        outs = list((content / "output").glob("*/*.mp4")) if (content / "output").is_dir() else []
        out.append({
            "nome": d.name, "pasta": d, "content": content, "content_nome": content.name,
            "modelos": [m.name for m in mods], "n_modelos": len(mods), "n_videos": len(outs),
        })
    return out


def cliente(nome: str) -> dict | None:
    for c in clientes():
        if c["nome"].lower() == nome.lower():
            return c
    return None


def _regras(pasta_modelo: Path) -> dict:
    return ler_json(pasta_modelo / "aprendizado" / "regras.json", {}) or {}


def modelo(cli: dict, nome_modelo: str) -> dict | None:
    if not cli or Path(nome_modelo).name != nome_modelo or nome_modelo in (".", ".."):
        return None
    pasta = cli["content"] / "modelos" / nome_modelo
    if not pasta.is_dir():
        return None
    mapa = mapa_claude_md()
    regras = _regras(pasta)
    historico = ler_jsonl(pasta / "aprendizado" / "historico.jsonl")
    readme = pasta / "README.md"
    outputs = sorted((cli["content"] / "output" / nome_modelo).glob("*.mp4"),
                     key=lambda p: p.stat().st_mtime, reverse=True) if (cli["content"] / "output" / nome_modelo).is_dir() else []
    scripts = sorted([p.name for p in pasta.iterdir()
                      if p.is_file() and p.suffix in (".sh", ".py", ".js", ".tsx", ".ts") and not p.name.startswith(".")])
    assets = []
    if (pasta / "assets").is_dir():
        for p in sorted((pasta / "assets").rglob("*")):
            if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in (".mp3", ".wav", ".png", ".jpg", ".jpeg", ".ttf", ".otf", ".mp4"):
                assets.append(str(p.relative_to(pasta / "assets")))
    sandboxes = sorted([p.name for p in pasta.iterdir() if p.is_dir() and p.name.startswith("_sandbox")])
    return {
        "nome": nome_modelo, "pasta": pasta, "cliente": cli["nome"],
        "readme": readme.read_text(encoding="utf-8") if readme.exists() else "",
        "regras": regras, "lista_regras": [
            {**r, "categoria": str(r.get("categoria") or "geral"),
             "peso": r.get("peso") if isinstance(r.get("peso"), (int, float)) else 5}
            for r in (regras.get("regras", []) or []) if isinstance(r, dict)
        ] if isinstance(regras, dict) else [],
        "historico": historico, "descricoes": mapa.get((cli["nome"], nome_modelo), []),
        "outputs": outputs, "scripts": scripts, "assets": assets, "sandboxes": sandboxes,
        "comando_referencia": regras.get("comando_referencia") if isinstance(regras, dict) else None,
    }


def modelos(cli: dict) -> list[dict]:
    return [m for m in (modelo(cli, n) for n in cli["modelos"]) if m]


# ───────────────────────── markdown mínimo ─────────────────────────

def md_para_html(md: str) -> str:
    """Conversor markdown → HTML sem dependências (títulos, listas, tabelas, código, negrito, links)."""
    linhas = md.splitlines()
    out, i = [], 0
    em_lista = None
    def fecha_lista():
        nonlocal em_lista
        if em_lista:
            out.append(f"</{em_lista}>")
            em_lista = None
    def inline(t: str) -> str:
        t = html.escape(t, quote=False)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        return t
    while i < len(linhas):
        l = linhas[i]
        if l.strip().startswith("```"):
            fecha_lista()
            bloco = []
            i += 1
            while i < len(linhas) and not linhas[i].strip().startswith("```"):
                bloco.append(linhas[i]); i += 1
            out.append("<pre><code>" + html.escape("\n".join(bloco)) + "</code></pre>")
            i += 1; continue
        if l.startswith("|") and i + 1 < len(linhas) and re.match(r"^\|[\s:|-]+\|?$", linhas[i + 1].strip()):
            fecha_lista()
            cab = [c.strip() for c in l.strip().strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cab) + "</tr></thead><tbody>")
            i += 2
            while i < len(linhas) and linhas[i].startswith("|"):
                cs = [c.strip() for c in linhas[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cs) + "</tr>")
                i += 1
            out.append("</tbody></table>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)", l)
        if m:
            fecha_lista()
            n = min(len(m.group(1)) + 1, 5)
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
        if l.strip().startswith(">"):
            fecha_lista()
            out.append(f"<blockquote>{inline(l.strip()[1:].strip())}</blockquote>"); i += 1; continue
        m = re.match(r"^\s*[-*]\s+(.*)", l)
        if m:
            if em_lista != "ul":
                fecha_lista(); out.append("<ul>"); em_lista = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>"); i += 1; continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)", l)
        if m:
            if em_lista != "ol":
                fecha_lista(); out.append("<ol>"); em_lista = "ol"
            out.append(f"<li>{inline(m.group(1))}</li>"); i += 1; continue
        if not l.strip():
            fecha_lista(); i += 1; continue
        fecha_lista()
        par = [l]
        i += 1
        while i < len(linhas) and linhas[i].strip() and not re.match(r"^(#{1,6}\s|\s*[-*]\s|\s*\d+[.)]\s|>|\||```)", linhas[i]):
            par.append(linhas[i]); i += 1
        out.append(f"<p>{inline(' '.join(p.strip() for p in par))}</p>")
    fecha_lista()
    return "\n".join(out)


# ───────────────────────── get-brolls ─────────────────────────

def gb_instalado() -> bool:
    return GB_PY.exists() and GB_CLI.exists()


def gb(args: list[str], timeout: int = 900) -> dict:
    """Roda `gb.py <args>` com a venv da skill e devolve o JSON."""
    if not gb_instalado():
        return {"erro": f"get-brolls não instalado em {GB_ROOT}. Rode: bash {GB_ROOT}/scripts/install.sh"}
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    r = subprocess.run([str(GB_PY), str(GB_CLI), *args], cwd=str(GB_ROOT),
                       capture_output=True, text=True, timeout=timeout, env=env)
    saida = (r.stdout or "").strip()
    try:
        i, j = saida.index("{"), saida.rindex("}")
        dados = json.loads(saida[i:j + 1])
    except Exception:
        dados = {"raw": saida}
    if r.returncode != 0:
        dados.setdefault("erro", (r.stderr or saida or "falha")[-2000:])
    dados["_stderr"] = (r.stderr or "")[-2000:]
    return dados


def gb_env() -> dict:
    """Chaves do b-roll (só pra saber se estão configuradas): app/.env primeiro, depois o .env da skill."""
    import chaves
    d = chaves.ler_env(GB_ENV)
    d.update({k: v for k, v in chaves.ler_env(ESTUDIO / ".env").items() if v and k in ("PEXELS_API_KEY", "PIXABAY_API_KEY")})
    return d


def gb_env_gravar(atualizacoes: dict) -> None:
    """Grava no app/.env (a fonte) e copia pro .env da skill, que ela lê quando roda sozinha."""
    import chaves
    chaves.gravar(ESTUDIO / ".env", atualizacoes)
    linhas = GB_ENV.read_text(encoding="utf-8").splitlines() if GB_ENV.exists() else []
    vistos = set()
    novas = []
    for l in linhas:
        if "=" in l and not l.strip().startswith("#"):
            k = l.split("=", 1)[0].strip()
            if k in atualizacoes:
                novas.append(f"{k}={atualizacoes[k]}"); vistos.add(k); continue
        novas.append(l)
    for k, v in atualizacoes.items():
        if k not in vistos:
            novas.append(f"{k}={v}")
    GB_ENV.write_text("\n".join(novas) + "\n", encoding="utf-8")


def claude_bin() -> str | None:
    """Binário real do claude (o alias do zsh não vale em subprocess)."""
    import shutil
    for cand in (shutil.which("claude"), Path.home() / ".npm-global" / "bin" / "claude",
                 Path.home() / ".claude" / "local" / "claude", Path.home() / ".local" / "bin" / "claude",
                 "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if cand and Path(cand).exists():
            return str(cand)
    return None


# ───────────────────────── lixeira do Estúdio ─────────────────────────
# Remover no Estúdio nunca apaga na hora: o que sai (modelo, asset) fica aqui até o João restaurar
# ou mandar apagar de vez. Guardar é MOVER — instantâneo, mesmo com .mp4 junto.

def lixeira_dir() -> Path:
    return ESTUDIO / ".lixeira"


def lixeira_guardar(caminhos: dict, info: dict) -> str:
    """Move cada {apelido: caminho} pra um item novo da lixeira e grava o `info.json` ao lado."""
    import shutil
    ident = f"{agora().replace(':', '').replace(' ', '-')}-{make_slug(info.get('rotulo') or info.get('tipo') or 'item')}"
    destino = lixeira_dir() / ident
    n = 2
    while destino.exists():
        destino = lixeira_dir() / f"{ident}-{n}"; n += 1
    ensure(destino)
    guardados = {}
    for apelido, origem in caminhos.items():
        origem = Path(origem)
        if not origem.exists():
            continue
        shutil.move(str(origem), str(destino / apelido))
        guardados[apelido] = origem.name
    gravar_json(destino / "info.json", {**info, "em": agora(), "guardados": guardados})
    return destino.name


def lixeira_item(ident: str) -> Path:
    if Path(ident).name != ident or ident in (".", ".."):
        raise ValueError("identificador inválido")
    d = lixeira_dir() / ident
    if not (d / "info.json").is_file():
        raise ValueError("item não encontrado na lixeira")
    return d


def lixeira_listar() -> list[dict]:
    base = lixeira_dir()
    if not base.is_dir():
        return []
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        info = ler_json(d / "info.json")
        if not info:
            continue
        arquivos = [p for p in d.rglob("*") if p.is_file() and p.name != "info.json"]
        info.update(id=d.name, arquivos=len(arquivos),
                    videos=sum(1 for p in arquivos if p.suffix.lower() in VIDEO_EXTS),
                    mb=round(sum(p.stat().st_size for p in arquivos) / 1e6, 1))
        out.append(info)
    return out


def lixeira_apagar(ident: str) -> bool:
    import shutil
    d = lixeira_item(ident)
    if d.resolve().parent != lixeira_dir().resolve():
        raise ValueError("caminho fora da lixeira")
    shutil.rmtree(d)
    return True


# ───────────────────────── cópia que não gasta espaço ─────────────────────────
# No APFS (o disco do Mac) `cp -c` faz um CLONE: outro nome pro mesmo conteúdo, que só ocupa espaço de novo se um dos dois
# mudar. Copiar bruto de 350 MB três vezes (upload → job → rascunho) custa 350 MB uma vez só. Fora do APFS (ou em outro
# volume) cai na cópia normal, então nada quebra.

def clonar(origem, destino) -> str:
    """Copia `origem` pra `destino` (arquivo) sem gastar espaço quando dá. Devolve "clone" ou "copia". Mantém as datas."""
    import shutil
    origem, destino = Path(origem), Path(destino)
    if destino.is_dir():
        destino = destino / origem.name
    destino.parent.mkdir(parents=True, exist_ok=True)
    if os.uname().sysname == "Darwin":
        try:
            if destino.exists() or destino.is_symlink():
                destino.unlink()
            r = subprocess.run(["cp", "-c", "-p", str(origem), str(destino)], capture_output=True, timeout=120)
            if r.returncode == 0 and destino.is_file() and destino.stat().st_size == origem.stat().st_size:
                return "clone"
            destino.unlink(missing_ok=True)
        except Exception:                      # qualquer falha do clone (sem cp, sem APFS...) cai na cópia normal
            pass
    destino.unlink(missing_ok=True) if destino.is_symlink() else None
    shutil.copy2(str(origem), str(destino))
    return "copia"


# ───────────────────────── hash com cache ─────────────────────────
# Saber se um arquivo do motor JÁ está no acervo é comparar conteúdo, não nome. Hashear 300MB a cada
# carregamento de página seria absurdo, então o resultado fica em cache por (caminho, mtime, tamanho).

def sha_arquivo(p: Path) -> str:
    import hashlib
    p = Path(p)
    st = p.stat()
    cache_p = CACHE / "hashes.json"
    cache = ler_json(cache_p, {}) or {}
    chave = str(p)
    guardado = cache.get(chave)
    if guardado and guardado.get("mtime") == int(st.st_mtime) and guardado.get("tamanho") == st.st_size:
        return guardado["sha"]
    h = hashlib.sha256()
    with p.open("rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    cache[chave] = {"mtime": int(st.st_mtime), "tamanho": st.st_size, "sha": h.hexdigest()}
    ensure(CACHE)
    gravar_json(cache_p, cache)
    return cache[chave]["sha"]


def _norm(s: str) -> str:
    """Texto sem acento, minúsculo, só letras/números/espaço (pra comparar fala com roteiro). Usado por fala.py e corte.py."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


MSG_GROQ_LIMITE = "A transcrição (Groq) está no limite agora. Espere 1 minuto e clique de novo."
_ERROS_SIMPLES = [
    (("entity too large", "request entity", "413"), "O áudio é grande demais pra transcrever de uma vez."),
    (("rate_limit", "rate limit", "429", "limite agora"), MSG_GROQ_LIMITE),
    (("no space left",), "Falta espaço no disco."),
    (("could not resolve host", "connection refused", "connection reset", "connection error", "network is unreachable"),
     "Sem internet agora."),
    (("invalid data found", "moov atom"), "O vídeo está corrompido ou incompleto: envie de novo."),
    (("no such file",), "Um arquivo sumiu no meio (foi movido ou apagado)."),
    (("permission denied",), "Sem permissão pra ler o arquivo."),
]


def erro_simples(txt) -> str:
    """Erro técnico (inglês, stderr do ffmpeg, JSON do Groq) vira uma frase curta em português.
    Mensagem que já está em português passa direto; o original fica no log de quem chamou."""
    t = str(txt or "")
    baixo = t.lower()
    for chaves, msg in _ERROS_SIMPLES:
        if any(c in baixo for c in chaves):
            return msg
    if re.search(r"[ãõçáéíóúâêô]|\b(de|do|da|para|pra|antes|suas|seus|uma|com|que|foi|ou|salve|escolha|vídeo|arquivo)\b", baixo):
        return t
    return "Algo deu errado nesta etapa. Clique em Tentar de novo."


def texto_fila(cli, slug, base="Na fila, esperando a vez"):
    """"Na fila: é o 3º (antes dele: 2 vídeos)"; sem posição conhecida devolve o texto base."""
    try:
        import fila
        n = fila.posicao(cli, slug)
    except Exception:
        return base
    if n <= 1:
        return "Na fila: é o próximo" if n == 1 else base
    return f"Na fila: é o {n}º (antes dele: {n - 1} vídeos)"
