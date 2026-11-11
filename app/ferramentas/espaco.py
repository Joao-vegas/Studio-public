#!/usr/bin/env python3
"""
espaco — o disco do Estúdio: nada de gravação repetida, apagar de verdade e liberar espaço.

1. `desduplicar`: arquivos de mídia grandes IDÊNTICOS (mesmo tamanho e mesmo hash) viram clones do APFS do mais importante
   (`cp -c`): o conteúdo continua em todo lugar, mas o espaço é gasto uma vez só.
2. `para_lixeira_mac`: apagar um vídeo (ou liberar espaço) MOVE pra Lixeira do Mac (`~/.Trash/<título>-<data>/...`), que o
   João recupera pelo Finder; o espaço só volta quando ele esvazia a Lixeira.
3. `itens_liberaveis` / `liberar`: a tela "Liberar espaço" (/espaco): o que dá pra tirar sem perder o vídeo pronto.
   NUNCA entram: vídeo pronto (output), editor/versoes, cenas.json/PLANO/roteiro, aprendizado.

Linha de comando:  espaco.py desduplicar [--aplicar] | espaco.py itens | espaco.py tamanho <cliente> <slug>
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import VIDEO_EXTS, agora, gravar_json, ler_json, make_slug  # noqa: E402

RAIZ_REAL = Path(__file__).resolve().parent.parent.parent
MIDIA = VIDEO_EXTS | {".wav", ".m4a", ".mp3", ".aac", ".flac"}
IMAGEM = {".jpg", ".jpeg", ".png", ".webp"}
IGNORA = {".git", "node_modules", ".venv", "__pycache__", ".cache"}
RECENTE_S = 30 * 60          # arquivo mexido há menos que isso pode estar em uso: não entra
RECENTE_CLONE_S = 120
ENTREGUE = {"concluido", "aprovado", "exportado", "arquivado", "finalizado"}
EDITADO_S = 7 * 86400         # vídeo editado há menos que isso (ou esperando o João) nunca é oferecido
AVISO_VIDEO = "Depois disso, este vídeo não dá mais pra editar nem refazer; o vídeo pronto continua."
# subpastas de um rascunho (sandbox) que são só conferência/prévia: sem custo nenhum de tirar
CACHES = {"quadros", "qa", "frames", "folhas", "previa", "previas", "thumbs", "mini", "miniaturas", "miniatura"}
# nunca vão: editor (versões e miniaturas das cenas), o que o vídeo lembra de si mesmo e o aprendizado
INTOCAVEL = {"editor", "versoes", "aprendizado", "bruto", "work", ".git"}


def raiz() -> Path:
    return Path(_comum.RAIZ).resolve()


def fmt_bytes(n: float) -> str:
    n = float(n or 0)
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB".replace(".", ",")
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.0f} KB"
    return f"{int(n)} B"


# ───────────────────────── medir ─────────────────────────

def tamanho(p: Path) -> int:
    """Bytes do arquivo ou da pasta (sem seguir atalho). Cada arquivo conta pelo tamanho cheio (clone conta como cópia)."""
    p = Path(p)
    try:
        if p.is_symlink():
            return 0
        if p.is_file():
            return p.stat().st_size
        total = 0
        for dp, dns, fns in os.walk(p):
            dns[:] = [d for d in dns if not os.path.islink(os.path.join(dp, d))]
            for f in fns:
                try:
                    st = os.lstat(os.path.join(dp, f))
                    if stat.S_ISREG(st.st_mode):
                        total += st.st_size
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _mexido_ha(p: Path) -> float:
    try:
        return time.time() - p.stat().st_mtime
    except OSError:
        return 1e9


def _sha(p: str | Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(4 << 20), b""):
            h.update(ch)
    return h.hexdigest()


# ───────────────────────── 1. desduplicar (clone APFS) ─────────────────────────

def _grandes(base: Path, minimo: int):
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in IGNORA]
        for f in fns:
            if Path(f).suffix.lower() not in MIDIA:
                continue
            p = os.path.join(dp, f)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_size >= minimo:
                yield p, st


def _prioridade(item) -> tuple:
    p, st = item
    pri = 0 if ("/output/" in p or "/formatos/" in p or "/acervo/" in p) else 1
    return (pri, st.st_mtime_ns, len(p))


def _marca_arq() -> Path:
    return Path(_comum.ESTUDIO) / ".cache" / "desduplicado.json"


def duplicados(base: Path | None = None, minimo: int = 20_000_000) -> list[dict]:
    """Grupos de arquivos de mídia idênticos: [{tamanho, original, copias:[...]}]. Só hasheia o que tem o mesmo tamanho."""
    base = Path(base or raiz())
    por_tam: dict[int, list] = {}
    for p, st in _grandes(base, minimo):
        por_tam.setdefault(st.st_size, []).append((p, st))
    marcas = ler_json(_marca_arq(), {}) or {}
    grupos = []
    for tam, lst in por_tam.items():
        if len(lst) < 2:
            continue
        por_sha: dict[str, list] = {}
        for p, st in lst:
            por_sha.setdefault(_sha(p), []).append((p, st))
        for sha, g in por_sha.items():
            if len(g) < 2:
                continue
            g.sort(key=_prioridade)
            orig, resto = g[0], g[1:]
            # já virou clone num passe anterior (mesma data e tamanho gravados): não conta de novo
            novas = [(p, st) for p, st in resto if marcas.get(p) != f"{st.st_mtime_ns}:{st.st_size}"]
            grupos.append({"tamanho": tam, "sha": sha, "original": orig[0], "copias": [p for p, _ in novas],
                           "_orig": orig, "_novas": novas, "ja_clone": len(resto) - len(novas)})
    return grupos


def desduplicar(aplicar: bool = False, base: Path | None = None, minimo: int = 20_000_000) -> dict:
    """Troca cada cópia idêntica por um clone do original (nada é apagado: o conteúdo é o mesmo). Sem `aplicar` só mede.
    Devolve {grupos, copias, bytes (que voltam), feitos, erros, livre_antes, livre_depois}."""
    base = Path(base or raiz())
    antes = shutil.disk_usage(base).free
    grupos = duplicados(base, minimo)
    r = {"grupos": 0, "copias": 0, "bytes": 0, "feitos": 0, "erros": [], "pulados": [], "livre_antes": antes, "livre_depois": antes}
    marcas = ler_json(_marca_arq(), {}) or {}
    for g in grupos:
        if not g["copias"]:
            continue
        r["grupos"] += 1
        r["copias"] += len(g["copias"])
        r["bytes"] += g["tamanho"] * len(g["copias"])
        if not aplicar:
            continue
        orig, st_o = g["_orig"]
        if time.time() - st_o.st_mtime < RECENTE_CLONE_S:
            r["pulados"].append(orig)
            continue
        for p, st in g["_novas"]:
            if time.time() - st.st_mtime < RECENTE_CLONE_S:
                r["pulados"].append(p)
                continue
            tmp = p + ".clone-tmp"
            try:
                c = subprocess.run(["cp", "-c", "-p", orig, tmp], capture_output=True, timeout=300)
                if c.returncode != 0 or os.path.getsize(tmp) != g["tamanho"]:
                    raise OSError((c.stderr or b"").decode(errors="replace").strip() or "cp -c falhou (disco não é APFS?)")
                novo = os.lstat(p)           # o arquivo continua como foi hasheado?
                if novo.st_mtime_ns != st.st_mtime_ns or novo.st_size != st.st_size:
                    raise OSError("mudou durante a conferência")
                os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
                os.chmod(tmp, stat.S_IMODE(st.st_mode))
                os.replace(tmp, p)
                marcas[p] = f"{st.st_mtime_ns}:{st.st_size}"
                r["feitos"] += 1
            except OSError as e:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                r["erros"].append(f"{p}: {e}")
    if aplicar:
        gravar_json(_marca_arq(), marcas)
    r["livre_depois"] = shutil.disk_usage(base).free
    return r


# ───────────────────────── 2. Lixeira do Mac ─────────────────────────

def lixeira_mac() -> Path:
    """~/.Trash. Em teste (RAIZ trocada) ou com ESTUDIO_LIXEIRA_MAC, vai pra outra pasta: teste nunca mexe na Lixeira do João."""
    env = os.environ.get("ESTUDIO_LIXEIRA_MAC")
    if env:
        return Path(env)
    if raiz() != RAIZ_REAL.resolve():
        return raiz() / ".Trash-teste"
    return Path.home() / ".Trash"


def _dentro(p: Path) -> bool:
    """O caminho está dentro do Estúdio e nenhum pedaço dele é atalho (nunca mando atalho nem coisa de fora pra Lixeira)."""
    q = Path(os.path.abspath(p))
    try:
        q.relative_to(raiz())
    except ValueError:
        return False
    return not q.is_symlink() and q.resolve() == q


def para_lixeira_mac(caminhos: list, titulo: str) -> dict:
    """Move cada caminho (arquivo ou pasta do Estúdio) pra `~/.Trash/<título>-<data>/<caminho relativo ao Estúdio>`.
    Devolve {pasta, nome, itens, bytes}. Levanta ValueError se algum caminho for de fora ou atalho; nada some antes disso."""
    caminhos = [Path(os.path.abspath(c)) for c in dict.fromkeys(caminhos or [])]
    for c in caminhos:
        if not _dentro(c):
            raise ValueError(f"{c.name}: fora do Estúdio ou atalho, não mexo")
    caminhos = [c for c in caminhos if c.exists()]
    base = lixeira_mac()
    nome = f"{make_slug(titulo or 'estudio', 50) or 'estudio'}-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    dest, n = base / nome, 2
    while dest.exists():
        dest = base / f"{nome}-{n}"; n += 1
    bytes_ = sum(tamanho(c) for c in caminhos)
    movidos = 0
    rels, fora = [], []
    try:
        dest.mkdir(parents=True)
        for c in caminhos:
            alvo = dest / c.relative_to(raiz())
            alvo.parent.mkdir(parents=True, exist_ok=True)
            os.rename(c, alvo)               # mesmo disco: instantâneo, mesmo com vídeo de 1 GB
            rels.append(str(c.relative_to(raiz())))
            movidos += 1
    except OSError as e:
        for c in caminhos[movidos:]:         # sem permissão na Lixeira: pede pro Finder (ele tem)
            if not c.exists():
                continue
            if not _finder_apaga(c):
                raise ValueError(f"não consegui mandar pra Lixeira do Mac ({e}). Dê acesso ao disco pro Terminal ou apague pelo Finder: {c}")
            fora.append(str(c.relative_to(raiz())))      # foi solto na Lixeira, sem a nossa pasta: o Desfazer não sabe onde está
    return {"pasta": str(dest), "nome": dest.name, "itens": len(caminhos), "bytes": bytes_, "rels": rels, "fora": fora}


def _finder_apaga(p: Path) -> bool:
    try:
        r = subprocess.run(["/usr/bin/trash", str(p)], capture_output=True, timeout=120)
        if r.returncode == 0 and not p.exists():
            return True
        r = subprocess.run(["osascript", "-e", f'tell application "Finder" to delete POSIX file "{p}"'], capture_output=True, timeout=120)
        return r.returncode == 0 and not p.exists()
    except (OSError, subprocess.SubprocessError):
        return False


# ───────────────────────── desfazer a última limpeza (manifesto + Finder) ─────────────────────────
# O Terminal NÃO lê ~/.Trash (privacidade do macOS), mas o Finder lê e move. Por isso toda leitura e devolução passa por ele.

_AS_LISTAR = (
    'on run argv', 'tell application "Finder"',
    'set f to (POSIX file (item 1 of argv)) as alias', 'set ns to name of every item of f', 'set cs to class of every item of f',
    'end tell', 'set out to ""', 'repeat with k from 1 to count of ns', 'set t to "f"',
    'if ((item k of cs) as text) is "folder" then set t to "d"', 'set out to out & t & tab & (item k of ns) & linefeed',
    'end repeat', 'return out', 'end run')
_AS_MOVER = ('on run argv', 'tell application "Finder"',
             'move (POSIX file (item 1 of argv) as alias) to (POSIX file (item 2 of argv) as alias)', 'end tell', 'end run')
_AS_TAMANHO = ('on run argv', 'tell application "Finder" to get size of (POSIX file (item 1 of argv) as alias)', 'end run')


def _osa(linhas: tuple, *args) -> str | None:
    cmd = ["osascript"] + [x for l in linhas for x in ("-e", l)] + [str(a) for a in args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _finder_listar(pasta: Path) -> list[tuple[str, bool]] | None:
    """[(nome, é_pasta)] do que o Finder vê dentro de `pasta` (um nível só). None = não conseguiu (sumiu, ou não é pasta)."""
    out = _osa(_AS_LISTAR, pasta)
    if out is None:
        return None
    return [(l[2:], l[0] == "d") for l in out.split("\n") if len(l) > 2 and l[1] == "\t"]


def _finder_mover(origem: Path, pasta_destino: Path) -> bool:
    """O Finder move `origem` pra dentro de `pasta_destino` (mantém o nome; nunca troca o que já existe lá)."""
    return _osa(_AS_MOVER, origem, pasta_destino) is not None


def _finder_tamanho(p: Path) -> int:
    out = _osa(_AS_TAMANHO, p)
    try:
        return int(float((out or "0").strip().replace(",", ".")))
    except ValueError:
        return 0


def _pasta_limpezas() -> Path:
    return Path(_comum.ESTUDIO) / ".cache" / "limpezas"


def gravar_manifesto(pasta: str | Path, caminhos: list[str], bytes_: int = 0, itens: int | None = None, nome: str = "") -> Path:
    """Guarda o que uma limpeza levou: a pasta da Lixeira e os caminhos relativos ao Estúdio, pra devolver depois."""
    pasta = Path(pasta)
    m = {"criado": agora(), "pasta": str(pasta), "nome": nome or pasta.name, "caminhos": list(caminhos), "bytes": int(bytes_),
         "itens": len(caminhos) if itens is None else itens, "desfeito": None}
    d = _pasta_limpezas()
    d.mkdir(parents=True, exist_ok=True)
    arq = d / (re.sub(r"^liberar-espaco-", "", pasta.name) + ".json")
    gravar_json(arq, m)
    return arq


def manifesto_legado(pasta: str | Path) -> Path:
    """Limpeza antiga, sem manifesto: monta um a partir do que o Finder lista dentro da pasta da Lixeira. NÃO devolve nada."""
    pasta = Path(pasta)
    filhos = _finder_listar(pasta)
    if filhos is None:
        raise ValueError(f"O Finder não achou a pasta {pasta}. Ela ainda está na Lixeira?")
    arq = gravar_manifesto(pasta, [n for n, _ in filhos], bytes_=_finder_tamanho(pasta), itens=_contar_finder(pasta))
    m = ler_json(arq, {})
    q = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})(\d{2})$", pasta.name)
    if q:                                                  # a hora da limpeza vem do nome da pasta, não de agora
        m["criado"] = f"{q.group(1)} {q.group(2)}:{q.group(3)}:{q.group(4)}"
    m["itens_aprox"] = m["itens"] >= 4000
    gravar_json(arq, m)
    return arq


def _contar_finder(pasta: Path, limite: int = 4000) -> int:
    """Quantos arquivos o Finder vê dentro da pasta (desce pelas subpastas; para no limite)."""
    n, fila = 0, [pasta]
    while fila and n < limite:
        atual = fila.pop()
        for nome, eh_pasta in _finder_listar(atual) or []:
            if eh_pasta:
                fila.append(atual / nome)
            else:
                n += 1
    return n


def limpezas() -> list[dict]:
    """Os manifestos, do mais novo pro mais velho (cada um com `arquivo`)."""
    out = []
    for f in sorted(_pasta_limpezas().glob("*.json"), reverse=True):
        m = ler_json(f, None)
        if isinstance(m, dict) and m.get("pasta"):
            out.append({**m, "arquivo": f.name})
    return out


def ultima_limpeza() -> dict | None:
    """A última limpeza que ainda dá pra desfazer (com o tamanho e a data em português pra tela)."""
    for m in limpezas():
        if not m.get("desfeito"):
            m["quando"] = str(m.get("criado", ""))[:16].replace("T", " ")
            m["tamanho"] = fmt_bytes(m.get("bytes") or 0)
            return m
    return None


def _devolver(pasta: Path, rel: str, r: dict) -> None:
    """Devolve `<pasta>/<rel>` pro mesmo lugar no Estúdio. Lugar livre: o Finder move tudo de uma vez. Pasta com pasta: junta, sem
    substituir nada do que já existe."""
    destino = raiz() / rel
    if ".." in Path(rel).parts or not _dentro(destino):
        r["ignorados"] += 1
        return
    origem = pasta / rel
    if not os.path.lexists(destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        if _finder_mover(origem, destino.parent):
            r["devolvidos"] += 1
        else:
            r["sumiram"] += 1           # já não está na Lixeira (devolvido à mão ou esvaziada)
    elif destino.is_dir() and not destino.is_symlink():
        filhos = _finder_listar(origem)
        if filhos is None:
            r["sumiram"] += 1
            return
        for nome, _ in filhos:
            _devolver(pasta, f"{rel}/{nome}", r)
    else:
        r["ficaram"] += 1               # já existe um arquivo no lugar: fica na Lixeira, nada é trocado


def desfazer_limpeza(arquivo: str = "") -> dict:
    """Devolve ao Estúdio o que a última limpeza (ou a do manifesto `arquivo`) levou. Marca o manifesto como desfeito."""
    alvo = None
    for m in limpezas():
        if (arquivo and m["arquivo"] == Path(arquivo).name) or (not arquivo and not m.get("desfeito")):
            alvo = m
            break
    if not alvo:
        raise ValueError("Não tem limpeza pra desfazer.")
    pasta = Path(alvo["pasta"])
    r = {"devolvidos": 0, "ficaram": 0, "sumiram": 0, "ignorados": 0}
    for rel in alvo["caminhos"]:
        _devolver(pasta, rel, r)
    arq = _pasta_limpezas() / alvo["arquivo"]
    m = ler_json(arq, {}) or {}
    m["desfeito"] = agora()
    m["resultado"] = r
    gravar_json(arq, m)
    return {**r, "nome": alvo["nome"]}


# ───────────────────────── o que pertence a um vídeo (uploads e corte do bruto) ─────────────────────────

def uploads_do_video(jobs: list[dict]) -> list[Path]:
    """Arquivos de app/.uploads que são o bruto deste vídeo: mesmo nome ou mesmo conteúdo (tamanho + hash) do bruto do job."""
    pasta = Path(_comum.ESTUDIO) / ".uploads"
    if not pasta.is_dir():
        return []
    brutos = []
    for j in jobs:
        b = j.get("bruto")
        if b and Path(b).suffix.lower() in MIDIA:
            q = raiz() / b
            brutos.append(q)
    out = []
    for u in sorted(pasta.iterdir()):
        if not u.is_file() or u.is_symlink() or _mexido_ha(u) < RECENTE_S:
            continue
        for b in brutos:
            try:
                if b.name == u.name or (b.is_file() and b.stat().st_size == u.stat().st_size and _sha(b) == _sha(u)):
                    out.append(u)
                    break
            except OSError:
                continue
    return out


def corte_do_video(jobs: list[dict], todos_os_jobs: list[dict]) -> list[Path]:
    """app/cortes/<id> que este vídeo usou (job.corte_id), se nenhum outro vídeo usa o mesmo."""
    out = []
    quem = {(j.get("cliente"), j.get("slug")) for j in jobs}
    for j in jobs:
        cid = str(j.get("corte_id") or "")
        if not cid or Path(cid).name != cid or cid in (".", ".."):
            continue
        outro = any(o.get("corte_id") == cid and (o.get("cliente"), o.get("slug")) not in quem for o in todos_os_jobs)
        d = Path(_comum.ESTUDIO) / "cortes" / cid
        if not outro and d.is_dir():
            out.append(d)
    return out


def pecas_extras(jobs: list[dict]) -> list[tuple[str, Path]]:
    todos = []
    for x in (Path(_comum.JOBS)).glob("*/*/job.json"):
        j = ler_json(x, {}) or {}
        todos.append(j)
    return [("uploads", p) for p in uploads_do_video(jobs)] + [("corte", p) for p in corte_do_video(jobs, todos)]


# ───────────────────────── 3. Liberar espaço ─────────────────────────

def _jobs_index() -> dict:
    idx = {}
    for x in Path(_comum.JOBS).glob("*/*/job.json"):
        j = ler_json(x, {}) or {}
        if isinstance(j, dict):
            idx[(x.parent.parent.name, x.parent.name)] = {**j, "_pasta": x.parent}
    return idx


def _vivo(pid_file: Path) -> bool:
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
        return True
    except Exception:
        return False


def _saidas_prontas() -> dict:
    """{cliente: [(Path do mp4, tamanho)]} de clientes/<C>/*Content/output/**.mp4."""
    out = {}
    for cdir in (raiz() / "clientes").glob("*"):
        lst = []
        for o in cdir.glob("*Content/output"):
            for dp, dns, fns in os.walk(o):
                for f in fns:
                    if f.lower().endswith((".mp4", ".mov")):
                        p = Path(dp) / f
                        try:
                            lst.append((p, p.stat().st_size))
                        except OSError:
                            pass
        out[cdir.name] = lst
    return out


EXPLICA_ITEM = {   # o que é cada item da tela Liberar espaço, em português simples (o painel mostra junto da prévia)
    "work": "Trechos, quadros e áudio de trabalho: o Estúdio refaz se precisar. O vídeo pronto continua.",
    "quadros": "Quadros e folhas de conferência: só serviam pra checar o vídeo. O vídeo pronto continua.",
    "material": "Clipes, fotos, recortes e prints usados no vídeo. O vídeo pronto continua; refazer o vídeo vai precisar buscar de novo.",
    "copia-final": "Uma cópia do vídeo pronto que sobrou dentro do rascunho. O original continua em output.",
    "bruto": "A gravação original deste vídeo. O vídeo pronto continua, mas sem ela não dá pra refazer o corte.",
    "upload": "Arquivo que você enviou pelo Estúdio. Se já entrou num vídeo, o vídeo guarda a cópia dele.",
    "lixeira": "Coisa que você já tirou do Estúdio. Depois disso o Restaurar de Configurações não acha mais; só a Lixeira do Mac.",
}


def _item(id_tipo: str, rotulo: str, caminhos: list[Path], aviso: str = "", marcado: bool = True, nota: str = "") -> dict | None:
    caminhos = [Path(c) for c in caminhos if Path(c).exists()]
    b = sum(tamanho(c) for c in caminhos)
    if not caminhos or b < 1_000_000:       # menos de 1 MB não vale uma linha na tela
        return None
    rels = [str(Path(os.path.abspath(c)).relative_to(raiz())) for c in caminhos]
    chave = hashlib.sha1((id_tipo + "|" + "|".join(rels)).encode()).hexdigest()[:12]
    return {"id": chave, "tipo": id_tipo, "rotulo": rotulo, "caminhos": rels, "bytes": b, "tamanho": fmt_bytes(b),
            "aviso": aviso, "marcado": marcado, "nota": nota, "explica": EXPLICA_ITEM.get(id_tipo, "")}


def _arquivos_de_trabalho(work: Path) -> list[Path]:
    """Dentro de work/: pastas e arquivos de mídia/imagem (trechos, quadros, áudio). Json e texto (words, CORTE, PLANO) ficam."""
    out = []
    for q in sorted(work.iterdir()):
        if q.is_symlink():
            continue
        if q.is_dir() or q.suffix.lower() in MIDIA | IMAGEM:
            out.append(q)
    return out


def _sandbox_itens(sb: Path, cli: str, saidas_cli: list, job: dict | None) -> list[dict]:
    itens = []
    work = sb / "work"
    if work.is_dir() and not work.is_symlink():
        it = _item("work", "Trechos, quadros e áudio de trabalho", _arquivos_de_trabalho(work),
                   aviso=AVISO_VIDEO)
        if it:
            itens.append(it)
    caches, material = [], []
    for q in sorted(sb.iterdir()):
        if q.is_symlink() or q.name in INTOCAVEL:
            continue
        if q.is_dir():
            (caches if q.name.lower() in CACHES else material).append(q)
        elif q.suffix.lower() in IMAGEM | {".m4a", ".mp3", ".wav"} and re.match(r"^(storyboard|previa|sb[-_\d]|folha|mini)", q.name.lower()):
            caches.append(q)
    it = _item("quadros", "Quadros e conferências (prévias do vídeo)", caches, aviso=AVISO_VIDEO)
    if it:
        itens.append(it)
    it = _item("material", "Material do vídeo (clipes, fotos, recortes, prints)", material, aviso=AVISO_VIDEO)
    if it:
        itens.append(it)
    # cópia do vídeo final dentro do rascunho: igual a um que já está em output/
    copias = []
    for q in sorted(sb.iterdir()):
        if q.is_file() and not q.is_symlink() and q.suffix.lower() in VIDEO_EXTS and _mexido_ha(q) > RECENTE_S:
            try:
                tam = q.stat().st_size
                if any(t == tam and str(p) != str(q) and _sha(p) == _sha(q) for p, t in saidas_cli):
                    copias.append(q)
            except OSError:
                pass
    it = _item("copia-final", "Cópia do vídeo pronto dentro do rascunho (o pronto fica em output)", copias,
               aviso="Nada muda: o vídeo pronto e a edição continuam.")
    if it:
        itens.append(it)
    bruto = sb / "bruto"
    it = _item("bruto", "A gravação original (bruto/)", [bruto] if bruto.is_dir() and not bruto.is_symlink() else [],
               aviso=AVISO_VIDEO + " É o seu bruto: só libere se tem a gravação em outro lugar.", marcado=False)
    if it:
        itens.append(it)
    return itens


def _esperando_aprovacao() -> set:
    """(cliente, slug) dos vídeos que esperam o João (lotes.esperando) ou que a tela ainda mostra como esperando/pronto pra assistir.
    Se alguma leitura falhar, a outra continua valendo; nunca o contrário."""
    achados = set()
    try:
        import lotes
        achados |= {(i["cliente"], i["slug"]) for i in lotes.esperando() if i.get("cliente") and i.get("slug")}
    except Exception:
        pass
    try:
        import andamento as _and
        achados |= {(d["cliente"], d["slug"]) for d in _and.registros() if d.get("estado") in ("esperando", "pronto") and not d.get("oculto")}
    except Exception:
        pass
    return achados


def _editado_ha(sb: Path, job: dict | None, d: dict | None) -> float:
    """Segundos desde a última mexida de verdade no vídeo: rascunho, work, editor/versoes, cenas/PLANO, job, vídeo pronto, registro."""
    alvos = [sb, sb / "work", sb / "editor", sb / "editor" / "versoes", sb / "cenas.json", sb / "PLANO.json"]
    if job:
        alvos.append(job["_pasta"] / "job.json")
        if job.get("saida"):
            alvos.append(raiz() / job["saida"])
    melhor = min(_mexido_ha(a) for a in alvos)
    try:
        import andamento as _and
        if d and d.get("atualizado"):
            melhor = min(melhor, _and._min_desde(d["atualizado"]) * 60)
    except Exception:
        pass
    return melhor


def itens_liberaveis() -> dict:
    """Tudo que a tela mostra: {grupos: [{nome, videos: [{titulo, itens}], bytes}], total, marcado}."""
    jobs = _jobs_index()
    saidas = _saidas_prontas()
    import andamento as _and
    ands = {(d.get("cliente"), d.get("slug")): d for d in _and.registros()}
    aprovando = _esperando_aprovacao()
    bruto_protegido: set[str] = set()                     # uploads de vídeos protegidos também ficam
    grupos: dict[str, list] = {}
    base = raiz()
    for sb in sorted(base.glob("clientes/*/*Content/modelos/*/_sandbox-*")):
        if sb.is_symlink() or not sb.is_dir():
            continue
        cli = sb.relative_to(base).parts[1]
        slug = sb.name[len("_sandbox-"):]
        job = jobs.get((cli, slug))
        if job and job.get("sandbox") and Path(os.path.abspath(base / job["sandbox"])) != Path(os.path.abspath(sb)):
            job = None
        if job:
            s = job.get("saida")
            if not (s and (base / s).is_file() and job.get("status") in ENTREGUE):
                continue                                  # ainda em produção ou sem vídeo pronto: não é daqui
            if _vivo(job["_pasta"] / "runner.pid"):
                continue
        pronto = True
        if not job:
            pronto = any(re.fullmatch(re.escape(slug) + r"(-v\d+)?", p.stem) for p, _ in saidas.get(cli, [])) \
                or any(q.is_file() and q.suffix.lower() in VIDEO_EXTS and q.stat().st_size > 5_000_000 and _mexido_ha(q) > 86400
                       for q in sb.iterdir())          # o vídeo final fica dentro do rascunho (documentário, anúncios)
            if not pronto and _mexido_ha(sb) < 3 * 86400:
                continue                                  # sem vídeo pronto e mexido há pouco: pode estar em uso
        d = ands.get((cli, slug))
        if d and _and.esta_trabalhando(d):
            continue
        if (cli, slug) in aprovando or _editado_ha(sb, job, d) < EDITADO_S:
            if job and job.get("bruto"):
                bruto_protegido.add(Path(job["bruto"]).name)
            continue                                      # espera o João ou foi editado esta semana: ainda precisa da mídia
        if min(_mexido_ha(sb), _mexido_ha(sb / "work") if (sb / "work").exists() else 1e9) < RECENTE_S:
            continue
        its = _sandbox_itens(sb, cli, saidas.get(cli, []), job)
        if not pronto:                                    # parado há dias e sem vídeo pronto achado: oferece, mas desmarcado
            for it in its:
                it["marcado"] = False
                it["aviso"] = ("Não achei o vídeo pronto desse rascunho. " + it["aviso"]).strip()
        if its:
            titulo = (job or {}).get("titulo") or (d or {}).get("titulo") or slug
            grupos.setdefault(cli, []).append({"titulo": titulo, "slug": slug, "modelo": sb.parent.name, "itens": its})
    # envios (app/.uploads): o que já entrou num vídeo e o que nunca entrou
    ups = _itens_uploads(jobs, bruto_protegido)
    if ups:
        grupos.setdefault("Envios (app/.uploads)", []).append({"titulo": "Arquivos que você enviou", "slug": "", "modelo": "", "itens": ups})
    lix = _itens_lixeira()
    if lix:
        grupos.setdefault("Lixeira do Estúdio (app/.lixeira)", []).append({"titulo": "Itens que você já tirou", "slug": "", "modelo": "", "itens": lix})
    saida = []
    total = marcado = 0
    for nome, vids in grupos.items():
        b = sum(i["bytes"] for v in vids for i in v["itens"])
        m = sum(i["bytes"] for v in vids for i in v["itens"] if i["marcado"])
        for v in vids:
            v["bytes"] = sum(i["bytes"] for i in v["itens"]); v["tamanho"] = fmt_bytes(v["bytes"])
        saida.append({"nome": nome, "videos": vids, "bytes": b, "tamanho": fmt_bytes(b)})
        total += b; marcado += m
    saida.sort(key=lambda g: -g["bytes"])
    return {"grupos": saida, "total": total, "total_txt": fmt_bytes(total), "marcado": marcado, "marcado_txt": fmt_bytes(marcado)}


def _itens_uploads(jobs: dict, protegidos: set = frozenset()) -> list[dict]:
    pasta = Path(_comum.ESTUDIO) / ".uploads"
    if not pasta.is_dir():
        return []
    # onde o conteúdo já vive: bruto/work de rascunhos e originais de corte (só por tamanho + hash)
    vivos: dict[int, list] = {}
    for padrao in ("clientes/*/*Content/modelos/*/_sandbox-*/bruto/*", "clientes/*/*Content/modelos/*/_sandbox-*/work/joao.mp4",
                   "app/cortes/*/original.*"):
        for p in raiz().glob(padrao):
            if p.is_file() and p.suffix.lower() in MIDIA:
                vivos.setdefault(p.stat().st_size, []).append(p)
    nomes = {Path(j.get("bruto") or "").name for j in jobs.values()}
    out = []
    for u in sorted(pasta.iterdir()):
        if u.is_symlink() or _mexido_ha(u) < RECENTE_S or u.name in protegidos:
            continue
        if u.is_file():
            usado = u.name in nomes
            if not usado and u.stat().st_size in vivos:
                h = _sha(u)
                usado = any(_sha(p) == h for p in vivos[u.stat().st_size])
        else:
            usado = False
        it = _item("upload", ("Já usado num vídeo: " if usado else "Ainda não entrou em nenhum vídeo: ") + u.name, [u],
                   aviso="" if usado else "Confira antes: pode ser um vídeo que você ainda vai usar.", marcado=usado)
        if it:
            out.append(it)
    return out


def _itens_lixeira() -> list[dict]:
    out = []
    for x in _comum.lixeira_listar():
        d = _comum.lixeira_dir() / x["id"]
        it = _item("lixeira", f"{x.get('rotulo') or x['id']} ({x.get('tipo') or 'item'}, tirado em {str(x.get('em') or '')[:10]})", [d],
                   aviso="Depois disso o Restaurar de Configurações não acha mais; só pela Lixeira do Mac.")
        if it:
            out.append(it)
    return out


def liberar(ids: list[str]) -> dict:
    """Manda pra Lixeira do Mac os itens marcados. Os caminhos vêm do scan de agora (nunca do que o navegador mandou)."""
    ids = {str(i) for i in ids or []}
    if not ids:
        raise ValueError("Marque pelo menos uma coisa.")
    achados = []
    for g in itens_liberaveis()["grupos"]:
        for v in g["videos"]:
            for it in v["itens"]:
                if it["id"] in ids:
                    achados.append(it)
    if not achados:
        raise ValueError("Esses itens mudaram ou já saíram. Atualize a tela.")
    caminhos = [raiz() / c for it in achados for c in it["caminhos"]]
    r = para_lixeira_mac(caminhos, "liberar-espaco")
    r["itens"] = len(achados)
    if r.get("rels"):
        gravar_manifesto(r["pasta"], r["rels"], bytes_=r["bytes"], itens=len(achados))
    return r


# ───────────────────────── tamanho de um vídeo (pra confirmar antes de apagar) ─────────────────────────

def tamanho_video(cli: str, slug: str) -> dict:
    import saidas
    r = saidas.apagar_video(cli, slug, confirmar=True, medir=True)
    if r["recusados"] and not r["apagados"]:
        raise ValueError(r["recusados"][0]["motivo"])
    a = r["apagados"][0]
    return {"bytes": a["bytes"], "texto": fmt_bytes(a["bytes"]), "titulo": a.get("titulo") or slug}


def _rascunho(rel: str) -> tuple[str, str, str, Path]:
    p = Path(os.path.abspath(raiz() / str(rel or "")))
    try:
        partes = p.relative_to(raiz()).parts
    except ValueError:
        raise ValueError("Esse vídeo não está no Estúdio.")
    if not (len(partes) == 6 and partes[0] == "clientes" and partes[3] == "modelos" and partes[5].startswith("_sandbox-") and p.is_dir()) \
            or not _dentro(p):
        raise ValueError("Esse não é um vídeo do Estúdio.")
    return partes[1], partes[4], partes[5][len("_sandbox-"):], p


def apagar_rascunho(rel: str, medir: bool = False) -> dict:
    """Editar vídeo → Apagar: leva TUDO desse vídeo pra Lixeira do Mac. Com projeto (job/Em andamento) usa o caminho único
    de saidas; sem projeto leva o rascunho e o vídeo pronto de mesmo nome. Devolve {bytes, texto, titulo, lixeira_nome}."""
    import saidas
    cli, modelo, slug, p = _rascunho(rel)
    r = saidas.apagar_video(cli, slug, medir=medir)
    if r["apagados"]:
        a = r["apagados"][0]
        return {"bytes": a["bytes"], "texto": fmt_bytes(a["bytes"]), "titulo": a.get("titulo") or slug,
                "lixeira_nome": a.get("lixeira_nome", ""), "mensagem": saidas.mensagem(r) if not medir else "", "itens": a.get("itens", [])}
    if r["recusados"] and "já não existe" not in r["recusados"][0]["motivo"]:
        raise ValueError(r["recusados"][0]["motivo"])
    # sem projeto: o rascunho e o vídeo pronto com o mesmo nome (menos o que é referência)
    if min(_mexido_ha(p), _mexido_ha(p / "work") if (p / "work").exists() else 1e9) < 5 * 60:
        raise ValueError("Esse vídeo foi mexido há poucos minutos. Espere terminar pra apagar.")
    pecas, avisos = [p], []
    for o in sorted(p.parents[2].glob(f"output/{modelo}/*")):
        if re.fullmatch(re.escape(slug) + r"(-v\d+)?(\.mp4|\.mov)?", o.name):
            try:
                if saidas.item(str(o.relative_to(raiz())))["referencia"] is not None:
                    avisos.append(f"{o.name} é referência: fica")
                    continue
            except ValueError:
                pass
            pecas.append(o)
    b = sum(tamanho(q) for q in pecas)
    if medir:
        return {"bytes": b, "texto": fmt_bytes(b), "titulo": slug,
                "itens": [{"tipo": "sandbox" if q == p else "video", "caminho": str(q.relative_to(raiz())), "bytes": tamanho(q)} for q in pecas]}
    lixo = para_lixeira_mac(pecas, slug)
    return {"bytes": b, "texto": fmt_bytes(b), "titulo": slug, "lixeira_nome": lixo["nome"],
            "mensagem": f"✓ Apagado: “{slug}”. {fmt_bytes(b)} foram pra Lixeira do Mac (pasta “{lixo['nome']}”): dá pra recuperar pelo Finder, "
                        f"e o espaço volta quando você esvaziar a Lixeira. " + " ".join(avisos)}


def lote(videos: list[str] = (), caminhos: list[str] = (), rascunhos: list[str] = (), medir: bool = False, musicas: list[str] = ()) -> dict:
    """Apagar vários de uma vez, de qualquer tela: `videos` = ["cliente/slug"], `caminhos` = vídeos prontos em output/ (também os
    feitos pelo chat, sem projeto: leva o mp4 e o rascunho dele), `rascunhos` = pastas do Editar vídeo. Devolve
    {bytes, texto, apagados, recusados:[(nome, motivo)], mensagens}. Com medir=True não mexe em nada.
    `musicas` = arquivos de música (caminho relativo ao Estúdio) da Biblioteca, dos estilos ou dos clientes: vão pra Lixeira do Mac."""
    import saidas
    r = {"bytes": 0, "apagados": 0, "recusados": [], "mensagens": [], "lixeiras": [], "videos": []}

    def somar(res: dict) -> None:
        for a in res["apagados"]:
            r["apagados"] += 1
            r["bytes"] += a["bytes"]
            if medir:
                r["videos"].append({"titulo": a.get("titulo") or a.get("slug") or "", "itens": a.get("itens", []), "avisos": a.get("avisos", [])})
            if a.get("lixeira_nome"):
                r["lixeiras"].append(a["lixeira_nome"])
        for x in res["recusados"]:
            r["recusados"].append((x["caminho"], x["motivo"]))
        if not medir and res["apagados"]:
            r["mensagens"].append(saidas.mensagem(res))

    vistos = set()
    for v in videos:
        cli, _, slug = str(v).partition("/")
        if not slug or (cli, slug) in vistos:
            continue
        vistos.add((cli, slug))
        somar(saidas.apagar_video(cli, slug, medir=medir))
    cams = [c for c in dict.fromkeys(caminhos) if str(c).strip()]
    if cams:
        somar(saidas.apagar(cams, medir=medir))
    for rel in dict.fromkeys(rascunhos):
        try:
            a = apagar_rascunho(rel, medir=medir)
            r["apagados"] += 1
            r["bytes"] += a["bytes"]
            if medir:
                r["videos"].append({"titulo": a.get("titulo") or Path(str(rel)).name, "itens": a.get("itens", []), "avisos": []})
            if a.get("lixeira_nome"):
                r["lixeiras"].append(a["lixeira_nome"])
            if not medir:
                r["mensagens"].append(a["mensagem"])
        except ValueError as e:
            r["recusados"].append((Path(str(rel)).name, str(e)))
    if [m for m in musicas if str(m).strip()]:
        import musica_busca as _mb
        m = _mb.apagar_musica([x for x in musicas if str(x).strip()], medir=medir)
        r["apagados"] += m["apagados"]
        r["bytes"] += m["bytes"]
        r["recusados"] += m["recusados"]
        r["lixeiras"] += m["lixeiras"]
        if not medir and m["apagados"]:
            r["mensagens"].append(f"✓ {', '.join('“' + t + '”' for t in m['titulos'][:3])} foi pra Lixeira do Mac ({fmt_bytes(m['bytes'])}). "
                                  "Dá pra recuperar pelo Finder; o espaço volta quando você esvaziar a Lixeira.")
    r["texto"] = fmt_bytes(r["bytes"])
    return r


# ───────────────────────── painel "o que vai pra Lixeira" (ver antes de apagar) ─────────────────────────
# Um painel só pra todo Apagar do Estúdio (static/studio.js + templates/_apagar_ui.html): lista TUDO que vai pra Lixeira do Mac,
# cada coisa com miniatura (vídeo toca, imagem aparece, música tem play), tamanho, o que é e "Mostrar no Finder".

EXPLICA = {   # o que é cada peça de um vídeo apagado (tipos de saidas._montar_pecas)
    "video": "O vídeo pronto. Some junto com este vídeo.",
    "pasta": "Pasta de saída do vídeo: o vídeo pronto e os arquivos que andam com ele.",
    "versao": "Uma versão anterior do vídeo pronto.",
    "metadados": "Miniatura e dados do vídeo pronto.",
    "job": "O projeto do vídeo: o pedido, o roteiro e o registro de como foi feito.",
    "sandbox": "Rascunho de trabalho do vídeo: trechos, quadros, material, a gravação original e as versões antigas.",
    "andamento": "O cartão deste vídeo na aba Em andamento.",
    "briefing": "O pedido que você preencheu no Novo vídeo (texto e arquivos que mandou).",
    "temporarios": "Arquivos temporários deste vídeo (prévias e conferências).",
    "uploads": "A gravação que você enviou pra fazer este vídeo. Some junto com ele.",
    "corte": "O corte do bruto (transcrição e marcações) feito pra este vídeo.",
}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
SERVE = VIDEO_EXTS | IMAGEM | AUDIO | {".gif"}     # o que a prévia pode mostrar (nunca .env, json, código)


def dentro_do_estudio(caminho: str | Path) -> Path:
    """Caminho (relativo ao Estúdio ou absoluto) conferido: sem `..`, e o resolve() cai dentro do Estúdio. Senão ValueError.
    Serve ao "Mostrar no Finder" e à prévia: nada de fora do Estúdio."""
    txt = str(caminho or "").strip()
    if not txt or "\x00" in txt:
        raise ValueError("Caminho vazio.")
    if ".." in Path(txt).parts:
        raise ValueError("Caminho com “..” não vale.")
    p = Path(txt)
    p = p if p.is_absolute() else raiz() / p
    try:
        r = p.resolve()
        r.relative_to(raiz())
    except (ValueError, OSError, RuntimeError):
        raise ValueError("Esse caminho está fora do Estúdio.") from None
    if not r.exists():
        raise ValueError("Esse arquivo já não existe.")
    return r


def _tipo_arquivo(p: Path) -> str:
    if p.is_dir():
        return "pasta"
    e = p.suffix.lower()
    return "video" if e in VIDEO_EXTS else "imagem" if e in IMAGEM | {".gif"} else "audio" if e in AUDIO else "arquivo"


def _rel_estudio(p: Path) -> str:
    return str(Path(os.path.abspath(p)).relative_to(raiz()))


def _dentro_da_pasta(d: Path, limite: int = 6) -> tuple[list[dict], int]:
    """Até `limite` arquivos de mídia de uma pasta (vídeos primeiro, os maiores antes) e quantos arquivos ela tem."""
    achados, n = [], 0
    for dp, dns, fns in os.walk(d):
        dns[:] = [x for x in dns if not os.path.islink(os.path.join(dp, x))]
        for f in fns:
            n += 1
            q = Path(dp) / f
            if q.suffix.lower() in SERVE and not q.is_symlink():
                try:
                    achados.append((0 if q.suffix.lower() in VIDEO_EXTS else 1, -q.stat().st_size, q))
                except OSError:
                    pass
        if n > 20000:
            break
    achados.sort(key=lambda x: (x[0], x[1], str(x[2])))
    return [{"caminho": _rel_estudio(q), "kind": _tipo_arquivo(q), "bytes": -t, "tamanho": fmt_bytes(-t)} for _, t, q in achados[:limite]], n


def _peca(caminho: str | Path, rotulo: str, explica: str, bytes_: int | None = None) -> dict | None:
    """Um item do painel. Caminho que já não existe ou é de fora: None (o painel avisa que sumiu)."""
    try:
        p = dentro_do_estudio(caminho)
    except ValueError:
        return None
    b = tamanho(p) if bytes_ is None else bytes_
    kind = _tipo_arquivo(p)
    it = {"rotulo": rotulo, "explica": explica, "caminho": _rel_estudio(p), "kind": kind, "bytes": b, "tamanho": fmt_bytes(b),
          "nome": p.name, "dentro": [], "n_arquivos": 1}
    if kind == "pasta":
        it["dentro"], it["n_arquivos"] = _dentro_da_pasta(p)
    return it


def previa(videos: list[str] = (), caminhos: list[str] = (), rascunhos: list[str] = (), arquivos: list[str] = (), explica: str = "",
           grupos: list[dict] | None = None, musicas: list[str] = ()) -> dict:
    """O que vai pra Lixeira, pronto pro painel: {ok, n, bytes, texto, grupos:[{titulo, avisos, itens:[{rotulo, explica, caminho, kind,
    tamanho, nome, dentro, n_arquivos}]}], recusados}. Três jeitos de pedir (misturáveis): vídeos (`videos`/`caminhos`/`rascunhos`,
    os mesmos do apagar), `arquivos` soltos com um texto `explica` (ou `musicas`), ou `grupos` = [{titulo, rotulo, explica, caminhos:[...]}] montados
    pela tela. Não mexe em nada."""
    out, recusados, total = [], [], 0
    if videos or caminhos or rascunhos:
        r = lote(list(videos), list(caminhos), list(rascunhos), medir=True)
        recusados += [{"nome": n, "motivo": m} for n, m in r["recusados"]]
        for v in r["videos"]:
            itens = []
            for x in v["itens"]:
                it = _peca(x["caminho"], saidas_rotulo(x["tipo"]), EXPLICA.get(x["tipo"], ""), x["bytes"])
                if it:
                    itens.append(it)
            if itens:
                out.append({"titulo": v["titulo"], "avisos": v.get("avisos", []), "itens": itens})
    if musicas:   # mesmos `musicas` do lote(): arquivos de áudio da Biblioteca, dos estilos ou dos clientes
        arquivos = list(arquivos) + list(musicas)
        explica = explica or "Música: o arquivo de áudio. Vai pra Lixeira do Mac; as músicas que você escolheu em outro lugar não são afetadas."
    if arquivos:
        itens = [it for a in arquivos if (it := _peca(a, "Música" if musicas else "Arquivo", explica))]
        sumiram = len(list(arquivos)) - len(itens)
        if itens:
            out.append({"titulo": "", "avisos": [f"{sumiram} arquivo(s) já não existem."] if sumiram else [], "itens": itens})
        elif sumiram:
            recusados.append({"nome": "arquivo", "motivo": "Esse arquivo já não existe ou é de fora do Estúdio."})
    for g in grupos or []:
        itens = [it for c in g.get("caminhos") or [] if (it := _peca(c, str(g.get("rotulo") or "Arquivo"), str(g.get("explica") or "")))]
        for it in itens:
            it["aviso"] = str(g.get("aviso") or "")
        if itens:
            titulo = str(g.get("titulo") or "")
            mesmo = next((x for x in out if x["titulo"] == titulo and x.get("junta")), None)   # itens do mesmo vídeo ficam juntos
            if mesmo:
                mesmo["itens"] += itens
            else:
                out.append({"titulo": titulo, "avisos": [], "itens": itens, "junta": True})
    total = sum(i["bytes"] for g in out for i in g["itens"])
    return {"ok": bool(out), "n": sum(len(g["itens"]) for g in out), "bytes": total, "texto": fmt_bytes(total), "grupos": out,
            "recusados": recusados}


def saidas_rotulo(tipo: str) -> str:
    return {"pasta": "Pasta do vídeo", "video": "Vídeo", "versao": "Versão", "metadados": "Miniatura e dados", "job": "Projeto",
            "sandbox": "Rascunho de trabalho", "andamento": "Cartão do Em andamento", "briefing": "Pedido (briefing)",
            "temporarios": "Temporários", "uploads": "Gravação enviada", "corte": "Corte do bruto"}.get(tipo, tipo.capitalize())


def mostrar_no_finder(caminho: str | list[str]) -> list[str]:
    """`open -R <caminho>`: abre o Finder já com o arquivo marcado (vários de uma vez, até 5). Só de dentro do Estúdio: um caminho
    ruim recusa tudo (ValueError) antes de abrir qualquer coisa. Devolve os caminhos abertos."""
    lista = [caminho] if isinstance(caminho, (str, Path)) else list(caminho or [])
    ps = [dentro_do_estudio(c) for c in lista if str(c).strip()][:5]
    if not ps:
        raise ValueError("Caminho vazio.")
    subprocess.run(["open", "-R", *map(str, ps)], capture_output=True, timeout=15)
    return [str(p) for p in ps]


def tamanho_corte(slug: str) -> dict:
    d = Path(_comum.ESTUDIO) / "cortes" / Path(slug).name
    if not d.is_dir():
        raise ValueError("Esse corte já não existe.")
    return {"bytes": tamanho(d), "texto": fmt_bytes(tamanho(d)), "titulo": slug}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("desduplicar"); d.add_argument("--aplicar", action="store_true")
    sub.add_parser("itens")
    t = sub.add_parser("tamanho"); t.add_argument("cliente"); t.add_argument("slug")
    a = ap.parse_args()
    if a.cmd == "desduplicar":
        r = desduplicar(aplicar=a.aplicar)
        print(f"{r['grupos']} grupos, {r['copias']} cópias repetidas = {fmt_bytes(r['bytes'])}"
              + (f"; trocadas por clone: {r['feitos']}; livre {fmt_bytes(r['livre_antes'])} → {fmt_bytes(r['livre_depois'])}" if a.aplicar else " (só medi; use --aplicar)"))
        for e in r["erros"][:10]:
            print("  erro:", e)
    elif a.cmd == "itens":
        x = itens_liberaveis()
        for g in x["grupos"]:
            print(g["nome"], g["tamanho"])
            for v in g["videos"]:
                for i in v["itens"]:
                    print("   ", "[x]" if i["marcado"] else "[ ]", i["tamanho"], v["titulo"], "·", i["rotulo"])
        print("total", x["total_txt"], "marcado", x["marcado_txt"])
    else:
        print(tamanho_video(a.cliente, a.slug))


if __name__ == "__main__":
    main()
