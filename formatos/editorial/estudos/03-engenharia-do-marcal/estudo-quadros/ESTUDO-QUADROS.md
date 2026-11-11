# Estudo quadro a quadro: DcY0R--B25a

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

1 vídeo(s) · 2026-10-29 · prova = `<vídeo> q<quadro>` (quadro a 30 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 1,79 s na mediana (média 2,57 s; 23 planos por minuto). Imagem nova a cada ~1,8 s. Prova: DcY0R--B25a q1893-q1948 (63,10 s, 1,87 s).
2. **Tipo de transição.** 0% das trocas são dissolve; o resto é corte seco. Especiais: 9 em 67 trocas (9,0 por vídeo). Prova: DcY0R--B25a q215-q215 (corte, 7,17 s).
3. **Câmera nunca para.** Câmera andando em 95% dos quadros; creep típico de 5,4% da largura por segundo; nos 10 primeiros quadros do plano ela anda 2,3× o resto (impulso na entrada). Maior trecho parado: 23 quadros. Prova: DcY0R--B25a q4228 (140,93 s).
4. **Ritmo da fala.** 186 palavras por minuto, voz em 89% do tempo; pausa depois de frase de 0,11 s na mediana (máx 1,36 s). Prova: DcY0R--B25a pausa típica no fim de frase em q217 (7,23 s).
5. **Troca de plano presa à palavra.** A troca de plano começa 1 quadro(s) ANTES do começo da palavra mais perto (mediana): imagem nova entra junto com a palavra nova. Prova: DcY0R--B25a troca q215.
6. **Ação × palavra.** Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica). Prova: DcY0R--B25a pico q62 → palavra q60.
7. **A imagem é o que a fala diz, no quadro da palavra.** 85% das orações trazem imagem nova (troca de plano em 47%, o resto é ação/objeto dentro do plano); a imagem muda 0 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: DcY0R--B25a 'Você responde no seu primeiro segundo,' troca q233 → palavra q245.
8. **Fato vira objeto.** 3,1 números falados por minuto; 67% deles têm um evento visível (objeto que aparece, rola, acende ou plano novo) a ±0,3 s da palavra, em média -2 quadros da palavra. Prova: DcY0R--B25a 'Dois' palavra q559, evento q557.
9. **Som medido.** Volume integrado -14,2 LUFS. Música (medida nas pausas da fala) 18 dB abaixo da voz. Picos de efeito: ~29 por minuto (estimativa: conferir no ouvido). Prova: DcY0R--B25a (áudio inteiro).
10. **Legenda.** Legenda com o centro a 25% da altura, letra de ~26 px numa tela de 1920, ~3 palavras por vez. Prova: DcY0R--B25a q2310 (77,00 s).
11. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 98,6 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: DcY0R--B25a (98,6). Prova: DcY0R--B25a q0 × q5249.
12. **Gancho.** A 1ª troca de imagem vem em 7,17 s na mediana; a primeira palavra em 0,00 s. Prova: DcY0R--B25a q215.

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 1,79 | 1,79 a 1,79 | s |
| Plano: média | 2,57 | 2,57 a 2,57 | s |
| Planos por minuto | 23,3 | 23,3 a 23,3 | /min |
| Transição dissolve | 0 | 0 a 0 | % das trocas |
| Câmera andando | 95 | 95 a 95 | % dos quadros |
| Creep típico | 5,37 | 5,37 a 5,37 | % da largura/s |
| Entrada do plano × resto | 2,28 | 2,28 a 2,28 | × |
| Maior trecho parado | 23 | 23 a 23 | quadros |
| Fala | 186 | 186 a 186 | palavras/min |
| Voz no tempo | 89 | 89 a 89 | % |
| Pausa pós-frase: mediana | 0,11 | 0,11 a 0,11 | s |
| Pausa pós-frase: máx | 1,36 | 1,36 a 1,36 | s |
| Troca de plano × palavra | 1,0 | 1,0 a 1,0 | quadros |
| Ação antes da palavra | 0,0 | 0,0 a 0,0 | quadros |
| Oração com imagem nova | 85 | 85 a 85 | % das orações |
| Oração com troca de plano | 47 | 47 a 47 | % das orações |
| Imagem muda antes da palavra | 0,0 | 0,0 a 0,0 | quadros |
| Números falados | 3,1 | 3,1 a 3,1 | /min |
| Número com evento visual | 67 | 67 a 67 | % |
| Volume (LUFS integrado) | -14,2 | -14,2 a -14,2 | LUFS |
| Música abaixo da voz | 17,6 | 17,6 a 17,6 | dB |
| Efeitos (estimativa) | 28,8 | 28,8 a 28,8 | /min |
| Legenda: altura do centro | 25 | 25 a 25 | % da altura |
| Legenda: altura do texto | 26 | 26 a 26 | px em 1920 |
| Legenda: palavras na tela | 3,0 | 3,0 a 3,0 | palavras |

## Base sugerida pro formato

**gravado** (pessoa gravada: rosto de gente em 61% dos quadros (ruído de câmera 2,0)). Regra: animação sem pessoa estilo cartoon → `formatos/desenho-3d/base`; animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| DcY0R--B25a | 175,0 s | 68 | 1,79 s | 0 (? q) | 95% | 186 | -14,2 | pessoa gravada |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| DcY0R--B25a | 73 | 85% | 47% | 0 q |

## Folhas

- DcY0R--B25a: `folhas/DcY0R--B25a-geral.jpg`, `folhas/DcY0R--B25a-01-numero-q559.jpg`, `folhas/DcY0R--B25a-02-numero-q896.jpg`, `folhas/DcY0R--B25a-03-numero-q947.jpg`, `folhas/DcY0R--B25a-04-numero-q988.jpg`, `folhas/DcY0R--B25a-05-numero-q1030.jpg` (+29)
