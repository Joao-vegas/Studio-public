"""Todos os frames da referência, com timestamps e mosaicos auditáveis."""
import hashlib
import json
import math
import subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from _comum import gravar_json,ler_json,rel


def extrair(video,folder,por_folha=24):
    video=Path(video);folder=Path(folder)
    fingerprint=hashlib.sha256(f'{video.resolve()}:{video.stat().st_size}:{video.stat().st_mtime_ns}:frames-v2'.encode()).hexdigest()
    index=ler_json(folder/'frames-indice.json',{}) or {}
    if index.get('assinatura')==fingerprint and all((folder/x['arquivo']).is_file() for x in index.get('frames',[])) and index.get('frames'):
        if all((folder/x['arquivo']).is_file() for x in index.get('folhas',[])):return index
    result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)],capture_output=True,text=True,check=True,timeout=1800)
    timestamps=[float(x['best_effort_timestamp_time']) for x in json.loads(result.stdout).get('frames',[]) if 'best_effort_timestamp_time' in x]
    if not timestamps:raise ValueError('Não foi possível identificar os frames da referência.')
    start=timestamps[0];timestamps=[max(0,t-start) for t in timestamps]
    frames=folder/'frames';frames.mkdir(parents=True,exist_ok=True)
    for p in frames.glob('f*.jpg'):p.unlink()  # apenas frames derivados desta referência
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(video),'-map','0:v:0','-vf','scale=360:-2','-fps_mode','passthrough','-q:v','3',str(frames/'f%07d.jpg')],capture_output=True,check=True,timeout=1800)
    paths=sorted(frames.glob('f*.jpg'))
    if len(paths)!=len(timestamps):raise ValueError(f'Extração incompleta: {len(paths)} de {len(timestamps)} frames. A análise não será iniciada.')
    entries=[dict(n=i+1,segundo=round(t,6),arquivo=str(p.relative_to(folder))) for i,(p,t) in enumerate(zip(paths,timestamps))]
    folhas=[];dest=folder/'folhas-completas';dest.mkdir(exist_ok=True)
    try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',15)
    except OSError:font=ImageFont.load_default()
    with Image.open(paths[0]) as im:portrait=im.height>im.width
    tile_h=350 if portrait else 174
    for offset in range(0,len(entries),por_folha):
        group=entries[offset:offset+por_folha]
        canvas=Image.new('RGB',(960,math.ceil(len(group)/4)*tile_h),'#141b20');draw=ImageDraw.Draw(canvas)
        for i,x in enumerate(group):
            with Image.open(folder/x['arquivo']) as raw:
                im=raw.convert('RGB');im.thumbnail((228,tile_h-34))
                left=(i%4)*240;top=(i//4)*tile_h
                canvas.paste(im,(left+(240-im.width)//2,top))
                draw.text((left+8,top+tile_h-26),f"#{x['n']}  {x['segundo']:.3f}s",font=font,fill='#d3ebad')
        target=dest/f'folha-{len(folhas)+1:04}.jpg';canvas.save(target,quality=86)
        folhas.append(dict(n=len(folhas)+1,arquivo=str(target.relative_to(folder)),rel=rel(target),
                           primeiro=group[0]['n'],ultimo=group[-1]['n'],inicio=group[0]['segundo'],fim=group[-1]['segundo']))
    index=dict(assinatura=fingerprint,total_frames=len(entries),total_folhas=len(folhas),frames=entries,folhas=folhas,
               metodo='todos-os-frames',resolucao_frames='360px de largura; proporção original',
               observacao='Todos os frames decodificados, inclusive os repetidos, na ordem original. Numeração começa em 1.')
    gravar_json(folder/'frames-indice.json',index)
    return index


def validar_relatorio(data,folhas):
    rows=data.get('folhas') if isinstance(data,dict) else None
    if not isinstance(rows,list) or len(rows)!=len(folhas):raise ValueError('A análise visual não cobriu todas as folhas deste lote.')
    expected={x['n']:(x['primeiro'],x['ultimo']) for x in folhas}
    seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Relatório visual inválido.')
        n=row.get('n')
        if n in seen or n not in expected or (row.get('primeiro'),row.get('ultimo'))!=expected[n]:
            raise ValueError('A cobertura de frames da análise não corresponde aos mosaicos.')
        if not str(row.get('observacao') or '').strip() or not row.get('evidencias'):
            raise ValueError('A análise precisa registrar observações e evidências por folha.')
        for evidence in row['evidencias']:
            frame=evidence.get('frame') if isinstance(evidence,dict) else None
            if not isinstance(frame,int) or not expected[n][0]<=frame<=expected[n][1] or not evidence.get('descricao'):
                raise ValueError('Uma evidência visual aponta para um frame fora da folha.')
        seen.add(n)
    return True
