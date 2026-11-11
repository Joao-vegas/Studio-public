# Como fazer: Caixinha de perguntas

**Quando usar:** resposta a uma pergunta (de seguidor de verdade ou escrita como gancho). A pergunta na caixinha
segura a retenção e a fala é a resposta. Precisa de b-roll ou de legenda corrida? É outro formato.
**Régua:** exemplo-1 (CONTRATO, item 6). Ele é a régua do visual da caixinha, nunca da fala.
**A tela (1080x1920):** pessoa em tela cheia e a caixa de pergunta do Stories do Instagram, a mesma do 1º ao último
quadro, igual ao print real:
- caixa de 708 px centrada, topo em y=255 (logo abaixo da zona de topo do Instagram), cantos de 24 px;
- faixa #262626 com o título ("O que você quer saber?" ou o que o João pedir) em SF Pro peso 700, 35,6 px, #FAFAFA;
- parte branca com a pergunta em SF Pro peso 680, 47,2 px, #262626, centralizada. Texto longo ganha linha e a caixa
  cresce pra baixo com as mesmas margens: **o tamanho da fonte nunca muda**.
Sem legenda da fala, b-roll, música nem efeito.
**Motor:** ffmpeg + PIL no modelo do cliente. Sandbox em `<modelo>/_sandbox-<slug>/`, script em `../gerar.sh`;
`build-caixinha.py` grava a camada (`camada.json`, tipo caixinha) e o desenho é o `app/ferramentas/caixinha.py` (medidas do print, fixas).
**Som:** só a voz do bruto.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Cortar o bruto.** Rotação conferida e `work/joao.mp4` em 1080x1920, sem silêncio, gaguejo nem erro de começo
   (se o Estúdio já cortou, usar esse). Bruto com texto queimado no lugar da caixinha: avisar no storyboard.
2. **Pergunta da caixinha.** No `PLANO.json` (campo `pergunta`). Veio no briefing: usar EXATAMENTE ela, com "q", "vc",
   "pq" e a maiúscula como ele escreveu (é isso que dá cara de pergunta real). Não veio: 3 opções curtas em
   `opcoes_pergunta`, a recomendada em `pergunta`, e parar pro João escolher. Título só muda se ele pedir (`--titulo`).
3. **Prévia da caixinha (para pro João aprovar).** `zsh ../gerar.sh --dir . --pergunta "<PERGUNTA>" --posicao cima --previa`
   gera o `storyboard.jpg`. Conferir ao lado da folha do exemplo: caixinha igual ao print e acima da cabeça sem encostar
   no cabelo (encostou: `--posicao peito` ou outra altura com `--topo`).
4. **Renderizar.** O mesmo comando sem `--previa` (renderiza pelo `camada.py`); saída em `output/caixinha-de-perguntas/<slug>.mp4` (ou `--saida`) e
   folha em `qa/folha.jpg`. Ao terminar: `python3 app/ferramentas/andamento.py pronto <Cliente> <slug> "Vídeo pronto" --video <mp4> --pasta <sandbox>`.
   O João troca a pergunta, o texto de cima e a altura depois, no botão **Editar o texto** do Em andamento (gera o vídeo de novo).
   Escolhas da tela: "Em cima da cabeça" = `cima`, "Embaixo (no peito)" = `peito`.
5. **Conferência.** `/watch` no vídeo e `qa/folha.jpg` ao lado de `exemplo-1-folha.jpg`: mesma caixinha o tempo todo,
   fonte e margem iguais ao print, rosto livre, sem legenda, b-roll nem música. Mais `conferir_video.py <mp4> --sandbox <sandbox>`.

## Regras

Ficam em `aprendizado/regras.json` do formato e do modelo do cliente. Correção do João vira regra pela REGRA Nº 2 do `CLAUDE.md`.

## Som e cena de apoio

**Música:** não usa (sempre).

**Efeitos:** não usa (sempre).

**Cena de apoio:** não usa (sempre: o vídeo é só a pessoa e a caixinha).
