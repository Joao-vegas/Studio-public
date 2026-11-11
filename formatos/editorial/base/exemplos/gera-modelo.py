# gera.py DO VÍDEO (copie pra <sandbox>/gera.py e troque as cenas; rode de dentro da sandbox: python3 gera.py).
# O tempo vem da voz (g.a("palavra") anda pela fala na ordem), a peça vem do que a oração diz (base/README.md, "Quando usar cada peça").
# Régua (4 estudos quadro a quadro): plano ~0,5-0,8 s de mediana, câmera sempre andando, nunca 3 peças iguais seguidas (fora foto),
# 7+ tipos de peça, cada clipe real UMA vez, a mesma foto no máximo 2 vezes. Exemplo completo e comentado: grupo-por-crenca-gera.py.
import sys
sys.path.insert(0, "/Users/joaomarcospiki/Projetos/Skill/Estúdio/formatos/editorial/base/exemplos")
from gera_lib import G
g = G(__file__)
F = lambda n: f"fotos/{n}.jpg"
R = lambda n: f"recortes/{n}.png"
P = lambda n: f"prints/{n}.png"
c = []
# gancho: pergunta ou frase que prende, com imagem real e câmera andando
c.append(g.foto(g.a("Por"), F("exemplo-0"), mov="in"))
# nome de pessoa -> cartão ou foto P&B com ponto; lista -> chips; dois lados -> dividido; número/ano -> contador; gente fazendo a coisa -> clipe
# c.append({"tipo": "cartao", "de": g.a("Elizabeth"), "imagem": F("holmes-0"), "mov": "esq"})
# c.append(g.clipe(g.a("torcida"), "torcida", som=.4, etiqueta="Torcida", nota="ninguém olha o dado"))
# c.append({"tipo": "print", "de": g.a("estudo"), "imagem": P("materia"), "giro": -2, "largura": 84, "grifos": [{"frase": "trecho exato do print", "t": g.t("pesquisa")}]})
# c.append(g.texto(g.a("Certeza"), "Certeza sem prova é golpe.", ["golpe."], entrada="flash"))   # virada / fecho: texto que acende
g.fechar(c, titulo="TÍTULO", saida="video.mp4", marca=None)
