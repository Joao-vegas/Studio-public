# Estudo quadro a quadro: Dafd6TnOlOI

> Medido sozinho por `app/ferramentas/estudo_quadros.py` (OpenCV + ffmpeg + tesseract; fala pelo Groq). Isto é ESTILO e
> régua: os números dizem COMO o vídeo é feito. Roteiro, falas, pessoas, rostos, marcas e textos da tela NÃO vêm daqui.

1 vídeo(s) · 2026-10-29 · prova = `<vídeo> q<quadro>` (quadro a 30 fps; folhas em `folhas/`)

## Regras com número (siga os números)

1. **Duração do plano.** Plano de 0,83 s na mediana (média 1,61 s; 37 planos por minuto). Imagem nova a cada ~0,8 s. Prova: Dafd6TnOlOI q2937-q2960 (97,90 s, 0,80 s).
2. **Tipo de transição.** 1% das trocas são dissolve de 2 quadros; o resto é corte seco. Especiais: 6 em 87 trocas (6,0 por vídeo). Prova: Dafd6TnOlOI q453-q454 (dissolve, 15,10 s).
3. **Câmera nunca para.** Câmera andando em 92% dos quadros; creep típico de 7,8% da largura por segundo; nos 10 primeiros quadros do plano ela anda 1,5× o resto (impulso na entrada). Maior trecho parado: 23 quadros. Prova: Dafd6TnOlOI q967 (32,23 s).
4. **Ritmo da fala.** 166 palavras por minuto, voz em 92% do tempo; pausa depois de frase de 0,00 s na mediana (máx 0,30 s). Prova: Dafd6TnOlOI pausa típica no fim de frase em q119 (3,97 s).
5. **Troca de plano presa à palavra.** A troca de plano começa 1 quadro(s) ANTES do começo da palavra mais perto (mediana): imagem nova entra junto com a palavra nova. Prova: Dafd6TnOlOI troca q3.
6. **Ação × palavra.** Sem padrão medível entre o gesto e a palavra seguinte (fala densa: uma palavra a cada ~8 quadros; o casamento não passa do acaso). Use a regra do formato (gesto termina ~4 quadros antes da palavra tônica). Prova: Dafd6TnOlOI pico q204 → palavra q205.
7. **A imagem é o que a fala diz, no quadro da palavra.** 82% das orações trazem imagem nova (troca de plano em 62%, o resto é ação/objeto dentro do plano); a imagem muda 4 quadro(s) antes da 1ª palavra da oração (mediana). Conferir oração por oração na folha fala-imagem e na tabela `fala-imagem/<vídeo>.md` (o que aparece × o que é dito). Prova: Dafd6TnOlOI 'Esse cara simplesmente engoliu o Brasil ' troca q3 → palavra q1.
8. **Fato vira objeto.** 3,4 números falados por minuto; 50% deles têm um evento visível (objeto que aparece, rola, acende ou plano novo) a ±0,3 s da palavra, em média -6 quadros da palavra. Prova: Dafd6TnOlOI '20' palavra q101, evento q92.
9. **Som medido.** Volume integrado -14,2 LUFS. Música (medida nas pausas da fala) 6 dB abaixo da voz. Picos de efeito: ~38 por minuto (estimativa: conferir no ouvido). Prova: Dafd6TnOlOI (áudio inteiro).
10. **Legenda.** Legenda com o centro a 48% da altura, letra de ~46 px numa tela de 1920, ~3 palavras por vez. Prova: Dafd6TnOlOI q1703 (56,77 s).
11. **Fim que emenda no começo.** Diferença entre o 1º e o último quadro: 162,3 (0 = idêntico; abaixo de ~12 o fim emenda no começo). Mais parecido: Dafd6TnOlOI (162,3). Prova: Dafd6TnOlOI q0 × q4257.
12. **Gancho.** A 1ª troca de imagem vem em 0,10 s na mediana; a primeira palavra em 0,02 s. Prova: Dafd6TnOlOI q3.

## Medidas (mediana do conjunto, com mínimo e máximo)

| Medida | Mediana | Faixa | Unidade |
|---|---|---|---|
| Plano: mediana | 0,83 | 0,83 a 0,83 | s |
| Plano: média | 1,61 | 1,61 a 1,61 | s |
| Planos por minuto | 37,2 | 37,2 a 37,2 | /min |
| Transição dissolve | 1 | 1 a 1 | % das trocas |
| Dissolve: quadros | 2,0 | 2,0 a 2,0 | quadros |
| Câmera andando | 92 | 92 a 92 | % dos quadros |
| Creep típico | 7,75 | 7,75 a 7,75 | % da largura/s |
| Entrada do plano × resto | 1,48 | 1,48 a 1,48 | × |
| Maior trecho parado | 23 | 23 a 23 | quadros |
| Fala | 166 | 166 a 166 | palavras/min |
| Voz no tempo | 92 | 92 a 92 | % |
| Pausa pós-frase: mediana | 0,00 | 0,00 a 0,00 | s |
| Pausa pós-frase: máx | 0,30 | 0,30 a 0,30 | s |
| Troca de plano × palavra | 1,0 | 1,0 a 1,0 | quadros |
| Ação antes da palavra | 0,0 | 0,0 a 0,0 | quadros |
| Oração com imagem nova | 82 | 82 a 82 | % das orações |
| Oração com troca de plano | 62 | 62 a 62 | % das orações |
| Imagem muda antes da palavra | 4,0 | 4,0 a 4,0 | quadros |
| Números falados | 3,4 | 3,4 a 3,4 | /min |
| Número com evento visual | 50 | 50 a 50 | % |
| Volume (LUFS integrado) | -14,2 | -14,2 a -14,2 | LUFS |
| Música abaixo da voz | 6,2 | 6,2 a 6,2 | dB |
| Efeitos (estimativa) | 38,0 | 38,0 a 38,0 | /min |
| Legenda: altura do centro | 48 | 48 a 48 | % da altura |
| Legenda: altura do texto | 46 | 46 a 46 | px em 1920 |
| Legenda: palavras na tela | 3,0 | 3,0 a 3,0 | palavras |

## Base sugerida pro formato

**formatos/explicador-3d/base** (animação 3D realista: render 3D com textura e sombra (lisura 0,12, ruído 5,0, saturação 57): jogo antigo/realista). Regra: animação sem pessoa estilo cartoon → `formatos/desenho-3d/base`; animação 3D realista feia estilo jogo antigo → `formatos/explicador-3d/base`; vídeo com pessoa gravada → formato gravado.

## Estilo × conteúdo

- **Estilo (vale copiar o jeito):** duração do plano, tipo e tamanho das transições, câmera andando, impulso na entrada, ação antes da palavra, ritmo da fala e das pausas, nível da música e dos efeitos, posição e tamanho da legenda, número virando evento na tela, fim que emenda no começo.
- **Conteúdo (nunca copiar):** o assunto, a transcrição (`videos/<vídeo>/words.json` é só pra medir), os personagens e rostos, os cenários específicos, marcas, nomes e o texto que aparece na tela.

## Por vídeo

| Vídeo | Duração | Planos | Mediana | Dissolve | Câmera andando | Palavras/min | LUFS | Base |
|---|---|---|---|---|---|---|---|---|
| Dafd6TnOlOI | 141,9 s | 88 | 0,83 s | 1 (2 q) | 92% | 166 | -14,2 | animação 3D realista |

## Fala × imagem (oração por oração)

Tabela de cada vídeo em `fala-imagem/<vídeo>.md` (fala · tempo · quadro · a imagem muda? · o que aparece · bate) e a folha `folhas/<vídeo>-fala-imagem-N.jpg` com o quadro da palavra de cada oração.

| Vídeo | Orações | Imagem nova | Troca de plano | Muda antes da palavra |
|---|---|---|---|---|
| Dafd6TnOlOI | 40 | 82% | 62% | 4 q |

## Folhas

- Dafd6TnOlOI: `folhas/Dafd6TnOlOI-geral.jpg`, `folhas/Dafd6TnOlOI-01-numero-q101.jpg`, `folhas/Dafd6TnOlOI-02-numero-q205.jpg`, `folhas/Dafd6TnOlOI-03-numero-q267.jpg`, `folhas/Dafd6TnOlOI-04-numero-q955.jpg`, `folhas/Dafd6TnOlOI-05-numero-q1319.jpg` (+26)
