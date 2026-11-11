# Como fazer: Lista de estáticos (pessoa no canto)

**Quando usar:** vídeo gravado em que a pessoa apresenta uma lista de ideias, e cada ideia tem uma imagem (estática, print, mockup). Ex.: "10 estáticos pra Black Friday".

**O que precisa receber:** o vídeo gravado (original da câmera, não o do WhatsApp) e a pasta das estáticas numeradas (`01-...png`, `02-...png`). Qualquer quantidade de itens: lista maior que a tela encolhe o passo.

**Régua:** o exemplo principal (o 1º de "exemplos" no `formato.json`: o vídeo do João, 10 estáticos pra Black Friday). A referência original é o reel do Luke (exemplo-1: 21 formatos, 23 s). Saiu um vídeo melhor? `python3 app/ferramentas/formatos.py exemplo lista-de-estaticos <mp4>`.

**Motor:** `formatos/lista-de-estaticos/base/render_lista.py` (PIL + ffmpeg, rosto por OpenCV). Roda por `--pasta <sandbox>` (`--storyboard`, `--out`, `--conferir`).
A análise da fala é `python3 app/ferramentas/analisar_fala.py` (rosto, pausas, recomeços e pistas de item).

**Som:** sem música e sem efeito: só a fala original (só pausa e erro saem).

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar a entrada.** Original em `work/bruto.mov` (iPhone HDR → bt709). `corte.py transcrever ... --groq` e `analisar_fala.py`
   (saída em `work/analise.json`: rosto, pausas, recomeços, pistas).
2. **Montar as cenas.** Lado pelo rosto (esquerda → coluna à direita; direita → coluna à esquerda; meio → estática acima da
   cabeça e lista estreita ao lado). Cortes: recomeço e pausa, depois de ler as palavras cortadas de cada um. Itens: um por
   estática (ordem da pasta), com o nome falado e o segundo em que é citado. Título em 2 linhas. Estilo pela escolha do Criar: `lista` (padrão) ou `ao-lado` (sem lista, estática ao lado da cabeça, bom pra até ~6 itens). Legenda palavra por palavra opcional (`palavras`). Escrever `cenas.json`.
3. **Storyboard (para pro João aprovar).** `--storyboard`: um quadro por item. Comparar com a folha do exemplo.
4. **Vídeo.** `--out <saida>`: lista se preenchendo (item atual em amarelo) e a estática com fade de 0,18 s a cada item.
5. **Conferência.** `--conferir`: folha do vídeo ao lado da do exemplo. Nada cobre o queixo, texto legível, item na hora da fala.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, titulo e texto). Correção do João vira regra pela REGRA Nº 2
do `CLAUDE.md`. Regras nascidas aqui: o texto é leve e em minúscula (como a referência), título em 2 linhas com UMA
palavra forte e suave; o lado vem do rosto, nunca fixo; falsa largada e pausa saem, mas confira as palavras antes.

## Som e cena de apoio

**Música:** não usa (sempre).

**Efeitos:** não usa (sempre).

**Cena de apoio:** estática (imagem) por item da lista; fontes: acervo, pexels, cliente; 2-4 s; 1 por item; não usa: no gancho. Prévia: folha com 3 opções por item antes do render.

Música e efeito rodam em rodízio (`acervo/usos.jsonl`): nem a mesma música nas últimas 8 entregas do cliente, nem o mesmo efeito nas últimas 4; favorito e pedido do João passam.
