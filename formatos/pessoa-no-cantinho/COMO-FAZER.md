# Como fazer: Pessoa em janela

**Quando usar:** vídeo gravado de alguém falando, em que alguns trechos ganham animação. Nos momentos-chave a
pessoa encolhe pra um quadradinho no canto (borda e plaquinha com o nome, nas cores do cliente) que acompanha o
rosto, e a tela vira a animação do que ela diz. No resto, ela aparece em tela cheia com legenda.
Nome técnico: picture-in-picture com rastreamento de rosto.

**O que precisa receber:** o vídeo gravado (original da câmera, não o comprimido do WhatsApp), o nome de quem
fala e o cliente (cores e fontes no `identidade.json`).

**Régua:** exemplo-1 (CONTRATO, item 6).

**Motor hoje:** ainda não há motor em `base/` (por isso o formato é `receita` e a tela não deixa usar). O vídeo
sai de um script da edição na sandbox (PIL + ffmpeg, ou HTML com o vídeo em quadros JPEG) que usa
`app/ferramentas/motion/quadradinho.py` (uso completo no topo dele). O exemplo saiu do `build-cena.py` do modelo
`gancho-jornal` do Cliente3 (removido em 10-out-2026, backup em `~/.config/estudio/backups/formatos-removidos-2026-10-10/`; beats `cena:` do `gerar.sh`: celular-mensagens, mais-menos, tipografia,
checklist-vira-x, palavras-riscadas, cta-final): é o ponto de partida do motor, mas a pele dele é do Cliente3.

**Som:** música nova do Mixkit pelo clima, baixa sob a fala e medida. As janelas não têm efeito sonoro; efeito
só quando a regra do cliente pede.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar o bruto.** Original da câmera em `work/`. Vídeo de iPhone é HDR: converter pra bt709 sem mexer na
   cor (G15). Tempo por palavra em `work/words.json`:
   `python3 app/ferramentas/corte.py transcrever <bruto> <sandbox>/work`, e ler o texto atrás de nome, número e
   acento (G5).
2. **Achar os rostos.** Nas coordenadas do quadro da edição (1080x1920):
   `python3 app/ferramentas/motion/quadradinho.py rostos <bruto> --out <sandbox>/work/rostos.json`
   (`--zoom` igual ao da edição, se ela der zoom).
3. **Escolher as janelas.** De 3 a 5 janelas, perto de 30% do vídeo, onde a fala tem conteúdo que vira imagem.
   O resto é a pessoa em tela cheia com legenda, título só nas frases fortes e nome no terço de baixo na 1ª
   aparição. Janelas a menos de 2 s uma da outra emendam (a pessoa fica no quadradinho). Dentro da janela, cada
   fala é uma cena com forma diferente, uma ideia por vez, texto grande, fundo liso ou o vídeo desfocado; nada de
   grade nem pilha de cartões. Música nova pelo clima:
   `python3 app/ferramentas/musica_busca.py buscar "<clima>" --fonte mixkit`.
4. **Storyboard (para pro João aprovar).** Uma linha ou um quadro por janela: tempo, quem fala e o que a tela
   mostra, olhado ao lado da folha do exemplo. Nada é animado antes da aprovação.
5. **Vídeo.** Só o aprovado. No script da edição, `Trilha("work/rostos.json", a, b, x, y)` escolhe a pessoa da
   janela (rosto inicial mais perto de x,y) e suaviza o caminho; `desenhar(tela, video, t, trilha, k, rect, nome,
   cor=..., cor_nome=...)` faz o vídeo encolher (k de 0 a 1) e seguir o rosto. `cor` e `cor_nome` vêm da
   `identidade.json` do cliente (sem elas sai o ouro/navy do Cliente3, G8). Entra encolhendo (k sobe em ~0,5 s); na
   saída k vai direto a 0, corte seco (o exemplo no topo do `quadradinho.py` anima a saída: não usar essa parte).
   Render 1080x1920; música medida na trilha só-música (~-40 dB sob a fala, ~-35 dB nas pausas, ducking suave).
6. **Conferência.** Folha do vídeo novo ao lado da folha do exemplo principal:
   `ffmpeg -i <vídeo> -vf "select='isnan(prev_selected_t)+gte(t-prev_selected_t\,4)',scale=216:-2,tile=6x4" -frames:v 1 qa/folha-video.jpg`
   - nenhum quadro com mais de 2 elementos além da legenda; o rosto inteiro no quadradinho a janela toda;
   - folha 5 por segundo nas emendas e nos 5 s finais: nenhum vai-e-volta de menos de 2 s e a volta pra tela
     cheia em corte seco (nenhum quadro do quadradinho crescendo);
   - somar as janelas: de 3 a 5, perto de 30% do tempo;
   - checagens gerais do `REGRAS.md` (sobreposição, respiro, volume, só a versão final em Downloads).
   Pior que o exemplo não sai.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, título e texto): `storyboard-antes-de-animar`,
`dose-3-a-5-janelas`, `entra-encolhendo-sai-corte-seco`, `janela-limpa-uma-ideia`, `quem-fala-nao-pula`,
`musica-nova-baixa-medida`. O que é do cliente (cor da borda, fonte, nome na plaquinha, b-roll, cards) fica na
regra dele.

## Som e cena de apoio

**Música:** baixa, discreta, pelo clima do vídeo. Volume: ~-40 dB na fala, ~-35 dB nas pausas, ducking suave. Quando: do início ao fim. Não usa: nunca a mesma do vídeo anterior do cliente. Troca: 1 faixa.

**Efeitos:** não usa (sempre, salvo regra do cliente (Cliente3: click nos cards e whoosh na entrada do b-roll)).

**Cena de apoio:** b-roll que troca com a fala, tela cheia atrás; fontes: acervo, youtube, pexels; 2-4 s; troca a cada frase; não usa: no gancho e no CTA. Prévia: folha com 3 opções por cena antes do render.
