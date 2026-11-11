#!/usr/bin/env python3
"""
melhoria — o Estúdio propõe consertar o PRÓPRIO motor e o João decide (CLAUDE.md, REGRA Nº 2, passo 4: "erro mecânico se
conserta no motor ou na checagem, não só em texto"). Duas espécies de proposta, o mesmo fluxo e o mesmo "Aprovou?":

  motor   a revisão (revisao.py) achou um erro mecânico que se repete (2+ vídeos) ou que é claramente do motor:
          "Melhoria sugerida no estilo X: <o que muda> · arquivo <base/...>"
  regras  o historico.jsonl de um modelo passou de LIMITE_HISTORICO linhas novas: passar a limpo vira regra (aprendizado.py),
          mostrando as regras novas e as reescritas.

Estados: proposta → [Ver a mudança] preparando → pronta (com o diff) → [Aplicar] aplicando → aplicada | falhou
         aplicada → [Desfazer] desfeita · proposta/pronta → [Agora não] recusada.

🔴 Sem "Aplicar" NENHUM arquivo real muda: a IA edita só uma CÓPIA (app/melhorias/<id>/proposta/). O Aplicar copia a copia pro
   lugar, roda a prova (sintaxe, formatos.validar sem falta nova, testes sem falha nova e, em formato de motor, um quadro
   renderizado com o motor novo) e, se qualquer passo falhar, restaura o ANTES (app/melhorias/<id>/antes/) e diz o porquê.
   "Desfazer" restaura o antes, mas só se o arquivo ainda é o que o Aplicar gravou (não pisa em mudança de outra pessoa).

  python3 app/ferramentas/melhoria.py preparar|aplicar|desfazer <id>      (a tela chama isto em processo próprio)
  python3 app/ferramentas/melhoria.py listar
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import agora, append_jsonl, ensure, gravar_json, hoje, ler_json, ler_jsonl  # noqa: E402

LIMITE_HISTORICO = 20      # linhas de histórico ainda não absorvidas, por modelo, até propor passar a limpo
LIM_LINHAS = 80            # linhas mudadas por melhoria de motor (diff pequeno)
LIM_ARQUIVOS = 2
ADIAR_DIAS = 14            # "Agora não" cala a mesma melhoria por esse tempo
TESTES_BASE = ("test_contrato_formatos", "test_formato_declara")
ESTADOS_ABERTOS = ("proposta", "preparando", "pronta", "aplicando")

_PERMITIDOS = (
    re.compile(r"^formatos/[^/]+/base/[^\n]+\.(?:py|js|mjs|html|css|sh)$"),
    re.compile(r"^clientes/[^/]+/[^/]+/modelos/[^/]+/[^/]+\.(?:py|js|mjs|sh)$"),
    re.compile(r"^app/ferramentas/conferir_video\.py$"),
)


def pasta_melhorias() -> Path:
    return _comum.ESTUDIO / "melhorias"


def _arq(id_: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{8,32}", str(id_ or "")):
        raise ValueError("Melhoria não encontrada.")
    return pasta_melhorias() / f"{id_}.json"


def carregar(id_: str) -> dict | None:
    try:
        d = ler_json(_arq(id_), None)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _salvar(rec: dict) -> dict:
    gravar_json(_arq(rec["id"]), rec)
    return rec


def listar(estados: tuple | None = None) -> list[dict]:
    out = []
    for p in sorted(pasta_melhorias().glob("*.json")) if pasta_melhorias().is_dir() else []:
        d = ler_json(p, None)
        if isinstance(d, dict) and d.get("id") and (not estados or d.get("estado") in estados):
            out.append(d)
    return sorted(out, key=lambda d: d.get("criado_em", ""), reverse=True)


def abertas() -> list[dict]:
    """O que espera o João (Esperando você): ainda não aplicada nem recusada."""
    return [r for r in listar(("proposta", "pronta", "falhou")) if not r.get("visto_falha")]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if Path(p).is_file() else ""


def permitido(rel: str) -> bool:
    """Só código do motor: base/ do estilo, scripts do modelo do cliente e o conferir_video. Nunca aprendizado, identidade, .env, mídia."""
    rel = str(rel or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/") or "aprendizado" in rel or ".env" in rel:
        return False
    if {"audio", "exemplos", "node_modules", "musicas"} & set(rel.split("/")):
        return False
    return any(r.match(rel) for r in _PERMITIDOS) and (_comum.RAIZ / rel).is_file()


# ───────────────────────────── propor ─────────────────────────────

def propor(job: dict, ctx: dict, achado: dict) -> dict | None:
    """Cria a proposta "Melhoria sugerida" (motor) se o arquivo é permitido e não há outra igual aberta ou recusada há pouco."""
    rel = str(achado.get("onde") or "").strip().replace("\\", "/")
    if not permitido(rel):
        return None
    chave = achado["tipo"]
    formato = ctx.get("formato") or ""
    agora_s = agora()
    for r in listar():
        if r.get("tipo") != "motor" or r.get("formato") != formato or r.get("chave") != chave or rel not in (r.get("arquivos") or []):
            continue
        if r["estado"] in ESTADOS_ABERTOS:
            r["achados"] = (r.get("achados") or []) + [{"job": f"{job['cliente']}/{job['slug']}", "t": achado["t"], "o_que": achado["o_que"]}]
            _salvar(r)
            return r
        if r["estado"] == "recusada" and _dias(r.get("resolvido_em")) < ADIAR_DIAS:
            return None
    titulo = ctx.get("formato_titulo") or formato or "este estilo"
    rec = {"id": uuid.uuid4().hex[:12], "tipo": "motor", "estado": "proposta", "formato": formato, "formato_titulo": titulo,
           "cliente": job["cliente"], "slug": job["slug"], "modelo": job.get("modelo") or "", "chave": chave,
           "titulo": f"Melhoria sugerida no estilo {titulo}: {achado['conserto'][:160] or achado['o_que'][:160]}",
           "o_que_muda": achado["conserto"], "causa": achado["causa"], "arquivos": [rel], "t": achado["t"],
           "achados": [{"job": f"{job['cliente']}/{job['slug']}", "t": achado["t"], "o_que": achado["o_que"]}],
           "miniatura": achado.get("miniatura", ""), "video": _comum.rel(ctx["saida"]) if ctx.get("saida") else "",
           "sandbox": job.get("sandbox") or "", "repetido_em": achado.get("repetido_em", 1), "criado_em": agora_s}
    return _salvar(rec)


def _dias(quando) -> float:
    from datetime import datetime
    try:
        return (datetime.now() - datetime.strptime(str(quando)[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 86400
    except ValueError:
        return 9999


def _hash_linha(x: dict) -> str:
    return hashlib.sha1(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _absorvidas(pasta: Path) -> set:
    return set((ler_json(Path(pasta) / ".absorvido.json", {}) or {}).get("hashes") or [])


def novas_do_historico(pasta: Path) -> list[dict]:
    """Linhas do historico.jsonl que ainda não viraram regra pelo passar a limpo."""
    import aprendizado
    ja = _absorvidas(pasta)
    return [x for x in aprendizado.historico(Path(pasta)) if _hash_linha(x) not in ja]


def propor_regras(pasta: Path, job: dict | None = None) -> dict | None:
    """Histórico do modelo passou de LIMITE_HISTORICO linhas novas: propõe passar a limpo. Uma proposta aberta por modelo."""
    pasta = Path(pasta)
    novas = novas_do_historico(pasta)
    if len(novas) <= LIMITE_HISTORICO:
        return None
    prel = _comum.rel(pasta)
    for r in listar():
        if r.get("tipo") == "regras" and r.get("pasta") == prel:
            if r["estado"] in ESTADOS_ABERTOS:
                return r
            if r["estado"] == "recusada" and _dias(r.get("resolvido_em")) < ADIAR_DIAS:
                return None
    modelo = pasta.parent.name
    cli = pasta.parts[-5] if len(pasta.parts) >= 5 and pasta.parts[-3] == "modelos" else ""
    rec = {"id": uuid.uuid4().hex[:12], "tipo": "regras", "estado": "proposta", "pasta": prel, "cliente": cli, "modelo": modelo,
           "slug": (job or {}).get("slug", ""), "formato": "", "formato_titulo": "",
           "titulo": f"Passar a limpo o que o modelo {modelo} ({cli}) aprendeu: {len(novas)} linhas de histórico viram regra",
           "o_que_muda": f"O histórico de {modelo} tem {len(novas)} linhas que ainda não viraram regra. Vou reescrever as regras que já existem e criar só as que faltam.",
           "arquivos": [prel + "/regras.json"], "n_linhas": len(novas), "criado_em": agora()}
    return _salvar(rec)


# ───────────────────────────── processo próprio ─────────────────────────────

def disparar(acao: str, id_: str) -> None:
    """Prepara/aplica/desfaz em processo próprio (a IA e a prova levam minutos; a tela não trava e o recarregar não mata)."""
    log = ensure(pasta_melhorias() / id_) / "processo.log"
    with log.open("a") as f:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), acao, id_], cwd=str(_comum.RAIZ),
                         start_new_session=True, stdout=f, stderr=subprocess.STDOUT)


def pedir(acao: str, id_: str) -> dict:
    """O clique do João. Valida o estado e dispara; 'agora_nao' resolve na hora."""
    rec = carregar(id_)
    if not rec:
        raise ValueError("Melhoria não encontrada.")
    est = rec["estado"]
    if acao == "ver":
        if est not in ("proposta", "pronta", "falhou"):
            raise ValueError("Essa melhoria já está em andamento ou foi respondida.")
        rec.update(estado="preparando", motivo="", inicio_prep=agora())
        _salvar(rec)
        disparar("preparar", id_)
    elif acao == "aplicar":
        if est not in ("proposta", "pronta"):
            raise ValueError("Só dá pra aplicar uma melhoria que ainda espera sua resposta.")
        rec.update(estado="aplicando", motivo="", inicio_apl=agora(), aplicar_apos_ver=(est == "proposta"))
        _salvar(rec)
        disparar("preparar" if est == "proposta" else "aplicar", id_)
    elif acao == "desfazer":
        if est != "aplicada":
            raise ValueError("Só dá pra desfazer uma melhoria aplicada.")
        desfazer(id_)
    elif acao == "agora_nao":
        if est not in ("proposta", "pronta", "falhou"):
            raise ValueError("Essa melhoria já foi respondida.")
        rec.update(estado="recusada", resolvido_em=agora())
        _salvar(rec)
    else:
        raise ValueError("Ação inválida.")
    return carregar(id_)


# ───────────────────────────── preparar (a IA edita a CÓPIA) ─────────────────────────────

def _copiar(origem: Path, destino: Path) -> None:
    ensure(destino.parent)
    shutil.copy2(origem, destino)


def _diff(antes: Path, depois: Path, rel: str) -> tuple[str, int]:
    a = antes.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if antes.is_file() else []
    d = depois.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if depois.is_file() else []
    linhas = list(difflib.unified_diff(a, d, "antes/" + rel, "depois/" + rel, n=2))
    mudadas = sum(1 for x in linhas if (x.startswith("+") or x.startswith("-")) and not x.startswith(("+++", "---")))
    return "".join(linhas), mudadas


def prompt_motor(rec: dict, pasta: Path) -> str:
    achados = "\n".join(f"  - {a['job']} no segundo {a['t']}: {a['o_que']}" for a in rec.get("achados", [])[:6])
    arqs = "\n".join(f"  - {pasta / 'proposta' / a}   (copia de {a})" for a in rec["arquivos"])
    return f"""Você está melhorando o MOTOR do Estúdio de vídeo do João com uma mudança PEQUENA e segura.

PROBLEMA QUE SE REPETE: {rec['chave']}
{achados}
CAUSA (da revisão): {rec.get('causa') or '(não explicada)'}
CONSERTO SUGERIDO: {rec['o_que_muda']}

EDITE SÓ estas copias (não os originais, não outro arquivo):
{arqs}
Regras: a menor mudança que impede o erro de voltar (no máximo {LIM_LINHAS} linhas mudadas no total); não renomeie nem apague função
usada por outros; não mude formato de arquivo de saída; mantenha o estilo do código que já está lá; nada de renderizar, baixar ou gerar mídia.
Quando terminar escreva {pasta / 'resumo.txt'} com 1-2 frases em português simples dizendo O QUE mudou (o João lê). Resposta final: uma linha."""


def preparar(id_: str) -> dict:
    rec = carregar(id_)
    if not rec:
        raise ValueError("Melhoria não encontrada.")
    pasta = ensure(pasta_melhorias() / id_)
    try:
        if rec["tipo"] == "regras":
            _preparar_regras(rec, pasta)
        else:
            _preparar_motor(rec, pasta)
    except Exception as e:  # noqa: BLE001
        rec = carregar(id_) or rec
        rec.update(estado="falhou", motivo=_comum.erro_simples(e), fim=agora(), aplicar_apos_ver=False)
        _salvar(rec)
        return rec
    rec = carregar(id_)
    if rec.get("aplicar_apos_ver") and rec["estado"] == "pronta":   # "Aplicar" direto, sem Ver antes: prepara e aplica
        rec["aplicar_apos_ver"] = False
        _salvar(rec)
        return aplicar(id_)
    return rec


def _executar_ia(prompt: str, pasta: Path, tipo: str = "melhoria") -> int:
    import ia
    if not ia.disponivel():
        raise ValueError("Sem motor de IA conectado: abra Configurações.")
    s = ia.para_alteracao(ia.selecao(), modelo="sonnet", esforco="medium")
    return ia.executar(prompt, pasta / "ia.log", pasta / "ia.jsonl", pasta / "ia.pid", s, tipo=tipo)


def _preparar_motor(rec: dict, pasta: Path) -> None:
    for a in rec["arquivos"]:
        if not permitido(a):
            raise ValueError(f"O arquivo {a} não é do motor; não mexo nele.")
    shutil.rmtree(pasta / "proposta", ignore_errors=True)
    shutil.rmtree(pasta / "antes", ignore_errors=True)
    shas = {}
    for a in rec["arquivos"]:
        o = _comum.RAIZ / a
        shas[a] = sha(o)
        _copiar(o, pasta / "antes" / a)
        _copiar(o, pasta / "proposta" / a)
    code = _executar_ia(prompt_motor(rec, pasta), pasta)
    for a, h in shas.items():   # a IA tem acesso a tudo: se ela mexeu no original, volta já
        if sha(_comum.RAIZ / a) != h:
            shutil.copy2(pasta / "antes" / a, _comum.RAIZ / a)
            raise ValueError("A IA mexeu direto no arquivo original; desfiz e não vale. Tente de novo.")
    diff, n = "", 0
    mudou = []
    for a in rec["arquivos"]:
        d, m = _diff(pasta / "antes" / a, pasta / "proposta" / a, a)
        diff += d
        n += m
        if m:
            mudou.append(a)
    for x in (pasta / "proposta").rglob("*"):   # a IA não pode criar arquivo novo na proposta
        if x.is_file() and _comum.rel(x).split("/proposta/", 1)[-1] not in rec["arquivos"]:
            raise ValueError("A IA criou um arquivo que não estava no pedido; não vale.")
    if code != 0 and not n:
        raise ValueError("A IA não terminou (teto de gasto ou prazo). Tente de novo.")
    if not n:
        raise ValueError("A IA não achou o que mudar nesse arquivo.")
    if n > LIM_LINHAS or len(mudou) > LIM_ARQUIVOS:
        raise ValueError(f"A mudança ficou grande demais ({n} linhas em {len(mudou)} arquivo(s)): o limite é {LIM_LINHAS} linhas. Não proponho.")
    resumo = (pasta / "resumo.txt").read_text(encoding="utf-8", errors="replace").strip()[:500] if (pasta / "resumo.txt").is_file() else ""
    rec.update(estado="pronta", diff=diff, linhas_mudadas=n, resumo=resumo or rec["o_que_muda"], sha_antes=shas, fim_prep=agora(), motivo="")
    _salvar(rec)


# regras: o mesmo gate, com a IA do aprendizado.py trabalhando numa copia do regras.json

def _preparar_regras(rec: dict, pasta: Path) -> None:
    import aprendizado
    alvo = _comum.RAIZ / rec["pasta"]
    real = alvo / "regras.json"
    novas = novas_do_historico(alvo)
    if not novas:
        raise ValueError("Não tem histórico novo pra passar a limpo.")
    shutil.rmtree(pasta / "proposta", ignore_errors=True)
    shutil.rmtree(pasta / "antes", ignore_errors=True)
    copia = pasta / "proposta" / "regras.json"
    antes_p = pasta / "antes" / rec["arquivos"][0]
    if real.is_file():
        _copiar(real, copia)
        _copiar(real, antes_p)
    else:
        ensure(copia.parent).joinpath("regras.json").write_text('{"regras": []}\n', encoding="utf-8")
    pr = aprendizado.prompt_absorver(alvo, novas).replace(str(alvo / "regras.json"), str(copia))
    pr += ("\n\nIMPORTANTE: edite SOMENTE a copia " + str(copia) + " (o original só muda quando o João der OK). "
           "Linhas de tipo `revisao` vêm da revisão do Estúdio (causa e conserto): só viram regra se repetirem em 2+ vídeos; "
           "nelas o `origem` da regra é \"revisão do Estúdio\".")
    h0 = sha(real)
    _executar_ia(pr, pasta, tipo="melhoria")
    if sha(real) != h0:
        if antes_p.is_file():
            shutil.copy2(antes_p, real)
        raise ValueError("A IA mexeu direto no regras.json original; desfiz e não vale. Tente de novo.")
    novo = ler_json(copia, None)
    if not isinstance(novo, dict) or not isinstance(novo.get("regras"), list):
        raise ValueError("A IA deixou o regras.json inválido; não vale.")
    antes = (ler_json(antes_p, {}) or {}).get("regras") or []
    mapa_a = {r.get("id"): r for r in antes if isinstance(r, dict)}
    mapa_d = {r.get("id"): r for r in novo["regras"] if isinstance(r, dict)}
    criadas = [mapa_d[i] for i in mapa_d if i not in mapa_a]
    reescritas = [{"id": i, "antes": str(mapa_a[i].get("texto", ""))[:400], "depois": str(mapa_d[i].get("texto", ""))[:400]}
                  for i in mapa_d if i in mapa_a and (mapa_a[i].get("texto") != mapa_d[i].get("texto") or mapa_a[i].get("evitar") != mapa_d[i].get("evitar"))]
    juntadas = [i for i in mapa_a if i not in mapa_d]
    if not (criadas or reescritas or juntadas):
        raise ValueError("A IA não achou nada durável nesse histórico (nenhuma regra nova ou mudada).")
    if len(novo["regras"]) > aprendizado.LIMITE_REGRAS:
        raise ValueError(f"A proposta passou do teto de {aprendizado.LIMITE_REGRAS} regras; não vale.")
    rec.update(estado="pronta", regras_novas=[{"id": r.get("id"), "categoria": r.get("categoria"), "texto": str(r.get("texto", ""))[:400]} for r in criadas],
               regras_reescritas=reescritas, regras_juntadas=juntadas, sha_antes={rec["arquivos"][0]: h0},
               resumo=f"{len(criadas)} regra(s) nova(s), {len(reescritas)} reescrita(s)" + (f", {len(juntadas)} juntada(s)" if juntadas else ""),
               fim_prep=agora(), motivo="")
    _salvar(rec)


# ───────────────────────────── aplicar (prova antes de gravar) ─────────────────────────────

def _py_compile(p: Path) -> str:
    r = subprocess.run([sys.executable, "-m", "py_compile", str(p)], capture_output=True, text=True)
    return "" if r.returncode == 0 else (r.stderr or r.stdout).strip().splitlines()[-1][:300]


def _node_check(p: Path) -> str:
    node = shutil.which("node")
    if not node:
        return ""
    r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True)
    return "" if r.returncode == 0 else (r.stderr or r.stdout).strip().splitlines()[-1][:300]


def _sintaxe(rel: str) -> str:
    p = _comum.RAIZ / rel
    return _py_compile(p) if p.suffix == ".py" else (_node_check(p) if p.suffix in (".js", ".mjs") else "")


def _testes_para(rec: dict) -> list[str]:
    mods = list(TESTES_BASE)
    if any(a.endswith("conferir_video.py") for a in rec.get("arquivos", [])):
        mods += ["test_polimento_6", "test_polimento_7", "test_formato_do_zero"]
    return [m for m in mods if (_comum.ESTUDIO / "tests" / f"{m}.py").is_file()]


def falhando_nos_testes(mods: list[str], timeout: int = 600) -> tuple[set, str]:
    """Roda os testes e devolve (nomes que falham, resumo). Falha em rodar = tudo falha."""
    if not mods:
        return set(), "sem testes"
    r = subprocess.run([sys.executable, "-m", "unittest", *mods], cwd=str(_comum.ESTUDIO / "tests"), capture_output=True, text=True, timeout=timeout)
    falhas = set(re.findall(r"^(?:ERROR|FAIL): (.+)$", r.stderr, re.M))
    ran = re.search(r"^Ran (\d+) tests?", r.stderr, re.M)
    if not ran:
        return {"(os testes não rodaram)"}, (r.stderr or r.stdout)[-300:]
    return falhas, f"{ran.group(1)} testes, {len(falhas)} com falha"


def _faltas_do_estilo(slug: str) -> set:
    if not slug:
        return set()
    try:
        import formatos
        return set(formatos.validar(slug))
    except Exception as e:  # noqa: BLE001
        return {"validar quebrou: " + str(e)[:120]}


def quadro_de_prova(rec: dict, pasta: Path) -> tuple[bool, str]:
    """Estilo de motor com render.py na base/: renderiza UM quadro (o do achado) com o motor NOVO e guarda ao lado do quadro de antes."""
    sb = _comum.RAIZ / (rec.get("sandbox") or "")
    base = _comum.RAIZ / "formatos" / (rec.get("formato") or "-") / "base" / "render.py"
    if not (rec.get("formato") and base.is_file() and (sb / "cenas.json").is_file()):
        return True, "sem quadro de prova (estilo gravado ou sem cenas.json): vale sintaxe, validar e testes"
    if "--quadro" not in base.read_text(encoding="utf-8", errors="ignore"):
        return True, "o render.py desse estilo não renderiza um quadro só: vale sintaxe, validar e testes"
    t = float(rec.get("t") or 0)
    import time
    t0 = time.time()
    r = subprocess.run([sys.executable, str(base), "--cenas", "cenas.json", "--quadro", f"{t:.2f}"], cwd=str(sb),
                       capture_output=True, text=True, timeout=900)
    png = sb / "quadros" / f"{t:06.2f}.png"
    if r.returncode != 0 or not png.is_file() or png.stat().st_mtime < t0 - 1:
        return False, "o motor com a mudança não renderizou o quadro: " + ((r.stderr or r.stdout).strip().splitlines() or ["sem mensagem"])[-1][:200]
    try:
        from PIL import Image
        im = Image.open(png).convert("RGB")
        im.thumbnail((360, 640))
        im.save(pasta / "depois.jpg", quality=84)
        vid = _comum.RAIZ / (rec.get("video") or "")
        if vid.is_file():
            import revisao
            revisao.quadro(vid, t, pasta / "antes.jpg")
    except Exception as e:  # noqa: BLE001
        return False, "o quadro de prova saiu inválido: " + str(e)[:120]
    return True, f"quadro do segundo {t:g} renderizado com o motor novo"


def aplicar(id_: str) -> dict:
    rec = carregar(id_)
    if not rec or rec["estado"] not in ("aplicando", "pronta"):
        raise ValueError("Essa melhoria não está pronta pra aplicar.")
    pasta = pasta_melhorias() / id_
    passos = []
    rec.update(estado="aplicando", prova={"passos": passos}, motivo="")
    _salvar(rec)
    reais = {a: _comum.RAIZ / a for a in rec["arquivos"]}

    def restaurar():
        for a, p in reais.items():
            b = pasta / "antes" / a
            if b.is_file():
                shutil.copy2(b, p)

    def falhou(motivo: str, restaurado: bool = True):
        if restaurado:
            restaurar()
        rec.update(estado="falhou", motivo=motivo, fim=agora())
        _salvar(rec)
        return rec

    for a, p in reais.items():   # o arquivo mudou desde que a IA preparou a copia? (outra frente mexendo) então a prévia vale pouco
        if sha(p) != (rec.get("sha_antes") or {}).get(a):
            return falhou(f"{a} mudou depois da prévia (alguém mexeu nele). Clique em Ver a mudança pra eu preparar de novo.", restaurado=False)
    if rec["tipo"] == "regras":
        return _aplicar_regras(rec, pasta, reais, passos, falhou)
    faltas0 = _faltas_do_estilo(rec.get("formato", ""))
    mods = _testes_para(rec)
    ruins0, _ = falhando_nos_testes(mods)
    for a, p in reais.items():
        tmp = p.with_suffix(p.suffix + ".melhoria-tmp")
        shutil.copy2(pasta / "proposta" / a, tmp)
        os.replace(tmp, p)
    for a in reais:
        erro = _sintaxe(a)
        passos.append({"nome": f"Sintaxe de {Path(a).name}", "ok": not erro, "detalhe": erro or "ok"})
        if erro:
            return falhou(f"A mudança em {Path(a).name} não passou na sintaxe ({erro}). Voltei como estava.")
    novas_faltas = _faltas_do_estilo(rec.get("formato", "")) - faltas0
    passos.append({"nome": "Contrato do estilo (formatos.py validar)", "ok": not novas_faltas, "detalhe": "; ".join(sorted(novas_faltas))[:300] or "nenhuma falta nova"})
    if novas_faltas:
        return falhou("O estilo passou a faltar no contrato: " + "; ".join(sorted(novas_faltas))[:200] + ". Voltei como estava.")
    ruins1, resumo = falhando_nos_testes(mods)
    novas = ruins1 - ruins0
    passos.append({"nome": "Testes (" + ", ".join(mods) + ")", "ok": not novas, "detalhe": resumo if not novas else "falhou: " + "; ".join(sorted(novas))[:300]})
    if novas:
        return falhou("Os testes quebraram com a mudança (" + "; ".join(sorted(novas))[:160] + "). Voltei como estava.")
    ok, msg = quadro_de_prova(rec, pasta)
    passos.append({"nome": "Quadro de prova", "ok": ok, "detalhe": msg})
    if not ok:
        return falhou(msg + ". Voltei como estava.")
    rec.update(estado="aplicada", aplicada_em=agora(), sha_depois={a: sha(p) for a, p in reais.items()},
               tem_quadros=(pasta / "depois.jpg").is_file() and (pasta / "antes.jpg").is_file())
    _salvar(rec)
    _registrar_conserto(rec)
    return rec


def _registrar_conserto(rec: dict) -> None:
    """REGRA Nº 2, passo 4: o conserto fica registrado (causa + arquivo mudado) no historico.jsonl do modelo."""
    try:
        cli = _comum.cliente(rec.get("cliente") or "")
        mod = _comum.modelo(cli, rec.get("modelo") or "") if cli else None
        if not mod:
            return
        append_jsonl(mod["pasta"] / "aprendizado" / "historico.jsonl", {
            "tipo": "conserto", "categoria": "qa", "chave": rec.get("chave") or rec["tipo"], "texto": rec["titulo"][:300],
            "causa": rec.get("causa", ""), "conserto": "mudado em " + ", ".join(rec["arquivos"]) + ": " + (rec.get("resumo") or rec["o_que_muda"])[:300],
            "origem": "estudio", "createdAt": hoje(), "job": f"{rec.get('cliente')}/{rec.get('slug')}"})
    except Exception:  # noqa: BLE001
        pass


def _aplicar_regras(rec: dict, pasta: Path, reais: dict, passos: list, falhou) -> dict:
    import aprendizado
    p = next(iter(reais.values()))
    prop = ler_json(pasta / "proposta" / "regras.json", None)
    if not isinstance(prop, dict) or not isinstance(prop.get("regras"), list):
        return falhou("A proposta de regras sumiu ou ficou inválida.", restaurado=False)
    alvo = p.parent
    hist = alvo / "historico.jsonl"
    if hist.is_file():
        _copiar(hist, pasta / "antes" / (rec["pasta"] + "/historico.jsonl"))
    novas = novas_do_historico(alvo)
    ensure(p.parent)
    if p.is_file():
        _copiar(p, pasta / "antes" / rec["arquivos"][0])
    gravar_json(p, prop)
    passos.append({"nome": "regras.json válido", "ok": True, "detalhe": f"{len(prop['regras'])} regras"})
    novos_hashes = sorted({_hash_linha(x) for x in novas})
    gravar_json(alvo / ".absorvido.json", {"hashes": sorted(_absorvidas(alvo) | set(novos_hashes)), "em": agora()})
    rec["hashes_marcados"] = novos_hashes
    r = aprendizado.arquivar_historico(alvo, motivo="passar a limpo (OK do João na tela)")
    passos.append({"nome": "Histórico arquivado", "ok": True, "detalhe": f"{r.get('arquivadas', 0)} linhas arquivadas, {r.get('ficaram', 0)} ficaram (vídeo aberto segura o resto)"})
    rec.update(estado="aplicada", aplicada_em=agora(), sha_depois={rec["arquivos"][0]: sha(p)})
    _salvar(rec)
    return rec


# ───────────────────────────── desfazer ─────────────────────────────

def desfazer(id_: str) -> dict:
    rec = carregar(id_)
    if not rec or rec["estado"] != "aplicada":
        raise ValueError("Só dá pra desfazer uma melhoria aplicada.")
    pasta = pasta_melhorias() / id_
    for a in rec["arquivos"]:
        if sha(_comum.RAIZ / a) != (rec.get("sha_depois") or {}).get(a):
            raise ValueError(f"{a} mudou depois que apliquei; não desfaço pra não perder essa outra mudança.")
    for a in rec["arquivos"]:
        b = pasta / "antes" / a
        if b.is_file():
            shutil.copy2(b, _comum.RAIZ / a)
    if rec["tipo"] == "regras":
        h = pasta / "antes" / (rec["pasta"] + "/historico.jsonl")
        real = _comum.RAIZ / rec["pasta"] / "historico.jsonl"
        if h.is_file():   # as linhas voltam; o arquivo/historico-AAAA.jsonl continua lá (nada é apagado)
            shutil.copy2(h, real)
        arq_abs = _comum.RAIZ / rec["pasta"] / ".absorvido.json"
        resto = sorted(_absorvidas(_comum.RAIZ / rec["pasta"]) - set(rec.get("hashes_marcados") or []))
        gravar_json(arq_abs, {"hashes": resto, "em": agora()})
    rec.update(estado="desfeita", resolvido_em=agora())
    return _salvar(rec)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["preparar", "aplicar", "desfazer", "listar"])
    ap.add_argument("id", nargs="?")
    a = ap.parse_args()
    if a.cmd == "listar":
        for r in listar():
            print(r["id"], r["estado"], r["titulo"][:100])
        return
    f = {"preparar": preparar, "aplicar": aplicar, "desfazer": desfazer}[a.cmd]
    try:
        r = f(a.id)
        print(r["estado"], r.get("motivo", ""))
    except ValueError as e:
        print("ERRO", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
