# Como fazer: Fala com cenas

**Quando usar:** vídeo gravado de alguém falando pra câmera (reel ou anúncio) que precisa de ritmo sem tirar a
pessoa da tela. Ela fica em tela cheia com legenda; de tempos em tempos entra um beat (cena na faixa de baixo,
frase na tela, impacto ou zoom no rosto) e sai.
**Régua:** exemplo-1 (CONTRATO, item 6).
**Motor:** vídeo gravado, ffmpeg + PIL. Os scripts são do modelo do cliente (`clientes/<Nome>/<x>Content/modelos/dividido-mascara/`):
`gerar.sh` (render), `build-card-timed.py`, `build-impacto.py`, `escolher-janela-broll.py`, `limpa-broll.py`.
Cliente sem a variante ganha a cópia da base (a do Cliente4). O render roda de dentro da sandbox: `zsh ../gerar.sh --dir .`.
**Som:** ver "Som e cena de apoio". `--sem-sfx` e `--click-cards` só existem na variante do João (nas outras dá erro).

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar o bruto.** `work/joao.mp4` em 1080x1920 (4K vertical desce; rotação conferida). Antes de transcrever, achar take
   refeito: o corte do bruto (`app/ferramentas/corte.py`) marca; na mão, palavra com mais de 1,5 s ou silêncio no meio da fala.
   Cortou: retranscreve tudo. Tempo por palavra em `work/words.json` (Groq), `normaliza-words.py <words.json> --dur <duração>`,
   e ler o texto atrás de nome, número e palavra trocada.
2. **Enquadramento e texto queimado.** Medir cada bruto de novo (a distância muda até na mesma gravação): cabeça e queixo no t=0
   com grade, daí `--video-zoom`, `--video-offset-y` e `--legy`, partindo da regra do cliente. Prévia do t=0: testa inteira,
   legenda abaixo do queixo. Texto queimado no bruto (cartela, gancho, manchete): medir início e fim e esconder a legenda com
   `--leg-hide 's-e'` (~0,5 s de folga); beat não entra em cartela preta, zoom não entra com manchete no topo; texto na altura
   da legenda só numa parte: `--legy-win`.
3. **Planejar os beats.** Base = a pessoa em tela cheia, legenda branca com contorno, 3 palavras por bloco.
   Um beat a cada 6 a 10 s, de 2 a 5 s, com 1 a 2 s de respiro; o 1º em t≈0,4 s com o plano mais forte. Tipos:
   - **cena na faixa:** b-roll mudo numa faixa de borda esfumada embaixo (nunca linha dura de split);
   - **frase na tela:** card animado palavra a palavra, copy = a fala literal, `*palavra*` na cor da ficha;
   - **impacto:** b-roll em tela cheia escurecido, com o texto da fala, 2,2 a 2,8 s, só em conceito forte;
   - **zoom no rosto:** punch suave (`--punch-zoom` ~1,15 a 1,18), 2,5 a 3 s, legenda visível.
   Cada beat ilustra a palavra dita naquele segundo (tempo tirado do `words.json`, nunca estimado); fala que
   lista = uma cena por item; produto citado entra na palavra que o cita. O briefing vira `PEDIDOS.md` numerado.
4. **Buscar as cenas e a música.** Vale a escolha "Cenas de apoio" da tela (sem cenas = nenhum b-roll; gerada por IA = paga,
   só com o João aprovando). Até 3 opções por cena, reais e identificáveis (filme, série, comercial, tela real, matéria real):
   acervo, cenas que o João já escolheu e get-brolls (`.claude/skills/broll/SKILL.md`), com prévia e quadros olhados.
   Fora: marca d'água, tarja preta, rosto ou nome de terceiro, nada ilícito, stock genérico. No máximo 2 beats da mesma
   obra e nenhuma fonte com mais da metade. Música: 2 ou 3 direções pela intenção da fala, sem cara de "vídeo
   motivacional", nunca faixa já reprovada. Tudo no `PLANO.json`, com o `ANALISE.md`.
5. **Storyboard (para pro João aprovar).** `python3 app/ferramentas/storyboard.py <sandbox>` → `storyboard.jpg` (um quadro
   por beat, com tempo e fala; rodapé com a música). Comparar com a folha do exemplo principal. O João escolhe cenas e música na tela.
6. **Montar as cenas aprovadas.** Só o que o João escolheu. Cena de apoio: janela com `escolher-janela-broll.py` (mov < 5, sem
   pico de corte) e versão limpa com `limpa-broll.py --h <altura da faixa>` (barras pretas fora) em `brolls/cuts/bN.mp4`; o "trecho"
   do PLANO.json é do vídeo original (descontar o `local_start_s`). Frase na tela: `build-card-timed.py` com tempos absolutos,
   `card:s-e:@brolls/cards/bN.mp4`. Impacto: `build-impacto.py`. Música: `loudnorm I=-20:TP=-2`. Faltou script na variante: portar de outra.
7. **Vídeo.** De dentro da sandbox (exemplo completo no `comando` da `ficha.json` do modelo):
   `zsh ../gerar.sh --dir . --beats "broll:14.58-19.12:brolls/cuts/b2.mp4;card:19.84-24.5:@brolls/cards/b3.mp4;punch:41.7-48.98" --music <faixa> --music-vol 0.11 --legy <medido> --leg-maxwords 3 --out work/render-final.mp4`
   Caminho relativo vale a partir da sandbox. Legenda em contagem exata de quadros, voz a -16 LUFS, cama baixa do começo ao fim.
8. **Conferência.** Quadros por seek preciso (`-ss` depois do `-i`) e `/watch`: legenda casando com a fala em ~8 pontos, inclusive
   o fim; abaixo do queixo e escondida no texto queimado; faixa esfumada; cards e produto no tempo da palavra e na cor da ficha
   (olhar o pixel); testa inteira; topo, direita e base do Instagram livres. Folha:
   `python3 app/ferramentas/formatos.py folha-video <sandbox>/work/render-final.mp4 <sandbox>/qa/folha-video.jpg`, ao lado da do
   exemplo. Pior que o exemplo não sai. `RESULTADO.md`: o que foi conferido, onde cada pedido entrou (beat e segundo), beats por fonte.
**Regras:** `aprendizado/regras.json`; o que é do cliente (câmera, b-roll, música, cores) fica na regra dele. Correção vira regra pela REGRA Nº 2.

## Som e cena de apoio

**Música:** cinematográfica, escolhida pelo clima da fala (tensa, épica ou calma), cama sem voz. Volume: baixa e constante (--music-vol ~0,11; -20 LUFS antes). Quando: do começo ao fim, sob a fala. Não usa: nunca por cima de trecho sem fala sozinha e nunca a mesma do vídeo anterior do cliente. Troca: 1 faixa por vídeo.

**Efeitos:** click. Momentos: só o click por palavra no card claro; whoosh só se o cliente pedir (Cliente3). Volume: 0,10-0,18. Não usa: sem whoosh nem boom de transição, salvo regra do cliente.

**Cena de apoio:** b-roll de filme ou notícia real; fontes: acervo, youtube, pexels; 2-4 s; 1 a cada 6-7 s; não usa: no gancho e no CTA. Prévia: folha com 3 opções por cena antes do render.
