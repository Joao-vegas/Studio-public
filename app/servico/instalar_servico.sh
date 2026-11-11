#!/usr/bin/env bash
# instalar_servico.sh — deixa o Estúdio ATIVO O TEMPO INTEIRO (LaunchAgent do macOS).
set -e
LABEL="com.joao.estudio"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
BASE="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$(command -v python3)"
if [ -x "${BASE}/app/.venv/bin/python" ]; then PY="${BASE}/app/.venv/bin/python"; fi
LOGDIR="${BASE}/app/servico/logs"; mkdir -p "$LOGDIR"
NODE_DIR="$(dirname "$(command -v npx 2>/dev/null || echo /usr/local/bin/npx)")"
SVC_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${NODE_DIR}:$HOME/.npm-global/bin:$HOME/.claude/local:$HOME/.local/bin"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>${PY}</string><string>${BASE}/app/interface/servidor.py</string></array>
  <key>WorkingDirectory</key><string>${BASE}</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>${SVC_PATH}</string><key>PYTHONDONTWRITEBYTECODE</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${LOGDIR}/out.log</string>
  <key>StandardErrorPath</key><string>${LOGDIR}/err.log</string>
</dict>
</plist>
PLISTEOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Serviço instalado. Estúdio em http://localhost:7655 · logs em ${LOGDIR}/"
echo "Desligar de vez: bash ${BASE}/app/servico/desinstalar_servico.sh"
