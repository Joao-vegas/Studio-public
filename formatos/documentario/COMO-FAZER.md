# Como fazer: Documentário

**Quando usar:** fala reflexiva, história, conselho, bastidor, gestão. Mini-documentário em cima do vídeo gravado: a
pessoa falando entre construções (frase acendendo, recorte P&B, relógio, polaroid, caderno, traço, jornal, cena de
filme). **Régua:** exemplo-1 (CONTRATO, item 6).
**Motor:** `base/` (`render.py` + `index.html`; esquema do `cenas.json` no `base/README.md`, os 9 tipos em
`base/cenas-modelo.json`). Roda de dentro da cópia (modelo do cliente ou `_sandbox-*`). Música, efeitos, legenda abaixo
do queixo e conferência saem do motor. Conserto vai na `base/` (chega sozinho na cópia); o ajuste de um vídeo vai no
`cenas.json`, nunca no motor.
## Os passos (formato.json → "esteira")
1. **Preparar a fala.** Transcrição com tempo por palavra e pontuação em `work/words.json`; conferir nome, número e
   acento. iPhone em HDR: bt709 sem mexer na cor. Folha dos rostos: `python3 render.py --rostos <bruto>`
   (`qa/rostos.jpg`): é dela que sai o `quadro_s` do jornal e dos recortes (olho aberto, sem borrão, sem mão no rosto).
   **Só roteiro:** `roteiro.txt` → `python3 app/ferramentas/motion/narracao_tts.py --pasta <sandbox>` (ou a voz das
   Configurações) → `python3 app/ferramentas/motion/preparar_audio.py --pasta <sandbox>`; no `cenas.json`, `"voz":
   "audio/voz.wav"`, `"palavras": "audio/palavras.json"` e `"video"` = foto real da pessoa (como no `cenas-modelo.json`).
2. **Cenas de fora.** **A imagem mostra o que a fala diz (G6):** achar o quadro do objeto, da ação ou do lugar citado com `app/.venv/bin/python app/ferramentas/casar_imagem.py melhores <vídeo> "<a frase>" -n 5 --saida brolls/<nome>` (procura DENTRO de um vídeo real, ex. o oficial da empresa: "a câmera de 1975" sai do vídeo da Kodak, não uma foto do inventor) e conferir com `casar_imagem.py pontuar <imagem> "<a frase>" --outras "<outras falas>"`; a mesma pessoa nunca em 2 cenas vizinhas e no máximo 2 vezes no vídeo. **Ação = vídeo da ação (G6, 30/10):** fala que descreve uma ação (mandar dinheiro, pagar, digitar, correr, cair, ligar, assinar, rir...) leva um clipe real de quem faz aquilo, não foto parada (`clipe.py busca`, get-brolls, `casar_imagem.py melhores <vídeo> "<a ação>"`). **Real e viral, nunca clichê:** momento real do caso, depois clipe viral ou famoso, só então banco; ator posando e pilha de dinheiro genérica reprovam (`casar_imagem.py cliche <imagem>` abaixo de 0,05; o `conferir` acusa `cliche`). **Nada repetido:** nem a mesma foto nem outra quase igual perto no tempo (`quase_igual`). Uma a cada ~21 s (o exemplo tem 4 em 1:23; 2 min pedem 6), **cada uma de um clipe diferente**.
   Cena de filme ou de arquivo real do que a fala descreve (escritório, equipe, fábrica, alguém pedindo demissão),
   **nunca banco de imagem com ator posando** (Pexels, Pixabay: o João odeia "banco de dados de vídeo"). Ordem: material
   do cliente → cenas que o João já escolheu (o pedido lista) → acervo → get-brolls grátis (método em
   `.claude/skills/broll/SKILL.md`). Toda rodada busca de novo. Quadro: `python3 render.py --folha-broll brolls/x.mp4`, sem marca
   d'água (logo no canto: `corte`). Cada cena de fora leva `"origem"`. Escolha trecho nítido e parado (não mão em movimento); arquivo com menos de ~475 px de largura não serve pra faixa de 1080 px (o motor trata clipe e foto pequenos, mas a conferência reprova o que ainda sai borrado). Nunca a própria pessoa na polaroid ou no filme. **Alterne filme e polaroid** (proporção, não contagem): pelo menos 1/3
   polaroid (o mesmo clipe com `"video"` + `"quadro_s"`), senão é a mesma tira de jornal toda hora.
3. **Montar as cenas.** `cenas.json` **do zero a cada rodada** (o anterior fica em `work/rodadas/`, só pra não repetir o
   que o João reprovou), lendo `aprendizado/regras.json` e as regras do modelo do cliente:
   - uma cena por trecho de fala, **até 2,5 s**; imagem **literal** da fala; os 3 primeiros segundos numa construção;
   - **tela de texto com a ideia inteira**: começa depois da vírgula, do ponto ou de uma pausa e termina no fim da ideia
     (nunca em "mas também envolve" com "uma carga" na tela seguinte);
     ideia curta (até 5 s) em 1 ou 2 telas, nunca 3;
   - **palavra-chave forte** (BARGANHA, PREJUÍZO, TURNOVER), nunca VEZES, TODO, GRANDE, INTEIRO ou -MENTE; a última
     tela termina nela, sem ficar pendurada ("com ele");
   - pessoa falando até 35%, pessoa na tela até 40%, frase até 30% e no máximo 2 seguidas, objetos 30% ou mais, 6 tipos
     ou mais. Pra tirar a pessoa da tela, objeto, não frase;
   - **caderno é lista**: 2 itens ou mais e o círculo fecha; só o círculo é frase disfarçada;
   - **papel claro e escuro se alternam** (pelo menos 1 tela clara a cada ~40 s): caderno sem `"tom": "escuro"`,
     polaroid com `"fundo": "papel"`. O cliente dá as cores (o motor lê `clientes/<Nome>/identidade.json`; não ponha
     "cores" no cenas.json), não deixa tudo escuro. Só se a regra do modelo do cliente
     recusa papel claro (a Vegas recusou papel claro + azul na Cartilha): `"estilo": {"papel_claro": false}`;
   - recorte e jornal de quadros diferentes do bruto (2 s ou mais), **no máximo 1 recorte a cada ~30 s** (o mesmo bruto
     dá recortes iguais); relógio só com hora na fala;
   - **música** pelo clima (`base/audio/catalogo.json` ou Mixkit), nunca a do último vídeo do cliente; trocou no meio,
     a opção escolhida no `PLANO.json` leva os mesmos `"trechos"`; `"efeitos": true`.
4. **Storyboard (para pro João aprovar).** `python3 render.py --storyboard --cenas cenas.json` → `storyboard.jpg` (um
   quadro por cena, com o tempo e a fala; rodapé com a música de/até e o número real de efeitos) + `previa-som.m4a`.
   Só vale com "APROVADO na checagem"; reprovou, corrigir o `cenas.json` e rodar de novo. Olhar ao lado da folha do exemplo e das
   `qa/folha-<b-roll>.jpg`. No ANALISE.md: tempo em m:ss e **o número de efeitos que ele imprime**.
5. **Vídeo.** `python3 render.py --cenas cenas.json` (1080x1920; `--ate 6` testa o começo).
6. **Conferência.** `app/.venv/bin/python app/ferramentas/casar_imagem.py conferir <sandbox>` (cena que não casa com a fala ou pessoa repetida: troque a imagem) e `python3 render.py --conferir --cenas cenas.json` tem que sair com exit 0 (olha o vídeo pronto: legenda na boca,
   imagem parada, música inaudível). Reprovou: corrigir o `cenas.json` e renderizar de novo. Olhar a `qa/folha-comparacao.jpg`.
**O motor confere sozinho** (`--conferir`, lista completa no `base/README.md`): tela acima de 2,5 s, b-roll pequeno demais pra tela (esticado acima de 1,25x mesmo com o upscale), proporções de pessoa, frase e objeto, menos de 6 tipos, imagem ou clipe repetido, cena de fora sem `origem` ou de banco de imagem, menos de 1/3 polaroid, recorte demais (mais de 1 a cada ~30 s), nenhuma tela clara, tela de texto cortada no meio da ideia, palavra-chave fraca, caderno com menos de 2 itens, legenda na boca, jornal borrado, música faltando, rejeitada ou inaudível, efeitos acima do ritmo do exemplo (até 12 por minuto, 2,4 s entre eles) ou qualquer golpe.

## Som e cena de apoio

**Música:** documental sombria, piano e cordas, em rodízio pelo catálogo do formato. Volume: baixa sob a fala. Quando: do início ao fim; pode trocar de faixa no meio. Não usa: nunca a do vídeo anterior do cliente; não repetir as 8 últimas. Troca: 1 faixa; 2 só se passar de 60 s.

**Efeitos:** pop, click-soft, tique, whoosh-short, typing. Momentos: teclado nas telas de texto, um toque por construção (até 12 por minuto, 2,4 s entre eles). Volume: 0,10-0,18. Não usa: zero golpe, boom ou impacto.

**Cena de apoio:** evidência real, print, card do motor e cena de filme; fontes: acervo, youtube, commons; 2-5 s; 1 a cada 5-7 s; não usa: no gancho falado e no CTA. Prévia: folha com 3 opções por cena antes do render.

O motor faz a mixagem: voz a -16 LUFS → música com ducking (~-40 dB sob a fala, ~-33 dB nas pausas) → efeitos suaves (0,10 a 0,18, sem grave): primeiro o teclado das telas de texto, depois um toque por construção, a passagem só quando o mundo muda → -14 LUFS. `"musica": null` / `"efeitos": false` só quando o João tirou na tela (`PLANO.json`); senão reprova.
