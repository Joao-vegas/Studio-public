# Como fazer: Tela dividida

**Quando usar:** fala gravada de 30 a 90 s em que as cenas de baixo seguram a retenção (a pessoa fica parada na
câmera). Cena pontual por cima da pessoa em tela cheia é outro formato (Fala com cenas).
**Régua:** exemplo-1 (CONTRATO, item 6).
**A tela (1080x1920):** em cima a pessoa (1056 px, 55%); no meio a faixa vermelha de bordas rasgadas com a
manchete em Bebas Neue branca (270 px, o vídeo inteiro); embaixo as cenas, vídeo mudo (594 px), trocando a cada
3 s. Cortes secos, sem fade (o fade pisca preto).
**Motor:** vídeo gravado, scripts do modelo do cliente (ffmpeg + PIL, zsh), em `../` da sandbox: `gerar.sh` (monta), `build-band.py` (faixa),
`buscar-broll.sh` (site, og:image, trecho do YouTube), `verificar.sh` (quadros pra conferir o rosto).
**Som:** a voz do bruto; as cenas sempre mudas. Música opcional, baixinha (~0,13 a 0,15) com fade, sem voz de
banco; só a que o João mandar ou aprovar (o modelo do cliente pode exigir que ele mande). Sem efeito sonoro.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar o bruto.** `ffprobe -v error -select_streams v:0 -show_entries stream_side_data=rotation` antes de
   converter: 3840x2160 com rotation=90 é vertical. `work/joao.mp4` em 1080x1920, sem o silêncio do começo e do
   fim (silencedetect, ~0,15 s de margem). Bruto já cortado pelo Estúdio: usar o `work/joao.mp4` dele.
   Transcrição com tempo por palavra (Groq) em `work/words.json`; conferir nome, número e acento.
2. **Manchete da faixa.** Caixa-alta, frase seca, verdade inconveniente que um leigo entende de primeira.
   Complementa a 1ª frase falada, nunca a repete, e nunca culpa quem assiste. Vai no `PLANO.json` (campo
   `manchete` e no começo do `resumo`). CTA (`--cta "COMENTE ..." --cta-t <s>`) só se o briefing pedir.
3. **Cenas de baixo.** Um beat `broll` por momento da fala, cobrindo o vídeo inteiro (o exemplo: 8 cenas em
   83 s), cada um com 3 opções de vídeo do mundo do cliente que casem com a fala. Ordem de busca: acervo,
   get-brolls (`.claude/skills/broll/SKILL.md`) e `../buscar-broll.sh` quando a fala cita site, marca ou canal.
   Olhar os quadros antes de propor: sem marca d'água no meio, sem letterbox, sem legenda queimada, sem rosto
   falando que compete com a pessoa de cima, nada ilícito nem sensual. Priorizar movimento. Se a tela limitou
   o número de cenas, cada uma cobre um trecho maior (pedaços diferentes do mesmo clipe); sem teto, vídeo longo leva mais cenas.
4. **Storyboard (para pro João aprovar).** `python3 app/ferramentas/storyboard.py <sandbox>` gera o
   `storyboard.jpg` (um quadro por cena, com tempo e fala), comparado com a folha do exemplo.
   O João escolhe cenas e música e aprova a manchete.
5. **Enquadrar o rosto.** O gerar.sh segue o rosto sozinho (seguir_rosto.py: rosto no meio, desliza sem corte seco; `--rosto-fixo` desliga).
   Prévia do bloco de cima, calibrando pelo PIOR quadro (quando a pessoa se inclina): rosto centralizado, folga acima da cabeça, ombros visíveis, faixa longe do queixo. Faixa encostando
   no queixo: descer a faixa com `--joao-h`, não mexer no offset. `--video-offset-y` menor = rosto desce.
   Partir da calibração aprovada nas regras do modelo do cliente; o exemplo usou `--joao-h 1056 --video-offset-y 330`.
   `gerar.sh` sem `--joao-h` (bloco fixo de 816, como o do Cliente2, que recusa a flag): portar a flag do modelo
   base antes (regra `proporcao-dos-blocos`).
6. **Montar e renderizar.** Cortar os trechos escolhidos e montar `work/master.mp4` na ordem da fala, do tamanho
   dela (blocos de ~3 s, mudos, sem trecho repetido) e marchar linear, de dentro da sandbox:
   ```
   zsh ../gerar.sh --dir . --titulo "A SITUAÇÃO NO BRASIL TÁ FEIA" --srcs work/master.mp4 \
     --takes "0,3,6,...,81" --step 3.0 --joao-h 1056 --video-offset-y 330
   ```
   `--takes`: um número por corte até o fim (83 s / 3 = 28 cortes: 0 a 81); lista curta volta pro começo do
   master e repete cena. `--video-zoom` e `--video-offset-x` vêm do passo 5. O render sai em
   `<x>Content/output/<modelo>/` e vai copiado pra saída final do vídeo. Música aprovada: mixar baixinha com fade
   (`--music` onde o gerar.sh tiver; senão depois, com `amix duration=first` e `-c:v copy`).
7. **Conferência.** Skill `/watch` no vídeo e `zsh ../verificar.sh <mp4> 2`: rosto no lugar quadro a quadro
   (mexer de leve é ok; cortado ou no canto = recalibrar e renderizar de novo), faixa longe do queixo, cenas
   variadas sem trecho repetido nem marca d'água, nada importante nas zonas do Instagram (topo, direita, base).
   Folha: `python3 app/ferramentas/formatos.py folha-video <mp4> <sandbox>/qa/folha.jpg`, ao lado da do exemplo: pior que ele não sai.

**Regras:** `aprendizado/regras.json`; as do modelo do cliente mandam mais (calibração de cada setup, cenas do nicho, música). Correção vira regra pela REGRA Nº 2.

## Som e cena de apoio

**Música:** leve e constante, discreta. Volume: ~0,13 a 0,15 sob a voz, com fade. Quando: do início ao fim, só se o João mandar ou aprovar no storyboard. Não usa: sem voz de banco; sem pedido, sai só a voz. Troca: 1 faixa.

**Efeitos:** não usa (sempre).
**Cena de apoio:** cena embaixo o vídeo todo, troca por frase; fontes: acervo, youtube, pexels; 3-6 s; a que o formato pede pela duração; não usa: nunca deixar a metade de baixo parada. Prévia: folha com 3 opções por cena antes do render.
