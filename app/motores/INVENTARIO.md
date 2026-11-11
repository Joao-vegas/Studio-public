# Inventário de motores e ferramentas (29-out-2026)

"Usado por" foi conferido no código (formatos, modelos dos clientes atuais, scripts), não de memória.
Versões vêm de `atualizacoes.json`; a tela é Configurações → Repositórios e motores (`app/ferramentas/repositorios.py`).

## Decisão de motor

| Material | Motor | Usado por |
|---|---|---|
| Gravado | ffmpeg + PIL | Fala com cenas, Tela dividida, Faixa com cenas, Caixinha, Chamada na tela, Crítica ao absurdo, Análise de tela, Lista de estáticos |
| Animação 2D | **HTML próprio** (`base/index.html` + `seek(t)` + `render.py` com Playwright) | Editorial, Documentário, `_modelo` |
| Animação 3D | Three.js no mesmo HTML próprio | Explicador 3D |
| HyperFrames | opcional, só por escolha explícita | ninguém |
| Remotion | aposentado; resto só no Mundo 3d | Mundo 3d (Cliente2, oculto, em teste) |

Por quê: os três formatos de animação prontos já rodam no HTML próprio (controle total do quadro, sem licença). HyperFrames é bom
(lint/check/snapshot), mas nenhum estilo o chama; fica instalado como opção, sem atualizar sozinho. O Remotion global
(`app/motores/remotion`) só tinha composições de clientes que saíram (Cliente8, Cliente4) e de modelos já removidos
(AnuncioVegas, ReelPostVegas, AnuncioCliente6, NoticiaDividida...); nenhum modelo atual o chamava.

## Inventário

| Item | Pra que serve | Onde mora | De onde vem | Versão | Disco | Usado por hoje | Ação |
|---|---|---|---|---|---|---|---|
| Estúdio | o app | raiz | github.com/Joao-vegas/Studio | 1.3.0 (`servidor.py VERSAO`) | 69 MB de git | tudo | manter |
| HyperFrames | HTML vira vídeo, com lint/check | `app/motores/hyperframes` | npm `hyperframes` (heygen-com/hyperframes) | 0.8.201 | 103 MB node_modules | ninguém | manter opcional; auto-atualização desligada |
| skills do HyperFrames | documentação oficial pra IA | `.../hyperframes/skills-oficiais` | git heygen-com/hyperframes (clone parcial) | c5a5203 | 21 MB | a IA, se escolher HyperFrames | manter |
| Remotion global | composições antigas | era `app/motores/remotion` | npm remotion 4.0.538 | 4.0.538 | 1,7 GB | ninguém | **backup** |
| skills do Remotion | documentação oficial pra IA | era `.../remotion/skills-oficiais` | git remotion-dev/skills | — | 3,5 MB | ninguém | **backup** |
| remotion-brink-finds | projeto antigo de shorts 3D (origem do Mundo 3d), fora do git, sem referência | era `app/motores/remotion-brink-finds` | local | — | 403 MB | ninguém | **backup** |
| Remotion do Mundo 3d | render do formato oculto | `formatos/mundo-3d/base/remotion` | npm remotion | 4.0.290 (fixo) | 143 MB | Mundo 3d (Cliente2) | manter, fora do MANIFESTO |
| Three.js | mundo 3D do Explicador | `app/motores/3d` | npm three | 0.186.1 | 22 MB | Explicador 3D (base, modelos de Cliente2 e João, prévia do elenco) | manter |
| scripts `reel.sh` etc. | rodavam o Remotion (NoticiaDividida) | era `app/automacao/{cliente2,joao}` | local | — | 48 KB | ninguém | **backup** |
| get-brolls | busca de b-roll | `~/.claude/skills/get-brolls` | git engenheirodevideo/get-brolls (outro autor) | c9c222f, limpo, igual ao origin/main | 87 MB | todo estilo com cena real | manter; atualiza por `git pull` |
| Gerador de imagem e vídeo | kie.ai | `~/Projetos/Skill/Gerador de imagem e vídeo` | git Joao-vegas/Gerador-imagem-video | abb430e | 20 MB | Gerar com IA | manter |
| VoiceStudio | voz local | aplicativo no Mac | github debpalash/VoiceStudio | 0.5.6 | — | estilos narrados | manter |
| ffmpeg | corte, junta, cor, áudio | brew | ffmpeg.org | 9.0.2 | — | todos | manter |
| Playwright | tira quadros do HTML | `app/.venv` (pip) + Chromium | PyPI | 1.62.0 | — | Editorial, Documentário, Explicador 3D | manter |
| Flask | telas | `app/.venv` (pip) | PyPI | 3.1.3 | — | o Estúdio | manter |
| yt-dlp | baixar por link | brew | yt-dlp/yt-dlp | 2026.8.19 | — | referência, acervo, gravados | manter |
| tesseract | ler texto nos quadros | brew | tesseract-ocr | 5.5.2 | — | estudo de referência, Editorial | manter |
| auto-editor | silêncio no corte | pip (usuário) | PyPI | 29.3.1 | — | corte dos gravados | manter |
| rembg | recorte da pessoa | pip | PyPI | 2.0.85 | — | Editorial, Documentário | manter |
| OpenCV | rosto e nitidez | pip | PyPI | 4.14.0.94 | — | 6 modelos de gravados + Documentário | manter |
| sentence-transformers | busca por significado no acervo | pip | PyPI | 5.7.0 | — | acervo | manter |
| mlx-whisper | transcrição local | pip | PyPI | 0.4.3 | — | estilos com fala | manter |
| Claude Code / Codex / anthropic SDK | IA | npm / pip | anthropics / openai | 2.1.314 / 0.163.0 / 1.8.0 | — | tudo | manter |

## Backup

`~/.config/estudio/backups/motores-aposentados-2026-10-29/`: `remotion/` (fonte, public, skills-oficiais, lock; `node_modules.tar.gz`),
`remotion-brink-finds/` (idem) e `automacao-remotion/`. Pra voltar: mover a pasta de volta pra `app/motores/`, `tar -xzf node_modules.tar.gz`
e recolocar a entrada no MANIFESTO do `atualizar.py`.

## get-brolls: fork próprio (opção, não feito)

O clone é do engenheirodevideo e fica limpo de propósito: mudança nossa dentro dele seria perdida ou brigaria com o `git pull`.
Se o João quiser mudanças próprias: fork em `Joao-vegas/get-brolls` (GitHub), trocar o `origin` do clone pro fork, manter o
original como `upstream` e puxar dele de vez em quando. Hoje não é necessário.
