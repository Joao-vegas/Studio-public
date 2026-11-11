#!/usr/bin/env bash
# Atalho pro modelo twitter-meme.
#
# Uso curto (pega último vídeo do ~/Downloads):
#   ./tweet.sh "eu usando o Claude pra renomear um arquivo"
#
# Uso com vídeo específico:
#   ./tweet.sh -v meu-video.mp4 -t "texto"
#
# Todos os args são repassados pro gerar.sh do modelo.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELO="$(cd "$DIR/../../.." && pwd)/clientes/Joao/vegasContent/modelos/twitter-meme/gerar.sh"

[[ ! -x "$MODELO" ]] && { echo "✗ modelo não encontrado/executável: $MODELO" >&2; exit 1; }
exec "$MODELO" "$@"
