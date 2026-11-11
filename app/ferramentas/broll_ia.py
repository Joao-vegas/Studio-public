"""B-rolls Kie do Estúdio: rascunho → revisão → UMA tarefa → seleção no plano.
Sem geração automática, sem retry de createTask e sem chave nos registros.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import os
import re
import secrets
import threading
import urllib.request
import uuid

import producao as prod

BASE = 'https://api.kie.ai/api/v1/jobs'
PRICE_DATE = '2026-09-22'
# Cardápio de modelos da kie.ai (preços do catálogo do Gerador de imagem e vídeo, 22/09/2026).
# O modelo é escolhido na hora de criar (telas de imagem e de animação). Cada modelo diz como montar o pedido.
MODELOS_IMAGEM = {
    'gpt-image-2-5-sunburst-text-to-image': {'nome': 'GPT Image 2.5', 'nota': 'melhor com texto na arte',
        'usd': {'1K': .03, '2K': .05, '4K': .08}},
    'grok-imagine/text-to-image': {'nome': 'Grok Imagine', 'nota': 'bom gosto, 2 opções por pedido', 'usd': {'1K': .02},
        'por_tarefa': 2},
    'google/nano-banana': {'nome': 'Nano Banana', 'nota': 'segue bem um estilo', 'usd': {'1K': .02}},
    'z-image': {'nome': 'Z-Image', 'nota': 'o mais barato; foto de gente real com prompt detalhado', 'usd': {'1K': .004}},
}
MODELOS_VIDEO = {
    'grok-imagine/image-to-video': {'nome': 'Grok Imagine', 'nota': 'teste de movimento barato',
        'usd': {'480p': .012, '720p': .0225, '1080p': .04}, 'duracoes': (6, 10)},
    'bytedance/seedance-2-mini': {'nome': 'Seedance 2 mini', 'nota': 'movimento mais natural',
        'usd': {'480p': .019, '720p': .041}, 'duracoes': (5, 10)},
    'kling-3.0/video': {'nome': 'Kling 3.0', 'nota': 'clipe padrão de qualidade', 'usd': {'720p': .07}, 'duracoes': (5, 10)},
}
IMAGE_MODEL = 'gpt-image-2-5-sunburst-text-to-image'
VIDEO_MODEL = 'grok-imagine/image-to-video'
# Pré-seleção das telas de criação (o mais barato que faz sentido). O IMAGE_MODEL/VIDEO_MODEL acima
# só valem quando o pedido não traz 'modelo' (ex.: chamadas antigas).
IMAGE_SUGERIDO = 'grok-imagine/text-to-image'
VIDEO_SUGERIDO = 'grok-imagine/image-to-video'


def modelos_escolhidos():
    """Modelos padrão quando o pedido não diz qual usar."""
    try:
        cfg = json.loads((Path(__file__).parents[1] / 'config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cfg = {}
    img = cfg.get('kie_imagem') if cfg.get('kie_imagem') in MODELOS_IMAGEM else IMAGE_MODEL
    vid = cfg.get('kie_video') if cfg.get('kie_video') in MODELOS_VIDEO else VIDEO_MODEL
    return img, vid


IMAGE_USD = MODELOS_IMAGEM[IMAGE_MODEL]['usd']
VIDEO_USD = MODELOS_VIDEO[VIDEO_MODEL]['usd']
RATIOS = {'9:16': 'Vertical · tela inteira', '16:9': 'Horizontal · janela de apoio', '1:1': 'Quadrado · insert'}
STATES = {'rascunho': 'Pronto para revisar', 'enviando': 'Enviando uma única solicitação',
          'processando': 'Gerando', 'pronto': 'Pronto para revisar', 'falhou': 'O provedor informou falha',
          'incerto': 'Envio sem confirmação — não reenviado'}


def key():
    value = os.environ.get('KIE_API_KEY')
    if value:
        return value
    explicit = os.environ.get('KIE_ENV_FILE')
    paths = [Path(explicit)] if explicit else [Path(__file__).parents[1] / '.env']
    for path in paths:
        if path.is_file():
            for line in path.read_text().splitlines():
                if line.strip().startswith('KIE_API_KEY='):
                    value = line.strip().split('=', 1)[1].strip().strip('\"\'')
                    if value:
                        return value
    raise ValueError('Configure KIE_API_KEY no ambiente ou KIE_ENV_FILE com o caminho do seu .env.')


def configured():
    try:
        return bool(key())
    except (ValueError, OSError):
        return False


def folder(job):
    return prod.RAIZ / job['sandbox'] / 'gerados'


def _path(job, ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise ValueError('B-roll inválido.')
    return folder(job) / (ident + '.json')


def load(job, ident):
    path = _path(job, ident)
    if not path.is_file():
        raise ValueError('B-roll não encontrado.')
    return json.loads(path.read_text())


def save(job, record):
    path = _path(job, record['id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    tmp.replace(path)


@contextmanager
def locked(job):
    folder(job).mkdir(parents=True, exist_ok=True)
    with (folder(job) / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def listing(job):
    return sorted((json.loads(p.read_text()) for p in folder(job).glob('*.json')),
                  key=lambda r: r['created'], reverse=True)


def beat(job, ident):
    result = next((b for b in (prod.plano(job) or {}).get('beats', []) if b['id'] == ident), None)
    if not result:
        raise ValueError('Escolha um trecho do plano da edição.')
    return result


def check_scene(job, record):
    current = beat(job, record['beat'])
    if any(current.get(k) != record.get(k) for k in ('inicio', 'fim', 'fala')):
        raise ValueError('O trecho mudou desde o rascunho. Prepare uma cena para o plano atualizado.')
    return current


def _modelo(form, catalogo, padrao):
    pedido = form.get('modelo')
    return pedido if isinstance(pedido, str) and pedido in catalogo else padrao


def entrada_imagem(model, prompt, ratio, resolution):
    """O corpo do pedido de imagem de cada modelo do cardápio (usado pelo b-roll e pelo Editar vídeo)."""
    if model == 'gpt-image-2-5-sunburst-text-to-image':
        return {'prompt': prompt, 'aspect_ratio': ratio, 'resolution': resolution, 'background': 'opaque'}
    if model == 'google/nano-banana':
        return {'prompt': prompt, 'aspect_ratio': ratio, 'output_format': 'png'}
    return {'prompt': prompt[:1000] if model == 'z-image' else prompt, 'aspect_ratio': ratio}


def entrada_video(model, prompt, ratio, resolution, duration):
    """O corpo do pedido de vídeo (imagem → vídeo); a URL da imagem entra depois, no envio."""
    if model == 'grok-imagine/image-to-video':
        return {'prompt': prompt, 'mode': 'normal', 'duration': str(duration), 'resolution': resolution, 'aspect_ratio': ratio}
    if model.startswith('bytedance/seedance'):
        return {'prompt': prompt, 'resolution': resolution, 'aspect_ratio': ratio, 'duration': duration, 'generate_audio': False}
    return {'prompt': prompt, 'duration': str(duration), 'aspect_ratio': ratio, 'mode': 'std', 'sound': False, 'multi_shots': False}


def draft(job, form):
    if job.get('broll_config', {}).get('origem') == 'nenhum':
        raise ValueError('Ative as cenas de apoio nas preferências desta edição antes de preparar um b-roll.')
    b = beat(job, form.get('beat', ''))
    prompt = form.get('prompt', '').strip()
    if not 10 <= len(prompt) <= 15000:
        raise ValueError('Descreva a cena em 10 a 15.000 caracteres.')
    kind = form.get('tipo', 'imagem')
    parent = None
    if kind == 'video':
        if len(prompt) > 4000:
            raise ValueError('Use até 4.000 caracteres no prompt de animação.')
        parent = load(job, form.get('origem', ''))
        if parent['tipo'] != 'imagem' or parent['status'] != 'pronto' or parent['beat'] != b['id']:
            raise ValueError('Escolha uma imagem pronta deste mesmo trecho para animar.')
        # Only an explicit image review authorizes its use as the video input.
        if form.get('imagem_aprovada') != '1':
            raise ValueError('Aprove a imagem de referência antes de preparar a animação.')
        ratio = parent['ratio']
        model = _modelo(form, MODELOS_VIDEO, modelos_escolhidos()[1])
        spec = MODELOS_VIDEO[model]
        resolution = form.get('resolucao') or ('720p' if '720p' in spec['usd'] else next(iter(spec['usd'])))
        try:
            duration = int(form.get('duracao') or spec['duracoes'][0])
        except ValueError:
            duration = 0
        if resolution not in spec['usd'] or duration not in spec['duracoes']:
            raise ValueError(f"Escolha {' ou '.join(map(str, spec['duracoes']))} segundos e uma resolução disponível no {spec['nome']}.")
        inp = entrada_video(model, prompt, ratio, resolution, duration)
        cost = round(spec['usd'][resolution] * duration, 4)
    elif kind == 'imagem':
        ratio = form.get('ratio', '9:16')
        model = _modelo(form, MODELOS_IMAGEM, modelos_escolhidos()[0])
        spec = MODELOS_IMAGEM[model]
        resolution = form.get('resolucao') or ('2K' if '2K' in spec['usd'] else next(iter(spec['usd'])))
        if ratio not in RATIOS or resolution not in spec['usd']:
            raise ValueError('Formato ou resolução inválidos para o ' + spec['nome'] + '.')
        duration = None
        inp = entrada_imagem(model, prompt, ratio, resolution)
        cost = spec['usd'][resolution]
    else:
        raise ValueError('Tipo de geração inválido.')
    r = {'id': uuid.uuid4().hex, 'created': datetime.now(timezone.utc).isoformat(),
         'status': 'rascunho', 'nonce': secrets.token_urlsafe(32), 'tipo': kind,
         'beat': b['id'], 'fala': b.get('fala', ''), 'inicio': b['inicio'], 'fim': b['fim'],
         'ratio': ratio, 'resolucao': resolution, 'duracao': duration, 'model': model,
         'input': inp, 'usd_estimado': cost, 'preco_em': PRICE_DATE,
         'origem': parent['id'] if parent else None}
    save(job, r)
    return r


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, headers={
        'Authorization': 'Bearer ' + key(), 'Content-Type': 'application/json'},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.load(response)
    if result.get('code') != 200:
        # Do not expose arbitrary upstream content or credentials to logs/UI.
        raise ValueError('A Kie não confirmou a operação. Confira o histórico no provedor.')
    return result.get('data') or {}


def _submit(job, ident):
    try:
        r = load(job, ident)
        inp = dict(r['input'])
        if r['origem']:
            parent = load(job, r['origem'])
            # Renew an expired URL by uploading the exact locally approved reference.
            url = upload(prod.RAIZ / job['sandbox'] / parent['arquivo'])
            if r['model'].startswith('bytedance/seedance'):
                inp['first_frame_url'] = url
            else:
                inp['image_urls'] = [url]
        data = call('POST', BASE + '/createTask', {'model': r['model'], 'input': inp})
        task = data.get('taskId')
        if not isinstance(task, str) or not task:
            raise ValueError('Resposta sem identificador de tarefa.')
        with locked(job):
            r = load(job, ident)
            r.update(status='processando', task_id=task)
            save(job, r)
    except Exception:
        with locked(job):
            r = load(job, ident)
            r.update(status='incerto', erro='Não foi possível confirmar o envio. Confira a Kie antes de criar outra tentativa; pode haver cobrança. Nenhum reenvio foi feito.')
            save(job, r)


def confirm(job, ident, nonce):
    if job.get('broll_config', {}).get('origem') == 'nenhum':
        raise ValueError('As cenas de apoio estão desativadas para esta edição.')
    key()  # Fail before recording any submission if configuration is missing.
    with locked(job):
        r = load(job, ident)
        if not secrets.compare_digest(r['nonce'], nonce):
            raise ValueError('Revisão inválida. Abra novamente o rascunho.')
        if r['status'] != 'rascunho':
            return r  # Double-click/replayed POST never creates a second paid task.
        check_scene(job, r)
        r['status'] = 'enviando'
        r['submitted_at'] = datetime.now(timezone.utc).isoformat()
        save(job, r)
    threading.Thread(target=_submit, args=(job, ident), daemon=True).start()
    return r


def upload(path):
    # The API receives only the explicitly approved reference image, never the raw video.
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('A imagem excede 10 MB. Use uma referência menor para animar.')
    boundary = '----studio' + uuid.uuid4().hex
    mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(path.suffix.lower(), 'image/png')
    parts = []
    for name, value in [('uploadPath', 'estudio-brolls'), ('fileName', path.name)]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    parts.extend([path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()])
    req = urllib.request.Request('https://kieai.redpandaai.co/api/file-stream-upload',
        data=b''.join(parts), headers={'Authorization': 'Bearer ' + key(),
        'Content-Type': 'multipart/form-data; boundary=' + boundary})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.load(response)
    url = (data.get('data') or {}).get('downloadUrl')
    if not url or not url.startswith('https://'):
        raise ValueError('Upload da referência não confirmado.')
    return url


def refresh(job, ident):
    # Polling resumes a known task; it never creates a new one.
    with locked(job):
        r = load(job, ident)
        if r['status'] != 'processando' or not r.get('task_id'):
            return r
        from urllib.parse import urlencode
        data = call('GET', BASE + '/recordInfo?' + urlencode({'taskId': r['task_id']}))
        if data.get('state') == 'fail':
            r.update(status='falhou', erro='A geração falhou no provedor. Nenhuma nova tentativa foi criada.')
        elif data.get('state') == 'success':
            result = data.get('resultJson') or {}
            if isinstance(result, str):
                result = json.loads(result)
            urls = result.get('resultUrls') or result.get('result_urls') or []
            if isinstance(urls, str):
                urls = [urls]
            if not urls or not urls[0].startswith('https://'):
                raise ValueError('A tarefa terminou, mas ainda não há arquivo disponível.')
            ext = '.mp4' if r['tipo'] == 'video' else '.png'
            path = folder(job) / (r['id'] + ext)
            tmp = path.with_suffix('.download')
            with urllib.request.urlopen(urls[0], timeout=120) as response, tmp.open('wb') as out:
                import shutil
                shutil.copyfileobj(response, out)
            if not tmp.stat().st_size:
                raise ValueError('Arquivo vazio; consulte novamente a mesma tarefa.')
            if r['tipo'] == 'imagem':
                from PIL import Image
                with Image.open(tmp) as generated:
                    r['dimensoes'] = list(generated.size)
                    generated.convert('RGB').save(tmp, format='PNG')
                w, h = r['dimensoes']
                rw, rh = map(int, r['ratio'].split(':'))
                if abs((w / h) / (rw / rh) - 1) > .04:
                    r['aviso_formato'] = 'O provedor entregou uma proporção diferente da pedida. Confira o enquadramento antes de usar.'
            tmp.replace(path)
            r.update(status='pronto', arquivo=str(path.relative_to(prod.RAIZ / job['sandbox'])),
                     creditos_reais=data.get('creditsConsumed'))
        save(job, r)
        return r


def use(job, ident):
    if job.get('rodando') or job.get('status') in ('na_fila', 'exportado', 'arquivado'):
        raise ValueError('Aguarde a edição terminar antes de alterar os trechos.')
    r = load(job, ident)
    if r['status'] != 'pronto':
        raise ValueError('Aguarde o b-roll ficar pronto e revise a prévia.')
    if not (prod.RAIZ / job['sandbox'] / r['arquivo']).is_file():
        raise ValueError('Arquivo local indisponível. Recupere a mídia antes de usá-la.')
    check_scene(job, r)
    plan = prod.plano(job)
    b = next((b for b in plan['beats'] if b['id'] == r['beat']), None)
    if not b:
        raise ValueError('Este trecho não existe mais no plano.')
    option_id = 'ia-' + r['id']
    option = {'id': option_id, 'titulo': 'Cena ilustrativa · ' + r['model'], 'fonte': 'Gerado por IA',
              'arquivo': r['arquivo'], 'motivo': r['input']['prompt'], 'gerado_ia': True,
              'proporcao': r['ratio'], 'tipo_midia': r['tipo'], 'com_audio': False,
              'verificado': 'Imagem/cena revisada e selecionada pelo usuário'}
    if r['tipo'] == 'imagem':
        option['sheet'] = r['arquivo']
    b['opcoes'] = [o for o in b.get('opcoes', []) if o['id'] != option_id] + [option]
    b.update(tipo='broll', escolha=option_id)
    import edicao
    edicao.validar(job, plan)
    b.pop('previa', None)
    plan.pop('aprovado_em', None)
    prod.gravar_json(prod.RAIZ / job['sandbox'] / 'PLANO.json', plan)
    job['status'] = 'plano'
    job['edicao_alterada'] = bool(job.get('saida'))
    prod.salvar(job)
    return r


def overlay(job, ident, text, position):
    """Acabamento local inspirado no overlay_texto: cópia, contorno e área segura."""
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    source = load(job, ident)
    text = text.strip()
    if source['tipo'] != 'imagem' or source['status'] != 'pronto':
        raise ValueError('Texto local exige uma imagem pronta.')
    if not text or len(text) > 100 or position not in ('top', 'bottom'):
        raise ValueError('Use até 100 caracteres e escolha topo ou base.')
    with Image.open(prod.RAIZ / job['sandbox'] / source['arquivo']) as opened:
        image = opened.convert('RGB')
    draw = ImageDraw.Draw(image)
    w, h = image.size
    font_paths = [Path.home() / 'Library/Fonts/Anton-Regular.ttf',
                  Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]
    font_path = next((p for p in font_paths if p.is_file()), None)
    # Shrink until the complete text fits both the safe width and 30% of the height.
    for size in range(max(12, int(min(w, h) * .11)), 7, -1):
        font = ImageFont.truetype(str(font_path), size) if font_path else ImageFont.load_default(size=size)
        lines = textwrap.wrap(text.upper(), width=max(8, int(w / (size * .7))))
        content = '\n'.join(lines)
        box = draw.multiline_textbbox((0, 0), content, font=font, spacing=size // 4, stroke_width=max(1, size // 15))
        if box[2] - box[0] <= w * .84 and box[3] - box[1] <= h * .3:
            break
    x = (w - (box[2] - box[0])) / 2 - box[0]
    y = h * .08 - box[1] if position == 'top' else h * .88 - box[3]
    draw.multiline_text((x, y), content, font=font, fill='white', stroke_fill='black',
                        stroke_width=max(1, size // 15), spacing=size // 4, align='center')
    r = dict(source)
    r.update(id=uuid.uuid4().hex, created=datetime.now(timezone.utc).isoformat(), nonce=secrets.token_urlsafe(32),
             model='Texto local', usd_estimado=0, creditos_reais=0, origem=None, overlay_de=ident,
             input={'prompt': text}, task_id=None)
    r['arquivo'] = 'gerados/' + r['id'] + '.png'
    image.save(prod.RAIZ / job['sandbox'] / r['arquivo'])
    save(job, r)
    return r


def recover(job, ident, task_id):
    """Vincula uma tarefa existente após envio incerto; nunca chama createTask."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', task_id):
        raise ValueError('Informe o taskId mostrado no histórico da Kie.')
    with locked(job):
        r = load(job, ident)
        sent = datetime.fromisoformat(r.get('submitted_at') or r['created'])
        expired = (datetime.now(timezone.utc) - sent).total_seconds() > 180
        if r['status'] != 'incerto' and not (r['status'] == 'enviando' and expired):
            raise ValueError('Esta cena já tem uma tarefa ou o envio ainda está em andamento.')
        from urllib.parse import urlencode
        try:
            data = call('GET', BASE + '/recordInfo?' + urlencode({'taskId': task_id}))
        except Exception:
            raise ValueError('Não foi possível consultar a tarefa. Nenhuma geração foi iniciada.') from None
        if data.get('model') != r['model']:
            raise ValueError('A tarefa informada não corresponde ao modelo desta cena.')
        params = data.get('param') or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except ValueError:
                params = {}
        remote_prompt = (params.get('input') or {}).get('prompt')
        if remote_prompt and remote_prompt != r['input']['prompt']:
            raise ValueError('O prompt da tarefa é diferente do rascunho. Confira o identificador.')
        r.update(status='processando', task_id=task_id)
        r.pop('erro', None)
        save(job, r)
        return r
