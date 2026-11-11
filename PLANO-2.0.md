# Plano da versão 2.0: editar o vídeo pela tela, cena por cena, com o Claude do lado

Pedido do João em 29-out-2026, vendo uma ferramenta de Reels/documentário (pipeline à esquerda, player e linha do tempo
no meio, Claude à direita). A 2.0 só sai quando isto estiver pronto (antes disso as versões seguem 1.x).

## Por que

Hoje o João manda os vídeos pro chat porque **pela tela dá muito erro e a IA não segue fielmente**. A causa provável: a
tela manda um pedido grande ("refaz o vídeo com esse feedback") e a IA mexe em tudo. A regra da 2.0 é o contrário:
**pedido pequeno e com alcance marcado**. O João marca o que quer mudar e a IA só pode tocar naquilo; o motor refaz só
aquela cena.

## O que ele pediu (nas palavras dele)

1. **Linha do tempo das cenas** embaixo do player: miniatura, fala e tempo de cada cena ("shot 2"). Clicou, o player vai pra ela.
2. **Claude do lado**, com alcance: **elemento** ("dentro da cena, só altere o elemento X") · **cena** · **trecho** (arrasta
   na linha do tempo) · **vídeo todo**. Sugestões prontas ("mais dinâmica", "apertar o tempo com a narração").
3. **Anexar print**: "tiro a print e falo: altere só esse". A imagem vai junto com a cena marcada.
4. **Pipeline com Refazer por etapa**: roteiro · voz · tempo das palavras · material · cenas · som · vídeo. Trocar só a voz
   sem refazer o resto.
5. **Escolher modelo e esforço do Claude em cada criação** (ex.: Sonnet 5.5 low). Já existe no `ia.py` (`--model`, `--effort`): falta pôr no Criar e no painel.
6. **Material de todas as fontes visível**: o que foi achado (clipe do YouTube, Commons, print, recorte) em miniaturas,
   pra trocar uma imagem por outra.
7. **Elenco fixo e visual**: personagens prontos (dentista, empreendedor...) com foto, **cor da roupa editável**, e no
   Criar "quero fazer com esse personagem". Base: `formatos/explicador-3d/base/elenco.js` (já tem 17 com figurino trocável).
8. **Toda mudança vira versão** (v1, v2, v3...) e dá pra voltar. **Nunca apagar versão.**
9. **Referência sempre à vista**: todo estilo mostra o vídeo de referência; o vídeo pronto pode virar referência (feito na 1.3).
10. **Criar mais simples**: hoje são 5 passos e ele acha confuso.
11. **Tudo bem visual**.

## Como encaixa no que já existe

- Formatos de motor (Editorial, Explicador 3D, Documentário): o vídeo já é uma lista de cenas (`cenas.json`, cada uma com
  `de`, `tipo` e os elementos: `imagem`, `texto`, `pessoas`, `quadros_de`...) e o `render.py` desenha qualquer instante
  (`--quadro`). **Elemento** = um campo da cena; **cena** = um item; refazer só a cena = renderizar o trecho e colar.
- Storyboard já sai um quadro por cena, com a fala: vira as miniaturas da linha do tempo.
- O editor de corte (`corte.js`) já tem linha do tempo com marcação: reaproveitar.
- Gravados (ffmpeg): cena = trecho do PLANO; fica pra depois dos formatos de motor.

## Mais pedidos (29-out-2026, depois do vídeo do Creatorize)

12. **Pegar o MÉTODO, não o modelo** de quem a gente estuda (virou REGRAS.md G0): estudo a 30 fps com o quadro de prova,
    régua juntando as referências, biblioteca, conferir o próprio trabalho em quadros seguidos, e **cada vídeo ensinando o
    estilo com causa e conserto no motor** (CLAUDE.md REGRA Nº 2, passo 4), pro próximo vídeo sair melhor de verdade.
13. **Ferramenta de estudar o vídeo do outro à vista**: hoje o `estudo_quadros.py` só roda escondido dentro da referência
    rápida. Precisa de um lugar na tela: joga o link → sai o estudo quadro a quadro.
14. **Apagar mais simples**: o que a IA cria vai somando; remover um estilo, um modelo ou um teste tem que ser um botão
    (indo pro backup, nunca apagando de vez). O peso do Estúdio fica nas ferramentas, nas referências e no método de estudo.
15. **Trocar a narração tem um lugar**: mudou a voz, o tempo das palavras muda e as cenas têm que se ajustar sozinhas,
    sem perder as edições feitas por cena.
16. **Vozes do VoiceStudio na tela**: todas as vozes grátis, prévia em português, a voz clonada do João, e qual motor cada
    uma usa. Completo, simples e visual.
17. **Pode mudar o design inteiro** se precisar: a experiência de hoje está ruim.
19. **Proporção em todo vídeo**: ~70% o fundamento das referências do estilo (entender o porquê de cada edição, não copiar a cara) e ~30% inovação vinda das críticas e aprendizados dos últimos vídeos. O brainstorm vem antes de criar (REGRAS.md G0, `producao.REGRA_ESTILO`).
18. **Como trabalhar**: o Opus orquestra, testa, deu erro volta; no máximo 1 ou 2 agentes de cada vez (limite do plano).

20. **Ideia (29-out): Editorial falado** — o João gravado é a narração. O vídeo dele entra cortado (corte automático) e vira o
    `words.json`; as cenas do Editorial vão por cima da voz dele, e ele aparece só nos momentos fortes: gancho, virada e fecho
    em tela cheia (peça `fala`: o trecho gravado dele), ou recortado no cantinho em cima do print (ref. 3, "narrador no
    cantinho"; o `recorte` já faz camada). Seria o Editorial aceitando `video-ou-roteiro`, sem formato novo.
    Três entradas: (a) só roteiro → narração na voz clonada dele (já funciona); (b) só o MP4 dele falando → a fala dele é a
    narração e ele aparece nos momentos fortes; (c) roteiro + o MP4 dele lendo → o roteiro é o gabarito do corte (tira tropeço).
    **FEITO (30-out):** o Editorial é `video-ou-roteiro` e aparece no `/criar-agora` com "Um vídeo gravado"; (c) é o vídeo com o roteiro colado em
    "O que o vídeo fala". Peça nova `fala` (`index.html` + `render.py`: quadros do `work/fala/fala.mp4` no tempo da cena, legenda forte; `modo`
    `cheia` ou `canto` sobre um print); `base/exemplos/preparar-fala.py` (corte → `work/fala/` com voz, palavras e sugestão de gancho/virada/fecho;
    roteiro vira gabarito e corrige nome próprio); `g.fala()` no `gera_lib`. **O João escolhe se aparece** ("Você aparece no vídeo?" → `job["aparecer"]`
    sim/não; não = só a voz dele, nenhuma cena `fala`). No Editar vídeo a cena é "Você falando" (elemento "Posição do João": cheia ↔ canto; trocar o
    tipo tira ou põe ele) e a voz dele não se troca. **Misturar estilos** (aba "Referências e peso" → "Misturar com outro estilo"): as referências do outro
    estilo (estudos, ou os exemplos se não tem) entram com peso em `job["estilo_refs"]` (cada uma com o `formato`) e o pedido da produção explica a
    mistura. Testes: `test_editorial_falado.py`. COMO-FAZER.md do Editorial tem as 3 entradas.

## Feito

- 29-out: **Editar vídeo** (menu e botão "Editar por cena" no vídeo): player, linha do tempo com miniatura e fala de cada
  cena, Claude do lado com alcance Elemento · Cena · Vídeo todo, print colado (Cmd+V) ou anexado, modelo e esforço por
  pedido, versões (v1 = original) com "Voltar pra esta". A fidelidade é do Estúdio, não da IA: `editor._fiel` só aceita a
  mudança no alcance marcado (campos que andam juntos em `JUNTOS`) e devolve o resto; texto novo acende na palavra falada
  (`editor._tempos`). Testado de verdade: elemento "texto" da cena 6 em ~1 min com Sonnet low. Testes: `test_editor.py`.

- 29-out (noite): **Vozes** (tela, prévia em português com pergunta, desenhar por descrição ou clonar de gravação, voz por
  cliente; `vozes.py`) · **Trocar a narração** e **Refazer por etapa** (voz → palavras → cenas → vídeo) no editor, com as
  edições por cena reaplicadas (`editor.edicoes.json`) · **Estudar um vídeo** (link → estudo a 30 fps → vira referência;
  `estudos_tela.py`) · **Trecho** (Shift+clique) · **Material deste vídeo** (trocar foto/clipe sem IA) · **Tirar** estilo,
  vídeo de teste e estudo (lixeira, `remover.py`) · **Peso de cada referência** e **modelo/esforço** no Criar ·
  **Novo vídeo numa tela** (`/criar-agora`: 01 vídeo · 02 estilo com Como funciona/Referências/O que usa · 03 história
  Claude escreve ou eu tenho · 04 direção + qualidade Padrão/Conferido/Ultra) · tema escuro padrão · motor do Editorial:
  música medida (voz-17 LU), checagem de fonte (nunca Wikipédia), repetição (clipe 1x), print com **grifo** pelo OCR.
- 29-out: **Alteração = Sonnet, esforço alto** (pedido do editor e feedback do vídeo; `ia.para_alteracao`), salvo escolha no próprio pedido.
- 29-out (noite): **Editar vídeo nos outros formatos de motor**: `editor.MOTORES` (uma camada por formato: rótulos em português, o que anda junto, etapas, narração/material, dicas pra IA, render da pasta ou da base). Explicador 3D (Lugar · Personagens · Ação · Câmera · Objetos · Transição; render da `base/`; `elenco` e `mundos` só aceitam acréscimo) e Documentário (Nome · Cargo · Texto · Vídeo...) entram na lista. Testado: Explicador (ação da cena 3, ~1 min de Claude + ~15 min de render com a máquina ocupada; só a cena 3 mudou) e Documentário (cargo da cena 2, 2,5 min). Sem narração trocável nem material por aqui nesses dois (a decupagem refaz tudo): pelo chat.
- 29-out (noite): **Editar vídeo nos GRAVADOS, começando pelo Faixa com cenas**: a cena é cada trecho do `PLANO.json` (janelas + os trechos só do João no meio, que viram cena "Só o João"). `editor._ler_faixa` / `_gravar_faixa` fazem a ida e volta sem mudar o jeito que o `gerar.py` lê; a IA edita só `editor/cenas.json` (a lista de cenas) e nunca o PLANO. Elementos: Tela · Cena de cima/tela (+ ponto do clipe) · e, valendo pro vídeo todo, Frase da faixa · Enquadramento do João (`MOTORES["faixa-com-cenas"]["globais"]`). Miniatura = quadro do meio da cena tirado do vídeo pronto (ffmpeg, ~2 s pra 11 cenas); render = `gerar.py` do modelo; o tempo da fala (`de`) não muda nem no pedido de vídeo todo (`_fiel(..., tempo_fixo=True)`). Testado: frase da faixa da `_sandbox-12-anos` (cópia) em ~50 s com Sonnet low, só a frase mudou. Sem narração nem material trocável (a voz é o João gravado). A lista `/editar` avisa quais gravados ainda não editam por aqui (`editor.ainda_nao`).
- 29-out (noite): **Gerar com IA no Editar vídeo** (`app/ferramentas/gerar_ia.py`, rotas `/editar/gerar/*`, caixa no painel do Claude): com uma cena marcada, "✦ Gerar com IA" abre a caixa (texto já sugerido pela fala + estilo do formato, imagem ou vídeo, modelo do cardápio do `broll_ia`, opções, custo em R$ e US$ na cotação da tela de Custos, saldo da kie.ai). Nada vai pra kie.ai antes do "Permitir e gerar" (rascunho com custo congelado + nonce → confirmar; sem retry de createTask; teto US$ 2 por pedido). As opções ficam em `<pasta>/editor/gerados/` com modelo, prompt e custo; clicar numa = `usar_material` (versão nova, dá pra voltar); o gasto vai pro `~/geracoes/_custos.tsv` (projeto = cliente, `custos.registrar_kie`) e aparece em Custos. Vídeo = imagem atual da cena → clipe (quadros a 30 fps em `quadros_de`). O Claude do editor NÃO gera: sem imagem boa, escreve `editor/sugestao_ia.json` e a tela mostra o cartão "Não achei imagem pra cena N. Gerar com Grok Imagine (~R$ 0,11)?" com Permitir · Ajustar · Dispensar. Só nos formatos com material trocável (Editorial). Testes: `test_gerar_ia.py` (kie.ai simulada).
- 30-out: **Editar vídeo em TODOS os estilos.** Pacote `app/ferramentas/editor_gravados/` (um arquivo por estilo gravado, contrato dos ganchos no `__init__.py`: fonte, arquivos, precisa, achar, ler/gravar, cmd, saida, onde/conferir). Entraram Caixinha e Frase fixa (camada.json + camada.py), Crítica ao absurdo, Análise de tela (gerar.sh padrão), Tela dividida (refaz o work/master.mp4), Fala com cenas (refaz só o corte ou o card do beat), Chamada na tela (config.json do tela.py) e Lista de estáticos. Vídeo montado à mão cai no **modo livre** (`livre.py`): o Estúdio guarda os textos e o vídeo, roda o comando e compara quadros fora da cena (vazou = volta tudo). Sem gravação ou sem comando: aparece com o motivo, sem botão. Um pedido real por estilo, todos aceitos (33 s a 3 min). Junto: `_comum.com_venv()` (todo processo filho usa a venv; o `python3` do sistema virou 3.15 pelo brew).
- Falta: Look/Elenco visual com cor de roupa (Explicador 3D), redesenho do resto das telas no padrão escuro do Novo vídeo, Clientes mais simples ("estilos do João" confuso).

## Ordem

1. ~~Tela "Editar o vídeo"~~ (feito 29-out; falta "Trecho" arrastando na linha do tempo).
2. Pipeline com Refazer por etapa + modelo e esforço no Criar.
3. Painel de material (miniaturas por fonte, trocar).
4. Elenco visual com cor de roupa (Explicador 3D primeiro).
5. Criar em uma tela: o que tem + estilo (com o vídeo de referência) + cliente; o resto recolhido.
6. Levar a tela de edição pros outros formatos de motor e depois pros gravados.

## Junto disso

- Muitos estilos: firmar 3 ou 4 até o nível do Editorial antes de criar outro; o resto vai pra "Mais formatos (em teste)".
- Música conhecida das redes em todo formato com música (REGRAS.md G24).

## Uso direto pelo app (29-out, noite): o João para de usar o chat

Pedido: "pegue tudo que foi feito, ajuste as falhas que podem me impedir... criar novas referências etc. é sempre importante
criar e pedir se aprovou, pra ver se o fluxo está certo; quero parar de usar o Estúdio pelo chat e usar direto no app...
todas as ferramentas do Estúdio buscando atualização (get-brolls, VoiceStudio e tudo mais)... loop de melhoria, mas com fim".

Regra de ouro: **todo fluxo que cria alguma coisa cria e para pedindo "Aprovou?"** (vídeo, referência, estilo novo, estudo,
voz nova, elenco, regra aprendida). Só segue (ou grava de vez) com o clique do João; "não" volta com o pedido de ajuste.

Lista de conferência (cada item tem que funcionar pela tela, sem o chat):
1. **Criar** (`/criar-agora`): Pra quem no topo (Avulso; `?cliente=`), todos os estilos (busca, etiquetas, 5/ver todas,
   apagado com motivo), Como funciona + storyboard momento a momento + referências com peso (ou "só esta"), Claude escreve /
   eu tenho, voz em cartões (todas do VoiceStudio, prévia em português), Força do Claude 0-100, qualidade, seguir direto,
   personagem (Explicador). O que foi escolhido chega no job e na produção (ia, voz, refs, personagem, qualidade).
2. **Produção pela tela por estilo**: o Editorial (e o Explicador 3D e o Documentário) NUNCA rodou pela esteira da tela,
   só pelo chat: tem que sair pela tela com tudo que o motor cobra (fonte confiável, nunca Wikipédia, grifo pelo OCR, clipe
   real com som, recorte, música famosa na batida medida em LUFS, voz fixa do cliente, @ no topo, sem repetir, 70/30 + brainstorm).
   Gravados: entra cortado sozinho, estilo, storyboard, aprovar, final. Lote e aprovar em lote.
3. **Aprovação**: Esperando você mostra tudo que espera o João (storyboard, vídeo pronto, referência a confirmar, estilo novo,
   regra aprendida); "Ficou bom?" → aprovar ou "Quero alterar" (feedback vira regra pela REGRA Nº 2 e a tela mostra
   "Aprendi: <regra> · camada <cliente|estilo|geral>" com OK / "não é isso").
4. **Editar vídeo** por cena (Editorial, Explicador 3D, Documentário, Faixa com cenas): elemento/cena/trecho/vídeo, print,
   versões, narração, material, **gerar imagem/vídeo por IA com custo antes e Permitir**; desde 30-out em todos os estilos (gravados pelo `editor_gravados/`, feito à mão pelo modo livre).
5. **Referência e estilo**: Jogar uma referência → entende → Confirmar (gate); Estudar um vídeo (30 fps, vídeo inteiro
   medido, folhas ±0,3 s) → juntar ao estilo; vídeo pronto vira referência; criar estilo novo → 1º vídeo → aprovar → pronto.
   Método, não modelo.
6. **Vozes**: todas do VoiceStudio (perfis + arquétipos), prévia em português, busca/etiquetas, usar; desenhar; clonar;
   **emoção automática pelo roteiro** (variações da voz por emoção; o Claude marca a emoção de cada frase; a tela mostra e
   deixa trocar). **Um VoiceStudio só** (o aplicativo); o Estúdio abre o aplicativo sozinho se estiver fechado; nunca troca
   pra voz paga sem avisar.
7. **Elenco** por estilo (`/elenco/<slug>`), roupa/cor mudando visível, no Criar e na página do estilo.
8. **Conexões, custos, atualizações**: cada app com situação real, Testar e "onde pego a chave"; "Se fosse pela API"; **toda
   ferramenta confere atualização** (Claude Code, Codex, VoiceStudio, get-brolls, skill Gerador de imagem e vídeo, yt-dlp,
   rembg, playwright, tesseract, ffmpeg, HyperFrames...) e a tela mostra; versão grande espera o João.
9. **Visual**: escuro padrão, espaçado, menu aberto com a explicação de cada item, claro coerente, celular sem rolagem
   lateral, título que não corta.
10. **Custo leve**: alteração = Sonnet esforço alto; kie.ai só com Permitir e preço na tela; nada pago sozinho.
11. **Testes**: suíte verde (as 6 falhas antigas do Frase fixa removido também: ajustar os testes ao que existe hoje).
- 29-out (noite): **O Estúdio aprende e melhora sozinho, pelo app.** Revisão depois de cada vídeo (`revisao.py`, runner dispara), melhoria do motor com Aplicar/Desfazer e prova (`melhoria.py`, `/melhoria/<id>`, `/melhorias`, Esperando você), passar a limpo o histórico com OK (>20 linhas novas por modelo), Recarregar agora sem terminal (`recarregar.py`). Testes: `test_revisao_autonoma.py`. Falta: revisão dos vídeos feitos só pelo chat (sem job.json), prova com quadro renderizado só nos estilos de motor com `--quadro` (gravado prova por sintaxe, validar e testes).
