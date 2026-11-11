"""Projetos com vários brutos ou variações de um bruto, usando a mesma fila."""
import re
import shutil
import uuid
from pathlib import Path
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import VIDEO_EXTS, ESTUDIO, agora, gravar_json, ler_json, make_slug, cliente, modelo
import producao as P
import andamento as AND
import formatos as FMT

LOTES=ESTUDIO/'lotes'


def carregar(slug):
    if Path(slug).name!=slug or slug in ('.','..'):raise ValueError('Lote inválido.')
    return ler_json(LOTES/(slug+'.json'))


def listar():return sorted((ler_json(p) for p in LOTES.glob('*.json')),key=lambda x:x['criado_em'],reverse=True)


def criar(cli,titulo,briefing,linhas,materiais=(),formato=''):
    if not linhas:raise ValueError('Adicione ao menos um vídeo.')
    c=cliente(cli)
    if not c:raise ValueError('Escolha um cliente.')
    for row in linhas:
        if not modelo(c,row['modelo']) or not Path(row['bruto']).is_file():raise ValueError('Revise os brutos e modelos do lote.')
    slug=make_slug(titulo)+'-'+uuid.uuid4().hex[:6]
    lote=dict(slug=slug,titulo=titulo,cliente=cli,briefing=briefing,criado_em=agora(),jobs=[])
    if formato:lote['formato']=formato
    for row in linhas:
        # Uploads são preservados até criar todos os jobs (1 bruto × N modelos).
        stage=ESTUDIO/'.uploads'/uuid.uuid4().hex;stage.mkdir(parents=True)
        bruto=stage/Path(row['bruto']).name;_clonar(row['bruto'],bruto)
        mats=[]
        for i,p in enumerate(materiais):
            dst=stage/(str(i)+'-'+Path(p).name);_clonar(p,dst);mats.append(dst)
        j=P.criar(cli,row['modelo'],bruto,row.get('titulo') or Path(row['bruto']).stem,
                  briefing+'\n\n'+row.get('observacao',''),camadas=row.get('camadas',[]),materiais=mats,formato=row.get('formato',''))
        j['lote']=slug;P.salvar(j);lote['jobs'].append(j['slug']);gravar_json(LOTES/(slug+'.json'),lote)
        shutil.rmtree(stage)
    return lote


def acao(lote,acao):
    results=[]
    for slug in lote['jobs']:
        j=P.carregar(lote['cliente'],slug)
        if not j:continue
        try:
            if acao=='analisar' and j['status'] in ('novo','cortando','erro','interrompido'):P.analisar(j['cliente'],slug)
            elif acao=='renderizar' and j['status'] in ('plano_aprovado',):P.renderizar(j['cliente'],slug)
            elif acao=='finalizar' and j['status'] in ('aprovado','exportado'):P.finalizar(j['cliente'],slug,apagar=True)
            elif acao=='apagar':P.apagar(j['cliente'],slug,lote=True)
            else:continue
            results.append(j['titulo']+': solicitado')
        except Exception as e:results.append(j['titulo']+': '+str(e))
    if acao=='apagar':
        lote['jobs']=[s for s in lote['jobs'] if P.carregar(lote['cliente'],s)]
        if lote['jobs']:gravar_json(LOTES/(lote['slug']+'.json'),lote)
        else:(LOTES/(lote['slug']+'.json')).unlink(missing_ok=True)
    return results


def brutos_da_pasta(caminho):
    """Vídeos de uma pasta local (sem subpastas), em ordem de nome. Só lista: quem usa copia, nunca move."""
    pasta=Path(str(caminho or '').strip()).expanduser()
    if not str(caminho or '').strip() or not pasta.is_dir():raise ValueError('Não achei essa pasta. Confira o caminho.')
    vids=sorted((p for p in pasta.iterdir() if p.is_file() and not p.name.startswith('.') and p.suffix.lower() in VIDEO_EXTS),key=lambda p:p.name.lower())
    if not vids:raise ValueError('Essa pasta não tem vídeo.')
    return vids


def exige_por_video(f):
    """Campos obrigatórios do estilo que mudam de vídeo pra vídeo e não cabem num lote (a tela da análise, o trecho da crítica...)."""
    return [c for c in (f.get('pede') or []) if c.get('obrigatorio') and not c.get('principal') and c.get('tipo') in ('arquivo','foto','tempo','arquivo_ou_link')]


def criar_por_estilo(cli,formato_slug,brutos,briefing='',titulo='',analisar=False):
    """Um estilo (formato) só pra vários brutos: um vídeo por bruto, igual ao do Criar (mesmo formato, entra na fila do Em andamento).
    Duplicado do Criar (simples.py): o título do vídeo vem do nome do arquivo e o formato vai gravado no vídeo e no lote."""
    brutos=[Path(b) for b in brutos]
    if not brutos:raise ValueError('Escolha ao menos um vídeo.')
    quem,mod=FMT.usar(formato_slug,cli or '')
    f=FMT.carregar(formato_slug) or {}
    if f.get('entrada')!='video':raise ValueError('Este estilo não serve pra fazer vários de uma vez: ele não parte de um vídeo gravado por bruto. Use o Criar.')
    falta=exige_por_video(f)
    if falta:raise ValueError('Este estilo pede '+', '.join(str(c.get('rotulo') or c['campo']).lower() for c in falta)+' em cada vídeo, e o lote não tem onde pôr isso. Use o Criar, um vídeo por vez.')
    linhas=[dict(bruto=b,modelo=mod,formato=formato_slug,titulo=(f.get('titulo') or formato_slug)+' · '+re.sub(r'^[0-9a-f]{8}-','',b.stem)) for b in brutos]
    titulo=(titulo or '').strip() or (f.get('titulo') or formato_slug)+' · '+str(len(brutos))+(' vídeo' if len(brutos)==1 else ' vídeos')
    lote=criar(quem,titulo,briefing or '',linhas,formato=formato_slug)
    if analisar:lote['resultados']=acao(lote,'analisar')
    return lote


def esperando():
    """Vídeos da tela que esperam o João (todos os clientes): storyboard pra aprovar (tipo 'storyboard') e vídeo pronto pra assistir (tipo 'video')."""
    lote_de={}
    for l in listar():
        for s in l.get('jobs',[]):lote_de[(l['cliente'],s)]=l
    out=[]
    for d in AND.listar():
        est=d.get('estado')
        chat=d.get('origem')=='chat'
        if est not in ('esperando','pronto') or (d.get('origem')!='tela' and not chat):continue
        if est=='pronto' and not d.get('video'):continue
        l=lote_de.get((d['cliente'],d['slug']))
        item=dict(cliente=d['cliente'],slug=d['slug'],titulo=d.get('titulo') or d['slug'],imagem=d.get('imagem') or '',
                  tipo='storyboard' if est=='esperando' else 'video',video=d.get('video') or '',
                  estilo=d.get('formato_titulo') or d.get('formato') or '',lote=l['slug'] if l else '',
                  lote_titulo=l['titulo'] if l else '',ha=d.get('ha',''))
        item['pronto']=bool(item['imagem']) if est=='esperando' else True
        if chat:   # feito pelo chat: as versões do mesmo vídeo (nome, nome-v2…) viram UM cartão com "N versões"
            item.update(chat=True,chave=_chave_chat(d))
            achou=next((x for x in out if x.get('chat') and x['chave']==item['chave']),None)
            if achou:achou['versoes'].append(d['slug']);achou['n_versoes']+=1;continue
            item.update(versoes=[d['slug']],n_versoes=1)
        if est=='esperando' and d.get('formato')=='frase-fixa':
            sb=(P.carregar(d['cliente'],d['slug']) or {}).get('sandbox')
            plano=ler_json(P.RAIZ/sb/'PLANO.json',{}) if sb else {}
            ops=plano.get('opcoes_frase') or []
            if isinstance(ops,list) and ops:item['opcoes_frase']=[str(o) for o in ops];item['frase']=plano.get('frase') or ''
        out.append(item)
    try:   # o resto que espera o "Aprovou?": referência, estudo, variações, estilo novo, regra aprendida (pendencias.py)
        import pendencias
        out+=pendencias.itens()
    except Exception:pass
    return out


def _chave_chat(d):
    """Versões do mesmo vídeo do chat: mesmo cliente, mesmo estilo e o slug sem o sufixo -vN."""
    return (d['cliente'],d.get('formato') or '',re.sub(r'-v\d+$','',d['slug']))


def _expandir(itens):
    """Um cartão de chat com N versões vale pras N: aprovar ou tirar da lista age em todas (nada é apagado)."""
    out=[];chat=[i for i in esperando() if i.get('chat')] if itens else []
    for cli,slug in itens:
        item=next((i for i in chat if i['cliente']==cli and slug in i['versoes']),None)
        for s in (item['versoes'] if item else [slug]):
            if (cli,s) not in out:out.append((cli,s))
    return out


def tirar_antigos_chat(dias=3):
    """Tira da lista todo vídeo feito pelo chat parado em 'pronto' há mais de `dias` dias. Só esconde: o vídeo segue em Meus vídeos."""
    n=0
    for d in AND.listar(True):
        if d.get('origem')=='chat' and d.get('estado')=='pronto' and not d.get('oculto') and AND._min_desde(d.get('atualizado',''))>dias*1440:
            n+=1 if AND.esconder(d['cliente'],d['slug']) else 0
    return n


def tirar_da_lista(itens):
    """Some da lista Esperando você (esconde o registro do Em andamento). Não apaga nada: o vídeo continua em Meus vídeos."""
    out=[]
    for cli,slug in _expandir(itens):
        d=AND.carregar(cli,slug);titulo=(d or {}).get('titulo') or slug
        out.append(titulo+(': tirado da lista' if d and AND.esconder(cli,slug) else ': não encontrado'))
    return out


def aprovar_varios(itens,frases=None):
    """Faz pra cada (cliente, slug) o mesmo que o Aprovar do Em andamento (storyboard) ou do Aprovar vídeo (vídeo pronto).
    frases: {"cliente/slug": frase escolhida} grava em PLANO.json antes de seguir. Um erro não para os outros."""
    out=[];frases=frases or {}
    for cli,slug in _expandir(itens):
        d=AND.carregar(cli,slug)
        titulo=(d or {}).get('titulo') or slug
        try:
            if not d:raise ValueError('vídeo não encontrado')
            if d.get('estado')=='pronto':
                _,idx=AND.responder(cli,slug,'aprovar');AND.marcar_resposta(cli,slug,idx,'feito')
                try:P.reconciliar(cli,slug)
                except Exception:
                    if d.get('origem')!='chat':raise   # feito pelo chat não tem job pra reconciliar
                out.append(titulo+': aprovado');continue
            if d.get('estado')!='esperando':raise ValueError('não está esperando você')
            if not d.get('imagem'):raise ValueError('ainda falta uma escolha: abra o vídeo e escolha antes de aprovar')
            fr=(frases.get(cli+'/'+slug) or '').strip()
            if fr:_gravar_frase(cli,slug,fr)
            _,idx=AND.responder(cli,slug,'aprovar')
            try:
                P.avancar(cli,slug);AND.marcar_resposta(cli,slug,idx,'feito')
            except Exception:
                AND.marcar_resposta(cli,slug,idx,'erro');raise
            out.append(titulo+': ok')
        except Exception as e:out.append(titulo+': erro ('+str(e)+')')
    return out


def _gravar_frase(cli,slug,frase):
    j=P.carregar(cli,slug) or {}
    if not j.get('sandbox'):return
    arq=P.RAIZ/j['sandbox']/'PLANO.json'
    plano=ler_json(arq,{})
    if plano:plano['frase']=frase;gravar_json(arq,plano)


def contagem(lote):
    """Quantos vídeos do lote: na fila, esperando o João, prontos pra assistir e aprovados."""
    c=dict(fila=0,esperando=0,pra_ver=0,aprovados=0)
    for s in lote.get('jobs',[]):
        j=P.carregar(lote['cliente'],s)
        if not j:continue
        d=AND.carregar(lote['cliente'],s) or {}
        if j.get('status') in ('aprovado','exportado','arquivado'):c['aprovados']+=1
        elif d.get('estado')=='pronto' or j.get('status')=='concluido':c['pra_ver']+=1
        elif d.get('estado')=='esperando':c['esperando']+=1
        else:c['fila']+=1
    return c
