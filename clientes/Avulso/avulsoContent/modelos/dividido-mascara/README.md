# Dividido-Máscara (BEATS) — Vegas

Evolução do `reel-dividido-por-video`. **NÃO é dividido o tempo todo.** Base = João
em **tela cheia + legenda abaixo do queixo** + **cama de música baixa** (sempre a já
aprovada, `assets/musica/bed.mp3` a `0.055`, constante com fade — o João sente falta
quando some). A cada ~6-10s entra um **beat** pontual (variedade / retenção):

- **broll** — b-roll numa faixa de baixo com **borda esfumada + sombra** (mesclagem
  tipo máscara do CapCut, SEM faixa vermelha / split duro), casando com a fala.
- **card** — fundo claro com frase-chave, **animado palavra a palavra COM click** em
  cada palavra (é o **único** efeito sonoro aprovado — João 17/09/2026: *"onde aparece
  o fundo branco você tirou o click, ele poderia ter deixado"*), no tempo exato da fala. Também há **card de arquivo** (`@arquivo.mp4`) pra cards
  especiais (ex: logo/rosto).
- **punch** — push-in **suave** no João (não fecha no rosto).

## 🔊 Áudio (doutrina fechada em 17/09/2026, duas rodadas de correção)

| | |
|---|---|
| **Receita** | `--sem-sfx --click-cards --music assets/musica/bed.mp3 --music-vol 0.055` |
| **Tem** | voz (`loudnorm I=-16`) · cama `bed.mp3` constante a `0.055` com fade 1,5s · **click por palavra só no card branco** (`0.55`) |
| **Não tem** | whoosh na entrada de b-roll · boom no impacto · faixa de música nova · `--music-expr` (volume desenhado em janelas) |
| **Mix** | `alimiter=limit=0.71:level=0` — `level=1` é auto-level e **sobe** a loudness; teto `0.71` e não `0.89` porque o AAC 128k do encode final devolve ~1,2 dB de overshoot |
| **Alvo medido** | `-15,6 LUFS` / `-2,1 dBTP` |

Card de **arquivo** (`@arquivo.mp4`) sem sidecar `.clicks` não é fundo branco e fica
mudo — se ele tiver um `.clicks` vazio (0 byte), é de propósito.

> 🔴 **LEIA `aprendizado/regras.json` ANTES de produzir.** São 11 regras vindas de
> uma sessão longa de correções do João (legenda, enquadramento, punch, b-roll,
> cards, etc.). O `comando_referencia` de lá reproduz o resultado aprovado.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `gerar.sh` | Único ponto de entrada. Base + beats + legenda + música + gancho. |
| `build-legenda.py` | Legenda Barlow-Black (chunks por palavra do GROQ, WORD_GAP). |
| `build-card.py` | Card animado de texto + `--sync` (casa cada palavra com a fala). |
| `build-logorosto.py` | Card especial logo→rosto (marca em cima, dono embaixo). |
| `build-mask.py` | (legado) máscara cheia; a faixa usa geração inline no gerar.sh. |
| `buscar-broll.sh` | Pesquisa de b-roll (site/og/yt/canal). |
| `assets/` | Música (bed) + SFX. **Só o `click.mp3` é usado**; `whoosh.mp3`/`boom.mp3` estão reprovados. |

## Uso (ver `aprendizado/regras.json` → `comando_referencia`)

```sh
./gerar.sh --dir _sandbox \
  --gancho brolls/gancho.mp4 --gancho-dur 2.5 \
  --sem-sfx --click-cards --music assets/musica/bed.mp3 --music-vol 0.055 \
  --video-zoom 1.2 --video-offset-y 120 --legy 1270 --leg-fontsize 50 \
  --leg-maxwords 3 --leg-lead 0.12 --band-h 520 --punch-zoom 1.18 \
  --beats "broll:4-9:brolls/ratoeira.mp4@2;card:13-16.5:PARECE *MELHOR*;punch:18-21;\
           card:35-38:@brolls/logorosto.mp4;broll:39-43:brolls/pagina.mp4;..."
```

### Sintaxe dos beats
`TYPE:START-END[:ARG]`, separados por `;`. START/END em segundos do CORPO.
- `broll:s-e:arquivo[@seg-inicial]` — b-roll na faixa mesclada.
- `card:s-e:TEXTO com *palavra vermelha*` — card de texto animado (click por palavra com `--click-cards`).
- `card:s-e:@arquivo.mp4` — card pré-montado (ex: logo/rosto).
- `punch:s-e` — push-in suave.

## Saída / arquivamento

`vegasContent/output/dividido-mascara/`. Após o João **aprovar**: arquivar no iCloud
(final + bruto + `material/` + `material.md`) e **apagar `_sandbox/` e os renders**
(higiene — só os scripts ficam no repo). Ver memória `project_arquivamento_icloud_vegas`.

## QA obrigatório

Conferir com frames/`/watch`: legenda casando com a fala em vários pontos
(**seek preciso**, `-ss` DEPOIS do `-i`; offset = dur_total − dur_joao), legenda
abaixo do queixo, mesclagem (não parece split duro), cards no tempo da fala, e as
ZONAS PROIBIDAS do Instagram. Sem efeito/cor no Vegas.
