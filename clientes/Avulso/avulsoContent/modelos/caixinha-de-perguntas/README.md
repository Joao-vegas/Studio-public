# Caixinha de perguntas — Vegas

Pessoa em tela cheia + a caixa de pergunta do Stories do Instagram fixa o vídeo inteiro.

| Arquivo | O que faz |
|---|---|
| `gerar.sh` | Grava a camada e renderiza pelo `camada.py` (h264_videotoolbox 12M, aac). `--previa` = só um quadro. |
| `build-caixinha.py` | Grava a camada (`camada.json`, tipo caixinha); o desenho é o `app/ferramentas/caixinha.py`. A tela "Editar o texto" troca pergunta e título depois. |

Uso, de dentro de `_sandbox-<slug>/`:

    zsh ../gerar.sh --dir . --pergunta "A PERGUNTA" [--titulo "..."] [--posicao cima|peito] [--topo px]
