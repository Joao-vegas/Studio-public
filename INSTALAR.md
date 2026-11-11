# Instalar o Estúdio

Estúdio de vídeo com IA: Reels, anúncio, documentário, explicador 3D, tela dividida e mais, feitos pelo Claude Code
a partir da sua gravação ou do roteiro, com um app local em http://localhost:7655.

## Do zero, em 3 comandos

```bash
git clone https://github.com/Joao-vegas/Studio-public.git Estudio
cd Estudio
bash instalar.sh
```

O `instalar.sh` faz tudo sozinho e pode ser rodado de novo quando quiser (só refaz o que faltou):

| Passo | O que instala | Para quê |
|---|---|---|
| 1 | Homebrew | instalador de programas do Mac |
| 2 | Python 3.14, Node, ffmpeg, yt-dlp, tesseract, git | cortar e juntar vídeo, baixar por link, ler texto da tela |
| 3 | `app/.venv` com `app/requirements.txt` | Flask (telas), anthropic, OpenCV, rembg, mlx-whisper, sentence-transformers, torch, Demucs, auto-editor, Playwright |
| 4 | Chromium do Playwright | capturar os quadros do HTML e do 3D |
| 5 | **HyperFrames** da HeyGen (`app/motores/hyperframes`), **Three.js** (`app/motores/3d`), **Remotion** (`formatos/mundo-3d/base/remotion`) e as skills oficiais do HyperFrames | motores de vídeo em código |
| 6 | **Claude Code** e **Codex** (npm global) | a IA que produz os vídeos; o Codex é opcional e também gera imagem |
| 7 | Modelos locais em `app/modelos-locais` (~1,6 GB): YuNet e SFace (rosto), CLIP (casar imagem com a fala), Real-ESRGAN (ampliar foto), Depth Anything V2 (câmera 3D na foto), rembg | tudo roda no próprio Mac, sem custo |
| 8 | Fontes em `~/Library/Fonts` (Bebas Neue, Anton, Barlow, Poppins, Inter, Roboto, Playfair, League Spartan, DejaVu; Helvetica, SF e Arial vêm do macOS) | os estilos usam os nomes exatos dos arquivos |
| 9 | Skill **get-brolls** em `~/.claude/skills/get-brolls` | buscar b-roll no YouTube, Pexels, Pixabay, Commons e NASA |
| 10 | `app/.env` a partir de `app/.env.example` | as chaves das APIs |
| 11 | Conferência | testa se tudo carrega junto |

No fim ele mostra "Estúdio pronto" ou a lista do que ficou pendente.

## Depois de instalar

1. **Entre no Claude Code:** rode `claude` uma vez no Terminal e faça o login.
2. **Chaves:** abra `app/.env` e cole as chaves. Pra que serve cada uma e onde pegar: `app/CHAVES.md`.
   - Transcrição: `GROQ_API_KEY` (ou nada, se usar o mlx-whisper local no Apple Silicon)
   - B-roll grátis: `PEXELS_API_KEY`, `PIXABAY_API_KEY`
   - Música e efeito grátis: `FREESOUND_API_KEY`, `JAMENDO_CLIENT_ID`
   - Imagem e vídeo por IA (pago, sempre com sua aprovação): `KIE_API_KEY`
   - Voz clonada (opcional): `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`
3. **Voz local (opcional):** baixe o [VoiceStudio](https://github.com/debpalash/VoiceStudio/releases) e arraste para Aplicativos.
4. **Abrir:** `bash app/iniciar.command` → http://localhost:7655
5. **Seu primeiro cliente:** veja `clientes/README.md` (o `clientes/Avulso` já vem com todos os modelos prontos).

## Requisitos

- macOS, de preferência Apple Silicon (M1 ou mais novo). No Intel tudo roda, menos a transcrição local (mlx).
- ~6 GB livres (bibliotecas, modelos e motores).
- Conta no Claude (Pro ou Max) para o Claude Code.

## Se algo falhar

| Sintoma | O que fazer |
|---|---|
| `npm install -g` com permissão negada | `npm config set prefix ~/.npm-global` e ponha `~/.npm-global/bin` no PATH (`~/.zshrc`) |
| `pip install` falha no torch ou no mlx | confira `python3.14 --version`; no Mac Intel o instalador já pula o mlx |
| Folha de prévia sem o tempo escrito | ffmpeg sem drawtext: `brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg` |
| "Faltam os modelos do CLIP" | `app/.venv/bin/python app/ferramentas/casar_imagem.py baixar` |
| Ampliar foto ou parallax não funciona | `app/.venv/bin/python app/ferramentas/midia_local.py baixar` |
| Remotion (mundo 3D) | `cd formatos/mundo-3d/base/remotion && npm install` |
| HyperFrames | `cd app/motores/hyperframes && npm install` |
| get-brolls | `bash ~/.claude/skills/get-brolls/scripts/install.sh` |
| Fonte faltando num estilo | rode `bash instalar.sh` de novo (passo 8); Gilroy e Gotham são pagas e não vêm |

Atualizações: com o Estúdio aberto, toda segunda às 4h `app/ferramentas/atualizar.py` confere versão nova de cada
ferramenta (Config → Atualizações). Versão pequena instala e testa sozinha; versão grande espera você decidir.
