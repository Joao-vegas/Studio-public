#!/usr/bin/env python3
"""
Em andamento: em que passo cada vídeo está, pra o João abrir a tela e ver ("storyboard pronto, agora renderizando").
Vale pra vídeo feito pela tela (runner.py) e pelo chat. Um arquivo por vídeo: app/andamento/<Cliente>/<slug>.json.

  python3 app/ferramentas/andamento.py passo  <Cliente> <slug> "Gerando as vozes" [--etapa storyboard] [--titulo T] [--formato F]
  python3 app/ferramentas/andamento.py espera <Cliente> <slug> "Storyboard pronto: aprove" [--imagem <caminho do storyboard.jpg>]
  python3 app/ferramentas/andamento.py pronto <Cliente> <slug> [--video <mp4>] [--imagem <folha.jpg>]
  python3 app/ferramentas/andamento.py erro   <Cliente> <slug> "o que deu errado"
  python3 app/ferramentas/andamento.py nota   <Cliente> <slug> "Aprendido: ..."   (entra na linha do tempo sem mudar o estado)
  python3 app/ferramentas/andamento.py ver

Etapas (a barra da tela): preparar · storyboard · aprovacao · video · conferencia · pronto. Sem --etapa, fica a do passo anterior.
Dentro de um job da tela, a variável ESTUDIO_JOB=<Cliente>/<slug> manda (o runner põe): o passo cai no vídeo certo.
Nunca derruba quem chamou: qualquer falha aqui só vira um aviso.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, agora, append_jsonl, hoje, rel  # noqa: E402

def _pasta() -> Path:
    """app/andamento/ (lido na hora: os testes trocam _comum.ESTUDIO por uma pasta temporária)."""
    import _comum
    return _comum.ESTUDIO / "andamento"


ETAPAS = [("preparar", "Preparando"), ("storyboard", "Storyboard"), ("aprovacao", "Sua aprovação"),
          ("video", "Vídeo final"), ("conferencia", "Conferência"), ("pronto", "Pronto")]
NOMES = dict(ETAPAS)
SEM_NOTICIA_MIN = 20          # trabalhando sem passo novo há mais que isso = "sem notícia"
PRONTO_FICA_H = 48            # pronto (ou erro) continua na aba por esse tempo
SOME_DIAS = 3                 # qualquer um sem passo novo há mais que isso sai da aba (conversa que morreu no meio)


def _seguro(v: str) -> str:
    v = (v or "").strip()
    if not v or Path(v).name != v or v in (".", ".."):
        raise ValueError("cliente/slug inválido: " + repr(v))
    return v


def _arq(cli: str, slug: str) -> Path:
    return _pasta() / _seguro(cli) / f"{_seguro(slug)}.json"


def _rel(p) -> str:
    if not p:
        return ""
    p = Path(p).expanduser()
    p = p if p.is_absolute() else (Path.cwd() / p)
    try:
        return rel(p.resolve())
    except Exception:
        return str(p)


@contextmanager
def _trava():
    _pasta().mkdir(parents=True, exist_ok=True)
    with open(_pasta() / ".trava", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _ler(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _gravar(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def alvo(cli: str = "", slug: str = "") -> tuple[str, str]:
    """ESTUDIO_JOB (job da tela) ganha do que o chamador deduziu."""
    j = os.environ.get("ESTUDIO_JOB", "")
    if "/" in j:
        c, s = j.split("/", 1)
        return c, s
    return cli, slug


def registrar(cli: str, slug: str, texto: str = "", estado: str = "trabalhando", etapa: str = "", titulo: str = "",
              formato: str = "", origem: str = "", imagem: str = "", video: str = "", pasta: str = "") -> dict | None:
    """estado: trabalhando | esperando | pronto | erro. Fecha o passo anterior e abre este."""
    try:
        cli, slug = alvo(cli, slug)
        p = _arq(cli, slug)
        with _trava():
            d = _ler(p) or {"cliente": cli, "slug": slug, "titulo": titulo or slug.replace("-", " ").capitalize(),
                            "formato": formato, "origem": origem or ("tela" if os.environ.get("ESTUDIO_JOB") else "chat"),
                            "inicio": agora(), "passos": [], "etapa": "preparar"}
            if d.get("estado") in ("pronto", "erro") and estado in ("trabalhando", "esperando"):
                d["passos"].append({"texto": "Recomeçou", "inicio": agora(), "fim": agora(), "estado": "feito"})
            if d.get("estado") == "esperando" and estado == "trabalhando" and texto.startswith("Aprendido"):
                # Informativo, não é retomada: entra só no passo a passo e o banner segue na espera.
                d["passos"].append({"texto": texto, "inicio": agora(), "fim": agora(), "etapa": d.get("etapa", "preparar"), "estado": "feito"})
                d["atualizado"] = agora()
                _gravar(p, d)
                return d
            d.pop("oculto", None)
            for k, v in (("titulo", titulo), ("formato", formato), ("origem", origem)):
                if v and not d.get(k):   # quem criou manda (o runner dá o título do job; o chat não renomeia)
                    d[k] = v
            if imagem:
                d["imagem"] = _rel(imagem)
            if video:
                d["video"] = _rel(video)
            if pasta:
                d["pasta"] = _rel(pasta)
            etapa = etapa or {"esperando": "aprovacao", "pronto": "pronto"}.get(estado, "") or d.get("etapa") or "preparar"
            nova = etapa if etapa in NOMES else d.get("etapa", "preparar")
            ordem = [k for k, _ in ETAPAS]
            # A barra não regride no meio de uma rodada (o claude -p do job às vezes volta a "preparar" depois do vídeo final).
            # Recomeço de verdade (depois de pronto/erro, ou depois de uma resposta do João a um "esperando") pode voltar.
            if (d.get("estado") not in (None, "pronto", "erro", "esperando") and d.get("etapa") in ordem and nova in ordem
                    and ordem.index(nova) < ordem.index(d["etapa"])):
                nova = d["etapa"]
            d["etapa"] = nova
            texto = texto or {"pronto": "Vídeo pronto", "esperando": "Esperando você", "erro": "Parou com erro"}.get(estado, "Trabalhando")
            ult = d["passos"][-1] if d["passos"] else None
            if ult and ult.get("texto") == texto and not ult.get("fim"):
                ult["estado"] = {"trabalhando": "agora"}.get(estado, estado)
            else:
                if ult and not ult.get("fim"):
                    ult["fim"] = agora()
                    if ult.get("estado") in ("agora", "esperando"):
                        ult["estado"] = "feito"
                d["passos"].append({"texto": texto, "inicio": agora(), "etapa": d["etapa"],
                                    "estado": {"trabalhando": "agora"}.get(estado, estado)})
            if estado in ("pronto", "erro"):
                d["passos"][-1]["fim"] = agora()
            d["estado"] = estado
            d["atualizado"] = agora()
            _gravar(p, d)
            _sincronizar_job(d)
            if estado == "pronto":
                _registrar_midia(d)
            return d
    except Exception as e:
        print(f"(andamento não registrado: {e})", file=sys.stderr)
        return None


def _registrar_midia(d: dict) -> None:
    """Vídeo pronto: grava a música e os efeitos usados em acervo/usos.jsonl (rodízio). Falha aqui nunca derruba."""
    try:
        import producao as _p
        import uso_midia as _u
        j = _p._job_do_andamento(d["cliente"], d["slug"], d.get("pasta", "")) or {}
        sb = j.get("sandbox") or d.get("pasta") or ""
        if sb:
            _u.registrar_entrega(d["cliente"], d.get("formato") or j.get("formato", ""), j.get("modelo", ""), d["slug"], sb)
    except Exception as e:
        print(f"(uso de mídia não registrado: {e})", file=sys.stderr)


def _sincronizar_job(d: dict) -> None:
    """Um estado só: pronto/erro/espera também valem pro job.json do mesmo vídeo (producao.sincronizar). Falha aqui nunca derruba."""
    try:
        import producao as _p
        est = d.get("estado", "")
        if est == "esperando" and d.get("etapa") == "conferencia" and d.get("video"):
            est = "pronto"   # vídeo feito esperando conferência: o job está concluído, não de volta ao plano
        _p.sincronizar(d["cliente"], d["slug"], est, video=d.get("video", ""), pasta=d.get("pasta", ""))
    except Exception as e:
        print(f"(job não sincronizado: {e})", file=sys.stderr)


def passo(cli, slug, texto, **kw):
    return registrar(cli, slug, texto, "trabalhando", **kw)


def espera(cli, slug, texto="Esperando você", **kw):
    return registrar(cli, slug, texto, "esperando", **kw)


def _avisos_do_video(cli: str, slug: str, pasta: str = "") -> list[str]:
    """Vídeo gravado só vale como pronto com a conferência aprovada: roda producao.conferir_pos_render no job do vídeo. Falha aqui nunca derruba."""
    try:
        import producao as _p
        cli, slug = alvo(cli, slug)
        j = _p._job_do_andamento(cli, slug, pasta)
        est = _p._esteira(j) if j else None
        if not j or not j.get("saida") or not est or est.get("tipo") != "gravado":
            return []   # só vídeo gravado de formato com esteira passa pela conferência
        avisos = _p.conferir_pos_render(j)
        _p.salvar(j)
        return avisos
    except Exception as e:
        print(f"(conferência não rodou: {e})", file=sys.stderr)
        return []


def pronto(cli, slug, texto="Vídeo pronto", **kw):
    """Vídeo gravado reprovado na conferência não vira "Vídeo pronto": fica esperando, na etapa da conferência, com os avisos."""
    if kw.get("video"):
        try:
            _c, _s = alvo(cli, slug)
            _d = _ler(_arq(_c, _s)) or {}
        except Exception:
            _d = {}
        # o job precisa apontar pra saída antes de conferir
        try:
            import producao as _p
            _j = _p._job_do_andamento(_c, _s, kw.get("pasta") or _d.get("pasta", ""))
            if _j and not _j.get("rodando") and _j.get("status") not in _p.FECHADOS:
                _sai = _p.achar_saida(_j, kw["video"])
                if _sai:
                    _j["saida"] = _sai
                    _p.salvar(_j)
        except Exception:
            pass
        avisos = _avisos_do_video(cli, slug, kw.get("pasta") or _d.get("pasta", ""))
        if avisos:
            return registrar(cli, slug, "Conferir: " + "; ".join(avisos), "esperando", etapa="conferencia", **kw)
    r = registrar(cli, slug, texto, "pronto", **kw)
    if kw.get("video"):   # capa e miniaturas nascem agora, em segundo plano: a tela já abre com elas
        try:
            import preparar
            preparar.depois(video=kw["video"], pasta=kw.get("pasta") or _d.get("pasta"))
        except Exception:
            pass
    return r


def erro(cli, slug, texto="Parou com erro", **kw):
    from _comum import erro_simples
    return registrar(cli, slug, erro_simples(texto), "erro", **kw)


def nota(cli: str, slug: str, texto: str) -> dict | None:
    """Anota um passo já feito na linha do tempo sem mexer no estado, na etapa nem no passo em andamento."""
    try:
        cli, slug = alvo(cli, slug)
        p = _arq(cli, slug)
        with _trava():
            d = _ler(p)
            if not d:
                return None
            d["passos"].append({"texto": texto, "inicio": agora(), "fim": agora(), "etapa": d.get("etapa", "preparar"), "estado": "feito"})
            d["atualizado"] = agora()
            _gravar(p, d)
            return d
    except Exception as e:
        print(f"(nota não registrada: {e})", file=sys.stderr)
        return None


def esconder(cli: str, slug: str) -> bool:
    p = _arq(cli, slug)
    with _trava():
        d = _ler(p)
        if not d:
            return False
        d["oculto"] = True
        _gravar(p, d)
    return True


def remover(cli: str, slug: str) -> bool:
    """Tira o registro do vídeo de vez (o arquivo some; esconder só marca). Usado pelo caminho único de apagar (saidas.py)."""
    p = _arq(cli, slug)
    with _trava():
        if not p.is_file():
            return False
        p.unlink()
    return True


def esta_trabalhando(d: dict) -> bool:
    """Passo novo nos últimos SEM_NOTICIA_MIN minutos: tem alguém (a IA) mexendo nesse vídeo agora."""
    return d.get("estado") == "trabalhando" and _min_desde(d.get("atualizado", "")) < SEM_NOTICIA_MIN


# ───────────────────────── resposta do João (aprovar / pedir ajuste) ─────────────────────────

DECISOES = ("aprovar", "ajustar")


def pasta_do_episodio(d: dict) -> Path | None:
    """Pasta do vídeo em output/. Registros antigos não têm: procura clientes/<Cliente>/*Content/output/<formato>/<slug>."""
    if d.get("pasta") and (RAIZ / d["pasta"]).is_dir():
        return RAIZ / d["pasta"]
    if d.get("formato") and d.get("cliente") and d.get("slug"):
        for q in sorted((RAIZ / "clientes" / d["cliente"]).glob(f"*Content/output/{d['formato']}/{d['slug']}")):
            if q.is_dir() and (q / "episodio.json").is_file():
                return q
    return None


APLICANDO_MAX_MIN = 90   # "aplicando" mais velho que isso = o processo morreu; não trava mais respostas


def aplicando(d: dict) -> bool:
    return any(r.get("status") == "aplicando" and _min_desde(r.get("em", "")) < APLICANDO_MAX_MIN for r in d.get("respostas", []))


def responder(cli: str, slug: str, decisao: str, texto: str = "", ref: str = "", segundo=None) -> tuple[dict, int]:
    """Guarda a resposta do João no registro e uma linha no histórico do formato (vira regra pela REGRA Nº 2).
    Devolve (registro, índice da resposta). Quem dispara o trabalho em segundo plano é a rota."""
    if decisao not in DECISOES:
        raise ValueError("decisão inválida")
    texto = (texto or "").strip()
    if decisao == "ajustar" and not texto:
        raise ValueError("Conte o que ajustar.")
    try:
        segundo = round(float(segundo), 1) if segundo not in (None, "") else None
    except (TypeError, ValueError):
        segundo = None
    ref = (ref or "").strip()
    p = _arq(cli, slug)
    with _trava():
        d = _ler(p)
        if not d:
            raise ValueError("vídeo não encontrado")
        if aplicando(d):
            raise ValueError("Ainda estou aplicando o pedido anterior. Espere terminar.")
        resp = {"em": agora(), "decisao": decisao, "texto": texto, "ref": ref, "segundo": segundo,
                "etapa_no_momento": d.get("etapa", ""), "estado_no_momento": d.get("estado", ""), "status": "enviado"}
        d.setdefault("respostas", []).append(resp)
        fmt = d.get("formato") or ""
        try:
            pasta_fmt = RAIZ / "formatos" / _seguro(fmt) / "aprendizado" if fmt else None
        except ValueError:
            pasta_fmt = None
        if pasta_fmt and pasta_fmt.parent.is_dir():
            linha = {"tipo": "feedback" if texto else "aprovacao", "categoria": "geral",
                     "texto": texto or f"Vídeo '{d.get('titulo', slug)}' aprovado sem ressalvas.",
                     "origem": "usuario", "createdAt": hoje(), "job": d.get("pasta") or f"{cli}/{slug}"}
            if ref:
                linha["referencia"] = {"ref": ref, "segundo": segundo}
            append_jsonl(pasta_fmt / "historico.jsonl", linha)
        _gravar(p, d)
        return d, len(d["respostas"]) - 1


def marcar_resposta(cli: str, slug: str, idx: int, status: str) -> bool:
    """status: enviado | aplicando | feito | erro."""
    try:
        p = _arq(cli, slug)
        with _trava():
            d = _ler(p)
            if not d or not (0 <= idx < len(d.get("respostas", []))):
                return False
            d["respostas"][idx]["status"] = status
            _gravar(p, d)
            return True
    except Exception as e:
        print(f"(resposta não marcada: {e})", file=sys.stderr)
        return False


def referencias(formato: str) -> list[dict]:
    """Vídeos de referência do formato pra marcar um momento: estudos (o principal primeiro) e os exemplos do formato.json."""
    out = []
    try:
        import formatos as _f
        for e in _f.estudos(formato):
            for v in e["videos"]:
                out.append({"video": v, "nome": f"{e['titulo']}" + (f" ({Path(v).stem})" if len(e["videos"]) > 1 else ""),
                            "principal": e["principal"], "poster": ""})
        f = _f.carregar(formato)
        for e in (f["exemplos"] if f else []):
            out.append({"video": e["video"], "nome": e.get("legenda") or Path(e["video"]).stem, "principal": False,
                        "poster": e.get("poster_rel") or ""})
    except Exception:
        pass
    return out


# ───────────────────────── leitura (tela) ─────────────────────────

def _min_desde(t: str) -> float:
    try:
        return (datetime.now() - datetime.strptime(t, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
    except Exception:
        return 0.0


def ha(t: str) -> str:
    m = _min_desde(t)
    if m < 1:
        return "agora há pouco"
    if m < 60:
        return f"há {int(m)} min"
    if m < 60 * 24:
        h = int(m // 60)
        return f"há {h} h" + (f" {int(m % 60)} min" if m % 60 >= 1 and h < 3 else "")
    return f"há {int(m // 1440)} dia(s)"


def duracao(a: str, b: str = "") -> str:
    try:
        f = "%Y-%m-%d %H:%M:%S"
        s = ((datetime.strptime(b, f) if b else datetime.now()) - datetime.strptime(a, f)).total_seconds()
    except Exception:
        return ""
    return f"{int(s)} s" if s < 60 else (f"{int(s // 60)} min" if s < 3600 else f"{int(s // 3600)} h {int(s % 3600 // 60)} min")


def aprovado_em(d: dict) -> str:
    """Quando o João aprovou o vídeo pronto ("Ficou bom?"): a última resposta dele, depois do último pronto, foi aprovar. Vazio = não."""
    if d.get("estado") != "pronto":
        return ""
    ult = next((r for r in reversed(d.get("respostas") or []) if r.get("estado_no_momento") == "pronto"
                and r.get("em", "") >= d.get("atualizado", "")), None)
    return ult["em"] if ult and ult.get("decisao") == "aprovar" and not ult.get("desfeita") else ""


def desfazer_aprovacao(cli: str, slug: str) -> bool:
    """"Desfazer aprovação": a última aprovação vira desfeita (o vídeo volta pro "Ficou bom?" e pro Esperando você). A resposta fica no
    registro, só marcada. False = não havia aprovação valendo."""
    p = _arq(cli, slug)
    with _trava():
        d = _ler(p)
        if not d or not aprovado_em(d):
            return False
        ult = next(r for r in reversed(d["respostas"]) if r.get("decisao") == "aprovar" and not r.get("desfeita"))
        ult["desfeita"] = agora()
        _gravar(p, d)
        return True


def registros():
    """Os registros crus (sem enfeitar), pra quem só precisa ler o estado."""
    if _pasta().is_dir():
        for p in _pasta().glob("*/*.json"):
            d = _ler(p)
            if d and d.get("cliente") and d.get("slug"):
                yield d


def _barra_pelo_pipeline(d: dict, job: dict | None) -> None:
    """Com job, a barra usa as mesmas etapas dos Detalhes técnicos (pipeline.etapas): uma fonte só.
    Etapa que não aconteceu num vídeo já entregue não é desenhada (sem bolinha fantasma)."""
    if not job:
        return
    try:
        import pipeline as _pl
        lista = _pl.etapas(job)
    except Exception:
        return
    if not lista:
        return
    mapa = {"pronto": "feito", "rodando": "agora", "revisar": "agora", "atencao": "agora", "aguardando": "depois"}
    entregue = d.get("estado") == "pronto"
    d["barra"] = [{"id": e["id"], "nome": e["titulo"], "estado": mapa.get(e["estado"], "depois")}
                  for e in lista if not (entregue and e["estado"] == "aguardando")]   # etapa que não rodou nem aparece


def _enfeitar(d: dict) -> dict:
    d["id"] = f"{d['cliente']}/{d['slug']}"
    for p in d.get("passos", []):
        p["dura"] = duracao(p["inicio"], p["fim"]) if p.get("fim") else ("agora" if p.get("estado") == "agora" else "")
    d["atual"] = d["passos"][-1] if d.get("passos") else {}
    if d.get("estado") == "esperando":   # banner = a última espera; notas ("Aprendido...") entram só no passo a passo
        d["atual"] = next((x for x in reversed(d["passos"]) if x.get("estado") == "esperando"), d["atual"])
    if d.get("estado") == "pronto":   # a revisão do Estúdio roda depois do "Vídeo pronto"; o banner continua dizendo pra assistir e aprovar
        d["atual"] = next((x for x in reversed(d["passos"]) if not str(x.get("texto", "")).startswith("Revisão do Estúdio")), d["atual"])
    if not (d.get("titulo") or "").strip() or d.get("titulo") == d["slug"]:
        d["titulo"] = d["slug"].replace("-", " ").capitalize()
    if not d.get("formato"):
        m = re.search(r"/modelos/([^/]+)", d.get("pasta") or "")
        if m:
            try:
                import formatos as _f0
                dono = _f0.de_modelo(m.group(1))
                if dono:
                    d["formato"] = dono["slug"]
            except Exception:
                pass
    d["respostas"] = d.get("respostas") or []
    d["aplicando"] = aplicando(d)
    d["ha"] = ha(d.get("atualizado", ""))
    d["tempo_total"] = "" if d.get("inicio") == d.get("atualizado") else duracao(d.get("inicio", ""), d.get("atualizado", "") if d.get("estado") in ("pronto", "erro") else "")
    # job da tela: o runner sabe se a IA ainda está viva
    job = None
    try:
        import producao as _p
        job = _p.carregar(d["cliente"], d["slug"])
    except Exception:
        pass
    d["tem_job"] = bool(job)
    d["sem_noticia"] = (d.get("estado") == "trabalhando" and _min_desde(d.get("atualizado", "")) > SEM_NOTICIA_MIN
                        and not (job and job.get("rodando")))
    if job and d.get("estado") == "trabalhando" and not job.get("rodando") and job.get("status") not in ("na_fila",):
        d["sem_noticia"] = d["sem_noticia"] or _min_desde(d.get("atualizado", "")) > 2
    idx = [k for k, _ in ETAPAS].index(d.get("etapa", "preparar")) if d.get("etapa") in NOMES else 0
    d["barra"] = [{"id": k, "nome": n, "estado": ("feito" if i < idx or d.get("estado") == "pronto"
                                                    else ("agora" if i == idx else "depois"))}
                  for i, (k, n) in enumerate(ETAPAS)]
    _barra_pelo_pipeline(d, job)
    try:
        import formatos as _f
        f = _f.carregar(d.get("formato") or "")
        d["formato_titulo"] = f["titulo"] if f else (d.get("formato") or "")
    except Exception:
        d["formato_titulo"] = d.get("formato") or ""
    for k in ("imagem", "video"):
        if d.get(k) and not (RAIZ / d[k]).is_file():
            d[k] = ""
    return d


def carregar(cli: str, slug: str) -> dict | None:
    try:
        d = _ler(_arq(cli, slug))
    except ValueError:
        return None
    return _enfeitar(d) if d else None


def listar(tudo: bool = False) -> list[dict]:
    """Ativos: trabalhando, esperando, erro (até esconder) e pronto nas últimas PRONTO_FICA_H horas, enquanto o João não aprovou
    (aprovado vai pra Meus vídeos: o mesmo vídeo não fica nos dois lugares)."""
    out = []
    for d in registros():
        velho = _min_desde(d.get("atualizado", ""))
        if not tudo and (d.get("oculto") or (d.get("estado") in ("pronto", "erro") and velho > PRONTO_FICA_H * 60)
                         or velho > SOME_DIAS * 1440 or aprovado_em(d)):
            continue
        out.append(_enfeitar(d))
    ordem = {"trabalhando": 0, "esperando": 1, "erro": 2, "pronto": 3}
    out.sort(key=lambda d: d.get("atualizado", ""), reverse=True)
    out.sort(key=lambda d: ordem.get(d.get("estado"), 9))
    return out


def contagem() -> int:
    """Badge do menu: o que está trabalhando ou esperando o João."""
    try:
        return sum(1 for d in listar() if d.get("estado") in ("trabalhando", "esperando"))
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Em andamento: registra o passo atual de um vídeo.")
    ap.add_argument("acao", choices=["passo", "espera", "pronto", "erro", "nota", "esconder", "ver"])
    ap.add_argument("args", nargs="*", help="<Cliente> <slug> \"texto\"; dentro de um job da tela (ESTUDIO_JOB) basta o texto")
    ap.add_argument("--etapa", default="", choices=[""] + [k for k, _ in ETAPAS])
    ap.add_argument("--titulo", default="")
    ap.add_argument("--formato", default="")
    ap.add_argument("--imagem", default="")
    ap.add_argument("--video", default="")
    ap.add_argument("--pasta", default="")
    a = ap.parse_args()
    if a.acao == "ver":
        for d in listar():
            print(f"{d['estado']:<11} {d['id']:<36} {NOMES.get(d.get('etapa'), '')}: {d['atual'].get('texto', '')} ({d['ha']})")
        return
    x = a.args
    if os.environ.get("ESTUDIO_JOB") and len(x) <= 1:
        x = ["", ""] + x
    cli, slug = alvo(*(x[:2] + ["", ""])[:2])
    a.texto = " ".join(x[2:])
    if not cli or not slug:
        ap.error("diga o cliente e o slug (ou rode dentro de um job, com ESTUDIO_JOB)")
    if a.acao == "esconder":
        print("escondido" if esconder(cli, slug) else "não achei")
        return
    if a.acao == "nota":
        print("ok" if nota(cli, slug, a.texto) else "não achei")
        return
    estado = {"passo": "trabalhando", "espera": "esperando"}.get(a.acao, a.acao)
    d = registrar(cli, slug, a.texto, estado, etapa=a.etapa, titulo=a.titulo, formato=a.formato, imagem=a.imagem, video=a.video,
                  pasta=a.pasta)
    if d:
        print(f"ok · {NOMES.get(d['etapa'])}: {d['passos'][-1]['texto']}")


if __name__ == "__main__":
    main()
