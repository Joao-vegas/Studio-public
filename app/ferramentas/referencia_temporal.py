"""Cobertura por segundo e contrato temporal para reproduzir a edição observada."""
from bisect import bisect_right
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from _comum import gravar_json


def indexar(indice, folder, duracao):
    folder=Path(folder)
    frames=indice['frames'];times=[f['segundo'] for f in frames]
    seconds=[]
    for second in range(math.ceil(duracao)):
        frame=frames[max(0,bisect_right(times,second)-1)]
        seconds.append(dict(segundo=second,frame=frame['n'],tempo_frame=frame['segundo'],arquivo=frame['arquivo']))
    sheets=[];dest=folder/'folhas-segundos';dest.mkdir(exist_ok=True)
    try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',16)
    except OSError:font=ImageFont.load_default()
    with Image.open(folder/frames[0]['arquivo']) as im:height=350 if im.height>im.width else 174
    for offset in range(0,len(seconds),12):
        group=seconds[offset:offset+12]
        canvas=Image.new('RGB',(960,math.ceil(len(group)/4)*height),'#141b20');draw=ImageDraw.Draw(canvas)
        for i,row in enumerate(group):
            with Image.open(folder/row['arquivo']) as raw:
                image=raw.convert('RGB');image.thumbnail((228,height-34))
                x=(i%4)*240;y=(i//4)*height
                canvas.paste(image,(x+(240-image.width)//2,y))
                draw.text((x+8,y+height-26),f"{row['segundo']}s · frame #{row['frame']}",font=font,fill='#d3ebad')
        name=f'folha-{len(sheets)+1:04}.jpg';canvas.save(dest/name,quality=86)
        sheets.append(dict(n=len(sheets)+1,arquivo='folhas-segundos/'+name,primeiro=group[0]['frame'],ultimo=group[-1]['frame'],inicio=group[0]['segundo'],fim=group[-1]['segundo']))
    result=dict(duracao=duracao,total_segundos=len(seconds),segundos=seconds,folhas=sheets,
                metodo='um-frame-por-segundo',assinatura=indice['assinatura'],
                observacao='Frame exibido em cada segundo inteiro. Os frames completos continuam disponíveis para conferir cortes menores que um segundo.')
    gravar_json(folder/'segundos-indice.json',result)
    return result


def validar(proposta, indice, segundos):
    rows=proposta.get('linha_do_tempo')
    expected={x['segundo']:x['frame'] for x in segundos['segundos']}
    if not isinstance(rows,list) or len(rows)!=len(expected):
        raise ValueError('A referência precisa de uma observação para cada segundo do vídeo inteiro.')
    seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Linha do tempo inválida.')
        t=row.get('segundo')
        if t in seen or t not in expected or row.get('frame')!=expected[t] or not row.get('descricao') or row.get('tipo') not in ('fala','broll','card','misto','outro'):
            raise ValueError('A linha do tempo não corresponde aos frames de cada segundo.')
        seen.add(t)
    duration=segundos['duracao'];frames={f['n']:f['segundo'] for f in indice['frames']}
    def interval(row):
        start,end=row.get('inicio'),row.get('fim')
        if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end<=duration+.001:
            raise ValueError('Intervalo fora do vídeo de referência.')
        return start,end
    brolls=proposta.get('brolls');problems=proposta.get('problemas')
    if not isinstance(brolls,list) or not isinstance(problems,list):
        raise ValueError('A proposta precisa registrar b-rolls e problemas observados, mesmo que as listas estejam vazias.')
    ids=set()
    for b in brolls:
        if not isinstance(b,dict):raise ValueError('B-roll temporal inválido.')
        start,end=interval(b)
        if not b.get('id') or b['id'] in ids:raise ValueError('Identificadores de b-roll devem ser únicos.')
        ids.add(b['id'])
        try:delta=abs(float(b['duracao'])-(end-start))
        except (KeyError,ValueError,TypeError):raise ValueError('Informe a duração de cada b-roll.') from None
        if not math.isfinite(delta) or delta>.05:raise ValueError('A duração do b-roll não confere com seus cortes de entrada e saída.')
        for name in ('frame_entrada','frame_saida'):
            if b.get(name) not in frames:raise ValueError('O b-roll precisa apontar frames reais de entrada e saída.')
        if abs(frames[b['frame_entrada']]-start)>.15 or abs(frames[b['frame_saida']]-end)>.15:
            raise ValueError('Confira os frames próximos aos cortes do b-roll; a precisão precisa ser melhor que 0,15 segundo.')
        if any(not str(b.get(k,'')).strip() for k in ('conteudo','funcao','entrada','saida','layout','como_replicar')):
            raise ValueError('Explique a função, o enquadramento e os cortes de cada b-roll.')
    for issue in problems:
        if not isinstance(issue,dict):raise ValueError('Problema observado inválido.')
        start,end=interval(issue)
        frame=issue.get('frame')
        if frame not in frames or not start-.15<=frames[frame]<=end+.15 or any(not issue.get(k) for k in ('problema','impacto','correcao')):
            raise ValueError('Cada problema precisa de evidência temporal, impacto e correção proposta.')
    return True
