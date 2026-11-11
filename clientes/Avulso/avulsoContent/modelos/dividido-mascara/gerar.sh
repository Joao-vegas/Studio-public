#!/bin/zsh
# MODELO: dividido-mascara (BEATS) — Vegas
#
# NÃO é tela dividida o tempo todo. Base = João TELA CHEIA + LEGENDA abaixo do
# queixo + MÚSICA bem baixa (depois do gancho). A cada ~6-10s, quando NÃO é um
# ponto-chave da fala, entra um BEAT pontual (variedade / retenção):
#   broll  -> b-roll MESCLADO numa faixa de baixo com borda esfumada + sombra
#             (o "máscara/mesclagem" que o João pediu), casando com a fala.
#   card   -> fundo branco com uma frase-chave grande (flash card estilo Cliente8).
#   punch  -> só o João com ZOOM maior no rosto (momento de ênfase).
# O gancho de abertura fica só uns 3s e corta. Legenda sempre por cima (menos no card).
#
# Estrutura do --dir: <sandbox>/work/joao.mp4  e  <sandbox>/brolls/
#
# Uso:
#   ./gerar.sh --dir _sandbox \
#     --gancho brolls/gancho.mp4 --gancho-dur 3 \
#     --beats "broll:4-8:brolls/ratoeira.mp4@2;card:11-14:PARECE *MELHOR*;punch:16-20;\
#              broll:27-31:brolls/scroll.mp4;broll:50-55:brolls/dashboard.mp4;punch:59-63;\
#              broll:65-70:brolls/engrenagem.mp4" \
#     [--music assets/musica/bed.mp3] [--music-vol 0.055] [--sem-sfx] [--click-cards] \
#     [--legy 900] [--leg-fontsize 54] [--leg-maxwords 3] [--from 0] \
#     [--video-zoom 1.2] [--video-offset-x 0] [--video-offset-y 120] \
#     [--punch-zoom 1.7] [--band-h 760] [--band-feather 180]
#
# beats: separados por ';', campos por ':'. TYPE:START-END[:ARG]
#   broll ARG = arquivo[@segundo-inicial-na-fonte]   card ARG = texto (*x*=vermelho)
# START/END em segundos do CORPO (sem contar o gancho).
set -euo pipefail
SELF="$(cd "$(dirname "$0")" && pwd)"

DIRSB="" ; GANCHO="" ; GANCHO_DUR="2.5" ; BEATS="" ; MUSIC="" ; MUSIC_VOL="0.08"
LEGY="1150" ; LEG_FS="54" ; LEG_MAXW="3" ; FROM="0" ; LEG_LEAD="0.18" ; LEG_HIDE=""
VZOOM="1.2" ; VOFFX="0" ; VOFFY="120" ; PUNCH_Z="1.18"
BAND_H="640" ; BAND_FEATHER="170" ; BAND_POS="bottom" ; CLICK="$SELF/assets/sfx/click.mp3"
# musica em JANELAS (nao cama contínua) + SFX pontuais (whoosh/boom) — João 17/09
MUSIC_SS="0" ; MUSIC_EXPR="" ; SFX=""
# João 17/09 (v2): "você fez um efeito sonoro em todas as coisas, não gostei".
# --sem-sfx desliga TODO efeito sonoro, inclusive o click por palavra dos cards
# (que é automático). Peça fica só voz (+ música, se houver).
SEM_SFX=0
# João 17/09 (v3): "onde aparece o fundo branco você tirou o click, ele poderia ter
# deixado". --click-cards devolve SÓ o click por palavra dos CARDS BRANCOS (o único
# efeito sonoro que ele aprovou), mesmo com --sem-sfx ligado. Whoosh/boom seguem mortos.
CLICK_CARDS=0
while [[ $# -gt 0 ]]; do case "$1" in
  --dir) DIRSB="$2"; shift 2;;
  --gancho) GANCHO="$2"; shift 2;;
  --gancho-dur) GANCHO_DUR="$2"; shift 2;;
  --beats) BEATS="$2"; shift 2;;
  --music) MUSIC="$2"; shift 2;;
  --music-vol) MUSIC_VOL="$2"; shift 2;;
  --music-ss) MUSIC_SS="$2"; shift 2;;          # entra no meio da faixa
  --music-expr) MUSIC_EXPR="$2"; shift 2;;      # volume=volume='EXPR':eval=frame (janelas)
  --sfx) SFX="$2"; shift 2;;                    # "arquivo@tempo[@vol];..."
  --sem-sfx) SEM_SFX=1; shift;;                 # zero SFX (nem click de card)
  --click-cards) CLICK_CARDS=1; shift;;         # exceção: click do card BRANCO volta
  --legy) LEGY="$2"; shift 2;;
  --leg-fontsize) LEG_FS="$2"; shift 2;;
  --leg-maxwords) LEG_MAXW="$2"; shift 2;;
  --leg-lead) LEG_LEAD="$2"; shift 2;;
  --leg-hide) LEG_HIDE="$2"; shift 2;;
  --from) FROM="$2"; shift 2;;
  --video-zoom) VZOOM="$2"; shift 2;;
  --video-offset-x) VOFFX="$2"; shift 2;;
  --video-offset-y) VOFFY="$2"; shift 2;;
  --punch-zoom) PUNCH_Z="$2"; shift 2;;
  --band-h) BAND_H="$2"; shift 2;;
  --band-feather) BAND_FEATHER="$2"; shift 2;;
  --band-pos) BAND_POS="$2"; shift 2;;   # bottom (padrão) | top
  *) echo "flag?: $1"; exit 1;;
esac; done

[[ -z "$DIRSB" ]] && { echo "✗ --dir obrigatório"; exit 1; }
DIR="$(cd "$DIRSB" && pwd)"
JOAO="$DIR/work/joao.mp4"
[[ ! -f "$JOAO" ]] && { echo "✗ não achei $JOAO"; exit 1; }
rel(){ [[ "$1" = /* ]] && echo "$1" || echo "$DIR/$1"; }
# resolve arquivo: absoluto -> sandbox -> pasta do modelo
res(){ if [[ "$1" = /* ]]; then echo "$1"; elif [[ -f "$DIR/$1" ]]; then echo "$DIR/$1"; else echo "$SELF/$1"; fi; }

VC="$(cd "$SELF/../.." && pwd)"; JENV="$VC/../../../app/.env"   # todas as chaves moram em app/.env
OUT_DIR="$VC/output/dividido-mascara"; mkdir -p "$OUT_DIR"
DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$JOAO")
TS="$(date +%Y%m%d-%H%M%S)"; OUT="$OUT_DIR/${TS}.mp4"
WORK="$(mktemp -d /tmp/divmask-XXXXXX)"; trap "rm -rf '$WORK'" EXIT

if [[ "$BAND_POS" == "top" ]]; then BAND_Y=0; else BAND_Y=$(( 1920 - BAND_H )); fi

# --- 1. transcrição ---
WORDS_SAVE="$DIR/work/words.json"
if [[ -f "$WORDS_SAVE" ]]; then cp "$WORDS_SAVE" "$WORK/words.json"; else
  echo "▶ transcrevendo (GROQ)..."
  ffmpeg -i "$JOAO" -vn -ac 1 -ar 16000 "$WORK/audio.wav" -y -loglevel error
  GROQ=$(grep GROQ_API_KEY "$JENV" | head -1 | cut -d= -f2- | tr -d "\"' ")
  VOC="$SELF/../../../../../app/ferramentas/vocabulario.py"   # nome próprio certo (G5): identidade.json -> "palavras"
  VOCPROMPT=$(python3 "$VOC" prompt "$SELF" 2>/dev/null || true)
  curl -s https://api.groq.com/openai/v1/audio/transcriptions -H "Authorization: Bearer $GROQ" \
    -F model="whisper-large-v3" -F language="pt" -F response_format="verbose_json" ${VOCPROMPT:+-F} ${VOCPROMPT:+prompt=$VOCPROMPT} \
    -F 'timestamp_granularities[]=word' -F file="@$WORK/audio.wav" > "$WORK/words.json"
  python3 "$VOC" corrigir "$WORK/words.json" "$SELF" 2>/dev/null || true
  cp "$WORK/words.json" "$WORDS_SAVE"
fi

# --- 2. legendas -> faixa alpha única ---
LEGDIR="$WORK/leg"; mkdir -p "$LEGDIR"
python3 "$SELF/build-legenda.py" --words "$WORK/words.json" --word-offset 0 --t0 "$FROM" \
  --out-dir "$LEGDIR" --legy "$LEGY" --fontsize "$LEG_FS" --maxwords "$LEG_MAXW"
# Faixa de legenda SEM DRIFT e RÁPIDA: concat de clipes com contagem de frames
# EXATA derivada do tempo ABSOLUTO arredondado (não acumula erro como o concat de
# durações independentes) + clipes transparentes nos gaps. LEG_LEAD adianta de fato.
LEGV="$WORK/legs.mov"; : > "$WORK/leglist.txt"
prevf=0; li=0
# PNG 100% transparente p/ os GAPS (pausas sem legenda). O lavfi color=black@0.0
# NÃO gera plano alpha de verdade no ProRes 4444 -> virava PRETO OPACO ("preto do
# nada" nas pausas). Gerar o gap do MESMO jeito que os segmentos (loop de PNG
# transparente) garante o alpha e elimina o flash preto.
TRANSPNG="$WORK/trans.png"
python3 -c "from PIL import Image; Image.new('RGBA',(1080,1920),(0,0,0,0)).save('$TRANSPNG')"
mktrans(){ ffmpeg -nostdin -loop 1 -i "$TRANSPNG" -frames:v "$1" -r 30 \
  -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le -y "$2" -loglevel error; }
while IFS='|' read -r png s e; do
  sf=$(awk -v f="$FROM" -v s="$s" -v l="$LEG_LEAD" 'BEGIN{v=f+s-l; if(v<0)v=0; printf "%d", v*30+0.5}')
  ef=$(awk -v f="$FROM" -v e="$e" -v l="$LEG_LEAD" 'BEGIN{v=f+e-l; printf "%d", v*30+0.5}')
  (( sf < prevf )) && sf=$prevf
  (( ef <= sf )) && ef=$((sf+1))
  if (( sf > prevf )); then
    g="$WORK/gap_$(printf '%03d' $li).mov"; mktrans $((sf-prevf)) "$g"; echo "file '$g'" >> "$WORK/leglist.txt"
  fi
  seg="$WORK/lg_$(printf '%03d' $li).mov"
  # --leg-hide "s-e,s-e": se o chunk cai numa janela de hide, vira TRANSPARENTE
  # (remove aquela legenda específica sem mexer nas outras). João 31/07 pediu
  # remover só a legenda "que replica conteúdo ou que faz um post de IA".
  hide=0
  if [[ -n "$LEG_HIDE" ]]; then
    mid=$(awk -v s="$s" -v e="$e" 'BEGIN{printf "%.3f",(s+e)/2}')
    for win in ${(s:,:)LEG_HIDE}; do
      hs=${win%-*}; he=${win#*-}
      if (( $(awk -v m="$mid" -v a="$hs" -v b="$he" 'BEGIN{print (m>=a && m<=b)?1:0}') )); then hide=1; break; fi
    done
  fi
  if (( hide )); then
    mktrans $((ef-sf)) "$seg"
  else
    ffmpeg -nostdin -loop 1 -i "$png" -frames:v $((ef-sf)) -r 30 \
      -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le -y "$seg" -loglevel error
  fi
  echo "file '$seg'" >> "$WORK/leglist.txt"; prevf=$ef; li=$((li+1))
done < "$LEGDIR/manifest.txt"
ffmpeg -nostdin -f concat -safe 0 -i "$WORK/leglist.txt" -c copy -y "$LEGV" -loglevel error

# --- 3. máscara da faixa (feather no TOPO) + sombra ---
python3 - "$WORK/bandmask.png" "$WORK/bandshadow.png" "$BAND_H" "$BAND_FEATHER" "$BAND_Y" "$BAND_POS" <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFilter
mask_p, sh_p, band_h, feather, band_y = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
pos = sys.argv[6] if len(sys.argv) > 6 else "bottom"
W=1080
m=Image.new("L",(W,band_h),255); d=ImageDraw.Draw(m)
for i in range(feather):
    a=int(round(255*(i/max(1,feather-1))))
    # faixa embaixo -> esfuma a BORDA DE CIMA; faixa em cima -> esfuma a BORDA DE BAIXO
    y = i if pos=="bottom" else band_h-1-i
    d.line([(0,y),(W,y)],fill=a)
m.save(mask_p)
sh=Image.new("RGBA",(W,1920),(0,0,0,0)); d=ImageDraw.Draw(sh)
top = (band_y-70) if pos=="bottom" else (band_y+band_h-170)
for i in range(240):
    y=top+i
    if 0<=y<1920:
        a=int(round(150*(1-i/239)))
        if pos=="top": a=int(round(150*(i/239)))
        d.line([(0,y),(W,y)],fill=(0,0,0,a))
sh=sh.filter(ImageFilter.GaussianBlur(30)); sh.save(sh_p)
print(f"  bandmask {m.size} feather={feather} pos={pos} bandshadow y={band_y}")
PY
# --- 4. base João (tela cheia, esconde a calça) ---
SCW=$(awk -v z="$VZOOM" 'BEGIN{printf "%d",1080*z+0.5}')
SCH=$(awk -v z="$VZOOM" 'BEGIN{printf "%d",1920*z+0.5}')
CRX=$(( (SCW-1080)/2 + VOFFX )); [[ $CRX -lt 0 ]] && CRX=0; [[ $CRX -gt $((SCW-1080)) ]] && CRX=$((SCW-1080))
CRY=$VOFFY; [[ $CRY -lt 0 ]] && CRY=0; [[ $CRY -gt $((SCH-1920)) ]] && CRY=$((SCH-1920))
# punch = push-in SUAVE mantendo a MESMA composição da base (não fecha no rosto).
# PUNCH_Z é MULTIPLICADOR do zoom da base (ex 1.18 = 18% mais perto).
PZ=$(awk -v b="$VZOOM" -v m="$PUNCH_Z" 'BEGIN{printf "%.4f", b*m}')
PSCW=$(awk -v z="$PZ" 'BEGIN{printf "%d",1080*z+0.5}')
PSCH=$(awk -v z="$PZ" 'BEGIN{printf "%d",1920*z+0.5}')
PCRX=$(( (PSCW-1080)/2 + VOFFX )); [[ $PCRX -lt 0 ]] && PCRX=0; [[ $PCRX -gt $((PSCW-1080)) ]] && PCRX=$((PSCW-1080))
FC=$(awk -v o="$VOFFY" -v sch="$SCH" 'BEGIN{printf "%.5f",(o+960)/sch}')
PCRY=$(awk -v fc="$FC" -v psch="$PSCH" 'BEGIN{v=fc*psch-960; if(v<0)v=0; printf "%d", v}')
[[ $PCRY -gt $((PSCH-1920)) ]] && PCRY=$((PSCH-1920))

# --- 5. monta filtro do corpo ---
INPUTS=(-i "$JOAO" -i "$LEGV" -loop 1 -i "$WORK/bandmask.png" -loop 1 -i "$WORK/bandshadow.png")
IDX=4   # próximo índice de input livre
F="[0:v]scale=${SCW}:${SCH},crop=1080:1920:${CRX}:${CRY},fps=30,setsar=1[base];"
V="[base]"

typeset -a BROLL PUNCH CARD
if [[ -n "$BEATS" ]]; then
  for b in ${(s:;:)BEATS}; do
    [[ -z "$b" ]] && continue
    typ=${b%%:*}; r1=${b#*:}; rng=${r1%%:*}; arg=""; [[ "$r1" == *:* ]] && arg=${r1#*:}
    s=${rng%-*}; e=${rng#*-}
    case "$typ" in
      broll) BROLL+=("$s|$e|$arg");;
      punch) PUNCH+=("$s|$e");;
      card)  CARD+=("$s|$e|$arg");;
    esac
  done
fi

# 5a. broll (faixa mesclada): sombra + faixa esfumada com PTS deslocado
for it in "${BROLL[@]}"; do
  s=${it%%|*}; rest=${it#*|}; e=${rest%%|*}; arg=${rest#*|}
  file=${arg%@*}; insec=0; [[ "$arg" == *@* ]] && insec=${arg#*@}
  dur=$(awk -v s="$s" -v e="$e" 'BEGIN{printf "%.2f", e-s}')
  INPUTS+=(-ss "$insec" -t "$dur" -i "$(rel "$file")")
  bi=$IDX; IDX=$((IDX+1))
  # sombra (estática) só na janela
  F+="${V}[3:v]overlay=0:0:enable='between(t,${s},${e})'[bs${bi}];"; V="[bs${bi}]"
  # faixa: cover -> feather -> desloca PTS pra aparecer em t=s
  F+="[${bi}:v]scale=1080:${BAND_H}:force_original_aspect_ratio=increase,crop=1080:${BAND_H},format=rgba,setsar=1[bc${bi}];"
  F+="[bc${bi}][2:v]alphamerge,setpts=PTS-STARTPTS+${s}/TB[bm${bi}];"
  F+="${V}[bm${bi}]overlay=0:${BAND_Y}:enable='between(t,${s},${e})':eof_action=pass[bo${bi}];"; V="[bo${bi}]"
done

# 5b. punch (zoom no rosto), opaco.
for it in "${PUNCH[@]}"; do
  s=${it%%|*}; e=${it#*|}
  dur=$(awk -v s="$s" -v e="$e" 'BEGIN{printf "%.2f", e-s}')
  INPUTS+=(-ss "$s" -t "$dur" -i "$JOAO")
  pi=$IDX; IDX=$((IDX+1))
  F+="[${pi}:v]scale=${PSCW}:${PSCH},crop=1080:1920:${PCRX}:${PCRY},fps=30,setsar=1,setpts=PTS-STARTPTS+${s}/TB[pz${pi}];"
  F+="${V}[pz${pi}]overlay=0:0:enable='between(t,${s},${e})':eof_action=pass[po${pi}];"; V="[po${pi}]"
done

# 5c. legenda por cima — SEMPRE visível, INCLUSIVE no punch. João 31/07 mudou de
#     ideia: "mesmo quando dá zoom, põe legenda". Desenhada DEPOIS do punch pra
#     ficar por cima dele. Posição via --legy (topo/acima do cabelo neste vídeo).
F+="${V}[1:v]overlay=0:0[vleg];"; V="[vleg]"

# 5d. cards animados (palavra a palavra + click de mouse) por cima de tudo
ci=0; typeset -a CLICK_TIMES CLICK_TIMES_FILE
for it in "${CARD[@]}"; do
  hs=${it%%|*}; rest=${it#*|}; he=${rest%%|*}; txt=${rest#*|}
  # card pré-montado (mp4): card:s-e:@arquivo.mp4 (ex: logo/rosto). 2 clicks (logo, rosto).
  if [[ "$txt" == @* ]]; then
    cfile=$(res "${txt#@}"); s=$hs; e=$he
    INPUTS+=(-i "$cfile"); di=$IDX; IDX=$((IDX+1))
    F+="[${di}:v]setpts=PTS-STARTPTS+${s}/TB[csh${di}];"
    F+="${V}[csh${di}]overlay=0:0:enable='between(t,${s},${e})':eof_action=pass[cd${di}];"; V="[cd${di}]"
    # sidecar <arquivo>.clicks (build-cardkit.py --times): 1 click por palavra,
    # nos offsets relativos ao início do card. Sem sidecar = 2 clicks fixos.
    if [[ -f "$cfile.clicks" ]]; then
      for off in $(cat "$cfile.clicks"); do
        CLICK_TIMES+=("$(awk -v s="$s" -v o="$off" 'BEGIN{printf "%.3f", s+o}')")
      done
    else
      CLICK_TIMES_FILE+=("$(awk -v s="$s" 'BEGIN{printf "%.3f", s+0.30}')" "$(awk -v s="$s" 'BEGIN{printf "%.3f", s+1.50}')")
    fi
    ci=$((ci+1)); continue
  fi
  cdir="$WORK/card_${ci}"; mkdir -p "$cdir"
  NW=$(python3 "$SELF/build-card.py" --layers-dir "$cdir" --texto "$txt" | awk '/NWORDS/{print $2}')
  # tempos REAIS das palavras faladas (card aparece exatamente na fala, sem adiantar)
  SYN=$(python3 "$SELF/build-card.py" --sync "$WORK/words.json" --after "$hs" --texto "$txt")
  syn=(${(s: :)SYN}); shift syn   # remove "SYNC"
  s=$(awk -v t="${syn[1]}" 'BEGIN{printf "%.2f", t-0.12}')   # card entra pouco antes da 1ª palavra
  last=${syn[${#syn}]}
  # hold curto após a última palavra = card SNAPPY (João 31/07 quis o card de
  # abertura mais rápido). 0.7 no lugar de 1.1.
  e=$(awk -v l="$last" -v he="$he" 'BEGIN{v=l+0.7; if(he>v)v=he; printf "%.2f", v}')
  dur=$(awk -v s="$s" -v e="$e" 'BEGIN{printf "%.2f", e-s}')
  cinp=(-loop 1 -t "$dur" -i "$cdir/bg.png"); cf="[0:v]fps=30,setsar=1[cb];"; vl="[cb]"; wi=0
  while [[ $wi -lt ${NW:-0} ]]; do
    cinp+=(-loop 1 -t "$dur" -i "$cdir/word_$(printf '%03d' $wi).png")
    abst=${syn[$((wi+1))]}
    rev=$(awk -v a="$abst" -v s="$s" 'BEGIN{v=a-s; if(v<0)v=0; printf "%.2f", v}')
    cf+="[$((wi+1)):v]fps=30,format=rgba,fade=in:st=${rev}:d=0.10:alpha=1,setsar=1[w${wi}];"
    cf+="${vl}[w${wi}]overlay=0:0[cv${wi}];"; vl="[cv${wi}]"
    CLICK_TIMES+=("$abst")
    wi=$((wi+1))
  done
  cf="${cf%;}"
  ffmpeg -nostdin "${cinp[@]}" -filter_complex "$cf" -map "$vl" -t "$dur" -r 30 \
    -pix_fmt yuv420p -c:v libx264 -preset veryfast -crf 20 -y "$WORK/card_${ci}.mp4" -loglevel error
  INPUTS+=(-i "$WORK/card_${ci}.mp4"); di=$IDX; IDX=$((IDX+1))
  F+="[${di}:v]setpts=PTS-STARTPTS+${s}/TB[csh${di}];"
  F+="${V}[csh${di}]overlay=0:0:enable='between(t,${s},${e})':eof_action=pass[cd${di}];"; V="[cd${di}]"
  ci=$((ci+1))
done
F="${F%;}"

# --- 6. áudio: voz + música baixa + clicks dos cards ---
AF="[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[va];"; AMIX="[va]"; NMIX=1
if [[ -n "$MUSIC" ]]; then
  MUSIC="$(res "$MUSIC")"; INPUTS+=(-ss "$MUSIC_SS" -i "$MUSIC"); mi=$IDX; IDX=$((IDX+1))
  if [[ -n "$MUSIC_EXPR" ]]; then
    # João 17/09: música de IMPACTO, não cama contínua — o volume é uma CURVA em t
    # (silêncio no gancho, entra em fade, sobe no beat de impacto, fade-out no fim).
    AF+="[${mi}:a]volume=volume='${MUSIC_EXPR}':eval=frame,aloop=loop=-1:size=2e9[mb];"
  else
    # cama CONSTANTE com fade de entrada/saída. Não confundir com "música em janelas"
    # (curva desenhada em t), que o João reprovou em 17/09 — aqui é só a cama entrando
    # e saindo suave, no volume dele. João 17/09 (v3): "a música sumiu agoraaa".
    MFO=$(awk -v d="$DUR" 'BEGIN{v=d-1.5; if(v<0)v=0; printf "%.2f", v}')
    AF+="[${mi}:a]volume=${MUSIC_VOL},aloop=loop=-1:size=2e9,afade=t=in:st=0:d=1.5,afade=t=out:st=${MFO}:d=1.5[mb];"
  fi
  AMIX+="[mb]"; NMIX=$((NMIX+1))
fi
# quais clicks realmente tocam:
#   SEM_SFX=0                    -> todos (comportamento antigo)
#   --sem-sfx                    -> nenhum
#   --sem-sfx + --click-cards    -> SÓ o click por palavra do card BRANCO. O card de
#                                   ARQUIVO sem sidecar (ex: beat de impacto fullscreen)
#                                   NÃO tem fundo branco, então fica mudo.
typeset -a CK_PLAY
if [[ $SEM_SFX -eq 0 ]]; then
  CK_PLAY=("${CLICK_TIMES[@]}" "${CLICK_TIMES_FILE[@]}")
elif [[ $CLICK_CARDS -eq 1 ]]; then
  CK_PLAY=("${CLICK_TIMES[@]}")
fi
ck=0
for t in "${CK_PLAY[@]}"; do
  INPUTS+=(-i "$CLICK"); ai=$IDX; IDX=$((IDX+1))
  ms=$(awk -v t="$t" 'BEGIN{printf "%d", t*1000}')
  AF+="[${ai}:a]adelay=${ms}|${ms},volume=0.55[ck${ck}];"; AMIX+="[ck${ck}]"; NMIX=$((NMIX+1)); ck=$((ck+1))
done
# SFX pontuais: whoosh na entrada de cada b-roll, boom no beat de impacto.
sx=0
if [[ $SEM_SFX -eq 1 ]]; then SFX=""; fi
if [[ -n "$SFX" ]]; then
  for it in ${(s:;:)SFX}; do
    [[ -z "$it" ]] && continue
    sfile=${it%%@*}; rest=${it#*@}; st=${rest%%@*}; svol="0.8"
    [[ "$rest" == *@* ]] && svol=${rest#*@}
    sfile="$(res "$sfile")"
    INPUTS+=(-i "$sfile"); ai=$IDX; IDX=$((IDX+1))
    ms=$(awk -v t="$st" 'BEGIN{printf "%d", t*1000}')
    AF+="[${ai}:a]adelay=${ms}|${ms},volume=${svol}[sx${sx}];"; AMIX+="[sx${sx}]"
    NMIX=$((NMIX+1)); sx=$((sx+1))
  done
fi
if [[ $NMIX -eq 1 ]]; then
  AOUT="[va]"; FULL="${AF%;}"
else
  # alimiter: com click/SFX somando por cima da voz o pico passa de 0 dBFS e estoura.
  # O limiter só age nos picos, não achata a cama. level=0 é OBRIGATÓRIO (o auto-level
  # padrão renormaliza e SOBE a loudness). Teto 0.71 (-3 dBFS): medido em 17/09 que o
  # AAC 128k do encode final devolve ~+1,2 dB de overshoot, então 0.89 saía a +0,0 dBTP.
  # Com 0.71 -> -2,1 dBTP, mesma loudness (-15,6 LUFS) e o click continua audível.
  FULL="${AF}${AMIX}amix=inputs=${NMIX}:duration=first:dropout_transition=0:normalize=0[amx];[amx]alimiter=limit=0.71:level=0:attack=5:release=60[aout]"; AOUT="[aout]"
fi
echo "▶ corpo..."
ffmpeg "${INPUTS[@]}" -filter_complex "${F};${FULL}" -map "${V}" -map "${AOUT}" -t "$DUR" \
  -c:v h264_videotoolbox -b:v 8M -c:a aac -b:a 128k -movflags +faststart -y "$WORK/body.mp4" -loglevel error

# --- 7. gancho + concat ---
if [[ -n "$GANCHO" ]]; then
  GANCHO="$(rel "$GANCHO")"
  echo "▶ gancho (${GANCHO_DUR}s)..."
  ffmpeg -t "$GANCHO_DUR" -i "$GANCHO" \
    -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1" \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
    -c:v h264_videotoolbox -b:v 8M -c:a aac -b:a 128k -movflags +faststart -y "$WORK/intro.mp4" -loglevel error
  ffmpeg -i "$WORK/intro.mp4" -i "$WORK/body.mp4" \
    -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]" -map "[v]" -map "[a]" \
    -c:v h264_videotoolbox -b:v 8M -c:a aac -b:a 128k -movflags +faststart -y "$OUT" -loglevel error
else
  cp "$WORK/body.mp4" "$OUT"
fi
echo "✓ $OUT"
