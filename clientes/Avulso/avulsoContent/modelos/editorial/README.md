# Motor do Editorial

`index.html` desenha (função `seek(t)`), `render.py` grava (Playwright + ffmpeg, o genérico do Estúdio) e mixa o som
(voz + música + efeitos, -14 LUFS, fade de 0,6 s no fim). Exemplo completo: `exemplos/grupo-por-crenca-gera.py`
(gera o `cenas.json` a partir do `words.json`), `exemplos/commons.py` (busca foto no Wikimedia Commons) e
`exemplos/apertar.py` (aperta as pausas da narração).

```
python3 render.py --cenas cenas.json --storyboard   # storyboard.jpg + previa-som.m4a
python3 render.py --cenas cenas.json --quadro 5.2,10 # quadros/ (PNG) pra conferir uma cena
python3 render.py --cenas cenas.json                # vídeo 1080x1920 (nome em "saida"), ~50 s pra 78 s de vídeo
python3 render.py --cenas cenas.json --conferir     # folha lado a lado com o exemplo principal
```

## cenas.json

```json
{"saida": "video.mp4", "voz": "work/voz.wav", "palavras": "work/words.json", "duracao": 78.6,
 "legenda": true, "legenda_y": 62,
 "musica": {"arquivo": "audio/musicas/364.mp3", "volume": 0.10, "inicio_s": 0},
 "efeitos": [{"t": 4.6, "arquivo": "audio/sfx/whoosh-short.mp3", "volume": 0.22}],
 "cenas": [{"tipo": "foto", "de": 0, "imagem": "fotos/x.jpg", "mov": "in"}]}
```

Toda cena: `tipo`, `de` (1ª palavra da oração), opcionais `entrada` (`corte` padrão | `flash` | `negativo` | `zoom` | `chicote`: desliza com rastro em 6 quadros, na batida),
`legenda: false`. Foto: `mov` (`in` `out` `esq` `dir` `cima` `baixo`), `forca`, `foco` [x, y], `pb`, `ponto`
(pontilhado de jornal), `texto` + `forte` [palavras em vermelho] + `tam` (`g` `m` `p`) + `y` (% da altura).

## Biblioteca (medida quadro a quadro nas 4 referências, `../estudos/`)

| tipo | O que é | De qual referência | Campos |
|---|---|---|---|
| `foto` / `titulo` | Foto em tela cheia, câmera sempre andando (creep ~13% da largura/s), frase grande Gilroy por cima se tiver `texto` | todas | `imagem`, `mov`, `pb`, `ponto`, `texto`, `forte`, `tam`, `y`, `escuro` |
| `cartao` | Foto num cartão de canto redondo sobre o fundo borrado dela | ref. 1 | `imagem`, `texto` |
| `rajada` | Fotos trocando a cada N quadros (P&B por padrão) | ref. 3 (3-4 quadros) | `imagens`, `quadros` (8 = 0,27 s), `pb`, `texto` |
| `print` | Print/manchete/documento flutuando, inclinado, sobre o fundo borrado; **grifo**: marca-texto amarelo corre no trecho exato quando a palavra é dita e a câmera chega perto (lupa) | ref. 2 e 3 + pedido do João | `imagem`, `giro`, `largura` (%), `texto`, `grifos` [{`x`,`y`,`w`,`h` em % do print, `t`}], `lupa` (false desliga) |
| `colagem` | Fotos entrando uma a uma, espalhadas, com pop | ref. 1 e 2 | `imagens`, `pb`, `texto` |
| `texto` | Frase inteira apagada; cada palavra acende no tempo dela, forte em vermelho | ref. 4 | `texto`, `forte`, `tempos` (o gera calcula), `tam` (px), `imagem` (fundo escuro opcional) |
| `icone` | Círculo tracejado girando com a LOGO real ou a foto da coisa dentro, rótulo embaixo. **Emoji não vale** (30-out, João: "fundo cinza... coisas meio broxantes"): `imagem` é obrigatória e o `--conferir` reprova ícone com `simbolo`. PNG com transparência (ou `logo` no nome do arquivo, ou `"logo": true`) entra colorido e inteiro sobre um disco claro/escuro; foto entra P&B enchendo o círculo | ref. 3 e 4 | `imagem`, `logo`, `rotulo`, `forte` |
| `venn` | Dois círculos tracejados que se encontram, rótulo no meio | ref. 1 | `rotulos` [a, b], `meio` |
| `chips` | Pílulas de borda branca acendendo sobre a foto escura | ref. 1 | `imagem`, `itens` [{`texto`, `t`}] |
| `dividido` | Duas fotos em cima e embaixo entrando de lados opostos, etiqueta inclinada | ref. 4 (cópia × original) | `imagens` [2], `rotulos` [2], `focos` |
| `contador` | Número contando e assentando, rótulo embaixo | ref. 4 (-20 dias) | `de_n`, `ate_n`, `ano`, `prefixo`, `sufixo`, `rotulo`, `imagem` |
| `zap` | Conversa de grupo genérica (sem marca), mensagens no tempo da fala | ref. 2 (prints de WhatsApp) | `grupo`, `membros`, `msgs` [{`de`, `eu`, `texto`, `imagem`, `t`, `altura`}] |
| `linha` | Linha do tempo com marcos | ref. 2 (2022 · 2023) | `marcos` [{`texto`, `nota`, `t`}] |
| `clipe` | Vídeo real (rua, torcida, comício, podcast) quadro a quadro, etiqueta itálica com traço vermelho | ref. 2 (bora Lula, podcast) | `quadros_de` (pasta de JPG a 30 fps), `inicio` (quadro), `etiqueta`, `nota`, `texto`; som do clipe vai em `efeitos` com `dur` |
| `fala` | O João gravado (entrada por vídeo): quadros do `fala.mp4` no tempo da cena, legenda forte (2-3 palavras Gilroy, `forte` em vermelho), soco de zoom a cada bloco; `modo` `cheia` ou `canto` (num cartão no cantinho sobre `imagem`) | pedido do João ("Editorial falado") + ref. 3 | `modo`, `imagem` (canto), `lado` (`esq`/`dir`), `pb`, `escuro`, `forte`, `y`, `legenda` |
| `recorte` | Pessoas sem fundo (PNG do rembg) em camadas sobre print/foto, cada camada anda numa velocidade: o "3D" | ref. 2 e 4 | `imagem` (fundo), `pessoas` [{`imagem`, `x`, `altura`, `escala`, `t`}], `escuro`, `pb`, `texto` |

**Fundo vivo (30-out-2026).** Peça que só desenha no degradê (`texto` sem `imagem`, `icone`, `venn`, `contador`, `chips`, `linha`, `zap` e `colagem` sem imagem, `fala` no canto sem imagem) ganha sozinha `fundo_vivo`: o `render.py` pega a imagem da cena mais próxima no tempo (a anterior no empate; foto vale mais que print; clipe vira o quadro do meio), a página desfoca (22 px), acerta o brilho pela imagem (média ~0,27, foto escura clareia, print branco escurece) e a faz andar devagar (zoom 1,3-1,4 e deriva). Sobre o fundo vivo a cena ganha a classe `fv`: halo escuro atrás do texto, faixa escura suave e a palavra forte em vermelho mais claro (`--forte-claro`), pra o rótulo não sumir (contraste medido em render: 3,3:1 ou mais; o halo conta). O grão do quadro (`#grao`) fica em opacity .12: a .32 sujava o fundo desfocado. Só `"fundo": "liso"` na cena tira (a conferência avisa); `"fundo_vivo": "fotos/x.jpg"` escolhe a imagem. Sem nenhuma imagem a 6 cenas de distância o `--conferir` reprova ("fundo liso sem imagem"). Conferência nova: ícone sem imagem (emoji) e cena em fundo liso sem imagem reprovam.

Assinatura do cliente: `"marca": "@soujoaovegas"` no topo do cenas.json (leve, 34%, no topo o vídeo todo).
Efeito com `"dur"` corta o som no tamanho do plano (som de clipe).

Por cima de tudo: grão animado, vinheta e a legenda curta (2-3 palavras, Inter 700 44 px, centro a 62%) nas cenas de
imagem sem texto próprio. Fundo das telas de texto: a imagem da cena vizinha desfocada (fundo vivo, abaixo); grafite liso só com `"fundo": "liso"`.

## Quando usar cada peça (adaptar ao roteiro, não copiar a referência)

- Nome de pessoa → `cartao` ou `foto` P&B com `ponto` e o nome pequeno embaixo (`tam: "p"`, `y: 82`).
- Lista falada ("preço, técnica, diploma") → `chips` com o `t` de cada palavra.
- Dois lados ("petista e bolsonarista", "cópia e original") → `dividido`; o que os dois têm em comum → `venn`.
- Ano ou número → `contador` (ano com `"ano": true`); ideia abstrata curta ("foi sorteio") ou marca citada ("Spotify") → `icone` com a logo real ou a foto da coisa, nunca emoji.
- Frase de virada ou fecho → `texto` (às vezes com `entrada: "flash"` ou `"negativo"`).
- "Muita gente", "vários casos" → `colagem` ou `rajada`. Conversa, grupo, comentário → `zap`.
- Gente de verdade fazendo a coisa (torcida cantando, multidão gritando, alguém falando) → `clipe` com o som dele baixo. Dois lados com rosto → `recorte` lado a lado.
- Estudo, dado, estatística, termo técnico ("viés de confirmação") → `print` da fonte real com `grifos` na linha exata, no tempo da palavra; nunca gráfico inventado.
- Plano de foto acima de 1,15 s sem texto vira dois (o gera corta na palavra do meio com outro enquadramento).

O motor é do formato: conserto aqui chega na cópia do cliente e na sandbox. Ajuste de um vídeo vai no `cenas.json`.

## Ferramentas da esteira (exemplos/, rodam da raiz do Estúdio; URL sempre entre aspas)

| Ferramenta | Faz |
|---|---|
| `preparar-narracao.py <sandbox> --voz <perfil> --cliente <Nome>` | roteiro.txt -> voz fixa em blocos conferidos -> work/voz.wav + words.json + narracao.json |
| `commons.py <pasta> consultas.json` | fotos do Wikimedia Commons (só as de lado maior >= 1100 px) com origem e licença |
| `print_fonte.py <sandbox> <nome> "<url>"` | print de matéria/estudo em prints/ + origem.json (recusa Wikipédia) |
| `clipe.py busca "<consulta>"` / `clipe.py baixa <sandbox> <nome> "<url>" <ini> <dur>` | clipe real 9:16 a 30 fps + som, uma vez no vídeo |
| `recorte.py <foto> <saida.png>` | pessoa sem fundo (rembg isnet-general-use) |
| `batida.py <musica> <work/batida.json>` | período da batida e drop da música (o gera_lib chama sozinho) |
| `gera-modelo.py` + `gera_lib.py` | o gera.py do vídeo só lista as cenas; a lib divide plano longo, corta na batida, põe os efeitos e avisa plano parado |
| `trocar_pequenas.py <sandbox>` | troca foto de tela cheia < 800 px por outra maior da mesma chave |
