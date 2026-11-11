# Pesquisa de B-roll — método

A parte mais difícil deste modelo é achar b-roll que **case com o transcript**.
O João fica parado na câmera; **o b-roll embaixo é quem cria a retenção** — então
tem que CHAMAR ATENÇÃO, ter DINAMISMO, e (em conteúdo de marca/produto) **NUNCA
mostrar rosto de pessoa**.

## Passo a passo

1. **Transcrever** o `work/joao.mp4` (whisper) e segmentar por momento/tema.
2. Pra cada momento, identificar o **assunto concreto** (ferramenta, site, marca, conceito).
3. Achar o b-roll por **ordem de prioridade** (sempre sem rosto):

   **a) Ele cita um SITE / produto → capture a TELA do site (melhor opção).**
   ```sh
   ./buscar-broll.sh site https://www.firecrawl.dev firecrawl <sandbox>/brolls
   ```
   Vira um `.png` alto; o `gerar.sh` faz **scroll** automático (parece navegação).
   É o mais garantido: oficial, sem rosto, e sempre casa com o que ele falou.

   **b) CANAL OFICIAL da empresa no YouTube → anúncio / trailer / demo de produto.**
   ```sh
   ./buscar-broll.sh canal "remotion trailer" 10      # lista título :: canal :: link
   ./buscar-broll.sh yt https://youtu.be/XXXX 30-45 remotion <sandbox>/brolls
   ```
   Priorizar vídeos curtos, de produto em uso, **sem rosto**. Confirmar com /watch.

   **c) og:image / imagem oficial (site ou GitHub) → anúncio estático.**
   ```sh
   ./buscar-broll.sh og https://github.com/owner/repo claudecode <sandbox>/brolls
   ```

   **d) Tema genérico (não-marca)** → documentário/clipe temático no YouTube
   (ex: "Homer fazendo burrice", "documentário seita"). Aqui pode ter pessoas
   (é o conteúdo). Sempre **sem áudio** (o `gerar.sh` já tira).

4. **VERIFICAR cada candidato** com `/watch` (ou `verificar.sh`): se for conteúdo
   de marca/produto e tiver rosto de pessoa → **descartar**.

5. **Montar dinâmico:**
   - cortes curtos (`--step` 1.0–2.0); telas viram scroll.
   - deixar o material **rolar sequencial** (não reciclar os mesmos trechos =
     evita repetição, que o João já reprovou).

## Regras de ouro
- Marca/produto = **sem rosto de pessoa**.
- O b-roll é o que segura a retenção → dinamismo > estático.
- Nunca repetir os mesmos trechos.
- Cortes secos (o `gerar.sh` já faz; fade do preto causa "piscado preto").
- yt-dlp **atualizado** (versão >90 dias só baixa 360p).
