#!/usr/bin/env python3
"""
auto_juntar — o Estúdio decide sozinho (pedido do João, 29-out noite): "não é que o João decida essas coisas; baseado no que
tem, o sistema deve fazer". Referência, set ou estudo pronto → junta ao estilo mais parecido (ou cria um estilo novo EM TESTE)
e só AVISA, com "Desfazer" (Esperando você → "Juntei ao Editorial"). A aprovação do João fica pro RESULTADO (o vídeo final).

Como decide: referência/set → o estilo que a leitura do estilo sugeriu (nota 70+); senão (e pra estudo) o estilo cujas
referências têm as medidas mais próximas (cortes/min, palavras/min, câmera, legenda, volume: estudo quadro a quadro);
nada perto → estilo novo em teste (só vira pronto com o vídeo de teste aprovado). Tudo reversível: Desfazer manda
pra lixeira e devolve o item pra decisão do João.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import agora, gravar_json, ler_json, rel  # noqa: E402
import estilo_ref as _er  # noqa: E402
import formatos as _fmt  # noqa: E402

CHAVES = {"planos.por_min": 30.0, "fala.ppm": 60.0, "camera.pct_quadros_andando": 30.0, "legenda.y_pct": 30.0, "som.lufs": 6.0}
PERTO = 0.8   # distância média (em "escalas") até onde um estilo é "parecido"; acima disso nasce estilo novo


def metricas(pasta_estudo: Path) -> dict:
    conj = (ler_json(Path(pasta_estudo) / "estudo.json", {}) or {}).get("conjunto") or {}
    return {k: float(conj[k]["mediana"]) for k in CHAVES if isinstance(conj.get(k), dict) and conj[k].get("mediana") is not None}


def _dist(a: dict, b: dict) -> float:
    comuns = [k for k in CHAVES if k in a and k in b]
    return sum(abs(a[k] - b[k]) / CHAVES[k] for k in comuns) / len(comuns) if len(comuns) >= 3 else 9.0


def estilo_mais_parecido(m: dict) -> tuple[str, float]:
    """(slug, distância) do estilo visível cujas referências medidas estão mais perto de `m`; ("", 9) se não há medida."""
    melhor, nota = "", 9.0
    for f in _fmt.listar():
        base = _fmt.FORMATOS / f["slug"]
        ms = [metricas(j.parent) for j in sorted(base.glob("estudos/*/estudo-quadros/estudo.json"))]
        ms = [x for x in ms if x]
        if not ms:
            continue
        d = min(_dist(m, x) for x in ms)
        if d < nota:
            melhor, nota = f["slug"], d
    return melhor, nota


def _titulo(slug: str) -> str:
    return (_fmt.carregar(slug) or {}).get("titulo") or slug


def _decidir(ids: list[str], m: dict) -> tuple[str, str]:
    """(slug, porque) pelos votos da leitura do estilo; sem voto, pelas medidas; senão ("", ...) = estilo novo."""
    votos: dict[str, int] = {}
    for i in ids:
        e = _er.estilo_de(i)
        if e and _er.serve(e):
            votos[e["formato_sugerido"]["slug"]] = votos.get(e["formato_sugerido"]["slug"], 0) + 1
    if votos:
        s = max(votos, key=votos.get)
        if _fmt.carregar(s):
            return s, "a leitura do estilo apontou esse"
    s, d = estilo_mais_parecido(m)
    if s and d <= PERTO:
        return s, "as medidas (cortes, fala, câmera, legenda, volume) são as mais parecidas"
    return "", "nenhum estilo tem medidas parecidas"


def _novo_estilo(ref_id: str, nome: str) -> str:
    import estilo_novo
    return estilo_novo.criar(ref_id, nome)


def referencia(id_: str) -> dict:
    st = _er.estado(id_) or {}
    m = metricas(_er.pasta(id_) / "quadros")
    slug, porque = (("", "você pediu um estilo novo") if st.get("estilo_novo") else _decidir([id_], m))
    nome = _er.nome_curto(st)
    if slug:
        r = _er.confirmar(id_, slug, nome, False)
        info = {"formato": slug, "novo": False, "porque": porque}
        if not r.get("ok"):
            raise ValueError("não consegui guardar")
    else:
        slug = _novo_estilo(id_, nome)
        info = {"formato": slug, "novo": True, "porque": porque}
    info.update(titulo=_titulo(slug), quando=agora())
    _er._salvar(id_, auto_feito=info)
    return info


def conjunto(cid: str) -> dict:
    import ref_conjunto as rc
    s = rc.situacao(cid)
    ids = [i["id"] for i in s["itens"] if i.get("estado") == "pronto"]
    if not ids:
        raise ValueError("nenhuma referência pronta")
    c = s["conjunto"]
    m = metricas(rc.pasta(cid) / "quadros") if c.get("regua") else metricas(_er.pasta(ids[0]) / "quadros")
    slug, porque = (("", "você pediu um estilo novo") if c.get("estilo_novo") else _decidir(ids, m))
    nome = c.get("nome") or f"set de {len(ids)}"
    if slug:
        for n, i in enumerate(ids, 1):
            _er.confirmar(i, slug, f"{nome}-{n}", False)
        info = {"formato": slug, "novo": False, "porque": porque}
    else:
        slug = _novo_estilo(ids[0], nome)
        for n, i in enumerate(ids[1:], 2):
            _er.confirmar(i, slug, f"{nome}-{n}", False)
        info = {"formato": slug, "novo": True, "porque": porque}
    info.update(titulo=_titulo(slug), quando=agora())
    rc._salvar(cid, estado="confirmado", formato=slug, auto_feito=info)
    return info


def estudo(sid: str) -> dict:
    import estudos_tela as et
    d = et.PASTA / Path(sid).name
    nome = (ler_json(d / "estado.json", {}) or {}).get("nome") or "estudo"
    slug, d_ = estilo_mais_parecido(metricas(d / "estudo-quadros"))
    novo = not slug or d_ > PERTO
    if novo:
        from _comum import make_slug
        slug = make_slug(nome, 40)
        n, base = 1, slug
        while _fmt.carregar(slug) or (_fmt.FORMATOS / slug).exists():
            n += 1
            slug = f"{base}-{n}"
        p = _fmt.novo_formato(slug, titulo=nome)
        dados = ler_json(p / "formato.json", {}) or {}
        dados.update({"oculto": True, "status": "receita", "em_teste": True, "primeiro_video": {"estado": "a_propor", "criado_em": agora()}})
        gravar_json(p / "formato.json", dados)
    onde = et.juntar(sid, slug)
    info = {"formato": slug, "novo": novo, "titulo": _titulo(slug), "quando": agora(), "pasta": onde,
            "porque": "nenhum estilo tem medidas parecidas" if novo else "as medidas (cortes, fala, câmera, legenda, volume) são as mais parecidas"}
    et._est(d, auto_feito=info)
    return info


# ───────────── Desfazer / Tá bom ─────────────

def _estado_arq(tipo: str, id_: str) -> tuple[Path, dict]:
    import estudos_tela as et
    import ref_conjunto as rc
    p = {"ref": _er.pasta, "set": rc.pasta, "estudo": lambda x: et.PASTA / Path(x).name}[tipo](id_) / \
        {"ref": "estado.json", "set": "conjunto.json", "estudo": "estado.json"}[tipo]
    return p, ler_json(p, {}) or {}


def ok(tipo: str, id_: str) -> None:
    p, d = _estado_arq(tipo, id_)
    if not d.get("auto_feito"):
        raise ValueError("Nada pra confirmar aqui.")
    d["auto_visto"] = True
    gravar_json(p, d)


def _desfazer_ref(id_: str) -> None:
    import remover
    p, d = _estado_arq("ref", id_)
    if d.get("estudo"):
        remover.remover_pasta(d["estudo"], "referência guardada sozinha (desfeita)")
    for k in ("formato", "estudo", "principal", "guardado_para_novo", "comando_novo"):
        d.pop(k, None)
    d.update(estado="pronto", auto=False, auto_desfeita=True)
    gravar_json(p, d)


def desfazer(tipo: str, id_: str) -> str:
    """Devolve o item pra decisão do João (volta em Esperando você) e manda o que foi guardado pra lixeira."""
    import estudos_tela as et
    import remover
    import ref_conjunto as rc
    p, d = _estado_arq(tipo, id_)
    info = d.get("auto_feito") or {}
    if not info:
        raise ValueError("Nada pra desfazer aqui.")
    if tipo == "ref":
        _desfazer_ref(id_)
        d = ler_json(p, {}) or {}   # _desfazer_ref gravou o estado: relê (senão sobrescreve com o velho)
    elif tipo == "set":
        for r in d.get("refs") or []:
            if (_er.estado(r) or {}).get("estado") == "confirmado":
                _desfazer_ref(r)
        d.update(estado="analisando")
    else:
        if info.get("pasta"):
            remover.remover_pasta(info["pasta"], "estudo guardado sozinho (desfeito)")
        d.pop("juntado", None)
        d.pop("juntado_em_estilo", None)
    if info.get("novo") and (_fmt.FORMATOS / info["formato"] / "formato.json").is_file():
        remover.remover_estilo(info["formato"])
    d.pop("auto_feito", None)
    d["auto_desfeito"] = True
    gravar_json(p, d)
    return info.get("titulo") or info.get("formato", "")


def avisos() -> list[dict]:
    """Itens "Eu já fiz, você pode desfazer" pra tela Esperando você (não pedem aprovação: só aviso)."""
    import estudos_tela as et
    import ref_conjunto as rc
    out = []
    fontes = [("ref", [p.parent for p in _er.ESTILOS.glob("*/estado.json")], "estado.json"),
              ("set", [p.parent for p in (_er.ESTILOS / "_conjuntos").glob("*/conjunto.json")], "conjunto.json"),
              ("estudo", [p.parent for p in et.PASTA.glob("*/estado.json")] if et.PASTA.is_dir() else [], "estado.json")]
    for tipo, pastas, arq in fontes:
        for pasta in pastas:
            d = ler_json(pasta / arq, {}) or {}
            info = d.get("auto_feito")
            if not info or d.get("auto_visto"):
                continue
            nome = d.get("nome") or (_er.nome_curto(d) if tipo == "ref" else "")
            out.append({"tipo": "aviso", "id": pasta.name, "kind": tipo, "info": info, "nome": nome, "pasta": pasta})
    return out
