"""Fila persistente, FIFO, com limites separados e exclusão entre processos (flock)."""
from __future__ import annotations
import fcntl
import os
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from _comum import ESTUDIO, RAIZ, agora, com_venv, ensure, gravar_json, ler_json
import ia

FILA=ESTUDIO/'fila.json'
LOCK=ESTUDIO/'.fila.lock'

@contextmanager
def bloqueio(path=LOCK, nonblocking=False):
    ensure(path.parent)
    with path.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        try: yield
        finally: fcntl.flock(f,fcntl.LOCK_UN)


def ler(): return ler_json(FILA,[]) or []


def enfileirar(job,prompt,tipo,status_ok=None):
    import producao as P
    with bloqueio():
        items=ler()
        if any(x['cliente']==job['cliente'] and x['slug']==job['slug'] and x['estado'] in ('na_fila','rodando') for x in items):
            return
        cfg=dict(ia.selecao(),**(job.get('ia_escolhida') or {}))   # o modelo/esforço que o João escolheu no Criar vale pra este vídeo todo (antes a fila trocava pelo de Configurações)
        if not ia.disponivel(): raise ValueError('Configure o motor de IA antes de iniciar a produção.')
        jid=uuid.uuid4().hex
        pasta=ensure(P._pasta_job(job['cliente'],job['slug']))
        pf=pasta/f'prompt-{tipo}-{jid}.txt';pf.write_text(prompt,encoding='utf-8')
        items.append(dict(id=jid,cliente=job['cliente'],slug=job['slug'],tipo=tipo,prompt=str(pf),
                          status_ok=status_ok,estado='na_fila',criado_em=agora(),ia=cfg))
        gravar_json(FILA,items)
        fresh=P.carregar(job['cliente'],job['slug']) or job
        fresh.update(status='na_fila',fila_id=jid,etapa_fila=tipo,ia=cfg)
        P.salvar(fresh)
    iniciar()


def iniciar():
    with (ESTUDIO/'.fila.log').open('a') as log:
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'worker'],cwd=RAIZ,env=com_venv(),
                         start_new_session=True,stdout=log,stderr=subprocess.STDOUT)


def vivo(pid):
    try: os.kill(int(pid),0);return True
    except (OSError,ValueError,TypeError): return False


def cancelar(cli,slug):
    import producao as P
    with bloqueio():
        items=ler()
        for x in items:
            if (x['cliente'],x['slug'])!=(cli,slug) or x['estado'] not in ('na_fila','rodando'): continue
            if x.get('pid') and vivo(x['pid']):
                try: os.killpg(x['pid'],signal.SIGTERM)
                except ProcessLookupError: pass
            x['estado']='cancelado';x['fim']=agora()
        gravar_json(FILA,items)
        j=P.carregar(cli,slug)
        if j:
            j['status']='interrompido';P.salvar(j)
            (P._pasta_job(cli,slug)/'runner.pid').unlink(missing_ok=True)
    return True


def priorizar(cli,slug):
    with bloqueio():
        items=ler();front=[x for x in items if (x['cliente'],x['slug'],x['estado'])==(cli,slug,'na_fila')]
        gravar_json(FILA,front+[x for x in items if x not in front])


def finalizar(item_id,estado):
    with bloqueio():
        items=ler()
        for x in items:
            if x['id']==item_id and x['estado']!='cancelado': x.update(estado=estado,fim=agora())
        gravar_json(FILA,items)


def _aviso(como,x,texto):
    """Conta no Em andamento o que a fila fez (queda, retomada)."""
    try:
        import andamento
        getattr(andamento,como)(x['cliente'],x['slug'],texto)
    except Exception: pass


def posicao(cli,slug):
    """Lugar do vídeo na fila do mesmo grupo (1 = o próximo). 0 se não está esperando."""
    def grupo(x): return 'render' if x['tipo'] in ('producao','previas','feedback') else 'analise'
    items=[x for x in ler() if x['estado']=='na_fila']
    meu=next((x for x in items if (x['cliente'],x['slug'])==(cli,slug)),None)
    if not meu: return 0
    return 1+sum(1 for x in items[:items.index(meu)] if grupo(x)==grupo(meu))


def ciclo():
    # Recolhe filhos terminados antes do teste de PID (zumbis ainda respondem a kill(0)).
    try:
        while os.waitpid(-1, os.WNOHANG)[0]: pass
    except ChildProcessError: pass
    import producao as P
    cfg=ia.config()
    with bloqueio():
        items=ler()
        for x in items:
            if x['estado']=='rodando' and not vivo(x.get('pid')):
                x.update(estado='erro',fim=agora())
                j=P.carregar(x['cliente'],x['slug'])
                if j and j['status'] in ('na_fila','rodando','analisando','renderizando','feedback','previas'):
                    if x.get('tentativa',0)<1 and not j.get('saida') and Path(x.get('prompt','')).exists():
                        # caiu no meio (Mac dormiu, Estúdio reiniciou): recomeça sozinho, 1 vez
                        novo=dict(x,id=uuid.uuid4().hex,estado='na_fila',criado_em=agora(),tentativa=1)
                        for k in ('pid','inicio','fim'): novo.pop(k,None)
                        items.append(novo)
                        j.update(status='na_fila',fila_id=novo['id']);j.pop('erro',None);P.salvar(j)
                        _aviso('passo',x,'Caiu no meio: recomeçando sozinho')
                        continue
                    j.update(status='erro',erro='Parou no meio (o Mac dormiu ou o Estúdio reiniciou). Clique em Tentar de novo.');P.salvar(j)
                    _aviso('erro',x,j['erro'])
                    try:
                        import custos
                        custos.registrar_video_job(j,'erro')
                    except Exception: pass
        def grupo(x): return 'render' if x['tipo'] in ('producao','previas') or x.get('tipo')=='feedback' else 'analise'
        usados={g:sum(x['estado']=='rodando' and grupo(x)==g for x in items) for g in ('render','analise')}
        limites={'render':cfg['renders_simultaneos'],'analise':cfg['analises_simultaneas']}
        for x in items:
            g=grupo(x)
            if x['estado']!='na_fila' or usados[g]>=limites[g]: continue
            pasta=P._pasta_job(x['cliente'],x['slug'])
            if not (pasta/'job.json').exists(): x['estado']='cancelado';continue
            with (pasta/'runner.out').open('a') as out:
                proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('runner.py')),
                    x['cliente'],x['slug'],x['tipo'],x['prompt'],x.get('status_ok') or '',x['id']],
                    cwd=RAIZ,env=com_venv(),start_new_session=True,stdout=out,stderr=subprocess.STDOUT)
            x.update(estado='rodando',pid=proc.pid,inicio=agora());usados[g]+=1
            (pasta/'runner.pid').write_text(str(proc.pid))
        gravar_json(FILA,items)
        return any(x['estado'] in ('na_fila','rodando') for x in items)


def worker():
    try:
        while True:
            with bloqueio(ESTUDIO/'.fila-worker.lock',True):
                while ciclo(): time.sleep(2)
            # Um enqueue pode ter chegado entre o último ciclo e a liberação
            # do worker. Confira depois de liberar: seu processo já pode ter
            # desistido do lock, mas o pedido ainda precisa ser atendido.
            with bloqueio():
                if not any(x['estado'] in ('na_fila','rodando') for x in ler()):
                    return
    except BlockingIOError: pass

if __name__=='__main__': worker()
