#!/usr/bin/env python3
"""
revisao — o Estúdio confere sozinho cada vídeo que acabou de ficar pronto (CLAUDE.md, REGRA Nº 2, passo 4).

Antes isso era o chat olhando a folha de todos os planos. Agora o runner dispara esta etapa assim que o vídeo final sai:
  1. conferência automática (o que o conferir_video.py já checa) + régua do estilo (estudo_quadros comparar) quando houver;
  2. folha de quadros do vídeo inteiro (1 quadro por segundo, em até 3 folhas);
  3. UMA chamada curta ao Claude (Sonnet, esforço baixo/médio, teto de US$ 0,50) que olha a folha e lista o que ficou fora:
     texto ilegível, rosto cortado, parado demais, repetição, música alta, voz trocada...;
  4. cada achado vira uma linha no historico.jsonl do modelo, com `causa` e `conserto` sugerido, e uma miniatura do quadro;
  5. achado MECÂNICO (é do motor/checador) que já apareceu em 2+ vídeos, ou que a IA marcou como claramente do motor,
     vira "Melhoria sugerida" (melhoria.py): o João vê o diff e só o "Aplicar" dele mexe em arquivo.

Resultado em app/jobs/<cliente>/<slug>/revisao.json (a tela Em andamento mostra "Revisão do Estúdio: N coisas pra melhorar").
Roda em processo próprio (não trava a fila nem a tela e sobrevive ao recarregar do servidor).

  python3 app/ferramentas/revisao.py rodar <Cliente> <slug>
  python3 app/ferramentas/revisao.py ver    <Cliente> <slug>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum  # noqa: E402
from _comum import agora, append_jsonl, ensure, gravar_json, hoje, ler_json, ler_jsonl  # noqa: E402

# o que a revisão sabe nomear (chave fixa: é por ela que "apareceu em 2+ vídeos" é contado)
FALHAS = {
    "texto_ilegivel": "Texto ilegível ou cortado", "rosto_cortado": "Rosto cortado ou escondido", "parado_demais": "Parado demais",
    "repeticao": "Repetição (cena, clipe ou frase)", "musica_alta": "Música alta por cima da voz", "voz_trocada": "Voz trocada ou estranha",
    "legenda_cobre": "Legenda cobrindo algo importante", "audio_cortado": "Áudio cortado ou com ruído", "enquadramento": "Enquadramento ruim",
    "corte_ruim": "Corte ou transição ruim", "material_ruim": "Material ruim (imagem, clipe ou fonte)", "outro": "Outro",
    "imagem_nao_casa": "Imagem que não mostra o que a fala diz", "imagem_repetida": "Mesma pessoa ou mesma imagem (mesmo de arquivo diferente) perto no tempo",
    "imagem_cliche": "Imagem clichê de banco (foto posando, pilha de dinheiro genérica)",
}
MAX_ACHADOS = 5
MAX_FOLHAS = 3
MECANICO = ("nao", "provavel", "claro")


def arquivo(cli: str, slug: str) -> Path:
    return _comum.ESTUDIO / "jobs" / cli / slug / "revisao.json"


def carregar(cli: str, slug: str) -> dict | None:
    d = ler_json(arquivo(cli, slug), None)
    return d if isinstance(d, dict) else None


def _vivo(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def rodando(cli: str, slug: str) -> bool:
    d = carregar(cli, slug) or {}
    return d.get("estado") == "rodando" and _vivo(d.get("pid"))


def disparar(cli: str, slug: str) -> bool:
    """Chamado pelo runner quando o vídeo final sai. Processo próprio; nunca derruba quem chamou."""
    try:
        if rodando(cli, slug):
            return False
        log = ensure(_comum.ESTUDIO / "jobs" / cli / slug) / "revisao.log"
        with log.open("a") as f:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "rodar", cli, slug], cwd=str(_comum.RAIZ),
                             start_new_session=True, stdout=f, stderr=subprocess.STDOUT)
        return True
    except Exception as e:  # noqa: BLE001
        print("(revisão não disparada: " + str(e) + ")", file=sys.stderr)
        return False


# ───────────────────────────── o que existe pra olhar ─────────────────────────────

def _contexto(job: dict) -> dict:
    """Vídeo, sandbox, pasta de aprendizado do modelo e estilo (formato) do job. Levanta ValueError se faltar o vídeo."""
    import formatos as _fmt
    saida = _comum.RAIZ / (job.get("saida") or "")
    if not job.get("saida") or not saida.is_file():
        raise ValueError("o vídeo final não existe")
    sb = _comum.RAIZ / (job.get("sandbox") or "")
    cli = _comum.cliente(job["cliente"])
    mod = _comum.modelo(cli, job.get("modelo") or "") if cli else None
    f = _fmt.do_job(job) or {}
    est = None
    try:
        import producao as P
        est = P._esteira(job)
    except Exception:  # noqa: BLE001
        pass
    return {"saida": saida, "sandbox": sb, "pasta_aprendizado": (mod["pasta"] / "aprendizado") if mod else None,
            "formato": f.get("slug") or job.get("formato") or "", "formato_titulo": f.get("titulo") or "",
            "gravado": bool(est and est.get("tipo") == "gravado"), "proporcao": str(f.get("proporcao") or "9:16")}


def conferencia(job: dict, ctx: dict) -> list[str]:
    """Avisos da conferência automática, em português. Gravado: o conferir_video completo; motor: o que vale pra qualquer vídeo."""
    import conferir_video as C
    sb, video = ctx["sandbox"], ctx["saida"]
    if ctx["gravado"] and sb.is_dir():
        q = ler_json(sb / "qa" / "conferir.json", None)
        if isinstance(q, dict) and q.get("video") and Path(q["video"]) == video and video.stat().st_mtime <= (sb / "qa" / "conferir.json").stat().st_mtime + 1:
            return [str(a) for a in (q.get("avisos") or [])]
        return [str(a) for a in C.conferir(video, sb)["avisos"]]
    info = _comum.ffprobe(video)
    dur = float(info.get("duracao") or 0)
    av = C.checar_formato(info, C.tem_audio(video)) if ctx["proporcao"] == "9:16" else ([] if C.tem_audio(video) else ["Vídeo sem áudio"])
    av += C.checar_tela(video, dur)
    lufs = C.medir_lufs(video)
    if lufs is not None and not C.LUFS_MIN <= lufs <= C.LUFS_MAX:
        av.append(f"Voz em {lufs:.0f} LUFS (o certo é entre -17 e -11)")
    return av


def regua(ctx: dict, destino: Path) -> list[str]:
    """Medidas do vídeo FORA da régua do estilo (estudo_quadros comparar). Vazio se o estilo não tem régua ou a medição falhar."""
    estudo = _comum.RAIZ / "formatos" / ctx["formato"] / "estudo-quadros" / "estudo.json"
    if not ctx["formato"] or not estudo.is_file():
        return []
    try:
        import estudo_quadros as EQ
        words = next((p for p in (ctx["sandbox"] / "qa/words-saida.json", ctx["sandbox"] / "work/legenda/words.json",
                                  ctx["sandbox"] / "work/words.json") if p.is_file()), None)
        cenas = ctx["sandbox"] / "cenas.json"
        r = EQ.comparar(estudo, ctx["saida"], saida=destino, words=str(words) if words else None,
                        cenas=str(cenas) if cenas.is_file() else None)
        return [f"{x['medida']}: nosso {x['nosso']} {x['unidade']}, a régua pede {x['ref']} (faixa {x['faixa_ref'][0]} a {x['faixa_ref'][1]})"
                for x in r.get("linhas", []) if x.get("ok") is False][:6]
    except Exception as e:  # noqa: BLE001
        print("(régua não medida: " + str(e) + ")", file=sys.stderr)
        return []


def imagens_x_fala(ctx: dict) -> list[dict]:
    """Medido, sem IA: nota de cada cena com imagem contra a fala (casar_imagem.conferir_cenas, REGRAS.md G6). Só estilo de motor com
    cenas.json (Editorial, Documentário); sem modelo CLIP no cache ou sem cenas devolve []. Já vem no formato dos achados da revisão."""
    sb = ctx["sandbox"]
    if ctx["gravado"] or not (sb / "cenas.json").is_file():
        return []
    try:
        import casar_imagem as CI
        r = CI.conferir_cenas(sb)
    except Exception as e:  # noqa: BLE001
        print("(imagem x fala não medida: " + str(e)[:120] + ")", file=sys.stderr)
        return []
    por_n = {c["n"]: c for c in r.get("cenas", [])}
    out = []
    causas = {
        "imagem_nao_casa": "A cena foi fechada sem conferir a imagem contra a fala: faltou o `casar_imagem.py melhores` (achar o quadro do objeto citado) "
                           "e o `pontuar` antes de aprovar.",
        "imagem_cliche": "A imagem veio de banco ou é genérica (foto posando, pilha de dinheiro): faltou buscar o momento real do caso, o clipe viral ou "
                         "o vídeo da ação antes de cair no banco, e rodar `casar_imagem.py conferir` (achado `cliche`).",
        "imagem_repetida": "A mesma pessoa ou a mesma imagem (mesmo de arquivo diferente) foi reaproveitada perto no tempo em vez de buscar a imagem do que a "
                           "fala cita; a regra G6 limita a 2 vezes por pessoa no vídeo e não repete imagem.",
    }
    por_tipo = {"nao_casa": "imagem_nao_casa", "cliche": "imagem_cliche", "mesma_imagem": "imagem_repetida", "quase_igual": "imagem_repetida",
                "mesma_pessoa": "imagem_repetida", "pessoa_demais": "imagem_repetida"}   # acao_sem_video é aviso da conferência, não achado da revisão
    for a in r.get("achados", []):
        tipo = por_tipo.get(a["tipo"])
        if not tipo:
            continue
        c = por_n.get(a["cena"]) or {}
        out.append({"t": float(c.get("de") or 0) + 0.3, "tipo": tipo, "o_que": a["texto"], "causa": causas[tipo],
                    "conserto": a["conserto"], "mecanico": "nao", "onde": "", "regra_furou": "G6"})
    return out


def folhas(video: Path, destino: Path) -> list[Path]:
    """Até 3 folhas cobrindo o vídeo inteiro (1 quadro por segundo; vídeo longo sobe o passo). Cada quadro tem o segundo escrito."""
    import folha as F
    dur = float(_comum.ffprobe(video).get("duracao") or 0)
    if dur <= 0:
        return []
    por_folha = F.MAX_QUADROS
    n = min(MAX_FOLHAS, max(1, int(-(-dur // por_folha))))
    passo = max(1.0, dur / (n * por_folha))
    trecho = dur / n
    out = []
    ensure(destino)
    for i in range(n):
        p = destino / f"folha-{i + 1}.jpg"
        F.folha(video, p, de=i * trecho, ate=(i + 1) * trecho if i + 1 < n else dur, passo=passo, colunas=6)
        out.append(p)
    return out


def quadro(video: Path, t: float, saida: Path, largura: int = 360) -> bool:
    ensure(saida.parent)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={largura}:-2", "-q:v", "4", str(saida)], capture_output=True, timeout=120)
    return r.returncode == 0 and saida.is_file()


# ───────────────────────────── a chamada à IA ─────────────────────────────

def prompt_revisao(job: dict, ctx: dict, fl: list[Path], avisos: list[str], fora: list[str], saida_json: Path, imagens: list[dict] | None = None) -> str:
    regras = []
    if ctx["pasta_aprendizado"]:
        d = ler_json(ctx["pasta_aprendizado"] / "regras.json", {}) or {}
        regras = [f"  [{r.get('id')}] {str(r.get('texto', ''))[:160]}" for r in (d.get("regras") or []) if isinstance(r, dict)][:24]
    cenas = next((p for p in (ctx["sandbox"] / "cenas.json", ctx["sandbox"] / "PLANO.json") if p.is_file()), None)
    onde = []
    if ctx["formato"]:
        onde.append(f"formatos/{ctx['formato']}/base/ (o motor do estilo, se for motor)")
    if ctx["pasta_aprendizado"]:
        onde.append(f"{_comum.rel(ctx['pasta_aprendizado'].parent)}/ (os scripts do modelo do cliente)")
    onde.append("app/ferramentas/conferir_video.py (o checador)")
    return f"""Você é a REVISÃO do Estúdio de vídeo do João. Um vídeo acabou de ficar pronto e ninguém olhou ainda. Seu trabalho: achar o que ficou FORA, curto e honesto.

VÍDEO: {_comum.rel(ctx['saida'])}  ·  estilo: {ctx['formato_titulo'] or ctx['formato'] or 'sem estilo'}  ·  cliente: {job['cliente']}  ·  modelo: {job.get('modelo')}
FOLHAS DE QUADROS (1 quadro por segundo, o segundo escrito em cada um; abra CADA uma com o Read):
""" + "\n".join(f"  - {_comum.rel(p)}" for p in fl) + f"""
{('CENAS/PLANOS (pra ligar o segundo ao plano): ' + _comum.rel(cenas)) if cenas else ''}
CONFERÊNCIA AUTOMÁTICA JÁ FEITA: {('; '.join(avisos)) if avisos else 'nada reprovou'}
FORA DA RÉGUA DO ESTILO: {('; '.join(fora)) if fora else 'nada fora (ou o estilo não tem régua)'}
IMAGEM × FALA, JÁ MEDIDO (CLIP, não repita): {(' | '.join(a['o_que'] for a in imagens)) if imagens else 'nada fora (ou não medido)'}
REGRAS QUE O MODELO JÁ TEM (se um achado quebra uma delas, coloque o id em "regra_furou"):
{chr(10).join(regras) or '  (nenhuma)'}

O QUE PROCURAR em cada plano: {', '.join(f'{k} ({v.lower()})' for k, v in FALHAS.items() if k != 'outro')}.
Olhe os quadros de verdade. Só liste o que você VÊ ou o que a conferência acima provou. Vídeo bom = lista vazia (não invente defeito).

Escreva SÓ o arquivo {saida_json} (JSON válido, UTF-8), no formato:
{{"achados": [{{"t": <segundo do quadro mais claro do problema>, "tipo": "<uma chave de: {'|'.join(FALHAS)}>",
  "o_que": "o problema em 1 frase, direto",
  "causa": "POR QUE aconteceu e por que o Estúdio deixou passar (específico: qual passo, regra ou checagem faltou)",
  "conserto": "o que mudar pra isso não se repetir (arquivo/função/medida, 1-2 frases)",
  "mecanico": "nao|provavel|claro",   // claro = erro do motor/checador que se conserta em código; nao = depende do conteúdo deste vídeo
  "onde": "caminho de UM arquivo de código (de: {'; '.join(onde)}) onde o conserto vai, ou vazio se mecanico=nao",
  "regra_furou": "id da regra do modelo que já proibia isso, ou vazio"}}]}}
No máximo {MAX_ACHADOS} achados, os mais graves primeiro. NÃO edite nenhum outro arquivo, NÃO renderize, NÃO gere nada. Resposta final: uma linha.
"""


def _ia(prompt: str, pasta: Path):
    import ia
    pf = pasta / "revisao.prompt.txt"
    pf.write_text(prompt, encoding="utf-8")
    s = ia.para_alteracao(ia.selecao(), modelo="sonnet", esforco="medium")
    return ia.executar(prompt, pasta / "revisao-ia.log", pasta / "revisao-ia.jsonl", pasta / "revisao-ia.pid", s, tipo="revisao")


def ler_achados(arq: Path, dur: float) -> list[dict]:
    """O JSON da IA, limpo: tipo conhecido, segundo dentro do vídeo, textos curtos, no máximo MAX_ACHADOS."""
    d = ler_json(arq, None)
    lista = d.get("achados") if isinstance(d, dict) else d
    out = []
    for a in (lista if isinstance(lista, list) else []):
        if not isinstance(a, dict) or not str(a.get("o_que") or "").strip():
            continue
        try:
            t = float(a.get("t") or 0)
        except (TypeError, ValueError):
            t = 0.0
        tipo = str(a.get("tipo") or "outro")
        mec = str(a.get("mecanico") or "nao")
        out.append({"t": round(min(max(t, 0.0), max(dur - 0.1, 0.0)), 2), "tipo": tipo if tipo in FALHAS else "outro",
                    "o_que": str(a["o_que"]).strip()[:240], "causa": str(a.get("causa") or "").strip()[:400],
                    "conserto": str(a.get("conserto") or "").strip()[:400], "mecanico": mec if mec in MECANICO else "nao",
                    "onde": str(a.get("onde") or "").strip()[:200], "regra_furou": str(a.get("regra_furou") or "").strip()[:80]})
    return out[:MAX_ACHADOS]


# ───────────────────────────── histórico e repetição ─────────────────────────────

def historicos_do_estilo(pasta_aprendizado: Path | None) -> list[Path]:
    """historico.jsonl do modelo + o do MESMO modelo nos outros clientes (o estilo é o mesmo; o gosto de cada cliente não entra na conta)."""
    if not pasta_aprendizado:
        return []
    nome = pasta_aprendizado.parent.name
    out = []
    for p in _comum.RAIZ.glob("clientes/*/*Content/modelos/" + nome + "/aprendizado/historico.jsonl"):
        out.append(p)
    mine = pasta_aprendizado / "historico.jsonl"
    if mine not in out:
        out.append(mine)
    return out


def videos_com_falha(pasta_aprendizado: Path | None, tipo: str, extra_job: str = "") -> set[str]:
    jobs = {extra_job} if extra_job else set()
    for h in historicos_do_estilo(pasta_aprendizado):
        for x in ler_jsonl(h):
            if x.get("tipo") == "revisao" and x.get("chave") == tipo and x.get("job"):
                jobs.add(str(x["job"]))
    return jobs


def gravar_historico(ctx: dict, job: dict, a: dict, n: int, miniatura: str) -> bool:
    """Uma linha por achado no historico.jsonl do modelo (REGRA Nº 2, passo 4): tipo, categoria, texto, origem, createdAt, job + causa e conserto."""
    pasta = ctx["pasta_aprendizado"]
    if not pasta:
        return False
    hist = pasta / "historico.jsonl"
    jid = f"{job['cliente']}/{job['slug']}"
    for x in ler_jsonl(hist):
        if x.get("tipo") == "revisao" and x.get("job") == jid and x.get("chave") == a["tipo"] and abs(float(x.get("t") or 0) - a["t"]) < 1.5:
            return False
    append_jsonl(hist, {"tipo": "revisao", "categoria": "qa", "chave": a["tipo"], "texto": a["o_que"], "causa": a["causa"],
                        "conserto": a["conserto"], "mecanico": a["mecanico"], "t": a["t"], "regra_furou": a["regra_furou"],
                        "origem": "estudio", "createdAt": hoje(), "job": jid, "video": job.get("saida"), "miniatura": miniatura})
    return True


# ───────────────────────────── a revisão inteira ─────────────────────────────

def rodar(cli: str, slug: str) -> dict:
    import producao as P
    job = P.carregar(cli, slug)
    if not job:
        raise ValueError("vídeo não existe")
    pasta = ensure(_comum.ESTUDIO / "jobs" / cli / slug)
    res = {"estado": "rodando", "pid": os.getpid(), "iniciado_em": agora(), "cliente": cli, "slug": slug, "achados": []}
    gravar_json(arquivo(cli, slug), res)

    def fim(**kw):
        res.update(kw, fim=agora())
        res.pop("pid", None)
        gravar_json(arquivo(cli, slug), res)
        return res

    try:
        ctx = _contexto(job)
        res.update(video=_comum.rel(ctx["saida"]), video_mtime=int(ctx["saida"].stat().st_mtime), formato=ctx["formato"],
                   formato_titulo=ctx["formato_titulo"])
        gravar_json(arquivo(cli, slug), res)
        _nota(cli, slug, "Revisão do Estúdio: conferindo o vídeo…")
        qa = ensure(ctx["sandbox"] / "qa" / "revisao") if ctx["sandbox"].is_dir() else ensure(pasta / "qa")
        avisos = conferencia(job, ctx)
        fora = regua(ctx, qa / "regua")
        fl = folhas(ctx["saida"], qa)
        medidos = imagens_x_fala(ctx)
        res.update(avisos=avisos, fora_da_regua=fora, folhas=[_comum.rel(p) for p in fl])
        gravar_json(arquivo(cli, slug), res)
        achados, code = [], 0
        if _ia_ok():
            saida_json = pasta / "revisao-ia.json"
            saida_json.unlink(missing_ok=True)
            code = _ia(prompt_revisao(job, ctx, fl, avisos, fora, saida_json, medidos), pasta)
            achados = ler_achados(saida_json, float(_comum.ffprobe(ctx["saida"]).get("duracao") or 0))
        elif not medidos:
            return fim(estado="pronta", achados=[], nota="Sem motor de IA: só a conferência automática rodou.")
        if code != 0 and not achados and not medidos:
            return fim(estado="erro", erro="A revisão por IA não terminou (teto de gasto ou prazo). A conferência automática ficou valendo.")
        if int(ctx["saida"].stat().st_mtime) != res["video_mtime"]:   # o vídeo foi refeito enquanto eu olhava: este resultado é do vídeo velho
            return fim(estado="velha", achados=[], nota="O vídeo foi refeito durante a revisão; ela roda de novo no vídeo novo.")
        achados = (medidos[:3] + achados)[:MAX_ACHADOS]   # o medido vai na frente: é prova, não palpite
        jid = f"{cli}/{slug}"
        for n, a in enumerate(achados, 1):
            mini = qa / f"achado-{n}.jpg"
            a["miniatura"] = _comum.rel(mini) if quadro(ctx["saida"], a["t"], mini) else ""
            a["id"] = f"a{n}"
            a["rotulo"] = FALHAS[a["tipo"]]
            a["repetido_em"] = len(videos_com_falha(ctx["pasta_aprendizado"], a["tipo"], jid))
            a["gravado_no_historico"] = gravar_historico(ctx, job, a, n, a["miniatura"])
        for a in achados:   # depois de gravar: a contagem de vídeos já inclui este
            a["repetido_em"] = max(a["repetido_em"], len(videos_com_falha(ctx["pasta_aprendizado"], a["tipo"], jid)))
            a["melhoria"] = _propor_melhoria(job, ctx, a)
        res["achados"] = achados
        _nota(cli, slug, f"Revisão do Estúdio: {len(achados)} coisa{'s' if len(achados) != 1 else ''} pra melhorar" if achados
              else "Revisão do Estúdio: nada fora do lugar")
        _regras_acumuladas(ctx, job)
        return fim(estado="pronta")
    except Exception as e:  # noqa: BLE001
        return fim(estado="erro", erro=_comum.erro_simples(e))


def _ia_ok() -> bool:
    try:
        import ia
        return ia.disponivel()
    except Exception:  # noqa: BLE001
        return False


def _nota(cli: str, slug: str, texto: str) -> None:
    try:
        import andamento as A
        A.nota(cli, slug, texto)
    except Exception:  # noqa: BLE001
        pass


def deve_propor(a: dict) -> bool:
    """Melhoria só quando é do motor: a IA disse que é claramente do motor, ou é provável e já apareceu em 2+ vídeos."""
    return bool(a.get("onde")) and (a.get("mecanico") == "claro" or (a.get("mecanico") == "provavel" and a.get("repetido_em", 0) >= 2))


def _propor_melhoria(job: dict, ctx: dict, a: dict) -> str:
    if not deve_propor(a):
        return ""
    try:
        import melhoria
        r = melhoria.propor(job=job, ctx=ctx, achado=a)
        return r["id"] if r else ""
    except Exception as e:  # noqa: BLE001
        print("(melhoria não proposta: " + str(e) + ")", file=sys.stderr)
        return ""


def _regras_acumuladas(ctx: dict, job: dict) -> None:
    """O histórico do modelo cresceu além do limite? Propõe passar a limpo (vira regra) com o gate do OK."""
    try:
        import melhoria
        if ctx["pasta_aprendizado"]:
            melhoria.propor_regras(ctx["pasta_aprendizado"], job)
    except Exception as e:  # noqa: BLE001
        print("(regras acumuladas: " + str(e) + ")", file=sys.stderr)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rodar", "ver"])
    ap.add_argument("cliente")
    ap.add_argument("slug")
    a = ap.parse_args()
    if a.cmd == "rodar":
        r = rodar(a.cliente, a.slug)
        print(r.get("estado"), len(r.get("achados") or []), "achados")
    else:
        print(json.dumps(carregar(a.cliente, a.slug), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
