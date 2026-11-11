"""Mídia própria opcional e evidência visual das opções de um trecho."""
from pathlib import Path
import json
import subprocess
import uuid
import producao as P
from _comum import gravar_json, ler_json


def midia(job, op):
    sb=(P.RAIZ/job['sandbox']).resolve()
    for key in ('arquivo','gif','sheet'):
        value=op.get(key)
        if not value:continue
        path=(sb/value).resolve()
        if path.is_relative_to(sb) and path.is_file():return path
    return None


def preparar_tela(job, plan):
    for beat in (plan or {}).get('beats',[]):
        for op in beat.get('opcoes',[]):
            op['disponivel']=bool(midia(job,op))
            op['registro_busca']=not op['disponivel'] and not op.get('url') and not op.get('arquivo') and beat.get('escolha') != op.get('id')
            op['pendente_visual']=op.get('fonte')=='proprio' and not op.get('avaliacao_visual')
    return plan


def anexar(job, beat_id, upload):
    if job.get('rodando') or job.get('status') in ('na_fila','exportado','arquivado'):
        raise ValueError('Aguarde a execução antes de anexar um take.')
    plan=P.plano(job) or {}
    beat=next((b for b in plan.get('beats',[]) if b['id']==beat_id),None)
    if not beat:raise ValueError('Trecho não encontrado.')
    suffix=Path(upload.filename or '').suffix.lower()
    if suffix not in ('.mp4','.mov','.m4v','.webm','.mkv','.jpg','.jpeg','.png','.webp'):
        raise ValueError('Envie um vídeo ou imagem para este trecho.')
    ident='proprio-'+uuid.uuid4().hex[:12]
    folder=P.RAIZ/job['sandbox']/'material';folder.mkdir(exist_ok=True)
    path=folder/(ident+suffix);upload.save(path)
    try:
        probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30)
        if not any(s.get('codec_type')=='video' for s in json.loads(probe.stdout)['streams']):raise ValueError('Sem imagem no arquivo.')
    except Exception:
        path.unlink(missing_ok=True)
        raise ValueError('Não foi possível ler esse vídeo ou imagem.') from None
    relative=str(path.relative_to(P.RAIZ/job['sandbox']))
    job.setdefault('materiais',[]).append(relative)
    job.setdefault('takes_proprios',[]).append(dict(id=ident,beat=beat_id,arquivo=relative,nome=Path(upload.filename).name,status='aguardando_analise'))
    P.salvar(job)
    return ident


def prompt(job, beat_id, avaliar=False):
    plan=P.plano(job) or {};beat=next((b for b in plan.get('beats',[]) if b['id']==beat_id),None)
    if not beat:raise ValueError('Trecho não encontrado.')
    pending=[x for x in job.get('takes_proprios',[]) if x['beat']==beat_id]
    sb=job['sandbox']
    return f'''Avalie visualmente e prepare as opções SOMENTE do trecho {beat_id} em {sb}/PLANO.json.
Fala e intenção: {json.dumps(beat,ensure_ascii=False)}
Material próprio opcional: {json.dumps(pending,ensure_ascii=False)}
Abra os arquivos reais. Extraia frames a cada segundo e confira o movimento e cortes adjacentes; gere contact sheet e prévia curta de cada candidato. Para arquivos já locais use ffmpeg, sem buscar nem gerar mídia. Para opção remota sem arquivo, use a URL existente e get-brolls preview, sem substituir a opção por outro vídeo. Se não conseguir obter mídia, marque indisponivel e explique, nunca invente que conferiu.
Para cada take próprio, compare conteúdo com a fala; registre qualidade, enquadramento, movimento, limitações e intervalo sugerido. Arquivo {sb}/material/avaliacao-{beat_id}.json: {{"takes":[{{"id":"id do anexo","adequado":true ou false,"motivo":"relação com a fala e limitações","sheet":"caminho relativo de contact sheet real","inicio":0,"fim":2}}]}}. Abra a folha ANTES de avaliar. Se não tiver anexo, takes: [].
Inclua como opção fonte proprio somente material considerado adequado, com arquivo, gif ou sheet e avaliacao_visual. Não selecione automaticamente. Material inadequado fica apenas no relatório, com motivo; não force seu uso.
Preserve IDs, escolhas, comentários e todos os outros trechos. Não apague arquivos. Não renderize o vídeo final. Não chame APIs de geração de imagem ou vídeo. Ao terminar registre as limitações em PREVIAS.md.
'''


def validar_avaliacao(job, beat_id):
    sb=P.RAIZ/job['sandbox'];pending=[x for x in job.get('takes_proprios',[]) if x['beat']==beat_id]
    report=ler_json(sb/'material'/f'avaliacao-{beat_id}.json',{}) or {}
    rows={r.get('id'):r for r in report.get('takes',[])}
    for item in pending:
        row=rows.get(item['id'],{})
        if not isinstance(row.get('adequado'),bool) or not row.get('motivo') or not row.get('sheet') or not midia(job,{'sheet':row['sheet']}):
            raise ValueError('A análise visual do take próprio não entregou evidência e justificativa. Revise antes de usar.')
    beat=next((b for b in (P.plano(job) or {}).get('beats',[]) if b['id']==beat_id),{})
    missing=[o['id'] for o in beat.get('opcoes',[]) if o.get('url') and not o.get('indisponivel') and not midia(job,o)]
    if missing: raise ValueError('Ainda faltam prévias reais para: '+', '.join(missing)+'. A etapa não foi concluída.')
    for item in pending:
        item.update(status='avaliado',avaliacao=rows[item['id']])
    P.salvar(job)


def validar_escolhas(job, plan):
    for beat in (plan or {}).get('beats',[]):
        if beat.get('tipo') not in ('broll','citacao') or not beat.get('escolha'):continue
        op=next((o for o in beat.get('opcoes',[]) if o.get('id')==beat['escolha']),None)
        clean=P.arquivo_da_opcao(job,beat,op or {})
        if op is None or (not midia(job,op) and not clean):
            raise ValueError(f"O trecho {beat['id']} tem um take sem prévia disponível. Prepare as prévias ou escolha outra opção antes de renderizar.")
        if op.get('fonte')=='proprio':
            report=ler_json(P.RAIZ/job['sandbox']/'material'/f"avaliacao-{beat['id']}.json",{}) or {}
            row=next((r for r in report.get('takes',[]) if r.get('id')==op['id']),{})
            if row.get('adequado') is not True or not row.get('sheet') or not midia(job,{'sheet':row['sheet']}):
                raise ValueError('Analise visualmente o take próprio antes de usar na edição.')
