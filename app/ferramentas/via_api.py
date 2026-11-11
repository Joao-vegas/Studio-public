"""Roda tarefas do Estúdio no Claude Code cobrando da API (crédito do Console), nunca do limite da assinatura.

Chave: ANTHROPIC_API_KEY em app/.env (ou no ambiente; ~/.config/estudio/anthropic_api_key só como reserva).
Se o Claude Code não confirmar que está usando a chave (apiKeySource), a tarefa é parada na hora.
Exceção: `fila_cobranca = assinatura` em app/config.json (Configurações) roda sem chave e sem essa trava, no limite da semana.

  python3 app/ferramentas/via_api.py testar
  python3 app/ferramentas/via_api.py fila app/api/<nome>/fila.json [--fundo] [--refazer <tarefa>]
  python3 app/ferramentas/via_api.py status app/api/<nome>

fila.json: {"teto_usd": 90, "etapas": [[{"nome", "prompt", "modelo": "opus|sonnet", "orcamento_usd": 8}, ...], ...]}
Etapas rodam em ordem; as tarefas de uma etapa rodam juntas. Cada tarefa grava log.jsonl, resultado.md e custo.json.
Rodar a mesma fila de novo continua de onde parou: tarefa com custo.json "ok" é pulada (--refazer força).
O teto vale pra fila inteira (conta o que as puladas já gastaram) e cada tarefa recebe só a parte que cabe nele.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, claude_bin, ler_json  # noqa: E402

CHAVE = Path.home() / ".config" / "estudio" / "anthropic_api_key"
LIVRO = RAIZ / "app" / "custos" / "api.jsonl"
LIVRO_PLANO = RAIZ / "app" / "custos" / "execucoes.jsonl"
CONFIG = RAIZ / "app" / "config.json"
AVISO_ASSINATURA = "Cobrança da fila: assinatura. Vai gastar seu limite da semana (nada sai do crédito da API)."
MINIMO_USD = 0.30
PREAMBULO = """REGRAS DA FILA (valem acima de tudo):
- Sem commit. Nada pago de imagem, vídeo ou voz (kie.ai, ElevenLabs). Não reinicie o servidor 7655.
- Nunca rode nada em segundo plano (run_in_background, Monitor, '&', subagente em background): neste modo a sessão
  termina quando você para de responder e o trabalho fica pela metade. Pra esperar, use Bash de até 5 min, quantas vezes precisar.
- Termine em até 10 linhas: o que fez, o que não fez e por quê.

"""
ESPERA = ("em segundo plano", "aviso quando", "ainda rodando", "espero o aviso")
_trava = threading.Lock()
_filhos: set = set()


def chave() -> str:
    import chaves   # app/.env é a casa de todas as chaves; o arquivo antigo em ~/.config/estudio fica como reserva
    k = os.environ.get("ANTHROPIC_API_KEY") or chaves.chave("ANTHROPIC_API_KEY") or (CHAVE.read_text().strip() if CHAVE.is_file() else "")
    if not k:
        sys.exit("Sem chave da API: ponha ANTHROPIC_API_KEY em app/.env (ou cole em Configurações).")
    return k


def cobranca_fila() -> str:
    """'api' (padrão: crédito do Console, com trava) ou 'assinatura' (limite da semana do plano), escolhida em Configurações."""
    return "assinatura" if (ler_json(CONFIG, {}) or {}).get("fila_cobranca") == "assinatura" else "api"


def ambiente(api_key: str | None = None) -> dict:
    """api_key: força a cobrança da API com essa chave (usado pra testar uma chave recém-colada)."""
    if cobranca_fila() == "assinatura" and not api_key:   # login do plano: sem chave da API no ambiente
        return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "ANTHROPIC_API_KEY"}
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE_OAUTH", "CLAUDECODE", "CLAUDE_CODE_SESSION"))}
    env["ANTHROPIC_API_KEY"] = api_key or chave()
    return env


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def incompleta(texto: str) -> bool:
    """Resultado vazio ou com cara de 'ainda vou fazer' (a sessão -p acabou antes do trabalho)."""
    t = (texto or "").strip().lower()
    return not t or any(m in t for m in ESPERA)


def vivo(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False


def matar_grupo(pid) -> None:
    try:
        os.killpg(int(pid), signal.SIGTERM)
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        pass


def ler_custo(pasta: Path) -> dict:
    try:
        return json.loads((pasta / "custo.json").read_text())
    except (OSError, ValueError):
        return {}


def rodar(pasta: Path, t: dict, orcamento: float | None = None, api_key: str | None = None) -> dict:
    plano = cobranca_fila() == "assinatura" and not api_key
    pasta.mkdir(parents=True, exist_ok=True)
    orc = round(float(orcamento if orcamento is not None else t.get("orcamento_usd", 8)), 2)
    cmd = [claude_bin(), "-p", "--model", t.get("modelo", "opus"), "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions", "--add-dir", str(RAIZ), "--max-budget-usd", str(orc)]
    if t.get("esforco"):   # ex.: "high" (pedido do João: Sonnet alterando com esforço alto)
        cmd += ["--effort", t["esforco"]]
    out = {"nome": t["nome"], "inicio": agora(), "estado": "rodando", "usd": 0.0, "orcamento_usd": orc}
    (pasta / "custo.json").write_text(json.dumps(out, ensure_ascii=False))
    texto, fonte = "", None
    with open(pasta / "log.jsonl", "w") as log:
        p = subprocess.Popen(cmd, cwd=RAIZ, env=ambiente(api_key), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)
        _filhos.add(p.pid)
        (pasta / "custo.json").write_text(json.dumps({**out, "pid": p.pid}, ensure_ascii=False))
        pre = PREAMBULO
        if t.get("pode_reiniciar"):   # fila em que o João não está usando a tela: pode recarregar o 7655 pra ver a mudança
            pre = pre.replace("Não reinicie o servidor 7655.", "Pode reiniciar o servidor 7655 quando precisar ver a mudança "
                              "na tela (kill $(pgrep -f 'Estúdio/app/interface/servidor.py'); o launchd sobe de novo; "
                              "confira com curl que voltou; se der conexão recusada, espere e tente de novo).")
        p.stdin.write(pre + t["prompt"]); p.stdin.close()
        for linha in p.stdout:
            log.write(linha); log.flush()
            try:
                ev = json.loads(linha)
            except ValueError:
                continue
            if ev.get("type") == "system" and ev.get("subtype") == "init":
                fonte = ev.get("apiKeySource")
                if fonte != "ANTHROPIC_API_KEY" and not plano:   # nunca gastar a assinatura sem o João ter escolhido
                    p.kill()
                    out.update(estado="erro", erro=f"não está cobrando da API (apiKeySource={fonte})")
                    break
            if ev.get("type") == "result":
                texto = ev.get("result") or ""
                out.update(usd=round(float(ev.get("total_cost_usd") or 0), 4), uso=ev.get("usage"),
                           estado="erro" if ev.get("is_error") else "ok", turnos=ev.get("num_turns"))
        p.wait()
        _filhos.discard(p.pid)
    if out["estado"] == "rodando":
        out.update(estado="erro", erro=f"saiu sem resultado (código {p.returncode})")
    if out["estado"] == "ok" and incompleta(texto):
        out.update(estado="incompleta", erro="terminou sem concluir (resultado vazio ou 'ainda rodando')")
    out.update(fim=agora(), fonte=fonte)
    (pasta / "resultado.md").write_text(texto)
    (pasta / "custo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    linha = {"quando": out["fim"], "fila": pasta.parent.name, "tarefa": t["nome"], "modelo": t.get("modelo", "opus"),
             "usd": out["usd"], "estado": out["estado"]}
    # No plano o valor é só o equivalente da API: vai pro livro das execuções (assinatura), nunca pro do dinheiro que saiu.
    with _trava, open(LIVRO_PLANO if plano else LIVRO, "a") as f:
        f.write(json.dumps(({"data": linha["quando"], "provedor": "claude", "modelo": linha["modelo"], "usd": linha["usd"],
                             "tokens": out.get("uso") or {}, "onde": f"fila {linha['fila']} · {linha['tarefa']}"} if plano else linha),
                           ensure_ascii=False) + "\n")
    return out


def limpar_orfas(base: Path) -> list[str]:
    """custo.json 'rodando' de uma fila que já morreu: mata o filho se ainda vive e marca 'interrompida'."""
    feitas = []
    for arq in sorted(base.glob("*/custo.json")):
        c = ler_custo(arq.parent)
        if c.get("estado") != "rodando":
            continue
        if vivo(c.get("pid")):
            matar_grupo(c["pid"])
        c.update(estado="interrompida", erro="a fila parou no meio desta tarefa", fim=c.get("fim") or agora())
        c.pop("pid", None)
        arq.write_text(json.dumps(c, ensure_ascii=False, indent=1))
        feitas.append(c.get("nome", arq.parent.name))
    return feitas


def dividir(etapa: list[dict], sobra: float) -> dict:
    """Orçamento de cada tarefa: o dela, mas sem a etapa passar do que sobra do teto (proporcional)."""
    total = sum(float(t.get("orcamento_usd", 8)) for t in etapa) or 1.0
    return {t["nome"]: round(min(float(t.get("orcamento_usd", 8)), sobra * float(t.get("orcamento_usd", 8)) / total), 2)
            for t in etapa}


def _parar(*_):
    for pid in list(_filhos):
        matar_grupo(pid)
    raise SystemExit("fila parada: tarefas em andamento foram encerradas")


def fila(arq: Path, refazer: tuple = ()) -> dict:
    cfg = json.loads(arq.read_text())
    base, teto, gasto = arq.parent, float(cfg.get("teto_usd", 90)), 0.0
    trava = base / "fila.pid"
    if trava.is_file() and vivo(trava.read_text().strip()) and int(trava.read_text().strip()) != os.getpid():
        sys.exit("essa fila já está rodando")
    trava.write_text(str(os.getpid()))
    antigos = {}
    if threading.current_thread() is threading.main_thread():
        antigos = {sig: signal.signal(sig, _parar) for sig in (signal.SIGINT, signal.SIGTERM)}
    estado = {"inicio": agora(), "teto_usd": teto, "etapas": [], "interrompidas": limpar_orfas(base)}
    if cobranca_fila() == "assinatura":
        estado["aviso"] = AVISO_ASSINATURA
        print(AVISO_ASSINATURA, flush=True)
    salvar = lambda: (base / "status.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    try:
        for i, etapa in enumerate(cfg["etapas"]):
            if gasto >= teto - MINIMO_USD:
                estado["parou"] = f"teto de US$ {teto} atingido antes da etapa {i + 1}"
                break
            puladas, rodar_ja = [], []
            for t in etapa:
                c = ler_custo(base / t["nome"])
                if c.get("estado") == "ok" and t["nome"] not in refazer:
                    puladas.append({"nome": t["nome"], "estado": "pulada", "usd": c.get("usd", 0)})
                    gasto += float(c.get("usd") or 0)
                else:
                    rodar_ja.append(t)
            orc = dividir(rodar_ja, teto - gasto)
            sem = [{"nome": t["nome"], "estado": "sem crédito", "usd": 0.0} for t in rodar_ja if orc[t["nome"]] < MINIMO_USD]
            rodar_ja = [t for t in rodar_ja if orc[t["nome"]] >= MINIMO_USD]
            estado["etapas"].append({"etapa": i + 1, "tarefas": [t["nome"] for t in etapa], "estado": "rodando"}); salvar()
            res = []
            if rodar_ja:
                with ThreadPoolExecutor(max_workers=len(rodar_ja)) as ex:
                    res = list(ex.map(lambda t: rodar(base / t["nome"], t, orc[t["nome"]]), rodar_ja))
            gasto += sum(r["usd"] for r in res)
            estado["etapas"][-1].update(estado="ok", resultados=puladas + res + sem, gasto_total_usd=round(gasto, 4)); salvar()
            if any(r.get("erro", "").startswith("não está cobrando") for r in res):
                estado["parou"] = "a chave da API não foi usada: parei pra não gastar a assinatura"
                break
    finally:
        estado.update(fim=agora(), gasto_total_usd=round(gasto, 4)); salvar()
        trava.unlink(missing_ok=True)
        for sig, h in antigos.items():
            signal.signal(sig, h)
    return estado


def testar_dados(api_key: str | None = None) -> dict:
    r = rodar(RAIZ / "app" / "api" / "_teste", {"nome": "teste", "prompt": "Responda só: ok", "modelo": "sonnet", "orcamento_usd": 0.2}, api_key=api_key)
    return {k: r.get(k) for k in ("estado", "fonte", "usd", "erro")}


def testar() -> None:
    print(json.dumps(testar_dados(), ensure_ascii=False))


def status(pasta: Path) -> None:
    s = json.loads((pasta / "status.json").read_text()) if (pasta / "status.json").is_file() else {}
    print(f"gasto: US$ {s.get('gasto_total_usd', 0)} de {s.get('teto_usd')} · {'terminou ' + s['fim'] if s.get('fim') else 'rodando'}")
    if s.get("parou"):
        print(f"  parou: {s['parou']}")
    puladas = {r["nome"] for e in s.get("etapas", []) for r in e.get("resultados", []) if r.get("estado") == "pulada"}
    total, conta = 0.0, {}
    for d in sorted(pasta.glob("*/custo.json")):
        c = json.loads(d.read_text())
        est = "pulada" if c["nome"] in puladas else c["estado"]
        conta[est] = conta.get(est, 0) + 1
        total += float(c.get("usd") or 0)
        print(f"  {c['nome']:22s} {est:12s} US$ {c.get('usd', 0):<8} {c.get('erro', '')}")
    print("  " + " · ".join(f"{n} {e}" for e, n in sorted(conta.items())) + f" · total gasto nas tarefas: US$ {round(total, 2)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    refazer = tuple(a[i + 1] for i, x in enumerate(a) if x == "--refazer" and i + 1 < len(a))
    if not a or a[0] == "testar":
        testar()
    elif a[0] == "fila" and "--fundo" in a:
        log = Path(a[1]).parent / "fila.log"
        extra = [x for r in refazer for x in ("--refazer", r)]
        subprocess.Popen([sys.executable, __file__, "fila", a[1], *extra], cwd=RAIZ, start_new_session=True,
                         stdout=open(log, "a"), stderr=subprocess.STDOUT)
        print(f"rodando em segundo plano · acompanhe: python3 {__file__} status {Path(a[1]).parent}")
    elif a[0] == "fila":
        fila(Path(a[1]), refazer)
    elif a[0] == "status":
        status(Path(a[1]))
