# Como fazer: TROQUE: nome do formato

**Quando usar:** TROQUE: que tipo de fala ou de vídeo pede este formato.
**Régua:** o exemplo principal (o 1º de "exemplos" no `formato.json`). Régua de estilo e qualidade (não é molde: o conteúdo é sempre próprio). Cada vídeo fica no nível dele ou melhor; se um sair
melhor, ele vira o exemplo: `python3 app/ferramentas/formatos.py exemplo <slug> <mp4>`.
**Motor:** TROQUE: onde está e como roda (motor próprio: `base/render.py` genérico + o visual em `base/index.html`;
vídeo gravado: o `gerar.sh` do modelo).
**Som:** TROQUE: música e efeitos, se usa e de onde vêm (o mesmo do "som" no `formato.json`).

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar a entrada.** Vídeo gravado: transcrição com tempo por palavra em `work/words.json`; conferir nome,
   número e acento. Roteiro: narração pelo motor de voz configurado.
2. **Montar as cenas.** Ler o `ESTUDO.md` (a referência já estudada: não reestude) e olhar a folha do exemplo
   principal. TROQUE: as medidas deste formato (duração de cada cena, tipos de cena, o que entra por cima da fala).
3. **Storyboard (para pro João aprovar).** O comando do formato gera o `storyboard.jpg` (um quadro por cena, com o
   tempo e a fala). Comparar com a folha do exemplo antes de mostrar.
4. **Vídeo.** Render pelo comando do formato, com a música e os efeitos aprovados.
5. **Conferência.** Comparar com o exemplo principal (folha lado a lado). Pior que o exemplo não sai.

## Som e cena de apoio

TROQUE: música (clima, volume, quando entra, quando não), efeitos (quais, em que momento, volume) e cena de apoio
(tipo, fontes, duração, quantidade, quando não) em prosa curta; o mesmo conteúdo do `som` e do `apoio` do formato.json.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, titulo e texto). Correção do João vira regra pela REGRA Nº 2
do `CLAUDE.md`; regra nova só do exemplo, do `historico.jsonl` ou do que o João disse.
