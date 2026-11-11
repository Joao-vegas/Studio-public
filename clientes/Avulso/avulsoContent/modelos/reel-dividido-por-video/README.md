# Reel Dividido por Vídeo — Vegas

Modelo para vídeos verticais com estrutura de tela dividida, **vídeo (b-roll) no
bloco inferior** (variante do `reel-dividido-por-imagem`):

- João no topo (816px), centralizado;
- faixa **vermelha** (Bebas Neue) com manchete branca no meio;
- **b-roll de vídeo** embaixo (834px), cortado em takes, **sem áudio**;
- opcional: a faixa troca para um **CTA** a partir de um tempo (ex: "COMENTE 'COLA'").

## Arquivos

| Arquivo | O que faz |
|---|---|
| `gerar.sh` | Monta o reel (topo + faixa + b-roll). `--srcs` aceita vídeos (corta) e telas .png/.jpg (scroll). Único ponto de entrada. |
| `buscar-broll.sh` | **Pesquisa de b-roll**: captura tela de site, og:image, baixa trecho YouTube, lista canal. |
| `build-band.py` | Gera a faixa vermelha (Bebas Neue, centralizada, bordas rasgadas). |
| `verificar.sh` | Extrai frames densos do reel pronto p/ o Claude conferir o rosto frame a frame. |
| `PESQUISA-BROLL.md` | Método de busca de b-roll (casar com transcript, dinâmico, sem rosto). |

## Saída

`gerar.sh` salva em `vegasContent/output/reel-dividido-por-video/` (output próprio
do projeto). Após o João aprovar, arquivar no iCloud (final + bruto + material).

## Fluxo de uso

1. Crie um **sandbox de trabalho DENTRO do modelo** (nunca solto em vegasContent),
   ex: `modelos/reel-dividido-por-video/_sandbox/`, com:
   - `work/joao.mp4` — seu vídeo gravado (vertical).
   - `brolls/` — material baixado pelo `buscar-broll.sh`.
2. Baixe os b-rolls (yt-dlp) para uma pasta qualquer do sandbox.
3. Rode o `gerar.sh` apontando `--dir` para o sandbox.
4. Saída em `<sandbox>/output/YYYYMMDD-HHMMSS.mp4`.
5. **VERIFICAÇÃO DE ENQUADRAMENTO (obrigatória):** rode `./verificar.sh <output.mp4>`
   (ou a skill `/watch`) e confira FRAME A FRAME se o rosto do João está bem
   posicionado. Regra do João:
   - Se ele sair MUITO do lugar (movimento absurdo, rosto cortado/pro canto) num
     trecho → reajustar (`--video-offset-x/y/zoom`, ou pan no trecho) e re-render.
   - Se for **só ele se mexendo de leve** → NÃO mexer (tolerância).
   - Cada gravação tem proporção/posição própria — calibrar olhando os vídeos.

> **Higiene (regra do João):** o sandbox e os outputs são TEMPORÁRIOS e ficam
> DENTRO do modelo (`_sandbox/`). Depois que o João aprova e o material vai pro
> iCloud, **apagar o `_sandbox/` e os renders** — nada de vídeo pesado fica no repo,
> senão a pasta incha. Só os SCRIPTS do modelo são permanentes.

## Exemplo

```sh
./gerar.sh --dir ../../sandbox-burros \
  --titulo "IDENTIFIQUE UMA PESSOA BURRA EM 10 SEGUNDOS" \
  --srcs "../../sandbox-burros/brolls/homer_clips.mp4 ../../sandbox-burros/brolls/homer3.mp4" \
  --step 1.5 --video-zoom 1.25 --video-offset-y 470 --video-offset-x 95
```

## Flags

| Flag | Default | O que faz |
|---|---|---|
| `--dir` | (obrigatório) | Sandbox com `work/joao.mp4`; saída vai em `output/`. |
| `--titulo` | "" | Texto da faixa vermelha (CAIXA ALTA, centralizado). |
| `--srcs` | "" | B-rolls (vídeos), separados por espaço. Rotaciona entre eles. |
| `--takes` | — | Lista de segundos (ex `2,8,14`) para **curar** trechos do b-roll. |
| `--step` | 2.0 | Duração de cada corte. Menor = troca mais rápida (ex 0.5). |
| `--cta` | — | Texto do CTA (a faixa troca para ele). |
| `--cta-t` | — | Tempo (s) em que a faixa troca para o CTA. |
| `--video-zoom` | 1.15 | Zoom no topo. Maior = mais perto. |
| `--video-offset-y` | 660 | Posição vertical. **Menor = rosto desce** no quadro. |
| `--video-offset-x` | 70 | Posição horizontal. Maior = conteúdo p/ esquerda. |

## Notas técnicas

- B-roll **sempre sem áudio** (`-an`); áudio vem do vídeo do João.
- Cortes **secos** (sem fade) — fade-in a partir do preto causa "piscado preto".
- Encoder do render final: `h264_videotoolbox` (hardware Apple, rápido).
- `yt-dlp` precisa estar **atualizado** (versão >90 dias falha o signature solving
  do YouTube e só baixa 360p).
- Cada gravação do João tem enquadramento próprio — **sempre calibrar via `/watch`**.
