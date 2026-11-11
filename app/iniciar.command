#!/usr/bin/env bash
# Clique duplo: abre a versão atual e substitui uma instância antiga, se necessário.
set -e
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
if [ -x app/.venv/bin/python ]; then
  exec app/.venv/bin/python app/ferramentas/iniciar.py
else
  exec python3 app/ferramentas/iniciar.py
fi
