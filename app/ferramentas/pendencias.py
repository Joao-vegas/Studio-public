#!/usr/bin/env python3
"""
pendencias — tudo que espera o "Aprovou?" do João, fora os vídeos (lotes.esperando junta com eles):
referência (ou set) a confirmar · estudo a juntar a um estilo · variações propostas · estilo novo com 1º vídeo ·
regra aprendida. Cada item: tipo, titulo, sub, imagem (miniatura), url, botao, ha. Lê só os json (rápido: roda em toda página).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import ler_json, rel  # noqa: E402

ROTULOS = {"referencia": "Referência a confirmar", "estudo": "Estudo a juntar a um estilo", "variacoes": "Variações pra aprovar",
           "estilo_novo": "Estilo novo em teste", "regra": "Regra aprendida",
           "melhoria": "Melhoria sugerida", "regras_fechar": "Passar a limpo o aprendizado"}


def _ha(quando: str) -> str:
    from datetime import datetime
    try:
        seg = (datetime.now() - datetime.strptime(quando[:19], "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return ""
    return "agora" if seg < 90 else f"há {int(seg // 60)} min" if seg < 3600 else f"há {int(seg // 3600)} h" if seg < 172800 else f"há {int(seg // 86400)} dias"


def _miniatura(pasta: Path) -> str:
    for nome in ("folha.jpg", "quadro-1.jpg"):
        if (pasta / nome).is_file():
            return rel(pasta / nome)
    return ""


def referencias() -> list[dict]:
    import estilo_ref as _er
    out = []
    if not _er.ESTILOS.is_dir():
        return out
    for p in _er.ESTILOS.glob("*/estado.json"):
        st = ler_json(p, {}) or {}
        if st.get("gate") and st.get("estado") == "pronto" and not st.get("conjunto"):
            out.append({"tipo": "referencia", "id": st["id"], "titulo": f"1 vídeo de referência que eu estudei: {_er.nome_curto(st)}",
                        "sub": "Confira o que eu entendi do estilo antes de eu guardar", "se_aprovar": SE["referencia"],
                        "imagem": _miniatura(p.parent), "url": f"/referencia-rapida/{st['id']}", "botao": "Ver o que entendi",
                        "ha": _ha(st.get("atualizado_em") or st.get("criado_em") or "")})
    for p in (_er.ESTILOS / "_conjuntos").glob("*/conjunto.json") if (_er.ESTILOS / "_conjuntos").is_dir() else []:
        c = ler_json(p, {}) or {}
        if c.get("estado") == "analisando" and c.get("refs"):
            sts = [ler_json(_er.pasta(r) / "estado.json", {}) or {} for r in c["refs"]]
            if sts and all(s.get("estado") == "pronto" for s in sts):
                out.append({"tipo": "referencia", "id": c["id"], "titulo": f"{len(sts)} vídeos de referência que eu estudei" + (f" ({c['nome']})" if c.get("nome") else ""),
                            "sub": "Confira o que eu entendi do estilo antes de eu guardar", "se_aprovar": SE["referencia"],
                            "imagem": _miniatura(_er.pasta(c["refs"][0])),
                            "url": f"/referencia-rapida/set/{c['id']}", "botao": "Ver o que entendi",
                            "ha": _ha(c.get("atualizado_em") or c.get("criado_em") or "")})
    return out


def estudos() -> list[dict]:
    import estudos_tela as _et
    out = []
    for p in _et.PASTA.glob("*/estado.json") if _et.PASTA.is_dir() else []:
        e = ler_json(p, {}) or {}
        if e.get("gate") and e.get("pronto") and not e.get("juntado") and not e.get("rodando"):
            folha = next(iter(sorted((p.parent / "estudo-quadros" / "folhas").glob("*geral*.jpg"))), None)
            out.append({"tipo": "estudo", "id": p.parent.name,
                        "titulo": "Estudo pronto: juntar a qual estilo?", "sub": f"Estudo “{e.get('nome') or p.parent.name}”: medi o vídeo quadro a quadro", "se_aprovar": SE["estudo"],
                        "imagem": rel(folha) if folha else "",
                        "url": f"/estudar/{p.parent.name}", "botao": "Escolher o estilo", "ha": e.get("atualizado", "")})
    return out


def variacoes() -> list[dict]:
    import variacoes as _v
    return [{"tipo": "variacoes", "id": d["id"], "titulo": f"{_v.esperando(d)} ideias de vídeo nesse estilo",
             "sub": "Leia e marque quais você quer que eu faça", "se_aprovar": SE["variacoes"], "botao": "Ver as ideias", "imagem": _miniatura(_comum_ref(d)),
             "url": f"/variacoes/{d['id']}", "ha": _ha(d.get("atualizado_em") or "")}
            for d in _v.listar() if d.get("origem", "variacoes") == "variacoes" and _v.esperando(d)]


def _comum_ref(d: dict) -> Path:
    import estilo_ref as _er
    try:
        return _er.pasta((d.get("refs") or [""])[0])
    except ValueError:
        return Path("/nada")


def _capa_do_estilo(slug: str) -> str:
    """Um quadro do vídeo de referência do estilo (capa, storyboard ou folha): nunca a caixa vazia."""
    import formatos as _fmt
    base = _fmt.FORMATOS / slug / "estudos"
    for nome in ("capa-1.jpg", "storyboard-1.jpg", "folha.jpg"):
        achou = next(iter(sorted(base.glob(f"*/{nome}"))), None) if base.is_dir() else None
        if achou:
            return rel(achou)
    return ""


def estilos_novos() -> list[dict]:
    import estilo_novo as _en
    out = []
    for e in _en.em_teste():
        pv = e["primeiro_video"]
        if pv.get("estado") in ("esperando", "proposta", "proposta_aprovada", "a_propor", "ajustar"):
            esp = pv.get("estado") == "esperando"
            out.append({"tipo": "estilo_novo", "id": e["slug"],
                        "titulo": "Estilo novo: aprove o 1º vídeo pra ele virar pronto" if esp else "Estilo novo em teste: falta o 1º vídeo",
                        "sub": f"{e['titulo']} · {e['rotulo']}", "se_aprovar": SE["estilo_novo"] if esp else "eu sigo pro próximo passo do teste; o estilo só vira pronto com o 1º vídeo aprovado.",
                        "imagem": _capa_do_estilo(e["slug"]), "url": f"/estilo-novo/{e['slug']}",
                        "botao": "Ver o 1º vídeo" if esp else "Abrir", "ha": _ha(pv.get("atualizado_em") or "")})
    return out


# "Se você aprovar: ..." (a linha cinza de cada cartão): o que acontece depois do clique, em português simples
SE = {"referencia": "eu guardo o estilo no estilo que você escolher, com a régua medida; nada é apagado e nada é copiado da fala.",
      "estudo": "eu guardo o estudo como referência do estilo que você escolher; nenhuma referência existente é apagada.",
      "variacoes": "cada ideia que você aprovar abre o Criar já preenchida; nenhum vídeo é feito sem o seu clique.",
      "estilo_novo": "o estilo vira pronto e passa a aparecer no Criar.",
      "regra": "eu guardo a regra pro erro não se repetir; se não for isso, você reescreve ou troca onde ela vale."}


def _video_do_andamento(cli: str, slug: str) -> str:
    try:
        import andamento as _and
        return (_and.carregar(cli, slug) or {}).get("video") or ""
    except Exception:  # noqa: BLE001
        return ""


def regras() -> list[dict]:
    import aprendi as _ap
    return [{"tipo": "regra", "id": r["id"], "titulo": _ap.frase(r), "sub": f"Do vídeo “{r.get('titulo_video', '')}”: posso guardar isso como regra?", "se_aprovar": SE["regra"],
             "imagem": "", "thumb": _video_do_andamento(r["cliente"], r["slug"]), "url": f"/andamento/{r['cliente']}/{r['slug']}#and-aprendi", "botao": "Ver e dar OK",
             "ha": _ha(r.get("criado_em", ""))} for r in _ap.pendentes()]


def melhorias() -> list[dict]:
    """Melhoria sugerida no motor e "passar a limpo" o aprendizado (melhoria.py): esperam o Aplicar / OK do João."""
    import melhoria as _m
    out = []
    for r in _m.abertas():
        pasta = _m.pasta_melhorias() / r["id"]
        achado = ((r.get("achados") or [{}])[0].get("o_que") or "").strip()
        curto = (f"Melhoria no estilo {r.get('formato_titulo') or 'do Estúdio'}: {achado[:140]}" if r["tipo"] == "motor" and achado else r["titulo"])
        out.append({"tipo": "melhoria" if r["tipo"] == "motor" else "regras_fechar", "id": r["id"], "titulo": r["titulo"], "titulo_curto": curto,
                    "sub": (f"Não passou na prova: {r.get('motivo', '')}" if r["estado"] == "falhou" else
                            ("O Estúdio quer ajustar o próprio jeito de fazer este estilo · nada muda sem o seu Aplicar" if r["tipo"] == "motor" else "Vira regra só depois do seu OK")),
                    "imagem": r.get("miniatura") or "", "url": f"/melhoria/{r['id']}",
                    "botao": "Ver a mudança e aplicar" if r["tipo"] == "motor" else "Ver as regras e dar OK", "ha": _ha(r.get("criado_em", ""))})
    return out


def avisos() -> list[dict]:
    """"Eu já fiz": o Estúdio juntou sozinho (auto_juntar.py); só avisa, com Desfazer. Aprovação do João fica pro vídeo final."""
    import auto_juntar as _aj
    import estilo_ref as _er
    out = []
    for a in _aj.avisos():
        info, kind, pasta = a["info"], a["kind"], a["pasta"]
        o_que = {"ref": "O vídeo de referência", "set": "Os vídeos de referência", "estudo": "O estudo"}[kind]
        if kind == "set":
            c = ler_json(pasta / "conjunto.json", {}) or {}
            miniatura = _miniatura(_er.pasta(c["refs"][0])) if c.get("refs") else ""
        elif kind == "estudo":
            f = next(iter(sorted((pasta / "estudo-quadros" / "folhas").glob("*geral*.jpg"))), None)
            miniatura = rel(f) if f else ""
        else:
            miniatura = _miniatura(pasta)
        out.append({"tipo": "aviso", "id": a["id"], "titulo": (f"Criei o estilo novo “{info['titulo']}” (em teste)" if info.get("novo") else f"Juntei ao {info['titulo']}"),
                    "sub": f"{o_que} {('“' + a['nome'] + '” ') if a['nome'] else ''}foi guardado sozinho: {info.get('porque', '')}.",
                    "nota": "Se você desfizer: o que guardei vai pra lixeira e o item volta pra cá, pra você escolher o estilo.",
                    "imagem": miniatura, "url": f"/formato/{info['formato']}" if not info.get("novo") else f"/estilo-novo/{info['formato']}",
                    "acoes": [{"label": "Tá bom", "url": f"/auto/{kind}/{a['id']}/ok", "primario": True},
                              {"label": "Desfazer", "url": f"/auto/{kind}/{a['id']}/desfazer"}],
                    "ha": _ha(info.get("quando", ""))})
    return out


def itens() -> list[dict]:
    out = []
    for f in (referencias, estudos, variacoes, estilos_novos, regras, melhorias, avisos):
        try:
            out += f()
        except Exception as e:  # noqa: BLE001  uma fonte quebrada não esconde as outras
            print(f"(pendencias.{f.__name__}: {e})", file=sys.stderr)
    return out
