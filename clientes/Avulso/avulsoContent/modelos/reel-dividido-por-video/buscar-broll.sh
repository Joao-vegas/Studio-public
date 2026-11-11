#!/bin/zsh
# Pesquisa de B-ROLL para o reel-dividido-por-video.
# Objetivo: material que CASE com o transcript, dinâmico (retenção) e SEM rosto
# de pessoa (em conteúdo de marca/produto). Método completo em PESQUISA-BROLL.md.
#
# Subcomandos:
#   site  <url> <nome> [outdir]        captura a TELA do site (fullpage) p/ scroll
#   og    <url> <nome> [outdir]        baixa og:image (anúncio estático oficial)
#   yt    <url> <secao> <nome> [outdir]  baixa trecho HD de vídeo (ex secao "30-45")
#   canal <busca> [n]                  lista candidatos do YouTube (título+canal+link)
#
# Sempre VERIFICAR o que baixou com /watch (ou verificar.sh) e descartar o que
# tiver rosto de pessoa quando a regra for "sem rosto".
set -euo pipefail
CMD="${1:-}"; shift 2>/dev/null || true

case "$CMD" in
  site)
    URL="$1"; NAME="${2:-site}"; OUTDIR="${3:-.}"; mkdir -p "$OUTDIR"
    curl -sL --max-time 60 "https://image.thum.io/get/width/1400/fullpage/${URL}" -o "$OUTDIR/${NAME}.png"
    python3 - "$OUTDIR/${NAME}.png" <<'PY'
import sys
from PIL import Image
p=sys.argv[1]; im=Image.open(p).convert("RGB")
im=im.crop((0,0,im.width,min(3600,im.height))); im.save(p)   # porção navegável p/ scroll
print(f"  {p}  {im.size}")
PY
    echo "  → use no gerar.sh em --srcs (faz scroll automático por ser .png)" ;;
  og)
    URL="$1"; NAME="${2:-og}"; OUTDIR="${3:-.}"; mkdir -p "$OUTDIR"
    IMG=$(curl -sL --max-time 20 -A "Mozilla/5.0" "$URL" | grep -ioE 'property="og:image"[^>]*content="[^"]+"|content="[^"]+"[^>]*property="og:image"|name="twitter:image"[^>]*content="[^"]+"' | grep -ioE 'https://[^"]+' | head -1)
    [[ -n "$IMG" ]] && curl -sL --max-time 20 -A "Mozilla/5.0" "$IMG" -o "$OUTDIR/${NAME}.png" && echo "  $OUTDIR/${NAME}.png  ($IMG)" || echo "  ✗ sem og:image em $URL" ;;
  yt)
    URL="$1"; SEC="$2"; NAME="${3:-yt}"; OUTDIR="${4:-.}"; mkdir -p "$OUTDIR"
    yt-dlp --no-update --no-playlist -f "bv*[height<=1080]+ba/b[height<=1080]" --merge-output-format mp4 \
      --download-sections "*${SEC}" --force-keyframes-at-cuts -o "$OUTDIR/${NAME}.%(ext)s" "$URL"
    echo "  ⚠ confira com /watch se NÃO tem rosto antes de usar" ;;
  canal|buscar)
    Q="$1"; N="${2:-10}"
    yt-dlp --no-update --flat-playlist --print "%(title)s :: %(channel)s :: https://youtu.be/%(id)s" "ytsearch${N}:${Q}" 2>/dev/null ;;
  *)
    echo "uso: buscar-broll.sh <site|og|yt|canal> ..."; exit 1 ;;
esac
