#!/usr/bin/env python3
"""
variacoes — "Criar variações nessa pegada" (pedido do João, 29-out noite).

Depois de entender uma ou mais referências (um SET jogado de uma vez), o Estúdio propõe N variações (padrão 3) no MESMO
estilo: ideia + gancho + roteiro curto (ou plano de corte), sem copiar a fala nem o assunto das referências (G0: ~70%
fundamento das referências, ~30% inovação). Cada variação nasce "proposta"; só vira vídeo depois do "Aprovou?" do João.

Arquivos: app/.variacoes/<id>/estado.json (+ execucao.log, raw.jsonl, variacoes.json da IA).
A IA da assinatura/API do Estúdio (ia.py) faz uma chamada; nada de kie.ai nem voz paga.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import agora, ensure, gravar_json, ler_json, rel  # noqa: E402
import estilo_ref as _er  # noqa: E402
import ia  # noqa: E402

QTD_PADRAO = 3
CAMPOS = ("titulo", "ideia", "gancho", "mantem", "muda")


def _pasta_raiz() -> Path:
    return _comum.ESTUDIO / ".variacoes"


def pasta(vid: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{8,32}", str(vid or "")):
        raise ValueError("Variações não encontradas.")
    return _pasta_raiz() / vid


def estado(vid: str) -> dict | None:
    try:
        return ler_json(pasta(vid) / "estado.json", None)
    except ValueError:
        return None


def _salvar(vid: str, **campos) -> dict:
    d = {**(estado(vid) or {}), **campos, "atualizado_em": agora()}
    gravar_json(pasta(vid) / "estado.json", d)
    return d


def listar() -> list[dict]:
    r = _pasta_raiz()
    out = [ler_json(p, {}) for p in sorted(r.glob("*/estado.json"))] if r.is_dir() else []
    return sorted([d for d in out if d], key=lambda d: d.get("criado_em", ""), reverse=True)


def do_conjunto(refs: list[str]) -> list[dict]:
    """As propostas já feitas pra esse mesmo conjunto de referências (mais nova primeiro)."""
    chave = sorted(refs)
    return [d for d in listar() if sorted(d.get("refs") or []) == chave and d.get("origem", "variacoes") == "variacoes"]


def _validar(d: dict, qtd: int) -> list[dict]:
    itens = d.get("variacoes") if isinstance(d, dict) else None
    if not isinstance(itens, list) or len(itens) < qtd:
        raise ValueError(f"A IA entregou menos de {qtd} variações.")
    out = []
    for i, v in enumerate(itens[:qtd], 1):
        if not isinstance(v, dict) or any(not str(v.get(c) or "").strip() for c in CAMPOS):
            raise ValueError(f"A variação {i} veio incompleta (precisa de {', '.join(CAMPOS)}).")
        if not (str(v.get("roteiro_curto") or "").strip() or str(v.get("plano_corte") or "").strip()):
            raise ValueError(f"A variação {i} veio sem roteiro curto nem plano de corte.")
        out.append({**{k: (str(v.get(k) or "").strip()) for k in (*CAMPOS, "roteiro_curto", "plano_corte")},
                    "n": i, "estado": "proposta"})
    return out


def _transcricoes(refs: list[str]) -> str:
    out = []
    for r in refs:
        p = _er.pasta(r) / "transcricao.txt"
        if p.is_file():
            out.append(p.read_text(encoding="utf-8"))
    return "\n".join(out)


def _prompt(vid: str, st: dict, erro: str = "") -> str:
    d = pasta(vid)
    refs = []
    for r in st["refs"]:
        pr = _er.pasta(r)
        refs.append(f"- {_er.nome_curto(_er.estado(r) or {})}: estilo {rel(pr / 'estilo.json')}"
                    + (f" · régua quadro a quadro {rel(pr / 'quadros' / 'ESTUDO-QUADROS.md')}" if (pr / "quadros" / "ESTUDO-QUADROS.md").is_file() else "")
                    + (f" · fala (SÓ pra não repetir o assunto) {rel(pr / 'transcricao.txt')}" if (pr / "transcricao.txt").is_file() else ""))
    ident = _comum.RAIZ / "clientes" / (st.get("cliente") or "Avulso") / "identidade.json"
    qtd = st["qtd"]
    esquema = {"variacoes": [{"titulo": "nome curto da variação", "ideia": "1-2 frases: de que trata, por que prende",
                              "gancho": "a frase de abertura nova (até ~12 palavras, no mecanismo da referência)",
                              "roteiro_curto": "5 a 9 frases curtas, uma por linha, no tom da pegada (ou deixe vazio se for plano_corte)",
                              "plano_corte": "se o vídeo é montagem/gravado: cena a cena com segundos (ou vazio se há roteiro_curto)",
                              "mantem": "o que vem da pegada das referências (ritmo, tipo de cena, legenda, gancho...) com número da régua",
                              "muda": "o que é novo (assunto, ângulo, reviravolta) e vale ~30%"}] * 1}
    return f"""Você é o roteirista de variações do Estúdio de vídeo do João. Ele jogou {len(st['refs'])} referência(s) do mesmo estilo e quer {qtd} VARIAÇÕES nessa mesma pegada.
Leia (use o Read) o que cada referência já tem medido:
{chr(10).join(refs)}
Identidade/tom do cliente ({st.get('cliente') or 'Avulso'}): {rel(ident) if ident.is_file() else '(sem identidade)'}.{(' Estilo (formato) alvo: ' + st['estilo']) if st.get('estilo') else ''}
REGRAS (G0 do REGRAS.md): referência é ESTILO, nunca molde. Mantenha ~70% do fundamento (ritmo, tipo de cena, mecanismo do gancho, legenda, som) e traga ~30% de novidade.
- NUNCA copie fala, frase, nome de pessoa, número ou cena específica das referências; cada variação trata de OUTRO assunto/ângulo (as referências tratam do assunto da fala delas: fuja dele).
- As {qtd} variações têm que ser diferentes entre si (assunto, ângulo e tipo de virada). Fale a língua do João: direto, sem guru, sem ponto de exclamação.
- Cada uma traz gancho novo, roteiro curto (ou plano de corte) e diz o que mantém × o que muda.
Escreva SOMENTE o arquivo {rel(d / 'variacoes.json')} (JSON puro) neste esquema (a lista tem {qtd} itens):
{json.dumps(esquema, ensure_ascii=False, indent=1)}{(chr(10) + 'A tentativa anterior foi recusada: ' + erro + '. Corrija.') if erro else ''}"""


def _trabalhar(vid: str) -> None:
    st = estado(vid) or {}
    d = pasta(vid)
    s = {**ia.selecao(), "modelo": "sonnet"} if ia.selecao().get("provedor") == "claude" else ia.selecao()
    erro = ""
    try:
        for _ in range(2):
            (d / "variacoes.json").unlink(missing_ok=True)
            code = ia.executar(_prompt(vid, st, erro), d / "execucao.log", d / "raw.jsonl", d / "runner.pid", s, tipo="outro")
            try:
                if code or not (d / "variacoes.json").is_file():
                    raise ValueError("a IA não entregou as variações")
                itens = _validar(json.loads((d / "variacoes.json").read_text(encoding="utf-8")), st["qtd"])
                _er.copia_proibida({"v": [[x for x in i.values() if isinstance(x, str)] for i in itens]}, _transcricoes(st["refs"]))
                _salvar(vid, estado="proposta", passo="", erro="", variacoes=itens)
                return
            except (ValueError, OSError) as e:
                erro = str(e)[:400]
        raise ValueError(erro)
    except Exception as e:  # noqa: BLE001
        _salvar(vid, estado="erro", passo="", erro="Não consegui montar as variações. Tente de novo.", detalhe=str(e)[:600])


def propor(refs: list[str], qtd: int = QTD_PADRAO, cliente: str = "", estilo: str = "", origem: str = "variacoes",
           esperar: bool = False) -> str:
    """Pede as variações pra IA (thread) e devolve o id na hora. A tela atualiza sozinha até virar "proposta"."""
    refs = [r for r in dict.fromkeys(refs or []) if (_er.estado(r) or {}).get("estado") in ("pronto", "confirmado")]
    if not refs:
        raise ValueError("Preciso de ao menos uma referência já entendida.")
    vid = uuid.uuid4().hex[:12]
    ensure(pasta(vid))
    gravar_json(pasta(vid) / "estado.json", {"id": vid, "refs": refs, "qtd": max(1, min(int(qtd), 6)), "cliente": cliente or "Avulso",
                                             "estilo": estilo, "origem": origem, "estado": "analisando",
                                             "passo": "Pensando nas variações…", "criado_em": agora(), "atualizado_em": agora()})
    t = threading.Thread(target=_trabalhar, args=(vid,), daemon=True)
    t.start()
    if esperar:
        t.join()
    return vid


def decidir(vid: str, n: int, decisao: str) -> dict:
    """"aprovar" (vira vídeo: o João abre no Criar) ou "recusar". Só quem está "proposta" muda."""
    st = estado(vid)
    if not st or st.get("estado") != "proposta":
        raise ValueError("Essas variações não estão esperando você.")
    if decisao not in ("aprovar", "recusar"):
        raise ValueError("Decisão inválida.")
    v = next((x for x in st["variacoes"] if x["n"] == int(n)), None)
    if not v:
        raise ValueError("Variação não encontrada.")
    if v["estado"] != "proposta":
        raise ValueError("Essa variação já foi respondida.")
    v["estado"] = "aprovada" if decisao == "aprovar" else "recusada"
    v["decidida_em"] = agora()
    return _salvar(vid, variacoes=st["variacoes"])


def esperando(st: dict) -> int:
    return len([v for v in st.get("variacoes") or [] if v.get("estado") == "proposta"]) if st.get("estado") == "proposta" else 0


def roteiro_de(vid: str, n: int) -> dict:
    """Texto pronto pro Criar: título, roteiro (ou plano) e gancho da variação (aprovada)."""
    st = estado(vid) or {}
    v = next((x for x in st.get("variacoes") or [] if x["n"] == int(n)), None)
    if not v or v.get("estado") != "aprovada":
        raise ValueError("Essa variação ainda não foi aprovada.")
    return {"titulo": v["titulo"], "roteiro": v.get("roteiro_curto") or v.get("plano_corte") or "", "gancho": v["gancho"],
            "estilo": st.get("estilo", ""), "cliente": st.get("cliente", "")}
