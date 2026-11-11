"""Referência → evidências determinísticas → proposta → construção aprovada → prova."""
from __future__ import annotations
import array
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from _comum import ESTUDIO, RAIZ, agora, hoje, ensure, gravar_json, ler_json, cliente, clientes, modelo, rel, ffprobe, append_jsonl
import ia

ESTUDOS=ESTUDIO/'estudos'


def carregar(slug):
    if Path(slug).name!=slug or slug in ('.','..'):raise ValueError('Referência inválida.')
    return ler_json(ESTUDOS/slug/'estado.json')


def salvar(d):gravar_json(ESTUDOS/d['slug']/'estado.json',d)

def remover(slug):
    """Apaga uma referência que não serve mais (estado + pasta de estudo dentro do cliente)."""
    d=carregar(slug)
    if not d:return False
    sb=(RAIZ/d['sandbox']).resolve()
    if sb.name=='_estudo-'+slug and sb.is_dir():shutil.rmtree(sb)
    pasta=(ESTUDOS/slug).resolve()
    if pasta.parent==ESTUDOS.resolve():shutil.rmtree(pasta,ignore_errors=True)
    return True


ERROS_SIMPLES={'403':'O site bloqueou o download (403). Baixe o vídeo e envie o arquivo em vez do link.',
               '404':'O link não existe mais (404).','timed out':'Demorou demais pra responder. Tente de novo.',
               'proposta':'A IA não terminou a análise. Tente de novo.'}


def erro_simples(d):
    e=str(d.get('erro') or '')
    for k,v in ERROS_SIMPLES.items():
        if k in e:return v
    return e[:160]


def listar():return sorted((ler_json(p) for p in ESTUDOS.glob('*/estado.json')),key=lambda x:x['criado_em'],reverse=True)


# O que olhar numa referência. Mandar "copia esse estilo" é vago: marcando os pontos (e escrevendo
# o que chamou a atenção em cada um) a análise sabe ONDE prestar atenção e o João não precisa
# descrever edição com palavras técnicas que ele não usa.
PONTOS_DE_OBSERVACAO = [
    ("gancho", "Gancho", "os 3 primeiros segundos: o que prende"),
    ("ritmo", "Ritmo e cortes", "quando corta, quanto dura cada plano"),
    ("legenda", "Legenda", "fonte, posição, animação, quantas palavras por vez"),
    ("enquadramento", "Enquadramento", "como a pessoa aparece, zoom, punch"),
    ("cards", "Cards e tipografia", "caixas de texto, destaque de palavra"),
    ("broll", "B-roll e inserts", "o que entra por cima/embaixo e em que momento"),
    ("cor", "Cor e tratamento", "filtro, contraste, textura, grão"),
    ("audio", "Música e efeitos", "cama, SFX, volume, onde entra e sai"),
    ("copy", "Copy e estrutura", "como o texto é construído, promessa, virada"),
    ("transicoes", "Transições e movimento", "como passa de um plano pro outro"),
]


def briefing_com_pontos(livre: str, marcados: list, notas: dict, momentos: str) -> str:
    """Junta o pedido livre + os pontos marcados + os momentos num BRIEF que a análise entende."""
    rotulos = {k: (r, d) for k, r, d in PONTOS_DE_OBSERVACAO}
    linhas = [(livre or "").strip()]
    escolhidos = [k for k in marcados if k in rotulos]
    if escolhidos:
        linhas += ["", "## Pontos de observação (é AQUI que ele quer que você olhe)", ""]
        for k in escolhidos:
            nota = (notas.get(k) or "").strip()
            linhas.append(f"- **{rotulos[k][0]}** ({rotulos[k][1]})" + (f": {nota}" if nota else ""))
    if (momentos or "").strip():
        linhas += ["", "## Momentos que ele marcou", ""]
        linhas += [f"- {l.strip()}" for l in momentos.splitlines() if l.strip()]
    if escolhidos or (momentos or "").strip():
        linhas += ["", "Responda ponto a ponto: o que o vídeo faz ali, com número (tempo, tamanho, cor, "
                       "duração), e o que é estilo aproveitável (nunca o conteúdo)."]
    return "\n".join(linhas).strip()


def _lista(x):
    """Aceita um item (str/Path) ou uma lista e devolve sempre lista, sem vazios."""
    if not x:return []
    if isinstance(x,(str,os.PathLike)):return [x]
    return [i for i in x if i]


def _ligar(origem,destino):
    """Segundo nome para o mesmo arquivo (sem duplicar espaço); se o disco não deixar, copia."""
    Path(destino).unlink(missing_ok=True)
    try:os.link(origem,destino)
    except OSError:shutil.copy2(origem,destino)


def criar(cli,video=None,url='',anexos=(),briefing='',inicio=None,fim=None):
    """Cria o estudo. `video` e `url` aceitam UM item (como antes) ou uma LISTA: vários vídeos do mesmo estilo."""
    c=cliente(cli)
    if not c:raise ValueError('Escolha um cliente válido.')
    videos=_lista(video);urls=[]
    for u in _lista(url):
        for linha in str(u).splitlines():
            linha=linha.strip()
            if linha and linha not in urls:urls.append(linha)
    if not videos and not urls:raise ValueError('Envie um vídeo de referência ou um link.')
    for u in urls:
        if not u.startswith(('https://','http://')):raise ValueError('Use um link HTTP ou HTTPS: '+u[:80])
    start=float(inicio) if inicio not in (None,'') else None;end=float(fim) if fim not in (None,'') else None
    if (start is None)!=(end is None) or start is not None and (start<0 or end<=start):raise ValueError('Informe início e fim válidos, em segundos.')
    slug='ref-'+uuid.uuid4().hex[:10];sb=ensure(c['content']/('_estudo-'+slug))
    # Um vídeo: referencia.<ext>, como sempre. Vários: referencia-1.<ext>, referencia-2.<ext>... e o
    # referencia.<ext> que o resto do código procura (aqui o primeiro; o preparar troca por uma montagem).
    fontes=[]
    for i,v in enumerate(videos,1):
        ext=Path(v).suffix.lower();nome='referencia'+ext if len(videos)==1 and not urls else f'referencia-{i}{ext}'
        shutil.move(str(v),sb/nome);fontes.append(dict(n=i,origem='arquivo',arquivo=nome,nome=Path(v).stem))
    if len(fontes)>1 or (fontes and urls):_ligar(sb/fontes[0]['arquivo'],sb/('referencia'+Path(fontes[0]['arquivo']).suffix))
    for k,u in enumerate(urls):fontes.append(dict(n=len(videos)+k+1,origem='link',url=u))
    for p in anexos:shutil.move(str(p),ensure(sb/'anexos')/Path(p).name)
    (sb/'BRIEF.md').write_text(briefing,encoding='utf-8')
    titulo=fontes[0].get('nome') or fontes[0]['url']
    if len(fontes)>1:titulo+=f' (+{len(fontes)-1})'
    d=dict(slug=slug,cliente=cli,titulo=titulo,criado_em=agora(),
           sandbox=rel(sb),url=urls[0] if urls else '',urls=urls,fontes=fontes,briefing=briefing,inicio=start,fim=end,status='novo',ia=ia.selecao())
    salvar(d);return d


def iniciar(slug,fase='analisar',nome=None):
    from fila import vivo,bloqueio
    if fase not in ('analisar','construir'):raise ValueError('Etapa de referência inválida.')
    carregar(slug)  # valida o identificador antes de abrir o lock
    with bloqueio(ESTUDOS/slug/'.lock'):
        d=carregar(slug)
        if not d:raise ValueError('Referência não encontrada.')
        if d.get('pid') and vivo(d['pid']):raise ValueError('A referência já está em processamento.')
        if fase=='construir':
            retry=d['status']=='erro' and d.get('fase_erro')=='construir'
            if d['status']!='proposta' and not retry:raise ValueError('Aguarde e revise a proposta antes de construir.')
            if retry and nome!=d.get('nome_aprovado'):raise ValueError('Retome com o nome já aprovado para este modelo.')
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',nome or ''):raise ValueError('Use um nome curto, em letras minúsculas e hífens.')
            dst=cliente(d['cliente'])['content']/'modelos'/nome
            if dst.exists() and (not retry or ler_json(dst/'.estudo-origem.json',{}).get('slug')!=slug):raise ValueError('Já existe um modelo com esse nome.')
            d['nome_aprovado']=nome;d['aprovado_em']=agora()
        if not ia.disponivel():raise ValueError('Configure o motor de IA primeiro.')
        d.pop('erro',None);d.pop('fase_erro',None)
        d['status']='preparando' if fase=='analisar' else 'construindo';d['ia']=ia.selecao();salvar(d)
        with (ESTUDOS/slug/'worker.log').open('a') as log:
            proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),slug,fase],cwd=RAIZ,start_new_session=True,stdout=log,stderr=subprocess.STDOUT)
        d['pid']=proc.pid;salvar(d)


def run(cmd,timeout=1800):
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    if r.returncode:raise RuntimeError((r.stderr or r.stdout)[-1800:])
    return r


def sheets(frames,folder,n=12):
    folder.mkdir(parents=True,exist_ok=True);results=[]
    for k in range(0,len(frames),n):
        group=frames[k:k+n];canvas=Image.new('RGB',(960,math.ceil(len(group)/4)*190),'#15191e');draw=ImageDraw.Draw(canvas)
        for i,(path,t) in enumerate(group):
            with Image.open(path) as im:
                im=im.convert('RGB');im.thumbnail((230,158));x=(i%4)*240+(240-im.width)//2;y=(i//4)*190
                canvas.paste(im,(x,y));draw.text(((i%4)*240+8,y+164),f'{t:.2f}s',fill='white')
        name=folder/f'folha-{k//n+1:03}.jpg';canvas.save(name,quality=85);results.append(rel(name))
    return results


def transcrever(video,folder,c):
    import chaves
    key=chaves.chave('GROQ_API_KEY',Path(c['pasta']))
    if not key:raise ValueError('Configure GROQ_API_KEY no app/.env para transcrever a referência antes da análise.')
    from fala import groq_transcrever
    js=groq_transcrever(video,key);words=js['words'];segments=js['segments']
    gravar_json(folder/'words.json',words);gravar_json(folder/'segmentos.json',segments)


def _numerada(sb,n):
    """Arquivo de vídeo `referencia-<n>.*` (ignora restos de download como .part)."""
    return next((x for x in sorted(sb.glob(f'referencia-{n}.*')) if x.suffix.lower() not in ('.part','.ytdl','.json','.txt','.vtt','.srt')),None)


def _motivo_download(e):
    t=str(e)
    for k in ('403','404','timed out'):
        if k in t:return ERROS_SIMPLES[k]
    return (t.strip().splitlines() or ['erro desconhecido'])[-1][:160]


def reunir_fontes(d,sb):
    """Resolve cada fonte (arquivo enviado ou link) em um arquivo de vídeo. Link que falha vira aviso e as
    outras seguem; só dá erro se NENHUMA fonte funcionou. Devolve (lista de fontes prontas, avisos)."""
    fontes=[dict(x) for x in d.get('fontes') or []]
    if not fontes:  # estudos criados antes de existir lista de fontes
        antigo=next(sb.glob('referencia.*'),None)
        if antigo:fontes=[dict(n=1,origem='arquivo',arquivo=antigo.name)]
        elif d.get('url'):fontes=[dict(n=1,origem='link',url=d['url'])]
    prontas=[];avisos=[]
    for f in fontes:
        p=sb/f['arquivo'] if f.get('arquivo') else None
        if not (p and p.is_file()):p=_numerada(sb,f['n'])  # já baixado numa tentativa anterior
        if not p and f.get('origem')=='link':
            try:
                run(['yt-dlp','--no-playlist','--merge-output-format','mp4','-o',str(sb/f"referencia-{f['n']}.%(ext)s"),'--',f['url']],900)
                p=_numerada(sb,f['n'])
                if not p:raise RuntimeError('o download terminou sem entregar o vídeo')
            except Exception as e:
                avisos.append(f"O link {f['url'][:80]} não baixou e ficou de fora: {_motivo_download(e)}")
                for resto in sb.glob(f"referencia-{f['n']}.*"):resto.unlink(missing_ok=True)  # pedaços de download que falhou
                p=None
        elif not p:avisos.append(f"O vídeo {f['n']} não foi encontrado e ficou de fora.")
        if p:prontas.append(dict(f,arquivo=p.name))
    if not prontas:raise ValueError('Nenhum vídeo pôde ser usado. '+' '.join(avisos) if avisos else 'O vídeo não foi baixado.')
    return prontas,avisos


def _duracao_video(p):
    """Duração da faixa de vídeo (a que manda na montagem); cai na duração do arquivo."""
    r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=duration','-of','json',str(p)],capture_output=True,text=True)
    try:dur=float((json.loads(r.stdout or '{}').get('streams') or [{}])[0].get('duration'))
    except (TypeError,ValueError):dur=0
    return dur if dur>0 else (ffprobe(p).get('duracao') or 0)


def _tamanho_visivel(p):
    """Largura x altura como o vídeo aparece (considera vídeo de celular gravado girado), em números pares."""
    r=run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height:stream_side_data=rotation:stream_tags=rotate','-of','json',str(p)],60)
    st=(json.loads(r.stdout).get('streams') or [{}])[0];w,h=int(st.get('width') or 0),int(st.get('height') or 0)
    rot=next((x['rotation'] for x in st.get('side_data_list') or [] if 'rotation' in x),(st.get('tags') or {}).get('rotate',0))
    try:rot=int(float(rot))
    except (TypeError,ValueError):rot=0
    if abs(rot)%180==90:w,h=h,w
    if not w or not h:raise ValueError('Não consegui ler o tamanho do vídeo '+p.name)
    return w//2*2,h//2*2


def montar(prontas,sb):
    """Emenda os vídeos (um depois do outro) em referencia.mp4, todos no tamanho do primeiro. Devolve a
    lista `videos` com o intervalo que cada um ocupa na montagem. Reaproveita a montagem se nada mudou."""
    folder=ensure(sb/'estudo');paths=[sb/f['arquivo'] for f in prontas]
    assinatura=[[x.name,x.stat().st_size,x.stat().st_mtime_ns] for x in paths]
    saida=sb/'referencia.mp4';cache=ler_json(folder/'montagem.json',{}) or {}
    if len(paths)>1 and cache.get('assinatura')==assinatura and saida.is_file() and cache.get('videos'):return cache['videos']
    durs=[_duracao_video(x) for x in paths]
    if any(not x for x in durs):raise ValueError('Um dos vídeos não tem imagem legível.')
    videos=[];t=0.0
    for f,x,dur in zip(prontas,paths,durs):
        videos.append(dict(n=f['n'],arquivo=x.name,origem=f.get('origem','arquivo'),nome=f.get('nome') or f.get('url') or x.stem,
                           duracao=round(dur,3),inicio=round(t,3),fim=round(t+dur,3)));t+=dur
    if len(paths)==1:
        if paths[0].name.startswith('referencia.'):return videos  # já é o referencia.<ext>
        for velho in sb.glob('referencia.*'):velho.unlink()
        _ligar(paths[0],sb/('referencia'+paths[0].suffix.lower()));return videos
    largura,altura=_tamanho_visivel(paths[0]);fps=ffprobe(paths[0]).get('fps') or 30
    fps=fps if 10<=fps<=60 else 30
    entradas=[];grafo=[]
    for i,(x,dur) in enumerate(zip(paths,durs)):
        entradas+=['-i',str(x)]
        grafo.append(f'[{i}:v:0]scale={largura}:{altura}:force_original_aspect_ratio=decrease,pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p,trim=duration={dur:.3f},setpts=PTS-STARTPTS[v{i}]')
        tem_audio=bool(json.loads(run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index','-of','json',str(x)],60).stdout).get('streams'))
        if tem_audio:grafo.append(f'[{i}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}]')
        else:grafo.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}]')
    grafo.append(''.join(f'[v{i}][a{i}]' for i in range(len(paths)))+f'concat=n={len(paths)}:v=1:a=1[v][a]')
    tmp=sb/'.montagem.tmp.mp4'
    run(['ffmpeg','-nostdin','-y','-v','error',*entradas,'-filter_complex',';'.join(grafo),'-map','[v]','-map','[a]',
         '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(tmp)])
    for velho in sb.glob('referencia.*'):
        if velho not in paths:velho.unlink()  # o nome extra (ligação com o primeiro) sai; os originais numerados ficam
    os.replace(tmp,saida)
    for velho in ('words.json','segmentos.json'):(folder/velho).unlink(missing_ok=True)  # transcrição de outra montagem não vale
    gravar_json(folder/'montagem.json',dict(assinatura=assinatura,videos=videos,tamanho=[largura,altura],fps=fps))
    return videos


def _videos_em(videos,a,b):
    """Números dos vídeos que ocupam o trecho [a, b] da montagem."""
    return [v['n'] for v in videos if v['inicio']<=b+1e-6 and v['fim']>a+1e-6]


def texto_multiplos(d):
    """Aviso para a IA quando a referência tem mais de um vídeo (vazio se for um só)."""
    v=d.get('videos') or []
    if len(v)<2:return ''
    onde='; '.join(f"vídeo {x['n']} = {x['inicio']:.2f}s a {x['fim']:.2f}s ({x['arquivo']})" for x in v)
    return f'''São {len(v)} vídeos do mesmo estilo. O estilo é o que se repete entre eles (personagens, cenário, câmera, legenda, ritmo, vozes); o que muda entre eles é conteúdo, não estilo.
O arquivo referencia.* é a MONTAGEM dos {len(v)} vídeos, um depois do outro; os originais estão em referencia-N.*. Todos os tempos e números de frame (frames, segundos, folhas, transcrição e proposta.json) são da montagem. Onde cada vídeo fica: {onde}. estudo/videos.json repete isso e lista, por vídeo, as folhas de frames e de segundos (campo "videos" de cada folha em frames-indice.json e segundos-indice.json). A emenda entre dois vídeos NÃO é corte de edição: não conte como corte nem como transição do estilo.
Compare os vídeos entre si. Só vira regra do formato o que se repete em mais de um vídeo; o que aparece em um só é variação ou conteúdo, e deve ser marcado assim. No ESTUDO.md separe "O que se repete (vira o formato)" de "O que muda (conteúdo)" e diga, em cada elemento do catálogo, em quais vídeos ele aparece.'''


def preparar(d):
    sb=RAIZ/d['sandbox'];folder=ensure(sb/'estudo')
    prontas,avisos=reunir_fontes(d,sb)
    if avisos:
        d['avisos']=avisos;salvar(d)
        log=ESTUDOS/d['slug']/'execucao.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a') as f:f.write(''.join('\nAviso: '+a+'\n' for a in avisos))
    else:d.pop('avisos',None)
    videos=montar(prontas,sb);video=next(sb.glob('referencia.*'),None)
    if not video:raise ValueError('O vídeo não foi baixado.')
    meta=ffprobe(video);dur=meta.get('duracao') or 0
    if not dur:raise ValueError('O arquivo não contém um vídeo legível.')
    if d.get('fim') and d['fim']>dur:raise ValueError('O trecho selecionado termina depois do vídeo.')
    # Transcrição antes de decisões e antes de chamar a IA.
    audio_streams=run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index','-of','json',str(video)])
    has_audio=bool(json.loads(audio_streams.stdout).get('streams'))
    if has_audio:
        if not (folder/'words.json').exists() or not (folder/'segmentos.json').exists():transcrever(video,folder,cliente(d['cliente']))
    else:
        gravar_json(folder/'words.json',[]);gravar_json(folder/'segmentos.json',[])
    from referencia_frames import extrair
    indice=extrair(video,folder)
    from referencia_temporal import indexar
    segundos=indexar(indice,folder,dur)
    if len(videos)>1:  # de qual vídeo veio cada folha (e cada segundo)
        for x in indice['folhas']:x['videos']=_videos_em(videos,x['inicio'],x['fim'])
        for x in segundos['folhas']:x['videos']=_videos_em(videos,x['inicio'],x['fim']+1)
        for x in segundos['segundos']:x['video']=(_videos_em(videos,x['segundo'],x['segundo']+.001) or [None])[0]
        gravar_json(folder/'frames-indice.json',indice);gravar_json(folder/'segundos-indice.json',segundos)
    gravar_json(folder/'videos.json',videos)
    # Os mosaicos contêm TODOS os frames. OCR e visão geral usam uma amostra
    # auxiliar por segundo; ela não substitui a leitura completa por lotes.
    timed=[];seconds=set()
    for x in indice['frames']:
        second=int(x['segundo'])
        if second not in seconds:timed.append((folder/x['arquivo'],x['segundo']));seconds.add(second)
    cuts=ensure(folder/'cortes')
    # Medir para null evita falha do encoder JPEG quando não há corte algum.
    r=run(['ffmpeg','-nostdin','-hide_banner','-i',str(video),'-vf',"select='gt(scene,0.30)',showinfo",'-an','-f','null','-'])
    times=[float(t) for t in re.findall(r'pts_time:([0-9.]+)',r.stderr)]
    juncoes=[v['inicio'] for v in videos[1:]]  # a emenda entre dois vídeos não é corte de edição
    times=[t for t in times if all(abs(t-j)>.1 for j in juncoes)]
    for old in cuts.glob('c*.jpg'):old.unlink()
    for i,t in enumerate(times):
        frame=min(indice['frames'],key=lambda x:abs(x['segundo']-t))
        shutil.copy2(folder/frame['arquivo'],cuts/f'c{i+1:05}.jpg')
    bordas=sorted(times+juncoes);spans=[b-a for a,b in zip([0]+bordas,bordas+[dur])]
    gravar_json(folder/'cortes.json',{'tempos':times,'quantidade':len(times),'intervalo_medio':sum(spans)/len(spans),
        'intervalo_minimo':min(spans),'intervalo_maximo':max(spans),'histograma':{label:sum(lo<=v<hi for v in spans) for label,lo,hi in [('0–1s',0,1),('1–3s',1,3),('3–6s',3,6),('6s+',6,float('inf'))]}})
    timed+=list(zip(sorted(cuts.glob('c*.jpg')),times));timed.sort(key=lambda x:x[1])
    overview=sheets(timed,folder/'folhas',12)
    folhas=[x['rel'] for x in indice['folhas']]
    colors=[]
    for p,t in (list(zip(sorted(cuts.glob('c*.jpg')),times)) or timed[:1]):
        with Image.open(p) as im:
            for label,band in [('topo',0),('meio',1),('base',2)]:
                crop=im.convert('RGB').crop((0,im.height*band//3,im.width,im.height*(band+1)//3)).resize((120,120)).quantize(colors=4)
                palette=crop.getpalette();colors.append({'segundo':t,'regiao':label,'cores':['#%02X%02X%02X'%tuple(palette[v*3:v*3+3]) for _,v in sorted(crop.getcolors(),reverse=True)]})
    gravar_json(folder/'cores.json',colors)
    if has_audio:
        audio=run(['ffmpeg','-hide_banner','-i',str(video),'-vn','-af','ebur128=peak=true','-f','null','-'])
        pcm=subprocess.run(['ffmpeg','-v','error','-i',str(video),'-vn','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True,check=True).stdout
        values=array.array('f');values.frombytes(pcm);energies=[math.sqrt(sum(x*x for x in values[i:i+8000])/max(1,len(values[i:i+8000]))) for i in range(0,len(values),8000)]
        peaks=[i for i,x in enumerate(energies) if x>1.8*(sum(energies[max(0,i-3):i+4])/len(energies[max(0,i-3):i+4]))]
        gravar_json(folder/'audio.json',{'ebur128':audio.stderr[-3000:],'energia_por_segundo':energies,'picos_segundos':peaks,
            'cortes_com_pico':sum(any(abs(t-p)<=1 for p in peaks) for t in times),
            'limite':'Energia inclui voz. Picos são candidatos a SFX; música deve ser confirmada ouvindo, não inferida como certeza.'})
    else:gravar_json(folder/'audio.json',{'tem_audio':False,'observacao':'Referência sem trilha de áudio.'})

    ocr=[]
    if shutil.which('tesseract'):
        for p,t in timed:
            r=subprocess.run(['tesseract',str(p),'stdout','tsv'],capture_output=True,text=True,timeout=30)
            rows=[]
            for line in r.stdout.splitlines()[1:]:
                col=line.split('\t')
                if len(col)>=12 and col[11].strip():rows.append(dict(texto=col[11],x=int(col[6]),y=int(col[7]),w=int(col[8]),h=int(col[9]),confianca=float(col[10])))
            if rows:
                with Image.open(p) as im:width,height=im.size
                ocr.append({'segundo':t,'frame':rel(p),'largura':width,'altura':height,'palavras':rows})
    gravar_json(folder/'ocr.json',{'disponivel':bool(shutil.which('tesseract')),'frames':ocr})
    extras=[]
    for i,p in enumerate((sb/'anexos').glob('*')):
        if p.suffix.lower() in ('.jpg','.png','.jpeg','.webp'):extras.append(rel(p))
        elif p.suffix.lower() in ('.mp4','.mov','.webm','.mkv'):
            ef=ensure(folder/f'extra-{i}')
            run(['ffmpeg','-y','-v','error','-i',str(p),'-vf','fps=1,scale=720:-2',str(ef/'f%05d.jpg')])
            extras+=sheets([(p,float(j)) for j,p in enumerate(sorted(ef.glob('f*.jpg')))],ef/'folhas')
    visao_videos=[_videos_em(videos,g[0][1],g[-1][1]) for g in (timed[k:k+12] for k in range(0,len(timed),12))] if len(videos)>1 else []
    gravar_json(folder/'evidencias.json',{'video':rel(video),'videos':videos,'visao_geral_videos':visao_videos,'meta':meta,'folhas':folhas,'visao_geral':overview,'extras':extras,'frames':indice['total_frames'],'metodo':'todos-os-frames','segundos':segundos['total_segundos'],'folhas_segundos':[x['arquivo'] for x in segundos['folhas']]})
    d.update(videos=videos,status='analisando',segundos=segundos['total_segundos'],folhas=len(folhas),frames=indice['total_frames'],metodo='todos-os-frames',lotes_concluidos=0,lotes_total=math.ceil(len(folhas)/12));salvar(d)
    return video


def analisar_frames(d):
    """Leitura visual em lotes pequenos; a síntese só começa com cobertura completa."""
    from referencia_frames import validar_relatorio
    sb=RAIZ/d['sandbox'];evidence=sb/'estudo';index=ler_json(evidence/'frames-indice.json')
    reports=ensure(evidence/'analises');logs=ESTUDOS/d['slug'];coverage=[]
    identity=hashlib.sha256((index['assinatura']+d.get('briefing','')+json.dumps(d['ia'],sort_keys=True)+'temporal-v2').encode()).hexdigest()
    for offset in range(0,len(index['folhas']),12):
        group=index['folhas'][offset:offset+12];target=reports/f'parte-{offset//12+1:03}.json'
        old=ler_json(target,{}) or {}
        try:
            if old.get('assinatura')!=identity:raise ValueError('Relatório de outra análise.')
            validar_relatorio(old,group)
        except ValueError:
            task=f'''Analise visualmente TODAS estas folhas de contato EM ORDEM, abrindo cada imagem com a ferramenta de imagem. Cada folha contém frames consecutivos, com número e tempo, da referência {rel(sb)}.
Leia BRIEF.md, estudo/words.json, segmentos.json e cortes.json para cruzar FALA e IMAGEM. Pedido: {d.get('briefing','')}. Trecho de maior interesse: {d.get('inicio')}–{d.get('fim')}s{' (no primeiro vídeo)' if len(d.get('videos') or [])>1 else ''}; ainda assim examine o vídeo inteiro.
{texto_multiplos(d)}
Folhas deste lote: {json.dumps(group,ensure_ascii=False)}
Compare cada frame ao anterior: entrada, permanência e saída de elementos; posição/tamanho do rosto, legenda, texto, máscara, paleta, movimento e transições. Registre também quando não há mudança. Identifique cada b-roll, seu frame/tempo de entrada e de saída, duração, corte seco ou transição, retorno ao apresentador e função na fala. Aponte erros visuais ou de ritmo com evidências, sem inventar defeitos. Não deduza imagem só da transcrição. Para texto pequeno ou detalhe, extraia do vídeo original o frame em resolução integral com ffmpeg e confira.
Escreva SOMENTE {rel(target)} no formato {{"assinatura":"{identity}","folhas":[{{"n":1,"primeiro":1,"ultimo":24,"observacao":"o que aparece e muda; ou estabilidade observada","evidencias":[{{"frame":1,"descricao":"elemento observado, posição e comportamento"}}]}}],"replicacao":[{{"elemento":"...","como_fazer":"script, filtro, máscara ou animação sugerida","limite":"aproximação e dúvida"}}]}}.
Uma entrada por folha, com seus números reais. Evidências precisam apontar frames dentro daquela folha. Se não conseguir abrir uma folha, termine com erro, não invente observação. Não construa modelo nem altere scripts/regras. Seja preciso e conciso.'''
            code=ia.executar(task,logs/'execucao.log',logs/'raw.jsonl',logs/'runner.pid',d['ia'])
            if code:raise ValueError(f'Falhou a leitura do lote visual {offset//12+1}. As folhas e análises anteriores foram preservadas.')
            old=ler_json(target,{}) or {};validar_relatorio(old,group)
            old['assinatura']=identity;gravar_json(target,old)
        coverage.extend(x['n'] for x in group)
        d['lotes_concluidos']=offset//12+1;salvar(d)
    gravar_json(evidence/'cobertura.json',{'metodo':'todos-os-frames','frames':index['total_frames'],'folhas':coverage,'relatorios':[rel(p) for p in sorted(reports.glob('parte-*.json'))],'completa':len(coverage)==len(index['folhas'])})


def prompt(d):
    sb=d['sandbox'];catalog=[{'cliente':c['nome'],'modelos':c['modelos']} for c in clientes()]
    return f'''Você trabalha no Estúdio em {RAIZ}. Analise a referência do cliente {d['cliente']} em {sb}.
Leia primeiro BRIEF.md, estudo/words.json e segmentos.json. Leia TODOS os relatórios listados em estudo/cobertura.json: cada um analisou um lote de frames consecutivos, com evidências por folha. Verifique cobertura completa; abra novamente os frames de troca, textos e movimentos que sustentam a proposta. Leia estudo/segundos-indice.json e suas folhas: há um frame de cada segundo do vídeo inteiro. Para cortes de b-roll, confira também os frames adjacentes no índice completo: cenas curtas podem entrar e sair entre dois segundos. As folhas em estudo/evidencias.json cobrem TODOS os frames, não só a grade por segundo. Veja anexos. Cruze com cortes.json, audio.json, ocr.json, cores.json. Não afirme ter ouvido sem ouvir. Fontes/efeitos são aproximações declaradas.
ESTUDO.md deve explicar: composição desenhada por áreas; roteiro/fala e mudanças de cena; catálogo de elementos com frame e tempo de exemplo; animação medida entre frames; como implementar cada elemento; diferenças inevitáveis e teste de comparação com a referência. Não basta descrever cores e dizer que o modelo é parecido.
Pedido: {d['briefing']}
{texto_multiplos(d)}
Escreva {sb}/ESTUDO.md e {sb}/proposta.json (JSON objeto) com estes campos:
 nome: kebab-case curto, alternativas: 2 nomes, ficha: objeto no esquema de app/ferramentas/ficha.py,
 motor_base: "Cliente/modelo" EXATO de um motor existente, comparacoes: lista de {{motor,nota:0-100,justificativa}},
 scripts: lista de {{arquivo,descricao,flags}}, limitacoes: lista, mapa_temporal: lista de {{inicio,fim,fala,tela,elemento}},
 layout: descrição por faixa 1080x1920, legenda: estilo/posição/cor/fonte/sombra/caixa, ritmo: medidas,
 elementos: catálogo com gatilho por palavra, exemplo frame/segundo, duração, animação,
 identidade: paleta, tipografia estimada, música e SFX; mocks: lista de caminhos RELATIVOS à sandbox.
 linha_do_tempo: uma entrada para CADA segundo em estudo/segundos-indice.json, com {{segundo: inteiro, frame: número REAL desse índice, tipo: fala|broll|card|misto|outro, descricao: o que está na tela e como mudou}}. Não pular segundos.
 brolls: lista de TODOS os inserts/cenas de apoio observados, inclusive os menores que 1 segundo. Cada um com {{id,inicio,fim,duracao,frame_entrada,frame_saida,conteudo,funcao,entrada,saida,layout,como_replicar}} (como_replicar = como aproveitar o estilo, sem copiar o conteúdo). Use segundos decimais e frames reais do índice completo, com precisão melhor que 0,15s. Identifique quando corta para o b-roll e quando volta à fala; não confunda duração do vídeo de origem com a janela efetivamente usada. Para overlay, declare área/posição e o que segue visível do bruto. Se não houver b-roll: [].
 problemas: lista de {{inicio,fim,frame,problema,impacto,correcao}} com evidência observável: legenda ilegível, enquadramento cortado, insert sem relação com fala, cena longa/curta demais, salto de ritmo etc. Se não houver problema verificável: [], sem inventar defeitos.
 regras_temporais: recomendações numéricas para duração, espaçamento, corte de entrada/saída e retorno à fala, derivadas dos brolls observados. Distinga estilo que vale reproduzir de problema que deve ser corrigido. O novo modelo deve permitir b-roll desligado e quantidade máxima escolhida no Estúdio.
No ESTUDO.md inclua tabelas por segundo, mapa dos b-rolls (entrada → saída, duração, função) e problemas/correções. Não transforme aproximações em medidas certas.
Motores disponíveis: {json.dumps(catalog,ensure_ascii=False)}.
Leia fichas e scripts dos motores próximos para comparar. Gere 2-3 frames de demonstração antecipada em {sb}/mocks/ usando os scripts do motor base com a nova paleta. Sem modificar o motor base. Identifique cada como demonstração aproximada.
NÃO construa um modelo, NÃO altere regras nem CLAUDE.md, NÃO apague a referência. Pare na proposta para o João aprovar.
'''


def construir(d):
    import novo_cliente
    from arquivo import sha,base_destino
    sb=RAIZ/d['sandbox'];p=ler_json(sb/'proposta.json');c=cliente(d['cliente'])
    oc,om=p['motor_base'].split('/',1)
    dst=c['content']/'modelos'/d['nome_aprovado']
    if dst.exists():
        if ler_json(dst/'.estudo-origem.json',{}).get('slug')!=d['slug']:
            raise ValueError('O nome aprovado pertence a outro modelo. Nada foi alterado.')
    else:
        dst=novo_cliente.portar_modelo(c,oc,om,d['nome_aprovado'])
        gravar_json(dst/'.estudo-origem.json',{'slug':d['slug']})
    # portar_modelo já exclui demos e referências da origem. Uma retomada
    # preserva os arquivos que a construção anterior conseguiu entregar.
    task=f'''Construa o modelo APROVADO {rel(dst)} usando {rel(sb)}/proposta.json e ESTUDO.md.
Implemente as regras temporais e as correções observadas em proposta.json, além dos scripts e flags no gerar.sh. Preserve a relação entre palavra, entrada do b-roll, duração e retorno à fala. Suporte b-roll desligado e quantidade máxima configurável, sem buscar ou gerar por conta própria. Compare frames imediatamente antes e depois de cada entrada/saída e gere uma demonstração local curta da montagem temporal; registre o caminho em VALIDACAO.md. Nenhuma API de geração paga é autorizada nesta construção.
Implemente todos os scripts propostos e flags no gerar.sh; scripts ficam DENTRO de {rel(dst)}. Leia estudo/evidencias.json e compare os frames.
Nome final: {d['nome_aprovado']}. Não altere o motor de origem. Escreva ficha.json completa (origem com referência e motor base), README.md e demos/index.json com frames REAIS gerados por seus scripts. Execute testes em frame e corrija.
Aprendizado deve ficar ZERADO. Não produza o vídeo de prova ainda. Não apague {rel(sb)}.
Escreva {rel(dst)}/VALIDACAO.md com comandos dos testes executados, resultados e limitações. Se algum script não puder ser concluído, declare explicitamente e termine com erro.
'''
    folder=ESTUDOS/d['slug'];code=ia.executar(task,folder/'execucao.log',folder/'raw.jsonl',folder/'runner.pid',d['ia'])
    if code:raise ValueError('A construção falhou. Veja os detalhes; os arquivos de referência foram preservados.')
    f=ler_json(dst/'ficha.json');demos=ler_json(dst/'demos/index.json',[]) or []
    if not f or not (dst/'README.md').is_file() or not demos or not (dst/'VALIDACAO.md').is_file():raise ValueError('A construção não entregou ficha, README, validação ou demonstrações.')
    for script in p.get('scripts',[]):
        name=script.get('arquivo','')
        q=(dst/name).resolve()
        if not name or not q.is_relative_to(dst.resolve()) or not q.is_file():raise ValueError('Script proposto não foi entregue: '+name)
        if q.suffix=='.py':compile(q.read_text(),str(q),'exec')
        if q.suffix=='.sh':run(['bash','-n',str(q)])
    if not any((dst/'demos'/str(x.get('arquivo',''))).is_file() for x in demos):raise ValueError('Faltam os frames de demonstração.')
    gravar_json(dst/'aprendizado/regras.json',dict(modelo=d['nome_aprovado'],cliente=d['cliente'],regras=[]))
    append_jsonl(dst/'aprendizado/historico.jsonl',dict(tipo='criacao',categoria='processo',texto='Modelo criado a partir de referência aprovada.',origem='usuario',createdAt=hoje()))
    ref=ensure(dst/'referencia')
    for name in ('ESTUDO.md','proposta.json'):shutil.copy2(sb/name,ref/('estudo.json' if name=='proposta.json' else name))
    frames=sorted((sb/'estudo/frames').glob('*.jpg'))
    for i in sorted(set(round(j*(len(frames)-1)/11) for j in range(12))) if frames else []:
        with Image.open(frames[i]) as im:im.thumbnail((540,960));im.save(ref/frames[i].name,quality=80)
    video=next(sb.glob('referencia.*'))
    export=ensure(base_destino(d['cliente'])/d['cliente']/'Referencias'/d['slug'])
    shutil.copy2(video,export/video.name)
    if sha(video)!=sha(export/video.name):raise ValueError('Falhou a integridade da referência exportada. Arquivos temporários preservados.')
    for n in ('BRIEF.md','ESTUDO.md','proposta.json'):shutil.copy2(sb/n,export/n)
    for original in sorted(sb.glob('referencia-*.*')):shutil.copy2(original,export/original.name)  # vários vídeos: guarda cada original
    archive=ensure(export/'estudo')
    for name in ('frames-indice.json','segundos-indice.json','cobertura.json','cortes.json','cores.json','audio.json','ocr.json','videos.json'):
        if (sb/'estudo'/name).exists():shutil.copy2(sb/'estudo'/name,archive/name)
    for name in ('analises','folhas-completas','folhas-segundos'):
        if (sb/'estudo'/name).exists():shutil.copytree(sb/'estudo'/name,archive/name,dirs_exist_ok=True)
    if (sb/'anexos').exists():shutil.copytree(sb/'anexos',export/'anexos',dirs_exist_ok=True)
    d.update(status='pronto',modelo=d['nome_aprovado'],pasta_mac=str(export),proposta=p);salvar(d)
    try:
        import formatos as _fmt
        _fmt.registrar_de_referencia(d['nome_aprovado'],f,d['cliente'],dst,export/video.name)
    except Exception as e:
        with (ESTUDOS/d['slug']/'execucao.log').open('a') as lg: lg.write('\nAviso: não entrou no catálogo de formatos: '+str(e)+'\n')
    shutil.rmtree(sb)


def worker(slug,fase):
    d=carregar(slug);folder=ESTUDOS/slug
    try:
        if fase=='analisar':
            preparar(d);analisar_frames(d)
            code=ia.executar(prompt(d),folder/'execucao.log',folder/'raw.jsonl',folder/'runner.pid',d['ia'])
            p=ler_json(RAIZ/d['sandbox']/'proposta.json')
            if code or not p or not (RAIZ/d['sandbox']/'ESTUDO.md').is_file():raise ValueError('A análise não entregou uma proposta completa.')
            required=('nome','ficha','motor_base','scripts','mapa_temporal','limitacoes','mocks')
            if any(k not in p for k in required):raise ValueError('A proposta está incompleta. Veja os detalhes e refaça a análise.')
            from referencia_temporal import validar
            evidence=RAIZ/d['sandbox']/'estudo'
            validar(p,ler_json(evidence/'frames-indice.json'),ler_json(evidence/'segundos-indice.json'))
            base=(RAIZ/d['sandbox']).resolve()
            if not isinstance(p['mocks'],list) or not 2<=len(p['mocks'])<=3 or any(not isinstance(m,str) or not (base/m).resolve().is_relative_to(base) or not (base/m).is_file() for m in p['mocks']):raise ValueError('Faltam duas ou três demonstrações da proposta dentro da referência.')
            motor=p['motor_base'].split('/',1)
            if len(motor)!=2 or not (c:=cliente(motor[0])) or not modelo(c,motor[1]):raise ValueError('A proposta precisa indicar um motor base existente.')
            d.update(status='proposta',proposta=p);salvar(d)
        else:construir(d)
    except Exception as e:
        d.update(status='erro',erro=str(e),fase_erro=fase);salvar(d)
        with (folder/'execucao.log').open('a') as f:f.write('\nFalha: '+str(e)+'\n')
    finally:
        d=carregar(slug);d.pop('pid',None);salvar(d)

def pasta_evidencias(d):
    local=RAIZ/d['sandbox']/'estudo'
    return local if local.exists() else Path(d.get('pasta_mac') or local.parent)/'estudo'


if __name__=='__main__':worker(*sys.argv[1:3])
