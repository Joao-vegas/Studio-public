# Changelog

Versões marcadas só quando um conjunto coerente fica pronto e testado.

## v2.2.1 — 2026-10-30

Arrumação pelo uso do João.
- **Novo vídeo começa por "O que você tem?"**: vídeo gravado (a voz vem dele) · só a minha voz (MP3, com a transcrição pra conferir e baixar) · só o roteiro (aí escolhe a voz pronta).
- **Esperando você**: uma conta só no Início, no selo e na página; vídeos do chat entram como "feito pelo chat" e versões do mesmo vídeo viram 1 card; faixa "Rodando agora" com o que está em produção.
- **Corte**: "↶ Voltar ao corte anterior" (nada se perde) e, depois de aprovar, volta pro vídeo.
- **Menu enxuto** (18 → 13, com Em andamento de volta), **Criar estilo novo** em Estilos, **melhorias dentro de cada estilo**, referências de teste fora e capa certa nos cards de referência.
- Vídeos de teste do Avulso apagados (Lixeira do Mac, 14,2 GB).

## v2.2.0 — 2026-10-30

O vídeo pronto vira o editor, a música é viral sem voz e o app fica rápido.
- **Página do vídeo pronto = editor por cenas**: Aprovar e Quero alterar no topo, a tira das cenas de agora e o painel do Claude do lado (o miolo do Editar vídeo virou um parcial só); a produção fica em "Como foi feito". Depois de aprovar: "Aprovado ✓ — e agora?" (baixar, Finder, guardar no iCloud, usar como referência do estilo, liberar espaço, desfazer aprovação).
- **Música**: Procurar por direção ("tensa de suspense, sem voz"), virais em versão instrumental medidas pelo Demucs, gênero que briga fica de fora, checagem de marca d'água, "Outras 3", volume em mais baixa · normal · mais alta, música e efeitos no Documentário e nos gravados; "Não usar mais" e "Apagar" faixa.
- **Voz**: "Meu áudio (MP3 ou MP4)" na narração; com o vídeo gravado as vozes somem; o VoiceStudio sobe sem janela, sozinho, e a tela diz "ligando" em vez de "ocupado".
- **Imagens**: ação da fala vira vídeo da ação, clichê de banco e imagem quase igual reprovam (`casar_imagem`); 52 cenas trocadas nos testes.
- **Apagar com prévia**: painel com o vídeo tocando, o tamanho, o que é cada coisa e Mostrar no Finder; Liberar espaço não oferece mais vídeo esperando aprovação ou editado há pouco, e ganhou "Desfazer a última limpeza".
- **Telas mais simples**: Referências numa porta só ("Jogar um vídeo"), página do estilo com "como as referências são usadas", Biblioteca em 4 abas com Buscar (grátis) e Gerar com IA (pago); capa escolhida em todo card.
- **Rápido**: toda tela abre em menos de 0,3 s com cache (Editar vídeo de 10,3 s para 0,19 s), capa e miniaturas nascem prontas em segundo plano, vídeos de lista só baixam no play; CLIP, ampliador e busca sem GPU dentro do Python, e render travado é abandonado.

## v2.1.1 — 2026-10-30

Acabamento pela revisão do João nos vídeos de teste.
- **Imagem casa com a fala**: `casar_imagem` (CLIP local e grátis) dá nota a cada cena contra a fala, acha dentro do vídeo o quadro que mostra o que a fala diz e pega a mesma pessoa em cenas vizinhas. Entra na produção, no Editar vídeo e na revisão. Kodak: a câmera de 1975 no lugar da terceira foto do engenheiro e a matéria real da falência de 2012.
- **Nada de fundo vazio**: no Editorial, ícone com emoji virou logo ou foto real (Spotify, Netflix, o CEO da Blockbuster) e toda cena sem foto própria tem a imagem da vizinha desfocada atrás. O jornal falso do Documentário saiu; foto pequena passa pelo upscale.
- **Texto fora do rosto**: no Faixa com cenas, com o João em tela cheia, a frase vai pra cima da cabeça ou abaixo do queixo; a conferência reprova texto em cima do rosto.
- **A edição chega no vídeo entregue**: o Editar vídeo atualiza o vídeo que a tela mostra (o anterior vira versão) e o vídeo volta pro "Ficou bom?".
- **Render que trava não segura mais nada**: limite com abandono e OpenCV sem OpenCL (o Python não carrega mais a placa de vídeo).

## v2.1.0 — 2026-10-30

O Editar vídeo passa a valer pra todo vídeo.
- **Todos os estilos editam por cena**: além de Editorial, Explicador 3D, Documentário e Faixa com cenas, agora Caixinha de perguntas e Frase fixa, Crítica ao absurdo, Análise de tela, Tela dividida, Fala com cenas, Chamada na tela e Lista de estáticos (`app/ferramentas/editor_gravados/`, um arquivo por estilo). Um pedido real em cada um, todos aceitos.
- **Vídeo montado à mão também edita** (modo livre): o Estúdio guarda os arquivos e o vídeo, roda o comando que montou e só aceita se, fora da cena marcada, o vídeo ficou igual; senão volta tudo. Vídeo sem a gravação ou sem o comando aparece com o motivo.
- **Python certo em todo processo**: o brew trocou o `python3` do sistema pra 3.15 sem as bibliotecas; o Estúdio agora abre tudo com a venv na frente e confere o ambiente depois de cada atualização.
- **7 melhorias que o Estúdio propôs foram aplicadas** (conferência de plano escuro, borrado e cenas repetidas; print do Editorial troca de plano; legenda sobe com timecode queimado; cabeçalho do jornal no Documentário). A do "Trocas demais" foi desfeita: reprovava os próprios vídeos de referência.
- **Editorial**: o grão cobre a tela inteira (ficava num retângulo cinza no canto) e a cena da conversa ganhou movimento. Os 4 vídeos de teste foram refeitos.
- **Checagem de ritmo calibrada pelas referências**: toda referência passa na checagem do próprio estilo, e o caso real de 16 s parado continua reprovado.

## v2.0.0 — 2026-10-30

O Estúdio passa a ser usado direto pelo app, sem o chat.
- **Editar vídeo por cena** com o Claude do lado (Editorial, Explicador 3D, Documentário, Faixa com cenas): elemento · cena · trecho · vídeo, print colado, versões que nunca se apagam, trocar a narração, material, **gerar imagem/vídeo por IA com o custo antes e só com Permitir**.
- **Novo vídeo numa tela**: pra quem, todos os estilos com busca e etiquetas, prévia viva com o "momento a momento" de todas as cenas da referência, referências com peso e mistura de estilos, modelo + esforço (low Rápido → max Ultra), seguir direto ligado.
- **Editorial pela tela** (voz em blocos conferida, print da fonte sem Wikipédia, clipe real, recorte, batida, foto grande) e **Editorial falado**: o vídeo gravado do João vira a narração e ele aparece se quiser.
- **Aprovação no resultado**: "Ficou bom?" com Assistir · Aprovar · Quero alterar → "Aprendi" (regra no cliente, no estilo ou geral). O app revisa cada vídeo sozinho e propõe melhoria no motor com Aplicar/Desfazer.
- **Referências**: vários vídeos de uma vez, o Estúdio junta sozinho ao estilo certo (com Desfazer) e propõe variações na mesma pegada.
- **Vozes**: VoiceStudio único (o aplicativo, aberto sozinho), todas as vozes com prévia em português, voz com emoção marcada pelo roteiro. Elenco por estilo com roupa e cor.
- **Dinamismo como regra geral** (REGRAS.md G26) com checagem no vídeo pronto; fontes grátis novas (Internet Archive, Openverse, NASA...), ampliar foto, parallax 3D e separar a voz do clipe, tudo local.
- **Conexões, repositórios e atualizações** simples (Gemini fora; Remotion aposentado pro backup), apagar de verdade (Lixeira do Mac), sem cópia repetida de bruto (clone APFS) e tela Liberar espaço. Visual escuro espaçado, menu aberto e recolhível.

## v1.3.0 — 2026-10-29

- Formato **Editorial** (4 referências estudadas quadro a quadro), referência escolhida no Criar, vídeo nosso vira referência, voz fixa do VoiceStudio, transcrição que não para no meio; saem Simulação 3D, Desenho 3D e Cinematográfico de evento.

## v1.2.0 — 2026-10-22

- **Produção em massa**: `/novo-lote` (um vídeo por bruto) e `/aprovar` (aprovar vários de uma vez).
- **Estilos e referência rápida**: catálogo de estilos; jogue um vídeo ou link e o Estúdio entende o estilo sem copiar a fala. Editor de corte.
- **Custos em reais**: Hoje, Este mês e Por fila, com a origem de cada valor. Música e efeito sem repetir, com favoritos.
- Formato Frase fixa refinado; telas revistas espaço a espaço (Criar e Em andamento com etapas claras).

## v1.1.0 — 2026-10-16

- Formato Frase fixa (frase numa caixa o vídeo inteiro) com editor de texto em camada; tela dividida segue o rosto; trocar a cena de apoio no storyboard.
- Corte: gaguejo não apaga mais fala boa. Gemini: rodízio sem chave repetida.
- Diálogo 3D e Passos numerados removidos (backup em `~/.config/estudio/backups/`); novos formatos Simulação 3D e cliente Marca1.

## v1.0.2 — 2026-10-12

- Formato Explicador 3D: gente estilo GTA 2000, mundos 3D, ações presas à narração e efeitos da ação.

## v1.0.1 — 2026-10-10 — correção de padronização

- **Chaves só em `app/.env`**: cliente não tem `.env`; conectar qualquer chave em Configurações cai ali (permissão 600, valor nunca aparece); leitura sem pôr nada no ambiente do processo; mapa só com nomes em `app/CHAVES.md`.
- **Clientes padronizados**: todos iguais, `identidade.json` + `<nome>Content/{entrada, material, modelos, output, transcricoes}`. Verificador `app/ferramentas/clientes_padrao.py` e cliente novo já nasce no padrão. Sem README, `.env`, `automacao`, `documentacao` nem banco por cliente (banco de imagem e música só no `acervo/`).
- **Scripts dos clientes foram para `app/automacao/`** com um `load-env.js` único; corrigido o caminho do Remotion que fazia as geradoras pararem no passo 5 de 6.
- **Formatos sem exemplo removidos** (movidos para backup): anúncio com manchetes, plantão, VSL gravada, como funciona, rosto com manchetes e o descritor "Só cortar" (o corte de vídeo, a tela /cortes e o aprendizado de corte continuam). A galeria tem 8 formatos.
- **Apagar vídeo apaga tudo**: pasta e mp4, job, sandbox, andamento, miniatura e metadados; preserva exportado, acervo, custo e regras; referência protegida.
- **Diálogo 3D com tela dividida** (`layout: dividido`), com a tela cheia inalterada; "sem legenda" continua valendo em todos os formatos que permitem e no dividido.
- **Correções**: página de formato com `regras.md`, Apagar de Meus vídeos protegendo referência, `saidas.apagar` com pasta de mesmo nome, chave do Groq nos scripts do `dividido-mascara`, texto de análise sem `.env` de cliente.
- **README** com a lista de ferramentas e repositórios usados e a explicação da fila de tarefas grandes.
- 780+ testes verdes, rodados arquivo por arquivo.

## v1.0.0 — 2026-10-10

Primeira versão do repositório `Studio` (antes `producao-reels`, histórico antigo descartado).

### Base
- Formatos como receita (`formatos/`), clientes como pele (`clientes/`), acervo único de b-roll, música e efeitos.
- Contrato dos formatos (`formatos/CONTRATO.md`) cobrado por `formatos.py validar`: passos, `material_aceito`, `layouts`, `legenda`.
- Regras em 3 camadas (cliente > formato > geral) e aprendizado a partir das correções.

### Novo nesta versão
- **Briefing em conversa** (passo 0) com pastas ligadas, ligação por nome e manifesto `ESTUDIO.md`; o briefing manda só no vídeo atual.
- **Saídas**: apagar vídeo do disco, marcar vários, guardar como referência (referência nunca sai em lote).
- **Referência que obriga**: o storyboard é reprovado se a "Referência analisada" faltar; aviso de layout antes de gastar.
- **Diálogo 3D**: cena do produto em tela cheia, legenda visível no storyboard, interruptor **sem legenda** (vale para todos os formatos que permitem) e botão **Usar em outro formato**.
- **Um estado só** por vídeo entre Em andamento, Início e Meus vídeos.
- **Custos claros** (dinheiro que saiu × preço de tabela), escolha plano ou API para vídeos e para a fila de construção.
- **Chaves num lugar só** (`app/.env`), leitura sem `os.environ`, mapa em `app/CHAVES.md`.
- **Página de cliente simples** (cores e vídeos entregues) e página de formato mais curta.
- Fila de trabalho pesado pela API (`via_api.py`) com teto, retomada e trava de assinatura.

### Testes
- 739 testes verdes, rodados arquivo por arquivo.
