"""Motor único de IA: Claude Code ou GPT via Codex. Nenhuma chave em config.json."""
from __future__ import annotations
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from _comum import ESTUDIO, RAIZ, claude_bin, com_venv, ler_json, gravar_json

CONFIG = ESTUDIO / 'config.json'
DEFAULTS = dict(provedor='claude', modelo_claude='opus', modelo_gpt='', ultra_mode=True, esforco='medium',
                analises_simultaneas=3, renders_simultaneos=2, destino_mac='~/Movies/Estudio',
                embedding_model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                similaridade_acervo=0.55,
                cobranca='api',   # Claude: 'api' = crédito do Console (ANTHROPIC_API_KEY) · 'assinatura' = limite do login
                cobranca_gpt='assinatura',   # GPT/Codex: 'api' = crédito da OpenAI (só com chave) · 'assinatura' = login do ChatGPT
                fila_cobranca='api')   # o mesmo, mas pra fila de construção do sistema (via_api.py)
# Teto de gasto (US$) de cada etapa feita pela tela: o claude -p para sozinho ao chegar nele (--max-budget-usd).
TETO_ETAPA = {'analise': 2.0, 'producao': 1.0, 'feedback': 1.0, 'rebusca': 0.5, 'previas': 0.5, 'revisao': 0.5, 'melhoria': 1.0, 'outro': 1.0}
AVISO_TETO = 'Parei no teto de US$ {} desta etapa. Clique em Tentar de novo ou aumente o teto em Configurações.'


def config():
    return {**DEFAULTS, **(ler_json(CONFIG, {}) or {})}


# Lista única dos modelos do Claude (a tela e a produção leem daqui). A versão real vem de aprendido/SEMENTE:
# o claude -p resolve o apelido (opus, sonnet...) e o 'model' do evento de início aparece nos logs.
# custo é relativo entre os três, sem valor em dólar (o valor real de cada vídeo fica em Custos).
MODELOS_CLAUDE = [
    dict(apelido='opus', serve='Pensa mais fundo. Pra roteiro e vídeo difícil.', custo='caro'),
    dict(apelido='sonnet', serve='Equilíbrio entre qualidade e preço. Serve pra quase tudo.', custo='médio'),
    dict(apelido='haiku', serve='Rápido e simples. Pra tarefa fácil, menos criterioso.', custo='barato'),
]
# Vistos nos logs reais (app/jobs, app/api: 'model' do evento de início); o Haiku vem da lista de modelos atuais.
SEMENTE_CLAUDE = {'opus': 'claude-opus-5-5', 'sonnet': 'claude-sonnet-5-5', 'haiku': 'claude-haiku-4-5-20251001'}
APRENDIDOS = ESTUDIO / '.cache/modelos-claude.json'


def aprender_modelo_claude(apelido, modelo_id):
    """Guarda a versão que o Claude Code usou de verdade pra esse apelido (vem do evento de início)."""
    if apelido in SEMENTE_CLAUDE and re.fullmatch(r'claude-[a-z0-9.-]+', str(modelo_id or '')):
        ap = ler_json(APRENDIDOS, {}) or {}
        if ap.get(apelido) != modelo_id: gravar_json(APRENDIDOS, {**ap, apelido: modelo_id})


def id_claude(apelido):
    """Versão real de um apelido: a última vista em execução; sem isso, a vista nos logs."""
    return (ler_json(APRENDIDOS, {}) or {}).get(apelido) or SEMENTE_CLAUDE.get(apelido) or apelido


def nome_do_id(modelo_id):
    """'claude-sonnet-5-5' → 'Sonnet 5.5' · 'claude-haiku-4-5-20251001' → 'Haiku 4.5' · desconhecido volta igual."""
    m = re.fullmatch(r'claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?', str(modelo_id or ''))
    return f"{m.group(1).capitalize()} {m.group(2)}{'.'+m.group(3) if m.group(3) else ''}" if m else str(modelo_id or '')


def nome_claude(apelido):
    return nome_do_id(id_claude(apelido))


ESFORCOS = [('low', 'Baixo — rápido e econômico'), ('medium', 'Médio — equilíbrio (recomendado)'),
            ('high', 'Alto — pensa mais'), ('xhigh', 'Muito alto'), ('max', 'Máximo — Ultra Mode')]


def codex_bin():
    for p in (shutil.which('codex'), Path.home()/'.npm-global/bin/codex', '/opt/homebrew/bin/codex', '/usr/local/bin/codex'):
        if p and Path(p).is_file(): return str(p)


def catalogo():
    """Catálogo real da instalação/conta; campo livre mantém modelos novos acessíveis."""
    cache = ler_json(Path.home()/'.codex/models_cache.json', {}) or {}
    result = []
    for m in cache.get('models', []):
        slug = m.get('slug', '')
        if slug.startswith(('gpt-', 'o1', 'o3', 'o4', 'chatgpt-')):
            result.append({'id':slug, 'nome':m.get('display_name') or slug, 'visivel':m.get('visibility')=='list',
                           'descricao':m.get('description') or '',
                           'esforcos':[v['effort'] for v in m.get('supported_reasoning_levels', [])]})
    api = ler_json(ESTUDIO/'.cache/modelos-openai.json', []) or []
    seen = {m['id'] for m in result}
    result.extend({'id':m, 'nome':m, 'visivel':False, 'descricao':'', 'esforcos':[]} for m in api if m not in seen)
    return result


def atualizar_catalogo():
    import chaves   # lê do app/.env sem pôr no ambiente: o codex filho herdaria e passaria a cobrar da API
    key = chaves.chave('OPENAI_API_KEY') or chaves.ler('openai')
    if not key:
        if catalogo(): return len(catalogo())
        raise ValueError('Entre no Codex para carregar o catálogo ou coloque OPENAI_API_KEY no app/.env.')
    req = urllib.request.Request('https://api.openai.com/v1/models', headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(req, timeout=25) as r: data = json.load(r)
    ids = sorted(x['id'] for x in data.get('data',[]) if x['id'].startswith(('gpt-', 'o1', 'o3', 'o4', 'chatgpt-')))
    gravar_json(ESTUDIO/'.cache/modelos-openai.json', ids)
    return len(catalogo())


def cobranca(cfg=None):
    """De onde sai o gasto: 'api' (crédito do provedor escolhido) ou 'assinatura' (plano do Claude Code / login do ChatGPT).
    Sem a chave do provedor, é sempre assinatura (a caixa fica desligada na tela)."""
    import chaves
    cfg = cfg or config()
    if cfg.get('provedor') != 'claude':
        quer = cfg.get('cobranca_gpt') == 'api'
        return 'api' if quer and chaves.configurada('openai') else 'assinatura'
    quer = cfg.get('cobranca') != 'assinatura'
    return 'api' if quer and chaves.configurada('anthropic') else 'assinatura'


def opcoes_modelo(cfg=None):
    """Lista única da tela: [{grupo, provedor, itens:[{valor, nome, id, serve, custo, atual}]}]. Escolher um item define o provedor."""
    cfg = cfg or config()
    atual = ('claude:' + (cfg.get('modelo_claude') or 'opus')) if cfg.get('provedor') == 'claude' else ('gpt:' + (cfg.get('modelo_gpt') or ''))
    claude = [dict(valor='claude:'+m['apelido'], nome='Claude '+nome_claude(m['apelido']), id=id_claude(m['apelido']),
                   serve=m['serve'], custo=m['custo']) for m in MODELOS_CLAUDE]
    if cfg.get('modelo_claude') and cfg['modelo_claude'] not in SEMENTE_CLAUDE:   # id completo gravado à mão
        claude.append(dict(valor='claude:'+cfg['modelo_claude'], nome='Claude '+nome_do_id(cfg['modelo_claude']), id=cfg['modelo_claude'], serve='Escolhido por você fora da lista.', custo=''))
    gpt = [dict(valor='gpt:', nome='GPT · padrão da conta', id='', serve='O Codex escolhe o modelo da sua conta.', custo='')]
    vistos = set()
    for m in catalogo():
        if not m.get('visivel') and 'gpt:'+m['id'] != atual: continue
        vistos.add(m['id'])
        gpt.append(dict(valor='gpt:'+m['id'], nome=m['nome'], id=m['id'], serve=frase_gpt(m.get('descricao')), custo=custo_gpt(m.get('descricao'))))
    if cfg.get('modelo_gpt') and cfg['modelo_gpt'] not in vistos:
        gpt.append(dict(valor='gpt:'+cfg['modelo_gpt'], nome=cfg['modelo_gpt'], id=cfg['modelo_gpt'], serve='Escolhido por você fora da lista.', custo=''))
    grupos = [dict(grupo='Claude (Anthropic)', provedor='claude', itens=claude), dict(grupo='GPT (OpenAI · Codex)', provedor='openai', itens=gpt)]
    for g in grupos:
        for i in g['itens']: i['atual'] = i['valor'] == atual
    return grupos


def _versao_id(i):
    """'gpt-6.1-sol' -> (6, 1); 'gpt-5.6-terra' -> (5, 6); sem número -> ()."""
    m = re.search(r'(\d+(?:\.\d+)*)', i or '')
    return tuple(int(x) for x in m.group(1).split('.')) if m else ()


def _familia_gpt(i):
    return (i or '').rsplit('-', 1)[-1].lower()


def opcoes_modelo_enxuto(cfg=None):
    """Mesma lista de `opcoes_modelo`, mas só o que importa: Claude Opus/Sonnet/Haiku (um de cada; id escolhido à mão vai pra
    `antigas`) e, no GPT, o padrão da conta + o mais novo de cada família (Sol, Astra, Terra, Luna...) + o escolhido agora.
    O resto vai em `antigas` ("Ver versões antigas"). Cada grupo: {grupo, provedor, itens, antigas}."""
    grupos = opcoes_modelo(cfg)
    for g in grupos:
        todos = g['itens']
        if g['provedor'] == 'claude':
            apelidos = {'claude:' + m['apelido'] for m in MODELOS_CLAUDE}
            fica = {i['valor'] for i in todos if i['valor'] in apelidos or i['atual']}
        else:
            mais_novo = {}
            for i in todos:
                if not i['id']: continue
                f = _familia_gpt(i['id'])
                if f not in mais_novo or _versao_id(i['id']) > _versao_id(mais_novo[f]['id']): mais_novo[f] = i
            fica = {i['valor'] for i in mais_novo.values()} | {i['valor'] for i in todos if not i['id'] or i['atual']}
        g['itens'] = [i for i in todos if i['valor'] in fica]
        g['antigas'] = [i for i in todos if i['valor'] not in fica]
    return grupos


# O Codex descreve cada modelo em inglês; aqui a tradução curta e o custo relativo que a própria descrição dá.
_GPT_FRASES = (('frontier', 'Mais capaz. Pra trabalho muito exigente.', 'caro'),
               ('fast and affordable', 'Rápido e barato. Pra tarefa fácil.', 'barato'),
               ('fast and efficient', 'Rápido e econômico.', 'barato'),
               ('balanced', 'Equilibrado. Pra trabalho direto.', 'médio'),
               ('workhorse', 'Cavalo de batalha. Serve pra quase tudo.', 'médio'))


def _gpt_info(desc):
    d = (desc or '').lower()
    base = next(((f, c) for k, f, c in _GPT_FRASES if k in d), ('Modelo do Codex.', ''))
    if d.startswith(('older', 'previous', 'legacy')): base = ('Versão mais antiga. ' + base[0], base[1])
    return base


def frase_gpt(desc): return _gpt_info(desc)[0]
def custo_gpt(desc): return _gpt_info(desc)[1]


def aplicar_modelo(cfg, valor):
    """'claude:sonnet' ou 'gpt:gpt-6.1-sol': escolher o modelo já define o provedor. Mantém provedor/modelo_claude/modelo_gpt."""
    prov, _, nome = (valor or '').partition(':')
    if prov == 'claude' and nome: cfg['provedor'], cfg['modelo_claude'] = 'claude', nome
    elif prov == 'gpt': cfg['provedor'], cfg['modelo_gpt'] = 'openai', nome
    return cfg


def agora(cfg=None):
    """Uma linha com a combinação que vale agora. Ex.: 'Claude Sonnet 5.5 · pelo plano do Claude Code'."""
    cfg = cfg or config()
    api = cobranca(cfg) == 'api'
    if cfg.get('provedor') == 'claude':
        return 'Claude ' + nome_claude(cfg.get('modelo_claude') or 'opus') + ' · ' + ('pela API da Anthropic (seu crédito)' if api else 'pelo plano do Claude Code')
    return (cfg.get('modelo_gpt') or 'GPT (padrão da conta)') + ' · ' + ('pela API da OpenAI (seu crédito)' if api else 'pelo login do ChatGPT')


def estado_cobranca(cfg=None):
    """Pra caixa 'Cobrar da API' de cada provedor: {provedor: {nome, tem_chave, ligada, texto}}."""
    import chaves
    cfg = cfg or config()
    out = {}
    for prov, nome, quer in (('anthropic', 'Anthropic', cfg.get('cobranca') != 'assinatura'), ('openai', 'OpenAI', cfg.get('cobranca_gpt') == 'api')):
        tem = chaves.configurada(prov)
        ligada = bool(tem and quer)
        out[prov] = dict(nome=nome, tem_chave=tem, ligada=ligada,
                         texto=('este vídeo vai cobrar do seu crédito da ' + nome) if ligada
                         else ('usa o plano (Claude Code ou login do ChatGPT)' if tem else 'cole a chave acima'))
    return out


def selecao():
    cfg = config()
    provider = cfg['provedor']
    model = (os.environ.get('ESTUDIO_MODELO') or cfg['modelo_claude']) if provider == 'claude' else cfg['modelo_gpt']
    return {'provedor':provider, 'modelo':model, 'ultra_mode':bool(cfg.get('ultra_mode')), 'cobranca':cobranca(cfg),
            'esforco':('max' if cfg.get('ultra_mode') else (cfg.get('esforco') or 'medium'))}


ALTERACAO = {'modelo': 'sonnet', 'esforco': 'high'}   # pedido do João (29-out): alteração e pedido no editor = Sonnet, esforço alto


def para_alteracao(s=None, modelo='', esforco=''):
    """Seleção pra alteração (feedback, pedido do editor): Sonnet com esforço alto, salvo escolha do próprio pedido."""
    s = dict(s or selecao())
    if s.get('provedor', 'claude') == 'claude':
        s['modelo'] = modelo or ALTERACAO['modelo']
        s['esforco'] = esforco or ALTERACAO['esforco']
    return s


def disponivel():
    s=selecao()
    return bool(claude_bin() if s['provedor']=='claude' else codex_bin())


def rotulo(s=None):
    s=s or selecao()
    base = ('Claude ' + nome_claude(s['modelo'] or 'opus')) if s['provedor']=='claude' else ('GPT · Codex / ' + (s['modelo'] or 'padrão da conta'))
    return base + ' · esforço ' + (s.get('esforco') or 'medium')


def validar(cfg):
    if cfg.get('provedor') not in ('claude','openai'): raise ValueError('Escolha Claude ou OpenAI.')
    for k in ('modelo_claude','modelo_gpt'):
        if cfg.get(k) and not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', cfg[k]):
            raise ValueError('Identificador do modelo inválido.')
    if cfg.get('cobranca', 'api') not in ('api','assinatura'): raise ValueError('Cobrança inválida.')
    if cfg.get('fila_cobranca', 'api') not in ('api','assinatura'): raise ValueError('Cobrança da fila inválida.')
    if cfg.get('cobranca_gpt', 'assinatura') not in ('api','assinatura'): raise ValueError('Cobrança do GPT inválida.')
    if cfg.get('esforco') and cfg['esforco'] not in [e for e,_ in ESFORCOS]:
        raise ValueError('Nível de esforço inválido.')
    for k, maximum in (('analises_simultaneas',8),('renders_simultaneos',4)):
        try: cfg[k]=int(cfg[k])
        except (TypeError,ValueError): raise ValueError('Informe um limite de fila inteiro.')
        if not 1<=cfg[k]<=maximum: raise ValueError(f'{k}: use entre 1 e {maximum}.')
    if not str(cfg.get('destino_mac','')).strip(): raise ValueError('Informe a pasta de exportação.')
    return cfg


def teto_etapa(tipo, cfg=None):
    """US$ máximo da etapa (analise, producao, feedback...). 0 ou vazio = sem teto."""
    if not tipo: return None
    tetos = {**TETO_ETAPA, **((cfg or config()).get('teto_usd_etapa') or {})}
    try: v = float(tetos.get(tipo, tetos.get('outro')) or 0)
    except (TypeError, ValueError): return None
    return v if v > 0 else None


def comando(s=None, tipo=None):
    s=s or selecao()
    if s['provedor']=='claude':
        exe=claude_bin()
        if not exe: raise ValueError('Claude Code não encontrado. Instale e entre na sua conta.')
        cmd=[exe,'-p','--model',s['modelo'] or 'opus','--output-format','stream-json','--verbose',
             '--dangerously-skip-permissions','--add-dir',str(RAIZ)]
        esf = s.get('esforco') or ('max' if s.get('ultra_mode') else 'medium')
        if esf in [e for e, _ in ESFORCOS]: cmd += ['--effort', esf]
        teto = teto_etapa(tipo)
        if teto: cmd += ['--max-budget-usd', str(teto)]
        return cmd
    exe=codex_bin()
    if not exe: raise ValueError('Codex não encontrado. Instale o Codex CLI e execute codex login.')
    cmd=[exe,'exec','--json','--color','never','--sandbox','workspace-write','-C',str(RAIZ),
         '-c','sandbox_workspace_write.network_access=true']
    if s['modelo']: cmd += ['--model',s['modelo']]
    m=next((m for m in catalogo() if m['id']==s['modelo']),None)
    levels=m['esforcos'] if m else []
    effort=levels[-1] if s.get('ultra_mode') and levels else s.get('esforco')
    if effort in levels:
        cmd += ['-c', 'model_reasoning_effort='+json.dumps(effort)]
    return cmd+['-']


def evento(ev):
    t=ev.get('type','')
    if t in ('item.completed','item.started'):
        it=ev.get('item') or {}
        return it.get('text') or ('▶ '+it['command'][:250] if it.get('command') else None)
    if t in ('error','turn.failed'): return '✖ '+str(ev.get('message') or ev.get('error','Falha do modelo'))
    if t=='turn.completed': return '✓ Etapa concluída'
    if t=='assistant':
        parts=[]
        for c in ev.get('message',{}).get('content',[]):
            if c.get('text'): parts.append(c['text'])
            elif c.get('type')=='tool_use':
                inp=c.get('input') or {}; parts.append('▶ '+c.get('name','')+' '+str(inp.get('command') or inp.get('file_path') or '')[:200])
        return '\n'.join(parts)
    if t=='result': return ('✖ ' if ev.get('is_error') else '✓ ')+str(ev.get('result') or 'Concluído')
    if t=='system' and ev.get('subtype')=='init': return 'Sessão iniciada · '+str(ev.get('model',''))


def ambiente(s=None):
    """Env do processo de IA. Com cobrança 'api': chave do Console e sem login (OAuth) da assinatura. A chave só vive aqui, na memória."""
    s = s or selecao()
    if s['provedor'] != 'claude':   # Codex: a chave entra só no ambiente do processo (CODEX_API_KEY, que o codex exec lê)
        env = {k:v for k,v in os.environ.items() if not k.startswith('CLAUDECODE') and k != 'CODEX_API_KEY'}
        if s.get('cobranca') == 'api':
            import chaves
            if not chaves.ler('openai'): raise ValueError('Cobrar da API está ligado, mas falta a chave da OpenAI. Cole em Configurações.')
            env['CODEX_API_KEY'] = chaves.ler('openai')
        return env
    if s.get('cobranca') != 'api':
        return {k:v for k,v in os.environ.items() if not k.startswith('CLAUDECODE')}
    import via_api
    env={k:v for k,v in os.environ.items() if not k.startswith(('CLAUDE_CODE_OAUTH','CLAUDECODE','CLAUDE_CODE_SESSION'))}
    try: env['ANTHROPIC_API_KEY']=via_api.chave()
    except SystemExit as e: raise ValueError('Cobrar da API está ligado, mas falta a chave. Desligue em Configurações ou grave a chave em '+str(via_api.CHAVE)+'.') from e
    return env


# Minutos máximos de cada etapa; passou, o claude é parado (config.json -> max_min_etapa sobrescreve).
MAX_MIN = {'analise': 40, 'rebusca': 20, 'previas': 30, 'producao': 90, 'feedback': 60, 'revisao': 15, 'melhoria': 20, 'outro': 30}


def max_min(tipo, cfg=None):
    if not tipo: return 0   # chamada fora da esteira da tela (estudo, referência): sem prazo
    m = {**MAX_MIN, **((cfg or config()).get('max_min_etapa') or {})}
    try: return float(m.get(tipo, m.get('outro')) or 0)
    except (TypeError, ValueError): return 0


def _matar_grupo(proc, sinal=signal.SIGTERM):
    try: os.killpg(proc.pid, sinal)
    except (ProcessLookupError, PermissionError, OSError): pass


def executar(prompt, log, raw, pid_file, s=None, on_event=None, tipo=None):
    s = dict(s or selecao())   # job antigo guarda só provedor/modelo: a cobrança vale a de agora
    s['cobranca'] = cobranca({**config(), 'provedor': s.get('provedor', 'claude')})
    env=ambiente(s)
    env['PATH']='/opt/homebrew/bin:/usr/local/bin:'+env.get('PATH','')
    env=com_venv(env)   # python3 do filho = o da venv (o do brew pode ser outra versão, sem PIL/numpy/cv2)
    # Render e QA podem ultrapassar dez minutos. Aguarde os agentes até terminarem.
    env['CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS']='0'
    with log.open('a',encoding='utf-8') as out, raw.open('a',encoding='utf-8') as trace:
        out.write('Iniciando '+rotulo(s)+(' · cobrando da API' if s['cobranca']=='api' else '')+'\n');out.flush()
        proc=subprocess.Popen(comando(s, tipo),cwd=RAIZ,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
        # runner.pid sempre identifica o worker, para parar também ffmpeg e subprocessos.
        pid_file.write_text(str(os.getpid()))
        estourou=[]
        prazo=max_min(tipo)
        def _estourar():
            estourou.append(1)
            try:
                out.write(f'✖ Passou de {prazo:g} min sem terminar: parei. Clique em Tentar de novo.\n');out.flush()
            except ValueError: pass
            _matar_grupo(proc)
        timer=threading.Timer(prazo*60,_estourar) if prazo>0 else None
        if timer: timer.daemon=True;timer.start()
        antigo=None
        try:   # "cancelar" manda SIGTERM pro runner: leva o claude (grupo próprio) junto
            antigo=signal.signal(signal.SIGTERM,lambda *a:(_matar_grupo(proc),sys.exit(143)))
        except ValueError: pass
        try:
            proc.stdin.write(prompt);proc.stdin.close()
            failed=False
            custo=None;tokens=None
            for line in proc.stdout:
                trace.write(line);trace.flush()
                if '"total_cost_usd"' in line:
                    try:
                        _ev=json.loads(line);custo=_ev.get('total_cost_usd');tokens=_ev.get('usage') or tokens
                    except ValueError: pass
                if 'Background tasks still running after' in line and 'terminating' in line:
                    failed=True
                try:
                    ev=json.loads(line);txt=evento(ev)
                    failed |= ev.get('type') in ('error','turn.failed') or bool(ev.get('is_error'))
                    if on_event: on_event(ev)
                    if ev.get('subtype')=='error_max_budget_usd':
                        out.write('✖ '+AVISO_TETO.format(teto_etapa(tipo) or '?')+'\n');out.flush()
                    if ev.get('type')=='system' and ev.get('subtype')=='init' and s['provedor']=='claude' and ev.get('model'):
                        aprender_modelo_claude(s.get('modelo') or 'opus', ev['model'])
                    if ev.get('type')=='system' and ev.get('subtype')=='init' and s.get('cobranca')=='api' and s['provedor']=='claude' \
                       and ev.get('apiKeySource') not in (None,'ANTHROPIC_API_KEY'):
                        proc.kill();failed=True   # nunca gastar a assinatura sem querer
                        out.write('✖ Parei: o Claude não usou a chave da API (usaria o limite da assinatura).\n');out.flush()
                except (ValueError,TypeError): txt=line.rstrip()
                if txt: out.write(txt+'\n');out.flush()
            code=proc.wait()
            try:
                import custos
                custos.registrar_execucao(s, custo, tokens, log)
            except Exception:
                pass
            return 1 if estourou else (code or (1 if failed else 0))
        finally:
            if timer: timer.cancel()
            if antigo is not None:
                try: signal.signal(signal.SIGTERM,antigo)
                except ValueError: pass
            if proc.poll() is None: _matar_grupo(proc)
            pid_file.unlink(missing_ok=True)


def main():
    prompt_file, folder=sys.argv[1:3]
    d=Path(folder)
    try: code=executar(Path(prompt_file).read_text(),d/'.log',d/'.raw.jsonl',d/'.runner.pid')
    except Exception as e:
        (d/'.log').write_text('Falha: '+str(e));code=1
    (d/'.runner.pid').unlink(missing_ok=True)
    sys.exit(code)

if __name__=='__main__': main()
