"""Consolidação conservadora e reversível: cobertura, valores e histórico preservados."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path
from _comum import RAIZ, hoje, agora, gravar_json, ler_json, make_slug

CATEGORIAS=('legenda','broll','beats','layout','enquadramento','audio','cards','copy','qa','processo')
MAPA={'musica':'audio','som':'audio','sfx':'audio','card':'cards','insert':'cards','imagem':'broll','assets':'broll',
      'ritmo':'beats','timing':'beats','punch':'beats','motion':'beats','motion-design':'beats','animacao':'beats',
      'abertura':'beats','intro':'beats','edicao':'beats','montagem':'beats','faixa':'layout','estrutura':'layout',
      'cor':'layout','fonte':'layout','identidade':'layout','tipografia':'layout','topo':'layout','posicao':'layout',
      'formato':'layout','estilo':'layout','area-segura':'layout','oferta':'copy','recorte':'enquadramento',
      'producao':'processo','render':'processo','transcricao':'processo','entrega':'processo','performance':'processo',
      'tecnico':'processo','organizacao':'processo'}


PALAVRAS_DO_ASSUNTO=[(r'm[úu]sica|trilha|cl[ií]ch[êe]|\bsom\b|sfx|efeito sonoro|volume','audio'),
                     (r'b-?roll|cena de apoio|clipe','broll'),(r'legenda','legenda'),(r'\bcards?\b|cartela|frase na tela','cards'),
                     (r'\bcor\b|cores|fonte|faixa|layout','layout'),(r'enquadr|zoom|recorte|\bcrop\b','enquadramento'),
                     (r'ritmo|\bbeats?\b|timing|corte','beats')]


def categoria_do_texto(texto,padrao='geral'):
    """Assunto de um feedback pela palavra (o João não escolhe): música/trilha/clichê → audio, b-roll → broll, cor → layout…"""
    t=str(texto or '').lower()
    for rx,c in PALAVRAS_DO_ASSUNTO:
        if re.search(rx,t):return c
    return padrao


def categoria(r):
    c=r.get('categoria')
    if c in CATEGORIAS:return c
    if c in MAPA:return MAPA[c]
    text=make_slug(str(r.get('id',''))+' '+str(r.get('texto','')),10000)
    for key,c in [('legenda','legenda'),('b-roll','broll'),('broll','broll'),('musica','audio'),('sfx','audio'),
                  ('audio','audio'),('card','cards'),('beat','beats'),('zoom','enquadramento'),('crop','enquadramento'),
                  ('fonte','layout'),('cor-','layout'),('manchete','copy'),('qa-','qa')]:
        if key in text:return c
    return 'processo'


def instrucao(r):
    return '\n'.join(str(v) if isinstance(v,str) else json.dumps(v,ensure_ascii=False) for k,v in r.items()
                     if k not in ('id','categoria','peso','createdAt','desde','cobre','origem'))


def tokens(text):
    # Tokens concretos por regra, incluindo flags, decimais, hex, URL e caminhos.
    return set(re.findall(r'https?://[^\s"<>]+|(?:[\w.~@-]+/)+[^\s"<>;,]+|--[\w-]+|#[\da-fA-F]{3,8}\b|\d+(?:[.,:]\d+)*',text))


def validar(antigo,novo):
    erros=[];old=antigo.get('regras',[]);new=novo.get('regras',[])
    ids=[r.get('id') for r in new]
    if len(ids)!=len(set(ids)) or any(not x for x in ids):erros.append('IDs novos vazios ou duplicados')
    conhecidos={r.get('id',f'regra-{i+1}') for i,r in enumerate(old)}
    for r in new:
        if r.get('categoria') not in CATEGORIAS:erros.append('Categoria inválida: '+str(r.get('categoria')))
        if not r.get('cobre'):erros.append('Regra sem cobertura: '+str(r.get('id')))
    for i,r in enumerate(old):
        rid=r.get('id',f'regra-{i+1}')
        cobertura=[x for x in new if rid in x.get('cobre',[])]
        if not cobertura:erros.append('Sem cobertura: '+rid);continue
        texto='\n'.join(instrucao(x) for x in cobertura)
        faltam=tokens(instrucao(r))-tokens(texto)
        if faltam:erros.append(rid+': valores perdidos '+', '.join(sorted(faltam)))
    return erros


def propor(d):
    if d.get('consolidacao'): return d
    novo=copy.deepcopy(d);groups={}
    for i,r in enumerate(d.get('regras',[])):
        groups.setdefault(categoria(r),[]).append((i,r))
    regras=[]
    for cat,entries in groups.items():
        textos=[];evitar=[];ids=[];extras=[];dates=[]
        for i,r in entries:
            rid=r.get('id',f'regra-{i+1}');ids.append(rid)
            texto=str(r.get('texto','')).strip()
            # A variante fica explícita, sem aplicar filme à edição de notícia.
            if str(d.get('cliente','')).lower()=='cliente3':
                label='NOTÍCIA' if any(x in texto.lower() for x in ('ocupacional','concausa','telejornal','bed-noticia')) else 'FILME' if any(x in texto.lower() for x in ('suits','shawshank','filme real','wolf')) else ''
                if label:texto=f'Variante {label}: '+texto
            if texto and texto not in textos:textos.append(texto)
            if r.get('evitar') and str(r['evitar']) not in evitar:evitar.append(str(r['evitar']))
            extra={k:v for k,v in r.items() if k not in ('id','categoria','peso','texto','evitar','createdAt','desde','cobre','origem')}
            if extra:extras.append(extra)
            if r.get('desde') or r.get('createdAt'):dates.append(str(r.get('desde') or r.get('createdAt')))
        regra=dict(id=cat+'-consolidado',categoria=cat,peso=max(int(r.get('peso',5)) for _,r in entries),
                   texto='\n\n'.join(textos),evitar='; '.join(evitar),cobre=ids,desde=min(dates) if dates else hoje())
        if extras:regra['detalhes_preservados']=extras
        regras.append(regra)
    novo['regras']=regras
    return novo


def consolidar(path):
    d=ler_json(path)
    if not isinstance(d,dict) or 'regras' not in d:return None
    if d.get('consolidacao'):return {'modelo':str(path),'antes':d['consolidacao']['antes'],'depois':len(d['regras']),'existente':True}
    novo=propor(d);errors=validar(d,novo)
    if errors:raise ValueError('; '.join(errors))
    archive=path.with_name('regras-arquivo-'+hoje()+'.json')
    if archive.exists():
        archive=path.with_name('regras-arquivo-'+hoje()+'-'+hashlib.sha256(path.read_bytes()).hexdigest()[:10]+'.json')
    if not archive.exists():shutil.copy2(path,archive)
    novo['consolidacao']={'em':agora(),'arquivo':archive.name,'antes':len(d['regras']),
                          'sha256_original':hashlib.sha256(archive.read_bytes()).hexdigest(),
                          'metodo':'agrupamento conservador por categoria; instruções preservadas'}
    gravar_json(path,novo)
    return {'modelo':str(path),'antes':len(d['regras']),'depois':len(novo['regras'])}


def restaurar(path):
    d=ler_json(path,{}) or {};info=d.get('consolidacao') or {}
    name=info.get('arquivo','')
    if not name or Path(name).name!=name:raise ValueError('Arquivo de restauração inválido.')
    src=path.with_name(name)
    if not src.is_file() or hashlib.sha256(src.read_bytes()).hexdigest()!=info.get('sha256_original'):
        raise ValueError('O arquivo original não passou na verificação de integridade.')
    # Preserva inclusive feedback novo dado após a consolidação.
    backup=path.with_name('regras-antes-de-restaurar-'+agora().replace(':','-').replace(' ','-')+'.json')
    shutil.copy2(path,backup);shutil.copy2(src,path)


def originais(path,rule):
    d=ler_json(path,{}) or {};name=(d.get('consolidacao') or {}).get('arquivo','')
    if not name or Path(name).name!=name:return []
    old=ler_json(path.with_name(name),{}) or {}
    return [r for i,r in enumerate(old.get('regras',[])) if r.get('id',f'regra-{i+1}') in rule.get('cobre',[])]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--validar',action='store_true');ap.add_argument('--aplicar',action='store_true');ap.add_argument('--modelo')
    args=ap.parse_args()
    paths=[Path(args.modelo)] if args.modelo else sorted(RAIZ.glob('*/*Content/modelos/*/aprendizado/regras.json'))
    paths+=[] if args.modelo else sorted(RAIZ.glob('Geral/modelos/*/aprendizado/regras.json'))
    errors=[]
    for p in paths:
        d=ler_json(p,{}) or {}
        if args.aplicar:print(json.dumps(consolidar(p),ensure_ascii=False))
        else:
            c=d.get('consolidacao')
            old=ler_json(p.with_name(c['arquivo'])) if c else d
            e=validar(old,d if c else propor(d));errors.extend(e)
            print(f'{p.relative_to(RAIZ)}: '+ ('OK' if not e else '; '.join(e)))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
