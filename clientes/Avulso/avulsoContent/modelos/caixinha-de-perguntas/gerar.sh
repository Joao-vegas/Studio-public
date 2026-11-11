#!/bin/zsh
# MODELO: Caixinha de perguntas — Vegas
# Pessoa em tela cheia respondendo + a caixa de pergunta do Stories do Instagram (faixa escura com o título + parte
# branca com a pergunta), fixa o vídeo inteiro. Sem legenda da fala, b-roll, música nem efeito.
#
# Sandbox: <modelo>/_sandbox-<slug>/work/joao.mp4 (já cortado: sem silêncio, gaguejo nem erro de começo).
# Uso (de dentro da sandbox): zsh ../gerar.sh --dir . --pergunta "A PERGUNTA" [--titulo "O que você quer saber?"]
#                             [--posicao cima|peito] [--topo px] [--previa] [--saida <mp4>]
# Grava a camada em <sandbox>/camada.json ("tipo": "caixinha"): a tela "Editar o texto" troca a pergunta, o título e a
# altura depois do vídeo pronto. Fonte (SF Pro), tamanho e margens são fixos no app/ferramentas/caixinha.py.
# Saída padrão: <x>Content/output/caixinha-de-perguntas/<slug>.mp4
set -euo pipefail
SELF="$(cd "$(dirname "$0")" && pwd)"
DIRSB="" ; PERGUNTA="" ; TITULO="O que você quer saber?" ; POSICAO="cima" ; TOPO=() ; SAIDA="" ; PREVIA=""
while [[ $# -gt 0 ]]; do case "$1" in
  --dir) DIRSB="$2"; shift 2;;
  --pergunta) PERGUNTA="$2"; shift 2;;
  --titulo) TITULO="$2"; shift 2;;
  --posicao) POSICAO="$2"; shift 2;;
  --topo) TOPO=(--topo "$2"); shift 2;;
  --previa) PREVIA="1"; shift;;   # só um quadro do meio com a caixa: <sandbox>/storyboard.jpg
  --saida) SAIDA="$2"; shift 2;;
  *) echo "flag?: $1"; exit 1;;
esac; done
[[ -z "$DIRSB" ]] && { echo "✗ --dir obrigatório"; exit 1; }
[[ -z "$PERGUNTA" ]] && { echo "✗ --pergunta obrigatória"; exit 1; }
DIR="$(cd "$DIRSB" && pwd)"
JOAO="$DIR/work/joao.mp4"
[[ ! -f "$JOAO" ]] && { echo "✗ não achei $JOAO"; exit 1; }
SLUG="${${DIR:t}#_sandbox-}"
VC="$(cd "$SELF/../.." && pwd)"
[[ -z "$SAIDA" ]] && SAIDA="$VC/output/caixinha-de-perguntas/${SLUG}.mp4"
mkdir -p "${SAIDA:h}"
WORK="$(mktemp -d /tmp/caixinha-XXXXXX)"; trap "rm -rf '$WORK'" EXIT
python3 "$SELF/build-caixinha.py" --dir "$DIR" --pergunta "$PERGUNTA" --titulo "$TITULO" --posicao "$POSICAO" "${TOPO[@]}" \
  --saida "$SAIDA" --png "$WORK/caixa.png"
if [[ -n "$PREVIA" ]]; then
  DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$JOAO")
  ffmpeg -y -v error -ss "$(awk -v d="$DUR" 'BEGIN{printf "%.2f", d/2}')" -i "$JOAO" -i "$WORK/caixa.png" \
    -filter_complex "[0:v]scale=1080:1920:flags=lanczos[b];[b][1:v]overlay=0:0" -frames:v 1 -q:v 3 "$DIR/storyboard.jpg"
  echo "$DIR/storyboard.jpg"; exit 0
fi
# o render é o do editor (voz nivelada, 0,3 s de silêncio no fim): o mesmo que sai quando o João edita o texto
python3 "$SELF/../../../../../app/ferramentas/camada.py" renderizar "$DIR"
mkdir -p "$DIR/qa"
python3 "$SELF/../../../../../app/ferramentas/formatos.py" folha-video "$SAIDA" "$DIR/qa/folha.jpg" >/dev/null || echo "⚠ folha não saiu"
