# Frase fixa — Vegas

Pessoa em tela cheia e UMA frase numa caixa no peito, o vídeo inteiro. Sem legenda da fala, b-roll, música nem efeito.

| Arquivo | O que faz |
|---|---|
| `gerar.sh` | Escala o `work/joao.mp4` pra 1080x1920, sobrepõe a caixa e renderiza (h264_videotoolbox 12M, aac). |
| `build-caixa.py` | Gera o PNG da caixa (Barlow SemiBold 60 a 48 px, preta ou branca, centro em y=1430). |

Uso, de dentro de `_sandbox-<slug>/` (com `work/joao.mp4` já cortado):

    zsh ../gerar.sh --dir . --frase "A FRASE" [--estilo preto|branco] [--saida <mp4>]

Saída padrão: `vegasContent/output/frase-fixa/<slug>.mp4`.
