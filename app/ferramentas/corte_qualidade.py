"""Contrato de fala fiel e revisão de continuidade compartilhados pelos modelos."""
import math
import re
import unicodedata


def _tokens(texto):
    t = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return [w for w in re.sub(r'[^a-z0-9 ]+', ' ', t).split() if w]


def _prefixo(parte, todo):
    """`parte` é o COMEÇO de `todo`?

    Aparar a CAUDA é legítimo (tira o gaguejo da emenda). Aparar o COMEÇO não: em "Não desista",
    cortar a primeira palavra inverte o sentido. Por isso prefixo, não fatia em qualquer posição.
    """
    return todo[:len(parte)] == parte

DIRETRIZES = '''
FALA E CONTINUIDADE — vale para qualquer cliente, estilo e provedor:
- O roteiro de edição é uma seleção da fala gravada. Não invente, complete ou
  troque palavras para emendar frases; legendas devem refletir o áudio real.
- Leia a transcrição COMPLETA antes de escolher os cortes. Depois leia o roteiro
  resultante em sequência: gancho, desenvolvimento e conclusão devem ter sentido.
- Preserve negações, números, condições, sujeito e conclusão. Duas falas parecidas
  podem defender ideias diferentes. O último take não é automaticamente o melhor.
- Use os tempos das palavras e o áudio para localizar as bordas. Preserve a
  consoante inicial e a terminação; confira cada emenda com contexto antes/depois.
- Encurte pausas confirmadas sem remover palavras curtas nem a pausa de ênfase.
  Texto incerto deve ser conferido no áudio; não transforme um palpite em legenda.
- Antes de concluir, verifique as emendas e a sincronização da legenda no vídeo
  final. Declare o que de fato foi conferido e sinalize dúvidas que restarem.
'''


def validar(proposta, original):
    """A fonte manda: a proposta só ESCOLHE e pode APARAR a ponta — nunca ampliar nem inventar.

    Aparar é legítimo e necessário: quando ele começa a frase, para e recomeça, a única forma de tirar
    o gaguejo é encolher o t1 do primeiro trecho até a última palavra que fica. Exigir t0/t1/texto
    idênticos à fonte proibia isso e travava o corte. O que continua proibido é o que protege a fala:
    trocar índice, ampliar o trecho além do que foi gravado e usar palavra que não está na fonte.
    """
    rows=proposta.get('segmentos') if isinstance(proposta,dict) else None
    if not isinstance(rows,list) or len(rows)!=len(original):
        raise ValueError('A proposta mudou os trechos da transcrição. Refaça a análise antes de cortar.')
    for row,source in zip(rows,original):
        if not isinstance(row,dict) or row.get('i')!=source.get('i'):
            raise ValueError('A proposta mudou os trechos da transcrição. Refaça a análise antes de cortar.')
        if not isinstance(row.get('manter'),bool):raise ValueError('Cada trecho precisa indicar se fica ou sai.')
        a,b=row.get('t0'),row.get('t1')
        if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not math.isfinite(a+b) or not 0<=a<b:
            raise ValueError('Há um trecho com tempos inválidos.')
        if abs(a-source.get('t0',a))>0.05 or b>source.get('t1',b)+0.05:
            raise ValueError('A proposta mexeu na borda inicial ou ampliou o trecho além da fala gravada. '
                             'O corte foi interrompido para preservar a fala.')
        if not _prefixo(_tokens(row.get('texto')),_tokens(source.get('texto'))):
            raise ValueError('A proposta alterou palavras da fonte. O corte foi interrompido para preservar a fala.')
    if not any(x['manter'] for x in rows):raise ValueError('Mantenha ao menos um trecho de fala.')


def continuidade(proposta):
    rows=proposta.get('segmentos',[])
    keep=[(i,s) for i,s in enumerate(rows) if s.get('manter')]
    alertas=[]
    if keep:
        texto=keep[0][1].get('texto','').lower().strip()
        if keep[0][0]>0 and texto.startswith(('porque ','por isso ','portanto ','então ','mas ','isso ','ele ','ela ')):
            alertas.append('A abertura pode depender de uma frase retirada. Confira se o assunto fica claro para quem chega agora.')
        for (a,ant),(b,prox) in zip(keep,keep[1:]):
            if b>a+1 and ant.get('texto','').lower().rstrip(' ,;:').endswith((' que',' de',' para',' porque',' se',' com',' uma',' um')):
                alertas.append(f"Confira a ligação entre {ant['t1']:.1f}s e {prox['t0']:.1f}s: a primeira frase pode ter ficado incompleta.")
    return {'roteiro':' '.join(s.get('texto','').strip() for _,s in keep),
            'alertas':list(dict.fromkeys(alertas)),
            'nota':'Texto montado apenas com os trechos escolhidos. Leia em sequência e confira a voz nas emendas.'}
