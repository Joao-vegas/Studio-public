#!/usr/bin/env python3
"""
producao — jobs de vídeo do Estúdio: sandbox + prompt + execução do Claude Code + feedback.

Um job = app/jobs/<cliente>/<slug>/job.json (+ claude.log / claude.jsonl por execução).
A sandbox fica NA PASTA DO MODELO (<modelo>/_sandbox-<slug>/), como o repo já faz hoje:
    bruto/<arquivo>      vídeo cru enviado pelo upload
    brolls/              b-rolls separados do acervo (o Claude acrescenta os que buscar)
    BRIEF.md             briefing do João + o que o Estúdio preparou
    work/, qa/           o modelo cria durante a produção

A produção NÃO é um script determinístico: cada modelo exige decisões (beats, legenda, b-roll,
QA por frames). Por isso o Estúdio dispara o Claude Code (`claude -p`) com um prompt que obriga
a ler o aprendizado do modelo (REGRA Nº 1 do CLAUDE.md) e a skill de b-roll. O feedback do João
volta pro aprendizado daquele modelo (REGRA Nº 2) — é assim que o modelo "se auto-aprende".
"""
from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import (texto_fila, RAIZ, VIDEO_EXTS, JOBS, SKILL_BROLL, agora, ffprobe, append_jsonl, claude_bin, cliente as _cliente,
                    ensure, gravar_json, hoje, ler_json, make_slug, modelo as _modelo, now_slug, rel)
import acervo as _acervo

_RODANDO: dict[str, subprocess.Popen] = {}
# Modelo usado nas execuções do Estúdio (o João pediu Opus, não Fable). ESTUDIO_MODELO=... sobrepõe.
from ia import MODELOS_CLAUDE  # noqa: E402,F401  lista única dos modelos (ia.py)


def modelo_claude() -> str:
    """Modelo das execuções: ESTUDIO_MODELO no ambiente > config.json > opus."""
    try:
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    return os.environ.get("ESTUDIO_MODELO") or cfg.get("modelo_claude") or "opus"


class _M(str):
    pass
MODELO_CLAUDE = "opus"  # compat; use modelo_claude()


# ───────────────────────── leitura ─────────────────────────

def _pasta_job(cli: str, slug: str) -> Path:
    if any(not v or Path(v).name != v or v in ('.','..') for v in (cli,slug)):
        raise ValueError('Identificador de vídeo inválido.')
    return JOBS / cli / slug


def _vivo(pid_file: Path) -> bool:
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def estimativa_etapa(tipo: str, job: dict | None = None) -> str:
    """Uma linha simples pra confirmação de etapa: quanto costuma levar (mediana das execuções que deram certo, de todos os vídeos) e
    de onde sai a conta (assinatura ou crédito da API, com o custo médio quando a API cobra). Sem histórico: "leva alguns minutos"."""
    import statistics
    mins, usd = [], []
    try:
        for j in listar():
            for e in j.get("execucoes") or []:
                if e.get("tipo") != tipo or str(e.get("exit")) != "0":
                    continue
                try:
                    t = (datetime.strptime(e["fim"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(e["inicio"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
                except Exception:
                    continue
                if 0.2 <= t <= 90:
                    mins.append(t)
                    usd.append(float(e.get("custo_usd") or 0))
    except Exception:
        pass
    if mins:
        m = statistics.median(mins)
        tempo = "leva menos de 1 min" if m < 1 else f"leva uns {round(m)} min"
    else:
        tempo = "leva alguns minutos"
    try:
        import ia
        api = ia.cobranca() == "api"
    except Exception:
        api = False
    if not api:
        conta = "sai da sua assinatura"
    else:
        med = statistics.median([u for u in usd if u] or [0])
        conta = "sai do crédito da API" + (f" (uns US$ {med:.2f}".replace(".", ",") + ")" if med else "")
    return f"{tempo} · {conta}"


def guardar_final_anterior(job: dict, motivo: str) -> str:
    """Antes de analisar ou renderizar de novo, guarda o vídeo final de agora como versão (30-out-2026: o teste da Faixa re-renderizou por cima
    do 1º final e o `versoes` ficou vazio). Mesmo esquema do editor: <sandbox>/editor/versoes/vN/{PLANO.json|cenas.json, video-vN.mp4, meta.json};
    a tela do Editar vídeo já lista. Mesmo vídeo já guardado (sha1) não repete. Cópia, nunca move nem apaga. Devolve 'vN' ou ''."""
    try:
        sb = RAIZ / job["sandbox"]
        fim = RAIZ / (job.get("saida") or "")
        if not (job.get("saida") and fim.is_file() and sb.is_dir()):
            return ""
        h = hashlib.sha1()
        with open(fim, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        sha = h.hexdigest()
        pasta = sb / "editor" / "versoes"
        nums = [int(x.name[1:]) for x in pasta.glob("v[0-9]*") if x.name[1:].isdigit()] if pasta.is_dir() else []
        for n in nums:
            if (ler_json(pasta / f"v{n}" / "meta.json", {}) or {}).get("sha1") == sha:
                return f"v{n}"
        n = max(nums + [0]) + 1
        v = ensure(pasta / f"v{n}")
        _clonar(fim, v / f"video-v{n}.mp4")
        for nome in ("PLANO.json", "cenas.json"):
            if (sb / nome).is_file():
                _clonar(sb / nome, v / nome)
                break
        gravar_json(v / "meta.json", {"o_que": motivo, "quando": datetime.now().strftime("%d/%m %H:%M"), "sha1": sha, "origem": "job"})
        job.setdefault("versoes", []).append({"versao": job.get("versao", 1), "arquivo": rel(v / f"video-v{n}.mp4"), "em": agora(), "motivo": motivo})
        return f"v{n}"
    except Exception as e:
        print(f"versão do final de {job.get('cliente')}/{job.get('slug')}: {e}", file=sys.stderr)
        return ""


def _disparar(job: dict, prompt: str, tipo: str, status_ok: str | None = None) -> None:
    import fila
    if job.get('status') in ('arquivado','exportado'):
        raise ValueError('Este vídeo já foi exportado. Crie um novo vídeo para produzir outra versão.')
    if tipo in ('analise', 'producao', 'rebusca'):
        guardar_final_anterior(job, {'producao': 'antes de renderizar de novo', 'analise': 'antes de analisar de novo'}.get(tipo, 'antes de buscar de novo'))
    from corte_qualidade import DIRETRIZES
    est = _esteira(job)   # formato com esteira: a receita manda (sem escopo essencial, teto de b-roll nem política do acervo visual)
    if est:
        atualizar_motor(job)   # o motor da sandbox sempre na versão mais nova da base (conserto chega sozinho)
    prompt += DIRETRIZES
    if not est:
        import semantica
        prompt += semantica.prompt(job) + sem_legenda_txt(job)
    c = _cliente(job['cliente'])
    if c: prompt += '\nLeia também as regras gerais do cliente: ' + str(c['content'] / 'aprendizado/regras-gerais.json') + ' (se existir).'
    prompt += camadas_de_regra(job)
    if job.get('lote'):
        prompt += '\nLote: ' + job['lote'] + '. Consulte os PLANO.json dos jobs irmãos listados em app/lotes/' + job['lote'] + '.json; pode reutilizar candidatos verificados entre vídeos, copiando para a própria sandbox. Nunca repetir URL dentro do mesmo vídeo.'
        prompt += '\nVÍDEO EM LOTE: ninguém vai responder perguntas agora. Se o COMO-FAZER manda propor opções (frase, gancho, cena...) e parar, escolha você a opção recomendada, siga até gerar o storyboard.jpg e só então peça a aprovação. O João troca a escolha olhando o storyboard.'
    prompt += "\nLIMITES DESTA EDIÇÃO: não chamar APIs de geração de imagens ou vídeos. Trabalhe com o bruto, materiais reais e composição local. Uma solicitação no briefing não autoriza geração paga. B-rolls de IA já gerados, revisados e selecionados pelo usuário no PLANO.json podem ser usados como arquivos locais. Preserve a proporção indicada na opção: encaixe horizontal em janela, vertical em tela inteira, sem esticar; respeite a composição do modelo. Descarte o áudio dos b-rolls gerados e preserve a voz do bruto. Identifique gerado_ia como ilustração, nunca como registro factual."
    import edicao as _ed
    if not est and job.get("escopo_edicao") == "essencial" and not _ed.apoio_do_job(job).get("usa"):
        prompt += "\nESCOPO ESSENCIAL (prevalece sobre políticas de busca do modelo): sem busca externa, downloads ou pesquisa de b-roll. Priorize fala, ritmo, legendas, enquadramento e materiais já anexados. Não execute etapas posteriores automaticamente."
    import edicao
    prompt += edicao.instrucao(job) if not est else edicao.instrucao_esteira(job)
    prompt += ANDAMENTO
    fila.enfileirar(job, prompt, tipo, status_ok)
    try:
        import andamento
        video = tipo in ("producao", "feedback")
        andamento.passo(job["cliente"], job["slug"], texto_fila(job["cliente"], job["slug"], "Na fila pro vídeo final" if video else "Na fila, esperando a vez"),
                        etapa="video" if video else "storyboard", titulo=job.get("titulo", ""),
                        formato=job.get("formato") or "", origem="tela")
    except Exception:
        pass


REGRA_ESTILO = ("REGRA G0: referência e exemplo são estilo, nunca molde. Deles vem ritmo, tipo de cena, enquadramento, acabamento e a régua "
                "de qualidade. Nunca vem deles roteiro, textos, falas, pessoas, logos, cores de outro cliente nem a sequência de cenas; "
                "isso vem do briefing, da fala e do cliente. PROPORÇÃO (João, 29-out-2026): ~70% do vídeo segue o fundamento das "
                "referências do estilo (o porquê de cada edição, o ritmo, as peças, o acabamento; não a cara de uma delas) e ~30% é "
                "inovação pra melhorar, tirada das críticas e do historico.jsonl dos últimos vídeos. Antes de montar, escreva no "
                "ANALISE.md o brainstorm: o que vem das referências e o que vai tentar melhorar desta vez.")

ANDAMENTO = """
ANDAMENTO (o João acompanha pela aba Em andamento do Estúdio, então isso é obrigatório): toda vez que começar um passo,
rode `python3 app/ferramentas/andamento.py passo "<o que você está fazendo agora, 3 a 8 palavras>" --etapa <preparar|storyboard|video|conferencia>`
(o vídeo já vem da variável ESTUDIO_JOB). Ex.: "Lendo as regras do formato", "Transcrevendo a fala", "Buscando b-roll da cena 3",
"Montando o storyboard", "Renderizando", "Conferindo os quadros". Storyboard pronto pra ele aprovar:
`python3 app/ferramentas/andamento.py espera "Storyboard pronto" --imagem <caminho do storyboard.jpg>`. Pronto/erro o Estúdio fecha sozinho.
"""


def camadas_de_regra(job: dict) -> str:
    """Regras em 3 camadas: geral (todo vídeo) → formato → cliente/modelo. Na briga, a mais específica ganha."""
    txt = "\nCAMADAS DE REGRA (na briga, a mais específica ganha: modelo do cliente > formato > geral):"
    geral = RAIZ / "REGRAS.md"
    if geral.exists():
        txt += f"\n- Geral: leia {rel(geral)} (vale pra todo vídeo)."
    est = None
    try:
        import formatos as _fmt
        f = _fmt.carregar(job.get("formato") or "") or _fmt.de_modelo(job.get("modelo", ""))
    except Exception:
        f = None
    if f:
        txt += f"\n- Formato \"{f['titulo']}\" (formatos/{f['slug']}/): leia COMO-FAZER.md se existir e tudo em aprendizado/."
        txt += _material_formato_txt(job, f).rstrip("\n")   # o que o João preencheu no Criar (pergunta da caixinha, tela, trecho...): sem isso a IA nunca via
        exs = f.get("exemplos") or []
        if exs:
            try:
                folha = _fmt.folha_exemplo(f["slug"], 0)
            except Exception:
                folha = None
            txt += (f" EXEMPLO PRINCIPAL (régua de estilo e de qualidade): {exs[0]['video']}"
                    + (f"; olhe a folha {rel(folha)} (1 quadro a cada 4 s) antes de planejar" if folha else " (extraia frames pra conferir o estilo)")
                    + " pra pegar ritmo, tipos de cena e acabamento; o conteúdo vem desta fala e deste cliente, nunca do exemplo."
                    " O vídeo novo não sai pior que ele. " + REGRA_ESTILO)
            if len(exs) > 1:
                txt += " Outros exemplos aprovados: " + ", ".join(e["video"] for e in exs[1:]) + "."
        est = _fmt.esteira(f)
        sb = job.get("sandbox") or "<sandbox>"
        saida_conf = str(RAIZ / job["saida_esperada"]) if job.get("saida_esperada") else ""
        como = (f"rode `{_fmt.comando(est, 'storyboard', sb)}` (o storyboard do formato)" if est and est.get("tipo") == "gravado" else
                f"formato com esteira: use o comando do motor (`{_fmt.comando(est, 'storyboard', sb)}`)" if est else
                f"rode `python3 app/ferramentas/storyboard.py {sb}` (o motor do formato pode ter o próprio storyboard)")
        txt += (" STORYBOARD PRIMEIRO: na etapa de análise/plano, o storyboard.jpg da sandbox (um quadro por cena, com a fala)"
                f" sai por ferramenta: {como}; nunca desenhe storyboard com script próprio. Depois PARE pra o João aprovar."
                " Só renderize o vídeo final na etapa de produção.")
        if est and est.get("tipo") == "gravado":   # vídeo gravado: a tela é a de sempre, mas os passos são os DO FORMATO
            txt += (f"\n- PASSOS DO FORMATO (siga na ordem, dentro deste fluxo; a parada pra aprovação é "
                    f"\"{est['etapas'][est['parada']]['titulo']}\"):")
            for i, e in enumerate(est["etapas"], 1):
                c = f" Comando: `{_fmt.na_sandbox(str(e['comando']), sb)}`" if e.get("comando") else ""
                txt += f"\n   {i}) {e['titulo']}: {e['faz']}{c}"
            if est["comandos"].get("render"):
                txt += f"\n   Render do formato: `{_fmt.comando(est, 'render', sb)}`."
            if est["comandos"].get("conferir"):
                txt += f"\n   Conferência do formato: `{_fmt.comando(est, 'conferir', sb, saida_conf)}` (só entrega com exit 0)."
            som = [f"{o_que}: {est[k + '_de_onde'] if est[k] else 'não usa'}" for k, o_que in (("musica", "música"), ("efeitos", "efeitos"))
                   if est[k + "_de_onde"] or not est[k]]
            if som:   # o que o formato declara em "som" (manda sobre a busca padrão de música e efeito)
                txt += "\n   Som do formato: " + " · ".join(som) + "."
            txt += (f"\n   Caminhos: os comandos sem <sandbox> rodam de DENTRO da sandbox ({sb}), então ../x é o arquivo x do "
                    f"modelo; a saída final vai em caminho absoluto ({RAIZ}/<saída do vídeo>), nunca relativo à raiz.")
        _refs = [r for r in (job.get("estilo_refs") or []) if isinstance(r, dict)]
        _mistura = sorted({r["formato"] for r in _refs if r.get("formato") and r["formato"] != f["slug"]})   # "Misturar com outro estilo" do Criar
        if len(_refs) > 1 or _mistura:   # pesos escolhidos no Criar (ex.: 50 · 30 · 20)
            _caminho = lambda r: (getattr(_fmt, "ref_caminho", lambda *_: None)(r.get("formato") or f["slug"], r["nome"])
                                  or f"formatos/{r.get('formato') or f['slug']}/estudos/{r['nome']}") + "/"
            txt += " REFERÊNCIAS DESTE VÍDEO COM PESO (o fundamento vem delas nessa proporção, ~70% do vídeo; ~30% é melhoria vinda do historico.jsonl): " + "; ".join(
                f"{r['peso']}% {_caminho(r).rstrip('/')}" + (f" (estilo {r['formato']})" if r.get("formato") and r["formato"] != f["slug"] else "") for r in _refs) + ". Nunca copie cena por cena nem a fala."
            if _mistura:
                _tit = {x: (_fmt.carregar(x) or {}).get("titulo", x) for x in _mistura}
                txt += (f" MISTURA DE ESTILOS (escolha do João): este vídeo é do estilo \"{f['titulo']}\" com um pouco de " + ", ".join(f'\"{_tit[x]}\"' for x in _mistura)
                        + ". O motor, as peças e a esteira são os do " + f"\"{f['titulo']}\"" + "; do(s) outro(s) estilo(s) leia o COMO-FAZER.md e olhe as referências acima e traga o FUNDAMENTO"
                        " (por que a edição funciona: ritmo, divisão de tela, tipo de gancho, jeito da frase e da legenda) na proporção dos pesos, só no que o motor do "
                        f"\"{f['titulo']}\" sabe fazer. É mistura de ideias, não colagem de cenas: nunca copie cena por cena, a fala nem a cara do outro estilo.")
        _esc = _fmt.estudo_escolhido(f["slug"], job.get("estilo_ref", "")) if getattr(_fmt, "estudo_escolhido", None) and len(_refs) <= 1 and not _mistura else None
        if _esc:   # o João escolheu no Criar qual referência este vídeo segue: ela manda sobre a principal
            _pq = f"formatos/{f['slug']}/estudos/{_esc['nome']}"
            txt += (f" REFERÊNCIA ESCOLHIDA PRA ESTE VÍDEO: {_pq}/ (vídeo {(_esc['videos'] or ['-'])[0]}"
                    + (f", régua {_pq}/estudo-quadros/ESTUDO-QUADROS.md" if (RAIZ / _pq / "estudo-quadros" / "ESTUDO-QUADROS.md").is_file() else "")
                    + "). Ela é a base da edição deste vídeo no lugar do exemplo principal: pegue o jeito (ritmo, peças, acabamento),"
                    " adapte ao roteiro e nunca copie cena por cena nem a fala.")
        if (f["pasta"] / "estudos").is_dir():
            txt += f" Estudos de referência (ideias de estilo, não molde; olhe os storyboards e ESTUDO.md): formatos/{f['slug']}/estudos/."
        for _d in sorted((f["pasta"] / "estudos").glob("*/PRINCIPAL")):   # estilo confirmado na referência rápida
            if (_d.parent / "estilo.json").is_file():
                txt += (f" Estilo principal deste formato: {_d.parent.relative_to(RAIZ)}/estilo.json (legenda, cores, gancho, ritmo medidos da referência). "
                        "É ideia de estilo, não molde: siga o jeito, nunca copie a fala nem o roteiro dela.")
                break
        if _fmt.estudo_txt(f["slug"]):   # a referência estudada UMA vez (formatos.py referencia): lê em vez de reestudar
            txt += " " + _fmt.estudo_txt(f["slug"])
        if getattr(_fmt, "estudo_quadros_txt", None) and _fmt.estudo_quadros_txt(f["slug"]):   # régua medida quadro a quadro
            txt += " " + _fmt.estudo_quadros_txt(f["slug"])
        for _d in sorted((f["pasta"] / "estudos").glob("*/PRINCIPAL")):   # estudo da referência rápida com a régua junto
            if (_d.parent / "estudo-quadros" / "ESTUDO-QUADROS.md").is_file():
                txt += (f" Régua do estilo principal: {_d.parent.relative_to(RAIZ)}/estudo-quadros/ESTUDO-QUADROS.md "
                        "(números medidos quadro a quadro; siga o jeito, nunca o conteúdo).")
                break
    cli = _cliente(job.get("cliente", ""))
    if cli and (cli["pasta"] / "identidade.json").exists():
        # o Cliente4 saiu dourado e vermelho (o padrão do motor) com a cor dele já no identidade.json: "usa a cor dele"
        txt += (f"\n- Cliente: a cara dele (cores, fontes, tom) está em {rel(cli['pasta'] / 'identidade.json')} e vale em qualquer "
                "formato: a cor do vídeo é a dele (\"papeis\": destaque, dor, empresa_lideranca, fundo, texto), nunca o padrão do motor.")
        if est and _fmt.motor_padrao(est):
            txt += (" O motor deste formato já lê essas cores sozinho: não ponha \"cores\" no cenas.json (o --storyboard reprova "
                    "cor que contradiz a identidade); palavra de empresa/liderança vai em \"empresa\".")
    ent = job.get("entrada", "video")
    voz = ((_fmt.esteira(f) or {}).get("voz") if f else None) or "narracao"
    if ent == "roteiro" and voz == "sem":
        txt += (f"\nENTRADA = ROTEIRO (não há vídeo gravado): o texto está em {job['bruto']}. Este formato não tem narração: "
                "o roteiro vira texto de tela e nenhuma voz é gerada. Monte o vídeo seguindo o formato.")
    elif ent == "roteiro" and voz == "motor":
        txt += (f"\nENTRADA = ROTEIRO (não há vídeo gravado): o texto está em {job['bruto']}. A voz sai do próprio motor do "
                "formato (nos comandos da esteira), não do narracao_tts.py. Monte o vídeo seguindo o formato.")
    elif ent == "roteiro":
        txt += (f"\nENTRADA = ROTEIRO (não há vídeo gravado): o texto está em {job['bruto']}. Gere a narração pelo motor de voz "
                "configurado (app/ferramentas/motion/narracao_tts.py: VoiceStudio, grátis e local, é o padrão; reserva ElevenLabs só com chave e voz; VoiceStudio fechado e sem reserva = erro, avise o João"
                + (f"; voz escolhida pro vídeo: passe --voz {job['voz']}" if job.get("voz") else "")
                + "; leva uns minutos, avise no Em andamento) e monte o vídeo seguindo o formato.")
    elif ent == "filmagem":
        txt += "\nENTRADA = FILMAGEM (vários vídeos do mesmo evento): " + ", ".join([job["bruto"]] + job.get("brutos_extras", [])) + "."
    return txt + "\n"


# ───────────────────────── esteira: a receita do formato manda ─────────────────────────
# Formato com "esteira" no formato.json roda os passos DELE, na ordem, e para só onde ele manda aprovar.
# Sem pipeline genérico de b-roll, sem teto de b-roll e sem "mantenha o bruto": b-roll é só um tipo de cena do motor.

def _esteira(job: dict) -> dict | None:
    try:
        import formatos as _fmt
        return _fmt.esteira_do_job(job)
    except Exception:
        return None


_ESQ_MUSICA = """{"opcoes": [{"id": "m1", "arquivo": "work/musica/faixa.mp3", "inicio_s": 0, "fim_s": 60,
                         "fonte": "motor|do-cliente|acervo|mixkit", "motivo": "por que o clima casa com a fala",
                         "trechos": [{"arquivo": "audio/musicas/364.mp3", "inicio_s": 0, "de": 0},
                                     {"arquivo": "audio/musicas/1154.mp3", "inicio_s": 0, "de": 76.96}]}],
             "escolha": "m1"}"""
_ESQ_SFX = """[{"id": "whoosh-short", "som": "whoosh-short", "titulo": "Passagem quando muda o fundo", "arquivo": "audio/sfx/whoosh-short.mp3", "motivo": "toca quando o fundo muda (papel claro ↔ escuro)", "ligado": true}]"""


def _esquema_esteira(est: dict | None = None) -> str:
    """O PLANO.json mínimo da esteira. Formato sem música ou sem efeitos (som.*.usa = false) vai sem faixa e sem efeito."""
    est = est or {}
    musica = _ESQ_MUSICA if est.get("musica", True) else '{"sem": true, "escolha": {"sem": true}, "opcoes": []}'
    sfx, ligado = (_ESQ_SFX, "true") if est.get("efeitos", True) else ("[]", "false")
    return f"""{{
  "resumo": "1-2 frases: o que o vídeo fala e o ângulo",
  "transcricao": [{{"t0": 0.0, "t1": 3.2, "texto": "trecho da fala"}}],
  "musica": {musica},
  "sfx": {sfx},
  "sfx_ligado": {ligado},
  "beats": [],
  "cenas": "{est.get('cenas') or 'cenas.json'}",
  "storyboard": "storyboard.jpg"
}}"""


ESQUEMA_ESTEIRA = _esquema_esteira()


MOTOR_PADRAO = ["render.py", "index.html"]


def _copiar_motor(src: Path, dst: Path, itens: list[str], manter: tuple[str, ...] = ()) -> list[str]:
    """Copia os arquivos do motor (itens: arquivos ou pastas, relativos) de src pra dst quando o de src é mais novo ou
    falta em dst (como rsync -u): o que é do vídeo (cenas.json, PLANO.json, work/, qa/...) nunca entra na lista.
    `manter`: arquivos que, se já existem em dst, nunca são trocados (o arquivo do vídeo do formato, ex.: o index.html
    de formato que é motor E cenas do vídeo: o conserto da base apagaria o vídeo em andamento)."""
    feitos = []
    for item in itens:
        o = src / item
        arqs = [o] if o.is_file() else ([p for p in sorted(o.rglob("*")) if p.is_file()] if o.is_dir() else [])
        for a in arqs:
            r = a.relative_to(src)
            if "__pycache__" in r.parts or a.suffix == ".pyc" or a.name.startswith("."):
                continue
            alvo = dst / r
            if alvo.exists() and r.as_posix() in manter:
                continue
            if alvo.exists() and (alvo.stat().st_mtime >= a.stat().st_mtime or filecmp.cmp(a, alvo, shallow=False)):
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a, alvo)
            feitos.append(str(r))
    return feitos


def atualizar_motor(job: dict) -> dict:
    """O motor de um formato com esteira é do FORMATO: conserto na base chega sozinho na cópia do cliente e na sandbox.
    Antes a sandbox guardava o render.py do dia em que foi criada (rsync --ignore-existing) e o Vídeo 1 V2 do Cliente4
    saiu com o storyboard antigo ("D▌", "BARG▌") depois do motor já consertado. Base → modelo do cliente → sandbox,
    só os arquivos do motor (formato.json → esteira.motor_arquivos) e só quando o de cima é mais novo.
    O que é do cliente vai no cenas.json (cores, estilo) e nas regras, nunca no motor. Nunca levanta erro.
    esteira.copiar_motor = false: o motor roda da base, nada é copiado. O arquivo do vídeo (esteira.cenas)
    que já está na sandbox nunca é trocado."""
    out = {"modelo": [], "sandbox": []}
    try:
        import formatos as _fmt
        est = _esteira(job)
        f = _fmt.carregar(est["slug"]) if est else None
        if not f or not est.get("copiar_motor", True):
            return out
        itens = (f.get("esteira") or {}).get("motor_arquivos") if isinstance(f.get("esteira"), dict) else None
        itens = [str(x) for x in (itens or MOTOR_PADRAO) if str(x).strip() and ".." not in str(x)]
        base = f["pasta"] / "base"
        cli = _cliente(job["cliente"])
        mod = _modelo(cli, job["modelo"]) if cli else None
        if mod and mod["pasta"].is_dir() and base.is_dir():
            out["modelo"] = _copiar_motor(base, mod["pasta"], itens)
        sb = RAIZ / job["sandbox"]
        if mod and sb.is_dir():
            out["sandbox"] = _copiar_motor(mod["pasta"], sb, itens, manter=(est.get("cenas") or "cenas.json",))
    except Exception as e:
        print(f"motor de {job.get('cliente')}/{job.get('slug')}: {e}", file=sys.stderr)
    return out


def _local_da_opcao(job: dict, beat: dict, op: dict) -> Path | None:
    """Arquivo local de uma opção de b-roll: o "arquivo" dela, o corte final ou o vídeo-fonte baixado (work/src/<id do YouTube>)."""
    achado = arquivo_da_opcao(job, beat, op)
    if achado:
        return achado
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})", str(op.get("url") or ""))
    if m:
        for p in sorted((RAIZ / job["sandbox"] / "work" / "src").glob(m.group(1) + ".*")):
            if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
                return p
    return None


def brolls_escolhidos(cliente: str, ignorar: str = "", limite: int = 12) -> list[dict]:
    """Cenas que o João já escolheu nos outros vídeos deste cliente (PLANO.json → beat.escolha): podem voltar quando a
    fala casar (o Vídeo 1 V2 do Cliente4 refez a mesma fala e não reusou nenhuma das 4 que ele aprovou no V1)."""
    out, vistos = [], set()
    for j in listar(cliente):
        if j.get("slug") == ignorar:
            continue
        for b in (plano(j) or {}).get("beats") or []:
            esc = b.get("escolha")
            op = next((o for o in b.get("opcoes") or [] if isinstance(o, dict) and o.get("id") == esc), None)
            chave = op and (op.get("url") or op.get("titulo"))
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            arq = _local_da_opcao(j, b, op)
            out.append({"titulo": op.get("titulo") or "", "url": op.get("url") or "", "trecho": op.get("trecho") or "",
                        "fala": b.get("fala") or "", "arquivo": rel(arq) if arq else "", "video": j.get("titulo") or j.get("slug")})
            if len(out) >= limite:
                return out
    return out


def _brolls_escolhidos_txt(job: dict) -> str:
    itens = brolls_escolhidos(job["cliente"], ignorar=job["slug"])
    if not itens:
        return ""
    linhas = ["CENAS QUE O JOÃO JÁ ESCOLHEU PRA ESTE CLIENTE (voltam como cena de fora quando a fala casar; olhe os quadros e "
              "copie o trecho pra brolls/ da sandbox antes de usar):"]
    for it in itens:
        onde = it["arquivo"] or it["url"]
        linhas.append(f"  - {it['titulo']} · {onde}" + (f" (trecho {it['trecho']} s)" if it["trecho"] else "")
                      + (f" · fala: \"{it['fala'][:80]}\"" if it["fala"] else "") + f" · {it['video']}")
    return "\n".join(linhas) + "\n"


def _base_esteira(job: dict) -> str:
    """Pasta base do formato do job (onde ficam as músicas e a demo/ que a sandbox não copia)."""
    try:
        import formatos as _fmt
        slug = (_esteira(job) or {}).get("slug") or ""
        f = _fmt.carregar(slug) or {}
        return f.get("base") or (f"formatos/{slug}/base" if slug else "")
    except Exception:
        return ""


def _musica_esteira(job: dict, base: str | None = None, est: dict | None = None) -> str:
    est = _esteira(job) if est is None else est
    if est and not est.get("musica", True):
        return ("MÚSICA: este formato não usa música (formato.json → som.musica.usa = false). Não busque nem proponha faixa; "
                "no PLANO.json, \"musica\": {\"sem\": true, \"escolha\": {\"sem\": true}, \"opcoes\": []}.\n")
    sb = job["sandbox"]
    base = _base_esteira(job) if base is None else base
    padrao = not est or est.get("cenas", "cenas.json") == "cenas.json"
    # as faixas não vão pra sandbox (154 MB por vídeo): o render acha "audio/musicas/<n>.mp3" na base do formato
    tem_catalogo = bool(base) and (RAIZ / base / "audio" / "catalogo.json").is_file()   # formato novo não tem: não mande procurar
    if not base:
        catalogo = "o catálogo audio/ do motor e "
    elif tem_catalogo and padrao:
        catalogo = (f"o catálogo do formato ({base}/audio/catalogo.json; as faixas ficam em {base}/audio/musicas/ e no cenas.json "
                    f"entram como \"audio/musicas/<n>.mp3\") e ")
    elif tem_catalogo:
        catalogo = f"o catálogo do formato ({base}/audio/catalogo.json) e "
    else:
        catalogo = ""
    diz = (est or {}).get("musica_de_onde") or ""
    return f"""MÚSICA (todo vídeo deste formato tem música; o João não precisa pedir), nesta ordem:
""" + (f"  O FORMATO DIZ (manda sobre a lista): {diz}\n" if diz else "") + f"""  0) {catalogo}as faixas do cliente: python3 app/ferramentas/musica_busca.py do-cliente "{job['cliente']}" (só deste cliente);
  1) o acervo (acervo/itens/*/meta.json, tipo musica);
  2) Mixkit: python3 app/ferramentas/musica_busca.py buscar "<clima em inglês>" --fonte mixkit (veja as opções e baixe as escolhidas pra {sb}/work/musica/).
  Nunca repita faixa listada por python3 app/ferramentas/musica_busca.py recentes "{job['cliente']}" --ignorar "{job['slug']}".
  Faixa sem melodia (drone, pad, ambiente parado) é reprovada. Freesound é só pra efeito sonoro, nunca pra música.
"""


ENTRADA_ROTEIRO = {
    "narracao": "(sem vídeo gravado: a voz sai do motor de voz configurado, app/ferramentas/motion/narracao_tts.py)",
    "motor": "(sem vídeo gravado: a voz sai do próprio motor do formato, nos comandos da esteira; não use o narracao_tts.py)",
    "sem": "(sem vídeo gravado e sem narração: o roteiro vira texto de tela; nenhuma voz é gerada)",
}


def _preencher(c: str, dentro: bool = False) -> str:
    """Comando com marcador que só a IA sabe preencher (<tempos>, <fim>, <id>): avisa em vez de deixar passar calado.
    dentro=True: o aviso entra num parêntese que já existe."""
    if not re.search(r"<[^<>\s]+[^<>]*>", c):
        return ""
    aviso = "o que estiver entre < > no comando você preenche pela receita"
    return f"; {aviso}" if dentro else f" ({aviso})"


def _marca_som(job: dict, f: dict, sb: str) -> None:
    """A escolha dele no Criar vira ARQUIVO na sandbox (o motor lê, não depende da IA lembrar): work/musica/sem e work/efeitos/sem."""
    try:
        base = Path(sb) if Path(sb).is_absolute() else RAIZ / sb
        if (job.get("musica") or {}).get("modo") == "sem":
            (base / "work" / "musica").mkdir(parents=True, exist_ok=True)
            (base / "work" / "musica" / "sem").touch()
        if (job.get("efeitos") or {}).get("modo") == "sem":
            (base / "work" / "efeitos").mkdir(parents=True, exist_ok=True)
            (base / "work" / "efeitos" / "sem").touch()
    except OSError:
        pass


def _musica_escolha_txt(job: dict, f: dict, sb: str) -> str:
    """"Música de fundo" nos estilos que não são o Editorial (Documentário e gravados com música): o João escolheu no Criar (job["musica"]).
    O render do estilo lê work/musica/escolhida.json (faixa) ou work/musica/sem (nada) sozinho; aqui a IA só prepara a faixa."""
    _marca_som(job, f, sb)
    esc = job.get("musica") or {}
    if esc.get("modo") == "sem":
        return ("MÚSICA DE FUNDO (escolha dele no Criar): SEM MÚSICA. O arquivo work/musica/sem já existe: o render não toca música. "
                "No PLANO.json/cenas.json, \"musica\": null (sem).\n")
    padrao_ = ((ler_json(RAIZ / "clientes" / job["cliente"] / "identidade.json", {}) or {}).get("musica_padrao") or {})
    if esc.get("modo") == "viral" and not esc.get("faixa") and padrao_.get("faixa"):   # música da marca do cliente (João, 05-nov-2026): só sai dela se ele escolher outra faixa
        esc = dict(esc, faixa=padrao_["faixa"], titulo=padrao_.get("titulo", ""), nivelar=bool(padrao_.get("nivelar")))
    if esc.get("faixa"):
        return (f"MÚSICA DE FUNDO (escolha dele no Criar): a faixa \"{esc.get('titulo') or esc['faixa']}\". Antes de renderizar rode (da raiz do Estúdio) "
                f"`app/.venv/bin/python app/ferramentas/musica_viral.py escolher {sb} --faixa \"{esc['faixa']}\" --dur <duração do vídeo em s> --cliente {job['cliente']}{' --nivelar' if esc.get('nivelar') else ''}`: "
                "ela corta o refrão, confere marca d'água e grava work/musica/escolhida.json, que o render usa sozinho (volume baixo sob a voz, ducking). "
                "Não escolha outra faixa e não baixe música de banco.\n")
    if esc.get("modo") == "viral":
        return ("MÚSICA DE FUNDO: ele quer música e deixou o Estúdio escolher. Rode `app/.venv/bin/python app/ferramentas/musica_viral.py escolher "
                f"{sb} --dur <duração do vídeo em s> --cliente {job['cliente']} --formato {f.get('slug', '')} --texto \"<a fala>\"`: escolhe uma faixa SEM voz cantada pelo clima, "
                "grava work/musica/escolhida.json e o render usa sozinho.\n")
    return ""


def _efeitos_escolha_txt(job: dict, f: dict, sb: str) -> str:
    """"Efeitos sonoros" ligados/desligados (job["efeitos"]). Desligados: work/efeitos/sem existe e o render não toca nenhum."""
    if not (((f.get("som") or {}).get("efeitos") or {}).get("usa")):
        return ""
    _marca_som(job, f, sb)
    if (job.get("efeitos") or {}).get("modo") == "sem":
        return ("EFEITOS SONOROS (escolha dele no Criar): DESLIGADOS. O arquivo work/efeitos/sem já existe: o render não toca efeito nenhum. "
                "No cenas.json, \"efeitos\": false.\n")
    return ""


def _musica_viral_base(job: dict, f: dict, sb: str) -> str:
    """A música de fundo do estilo que usa VIRAIS (formato.json → som.musica.viral): o que o João escolheu no Criar (job["musica"]).
    Padrão viral: o `g.fechar` do gera_lib já escolhe sozinho (viral do momento, conferida contra marca d'água); banco de trilha só sem internet."""
    mus = ((f.get("som") or {}).get("musica") or {})
    if not (mus.get("viral") or mus.get("escolha_na_tela")):
        return _efeitos_escolha_txt(job, f, sb)
    if not mus.get("viral"):   # Documentário e gravados com música: o motor (render) lê work/musica/ sozinho
        return _musica_escolha_txt(job, f, sb) + _efeitos_escolha_txt(job, f, sb)
    esc = job.get("musica") or {}
    padrao_ = ((ler_json(RAIZ / "clientes" / job["cliente"] / "identidade.json", {}) or {}).get("musica_padrao") or {})
    if esc.get("modo") != "sem" and not esc.get("faixa") and padrao_.get("faixa"):   # música padrão do cliente (João, 05-nov-2026)
        esc = dict(esc, faixa=padrao_["faixa"], titulo=padrao_.get("titulo", ""), nivelar=bool(padrao_.get("nivelar")))
    if esc.get("modo") == "sem":
        return (f"MÚSICA DE FUNDO (escolha dele no Criar): SEM MÚSICA. Crie o arquivo vazio {sb}/work/musica/sem (mkdir -p e touch) antes do "
                "gera.py: o g.fechar sai sem música, sem batida e sem corte na batida.\n")
    base = ("MÚSICA DE FUNDO: VIRAL DO MOMENTO (o que está bombando hoje no Brasil e no mundo), NUNCA banco de trilha nem música clichê. "
            "O g.fechar do gera_lib já escolhe sozinho (musica=\"auto\", o padrão: não passe `musica=`), corta o refrão/drop, confere marca d'água e faz a "
            "grade da batida. ")
    if esc.get("faixa"):
        return (base + f"O João JÁ ESCOLHEU a faixa \"{esc.get('titulo') or esc['faixa']}\": antes do gera.py rode (de dentro da raiz do Estúdio) "
                f"`app/.venv/bin/python app/ferramentas/musica_viral.py escolher {sb} --faixa \"{esc['faixa']}\" --dur <fim da última palavra do words.json + 0,8> "
                f"--cliente {job['cliente']}{' --nivelar' if esc.get('nivelar') else ''}`; ela grava work/musica/escolhida.json e o gera.py usa. Reprovada na checagem = o comando diz o motivo: escolha a próxima "
                "das 3 opções e avise no Em andamento. A faixa é música famosa: o Instagram pode silenciar se não for a do app (diga isso no fim).\n")
    return (base + "Se quiser ver as 3 opções antes: `app/.venv/bin/python app/ferramentas/musica_viral.py opcoes --formato editorial --cliente "
            f"{job['cliente']} --texto \"<a fala>\"`. A faixa é música famosa: o Instagram pode silenciar se não for a do app (diga isso no fim).\n")


def _musica_viral_txt(job: dict, f: dict, sb: str) -> str:
    """Música (viral no Editorial; escolha na tela nos outros) + a escolha de efeitos sonoros, em texto pro pedido à IA."""
    txt = _musica_viral_base(job, f, sb)
    if (((f.get("som") or {}).get("musica") or {}).get("viral")):
        txt += _efeitos_escolha_txt(job, f, sb)
    return txt


def _o_que_o_exemplo_tem(com_musica: bool, com_efeitos: bool) -> str:
    """O que o vídeo novo iguala em variedade (não em conteúdo): só cita música e efeitos se o formato usa (formato sem música e sem efeito não cita)."""
    itens = ["cenas"] + [x for x, ok in (("música", com_musica), ("efeitos", com_efeitos)) if ok]
    return ", ".join(itens[:-1]) + " e " + itens[-1] if len(itens) > 1 else itens[0]


def cenas_citadas(pedido: str) -> str:
    """Cenas que o João citou no pedido, pelo número ("cena 7", "quadros 3 e 4") ou pelo tempo ("0:12", "aos 12 s")."""
    nums, tempos = [], []
    for m in re.finditer(r"\b(?:cenas?|quadros?|beats?)\s+((?:\d+(?:\s*(?:,|e|a|-)\s*)?)+)", pedido, re.I):
        nums += re.findall(r"\d+", m.group(1))
    tempos += re.findall(r"\b\d{1,2}:\d{2}\b", pedido)
    tempos += [f"{x} s" for x in re.findall(r"\b(\d{1,3})\s*(?:s\b|seg)", pedido, re.I)]
    partes = ([("cena " if len(nums) == 1 else "cenas ") + ", ".join(dict.fromkeys(nums))] if nums else []) + list(dict.fromkeys(tempos))
    return "; ".join(partes)


# ───────────────────────── briefing do passo 0: o pedido deste vídeo ─────────────────────────

def briefing_do_job(job: dict) -> dict | None:
    """O briefing fechado na conversa do passo 0: briefing.json na pasta do vídeo (app/jobs/<cliente>/<slug>/) ou o
    rascunho da conversa (app/briefings/<briefing_id>/). Sem nenhum: None (vale só o briefing escrito no Criar)."""
    arqs = []
    try:
        arqs.append(_pasta_job(job.get("cliente") or "", job.get("slug") or "") / "briefing.json")
    except ValueError:
        pass
    bid = str(job.get("briefing_id") or "")
    if bid and Path(bid).name == bid and bid not in (".", ".."):
        arqs.append(JOBS.parent / "briefings" / bid / "briefing.json")
    for a in arqs:
        b = ler_json(a, None) if a.is_file() else None
        if isinstance(b, dict) and any(b.values()):
            return b
    return None


def _curto(v, n: int = 600) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def sem_legenda_txt(job: dict) -> str:
    """A linha SEM LEGENDA do pedido à IA (vazia com a legenda ligada ou num formato que não desliga). Legenda = a fala escrita
    sincronizada com o áudio; manchete, card, faixa e o texto que é o conteúdo do formato ficam. O formato diz o "como"."""
    if job.get("legenda") is not False:
        return ""
    import formatos as _fmt
    slug = (_esteira(job) or {}).get("slug") or job.get("formato") or ""
    como = ""
    if slug:
        leg = _fmt.legenda_do(_fmt.carregar(slug))
        if not leg["desligavel"]:
            return ""
        como = f" Como desligar neste formato: {leg['como']}."
    return ("\nSEM LEGENDA: não queime nem gere legenda neste vídeo (o João vai usá-lo em outro formato). Legenda é só a fala escrita "
            "sincronizada com o áudio: manchetes, cards, faixas, textos de tela e o texto que é o conteúdo do formato continuam."
            + como + " O storyboard e a conferência NÃO cobram legenda: legenda ausente não é falha, e os testes de legenda "
            "(abaixo do queixo, casando com a fala, fixa) ficam de fora.\n")


def secao_briefing(job: dict) -> str:
    """A seção BRIEFING DESTE VÍDEO do pedido à IA (vazia sem briefing.json). Vai antes das regras: é o pedido deste
    vídeo e ganha dos padrões, mas não muda regra de ninguém (peculiaridade não vira regra sem "aprenda isso")."""
    b = briefing_do_job(job)
    if not b:
        return ""
    L = ["", "BRIEFING DESTE VÍDEO (fechado com o João no passo 0; vale SÓ pra este vídeo):"]
    if b.get("objetivo"):
        L.append(f"   Objetivo: {_curto(b['objetivo'])}")
    if b.get("peculiaridade"):
        L.append(f"   Peculiaridade do pedido: {_curto(b['peculiaridade'])}")
    if b.get("roteiro") and job.get("entrada") != "roteiro":   # roteiro de entrada já está no roteiro.txt
        L.append(f"   Roteiro: {_curto(b['roteiro'], 1500)}")
    mats = [m for m in b.get("material_liberado") or [] if isinstance(m, dict) and m.get("arquivo")]
    if mats:
        L.append("   Material liberado (use no papel e no lugar marcados; o que não estiver em material/ vem da pasta ligada):")
        for m in mats[:20]:
            pasta = f"{_curto(m.get('pasta'), 80)}/" if m.get("pasta") else ""
            onde = f", {_curto(m.get('onde'), 120)}" if m.get("onde") else ""
            L.append(f"   - {pasta}{_curto(m['arquivo'], 300)} → {_curto(m.get('papel'), 40) or 'sem papel'}{onde}")
    ref = b.get("referencia") if isinstance(b.get("referencia"), dict) else {}
    if ref.get("video"):
        seg = (f" no segundo {ref['segundo']:.1f} s".replace(".", ",")
               if isinstance(ref.get("segundo"), (int, float)) and not isinstance(ref.get("segundo"), bool) else "")
        L.append(f"   Referência: {_curto(ref['video'], 300)}{seg}: estilo a aproveitar: {_curto(ref.get('o_que_copiar')) or 'o jeito dela'}"
                 " (só estilo: roteiro, textos, pessoas e cenas vêm deste briefing; extraia os quadros desse trecho antes de planejar"
                 " e diga no ANALISE.md o estilo aproveitado).")
    proibido = [_curto(x, 120) for x in (b.get("proibido") or []) if str(x).strip()]
    if proibido:
        L.append("   Proibido neste vídeo: " + "; ".join(proibido) + ".")
    abertas = [_curto(x, 200) for x in (b.get("perguntas_abertas") or []) if str(x).strip()]
    if abertas:
        L.append("   Ficou em aberto (decida pelo mais simples e diga no ANALISE.md o que assumiu): " + "; ".join(abertas))
    if b.get("descartavel"):
        L.append("   Vídeo de teste (descartável): não vira exemplo do formato.")
    try:
        import formatos as _fmt
        f = _fmt.carregar(job.get("formato") or "") or _fmt.de_modelo(job.get("modelo", ""))
        fora = _fmt.material_fora(b, f) if f else []
    except Exception:
        fora = []
    if fora:
        L.append("   O formato não tem lugar pra: " + "; ".join(f"{m['arquivo']} ({m.get('papel') or 'sem papel'})" for m in fora)
                 + ". Não force: use do jeito que o formato sabe ou deixe de fora, e diga no ANALISE.md.")
    L += ["   Prioridade: atenda cada ponto (ganha dos padrões). Na briga com regra escrita, a ordem é modelo do cliente >"
          " formato > geral: não force, diga no ANALISE.md.",
          "   O briefing vale só pra este vídeo e NÃO vira regra: nada dele (nem a peculiaridade) vai pro historico.jsonl nem"
          " pros regras.json. A REGRA Nº 2 só vale se o João disser \"aprenda isso\"."]
    return "\n".join(L)


# ───────────────────────── referência que obriga: registrada no ANALISE.md e conferida ─────────────────────────

SECAO_REFERENCIA = "Referência analisada"
_REF_NO_TEXTO = re.compile(r"REFERÊNCIA DESTE VÍDEO(?: \(link\))?: (.+?)(?=, no segundo|\. |\.?$)", re.M)


def referencia_do_job(job: dict) -> dict | None:
    """A referência deste vídeo: a linha "REFERÊNCIA DESTE VÍDEO" que o Criar escreve no briefing (com o "layout" que a
    conversa marcou) ou, sem ela, a do briefing do passo 0. None se o João não mandou nenhuma (ou tirou no Criar)."""
    bs = [b for b in (briefing_do_job(job), job.get("briefing_conversa")) if isinstance(b, dict)]
    rb = next((b["referencia"] for b in bs if isinstance(b.get("referencia"), dict)
               and str(b["referencia"].get("video") or "").strip()), None)
    txt = str(job.get("briefing") or "")
    m = _REF_NO_TEXTO.search(txt)
    if m:
        linha = txt[m.start():].splitlines()[0]
        seg = re.search(r", no segundo ([\d.,]+)", linha)
        copiar = re.search(r"(?:O que copiar|Estilo a aproveitar): (.+?)\. Siga o formato", linha)
        return {"video": m.group(1).strip(), "segundo": float(seg.group(1).replace(",", ".").rstrip(".")) if seg else None,
                "o_que_copiar": copiar.group(1).strip() if copiar else str((rb or {}).get("o_que_copiar") or ""),
                "layout": (rb or {}).get("layout") or ""}
    if rb and not job.get("conversa"):   # veio da conversa pelo Criar: vale o que o Criar mandou
        return {"video": str(rb["video"]).strip(), "segundo": rb.get("segundo"), "o_que_copiar": str(rb.get("o_que_copiar") or ""),
                "layout": rb.get("layout") or ""}
    return None


def instrucao_referencia(job: dict, f: dict | None = None) -> str:
    """O que a IA tem que fazer com a referência (vazio sem referência): folha de quadros, seção no ANALISE.md e o
    layout que o formato sabe montar. Sem a seção a conferência (conferir_referencia) reprova o storyboard."""
    ref = referencia_do_job(job)
    if not ref:
        return ""
    sb = job["sandbox"]
    v = ref["video"]
    link = v.startswith(("http://", "https://"))
    fonte = v if link or Path(v).is_absolute() or not (RAIZ / sb / v).is_file() else f"{sb}/{v}"
    seg = (f" (o João marcou o segundo {ref['segundo']:.1f})".replace(".", ",")
           if isinstance(ref.get("segundo"), (int, float)) and not isinstance(ref.get("segundo"), bool) else "")
    baixar = f"baixe antes com yt-dlp pra {sb}/work/referencia.mp4 e use ela; " if link else ""
    L = ["", f"REFERÊNCIA DESTE VÍDEO (obrigatório; sem isso a conferência reprova o storyboard): {v}{seg}.",
         f"- Antes de planejar, {baixar}extraia os quadros: `python3 app/ferramentas/folha.py \"{sb + '/work/referencia.mp4' if link else fonte}\""
         f" --saida {sb}/work/folhas/referencia.jpg` e OLHE a folha.",
         f"- No {sb}/ANALISE.md, escreva esta seção (o título e o começo de cada linha exatamente assim):",
         f"  ## {SECAO_REFERENCIA}",
         "  Usada: sim | em parte | não, porque <o motivo>",
         "  Quadros: work/folhas/referencia.jpg",
         "  Layout: <" + ", ".join(_layouts_txt()) + ": o que a referência usa>",
         "  Estilo aproveitado: <ritmo, enquadramento, acabamento, clima...; nunca roteiro, textos, pessoas ou cenas>",
         "  Não deu: <o que não deu e por quê; \"nada\" se deu tudo>"]
    try:
        import formatos as _fmt
        f = f or _fmt.carregar(job.get("formato") or "") or _fmt.de_modelo(job.get("modelo", ""))
        tem = [x for x in (f or {}).get("layouts") or [] if x in _fmt.LAYOUTS]
        aviso = _fmt.aviso_layout(ref, f) if f else None
    except Exception:
        tem, aviso = [], None
    if tem:
        L.append(f"- Este formato sabe montar: {', '.join(tem)}. Referência com outro layout: não force nem mexa no motor;"
                 " aproveite o resto do estilo e diga em \"Não deu\".")
    if aviso:
        L.append(f"- Já se sabe: a referência pede {aviso['layout']} e o formato não tem. \"Usada: em parte\" (ou \"não\") e explique.")
    return "\n".join(L)


def _layouts_txt() -> list[str]:
    try:
        import formatos as _fmt
        return list(_fmt.LAYOUTS)
    except Exception:
        return ["cheio", "dividido"]


def _secao_md(texto: str, titulo: str) -> str | None:
    """O corpo de uma seção "## <titulo>" de um .md (até o próximo título); None se ela não existe."""
    linhas = texto.splitlines()
    alvo = titulo.lower()
    for i, l in enumerate(linhas):
        if re.match(r"^\s*#{1,4}\s", l) and alvo in l.lower().replace("*", ""):
            corpo = []
            for x in linhas[i + 1:]:
                if re.match(r"^\s*#{1,4}\s", x):
                    break
                corpo.append(x)
            return "\n".join(corpo)
    return None


def _campo(secao: str, nome: str) -> str:
    m = re.search(rf"(?im)^[\s>*_-]*{nome}[*_\s]*:[*_\s]*(.*)$", secao)
    return m.group(1).strip().strip("*_ ") if m else ""


def referencia_analisada(job: dict) -> dict | None:
    """Lê a seção "Referência analisada" do ANALISE.md. None se o vídeo não tem referência. Senão: secao (bool), usada
    ("sim", "em parte", "não" ou ""), porque, quadros (a folha citada que existe, ou ""), copiado, nao_deu e a frase
    que a tela mostra no topo do storyboard ("Referência: usada" / "Referência: não usada porque …")."""
    if not referencia_do_job(job):
        return None
    sb = RAIZ / job.get("sandbox", "")
    try:
        md = (sb / "ANALISE.md").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        md = ""
    sec = _secao_md(md, SECAO_REFERENCIA.lower())
    r = {"secao": sec is not None, "usada": "", "porque": "", "quadros": "", "copiado": "", "nao_deu": ""}
    if sec is None:
        r["frase"] = "Referência: não usada porque a IA não registrou que olhou a referência"
        return r
    v = _campo(sec, "usada")
    low = v.lower()
    r["usada"] = ("sim" if low.startswith("sim") else "em parte" if low.startswith(("em parte", "parte", "parcial"))
                  else "não" if low.startswith(("não", "nao")) else "")
    m = re.search(r"porque\s*:?\s*(.+)", v, re.I) or re.search(r"^(?:sim|em parte|parcial\w*|n[ãa]o)\W+(.+)", v, re.I)
    r["porque"] = m.group(1).strip(" ()") if m else ""
    for cam in re.findall(r"[^\s`'\"()]+\.(?:jpe?g|png)", _campo(sec, "quadros"), re.I):
        p = Path(cam)
        if any(x.is_file() for x in ([p] if p.is_absolute() else [sb / p, RAIZ / p])):
            r["quadros"] = cam
            break
    r["copiado"], r["nao_deu"] = _campo(sec, "estilo aproveitado") or _campo(sec, "copiado"), _campo(sec, "n[ãa]o deu")
    nao_deu = r["nao_deu"] if r["nao_deu"].lower().strip(" .") not in ("", "nada", "-") else ""
    if r["usada"] == "sim":
        r["frase"] = "Referência: usada" + (f" (estilo: {_curto(r['copiado'], 160)})" if r["copiado"] else "")
    elif r["usada"] == "em parte":
        r["frase"] = "Referência: usada em parte" + (f"; não deu: {_curto(nao_deu or r['porque'], 160)}" if nao_deu or r["porque"] else "")
    elif r["usada"] == "não":
        r["frase"] = f"Referência: não usada porque {_curto(r['porque'] or nao_deu, 160) or 'a IA não disse o motivo'}"
    else:
        r["frase"] = "Referência: a IA não disse se usou"
    return r


def conferir_referencia(job: dict) -> str:
    """Conferência do storyboard: o vídeo tem referência e o ANALISE.md não prova que ela foi olhada? Devolve o motivo
    (reprova); "" quando passa ou quando não há referência."""
    r = referencia_analisada(job)
    if r is None:
        return ""
    if not r["secao"]:
        return (f"Reprovado: o vídeo tem referência e o ANALISE.md não tem a seção \"{SECAO_REFERENCIA}\". "
                "Nada prova que alguém olhou os quadros dela. Clique em tentar de novo.")
    if not r["usada"]:
        return f"Reprovado: a seção \"{SECAO_REFERENCIA}\" não diz se a referência foi usada (Usada: sim, em parte ou não)."
    if r["usada"] != "não" and not r["quadros"]:
        return (f"Reprovado: a seção \"{SECAO_REFERENCIA}\" não aponta a folha de quadros da referência (folha.py), "
                "ou ela não existe.")
    if r["usada"] != "sim" and not (r["porque"] or r["nao_deu"]):
        return f"Reprovado: a seção \"{SECAO_REFERENCIA}\" diz que a referência não foi usada toda, mas não diz por quê."
    return ""


def referencia_storyboard(cli: str, slug: str) -> str:
    """A linha que a tela mostra no topo do storyboard; "" se o vídeo não tem referência ou o storyboard não saiu."""
    try:
        job = carregar(cli, slug)
    except ValueError:
        return ""
    if not job or not (RAIZ / job.get("sandbox", "") / "ANALISE.md").is_file():
        return ""
    r = referencia_analisada(job)
    return r["frase"] if r else ""


def _material_formato_txt(job: dict, f: dict | None) -> str:
    """"MATERIAL DESTE VÍDEO": o que o João preencheu no passo 4 do Criar (job["material_formato"], campos do formato.json → pede)."""
    mf = job.get("material_formato") or {}
    if not mf:
        return ""
    rot = {c["campo"]: c.get("rotulo") or c["campo"] for c in ((f or {}).get("pede") or []) if isinstance(c, dict)}
    linhas = "; ".join(f"{rot.get(k, k)} = {v}" for k, v in mf.items())
    return f"\nMATERIAL DESTE VÍDEO (pedido pelo formato, preenchido pelo João no Criar; use exatamente): {linhas}.\n"


def _personagem_txt(job: dict) -> str:
    """"PERSONAGEM ESCOLHIDO": o protagonista que o João marcou no Criar (Explicador 3D); o figurino do elenco do estilo entra no render."""
    nome = job.get("personagem")
    if not nome:
        return ""
    import elenco
    arq = rel(elenco.arquivo(elenco.FORMATO))
    return (f"\nPERSONAGEM ESCOLHIDO: {nome} (elenco do estilo Explicador 3D em {arq}). É o protagonista: no elenco da decupagem escreva "
            f"\"<id>\": \"{nome}\" e não troque o figurino; se o {nome} estiver no elenco.json do estilo, o render usa as cores dele.\n")


def _voz_txt(job: dict) -> str:
    """A voz que o João escolheu no Criar (perfil fixo do VoiceStudio) e a força do Claude: chega no prompt, não só no job.json."""
    t = ""
    if job.get("voz"):
        t += f"VOZ ESCOLHIDA PELO JOÃO NO CRIAR (perfil fixo do VoiceStudio; passe exatamente este id na narração): {job['voz']}\n"
    return t


def prompt_esteira(job: dict, fase: str, saida: str | None = None, ajuste: str = "") -> str:
    """Prompt dos formatos com esteira, receita primeiro, em duas fases:
    'ate_aprovacao' roda as etapas até a que pede aprovação, gera storyboard.jpg pelo motor, grava um PLANO.json
    mínimo (com 2 a 3 músicas e os efeitos) e para; 'depois' leva a música e os efeitos escolhidos pro arquivo do vídeo,
    renderiza, roda a conferência (corrige até 3 vezes) e só entrega com ela aprovada.

    O texto segue o que o formato declara (formatos.esteira): o arquivo do vídeo ("cenas"; padrão cenas.json), se o motor
    é copiado pra sandbox ("copiar_motor"), de onde vem a voz ("voz"), a folha da conferência ("folha") e se tem música e
    efeitos (som.*.usa). Sem esses campos é o motor HTML do Estúdio, o do Documentário (previa-som, checagem, catálogo)."""
    if fase not in ("ate_aprovacao", "depois"):
        raise ValueError("Fase da esteira: ate_aprovacao ou depois.")
    import formatos as _fmt
    est = _esteira(job)
    f = _fmt.carregar(est["slug"]) if est else None
    if not f:
        raise ValueError("Este vídeo não é de um formato com esteira.")
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    pm, sb, slug = rel(mod["pasta"]), job["sandbox"], f["slug"]
    saida = saida or job["saida_esperada"]
    saida_abs = str(saida if Path(saida).is_absolute() else RAIZ / saida)
    base = f.get("base") or f"formatos/{slug}/base"
    cmd = lambda nome: _fmt.comando(est, nome, sb, saida_abs)
    padrao = _fmt.motor_padrao(est)
    cenas = est.get("cenas") or "cenas.json"
    copiar = est.get("copiar_motor", True)
    com_musica, com_efeitos = est.get("musica", True), est.get("efeitos", True)
    folha = est.get("folha") or "qa/folha-comparacao.jpg"
    folhas_txt = " e ".join(f"{sb}/{x}" for x in (est.get("folhas") or [folha]))
    motor = str(f["esteira"].get("motor") or "render.py") if isinstance(f.get("esteira"), dict) else "render.py"
    fala = ""
    if job.get("entrada") == "roteiro":
        entrada = f"roteiro em {job['bruto']} " + ENTRADA_ROTEIRO[est.get("voz") or "narracao"]
    else:
        video = (job.get('corte_aplicado') or {}).get('arquivo') or job['bruto']
        entrada = f"vídeo gravado {video}"
        if job.get("brutos_extras"):
            entrada += " + " + ", ".join(job["brutos_extras"])
        # o words.json de work/ é do bruto ORIGINAL; com o corte aplicado o vídeo cortado precisa da própria transcrição
        pasta_fala = f"{sb}/work/fala-cortada" if job.get("corte_aplicado") else f"{sb}/work"
        fala = (f"FALA (tempo por palavra; nunca estime): python3 app/ferramentas/corte.py transcrever \"{video}\" \"{pasta_fala}\" "
                f"--cliente \"{job['cliente']}\" → {pasta_fala}/words.json (reaproveita se já existir).\n")
        if any(e.get("faz_video") for e in est["etapas"]):   # a receita de vídeo (preparar-fala.py) já transcreve e escolhe a pasta
            fala = ""
            if job.get("aparecer") in ("sim", "nao"):
                fala = ("O JOÃO APARECE NO VÍDEO? (escolha dele no Criar): " + (
                    "SIM, nos momentos fortes (gancho, virada e fecho em tela cheia; às vezes no cantinho em cima de um print). Cenas `fala`.\n"
                    if job["aparecer"] == "sim" else
                    "NÃO, só a voz dele: a fala vira a narração e as cenas do Editorial cobrem o vídeo inteiro. NENHUMA cena `fala`.\n"))
            if job.get("roteiro_corte"):
                fala += f"ROTEIRO DO JOÃO (entrada c): {job['roteiro_corte']} é o gabarito da fala dele.\n"
        if job.get("entrada") == "filmagem":   # montagem de evento: são TODOS os takes de bruto/, sem fala pra transcrever
            entrada = f"filmagem de evento: TODOS os {1 + len(job.get('brutos_extras') or [])} vídeos de {sb}/bruto/ (olhe cada um numa folha de quadros)"
            fala = ""
    fala += _musica_viral_txt(job, f, sb)
    import resumo_regras
    regras_txt = resumo_regras.resumo(slug, job["cliente"], job["modelo"], com_passos=False)
    secoes = resumo_regras.secoes(f["pasta"] / "COMO-FAZER.md")
    if secoes:
        regras_txt += f"\nSeções do formatos/{slug}/COMO-FAZER.md (abra só a que precisar): {secoes}"
    exs = f.get("exemplos") or []
    if exs:
        try:
            folha_ex = _fmt.folha_exemplo(slug, 0)
        except Exception:
            folha_ex = None
        exemplo = (f"{exs[0]['video']} ({exs[0].get('legenda') or 'aprovado'})."
                   + (f" Abra a folha {rel(folha_ex)} (1 quadro a cada 4 s)" if folha_ex else " Extraia 1 quadro a cada 4 s")
                   + f" e olhe ANTES de montar qualquer cena: o vídeo novo iguala a variedade de {_o_que_o_exemplo_tem(com_musica, com_efeitos)} (ritmo, tipos de cena, acabamento); "
                   "o conteúdo (frases, pessoas, cenas) vem desta fala e deste cliente, nunca do exemplo. Nunca entregue pior que ele.")
    else:
        exemplo = "o formato ainda não tem exemplo: siga o COMO-FAZER à risca."
    if _fmt.estudo_txt(slug):   # a referência estudada UMA vez (formatos.py referencia): lê em vez de reestudar
        exemplo += " " + _fmt.estudo_txt(slug)
    linhas = []
    for i, e in enumerate(est["etapas"], 1):
        l = f"   {i}) {e['titulo']} [--etapa {e['andamento']}]"
        faz_e = e.get("faz_video") if (e.get("faz_video") and job.get("entrada") != "roteiro") else e["faz"]   # entrada por vídeo (Editorial falado): a receita dela
        if faz_e:
            l += f": {_fmt.na_sandbox(str(faz_e), sb) if '<sandbox>' in str(faz_e) else faz_e}"
        if e.get("comando"):
            l += f" Comando: `{_fmt.na_sandbox(str(e['comando']), sb, saida_abs)}`"
        if i - 1 == est["parada"]:
            l += "  ← PARA AQUI: aprovação do João"
        linhas.append(l)
    k = est["parada"] + 1
    material = material_txt(cli) + _material_formato_txt(job, f) + _personagem_txt(job)
    escolhidos = _brolls_escolhidos_txt(job)
    if copiar:
        so_base = padrao or any((RAIZ / base / x).is_dir() for x in ("audio/musicas", "demo"))
        protege = "" if padrao else f" --exclude '/{cenas}'"
        passo_motor = (f"""1. MOTOR: o Estúdio já pôs na sandbox o motor mais novo (base do formato → modelo do cliente → sandbox). Garanta com
   (só traz o que estiver mais novo; não mexe no que é do vídeo):
   rsync -a --update --exclude '_sandbox*' --exclude 'aprendizado/' --exclude '/audio/musicas/' --exclude '/demo/'{protege} "{pm}/" "{sb}/"
""" + (f"""   O {cenas} é o vídeo: só vem do modelo se a sandbox ainda não tiver (rsync -a --ignore-existing "{pm}/{cenas}" "{sb}/");
   depois disso ele é só deste vídeo.
""" if not padrao else "") + f"""   Se depois disso {sb}/{motor} não existir, rode o mesmo comando a partir de "{base}/". Trabalhe só dentro da sandbox.
""" + (f"""   As músicas (audio/musicas/) e a demo/ ficam só em "{base}/": o render acha lá sozinho, não copie. Nunca edite o
   motor da sandbox pra um vídeo: o ajuste é no {cenas}.""" if so_base else
       f"""   Nunca edite o motor da sandbox pra um vídeo: o ajuste é no {cenas}{'' if padrao else ' (o vídeo deste formato)'}."""))
    else:
        passo_motor = f"""1. MOTOR: este formato roda direto da base ("{base}/"): os comandos já apontam pra lá. Não copie o motor pra
   sandbox nem pro modelo do cliente; a sandbox ({sb}) é a pasta do vídeo: o {cenas} e o que o motor gerar. Nunca edite
   a base pra um vídeo."""
    txt = f"""Você está no Estúdio (raiz: {RAIZ}). Vídeo do formato "{f['titulo']}" pela tela. Quem manda é a RECEITA do formato:
siga a esteira dele, passo a passo, na ordem. Nada de pipeline genérico.

CLIENTE: {job['cliente']}   MODELO DO CLIENTE: {pm}
ENTRADA: {entrada}
{fala}SANDBOX: {sb}   SAÍDA FINAL: {saida} (caminho absoluto: {saida_abs})
BRIEFING DO JOÃO (é ordem e ganha dos padrões; atenda cada pedido): {job.get('briefing') or '(sem briefing: decida pelo conteúdo)'}
MATERIAL ANEXADO: {', '.join(job.get('materiais') or []) or '(nenhum)'}
{_voz_txt(job)}MATERIAL PRÓPRIO DO CLIENTE (foto real ganha de banco quando a fala cita a pessoa, o produto ou a prova):
{material}
{escolhidos}{secao_briefing(job)}{sem_legenda_txt(job)}
{passo_motor}
2. REGRAS (o resumo abaixo já tem o que vale; na briga: modelo do cliente > formato > geral). Leia REGRAS.md (curto).
   NÃO dê cat no COMO-FAZER.md, no formatos/{slug}/formato.json (campos "usa" e "esteira") nem nos regras.json
   (formatos/{slug}/aprendizado/, {pm}/aprendizado/) inteiros: abra só a seção que precisar, com grep (pelo [id] ou assunto).
{regras_txt}
   FOLHA DE QUADROS (pra ver um b-roll ou trecho inteiro numa imagem só, com o segundo em cada quadro):
   `python3 app/ferramentas/folha.py <video> --saida {sb}/work/folhas/<nome>.jpg [--de S --ate S]`
   (ou o --folha-broll do motor, se ele tiver). Nunca escreva script de folha nem de storyboard na hora.
3. EXEMPLO PRINCIPAL (régua de estilo e de qualidade): {exemplo}
   {REGRA_ESTILO}
4. ESTEIRA (a cada etapa rode `python3 app/ferramentas/andamento.py passo "<o que está fazendo>" --etapa <a do colchete>`):
{chr(10).join(linhas)}
"""
    if fase == "ate_aprovacao":
        if padrao:
            rodada = f"""- RODADA NOVA, PLANO NOVO: monte o {sb}/cenas.json do zero a partir da fala, com a busca de cenas de fora nova (acervo +
  get-brolls; as que o João já escolheu entram, mas não bastam). Cada cena de fora leva "origem" (o link ou o arquivo de
  onde veio): sem ela o --conferir reprova. O cenas.json de rodada anterior, se houver, está guardado
  em {sb}/work/rodadas/: serve só pra ver o que já foi usado e não repetir o que o João reprovou. Nunca parta dele."""
            sb_txt = f"""- Storyboard: gere {sb}/storyboard.jpg com o comando do motor: `{cmd('storyboard')}`. Nunca desenhe storyboard com script próprio.
  Abra o storyboard e compare com a folha do exemplo principal antes de mostrar pro João.
  O comando confere as cenas antes (o que o --conferir reprovaria no vídeo) e grava {sb}/previa-som.m4a (voz, música e
  efeitos, pra ouvir antes do render). Saiu "REPROVADO na checagem": corrija o cenas.json pelo motivo e rode de novo, até
  "APROVADO na checagem". Motivo sem jeito (ex.: nenhuma cena de fora boa): diga no ANALISE.md por quê."""
        else:
            rodada = f"""- RODADA NOVA, PLANO NOVO: monte o {sb}/{cenas} de novo pelos passos da esteira (entra nele só o que a receita
  manda: nada de cenas.json nem de busca de cena que o formato não usa). A versão da rodada anterior, se houver, está
  guardada em {sb}/work/rodadas/: serve só pra não repetir o que o João reprovou. Nunca parta dela.
- TENTATIVA INTERROMPIDA (limite de uso, Mac dormiu): a sandbox pode já ter voz (work/voz.wav, words.json), fotos/, clipes/, prints/,
  recortes/. Veja com `ls` e REAPROVEITE o que está lá; refaça só o que falta (a narração só se work/narracao.json não existir)."""
            c = cmd('storyboard')
            sb_txt = f"""- Storyboard: gere {sb}/storyboard.jpg com o comando do motor: `{c}`{_preencher(c)}.
  Nunca desenhe storyboard com script próprio. Abra o storyboard e compare com a folha do exemplo principal antes de
  mostrar pro João. O comando deu erro ou reprovou: corrija o {cenas} pelo motivo e rode de novo."""
        if ajuste:   # pedido do João sobre o storyboard: mexe só no que ele citou
            citadas = cenas_citadas(ajuste)
            rodada = f"""- AJUSTE DO STORYBOARD (não é rodada nova): o João pediu: \"\"\"{ajuste}\"\"\"
  Cenas citadas: {citadas or 'veja no pedido (pelo número do quadro ou pelo tempo)'}.
  Parta do {sb}/{cenas} ATUAL e mexa SÓ no que o pedido cita; as outras cenas ficam exatamente como estão (mesma mídia,
  mesmo tempo, mesmo texto). Não rebusque b-roll de cena que ele não citou: busca nova só pra cena citada que pede
  outra imagem. Música e efeitos ficam como estão, a não ser que o pedido fale deles. O {cenas} anterior está
  guardado em {sb}/work/rodadas/."""
        if com_musica:
            m1 = (f"""  A opção m1 (a escolhida) é EXATAMENTE a música do cenas.json, a que toca na previa-som.m4a. Trocou de faixa no meio:
  m1 leva "trechos" com a mesma lista do cenas.json (arquivo, inicio_s, de) e "arquivo" = a primeira; as outras opções
  são alternativas pro vídeo todo. Sem isso a tela mostra uma faixa só e o vídeo sai só com ela.""" if padrao else
                  f"""  A opção m1 (a escolhida) é EXATAMENTE a música que o motor vai tocar (onde a receita manda: no {cenas} ou no motor);
  as outras opções são alternativas pro vídeo todo.""")
            musica = (f"- {_musica_esteira(job, base, est)}  Deixe 2 a 3 faixas candidatas em {sb}/work/musica/ "
                      f"(catálogo do formato, do cliente ou Mixkit).\n{m1}")
        else:
            musica = f"- {_musica_esteira(job, base, est).rstrip()}"
        if com_efeitos and padrao:
            efeitos = """- Efeitos sonoros: em "sfx", UM POR TIPO de som que as cenas usam (nunca um por momento; até 6), ligados:
  id = som = nome do som no motor (catálogo audio/ do motor; Freesound só pra efeito), sem "t"; "titulo" em português
  curto pro João, ex.: typing "Teclado na frase", whoosh-short "Passagem quando muda o fundo", click-soft "Clique no ✓/X",
  tique "Tique do relógio", pop "Pop na foto e na etiqueta", key-press "Tecla nos rótulos". Desmarcar um tira esse som do vídeo todo."""
        elif com_efeitos:
            efeitos = """- Efeitos sonoros: em "sfx", UM POR TIPO de som que o motor usa (nunca um por momento; até 6), ligados: id = som =
  nome do som no motor, sem "t"; "titulo" em português curto pro João. Desmarcar um tira esse som do vídeo todo."""
        else:
            efeitos = """- Efeitos sonoros: este formato não usa (formato.json → som.efeitos.usa = false): "sfx": [] e "sfx_ligado": false."""
        if com_efeitos and est.get("efeitos_de_onde"):
            efeitos += f"\n  O FORMATO DIZ (de onde vêm os efeitos): {est['efeitos_de_onde']}"
        numeros = ("""
  Música e efeitos no ANALISE.md: use os números da linha "pro João (use estes números no ANALISE.md)" que o --storyboard
  imprime (a faixa com de e até, e o número REAL de efeitos); nunca estime nem copie do exemplo.""" if padrao else "")
        return txt + f"""
NESTA RODADA: etapas 1 a {k} (até "{est['etapas'][est['parada']]['titulo']}"). NÃO renderize o vídeo final.
{rodada}
{sb_txt}
{musica}
{efeitos}
- Grave {sb}/PLANO.json (JSON válido, UTF-8), no mínimo assim:
{_esquema_esteira(est)}
- Escreva {sb}/ANALISE.md curto: o que o vídeo vai mostrar, cena a cena, e o que o João deve olhar. Tempo sempre em
  minuto:segundo, como no storyboard (77 s = 1:17, nunca 0:77).{numeros}{instrucao_referencia(job, f)}
- No fim: `python3 app/ferramentas/andamento.py espera "Storyboard pronto" --imagem {sb}/storyboard.jpg` e PARE.
Não peça confirmação.
"""
    if ajuste:
        rodada = (f"o João assistiu o vídeo e pediu AJUSTE: \"\"\"{ajuste}\"\"\". Refaça as etapas {k + 1} a {len(est['etapas'])} "
                  f"aplicando o pedido (volte ao storyboard só se o pedido mexer nele) e salve em {saida}.")
    else:
        rodada = f"o João aprovou o storyboard. Faça as etapas {k + 1} a {len(est['etapas'])}."
    leia = []
    if com_musica:
        leia.append("musica.escolha é o id da faixa em musica.opcoes; musica.sem=true: sem música"
                    + ("; use só sfx ligados." if com_efeitos else "."))
        if padrao:
            leia.append("A faixa escolhida com \"trechos\" (troca de faixa no meio): o \"musica\" do cenas.json é a lista inteira dos trechos.")
    if com_efeitos:
        leia.append("Nos efeitos, só entram os de \"ligado\": true; sfx_ligado=false (ou nenhum ligado): nenhum efeito.")
    if not (com_musica or com_efeitos):
        leia.append("Este formato não usa música nem efeitos.")
    leia.append("observacoes_joao e o \"comentario\" de cada cena são pedidos dele: aplique antes do render.")
    render = cmd('render')
    if padrao and (com_musica or com_efeitos):
        passar = (f"- Passe {'a música escolhida e os efeitos' if com_musica and com_efeitos else 'a música escolhida' if com_musica else 'os efeitos'}"
                  f" pro {sb}/cenas.json e só então renderize: `{render}`.")
        if com_musica:
            passar += f"""
  "musica": a opção escolhida com "trechos" (troca de faixa no meio) vira a LISTA inteira, um item por trecho com
  "arquivo", "inicio_s" e "de", iguais aos da opção; sem "trechos", {{"arquivo", "inicio_s"}} da faixa; musica.sem=true: null.
  Faixa de fora da sandbox (como a do acervo): copie antes pra {sb}/work/musica/ e aponte pra cópia."""
        if com_efeitos:
            passar += """
  "efeitos": a LISTA dos sons ligados, os "som" dos sfx com "ligado": true, sem repetir, ex.: ["typing", "whoosh-short",
  "click-soft", "tique", "pop"]; o som desmarcado não toca em nenhum momento; "efeitos": false se nenhum estiver ligado;
  "sfx" vazio com sfx_ligado=true: "efeitos": true."""
    elif padrao:
        passar = f"- Este formato não usa música nem efeitos: no cenas.json, \"musica\": null e \"efeitos\": false. Renderize: `{render}`."
    elif com_musica or com_efeitos:
        oque = " e ".join(x for x, ok in (("a música escolhida", com_musica), ("os efeitos ligados", com_efeitos)) if ok)
        passar = (f"- Passe {oque} pro motor como a receita manda (no {cenas} ou no motor; o som desmarcado não toca em nenhum "
                  f"momento; faixa de fora da sandbox: copie antes pra {sb}/work/musica/) e só então renderize: `{render}`{_preencher(render)}.")
    else:
        passar = f"- Renderize: `{render}`{_preencher(render)}."
    conf = cmd('conferir')
    sons = " e ".join(x for x, ok in (("música", com_musica), ("efeitos", com_efeitos)) if ok)
    inclusive = f", inclusive {sons}" if sons else ""
    if padrao:
        conferir = f"""- Confira: `{conf}` (qa/conferir.json e {folha}, o render lado a lado com o exemplo principal). Olhe a folha.
  Se o comando não gerar a folha, monte-a: python3 app/ferramentas/formatos.py folha-video <render.mp4> {sb}/qa/folha-video.jpg
  (1 quadro a cada 4 s, igual à do exemplo) e ponha ao lado da folha do exemplo principal.
  Reprovou? Corrija e renderize de novo, até 3 vezes. Só copie o render pra {saida} (crie a pasta) com o --conferir aprovado."""
    else:
        conferir = f"""- Confira: `{conf}` (exit 0 = aprovado{_preencher(conf, dentro=True)}) e a skill /watch no vídeo; no RESULTADO.md cole o caminho
  do qa/conferir.json e 3 quadros que você abriu (nunca "não rodei o /watch"). Olhe a folha {folhas_txt} ao lado da folha do exemplo
  principal. Se o comando não gerar folha: python3 app/ferramentas/formatos.py folha-video <render.mp4> {sb}/qa/folha-video.jpg
  (1 quadro a cada 4 s, igual à do exemplo).
  Reprovou? Corrija e renderize de novo, até 3 vezes. Só copie o render pra {saida} (crie a pasta) com a conferência aprovada."""
    return txt + f"""
NESTA RODADA: {rodada}
- Se {sb}/{cenas} não existir (vídeo feito antes da esteira), faça antes as etapas 1 a {k} ({'motor na sandbox, ' if copiar else ''}o {cenas}
  pelas regras e o storyboard com `{cmd('storyboard')}`) e só então renderize.
- Leia {sb}/PLANO.json: {(chr(10) + '  ').join(leia)}
{passar}
{conferir}
  Se na 3ª ainda reprovar: NÃO copie; escreva no RESULTADO.md o que reprovou e por quê.
- Escreva {sb}/RESULTADO.json (comando como string; materiais_usados com arquivo, tipo, titulo, fonte, autor, licenca, descricao{inclusive})
  e grave o comando em {sb}/comando.sh.
- Escreva {sb}/RESULTADO.md curto: o que mudou em relação ao storyboard, o resultado da conferência e a folha {folhas_txt}.
- Não apague nada da sandbox. Não peça confirmação; execute até o fim.
"""


def carregar(cli: str, slug: str) -> dict | None:
    d = ler_json(_pasta_job(cli, slug) / "job.json")
    if d:
        d["_pasta"] = _pasta_job(cli, slug)
        d["rodando"] = _vivo(_pasta_job(cli, slug) / "runner.pid")
    return d


def salvar(job: dict) -> None:
    limpo = {k: v for k, v in job.items() if not k.startswith("_") and k != "rodando"}
    gravar_json(_pasta_job(job["cliente"], job["slug"]) / "job.json", limpo)


def listar(cli: str | None = None) -> list[dict]:
    out = []
    if not JOBS.is_dir():
        return out
    for pc in sorted(JOBS.iterdir()):
        if not pc.is_dir() or (cli and pc.name.lower() != cli.lower()):
            continue
        for pj in pc.iterdir():
            j = carregar(pc.name, pj.name)
            if j:
                out.append(j)
    out.sort(key=lambda j: j.get("criado_em", ""), reverse=True)
    return out


# ───────────────────────── um estado só: job.json × app/andamento ─────────────────────────
# O vídeo feito pelo chat só grava em app/andamento/; a tela lê o job.json. sincronizar() copia o estado
# na hora de gravar; reconciliar() conserta os que já ficaram pra trás. Só o job.json é escrito.

FECHADOS = ("aprovado", "exportado", "arquivado")


def _job_do_andamento(cli: str, slug: str, pasta: str = "") -> dict | None:
    """O job do mesmo vídeo: mesmo cliente+slug, ou o job cuja sandbox é a do vídeo (chat com slug diferente)."""
    try:
        j = carregar(cli, slug)
    except ValueError:
        return None
    if j:
        return j
    for j in listar(cli):
        sb = j.get("sandbox") or ""
        if sb and ((pasta and Path(sb) == Path(pasta)) or Path(sb).name == f"_sandbox-{slug}"):
            return j
    return None


def achar_saida(job: dict, video: str = "") -> str:
    """O .mp4 pronto do job: o que o andamento apontou, o que o job já tinha, o esperado, ou clientes/<Cliente>/*Content/output/**/<slug>.mp4."""
    for c in (video, job.get("saida"), job.get("saida_esperada")):
        if c and (RAIZ / c).is_file():
            return str(c)
    for q in sorted((RAIZ / "clientes" / job["cliente"]).glob(f"*Content/output/**/{job['slug']}.mp4")):
        return rel(q)
    return ""


def sincronizar(cli: str, slug: str, estado: str, video: str = "", pasta: str = "") -> bool:
    """Chamado por andamento.registrar. pronto → job 'concluido' com a saída; erro → 'erro'; esperando → 'plano' (storyboard esperando).
    Não mexe em job rodando (o runner fecha sozinho) nem em vídeo aprovado/exportado/arquivado."""
    j = _job_do_andamento(cli, slug, pasta)
    if not j or j.get("rodando") or j.get("status") in FECHADOS:
        return False
    novo = {"pronto": "concluido", "erro": "erro", "esperando": "plano"}.get(estado)
    if not novo:
        return False
    saida = j.get("saida")
    if estado == "pronto":
        saida = achar_saida(j, video)
        if not saida:
            return False
    if novo == j.get("status") and saida == j.get("saida"):
        return False
    j["status"], j["saida"] = novo, saida
    salvar(j)
    return True


def _ts(t: str) -> float:
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return 0.0


def reconciliar(cli: str | None = None, slug: str | None = None) -> int:
    """Conserta job que ficou pra trás do andamento: andamento 'pronto' mais novo que o job.json → job 'concluido' com a saída
    (e 'aprovado' se o João já aprovou depois). Job concluído que o João aprovou no andamento → 'aprovado'.
    Lê tudo, escreve só o job.json. Devolve quantos arrumou. Barato: chame à vontade ao listar."""
    import andamento as _and
    n = 0
    for d in _and.registros():
        if d.get("estado") != "pronto" or (cli and d["cliente"] != cli) or (slug and d["slug"] != slug):
            continue
        j = _job_do_andamento(d["cliente"], d["slug"], d.get("pasta", ""))
        if not j or j.get("rodando") or j.get("status") in FECHADOS:
            continue
        arq = _pasta_job(j["cliente"], j["slug"]) / "job.json"
        t_job = arq.stat().st_mtime if arq.is_file() else 0.0
        aprovou = _ts(_and.aprovado_em(d)) > t_job
        if j.get("status") == "concluido":
            novo = "aprovado" if aprovou else None
        elif _ts(d.get("atualizado", "")) > t_job:
            novo = "aprovado" if aprovou else "concluido"
        else:
            novo = None
        if not novo:
            continue
        saida = achar_saida(j, d.get("video", ""))
        if not saida:
            continue
        j["status"], j["saida"] = novo, saida
        salvar(j)
        n += 1
    return n


# ───────────────────────── criação ─────────────────────────

def criar(cli_nome: str, modelo_nome: str, bruto: Path | None, titulo: str, briefing: str = "",
          brolls: list[str] | None = None, camadas: list[str] | None = None,
          materiais: list[Path] | None = None, cortar_bruto: bool = False,
          roteiro: str = "", extras: list[Path] | None = None, formato: str = "", legenda: bool = True) -> dict:
    """bruto = vídeo gravado. Sem bruto, `roteiro` vira a entrada (formato narrado).
    `extras` = mais vídeos da mesma filmagem (formato de evento), todos em bruto/."""
    cli = _cliente(cli_nome)
    if not cli:
        raise ValueError(f"cliente não encontrado: {cli_nome}")
    mod = _modelo(cli, modelo_nome)
    if not mod:
        raise ValueError(f"modelo não encontrado: {modelo_nome}")
    base = make_slug(titulo) or now_slug()
    slug, n = base, 2
    while _pasta_job(cli["nome"], slug).exists() or (mod["pasta"] / f"_sandbox-{slug}").exists():
        slug = f"{base}-{n}"; n += 1
    sandbox = ensure(mod["pasta"] / f"_sandbox-{slug}")
    ensure(sandbox / "bruto"); ensure(sandbox / "brolls"); ensure(sandbox / "work"); ensure(sandbox / "qa"); ensure(sandbox / "material")
    proprios = []
    for mp in materiais or []:
        dst = sandbox / "material" / Path(mp).name
        shutil.move(str(mp), str(dst)); proprios.append(f"material/{dst.name}")
    entrada = "video"
    if bruto:
        destino_bruto = sandbox / "bruto" / Path(bruto).name
        shutil.move(str(bruto), str(destino_bruto))
    elif roteiro.strip():
        entrada = "roteiro"
        destino_bruto = sandbox / "roteiro.txt"
        destino_bruto.write_text(roteiro.strip() + "\n", encoding="utf-8")
    else:
        raise ValueError("Envie o vídeo gravado ou escreva o roteiro.")
    outros = []
    for x in extras or []:
        d = sandbox / "bruto" / Path(x).name
        shutil.move(str(x), str(d)); outros.append(rel(d))
    if outros:
        entrada = "filmagem"
    usados = []
    for s in brolls or []:
        it = _acervo.item(s)
        if it and it.get("clip"):
            _clonar(str(it["clip"]), str(sandbox / "brolls" / f"{s}{it['clip'].suffix}"))
            _acervo.registrar_uso(s, cli["nome"], modelo_nome, slug)
            usados.append({"slug": s, "titulo": it.get("titulo"), "tags": it.get("tags", []),
                           "fonte": it.get("fonte"), "arquivo": f"brolls/{s}{it['clip'].suffix}"})
    saida = cli["content"] / "output" / modelo_nome / f"{slug}.mp4"
    try:                                   # formato que declara cena de apoio (apoio.usa) nasce com busca, não "essencial"
        import edicao as _ed
        com_apoio = bool(_ed.apoio_do_job({"formato": formato, "modelo": modelo_nome}).get("usa"))
    except Exception:
        com_apoio = False
    job = {
        "slug": slug, "titulo": titulo or slug, "cliente": cli["nome"], "modelo": modelo_nome,
        "criado_em": agora(), "status": "novo", "bruto": rel(destino_bruto), "sandbox": rel(sandbox),
        "entrada": entrada, "brutos_extras": outros, "formato": formato,
        **({} if legenda else {"legenda": False}),
        "escopo_edicao": "esteira" if _esteira({"formato": formato, "modelo": modelo_nome}) else ("busca" if com_apoio else "essencial"),
        "broll_config": {"origem": "busca", "do_formato": True} if com_apoio else {"origem": "nenhum", "quantidade": 0},
        "briefing": briefing or "", "brolls": usados, "materiais": proprios, "cortar_bruto": bool(cortar_bruto) and entrada == "video",   # roteiro não tem o que cortar (o Criar manda cortar=1 sempre)
        "seguir_direto": _segue_direto(formato),
        "camadas": [c for c in (camadas or []) if c and c != modelo_nome],
        "saida_esperada": rel(saida), "saida": None,
        "versao": 1, "versoes": [], "execucoes": [], "feedbacks": [],
    }
    (sandbox / "BRIEF.md").write_text(brief_md(job), encoding="utf-8")
    salvar(job)
    if corta_sozinho(job):
        cortar_sozinho(cli["nome"], slug)
    return carregar(cli["nome"], slug)


def catalogo_material(cli: dict) -> list[dict]:
    """Material PRÓPRIO do cliente (<x>Content/material/<assunto>/): capa de produto,
    card de preço, print de prova, logo, foto real. Não é b-roll e não é do job — é do
    projeto daquela pessoa e serve qualquer modelo dela. O prompt precisa conhecer isso,
    senão o agente sai buscando stock justamente quando a fala cita o produto."""
    base = cli["content"] / "material"
    if not base.is_dir():
        return []
    out = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        meta = ler_json(d / "meta.json", {}) or {}
        arquivos = sorted(f.name for f in d.iterdir() if f.is_file() and f.name != "meta.json")
        if not arquivos:
            continue
        out.append({"assunto": d.name, "pasta": rel(d), "titulo": meta.get("titulo") or d.name,
                    "descricao": meta.get("descricao", ""), "tags": meta.get("tags", []),
                    "arquivos": arquivos})
    return out


def material_txt(cli: dict) -> str:
    cat = catalogo_material(cli)
    if not cat:
        return "  (este cliente ainda não tem material próprio catalogado)"
    linhas = []
    for m in cat:
        linhas.append(f"  - `{m['pasta']}/` — {m['titulo']}"
                      + (f" · tags: {', '.join(m['tags'])}" if m["tags"] else ""))
        if m["descricao"]:
            linhas.append(f"      {m['descricao']}")
        linhas.append(f"      arquivos: {', '.join(m['arquivos'])}")
    return "\n".join(linhas)


def brief_md(job: dict) -> str:
    linhas = [f"# Brief — {job['titulo']}", "",
              f"- Cliente: **{job['cliente']}**", f"- Modelo: **{job['modelo']}**",
              f"- Bruto: `{job['bruto']}`", f"- Saída esperada: `{job['saida_esperada']}`",
              f"- Criado pelo Estúdio em {job['criado_em']}", ""]
    if job.get("briefing"):
        linhas += ["## Briefing do João", "", job["briefing"], ""]
    if job.get("legenda") is False:
        linhas += ["## Legenda", "", "- **Sem legenda** (o João vai usar este vídeo em outro formato).", ""]
    cli = _cliente(job["cliente"])
    if cli:
        cat = catalogo_material(cli)
        if cat:
            linhas += ["## Material próprio DO CLIENTE (já existe no projeto, serve qualquer modelo dele)", "",
                       "Quando a fala citar o produto, a oferta, o preço ou a prova que está aqui, o beat é ESTE",
                       "arquivo real — não b-roll buscado, não card só de texto.", ""]
            for m in cat:
                linhas.append(f"- `{m['pasta']}/` — **{m['titulo']}**"
                              + (f" · {m['descricao']}" if m["descricao"] else ""))
                linhas.append(f"  - arquivos: {', '.join(m['arquivos'])}")
            linhas.append("")
    if job.get("materiais"):
        linhas += ["## Material próprio do João (em material/) — prioridade máxima onde couber", ""] + [f"- `{m}`" for m in job["materiais"]] + [""]
    if job.get("camadas"):
        linhas += ["## Camadas extras pedidas (somar a este modelo)", ""] + [f"- {c}" for c in job["camadas"]] + [""]
    if job.get("brolls"):
        linhas += ["## B-rolls já separados do acervo (em brolls/)", ""]
        for b in job["brolls"]:
            linhas.append(f"- `{b['arquivo']}` — {b.get('titulo')} · tags: {', '.join(b.get('tags', []))}"
                          + (f" · fonte: {b['fonte']}" if b.get("fonte") else ""))
        linhas.append("")
    return "\n".join(linhas)


# ───────────────────────── prompts ─────────────────────────

POLITICA_BROLL = """B-ROLL — curadoria obrigatória:
Sempre EXATAMENTE 3 opções reais e verificadas por beat de b-roll. Na rebusca, substitua o trio;
se conservar uma opção, ela conta nas três. Continue buscando até encontrar três opções pertinentes;
se uma fonte falhar, registre a limitação, sem inventar candidatos nem preencher com cena genérica.
Prefira YouTube: como referência, 2 opções do YouTube e 1 de outra fonte pertinente (Pexels,
Pixabay, Commons, site oficial ou acervo), respeitando as restrições visuais do modelo e material próprio.
Stock não é obrigatório se o modelo o proíbe. Se só couber YouTube, varie obras, canais e situações.
Diversidade é de CONTEÚDO: três cenas de obras/contextos diferentes, não três links do mesmo filme,
série ou episódio. Não concentre o plano numa única obra como Severance/Ruptura.
Busque ação + objeto + contexto específicos da fala (ex.: empresário conferindo fluxo de caixa,
cobrando prazo da equipe, delegando tarefa), não apenas 'empresário no escritório'.
Use ângulos literal, metáfora e sensação sem perder a ligação concreta. No motivo de cada opção,
explique qual ação visível corresponde à frase; registre obra/contexto e ângulo.
Não repita vídeo entre opções ou beats, mesmo com URL ou timestamp diferente.
Material próprio vem primeiro quando pertinente, completando as três opções com duas alternativas.
Estas preferências substituem orientações antigas de 2 opções ou teto de 50% por fonte.
VARIEDADE DE FONTE NO VÍDEO FECHADO (não só nas opções): olhe os clipes que você REALMENTE
escolheu para todos os beats juntos. Eles não podem sair quase todos da mesma fonte — um vídeo
inteiro montado com Pexels/Pixabay é reprovado. Regra prática: no máximo METADE dos beats de
b-roll do vídeo pode vir de uma única fonte, e stock (Pexels/Pixabay) nunca pode ser a fonte da
maioria; YouTube e material próprio entram no resto. Se só há stock disponível, diga no
RESULTADO.md por que cada busca no YouTube falhou — não entregue monocultura em silêncio.
No RESULTADO.json, a fonte de cada clipe escolhido é obrigatória, e no RESULTADO.md escreva a
contagem final por fonte (ex.: YouTube 3, material próprio 1, Pexels 1).
Preserve takes aprovados; não abra nova busca durante render de plano aprovado.
"""

POLITICA_MATERIAL = """MATERIAL PRÓPRIO DO CLIENTE — ganha de qualquer busca:
O cliente tem material real catalogado (capa/mockup de produto, card de preço, print de prova,
logo, foto de arquivo). Antes de fechar o plano de beats, passe a transcrição inteira e marque
TODO trecho em que a fala cita produto, nome da oferta, preço, bônus, garantia, link, resultado
ou prova. Em cada um desses trechos o beat é o ARQUIVO REAL do catálogo — não b-roll buscado,
não stock, não card só de texto. É erro entregar o vídeo com a fala citando o produto e a tela
mostrando cena genérica: quando ele fala do produto, o produto tem que APARECER.
Preço e mockup andam juntos: se a fala diz o preço, mostre o card de preço; se ela nomeia o
produto/pack, mostre o mockup. O modelo diz COMO montar isso (card de oferta, insert, faixa) —
consulte a ficha e as regras do modelo. Se o catálogo não tiver o arquivo que a fala pede,
registre a falta no RESULTADO.md em vez de improvisar com stock.
"""

POLITICA_MUSICA = """MÚSICA — todo vídeo tem música, mesmo sem briefing (o João não precisa pedir nem mandar link):
O briefing orienta quando preenchido; vazio, decida pelo conteúdo do bruto. A faixa da ficha é referência
de estilo, não seleção automática. Ordem de busca (pare quando tiver 2 a 3 faixas boas pro clima da fala):
0) Do cliente: python3 app/ferramentas/musica_busca.py do-cliente "<Cliente>" — só as faixas DESTE cliente;
   faixa de outro cliente não vale.
1) Acervo: itens musica (e audio legado que seja música, não SFX) em acervo/itens/*/meta.json. Compare
   descrição, tags, clima, usos anteriores e analise (BPM, LUFS, estrutura, trechos_usaveis) com a
   transcrição, intenção, ritmo e restrições do modelo. Faltou análise de uma candidata promissora:
   musica.py <arquivo> --out <sandbox>/work/musica/<slug>.
2) Mixkit (grátis, uso comercial): python3 app/ferramentas/musica_busca.py buscar "<clima em inglês>" --fonte mixkit.
   Veja as opções, baixe as escolhidas pra <sandbox>/work/musica/externa e analise com musica.py <arquivo>
   --out <sandbox>/work/musica/externa (sem --acervo).
3) Jamendo (musica_busca.py jamendo "<clima em inglês>"; sem chave ele avisa e você segue) ou SoundCloud
   (yt-dlp "scsearch5:<clima em inglês>").
Freesound é SÓ pra efeito sonoro (musica_busca.py freesound "<efeito em inglês>"), nunca pra música.
Faixa sem melodia (drone, pad, ambiente parado) é reprovada: precisa de melodia ou ritmo que dê clima.
YouTube só como referência de estilo ou quando o João mandar (direitos autorais). Evite licença "não
comercial" (NC) em anúncio ou vídeo pago.
VARIEDADE — NUNCA REPETIR MÚSICA DO MESMO CLIENTE: antes de escolher, rode
python3 app/ferramentas/musica_busca.py recentes "<cliente>" --ignorar "<slug deste vídeo>". As faixas listadas
não entram de novo (nem outro trecho da mesma faixa), mesmo que sejam as melhores. Exceção: o João pedir no briefing.
No campo musica do PLANO.json: opcoes com 2 a 3 faixas ({id, arquivo, inicio_s, fim_s, fonte, motivo} e, quando
houver, titulo, acervo_slug, url da página, autor, licenca e credito), escolha = id da que você recomenda (o João
pode trocar ou tirar a música), consulta_acervo (candidatas avaliadas e motivo de uso/descarte; registre se vazio)
e recentes_evitadas (o que o comando recentes listou). Trecho com inicio_s/fim_s: cama sob a voz, virada no card,
pico na oferta. Se recorrer a fonte externa, registre por que o cliente e o acervo não serviram.
EFEITOS SONOROS: cada efeito vai em sfx ({id, som, t, beat, arquivo, motivo, ligado: true}); o João desliga o que
não quiser. Preserve música e efeitos já aprovados no plano.
Esta regra substitui a orientação antiga de usar a faixa da ficha quando não há briefing.
"""

MUSICA_ESSENCIAL = """MÚSICA (só leitura, sem download nesta etapa): todo vídeo tem música. Proponha em musica.opcoes 2 a 3 faixas que
JÁ EXISTEM, casando o clima com a fala: as do cliente (python3 app/ferramentas/musica_busca.py do-cliente "{cliente}") e as do
acervo (acervo/itens/*/meta.json, tipo musica); escolha = a que você recomenda. Nunca repita faixa listada por
python3 app/ferramentas/musica_busca.py recentes "{cliente}" --ignorar "{slug}". Faixa sem melodia (drone, pad) não
serve. Se nada servir, deixe opcoes [] e escreva em musica.motivo o clima pra buscar no Mixkit depois.
"""


def prompt_producao(job: dict) -> str:
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    pasta_modelo = rel(mod["pasta"])
    brolls_txt = "\n".join(f"  - {b['arquivo']} — {b.get('titulo')} (tags: {', '.join(b.get('tags', []))})"
                           for b in job.get("brolls", [])) or "  (nenhum separado — buscar conforme a skill de b-roll)"
    return f"""Você está no Estúdio (raiz: {RAIZ}). Produza um vídeo novo pelo Estúdio.

CLIENTE: {job['cliente']}  (pasta {rel(cli['pasta'])})
MODELO:  {job['modelo']}   (pasta {pasta_modelo})
BRUTO:   {job['bruto']}
SANDBOX: {job['sandbox']}   (use work/, brolls/, qa/ daqui; o BRIEF.md tem o briefing)
SAÍDA FINAL OBRIGATÓRIA: {job['saida_esperada']}
BRIEFING DO JOÃO: {job.get('briefing') or '(sem briefing — decida pelo conteúdo do bruto)'}{secao_briefing(job)}
B-ROLLS JÁ SEPARADOS DO ACERVO:
{brolls_txt}
CAMADAS EXTRAS: {', '.join(job.get('camadas') or []) or '(nenhuma)'} — se houver, leia a ficha/regras/scripts do modelo-camada (mesmo cliente) e aplique por cima do render deste modelo, conforme os beats "camada" do plano.

REGRAS OBRIGATÓRIAS:
EXECUÇÃO: aguarde todos os agentes e renders terminarem antes de encerrar a sessão. Não entregue apenas
"está rodando em segundo plano". Assim que o render terminar, copie o arquivo para SAÍDA FINAL OBRIGATÓRIA,
antes do QA, para que ele fique recuperável se a revisão for interrompida. Se o QA exigir correção,
substitua essa saída pelo render corrigido. Nunca confunda arquivo gerado com revisão concluída.
BRIEFING MANDA, E VEM SOLTO: o que o João escreveu é ORDEM, não sugestão, e ganha dos defaults
do modelo e destas políticas quando conflitar. Ele escreve corrido e costuma juntar vários
pedidos diferentes num texto só (b-roll, música, card, enquadramento, produto, ritmo…), às vezes
em meia frase. Então a PRIMEIRA coisa do job, antes de buscar qualquer clipe: quebre o briefing
em pedidos numerados e escreva <sandbox>/PEDIDOS.md com um por linha e como você vai atender cada
um. Pedido curto ("varia o b-roll", "mostra o preço") é pedido inteiro — não descarte por ser
vago; se estiver ambíguo, escolha a leitura mais literal e diga em PEDIDOS.md qual você adotou.
Antes de renderizar, releia o briefing e confira o PEDIDOS.md contra o plano de beats. No fim,
no RESULTADO.md, repita a lista dizendo ONDE cada pedido aparece no vídeo (beat e segundo).
Pedido que você não conseguiu atender tem que estar declarado ali com o motivo — nunca
silenciosamente ignorado. Entregar um vídeo bonito que ignora um pedido do briefing é reprovado.

MATERIAL PRÓPRIO DO CLIENTE (já existe no projeto, serve qualquer modelo dele):
{material_txt(cli)}
{POLITICA_MATERIAL}
{POLITICA_BROLL}
{POLITICA_MUSICA}
1. Antes de qualquer coisa leia {pasta_modelo}/aprendizado/regras.json INTEIRO e {pasta_modelo}/README.md. Siga todas as regras e o comando_referencia quando existir. Regras de outros modelos/clientes NÃO valem aqui.
2. B-roll: siga a skill do projeto em {rel(SKILL_BROLL)}. A BUSCA PRINCIPAL é fora: get-brolls em TODAS as fontes (YouTube, Pexels, Pixabay, Commons, NASA) + site/canal oficial quando a fala cita marca/produto Mais fontes grátis com licença registrada: `python3 app/ferramentas/fontes_gratis.py video|imagem "<consulta>"` (Internet Archive em domínio público pra filme/noticiário antigo, NASA, Openverse, Commons). O acervo (acervo/itens) é só um atalho: use os itens que o João separou acima e, se nada foi separado, pode consultar o acervo mas NÃO se limite a ele — ele é pequeno e cresce com o que você aprovar. Sempre busca → prévia com contact sheet → verificar frames → aprovar; nunca use um clipe sem olhar os frames (rosto indevido, watermark, legenda queimada). NUNCA salve nada no acervo por conta própria: só o João decide o que entra, pela interface.
3. Transcreva com GROQ (GROQ_API_KEY no app/.env; se {rel(cli['pasta'])}/.env tiver uma, ela vale) como o modelo já faz; b-roll/cards/inserts sempre no tempo exato da palavra (conferir words.json, não estimar).
4. QA obrigatório, com prova: rode `python3 app/ferramentas/conferir_video.py <render.mp4> --sandbox {job['sandbox']}` (exit 0 ou corrija e re-renderize) e a skill /watch no vídeo (frames em vários pontos: legenda casando com a fala, zonas proibidas do Instagram, mesclagem, cards no tempo). No RESULTADO.md cole o caminho do qa/conferir.json e 3 quadros que você abriu. RESULTADO.md que diz "não rodei o /watch" deixa o vídeo em "conferir".
5. Escreva RESULTADO.json na sandbox com comando (string), materiais_usados (lista com arquivo, tipo, titulo, fonte, autor, licenca, descricao, fala, beat) e parametros_alterados. Liste TODOS os materiais realmente usados, inclusive cards, gancho, música e SFX. Grave o comando também em comando.sh. Copie o render final aprovado no QA para exatamente {job['saida_esperada']} (crie a pasta se não existir).
6. NÃO APAGUE NADA da sandbox (nem opções não escolhidas, nem sheets/GIFs, nem prévias): o João ainda vai olhar tudo na tela e escolher o que guardar no acervo; a limpeza é feita pelo Estúdio quando ele finalizar o vídeo. Se precisar renomear clipes pro render, COPIE em vez de mover.
7. Ao terminar escreva {job['sandbox']}/RESULTADO.md com: comando final usado, beats/b-rolls escolhidos e por quê, o que você conferiu no QA, e dúvidas/pontos que o João deve olhar.
8. Não peça confirmação: decida e execute até o fim. Se algo for impossível, explique no RESULTADO.md e ainda entregue o melhor render possível.
"""


GATE_APRENDI = """

REGRA GRAVADA SÓ COM O OK DO JOÃO (vale mais que o item 2 acima): a tela mostra "Aprendi: <regra> · vale pra <cliente|estilo|todo vídeo>" e o João
confirma (OK) ou corrige ("Não é isso"). Por isso NÃO grave nem reescreva regra em regras.json, regras.md nem REGRAS.md neste passo: deixe só a linha
do historico.jsonl (já feita) e conte no RESULTADO.md o que você aprendeu. O ajuste deste vídeo (item 3) você faz normalmente.
"""


def prompt_feedback(job: dict, fb: dict) -> str:
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    pasta_modelo = rel(mod["pasta"])
    nova_saida = job["saida_esperada"]
    if fb["decisao"] == "ajustar":
        v = job.get("versao", 1) + 1
        nova_saida = str(Path(job["saida_esperada"]).with_name(f"{job['slug']}-v{v}.mp4"))
    refazer = (f"""
3. Como a decisão foi AJUSTAR: refaça o vídeo aplicando o feedback, na MESMA sandbox ({job['sandbox']}), e salve a nova versão em exatamente {nova_saida}. Refaça o QA por frames antes de entregar. Atualize {job['sandbox']}/RESULTADO.md com o que mudou.""" if fb["decisao"] == "ajustar" else """
3. Decisão foi APROVADO: não re-renderize. Só registre o aprendizado.""")
    est = _esteira(job)
    receita = ""
    if est and fb["decisao"] == "ajustar":   # formato com esteira: refaz pela receita (render do motor + --conferir)
        refazer = f"""
3. Como a decisão foi AJUSTAR: depois de registrar o aprendizado, refaça o vídeo pela ESTEIRA DO FORMATO (abaixo), na MESMA sandbox ({job['sandbox']}), e salve a nova versão em exatamente {nova_saida}."""
        receita = "\n\nREFAZER PELA ESTEIRA DO FORMATO:\n" + prompt_esteira(job, "depois", saida=nova_saida, ajuste=fb["texto"])
    if est and not (est.get("musica", True) or est.get("efeitos", True)):   # formato sem música e sem efeitos
        musica = ("Este formato não usa música nem efeitos (formato.json → som.*.usa = false): não proponha faixa nem efeito "
                  "por causa do feedback.")
    else:
        musica = "Se envolver música, aplique a política abaixo à nova seleção:\n" + (_musica_esteira(job) if est else POLITICA_MUSICA)
        if est and not est.get("efeitos", True):
            musica += "\nEfeitos sonoros: este formato não usa (formato.json → som.efeitos.usa = false)."
    # Política de onde guardar: camada do FORMATO (vale pra todo cliente) x camada do CLIENTE (gosto dele).
    try:
        import formatos as _fmt
        f = _fmt.de_modelo(job["modelo"]) or _fmt.carregar(job.get("formato") or "")
    except Exception:
        f = None
    regras_cli = f"{pasta_modelo}/aprendizado/regras.json"
    if f:
        apr_fmt = f"formatos/{f['slug']}/aprendizado"
        outros = []
        for var in f.get("variantes") or []:
            oc = _cliente(var["cliente"]) if var["cliente"] != job["cliente"] else None
            if oc:
                outros.append(rel(oc["content"] / "modelos" / var["modelo"] / "aprendizado" / "regras.json"))
        md = (f" Se existir {apr_fmt}/regras.md, ele também é regra do formato: leia antes e, se o assunto já estiver lá, "
              "aprimore a linha dele em vez de duplicar.") if (f["pasta"] / "aprendizado" / "regras.md").exists() else ""
        onde = f"""ONDE GUARDAR (duas camadas):
   - FORMATO "{f['titulo']}": {apr_fmt}/regras.json — vale pra TODO cliente que usa esse formato.{md}
   - CLIENTE {job['cliente']}: {regras_cli} — vale só pra ele.
   • Correção sobre COMO O FORMATO FUNCIONA pra qualquer pessoa (ritmo, legenda, encaixe, tempo das cenas, QA, processo) → regra do FORMATO.
   • Correção sobre o GOSTO/IDENTIDADE do cliente (cor, fonte, tipo de b-roll do nicho dele, música dele, enquadramento da câmera dele, produto, preço) → regra do CLIENTE.
   • Na dúvida → CLIENTE (não contamina os outros clientes) e marque no RESULTADO.md como "candidata a valer pra todos".
   • Se a mesma regra já existir em outro cliente do mesmo formato ({', '.join(outros) or 'nenhum outro cliente usa esse formato ainda'}), suba pro FORMATO (com "origem": ["<Cliente>/<id>", ...]) e marque "promovida": "<id da regra no formato>" na regra de cada um desses clientes."""
        procurar = "no formato e no cliente"
    else:
        onde = f"ONDE GUARDAR: este modelo não pertence a nenhum formato do catálogo, então tudo vai na camada do CLIENTE ({regras_cli})."
        procurar = "no cliente"
    return f"""Você está no Estúdio (raiz: {RAIZ}). O João assistiu um vídeo produzido pelo Estúdio e deu FEEDBACK.

CLIENTE: {job['cliente']}   MODELO: {job['modelo']} (pasta {pasta_modelo})
VÍDEO: {job.get('saida') or job['saida_esperada']}   SANDBOX: {job['sandbox']}
DECISÃO DO JOÃO: {fb['decisao'].upper()}
FEEDBACK (palavras dele): \"\"\"{fb['texto']}\"\"\"

MATERIAL PRÓPRIO DO CLIENTE disponível:
{material_txt(cli)}
{POLITICA_MATERIAL}

Se o ajuste envolver identidade visual, leia a ficha ATUAL e compare com os defaults do motor;
aplique a paleta atual também aos cards pré-renderizados, regenerando-os. Não reutilize cards
com cores antigas. {musica}

O QUE FAZER (REGRA Nº 2 do CLAUDE.md — nunca cometer o mesmo erro duas vezes):
1. Leia {pasta_modelo}/aprendizado/regras.json e o {job['sandbox']}/RESULTADO.md pra entender o que foi feito.
2. O Estúdio já acrescentou a linha bruta do feedback em {pasta_modelo}/aprendizado/historico.jsonl. Agora interprete o feedback ponto a ponto (ele pode conter vários assuntos: SFX, música, b-roll, legenda…). Para CADA ponto durável (vale pra próximos vídeos), decida onde guardar:
   {onde}
   Antes de criar, PRIMEIRO procure ({procurar}) uma regra que já trate do mesmo assunto (mesma categoria/tema, mesmo que com outras palavras). Se existir, APRIMORE essa regra (reescreva texto/evitar incorporando o novo aprendizado, suba o peso se o João foi enfático, acrescente a data {hoje()} no texto) — NÃO crie uma duplicata. Só crie regra nova (id, categoria, peso, texto, evitar) se o assunto for realmente diferente de tudo que já existe. Se for pontual só deste vídeo, deixe apenas no histórico. TODA regra nova ou reescrita leva em `origem` a frase do João entre aspas; sem frase dele, não vira regra (fica só no RESULTADO.md). Ao final, diga no RESULTADO.md quais regras foram aprimoradas e quais criadas, e em qual camada (FORMATO ou CLIENTE). Se a regra mudar a identidade do modelo (cor, fonte, música, estrutura, política de b-roll, QA), atualize também {pasta_modelo}/ficha.json (esquema em app/ferramentas/ficha.py).{refazer}
4. Não peça confirmação: decida e execute até o fim.
""" + receita + GATE_APRENDI


# ───────────────────────── execução do Claude ─────────────────────────


def _detectar_saida(job, inicio, tipo):
    """Só reconhece saídas deste job; nunca captura um render paralelo do modelo."""
    esperado = RAIZ / job['saida_esperada']
    alvo = esperado.with_name(f"{job['slug']}-v{job.get('versao',1)+1}.mp4") if tipo=='feedback' else esperado
    if not alvo.is_file() or alvo.stat().st_mtime < inicio.timestamp():
        return False
    if tipo=='feedback':
        job.setdefault('versoes',[]).append({'versao':job.get('versao',1),'arquivo':job.get('saida'),'em':agora()})
        job['versao']=job.get('versao',1)+1
    job['saida']=rel(alvo)
    return True


def avisos_da_conferencia(job: dict) -> list[str]:
    """Avisos (português curto) que o qa/conferir.json da sandbox registrou; [] se não existe ou passou."""
    try:
        d = json.loads((RAIZ / job["sandbox"] / "qa/conferir.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    return [str(a) for a in (d.get("avisos") or [])] if d.get("ok") is False else []


def conferir_pos_render(job: dict) -> list[str]:
    """Vídeo gravado só vale como pronto com conferência: sem qa/conferir.json (ou com ok:false), roda o conferir_video.py aqui.
    Reprovou → job['avisos_conferencia'] e o Em andamento mostra "Conferir: ..." em vez de "Vídeo pronto". Motor próprio: só mede o
    dinamismo (parado demais, sem troca, poucas trocas) contra a régua do estilo; o resto é do render.py --conferir dele."""
    job.pop("avisos_conferencia", None)
    try:
        import formatos as _fmt
        est = _esteira(job)
        saida = RAIZ / (job.get("saida") or "")
        sb = RAIZ / job["sandbox"]
        if not saida.is_file() or not sb.is_dir():
            return []
        try:
            slug_fmt = (_fmt.do_job(job) or {}).get("slug")
        except Exception:
            slug_fmt = None
        if est and est.get("tipo") != "gravado":
            # motor próprio: a conferência dele (render.py --conferir) segue sozinha; só o dinamismo (G26) é medido aqui no mp4 final
            import conferir_video
            av_d, num_d = conferir_video.checar_dinamismo(saida, slug_fmt)
            try:
                qj = sb / "qa/conferir.json"
                d = json.loads(qj.read_text(encoding="utf-8")) if qj.is_file() else {}
                d.setdefault("numeros", {})["dinamismo"] = num_d
                if av_d:   # é isso que a barra de etapas lê (pipeline.avisos_da_conferencia): "Conferir: Parado demais..."
                    d["avisos"] = [str(m) for m in (d.get("motivos") or [])] + av_d
                    d["ok"] = False
                qj.parent.mkdir(parents=True, exist_ok=True)
                qj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:
                pass
            if av_d:
                job["avisos_conferencia"] = av_d
            return av_d
        q = sb / "qa/conferir.json"
        avisos = []
        if not (q.is_file() and json.loads(q.read_text(encoding="utf-8")).get("ok") is True):
            import conferir_video
            avisos = conferir_video.conferir(saida, sb, slug_fmt)["avisos"]
        rm = sb / "RESULTADO.md"
        if rm.is_file() and re.search(r"n[ãa]o rodei o /?watch", rm.read_text(encoding="utf-8", errors="replace"), re.I):
            avisos.append("Falta a conferência com /watch")
    except Exception:
        return []
    if avisos:
        job["avisos_conferencia"] = avisos
    return avisos


def rodar(cli: str, slug: str) -> dict:
    job = carregar(cli, slug)
    if not job:
        raise ValueError("job não existe")
    if job.get("rodando") or job.get("status") == "na_fila":
        return job
    return renderizar(cli, slug)


def parar(cli: str, slug: str) -> bool:
    import fila
    return fila.cancelar(cli, slug)


def log_atual(job: dict, tail: int = 4000) -> str:
    exes = job.get("execucoes") or []
    if not exes:
        return ""
    p = job["_pasta"] / exes[-1]["log"]
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="replace")
    return txt[-tail:]


# ───────────────────────── feedback → aprendizado ─────────────────────────

def _registrar_musica_reprovada(job: dict, motivo: str) -> None:
    """A faixa que o João reprovou (a escolhida no PLANO.json) vai pra acervo/musicas-reprovadas.jsonl e não volta pro cliente."""
    try:
        import uso_midia
        m = (plano(job) or {}).get("musica") or {}
        op = next((o for o in (m.get("opcoes") or []) if o.get("id") == m.get("escolha")), None) or {}
        arq = op.get("arquivo")
        if not arq or m.get("sem"):
            return
        f = next((x for x in (RAIZ / job["sandbox"] / arq, RAIZ / arq) if x.is_file()), None)
        if not f:
            return
        append_jsonl(RAIZ / "acervo/musicas-reprovadas.jsonl", {
            "cliente": job["cliente"], "chave": uso_midia.chave_de(f), "arquivo": f.name, "slug": op.get("acervo_slug") or "",
            "titulo": op.get("titulo") or "", "motivo": motivo[:200], "data": hoje(), "job": job.get("slug")})
    except Exception:
        pass


def feedback(cli: str, slug: str, decisao: str, texto: str, categoria: str = "geral") -> dict:
    """Registra o feedback no aprendizado DO MODELO usado (historico.jsonl) e, se houver texto ou
    pedido de ajuste, dispara o Claude pra consolidar regra durável / refazer."""
    job = carregar(cli, slug)
    if not job:
        raise ValueError("job não existe")
    if job.get('rodando') or job.get('status') in ('na_fila','arquivado','exportado'):
        raise ValueError('Aguarde a execução terminar antes de enviar feedback.')
    if decisao not in ('aprovado','ajustar') or not job.get('saida'):
        raise ValueError('É preciso um vídeo final para revisar.')
    if decisao == 'ajustar' and not (texto or '').strip():
        raise ValueError('Conte o que deve ser ajustado no vídeo.')
    import ia
    if (texto or '').strip() or decisao=='ajustar':
        if not ia.disponivel():raise ValueError('Configure o motor de IA antes de enviar um ajuste ou consolidar aprendizado.')
    c = _cliente(cli)
    mod = _modelo(c, job["modelo"])
    if (categoria or "").strip() in ("", "geral"):   # "A IA descobre": o assunto sai pelas palavras do João
        import regras as _regras
        categoria = _regras.categoria_do_texto(texto)
    fb = {"em": agora(), "decisao": decisao, "texto": (texto or "").strip(), "categoria": categoria}
    job.setdefault("feedbacks", []).append(fb)
    linha = {
        "tipo": "feedback" if fb["texto"] else "aprovacao",
        "categoria": categoria,
        "texto": fb["texto"] or f"Vídeo '{job['titulo']}' aprovado sem ressalvas.",
        "origem": "usuario", "createdAt": hoje(), "decisao": decisao,
        "job": f"app/jobs/{cli}/{slug}", "video": job.get("saida"),
    }
    append_jsonl(mod["pasta"] / "aprendizado" / "historico.jsonl", linha)
    if decisao == "ajustar" and re.search(r"m[úu]sica|trilha|cl[ií]ch[êe]", fb["texto"], re.I):
        _registrar_musica_reprovada(job, fb["texto"])
    job["status"] = "aprovado" if decisao == "aprovado" and not fb["texto"] else "feedback"
    salvar(job)
    if fb["texto"] or decisao == "ajustar":
        _disparar(job, prompt_feedback(job, fb), "feedback")
    return carregar(cli, slug)


# ═════════════════════ ETAPAS: análise → plano aprovado → prévias → render ═════════════════════
# O João não quer "produzir e ver": ele quer ver os TAKES propostos (b-roll/card/punch por trecho
# da fala, com frames), escolher, ver como ficaria, e só então renderizar. PLANO.json na sandbox.

ETAPAS = ["novo", "analisando", "plano", "plano_aprovado", "previas", "renderizando", "concluido", "feedback", "aprovado", "erro"]

ESQUEMA_PLANO = """{
  "resumo": "1-2 frases sobre o que o vídeo fala e o ângulo",
  "transcricao": [{"t0": 0.0, "t1": 3.2, "texto": "trecho da fala"}],
  "musica": {
    "opcoes": [
      {"id": "m1", "arquivo": "work/musica/faixa.mp3", "inicio_s": 0, "fim_s": 20, "fonte": "do-cliente|acervo|mixkit|jamendo|soundcloud",
       "motivo": "por que o clima casa com a fala", "titulo": "nome da faixa", "acervo_slug": "só se veio do acervo",
       "url": "página da faixa", "autor": "", "licenca": ""}
    ],
    "escolha": "m1",
    "consulta_acervo": [{"slug": "slug", "motivo": "adequação ao vídeo"}],
    "recentes_evitadas": []
  },
  "sfx": [{"id": "s1", "som": "whoosh", "t": 4.0, "beat": "b1", "arquivo": "work/sfx/whoosh.mp3", "motivo": "entrada do card", "ligado": true}],
  "sfx_ligado": true,
  "beats": [
    {"id": "b1", "inicio": 4.0, "fim": 9.0, "fala": "a frase exata dita nessa janela", "tipo": "broll|card|punch|impacto|insert",
     "intencao": "o que ilustrar e por quê (conexão com o público)",
     "texto_card": "só para tipo card/impacto: PARECE *MELHOR*",
     "opcoes": [
       {"id": "b1-1", "titulo": "nome curto", "fonte": "youtube|pexels|pixabay|acervo|site|commons|nasa", "url": "https://...",
        "arquivo": "brolls/xxx.mp4", "sheet": "brolls/xxx-sheet.jpg", "gif": "brolls/xxx.gif", "trecho": "12-17",
        "motivo": "por que essa opção serve a essa fala", "verificado": "sem watermark, sem rosto, 1080p"}
     ],
     "escolha": null, "comentario": ""}
  ],
  "observacoes": "dúvidas ou decisões que o João deve olhar"
}"""


TAMANHOS = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080", "4:5": "1080x1350"}


def _tamanho(job: dict) -> str:
    """Tamanho do vídeo pela proporção do formato (a VSL é 16:9: 1920x1080). Sem formato: 1080x1920 (Reels)."""
    try:
        import formatos as _fmt
        return TAMANHOS.get(str((_fmt.do_job(job) or {}).get("proporcao") or "").strip(), "1080x1920")
    except Exception:
        return "1080x1920"


def plano(job: dict) -> dict | None:
    return ler_json(RAIZ / job["sandbox"] / "PLANO.json")


def salvar_plano(job: dict, dados: dict) -> None:
    gravar_json(RAIZ / job["sandbox"] / "PLANO.json", dados)


def prompt_analise_essencial(job: dict) -> str:
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    sb = job["sandbox"]
    return f"""ETAPA: PLANEJAR A EDIÇÃO ESSENCIAL DO VÍDEO BRUTO. Não renderizar.
Cliente: {job['cliente']}. Modelo: {rel(mod['pasta'])}.
Bruto: {job['bruto']}. Sandbox: {sb}. Briefing: {job.get('briefing', '')}.
Materiais anexados: {job.get('materiais', [])}. Acervo separado: {job.get('brolls', [])}.
Leia ficha.json, README.md e aprendizado/regras.json do modelo.
Use o corte aprovado {job.get('corte_aplicado', {}).get('arquivo') or job['bruto']}.
Reutilize a transcrição correspondente se existir; caso contrário transcreva com tempos por palavra.
Não reutilize tempos do original quando houver corte. Salve work/words.json.
Planeje ritmo, enquadramento, legendas legíveis e destaques ancorados nas palavras reais.
Preserve o sentido e a ordem da fala. Não invente palavras, frases ou provas.
Não busque b-rolls, não pesquise fora, não baixe mídia e não use APIs de geração.
Materiais já anexados podem ser propostos quando tiverem relação clara com a fala.
{MUSICA_ESSENCIAL.format(cliente=job['cliente'], slug=job['slug'])}Explique as decisões e pontos de revisão em ANALISE.md. Salve PLANO.json neste esquema:
{ESQUEMA_PLANO}
Use opcoes: [] para cards/punches. Só proponha opções de mídia já disponível na sandbox.
Encerre ao salvar o plano; o usuário revisará os trechos antes das prévias ou do render.
"""


def prompt_analise(job: dict, ajuste: str = "") -> str:
    if _esteira(job):
        return prompt_esteira(job, "ate_aprovacao", ajuste=ajuste)
    if job.get("escopo_edicao") == "essencial":
        import edicao
        return prompt_analise_essencial(job) + edicao.instrucao(job)
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    pasta_modelo = rel(mod["pasta"])
    sb = job["sandbox"]
    brolls_txt = "\n".join(f"  - {b['arquivo']} — {b.get('titulo')} (tags: {', '.join(b.get('tags', []))})"
                           for b in job.get("brolls", [])) or "  (nenhum)"
    return f"""Você está no Estúdio (raiz: {RAIZ}). ETAPA 1 de um vídeo pelo Estúdio: ANALISAR e PROPOR OS TAKES. NÃO renderize o vídeo final nesta etapa.

CLIENTE: {job['cliente']} (pasta {rel(cli['pasta'])})   MODELO: {job['modelo']} (pasta {pasta_modelo})
BRUTO: {job['bruto']}   SANDBOX: {sb}   BRIEFING: {job.get('briefing') or '(sem briefing)'}{secao_briefing(job)}
B-ROLLS JÁ SEPARADOS DO ACERVO:
{brolls_txt}
CAMADAS EXTRAS PEDIDAS (modelos-camada do mesmo cliente a somar nesta edição): {', '.join(job.get('camadas') or []) or '(nenhuma — mas se o briefing pedir algo como "switches do iPhone"/"hook de texto", trate como camada)'}

O QUE FAZER:
0. TRANSCRIÇÃO PRIMEIRO, sempre: nada de propor beat antes de ter o words.json. A transcrição vai inteira no PLANO.json (campo transcricao) pro João ler.
1. Leia {pasta_modelo}/ficha.json, {pasta_modelo}/aprendizado/regras.json INTEIRO e {pasta_modelo}/README.md. Regras de outros modelos não valem.
2. Prepare o bruto como o modelo exige (ex.: {sb}/work/joao.mp4 {_tamanho(job)}, rotação conferida) — SE já existir {sb}/work/joao.mp4 vindo do corte do bruto (etapa 0), use ESSE arquivo e a transcrição dele, não o bruto original — e transcreva com GROQ (GROQ_API_KEY no app/.env; se {rel(cli['pasta'])}/.env tiver uma, ela vale) salvando {sb}/work/words.json. Não estime tempos: use o words.json.
2c. CITAÇÃO COM ÁUDIO (só quando o briefing pedir, ex.: "depois que eu falo X, põe o Lula falando isso"):
   use `python3 app/ferramentas/fala.py missao "<quem>" "<o que ele diz>" --limite 5` — ele busca vídeos,
   baixa a LEGENDA com tempos e devolve o SEGUNDO EXATO em que a frase é dita, com link `?t=`. Confirme com
   `fala.py achar <url> "<frase>"` e baixe só o trecho com `fala.py cortar <url> <t0> <t1> <saida.mp4>`.
   O beat vira tipo "citacao" com "com_audio": true e o bloco "citacao" preenchido (quem, frase, fonte, t0/t1).
   Se o João pedir várias épocas/pessoas ("no primeiro mandato", "em 2018", "puxa do Trump também"), faça uma
   missão por pedido e traga um beat de citação para cada, em ordem cronológica, mostrando a repetição da narrativa.
   NUNCA invente a frase: só entra o que aparece na legenda/transcrição da fonte, com o tempo conferido.

3. ENTIDADES AUTOMÁTICAS: varra a transcrição e liste todo nome próprio, marca, produto, lugar, jornal, notícia e número citado (ex.: "Lula", "Trump", "Folha", "Clinicorp"). Para cada um, a busca é AUTOMÁTICA e obrigatória — o João não vai pedir; ele espera que "falou Lula → aparece o Lula". FONTE LITERAL primeiro: se a fala cita uma pessoa, marca, produto, jornal, notícia ou dado, a opção principal tem que ser a FONTE REAL (vídeo da pessoa, print da matéria com manchete legível, tela do site, gráfico oficial) — só depois vêm cenas ilustrativas.
   Divida a fala em trechos e proponha os BEATS conforme a ficha e as regras do modelo (ritmo, tipos permitidos, política de b-roll). Para cada beat de b-roll traga ATÉ 3 OPÇÕES REAIS, seguindo a skill {rel(SKILL_BROLL)}: a busca principal é FORA, com get-brolls em todas as fontes (YouTube, Pexels, Pixabay, Commons, NASA — varie as fontes entre os beats) e site/canal oficial quando a fala cita marca/produto; os itens do acervo que o João separou entram como opção, e se nada foi separado o acervo é só mais um lugar pra olhar, nunca o único. Para CADA opção gere prévia visual dentro da sandbox: um contact sheet (12 frames) e um GIF curto, com caminhos RELATIVOS à sandbox (ex.: brolls/b1-1-sheet.jpg, brolls/b1-1.gif). Use `~/.claude/skills/get-brolls/.venv/bin/python ~/.claude/skills/get-brolls/scripts/gb.py preview --project {sb}` (os arquivos saem em {sb}/brolls/previews/ — referencie esse caminho) ou ffmpeg direto para clipes do acervo. OLHE os frames antes de propor: reprove watermark, rosto indevido, legenda queimada, baixa qualidade; escreva no campo "verificado" o que conferiu.
4. Para beats de card/impacto proponha o texto_card (com *palavra* destacada) no tempo exato da fala. Para punch, só a janela. Para cada CAMADA extra pedida, leia a ficha/regras da pasta dela (mesmo cliente, modelos/<camada>/) e proponha beats do tipo "camada" com o campo "camada": "<modelo>" e o conteúdo dela (ex.: switches: lista de labels+emoji e o tempo em que cada um liga), sem opções de b-roll.
5. Escolha a música conforme a política abaixo.
{POLITICA_MUSICA}
{POLITICA_BROLL}
6. Escreva {sb}/PLANO.json EXATAMENTE neste esquema (JSON válido, UTF-8):
{ESQUEMA_PLANO}
6b. ORDEM DAS OPÇÕES: em cada beat, a opção que você recomenda vai SEMPRE em primeiro lugar (b1-1 é a recomendada). O "Seguir direto" (sem o João escolher) usa a 1ª opção; se quiser dizer qual é a recomendada, marque também "recomendada": "<id>" no beat.
7. Não peça confirmação. Ao terminar, escreva também {sb}/ANALISE.md com um resumo em português do que propôs e por quê (o João vai ler na tela).
{instrucao_referencia(job)}"""


def prompt_previa(job: dict) -> str:
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    sb = job["sandbox"]
    return f"""Você está no Estúdio (raiz: {RAIZ}). ETAPA 3 de um vídeo pelo Estúdio: PRÉVIAS DOS BEATS APROVADOS ("como ficaria"). NÃO é o render final.

CLIENTE: {job['cliente']}   MODELO: {job['modelo']} (pasta {rel(mod['pasta'])})   SANDBOX: {sb}
O João aprovou os takes em {sb}/PLANO.json (campo "escolha" de cada beat = id da opção escolhida; "comentario" pode pedir ajuste; escolha null = beat rejeitado/sem beat; se pediu "buscar outro", traga exatamente 3 opções novas para esse beat e atualize o PLANO.json mantendo as escolhas dos outros).
{POLITICA_BROLL}

O QUE FAZER:
1. Leia ficha.json, regras.json e README do modelo. Monte os beats aprovados no formato do modelo (ex.: --beats do gerar.sh).
2. Para CADA beat aprovado renderize uma PRÉVIA CURTA com o pipeline real do modelo (legenda + faixa/card/punch como no final), cobrindo a janela do beat com ~1s de folga antes e depois, em {sb}/previas/<id-do-beat>.mp4 ({_tamanho(job)}, pode ser CRF alto pra ser rápido). Se o modelo não permitir renderizar só uma janela, renderize o vídeo inteiro em rascunho ({sb}/previas/rascunho.mp4) e corte as janelas com ffmpeg a partir dele.
3. Salve em cada beat do PLANO.json o campo "previa": "previas/<id>.mp4" e escreva {sb}/PREVIAS.md com o comando usado e observações.
4. Não peça confirmação; execute até o fim.
"""


def _prompt_producao_com_plano(job: dict) -> str:
    if _esteira(job):
        return prompt_esteira(job, "depois")
    base = prompt_producao(job)
    if plano(job):
        base += f"""
AJUSTES PEDIDOS PELO JOÃO NOS TAKES (campo "comentario" de cada beat): aplique no render quando for
ajuste de execução (trecho do clipe, enquadramento, duração, volume). Se for pedido de OUTRO material e o
beat já tem escolha, mantenha a escolha e faça o melhor com ela; não invente busca nova nesta etapa.

PLANO APROVADO: {job['sandbox']}/PLANO.json — use EXATAMENTE as escolhas do João (campo "escolha" de cada beat, "comentario" com ajustes pedidos, música escolhida). Preserve TODOS os arquivos das opções e suas prévias, inclusive os não escolhidos; o usuário poderá trocar depois. Não troque um take aprovado por outro. Beats com escolha null não entram. Se houver {job['sandbox']}/PREVIAS.md, parta do comando de lá.
"""
    return base


def guardar_rodada(job: dict) -> Path | None:
    """Formato com esteira: antes de uma análise nova, guarda o cenas.json da rodada anterior em work/rodadas/ (cópia;
    nada some da sandbox). O storyboard refeito do Vídeo 1 V2 do Cliente4 saiu em 2 min editando o cenas.json da prova
    anterior, sem buscar cena de fora nova: o prompt manda montar do zero e o anterior fica só como referência."""
    try:
        sb = RAIZ / job["sandbox"]
        est = _esteira(job)
        cenas = sb / ((est or {}).get("cenas") or "cenas.json")   # o arquivo do vídeo do formato (padrão cenas.json)
        if not (est and cenas.is_file()):
            return None
        destino = ensure(sb / "work" / "rodadas") / f"{cenas.stem}-{now_slug()}{cenas.suffix}"
        shutil.copy2(cenas, destino)
        return destino
    except Exception as e:
        print(f"rodada de {job.get('cliente')}/{job.get('slug')}: {e}", file=sys.stderr)
        return None


def _guardar_plano_gravado(job: dict) -> bool:
    """Vídeo gravado (sem esteira): analisar de novo é refazer. Sem tirar o PLANO.json do caminho a IA escrevia "já estava pronto, não
    refiz nada" e o número de cenas / o pedido novo nunca valia (29-out-2026, Teste fluxo faixa). Move pra work/rodadas/ (nada some)."""
    try:
        sb = RAIZ / job["sandbox"]
        if not (sb / "PLANO.json").is_file():
            return False
        dest = ensure(sb / "work" / "rodadas")
        ts = now_slug()
        for nome in ("PLANO.json", "ANALISE.md", "storyboard.jpg"):
            if (sb / nome).is_file():
                shutil.move(str(sb / nome), str(dest / f"{Path(nome).stem}-{ts}{Path(nome).suffix}"))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"plano de {job.get('cliente')}/{job.get('slug')}: {e}", file=sys.stderr)
        return False


def analisar(cli: str, slug: str, ajuste: str = "") -> dict:
    """Monta o storyboard. Com `ajuste` (formato com esteira): refaz só as cenas que o João citou, sem rodada nova."""
    job = carregar(cli, slug)
    if not job: raise ValueError('Vídeo não encontrado.')
    if job['status'] in ('exportado','arquivado'): raise ValueError('Este vídeo já foi exportado.')
    if job.get("rodando") or job.get("status") == "na_fila":
        return job
    if corte_rodando(job):                 # o corte automático ainda está rodando: o storyboard sai assim que ele terminar
        job["analisar_depois"] = ajuste or True; salvar(job)
        return job
    guardar_rodada(job)
    refaz = ""
    if not _esteira(job) and not ajuste and _guardar_plano_gravado(job):
        refaz = ("\n\nREFAZER (o João pediu a análise de novo): o PLANO.json, o ANALISE.md e o storyboard.jpg da rodada anterior foram guardados em "
                 "work/rodadas/ só como referência. Monte o plano NOVO do zero com as preferências de agora (número de cenas, estilo); "
                 "não copie nem restaure o plano antigo e não responda que \"já estava pronto\".")
    _disparar(job, prompt_analise(job, ajuste) + refaz, "analise", "plano")
    return job


def tentar_de_novo(cli: str, slug: str) -> dict:
    """"Tentar de novo" de um vídeo que parou com erro: repete a última etapa (a mesma função do botão dela)."""
    job = carregar(cli, slug)
    if not job: raise ValueError('Vídeo não encontrado.')
    if job.get("rodando") or job.get("status") == "na_fila":
        raise ValueError('Este vídeo já está rodando ou na fila.')
    ultimo = ((job.get('execucoes') or [{}])[-1] or {}).get('tipo') or 'analise'
    if ultimo in ('analise', 'rebusca'): return analisar(cli, slug)
    if ultimo == 'previas': return gerar_previas(cli, slug)
    return renderizar(cli, slug)   # producao e feedback


def gerar_previas(cli: str, slug: str) -> dict:
    job = carregar(cli, slug)
    if not job: raise ValueError('Vídeo não encontrado.')
    if job['status'] in ('exportado','arquivado'): raise ValueError('Este vídeo já foi exportado.')
    if job.get("rodando") or job.get("status") == "na_fila":
        return job
    import edicao
    edicao.validar(job, plano(job))
    _disparar(job, prompt_previa(job), "previas", "plano_aprovado")
    return job


def renderizar(cli: str, slug: str) -> dict:
    job = carregar(cli, slug)
    if not job: raise ValueError('Vídeo não encontrado.')
    if job['status'] in ('exportado','arquivado'): raise ValueError('Este vídeo já foi exportado.')
    if job.get("rodando") or job.get("status") == "na_fila":
        return job
    p = plano(job)
    if not p or not p.get('aprovado_em'):
        raise ValueError('Salve suas escolhas antes de renderizar.')
    import edicao
    edicao.validar(job, p)
    import takes
    takes.validar_escolhas(job, p)
    # Comentário NÃO bloqueia: pode ser elogio, observação ou um ajuste que o render aplica
    # (ex.: "esse mas mais no fim"). Ele vai pro prompt do render como instrução.
    _disparar(job, _prompt_producao_com_plano(job), "producao")
    return job


def _slug_do_acervo(op: dict) -> str:
    """Slug do item do acervo de onde a faixa veio (acervo_slug, acervo, ou o caminho acervo/itens/<slug>/...)."""
    s = op.get("acervo_slug") or (op.get("acervo") if isinstance(op.get("acervo"), str) else "")
    if not s:
        m = re.search(r"acervo/itens/([^/]+)/", str(op.get("arquivo") or ""))
        s = m.group(1) if m else ""
    return s if s and Path(s).name == s else ""


META_MUSICA = ("opcoes", "escolha", "sem", "clima", "consulta_acervo", "recentes_evitadas")


def _escolher_musica(job: dict, p: dict, musica) -> None:
    """musica: 'sem' ou {'sem': True} (sem música) | id de musica.opcoes | a opção inteira (dict da tela; se não
    estiver no plano, entra nas opções) | None (não mexe). A faixa escolhida fica no topo de musica (arquivo,
    fonte, inicio_s…), que é onde a tela, o acervo e o "recentes" procuram; a que estava lá vira alternativa."""
    if musica is None:
        return
    m = dict(p["musica"]) if isinstance(p.get("musica"), dict) else {}
    opcoes = [o for o in m.get("opcoes") or [] if isinstance(o, dict)]
    if not m.get("sem") and any(m.get(k) for k in ("arquivo", "opcao", "url")):   # a faixa do topo não se perde
        atual = {k: v for k, v in m.items() if k not in META_MUSICA}
        atual["id"] = str(atual.get("id") or (m.get("escolha") if isinstance(m.get("escolha"), str) else "") or "plano")
        if not any(str(o.get("id")) == atual["id"] for o in opcoes):
            opcoes.insert(0, atual)
    meta = {k: m[k] for k in META_MUSICA if k in m and k not in ("opcoes", "escolha", "sem")}
    if musica == "sem" or (isinstance(musica, dict) and musica.get("sem")):
        p["musica"] = {**meta, "opcoes": opcoes, "escolha": {"sem": True}, "sem": True}
        return
    pedido = ({k: v for k, v in musica.items() if k not in ("usada_txt", "opcoes", "sem", "escolha") and v not in (None, "")}
              if isinstance(musica, dict) else {})
    ident = str(pedido.get("id") or "") if isinstance(musica, dict) else str(musica)
    op = next((o for o in opcoes if str(o.get("id")) == ident), None) if ident else None
    if op is not None and pedido.get("trechos") and not op.get("trechos"):
        op["trechos"] = pedido["trechos"]   # a tela amarrou a troca de faixa do cenas.json (364 → 1154) a esta opção
    if op is None:
        if not any(pedido.get(k) for k in ("arquivo", "previa", "url")):
            raise ValueError("Música inválida: " + (ident or "sem arquivo"))
        op = {**pedido, "id": ident or f"m{len(opcoes) + 1}"}
        opcoes.append(op)
    faixa = {k: v for k, v in op.items() if k not in META_MUSICA and v not in (None, "")}
    p["musica"] = {**meta, **faixa, "opcoes": opcoes, "escolha": op["id"]}
    s = _slug_do_acervo(op)
    if s:
        _acervo.registrar_uso(s, job["cliente"], job["modelo"], job["slug"])


def _escolha_da_ia(p: dict):
    """A tela não mexeu na música: a faixa que a IA escolheu (só em musica.opcoes) sobe pro topo ao aprovar, pra o
    "recentes" (não repetir faixa) e o acervo enxergarem. Já no topo, sem música ou sem escolha: None (não mexe)."""
    m = p.get("musica")
    if not isinstance(m, dict) or m.get("sem") or not isinstance(m.get("escolha"), str) or any(m.get(k) for k in ("arquivo", "opcao", "url")):
        return None
    return m["escolha"] if any(isinstance(o, dict) and str(o.get("id")) == m["escolha"] for o in m.get("opcoes") or []) else None


def _ligar_sfx(p: dict, sfx) -> None:
    """sfx: lista dos ids ligados ([] = nenhum efeito) | {'ligado': chave geral, 'ativos': [ids]} (a tela) | None.
    Efeito sem id é o 'sfx-<posição>', como a tela mostra. Id que não existe no plano é ignorado."""
    if sfx is None:
        return
    if isinstance(sfx, dict):
        ids, geral = {str(x) for x in sfx.get("ativos") or []}, bool(sfx.get("ligado", True))
    else:
        ids = {str(x) for x in sfx}
        geral = bool(ids)
    for i, o in enumerate(p.get("sfx") if isinstance(p.get("sfx"), list) else []):
        if isinstance(o, dict):
            o["ligado"] = str(o.get("id") or f"sfx-{i}") in ids
    p["sfx_ligado"] = geral


def _storyboard_da_ferramenta(job: dict) -> None:
    """Formato sem esteira: refaz o storyboard.jpg pela ferramenta (nunca desenhado à mão). Nunca trava nem derruba.
    Formato de vídeo gravado com storyboard próprio (ex.: o storyboard.py do Cinematográfico) não é tocado: a ferramenta
    genérica escreveria por cima do dele; a IA refaz o dele na rodada."""
    try:
        if _esteira(job):
            return   # formato com esteira: o storyboard é do motor dele
        import formatos as _fmt
        if _fmt.storyboard_proprio(_fmt.do_job(job)):
            return
        ferramenta = RAIZ / "app" / "ferramentas" / "storyboard.py"
        if not ferramenta.is_file():
            return
        subprocess.run([sys.executable, str(ferramenta), str(RAIZ / job["sandbox"])], cwd=str(RAIZ),
                       capture_output=True, timeout=60)
    except Exception:
        pass


def aprovar_plano(cli: str, slug: str, escolhas: dict, comentarios: dict, obs: str = "", musica=None, sfx=None) -> dict:
    """Salva as escolhas do João. musica: 'sem' | id da opção | None (a tela também manda {'sem': True} ou a opção
    inteira); sfx: ids dos efeitos ligados | None (a tela manda {'ligado', 'ativos'})."""
    job = carregar(cli, slug)
    if not job or job.get('rodando') or job.get('status') in ('na_fila','arquivado','exportado'):
        raise ValueError('Este plano não pode ser editado durante uma execução ou depois da exportação.')
    p = plano(job) or {}
    for b in p.get("beats", []):
        e = escolhas.get(b["id"])
        if e not in (None, '', 'nenhum', b['id']) and e not in [o.get('id') for o in b.get('opcoes',[])]:
            raise ValueError('Take inválido: '+str(e))
        b["escolha"] = None if e in (None, "", "nenhum") else e
        b["comentario"] = (comentarios.get(b["id"]) or "").strip()
    _escolher_musica(job, p, musica if musica is not None else _escolha_da_ia(p))
    _ligar_sfx(p, sfx)
    p["aprovado_em"] = agora()
    p["observacoes_joao"] = obs
    salvar_plano(job, p)
    job["status"] = "plano_aprovado"; salvar(job)
    linha = {"em": agora(), "escolhas": escolhas, "comentarios": comentarios, "obs": obs}
    if musica is not None:
        linha["musica"] = musica
    if sfx is not None:
        linha["sfx"] = sfx if isinstance(sfx, dict) else list(sfx)
    append_jsonl(_pasta_job(cli, slug) / "decisoes.jsonl", linha)
    _storyboard_da_ferramenta(job)
    return carregar(cli, slug)


def prompt_rebusca(job: dict, beat_id=None) -> str:
    cli = _cliente(job["cliente"])
    mod = _modelo(cli, job["modelo"])
    sb = job["sandbox"]
    p = plano(job) or {}
    pend = [b for b in p.get("beats", []) if not b.get("escolha") or (b.get("comentario") or "").strip()]
    if beat_id: pend = [b for b in p.get("beats", []) if b["id"] == beat_id]
    lista = "\n".join(f"  - {b['id']} ({b['inicio']}-{b['fim']}s) fala: \"{b.get('fala','')}\" — escolha atual: {b.get('escolha') or 'NENHUMA'} — pedido do João: \"{b.get('comentario') or '(sem texto: as opções não serviram, traga outras diferentes)'}\""
                      for b in pend) or "  (nenhum pendente)"
    return f"""Você está no Estúdio (raiz: {RAIZ}). ETAPA 2b de um vídeo pelo Estúdio: BUSCAR OUTRAS OPÇÕES para os takes que o João não aprovou. NÃO faça o render final. Gere as prévias visuais das opções.

CLIENTE: {job['cliente']}   MODELO: {job['modelo']} (pasta {rel(mod['pasta'])})   SANDBOX: {sb}
PLANO: {sb}/PLANO.json (mantenha TUDO que já está aprovado; só mexa nos beats abaixo)
BEATS A REBUSCAR:
{lista}

O QUE FAZER:
1. Leia ficha.json e regras.json do modelo e a skill {rel(SKILL_BROLL)}.
2. Para cada beat acima, siga a direção que o João escreveu (se escreveu) e traga ATÉ 3 opções NOVAS, diferentes das anteriores, buscadas fora em TODAS as fontes (YouTube, Pexels, Pixabay, Commons, NASA, site/canal oficial); varie a fonte. Gere contact sheet + GIF de cada uma na sandbox e OLHE os frames (watermark, rosto indevido, legenda queimada, qualidade); preencha "verificado".
Se uma fonte não retornar mídia utilizável, registre em buscas_descartadas; nunca invente uma opção nem coloque um registro de consulta em opcoes. Propostas de IA ficam em geracao_sugerida até a aprovação da geração.
2b. As novas opções não podem repetir vídeos rejeitados nem vídeos já escolhidos em outro beat.
{POLITICA_BROLL}
3. Se o comentário for um pedido de ajuste de uma opção já escolhida (ex.: "esse mas mais no fim do clipe"), ajuste o trecho/opção e mantenha a escolha.
4. Atualize {sb}/PLANO.json: nesses beats, substitua "opcoes" pelas novas (pode manter a anterior se o João não a rejeitou explicitamente), zere "escolha" e "comentario". Se o comentário disser que não quer beat ali, remova o beat. Escreva um resumo curto em {sb}/ANALISE.md (acrescente uma seção "Rebusca <data>").
5. Não peça confirmação; execute até o fim.
"""


def rebuscar(cli: str, slug: str, beat_id=None) -> dict:
    job = carregar(cli, slug)
    if not job: raise ValueError('Vídeo não encontrado.')
    if job['status'] in ('exportado','arquivado'): raise ValueError('Este vídeo já foi exportado.')
    if job.get("rodando") or job.get("status") == "na_fila":
        return job
    _disparar(job, prompt_rebusca(job, beat_id), "rebusca", "plano")
    _storyboard_da_ferramenta(job)
    return job


def apagar(cli: str, slug: str, lote: bool = False, confirmar: bool = False) -> dict:
    """Apaga TUDO desse vídeo pelo caminho único (saidas.apagar_video): saída em output/, job, sandbox, versões, registro do
    Em andamento, briefing, miniatura e metadados. Recusa (ValueError) se estiver rodando ou se for referência."""
    import saidas
    r = saidas.apagar_video(cli, slug, lote=lote, confirmar=confirmar)
    if r["recusados"] and not r["apagados"]:
        raise ValueError(r["recusados"][0]["motivo"])
    return r


def itens_para_acervo(job):
    from arquivo import seguro
    sb=seguro(RAIZ/job['sandbox']);p=plano(job) or {};itens=[];seen=set()
    def add(o,beat='',fala='',default_id=''):
        arq=o.get('arquivo') or o.get('opcao')
        if not arq:return
        for candidate in (sb/arq,RAIZ/arq,sb.parent/arq):
            try:q=seguro(candidate)
            except ValueError:continue
            if q.is_file():break
        else:return
        if str(q) in seen:return
        if q.suffix.lower() not in _acervo.VIDEO_EXTS | _acervo.IMAGEM_EXTS | _acervo.AUDIO_EXTS:return
        seen.add(str(q))
        itens.append(dict(id=o.get('id') or default_id or make_slug(q.stem),tipo=_acervo._tipo(q.suffix.lower()),
            titulo=o.get('titulo') or q.stem,arquivo=rel(q),fonte=o.get('url') or o.get('fonte',''),autor=o.get('autor',''),
            licenca=o.get('licenca',''),motivo=o.get('motivo',''),descricao=o.get('descricao') or o.get('motivo',''),
            fala=fala or o.get('fala',''),beat=beat or o.get('beat',''),tags=o.get('tags',[]),
            thumb=rel(sb/o['sheet']) if o.get('sheet') and (sb/o['sheet']).is_file() else None))
    for b in p.get('beats',[]):
        for o in b.get('opcoes',[]):
            if o.get('id')==b.get('escolha'):add(o,b['id'],b.get('fala',''))
        if b.get('escolha') and b.get('arquivo'):add(b,b['id'],b.get('fala',''))
    m=p.get('musica')
    if isinstance(m,dict) and not m.get('sem'):   # a faixa escolhida (musica.escolha → musica.opcoes) ou o formato antigo
        op=next((o for o in m.get('opcoes') or [] if isinstance(o,dict) and o.get('id')==m.get('escolha')),None) if isinstance(m.get('escolha'),str) else None
        add(op or m,'musica',default_id='musica')
    if p.get('sfx_ligado',True) is not False:
        for i,o in enumerate(p.get('sfx',[])):
            if isinstance(o,dict) and o.get('ligado',True) is not False:add(o,'sfx',default_id='sfx-'+str(i))
    for i,o in enumerate((ler_json(sb/'RESULTADO.json',{}) or {}).get('materiais_usados',[])):
        if isinstance(o,dict):add(o,default_id='material-'+str(i))
    return itens


def guardar_no_acervo(job, ids, tags, titulos=None, descricoes=None):
    n=0; titulos=titulos or {};descricoes=descricoes or {}
    saved=job.setdefault('acervo_mapa',{})
    for it in itens_para_acervo(job):
        if it['id'] not in ids or it['id'] in saved:continue
        m=_acervo.adicionar_arquivo(RAIZ/it['arquivo'],titulos.get(it['id']) or it['titulo'],tags.get(it['id'],it.get('tags',[])),
            fonte=it['fonte'],autor=it['autor'],licenca=it.get('licenca',''),observacao=it.get('motivo',''),origem_tipo='estudio-job',
            extra={'descricao':descricoes.get(it['id']) or it.get('descricao',''), 'fala':it.get('fala',''),
                   'usos':[{'cliente':job['cliente'],'modelo':job['modelo'],'job':job['slug'],'em':hoje(),'beat':it['beat']}]})
        saved[it['id']]=m['slug'];n+=1
    job['acervo_itens']=list(saved.values());salvar(job)
    return n


def arquivo_da_opcao(job: dict, beat: dict, op: dict) -> Path | None:
    sb = RAIZ / job["sandbox"]
    cands = []
    if op.get("arquivo"): cands.append(sb / op["arquivo"])
    if beat.get("escolha") == op.get("id"): cands.append(sb / "brolls" / "clips" / f"{beat['id']}-clean.mp4")
    for c in cands:
        if c.is_file(): return c
    return None


def guardar_opcao_no_acervo(cli: str, slug: str, beat_id: str, op_id: str, tags: str = "") -> dict | None:
    job = carregar(cli, slug)
    p = plano(job) or {}
    for b in p.get("beats", []):
        if b["id"] != beat_id: continue
        for o in b.get("opcoes", []):
            if o.get("id") != op_id: continue
            arq = arquivo_da_opcao(job, b, o)
            if not arq: return None
            meta = _acervo.adicionar_arquivo(arq, o.get("titulo") or op_id, tags or "", fonte=o.get("url", ""),
                autor="", licenca=o.get("verificado", ""), observacao=f"Fala: \"{b.get('fala','')}\". {o.get('motivo','')} (job {cli}/{slug}, {beat_id})",
                origem_tipo=f"job:{o.get('fonte','')}", checklist={"casa_com_a_fala": True},
                extra={"usos": [{"cliente": cli, "modelo": job["modelo"], "job": slug, "em": hoje()}] if b.get("escolha") == op_id else []})
            o["acervo"] = meta["slug"]; salvar_plano(job, p)
            return meta
    return None


# ═════════════════════ ETAPA 5: FINALIZAR (Parte A do plano) ═════════════════════
import hashlib
from _comum import ESTUDIO as _ESTUDIO

CONFIG = _ESTUDIO / "config.json"


def config() -> dict:
    return ler_json(CONFIG, {}) or {}


MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def destino_padrao(cli=None):
    import arquivo
    return arquivo.base_destino(cli)


def pasta_destino(job, base=None):
    import arquivo
    return arquivo.destino(job, base)


def finalizar(cli, slug, destino=None, apagar=False, exemplo=False):
    import arquivo
    return arquivo.exportar(cli, slug, destino, apagar, exemplo)


def apagar_apos_export(cli, slug):
    """Fechar e liberar espaço: apaga os temporários E fecha o aprendizado daquele modelo.

    Enquanto o vídeo está aberto, o histórico tem que continuar inteiro (o João ainda pode cobrar).
    Aqui é o fim da linha: o que ele ensinou vira/melhora regra e o cru sai da frente (vai pra
    aprendizado/arquivo/). Roda em segundo plano — absorver pode demorar.
    """
    import arquivo, aprendizado
    job = carregar(cli, slug)
    r = arquivo.limpar(cli, slug)
    try:
        c = cliente(cli)
        pasta = c["content"] / "modelos" / job["modelo"] / "aprendizado"
        if pasta.is_dir():
            aprendizado.disparar_fechar(pasta, slug)
    except Exception:
        pass                                  # liberar espaço nunca pode falhar por causa do aprendizado
    return r


# ═════════════════════ ETAPA 0: CORTE DO BRUTO ═════════════════════
# O João grava corrido e erra/repete. Se pedir, o Estúdio transcreve, propõe o corte e aplica —
# o resultado vira work/joao.mp4, que é o que todo modelo do repo espera.

def _opcao_padrao(beat: dict) -> str:
    """"Seguir direto" não tem o João pra escolher a cena: vale a recomendada da IA (campo recomendada/recomendacao do beat) ou, sem ela,
    a 1ª opção. Sem isso o vídeo saía só com o João em tela cheia, sem nenhuma cena (29-out-2026, Teste fluxo faixa: 0 trocas em 74 s)."""
    ops = [o.get("id") for o in beat.get("opcoes") or [] if o.get("id")]
    rec = beat.get("recomendada") or beat.get("recomendacao") or beat.get("recomendado")
    if rec in ops:
        return rec
    return ops[0] if ops and beat.get("tipo") in ("broll", "citacao") else ""


def avancar(cli: str, slug: str) -> str:
    """O "Aprovar" da aba Em andamento em qualquer formato: leva o vídeo ao próximo passo da tela
    (corte proposto → aplica e monta o storyboard; storyboard → aprova as escolhas atuais e renderiza)."""
    job = carregar(cli, slug)
    if not job:
        return ""
    if job.get("rodando") or job.get("status") == "na_fila":
        return "O vídeo já está sendo feito."
    p = plano(job)
    if not p:
        if corte_json(job) and not job.get("corte_aplicado") and not corte_rodando(job):
            aplicar_corte(cli, slug)
        analisar(cli, slug)
        return "✓ Aprovado. Montando o storyboard da edição."
    if not p.get("aprovado_em"):
        beats = p.get("beats", [])
        aprovar_plano(cli, slug, {b["id"]: b.get("escolha") or _opcao_padrao(b) for b in beats},
                      {b["id"]: b.get("comentario") or "" for b in beats}, p.get("observacoes_joao", ""))
    if carregar(cli, slug).get("status") == "plano_aprovado":
        renderizar(cli, slug)
        return "✓ Storyboard aprovado. Renderizando o vídeo."
    return ""


def corte_json(job: dict):
    return ler_json(RAIZ / job["sandbox"] / "work" / "CORTE.json")


def corte_rodando(job: dict) -> bool:
    import corte as _c
    return _c.rodando(RAIZ / job["sandbox"] / "work")


def _segue_direto(formato: str) -> bool:
    """Regra do João (30-out-2026): depois do storyboard o vídeo segue sozinho até o final, em TODO estilo; o gate de aprovação é o
    vídeo pronto ("Ficou bom?" + Editar vídeo). O storyboard aparece no Em andamento como progresso. Só o vídeo sem estilo (modelo
    antigo, sem esteira) continua parando. O João desliga a chave "Seguir direto" no Criar pra parar no storyboard."""
    try:
        import formatos as _f
        return bool(_f.carregar(formato or ""))
    except Exception:
        return False


def corta_sozinho(job: dict) -> bool:
    """Todo vídeo gravado passa pelo corte automático ao entrar (silêncio, take refeito, erro assumido).
    O formato sai dessa com "corte_automatico": false no formato.json (ex.: o bruto não é a pessoa falando)."""
    if "unittest" in sys.modules:          # teste cria vídeo de mentira: o corte de verdade sujava o Em andamento real
        return False
    b = RAIZ / (job.get("bruto") or "")
    if not job.get("bruto") or b.suffix.lower() not in VIDEO_EXTS or job.get("entrada") == "filmagem":
        return False
    try:
        import formatos as _f
        d = _f.carregar(job.get("formato") or "") or {}
    except Exception:
        d = {}
    return d.get("corte_automatico", True) is not False


def cortar_sozinho(cli: str, slug: str) -> None:
    """Propõe E aplica o corte em segundo plano (vira work/joao.mp4). O João só ajusta depois, no Corrigir o corte."""
    import corte as _c
    job = carregar(cli, slug)
    if corte_rodando(job):
        return
    job["status"] = "cortando"; salvar(job)
    try:
        import andamento
        andamento.passo(cli, slug, "Cortando o bruto (silêncio, take refeito, erro)", etapa="preparar",
                        titulo=job.get("titulo", ""), formato=job.get("formato") or "", origem="tela")
    except Exception:
        pass
    _c.propor(RAIZ / job["bruto"], RAIZ / job["sandbox"] / "work", job["cliente"], job.get("briefing", ""),
              job_id=f"{cli}/{slug}", aplicar=True)


def propor_corte(cli: str, slug: str, com_ia: bool = False) -> dict:
    import corte as _c
    job = carregar(cli, slug)
    if corte_rodando(job):
        return job
    job["status"] = "cortando"; salvar(job)
    try:
        import andamento
        andamento.passo(cli, slug, "Preparando o corte da fala", etapa="preparar", titulo=job.get("titulo", ""),
                        formato=job.get("formato") or "", origem="tela")
    except Exception:
        pass
    _c.propor(RAIZ / job["bruto"], RAIZ / job["sandbox"] / "work", job["cliente"],
              job.get("briefing", ""), com_ia=com_ia, job_id=f"{cli}/{slug}")
    return carregar(cli, slug)


def salvar_corte(cli: str, slug: str, manter: list[str], obs: str = "") -> dict:
    job = carregar(cli, slug)
    d = corte_json(job) or {}
    ids = {str(x) for x in manter}
    for s in d.get("segmentos", []):
        s["manter"] = str(s.get("i")) in ids
    d["observacoes_joao"] = obs
    gravar_json(RAIZ / job["sandbox"] / "work" / "CORTE.json", d)
    return carregar(cli, slug)


def aplicar_corte(cli: str, slug: str, respiro: float = 0.16, aperto: float = 0.55, avisar: bool = True) -> dict:
    """Aplica o corte aprovado: bruto → work/joao.mp4 (guarda o bruto original)."""
    import corte as _c
    job = carregar(cli, slug)
    work = RAIZ / job["sandbox"] / "work"
    saida = work / "joao.mp4"
    if saida.exists():
        saida.rename(work / f"joao-antes-do-corte-{now_slug()}.mp4")
    _c.aplicar(RAIZ / job["bruto"], work / "CORTE.json", saida, respiro=respiro, aperto=aperto)
    d = corte_json(job) or {}
    job["corte_aplicado"] = {"em": agora(), "arquivo": rel(saida),
                             "segmentos_mantidos": sum(1 for s in d.get("segmentos", []) if s.get("manter")),
                             "segmentos_total": len(d.get("segmentos", [])),
                             "duracao_s": (ffprobe(saida).get("duracao") if saida.exists() else None)}
    job["status"] = "cortado"; salvar(job)
    if avisar:
        try:
            import andamento
            andamento.espera(cli, slug, "Corte aplicado: mande analisar a edição", etapa="preparar")
        except Exception:
            pass
    return carregar(cli, slug)
