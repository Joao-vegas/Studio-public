#!/bin/zsh
# Verificação de enquadramento — extrai frames densos do reel pronto para que o
# Claude confira FRAME A FRAME (via Read/skill watch) se o rosto do João está
# bem posicionado no bloco de cima (centralizado, sem cortar testa/cabelo, sem
# sair pro lado).
#
# Uso: ./verificar.sh <video.mp4> [intervalo_segundos=3]
#
# Saída: caminho de uma pasta com frames JPG nomeados pelo timestamp (t0003.jpg...)
# O Claude então LÊ esses frames e decide:
#   - rosto OK em todos -> aprovado.
#   - rosto saiu pro lado/cortou em um trecho e é ALGO ABSURDO -> reajustar
#     (offset/zoom global, ou pan no trecho). Se for só o João se mexendo de leve,
#     NÃO mexer (tolerância — instrução do João).
set -euo pipefail
VIDEO="${1:-}"; INT="${2:-3}"
[[ -z "$VIDEO" || ! -f "$VIDEO" ]] && { echo "✗ uso: ./verificar.sh <video.mp4> [intervalo]"; exit 1; }
OUT="$(mktemp -d /tmp/verificar-XXXXXX)"
DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$VIDEO")
ffmpeg -i "$VIDEO" -vf "fps=1/${INT}" -q:v 3 "$OUT/t%04d.jpg" -loglevel error
echo "frames ($(ls "$OUT" | wc -l | tr -d ' ') @ cada ${INT}s, vídeo ${DUR}s):"
ls -1 "$OUT"/*.jpg
echo ""
echo "→ Claude: leia os frames acima e confira o rosto do João (centralizado, sem cortar)."
echo "  Ajuste só se ele sair MUITO do lugar; se for leve movimento, deixe."
