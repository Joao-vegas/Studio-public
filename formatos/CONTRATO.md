# Contrato de formato

Todo formato do Estúdio, os de hoje e os que vierem, cumpre esta lista. O exemplo é régua de estilo e de qualidade (nunca molde): cada vídeo
fica no nível dele ou melhor, com conteúdo próprio, nunca pior.

- **Formato novo do zero, em 3 passos (sem IA):**
  1. `python3 app/ferramentas/formatos.py novo <slug> --motor --titulo "..."` (animação: `base/` com o motor genérico,
     que já faz `--storyboard`, `--quadro`, `--conferir` e o vídeo; o formato só troca o visual no `base/index.html`)
     ou `novo <slug> --gravado --base clientes/<Nome>/<x>Content/modelos/<modelo>` (o render sai do `gerar.sh` da base,
     visto de dentro da sandbox: `zsh ../gerar.sh --dir .`). Nasce `receita`, com a esteira e passando no validar.
     Cada modelo é de um formato só: se a base já é de outro formato, o novo ganha modelo próprio (o nome dele), que a
     tela copia da base pro cliente com o aprendizado zerado e a saída em `output/<nome>`.
  2. `formatos.py referencia <slug> <video ou link>`: o vídeo vira o exemplo (folha com o segundo marcado) e nasce o
     `ESTUDO.md` com perguntas curtas (ritmo, legenda, enquadramento, som). Responde UMA vez; os vídeos só leem.
  3. Troque tudo que tem `TROQUE:` e rode `formatos.py pronto <slug>` (só passa se cumprir esta lista).
- **Estudo da referência = quadro a quadro.** `formatos.py referencia` (e o `/referencia-rapida`) rodam
  `app/ferramentas/estudo_quadros.py`: cada troca de plano classificada (corte, dissolve com nº de quadros, especial), câmera
  medida em todo quadro, fala com tempo por palavra (só Groq), pausa, som (LUFS, música abaixo da voz, efeitos/min), todo número
  falado com o quadro dele e legenda. Sai `estudo-quadros/ESTUDO-QUADROS.md`: **regra com número e o quadro de prova** (`<vídeo>
  q<quadro>`), estilo separado de conteúdo. É a régua do formato: o vídeo pronto passa por `estudo_quadros.py comparar
  formatos/<slug>/estudo-quadros <mp4>` e o que sair FORA se corrige antes de entregar. Nada de regra "no olho".
- **Qual base (referência de animação):** sem pessoa e estilo cartoon (cabeção, cor chapada, contorno) → sem base pronta (o Desenho 3D saiu em 29-out-2026);
  3D "realista feia" de jogo antigo (gente low-poly com rosto de foto, cenário denso, luz de cinema) → `formatos/explicador-3d/base`;
  pessoa gravada → formato gravado. Quem decide: a leitura da referência (`estilo_ref`, com a sugestão de `estudo_quadros.sugerir_base`
  no pedido) e o `formatos.py referencia`, que imprime a base sugerida.
- **Conferir:** `python3 app/ferramentas/formatos.py validar <slug>` (sem slug: todos).
- **`pronto`** = passa sem nenhuma falta (o teste `app/tests/test_contrato_formatos.py` cobra).
  **`receita`** = ainda em construção: pode ter falta, só aparece na lista.

## Os dois tipos (`"tipo"` no formato.json)

- **`motor`**: animação construída (documentário, diálogo 3D, motion, papel recortado...). O motor mora em
  `formatos/<slug>/base/` (`render.py` + `index.html`, ou o que `esteira.motor_arquivos` listar). A tela segue os
  passos do formato e para no storyboard.
- **`gravado`**: vídeo gravado com corte, cenas e cards por cima (ffmpeg + PIL).
  A base é o modelo de um cliente. A tela continua a de vídeo gravado (com a escolha das cenas de apoio) e a IA
  segue os passos do formato por dentro dela.

## Lista de verificação

1. **Básico:** `titulo`, `frase`, `entrada` (video, roteiro, video-ou-roteiro ou filmagem), `proporcao`, `motor`
   (em texto), `status` (pronto ou receita) e `tipo` (motor ou gravado).
2. **Passos na ordem:** `esteira.etapas`, os passos DESTE formato. Cada etapa tem `id`, `titulo`, `andamento`
   (preparar, storyboard, video ou conferencia) e `faz` (o que fazer, em uma ou duas frases). A 1ª é sempre o
   **passo 0** `{"id": "briefing", "titulo": "Briefing", "andamento": "preparar", "aprovar": true, "faz": ...}`: o
   briefing que o João fecha na conversa (ou no Criar). Ele chega à IA como "BRIEFING DESTE VÍDEO", vale só pra
   este vídeo e não vira regra (REGRA Nº 2 só com "aprenda isso"). É igual em todo formato: não entra no COMO-FAZER.
3. **Onde para:** a 1ª etapa com `"aprovar": true` depois do briefing é o storyboard. Briefing, roteiro e elenco se
   aprovam antes, na conversa e na tela Criar.
4. **Depois do storyboard:** uma etapa de vídeo e, por último, a conferência contra o exemplo principal.
5. **Render declarado:** motor → `"base": "formatos/<slug>/base"` com todos os arquivos do motor; gravado →
   `base` aponta o modelo e `esteira.comandos.render` diz o comando. Todo arquivo citado nos comandos existe
   (`<sandbox>/x`, `<modelo>/x` e `../x` precisam estar na base). Nos comandos, `<sandbox>` é a pasta do vídeo,
   `<modelo>` a pasta do modelo do cliente e `<saida>` o mp4 final em caminho absoluto; comando sem `<sandbox>` nem
   `<modelo>` roda de dentro da sandbox.
6. **Exemplo:** `pronto` tem exemplo (sem exemplo fica `receita`; só o formato `"oculto"` espera). O 1º de `exemplos` é o principal: o arquivo está na pasta, tem `legenda` e tem folha de
   quadros com o segundo marcado (`exemplo-N-folha.jpg`: `python3 app/ferramentas/formatos.py folha <slug>`).
   Saiu um vídeo melhor? `python3 app/ferramentas/formatos.py exemplo <slug> <mp4>` e ele vira o principal.
   **Régua** (vale pra todo COMO-FAZER): o exemplo principal é régua de estilo e qualidade, nunca molde (o conteúdo é sempre do vídeo novo); cada vídeo fica no nível dele ou melhor, e se sair melhor, o João decide se vira o exemplo.
6b. **Catálogo (opcionais):** `"grupo"` (`falando` | `animacao`), `"ordem"` (menor = primeiro) e `"oculto": true` (some do catálogo e vai pra "Mais formatos (em teste)", sem apagar). Sem `grupo`, vale o da entrada.
**Rodízio** (vale pra todo formato, não repete nos COMO-FAZER): música e efeito rodam em rodízio (`acervo/usos.jsonl`): nem a mesma música nas últimas 8 entregas do cliente, nem o mesmo efeito nas últimas 4; favorito e pedido do João passam.
7. **Som e cena de apoio:** `"som": {"musica": {"usa", "de_onde", "clima", "volume", "quando", "quando_nao", "troca"}, "efeitos": {"usa", "de_onde", "quais": [...], "momentos", "volume", "quando_nao"}}` e
   `"apoio": {"usa", "tipo", "fontes": [...], "duracao_s", "quantidade", "quando_nao", "previa"}`. Com `"usa": true` o `validar` exige
   `clima` (música) ou `quais` (efeito), `volume` e `quando_nao`, e no apoio `tipo`, `fontes`, `duracao_s` e `quando_nao`; `"..."` conta como falta.
   O `COMO-FAZER.md` traz a seção `## Som e cena de apoio` com o mesmo conteúdo em prosa. O que o formato não usa é `"usa": false` + `"quando_nao": "sempre"`.
   Com `"usa": false` a tela não mostra o bloco e o pedido à IA não fala em buscar faixa nem efeito. Rodízio: nem a mesma música
   nas últimas 8 entregas do cliente, nem o mesmo efeito nas últimas 4 (`acervo/usos.jsonl`); favorito e pedido do João passam.
   Apoio com `usa: true` gera a POLÍTICA DE CENA DE APOIO no pedido: consulta pelo sentido, 2 fontes por cena, filtro de qualidade e
   folha de prévia (`app/ferramentas/folha_broll.py`) com 3 opções antes do render.
7b. **Material aceito:** `"material_aceito"`: a lista do material que o formato sabe usar, pelo papel de cada arquivo
   liberado no briefing: `cena-produto`, `mockup`, `logo`, `foto-pessoa`, `print`, `video-curto`, `musica`
   (`formatos.MATERIAIS`); `[]` se não usa nenhum. A conversa avisa cedo quando o briefing libera um que não está
   na lista (`formatos.material_fora`). Formato novo sem a lista não passa. O motor ganhou lugar pra mais um? Ponha na lista.
7c. **Layouts:** `"layouts"`: como o formato ocupa a tela, só o que o motor já monta: `cheio`, `dividido`, `faixa`,
   `cantinho`, `janela` (`formatos.LAYOUTS`); no mínimo um. A referência que pede outro é avisada antes de gastar
   (`formatos.aviso_layout`, na conversa e no Criar): o João troca de formato ou o formato ganha o layout (tarefa nova).
   Vídeo com referência: o `ANALISE.md` tem a seção `## Referência analisada` (Usada, Quadros da `folha.py`, Layout,
   Estilo aproveitado, Não deu; a conferência ainda aceita "Copiado" de vídeos antigos); sem ela a conferência reprova o storyboard (`producao.conferir_referencia`).
7d. **Legenda:** `"legenda": {"desligavel": true, "como": "<passo ou parâmetro exato que desliga>"}` ou
   `{"desligavel": false, "motivo": "<por quê>"}`. Legenda = a fala escrita, sincronizada com o áudio; manchete, card, faixa,
   texto de tela e o texto que É o conteúdo do formato continuam. O Criar só deixa ligar o "Sem legenda" nos `true` (nos outros
   mostra o motivo); o pedido à IA ganha a linha SEM LEGENDA com o `como`, e a conferência do formato não reprova legenda
   ausente. Formato sem legenda da fala (ou que só funciona com ela) é `false` com o motivo. O `como` tem que ser algo que o
   motor/script já faz (flag, campo do JSON); formato novo sem isso nasce `false`.
8. **Aprendizado:** `aprendizado/regras.json` com `"regras": [...]` (pode ser vazio); cada regra com `id`, `titulo`
   e `texto`. Quem usa `regras.md` (tabela) põe o título de cada uma em `aprendizado/titulos.json`.
8b. **Seu material:** `"pede": [{"campo", "rotulo", "tipo": arquivo|link|arquivo_ou_link|tempo|texto|voz|foto, "obrigatorio", "dica", "padrao"?, "principal"?}]`:
   o que o passo 4 do Criar pergunta pra este formato (`principal: true` = o vídeo ou roteiro que já vai na área de cima). Lista não vazia; `validar` cobra campo, rotulo e tipo.
9. **COMO-FAZER.md:** curto (até 90 linhas) e escrito como o passo a passo: cada etapa da esteira vira uma linha
   numerada (`1. **Título da etapa.** ...`) ou um `## Título`, na mesma ordem.
10. **Pronto sem sobra:** nenhum `TROQUE:` no formato.json, no COMO-FAZER.md nem no motor, e o `ESTUDO.md` (se tiver) respondido.

## Motor que não é o padrão (opcional, em `esteira`)

Sem estes campos vale o motor HTML do Estúdio (o do Documentário): `render.py` + `cenas.json`, `--storyboard` com a
checagem e a `previa-som.m4a`, `--conferir` com a `qa/folha-comparacao.jpg`.

- `"cenas"`: o arquivo do vídeo na sandbox (padrão `cenas.json`; formato de animação em HTML: `index.html`).
  É ele que o Estúdio guarda a cada rodada nova (`work/rodadas/`) e nunca sobrescreve quando o motor da base muda.
- `"copiar_motor": false`: o motor roda direto da base do formato (os comandos apontam pra `formatos/<slug>/base`);
  nada é copiado pro cliente nem pra sandbox.
- `"voz"`: `narracao` (padrão, `narracao_tts.py`), `motor` (o comando do motor gera a voz) ou `sem` (sem narração).
- `"folha"`: a folha que a conferência gera (padrão `qa/folha-comparacao.jpg`; duas versões: a lista). Pra qualquer vídeo:
  `python3 app/ferramentas/formatos.py folha-video <mp4> <saida.jpg>` (a mesma folha do exemplo).

Vídeo gravado: a escolha `"cenas"` (em `escolhas`) pode trazer `"quantidade"` (1 a 12), o teto de cenas de apoio que
o formato pede (a Tela dividida usa 8, como o exemplo); sem ela o teto é 3 e os intervalos ficam com o bruto.

## De onde vem uma regra

Só do exemplo, do `historico.jsonl` ou do que o João disse (REGRA Nº 2 do `CLAUDE.md`). Nada de regra inventada.
