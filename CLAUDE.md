# Estúdio: a casa única de produção de vídeo do João

Reels, anúncios, VSL, documentário, cinematográfico: tudo sai daqui. Até 09-out-2026
eram duas coisas: o repositório `producao-reels` (clientes + app) e a skill `motion-design`
(`~/Projetos/Skill/Motion design`). Chegou por caminho antigo? Equivalências:
`<Cliente>/` → `clientes/<Cliente>/` · `scripts/` da skill → `app/ferramentas/motion/` ·
`modelos/motion-venda` (formato Motion com narração, removido em 14-out-2026; backup em `~/.config/estudio/backups/formatos-removidos-2026-10-14/`) · `modelos/camera-mundo` (formato Como funciona, removido em 10-out-2026; backup em `~/.config/estudio/backups/formatos-removidos-2026-10-10/`) ·
`referencias/*.md` → no mesmo backup (`motion-narrado/aprendizado/`). Papel recortado também saiu em 14-out-2026 (mesmo backup). Passos numerados saiu em 15-out-2026 (não performou; backup em `~/.config/estudio/backups/formatos-removidos-2026-10-15/`). Desenho 3D (`formatos/desenho-3d`, grupo animação) entrou em 29-out-2026. Diálogo 3D saiu em 16-out-2026 (backup em ~/.config/estudio/backups/formatos-removidos-2026-10-16/). Frase fixa saiu em 29-out-2026 a pedido do João (backup em ~/.config/estudio/backups/formatos-removidos-2026-10-29/; os modelos dos clientes Joao e Avulso ficaram). Simulação 3D saiu em 29-out-2026 a pedido do João, com o modelo e os vídeos do Cliente2 (mesmo backup). Editorial (`formatos/editorial`, análise de caso com imagem real, 4 referências estudadas quadro a quadro) entrou em 29-out-2026. Desenho 3D e Cinematográfico de evento saíram em 29-out-2026 a pedido do João (mesmo backup).

## Mapa

```
formatos/<slug>/    catálogo (a receita): formato.json, COMO-FAZER.md, exemplo-N.mp4, aprendizado/, base/
clientes/<Nome>/    PADRÃO (confere: `python3 app/ferramentas/clientes_padrao.py`): só identidade.json (cores, fontes, tom) +
                    <x>Content/{entrada, material, modelos, output, transcricoes} (cada uma com .gitkeep; `novo_cliente.py`/tela Novo cliente criam sempre isso); sem .env (chave só em app/.env), sem README,
                    automacao nem documentacao (scripts em app/automacao/), sem banco-* (imagem, vídeo e música só no acervo/)
acervo/             biblioteca única: itens/ (música, efeito, b-roll + meta.json com os usos), busca/, indice.json
app/                interface/ (tela), ferramentas/ (scripts; motion/ = os da antiga skill), automacao/ (scripts Node dos modelos; lib/load-env.js lê app/.env), motores/, jobs/, tests/
REGRAS.md           regras que valem pra todo vídeo
```

Formato novo nasce de `formatos/_modelo/` (`python3 app/ferramentas/formatos.py novo <slug> --motor|--gravado`), ganha a
referência com `formatos.py referencia <slug> <video>` (exemplo + `ESTUDO.md` respondido UMA vez) e cumpre `formatos/CONTRATO.md`.
Pra marcar `pronto`: `python3 app/ferramentas/formatos.py pronto <slug>` (só passa sem falta no validar; o teste cobra).

**Estudo de referência = quadro a quadro (29-out-2026).** Todo vídeo de referência é estudado por
`app/ferramentas/estudo_quadros.py estudar <vídeo...> --saida <pasta>` (um ou vários do mesmo estilo; grátis: OpenCV, ffmpeg,
tesseract; fala só pelo Groq, sem chave segue sem fala): planos e transição de cada troca (corte seco, dissolve com nº de
quadros, especial), câmera medida em todo quadro (% andando, creep, impulso na entrada), palavras/min, voz, pausa pós-frase,
LUFS, música abaixo da voz, efeitos/min, todo número falado com o quadro e o recorte dele, legenda (altura e tamanho) e folhas a
30 fps em ±0,3 s de cada momento. Sai `estudo.json` + `ESTUDO-QUADROS.md` (regra com número citando o quadro de prova; estilo ×
conteúdo). Roda sozinho no `/referencia-rapida` (`estilo_ref.entender` → `app/.estilos/<id>/quadros/`, vai junto pro
`formatos/<slug>/estudos/NN/estudo-quadros/` no Confirmar e a régua entra no pedido à IA que lê o estilo) e no `formatos.py
referencia` (a 1ª vira a régua do formato em `formatos/<slug>/estudo-quadros/`, que entra no pedido da produção). Conferência:
`estudo_quadros.py comparar <estudo> <mp4> --words <words.json>` grava a tabela ref × nosso (`COMPARACAO.md`). Base pela cara:
animação sem pessoa estilo cartoon → sem base pronta (o Desenho 3D saiu); 3D "realista feia" de jogo antigo (Loaded Dice) →
`formatos/explicador-3d/base`; pessoa gravada → formato gravado (`estudo_quadros.sugerir_base` sugere; a IA da referência decide).

## Regras em 3 camadas

Na briga, a mais específica ganha: **modelo do cliente > formato > geral**.

1. **Geral:** `REGRAS.md`.
2. **Formato:** `formatos/<slug>/COMO-FAZER.md` + tudo em `formatos/<slug>/aprendizado/`.
3. **Cliente:** `clientes/<Nome>/identidade.json` + o `regras.json` do modelo dele + `regras-gerais.json` do cliente, se houver.

Regra de um cliente **não** vale pra outro.

## REGRA Nº 1: ler o aprendizado antes de produzir

Ordem: `formato.json` e `COMO-FAZER.md` do formato → aprendizado do formato → identidade e regras do
modelo do cliente → `REGRAS.md`. Olhe os exemplos do formato em quadros. Não repita erro já corrigido.
Exemplo e referência = estilo e régua, nunca molde (ver G0 do REGRAS.md).

## REGRA Nº 2: correção do João vira regra, sem duplicar

1. Uma linha no `historico.jsonl` do modelo usado (`tipo, categoria, texto, origem, createdAt, job`).
2. Escolha a camada: vale pra esse formato em qualquer cliente → aprendizado do formato; é gosto ou
   identidade do cliente → modelo do cliente ou `identidade.json`; vale pra todo vídeo → `REGRAS.md`.
   **Na dúvida, cliente.**
3. Procure a regra do mesmo assunto. Existe: reescreva a própria regra (sobe o peso, mantém `cobre` e
   `desde`), nunca cole parágrafo no fim. Não existe: crie uma. Regra é instrução com número, não diário.
   Teto: 24 regras por modelo, ~600 caracteres cada; estourou, junte as parecidas sem perder medida.
4. A regra já existia e furou? Descubra por quê (protocolo no `SKILL.md`) e conserte a causa.
   **Erro mecânico se conserta no motor ou na checagem do formato, não só em texto** (29-out-2026, método Creatorize): depois de
   cada vídeo, olhar a folha de todos os planos; cada problema vira uma linha no `historico.jsonl` com `causa` e `conserto`
   (o arquivo e a função mudados), e o conserto vai no `base/` do formato ou num teste, pro próximo vídeo não conseguir repetir.
   Ex.: palavra forte com pontuação não acendia → `index.html` normaliza; Groq parava no meio → `corte._parou_no_meio`.
5. Diga ao João em uma frase o que foi aprendido. No "fechar e liberar espaço" o histórico vira regra
   e o cru vai pra `aprendizado/arquivo/` (`app/ferramentas/aprendizado.py`). Nada é apagado.

## Como produzir

- **Corte e seguir direto (23-out-2026):** todo vídeo gravado entra cortado sozinho (`producao.cortar_sozinho` → `corte.py`, já aplicado em work/joao.mp4; formato sai com `"corte_automatico": false`). "Corrigir o corte" só ajusta: aplica, o João assiste e aprova (aí o vídeo é refeito). A chave "Seguir direto até o vídeo final" do Criar (`job.seguir_direto`) vem LIGADA em todo estilo (30-out-2026, `producao._segue_direto`): o storyboard é progresso no Em andamento, o gate é o vídeo final ("Ficou bom?" + Editar vídeo); desligada, para no storyboard. Aprova o storyboard sozinha e renderiza (`runner.py` → `avancar`).
- **Editar por cena (29-out-2026; todos os estilos desde 30-out):** menu Editar vídeo (`/editar`, `app/ferramentas/editor.py`) com Claude do lado; alcance elemento · cena · trecho · vídeo; o Estúdio só aceita a mudança no alcance (`editor._fiel`); versões em `<sandbox>/editor/versoes/`, nunca apagadas. Motor: cenas.json + render.py (Editorial, Explicador 3D, Documentário). Gravado: um arquivo por estilo em `app/ferramentas/editor_gravados/` (contrato dos ganchos no `__init__.py`): Faixa com cenas, Caixinha e Frase fixa (camada.json), Crítica ao absurdo, Análise de tela, Tela dividida, Fala com cenas, Chamada na tela, Lista de estáticos. Vídeo montado à mão (montar.sh, montar.py, comando.sh) edita no modo livre (`editor_gravados/livre.py`): guarda os arquivos e o vídeo, roda o comando e só aceita se, fora da cena marcada, o vídeo ficou igual. Sem a gravação (work/joao.mp4) ou sem o comando que refaz o vídeo, ele aparece na lista com o motivo. Estilo gravado novo = um arquivo novo nesse pacote.
- **Python (30-out-2026):** o Estúdio roda na `app/.venv` (3.14, com flask, PIL, numpy e opencv) e abre todo processo filho com ela na frente do PATH (`_comum.com_venv()`): o `python3` de dentro do gerar.sh e da esteira é o da venv. O `python3` do sistema pode ser outro (o brew trocou pra 3.15 em 30-out, sem as bibliotecas): pelo terminal use `app/.venv/bin/python`. Testes: `cd app/tests && ../.venv/bin/python -m unittest discover`. O `atualizar.py` confere o ambiente depois de cada atualização pelo brew.
- **Telas novas (29-out-2026):** Novo vídeo (`/criar-agora`, o botão Criar vídeo), Vozes (`/vozes`), Estudar um vídeo (`/estudar`), tirar estilo/teste/estudo pra lixeira (`remover.py`). Tudo no `PLANO-2.0.md`.
- **Pela tela:** http://localhost:7655 (se não abrir: `bash app/iniciar.command`). Criar vídeo em 5 passos (o que você tem · formato · pra quem · material · detalhes) →
  a IA produz → o feedback vira regra. Corte errado: botão ✂︎ Corrigir o corte (Em andamento ou na etapa do corte), marca o erro com ● ou tecla M e Aplicar.
- **Em massa (1.2):** `/novo-lote` (cliente · estilo · brutos) cria um vídeo por bruto; `/aprovar` aprova vários de uma vez.
  Referência nova: `/referencia-rapida` (joga o vídeo, ele entende o estilo, sem copiar a fala).
- **Direto pela IA:** ler na ordem da REGRA Nº 1 e seguir o `COMO-FAZER.md`. Trabalho em
  `<modelo>/_sandbox-<slug>/`; entrega em `clientes/<Nome>/<x>Content/output/<modelo>/<slug>.mp4`.
- **Conferência automática (gravados):** `python3 app/ferramentas/conferir_video.py <mp4> --sandbox <sandbox>` grava `qa/conferir.json` (tamanho, fim de frase, cauda, tela preta/parada, LUFS, folha 1 s, sobra de legenda no frase-fixa). Sem ela aprovada o Em andamento mostra "Conferir: ...", não "Vídeo pronto". Nome próprio certo: `identidade.json → "palavras"` vai no prompt do Groq (`vocabulario.py`).
- **O Estúdio se revisa sozinho (29-out-2026, `app/ferramentas/revisao.py` · `melhoria.py` · `recarregar.py`):** todo vídeo da tela que fica `concluido` dispara a revisão (processo próprio, Sonnet esforço médio, teto US$ 0,50, `ia.TETO_ETAPA['revisao']`): conferência + régua do estilo + folha do vídeo inteiro → achados com `causa` e `conserto` no `historico.jsonl` do modelo (tipo `revisao`, `origem: estudio`) e o cartão "Revisão do Estúdio" no Em andamento. Achado mecânico (do motor/checador) claro, ou provável que apareceu em 2+ vídeos, vira "Melhoria sugerida" (Esperando você, `/melhoria/<id>`): a IA edita só uma CÓPIA, o João vê o diff e só o Aplicar grava (backup em `app/melhorias/<id>/antes/`, prova: sintaxe + `formatos.py validar` + testes + 1 quadro renderizado com o motor novo; falhou = volta como estava; Desfazer disponível). Histórico com mais de 20 linhas novas num modelo vira proposta "passar a limpo" (regras novas/reescritas, OK do João). "Atualização pronta" é o botão Recarregar agora (`/api/recarregar`; com vídeo rodando agenda e reinicia sozinho quando acabar). Quem produz pelo chat segue a REGRA Nº 2 do mesmo jeito; a tela cobre o que o app produz.
- **Em andamento (obrigatório pelo chat):** o João acompanha na aba Em andamento. A cada passo:
  `python3 app/ferramentas/andamento.py passo <Cliente> <slug> "<o que está fazendo>" --titulo "<título>" --formato <formato>`;
  parou pra ele aprovar: `espera ... --imagem <storyboard.jpg>`; no fim: `pronto ... --video <mp4>`.
- Cliente sem a variante do formato: o Estúdio copia a `base/` pra ele, aprendizado zerado. Sem cliente: `clientes/Avulso/`.

## Versão 2.2.1 (30-out-2026: Novo vídeo por "O que você tem?", Esperando você numa conta só com "Rodando agora", desfazer no corte, menu enxuto e melhorias por estilo); antes 2.2.0 (30-out: o vídeo pronto vira o editor por cenas, música viral sem voz, voz sem janela, apagar com prévia, telas mais simples e app rápido); antes 2.1.1 (30-out: acabamento visual, imagem casando com a fala, a edição chega no vídeo entregue), 2.1.0 (30-out: Editar vídeo em todos os estilos, inclusive vídeo montado à mão), 2.0.0 (30-out: o Estúdio usado direto pelo app — editar por cena, Novo vídeo numa tela, aprovação no resultado, app que revisa e aprende sozinho), 1.3.0 (29-out) e 1.2.0 (22-out). Número em `app/interface/servidor.py` `VERSAO`, aparece ao lado da marca; histórico no `CHANGELOG.md`

- **Estilo é a palavra da tela.** Referência é estilo, nunca cópia. `/referencia-rapida` (joga vídeo/link → `estilo_ref.entender` mede, transcreve (só Groq; sem Groq segue pelas imagens, nunca um transcritor pago) e faz 1 chamada de IA → `estilo.json` sem copiar a fala → "Confirmar" grava em `formatos/<slug>/estudos/`; estilo novo sai pelo botão "Criar este estilo novo"). Trabalho em `app/.estilos/<id>/` (fora do git). O `estilo.json` do estudo PRINCIPAL vai no prompt da produção como ideia de estilo, não molde. O estudo completo (`/nova-referencia`) segue como "demorado".
- **Vários vídeos:** `/novo-lote` (cliente · estilo · brutos ou pasta) cria um vídeo por bruto (`lotes.criar_por_estilo`, só estilo de entrada `video`). **Aprovar em lote:** `/aprovar` ("Esperando você", mesma conta do selo do menu: `lotes.esperando`).
- **Catálogo:** `formato.json` aceita `grupo` (`falando` | `animacao`), `ordem` e `oculto` (vai pra "Mais formatos (em teste)"); `formatos.catalogo()` alimenta `/formatos` e o passo do `/criar`.
- **Visual:** `app/interface/static/estilo.css` tem o único `:root`; `simples.css`, `studio.css` e `briefing.css` só usam as variáveis (sem hex, sem `:root`). Componentes: `grade-cards`, `card-video`, `lado-a-lado`, `btn grande`, `selo ok|espera|erro`, `vazio`, `passo-dica`, `titulo-grupo`, `item-estilo`, `acoes-estilo`. Menu: botão "Criar vídeo" + Início · Esperando você · Estilos · Meus vídeos · Recortar vídeo · Clientes · "Mais". Formato `pronto` nunca é `oculto` (teste cobra). Erro 500 mostra página em português e, se o código mudou, manda fechar e abrir o Estúdio.

## Qual motor (decidido em 29-out-2026 pelo uso real; inventário em `app/motores/INVENTARIO.md`)

| Material | Motor | Quem usa hoje |
|---|---|---|
| Vídeo gravado (corte, legenda, b-roll e cards por cima) | **ffmpeg + PIL** | Fala com cenas, Tela dividida, Faixa com cenas, Caixinha, Chamada na tela, Crítica ao absurdo, Análise de tela, Lista de estáticos |
| Animação 2D construída (motion, documentário, editorial) | **HTML próprio**: `base/index.html` com `seek(t)` + `render.py` (Playwright tira o quadro, ffmpeg monta). É o PADRÃO | Editorial, Documentário, modelo `_modelo` |
| Animação 3D | **Three.js** (`app/motores/3d`) dentro do mesmo HTML próprio + Playwright | Explicador 3D |
| HyperFrames (`app/motores/hyperframes`: `npx hyperframes lint`, `check`, `snapshot`, `render`) | **Opcional, nenhum estilo usa hoje.** Só vale se um estilo NOVO de animação precisar da checagem automática dele (lint/check) e não do HTML próprio. Não atualiza sozinho | ninguém |
| Remotion | **Aposentado do Estúdio em 29-out-2026.** O motor global `app/motores/remotion` (AnuncioVegas, ReelPostVegas, AnuncioCliente6, VslCliente8, composições de Cliente8 e Cliente2) não era chamado por nenhum modelo atual: foi pro backup `~/.config/estudio/backups/motores-aposentados-2026-10-29/`. Único resto: o formato oculto **Mundo 3d** (Cliente2, ainda em teste) leva o Remotion 4.0.290 dentro dele (`formatos/mundo-3d/base/remotion`). Nenhum formato novo nele: grátis só até 3 pessoas na empresa | só Mundo 3d |

Regra: **gravado → ffmpeg; animação → HTML próprio (padrão); 3D → Three.js no HTML próprio; HyperFrames só por escolha explícita; Remotion nunca em formato novo.**
"Skills do HyperFrames" = a documentação oficial do fabricante (repositório clonado em `app/motores/hyperframes/skills-oficiais/`) que a IA consulta; não é código nosso.

## B-roll

Acervo primeiro (`acervo/itens/`), depois a skill **get-brolls** (busca → prévia em folha → **olhar os
quadros** → aprovar → baixar). Checar rosto indevido, marca d'água, legenda queimada, qualidade e se
casa com a fala. Só entra no acervo o que o João marcar (`python3 app/ferramentas/acervo.py add ...`).
Método completo: `.claude/skills/broll/SKILL.md`. A regra do modelo manda sobre a skill.

## Voz, imagem, custos, atualizações

- **Voz:** VoiceStudio é o padrão (grátis, local, `app/ferramentas/voicestudio.py`, porta 3900; lento, ~8x o tempo real, por isso em blocos). **Um VoiceStudio só: o aplicativo** `/Applications/VoiceStudio.app` (desde 29-out-2026; a cópia de código antiga foi pra `~/.Trash/voicestudio-copia-antiga-2026-10-29`). O backend dele mora em `~/Library/Application Support/VoiceStudio/runtime/project/.venv`; as vozes e perfis (inclusive a clonada do João, 8800a992) ficam em `~/Library/Application Support/OmniVoice` (nunca apagar). O Estúdio abre o aplicativo sozinho (`open -g -j -a VoiceStudio`, espera até 120 s) se o 3900 não responder; sem subir, o erro diz "Abra o VoiceStudio". Como o app sobe o backend: docstring de `voicestudio.py`.
  `voz.falar(texto, saida, voz, cliente)` tenta VoiceStudio → ElevenLabs (`voz.py clonar`), esta só se tiver chave E voz; senão para com o erro
  "VoiceStudio fechado: abra ele" (**Gemini removido em 29-out-2026** a pedido do João: o `--motor gemini` do `narracao_tts.py` ficou só no arquivo, o Estúdio não chama; chaves `GEMINI_API_KEY_*` seguem no `app/.env`, sem uso) e escreve no log qual usou.
  A voz preferida do cliente fica em `identidade.json → voz`; a escolha geral, em Configurações. **Configurações abre em "Conexões"** (`app/ferramentas/conexoes.py`): uma linha por aplicativo
  (VoiceStudio, Claude, Codex/GPT, kie.ai, Groq, ElevenLabs, Pexels, Pixabay, Freesound, Jamendo) com custo, situação medida, Testar (só consulta, nunca gera) e "Onde pego a chave" (link oficial). Groq transcreve a fala (grátis).
- **Emoção na voz (29-out-2026, de graça):** o OmniVoice imita a emoção do áudio de referência e só aceita `whisper` como estilo; nenhum motor instalado aceita emoção por texto. Então cada voz ganha variações FIXAS por emoção (`calmo firme indignado animado segredo pergunta`; `app/ferramentas/emocao.py`, mapa em `app/.cache/vozes-emocao.json`). Voz desenhada: amostra falada com texto que puxa a emoção, guardada "aguardando"; **o perfil `<voz> · <emoção>` só nasce no "Aprovei" da tela Vozes** (nada de perfil sem Aprovou; nada é apagado). Voz do João (8800a992): nunca sintética; `emocao_joao.py procurar` mede os brutos dele e propõe trechos; "Usar como João · animado" cria o perfil, ou ele grava 15 s com o texto sugerido. O Claude (Sonnet, 1 chamada) marca a emoção de cada frase no Criar (botão/ao colar o roteiro; senão ao criar) e grava `emocoes.json` ao lado do `roteiro.txt`; `motion/narracao_tts.py` e o Editar vídeo → Narração (`editor._rodar_narracao`) falam bloco a bloco com a variação da emoção (sem variação aprovada = a voz normal, um pedido só); o tempo das palavras continua vindo do Groq. IndexTTS 2.5 (único motor com emoção por instrução) NÃO instalado: ~13 GB e só CPU no Mac.
- **Música e efeito:** do cliente (assets/musica dos modelos) → acervo → Mixkit/SoundCloud/Jamendo (musica_busca.py); Freesound só efeito.
- **Imagem e vídeo por IA:** kie.ai, modelos em Configurações. Fora da tela: skill `gerador-imagem-video`
  com `--projeto`. Geração paga só com aprovação do João.
- **Custos:** aba Custos (assinatura · grátis · pago), `app/ferramentas/custos.py`.
- **Atualizações:** `app/ferramentas/atualizar.py` (MANIFESTO: Claude Code, Codex, VoiceStudio, get-brolls, skill Gerador de imagem e vídeo, yt-dlp, tesseract, ffmpeg, Playwright, rembg, HyperFrames...). Confere segunda às 4h, uma vez por dia quando o Estúdio abre e a cada 30 min enquanto algo está "na fila"; versão pequena instala sozinha quando não há vídeo sendo feito (testa, volta se falhar); versão grande espera o João. VoiceStudio nunca instala sozinho (o botão só abre o app, que tem o atualizador dele). Selo discreto no menu (Configurações) e "Atualização disponível" na linha do app em Conexões.

## Guardar e arquivar

- Cliente é autocontido em `clientes/<Nome>/`. Compartilhado: `formatos/`, `acervo/`, `app/motores/` (3d, hyperframes).
- Finalizar (tela) escolhe o que vai pro acervo e exporta com conferência SHA-256; limpar é um segundo
  clique. Modelo removido vai pra `app/.lixeira/` e pode voltar. Mudou um modelo? Atualize a `ficha.json`.

## Telas e ferramentas novas (30-out-2026)

Tudo em `app/ferramentas/` (a tela fica em `app/interface/*_rotas.py` + `templates/`). Regra de ouro: criou algo, para e pede "Aprovou?"; nada pago sem o clique do João. Detalhe no `PLANO-2.0.md` (seção "Uso direto pelo app").

- `aprendi`: depois do "Quero alterar" propõe a regra, a camada e se já existe parecida; a tela mostra "Aprendi: ..." com OK / "Não é isso" (Em andamento e Esperando você).
- `variacoes`: 3 ideias de vídeo no mesmo estilo de uma referência, sem copiar a fala; cada uma só vira vídeo no "Aprovou?" (`/variacoes/<id>`, botão na referência).
- `ref_conjunto`: joga várias referências de uma vez e tira UMA régua conjunta (`/referencia-rapida/set/<id>`).
- `estilo_novo`: estilo novo nasce em teste e só vira pronto com o 1º vídeo aprovado (`/estilo-novo/<slug>`).
- `auto_juntar`: referência ou estudo pronto entra sozinho no estilo mais parecido (ou num novo em teste) e só avisa, com "Desfazer" (Esperando você, "Juntei ao X").
- `pendencias`: tudo que espera o João além dos vídeos (referência, estudo, variações, estilo novo, regra, melhoria); alimenta Esperando você (`/aprovar`) e o selo do menu.
- `regua_tela`: resume o estudo quadro a quadro em números e quadros de prova (referência rápida, Estudar um vídeo, set).
- `revisao`: depois de cada vídeo pronto confere sozinha (conferência, régua, folha, 1 chamada Sonnet médio, teto US$ 0,50) e mostra o cartão "Revisão do Estúdio" com achados e miniaturas no Em andamento.
- `melhoria`: o Estúdio propõe consertar o próprio motor (ou passar o histórico a limpo) com diff e prova; só o "Aplicar" do João mexe em arquivo, com Desfazer (`/melhoria/<id>`, `/melhorias`).
- `recarregar`: o botão "Recarregar agora" reinicia o servidor sozinho (espera o vídeo em andamento acabar).
- `espaco`: desduplica mídia igual (clone APFS) e libera espaço mandando pra Lixeira do Mac (`/espaco`).
- `gerar_ia`: "✦ Gerar com IA" no Editar vídeo, por cena: custo na tela, Permitir, miniaturas, o João escolhe uma.
- `emocao` e `emocao_joao`: voz com emoção grátis (o Claude marca a emoção de cada frase; variações fixas da voz); `emocao_joao` acha nos brutos do João os trechos pra virarem as variações dele (`/vozes`, passo do roteiro no Novo vídeo).
- `fontes_gratis`: imagem, vídeo e ícone de fonte livre (Openverse, NASA, Internet Archive, Commons) com origem e licença; usado pelo Editorial e pelo Editar vídeo.
- `midia_local`: upscale (Real-ESRGAN), parallax (profundidade) e separar a voz da música, tudo local e grátis, antes do motor.
- `conexoes`: cada aplicativo que o Estúdio usa com a situação medida, o custo, "onde pego a chave" e Testar que nunca gasta (Configurações, topo).
- `repositorios`: cartão de cada ferramenta e motor (pra que serve, quem usa, versão, atualização) em Configurações, Repositórios e motores.
- `storyboard_estilo`: a tira "Momento a momento" de cada estilo (todos os planos da referência) no Novo vídeo e na página do estilo.
- `elenco`: elenco do ESTILO (hoje Explicador 3D): personagens, roupa e cor, no Novo vídeo e em `/elenco/<slug>`.
- `modelo_forca` (`app/interface/`): o cartão único "modelo + esforço do Claude" (Novo vídeo, Editar vídeo e Configurações).
- Versão do final: `producao.guardar_final_anterior` guarda o vídeo anterior em `<sandbox>/editor/versoes/vN` antes de analisar ou renderizar de novo (nunca se perde); `producao.estimativa_etapa` dá a linha "leva uns N min · sai da assinatura" da confirmação de etapa.
- `casar_imagem` (30-out-2026): nota de quanto a imagem casa com a fala (CLIP ViT-B/32 + texto multilíngue, local e grátis, modelos em `app/modelos-locais/`, fora do git, 1,6 GB) e busca do quadro certo dentro de um vídeo (`melhores_quadros`); `conferir_cenas` acha cena que não casa e a mesma pessoa em cenas vizinhas (rosto, YuNet + SFace). Entra na produção do Editorial e do Documentário, no Editar vídeo e na revisão (achados `imagem_nao_casa`, `imagem_repetida`); régua no G6 do `REGRAS.md`.
- `texto_fora_do_rosto` (30-out-2026): com a pessoa em tela cheia, a frase ou legenda vai pra cima da cabeça ou abaixo do queixo, medido pelo rosto do vídeo (Faixa com cenas); `conferir_video` reprova "Texto em cima do rosto". Caixinha, Frase fixa, Fala com cenas e Chamada na tela ainda usam altura fixa.
- Fundo vivo (30-out-2026): no Editorial (ícone, texto, contador, pílulas, Venn...) e no Documentário (filme e polaroid no fundo jornal), a cena sem foto própria leva atrás a imagem real da cena vizinha, desfocada e escurecida; ícone com emoji e fundo liso reprovam no `--conferir`. Grão do Editorial em .12 na tela inteira.
- Entrega da edição (30-out-2026): `editor.entregar` leva o vídeo editado pro `job["saida"]` (guarda o anterior como versão, trata o fim como o runner, confere) e o vídeo volta pro "Ficou bom?"; exportado não é tocado. Render que trava é abandonado (`_comum.rodar_com_limite`) e o OpenCV roda sem OpenCL (`OPENCV_OPENCL_RUNTIME=disabled`), sem carregar o Metal no Python.
- Página do vídeo pronto (2.2.0): é o editor por cenas (miolo em `templates/_editor_miolo.html`, contexto em `editor_rotas.contexto_editor`, usado também no `/editar/video`); a produção vai pra "Como foi feito". Depois de aprovar, "Aprovado ✓ — e agora?" (baixar, Finder, guardar no iCloud, usar como referência do estilo = `formatos/<estilo>/estudos/`, liberar espaço, desfazer aprovação).
- Música (2.2.0, `musica_viral.py`): virais de hoje (Shazam, Spotify via kworb, Apple, Deezer) em VERSÃO INSTRUMENTAL do YouTube, voz medida pelo Demucs (limite -20 dB) e marca d'água conferida; Procurar = direção em palavras (`por_direcao`); gênero que briga (funk, sertanejo, pop cantado) só se o roteiro falar dele; Mixkit é plano B. "Não usar mais" = `acervo/musicas-reprovadas.jsonl`.
- Voz (2.2.0): `voicestudio.py` sobe o backend SEM JANELA (uvicorn do runtime do app, log em `~/Library/Logs/voicestudio-sem-tela.log`); o app aberto junto reaproveita a porta 3900. "Meu áudio (MP3 ou MP4)" na narração; com o vídeo gravado as vozes somem.
- Apagar e Liberar espaço (2.2.0): painel com prévia e Mostrar no Finder (prefixo de classe `pa-`; `ap-` é da tela de aprovar). Liberar espaço não oferece vídeo esperando aprovação nem editado nos últimos 7 dias; cada limpeza grava manifesto em `app/.cache/limpezas/` e o "Desfazer" devolve pelo Finder (o Terminal não lê `~/.Trash`; o Finder lê).
- Velocidade (2.2.0): `_comum.memo_curto` (uma varredura por pedido), `preparar.py` (capa e miniaturas em segundo plano no `andamento.pronto` e no `editor.entregar`), listas com `preload="none"` + `poster`; toda tela abaixo de 0,3 s com cache. Teste nunca usa pasta temporária fixa (`test_velocidade.py` cobra).

## Mapa de modelos (o app lê e escreve esta tabela: mantenha as 3 colunas)

| Cliente | Modelo | Aprendizado |
|---|---|---|
| Cliente2 | `dividido-mascara` (fala-com-cenas; cores do pack Marca3, rosa proibido) | `clientes/Cliente2/marca2Content/modelos/dividido-mascara/aprendizado/` |
| Cliente2 | `reel-dividido-por-video` (tela-dividida) | `clientes/Cliente2/marca2Content/modelos/reel-dividido-por-video/aprendizado/` |
| Joao | `dividido-mascara` (fala-com-cenas; sem efeito sonoro de transição) | `clientes/Joao/vegasContent/modelos/dividido-mascara/aprendizado/` |
| Joao | `reel-dividido-por-video` (tela-dividida, faixa vermelha com manchete) | `clientes/Joao/vegasContent/modelos/reel-dividido-por-video/aprendizado/` |
| Cliente3 | `dividido-mascara` (fala-com-cenas; cena de filme real com whoosh, variante notícia) | `clientes/Cliente3/cliente3Content/modelos/dividido-mascara/aprendizado/` |
| Joao | `frase-fixa` (uma frase fixa numa caixa preta ou branca o vídeo inteiro, em cima da cabeça ou no peito conforme a posição da pessoa; sem legenda, b-roll, música nem efeito) | `clientes/Joao/vegasContent/modelos/frase-fixa/aprendizado/` |
| Cliente1 | `dividido-mascara` (portado de Cliente4/dividido-mascara pelo Estúdio em 2026-10-16; autocontido em `clientes/Cliente1/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Cliente1/cliente1Content/modelos/dividido-mascara/aprendizado/` |
| Cliente1 | `documentario` (portado de formato/documentario pelo Estúdio em 2026-10-16; autocontido em `clientes/Cliente1/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Cliente1/cliente1Content/modelos/documentario/aprendizado/` |
| Cliente1 | `chamada-na-tela` (anúncio de fala da Produto1: gancho que atrai no t=0 em 4 variações, título neon #FF9800, legenda de uma palavra no peito, motion limpo de vez em quando, cama musical, voz nivelada por trecho; motor `tela.py` + `lote.py`) | `clientes/Cliente1/cliente1Content/modelos/chamada-na-tela/aprendizado/` |
| Joao | `critica-ao-absurdo` (trecho de 20-30 s do vídeo absurdo em cima com legenda roxa de 1 a 3 palavras, foto fixa do João reagindo embaixo, divisão em y=1046; resposta dele em tela cheia no fim; ref. reel DdXnhWBPmza) | `clientes/Joao/vegasContent/modelos/critica-ao-absurdo/aprendizado/` |
| Cliente2 | `mundo-3d` (portado de formato/mundo-3d pelo Estúdio em 2026-10-18; autocontido em `clientes/Cliente2/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Cliente2/marca2Content/modelos/mundo-3d/aprendizado/` |
| Cliente2 | `explicador-3d` (portado de formato/explicador-3d pelo Estúdio em 2026-10-18; autocontido em `clientes/Cliente2/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Cliente2/marca2Content/modelos/explicador-3d/aprendizado/` |
| Avulso | `frase-fixa` (portado de Joao/frase-fixa pelo Estúdio em 2026-10-22; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/frase-fixa/aprendizado/` |
| Avulso | `critica-ao-absurdo` (portado de Joao/critica-ao-absurdo pelo Estúdio em 2026-10-22; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/critica-ao-absurdo/aprendizado/` |
| Joao | `caixinha-de-perguntas` (caixa de pergunta do Stories do Instagram fixa acima da cabeça: faixa #262626 com o título + pergunta em SF Pro peso 680 47 px no branco, igual ao print; fonte nunca encolhe, caixa cresce pra baixo; pergunta e título editáveis no Editar o texto; sem legenda, b-roll, música nem efeito) | `clientes/Joao/vegasContent/modelos/caixinha-de-perguntas/aprendizado/` |
| Cliente3 | `caixinha-de-perguntas` (portado de Joao/caixinha-de-perguntas em 2026-10-23; Cliente3 falando: caixinha no PEITO; equipe do escritório: caixinha em cima + legenda simples embaixo pelo legenda.py do modelo; faixa cinza = tema do vídeo; sem zoom) | `clientes/Cliente3/cliente3Content/modelos/caixinha-de-perguntas/aprendizado/` |
| Joao | `analise-de-tela` (gravação de tela em cima, João embaixo seguindo o rosto, sombrinha na emenda e frase fixa o vídeo inteiro em faixas branca e vermelha #DE1C21, Gilroy ExtraBold; sem legenda, b-roll, música nem efeito; ref. reel De5M51LRqvy) | `clientes/Joao/vegasContent/modelos/analise-de-tela/aprendizado/` |
| Joao | `faixa-com-cenas` (só a câmera: cena em cima (dividido) ou em tela cheia, João em tela cheia nas teses; frase em faixas branca e vermelha #DE1C21; 2 estilos no PLANO.json: frase-fixa (frase o vídeo todo) e gancho-legenda (frase até ~9 s, depois legenda de 3 palavras na emenda ou no peito); abre dividido com cena forte de até 3 s) | `clientes/Joao/vegasContent/modelos/faixa-com-cenas/aprendizado/` |
| Joao | `explicador-3d` (motor novo com cara Loaded Dice: dentista protagonista realista-feio de jaleco, Vila Serena no entardecer, consultório com painel de luz, escritório noir; roteiro do 1º vídeo: cidade-12-mil-loaded; motor roda da base do formato) | `clientes/Joao/vegasContent/modelos/explicador-3d/aprendizado/` |
| Joao | `editorial` (análise de caso narrada na voz do João (perfil VoiceStudio 8800a992), @soujoaovegas leve no topo: clipe real com som, pessoa recortada em camadas, print da fonte, foto do Commons, rajada P&B, cartão, pílulas, Venn, ícone em círculo, grupo de conversa e texto que acende; vermelho #e0353f na palavra forte, Gilroy/Inter; beat sombrio; 1º vídeo: grupo-por-crenca, v3 com roteiro simples, a técnica no fecho e música famosa na batida) | `clientes/Joao/vegasContent/modelos/editorial/aprendizado/` |
| Joao | `legenda-no-lado` (legenda-no-lado, 16:9 de carro: corta todo silêncio, tira o volante com zoom 1,25x e escurecido, pessoa à esquerda, legenda do lado direito em maiúsculas, 3 palavras, palavra falada em dourado #d4af37; em teste até o 1º vídeo aprovado; criado em 04-nov-2026) | `clientes/Joao/vegasContent/modelos/legenda-no-lado/aprendizado/` |
| Joao | `imagens-na-fala` (pessoa em tela cheia, título fixo amarelo no topo, legenda pequena abaixo do queixo e cartões de gravura/pintura antiga em corte seco em 3 posições, um por ideia; ref. reel DecxbwzBRru; em teste, receita r1 criada em 05-nov-2026, ainda não pronto) | `clientes/Joao/vegasContent/modelos/imagens-na-fala/aprendizado/` |
| Avulso | `faixa-com-cenas` (portado de Joao/faixa-com-cenas pelo Estúdio em 2026-10-29; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/faixa-com-cenas/aprendizado/` |
| Avulso | `caixinha-de-perguntas` (portado de Joao/caixinha-de-perguntas pelo Estúdio em 2026-10-29; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/caixinha-de-perguntas/aprendizado/` |
| Avulso | `editorial` (portado de formato/editorial pelo Estúdio em 2026-10-29; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/editorial/aprendizado/` |
| Avulso | `explicador-3d` (portado de formato/explicador-3d pelo Estúdio em 2026-10-30; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/explicador-3d/aprendizado/` |
| Avulso | `documentario` (portado de formato/documentario pelo Estúdio em 2026-10-30; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/documentario/aprendizado/` |
| Avulso | `reel-dividido-por-video` (portado de Joao/reel-dividido-por-video pelo Estúdio em 2026-10-30; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/reel-dividido-por-video/aprendizado/` |
| Avulso | `dividido-mascara` (portado de Joao/dividido-mascara pelo Estúdio em 2026-10-30; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/dividido-mascara/aprendizado/` |
| Avulso | `chamada-na-tela` (portado de Cliente1/chamada-na-tela pelo Estúdio em 2026-10-30; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/chamada-na-tela/aprendizado/` |
| Avulso | `lista-de-estaticos` (portado de formato/lista-de-estaticos pelo Estúdio em 2026-10-30; autocontido em `clientes/Avulso/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Avulso/avulsoContent/modelos/lista-de-estaticos/aprendizado/` |
| Cliente3 | `editorial` (portado de formato/editorial pelo Estúdio em 2026-10-30; autocontido em `clientes/Cliente3/`. Descrever aqui a cara do modelo pra este cliente conforme o João aprovar) | `clientes/Cliente3/cliente3Content/modelos/editorial/aprendizado/` |
