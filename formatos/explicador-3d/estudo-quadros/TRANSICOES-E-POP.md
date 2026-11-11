# Transições especiais e "levantadinha" (Loaded Dice, 11 shorts, quadro a quadro)

Medido em 29-out-2026 nas folhas a 30 fps de TODA transição especial e dissolve do estudo (78; 72 olhadas uma a uma; folhas
em `/private/.../scratchpad/v4/esp/`, recriáveis com o estudo). Quadro de prova = `<vídeo> q<início>-q<fim>`.

## Catálogo das especiais

| Tipo | Quadros | Direção | Provas |
|---|---|---|---|
| Chicote de câmera (giro/tilt rápido com borrão, cai no plano novo) | 10-15 | lado, cima→baixo, baixo→cima | AuX7znns3fs q709-720, q743-754, q789-803; oMvgmMNB_Bg q508-525; eXRvlY69aFg q99-113 (desce até as fichas), q172-182; KxEs8tTORWM q1891-1897, q1934-1943; kJBP2qr3SYU q427-441; 6dr3xfgvJfQ q1224-1237, q1377-1386 |
| Objeto escuro passa na frente da câmera e o plano novo aparece atrás | 8-9 | direita→esquerda e volta | AuX7znns3fs q1153-1167, q1228-1242; KxEs8tTORWM q86-89 (porta abrindo); hPgvC2-Azr0 q117-131 |
| Papel/objeto desliza e revela o plano | 8-16 | sobe / desce | kJBP2qr3SYU q306-314 (desce), q1165-1180 (sobe), q1226-1233, q1739-1745 |
| Barra/faixa que varre a tela | 8-12 | baixo→cima | 6dr3xfgvJfQ q898-905, q952-959, q972-983 |
| Corte diagonal (linha branca) | ~9 | diagonal | oMvgmMNB_Bg q1271-1279, q1453-1459 |
| Atravessa o objeto (zoom pra dentro de cartão/tela/papel) | 13-15 | pra frente | KxEs8tTORWM q1456-1468 (cartão VIP); GYO41yUtOUk q882-896 (monitor); 6dr3xfgvJfQ q550-553 |
| Flash branco | 5-15 | - | AuX7znns3fs q267-271; OPY6loAW3iI q1044-1059 |
| Estática de TV | 7 | - | GYO41yUtOUk q1545-1552 |

**Dinheiro:** nenhuma das 72 é chuva de moedas ou notas. O dinheiro aparece como OBJETO dentro do plano (fichas caindo em
volta da crupiê KxEs8tTORWM q1650-1670, pilha de fichas OPY6loAW3iI q879-885, notas na mesa w5YeTcV5daA q703-721). As
transições de dinheiro do motor (`moedas_caem`, `notas_sobem`) foram pedidas pelo João e usam o tempo das especiais com
objeto medidas aqui (12-16 quadros, o objeto cobre a tela no meio e a troca acontece atrás dele).

## A "levantadinha" (pop de reação)

Rastreio do rosto (Haar) em todo quadro dos 11 vídeos, só em close (rosto > 13% da altura), subida sem zoom (tamanho do rosto
muda < 12%):

| Tipo | Quanto sobe | Em quantos quadros | Volta | Quando | Provas |
|---|---|---|---|---|---|
| Pop de reação (a pessoa "se levanta" um pouco ao reagir/falar) | ~20% da altura do rosto (~3% da tela) | 3-4 | volta ~90% em ~5 quadros (quique leve) | na 1ª palavra (0 quadro) | KxEs8tTORWM q1657 (3 q, 19%, volta 93%), q1666 (4 q, 20%, volta 88%) |
| Pulo de comemoração | ~90% da altura do rosto (~12% da tela) | 8 | volta toda | na palavra (±2 q) | oMvgmMNB_Bg q1408 (8 q, 91%, volta 101%), q1434 (8 q, 88%, volta 100%) |

Os outros 66 movimentos achados são subida sem volta (tilt de câmera), não pop. No motor: toda ação com `rosto` ganha o pop
pequeno (`pop: false` desliga; `pop: "grande"` = comemoração), `estilo.pop_alt` (0,052 m) e `estilo.pop_quadros` (3,5).
