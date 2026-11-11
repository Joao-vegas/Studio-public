"""Preferências simples da edição, compartilhadas pela UI, plano e render.

Formato com ESTEIRA (formato.json → "esteira") segue os passos da própria receita: aqui ele sai do caminho
(sem teto de b-roll, sem "mantenha o bruto"); b-roll vira só um tipo de cena do motor do formato."""


QTD_MAX = 200   # só trava digitação absurda; o formato (Tela dividida) cobre o vídeo inteiro, 3 min = muitas cenas


def _esteira(job):
    try:
        import formatos
        return formatos.esteira_do_job(job or {})
    except Exception:
        return None


def regra_cenas(job):
    """O que o formato do vídeo declara sobre a quantidade de cenas de apoio (formato.json → escolhas → "cenas"):
    "quantidade" fixa e/ou "cenas_por_segundo" com "minimo" e "maximo". Sem formato ou sem a escolha: {}."""
    try:
        import formatos
        f = formatos.do_job(job or {}) or {}
    except Exception:
        return {}
    return next((e for e in f.get('escolhas') or [] if isinstance(e, dict) and e.get('campo') == 'cenas'), {})


def duracao_bruto(job):
    try:
        from _comum import RAIZ, ffprobe
        b = RAIZ / (job or {}).get('bruto', '')
        return float(ffprobe(b).get('duracao') or 0) if (job or {}).get('bruto') and b.is_file() else 0.0
    except Exception:
        return 0.0


def cenas_pela_duracao(regra, dur):
    """Número de cenas pela duração do bruto (ex.: 0.1 por segundo = 1 a cada 10 s), do mínimo ao máximo (se houver)."""
    cps = regra.get('cenas_por_segundo')
    if not cps or not dur:
        return regra.get('quantidade')
    n = max(int(regra.get('minimo') or 1), round(dur * float(cps)))
    return min(int(regra['maximo']), n) if regra.get('maximo') else n   # sem "maximo": sem teto, vídeo longo leva mais cenas


def quantidade(job):
    """Quantas cenas de apoio este vídeo leva. A escolha do João na tela manda; sem ela (padrão do formato, marcado
    "do_formato"), segue a regra do formato pela duração do bruto; sem regra, o que está salvo ou 3."""
    prefs = (job or {}).get('broll_config') or {}
    if prefs.get('origem') == 'nenhum':
        return 0
    if 'quantidade' in prefs and not prefs.get('do_formato'):
        return prefs['quantidade']
    regra = regra_cenas(job)
    dur = duracao_bruto(job) if regra.get('cenas_por_segundo') else 0
    return cenas_pela_duracao(regra, dur) or prefs.get('quantidade') or 3


def apoio_do_job(job):
    """formato.json → "apoio" (cena de apoio: b-roll, print, 3D…) do formato do vídeo, ou {}."""
    try:
        import formatos
        a = (formatos.do_job(job or {}) or {}).get('apoio')
    except Exception:
        return {}
    return a if isinstance(a, dict) else {}


def politica_apoio(job):
    """POLÍTICA DE CENA DE APOIO: vale pra formato com `apoio.usa: true` (job novo nasce com busca; "sem cena de apoio" na tela vira origem nenhum e some).
    Consulta pelo sentido, 2 fontes por cena, filtro de qualidade e folha de prévia com 3 opções SEMPRE antes do render."""
    ap = apoio_do_job(job)
    prefs = (job or {}).get('broll_config') or {}
    if not ap.get('usa') or prefs.get('origem') == 'nenhum':
        return ''
    fontes = ', '.join(ap.get('fontes') or []) or 'acervo, youtube, pexels'
    return ('\nPOLÍTICA DE CENA DE APOIO (deste formato: ' + str(ap.get('tipo') or 'b-roll') + '; fontes: ' + fontes
            + '; duração: ' + str(ap.get('duracao_s') or '2-4') + ' s; quantidade: ' + str(ap.get('quantidade') or 'a do formato')
            + '; não usa: ' + str(ap.get('quando_nao') or 'no gancho e no CTA') + '). Acervo primeiro, depois a busca. Regras: '
            '(1) consulta pelo SENTIDO da fala, não pela palavra: escreva no PLANO a ideia visual e 2-3 consultas (literal, metafórica, cena de filme ou notícia); '
            '(2) pelo menos 2 fontes por cena (YouTube + Pexels/Pixabay/Commons); '
            '(3) filtro antes de mostrar: 720p ou mais, sem marca d\'água, legenda queimada nem rosto indevido, duração igual ou maior que a da cena, com movimento; confira olhando os quadros; '
            '(4) 3 opções por cena e a FOLHA DE PRÉVIA obrigatória: monte work/brolls/folha-<cena>.jpg com `python3 app/ferramentas/folha_broll.py` '
            '(6 quadros por opção, com fonte, link, tempo e resolução) e grave a opção em `escolha` no PLANO.json; nada entra no render sem `escolha`.')


def instrucao_esteira(job):
    """Formato com esteira: diz à IA o número de cenas de apoio quando o formato declara a regra (Tela dividida) ou o
    João mudou o número na página do vídeo ("na_tela"). Onde e como cada cena entra continua sendo a receita do formato."""
    prefs = (job or {}).get('broll_config') or {}
    politica = politica_apoio(job)
    if prefs.get('origem') in (None, 'nenhum') or not (regra_cenas(job) or prefs.get('na_tela')):
        return politica
    dur = duracao_bruto(job)
    return (f'\nQUANTIDADE DE CENAS: {quantidade(job)} cenas de apoio no vídeo inteiro'
            + (f' (bruto de {dur:.0f} s)' if dur else '') + '. Não invente cena a mais; onde e como cada uma entra '
            'segue os passos do formato.' + politica)


def preferencias(form):
    if form.get('usar_broll') != '1':
        return {'origem': 'nenhum', 'quantidade': 0}
    origem = form.get('origem_broll', 'busca')
    if origem not in ('busca', 'ia', 'misto'):
        raise ValueError('Escolha banco, IA ou ambos.')
    try:
        quantidade = int(form.get('quantidade_broll', '3'))
    except (ValueError, TypeError):
        raise ValueError('Informe uma quantidade inteira de b-rolls.') from None
    if not 1 <= quantidade <= QTD_MAX:
        raise ValueError(f'Escolha de 1 a {QTD_MAX} cenas por vídeo.')
    return {'origem': origem, 'quantidade': quantidade, **({'na_tela': True} if form.get('na_tela') else {})}


def aplicar(job, prefs):
    job['broll_config'] = prefs
    if _esteira(job):
        job['escopo_edicao'] = 'esteira'   # a receita do formato manda; a preferência fica guardada, sem forçar b-roll
        return
    job['escopo_edicao'] = 'busca' if prefs['origem'] in ('busca', 'misto') else 'essencial'


def instrucao(job):
    prefs = job.get('broll_config')
    if not prefs or _esteira(job):
        return ''  # Projetos anteriores mantêm suas decisões até serem alterados; formato com esteira segue a receita.
    if prefs['origem'] == 'nenhum':
        return '\nPREFERÊNCIA DO USUÁRIO: SEM B-ROLL. Não proponha, busque, gere ou insira cenas de apoio nem citações em vídeo. Use apenas o bruto, cortes, legendas e acabamento do modelo. Esta escolha prevalece sobre a política de b-roll do modelo.'
    total = quantidade(job)
    source = ('Buscar cenas reais nas fontes disponíveis (YouTube, Pexels, Pixabay, Commons, NASA), sem gerar mídia.'
              if prefs['origem'] in ('busca', 'misto') else
              'Não fazer busca externa. Proponha somente as cenas mais úteis como beats tipo broll com opcoes: [], escolha: null e geracao_sugerida: {prompt: descrição visual da cena, ratio: 9:16 ou 16:9 ou 1:1}. Não gerar mídia nesta etapa; o usuário aprovará as imagens e animações separadamente no Estúdio.')
    if prefs['origem'] == 'misto':
        source = ('Banco e IA estão habilitados juntos. Em TODO beat de broll traga as cenas reais verificadas E TAMBÉM '
                  'geracao_sugerida: {prompt: descrição visual da cena, ratio: 9:16 ou 16:9 ou 1:1}, pra o João poder '
                  'trocar por uma imagem de IA naquele trecho sem nova análise. Diga no motivo qual das duas comunica '
                  'melhor a fala. Para IA só proponha a imagem; nunca chame geração paga, que depende de aprovação '
                  'separada no Estúdio.')
    source += ' Material próprio é opcional. Se houver anexos, abra seus frames, avalie relação com a fala, enquadramento, resolução, movimento e defeitos antes de recomendar. Nunca aprove por nome do arquivo nem force um take inadequado.'
    if prefs.get('do_formato'):   # o teto veio do formato (ex.: Tela dividida, cena embaixo o tempo todo): os intervalos são dele
        return (f'\nPREFERÊNCIA DO USUÁRIO: até {total} cenas de apoio no vídeo inteiro (o número que o formato pede). '
                + source + ' Não insira beats sem mídia escolhida. Entre uma cena e outra, siga os passos do formato '
                '(se ele cobre o vídeo todo com cenas, cada cena cobre um trecho maior); nunca invente cena a mais.')
    return (f'\nPREFERÊNCIA DO USUÁRIO: no máximo {total} trechos de b-roll no vídeo inteiro. '
            'A quantidade é um teto, não uma obrigação de preencher. Priorize os momentos em que a imagem explica a fala. '
            + source + ' Não crie b-rolls adicionais por conta própria. Não insira beats sem mídia escolhida; nesses intervalos mantenha o bruto.')


def selecionados(plan):
    return [b for b in (plan or {}).get('beats', []) if b.get('tipo') in ('broll', 'citacao') and b.get('escolha')]


def validar(job, plan):
    prefs = job.get('broll_config')
    if not prefs or _esteira(job):
        return
    n, teto = len(selecionados(plan)), quantidade(job)
    if n > teto:
        raise ValueError(f'O plano tem {n} b-rolls selecionados; o limite escolhido é {teto}. Ajuste as escolhas ou a quantidade antes de renderizar.')
