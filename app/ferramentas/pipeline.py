"""Etapas observáveis do projeto. Não estima percentuais nem inventa progresso."""
import json
import producao as P
import edicao
from _comum import texto_fila


def _curto(txt, n=70):
    txt = (txt or '').strip().split('. ')[0].rstrip('.')
    return txt if len(txt) <= n else txt[:n - 2].rsplit(' ', 1)[0] + '…'


def _etapas_esteira(job, est):
    """Formato com esteira: a barra são os passos DO FORMATO (titulo do formato.json), na ordem.
    O estado de cada um sai do status e dos arquivos: storyboard.jpg, aprovado_em, saida, qa/conferir.json."""
    sb = P.RAIZ / job['sandbox']
    plan = P.plano(job) or {}
    status = job.get('status')
    execution = (job.get('execucoes') or [{}])[-1].get('tipo', '')
    active = bool(job.get('rodando'))
    analisando = active and execution in ('analise', 'rebusca')
    produzindo = active and execution in ('producao', 'feedback')
    falada = (sb / 'work/words.json').is_file() or bool(plan.get('transcricao'))
    storyboard = (sb / 'storyboard.jpg').is_file()
    aprovado = bool(plan.get('aprovado_em'))
    final = bool(job.get('saida')) and not job.get('edicao_alterada')
    avisos = P.avisos_da_conferencia(job)
    conferido = (sb / 'qa/conferir.json').is_file() and not avisos
    exportavel = status in ('aprovado', 'exportado', 'arquivado')
    etapas, k = est['etapas'], est['parada']
    ultimo = len(etapas) - 1

    def feita(i, e):   # plano aprovado = o João já viu e aprovou o storyboard (mesmo que o jpg tenha outro nome)
        if i < k:
            if analisando:
                return e['andamento'] == 'preparar' and falada
            return storyboard or aprovado or (e['andamento'] == 'preparar' and falada)
        if i == k:
            return aprovado and not analisando
        if produzindo or not final:
            return False
        return (conferido or exportavel) if e['andamento'] == 'conferencia' else True

    feitas = [feita(i, e) for i, e in enumerate(etapas)]
    primeira = next((i for i, x in enumerate(feitas) if not x), None)
    result = []
    if job.get('cortar_bruto'):   # o corte da fala vem antes da esteira, como no resto do Estúdio
        state = 'pronto' if job.get('corte_aplicado') else ('rodando' if P.corte_rodando(job) else ('revisar' if P.corte_json(job) else 'aguardando'))
        detail = {'pronto': 'Corte aprovado', 'rodando': 'Transcrevendo e preparando os cortes', 'revisar': 'Escolha o que fica na fala',
                  'aguardando': 'Tirar repetições e pausas da fala'}[state]
        # "Cortar a fala": o 1º passo da esteira já se chama "Preparar a fala" e a barra mostrava os dois quase iguais
        result.append(dict(id='corte-fala', titulo='Cortar a fala', estado=state, detalhe=detail, alvo='#bruto'))
    for i, e in enumerate(etapas):
        alvo = '#render-final' if i > k and final else '#editar'
        if feitas[i]:
            state = 'pronto'
            detail = 'Aprovado' if i == k else ('Conferido' if e['andamento'] == 'conferencia' else 'Feito')
            if i == ultimo:
                state, detail = ('pronto', 'Pronto para exportar') if exportavel else ('revisar', 'Assista e aprove o vídeo')
        elif i != primeira:
            state, detail = 'aguardando', 'Próxima etapa'   # o "faz" é instrução pra IA: na tela, só título e estado
        elif status == 'erro':
            state, detail = 'atencao', 'Parou com erro; veja os detalhes'
        elif status == 'na_fila':
            state, detail = 'aguardando', texto_fila(job.get('cliente'), job.get('slug'))
        elif (analisando and i <= k) or (produzindo and i > k):
            state = 'rodando'
            detail = ('Fazendo o vídeo agora' if e['andamento'] == 'video' else
                      'Montando o storyboard' if i == k or e['andamento'] == 'storyboard' else 'Fazendo agora')
        elif i == k and storyboard:
            state, detail = 'revisar', 'Veja o storyboard e aprove'
        elif i > k and final and e['andamento'] == 'conferencia':
            state, detail = 'atencao', ('Conferir: ' + '; '.join(avisos[:2]) if avisos else 'Vídeo entregue sem a conferência registrada')
        else:
            state, detail = 'aguardando', 'Próxima etapa'   # o "faz" é instrução pra IA: na tela, só título e estado
        result.append(dict(id=e['id'], titulo=e['titulo'], estado=state, detalhe=detail, alvo=alvo))
    return result


def _etapas(job):
    est = P._esteira(job)
    if est:
        return _etapas_esteira(job, est)
    sb = P.RAIZ / job['sandbox']
    plan = P.plano(job)
    cutting = P.corte_rodando(job)
    cut = P.corte_json(job)
    active = bool(job.get('rodando'))
    execution = (job.get('execucoes') or [{}])[-1].get('tipo', '')
    queue = job.get('status') == 'na_fila'
    prefs = job.get('broll_config') or {'origem':'busca','quantidade':edicao.quantidade(job)}
    result = []
    def add(ident, title, state, detail, target):
        result.append(dict(id=ident,titulo=title,estado=state,detalhe=detail,alvo=target))
    add('bruto','Vídeo bruto','pronto','Arquivo recebido','#bruto')
    if job.get('cortar_bruto'):
        state = 'pronto' if job.get('corte_aplicado') else ('rodando' if cutting else ('revisar' if cut else 'aguardando'))
        detail = {'pronto':'Corte aprovado','rodando':'Transcrevendo e preparando os cortes','revisar':'Escolha o que fica na fala','aguardando':'Preparar fala e remover repetições'}[state]
        add('fala','Preparar fala',state,detail,'#bruto')
    else:
        add('fala','Preparar fala','pronto','Usar a gravação como enviada','#bruto')
    state = 'rodando' if active and execution in ('analise','rebusca') else ('pronto' if plan else 'aguardando')
    words = (sb/'work/words.json').is_file() or bool((plan or {}).get('transcricao'))
    detail = ('Plano disponível para revisão' if plan else ('Transcrição disponível · planejando a edição' if words else 'A análise começa pela transcrição'))
    if queue and not plan:detail='Aguardando a vez na fila'
    if job.get('status')=='erro' and execution in ('analise','rebusca'):
        state,detail='atencao','A análise precisa de atenção; consulte os detalhes'
    add('analise','Analisar edição',state,detail,'#editar')
    if prefs['origem'] != 'nenhum':
        chosen=len(edicao.selecionados(plan))
        detail=f'{chosen} cena(s) selecionada(s) · limite {edicao.quantidade(job)}'
        state='pronto' if chosen else ('revisar' if plan else 'aguardando')
        if prefs['origem']=='ia':
            records=[]
            for file in (sb/'gerados').glob('*.json'):
                try:records.append(json.loads(file.read_text()))
                except (ValueError,OSError):continue
            pending=[r for r in records if r.get('status') in ('enviando','processando')]
            ready=[r for r in records if r.get('status')=='pronto']
            if pending:state,detail='rodando',f'{len(pending)} geração(ões) em andamento'
            elif not chosen:detail=f'{len(ready)} resultado(s) para revisar · imagem antes da animação'
            add('cenas','Imagem → animação',state,detail,'brolls')
        else:add('cenas','Cenas de apoio',state,detail,'#editar')
    preview=(sb/'PREVIAS.md').is_file() or any(b.get('previa') for b in (plan or {}).get('beats',[]))
    add('previa','Prévia da edição','rodando' if active and execution=='previas' else ('pronto' if preview else 'aguardando'),
        'Prévias disponíveis' if preview else 'Opcional: conferir trechos antes do render','#editar')
    approved=job.get('status') in ('aprovado','exportado','arquivado')
    final=bool(job.get('saida')) and not job.get('edicao_alterada')
    state='rodando' if active and execution in ('producao','feedback') else ('pronto' if approved else ('revisar' if final else 'aguardando'))
    detail=('Fazendo o vídeo agora' if state=='rodando' else
            'Pronto para exportar' if approved else ('Assista e aprove o vídeo' if final else 'Produzir depois de revisar suas escolhas'))
    add('final','Vídeo final',state,detail,'#render-final' if final else '#editar')
    return result


# Quem age em cada estado da barra: o João só aparece quando precisa aprovar ou olhar um erro.
QUEM = {'revisar': 'Você aprova', 'atencao': 'Você olha'}


def etapas(job):
    """As etapas de _etapas + `quem` ("Estúdio faz" / "Você aprova" / "Você olha"), `sua_vez` e `atual` (a etapa em foco).
    Na etapa do corte da fala, `editor_corte` pede o link pro editor de corte na mão."""
    lista = _etapas(job)
    atual = etapa_atual(lista)
    for e in lista:
        e['quem'] = QUEM.get(e['estado'], 'Estúdio faz')
        e['sua_vez'] = e['estado'] in QUEM
        e['atual'] = e['id'] == atual
        if e['id'] in ('corte-fala', 'fala') and job.get('cortar_bruto'):
            e['editor_corte'] = True
            if e['estado'] != 'pronto':
                e['detalhe'] += ' · dá pra corrigir na mão'
    return lista


def etapa_atual(lista_ou_job):
    """Id da etapa em foco: a primeira que pede o João, senão a que está rodando, senão a primeira que não está pronta
    (None se tudo pronto). Aceita a lista de etapas ou o próprio job."""
    lista = lista_ou_job if isinstance(lista_ou_job, list) else _etapas(lista_ou_job)
    for estados in (('revisar', 'atencao'), ('rodando',), ('aguardando',)):
        achada = next((e['id'] for e in lista if e['estado'] in estados), None)
        if achada:
            return achada
    return None
