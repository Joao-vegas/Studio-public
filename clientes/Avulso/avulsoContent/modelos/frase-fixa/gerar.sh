#!/bin/zsh
# MODELO: Frase fixa — Vegas
# Pessoa em tela cheia + UMA frase fixa numa caixa no peito, o vídeo inteiro. Sem legenda da fala, b-roll, música nem efeito.
#
# Sandbox: <modelo>/_sandbox-<slug>/work/joao.mp4 (já cortado: sem silêncio, gaguejo nem erro de começo).
# Uso (de dentro da sandbox): zsh ../gerar.sh --dir . --frase "A FRASE" [--estilo preto|branco] [--posicao peito|cima|auto] [--saida <mp4>]
# Ajustes finos (editor): --cor-caixa #hex --cor-texto #hex --fonte Nome|caminho --tamanho px --y centro-px.
# Grava a camada em <sandbox>/camada.json (a tela "Editar o texto" abre ela); o vídeo limpo (sem a caixa) é o <sandbox>/work/joao.mp4.
# Posição (padrão auto): peito = abaixo do queixo; cima = acima da cabeça (fora da zona de topo do IG);
# auto = detecta o rosto: cabeça abaixo de 1/3 da tela -> cima, senão peito.
# --como <sandbox-irmã>: copia fonte, tamanho, estilo, cores e a caixa (MAIÚSCULAS ou normal) do camada.json da irmã (lote sai igual).
# Saída padrão: vegasContent/output/frase-fixa/<slug>.mp4
set -euo pipefail
SELF="$(cd "$(dirname "$0")" && pwd)"
DIRSB="" ; FRASE="" ; ESTILO="preto" ; POSICAO="auto" ; EXTRA=() ; SAIDA="" ; PREVIA="" ; COMO=""
while [[ $# -gt 0 ]]; do case "$1" in
  --dir) DIRSB="$2"; shift 2;;
  --frase) FRASE="$2"; shift 2;;
  --estilo) ESTILO="$2"; shift 2;;
  --posicao) POSICAO="$2"; shift 2;;
  --cor-caixa|--cor-texto|--fonte|--tamanho|--y|--cliente) EXTRA+=("$1" "$2"); shift 2;;
  --como) COMO="$2"; shift 2;;
  --previa) PREVIA="1"; shift;;   # só um quadro do meio com a caixa: <sandbox>/storyboard.jpg
  --saida) SAIDA="$2"; shift 2;;
  *) echo "flag?: $1"; exit 1;;
esac; done
[[ -z "$DIRSB" ]] && { echo "✗ --dir obrigatório"; exit 1; }
[[ -z "$FRASE" ]] && { echo "✗ --frase obrigatória"; exit 1; }
[[ "$ESTILO" == "preto" || "$ESTILO" == "branco" ]] || { echo "✗ --estilo: preto ou branco"; exit 1; }
DIR="$(cd "$DIRSB" && pwd)"
if [[ -n "$COMO" ]]; then
  [[ -f "$COMO/camada.json" ]] || { echo "✗ --como: não achei $COMO/camada.json"; exit 1; }
  COPIA=("${(@f)$(python3 - "$COMO/camada.json" "$FRASE" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); f = sys.argv[2]
print(f.upper() if c["texto"].isupper() else f)
print(c.get("estilo", "preto")); print(c["fonte"]); print(c["tamanho"]); print(c["cor_caixa"]); print(c["cor_texto"])
PY
)}")
  FRASE="${COPIA[1]}"; ESTILO="${COPIA[2]}"; EXTRA+=(--fonte "${COPIA[3]}" --tamanho "${COPIA[4]}" --cor-caixa "${COPIA[5]}" --cor-texto "${COPIA[6]}")
fi
JOAO="$DIR/work/joao.mp4"
[[ ! -f "$JOAO" ]] && { echo "✗ não achei $JOAO"; exit 1; }
SLUG="${${DIR:t}#_sandbox-}"
VC="$(cd "$SELF/../.." && pwd)"
CLIENTE="${VC:h:t}"   # clientes/<Nome>/<x>Content: o nome vem do caminho, nunca fixo
if [[ -n "$PREVIA" ]]; then SAIDA="$DIR/storyboard.jpg"; elif [[ -z "$SAIDA" ]]; then mkdir -p "$VC/output/frase-fixa"; SAIDA="$VC/output/frase-fixa/${SLUG}.mp4"; else mkdir -p "${SAIDA:h}"; fi
WORK="$(mktemp -d /tmp/frase-fixa-XXXXXX)"; trap "rm -rf '$WORK'" EXIT
# o desenho é o do editor (app/ferramentas/camada.py): build-caixa.py grava <sandbox>/camada.json e o render é o dele
[[ -n "$PREVIA" ]] && SAIDA_CJ="$VC/output/frase-fixa/${SLUG}.mp4" || SAIDA_CJ="$SAIDA"
mkdir -p "${SAIDA_CJ:h}"
python3 "$SELF/build-caixa.py" --dir "$DIR" --frase "$FRASE" --estilo "$ESTILO" --posicao "$POSICAO" --cliente "$CLIENTE" "${EXTRA[@]}" \
  --saida "$SAIDA_CJ" --png "$WORK/caixa.png" >/dev/null
if [[ -n "$PREVIA" ]]; then
  DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$JOAO")
  ffmpeg -y -v error -ss "$(awk -v d="$DUR" 'BEGIN{printf "%.2f", d/2}')" -i "$JOAO" -i "$WORK/caixa.png" \
    -filter_complex "[0:v]scale=1080:1920:flags=lanczos[b];[b][1:v]overlay=0:0" -frames:v 1 -q:v 3 "$SAIDA"
  echo "$SAIDA"; exit 0
fi
python3 "$SELF/../../../../../app/ferramentas/camada.py" renderizar "$DIR"
# conferência pronta: folha ao lado da do exemplo + bordas da caixa (nada de texto antigo vazando)
mkdir -p "$DIR/qa"
python3 "$SELF/../../../../../app/ferramentas/formatos.py" folha-video "$SAIDA" "$DIR/qa/folha.jpg" >/dev/null || echo "⚠ folha não saiu"
python3 "$SELF/build-caixa.py" --bordas "$DIR" "$SAIDA" "$DIR/qa/caixa-bordas.jpg" || echo "⚠ bordas não saíram"
