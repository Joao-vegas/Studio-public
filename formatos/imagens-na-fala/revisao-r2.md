# Revisão r2: Imagens na fala

Revisor: Opus, 05-nov-2026. Material: `exemplo-teste-r2.mp4` (25,9 s), `comparacao-r2.jpg`, 6 quadros da r2 e 6 de `DecxbwzBRru.mp4` extraídos com ffmpeg, `_sandbox-teste-r2/qa/medidas.json`, `PLANO.json`, `revisao-r1.md`, `COMO-FAZER.md`, `aprendizado/regras.json`.
Executor da r3: Sonnet. Não gastar nada pago, não publicar, não commitar, não mexer em outros formatos.

## Veredito de diretor de arte

**Semelhança com a referência: 6 de 10** (r1 foi 4).

A estrutura agora é a da referência: colagem de 3 cartões em volta da pessoa, título amarelo fixo, legenda sob o queixo, corte seco, 3 na tela em 85% do tempo. Quem olha de relance já reconhece o formato.

O que ainda separa as duas é a **imagem** e o **ritmo da troca**. Na referência os cartões são pinturas em cor, de massa simples, que se leem no celular e se renovam um de cada vez. Na r2 são 14 gravuras bege, cheias de detalhe e às vezes com texto, que trocam sempre em trio. Parece um carrossel de páginas de livro antigo, não uma colagem viva.

## O que melhorou (r1 para r2)

| Ponto | r1 | r2 | Referência |
|---|---|---|---|
| Rosto (largura) | 48,6% | 39% (421 px) | 39% |
| Topo do rosto | 31,6% | 23,5% | 23% |
| Cartões por minuto | 19,1 | 32,5 | 30 |
| Média na tela | 1,38 | 2,75 | 2,77 |
| 3 na tela | 0% | 85,4% | 82% |
| 3 cartões até | 3,08 s | 0,53 s | 0,57 s |
| Cartão em pé, largura | 299 a 368 px, 1 deitado | 400 e 454 px, 1,10 a 1,53 | 370 a 500 px |
| Legenda 1ª linha | 64% | 55,8% | 55,8% |
| Pausa máxima | 0,74 s | 0,2 s | 0,3 s |
| Conferência com régua do formato | não | sim | |

Título, legenda, posições e corte seco: não mexer.

## Lacunas novas que a r2 revelou

1. **A curadoria foi corrigida na direção errada.** A r1 disse que a referência era "majoritariamente gravura em papel claro". Medindo os cartões da referência (recorte A, B, C em 6 quadros, HSV e luminância em 200 px de largura): saturação mediana ~80 de 255, luminância mediana ~100, densidade de borda mediana ~19. Na r2: saturação ~37, luminância ~170, borda ~44. A referência é maioria **pintura em cor, de meio-tom a escura, com poucas massas grandes** (cachorro, lobo, campo, silhueta laranja, mar). Gravura entra como contraste, não como regra.
2. **Imagem ilegível no celular.** Plateia (borda 67), Sísifo (77), Melencolia, alquimista e escriba são cenas lotadas de traço fino. A 400 px viram textura cinza. Na referência cada cartão tem 1 sujeito que se lê em meio segundo.
3. **Texto dentro da imagem.** Ourives (cartão comercial "STEWART Working Goldsmith"), relojoeiro ("S.W. BENEDICT"), escriba (página impressa em gótico) e o charlatão 01 (bloco de verso embaixo) trazem letra. Disputa com a legenda e fere a regra "sem legenda no quadro".
4. **Troca sempre em trio.** Em `medidas.json`, nas 5 viradas os 3 cartões saem juntos (4,64 · 4,64 · 4,64; 18,27 · 18,27 · 18,27; 11,67 a 12,22). Na prática são 5 limpezas de tela. Na referência cada posição tem seu tempo: a silhueta laranja fica de 16 a 24 s enquanto A e B trocam, a pedra com o lobo fica de 31 a 38 s. Só 3 vezes tudo sai junto.
5. **Metáfora erudita demais.** Argos, Cassandra e Melencolia pedem repertório pra decodificar. Na referência a imagem casa com o substantivo dito ("cachorro que quer virar lobo" entra com cachorro e lobos). O fio do charlatão funciona; os outros não se ligam à fala sem explicação.
6. **Fundo da redução.** O zoom de 0,80 deixa uma faixa borrada e escura na coluna da esquerda e no terço de baixo. Atrás do cartão A aparece borrão, onde a referência tem sala com quadro e planta. Só gravação nova resolve de vez.

Não é lacuna: viradas por segundo. 5 em 26 s (1 a cada 5,2 s) é o mesmo ritmo de 10 em 49 s (1 a cada 4,9 s). A frase "5 contra 10" do `COMO-FAZER.md` compara totais, não ritmo.

## Plano de correção da r3 (ordem de impacto)

### Motor e imagens (dá pra fazer agora, sem João)

**1. Recalibrar a paleta das imagens pela medida, não pelo olho.**
- Correção: rodar `medir_cartoes.py` (ou o recorte por posição) em todos os 25 cartões da referência e gravar saturação, luminância e borda de cada um em `estudos/01-hedonismo-decx/`. Trocar a regra "2/3 em gravura" (`COMO-FAZER.md` passo 3, `regras.json` › `curadoria-gravura`, checagem da conferência) pela faixa medida. Gravura entra no máximo em 1/3.
- Critério: nos 14 a 16 cartões da r3, saturação mediana ≥ 60, luminância mediana entre 80 e 130, pelo menos metade com saturação ≥ 60; cada rajada com pelo menos 1 cartão escuro (lum < 90) e 1 claro (lum > 140). Gravar os 3 números por imagem em `imagens/origem.json`.

**2. Imagem que se lê a 400 px: um sujeito, nenhuma letra.**
- Correção: no passo 3, descartar opção com densidade de borda alta ou com texto. Checagem de texto pode ser OCR grátis (tesseract, se instalado) ou recorte manual da faixa com letra; se não der pra recortar, troca a imagem.
- Critério: borda média (FIND_EDGES em 200 px de largura) ≤ 30 em todos os cartões; zero palavras legíveis no cartão já recortado; sujeito principal ocupando ≥ 35% da área do cartão (anotar `sujeito_pct` no `origem.json`). Ourives, relojoeiro, escriba, plateia e Sísifo saem.

**3. Cada posição com seu tempo (fim da troca em trio).**
- Correção: em `planejar.py`, numa virada trocar 1 ou 2 posições, não as 3; a posição que não troca segura o cartão até a virada seguinte (até 11,4 s). `limpa` só nas 3 viradas mais fortes. No `resolver_tempos`, saída "até o próximo da mesma posição menos 0,35 s" já existe; o problema é o PLANO pôr 3 por virada sempre.
- Critério em `qa/medidas.json` (campo novo `saidas_juntas`: instantes em que 2 ou mais cartões saem no mesmo quadro): no máximo 2 em 26 s (proporcional a 3 em 49 s). Pelo menos 30% dos cartões atravessam uma virada. Intervalo mediano entre entradas consecutivas (de qualquer posição) entre 1,5 e 2,5 s. Manter média na tela ≥ 2,6 e 3 na tela ≥ 75%.

**4. Imagem casada com a palavra dita.**
- Correção: no `IDEIAS.json`, cada cartão nomeia o substantivo concreto da oração que ilustra (vendedor, plateia, vitrine, cliente, dinheiro, preço), em vez de figura mitológica. Metáfora erudita só se a fala a nomear. O fio visual (charlatão) continua em 3 cartões.
- Critério: em ≥ 80% dos cartões, o campo `palavra` do PLANO aparece em `words-saida.json` entre o `t` do cartão e 2,5 s depois; `casar` ≥ 0,25 (ou a nota de corte que o `casar_imagem.py` usar) em 100%; teste do relance: mostrar 3 cartões ao João sem a fala e ele diz do que é o vídeo.

**5. Conferência que reprova a r2 nos pontos novos.**
- Correção: em `conferir_video.py › checar_cartoes`, acrescentar: saturação mediana < 60, borda média > 30 em algum cartão, `saidas_juntas` acima do teto do item 3, cartão sem `palavra` casada. Só quando existir `qa/medidas.json` com `media_na_tela` (outros formatos não mudam).
- Critério: rodar na r2 dá REPROVADO com os motivos de paleta, borda e saídas juntas; a r3 dá OK.

**6. Fundo da redução menos chapado (paliativo até gravar de novo).**
- Correção: no `compor_reduzido`, sigma 40 para 24 e brilho de 0,55 para 0,75, pra o borrão ler como desfoque de lente e não como faixa escura. Se o bruto tiver zoom ≥ 0,9, não reduzir.
- Critério: desvio padrão da luminância na coluna da esquerda (x < 44%, y 25 a 50%) ≥ 30 (r2 está perto de 13 a 26, referência 42 a 69); emenda invisível na `storyboard.jpg` aprovada pelo João.

**7. Sobreposição quadro a quadro, não só na média.**
- Correção: quando o João se inclina pra câmera (r2 em 0,5 s e 1,9 s) o rosto cresce e chega a encostar no cartão A. Rodar a detecção de rosto a cada 0,5 s no vídeo final.
- Critério: em 100% das amostras, distância entre caixa do rosto e qualquer cartão ≥ 2,5% da largura; registrar `rosto_p95_w` em `medidas.json` (≤ 46%).

**8. Atualizar receita e regras com o que foi medido.**
- Correção: `COMO-FAZER.md` (tabela de medidas ganha a linha "Paleta dos cartões" com os números do item 1; passo 3 reescrito; "Estado da receita" com números da r3), `regras.json` (`curadoria-gravura` vira `curadoria-paleta`; `rajada-por-ideia` ganha "cada posição com seu tempo"). Corrigir a frase "5 viradas contra 10" para ritmo por segundo.
- Critério: `grep` de "saturação", `saidas_juntas` e "palavra" bate nos 3 arquivos e no código; nenhuma regra sem origem (referência, histórico ou João).

### Depende de gravação nova do João

| O que | Por quê | Medida alvo |
|---|---|---|
| Roupa escura, lisa | Legenda está sobre luminância 200; referência 37 a 77. O contorno de 5 px segura, mas pesa | Luminância atrás da legenda ≤ 90; aí volta contorno 3 px |
| Câmera mais longe (plano médio, peito e cintura) | Evita o zoom de 0,80 e o fundo borrado | Rosto entre 38 e 42% da largura já no bruto, zoom 1,0 |
| Corpo à direita do quadro | Libera a coluna da esquerda sem esticar borda | Rosto começando em ~46% da largura no bruto |
| Fundo com textura (estante, quadro, planta, luz quente) | A estante atual some no borrão | Desvio do fundo 42 a 69 |
| Gestos no centro, sem se inclinar pra câmera | Inclinar cresce o rosto e invade o cartão A | `rosto_p95_w` ≤ 46% sem correção do motor |

Com o motor nos itens 1 a 5 a nota esperada é 7,5. Com a gravação nova, 8,5 a 9.
