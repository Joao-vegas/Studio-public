# Motor do Documentário

`index.html` desenha (função `seek(t)`), `render.py` grava (Playwright + ffmpeg) e mixa o áudio. Tudo roda de
dentro da pasta copiada (base do formato, modelo do cliente ou `_sandbox-*`); o que ele grava fica ao lado do
`cenas.json` (ou em `--out`). Exemplo completo com os 9 tipos: `cenas-modelo.json` (usa `demo/`).

```
python3 render.py --cenas cenas.json --storyboard   # storyboard.jpg (1 quadro por cena) + previa-som.m4a; confere antes
python3 render.py --cenas cenas.json --quadro tipos # quadros/: 1 PNG por tipo (ou "cenas", ou "3.5,10")
python3 render.py --cenas cenas.json --ate 6        # teste.mp4 só com os 6 primeiros segundos
python3 render.py --cenas cenas.json                # vídeo final 1080x1920 (nome em "saida")
python3 render.py --cenas cenas.json --conferir     # reprova sozinho (exit 1); grava qa/conferir.json e qa/folha-comparacao.jpg
python3 render.py --folha-broll brolls/x.mp4        # qa/folha-x.jpg: 12 quadros do b-roll com o segundo de cada (escolher quadro_s/inicio_s)
python3 render.py --rostos work/joao.mp4            # qa/rostos.jpg: o rosto do bruto a cada 0,5 s; em vermelho olho não achado
```

Precisa de: `ffmpeg`, Playwright com Chromium, numpy, PIL e OpenCV (o `python3` do Mac tem; o rosto usa o haar do OpenCV,
sem rede). O recorte usa rembg
(u2net em `~/.u2net`); se o `python3` não tiver, o render chama o `app/.venv` sozinho.

## cenas.json

```json
{
  "titulo": "Vídeo 1",
  "saida": "video-1.mp4",
  "video": "work/joao.mp4",            // o bruto (mp4) ou uma foto; dá o áudio da voz se não houver "voz"
  "voz": null,                         // opcional: arquivo só de voz (roteiro narrado)
  "palavras": "work/words.json",       // tempo por palavra (Groq/Scribe {"words":[{word,start,end}]} ou [{w,s,e}])
  "duracao": null,                     // opcional; sem ela = fim da última cena / da voz
  "cores": {"marca": "#D4AF37", "dor": "#E23A3A"},  // só sem cliente: com clientes/<Nome>/identidade.json o motor usa a cor dele
  "estilo": {"legenda_y": 1250, "foco": [0.5, 0.4], "maiusculas": true},
  "destaque": ["liberdade"],           // palavras-chave boas no vídeo todo (cor da marca)
  "dor": ["prejuízo"],                 // palavras-chave de dor no vídeo todo (cor de dor)
  "empresa": ["liderança"],            // palavras de empresa/liderança (3ª cor do cliente; sem ela, a da marca)
  "musica": {"arquivo": "audio/musicas/1154.mp3", "inicio_s": 20},
  "efeitos": true,
  "cenas": [ {"tipo": "frase", "de": 0, "dor": ["malandro"]}, ... ]
}
```

- **musica**: `{"arquivo", "inicio_s"}` (de onde a faixa começa a tocar), uma lista de trechos pra trocar de
  faixa no meio (`[{"arquivo", "inicio_s", "de": 0}, {"arquivo", "inicio_s", "de": 58.4}]`, crossfade de 1,2 s)
  ou `null` (sem música). `musica_db` sobe/desce a música em dB (padrão 0). Faixas e clima: `audio/catalogo.json`
  (Mixkit; as rejeitadas o `--conferir` reprova).
- **efeitos**: `true` = efeitos suaves que o motor escolhe, **no ritmo do exemplo**: o exemplo-1 tem 16 em 1:23 (o teclado
  de cada tela de texto; passagem e pop não aparecem), então o teto é 12 por minuto, com 2,4 s ou mais entre um e outro.
  Ordem de preferência: teclado da frase/traço/relógio → um toque por construção (tique no fim do relógio, clique no
  círculo ou na última marca do caderno, tecla no rótulo do traço) → teclado do rodapé → pop na polaroid e na etiqueta →
  passagem (whoosh-short) só quando o mundo muda (pessoa, papel claro, jornal, escuro). Volume 0,10 a 0,18, passa-alta em
  200 Hz: zero golpe. `false` = nenhum efeito. Lista = só esses sons (`["typing", "whoosh-short", "click-soft", "tique",
  "pop", "key-press"]` são os 6): é o que a tela manda quando o João desmarca um som. O rodapé do storyboard e a saída do
  `--storyboard` dizem o número real ("efeitos: 19 em 1:59 (teclado 17, clique 2)"): é esse que vai pro João.
- **música aprovada na tela**: o `PLANO.json` ao lado manda. Com 2 faixas, a opção escolhida guarda os `"trechos"`
  (arquivo, inicio_s, de) iguais aos do cenas.json; o `qa/checagem.json` devolve cada trecho com `de` e `ate`. Opção com
  uma faixa só e cenas.json com duas (ou o contrário): reprova, senão o vídeo sai só com a 1ª.
- Áudio: voz a -16 LUFS, música com ducking por sidechain (threshold 0,15, ratio 2,5), tudo a -14 LUFS em duas
  passadas. A trilha sem voz vai pra `qa/trilha-sem-voz.wav` (é o que o `--conferir` mede).

## Cenas

Toda cena: `tipo`, `de` (segundo em que entra; `ate` opcional = início da próxima). Opcionais: `texto` (corrige a
transcrição; mesma contagem de palavras mantém os tempos), `destaque` / `dor` (palavras-chave dessa cena),
`legenda: false` (sem texto), `fundo` (`escuro` | `papel` | `jornal`). A fala daquele trecho entra datilografada
uma vez só, no tempo de cada palavra. Cena de fora (polaroid/filme com b-roll): `origem` = de onde veio (o filme ou o
arquivo, o acervo ou o link); banco de imagem (Pexels, Pixabay...) reprova.

| tipo | O que é (construção do exemplo-1) | Campos |
|---|---|---|
| `frase` | Fundo escuro, serifa Tinos 700 acendendo palavra a palavra com cursor, centraliza conforme entra; palavra-chave grande na cor da marca ou vermelha | `topo` |
| `pessoa` | O bruto em tela cheia, legenda serifa em blocos curtos com a palavra colorida, **abaixo do queixo** (o motor acha o rosto e põe a legenda e o zoom; `estilo.legenda_y` é o mínimo) | `plano` (`aberto` \| `close`, alterna sozinho), `foco` [x, y], `video` (outro clipe), `legenda_y` |
| `recorte` | Silhueta P&B com borda branca tirada de um quadro do próprio bruto (rembg u2net, limitado pelo u2net_human_seg: só a pessoa, sem abajur nem móvel); o motor acerta o quadro até 0,6 s (rosto parado) | `quadro_s` (segundo do bruto; cada recorte um quadro diferente), `fonte` (outro arquivo), `altura`, `topo` |
| `relogio` | Relógio correndo (23:00 → 05:00), com a silhueta embaixo se pedir | `de_hora`, `ate_hora`, `recorte: true`, `quadro_s` |
| `polaroid` | Polaroid com fita sobre o papel de jornal escuro e limpo (sem texto inventado); foto/quadro pequeno pra janela passa pelo Real-ESRGAN | `imagem` ou `video` + `quadro_s` (escolhido na `--folha-broll`), `corte` [x, y, w, h] tira logo do canto, `giro`, `topo` |
| `caderno` | Caderno quadriculado (papel claro, como no exemplo), título e **lista de 2 itens ou mais** à mão (Caveat), X/✓ e círculo de caneta desenhados (palavra longa encolhe e o círculo abraça a palavra inteira) | `titulo`, `itens` [{`texto`, `marca`: `x`\|`v`, `em`}], `circulo` {`texto`, `sub`, `em`}, `tom: "escuro"` |
| `traco` | Bifurcação desenhada, frase no topo e um rótulo em cada caminho | `rotulos` {`esquerda` {`texto`, `nota`, `em`}, `direita` {`texto`, `cor`, `em`}} |
| `jornal` | Papel de jornal escuro com um painel claro reto atrás do recorte da pessoa e a etiqueta de nome; o motor acerta o quadro até 1,5 s (de frente, olho aberto, parado) | `nome`, `cargo`, `quadro_s`, `etiqueta_x`, `etiqueta_y` |
| `filme` | B-roll P&B numa faixa reta de ponta a ponta com régua clara em cima e embaixo (barras pretas cortadas sozinhas; clipe pequeno demais passa por denoise + Lanczos 2x + nitidez) | `video` + `inicio_s` + `corte` [x, y, w, h] opcional, ou `imagem` |

`em` = primeira palavra da fala em que o item/rótulo/círculo aparece (sem ela, espalha no tempo da cena).
Caminhos: absolutos ou relativos à pasta do `cenas.json`, a esta pasta, à base do formato ou à raiz do Estúdio.

## Visual do fundo e do b-roll (30-out-2026, João no Kodak: "acho muito feio visualmente falando")

O fundo `jornal` é só CSS: papel de jornal escuro com luz quente, grão e moldura de duas réguas finas, **sem texto, sem colunas de enfeite**
(saíram o cabeçalho "BALCÃO", as linhas cinza, a borda rasgada e a caixa de papel com cursor do rodapé: a fala vai direto no fundo, clara com
contorno no escuro e escura no papel claro). Fundo vivo: `filme` e `polaroid` em fundo jornal levam a própria imagem da cena desfocada e escurecida atrás do papel (`fundoVivo()`; o papel claro continua liso de propósito). `filme` com `imagem` aceita `foco` [x, y] (foto vertical numa faixa horizontal). Mídia de fora: `escala_na_tela` mede quanto o arquivo é esticado pra encher a moldura (filme 1080 px
de largura, polaroid 772x620, já com o zoom); acima de `UPSCALE_MAX` (1,3x) o `preparar()` trata antes de montar (foto e quadro de polaroid: Real-ESRGAN
x4plus em `app/ferramentas/midia_local.py`; clipe: `filtro_clipe_ampliado`, denoise + Lanczos 2x + nitidez em P&B suave) e a checagem **3j** reprova o que
ainda fica acima de `UPSCALE_FINAL_MAX` (1,25x), como clipe de menos de ~475 px de largura. `"ampliar": false` na cena desliga o tratamento (e aí reprova).
O Real-ESRGAN de vídeo foi testado no clipe de 1971 e deu cara de cartoon, por isso o clipe usa o filtro do ffmpeg. A checagem antiga do "jornal borrado" (3i) só mede o rosto da
cena `jornal`; o b-roll do `filme` e da `polaroid` nunca era medido, e foi por isso que o Kodak passou.

## O que o --conferir reprova (números do exemplo-1)

Tela acima de 2,5 s (a última cena vai até o fim do vídeo) · pessoa falando acima de 35% do tempo · a pessoa na
tela somando tudo (falando, recorte, jornal, relógio com silhueta, polaroid/filme do bruto) acima de 40% (exemplo:
35%) · **frase acima de 30%** do tempo (exemplo: ~29%) · **mais de 2 frases seguidas** · **objetos** (polaroid,
caderno, traço, jornal, filme, relógio) **abaixo de 30%** (exemplo: ~45%) · **b-roll de filme/polaroid esticado acima de 1,25x depois do tratamento (arquivo pequeno pra tela, borrado e em blocos)** · polaroid ou filme com a própria pessoa ·
menos cenas de fora (polaroid/filme com b-roll) que 1 a cada ~21 s (1 até 45 s; exemplo: 4 em 83 s) · **a mesma
imagem duas vezes** (recortes do mesmo quadro a menos de 2 s, a mesma polaroid ou o mesmo trecho de filme) · **tela
de texto cortando a ideia** (a cena antes ou depois de uma frase/traço termina em "o", "do", "e", "muito"...) ·
**palavra-chave que não está na fala da cena** · **fim sem palavra-chave** · relógio sem hora na fala (até 1,5 s
antes da cena) · menos de 6 tipos de construção · os 3 primeiros segundos fora de construção (não precisa ser fundo
preto) · música abaixo de -35 dB nas pausas ou drone/pad (médio+agudo abaixo de 20%) · música rejeitada · sem
efeitos, **mais efeitos que o teto do exemplo (12 por minuto) ou colados (menos de 2,4 s)** ou qualquer golpe · vídeo fora
de 1080x1920 ou com imagem parada mais de 2,5 s.

Da prova do V2 do Cliente4 (nota 7,5): **palavra-chave fraca** em letra grande (VEZES, TODO, GRANDE, INTEIRO, -MENTE) ·
**tela de texto começando no meio da ideia** (depois de palavra sem pontuação e sem pausa) · **ideia curta (até 5 s)
quebrada em 3 telas** · **fim pendurado** ("com ele") · **caderno com menos de 2 itens** (só o círculo é frase disfarçada) ·
**menos telas claras que o exemplo** (2 em 1:23: caderno de papel, polaroid no papel; nada de tudo escuro; só o cliente cuja
regra recusa papel claro leva `"estilo": {"papel_claro": false}` e fica fora desta) · **legenda da
pessoa colada na boca/barba** (vai no peito: 0,35 rosto abaixo do queixo no plano; reprova abaixo de 0,22 medido no quadro
pronto do storyboard e, no `--conferir`, em 3 quadros de cada cena do vídeo) · **"cores" contra a identidade do cliente** · **jornal com o rosto ruim** (sem rosto de
frente, olho fechado, borrado) · **o mesmo clipe de fora em duas cenas** (o mesmo plano de filme emendado conta 1) · **cena
de fora sem `origem` ou de banco de imagem** · **música diferente da aprovada na tela**.

Da prova das 22h do V2 do Cliente4: **cenas de fora quase todas filme** (13 de 14 na mesma tira de jornal: pelo menos 1/3
polaroid, como no exemplo, 2 + 2) · **recortes demais** (mais de 1 a cada ~30 s: o mesmo bruto dá recortes iguais) ·
**tela de texto parando no meio da ideia** ("mas também envolve" + "uma carga": sem pontuação, sem pausa e a palavra
seguinte não abre outra ideia) · MAIORIA/MINORIA como palavra-chave.

O `--storyboard` roda a mesma checagem antes do render (tudo menos o mp4), mede a música nas pausas na
`previa-som.m4a` e grava `qa/folha-<b-roll>.jpg` de cada cena de fora com o quadro usado em dourado (olhar: o que a
fala diz, gente quando ela fala de gente, sem marca d'água): sai com exit 1 e "REPROVADO na checagem" + os motivos (também em vermelho no rodapé do
storyboard e em `qa/checagem.json`). O quadro de cada cena sai no fim dela, com a última palavra já digitada. Exceção: o `PLANO.json` ao lado do `cenas.json`
(a tela grava nele) com `musica.sem` ou `sfx_ligado: false` = o João tirou na tela; a falta não reprova, pôr de
volta reprova. Som desmarcado sozinho (`sfx` com `ligado: false`) também: tocar esse som no vídeo reprova.

## Arquivos

`fontes/` Tinos (Apache 2.0) e Caveat (OFL), sem rede cai em Times New Roman e Bradley Hand ·
`audio/musicas/` 38 faixas Mixkit (licença livre Mixkit) + `audio/catalogo.json` · `audio/sfx/` 6 efeitos
Pixabay (`CREDITS.md`) · `demo/` mídia do `cenas-modelo.json`. A cópia do cliente e a `_sandbox-*` não levam
`audio/musicas/` nem `demo/` (154 MB por vídeo): o `render.py` acha os dois em `formatos/documentario/base/`
(e qualquer efeito que a cópia não tenha).

O motor é do formato, não do cliente: a cada vídeo o Estúdio copia o que estiver mais novo da base pro modelo do
cliente e dele pra sandbox (`esteira.motor_arquivos` no `formato.json`). A cor do cliente vem sozinha do
`clientes/<Nome>/identidade.json` ("papeis": destaque → marca, dor, empresa_lideranca → empresa, fundo, texto,
destaque_escuro → etiqueta e ✓); "cores" no `cenas.json` que contradiz a identidade o `--storyboard` reprova. O resto que é
do cliente vai no `cenas.json` (estilo) e nas regras; mexer no motor da cópia se perde no próximo conserto da base.
