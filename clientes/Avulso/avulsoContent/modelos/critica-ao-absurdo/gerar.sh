#!/bin/zsh
# MODELO: Crítica ao absurdo — Vegas
# Em cima, o trecho (20-30 s) de um vídeo com um comportamento que as pessoas normalizaram, com legenda de 1 a 3 palavras;
# embaixo, a SUA foto fixa reagindo (a mesma do 1º ao último quadro). Depois, se tiver, a sua resposta em tela cheia.
#
# Sandbox: <modelo>/_sandbox-<slug>/work/absurdo.mp4 (vídeo inteiro, pode ter 3 min), work/foto.* (opcional:
# sem ela vale assets/foto-padrao.png) e work/joao.mp4 (opcional: sua resposta já cortada).
# Uso (de dentro da sandbox): zsh ../gerar.sh --dir . --de 1:10 --ate 1:35 [--previa] [--sem-legenda] [--sem-resposta]
#   [--foto <img>] [--foco-x 0..1] [--foco-y 0..1] [--foto-y 0..1] [--saida <mp4>]
# Saída padrão: vegasContent/output/critica-ao-absurdo/<slug>.mp4 · prévia: <sandbox>/storyboard.jpg
set -euo pipefail
SELF="$(cd "$(dirname "$0")" && pwd)"
DIRSB="" ; SAIDA="" ; PREVIA="" ; EXTRA=()
while [[ $# -gt 0 ]]; do case "$1" in
  --dir) DIRSB="$2"; shift 2;;
  --saida) SAIDA="$2"; shift 2;;
  --previa) PREVIA="1"; shift;;
  --sem-legenda|--sem-resposta) EXTRA+=("$1"); shift;;
  --de|--ate|--foto|--video|--foco-x|--foco-y|--foto-y) EXTRA+=("$1" "$2"); shift 2;;
  *) echo "flag?: $1"; exit 1;;
esac; done
[[ -z "$DIRSB" ]] && { echo "✗ --dir obrigatório"; exit 1; }
DIR="$(cd "$DIRSB" && pwd)"
SLUG="${${DIR:t}#_sandbox-}"
VC="$(cd "$SELF/../.." && pwd)"
if [[ -n "$PREVIA" ]]; then SAIDA="$DIR/storyboard.jpg"; EXTRA+=(--previa)
elif [[ -z "$SAIDA" ]]; then mkdir -p "$VC/output/critica-ao-absurdo"; SAIDA="$VC/output/critica-ao-absurdo/${SLUG}.mp4"
else mkdir -p "${SAIDA:h}"; fi
python3 "$SELF/build.py" --dir "$DIR" --saida "$SAIDA" "${EXTRA[@]}"
