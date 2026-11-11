#!/usr/bin/env python3
"""
aprendi — o "Aprendi:" do feedback (REGRA Nº 2 do CLAUDE.md, com o gate "Aprovou?" do PLANO-2.0, item 3).

O João manda "Quero alterar" num vídeo. O Estúdio:
  1. grava a linha bruta no historico.jsonl do modelo (passo 1 da REGRA Nº 2, feito aqui);
  2. PROPÕE a regra (curta), a camada (cliente · estilo · todo vídeo) e avisa se já existe uma parecida (aí a regra
     existente é reescrita, nunca duplicada);
  3. a tela mostra "Aprendi: <regra> · vale pra <este cliente | este estilo | todo vídeo>" com OK e "Não é isso".
Só o OK (ou "Guardar assim", depois de reescrever / trocar a camada) grava a regra. "Descartar" deixa só o histórico.

Arquivos: app/aprendi/<id>.json (uma proposta cada). Regras: cliente → <modelo>/aprendizado/regras.json ·
estilo → formatos/<slug>/aprendizado/regras.json · todo vídeo → REGRAS.md (linha nova G<n>).
"""
from __future__ import annotations

import re
import sys
import unicodedata
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import agora, append_jsonl, gravar_json, hoje, ler_json, make_slug  # noqa: E402

CAMADAS = ("cliente", "estilo", "geral")
ROTULO = {"cliente": "este cliente", "estilo": "este estilo", "geral": "todo vídeo"}
TETO_REGRAS = 24          # por modelo (CLAUDE.md, REGRA Nº 2)
MAX_REGRA = 600           # caracteres de uma regra
SEMELHANTE = 0.34         # parte das palavras em comum (mesmo assunto) que faz a regra nova reescrever a velha

_CLIENTE = re.compile(r"\b(cor|cores|fonte|logo|marca|produto|pre[çc]o|nome|sotaque|meu rosto|minha cara|o cliente|"
                      r"enquadr\w*|c[âa]mera dele|m[úu]sica dele|nicho)\b", re.I)
_GERAL = re.compile(r"\b(todo v[ií]deo|todos os v[ií]deos|em qualquer v[ií]deo|sempre em (todo|qualquer)|"
                    r"nunca em (nenhum|qualquer)|vale pra tudo|regra geral|pra todos)\b", re.I)
_ESTILO = re.compile(r"\b(ritmo|corte|cortes|transi[çc][ãa]o|cenas?|legenda|encaixe|dura[çc][ãa]o|layout|"
                     r"b-?roll|efeito|gancho|abertura|fecho|batida|velocidade)\b", re.I)
_PARADAS = set("a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem que e ou mas se "
               "ao aos à é está esta isso isto esse essa este ela ele eu meu minha seu sua mais muito pouco ficou "
               "fica tá tem foi ser vai quero quer quando como onde já não nao só so também tambem".split())


def _pasta() -> Path:
    return _comum.ESTUDIO / "aprendi"


def _arq(id_: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{8,32}", str(id_ or "")):
        raise ValueError("Aprendizado não encontrado.")
    return _pasta() / f"{id_}.json"


def carregar(id_: str) -> dict | None:
    try:
        return ler_json(_arq(id_), None)
    except ValueError:
        return None


def listar(estado: str | None = None, cli: str = "", slug: str = "") -> list[dict]:
    out = []
    for p in sorted(_pasta().glob("*.json")) if _pasta().is_dir() else []:
        d = ler_json(p, None)
        if not isinstance(d, dict):
            continue
        if estado and d.get("estado") != estado:
            continue
        if cli and (d.get("cliente") != cli or d.get("slug") != slug):
            continue
        out.append(d)
    return sorted(out, key=lambda d: d.get("criado_em", ""), reverse=True)


def pendentes(cli: str = "", slug: str = "") -> list[dict]:
    return listar("pendente", cli, slug)


# ───────────────────────────── a proposta ─────────────────────────────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def _palavras(s: str) -> set[str]:
    return {p for p in _norm(s).split() if len(p) > 3 and p not in _PARADAS}


def camada_sugerida(texto: str, tem_estilo: bool = True) -> str:
    """Na dúvida, cliente (REGRA Nº 2): só sobe pro estilo ou pro geral com palavra clara."""
    if _GERAL.search(texto or ""):
        return "geral"
    if _CLIENTE.search(texto or ""):
        return "cliente"
    if tem_estilo and _ESTILO.search(texto or ""):
        return "estilo"
    return "cliente"


def regra_curta(texto: str) -> str:
    """A fala do João limpa e curta: sem "quero alterar", sem o "no segundo 12", primeira ideia inteira."""
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    t = re.sub(r"^(quero alterar|quero mudar|ajusta|ajuste|altera)[:,. ]*", "", t, flags=re.I).strip()
    t = re.sub(r"\b(no|em|aos|ao) (segundo|seg\.?|minuto) \d+([.,:]\d+)?\s*[,:]?\s*", "", t, flags=re.I).strip()
    frases = re.split(r"(?<=[.!?])\s+", t)
    out = ""
    for f in frases:
        if out and len(out) + len(f) > 220:
            break
        out = (out + " " + f).strip()
    out = (out or t)[:MAX_REGRA].strip()
    return (out[:1].upper() + out[1:]) if out else ""


def _caminho_regras(camada: str, rec: dict) -> Path | None:
    if camada == "estilo" and rec.get("formato"):
        import formatos
        return formatos.FORMATOS / Path(rec["formato"]).name / "aprendizado" / "regras.json"
    if camada == "cliente" and rec.get("cliente") and rec.get("modelo"):
        c = _comum.cliente(rec["cliente"])
        if c and Path(rec["modelo"]).name == rec["modelo"]:
            return c["content"] / "modelos" / rec["modelo"] / "aprendizado" / "regras.json"
    return None


def _regras_md() -> Path:
    return _comum.RAIZ / "REGRAS.md"


def parecida(camada: str, rec: dict, texto: str, categoria: str) -> dict | None:
    """A regra que já trata do mesmo assunto nessa camada (pra reescrever em vez de duplicar), ou None."""
    quero = _palavras(texto)
    if len(quero) < 2:
        return None
    melhor, nota = None, 0.0
    if camada == "geral":
        md = _regras_md()
        for linha in md.read_text(encoding="utf-8").splitlines() if md.is_file() else []:
            m = re.match(r"^\|\s*(G\d+)\s*\|\s*(.*?)\s*\|", linha)
            if m:
                tem = _palavras(m.group(2))
                n = len(quero & tem) / max(1, len(quero | tem))
                if n > nota:
                    melhor, nota = {"id": m.group(1), "texto": m.group(2)[:200], "onde": "REGRAS.md"}, n
    else:
        p = _caminho_regras(camada, rec)
        for r in ((ler_json(p, {}) or {}).get("regras") or []) if p else []:
            if not isinstance(r, dict):
                continue
            tem = _palavras(f"{r.get('titulo', '')} {r.get('texto', '')}")
            n = len(quero & tem) / max(1, len(quero | tem))
            if r.get("categoria") == categoria:
                n += 0.1
            if n > nota:
                melhor, nota = {"id": r.get("id", ""), "texto": str(r.get("texto") or r.get("titulo") or "")[:200],
                                "onde": _comum.rel(p)}, n
    return melhor if melhor and nota >= SEMELHANTE else None


def propor(cli: str, slug: str, texto: str, formato: str = "", modelo: str = "", titulo: str = "",
           ref: str = "", segundo=None) -> dict | None:
    """Cria a proposta "Aprendi" pendente. None se o João não disse nada durável (texto vazio)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for r in listar("pendente", cli, slug):   # o mesmo pedido não vira duas propostas
        if r.get("texto") == texto:
            return r
    from regras import categoria_do_texto
    categoria = categoria_do_texto(texto, "processo")
    camada = camada_sugerida(texto, tem_estilo=bool(formato))
    if camada == "estilo" and not _caminho_regras("estilo", {"formato": formato}):
        camada = "cliente"
    rec = {"id": uuid.uuid4().hex[:12], "estado": "pendente", "cliente": cli, "slug": slug, "titulo_video": titulo or slug,
           "formato": formato, "modelo": modelo, "texto": texto, "regra": regra_curta(texto) or texto[:MAX_REGRA],
           "categoria": categoria, "camada": camada, "camada_sugerida": camada, "ref": ref,
           "segundo": segundo, "criado_em": agora()}
    rec["parecida"] = parecida(camada, rec, rec["regra"], categoria)
    # passo 1 da REGRA Nº 2: a linha bruta no historico.jsonl do modelo (uma vez só)
    c = _comum.cliente(cli) if cli else None
    if c and modelo and (c["content"] / "modelos" / Path(modelo).name).is_dir():
        hist = c["content"] / "modelos" / Path(modelo).name / "aprendizado" / "historico.jsonl"
        ja = [x for x in _comum.ler_jsonl(hist) if x.get("texto") == texto and x.get("job") == f"{cli}/{slug}"] if hist.is_file() else []
        if not ja:
            append_jsonl(hist, {"tipo": "feedback", "categoria": categoria, "texto": texto, "origem": "usuario",
                                "createdAt": hoje(), "decisao": "ajustar", "job": f"{cli}/{slug}"})
    gravar_json(_arq(rec["id"]), rec)
    return rec


def frase(rec: dict) -> str:
    """O texto que a tela mostra: "Aprendi: <regra> · vale pra <camada>"."""
    return f"Aprendi: {rec.get('regra', '')} · vale pra {ROTULO.get(rec.get('camada'), 'este cliente')}"


# ───────────────────────────── o clique do João ─────────────────────────────

def ajustar(id_: str, regra: str | None = None, camada: str | None = None) -> dict:
    """"Não é isso": reescreve a regra e/ou troca a camada. Continua pendente (só o OK grava)."""
    rec = carregar(id_)
    if not rec or rec.get("estado") != "pendente":
        raise ValueError("Esse aprendizado já foi respondido.")
    if camada is not None and camada != "":
        if camada not in CAMADAS:
            raise ValueError("Camada inválida: cliente, estilo ou todo vídeo.")
        if camada == "estilo" and not _caminho_regras("estilo", rec):
            raise ValueError("Este vídeo não tem estilo; use cliente ou todo vídeo.")
        if camada == "cliente" and not _caminho_regras("cliente", rec):
            raise ValueError("Não achei o modelo do cliente; use estilo ou todo vídeo.")
        rec["camada"] = camada
    if regra is not None and regra.strip():
        rec["regra"] = re.sub(r"\s+", " ", regra).strip()[:MAX_REGRA]
    rec["parecida"] = parecida(rec["camada"], rec, rec["regra"], rec["categoria"])
    rec["ajustado"] = True
    gravar_json(_arq(id_), rec)
    return rec


def _gravar_json_regra(p: Path, rec: dict) -> dict:
    d = ler_json(p, None)
    if not isinstance(d, dict):
        d = {"regras": []}
    regras = d.setdefault("regras", [])
    par = rec.get("parecida") or {}
    alvo = next((r for r in regras if isinstance(r, dict) and r.get("id") == par.get("id")), None) if par else None
    frase_joao = rec["texto"][:200]
    if alvo is not None:   # reescreve a própria regra (sobe o peso, mantém cobre e desde)
        alvo["texto"] = rec["regra"]
        alvo["origem"] = f"{alvo.get('origem', '')} | \"{frase_joao}\" ({hoje()})".strip(" |") if alvo.get("origem") else f"\"{frase_joao}\""
        pw = str(alvo.get("peso", 5))
        if pw.isdigit():
            alvo["peso"] = str(int(pw) + 1)
        alvo["atualizada_em"] = hoje()
        gravar_json(p, d)
        return {"acao": "reescrita", "id": alvo.get("id"), "onde": _comum.rel(p)}
    if len(regras) >= TETO_REGRAS:
        aviso = f"o modelo já tem {len(regras)} regras (teto {TETO_REGRAS}); 'fechar e liberar espaço' junta as parecidas"
    else:
        aviso = ""
    ids = {r.get("id") for r in regras if isinstance(r, dict)}
    base = make_slug(rec["regra"], 48)
    rid, n = base, 2
    while rid in ids:
        rid = f"{base}-{n}"
        n += 1
    regras.append({"id": rid, "titulo": rec["regra"][:70], "categoria": rec["categoria"], "peso": "6", "desde": hoje(),
                   "origem": f"\"{frase_joao}\"", "texto": rec["regra"]})
    gravar_json(p, d)
    return {"acao": "criada", "id": rid, "onde": _comum.rel(p), "aviso": aviso}


def _gravar_geral(rec: dict) -> dict:
    md = _regras_md()
    linhas = md.read_text(encoding="utf-8").splitlines() if md.is_file() else []
    par = rec.get("parecida") or {}
    if par.get("id"):   # reescreve a linha da própria regra
        for i, ln in enumerate(linhas):
            m = re.match(r"^\|\s*" + re.escape(par["id"]) + r"\s*\|\s*(.*?)\s*\|(.*)$", ln)
            if m:
                linhas[i] = f"| {par['id']} | {rec['regra']} (reescrita em {hoje()}: \"{rec['texto'][:120]}\") |{m.group(2)}"
                md.write_text("\n".join(linhas) + "\n", encoding="utf-8")
                return {"acao": "reescrita", "id": par["id"], "onde": "REGRAS.md"}
    ids = [int(m.group(1)) for ln in linhas if (m := re.match(r"^\|\s*G(\d+)\s*\|", ln))]
    novo = f"G{max(ids, default=0) + 1}"
    ultima = max((i for i, ln in enumerate(linhas) if re.match(r"^\|\s*G\d+\s*\|", ln)), default=len(linhas) - 1)
    linhas.insert(ultima + 1, f"| {novo} | {rec['regra']} (João, {hoje()}: \"{rec['texto'][:120]}\") | Conferir nos quadros do vídeo |")
    md.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return {"acao": "criada", "id": novo, "onde": "REGRAS.md"}


def confirmar(id_: str) -> dict:
    """"OK": agora sim a regra é gravada na camada escolhida."""
    rec = carregar(id_)
    if not rec or rec.get("estado") != "pendente":
        raise ValueError("Esse aprendizado já foi respondido.")
    if rec["camada"] == "geral":
        r = _gravar_geral(rec)
    else:
        p = _caminho_regras(rec["camada"], rec)
        if not p:
            raise ValueError("Não achei onde guardar nessa camada. Troque em \"Não é isso\".")
        r = _gravar_json_regra(p, rec)
    rec.update(estado="ok", resolvido_em=agora(), gravada=r)
    gravar_json(_arq(id_), rec)
    return rec


def descartar(id_: str) -> dict:
    """Não vira regra: fica só a linha do historico.jsonl."""
    rec = carregar(id_)
    if not rec or rec.get("estado") != "pendente":
        raise ValueError("Esse aprendizado já foi respondido.")
    rec.update(estado="descartada", resolvido_em=agora())
    gravar_json(_arq(id_), rec)
    return rec


if __name__ == "__main__":
    for r in listar():
        print(r["id"], r["estado"], frase(r))
