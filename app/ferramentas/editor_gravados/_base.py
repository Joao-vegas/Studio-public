"""Ajudantes que os módulos do editor_gravados repartem (não é um spec: o nome começa com "_")."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def duracao_video(f: Path) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                                              str(f)], text=True, timeout=30))
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def saida_padrao(p: Path) -> Path:
    """clientes/<C>/<x>Content/output/<modelo>/<slug>.mp4 de uma pasta clientes/<C>/<x>Content/modelos/<modelo>/_sandbox-<slug>."""
    return p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def palavras(f: Path) -> list[dict]:
    """[{word, start, end}] de um words.json (lista ou {"words": [...]}); [] se não existe ou está quebrado."""
    try:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [w for w in (d.get("words", d) if isinstance(d, dict) else d) if isinstance(w, dict) and "start" in w]


def trechos_da_fala(ws: list[dict], dur: float, minimo: float = 3.0, maximo: float = 8.0) -> list[float]:
    """Segundos onde cada trecho começa (o primeiro é 0): corta em pausa (>= 0,35 s) ou fim de frase, trechos de `minimo` a `maximo` s.
    Sem palavras, de `maximo*0.6` em `maximo*0.6` s. O último trecho nunca fica menor que `minimo`/2."""
    dur = float(dur or 0)
    cortes: list[float] = []
    atual = 0.0
    if ws:
        for i, w in enumerate(ws[:-1]):
            fim = float(w.get("end", w["start"]))
            prox = float(ws[i + 1]["start"])
            pausa = prox - fim
            fim_frase = str(w.get("word", "")).strip()[-1:] in ".?!"
            t = prox if pausa >= .35 else (fim + prox) / 2
            dist = t - atual
            if (dist >= minimo and (pausa >= .35 or fim_frase)) or dist >= maximo:
                if pausa < .35 and not fim_frase and dist >= maximo:
                    t = fim + max(pausa, 0) / 2   # forçado: no vão entre duas palavras
                if dur and dur - t < minimo / 2:
                    break
                cortes.append(round(t, 2))
                atual = t
    else:
        passo = maximo * .6
        t = passo
        while dur and t < dur - minimo / 2:
            cortes.append(round(t, 2))
            t += passo
    return [0.0] + cortes


# ───────────── comando.sh do gerar.sh: ler os flags e escrever de volta sem perder o que o editor não conhece ─────────────

def ler_comando(txt: str, bool_flags: tuple = ("--previa",)) -> dict | None:
    """Acha a linha do `zsh ../gerar.sh ...` (aceita `\\` no fim da linha) e devolve
    {"antes": texto antes do shell (ex.: 'cd pasta && '), "shell", "script", "flags": {flag: valor | True}, "linha": índice, "linhas": [...]}.
    None se não há gerar.sh. Flag repetido guarda o último valor."""
    import re
    import shlex
    linhas = txt.replace("\\\n", " ").splitlines()
    for i, l in enumerate(linhas):
        m = re.search(r"(zsh|bash|sh)\s+(\S*gerar\.sh)\s*(.*)$", l)
        if not m:
            continue
        try:
            t = shlex.split(m.group(3))
        except ValueError:
            return None
        flags: dict = {}
        k = 0
        while k < len(t):
            if t[k].startswith("--"):
                if t[k] in bool_flags or k + 1 >= len(t):
                    flags[t[k]] = True
                    k += 1
                else:
                    flags[t[k]] = t[k + 1]
                    k += 2
            else:
                k += 1
        return {"antes": l[:m.start()], "shell": m.group(1), "script": m.group(2), "flags": flags, "linha": i, "linhas": linhas}
    return None


def montar_comando(flags: dict, shell: str = "zsh", script: str = "../gerar.sh") -> list[str]:
    """[shell, script, --flag, valor...] a partir do dict de ler_comando (valor True = flag sem valor; None/'' = não vai)."""
    out = [shell, script]
    for f, v in flags.items():
        if v is True:
            out.append(f)
        elif v not in (None, False, ""):
            out += [f, str(v)]
    return out


def escrever_comando(arq: Path, cm: dict, flags: dict) -> None:
    """Reescreve o comando.sh trocando só a linha do gerar.sh (o resto do arquivo fica)."""
    import shlex
    linhas = list(cm["linhas"])
    toks = montar_comando(flags, cm["shell"], cm["script"])
    linhas[cm["linha"]] = cm["antes"] + " ".join(x if i < 2 or x.startswith("--") else shlex.quote(x) for i, x in enumerate(toks))
    Path(arq).write_text("\n".join(linhas) + "\n", encoding="utf-8")
