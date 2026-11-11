#!/usr/bin/env python3
"""
estilo_novo — o estilo novo nasce "em teste" e só vira pronto com o "Aprovou?" do João no 1º vídeo de teste
(PLANO-2.0, "Uso direto pelo app", item 5).

Fluxo (formato.json → em_teste: true, primeiro_video.estado):
  a_propor → o Estúdio propõe o 1º vídeo de teste (ideia + gancho + roteiro, variacoes.py, 1 variação) → proposta
  proposta → João aprova a proposta → proposta_aprovada → alguém monta o vídeo e registra (tela ou
  `python3 app/ferramentas/estilo_novo.py video <slug> <mp4>`) → esperando
  esperando → João aprova → vira exemplo principal + formatos.marcar_pronto (pelo CONTRATO); só aí sai de "em teste"
  esperando → "Quero alterar" → ajustar (volta a ser refeito; continua em teste)
Enquanto não aprova: status "receita" e oculto (fica em "Mais formatos (em teste)"; nunca no Criar).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import agora, append_jsonl, ensure, gravar_json, hoje, ler_json, make_slug, rel  # noqa: E402
import formatos as _fmt  # noqa: E402

ESTADOS = ("a_propor", "proposta", "proposta_aprovada", "esperando", "ajustar", "aprovado")
ROTULO = {"a_propor": "Falta propor o 1º vídeo de teste", "proposta": "Proposta do 1º vídeo esperando você",
          "proposta_aprovada": "Proposta aprovada: falta montar o 1º vídeo", "esperando": "1º vídeo de teste esperando você",
          "ajustar": "Pediu ajuste: falta refazer o 1º vídeo", "aprovado": "Aprovado: estilo pronto"}


def _pasta(slug: str) -> Path:
    if Path(slug).name != slug or slug.startswith((".", "_")):
        raise ValueError("Estilo inválido.")
    return _fmt.FORMATOS / slug


def _dados(slug: str) -> dict:
    d = ler_json(_pasta(slug) / "formato.json", None)
    if not d:
        raise ValueError("Estilo não encontrado.")
    return d


def _grava(slug: str, **pv) -> dict:
    d = _dados(slug)
    d["primeiro_video"] = {**(d.get("primeiro_video") or {}), **pv, "atualizado_em": agora()}
    gravar_json(_pasta(slug) / "formato.json", d)
    return d["primeiro_video"]


def estado(slug: str) -> dict | None:
    """{slug, titulo, em_teste, primeiro_video, rotulo}; None se o estilo não é um estilo em teste."""
    try:
        d = _dados(slug)
    except ValueError:
        return None
    if not d.get("em_teste"):
        return None
    pv = d.get("primeiro_video") or {"estado": "a_propor"}
    return {"slug": slug, "titulo": d.get("titulo") or slug, "em_teste": True, "status": d.get("status"), "primeiro_video": pv,
            "rotulo": ROTULO.get(pv.get("estado"), pv.get("estado", ""))}


def em_teste() -> list[dict]:
    return [e for f in _fmt.listar(ocultos=True) if f.get("slug") and (e := estado(f["slug"]))]


def criar(ref_id: str, nome: str = "") -> str:
    """Cria o estilo (receita, oculto, em teste) com a referência como principal. NUNCA pronto."""
    import estilo_ref as _er
    nome = (nome or "").strip() or ("estilo " + ref_id[:4])
    slug = make_slug(nome, 40)
    base_slug, n = slug, 1
    while _fmt.carregar(slug) or (_fmt.FORMATOS / slug).exists():   # nome já existe: nunca mexe no estilo pronto
        n += 1
        slug = f"{base_slug}-{n}"
    d = _fmt.novo_formato(slug, titulo=nome if n == 1 else f"{nome} ({n})")
    dados = ler_json(d / "formato.json", {}) or {}
    dados.update({"oculto": True, "status": "receita", "em_teste": True,
                  "primeiro_video": {"estado": "a_propor", "ref": ref_id, "criado_em": agora()}})
    gravar_json(d / "formato.json", dados)
    _er.confirmar(ref_id, slug, nome, True)
    return slug


def propor_primeiro(slug: str, esperar: bool = False) -> str:
    """Pede a proposta do 1º vídeo de teste (1 variação na pegada da referência). Estado → proposta."""
    import variacoes
    pv = (_dados(slug).get("primeiro_video") or {})
    if pv.get("estado") not in ("a_propor", "ajustar", "proposta"):
        raise ValueError("A proposta do 1º vídeo já foi feita.")
    if not pv.get("ref"):
        raise ValueError("Este estilo não guarda a referência de origem.")
    vid = variacoes.propor([pv["ref"]], qtd=1, estilo=slug, origem="primeiro_video", esperar=esperar)
    _grava(slug, estado="proposta", proposta=vid)
    return vid


def aprovar_proposta(slug: str) -> None:
    import variacoes
    pv = _dados(slug).get("primeiro_video") or {}
    st = variacoes.estado(pv.get("proposta") or "") or {}
    if st.get("estado") != "proposta":
        raise ValueError("A proposta ainda não está pronta.")
    variacoes.decidir(st["id"], 1, "aprovar")
    _grava(slug, estado="proposta_aprovada")


def registrar_video(slug: str, mp4: Path) -> Path:
    mp4 = Path(mp4)
    if not mp4.is_file() or not _fmt.e_video(mp4):
        raise ValueError("Esse arquivo não é um vídeo que dê pra abrir.")
    pv = _dados(slug).get("primeiro_video") or {}
    if pv.get("estado") not in ("proposta_aprovada", "ajustar", "a_propor", "proposta", "esperando"):
        raise ValueError("Este estilo já foi aprovado.")
    dst = ensure(_pasta(slug) / "teste") / f"primeiro-video-v{len(list((_pasta(slug) / 'teste').glob('primeiro-video-v*.mp4'))) + 1}.mp4"
    _clonar(mp4, dst)
    _grava(slug, estado="esperando", video=rel(dst), faltas=[])
    return dst


def aprovar_video(slug: str) -> list[str]:
    """O "Aprovou?" final. Devolve as faltas do CONTRATO (vazio = o estilo virou pronto e sai de "em teste")."""
    pv = _dados(slug).get("primeiro_video") or {}
    if pv.get("estado") != "esperando" or not pv.get("video"):
        raise ValueError("Ainda não há 1º vídeo de teste esperando você.")
    video = _comum.RAIZ / pv["video"]
    _fmt.promover_exemplo(slug, video, "1º vídeo de teste aprovado pelo João", origem=pv["video"])
    faltas = _fmt.marcar_pronto(slug)
    if faltas:
        _grava(slug, faltas=faltas)
        return faltas
    d = _dados(slug)
    d.pop("oculto", None)
    d["em_teste"] = False
    d["primeiro_video"] = {**(d.get("primeiro_video") or {}), "estado": "aprovado", "aprovado_em": agora(), "faltas": []}
    gravar_json(_pasta(slug) / "formato.json", d)
    return []


def pedir_ajuste(slug: str, texto: str) -> None:
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Conte o que ajustar.")
    pv = _dados(slug).get("primeiro_video") or {}
    if pv.get("estado") != "esperando":
        raise ValueError("Não há vídeo esperando você.")
    append_jsonl(_pasta(slug) / "aprendizado" / "historico.jsonl", {
        "tipo": "feedback", "categoria": "geral", "texto": texto, "origem": "usuario", "createdAt": hoje(),
        "decisao": "ajustar", "job": "primeiro-video-de-teste", "video": pv.get("video")})
    _grava(slug, estado="ajustar", ajuste=texto)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["video"] and len(a) == 3:
        print(rel(registrar_video(a[1], Path(a[2]))))
    else:
        for e in em_teste():
            print(e["slug"], e["rotulo"])
