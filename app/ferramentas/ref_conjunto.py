#!/usr/bin/env python3
"""
ref_conjunto — jogar um SET de referências de uma vez (pedido do João, 29-out noite).

Cada vídeo/link vira uma referência entendida (estilo_ref.entender: estudo quadro a quadro + estilo.json) e, juntos, viram
UMA régua (estudo_quadros.estudar com todos os vídeos: o que se repete é o fundamento do estilo). A tela mostra cada um e
a régua conjunta, pede "Aprovou?" e deixa criar variações nessa pegada. Arquivos: app/.estilos/_conjuntos/<id>.json
(+ pasta com a régua conjunta). A pasta _conjuntos não tem estado.json: estilo_ref.listar() não a confunde com referência.
"""
from __future__ import annotations

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

MAX_NO_SET = 8


def _raiz() -> Path:
    return _er.ESTILOS / "_conjuntos"


def pasta(cid: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{8,32}", str(cid or "")):
        raise ValueError("Conjunto não encontrado.")
    return _raiz() / cid


def carregar(cid: str) -> dict | None:
    try:
        return ler_json(pasta(cid) / "conjunto.json", None)
    except ValueError:
        return None


def _salvar(cid: str, **campos) -> dict:
    d = {**(carregar(cid) or {}), **campos, "atualizado_em": agora()}
    gravar_json(pasta(cid) / "conjunto.json", d)
    return d


def listar() -> list[dict]:
    r = _raiz()
    out = [ler_json(p, {}) for p in sorted(r.glob("*/conjunto.json"))] if r.is_dir() else []
    return sorted([d for d in out if d], key=lambda d: d.get("criado_em", ""), reverse=True)


def situacao(cid: str) -> dict:
    """{conjunto, itens: [estado de cada referência], todas_prontas, algum_erro}. Atualiza o estado do conjunto."""
    c = carregar(cid)
    if not c:
        raise ValueError("Conjunto não encontrado.")
    itens = []
    for r in c["refs"]:
        st = _er.estado(r) or {"id": r, "estado": "erro", "erro": "sumiu"}
        st = {**st, "nome_curto": _er.nome_curto(st)}
        itens.append(st)
    estados = [i.get("estado") for i in itens]
    prontas = all(e in ("pronto", "confirmado") for e in estados)
    return {"conjunto": c, "itens": itens, "todas_prontas": prontas, "algum_erro": "erro" in estados,
            "analisando": any(e == "analisando" for e in estados)}


def _regua(cid: str) -> None:
    try:
        _regua_conjunta(cid)
    finally:
        if (carregar(cid) or {}).get("auto") and (carregar(cid) or {}).get("estado") == "analisando":
            try:
                import auto_juntar
                auto_juntar.conjunto(cid)
            except Exception as e:  # noqa: BLE001  não decidiu: o set fica esperando o João
                _salvar(cid, aviso_auto=f"Não consegui decidir sozinho: {str(e)[:160]}")


def _regua_conjunta(cid: str) -> None:
    """Espera as referências terminarem e roda a régua conjunta (grátis: OpenCV/ffmpeg/tesseract)."""
    import time
    c = carregar(cid) or {}
    for _ in range(720):   # até ~1 h
        s = situacao(cid)
        if not s["analisando"]:
            break
        time.sleep(5)
    vids, words = [], {}
    for r in c["refs"]:
        if (_er.estado(r) or {}).get("estado") in ("pronto", "confirmado") and _er.video_de(r):
            ln = ensure(pasta(cid) / "videos") / f"ref-{len(vids) + 1}{_er.video_de(r).suffix}"   # nomes distintos: todos se chamam video.mp4
            ln.unlink(missing_ok=True)
            ln.symlink_to(_er.video_de(r).resolve())
            vids.append(ln)
            pr = _er.pasta(r)
            if (pr / "fala-palavras.json").is_file():
                words[str(ln)] = str(pr / "fala-palavras.json")
    if len(vids) < 2:
        _salvar(cid, regua="", aviso_regua="Só uma referência ficou pronta: a régua conjunta precisa de duas.")
        return
    try:
        import estudo_quadros
        est = estudo_quadros.estudar(vids, pasta(cid) / "quadros", nome=c.get("nome") or "conjunto", transcrever_fala=False,
                                     words=words or None)
        _salvar(cid, regua="quadros/ESTUDO-QUADROS.md", base_sugerida=est["conjunto"].get("base_sugerida", ""))
    except Exception as e:  # noqa: BLE001  nunca derruba o conjunto
        _salvar(cid, regua="", aviso_regua=f"Régua conjunta falhou: {str(e)[:200]}")


def criar(fontes: list, cliente: str = "", nome: str = "", esperar: bool = False, auto: bool = False, estilo_novo: bool = False) -> str:
    """fontes: caminhos de vídeo e/ou links. Devolve o id do conjunto na hora (cada referência trabalha em segundo plano)."""
    fontes = [f for f in fontes if str(f or "").strip()]
    if not fontes:
        raise ValueError("Mande um vídeo ou cole um link.")
    if len(fontes) > MAX_NO_SET:
        raise ValueError(f"No máximo {MAX_NO_SET} vídeos por vez.")
    cid = uuid.uuid4().hex[:12]
    ensure(pasta(cid))
    gravar_json(pasta(cid) / "conjunto.json", {"id": cid, "cliente": cliente or "", "nome": nome.strip(), "criado_em": agora(),
                                               "atualizado_em": agora(), "refs": [], "estado": "analisando", "auto": bool(auto), "estilo_novo": bool(estilo_novo)})
    refs = [_er.entender(f, cliente, esperar=esperar, gate=True, conjunto=cid) for f in fontes]
    _salvar(cid, refs=refs)
    t = threading.Thread(target=_regua, args=(cid,), daemon=True)
    t.start()
    if esperar:
        t.join()
    return cid


def confirmar(cid: str, formato: str, nome: str = "", principal: str = "") -> list[dict]:
    """"Aprovou?" do set: guarda cada referência pronta no estilo `formato` (a 1ª como principal se pedido)."""
    s = situacao(cid)
    if s["analisando"]:
        raise ValueError("Ainda estou olhando os vídeos.")
    out = []
    for i, st in enumerate([x for x in s["itens"] if x.get("estado") == "pronto"], 1):
        out.append(_er.confirmar(st["id"], formato, f"{nome or s['conjunto'].get('nome') or 'set'}-{i}", principal == "1" and i == 1))
    _salvar(cid, estado="confirmado", formato=formato)
    return out


def descartar(cid: str) -> int:
    """Manda o conjunto e as referências ainda não confirmadas pra lixeira (volta em Configurações → Lixeira)."""
    import remover
    n = 0
    for r in (carregar(cid) or {}).get("refs", []):
        if (_er.estado(r) or {}).get("estado") != "confirmado":
            remover.remover_pasta(rel(_er.pasta(r)), "referência " + r)
            n += 1
    remover.remover_pasta(rel(pasta(cid)), "conjunto de referências " + cid)
    return n
