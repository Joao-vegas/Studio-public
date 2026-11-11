---
name: broll
description: Metodologia de B-ROLL do producao-reels para QUALQUER cliente/modelo (Joao, Cliente3, Cliente2, Cliente1 e futuros). Use sempre que um modelo precisar de b-roll, insert, cutaway ou imagem de apoio — busca em todas as fontes com a skill get-brolls (acervo compartilhado é atalho, não limite) (YouTube/TikTok/Instagram/Pexels/Pixabay/Commons/NASA), prévia com contact sheet, verificação por frames e registro no acervo. Também quando o João pedir "acha um b-roll de X", "alimenta o acervo", "busca cena de filme".
---

# B-roll — acervo + get-brolls + verificação

O b-roll é o que segura a retenção enquanto a pessoa fala parada. Ele tem que **casar com a fala**
no tempo exato da palavra, ser **dinâmico**, e passar na verificação por frames ANTES de entrar no beat.
Isto vale pra todos os clientes; a regra específica de cada modelo (sem rosto, cena de filme, stock
proibido, watermark…) está em `<modelo>/aprendizado/regras.json` e **manda** sobre esta skill.

## Onde as coisas estão

| O quê | Onde |
|---|---|
| Acervo compartilhado (todos os clientes) | `acervo/itens/<slug>/{clip.*,thumb.jpg,meta.json}` |
| CLI do acervo | `python3 app/ferramentas/acervo.py add\|url\|list` |
| Skill get-brolls (instalada, com venv) | `~/.claude/skills/get-brolls/` → `.venv/bin/python scripts/gb.py …` |
| Projeto get-brolls da busca pelo Estúdio | `acervo/busca/` (ledger com memória de decisões) |
| Sandbox do vídeo em produção | `<modelo>/_sandbox-<slug>/brolls/` (o beat aponta pra cá) |
| Estúdio (interface) | `http://localhost:7655` → abas **Acervo** e **Buscar b-roll** |

## Ordem obrigatória

1. **Transcreva e marque os beats** antes de procurar qualquer coisa: pra cada beat, escreva o
   *assunto concreto* (marca/site/produto/fato/sensação) e a janela `s-e` do `words.json`.
2. **Acervo é atalho, não limite.** Se o João separou itens do acervo no job, use-os. Senão, dê uma
   olhada (`python3 app/ferramentas/acervo.py list <termo>`) mas NÃO se prenda a ele: o acervo é
   pequeno e só cresce com o que for aprovado. A busca principal é fora (passos 3 e 4), em TODAS as
   fontes, variando entre os beats.
3. **Literal antes de stock.** Se a fala cita site/produto/marca/pessoa/notícia: tela do site,
   canal oficial, og:image, a matéria real (o `buscar-broll.sh` do modelo faz `site|og|yt|canal`).
   Stock (Pexels/Pixabay) só quando a regra do modelo permite ou é sensação/tema genérico.
4. **Busca com a skill get-brolls** (mesma metodologia que o Estúdio usa na interface):
   ```sh
   GB=~/.claude/skills/get-brolls; PY=$GB/.venv/bin/python; P=<sandbox>   # ou acervo/busca
   $PY $GB/scripts/gb.py search  --provider youtube --query "..." --limit 8 --intent literal --project $P
   $PY $GB/scripts/gb.py preview --candidate "<ID>" --start 12 --end 17 --reason "fala X (t=31.2)" --project $P
   ```
   `preview` devolve `files.contact_sheet` + `files.gif`. **Abra o contact sheet (Read) e olhe as
   células.** Só siga se elas mostram o que a fala pede. Se não, mude `--start/--end` ou descarte.
5. **Checklist de verificação** (reprova em qualquer item que a regra do modelo exigir):
   - casa com a fala/ideia · tem movimento (não é frame parado)
   - sem rosto de pessoa quando é conteúdo de marca/produto
   - sem marca d'água / vinheta / "SUBSCRIBE" (conferir um frame do MEIO e do FIM, não só o início)
   - sem legenda queimada (ou cortar a janela sem ela)
   - ≥720p, sem serrilhado; formato serve à faixa do modelo (16:9 perde as laterais no 9:16 → âncora)
   - canais que sempre saem com watermark (Motion Array, Stock Pilots, StockVideos.org, VideoKot) → nem baixe
6. **Aprove, registre e colete** com a skill (o ledger guarda fonte/autor/condição):
   ```sh
   $PY $GB/scripts/gb.py approve --candidate "<ID>" --by "João (via Claude)" --project $P
   $PY $GB/scripts/gb.py permit  --candidate "<ID>" --evidence "descrição do canal diz free stock / Pexels License / cena de filme uso editorial" --project $P
   $PY $GB/scripts/gb.py fetch   --candidate "<ID>" --project $P     # corte final em $P/brolls/clips/
   ```
   Alternativa rápida quando já sabe o vídeo e o trecho: `buscar-broll.sh yt <url> <ini-fim> <nome> <sandbox>/brolls`
   — mas AINDA ASSIM olhe frames (`ffmpeg -ss … -frames:v 1`) antes de montar o beat.
7. **Acervo só entra pela mão do João.** Nunca rode `acervo.py add` por conta própria durante um job do
   Estúdio; ele escolhe item a item na interface. Fora do Estúdio, só quando ele pedir explicitamente:
   ```sh
   python3 app/ferramentas/acervo.py add <clip.mp4> --titulo "relógio thriller close" \
     --tags "tensao,relogio,thriller,filme" --fonte "<url>" --autor "<canal>" --licenca "<evidência>"
   ```
8. **Registre aprendizado**: candidato reprovado com motivo vai pro `historico.jsonl` do modelo
   (categoria `broll`) quando o motivo for reutilizável (ex.: "canal X sempre tem watermark").

## Fontes grátis a mais (alem do get-brolls)

O get-brolls é do engenheirodevideo e só atualiza por `git pull` (não se mexe nele). As fontes extras ficam do lado do Estúdio:

```sh
python3 app/ferramentas/fontes_gratis.py video  "<consulta em inglês>" [--fontes archive,commons,nasa,pexels,pixabay]   # lista com licença e link direto
python3 app/ferramentas/fontes_gratis.py cortar <link-direto> <ini> <fim> <saida.mp4> [--vertical]                      # só o trecho
python3 app/ferramentas/fontes_gratis.py imagem "<consulta>" --saida <pasta> [--fontes commons,openverse,nasa,archive]   # baixa + origem.json + folha (fonte, licença, tamanho)
python3 app/ferramentas/fontes_gratis.py icone  "<consulta>" --saida <pasta>                                              # SVG do Iconify (os line-md são animados)
python3 app/ferramentas/musica_busca.py buscar "<clima>" --fonte openverse   # música (Jamendo) e efeito (Freesound) livres, sem chave
python3 app/ferramentas/fontes_gratis.py fontes   # o que está ligado, a licença e o que ficou de fora
```

- **Internet Archive** é a melhor fonte de filme e noticiário antigo em domínio público (só entram itens com licença declarada).
- Só entra licença livre (CC0, domínio público, CC BY, CC BY-SA, NASA, Pexels/Pixabay License); NC e ND são filtrados.
- Olhe a folha como em qualquer b-roll: o mesmo checklist vale. Foto pequena (o Openverse/Flickr traz 500 px) sobe por `midia_local.py upscale`.
- **Nunca Wikipédia como print de notícia ou estudo** (REGRAS.md G25); foto do Commons como imagem ilustrativa é outra coisa.

## Citação com áudio (quando o João pedir "põe fulano falando isso")

Não é b-roll mudo: é o take da pessoa FALANDO, com o áudio dela.

```sh
python3 app/ferramentas/fala.py missao "lula" "três refeições por dia" --limite 5   # busca + acha o segundo exato
python3 app/ferramentas/fala.py achar <url> "<frase>"                               # confere num vídeo específico
python3 app/ferramentas/fala.py cortar <url> 268 274 <sandbox>/brolls/citacao.mp4   # baixa só o trecho
```

`missao`/`achar` leem a LEGENDA do vídeo (oficial ou automática, pt/en/es) com tempo em cada linha; sem
legenda, `--whisper` baixa o áudio e transcreve com GROQ. O resultado traz `t0`, o texto dito e o link `?t=`.

- **Nunca invente a frase.** Só entra o que está na legenda/transcrição da fonte, com o tempo conferido.
- Vários pedidos ("no primeiro mandato", "em 2018", "puxa do Trump") = uma missão por pedido, um beat por
  citação, em ordem cronológica — é isso que mostra a narrativa se repetindo.
- No render, a voz do cliente abaixa ou pausa na janela da citação, e a legenda passa a ser a fala do citado,
  com identificação (nome + ano).

## Variedade (obrigatório)

- Nunca o mesmo vídeo (mesma URL) em dois beats, nem duas opções do mesmo vídeo num beat.
- Não ficar preso no YouTube: alterne fontes entre as opções; nenhuma fonte acima de ~50% do plano.
- Três ângulos de busca por beat: literal, metáfora visual, sensação. Termos em inglês e português.
  Se duas buscas devolvem o mesmo vídeo, troque o termo.
- Material próprio do João (`<sandbox>/material/`) vem primeiro onde couber.

## Cena de apoio: política do Estúdio (midia-v2)

1. Consulta pelo **sentido** da fala, não pela palavra: ideia visual + 2-3 consultas (literal, metafórica, cena de filme/notícia).
2. **Pelo menos 2 fontes por cena** (YouTube + Pexels/Pixabay/Commons); acervo primeiro.
3. Filtro antes de mostrar: 720p ou mais, sem marca d'água/legenda queimada/rosto indevido, duração ≥ a da cena, com movimento (olhar os quadros).
4. **3 opções por cena e a folha de prévia obrigatória** (`python3 app/ferramentas/folha_broll.py --opcoes <json> --saida work/brolls/folha-<cena>.jpg`, 6 quadros por opção com fonte, link, tempo e resolução). Nada entra no render sem `escolha` no PLANO.json.

## O que nunca fazer

- Montar o beat sem olhar frames do clipe baixado.
- Usar poster/thumbnail como prova de movimento.
- Preencher beat com stock genérico só pra bater contagem.
- Reaproveitar o pacote de b-roll do vídeo anterior do mesmo cliente quando a regra do modelo proíbe.
- Inventar licença: `permit` registra a evidência real (ou a declaração do João), nunca uma suposição.
