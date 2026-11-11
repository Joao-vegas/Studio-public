# Estudo quadro a quadro: Loaded Dice (os 11 shorts de referência)

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

11 vídeo(s) · 2026-10-29 · prova = `<vídeo> q<quadro>` (quadro a 30 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 2,20 s na mediana (média 2,33 s; 26 planos por minuto). Imagem nova a cada ~2,2 s. Prova: KxEs8tTORWM q534-q599 (17,80 s, 2,20 s).
2. **Tipo de transição.** 7% das trocas são dissolve de 6 quadros; o resto é corte seco. Especiais: 54 em 322 trocas (4,9 por vídeo). Prova: GYO41yUtOUk q1024-q1028 (dissolve, 34,13 s).
3. **Câmera nunca para.** Câmera andando em 93% dos quadros; creep típico de 11,6% da largura por segundo; nos 10 primeiros quadros do plano ela anda 1,2× o resto (impulso na entrada). Maior trecho parado: 27 quadros. Prova: KxEs8tTORWM q1476 (49,20 s).
4. **Ritmo da fala.** 186 palavras por minuto, voz em 89% do tempo; pausa depois de frase de 0,11 s na mediana (máx 0,36 s). Prova: oMvgmMNB_Bg pausa típica no fim de frase em q328 (10,93 s).
5. **Troca de plano presa à palavra.** A troca de plano começa junto do começo da palavra mais perto (±1 quadro, mediana): imagem nova entra junto com a palavra nova. Prova: GYO41yUtOUk troca q65.
6. **Ação × palavra.** Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica). Prova: eXRvlY69aFg pico q151 → palavra q149.
7. **A imagem é o que a fala diz, no quadro da palavra.** 73% das orações trazem imagem nova (troca de plano em 42%, o resto é ação/objeto dentro do plano); a imagem muda 0 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: 6dr3xfgvJfQ 'Not only did they both own competing air' troca q132 → palavra q135.
8. **Conferido no olho: a tela mostra o que é dito.** 53 de 60 orações (88%) mostram literalmente o objeto, a ação, a pessoa ou o número da fala no quadro da palavra; 4 em parte e 3 não (o plano genérico de cenário é a exceção, não a regra). Cada oração ganha a imagem do que ela diz. Prova: `fala-imagem/KxEs8tTORWM.md`; `fala-imagem/eXRvlY69aFg.md`.
9. **Fato vira objeto.** 3,8 números falados por minuto; 57% deles têm um evento visível (objeto que aparece, rola, acende ou plano novo) a ±0,3 s da palavra, em média 1 quadros da palavra. Prova: AuX7znns3fs 'For $5,' palavra q77, evento q78.
10. **Som medido.** Volume integrado -13,7 LUFS. Música (medida nas pausas da fala) 10 dB abaixo da voz. Picos de efeito: ~31 por minuto (estimativa: conferir no ouvido). Prova: AuX7znns3fs (áudio inteiro).
11. **Legenda.** Legenda com o centro a 72% da altura, letra de ~44 px numa tela de 1920, ~2 palavras por vez. Prova: KxEs8tTORWM q1393 (46,43 s).
12. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 56,6 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: 6dr3xfgvJfQ (2,1). Prova: 6dr3xfgvJfQ q0 × q1728.
13. **Gancho.** A 1ª troca de imagem vem em 2,17 s na mediana; a primeira palavra em 0,00 s. Prova: AuX7znns3fs q78.

## Transições especiais e levantadinha

Catálogo medido quadro a quadro (tipo, quadros, direção, prova) e o pop de reação: `TRANSICOES-E-POP.md`. Resumo: especial ~5 por vídeo, quase todas chicote de câmera (10-15 q) ou objeto passando na frente (8-9 q); pop de reação = sobe ~20% do rosto em 3-4 q e volta, na 1ª palavra (KxEs8tTORWM q1657).

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 2,20 | 1,25 a 2,57 | s |
| Plano: média | 2,33 | 1,69 a 3,48 | s |
| Planos por minuto | 25,8 | 17,3 a 35,5 | /min |
| Transição dissolve | 7 | 0 a 18 | % das trocas |
| Dissolve: quadros | 5,5 | 4,0 a 10,0 | quadros |
| Câmera andando | 93 | 80 a 97 | % dos quadros |
| Creep típico | 11,56 | 3,38 a 22,41 | % da largura/s |
| Entrada do plano × resto | 1,20 | 0,68 a 2,65 | × |
| Maior trecho parado | 27 | 7 a 52 | quadros |
| Fala | 186 | 175 a 220 | palavras/min |
| Voz no tempo | 89 | 74 a 93 | % |
| Pausa pós-frase: mediana | 0,11 | 0,00 a 0,20 | s |
| Pausa pós-frase: máx | 0,36 | 0,08 a 0,76 | s |
| Troca de plano × palavra | 0,0 | -1,0 a 1,0 | quadros |
| Ação antes da palavra | -0,5 | -1,0 a 1,5 | quadros |
| Oração com imagem nova | 73 | 51 a 85 | % das orações |
| Oração com troca de plano | 42 | 17 a 60 | % das orações |
| Imagem muda antes da palavra | 0,0 | -4,0 a 3,0 | quadros |
| Números falados | 3,8 | 0,0 a 7,0 | /min |
| Número com evento visual | 57 | 0 a 100 | % |
| Volume (LUFS integrado) | -13,7 | -15,2 a -12,1 | LUFS |
| Música abaixo da voz | 10,3 | 6,2 a 12,5 | dB |
| Efeitos (estimativa) | 31,2 | 16,3 a 40,8 | /min |
| Legenda: altura do centro | 72 | 66 a 76 | % da altura |
| Legenda: altura do texto | 44 | 36 a 57 | px em 1920 |
| Legenda: palavras na tela | 2,0 | 2,0 a 3,0 | palavras |

## Base sugerida pro formato

**formatos/explicador-3d/base** (animação 3D realista: render 3D com textura e sombra (lisura 0,32, ruído 2,0, saturação 82): jogo antigo/realista). Regra: animação sem pessoa estilo cartoon → `formatos/desenho-3d/base`; animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| AuX7znns3fs | 89,7 s | 27 | 2,50 s | 2 (6 q) | 93% | 218 | -13,7 | animação 3D realista |
| oMvgmMNB_Bg | 57,7 s | 26 | 1,40 s | 1 (10 q) | 80% | 220 | -12,9 | animação 3D realista |
| GYO41yUtOUk | 55,6 s | 16 | 2,50 s | 1 (5 q) | 85% | 184 | -13,7 | animação 3D realista |
| w5YeTcV5daA | 68,3 s | 25 | 2,57 s | 2 (5 q) | 89% | 203 | -12,5 | animação 3D realista |
| Ptemtxmby14 | 44,2 s | 19 | 2,30 s | 1 (5 q) | 96% | 178 | -13,0 | animação 3D realista |
| eXRvlY69aFg | 90,5 s | 32 | 2,46 s | 1 (4 q) | 88% | 192 | -14,2 | animação 3D realista |
| KxEs8tTORWM | 89,3 s | 39 | 2,20 s | 7 (6 q) | 93% | 180 | -15,2 | animação 3D realista |
| OPY6loAW3iI | 95,8 s | 35 | 1,67 s | 2 (5 q) | 81% | 175 | -13,5 | animação 3D realista |
| kJBP2qr3SYU | 98,0 s | 58 | 1,25 s | 0 (? q) | 96% | 184 | -14,8 | animação 3D realista |
| 6dr3xfgvJfQ | 57,6 s | 26 | 1,58 s | 3 (8 q) | 97% | 202 | -12,1 | animação 3D realista |
| hPgvC2-Azr0 | 62,7 s | 30 | 1,51 s | 4 (10 q) | 94% | 186 | -14,6 | animação 3D realista |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| AuX7znns3fs | 39 | 51% | 26% | 2 q |
| oMvgmMNB_Bg | 24 | 79% | 33% | -1 q |
| GYO41yUtOUk | 23 | 52% | 17% | 0 q |
| w5YeTcV5daA | 26 | 85% | 42% | -2 q |
| Ptemtxmby14 | 20 | 80% | 60% | 2 q |
| eXRvlY69aFg | 31 | 74% | 42% | 0 q |
| KxEs8tTORWM | 40 | 68% | 48% | 1 q |
| OPY6loAW3iI | 42 | 57% | 40% | -0 q |
| kJBP2qr3SYU | 46 | 80% | 48% | 3 q |
| 6dr3xfgvJfQ | 26 | 73% | 35% | -4 q |
| hPgvC2-Azr0 | 24 | 71% | 54% | 3 q |

## Folhas

- AuX7znns3fs: `folhas/AuX7znns3fs-geral.jpg`, `folhas/AuX7znns3fs-01-numero-q77.jpg`, `folhas/AuX7znns3fs-02-numero-q1444.jpg`, `folhas/AuX7znns3fs-fala-imagem-1.jpg`, `folhas/AuX7znns3fs-fala-imagem-2.jpg`
- oMvgmMNB_Bg: `folhas/oMvgmMNB_Bg-geral.jpg`, `folhas/oMvgmMNB_Bg-01-numero-q578.jpg`, `folhas/oMvgmMNB_Bg-02-transicao-q508.jpg`, `folhas/oMvgmMNB_Bg-fala-imagem-1.jpg`
- GYO41yUtOUk: `folhas/GYO41yUtOUk-geral.jpg`, `folhas/GYO41yUtOUk-01-transicao-q666.jpg`, `folhas/GYO41yUtOUk-02-transicao-q1024.jpg`, `folhas/GYO41yUtOUk-fala-imagem-1.jpg`
- w5YeTcV5daA: `folhas/w5YeTcV5daA-geral.jpg`, `folhas/w5YeTcV5daA-01-numero-q712.jpg`, `folhas/w5YeTcV5daA-02-numero-q1517.jpg`, `folhas/w5YeTcV5daA-fala-imagem-1.jpg`
- Ptemtxmby14: `folhas/Ptemtxmby14-geral.jpg`, `folhas/Ptemtxmby14-01-numero-q567.jpg`, `folhas/Ptemtxmby14-02-numero-q629.jpg`, `folhas/Ptemtxmby14-fala-imagem-1.jpg`
- eXRvlY69aFg: `folhas/eXRvlY69aFg-geral.jpg`, `folhas/eXRvlY69aFg-01-numero-q50.jpg`, `folhas/eXRvlY69aFg-02-numero-q163.jpg`, `folhas/eXRvlY69aFg-fala-imagem-1.jpg`, `folhas/eXRvlY69aFg-fala-imagem-2.jpg`
- KxEs8tTORWM: `folhas/KxEs8tTORWM-geral.jpg`, `folhas/KxEs8tTORWM-01-numero-q1948.jpg`, `folhas/KxEs8tTORWM-02-transicao-q86.jpg`, `folhas/KxEs8tTORWM-fala-imagem-1.jpg`, `folhas/KxEs8tTORWM-fala-imagem-2.jpg`
- OPY6loAW3iI: `folhas/OPY6loAW3iI-geral.jpg`, `folhas/OPY6loAW3iI-01-numero-q14.jpg`, `folhas/OPY6loAW3iI-02-numero-q257.jpg`, `folhas/OPY6loAW3iI-fala-imagem-1.jpg`, `folhas/OPY6loAW3iI-fala-imagem-2.jpg`
- kJBP2qr3SYU: `folhas/kJBP2qr3SYU-geral.jpg`, `folhas/kJBP2qr3SYU-01-numero-q605.jpg`, `folhas/kJBP2qr3SYU-02-numero-q1402.jpg`, `folhas/kJBP2qr3SYU-fala-imagem-1.jpg`, `folhas/kJBP2qr3SYU-fala-imagem-2.jpg`
- 6dr3xfgvJfQ: `folhas/6dr3xfgvJfQ-geral.jpg`, `folhas/6dr3xfgvJfQ-01-numero-q3.jpg`, `folhas/6dr3xfgvJfQ-02-numero-q426.jpg`, `folhas/6dr3xfgvJfQ-fala-imagem-1.jpg`
- hPgvC2-Azr0: `folhas/hPgvC2-Azr0-geral.jpg`, `folhas/hPgvC2-Azr0-01-numero-q234.jpg`, `folhas/hPgvC2-Azr0-02-numero-q347.jpg`, `folhas/hPgvC2-Azr0-fala-imagem-1.jpg`
