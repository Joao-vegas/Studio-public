# Revisão r1: Imagens na fala

Revisor: Opus, 05-nov-2026. Material: `exemplo-teste-r1.mp4` (28,3 s), `comparacao-r1.jpg`, quadros extraídos com ffmpeg da r1 e de `DecxbwzBRru.mp4`, `qa/medidas.json`, `gerar.py`.
Executor da r2: Sonnet. Não gastar nada pago, não publicar, não commitar, não mexer em outros formatos.

## Veredito de diretor de arte

**Semelhança com a referência: 4 de 10.** As peças estão certas (título amarelo, legenda branca sem karaokê, 3 posições, corte seco, cartão sem enfeite). A composição não está.

Na referência a tela é uma **colagem**: 3 cartões grandes e em pé cercam uma pessoa em plano médio, rosto pequeno no terço de cima. Na r1 a tela é um **close**: o rosto ocupa metade da largura e 1 ou 2 cartões pequenos ficam pendurados nas bordas. Quem olha de relance vê "vídeo de selfie com figurinha", não "ensaio ilustrado".

## Lacunas do criador: validar ou derrubar

| Lacuna reportada | Veredito | Por quê |
|---|---|---|
| Densidade 1,4 na tela contra 2,8 | **Valida, é a nº 2** | E a causa não é só o plano: `resolver_tempos` tira o cartão em 4,6 s mesmo sem ninguém pra substituir. |
| Bruto muito fechado (cartão 368 px, legenda a 64%) | **Valida, é a nº 1** | Rosto Haar 525 px = 48,6% da largura (ref 39%), topo a 31,6% (ref 23%). É a raiz de 4 outros problemas. |
| Motor não corta pausa (voz 59% contra 79%) | **Derruba em parte** | Só 3 pausas acima de 0,3 s (0,74 · 0,34 · 0,72), excesso de 1,2 s (4% do vídeo). O resto é o ritmo do João (174 contra 198 palavras/min). Prioridade baixa. |
| Imagens a olho, sem casar_imagem | **Valida** | E o problema maior é de curadoria (ver item 5), não de ferramenta. |
| Música e efeitos não conferidos | **Valida, baixa** | A ref não tem nenhum trecho abaixo de -45 dB (silencedetect deu 0). Pode ser cama ou ruído de sala. Decide de ouvido, não por medida. |
| G26 não conhece o formato | **Valida, e é pior** | O `COMO-FAZER` manda rodar sem `--formato`, então a régua caiu em "estilo sem cena de apoio" e só cobrou o parado. Com `--formato imagens-na-fala` a r1 teria **reprovado** (sem troca por 13,1 s contra teto de 10 s). |
| Secundária só medida | **Derruba** | Não é lacuna. A secundária tem outra gramática (título branco 2 linhas, sem legenda). Fica de fora da r2. |

## Lacunas que o criador não viu

1. **Legenda sobre camiseta branca.** Luminância mediana atrás da legenda: ref 37 a 77, r1 163 a 194. Texto branco com contorno de 3 px em fundo quase branco perde peso e cansa a leitura.
2. **Cartão deitado e cartão estreito.** `CARTAO["aspecto_min"] = 0.85` deixa passar cartão mais largo que alto: o Argos saiu 368x313. E `preparar_cartao` encolhe a LARGURA quando a altura não cabe: Cassandra saiu com 299 px e a prensa com 314 px (ref 370 a 414).
3. **Teto de altura dos cartões de baixo.** Como a legenda desceu pra 64%, `caixa_do_slot` empurra o topo de B e C pra y 1316: todos os cartões de baixo travaram em ~498 px de altura (ref até 730).
4. **Gancho fraco.** Ref: 3 cartões na tela até 0,57 s. r1: 1 cartão até 3,08 s.
5. **Sem rajada.** O PLANO tem 9 cartões em fila, um a cada 2,95 s. Nenhuma virada de ideia com 2 a 3 entrando juntos.
6. **Textura das imagens.** 6 de 9 são óleo escuro de museu (Rubens, 2 Vermeer, Ostade, Marinus). A ref é majoritariamente gravura, iluminura e ilustração de livro em papel claro. Dois Vermeer de mulher trabalhando ficaram juntos na tela (8,7 a 10,7 s): parece repetição.
7. **Sem fio visual.** Na ref, cachorro e lobo voltam várias vezes e amarram a tese. Na r1 são 9 metáforas soltas.
8. **Fundo pobre.** Desvio da parede na r1: 13 a 26; na ref: 42 a 69 (sala com quadro e plantas). A borda esquerda esticada e borrada (dx 149 px) vira uma faixa marrom chapada.

## Plano de correção (ordem de execução = ordem de impacto)

### 1. Enquadramento: rosto do tamanho e na altura da referência

- **Problema:** rosto 525 px (48,6% da largura), topo em y 606 (31,6%). Ref: 39% e 23%. Daí vêm a legenda a 64%, os cartões de baixo travados em 498 px e o cartão A espremido pelo rosto.
- **Causa:** `gerar.py` › `calcular_enquadramento` só desloca pra direita (`zoom` fica 1.0, `dy_max` 0). `deslocar` só sabe esticar a borda.
- **Correção:**
  - Em `ROSTO`, criar `"largura_alvo": 0.39`, `"zoom_min": 0.78`, trocar `"esquerda_min"` por 0.46 e `"topo"` por 0.235.
  - Em `calcular_enquadramento` (modo `auto`): `zoom = max(ROSTO["zoom_min"], min(1.0, ROSTO["largura_alvo"] * W / rosto["w"]))`. Com o rosto escalado, calcular `dx` pra caixa do rosto começar em 46% e `dy` pra o topo do rosto ir a 23,5% (pode ser negativo, ou seja, subir).
  - Nova função `compor_reduzido(frame, enq)` usada por `quadro_base` e `renderizar` quando `zoom < 1`: fundo = o próprio quadro em 1080x1920, `GaussianBlur` sigma 40 e brilho x0,55; por cima, o quadro reduzido em (dx, dy), com rampa de alfa de 60 px nas bordas que ficam dentro da tela (esquerda e baixo). O filtro do ffmpeg (`filtro_enquadramento`) vira só decodificação, a composição sai no PIL/numpy como hoje faz o `deslocar`.
  - `rosto_no_quadro` já aceita `zoom`: conferir que usa o novo `dy` com sinal certo.
  - Gravar em `qa/medidas.json` › `enquadramento` o `zoom` usado e um aviso `"bruto_de_perto": true` quando o zoom ficar abaixo de 0,9.
- **Aceite:** `rosto_no_quadro.w` entre 400 e 440 px; `rosto_no_quadro.y` entre 430 e 480 px; `rosto_no_quadro.x` ≥ 480 px; legenda com 1ª linha em y ≤ 1110 (57,8%); emenda do quadro reduzido invisível na `storyboard.jpg` (mostrar pro João antes do render). Se a emenda ficar feia, o aceite vira "bruto novo em plano médio" (item 9) e o zoom fica opcional.

### 2. Densidade e rajada: 3 cartões na tela na maior parte do tempo

- **Problema:** 9 cartões (19,1/min), média 1,38 na tela, 3 na tela em 0% do tempo, nenhum começo de rajada. Ref: 30/min, 2,77, 82%.
- **Causa:** (a) `gerar.py` › `resolver_tempos` fecha todo cartão em `t + 4.6` mesmo sem sucessor na posição; (b) o PLANO tem um cartão por ideia, em fila; (c) não existe jeito de declarar rajada.
- **Correção:**
  - `resolver_tempos`: padrão de saída passa a ser "até o próximo da mesma posição menos 0,35 s"; sem sucessor, fica até `fim` com teto `dur_max_s` (11,4). `dur` explícito no PLANO continua mandando.
  - Campo novo no cartão: `"depois_do_anterior": 0.25` (entra X s depois do cartão anterior da lista, sem precisar de palavra). É assim que se escreve rajada B, A, C.
  - Campo novo `"limpa": true`: no `t_ini` desse cartão, todos os que estão na tela saem no mesmo quadro (a ref faz isso 3 vezes).
  - Reescrever `_sandbox-teste-r1/PLANO.json`: 6 viradas de ideia, cada uma com 2 a 3 cartões (ordem B, A, C ou B, C, A, 0,1 a 0,6 s entre eles), total 14 a 16 cartões. A 1ª rajada abre em 0,1 s com 3 cartões. Usar as viradas de frase do `words.json`.
- **Aceite (em `qa/medidas.json`):** `cartoes` 14 a 16; `cartoes_por_min` 28 a 34; `media_na_tela` ≥ 2,4; `cartoes_na_tela_pct["3"]` ≥ 65; `duracao_cartao_mediana_s` 3,9 a 6,1; 3 cartões na tela até 1,0 s.

### 3. Cartão em pé e na largura da referência

- **Problema:** Argos 368x313 (deitado), Cassandra 299 px de largura, prensa 314 px. Ref: 370 a 414 px (C até 500), altura/largura 1,1 a 1,8.
- **Causa:** `CARTAO["aspecto_min"] = 0.85`; em `preparar_cartao`, `esc = min(alvo_w / iw, ch / ih)` encolhe a largura quando a altura não cabe.
- **Correção:**
  - `CARTAO["aspecto_min"] = 1.10`.
  - Largura alvo por posição: A e B 0,37 W (400 px), C 0,42 W (454 px). Pôr `"largura"` dentro de cada `SLOTS[...]`.
  - Em `preparar_cartao`: depois do recorte por aspecto, se `ih / iw > ch / alvo_w`, recortar a ALTURA em volta do `foco` até `ch / alvo_w` (sem baixar de 1,10). Só encolher a largura se nem 1,10 couber, e aí avisar no terminal.
- **Aceite:** em `cartoes_lista`, todo `box` com `w` ≥ 370 (C ≥ 420) e `h / w` entre 1,10 e 1,80; nenhum cartão deitado.

### 4. Legenda legível em roupa clara

- **Problema:** fundo atrás da legenda com luminância mediana 163 a 194 (ref 37 a 77).
- **Causa:** `LEGENDA["contorno_px"] = 3` fixo, pensado pra camiseta escura.
- **Correção:** em `Cena.__init__`, medir a luminância mediana do retângulo da legenda em 5 quadros do bruto já enquadrado. Se passar de 120: contorno 5 px e sombra `(0, 3, 3, 0.75)`. Gravar `"legenda_fundo_lum"` e `"legenda_contorno_px"` em `qa/medidas.json`. Não pôr tarja nem caixa (a ref não usa).
- **Aceite:** `legenda_fundo_lum` registrado; com fundo > 120, contorno 5 px; recorte da legenda em 3 quadros salvo em `qa/legenda-*.jpg` e lido sem esforço no tamanho de celular (360 px de largura).

### 5. Curadoria das imagens

- **Problema:** 6 de 9 em óleo escuro, 2 Vermeer juntos, nenhum fio visual, escolha a olho.
- **Causa:** passo 3 do `COMO-FAZER.md` não tem critério de textura nem de repetição; `casar_imagem` é "na dúvida".
- **Correção (sem custo, só fontes grátis):**
  - Pelo menos 2/3 dos cartões em gravura, xilogravura, iluminura ou ilustração de livro (papel claro). Óleo escuro no máximo 1/3, e nunca 2 escuros (luminância média < 70) na mesma rajada.
  - Nunca 2 obras do mesmo autor na tela ao mesmo tempo.
  - Fio visual: a metáfora central da tese (no teste, o charlatão e a plateia) volta em pelo menos 3 cartões.
  - Rodar `app/.venv/bin/python app/ferramentas/casar_imagem.py pontuar <img> "<oração>"` em TODAS as opções da folha e guardar a nota em `imagens/origem.json` (`"casar": 0.xx`). Escolher a de maior nota entre as que passam na textura.
  - Trocar Argos (deitado, cheio) e um dos Vermeer.
- **Aceite:** `origem.json` com `casar` em 100% dos cartões; contagem de gravura ≥ 2/3 anotada no `origem.json` (`"tecnica"`); nenhum autor repetido na mesma rajada.

### 6. Conferência que reprova o que a régua reprova

- **Problema:** `qa/conferir.json` deu OK com régua nula.
- **Causa:** `COMO-FAZER.md` passo 6 e `formato.json` › esteira › `conferir` chamam `conferir_video.py` sem `--formato`. E G26 mede troca de tela inteira, não cartão.
- **Correção:**
  - Acrescentar `--formato imagens-na-fala` no passo 6 do `COMO-FAZER.md` e no comando da esteira em `formato.json`.
  - Em `conferir_video.py`, função nova `checar_cartoes(sandbox)` chamada dentro de `conferir` só quando existir `<sandbox>/qa/medidas.json` com a chave `media_na_tela`: reprova se `media_na_tela` < 2,3, `cartoes_por_min` < 26 ou rosto com `w` > 0,42 W. Sem esse arquivo, não faz nada (os outros formatos não mudam).
- **Aceite:** rodar a conferência de novo na r1 antiga dá REPROVADO com os 3 motivos; na r2 dá OK.

### 7. Pausas acima de 0,3 s

- **Problema:** 3 pausas de 0,34 a 0,74 s; ref no máximo 0,3 s.
- **Causa:** o bruto veio cortado pela régua de outro formato (`corte.py`: `APERTO = 0.55`, `APERTO_ALVO = 0.18`).
- **Correção:** se `corte.py aplicar` já aceita sobrescrever o aperto, rodar com teto 0,3 s. Se não aceita, acrescentar `--aperto` e `--aperto-alvo` opcionais com os valores atuais como padrão (nenhum outro formato muda) e rodar com 0,30 e 0,20. Refazer `words.json` pela fala nova e reaplicar os gatilhos.
- **Aceite:** em `qa/words-saida.json`, nenhum intervalo entre palavras acima de 0,35 s; duração cai ~1 s.

### 8. Som: decidir de ouvido, não por medida

- **Problema:** ninguém ouviu a ref; a medida acusa cama a 15 dB, mas nada abaixo de -45 dB aparece.
- **Correção:** cortar 3 trechos de pausa da ref (ffmpeg, sem custo) num `qa/ref-pausas.wav` de ~5 s e deixar pro João ouvir. A r2 continua só voz.
- **Aceite:** arquivo existe; `formato.json` › som segue `usa: false` até o João dizer.

### 9. Documentar o que vale pra todo vídeo

- **Correção:** `COMO-FAZER.md` ganha um bloco "Gravação": plano médio, peito e cintura, rosto ~40% da largura, cabeça no terço de cima, corpo deslocado pra direita, roupa escura, fundo com textura. Atualizar "Estado da receita" com os números da r2. Atualizar `regras.json` (`cartao-limpo` com aspecto 1,10 e largura por posição; `rajada-por-ideia` com o campo `depois_do_anterior`). Não criar regra que não venha da ref, do histórico ou do João.
- **Aceite:** passo a passo e regras batem com o código (`grep` de 1.10, 0.39 e `depois_do_anterior` nos 3 arquivos).

### 10. Comparação final

- **Correção:** rodar `comparar_folha.py` de novo e salvar `comparacao-r2.jpg` ao lado da r1.
- **Aceite:** na folha, 3 cartões em pelo menos 14 dos 20 quadros da linha de baixo; rosto visivelmente do tamanho da linha de cima.

## Ordem pro Sonnet

```
1 enquadramento ──► prévia (storyboard) ──► conferir emenda
        │
        ▼
3 cartão em pé ──► 4 legenda ──► 5 imagens novas ──► 2 PLANO com rajadas
        │
        ▼
7 pausas (refaz words) ──► reaplicar gatilhos ──► render
        │
        ▼
6 conferência ──► 10 comparação ──► 8 trecho de som ──► 9 documentação
```

O 2 vem depois do 5 porque o PLANO novo depende das imagens novas. O 7 vem antes do render porque muda os tempos.

## O que NÃO mexer

- Título (fonte, cor, 72 px, linha de base 378): já bate com a ref.
- Corte seco de 1 quadro, cartão parado, sem borda, sombra ou canto redondo.
- Coordenadas das 3 posições em `SLOTS` (só ganham a largura por posição).
- Loudnorm de 2 passadas a -14 LUFS e silêncio depois da última palavra.
- Padrões de `corte.py` e o comportamento de `conferir_video.py` pros outros formatos.
- Referência secundária (`exemplo-2`), outros formatos, `exemplo-teste-r1.mp4` (vira histórico; a r2 sai como `exemplo-teste-r2.mp4`).
- Nada pago, nada publicado, nenhum commit.
