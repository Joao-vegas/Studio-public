# Como fazer: Faixa com cenas

**Quando usar:** fala gravada só com a câmera (sem gravação de tela) que conta uma ideia com imagens fortes: medo,
dinheiro, cliente, rotina. Tem gravação de tela? É a Análise de tela.
**Régua:** o exemplo do MESMO estilo (12-anos = Frase fixa, video-2 = Gancho + legenda). Régua de estilo e qualidade (não é molde: o conteúdo é sempre próprio). Cada vídeo fica no nível dele ou melhor; se um sair
melhor, ele vira o exemplo: `python3 app/ferramentas/formatos.py exemplo <slug> <mp4>`.
**A tela (1080x1920), 3 jeitos alternando:** S = dividido (cena em cima 960 px, João embaixo seguindo o rosto,
sombrinha forte na emenda y=960) · C = cena em tela cheia · João em tela cheia. Frase em faixas: linha branca
(texto preto), vermelha #DE1C21 (texto branco), branca; Gilroy ExtraBold 64 px, caixa-alta, centrada na emenda.
**Os 2 estilos (escolha "Estilo" do Criar → `estilo` no PLANO.json):**
- **Frase fixa:** a frase o vídeo todo, sem legenda.
- **Gancho + legenda:** a frase até `faixa_ate` (fim da 1ª ideia, ~9 s); depois legenda branca de 3 palavras
  (Barlow SemiBold 60), na emenda no S e no C, no PEITO (y=1420, ou mais embaixo se o queixo pedir) com o João em tela cheia. Nunca no rosto.
**Frase fora do rosto (30-out-2026):** com o João em tela cheia a frase também sai da emenda quando ela cobriria o rosto: fica no peito (y=1180) se está livre, senão acima da cabeça ou abaixo do queixo, uma posição por trecho (`texto_fora_do_rosto.py`, grava `work/gerado/texto-posicao.json`). `conferir_video` reprova "Texto em cima do rosto".
**Motor:** `gerar.py` do modelo (ffmpeg + PIL), lê `<sandbox>/PLANO.json` (formato no cabeçalho do script).
**Som:** só a voz da câmera, a -14 LUFS, com 0,4 s de folga no fim. Sem música e sem efeito.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Cortar o bruto.** `corte.py auto` + `aplicar` → `work/joao.mp4`. Conferir os 3 primeiros segundos: a 1ª palavra
   está lá (gaguejo que passa do início do take bom come a palavra: encurte o `t1` em `gaguejos.json`) e o falso
   começo saiu. Retranscrever em `work/cortado/words.json`; palavra trocada vai em `trocas`, palavra comida em `palavras_extra`.
2. **Frase e estilo.** A 1ª ideia falada em 2 a 3 linhas (`|` quebra). Estilo da escolha do Criar.
3. **Escolher as cenas.** Janelas `[início, fim, modo, clipe, início-no-clipe]`: S nas frases com imagem concreta,
   C em 2 a 4 momentos de impacto, João em tela cheia na tese e no CTA. A 1ª janela é S no t=0.
4. **Prévia (para pro João aprovar).** `zsh ../gerar.sh --dir . --previa` → `storyboard.jpg`.
5. **Montar e renderizar.** `zsh ../gerar.sh --dir .` → `output/faixa-com-cenas/<slug>.mp4` + `qa/folha.jpg`.
6. **Conferência.** `conferir_video.py` e a folha ao lado do exemplo do mesmo estilo.

## Som e cena de apoio

Sem música e sem efeito: só a voz. Cena de apoio: cena de stock que ilustra a frase (literal ou metáfora forte), do
acervo ou do Pexels/Wikimedia pela get-brolls, com folha de 3 a 4 opções antes do render. 2,5 a 8 s por cena; a de
abertura até ~3 s e já troca. Tese, opinião e CTA ficam com o João em tela cheia.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, titulo e texto). Correção do João vira regra pela REGRA Nº 2
do `CLAUDE.md`; regra nova só do exemplo, do `historico.jsonl` ou do que o João disse.
