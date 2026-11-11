# Como fazer: Mundo 3D

**Quando usar:** short vertical (9:16) de 45 a 110 s que explica algo mostrando coisas em 3D (lugar, objeto, comparação, processo, anúncio simples), com voz narrando frases curtas de 8 a 12 palavras.
**Régua:** exemplo-1 (CONTRATO, item 6).
**Motor:** `base/short3d.py` (Remotion + three.js). A câmera nunca para, a cena muda a cada 3 a 5 s presa à palavra, o número fica DENTRO da cena. Sem chip no canto, sem rodapé. Como rodar e como criar peça: `base/README.md`.
**Som:** voz (ElevenLabs, ~US$ 0,08 por vídeo de 60 s) e música opcional baixa (~0,09). Sem efeitos sonoros.
**Custo e tempo (estimativa, confirmar no próximo vídeo):** render ~3 min, imagens sem custo (código). O 1º vídeo de um assunto novo leva horas (objeto novo); com peças prontas e objeto simples, bem menos.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Pesquisa.** Cada número confirmado em fonte oficial e anotado em `fontes/FONTES.md`. Sem fonte, a frase sai.
2. **Roteiro.** 120 a 260 palavras: gancho com paradoxo, frase de identidade, a viagem em ordem, virada no meio ("But..."), fecho que volta ao gancho. Um número por frase. O João aprova.
3. **Voz.** Narração em `audio/voz.wav` (sem ruído depois da última palavra). O tempo de cada palavra sai em `audio/palavras.json`; o whisper roda sozinho e o idioma vem de `MOTION_LINGUA` (padrão `en`; português: `pt`).
4. **Storyboard (para pro João aprovar).** Copie `base/exemplo-s001/short3d.json` e troque as peças e os tempos: o `de` de cada cena é o início da palavra dita (olhe `palavras.json`). `python3 base/short3d.py <sandbox> --json short3d.json` gera `storyboard.jpg` (um quadro por cena). Compare com a folha do exemplo.
5. **Cenas 3D.** Reaproveite as peças da caixa abaixo; crie as que faltam (copiar `CenaModelo`, registrar em `Registro3D`). Cada cena é conferida com `--still <segundo>` abrindo a imagem, nunca só confiando no código.
6. **Render.** `python3 base/short3d.py <sandbox> --final --saida <mp4>`: 1080x1920, 30 fps, volume nivelado em -14 LUFS. Um único render por vez.
7. **Entrega.** Folha do vídeo, conferência contra o exemplo e `short-final.mp4`. O comentário do João vira regra pelo `aprendizado/`.

## Caixa de peças (cenas que já existem)

Nome exato no `short3d.json`. "Genérica" = só texto e números mudam; "Exemplo Roadster" = desenha o carro, o boneco, o foguete ou a Terra, e o objeto precisa ser trocado em cada assunto.

| Peça | O que mostra | Tipo | O que muda por assunto |
|---|---|---|---|
| `espaco` | o objeto principal girando, com um planeta atrás | Exemplo Roadster | objeto, planeta |
| `volante` | a câmera dentro do objeto, vendo o que ele vê | Exemplo Roadster | objeto |
| `afastar` | a câmera se afasta até o objeto virar um ponto, com régua e texto da distância | Genérica | distância, texto |
| `lateral` | o objeto de lado em travelling lento | Exemplo Roadster | objeto |
| `foguete` | decolagem com chama, fumaça e câmera acompanhando | Exemplo Roadster | só se o assunto tem lançamento |
| `carro_xray` | o objeto em raio-X (malha azul transparente + arestas), com medida | Exemplo Roadster | objeto, medida |
| `starman_close` | close de um detalhe ou personagem, luz dura e reflexo | Exemplo Roadster | personagem |
| `orbita` | Sistema Solar 3D com órbitas, rótulos e contador de voltas | Genérica | só se algo gira ou se repete |
| `mergulho` | a câmera desce da escala grande para a pequena (espaço → estrada) | Genérica | origem e destino |
| `patios_2018`, `patios_2025` | comparação A × B: dois pátios de carrinhos em planta técnica, cada carrinho = uma unidade, com números | Exemplo Roadster | só se o assunto compara duas coisas; unidade e valores |
| `patios_pergunta` | a interrogação amarela 3D sobre a cena | Genérica | texto do rótulo |
| `final_espaco` | volta ao objeto, câmera se afasta até ele sumir | Exemplo Roadster | objeto |
| `modelo` | cena em branco para copiar | Genérica | tudo |

Cada vídeo usa de 6 a 13 peças; as que não servem ao assunto ficam na caixa.

## O que precisa ser criado de novo em cada assunto

O **objeto principal** em 3D (no S001 foi um carro e um foguete). Opções: modelar por código com formas extrudadas, ou modelo CC0 / domínio público (kenney.nl, quaternius.com, poly.pizza) com a licença anotada. Objeto simples (caixa, prédio, frasco, navio básico) é rápido; objeto complexo leva horas.

## Anúncio simples (exemplo de pedido)

"Short 3D anunciando [produto ou evento], 30 s." Peças: objeto girando (`espaco`), zoom em cada destaque com o nome na cena (`lateral`), o preço ou número grande dentro da cena e `final_espaco` com a chamada. Precisa do objeto em 3D.

## Regras

Ficam em `aprendizado/regras.json`. Resumo: tudo no vídeo é público, de licença aberta ou feito por nós; sem logos (nomes só em texto simples); texto 3D sempre voltado para a câmera; legenda em y≈1340 e nada importante abaixo de ~1620 px; um json por grupo de cenas e um único render por vez. Correção do João vira regra pela REGRA Nº 2 do `CLAUDE.md`.

## Som e cena de apoio

**Música:** opcional, leve. Volume: ~0,09. Quando: do início ao fim, se houver. Não usa: sem música sem pedido. Troca: 1 faixa.

**Efeitos:** não usa (sempre).

**Cena de apoio:** não usa (sempre: o mundo 3D é o visual, sem b-roll).
