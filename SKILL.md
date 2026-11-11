---
name: estudio
description: Estúdio de vídeo do João, em QUALQUER projeto. Produz e corrige Reels, anúncio em vídeo, documentário, cinematográfico de evento, tela dividida, fala com cenas, frase fixa, chamada na tela, crítica ao absurdo, lista de estáticos, explicador 3D, desenho 3D e editorial, e aprende com cada correção. Aciona em /estudio, /motion-design, "faz um motion", "motion desse roteiro", "motion em cima do meu vídeo", "narração pro vídeo", "reels", "editar vídeo", "cortar vídeo", "tira os silêncios", "legenda", "b-roll", "VSL", "anúncio em vídeo", "cinematográfico", "documentário", "quadradinho que segue o rosto", "pessoa no cantinho", "PiP acompanhando o rosto", "face tracking", "auto reframe", "reenquadramento automático", "vídeo do evento", e em QUALQUER correção de vídeo ("tá em cima", "tira isso", "a voz tá estranha", "muito clichê", "música alta", "cortou ele", "tá parado").
---

# Estúdio

Casa: `~/Projetos/Skill/Estúdio/` (abaixo, `$E`). Substitui a antiga skill `motion-design` e o `producao-reels`.

## Dois caminhos

1. **Pela tela:** abrir http://localhost:7655. Se não responder: `bash ~/Projetos/Skill/Estúdio/app/iniciar.command`.
   Criar vídeo → formato → cliente → bruto ou roteiro. O feedback dado na tela vira regra sozinho.
2. **Direto aqui:** ler, nesta ordem, e só então produzir:
   - `$E/CLAUDE.md` (mapa, camadas de regra, motor, voz, b-roll)
   - `$E/formatos/<slug>/formato.json`, `COMO-FAZER.md` e `aprendizado/`; olhar o `exemplo-1.mp4` em quadros
   - `$E/clientes/<Nome>/identidade.json` e o `regras.json` do modelo dele (sem cliente: `clientes/Avulso/`)
   - `$E/REGRAS.md`

Fora do Estúdio, não crie pasta de vídeo no repositório do projeto atual: trabalhe na sandbox do job
ou no rascunho da sessão, e a versão final vai pra `~/Downloads` (G17).

## Qual formato

Lista de hoje, sempre atual: `python3 $E/app/ferramentas/formatos.py lista` (slug · título · frase; os ocultos vêm marcados). Os prontos:

| Pedido | Formato (`formatos/<slug>`) |
|---|---|
| Vídeo gravado + cenas de filme, gráfico ou frase a cada 6-7 s | `fala-com-cenas` |
| Gravado, tela dividida o tempo todo | `tela-dividida` |
| Gravado, uma frase fixa numa caixa o vídeo inteiro | `frase-fixa` |
| Gravado, gancho forte no t=0, legenda de uma palavra, motion limpo | `chamada-na-tela` |
| Vídeo absurdo em cima, foto fixa sua reagindo embaixo | `critica-ao-absurdo` |
| Pessoa num canto, lista numerada e uma estática por item | `lista-de-estaticos` |
| Mini-documentário: serifa acendendo, recortes P&B | `documentario` |
| Narrador em off com cenas 3D que mudam a cada ideia | `explicador-3d` |
| Análise de caso real com foto e print da internet, texto que acende | `editorial` |
| Vídeo de carro horizontal 16:9: corta silêncio, tira o volante com zoom, pessoa à esquerda e legenda do lado direito (em teste) | `legenda-no-lado` |
| Só tirar silêncio e take repetido | não é formato: tela `/cortes` |

Ocultos (em teste, aparecem em "Mais formatos"): `mundo-3d` e `pessoa-no-cantinho` (Pessoa em janela). Formatos removidos: ver o CLAUDE.md do Estúdio.

## Protocolo de correção (é o que faz o Estúdio melhorar)

```
correção ─→ procurar a regra que já cobria isso (cliente, formato, REGRAS.md)
              │
              ├─ NÃO tinha ─→ corrige o vídeo
              │               └→ regra nova na camada certa: formato (vale em qualquer cliente),
              │                  cliente (gosto, identidade) ou REGRAS.md (todo vídeo). Na dúvida, cliente.
              │
              └─ JÁ tinha (furo) ─→ corrige o vídeo
                                    └→ diagnostica por que furou (tabela abaixo)
                                    └→ conserta a CAUSA e reescreve a própria regra (nunca duplica)
                                    └→ registra o furo numa linha no histórico do modelo
```

| Causa do furo | Conserto |
|---|---|
| **Não lida** | A regra estava num arquivo que o fluxo não manda ler → levar pro passo em que ela vale |
| **Vaga** | Dava pra obedecer e errar mesmo assim → reescrever com número ou exemplo |
| **Só manual** | Dependia de olho → automatizar no script ou no checador |
| **Código contra** | O script ou a base faz o contrário da regra → corrigir o código |
| **Conflito** | Duas regras brigam, ou gosto de um cliente virou regra geral → dizer qual vale onde |

Fechar dizendo ao João, em uma frase, o que foi aprendido ("virou a G12" ou "furou a regra X porque Y, agora Z").
Correção que se repete em 2 vídeos vira código na base, e a regra encolhe.
