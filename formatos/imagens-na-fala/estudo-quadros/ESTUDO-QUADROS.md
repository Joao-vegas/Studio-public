# Estudo quadro a quadro: DecxbwzBRru

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

1 vídeo(s) · 2026-11-05 · prova = `<vídeo> q<quadro>` (quadro a 30 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 6,13 s na mediana (média 7,06 s; 8 planos por minuto). Imagem nova a cada ~6,1 s. Prova: DecxbwzBRru q1062-q1245 (35,40 s, 6,13 s).
2. **Tipo de transição.** 0% das trocas são dissolve; o resto é corte seco. Especiais: 0 em 6 trocas (0,0 por vídeo). Prova: DecxbwzBRru q270-q270 (corte, 9,00 s).
3. **Câmera nunca para.** Câmera andando em 90% dos quadros; creep típico de 0,9% da largura por segundo; nos 10 primeiros quadros do plano ela anda 1,8× o resto (impulso na entrada). Maior trecho parado: 8 quadros. Prova: DecxbwzBRru q760 (25,33 s).
4. **Ritmo da fala.** 198 palavras por minuto, voz em 79% do tempo; pausa depois de frase de 0,20 s na mediana (máx 0,30 s). Prova: DecxbwzBRru pausa típica no fim de frase em q374 (12,47 s).
5. **Troca de plano presa à palavra.** A troca de plano começa junto do começo da palavra mais perto (±1 quadro, mediana): imagem nova entra junto com a palavra nova. Prova: DecxbwzBRru troca q270.
6. **Ação × palavra.** Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica). Prova: DecxbwzBRru pico q3 → palavra q0.
7. **A imagem é o que a fala diz, no quadro da palavra.** 100% das orações trazem imagem nova (troca de plano em 12%, o resto é ação/objeto dentro do plano); a imagem muda 1 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: DecxbwzBRru 'O que você consome todo dia define o tam' troca q270 → palavra q272.
8. **Som medido.** Volume integrado -14,1 LUFS. Música (medida nas pausas da fala) 15 dB abaixo da voz. Picos de efeito: ~11 por minuto (estimativa: conferir no ouvido). Prova: DecxbwzBRru (áudio inteiro).
9. **Legenda.** Legenda com o centro a 57% da altura, letra de ~43 px numa tela de 1920, ~2 palavras por vez. Prova: DecxbwzBRru q750 (25,00 s).
10. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 43,3 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: DecxbwzBRru (43,3). Prova: DecxbwzBRru q0 × q1481.
11. **Gancho.** A 1ª troca de imagem vem em 9,00 s na mediana; a primeira palavra em 0,00 s. Prova: DecxbwzBRru q270.

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 6,13 | 6,13 a 6,13 | s |
| Plano: média | 7,06 | 7,06 a 7,06 | s |
| Planos por minuto | 8,5 | 8,5 a 8,5 | /min |
| Transição dissolve | 0 | 0 a 0 | % das trocas |
| Câmera andando | 90 | 90 a 90 | % dos quadros |
| Creep típico | 0,90 | 0,90 a 0,90 | % da largura/s |
| Entrada do plano × resto | 1,80 | 1,80 a 1,80 | × |
| Maior trecho parado | 8 | 8 a 8 | quadros |
| Fala | 198 | 198 a 198 | palavras/min |
| Voz no tempo | 79 | 79 a 79 | % |
| Pausa pós-frase: mediana | 0,20 | 0,20 a 0,20 | s |
| Pausa pós-frase: máx | 0,30 | 0,30 a 0,30 | s |
| Troca de plano × palavra | 0,5 | 0,5 a 0,5 | quadros |
| Ação antes da palavra | 0,5 | 0,5 a 0,5 | quadros |
| Oração com imagem nova | 100 | 100 a 100 | % das orações |
| Oração com troca de plano | 12 | 12 a 12 | % das orações |
| Imagem muda antes da palavra | 1,0 | 1,0 a 1,0 | quadros |
| Números falados | 0,0 | 0,0 a 0,0 | /min |
| Volume (LUFS integrado) | -14,1 | -14,1 a -14,1 | LUFS |
| Música abaixo da voz | 15,3 | 15,3 a 15,3 | dB |
| Efeitos (estimativa) | 10,9 | 10,9 a 10,9 | /min |
| Legenda: altura do centro | 57 | 57 a 57 | % da altura |
| Legenda: altura do texto | 43 | 43 a 43 | px em 1920 |
| Legenda: palavras na tela | 2,0 | 2,0 a 2,0 | palavras |

## Base sugerida pro formato

**gravado** (pessoa gravada: rosto de gente em 100% dos quadros (ruído de câmera 9,0)). Regra: animação sem pessoa estilo cartoon → sem base pronta (o Desenho 3D saiu do catálogo); animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| DecxbwzBRru | 49,4 s | 7 | 6,13 s | 0 (? q) | 90% | 198 | -14,1 | pessoa gravada |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| DecxbwzBRru | 16 | 100% | 12% | 1 q |

## Folhas

- DecxbwzBRru: `folhas/DecxbwzBRru-geral.jpg`, `folhas/DecxbwzBRru-01-transicao-q270.jpg`, `folhas/DecxbwzBRru-02-transicao-q273.jpg`, `folhas/DecxbwzBRru-03-transicao-q889.jpg`, `folhas/DecxbwzBRru-04-transicao-q894.jpg`, `folhas/DecxbwzBRru-05-transicao-q1062.jpg` (+7)
