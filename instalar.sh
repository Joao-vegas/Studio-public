#!/usr/bin/env bash
# instalar.sh — deixa o Estúdio pronto num Mac, do zero. Rode da pasta do projeto:
#     bash instalar.sh
# Pode rodar de novo quando quiser: o que já está instalado é pulado (ou só atualizado).
# Detalhe de cada passo e o que fazer se algo falhar: INSTALAR.md
set -uo pipefail
cd "$(dirname "$0")"
RAIZ="$PWD"
FALHOU=()

passo() { printf "\n\033[1;33m→ %s\033[0m\n" "$*"; }
ok()    { printf "   \033[32m✓\033[0m %s\n" "$*"; }
aviso() { printf "   \033[31m⚠\033[0m %s\n" "$*"; }
falha() { aviso "$*"; FALHOU+=("$*"); }

[ "$(uname)" = "Darwin" ] || { echo "O Estúdio roda no macOS."; exit 1; }
[ "$(uname -m)" = "arm64" ] || aviso "Mac Intel: a transcrição local (mlx-whisper) não roda; o resto funciona. Use a chave da Groq para transcrever."

# ---------------------------------------------------------------- 1. Homebrew
passo "1/11 Homebrew (instalador de programas do Mac)"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
  [ -x /usr/local/bin/brew ] && eval "$(/usr/local/bin/brew shellenv)"
fi
command -v brew >/dev/null 2>&1 && ok "brew $(brew --version | head -1 | cut -d' ' -f2)" || { aviso "Homebrew não instalou. Instale em https://brew.sh e rode de novo."; exit 1; }

# ---------------------------------------------------------------- 2. Programas do sistema
passo "2/11 Programas do sistema: Python 3.14, Node, ffmpeg, yt-dlp, tesseract, git"
for f in python@3.14 node ffmpeg yt-dlp tesseract tesseract-lang git; do
  if brew list --formula "$f" >/dev/null 2>&1; then ok "$f"; else brew install "$f" && ok "$f instalado" || falha "brew install $f"; fi
done
if ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' drawtext '; then
  ok "ffmpeg com drawtext"
else
  aviso "ffmpeg sem o filtro drawtext: as folhas de prévia saem sem o tempo escrito (o vídeo final não depende disso)."
  aviso "Para ter: brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg"
fi

# ---------------------------------------------------------------- 3. Python do Estúdio
passo "3/11 Python do Estúdio (app/.venv) com todas as bibliotecas (app/requirements.txt)"
PYBASE="$(brew --prefix python@3.14 2>/dev/null)/bin/python3.14"
[ -x "$PYBASE" ] || PYBASE="$(command -v python3.14 || command -v python3)"
if [ ! -x app/.venv/bin/python ]; then "$PYBASE" -m venv app/.venv && ok "venv criado" || falha "criar app/.venv"; fi
if [ -x app/.venv/bin/python ]; then
  app/.venv/bin/python -m pip install --quiet --upgrade pip
  if [ "$(uname -m)" = "arm64" ]; then REQ=app/requirements.txt
  else REQ="$(mktemp)"; grep -v -E '^mlx' app/requirements.txt > "$REQ"; fi
  app/.venv/bin/python -m pip install --quiet -r "$REQ" && ok "bibliotecas do Python ($(grep -c -v '^#' app/requirements.txt))" || falha "pip install -r app/requirements.txt"
fi

# ---------------------------------------------------------------- 4. Playwright
passo "4/11 Navegador do Playwright (captura os quadros do HTML e do 3D)"
app/.venv/bin/python -m playwright install chromium >/dev/null 2>&1 && ok "Chromium do Playwright" || falha "playwright install chromium"

# ---------------------------------------------------------------- 5. Motores Node
passo "5/11 Motores de vídeo em Node: HyperFrames (HeyGen), Three.js e Remotion"
for pasta in app/motores/hyperframes app/motores/3d formatos/mundo-3d/base/remotion; do
  if [ -f "$pasta/package.json" ]; then
    ( cd "$pasta" && { [ -f package-lock.json ] && npm ci --no-audit --no-fund --silent || npm install --no-audit --no-fund --silent; } ) \
      && ok "$pasta" || falha "npm install em $pasta"
  fi
done
SK=app/motores/hyperframes/skills-oficiais
if [ -d "$SK/.git" ]; then git -C "$SK" pull --quiet --ff-only && ok "skills oficiais do HyperFrames atualizadas"
else git clone --quiet --depth 1 https://github.com/heygen-com/hyperframes.git "$SK" && ok "skills oficiais do HyperFrames (heygen-com/hyperframes)" || falha "git clone heygen-com/hyperframes"; fi

# ---------------------------------------------------------------- 6. IAs de linha de comando
passo "6/11 IAs que produzem os vídeos: Claude Code (principal) e Codex (opcional, também gera imagem)"
for pkg in @anthropic-ai/claude-code @openai/codex; do
  bin=$([ "$pkg" = "@openai/codex" ] && echo codex || echo claude)
  if command -v "$bin" >/dev/null 2>&1; then ok "$bin $("$bin" --version 2>/dev/null | head -1)"
  else npm install -g "$pkg" --silent && ok "$bin instalado" || falha "npm install -g $pkg (se der permissão negada: npm config set prefix ~/.npm-global e ponha ~/.npm-global/bin no PATH)"; fi
done

# ---------------------------------------------------------------- 7. Modelos de IA locais
passo "7/11 Modelos de IA que rodam no próprio Mac (vão para app/modelos-locais, ~1,6 GB, só na 1ª vez)"
export OPENCV_OPENCL_RUNTIME=disabled
app/.venv/bin/python app/ferramentas/casar_imagem.py baixar >/dev/null 2>&1 && ok "rosto (YuNet, SFace) e CLIP (casar imagem com a fala)" || falha "casar_imagem.py baixar"
app/.venv/bin/python app/ferramentas/midia_local.py baixar >/dev/null 2>&1 && ok "Real-ESRGAN (ampliar foto) e Depth Anything V2 (câmera 3D na foto)" || falha "midia_local.py baixar"
app/.venv/bin/python -c "from rembg import new_session; new_session('u2net'); new_session('u2netp')" >/dev/null 2>&1 && ok "rembg (recortar a pessoa do fundo)" || falha "modelo do rembg"
ok "Whisper (mlx) e Demucs baixam o modelo sozinhos no primeiro uso"

# ---------------------------------------------------------------- 8. Fontes
passo "8/11 Fontes que os estilos usam (~/Library/Fonts)"
FD="$HOME/Library/Fonts"; mkdir -p "$FD"
fonte() {  # arquivo-esperado  id-no-fontsource  peso
  [ -f "$FD/$1" ] && { ok "$1"; return; }
  curl -fsSL "https://cdn.jsdelivr.net/fontsource/fonts/$2@latest/latin-$3-normal.ttf" -o "$FD/$1" && ok "$1" || falha "fonte $1"
}
fonte BebasNeue-Regular.ttf bebas-neue 400
fonte Anton-Regular.ttf anton 400
fonte Barlow-Regular.ttf barlow 400
fonte Barlow-Medium.ttf barlow 500
fonte Barlow-SemiBold.ttf barlow 600
fonte Barlow-Black.ttf barlow 900
fonte Poppins-Light.ttf poppins 300
fonte Poppins-Regular.ttf poppins 400
fonte Poppins-Medium.ttf poppins 500
fonte Poppins-SemiBold.ttf poppins 600
fonte Poppins-Bold.ttf poppins 700
fonte Inter-SemiBold.otf inter 600
fonte Inter-Bold.otf inter 700
fonte InterDisplay-Regular.otf inter 400
fonte Roboto-Black.ttf roboto 900
fonte PlayfairDisplay-Bold.ttf playfair-display 700
fonte LeagueSpartan-Bold.otf league-spartan 700
fonte DejaVuSans-Bold.ttf dejavu-sans 700
for sis in /System/Library/Fonts/Helvetica.ttc /System/Library/Fonts/SFNS.ttf /System/Library/Fonts/Supplemental/Arial.ttf; do
  b=$(basename "$sis"); [ -f "$FD/$b" ] || { [ -f "$sis" ] && cp "$sis" "$FD/$b"; }; [ -f "$FD/$b" ] && ok "$b (do macOS)"
done
for paga in Gilroy-ExtraBold.otf Gotham-Bold.otf Gotham-Black.otf; do
  [ -f "$FD/$paga" ] && ok "$paga" || aviso "$paga é fonte paga: só um estilo antigo usa; sem ela, ele cai numa fonte parecida"
done

# ---------------------------------------------------------------- 9. Skill get-brolls
passo "9/11 Skill get-brolls (busca de b-roll no YouTube, Pexels, Pixabay, Commons, NASA)"
GB="$HOME/.claude/skills/get-brolls"
if [ ! -d "$GB" ]; then git clone --quiet --depth 1 https://github.com/engenheirodevideo/get-brolls.git "$GB" || falha "git clone get-brolls"; fi
if [ -d "$GB" ]; then bash "$GB/scripts/install.sh" >/dev/null 2>&1 && ok "get-brolls" || falha "instalação do get-brolls ($GB/scripts/install.sh)"; fi

# ---------------------------------------------------------------- 10. Chaves e voz
passo "10/11 Chaves das APIs e voz"
if [ ! -f app/.env ]; then cp app/.env.example app/.env && ok "app/.env criado a partir do modelo (preencha as chaves)"; else ok "app/.env já existe"; fi
aviso "Abra app/.env e cole as chaves. Pra que serve cada uma e onde pegar: app/CHAVES.md"
aviso "Claude Code: rode 'claude' uma vez no Terminal para entrar na sua conta."
if [ -d /Applications/VoiceStudio.app ]; then ok "VoiceStudio (voz local)"
else aviso "Voz local (opcional): baixe o VoiceStudio em https://github.com/debpalash/VoiceStudio/releases e arraste para Aplicativos. Sem ele, use ElevenLabs (chave no app/.env)."; fi

# ---------------------------------------------------------------- 11. Conferência
passo "11/11 Conferência final"
app/.venv/bin/python -c "import flask, anthropic, numpy, PIL, yaml, requests, cv2, rembg, sentence_transformers, playwright.sync_api" 2>/dev/null \
  && ok "bibliotecas do Python carregam juntas" || falha "alguma biblioteca do Python não carregou (rode: app/.venv/bin/python -c 'import cv2, rembg, sentence_transformers')"
for b in ffmpeg ffprobe yt-dlp tesseract node npm claude; do command -v "$b" >/dev/null 2>&1 && ok "$b" || falha "$b não está no PATH"; done
chmod +x app/iniciar.command 2>/dev/null

echo
if [ ${#FALHOU[@]} -eq 0 ]; then
  printf "\033[1;32m✅ Estúdio pronto.\033[0m Para abrir: bash app/iniciar.command  →  http://localhost:7655\n"
else
  printf "\033[1;31mTerminou com %d pendência(s):\033[0m\n" "${#FALHOU[@]}"; for f in "${FALHOU[@]}"; do echo "   - $f"; done
  echo "Resolva (veja INSTALAR.md) e rode 'bash instalar.sh' de novo: ele só refaz o que faltou."
fi
