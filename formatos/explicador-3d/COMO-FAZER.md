# Como fazer: Explicador 3D

**Quando usar:** roteiro narrado (sem pessoa gravada), de QUALQUER assunto, que conta um caso ou explica uma regra escondida,
de preferência com números. 45-90 s, 9:16. Cara de jogo antigo realista e feio (Loaded Dice): elenco variado escolhido pelo
roteiro, rosto pintado esquisito e exagerado, cenário cheio com luz de cinema. O formato não é "do dentista": o elenco e os
cenários saem do roteiro.
**Régua:** o exemplo principal (o 1º de "exemplos" no `formato.json`) e a régua medida quadro a quadro nos 11 shorts do Loaded
Dice (`estudo-quadros/ESTUDO-QUADROS.md` + `TRANSICOES-E-POP.md`; resumo no `ESTUDO.md`). Estilo e qualidade, nunca molde.
**Motor** (`base/`, campos em `base/README.md`): `elenco.js` (biblioteca de 17 personagens), `gente.js`, `mundos.js` (cidade,
praça, consultório, escritório, aquário, casa, loja, restaurante, banco, cassino; marcas em `marcas.json`), `objetos.js`
(contador, pilha, calendário, placa, celular, gaveta, urna, holofote, imagem...), `motor.js` e `gerar.py` (decupagem → cenas).
Rodar de `formatos/explicador-3d/base/` com `../../../app/.venv/bin/python render.py ...`.
**Exemplo completo:** a decupagem do 1º vídeo em `base/exemplos/cidade-12-mil-decupagem.json`.

## A régua do Loaded Dice (siga os números)

- **A imagem é o que a fala diz, no quadro da palavra** (88% das orações conferidas no olho). Nada de plano genérico.
- **Ritmo:** plano de ~2,2 s na mediana (1 a 3 orações por plano). Nem toda oração troca de plano (42% trocam): a imagem nova
  vem pela câmera que desliza pro enquadramento da oração (`passos`), por objeto que entra ou por ação, na palavra.
- **Troca:** corte seco em ~90%, 1 quadro antes da palavra. Dissolve raro (6 quadros). ~5 especiais por vídeo: chicote de câmera
  (10-15 q), objeto que passa na frente (`wipe`, 8-9 q), flash; nos números de dinheiro, `moedas_caem` e `notas_sobem` (14 q:
  o objeto cobre a tela no meio e a troca acontece atrás).
- **Câmera nunca para** (93% dos quadros), creep com impulso de 1,2× na entrada.
- **Pop de reação:** toda ação com `rosto` faz a pessoa subir ~20% da altura do rosto em 3-4 quadros e voltar com quique, na 1ª
  palavra (KxEs8tTORWM q1657); `pop: "grande"` = pulo de comemoração (8 q); `pop: false` desliga.
- **Fato é objeto:** número falado vira evento físico no quadro da palavra, com brilho de borda sutil (`brilho`).
- **Parado é parado:** ninguém respira; gesto termina 4 quadros antes da palavra; rosto troca atrás de uma piscada.
- **Fala:** ~186 palavras/min, pausa pós-frase ~0,11 s. **Legenda:** branca, 2 palavras, centro a 72%.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Narrativa visual.** Ler o roteiro e escrever `decupagem.json` na sandbox (formato no topo do `base/gerar.py`): elenco da
   biblioteca (`"elenco": {"dono": "comerciante"}` ou `{"base": "...", troca}`), vários personagens onde o roteiro pede gente
   (vizinhos, clientes, moradores), cenários e objetos dos números, e os planos: `oracoes` · `mundo` · `lugar` (posição ou
   `@marca`) · `acoes` (pose e rosto na `@palavra`) · `obj` · `cam` (`alvo`/`dist`/`az` ou `rosto:<id>`) · `passos` · `trans`
   · `mostra` (o que aparece). Mostrar a tabela ao João se ele pedir antes de produzir.
   **Elenco do cliente (29-out-2026, tela Elenco):** cada cliente guarda o figurino dos personagens em
   `<modelo>/elenco.json` (`{"<nome>": {"base": "...", ...só o que mudou}}`). Se o prompt trouxer "PERSONAGEM ESCOLHIDO: <nome>", ele
   é o protagonista: escreva `"elenco": {"<id>": "<nome>"}` (só o nome) e o `render.py` põe o figurino do cliente (`mesclar_elenco`).
   Só escreva campos do figurino na decupagem se o roteiro pedir uma roupa diferente daquela vez.
2. **Preparar a narração.** `voz.falar` (VoiceStudio; reserva ElevenLabs só com chave e voz; nunca pago sem o João), números por extenso. Apertar
   pausas: `python3 base/exemplos/apertar.py bruta.mp3 work/voz.wav` (silêncio > 0,20 s vira 0,14 s). `corte.py transcrever
   work/voz.wav work/tr2 --groq` e conferir cada número.
3. **Gerar as cenas.** `python3 base/gerar.py <sandbox>` → `cenas.json` + `DECUPAGEM.md` (tabela oração · tempo · cenário ·
   quem · ação · rosto · objeto · transição · o que aparece).
4. **Storyboard.** `render.py --storyboard --cenas cenas.json` e `--quadro` nos números e nas especiais; OLHAR: cada plano é a
   imagem da sua oração, rosto legível, nada cortado. Para pro João aprovar (a não ser que ele peça pra seguir).
5. **Vídeo.** `render.py --cenas cenas.json --processos 6` (sem outro processo pesado junto: a parte do render cai).
6. **Conferência.** `python3 app/ferramentas/estudo_quadros.py comparar formatos/explicador-3d/estudo-quadros <mp4> --words
   work/tr2/words.json --cenas cenas.json` (régua ref × nosso e a folha fala × imagem de cada plano); anotar o que aparece e
   se bate (`fala-imagem/<vídeo>.anotado.json`) e corrigir o que não bater; -14 LUFS. Pior que o exemplo não sai.

## Som e cena de apoio

**Música:** curiosidade/suspense leve, sem drop, uma faixa em rodízio (`base/audio/musicas/` ou acervo), ~10 dB abaixo da voz
nas pausas, constante do início ao fim (fade de 2,5 s), nunca com ducking. Pro João: 876.mp3 aprovada (favorita deste estilo).

**Efeitos:** moedas, ding, baque, whoosh, pop, porta, carimbo, notificação, urna, grilo, comemoração, sirene. Só na ação que
aparece, no quadro dela; impacto ~10 LU abaixo da voz, whoosh/pop ~15; as transições especiais já trazem o som delas.

**Cena de apoio:** não usa (sempre cena 3D própria, sem b-roll).

Música e efeito rodam em rodízio (`acervo/usos.jsonl`): nem a mesma música nas últimas 8 entregas do cliente, nem o mesmo
efeito nas últimas 4; favorito e pedido do João passam.

## Regras

Ficam em `aprendizado/regras.json`. Correção do João vira regra pela REGRA Nº 2 do `CLAUDE.md`.
