# Como fazer: Chamada na tela

**Quando usar:** anúncio de fala de alguém olhando pra câmera, já cortado em gancho + corpo + CTA, que precisa
prender nos primeiros 0,8 s e não pode ficar parado, mas sem poluir a tela.
**Régua:** exemplo-1 (CONTRATO, item 6).
**Motor:** vídeo gravado, Python (OpenCV + PIL) quadro a quadro com pipe pro ffmpeg: `tela.py <config.json>` do
modelo do cliente; `lote.py` gera as configs de várias combinações e roda (3 de cada vez, trio por trio).
**Som:** cama musical baixa (~-31 LUFS antes do ducking, sidechain na voz, fade no fim), faixa diferente por vídeo.
Sem efeito sonoro. Voz pela regra G13 (cada trecho a -16 LUFS, final -14).

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar a entrada.** Vídeo em SDR 1080x1920, 30 fps (HLG do iPhone convertido com `scale_vt`, sem mexer na
   cor) e o `words.json` com `dur`, `pecas` (ini/fim de gancho, corpo e CTA) e `words` (w, s, e) no tempo do vídeo.
2. **Montar as cenas.** Config: `titulo` em 2 linhas (Bebas, neon, até 860 px; o assunto do gancho), `gancho`
   revezando bate → puxa → luz → sinal, `musica` + `musica_lufs`, `destaques`. Título no peito (y 1150) até o fim do
   gancho (3,2 a 7 s) e sai com falha de sinal; depois legenda de uma palavra (Poppins Bold 64, branca com sombra;
   número e destaque no neon). Motion pelos `GATILHOS`: palavra neon (1,6 s, empurrão de 6%), riscado (1,9 s) ou
   etiqueta laranja (2,6 s), no mínimo 3,5 s entre um e outro, no lugar da legenda.
3. **Storyboard (para pro João aprovar).** Folha de quadros do render (1 por segundo) ao lado da do exemplo; o 1º
   de cada lote para pro João.
4. **Vídeo.** `python3 <modelo>/tela.py <sandbox>/config.json` (lote: `python3 <modelo>/lote.py <números>`).
5. **Conferência.** Folha lado a lado com o exemplo; abertura em cor no t=0, título sem cobrir o rosto, legenda
   casando com a fala, motion na palavra certa, voz no mesmo volume nos trechos (G13). Pior que o exemplo não sai.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, titulo e texto). Correção do João vira regra pela REGRA Nº 2
do `CLAUDE.md`; regra nova só do exemplo, do `historico.jsonl` ou do que o João disse.

## Som e cena de apoio

**Música:** cama musical que acompanha o gancho do anúncio. Volume: baixa com ducking (LUFS no catalogo.json). Quando: do início ao fim, sob a fala. Não usa: nunca a mesma do vídeo anterior; sem música alta no gancho. Troca: 1 faixa por vídeo.

**Efeitos:** não usa (sempre).

**Cena de apoio:** motion limpo de vez em quando; fontes: motor; 1-2 s; pontual, nos títulos; não usa: no gancho e no CTA. Prévia: storyboard antes do render.
