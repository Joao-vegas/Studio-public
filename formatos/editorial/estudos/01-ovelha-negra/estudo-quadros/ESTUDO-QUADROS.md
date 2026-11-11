# Estudo quadro a quadro: De2EsGkNuMZ

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

1 vídeo(s) · 2026-10-29 · prova = `<vídeo> q<quadro>` (quadro a 25 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 0,52 s na mediana (média 1,08 s; 56 planos por minuto). Imagem nova a cada ~0,5 s. Prova: De2EsGkNuMZ q2591-q2603 (103,64 s, 0,52 s).
2. **Tipo de transição.** 2% das trocas são dissolve de 6 quadros; o resto é corte seco. Especiais: 11 em 134 trocas (11,0 por vídeo). Prova: De2EsGkNuMZ q2348-q2356 (dissolve, 93,92 s).
3. **Câmera nunca para.** Câmera andando em 97% dos quadros; creep típico de 13,6% da largura por segundo; nos 10 primeiros quadros do plano ela anda 1,3× o resto (impulso na entrada). Maior trecho parado: 13 quadros. Prova: De2EsGkNuMZ q2266 (90,64 s).
4. **Ritmo da fala.** 185 palavras por minuto, voz em 72% do tempo; pausa depois de frase de 0,20 s na mediana (máx 0,70 s). Prova: De2EsGkNuMZ pausa típica no fim de frase em q542 (21,68 s).
5. **Troca de plano presa à palavra.** A troca de plano começa junto do começo da palavra mais perto (±1 quadro, mediana): imagem nova entra junto com a palavra nova. Prova: De2EsGkNuMZ troca q86.
6. **Ação × palavra.** Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica). Prova: De2EsGkNuMZ pico q101 → palavra q110.
7. **A imagem é o que a fala diz, no quadro da palavra.** 85% das orações trazem imagem nova (troca de plano em 44%, o resto é ação/objeto dentro do plano); a imagem muda 1 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: De2EsGkNuMZ 'Bora Lula!' troca q328 → palavra q340.
8. **Som medido.** Volume integrado -14,1 LUFS. Música (medida nas pausas da fala) 13 dB abaixo da voz. Picos de efeito: ~26 por minuto (estimativa: conferir no ouvido). Prova: De2EsGkNuMZ (áudio inteiro).
9. **Legenda.** Legenda com o centro a 62% da altura, letra de ~39 px numa tela de 1920, ~4 palavras por vez. Prova: De2EsGkNuMZ q1599 (63,96 s).
10. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 97,6 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: De2EsGkNuMZ (97,6). Prova: De2EsGkNuMZ q0 × q3634.
11. **Gancho.** A 1ª troca de imagem vem em 3,44 s na mediana; a primeira palavra em 0,00 s. Prova: De2EsGkNuMZ q86.

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 0,52 | 0,52 a 0,52 | s |
| Plano: média | 1,08 | 1,08 a 1,08 | s |
| Planos por minuto | 55,7 | 55,7 a 55,7 | /min |
| Transição dissolve | 2 | 2 a 2 | % das trocas |
| Dissolve: quadros | 5,5 | 5,5 a 5,5 | quadros |
| Câmera andando | 97 | 97 a 97 | % dos quadros |
| Creep típico | 13,61 | 13,61 a 13,61 | % da largura/s |
| Entrada do plano × resto | 1,28 | 1,28 a 1,28 | × |
| Maior trecho parado | 13 | 13 a 13 | quadros |
| Fala | 185 | 185 a 185 | palavras/min |
| Voz no tempo | 72 | 72 a 72 | % |
| Pausa pós-frase: mediana | 0,20 | 0,20 a 0,20 | s |
| Pausa pós-frase: máx | 0,70 | 0,70 a 0,70 | s |
| Troca de plano × palavra | 0,0 | 0,0 a 0,0 | quadros |
| Ação antes da palavra | 0,0 | 0,0 a 0,0 | quadros |
| Oração com imagem nova | 85 | 85 a 85 | % das orações |
| Oração com troca de plano | 44 | 44 a 44 | % das orações |
| Imagem muda antes da palavra | 1,0 | 1,0 a 1,0 | quadros |
| Números falados | 0,0 | 0,0 a 0,0 | /min |
| Volume (LUFS integrado) | -14,1 | -14,1 a -14,1 | LUFS |
| Música abaixo da voz | 13,4 | 13,4 a 13,4 | dB |
| Efeitos (estimativa) | 26,0 | 26,0 a 26,0 | /min |
| Legenda: altura do centro | 62 | 62 a 62 | % da altura |
| Legenda: altura do texto | 39 | 39 a 39 | px em 1920 |
| Legenda: palavras na tela | 4,0 | 4,0 a 4,0 | palavras |

## Base sugerida pro formato

**formatos/desenho-3d/base** (animação cartoon: áreas chapadas de cor (lisura 0,50) com cor moderada (63): desenho). Regra: animação sem pessoa estilo cartoon → `formatos/desenho-3d/base`; animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| De2EsGkNuMZ | 145,4 s | 135 | 0,52 s | 2 (6 q) | 97% | 185 | -14,1 | animação cartoon |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| De2EsGkNuMZ | 73 | 85% | 44% | 1 q |

## Folhas

- De2EsGkNuMZ: `folhas/De2EsGkNuMZ-geral.jpg`, `folhas/De2EsGkNuMZ-01-transicao-q86.jpg`, `folhas/De2EsGkNuMZ-02-transicao-q196.jpg`, `folhas/De2EsGkNuMZ-03-transicao-q970.jpg`, `folhas/De2EsGkNuMZ-04-transicao-q1096.jpg`, `folhas/De2EsGkNuMZ-05-transicao-q2457.jpg` (+22)
