# Motor do Explicador 3D (cara Loaded Dice, 29-out-2026)

Three.js + Playwright, tudo função de `t` (`seek(t)`). A gramática é a do Desenho 3D (mesmo `cenas.json`, mesmos campos):
parado é parado, gesto que termina 4 quadros antes da palavra, rosto que troca atrás de uma piscada, câmera que nunca para,
dissolve de 6 quadros, número como objeto. A CARA é outra: jogo antigo realista e meio feio (a referência: 11 shorts do
Loaded Dice, `../estudo-quadros/ESTUDO-QUADROS.md`).

- `gente.js`: gente de proporção humana, low-poly de 8 lados, roupa com textura de pano (jaleco, terno com gravata, moletom
  com zíper, florida, xadrez), e o ROSTO pintado em canvas como foto colada (pele com poro e sombra, olho com íris e brilho,
  sobrancelha de fio, dente, ruga, suor). 19 expressões (`EXPRESSOES`, as mesmas nomes do Desenho 3D, exageradas: olho arregalado,
  sorrisão de dente, grito). Elenco aceita os campos do Desenho 3D + `olhos` (castanho|azul|verde|mel|escuro), `mulher`,
  `idade: velho`, `corpo: magro|forte|gordo`, `barba: curta|cheia|nenhuma`, `camisa.tipo: jaleco|terno|moletom|gola`,
  `camisa/calca.estampa: florida|xadrez|listra`, `cabeca` (1,14 padrão), `semente`.
- `mundos.js`: cidade no entardecer (poste e letreiro acesos, janela acesa, luzes ao longe), consultório (piso de cerâmica,
  painel de luz, reboco), escritório noir de abajur, sala do aquário. Mesmas coordenadas do antigo Desenho 3D; casa, loja, restaurante, banco e cassino novos; textura de pixel de jogo antigo.
- `objetos.js`: contador, pilha, medidor, calendário, placa, celular, gaveta, aquário, balão, etiqueta, urna, confete, ondas,
  holofote (com luz de verdade). Campos iguais aos do antigo Desenho 3D (removido em 29-out-2026).
- `motor.js`: PBR + sombra suave, luz de preenchimento que anda com a câmera, profundidade de campo (foco no `cam.olha` ou
  `cam.foco`), glow do que acende, ACES, grade de cinema (sombra fria, luz quente), vinheta e grão.

## Narrativa visual → cenas (qualquer roteiro)

`decupagem.json` (a IA escreve depois de ler o roteiro) → `python3 gerar.py <sandbox>` → `cenas.json` + `DECUPAGEM.md`. Formato no
topo do `gerar.py`; exemplo: `exemplos/cidade-12-mil-decupagem.json`.
- `elenco.js`: 17 personagens (dentista, medica, paciente, aposentado, vovo, estudante, executivo, comerciante, vendedora,
  motoboy, pedreiro, garcom, gerente, influencer, policial, agricultor, menina); `"dono": "comerciante"` ou `{"base": ..., troca}`.
- Cenários: cidade (com praça e eleição), consultorio, escritorio, aquario, casa, loja, restaurante, banco, cassino; posições
  nomeadas em `marcas.json` (`"pos": "@balcao"`).
- Transições (`trans` do plano): `corte` (padrão), `dissolve`, `moedas_caem`, `notas_sobem`, `wipe` (ficha gigante passando),
  `chicote` (giro rápido com borrão), `flash`; `trans_q` muda os quadros. Medidas em `../estudo-quadros/TRANSICOES-E-POP.md`.
- `cam.passos [{em, de, para, olha, fov, dura}]`: a câmera desliza pro enquadramento da oração seguinte dentro do mesmo plano.
- Pop de reação: automático em toda ação com `rosto` (`pop: false` desliga, `pop: "grande"` = comemoração).

## Campos novos do cenas.json

- `estilo {desfoque: 1, exposicao: 1, ambiente: .4 (luz chapada), chave: 1.25 (sol), pratica: 1.6 (lâmpadas), lampada: 2.6
  (quanto o que acende passa de 1), fill: 1.2 (preenchimento)}`.
- No plano: `brilho {cor, de, ate, forca}` (o brilho amarelo de borda do Loaded Dice quando o número assenta) e `cam.foco [x,y,z]`.

## Comandos

`render.py --storyboard --cenas cenas.json` · `render.py --cenas cenas.json --processos 6` · `render.py --quadro 3.5,10 --cenas cenas.json`
· `render.py --conferir --cenas cenas.json`. Modelo completo: `exemplos/cidade-12-mil-decupagem.json` (rode `gerar.py`). O motor antigo ("GTA 2000",
cenas com `check`, `choque`, `viatura`, `roleta`, tribunal, lanchonete, salão) está em `~/.config/estudio/backups/explicador-3d-base-2026-10-29/`.
