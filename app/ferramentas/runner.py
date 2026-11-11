"""Uma etapa independente, usando o motor salvo ao entrar na fila."""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from _comum import agora, now_slug, erro_simples
import producao as P
import ia
import fila


LIVRO_TIPOS=('analise','rebusca','producao','feedback')   # etapas que entram na aba Custos (o vídeo aparece assim que a 1ª começa)


def _custos_ao_vivo(job,status,tipo):
    """Aba Custos: cria/atualiza a linha do vídeo (status "em produção", "pronto" ou "erro"). Nunca derruba o job."""
    try:
        import custos
        custos.registrar_video_job(job,status)
    except Exception as e:
        print('(custo não registrado no livro: '+str(e)+')',file=sys.stderr)


PASSO={'analise':('Analisando e montando o storyboard','storyboard'),'rebusca':('Procurando outras opções pras cenas','storyboard'),
       'previas':('Gerando as prévias das cenas','storyboard'),'producao':('Produzindo o vídeo final','video'),
       'feedback':('Refazendo com o seu comentário','video'),'takes':('Avaliando os takes','preparar')}


def _andamento(job,fim=False,tipo=''):
    """Aba Em andamento: abre o passo da etapa e, no fim, diz o que o João tem que fazer. Nunca derruba o job."""
    try:
        import andamento as A
        cli,slug=job['cliente'],job['slug']
        if not fim:
            txt,et=PASSO.get(tipo,('Trabalhando','preparar'))
            if tipo=='feedback' and (job.get('feedbacks') or [{}])[-1].get('decisao')=='aprovado': txt,et='Registrando o aprendizado','pronto'
            A.passo(cli,slug,txt,etapa=et,titulo=job.get('titulo',''),formato=job.get('formato') or '',origem='tela')
            return
        st=job.get('status');sb=P.RAIZ/job.get('sandbox','')
        img=next((str(sb/n) for n in ('storyboard.jpg','folha.jpg') if (sb/n).is_file()),'')
        if st=='erro': A.erro(cli,slug,(job.get('erro') or 'Parou com erro')[:160])
        elif st=='interrompido': A.erro(cli,slug,'Interrompido')
        elif st in ('concluido','aprovado'):
            A.pronto(cli,slug,'Vídeo pronto: assista e aprove' if st=='concluido' else 'Aprovado',video=str(P.RAIZ/job['saida']) if job.get('saida') else '')
        elif st=='plano' and (sb/'storyboard.jpg').is_file() and ((A.carregar(cli,slug) or {}).get('passos') or [{}])[-1].get('texto','').startswith('Storyboard pronto'): pass
        elif st=='plano': A.espera(cli,slug,'Storyboard pronto: confira e aprove' if (sb/'storyboard.jpg').is_file() else 'Falta você escolher: abra o vídeo',imagem=img if (sb/'storyboard.jpg').is_file() else '')
        elif st=='plano_aprovado': A.espera(cli,slug,'Prévias prontas: confira e mande produzir',imagem=img)
        else: A.espera(cli,slug,'Etapa concluída: sua vez',imagem=img)
    except Exception as e:
        print('(andamento não registrado: '+str(e)+')',file=sys.stderr)


def _limite_da_ia(log) -> str:
    """O Claude parou por limite de uso ("You've hit your session limit · resets 7pm")? Devolve o aviso em português."""
    import re
    try:
        t=Path(log).read_text(encoding='utf-8',errors='ignore')[-4000:]
    except OSError:
        return ''
    if not re.search(r"hit your [a-z ]*limit|usage limit reached",t,re.I):
        return ''
    m=re.search(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)",t,re.I)
    if not m:
        return 'Acabou o limite de uso do Claude por agora. Espere um pouco e clique de novo.'
    h=int(m.group(1))%12+(12 if m.group(3).lower()=='pm' else 0)
    return f'Acabou o limite de uso do Claude por agora. Ele volta às {h}h{m.group(2) or ""}: depois disso, clique de novo.'


def _sem_login(log) -> str:
    """O claude -p respondeu "Not logged in" (a sessão do Claude caiu ou o refresh do login atrapalhou)? Devolve o aviso em português."""
    try:
        t=Path(log).read_text(encoding='utf-8',errors='ignore')[-4000:]
    except OSError:
        return ''
    if 'Not logged in' not in t and 'Please run /login' not in t:
        return ''
    return 'O Claude não está conectado agora (a sessão dele caiu). Abra o Claude no terminal, digite /login e clique em Tentar de novo.'


def _prazo_da_etapa(log) -> str:
    """A etapa passou do prazo (ia.MAX_MIN)? Devolve a frase que o ia.executar gravou no log."""
    try:
        t=Path(log).read_text(encoding='utf-8',errors='ignore')[-4000:]
    except OSError:
        return ''
    i=t.rfind('✖ Passou de ')
    return t[i+2:].splitlines()[0].strip() if i>=0 else ''


def _teto_da_etapa(log) -> str:
    """A etapa parou no teto de gasto (--max-budget-usd)? Devolve a frase simples que o ia.executar gravou no log."""
    try:
        t=Path(log).read_text(encoding='utf-8',errors='ignore')[-4000:]
    except OSError:
        return ''
    i=t.rfind('Parei no teto de US$')
    return t[i:].splitlines()[0].strip() if i>=0 else ''


def main():
    cli,slug,tipo,prompt_file=sys.argv[1:5]
    import os
    os.environ['ESTUDIO_JOB']=f'{cli}/{slug}'   # o claude -p herda: os passos que ele registrar caem neste vídeo
    status_ok=sys.argv[5] if len(sys.argv)>5 else ''
    item_id=sys.argv[6] if len(sys.argv)>6 else None
    job=P.carregar(cli,slug)
    pasta=P._pasta_job(cli,slug)
    token=(item_id or now_slug())[:12]
    log=pasta/f'{tipo}-{token}.log';raw=pasta/f'{tipo}-{token}.jsonl'
    s=job.get('ia') or ia.selecao()
    if tipo=='feedback': s=ia.para_alteracao(s)   # alteração = Sonnet, esforço alto
    exe=dict(tipo=tipo,inicio=agora(),fim=None,exit=None,log=log.name,raw=raw.name,ia=s)
    job.setdefault('execucoes',[]).append(exe)
    job['status']={'analise':'analisando','rebusca':'analisando','producao':'renderizando','previas':'previas','feedback':'feedback'}.get(tipo,'rodando')
    job.pop('erro',None)   # a tela não mostra o erro da tentativa anterior enquanto esta roda
    P.salvar(job)
    aprovando=tipo=='feedback' and (job.get('feedbacks') or [{}])[-1].get('decisao')=='aprovado'
    if tipo in LIVRO_TIPOS and not aprovando: _custos_ao_vivo(job,'em produção',tipo)
    _andamento(job,tipo=tipo)
    inicio=datetime.now()
    def event(ev):
        if 'total_cost_usd' in ev: exe['custo_usd']=ev['total_cost_usd']
        if ev.get('usage'): exe['tokens']=ev['usage']
    try:
        code=ia.executar(Path(prompt_file).read_text(encoding='utf-8'),log,raw,pasta/'runner.pid',s,event,tipo=tipo)
        if code!=0 and _sem_login(log):   # 29-out-2026: o login do Claude falhou por um instante; uma segunda tentativa quase sempre passa
            import time
            time.sleep(20)
            with log.open('a',encoding='utf-8') as f:f.write('\n(login do Claude falhou; tentando de novo uma vez)\n')
            code=ia.executar(Path(prompt_file).read_text(encoding='utf-8'),log,raw,pasta/'runner.pid',s,event,tipo=tipo)
        job=P.carregar(cli,slug)
        if job.get('status')=='interrompido':
            if tipo in LIVRO_TIPOS and not aprovando: _custos_ao_vivo(job,'interrompido',tipo)
            _andamento(job,fim=True)
            return
        if tipo == 'takes' and code == 0:
            import takes
            takes.validar_avaliacao(job, job.get('take_em_analise'))
            job.pop('take_em_analise', None)
        reprovou=''
        if tipo in ('producao','feedback'):
            aprovado=tipo=='feedback' and (job.get('feedbacks') or [{}])[-1].get('decisao')=='aprovado'
            render_novo = True if aprovado else P._detectar_saida(job,inicio,tipo)
            ok=code==0 and render_novo and bool(job.get('saida')) and (P.RAIZ/job['saida']).is_file()
            job['status']=('aprovado' if aprovado else 'concluido') if ok else 'erro'
            if ok and not aprovado:
                job.pop('edicao_alterada', None)
                try:   # ruído nos últimos 0,2 s (G10) é conserto mecânico: fade-out e silêncio no fim, vídeo intacto (checar_cauda.fechar)
                    import checar_cauda
                    f_=checar_cauda.fechar(P.RAIZ/job['saida'],P.RAIZ/job['sandbox']/'qa'/'antes-cauda.mp4')
                    if f_:
                        with log.open('a',encoding='utf-8') as fl:fl.write('\nFim do áudio: '+f_+'\n')
                except Exception as e_:
                    print('(cauda do áudio não conferida: '+str(e_)+')',file=sys.stderr)
                P.conferir_pos_render(job)   # sem conferência aprovada o Em andamento mostra os avisos, não "Vídeo pronto"
        else:
            ok=code==0 and (tipo not in ('analise','rebusca') or bool(P.plano(job)))
            reprovou=P.conferir_referencia(job) if ok and tipo=='analise' else ''   # referência sem a seção no ANALISE.md
            ok=ok and not reprovou
            job['status']=(status_ok or 'concluido') if ok else 'erro'
        if job['status']!='erro':
            job.pop('erro',None)   # a mensagem de uma tentativa anterior não fica pendurada num vídeo que deu certo
        else:
            job['erro']=(reprovou or _limite_da_ia(log) or _sem_login(log) or _teto_da_etapa(log) or _prazo_da_etapa(log) or
                         ('A execução foi interrompida. O vídeo gerado está disponível abaixo para assistir; a revisão final ficou pendente.'
                          if job.get('saida') else 'A etapa não terminou ou não entregou os arquivos esperados. Veja os detalhes da execução.'))
    except Exception as e:
        code=1;job=P.carregar(cli,slug);job['status']='erro';job['erro']=erro_simples(e)
        with log.open('a',encoding='utf-8') as f:f.write('\nFalha: '+str(e)+'\n')
    finally:
        (pasta/'runner.pid').unlink(missing_ok=True)
    exe.update(fim=agora(),exit=code)
    for n,x in enumerate(job.get('execucoes',[])):
        if x.get('log')==log.name: job['execucoes'][n]=exe
    P.salvar(job)
    _andamento(job,fim=True)
    if tipo in LIVRO_TIPOS and not aprovando:   # livro de vídeos da aba Custos: fecha "pronto" (produção/ajuste) ou atualiza o parcial
        if job.get('status')=='concluido' and tipo in ('producao','feedback'): _custos_ao_vivo(job,'pronto',tipo)
        elif job.get('status')=='erro': _custos_ao_vivo(job,'erro',tipo)
        else: _custos_ao_vivo(job,'em produção',tipo)
    if item_id: fila.finalizar(item_id,'concluido' if job['status']!='erro' else 'erro')
    if tipo in ('producao','feedback') and job.get('status')=='concluido' and not aprovando:   # o Estúdio confere o vídeo sozinho (revisao.py): processo próprio, não segura a fila
        try:
            import revisao
            revisao.disparar(cli,slug)
        except Exception as e:print('(revisão não disparada: '+str(e)+')',file=sys.stderr)
    # "Seguir direto até o vídeo final": storyboard pronto já vira vídeo, sem parar pro João aprovar
    if tipo=='analise' and job.get('status')=='plano' and job.get('seguir_direto'):
        try:P.avancar(cli,slug)
        except Exception as e:
            with log.open('a',encoding='utf-8') as f:f.write('\nSeguir direto falhou: '+str(e)+'\n')

if __name__=='__main__':main()
