#!/bin/zsh
# MODELO: Faixa com cenas (Vegas). Só a câmera; cenas em cima (dividido) ou na tela cheia; frase em faixas.
# Estilos no PLANO.json: frase-fixa (frase o vídeo todo) | gancho-legenda (frase no gancho, depois legenda).
# Uso (de dentro da sandbox): zsh ../gerar.sh --dir . [--previa] [--saida <mp4>]   (detalhes: cabeçalho do gerar.py)
exec python3 "$(cd "$(dirname "$0")" && pwd)/gerar.py" "$@"
