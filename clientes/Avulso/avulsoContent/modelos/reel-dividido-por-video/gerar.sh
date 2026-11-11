#!/bin/zsh
# MODELO: Reel Dividido por Vídeo — Vegas
# Topo: Joao centralizado. Meio: faixa vermelha (Bebas Neue). Baixo: B-ROLL
# cortado em takes (cover, SEM AUDIO), opcionalmente trocando p/ faixa CTA.
#   --srcs aceita VÍDEOS (corta em trechos) E IMAGENS/telas .png/.jpg (faz SCROLL
#   vertical — parece gravação de tela navegando). Pra pesquisar b-roll use o
#   buscar-broll.sh (site/og/yt/canal). Método em PESQUISA-BROLL.md.
#
# O sandbox de trabalho fica fora do modelo. Estrutura esperada do --dir:
#   <sandbox>/work/joao.mp4   (seu vídeo gravado, vertical)
#   <sandbox>/output/         (saida, criada automaticamente)
#
# Uso:
#   ./gerar.sh --dir <sandbox> --titulo "TÍTULO" --srcs "broll1.mp4 broll2.mp4" \
#       [--takes "2,8,14,..."]            # curar segundos específicos do b-roll
#       [--step 2.0]                      # duração de cada corte (menor = mais rápido)
#       [--cta "COMENTE 'COLA'" --cta-t 58]   # troca a faixa pro CTA a partir de t=58s
#       [--video-zoom 1.25 --video-offset-y 510 --video-offset-x 80]
#       [--rosto-fixo]                    # recorte parado no offset-y (padrão: segue o rosto)
#       [--invertido]                     # INVERTE o layout: B-ROLL EM CIMA, João EMBAIXO
#                                         # (faixa continua no meio). Formato-teste do João.
#
# Calibração do topo: zoom maior = mais perto; offset-y MENOR = rosto desce;
# offset-x maior = conteúdo vai p/ esquerda. SEMPRE conferir com a skill /watch.
set -euo pipefail
SELF="$(cd "$(dirname "$0")" && pwd)"

DIRSB="" ; TITULO="" ; CTA="" ; CTA_T="" ; SRCS="" ; TAKES="" ; INVERT="" ; JOAOH="816" ; ROSTO_FIXO=""
VIDEO_ZOOM="1.15" ; VIDEO_OFFSET_Y="660" ; VIDEO_OFFSET_X="70" ; STEP="2.0"
while [[ $# -gt 0 ]]; do case "$1" in
  --dir) DIRSB="$2"; shift 2;;
  --titulo) TITULO="$2"; shift 2;;
  --cta) CTA="$2"; shift 2;;
  --cta-t) CTA_T="$2"; shift 2;;
  --srcs) SRCS="$2"; shift 2;;
  --takes) TAKES="$2"; shift 2;;
  --video-zoom) VIDEO_ZOOM="$2"; shift 2;;
  --video-offset-y) VIDEO_OFFSET_Y="$2"; shift 2;;
  --video-offset-x) VIDEO_OFFSET_X="$2"; shift 2;;
  --step) STEP="$2"; shift 2;;
  --invertido) INVERT="1"; shift;;
  --joao-h) JOAOH="$2"; shift 2;;   # altura do bloco do Joao (816 padrao); maior = faixa desce
  --rosto-fixo) ROSTO_FIXO="1"; shift;;   # desliga o seguir_rosto e usa o --video-offset-y fixo
  *) echo "flag?: $1"; exit 1;;
esac; done

# Layout dos blocos. Faixa fixa no meio (816..1086). Normal: João em cima (816),
# b-roll embaixo (834). Invertido (--invertido): b-roll em cima (816), João embaixo (834).
BAND_H=270
if [[ -n "$INVERT" ]]; then
  JOAO_H=$(( 1920 - JOAOH - BAND_H )) ; JOAO_Y=$(( JOAOH + BAND_H )) ; BROLL_H=$JOAOH ; BROLL_Y=0
else
  JOAO_H=$JOAOH ; JOAO_Y=0 ; BROLL_H=$(( 1920 - JOAOH - BAND_H )) ; BROLL_Y=$(( JOAOH + BAND_H ))
fi

[[ -z "$DIRSB" ]] && { echo "✗ --dir obrigatório"; exit 1; }
DIR="$(cd "$DIRSB" && pwd)"
JOAO="$DIR/work/joao.mp4"
[[ ! -f "$JOAO" ]] && { echo "✗ não achei $JOAO"; exit 1; }
# saída padrão do projeto: vegasContent/output/reel-dividido-por-video/
VC="$(cd "$SELF/../.." && pwd)"
OUT_DIR="$VC/output/reel-dividido-por-video"; mkdir -p "$OUT_DIR"
DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$JOAO")
TS="$(date +%Y%m%d-%H%M%S)"; OUT="$OUT_DIR/${TS}.mp4"
WORK="$(mktemp -d /tmp/reel-divvid-XXXXXX)"; trap "rm -rf '$WORK'" EXIT

srcarr=(${=SRCS}); nsrc=${#srcarr[@]}
typeset -A srcdur
for f in "${srcarr[@]}"; do srcdur[$f]=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$f" 2>/dev/null || echo 0); done

echo "▶ bloco inferior (b-roll, sem audio, cortes ~${STEP}s)..."
LIST="$WORK/list.txt"; : > "$LIST"
NTAKES=$(awk -v d="$DUR" -v s="$STEP" 'BEGIN{n=int(d/s); if (d-n*s>0.1) n++; print n}')
for (( i=0; i<NTAKES; i++ )); do
  dur=$(awk -v i="$i" -v s="$STEP" -v d="$DUR" 'BEGIN{r=d-i*s; v=(r<s)?r:s; printf "%.2f", v}')
  if (( $(awk -v v="$dur" 'BEGIN{print (v<0.2)?1:0}') )); then continue; fi
  src=${srcarr[$(( i % nsrc + 1 ))]}
  sd=${srcdur[$src]}
  if [[ -n "$TAKES" ]]; then
    takearr=(${(s:,:)TAKES}); nt=${#takearr[@]}
    ss=${takearr[$(( i % nt + 1 ))]}
  else
    ss=$(awk -v i="$i" -v n="$nsrc" -v st="$STEP" -v sd="$sd" 'BEGIN{lim=sd-st-1; if(lim<1)lim=1; v=(int(i/n))*st*1.35; while(v>=lim)v-=lim; printf "%.2f", v}')
  fi
  out="$WORK/s_$(printf '%03d' $i).mp4"
  case "${src:l}" in
    *.png|*.jpg|*.jpeg)
      # IMAGEM/tela → scroll vertical suave (parece gravação de tela navegando)
      ffmpeg -loop 1 -t "$dur" -i "$src" \
        -vf "scale=1080:-1:flags=bicubic,crop=1080:${BROLL_H}:0:'min((ih-${BROLL_H})*t/${dur}\,ih-${BROLL_H})',format=yuv420p,fps=30,setsar=1" \
        -an -r 30 -c:v libx264 -preset veryfast -crf 20 -y "$out" -loglevel error ;;
    *)
      # VÍDEO → corta trecho (cover), cortes secos (sem fade = sem piscado preto)
      ffmpeg -ss "$ss" -t "$dur" -i "$src" \
        -vf "scale=1080:${BROLL_H}:force_original_aspect_ratio=increase,crop=1080:${BROLL_H},format=yuv420p,fps=30,setsar=1" \
        -an -r 30 -c:v libx264 -preset veryfast -crf 20 -y "$out" -loglevel error ;;
  esac
  echo "file '$out'" >> "$LIST"
done
ffmpeg -f concat -safe 0 -i "$LIST" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -an -y "$WORK/bottom.mp4" -loglevel error
echo "  $i takes"

echo "▶ faixa(s)..."
python3 "$SELF/build-band.py" --out "$WORK/band.png" --titulo "$TITULO" --top-h "$JOAOH"
HAS_CTA=0
if [[ -n "$CTA" && -n "$CTA_T" ]]; then
  python3 "$SELF/build-band.py" --out "$WORK/band_cta.png" --titulo "$CTA" --top-h "$JOAOH"; HAS_CTA=1
fi

SCW=$(awk -v z="$VIDEO_ZOOM" 'BEGIN{printf "%d",1080*z+0.5}')
SCH=$(awk -v z="$VIDEO_ZOOM" 'BEGIN{printf "%d",1920*z+0.5}')
CRX=$(( (SCW-1080)/2 + VIDEO_OFFSET_X )); [[ $CRX -lt 0 ]] && CRX=0
[[ $CRX -gt $((SCW-1080)) ]] && CRX=$((SCW-1080))
CRY=$VIDEO_OFFSET_Y; [[ $CRY -lt 0 ]] && CRY=0
[[ $CRY -gt $((SCH-JOAO_H)) ]] && CRY=$((SCH-JOAO_H))
# Padrão: o recorte segue o rosto (rosto no meio do bloco; quando ele sai do centro, desliza ~0,8s até
# recentralizar, sem corte seco). --rosto-fixo volta pro offset-y fixo.
if [[ -z "$ROSTO_FIXO" && -f "$SELF/seguir_rosto.py" ]]; then
  PYR="$SELF/../../../../../app/.venv/bin/python"; [[ -x "$PYR" ]] || PYR=python3
  echo "▶ seguindo o rosto..."
  CRY="'$("$PYR" "$SELF/seguir_rosto.py" "$JOAO" --joao-h "$JOAO_H" --zoom "$VIDEO_ZOOM")'"
fi

FILTER="color=c=white:s=1080x1920:d=${DUR}[bg];"
FILTER+="[0:v]crop=ih*9/16:ih:iw/2-ih*9/16/2:0,scale=${SCW}:${SCH},crop=1080:${JOAO_H}:${CRX}:${CRY},setsar=1[topvid];"
FILTER+="[2:v]scale=1080:${BROLL_H},setsar=1[bottom];"
FILTER+="[bg][topvid]overlay=0:${JOAO_Y}[s1];"
FILTER+="[s1][bottom]overlay=0:${BROLL_Y}[s2];"
if [[ $HAS_CTA -eq 1 ]]; then
  FILTER+="[s2][1:v]overlay=0:0:enable='lt(t,${CTA_T})'[s3];"
  FILTER+="[s3][3:v]overlay=0:0:enable='gte(t,${CTA_T})'[out]"
  EXTRA=(-loop 1 -i "$WORK/band_cta.png")
else
  FILTER+="[s2][1:v]overlay=0:0[out]"; EXTRA=()
fi

echo "▶ render..."
ffmpeg -i "$JOAO" -loop 1 -i "$WORK/band.png" -i "$WORK/bottom.mp4" "${EXTRA[@]}" \
  -filter_complex "$FILTER" -map "[out]" -map "0:a?" \
  -c:v h264_videotoolbox -b:v 8M -c:a aac -b:a 128k -movflags +faststart -shortest \
  -y "$OUT" -loglevel error
echo "✓ $OUT"
