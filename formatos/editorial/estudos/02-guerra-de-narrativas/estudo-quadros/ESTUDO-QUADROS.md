# Estudo quadro a quadro: DeS7yVRNyuG

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

1 vídeo(s) · 2026-10-29 · prova = `<vídeo> q<quadro>` (quadro a 30 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 1,52 s na mediana (média 1,87 s; 32 planos por minuto). Imagem nova a cada ~1,5 s. Prova: DeS7yVRNyuG q4091-q4136 (136,37 s, 1,53 s).
2. **Tipo de transição.** 2% das trocas são dissolve de 8 quadros; o resto é corte seco. Especiais: 3 em 99 trocas (3,0 por vídeo). Prova: DeS7yVRNyuG q5307-q5318 (dissolve, 176,90 s).
3. **Câmera nunca para.** Câmera andando em 92% dos quadros; creep típico de 13,6% da largura por segundo; nos 10 primeiros quadros do plano ela anda 4,0× o resto (impulso na entrada). Maior trecho parado: 57 quadros. Prova: DeS7yVRNyuG q421 (14,03 s).
4. **Ritmo da fala.** 197 palavras por minuto, voz em 89% do tempo; pausa depois de frase de 0,00 s na mediana (máx 0,30 s). Prova: DeS7yVRNyuG pausa típica no fim de frase em q617 (20,57 s).
5. **Troca de plano presa à palavra.** A troca de plano começa 1 quadro(s) ANTES do começo da palavra mais perto (mediana): imagem nova entra junto com a palavra nova. Prova: DeS7yVRNyuG troca q21.
6. **Ação × palavra.** Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica). Prova: DeS7yVRNyuG pico q29 → palavra q31.
7. **A imagem é o que a fala diz, no quadro da palavra.** 72% das orações trazem imagem nova (troca de plano em 51%, o resto é ação/objeto dentro do plano); a imagem muda 1 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: DeS7yVRNyuG 'E quem vai decidir essa eleição não é pr' troca q56 → palavra q65.
8. **Fato vira objeto.** 5,1 números falados por minuto; 56% deles têm um evento visível (objeto que aparece, rola, acende ou plano novo) a ±0,3 s da palavra, em média -6 quadros da palavra. Prova: DeS7yVRNyuG '2002.' palavra q730, evento q722.
9. **Som medido.** Volume integrado -14,6 LUFS. Música (medida nas pausas da fala) 10 dB abaixo da voz. Picos de efeito: ~40 por minuto (estimativa: conferir no ouvido). Prova: DeS7yVRNyuG (áudio inteiro).
10. **Legenda.** Legenda com o centro a 44% da altura, letra de ~41 px numa tela de 1920, ~2 palavras por vez. Prova: DeS7yVRNyuG q2693 (89,77 s).
11. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 136,9 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: DeS7yVRNyuG (136,9). Prova: DeS7yVRNyuG q0 × q5610.
12. **Gancho.** A 1ª troca de imagem vem em 0,70 s na mediana; a primeira palavra em 0,00 s. Prova: DeS7yVRNyuG q21.

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 1,52 | 1,52 a 1,52 | s |
| Plano: média | 1,87 | 1,87 a 1,87 | s |
| Planos por minuto | 32,1 | 32,1 a 32,1 | /min |
| Transição dissolve | 2 | 2 a 2 | % das trocas |
| Dissolve: quadros | 8,5 | 8,5 a 8,5 | quadros |
| Câmera andando | 92 | 92 a 92 | % dos quadros |
| Creep típico | 13,55 | 13,55 a 13,55 | % da largura/s |
| Entrada do plano × resto | 4,05 | 4,05 a 4,05 | × |
| Maior trecho parado | 57 | 57 a 57 | quadros |
| Fala | 197 | 197 a 197 | palavras/min |
| Voz no tempo | 89 | 89 a 89 | % |
| Pausa pós-frase: mediana | 0,00 | 0,00 a 0,00 | s |
| Pausa pós-frase: máx | 0,30 | 0,30 a 0,30 | s |
| Troca de plano × palavra | 1,0 | 1,0 a 1,0 | quadros |
| Ação antes da palavra | 0,0 | 0,0 a 0,0 | quadros |
| Oração com imagem nova | 72 | 72 a 72 | % das orações |
| Oração com troca de plano | 51 | 51 a 51 | % das orações |
| Imagem muda antes da palavra | 1,0 | 1,0 a 1,0 | quadros |
| Números falados | 5,1 | 5,1 a 5,1 | /min |
| Número com evento visual | 56 | 56 a 56 | % |
| Volume (LUFS integrado) | -14,6 | -14,6 a -14,6 | LUFS |
| Música abaixo da voz | 10,1 | 10,1 a 10,1 | dB |
| Efeitos (estimativa) | 40,4 | 40,4 a 40,4 | /min |
| Legenda: altura do centro | 44 | 44 a 44 | % da altura |
| Legenda: altura do texto | 41 | 41 a 41 | px em 1920 |
| Legenda: palavras na tela | 2,0 | 2,0 a 2,0 | palavras |

## Base sugerida pro formato

**formatos/explicador-3d/base** (animação 3D realista: render 3D com textura e sombra (lisura 0,28, ruído 3,0, saturação 60): jogo antigo/realista). Regra: animação sem pessoa estilo cartoon → `formatos/desenho-3d/base`; animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| DeS7yVRNyuG | 187,0 s | 100 | 1,52 s | 2 (8 q) | 92% | 197 | -14,6 | animação 3D realista |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| DeS7yVRNyuG | 96 | 72% | 51% | 1 q |

## Folhas

- DeS7yVRNyuG: `folhas/DeS7yVRNyuG-geral.jpg`, `folhas/DeS7yVRNyuG-01-numero-q730.jpg`, `folhas/DeS7yVRNyuG-02-numero-q779.jpg`, `folhas/DeS7yVRNyuG-03-numero-q1660.jpg`, `folhas/DeS7yVRNyuG-04-numero-q2044.jpg`, `folhas/DeS7yVRNyuG-05-numero-q2231.jpg` (+28)
