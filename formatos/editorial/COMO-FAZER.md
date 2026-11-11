# Como fazer: Editorial

**Quando usar:** análise de caso real narrada (político, artista, influenciador, estudo famoso) que vira lição de
posicionamento: gancho com nome conhecido → o caso, com imagem real → o mecanismo (estudo, livro, dado) → vira pra
você/seu negócio → fecho seco. Conteúdo de topo da zona editorial.
**Régua:** o exemplo principal (o 1º de "exemplos" no `formato.json`) e os 4 estudos quadro a quadro em
`estudos/<NN-nome>/estudo-quadros/` (a régua de número fica em `estudo-quadros/`). Régua de estilo e qualidade, não molde: cada
referência tem uma edição um pouco diferente e o vídeo novo escolhe as peças pelo que o roteiro fala. Cada vídeo fica no
nível dele ou melhor; se sair melhor, vira o exemplo: `python3 app/ferramentas/formatos.py exemplo editorial <mp4>`.
**Motor:** `base/render.py` (genérico do Estúdio) + `base/index.html` (biblioteca de 13 cenas, ver `base/README.md`).
**Som:** narração pela voz configurada, música VIRAL do momento (refrão/drop) abaixo da voz, efeitos só na ação (20-26 por minuto).

## As três entradas (formato.json → "entrada": "video-ou-roteiro")

No `/criar-agora` o Editorial aceita "Um roteiro" e "Um vídeo gravado"; a opção (c) é o vídeo com o roteiro colado em "O que o vídeo fala".

- **(a) Só o roteiro → voz clonada.** O caminho de sempre (`preparar-narracao.py`): a voz é gerada, as cenas cobrem o vídeo todo.
- **(b) Só o MP4 dele falando.** O corte automático entra sozinho (`producao.cortar_sozinho` → `work/joao.mp4`); `base/exemplos/preparar-fala.py <sandbox>`
  tira dali `work/fala/` (`fala.mp4` 1080x1920 a 30 fps, `voz.wav` = a narração, `words.json`, `momentos.json` com a sugestão de gancho, virada e fecho).
  As cenas do Editorial vão por cima da voz dele. **Ele aparece ou não: escolha do João no Criar (`job["aparecer"]`).**
  *Sim, nos momentos fortes:* peça `fala` (`g.fala(de, "cheia")`) no gancho, na virada e no fecho, tela cheia, legenda forte (Gilroy grande, palavra-chave
  em vermelho, soco de zoom a cada bloco), até ~6 s cada; e 1 ou 2 vezes `g.fala(de, "canto", imagem=<print>, lado="dir")`: ele num cartão no cantinho em
  cima de um print ou foto real (ref. 3, "narrador no cantinho"). *Não, só a voz:* nenhuma cena `fala`, as cenas do Editorial cobrem tudo sobre a voz dele.
- **(c) Roteiro + o MP4 dele lendo.** Igual à (b), e o roteiro (`work/roteiro.txt`) é o gabarito: já guia o corte (tira tropeço e repetição) e o
  `preparar-fala.py` corrige a grafia de nome próprio pelo roteiro e lista em `momentos.json → conferencia_roteiro` o que faltou e o que sobrou.

A peça `fala` não gera cena de vídeo nova: `render.py` extrai os quadros do `fala.mp4` no tempo da cena (cache em `work/fala-quadros/`). No Editar vídeo ela
aparece como "Você falando" (elemento "Posição do João": cheia ↔ canto); trocar a cena por foto/print/clipe tira ele, trocar por `fala` põe.
A voz dele não se troca ("Trocar a narração" fica desligado nesse vídeo); a fala só muda trocando o vídeo gravado.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

0. **Roteiro.** Língua do povo, frase curta, a ideia central sempre com a mesma palavra (fato × crença); nome difícil vai pra tela, não pra fala.
1. **Preparar a narração (ou a sua fala).** (Entrada por roteiro:) `voz.falar` com perfil fixo (nunca a voz "default", que troca de pessoa por bloco) e o número por extenso; `base/exemplos/apertar.py` (pausa pós-frase ~0,2 s);
   `corte.py transcrever --groq` em `work/words.json`. (Entrada por vídeo: tudo isso é o `preparar-fala.py`, em `work/fala/`.) O Groq às vezes para no meio: confira a última palavra e, se
   faltar, transcreva o resto à parte e junte. Nome próprio certo no words.json.
2. **Imagem.** Print só de matéria ou página de fonte confiável (CNN, NYT, Estadão, Globo, Folha, BBC...), **nunca Wikipédia nem site duvidoso**, com a página anotada em `prints/origem.json` (sem origem a checagem reprova). Depois, Clipes reais com `yt-dlp --download-sections` (1-2,5 s, `crop=ih*9/16:ih,scale=1080:1920,fps=30` em `clipes/q-<nome>/` + o som em mp3), pessoas recortadas com rembg (`isnet-general-use`), print da fonte com Playwright quando a fala cita estudo/dado, e fotos: 30-40 por minuto, reais e do caso: `base/exemplos/commons.py <pasta> consultas.json` (Wikimedia Commons,
   guarda a origem e a licença) + o material liberado. Olhar a folha de contato e descartar o que não casa com a fala. **Quem decide é a medida (G6):** pra cada ideia ache o quadro com `app/.venv/bin/python app/ferramentas/casar_imagem.py melhores <vídeo> "<a frase>" -n 5 --saida <pasta>` (dentro de um clipe ou vídeo real; descreva o que se VÊ) e confira com `casar_imagem.py pontuar <imagem> "<a frase>" --outras "<outras falas>"`. A mesma pessoa nunca em 2 cenas vizinhas, no máximo 2 vezes no vídeo (a não ser que a fala seja sobre ela ali). **Ação = vídeo da ação (G6, 30/10):** fala que descreve uma ação (mandar dinheiro, pagar, digitar, correr, cair, ligar, assinar, rir...) leva um clipe real de quem faz aquilo, não foto parada (`clipe.py busca`, get-brolls, `casar_imagem.py melhores <vídeo> "<a ação>"`). **Real e viral, nunca clichê:** momento real do caso, depois clipe viral ou famoso, só então banco; ator posando e pilha de dinheiro genérica reprovam (`casar_imagem.py cliche <imagem>` abaixo de 0,05; o `conferir` acusa `cliche`). **Nada repetido:** nem a mesma foto nem outra quase igual perto no tempo (`quase_igual`).
   Mais de onde tirar: `python3 app/ferramentas/fontes_gratis.py imagem "<consulta>" --saida fotos` (Openverse, NASA, Internet Archive, só licença livre, `origem.json` + folha com fonte e tamanho) e `clipe.py busca` (get-brolls no YouTube + Internet Archive/NASA/Commons). No cenas.json: foto pequena sobe sozinha (Real-ESRGAN), `"parallax": true` dá câmera 3D na foto e `"so_voz": true` no efeito de clipe tira a música dele (Demucs).
3. **Montar os planos.** Se o João escolheu uma referência no Criar, ela é a base do ritmo. Copiar `base/exemplos/grupo-por-crenca-gera.py` (v2: clipe, recorte, corte na batida) e trocar as cenas: cada oração entra na 1ª
   palavra dela (`t("palavra", apos)`), a peça vem do que a fala diz (tabela "Quando usar cada peça" do README).
   Medidas: plano de ~0,5-0,8 s na mediana, câmera andando em ~95% dos quadros, creep ~12-14% da largura/s, maior
   trecho parado até 13 quadros, legenda curta a 62%, telas de texto até ~1/4 das cenas.
4. **Storyboard.** `render.py --storyboard` e `--quadro` nas cenas novas: nada vazio, texto legível, foto casando com a fala.
5. **Vídeo.** `render.py --cenas cenas.json`.
6. **Conferência.** `app/.venv/bin/python app/ferramentas/casar_imagem.py conferir <sandbox>` (nota de cada cena com imagem contra a fala; não casa ou pessoa repetida = trocar a imagem) + `estudo_quadros.py comparar formatos/editorial/estudo-quadros <mp4> --words work/words.json`
   (o que sair FORA e for estilo se corrige) + `conferir_video.py <mp4> --sandbox <sandbox>` (cauda, tela preta).

## Fundo vivo e ícone (30-out-2026, João: "quando eu só tenho o fundo cinza, essas coisas meio broxantes")

Nenhuma cena fica em fundo cinza liso. Peça sem foto própria (texto, ícone, Venn, contador, pílulas, linha, conversa, colagem) ganha sozinha a imagem da
cena vizinha desfocada, escura e andando devagar (`fundo_vivo`, ver `base/README.md`); fundo liso só com `"fundo": "liso"`. O `icone` **nunca leva emoji**: `imagem`
com a logo real (site oficial, press kit, Wikimedia Commons ou `fontes_gratis.py`; nunca Wikipédia) ou a foto real da coisa citada ("Spotify" = a logo do Spotify;
"a maior locadora do mundo" = a foto da loja). O `--conferir` reprova ícone sem imagem e cena em fundo liso sem imagem.

## Som e cena de apoio

Música: **viral do momento** (30-out-2026, João: "sempre que eu quiser música tem que ter uma opção... sempre coisas VIRAIS, não clichês"). `app/ferramentas/musica_viral.py`
lê as paradas públicas de hoje (Shazam BR e Mundo, Spotify BR e Global, Apple Music BR e EUA, Deezer; cache de 1 dia), escolhe 3 que casam com o clima do estilo e da fala
(cada uma com o motivo em uma linha), baixa o áudio oficial pelo yt-dlp, acha o **refrão/drop** (a subida de energia que fica alta, encaixada no kick mais perto) e corta o
arquivo da sandbox 0,15 s antes dele: o 1º quadro já é o momento conhecido. A grade da batida (`work/batida.json`) nasce desse ponto e o corte na batida do `gera_lib` segue valendo.
O `g.fechar` já faz tudo sozinho (`musica="auto"`); `musica_viral.py escolher <sandbox> --faixa <id> --dur <s>` fixa a que o João escolheu no Criar; `work/musica/sem` = sem música.
No Criar: "Música de fundo: Sem música · Viral do momento (3 opções com prévia de 10 s) · Procurar"; no Editar vídeo: "Música (vale pro vídeo todo)" (faixa, ponto de entrada, volume).
Volume ~17 LU abaixo da voz (o render mede e acerta), do primeiro ao último quadro, uma faixa por vídeo. **Marca d'água:** toda faixa passa por `musica_viral.checar` (voz falada que
não é a letra: "type beat", "prod. by", locutor; bip; silêncio no meio) e a reprovada nem vira opção. Rodízio: nada que o cliente usou nos últimos 8 vídeos; "Não usar mais" na
Biblioteca ou nas opções manda a faixa pra `acervo/musicas-reprovadas.jsonl` pra sempre. Aviso: é música famosa, o Instagram pode silenciar se não for a do app. Banco de trilha
(`base/audio/musicas/`, Mixkit) só como PLANO B sem internet. Efeitos de `base/audio/sfx/`: whoosh na transição
especial (negativo, flash, zoom), pop em cada peça da colagem e pílula, tique no número que assenta, notificação na
mensagem do grupo, clique no ícone; 0,14 a 0,25 de volume, nunca em corte comum. Cena de apoio: foto e print reais do
caso (Commons, material liberado, acervo), 0,3 a 1,3 s por plano, nunca banco de imagem com ator posando nem marca d'água.

## Regras

Ficam em `aprendizado/regras.json` (cada uma com id, titulo e texto). Correção do João vira regra pela REGRA Nº 2
do `CLAUDE.md`; regra nova só do exemplo, do `historico.jsonl` ou do que o João disse.
