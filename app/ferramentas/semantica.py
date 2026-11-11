"""Busca por fala com embeddings locais incrementais e alternativa textual explícita."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
import shlex
import unicodedata
from pathlib import Path
from _comum import BROLLS, ESTUDIO, gravar_json, ler_json
import ia

INDICE=BROLLS/'indice.json'
_MODEL=None
_STOP=set('a o as os de da do das dos e em um uma que para por com no na nos nas eu voce ele ela isso esse essa tem ser ao se'.split())
_SINONIMOS={'dinheiro':'financas lucro receita faturamento money cash','medo':'tensao suspense ansiedade fear',
            'tempo':'relogio prazo pressa time clock','trabalho':'escritorio equipe empresa work office',
            'saude':'medico clinica dentista hospital health medical','sucesso':'vitoria conquista resultado success',
            'cansaco':'exaustao estresse burnout cansaço','familia':'mae pai filho family'}


def normalizar(s):return unicodedata.normalize('NFKD',s.lower()).encode('ascii','ignore').decode()


def palavras(s):
    raw=set(re.findall(r'[a-z0-9]+',normalizar(s)))-_STOP
    for root,terms in _SINONIMOS.items():
        group=set(normalizar(root+' '+terms).split())
        if raw & group:raw |= group
    return raw


def texto(it):
    return '\n'.join(str(it.get(k) or '') for k in ('titulo','descricao','movimento','emocao','serve_para','evitar','fala','observacao'))+' '+', '.join(it.get('tags',[]))


def encoder(download=False):
    global _MODEL
    if _MODEL is not None:return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL=SentenceTransformer(ia.config()['embedding_model'],local_files_only=not download,cache_folder=str(ESTUDIO/'modelos-locais'),device='cpu')   # cpu: sem MPS/Metal no Python do app
        return _MODEL
    except (ImportError,OSError,ValueError):return None


def reindexar(download=False):
    import acervo
    from fila import bloqueio
    with bloqueio(BROLLS/'.indice.lock'):
        model=encoder(download)
        engine=ia.config()['embedding_model'] if model else 'texto-local'
        old=ler_json(INDICE,{}) or {};entries={};changes=0
        for it in acervo.listar():
            text=texto(it);h=hashlib.sha256(text.encode()).hexdigest();prev=old.get('itens',{}).get(it['slug'],{})
            if prev.get('hash')==h and old.get('motor')==engine:entries[it['slug']]=prev;continue
            vector=model.encode(text,normalize_embeddings=True).tolist() if model else None
            entries[it['slug']]={'hash':h,'texto':text,'vetor':vector};changes+=1
        data={'motor':engine,'itens':entries,'alterados':changes}
        if old.get('favoritos'):data['favoritos']=old['favoritos']
        gravar_json(INDICE,data)
        return data


def consultar(fala,top=5,tipo='',limiar=None,tag=''):
    import acervo
    data=reindexar();model=encoder() if data['motor']!='texto-local' else None
    vector=model.encode(fala,normalize_embeddings=True).tolist() if model else None
    q=palavras(fala);result=[]
    for it in acervo.listar(tag=tag,tipo=tipo):
        row=data['itens'].get(it['slug'],{})
        if vector and row.get('vetor'):
            score=sum(a*b for a,b in zip(vector,row['vetor']))
        else:
            p=palavras(row.get('texto',''));score=len(p&q)/max(1,math.sqrt(len(q)*len(p)))
        if score>=(limiar if limiar is not None else (0.35 if vector else 0.08)):
            it.update(similaridade=round(score,3),busca_motor='semantica' if vector else 'texto');result.append(it)
    return sorted(result,key=lambda x:x['similaridade'],reverse=True)[:top]


def politica(briefing):
    text=normalizar(briefing or '')
    if any(x in text for x in ('nao usa o acervo','nao usar o acervo','nao use o acervo','tudo novo','ignorar acervo')):return 'ignorar'
    if any(x in text for x in ('olha o acervo','use o acervo','usa o acervo','usa o que tem no acervo','priorize o acervo','musica do acervo')):return 'priorizar'
    return 'complementar'


def prompt(job):
    policy=politica(job.get('briefing',''))
    return f'''\nPOLÍTICA DO ACERVO VISUAL DESTE BRIEFING: {policy}. Esta decisão se aplica a b-roll e imagens.
MÚSICA tem política separada: sempre consulte primeiro o acervo, mesmo sem briefing; só busque fora se nenhuma faixa servir.
Se ignorar: NÃO consulte nem proponha itens do acervo. Se priorizar: itens compatíveis são a primeira opção.
Se complementar: só acrescente opção do acervo com similaridade >= {ia.config()['similaridade_acervo']}.
Depois de transcrever, para CADA beat consulte: {shlex.quote(sys.executable)} app/ferramentas/semantica.py --fala "FALA E INTENÇÃO" --top 5
A saída declara se a busca usou embedding ou texto. Um score textual NÃO comprova equivalência semântica: confira cena e fala.
Respeite restrições do modelo, usos anteriores e verifique frames antes de propor. Marque fonte="acervo" e acervo=<slug>.
Regras gerais deste cliente: <Content>/aprendizado/regras-gerais.json (leia se existir).
Nenhum item entra no acervo sem ação explícita do João. Sugira descrição, emoção, movimento, usos adequados, limitações e tags no RESULTADO.json.
'''


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fala');ap.add_argument('--top',type=int,default=5);ap.add_argument('--instalar',action='store_true');a=ap.parse_args()
    if a.instalar:
        result=reindexar(True)
        if result['motor']=='texto-local':raise SystemExit('Embedding indisponível. Instale sentence-transformers e tente novamente.')
        print(result['motor']);return
    if a.fala:
        result=consultar(a.fala,a.top,limiar=0)
        print(json.dumps([{k:v for k,v in x.items() if k not in ('pasta','clip')} for x in result],ensure_ascii=False))
    else:print(json.dumps({'motor':reindexar()['motor']},ensure_ascii=False))

if __name__=='__main__':main()
