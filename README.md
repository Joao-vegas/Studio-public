# Estúdio

Estúdio de produção de vídeo com IA: Reels, anúncio, documentário, explicador e desenho 3D.
Você manda o vídeo gravado (ou só o roteiro), escolhe formato e cliente, e a IA monta.
Cada correção vira regra, e o mesmo erro não volta.

## Instalar (do zero, num Mac)

```bash
git clone https://github.com/Joao-vegas/Studio-public.git Estudio
cd Estudio
bash instalar.sh
```

O `instalar.sh` instala tudo: Homebrew, Python 3.14 e as bibliotecas, ffmpeg, yt-dlp, tesseract, Node, os motores
**HyperFrames** (HeyGen), **Three.js** e **Remotion**, **Claude Code** e **Codex**, os modelos de IA locais, as fontes
e a skill get-brolls. Passo a passo, chaves e o que fazer se algo falhar: [INSTALAR.md](INSTALAR.md).

Os exemplos de referência dos formatos (vídeos e folhas de quadros de outros criadores) e os clientes reais não vêm
neste repositório: só o cliente neutro `clientes/Avulso`, com todos os modelos prontos.

## Abrir

`bash app/iniciar.command` → http://localhost:7655

Menu: **Início** · **Criar** · **Esperando você** · **Estilos** · **Meus vídeos** · **Clientes** · **Mais** (Conversar, Saídas, Custos, Config…).

## Ideia em 4 linhas (detalhes no `CLAUDE.md`)

- **Formato** (`formatos/<slug>/`) é a receita: `formato.json`, `COMO-FAZER.md`, exemplo, aprendizado.
- **Cliente** (`clientes/<Nome>/`) é só a pele: `identidade.json` (cores, fontes, tom) + `<x>Content/{entrada, material, modelos, output, transcricoes}` (as 5 pastas, cada uma com `.gitkeep`, nascem junto com o cliente: **Novo cliente** na tela ou `app/ferramentas/novo_cliente.py <Nome>` cria sempre isso e nada além; `--completar` cria o que faltar nos que já existem). Sem `.env` (chave só em `app/.env`), sem `automacao` (scripts em `app/automacao/`) e sem banco de imagem/vídeo/música (só no `acervo/`). Confere com `python3 app/ferramentas/clientes_padrao.py`.
- **Regras em 3 camadas**: modelo do cliente > formato > geral (`REGRAS.md`). O briefing vale só para aquele vídeo.
- **Motor**: gravado → ffmpeg + PIL; animação → HTML próprio (HyperFrames só opcional); sem Remotion (aposentado em 29-out-2026; sobrou só dentro do formato Mundo 3d).

## Chaves e custos

**Cliente não tem chave.** Todas as chaves (Anthropic, OpenAI, Groq, kie.ai, Pexels, Pixabay, Freesound) ficam em
`app/.env`, que nunca vai pro Git. Mapa só com nomes em [`app/CHAVES.md`](app/CHAVES.md).
A aba Custos mostra o **dinheiro que saiu**; o preço de tabela é só referência.

Em **Config** você escolhe, para cada tipo de trabalho, se roda no **plano** (Claude Code) ou na **API** (crédito):
- vídeos pela tela: plano por padrão;
- fila de tarefas grandes (abaixo): API por padrão.

## Fila de tarefas grandes (opcional)

É para quando uma mudança no sistema é grande demais para uma conversa só: várias tarefas de IA em sequência, cada uma com teto em dólar.
`python3 app/ferramentas/via_api.py fila <fila.json> --fundo` roda, `status <pasta>` mostra o andamento, e rodar de novo retoma de onde parou.
Não é necessária para fazer vídeos.

## Ferramentas e repositórios que usamos

Só o que o código usa de verdade (clientes não têm código nem scripts):

| Para quê | O quê | De onde |
|---|---|---|
| A IA que produz o vídeo (pela tela e pela fila) | **Claude Code** (`claude -p`) e, opcional, **Codex** (`codex exec`) | [anthropics/claude-code](https://github.com/anthropics/claude-code) · [openai/codex](https://github.com/openai/codex) |
| Chat de briefing | SDK **anthropic** | [anthropics/anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python) |
| Buscar b-roll (YouTube, Pexels, Pixabay, Commons, NASA), prévia em quadros | skill **get-brolls** (`~/.claude/skills/get-brolls`) | [engenheirodevideo/get-brolls](https://github.com/engenheirodevideo/get-brolls) |
| Baixar por link: referência, trecho de fala, música, item do acervo | **yt-dlp** (o get-brolls também usa por dentro) | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| Cortar, juntar, cor e áudio | **ffmpeg** e **ffprobe** 8.0 | [ffmpeg.org](https://ffmpeg.org) |
| Medir silêncio no corte do bruto | **auto-editor** 29.3 | [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) |
| Transcrever a fala (palavra por palavra) | **Groq** (Whisper, na nuvem) e **mlx-whisper** (no próprio Mac) | [ml-explore/mlx-examples](https://github.com/ml-explore/mlx-examples/tree/main/whisper) |
| HTML vira vídeo, com checagem automática (opcional, nenhum estilo usa hoje) | **HyperFrames** 0.8.x (`app/motores/hyperframes`) | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) |
| Explicador 3D | **Three.js** 0.186 (`app/motores/3d`) | [mrdoob/three.js](https://github.com/mrdoob/three.js) |
| Capturar quadros do HTML e do 3D | **Playwright** 1.62 (Chromium) | [microsoft/playwright-python](https://github.com/microsoft/playwright-python) |
| Recortar a pessoa do fundo | **rembg** | [danielgatis/rembg](https://github.com/danielgatis/rembg) |
| Ampliar foto pequena (Real-ESRGAN), câmera 3D dentro da foto (Depth Anything v2, `parallax: true`) e só a voz do clipe (Demucs, `so_voz: true`) | `app/ferramentas/midia_local.py`: **Real-ESRGAN** ncnn-vulkan, **Depth Anything V2** (onnxruntime), **Demucs** | [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) · [DepthAnything/Depth-Anything-V2](https://github.com/DepthAnything/Depth-Anything-V2) · [facebookresearch/demucs](https://github.com/facebookresearch/demucs) |
| Fontes grátis de foto, vídeo, ícone e música (Commons, Openverse, NASA, Internet Archive, Iconify) | `app/ferramentas/fontes_gratis.py` e `musica_busca.py` (lista e licença em `app/api/uso-direto/FONTES.md`) | APIs abertas |
| Achar rosto e medir nitidez do quadro (documentário, 3D) | **OpenCV** 4.14 | [opencv/opencv-python](https://github.com/opencv/opencv-python) |
| Busca por significado no acervo | **sentence-transformers** + **torch** | [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) |
| Telas do Estúdio | **Flask** | [pallets/flask](https://github.com/pallets/flask) |
| Imagens, números, YAML, HTTP | Pillow, NumPy, PyYAML, requests | PyPI |

Voz: **VoiceStudio** (local, grátis) e, de reserva, **ElevenLabs** (só com chave e voz), chamados direto, sem biblioteca extra. O Gemini saiu em 29-out-2026.
Fora deste repositório, no Mac: a skill **jev** (OpenRouter, triagem barata de texto) e a skill **Gerador de imagem e vídeo**
(kie.ai). Node.js 26 roda os motores; Python 3.14 em `app/.venv`.

Serviços com chave (`app/.env`): Anthropic, OpenAI, Groq (transcrição), kie.ai (imagem e vídeo, só com sua aprovação),
Pexels, Pixabay, Freesound; opcionais: ElevenLabs e Jamendo. Sem chave: Mixkit, SoundCloud, Wikimedia Commons e NASA.
Toda segunda, 4h, `app/ferramentas/atualizar.py` confere versão nova de cada ferramenta da tabela (a lista fica em Config → Atualizações).
yt-dlp, tesseract e as skills atualizam sozinhos e só ficam se passar no teste; o resto só avisa "disponível".

## Testes

`for f in app/tests/test_*.py; do app/.venv/bin/python -m unittest "$f"; done`
(o `discover` completo trava no teste de fumaça dos motores, que usa navegador.)

## Versões

Só sobem versões que fazem sentido (`vX.Y.Z`, ver [`CHANGELOG.md`](CHANGELOG.md)). Sem deploy automático.
`CLAUDE.md` é o manual da IA, `SKILL.md` a entrada da skill e `REGRAS.md` o que vale para todo vídeo.
