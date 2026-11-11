"""Exportação transacional com manifesto SHA-256 e limpeza limitada ao job."""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from _comum import RAIZ, CACHE, agora, hoje, make_slug, gravar_json, ler_json, append_jsonl, cliente, modelo, thumb, ffprobe
import ia


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def seguro(path,root=None):
    root = root or RAIZ
    p=Path(path).resolve()
    if not p.is_relative_to(root.resolve()) or p==root.resolve():raise ValueError('Caminho fora da pasta permitida: '+str(path))
    return p


def base_destino(cli):
    cfg=ia.config();return Path(cfg.get('destinos',{}).get(cli) or cfg['destino_mac']).expanduser()


def destino(job,base=None):
    return Path(base or base_destino(job['cliente'])).expanduser()/job['cliente']/(hoje()+'-'+make_slug(job['slug']))


def comando_final(job):
    sb=seguro(RAIZ/job['sandbox'])
    data=ler_json(sb/'RESULTADO.json',{}) or {}
    if isinstance(data.get('comando'),str):return data['comando']
    for name in ('comando-v2.sh','comando.sh'):
        if (sb/name).is_file():return (sb/name).read_text().strip()
    txt=(sb/'RESULTADO.md').read_text() if (sb/'RESULTADO.md').exists() else ''
    blocks=re.findall(r'```(?:bash|sh|shell)?\s*\n(.*?)```',txt,re.S)
    return next((b.strip() for b in reversed(blocks) if 'gerar' in b or 'ffmpeg' in b), '')


def fontes(job):
    import producao as P
    sb=seguro(RAIZ/job['sandbox']);out=[];seen=set()
    def add(src,dst,required=False):
        src=seguro(src)
        if not src.is_file():
            if required:raise ValueError('Arquivo necessário não encontrado: '+str(src))
            return
        if str(src) in seen:return
        seen.add(str(src));out.append((src,Path(dst)))
    for r in [job.get('saida')]+[v.get('arquivo') for v in job.get('versoes',[])]:
        if r:add(RAIZ/r,'final/'+Path(r).name,True)
    add(RAIZ/job['bruto'],'bruto/'+Path(job['bruto']).name,True)
    for name in ('PLANO.json','BRIEF.md','RESULTADO.md','RESULTADO.json','ANALISE.md','PREVIAS.md'):
        add(sb/name,name)
    word=next((p for p in (sb/'work/words.json',sb/'words.json',sb/'transcricao.json') if p.is_file()),None)
    if word:add(word,'transcricao.json')
    for it in P.itens_para_acervo(job):
        group='musica' if it['tipo']=='audio' else 'cards' if it['tipo']=='imagem' else 'brolls'
        add(RAIZ/it['arquivo'],f"material/{group}/{make_slug(it['id'])}-{Path(it['arquivo']).name}",True)
    for p in (sb/'material').rglob('*'):
        if p.is_file():add(p,Path('material/proprio')/p.relative_to(sb/'material'))
    for p in P._pasta_job(job['cliente'],job['slug']).iterdir():
        if p.is_file() and p.name not in ('job.json','runner.pid','runner.out'):
            add(p,Path('registro')/p.name)
    return out


def verificar(job):
    base=Path(job.get('pasta_mac',''))
    manifest=job.get('exportacao',{}).get('arquivos',[])
    if not base.is_dir() or not manifest:raise ValueError('Exporte este vídeo antes de limpar. Falta um manifesto verificado.')
    for x in manifest:
        p=seguro(base/x['destino'],base)
        if not p.is_file() or sha(p)!=x['sha256']:raise ValueError('A cópia foi alterada ou está ausente: '+x['destino'])
    if not any(x['destino'].startswith('final/') for x in manifest):raise ValueError('Não há vídeo final verificado.')
    return True


def estrategia(job,exemplo=False):
    c=cliente(job['cliente']);m=modelo(c,job['modelo']);cmd=comando_final(job)
    if cmd and not job.get('modelo_estrategico_atualizado'):
        fp=m['pasta']/'ficha.json';f=ler_json(fp,{}) or {};anterior=f.get('comando','')
        f['comando']=cmd;gravar_json(fp,f)
        rp=m['pasta']/'aprendizado/regras.json';r=ler_json(rp,{}) or {};r['comando_referencia']=cmd;gravar_json(rp,r)
        resultado=RAIZ/job['sandbox']/'RESULTADO.md'
        append_jsonl(m['pasta']/'aprendizado/historico.jsonl',dict(tipo='comando_referencia',categoria='processo',
            texto=f"Vídeo {job['titulo']} aprovado e exportado.",comando_anterior=anterior,comando=cmd,
            motivo=resultado.read_text() if resultado.exists() else '',origem='usuario',createdAt=hoje(),job=job['slug']))
        job['modelo_estrategico_atualizado']=True
    if exemplo and not job.get('exemplo_salvo'):
        src=RAIZ/job['saida'];d=m['pasta']/'demos';d.mkdir(exist_ok=True)
        dur=ffprobe(src).get('duracao') or 3;idx=ler_json(d/'index.json',[]) or []
        for i,f in enumerate((.25,.5,.75)):
            name=f"exemplo-{job['slug']}-{i}.jpg"
            if not thumb(src,d/name,t=dur*f,largura=540):raise ValueError('Não foi possível extrair os frames de exemplo.')
            idx=[x for x in idx if x.get('arquivo')!=name]
            idx.append(dict(arquivo=name,titulo='Exemplo real · '+job['titulo'],descricao=f'{dur*f:.1f}s'))
        gravar_json(d/'index.json',idx);job['exemplo_salvo']=True
    if exemplo and job.get('formato') and not job.get('exemplo_formato'):
        # Exemplo vivo: o vídeo aprovado vira o exemplo PRINCIPAL do formato (a régua dos próximos); os antigos ficam.
        import formatos
        copia=Path(job['pasta_mac'])/'final'/Path(job['saida']).name if job.get('pasta_mac') else None
        try:
            novo=formatos.promover_exemplo(job['formato'],RAIZ/job['saida'],f"{job['titulo']} · {job['cliente']} · aprovado",
                                           origem=str(copia if copia and copia.is_file() else RAIZ/job['saida']),
                                           job=f"app/jobs/{job['cliente']}/{job['slug']}")
            job['exemplo_formato']=f"formatos/{job['formato']}/{novo['arquivo']}"
        except Exception as e:   # a exportação já está feita e conferida; o exemplo pode ser promovido depois pelo CLI
            job['exemplo_formato_erro']=str(e)


def exportar(cli,slug,base=None,apagar=False,exemplo=False):
    import producao as P
    from fila import bloqueio
    with bloqueio(P._pasta_job(cli,slug)/'.export.lock'):
        job=P.carregar(cli,slug)
        if not job or job.get('rodando') or job['status'] not in ('aprovado','exportado'):
            raise ValueError('Aprove o vídeo final e aguarde as execuções terminarem antes de finalizar.')
        if job.get('feedbacks') and job['feedbacks'][-1]['decisao']!='aprovado':raise ValueError('Ainda há ajuste pendente.')
        if job.get('exportacao'):
            verificar(job)
        else:
            files=fontes(job);target=destino(job,base).resolve()
            if target.is_relative_to((RAIZ/job['sandbox']).resolve()) or target.is_relative_to(P._pasta_job(cli,slug).resolve()):
                raise ValueError('Escolha um destino fora dos arquivos temporários do vídeo.')
            if target.exists():target=target.with_name(target.name+'-'+uuid.uuid4().hex[:6])
            parent=target.parent
            ancestor=parent
            while not ancestor.exists():ancestor=ancestor.parent
            total=sum(src.stat().st_size for src,_ in files)
            if shutil.disk_usage(ancestor).free<total*1.1+16*1024*1024:raise ValueError('Espaço insuficiente no destino. Libere espaço e tente novamente.')
            parent.mkdir(parents=True,exist_ok=True)
            stage=parent/('.export-'+uuid.uuid4().hex);stage.mkdir()
            manifest=[]
            try:
                for src,dst in files:
                    dest=stage/dst;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
                    digest=sha(src)
                    if digest!=sha(dest):raise ValueError('Falha ao verificar a cópia: '+src.name)
                    manifest.append(dict(origem=str(src.relative_to(RAIZ.resolve())),destino=str(dst),sha256=digest,tamanho=src.stat().st_size))
                rows=['# Material utilizado','', '| Arquivo | Descrição | Fonte | Autor | Condição de uso | Beat / fala |','|---|---|---|---|---|---|']
                for it in P.itens_para_acervo(job):
                    vals=[it['arquivo'],it.get('descricao') or it.get('motivo',''),it.get('fonte',''),it.get('autor',''),it.get('licenca',''),it.get('beat','')+' '+it.get('fala','')]
                    rows.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in vals)+' |')
                (stage/'material.md').write_text('\n'.join(rows),encoding='utf-8')
                manifest.append(dict(destino='material.md',sha256=sha(stage/'material.md'),tamanho=(stage/'material.md').stat().st_size))
                gravar_json(stage/'manifesto.json',{'cliente':cli,'job':slug,'arquivos':manifest,'em':agora()})
                os.rename(stage,target)
            except Exception:
                shutil.rmtree(stage,ignore_errors=True)
                raise
            job.update(pasta_mac=str(target),hash_final=next(x['sha256'] for x in manifest if x['origem']==job['saida']),
                       exportacao={'arquivos':manifest,'verificado_em':agora()},fechado_em=agora(),status='exportado',
                       takes_resumo=[{'beat':b['id'],'fala':b.get('fala',''),'escolha':b.get('escolha')} for b in (P.plano(job) or {}).get('beats',[])])
            P.salvar(job)
        estrategia(job,exemplo);P.salvar(job)
    if apagar:return limpar(cli,slug)
    return P.carregar(cli,slug)


def limpar(cli,slug):
    import producao as P
    job=P.carregar(cli,slug)
    if not job or job.get('rodando') or job['status'] not in ('exportado','arquivado'):raise ValueError('Exporte primeiro e aguarde o término da execução.')
    verificar(job)
    sb=seguro(RAIZ/job['sandbox']);c=cliente(cli);mp=(c['content']/'modelos'/job['modelo']).resolve()
    if sb.parent!=mp or sb.name!='_sandbox-'+slug:raise ValueError('Sandbox não corresponde a este vídeo.')
    output=(c['content']/'output'/job['modelo']).resolve()
    outputs=[]
    for r in [job.get('saida')]+[v.get('arquivo') for v in job.get('versoes',[])]:
        if not r:continue
        p=seguro(RAIZ/r)
        if p.parent!=output or not re.fullmatch(re.escape(slug)+r'(?:-v\d+)?\.mp4',p.name):
            raise ValueError('Render fora do escopo deste vídeo; preservado: '+p.name)
        outputs.append(p)
    # Revalida fontes: se render/material mudou depois da cópia, não limpa.
    for x in job['exportacao']['arquivos']:
        if not x.get('origem'):continue
        p=seguro(RAIZ/x['origem'])
        if p.is_file() and sha(p)!=x['sha256']:raise ValueError('Arquivo alterado após exportação; preservado: '+p.name)
    if sb.exists():shutil.rmtree(sb)
    for p in outputs:p.unlink(missing_ok=True)
    for p in CACHE.rglob('*'):
        if p.is_file() and slug in p.name:p.unlink(missing_ok=True)
    job['status']='arquivado';job['fechado_em']=agora();P.salvar(job)
    folder=P._pasta_job(cli,slug)
    for p in folder.iterdir():
        if p.name=='job.json':continue
        if p.is_file():p.unlink()
    return P.carregar(cli,slug)
