#!/usr/bin/env python3
"""
demos — demonstrações VISUAIS de um modelo (<modelo>/demos/): frames/clipes que mostram cada
elemento da tela (switch, faixa, card, legenda…) pra quem nunca viu o modelo entender o que ele faz.

- demos/index.json: [{"arquivo": "01-switch-off-on.png", "titulo": "...", "descricao": "..."}]
- Arquivos soltos em demos/ sem entrada no index aparecem também (título = nome do arquivo).
- gerar(): dispara o Claude (processo independente) pra renderizar demos com os PRÓPRIOS scripts do
  modelo (fundo neutro + textos de exemplo), um por elemento da estrutura, e escrever o index.json.
- Também extrai 3 frames de cada vídeo em output/<modelo>/ como "exemplos reais".
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ensure, ler_json, gravar_json, rel, now_slug, claude_bin, thumb, CACHE, ffprobe

IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif")
VID = (".mp4", ".mov", ".webm")


def pasta_demos(pasta_modelo: Path) -> Path:
    return pasta_modelo / "demos"


def listar(pasta_modelo: Path) -> list[dict]:
    d = pasta_demos(pasta_modelo)
    itens, vistos = [], set()
    for it in ler_json(d / "index.json", []) or []:
        p = d / it.get("arquivo", "")
        if p.exists():
            vistos.add(p.name)
            itens.append({**it, "rel": rel(p), "tipo": "video" if p.suffix.lower() in VID else "imagem"})
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.name in vistos or p.name.startswith(".") or p.suffix.lower() not in IMG + VID:
                continue
            itens.append({"arquivo": p.name, "titulo": p.stem.replace("-", " "), "descricao": "", "rel": rel(p),
                          "tipo": "video" if p.suffix.lower() in VID else "imagem"})
    return itens


def frames_reais(outputs: list[Path]) -> list[dict]:
    """3 frames (25/50/75%) de cada vídeo produzido — o exemplo real do modelo."""
    out = []
    for v in outputs[:4]:
        dur = (ffprobe(v).get("duracao") or 0)
        for i, frac in enumerate((0.25, 0.5, 0.75)):
            key = f"{rel(v).replace('/', '_')}-{i}.jpg"
            t = thumb(v, CACHE / "frames" / key, t=max(0.5, dur * frac), largura=540)
            if t:
                out.append({"rel": rel(t), "titulo": f"{v.name} · {int(dur * frac)}s"})
    return out


def rodando(pasta_modelo: Path) -> bool:
    pf = pasta_demos(pasta_modelo) / ".runner.pid"
    try:
        os.kill(int(pf.read_text().strip()), 0)
        return True
    except Exception:
        return False


def log(pasta_modelo: Path) -> str:
    p = pasta_demos(pasta_modelo) / ".log"
    return p.read_text(encoding="utf-8", errors="replace")[-6000:] if p.exists() else ""


def prompt(cli: dict, m: dict, ficha: dict) -> str:
    pm = rel(m["pasta"])
    estrutura = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(ficha.get("estrutura") or []))
    return f"""Você está no Estúdio (raiz: {RAIZ}). Gere DEMONSTRAÇÕES VISUAIS do modelo {m['nome']} do cliente {cli['nome']} (pasta {pm}) pra uma pessoa leiga entender o que ele faz.

Leia {pm}/ficha.json, {pm}/README.md e os scripts da pasta. Estrutura da tela segundo a ficha:
{estrutura}

O QUE FAZER:
1. Para CADA elemento da estrutura, renderize uma imagem 1080x1920 (PNG) mostrando SÓ aquele elemento em cima de um fundo neutro (cinza #2A2A2A com um retângulo mais claro onde ficaria a pessoa, ou um frame real se houver vídeo em {rel(cli['content'])}/output/{m['nome']}/ ou em alguma _sandbox-*/work/). Use os PRÓPRIOS scripts do modelo (build-*.py, gerar.sh com --from/--to curto, composição Remotion com props de exemplo) com textos de exemplo realistas do nicho do cliente, nas cores e fontes da ficha. Quando o elemento é animado (switch ligando, card palavra a palavra, punch), gere também um GIF ou MP4 curto (2-4s) da animação.
2. Gere uma imagem "00-visao-geral" com TODOS os elementos juntos, como fica o vídeo final.
3. Se a paleta tiver cores, gere "paleta.png": cada cor como um bloco grande com o hex e onde ela aparece (texto da ficha).
4. Salve tudo em {pm}/demos/ com nomes numerados (01-nome-do-elemento.png …) e escreva {pm}/demos/index.json como lista de {{"arquivo","titulo","descricao"}} — descricao em 1-2 frases em português explicando o que o elemento é e quando aparece.
5. Não invente elementos que o modelo não tem; se algo não der pra renderizar, escreva no index.json uma entrada sem arquivo? NÃO: só entradas com arquivo existente. Anote limitações em {pm}/demos/NOTAS.md.
6. Não peça confirmação; execute até o fim.
"""


def gerar(cli: dict, m: dict, ficha: dict, modelo_claude: str) -> None:
    d = ensure(pasta_demos(m["pasta"]))
    pf = d / f".prompt-{now_slug()}.txt"
    pf.write_text(prompt(cli, m, ficha), encoding="utf-8")
    if rodando(m['pasta']): return
    with (d / '.log').open('a') as log:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name('ia.py')), str(pf), str(d)],
                                cwd=RAIZ, start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
    (d / '.runner.pid').write_text(str(proc.pid))
