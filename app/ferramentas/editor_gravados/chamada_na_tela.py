#!/usr/bin/env python3
"""
editor_gravados.chamada_na_tela — "Editar vídeo por cena" da Chamada na tela (modelo chamada-na-tela; tela.py + config.json).

O vídeo é a pessoa em tela cheia com um gancho no começo (título neon + batida/puxão/luz/sinal), legenda de uma palavra por vez e,
de vez em quando, um motion limpo (palavra neon, riscado, etiqueta, número subindo, X, itens empilhando). Tudo sai do config.json:
título, gancho, estilo da legenda, destaques e (opcional) a lista `motions`. Sem `motions` o tela.py acha os motions sozinho pelos
gatilhos da fala; o editor lê essa mesma lista (o mesmo código, o mesmo sorteio) e a grava no config.json só se a edição mudar algo.

A "cena" é um trecho: o gancho (título neon), cada motion e a fala (legenda) entre eles.

    python3 chamada_na_tela.py refazer <sandbox>    # roda o tela.py no config.json e troca o vídeo só se der certo (o editor chama)
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import RAIZ, com_venv, gravar_json, ler_json, rodar_com_limite  # noqa: E402

SLUG = "chamada-na-tela"
MOTIONS = ("neon", "riscado", "etiqueta", "contador", "x", "empilha")
ENTRADAS = ("pop", "desliza", "pisca")
TIPOS = {"gancho": "Gancho (título neon)", "fala": "Legenda de uma palavra", "neon": "Motion: palavra neon", "riscado": "Motion: palavra riscada",
         "etiqueta": "Motion: etiqueta", "contador": "Motion: número subindo", "x": "Motion: X atrás do texto", "empilha": "Motion: itens empilhando"}
ROTULOS = {"tipo": "Tela", "texto": "Texto do motion", "itens": "Itens do motion (texto e segundo)",
           "titulo": "Título neon", "gancho": "Gancho",
           "legenda": "Estilo da legenda", "destaques": "Palavras em laranja"}
GLOBAIS = {"titulo": ["titulo_neon"], "gancho": ["gancho"], "legenda": ["legenda"], "destaques": ["destaques"]}


# ───────────────────────── tela.py e config.json ─────────────────────────

_MODULOS: dict = {}


def _tela(p: Path):
    """O tela.py do modelo, importado (só pra usar o planejar_motions e as constantes: o render roda em outro processo)."""
    f = (p.parent / "tela.py").resolve()
    chave = (str(f), f.stat().st_mtime)
    if chave not in _MODULOS:
        spec = importlib.util.spec_from_file_location("tela_" + hashlib.sha1(str(f).encode()).hexdigest()[:8], f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODULOS[chave] = mod
    return _MODULOS[chave]


def _abs(p: Path, c) -> Path:
    return Path(c) if str(c).startswith("/") else p / str(c)


def saida(p: Path) -> Path:
    cfg = ler_json(p / "config.json", {}) or {}
    return _abs(p, cfg["out"]) if cfg.get("out") else p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def _palavras(p: Path, cfg: dict) -> dict:
    return json.loads(_abs(p, cfg["words"]).read_text(encoding="utf-8"))


def _fim_titulo(cfg: dict, words: dict) -> float:
    pecas = words.get("pecas") or [{"fim": 0}]
    return float(cfg.get("titulo_fim", min(max(pecas[0]["fim"], 2.2), 3.0)))


def _norm(m: dict) -> tuple:
    return (m["tipo"], m["txt"], round(float(m["ini"]), 3), round(float(m["fim"]), 3), m.get("entrada", "pop"),
            tuple((r, round(float(t), 3)) for r, t in m.get("itens") or []))


def _motions_de_agora(p: Path, cfg: dict, words: dict) -> list[dict]:
    """Os motions do vídeo hoje: a lista `motions` do config.json ou a que o tela.py acha sozinho (mesmo sorteio)."""
    if cfg.get("motions") is not None:
        return [dict(m) for m in cfg["motions"]]
    tela = _tela(p)
    return tela.planejar_motions(words["words"], _fim_titulo(cfg, words) + 0.8, words["dur"], random.Random(cfg.get("seed", 7)))


# ───────────────────────── config.json ⇄ lista de cenas ─────────────────────────

def ler(p: Path) -> dict:
    """config.json → lista de cenas: o gancho (título neon), cada motion e a fala (legenda) entre eles."""
    cfg = json.loads((p / "config.json").read_text(encoding="utf-8"))
    words = _palavras(p, cfg)
    dur = float(words["dur"])
    t_fim = _fim_titulo(cfg, words)
    cs = [{"de": 0.0, "tipo": "gancho"}]
    t = t_fim
    for m in sorted(_motions_de_agora(p, cfg, words), key=lambda m: m["ini"]):
        if m["ini"] - t > 0.05:
            cs.append({"de": t, "tipo": "fala"})
        c = {"de": float(m["ini"]), "tipo": m["tipo"], "texto": m["txt"], "entrada": m.get("entrada", "pop")}
        if m["tipo"] == "empilha":
            c["itens"] = [[r, float(ts)] for r, ts in m["itens"]]
        cs.append(c)
        t = float(m["fim"])
    if dur - t > 0.05 or len(cs) == 1:
        cs.append({"de": min(t, dur), "tipo": "fala"})
    ed = p / "editor"   # a fala no formato do editor ({word, start}) e no tempo do vídeo, pra mostrar o que se diz em cada cena
    ed.mkdir(parents=True, exist_ok=True)
    pal = [{"word": w["w"], "start": w["s"], "end": w["e"]} for w in words["words"]]
    if ler_json(ed / "palavras.json", None) != pal:
        gravar_json(ed / "palavras.json", pal)
    titulo = " ".join(cfg.get("titulo") or []).capitalize() or p.name
    doc = {"titulo": titulo, "duracao": dur, "saida": str(saida(p)), "palavras": "editor/palavras.json",
           "titulo_neon": list(cfg.get("titulo") or []), "gancho": cfg.get("gancho", "bate"), "legenda": cfg.get("legenda", 1),
           "destaques": list(cfg.get("destaques") or [])}
    doc["cenas"] = cs
    return doc


def gravar(p: Path, doc: dict) -> None:
    """Lista de cenas → config.json (título, gancho, legenda, destaques e `motions` — só se a lista difere da automática)."""
    f = p / "config.json"
    cfg = json.loads(f.read_text(encoding="utf-8"))
    words = _palavras(p, cfg)
    dur, t_fim = float(words["dur"]), _fim_titulo(cfg, words)
    tela = _tela(p)
    if doc.get("titulo_neon"):
        cfg["titulo"] = [str(l) for l in doc["titulo_neon"]][:2]
    if doc.get("gancho"):
        cfg["gancho"] = str(doc["gancho"])
    if doc.get("legenda") in (1, 2):
        cfg["legenda"] = doc["legenda"]
    if "destaques" in doc:
        cfg["destaques"] = [str(d) for d in doc["destaques"]]
    ms = []
    for c in sorted((c for c in doc.get("cenas") or [] if isinstance(c, dict)), key=lambda c: float(c["de"])):
        tipo, ini = c.get("tipo"), float(c["de"])
        if tipo not in MOTIONS or ini < t_fim or ini > dur - 1.4:
            continue
        texto = str(c.get("texto") or "").strip()
        ent = c.get("entrada") if c.get("entrada") in ENTRADAS else "pop"
        if tipo == "empilha":
            itens = [[str(r), float(ts)] for r, ts in c.get("itens") or []]
            if len(itens) < 2:
                continue
            ms.append({"tipo": tipo, "txt": "|".join(r for r, _ in itens), "ini": ini, "entrada": ent, "itens": itens,
                       "fim": min(itens[-1][1] + 1.3, dur - 0.2)})
            continue
        if not texto:
            continue
        if tipo == "contador" and not any(ch.isdigit() for ch in texto):
            tipo = "neon"   # número subindo precisa de número
        ms.append({"tipo": tipo, "txt": texto, "ini": ini, "entrada": ent, "fim": min(ini + tela.DUR[tipo], dur - 0.2)})
    auto = tela.planejar_motions(words["words"], t_fim + 0.8, dur, random.Random(cfg.get("seed", 7)))
    if [_norm(m) for m in ms] == [_norm(m) for m in auto]:
        cfg.pop("motions", None)
    else:
        cfg["motions"] = ms
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────── refazer ─────────────────────────

def refazer(p: Path) -> int:
    """Roda o tela.py no config.json (num config temporário com a saída ao lado) e só troca o vídeo se o render der certo. 0 = ok."""
    p = Path(p).resolve()
    tela = p.parent / "tela.py"
    cfg = json.loads((p / "config.json").read_text(encoding="utf-8"))
    destino = saida(p)
    destino.parent.mkdir(parents=True, exist_ok=True)
    novo = destino.with_name(destino.name + ".novo.mp4")
    c2 = dict(cfg, out=str(novo))
    for k in ("video", "words", "musica"):
        if c2.get(k):
            c2[k] = str(_abs(p, c2[k]))
    gravar_json(p / "editor" / "config-render.json", c2)
    r = rodar_com_limite([sys.executable, str(tela), str(p / "editor" / "config-render.json")], 7200, cwd=p, env=com_venv(),
                         capture_output=True, text=True)
    if r.returncode or not novo.is_file():
        print((r.stderr or r.stdout)[-600:])
        novo.unlink(missing_ok=True)
        return r.returncode or 1
    os.replace(novo, destino)
    print("ok", destino)
    return 0


def cmd(p: Path) -> tuple[list[str], Path]:
    return [sys.executable, str(Path(__file__).resolve()), "refazer", str(p)], p


def cmd_txt(p: Path) -> str:
    return f"python3 {p.parent / 'tela.py'} {p / 'config.json'}"


def achar(p: Path) -> bool:
    return (p / "config.json").is_file() and (p.parent / "tela.py").is_file()


SPEC = {
    "gravado": True, "fonte": "config.json", "ler": ler, "gravar": gravar,
    "arquivos": ["config.json"], "precisa": ["config.json"],
    "achar": achar, "cmd": cmd, "cmd_txt": cmd_txt, "saida": saida, "timeout": 7200,
    "rotulos": ROTULOS, "tipos": TIPOS, "tipo_padrao": "fala",
    "juntos": {"tipo": ["texto", "itens", "entrada"], "texto": ["entrada"], "itens": []}, "sempre": ("tipo", "texto"), "globais": GLOBAIS,
    "sugestoes": ["Troca o texto desse motion por uma palavra mais forte", "Põe um motion nesse trecho", "Tira o motion desse trecho",
                  "Troca o título neon por outro mais direto"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "tela.py e o lote.py",
    "motivo_narracao": "Neste formato a voz é a pessoa gravada: a fala só muda trocando o vídeo gravado.",
    "onde": ("O vídeo é a pessoa gravada em tela cheia com um gancho no começo (título neon), legenda de uma palavra por vez e, de vez em quando, um "
             "motion no tempo da palavra, desenhado pelo tela.py do modelo a partir do config.json. Você NÃO mexe no config.json: edite só a lista "
             "de cenas (cada cena é um trecho do vídeo, com \"de\" = segundo em que começa; ela termina onde a próxima começa)."),
    "conferir": ("Você não renderiza o vídeo (o tela.py leva alguns minutos): confira só que o texto cabe (palavras curtas, caixa-alta) e que o "
                 "\"de\" de cada motion cai na palavra falada daquele trecho (a fala da cena está no pedido)."),
    "dicas": ("Cada cena é um trecho. \"gancho\" (o 1º, ~3 s) mostra o título neon; \"fala\" é só a legenda; os outros tipos são motions na palavra "
              "forte: \"neon\" (palavra grande), \"riscado\" (palavra com risco), \"etiqueta\" (faixa com frase curta), \"contador\" (número subindo: "
              "\"texto\" com número, ex.: \"R$ 97\" ou \"-80%\"), \"x\" (X que se desenha atrás do texto) e \"empilha\" (\"itens\": [[\"JANEIRO\", "
              "segundo], ...], cada item entra no segundo dele, que é DENTRO da cena). \"texto\" em caixa-alta, curto (até ~3 palavras; etiqueta até ~5). "
              "\"entrada\": pop, desliza ou pisca. Pra TIRAR um motion, troque o \"tipo\" por \"fala\"; pra PÔR, troque uma cena \"fala\" por um tipo de "
              "motion e preencha \"texto\" (deixe 2,4 s ou mais entre dois motions). O \"de\" do motion tem que cair na palavra dita. No topo: "
              "\"titulo_neon\" (2 linhas de até ~20 letras, caixa-alta), \"gancho\" (bate, puxa, luz, sinal ou brilho), \"legenda\" (1 = uma palavra, "
              "2 = bloco de 3) e \"destaques\" (palavras em minúsculo que a legenda pinta de laranja)."),
}
SPECS = {SLUG: SPEC}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "refazer":
        sys.exit(refazer(Path(sys.argv[2])))
    print(__doc__)
    sys.exit(2)
