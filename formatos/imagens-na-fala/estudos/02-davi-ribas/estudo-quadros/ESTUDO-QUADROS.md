# Estudo quadro a quadro: exemplo-2

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

1 vídeo(s) · 2026-11-05 · prova = `<vídeo> q<quadro>` (quadro a 60 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 9,95 s na mediana (média 21,94 s; 3 planos por minuto). Imagem nova a cada ~9,9 s. Prova: exemplo-2 q12395-q12984 (206,58 s, 9,83 s).
2. **Tipo de transição.** 0% das trocas são dissolve; o resto é corte seco. Especiais: 0 em 9 trocas (0,0 por vídeo). Prova: exemplo-2 q604-q604 (corte, 10,07 s).
3. **Câmera nunca para.** Câmera andando em 69% dos quadros; creep típico de 1,7% da largura por segundo; nos 10 primeiros quadros do plano ela anda 1,8× o resto (impulso na entrada). Maior trecho parado: 67 quadros. Prova: exemplo-2 q7645 (127,42 s).
4. **Ritmo da fala.** 198 palavras por minuto, voz em 79% do tempo; pausa depois de frase de 0,13 s na mediana (máx 0,34 s). Prova: exemplo-2 pausa típica no fim de frase em q2374 (39,57 s).
5. **Troca de plano presa à palavra.** A troca de plano começa 9 quadro(s) ANTES do começo da palavra mais perto (mediana): imagem nova entra junto com a palavra nova. Prova: exemplo-2 troca q604.
6. **Ação antes da palavra.** O movimento dentro do quadro (gesto, troca de rosto, objeto) acontece 3 quadros ANTES da palavra seguinte (mediana; picos de movimento sem a câmera, acima do acaso em 1 de 1 vídeos). Prova: exemplo-2 pico q6083 → palavra q6083.
7. **A imagem é o que a fala diz, no quadro da palavra.** 66% das orações trazem imagem nova (troca de plano em 1%, o resto é ação/objeto dentro do plano); a imagem muda 2 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: exemplo-2 'É só digitar ED11 aqui embaixo e acessar' troca q12985 → palavra q12997.
8. **Fato vira objeto.** 1,1 números falados por minuto; 25% deles têm um evento visível (objeto que aparece, rola, acende ou plano novo) a ±0,3 s da palavra, em média 7 quadros da palavra. Prova: exemplo-2 'ED11' palavra q12058, evento q12065.
9. **Som medido.** Volume integrado -14,2 LUFS. Música (medida nas pausas da fala) 19 dB abaixo da voz. Picos de efeito: ~37 por minuto (estimativa: conferir no ouvido). Prova: exemplo-2 (áudio inteiro).
10. **Legenda.** Legenda com o centro a 18% da altura, letra de ~80 px numa tela de 1920, ~2 palavras por vez. Prova: exemplo-2 q6581 (109,68 s).
11. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 41,3 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: exemplo-2 (41,3). Prova: exemplo-2 q0 × q13162.
12. **Gancho.** A 1ª troca de imagem vem em 10,07 s na mediana; a primeira palavra em 0,04 s. Prova: exemplo-2 q604.

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 9,95 | 9,95 a 9,95 | s |
| Plano: média | 21,94 | 21,94 a 21,94 | s |
| Planos por minuto | 2,7 | 2,7 a 2,7 | /min |
| Transição dissolve | 0 | 0 a 0 | % das trocas |
| Câmera andando | 69 | 69 a 69 | % dos quadros |
| Creep típico | 1,73 | 1,73 a 1,73 | % da largura/s |
| Entrada do plano × resto | 1,79 | 1,79 a 1,79 | × |
| Maior trecho parado | 67 | 67 a 67 | quadros |
| Fala | 198 | 198 a 198 | palavras/min |
| Voz no tempo | 79 | 79 a 79 | % |
| Pausa pós-frase: mediana | 0,13 | 0,13 a 0,13 | s |
| Pausa pós-frase: máx | 0,34 | 0,34 a 0,34 | s |
| Troca de plano × palavra | 9,0 | 9,0 a 9,0 | quadros |
| Ação antes da palavra | 3,0 | 3,0 a 3,0 | quadros |
| Oração com imagem nova | 66 | 66 a 66 | % das orações |
| Oração com troca de plano | 1 | 1 a 1 | % das orações |
| Imagem muda antes da palavra | 2,0 | 2,0 a 2,0 | quadros |
| Números falados | 1,1 | 1,1 a 1,1 | /min |
| Número com evento visual | 25 | 25 a 25 | % |
| Volume (LUFS integrado) | -14,2 | -14,2 a -14,2 | LUFS |
| Música abaixo da voz | 18,8 | 18,8 a 18,8 | dB |
| Efeitos (estimativa) | 36,6 | 36,6 a 36,6 | /min |
| Legenda: altura do centro | 18 | 18 a 18 | % da altura |
| Legenda: altura do texto | 80 | 80 a 80 | px em 1920 |
| Legenda: palavras na tela | 2,0 | 2,0 a 2,0 | palavras |

## Base sugerida pro formato

**gravado** (pessoa gravada: rosto de gente em 88% dos quadros (ruído de câmera 5,0)). Regra: animação sem pessoa estilo cartoon → sem base pronta (o Desenho 3D saiu do catálogo); animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| exemplo-2 | 219,4 s | 10 | 9,95 s | 0 (? q) | 69% | 198 | -14,2 | pessoa gravada |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| exemplo-2 | 89 | 66% | 1% | 2 q |

## Folhas

- exemplo-2: `folhas/exemplo-2-geral.jpg`, `folhas/exemplo-2-01-numero-q952.jpg`, `folhas/exemplo-2-02-numero-q7369.jpg`, `folhas/exemplo-2-03-numero-q12058.jpg`, `folhas/exemplo-2-04-numero-q13033.jpg`, `folhas/exemplo-2-05-transicao-q604.jpg` (+16)
