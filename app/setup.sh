#!/usr/bin/env bash
# setup.sh — instala o que o Estúdio precisa. Roda uma vez.
set -e
cd "$(dirname "$0")/.."
pip_inst() { python3 -m pip install --quiet --upgrade "$@" 2>/dev/null || python3 -m pip install --quiet --upgrade --break-system-packages "$@"; }
echo "→ 1/4 Flask e acabamento de imagens"; pip_inst flask pillow
echo "→ 2/4 auto-editor (mede o espaço morto do bruto no corte)"; pip_inst auto-editor
echo "→ 3/4 ffmpeg / yt-dlp / claude"
for bin in ffmpeg ffprobe yt-dlp claude; do command -v "$bin" >/dev/null 2>&1 && echo "   ✓ $bin" || echo "   ⚠ $bin não encontrado (brew install $bin)"; done
ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' drawtext ' && echo "   ✓ ffmpeg com drawtext" || echo "   ⚠ ffmpeg SEM drawtext: contact sheet do get-brolls sai sem número/timecode (brew reinstall ffmpeg)"
echo "→ 4/4 skill get-brolls (~/.claude/skills/get-brolls)"
GB="$HOME/.claude/skills/get-brolls"
if [ ! -d "$GB" ]; then git clone --depth 1 https://github.com/engenheirodevideo/get-brolls.git "$GB"; fi
if [ ! -x "$GB/.venv/bin/python" ]; then bash "$GB/scripts/install.sh"; else echo "   ✓ já instalada"; fi
echo ""; echo "✅ Pronto. Abrir: bash app/iniciar.command  (http://localhost:7655)"
