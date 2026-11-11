# Chaves do Estúdio (só nomes, nunca valores)

Atualizado em 10-out-2026. **Todas as chaves ficam num lugar só: `app/.env`.** O código lê de lá
(`app/ferramentas/chaves.py`). Modelo do arquivo, sem valores: `app/.env.example`.
Backup dos `.env` de antes da mudança: `~/.config/estudio/backups/env-2026-10-10/`.

| Chave | Pra que serve | Custo | Onde pegar |
|---|---|---|---|
| GEMINI_API_KEY_1..7 | **sem uso desde 29-out-2026** (o Gemini saiu do Estúdio; as chaves ficam no arquivo, nada as lê) | — | — |
| KIE_API_KEY | imagem e vídeo por IA (kie.py) | pago, só com aprovação | https://kie.ai/api-key |
| GROQ_API_KEY | transcrição da fala e corte inteligente | grátis com limite | https://console.groq.com/keys |
| OPENAI_API_KEY | lista de modelos GPT (não gasta) | pago se usar | https://platform.openai.com/api-keys |
| PEXELS_API_KEY | b-roll em banco de vídeo | grátis | pexels.com/api |
| PIXABAY_API_KEY | b-roll em banco de vídeo | grátis | pixabay.com/api/docs |
| FREESOUND_API_KEY | efeitos sonoros | grátis | freesound.org/apiv2/apply |
| ELEVENLABS_API_KEY | voz reserva (só com chave e voz) | assinatura | https://elevenlabs.io/app/settings/api-keys |
| JAMENDO_CLIENT_ID | música com licença livre (opcional) | grátis | devportal.jamendo.com |

**Fora do `app/.env`, de propósito:**
- `~/.config/estudio/anthropic_api_key` e `openai_api_key`: só pra "Cobrar da API" (cartão em Configurações).
  Ficam separadas pra o Claude e o Codex nunca passarem a cobrar sozinhos.
- Jev/OpenRouter fica na skill `jev`.

**Ordem de leitura:** `app/.env` → ambiente. Cliente não tem `.env`.
O valor nunca vai pro ambiente do processo nem aparece na tela: só nome, "configurada" e um hash curto.

**Comandos** (mostram só nomes e hash):
- `python3 app/ferramentas/chaves.py listar`: onde cada chave está e se as cópias são iguais.
- `python3 app/ferramentas/chaves.py sincronizar`: copia PEXELS/PIXABAY pra skill get-brolls e KIE pro
  Gerador de imagem e vídeo, pra elas funcionarem fora do Estúdio. Rode depois de trocar uma dessas no `app/.env`.
- `python3 app/ferramentas/chaves.py limpar-clientes`: lista as linhas repetidas nos `.env` dos clientes.
  Só tira com `--sim` (faz backup antes em `~/.config/estudio/backups/`).

Cliente novo não ganha `.env`: usa o `app/.env`.
Sem chave: Mixkit, YouTube (yt-dlp), SoundCloud, Wikimedia Commons, NASA.
