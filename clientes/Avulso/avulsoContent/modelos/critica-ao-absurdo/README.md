# Crítica ao absurdo — Vegas

Em cima, o trecho (20-30 s) de um vídeo com um comportamento que as pessoas normalizaram, com legenda de 1 a 3 palavras;
embaixo, a sua foto fixa reagindo; no fim, se tiver, a sua resposta em tela cheia.

| Arquivo | O que faz |
|---|---|
| `gerar.sh` | Lê as flags, decide a saída e chama o `build.py`. |
| `build.py` | Corta o trecho, transcreve (Groq), desenha a legenda (PIL), põe a foto embaixo e emenda a resposta (ffmpeg). |
| `assets/foto-padrao.png` | A sua foto reagindo (1080x874), tirada do reel DdXnhWBPmza. |

Uso, de dentro de `_sandbox-<slug>/` (com `work/absurdo.mp4`, e `work/joao.mp4` se tiver resposta):

    zsh ../gerar.sh --dir . --de 1:10 --ate 1:35 [--previa] [--sem-legenda] [--sem-resposta] [--foto <img>] [--foco-x 0..1]

Saída padrão: `vegasContent/output/critica-ao-absurdo/<slug>.mp4`.
