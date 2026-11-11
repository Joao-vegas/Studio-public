# Como fazer: Análise de tela

**Quando usar:** análise gravada da tela (site, página, anúncio, perfil, o próprio Estúdio) com você comentando
pela câmera, do começo ao fim. Se precisa de b-roll trocando embaixo, é a Tela dividida.
**Régua:** o exemplo principal (o 1º de "exemplos" no `formato.json`). Régua de estilo e qualidade (não é molde: o conteúdo é sempre próprio). Cada vídeo fica no nível dele ou melhor; se um sair
melhor, ele vira o exemplo: `python3 app/ferramentas/formatos.py exemplo <slug> <mp4>`.
**A tela (1080x1920):** em cima a gravação de tela (960 px), embaixo a câmera (960 px) seguindo o rosto. Na emenda
(y=960) uma sombrinha escura (degradê de ~150 px pra cada lado) e a frase fixa empilhada em faixas que abraçam o
texto: linha 1 branca com texto preto, linha 2 vermelha #DE1C21 com texto branco, linha 3 branca. Gilroy ExtraBold
64 px em caixa-alta, centralizada, o vídeo INTEIRO (a referência só usava no começo; aqui não sai).
**Motor:** vídeo gravado, `gerar.sh` do modelo do cliente (ffmpeg + PIL), com `build-faixa.py` (sombrinha e
faixas) e `seguir_rosto.py` (recorte da câmera).
**Som:** só a voz da câmera (`--audio tela` se a voz estiver na gravação de tela). Sem música e sem efeito.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar as duas gravações.** `work/joao.mp4` = câmera (já cortada; conferir rotation), `work/tela.mp4` =
   gravação de tela. Sincronismo: `--tela-atraso <s>` (positivo = a tela começou depois da câmera). Se o corte
   tirou trechos da câmera, cortar a tela nos mesmos pontos antes de montar.
2. **Frase fixa.** A do João; sem ela, propor em caixa-alta, 2 a 3 linhas curtas (`|` quebra a linha): o que está
   sendo analisado e o achado. Não repete a 1ª frase falada.
3. **Prévia (para pro João aprovar).** `zsh ../gerar.sh --dir . --titulo "LINHA 1|LINHA 2|LINHA 3" --previa`
   grava `storyboard.jpg`. Tela horizontal: `cover` (padrão) enche o bloco e corta as laterais, foco com
   `--tela-x 0..1`; se o que importa está nas bordas, `--tela-modo fit` (tela inteira com fundo desfocado).
   Emenda em outro lugar: `--corte <y>`.
4. **Montar e renderizar.** O mesmo comando sem `--previa`. Sai em `vegasContent/output/analise-de-tela/<slug>.mp4`
   e a folha em `<sandbox>/qa/folha.jpg`.
5. **Conferência.** Folha do vídeo ao lado da `exemplo-1-folha.jpg`: faixas e emenda fixas o vídeo todo, rosto
   no bloco de baixo quadro a quadro, voz batendo com o que aparece na tela. Pior que o exemplo não sai.

## Som e cena de apoio

Sem música, sem efeito e sem cena de apoio: em cima é a gravação de tela, embaixo a pessoa, sempre.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, titulo e texto). Correção do João vira regra pela REGRA Nº 2
do `CLAUDE.md`; regra nova só do exemplo, do `historico.jsonl` ou do que o João disse.
