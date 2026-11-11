#!/usr/bin/env python3
"""
aprendizado — ciclo de vida do que o João ensina, pra regra só SOMAR e nunca inchar.

Duas peças, com papéis diferentes:

  historico.jsonl   CAIXA DE ENTRADA. O cru: o que o João mandou naquele vídeo, palavra por palavra.
                    Serve enquanto o vídeo está aberto (ele ainda vai conferir, ainda pode cobrar).
  regras.json       O PRODUTO. O que já virou instrução durável. É isso que o modelo lê antes de
                    produzir. Uma regra = um assunto.

O ciclo:
  1. João manda feedback  → entra no histórico.
  2. Vira regra           → procura a regra DO MESMO ASSUNTO: se existe, MELHORA ela (reescreve texto
                            e evitar, sobe o peso, preserva `cobre`/`desde`); se não existe, cria uma.
                            Regra nunca é anexada em cima da outra — é reescrita.
  3. Vídeo fechado        → ("fechar e liberar espaço") o histórico daquele modelo é ARQUIVADO. O que
                            ele ensinou já está na regra; guardar o cru duas vezes só faz o modelo ler
                            lixo antes de produzir. O arquivo fica em aprendizado/arquivo/ (recuperável).

🔴 Histórico de vídeo AINDA ABERTO não é arquivado: enquanto ele não fecha, o que ele mandou tem que
   continuar lá inteiro.

CLI:
  aprendizado.py inventario                    quanto cada modelo carrega hoje
  aprendizado.py enxugar [--aplicar]           desfaz blocão, junta regra repetida, mede o orçamento
  aprendizado.py fechar <pasta-aprendizado> [--job slug]     arquiva o histórico absorvido
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, agora, ensure, gravar_json, hoje, ler_json
import regras as _regras

# Orçamento: o modelo lê isso ANTES de cada produção. Passou disso, ele para de ler com atenção.
# Alvo: ~600 caracteres por regra. Os limites abaixo são ALARME — passou disso, o arquivo voltou a
# inchar e a próxima correção tem que MELHORAR uma regra existente em vez de acrescentar mais uma.
LIMITE_REGRAS = 24          # regras por modelo
LIMITE_CHARS_REGRA = 1800   # texto + evitar de uma regra (os blocões antigos tinham 3.000 a 8.700)
LIMITE_TEXTO_REGRA = 600    # aviso (não alarme): regra com `texto` acima disso é cortada antes de chegar na IA (resumo_regras)
LIMITE_CHARS_TOTAL = 20000  # o arquivo inteiro
SEMELHANTE = 0.86           # acima disso, duas regras falam do mesmo assunto


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def _tamanho(r: dict) -> int:
    return len(str(r.get("texto", ""))) + len(str(r.get("evitar", "")))


# ───────────────────────────── inventário ─────────────────────────────

def pastas() -> list[Path]:
    """Toda pasta de aprendizado do repositório: dos modelos e a geral de cada cliente."""
    out = set()
    for padrao in ("*/*Content/modelos/*/aprendizado", "*/*Content/aprendizado",
                   "Geral/modelos/*/aprendizado", "app/aprendizado/*"):
        for p in RAIZ.glob(padrao):
            if p.is_dir() and "_sandbox" not in str(p):
                out.add(p)
    return sorted(out)


def historico(pasta: Path) -> list[dict]:
    p = Path(pasta) / "historico.jsonl"
    if not p.exists():
        return []
    linhas = []
    for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if l.strip():
            try:
                linhas.append(json.loads(l))
            except ValueError:
                linhas.append({"tipo": "bruto", "texto": l[:400]})
    return linhas


def orcamento(pasta: Path) -> dict:
    d = ler_json(Path(pasta) / "regras.json", {}) or {}
    rs = d.get("regras", [])
    h = historico(pasta)
    grandes = [r.get("id") for r in rs if _tamanho(r) > LIMITE_CHARS_REGRA]
    return {"pasta": str(Path(pasta).relative_to(RAIZ)) if Path(pasta).is_absolute() else str(pasta),
            "regras": len(rs), "chars": sum(_tamanho(r) for r in rs), "historico": len(h),
            "historico_kb": round(sum(len(json.dumps(x, ensure_ascii=False)) for x in h) / 1024, 1),
            "blocao": any(str(r.get("id", "")).endswith("-consolidado") for r in rs),
            "regras_grandes": grandes,
            "acima_de_600": [r.get("id") for r in rs if len(str(r.get("texto") or "")) > LIMITE_TEXTO_REGRA],
            "estourado": len(rs) > LIMITE_REGRAS or sum(_tamanho(r) for r in rs) > LIMITE_CHARS_TOTAL or bool(grandes)}


# ───────────────────── desfazer o blocão e juntar repetida ─────────────────────

def desconsolidar(pasta: Path) -> dict:
    """Desfaz o agrupamento por categoria (`<categoria>-consolidado`), voltando às regras atômicas.

    Juntar 20 regras de b-roll num texto de 8.759 caracteres reduz a CONTAGEM e piora tudo o mais:
    não dá pra melhorar "a regra sobre X" quando X é o parágrafo 14 de um blocão, que é justamente o
    que o João pede (achar a regra do assunto e reescrever). Uma regra = um assunto.
    """
    p = Path(pasta) / "regras.json"
    d = ler_json(p, {}) or {}
    info = d.get("consolidacao") or {}
    nome = info.get("arquivo", "")
    if not nome or Path(nome).name != nome or not (p.with_name(nome)).is_file():
        return {"pasta": str(pasta), "mudou": False, "motivo": "não estava consolidado"}
    antigo = ler_json(p.with_name(nome), {}) or {}
    atomicas = list(antigo.get("regras", []))
    conhecidas = {r.get("id") for r in atomicas}
    # regra criada DEPOIS do agrupamento (feedback novo) não pode se perder
    novas = [r for r in d.get("regras", [])
             if not str(r.get("id", "")).endswith("-consolidado") and r.get("id") not in conhecidas]
    d["regras"] = atomicas + novas
    d.pop("consolidacao", None)
    gravar_json(p, d)
    return {"pasta": str(pasta), "mudou": True, "de": len(ler_json(p.with_name(nome), {}).get("regras", [])),
            "regras": len(d["regras"]), "recuperadas_do_arquivo": len(atomicas), "criadas_depois": len(novas)}


def _fundir(a: dict, b: dict) -> dict:
    """Funde duas regras do mesmo assunto: fica o texto mais completo, o resto é preservado."""
    principal, outra = (a, b) if len(str(a.get("texto", ""))) >= len(str(b.get("texto", ""))) else (b, a)
    r = dict(principal)
    perdidos = _regras.tokens(_regras.instrucao(outra)) - _regras.tokens(_regras.instrucao(principal))
    if perdidos:                       # número/flag/caminho que só existia na outra: preserva o texto
        r["texto"] = str(r.get("texto", "")).rstrip() + "\n" + str(outra.get("texto", "")).strip()
    ev = [x for x in (str(principal.get("evitar", "")).strip(), str(outra.get("evitar", "")).strip()) if x]
    if len(ev) == 2 and _semelhante(ev[0], ev[1]) < SEMELHANTE:
        r["evitar"] = " ".join(ev)
    elif ev:
        r["evitar"] = max(ev, key=len)
    r["peso"] = max(int(principal.get("peso") or 5), int(outra.get("peso") or 5))
    datas = [str(x.get("desde") or x.get("createdAt") or "") for x in (a, b) if x.get("desde") or x.get("createdAt")]
    if datas:
        r["desde"] = min(datas)
    cobre = list(dict.fromkeys(list(a.get("cobre", [])) + list(b.get("cobre", [])) + [a.get("id"), b.get("id")]))
    r["cobre"] = [c for c in cobre if c and c != r.get("id")]
    return r


def _semelhante(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def juntar_repetidas(pasta: Path, limiar: float = SEMELHANTE) -> dict:
    """Junta regras que dizem a mesma coisa (mesmo id ou texto quase igual), sem perder nenhum valor."""
    p = Path(pasta) / "regras.json"
    d = ler_json(p, {}) or {}
    rs = d.get("regras", [])
    antes = len(rs)
    saida: list[dict] = []
    for r in rs:
        alvo = None
        for s in saida:
            if s.get("id") == r.get("id") or _semelhante(r.get("texto", ""), s.get("texto", "")) >= limiar:
                alvo = s; break
        if alvo is None:
            saida.append(dict(r))
        else:
            saida[saida.index(alvo)] = _fundir(alvo, r)
    # nenhum número, flag, caminho ou cor pode sumir na fusão
    perdidos = (set().union(*[_regras.tokens(_regras.instrucao(r)) for r in rs]) if rs else set()) - \
               (set().union(*[_regras.tokens(_regras.instrucao(r)) for r in saida]) if saida else set())
    if perdidos:
        raise ValueError(f"{pasta}: a fusão perderia valores concretos: {', '.join(sorted(perdidos))}")
    d["regras"] = saida
    gravar_json(p, d)
    return {"pasta": str(pasta), "antes": antes, "depois": len(saida)}


# Valor concreto = o que a regra perde e o vídeo sai errado: flag, medida, cor, caminho, número.
# NÃO conta "palavra/palavra" (o extrator das consolidações lia isso como caminho e enchia de falso
# positivo), e datas são tiradas antes: "o João pediu em 14/08" é diário, não critério.
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_CONCRETO = re.compile(r"""https?://[^\s"<>]+
  | (?:[\w.~@-]+/)+[\w.~@-]*\.[A-Za-z0-9]{2,5}\b
  | --[\w-]+
  | \#[0-9a-fA-F]{3,8}\b
  | \b\d+(?:[.,:x]\d+)+\b
  | \b\d{2,}\b""", re.X)


def concretos(regras_: list[dict]) -> set:
    txt = _DATA.sub(" ", "\n".join(_regras.instrucao(r) for r in regras_))
    return set(_CONCRETO.findall(txt))


def substituir(pasta: Path, novas: list[dict], perda_ok: list[str] | None = None) -> dict:
    """Troca as regras de um modelo por uma versão enxuta — e RECUSA se algo concreto se perder.

    Enxugar é cortar narrativa ("o João pediu em 05/08", a história do vídeo), nunca cortar critério.
    O que não pode sumir é valor concreto: número, flag (--legy), caminho, cor (#DC2626), medida.
    A checagem usa o mesmo extrator de tokens da consolidação de regras.
    """
    p = Path(pasta) / "regras.json"
    d = ler_json(p, {}) or {}
    antes = d.get("regras", [])
    ids_antes = {r.get("id") for r in antes}
    sem_origem = [r.get("id") for r in novas if r.get("id") not in ids_antes and not str(r.get("origem") or "").strip()]
    if sem_origem:   # regra inventada pelo agente: sem a frase do João em `origem`, não vira regra
        raise ValueError(f"{pasta}: regra nova sem `origem` (a frase do João): {', '.join(map(str, sem_origem))}")
    perdidos = concretos(antes) - concretos(novas) - set(perda_ok or [])
    if perdidos:
        raise ValueError(f"{pasta}: sumiria valor concreto: {', '.join(sorted(perdidos))}")
    arq = ensure(Path(pasta) / "arquivo") / f"regras-antes-de-enxugar-{hoje()}.json"
    if not arq.exists():
        gravar_json(arq, d)
    d["regras"] = novas
    d["enxugado"] = {"em": agora(), "de": len(antes), "para": len(novas), "arquivo": arq.name}
    gravar_json(p, d)
    return {"pasta": str(pasta), "de": len(antes), "para": len(novas),
            "chars": sum(_tamanho(r) for r in novas)}


# ───────────────────────────── fechar o vídeo ─────────────────────────────

def jobs_abertos() -> set[tuple]:
    """(cliente, modelo, slug) de todo vídeo que ainda não foi fechado — o histórico deles fica."""
    abertos = set()
    for j in (RAIZ / "app" / "jobs").glob("*/*/job.json"):
        d = ler_json(j, {}) or {}
        if d.get("status") not in ("arquivado",):
            abertos.add((d.get("cliente"), d.get("modelo"), d.get("slug")))
    return abertos


def pendentes(pasta: Path, ignorar_slug: str | None = None) -> tuple[list, list]:
    """Divide o histórico em (pode arquivar, tem que ficar).

    🔴 Enquanto existir vídeo ABERTO daquele modelo, o histórico dele não é tocado — o João ainda vai
    conferir a peça e o que ele mandou tem que continuar lá inteiro, entrada por entrada. Nem toda
    entrada tem o campo `job`, então a conta é por MODELO, não por entrada: um vídeo aberto segura o
    histórico todo. `ignorar_slug` é o vídeo que está sendo fechado agora (esse já não conta).
    """
    pasta = Path(pasta)
    modelo = pasta.parent.name
    partes = pasta.parts
    cli = partes[-5] if len(partes) >= 5 and partes[-3] == "modelos" else None
    h = historico(pasta)
    if any(m == modelo and (cli is None or c == cli) and s != ignorar_slug for c, m, s in jobs_abertos()):
        return [], h
    return h, []


def arquivar_historico(pasta: Path, motivo: str = "", ignorar_slug: str | None = None) -> dict:
    """Tira do histórico o que já virou regra e guarda em aprendizado/arquivo/ (não some, sai da frente)."""
    pasta = Path(pasta)
    vai, fica = pendentes(pasta, ignorar_slug)
    if not vai:
        return {"pasta": str(pasta), "arquivadas": 0, "ficaram": len(fica)}
    destino = ensure(pasta / "arquivo") / f"historico-{hoje()}.jsonl"
    with destino.open("a", encoding="utf-8") as f:
        for e in vai:
            f.write(json.dumps({**e, "arquivado_em": agora(), "motivo_do_arquivo": motivo},
                               ensure_ascii=False) + "\n")
    hp = pasta / "historico.jsonl"
    hp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in fica), encoding="utf-8")
    return {"pasta": str(pasta), "arquivadas": len(vai), "ficaram": len(fica), "arquivo": str(destino)}


def prompt_absorver(pasta: Path, entradas: list[dict]) -> str:
    """Prompt do fechamento: transformar o que sobrou de histórico em regra ANTES de arquivar."""
    d = ler_json(Path(pasta) / "regras.json", {}) or {}
    rs = sorted(d.get("regras", []), key=lambda r: -(r.get("peso") or 5))
    lista = "\n".join(f"  [{r.get('categoria','geral')}] {r.get('id')} (peso {r.get('peso')}): "
                      f"{str(r.get('texto',''))[:220]}" for r in rs)
    cru = "\n".join(f"  - ({e.get('createdAt','')}, {e.get('tipo','feedback')}) {str(e.get('texto',''))[:600]}"
                    + (f" | causa: {str(e.get('causa',''))[:300]} | conserto: {str(e.get('conserto',''))[:300]}" if e.get('causa') or e.get('conserto') else "")
                    for e in entradas[-40:])
    return f"""Você está no repositório producao-reels, fechando um vídeo. Trabalho: passar a limpo o
APRENDIZADO de {Path(pasta).parent.name} antes de arquivar o histórico.

REGRAS QUE JÁ EXISTEM ({len(rs)}):
{lista}

HISTÓRICO QUE AINDA NÃO VIROU REGRA ({len(entradas)} entradas):
{cru}

O QUE FAZER, entrada por entrada:
1. Isso já é assunto de alguma regra acima? Se SIM, **melhore aquela regra**: reescreva `texto` e
   `evitar` incorporando o que faltava, suba o `peso` se ele cobrou de novo, e PRESERVE `cobre` e
   `desde`. Reescrever, nunca anexar parágrafo no fim.
2. Se NÃO existe regra do assunto, crie UMA regra nova.
3. Se a entrada não ensina nada durável (elogio, "ficou bom", combinado de um vídeo só), ignore.
4. ORÇAMENTO: no máximo {LIMITE_REGRAS} regras neste modelo, mirando ~600 caracteres por regra e
   nunca passando de {LIMITE_CHARS_REGRA}. Estourou? Junte as duas regras mais próximas ou corte narrativa —
   mas NUNCA jogue fora número, flag, caminho, cor ou medida concreta.
5. A regra é instrução, não diário: diga o critério e o número. Sem "o João pediu em 05/08", sem
   contar a história do vídeo. O que NÃO fazer vai em `evitar`.

Edite só {Path(pasta)}/regras.json. Formato de cada regra:
{{"id":"kebab-case","categoria":"legenda|broll|beats|layout|enquadramento|audio|cards|copy|qa|processo",
  "peso":1-10,"texto":"o critério, com o número concreto","evitar":"o erro que não pode voltar","desde":"AAAA-MM-DD"}}
JSON válido, UTF-8. Não mexa no histórico (quem arquiva é a ferramenta). Resposta curta, sem relatório.
"""


def fechar(pasta: Path, job_slug: str | None = None, com_ia: bool = True) -> dict:
    """Fim da linha de um vídeo: absorve o histórico pendente nas regras e arquiva o cru."""
    pasta = Path(pasta)
    vai, fica = pendentes(pasta, job_slug)
    absorvido = False
    if vai and com_ia:
        try:
            import ia
            if ia.disponivel():
                pf = ensure(pasta) / ".prompt-absorver.txt"
                pf.write_text(prompt_absorver(pasta, vai), encoding="utf-8")
                ia.executar(pf.read_text(encoding="utf-8"), pasta / ".log",
                            pasta / ".raw.jsonl", pasta / ".runner.pid")
                absorvido = True
        except Exception as e:                       # absorver é bônus; arquivar não pode travar
            (pasta / ".log").open("a", encoding="utf-8").write(f"\n✖ absorver falhou: {e}\n")
    r = arquivar_historico(pasta, motivo=f"vídeo fechado{' · ' + job_slug if job_slug else ''}", ignorar_slug=job_slug)
    r["absorvido_pela_ia"] = absorvido
    return r


def disparar_fechar(pasta: Path, job_slug: str | None = None) -> None:
    """Fecha o aprendizado em segundo plano — absorver pode levar minutos e a tela não pode travar."""
    import subprocess
    cmd = [sys.executable, str(Path(__file__)), "fechar", str(pasta)]
    if job_slug:
        cmd += ["--job", job_slug]
    subprocess.Popen(cmd, cwd=str(RAIZ), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def fechar_do_job(job: dict, com_ia: bool = True) -> dict | None:
    """Chamado quando o João clica em 'fechar e liberar espaço' num vídeo."""
    import producao as P
    try:
        c = P.cliente(job["cliente"])
        pasta = c["content"] / "modelos" / job["modelo"] / "aprendizado"
    except Exception:
        return None
    return fechar(pasta, job.get("slug"), com_ia=com_ia) if pasta.is_dir() else None


# ───────────────────────────── CLI ─────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Ciclo de vida do aprendizado")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventario")
    e = sub.add_parser("enxugar"); e.add_argument("--aplicar", action="store_true")
    f = sub.add_parser("fechar"); f.add_argument("pasta"); f.add_argument("--job", default=None)
    f.add_argument("--sem-ia", action="store_true")
    args = ap.parse_args()

    if args.cmd == "inventario":
        linhas = [orcamento(p) for p in pastas()]
        linhas.sort(key=lambda x: -x["chars"])
        print(f"{'regras':>6} {'chars':>7} {'hist':>5} {'histKB':>7}  modelo")
        for l in linhas:
            marca = " ⚠" if l["estourado"] else "  "
            print(f"{l['regras']:>6} {l['chars']:>7} {l['historico']:>5} {l['historico_kb']:>7}{marca} {l['pasta']}")
        print(f"\nTOTAL: {sum(l['regras'] for l in linhas)} regras · "
              f"{sum(l['chars'] for l in linhas)} chars · {sum(l['historico'] for l in linhas)} linhas de histórico")
    elif args.cmd == "enxugar":
        for p in pastas():
            antes = orcamento(p)
            if not args.aplicar:
                print(f"{antes['pasta']}: {antes['regras']} regras, {antes['chars']} chars"
                      + (" · BLOCÃO" if antes["blocao"] else "") + (" · ESTOURADO" if antes["estourado"] else ""))
                continue
            desconsolidar(p)
            j = juntar_repetidas(p)
            dep = orcamento(p)
            print(f"{dep['pasta']}: {antes['regras']}→{dep['regras']} regras · "
                  f"{antes['chars']}→{dep['chars']} chars" + (" ⚠ ainda estourado" if dep["estourado"] else ""))
    else:
        print(json.dumps(fechar(Path(args.pasta), args.job, com_ia=not args.sem_ia), ensure_ascii=False))


if __name__ == "__main__":
    main()
