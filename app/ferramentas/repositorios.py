#!/usr/bin/env python3
"""Repositórios e motores: o cartão de cada ferramenta que o Estúdio usa (Configurações → Repositórios e motores).

Cada cartão diz: pra que serve (1 frase), quem usa hoje (estilos/telas de verdade, conferido no código em 29-out-2026),
de onde vem (link), onde mora, versão, tamanho em disco e a situação da atualização.
A versão e a situação vêm do atualizar.py (MANIFESTO); aqui só entra o que ele não sabe (Estúdio, Remotion do Mundo 3d)
e o texto humano de cada um. Inventário completo, com a decisão de motor: app/motores/INVENTARIO.md.

    python3 app/ferramentas/repositorios.py     mostra os cartões
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import RAIZ, ler_json

GH = "https://github.com/"
# nome (igual ao do MANIFESTO) → texto. "onde" é relativo à raiz do Estúdio ou absoluto; "" = fora de pasta (brew, pip, app).
# "dono": quem mantém o repositório (seu = Joao-vegas; fabricante; autor). "nao_mexer": por que o clone não se edita.
REGISTRO = [
    dict(nome="Estúdio (este)", serve="O próprio Estúdio: telas, esteira de produção, formatos, clientes e regras.",
         usado="tudo", origem=GH + "Joao-vegas/Studio", onde=".", dono="seu", tamanho=False),
    dict(nome="Claude Code", serve="A IA que produz e altera os vídeos.", usado="todos os estilos",
         origem=GH + "anthropics/claude-code", onde="", dono="fabricante"),
    dict(nome="Codex", serve="IA opcional (GPT) no lugar do Claude.", usado="opcional, nenhum estilo exige",
         origem=GH + "openai/codex", onde="", dono="fabricante"),
    dict(nome="VoiceStudio", serve="A voz local dos vídeos narrados (aplicativo; ele mesmo instala a versão nova).",
         usado="Explicador 3D, Documentário, Editorial", origem=GH + "debpalash/VoiceStudio", onde="", dono="outro autor"),
    dict(nome="anthropic (SDK)", serve="Biblioteca do chat de briefing.", usado="Criar vídeo (chat de briefing)",
         origem=GH + "anthropics/anthropic-sdk-python", onde="", dono="fabricante"),
    dict(nome="HyperFrames", serve="Motor opcional: HTML vira vídeo, com checagem automática (lint, check, snapshot).",
         usado="nenhum estilo hoje (os estilos de animação usam o HTML próprio do Estúdio)",
         origem=GH + "heygen-com/hyperframes", onde="app/motores/hyperframes", dono="fabricante"),
    dict(nome="Skills do HyperFrames", serve="Documentação oficial do HyperFrames, cópia do fabricante, que a IA consulta. Não é código nosso.",
         usado="a IA, se um estilo novo escolher o HyperFrames", origem=GH + "heygen-com/hyperframes",
         onde="app/motores/hyperframes/skills-oficiais", dono="fabricante"),
    dict(nome="Remotion (só no Mundo 3d)", serve="Motor de React que vira vídeo. Saiu do Estúdio em 29-out-2026; sobrou a cópia 4.0.290 dentro do formato Mundo 3d.",
         usado="só o Mundo 3d (Cliente2, formato oculto, em teste)", origem=GH + "remotion-dev/remotion",
         onde="formatos/mundo-3d/base/remotion", dono="fabricante", fixo="4.0.290",
         nota="não atualiza sozinho; grátis só até 3 pessoas na empresa; o resto está no backup motores-aposentados-2026-10-29"),
    dict(nome="Three.js", serve="Mundo 3D que a câmera percorre, desenhado dentro do HTML.", usado="Explicador 3D",
         origem=GH + "mrdoob/three.js", onde="app/motores/3d", dono="fabricante"),
    dict(nome="Playwright", serve="Tira os quadros do HTML e do 3D (navegador sem tela).", usado="Editorial, Documentário, Explicador 3D",
         origem=GH + "microsoft/playwright-python", onde="", dono="fabricante"),
    dict(nome="ffmpeg", serve="Corta, junta, cor e áudio de todo vídeo.", usado="todos os estilos",
         origem="https://ffmpeg.org", onde="", dono="fabricante"),
    dict(nome="auto-editor", serve="Mede o silêncio pra cortar o bruto.", usado="estilos gravados (corte automático)",
         origem=GH + "WyattBlue/auto-editor", onde="", dono="outro autor"),
    dict(nome="yt-dlp", serve="Baixa por link: referência, trecho de fala, música, b-roll.", usado="Referência rápida, acervo, Fala com cenas e Tela dividida",
         origem=GH + "yt-dlp/yt-dlp", onde="", dono="outro autor"),
    dict(nome="tesseract", serve="Lê o texto escrito nos quadros.", usado="estudo de referência, Editorial (grifo)",
         origem=GH + "tesseract-ocr/tesseract", onde="", dono="outro autor"),
    dict(nome="get-brolls", serve="Busca b-roll (YouTube, Pexels, Pixabay, Commons, NASA) com prévia em quadros e a origem registrada.",
         usado="todo estilo com cena real: Fala com cenas, Tela dividida, Editorial, Documentário",
         origem=GH + "engenheirodevideo/get-brolls", onde=str(Path.home() / ".claude/skills/get-brolls"), dono="outro autor",
         nota="É do engenheirodevideo e se atualiza do repositório dele (git pull); por isso não editamos o clone. "
              "Pra ter mudança própria, o caminho é um fork em Joao-vegas/get-brolls (ainda não criado)."),
    dict(nome="Gerador de imagem e vídeo", serve="Skill da kie.ai: imagem e vídeo por IA, com cotação antes e custo por projeto.",
         usado="Editar vídeo (Gerar com IA), b-roll gerado, thumbnails", origem=GH + "Joao-vegas/Gerador-imagem-video",
         onde=str(Path.home() / "Projetos/Skill/Gerador de imagem e vídeo"), dono="seu"),
    dict(nome="mlx-whisper", serve="Transcreve a fala no próprio Mac (quando o Groq não está disponível).", usado="estilos com fala",
         origem=GH + "ml-explore/mlx-examples", onde="", dono="outro autor"),
    dict(nome="rembg", serve="Recorta a pessoa do fundo.", usado="Editorial, Documentário", origem=GH + "danielgatis/rembg",
         onde="", dono="outro autor"),
    dict(nome="Demucs", serve="Separa a voz da música num clipe real (`so_voz` do Editorial).", usado="Editorial (clipe real com som)",
         origem=GH + "facebookresearch/demucs", onde="app/ferramentas/midia_local.py", dono="outro autor"),
    dict(nome="onnxruntime", serve="Roda o mapa de profundidade (Depth Anything V2) do `parallax` e o rembg; o Real-ESRGAN (ampliar foto) fica em app/modelos-locais.",
         usado="Editorial (foto com relevo 3D, foto pequena ampliada)", origem=GH + "microsoft/onnxruntime", onde="app/ferramentas/midia_local.py",
         dono="outro autor"),
    dict(nome="OpenCV", serve="Acha rosto e mede nitidez do quadro.", usado="Faixa com cenas, Análise de tela, Frase fixa, Chamada na tela, Documentário, estudo de referência",
         origem=GH + "opencv/opencv-python", onde="", dono="outro autor"),
    dict(nome="sentence-transformers", serve="Busca por significado no acervo.", usado="acervo (b-roll, música)",
         origem=GH + "UKPLab/sentence-transformers", onde="", dono="outro autor"),
    dict(nome="Flask", serve="As telas do Estúdio.", usado="o Estúdio inteiro", origem=GH + "pallets/flask", onde="", dono="fabricante"),
]

_TAM: dict = {}


def _tamanho(pasta: Path, segundos: float = 3600.0) -> str:
    """Tamanho em disco da pasta (lembra 1 h: a tela de Configurações não pode andar a cada abertura)."""
    t, v = _TAM.get(str(pasta), (0.0, ""))
    if time.time() - t < segundos:
        return v
    total = 0
    for d, _, fs in os.walk(pasta):
        for f in fs:
            try:
                total += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
    v = f"{total / 1e9:.1f} GB" if total >= 1e9 else f"{total / 1e6:.0f} MB"
    _TAM[str(pasta)] = (time.time(), v)
    return v


def _versao_estudio() -> str:
    try:
        m = re.search(r'^VERSAO\s*=\s*"([^"]+)"', (RAIZ / "app/interface/servidor.py").read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def _git(pasta: Path) -> str:
    """Pra clone git: 'c9c222f, limpo' ou 'c9c222f, com mudança nossa'."""
    try:
        h = subprocess.run(["git", "-C", str(pasta), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        sujo = subprocess.run(["git", "-C", str(pasta), "status", "--porcelain", "-uno"], capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{h}, " + ("com mudança ainda não salva no git" if sujo else "limpo")
    except Exception:
        return ""


def cartoes(atualizacoes: dict | None = None) -> list[dict]:
    """Um dicionário por item, na ordem do REGISTRO, pronto pra tela."""
    if atualizacoes is None:
        import atualizar
        atualizacoes = atualizar.estado()
    por_nome = {i["nome"]: i for i in atualizacoes.get("itens", [])}
    saida = []
    for r in REGISTRO:
        m = por_nome.get(r["nome"], {})
        pasta = (Path(r["onde"]) if r["onde"].startswith("/") else RAIZ / r["onde"]) if r["onde"] else None
        versao, situacao, nova = m.get("versao", ""), m.get("estado", ""), m.get("nova", "")
        if r["nome"] == "Estúdio (este)":
            versao, situacao = _versao_estudio(), "seu repositório"
        elif r.get("fixo"):
            versao = (ler_json(pasta / "package.json", {}) or {}).get("dependencies", {}).get("remotion", r["fixo"]) if pasta else r["fixo"]
            situacao = "fixo, não atualiza"
        elif m.get("tipo") == "git" and pasta and (pasta / ".git").exists():
            versao = _git(pasta) or versao
        saida.append({**r, "versao": versao, "nova": nova, "situacao": situacao or "ainda não conferido",
                      "tamanho": _tamanho(pasta) if pasta and pasta.exists() and r.get("tamanho", True) else "",
                      "onde_txt": (str(pasta).replace(str(Path.home()), "~") if pasta and r["onde"] != "." else "")})
    return saida


# A caixinha "Quando o Estúdio usa cada um" (a mesma regra do CLAUDE.md, em linguagem de tela).
REGRA_MOTOR = [
    ("Vídeo gravado (você falando)", "ffmpeg + PIL", "corta, junta e põe legenda, cena e cartão por cima"),
    ("Animação 2D (motion, documentário, editorial)", "HTML próprio do Estúdio", "uma página HTML que o Playwright fotografa quadro a quadro; é o padrão"),
    ("Animação 3D (Explicador 3D)", "Three.js dentro do HTML próprio", "o mesmo caminho do 2D, com mundo 3D"),
    ("HyperFrames", "só se um estilo novo pedir", "nenhum estilo usa hoje; fica instalado como opção"),
    ("Remotion", "não se usa mais", "saiu em 29-out-2026; sobrou só dentro do Mundo 3d (Cliente2, em teste)"),
]

if __name__ == "__main__":
    for c in cartoes():
        print(f"{c['nome']:32} {c['versao'] or '-':22} {c['situacao']:18} {c['tamanho']:8} usado por: {c['usado']}")
