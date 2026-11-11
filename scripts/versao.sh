#!/usr/bin/env bash
# Marca e publica UMA versão que faz sentido. Uso: scripts/versao.sh 1.1.0
# Exige: árvore limpa, seção "## v<versão>" no CHANGELOG.md, tag ainda inexistente. Não faz push de nada além da tag e da main.
set -euo pipefail
cd "$(dirname "$0")/.."
v="${1:?Informe a versão. Exemplo: scripts/versao.sh 1.1.0}"; tag="v${v#v}"
[ -z "$(git status --porcelain)" ] || { echo "Há mudanças sem commit. Commite antes de marcar versão."; exit 1; }
grep -qE "^## $tag( |$)" CHANGELOG.md || { echo "Falta a seção '## $tag' no CHANGELOG.md."; exit 1; }
git rev-parse "$tag" >/dev/null 2>&1 && { echo "A tag $tag já existe."; exit 1; }
notas="$(awk -v t="## $tag" 'index($0,t)==1{p=1;next} /^## /{p=0} p' CHANGELOG.md)"
git tag -a "$tag" -m "Estúdio $tag"
git push origin main "$tag"
gh release create "$tag" --title "Estúdio $tag" --notes "$notas"
echo "Versão $tag publicada."
