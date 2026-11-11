"""Esquemas ilustrativos da ficha; nunca tratados como um frame renderizado."""
import re
import unicodedata


def norm(value):
    return unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()


def esquema(ficha, nome=''):
    estrutura=ficha.get('estrutura') or []
    texto=norm(' '.join(str(x) for x in estrutura))
    nome=norm(nome)
    formato=ficha.get('formato')   # em fichas portadas é só o nome do formato (texto)
    resolucao=str((formato.get('resolucao') if isinstance(formato,dict) else None) or '1080x1920')
    dimensoes=re.search(r'(\d+)\s*[x×]\s*(\d+)',resolucao)
    largura,altura=map(int,dimensoes.groups()) if dimensoes else (1080,1920)
    largura=max(1,largura);altura=max(1,altura)
    cores=[x.get('cor') for x in ficha.get('paleta',[]) if isinstance(x,dict) and re.fullmatch(r'#[0-9a-fA-F]{6}',str(x.get('cor','')))]
    cor=next((x for x in cores if x.upper() not in ('#FFFFFF','#000000')),'#53795B')

    def zona(tipo,titulo,y,h,descricao,**extra):
        return dict(tipo=tipo,titulo=titulo,x=0,y=y,w=100,h=h,descricao=descricao,**extra)
    def estado(titulo,zonas):return dict(titulo=titulo,zonas=zonas)

    pessoa=zona('pessoa','Quem fala',0,100,'O rosto e a voz conduzem a mensagem.')
    legenda=zona('legenda','Legenda da fala',65,12,'Palavras realmente ditas, sincronizadas com a voz. Exemplo de texto apenas ilustrativo.')
    dividido=('reel-dividido' in nome or nome=='react') and 'mascara' not in nome
    if dividido:
        topo,faixa=42.5,14.0625
        medidas=[]
        for linha in estrutura:
            m=re.search(r'(\d+)\s*[–-]\s*(\d+)\s*px',str(linha))
            if m:medidas.append((int(m[1]),int(m[2])))
        if len(medidas)>=3 and medidas[0][0]==0 and medidas[0][1]==medidas[1][0] and medidas[1][1]==medidas[2][0]:
            topo=100*medidas[0][1]/altura;faixa=100*(medidas[1][1]-medidas[1][0])/altura
        estados=[estado('Composição do vídeo',[
            zona('cena' if nome=='react' else 'pessoa','Cena comentada' if nome=='react' else 'Quem fala',0,topo,'Parte de cima: enquadramento do rosto.' if nome!='react' else 'A referência aparece na parte de cima.'),
            zona('faixa','Legenda' if 'placa da legenda' in texto else 'Texto em destaque',topo,faixa,'Faixa de cor com texto branco. A ficha define se o texto é fixo ou acompanha a fala.',cor=cor),
            zona('pessoa' if nome=='react' else 'cena','Reação' if nome=='react' else 'Imagem de apoio',topo+faixa,100-topo-faixa,'Parte de baixo: imagem ou cena relacionada ao que está sendo dito.')])]
    elif 'meme' in nome or 'reel-post' in nome:
        estados=[estado('Post com vídeo',[
            zona('post','Nome + mensagem',0,31,'Cabeçalho de perfil e a frase que apresenta o assunto.'),
            zona('pessoa','Vídeo',31,69,'O vídeo ocupa a área abaixo da mensagem.'),
            zona('legenda','Legenda',76,10,'A legenda acompanha a fala dentro da área do vídeo.')])]
    elif 'react-recorte' in nome:
        estados=[estado('Cena e apresentador',[
            zona('cena','Cena comentada',9,43,'Cena completa, sem esconder o assunto principal.'),
            zona('legenda','Legenda',52,11,'Texto entre a cena e o rosto.'),
            zona('pessoa','Apresentador recortado',63,37,'A pessoa aparece por cima do fundo.')])]
    elif 'mascara' in nome or 'anuncio-imagem' in nome:
        estados=[estado('1 · Fala principal',[pessoa,legenda]),estado('2 · Entra uma imagem',[
            pessoa,zona('cena','Imagem de apoio',9,42,'A imagem entra durante a frase relacionada e depois sai.'),
            legenda])]
    elif ficha.get('tipo')=='camada':
        tipo='switches' if 'toggle' in nome else 'faixa'
        estados=[estado('Camada sobre o vídeo',[pessoa,
            zona(tipo,'Texto / elemento extra',12,22,'Elemento aplicado sobre o vídeo de base, no momento indicado pela ficha.',cor=cor),legenda])]
    elif 'outro-' in nome:
        estados=[estado('Encerramento',[zona('post','Chamada final',20,60,'Mensagem final centralizada, sem acrescentar novas falas.')])]
    else:
        estados=[estado('Fala e legenda',[pessoa,legenda])]
    return dict(estados=estados,ratio=f'{largura} / {altura}',tecnica=estrutura,
                nota='Desenho ilustrativo da composição. As imagens e palavras abaixo são exemplos; os frames reais estão nas demonstrações.')
