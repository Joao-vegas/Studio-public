#!/usr/bin/env bash
PLIST="$HOME/Library/LaunchAgents/com.joao.app.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Serviço do Estúdio removido."
