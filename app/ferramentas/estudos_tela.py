#!/usr/bin/env python3
"""
estudos_tela — a ferramenta de estudar o vídeo dos outros QUADRO A QUADRO, com lugar na tela (PLANO-2.0, item 13).

    python3 estudos_tela.py rodar <id>        # a tela chama: baixa os links, roda o estudo_quadros e grava o estado

Joga um ou mais links (ou vídeos) do mesmo estilo → sai o estudo a 30 fps (planos, transições, câmera, fala, som,
legenda, cada regra com o quadro de prova) em app/.estudos/<id>/. Daí o João junta como referência de um estilo
(formatos/<slug>/estudos/NN-nome/, com vídeo, capa, folha e o estudo), sem perder nenhuma referência.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import ESTUDIO, RAIZ, gravar_json, ler_json, make_slug  # noqa: E402

PASTA = ESTUDIO / ".estudos"


def _est(d: Path, **kw) -> None:
    e = ler_json(d / "estado.json", {}) or {}
    e.update(kw, atualizado=time.strftime("%d/%m %H:%M"))
    gravar_json(d / "estado.json", e)


def novo(links: list[str], arquivos: list[Path], nome: str = "", auto: bool = False) -> str:
    links = [l.strip() for l in links if l.strip()]
    if not links and not arquivos:
        raise ValueError("Cole um link ou suba um vídeo.")
    sid = time.strftime("%Y%m%d-%H%M%S") + "-" + make_slug(nome or "estudo", 30)
    d = PASTA / sid
    (d / "videos").mkdir(parents=True)
    for i, a in enumerate(arquivos, 1):
        shutil.move(str(a), d / "videos" / f"video-{i}{Path(a).suffix.lower() or '.mp4'}")
    gravar_json(d / "pedido.json", {"links": links, "nome": nome, "auto": bool(auto)})
    _est(d, rodando=True, fase="Baixando os vídeos" if links else "Estudando quadro a quadro", erro="", nome=nome or "Estudo", gate=True)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "rodar", sid], cwd=RAIZ, stdout=subprocess.DEVNULL,
                     stderr=open(d / "erro.txt", "w"), start_new_session=True)
    return sid


def rodar(sid: str) -> int:
    d = PASTA / sid
    ped = ler_json(d / "pedido.json", {}) or {}
    n = len(list((d / "videos").glob("*")))
    for j, url in enumerate(ped.get("links") or [], n + 1):
        alvo = d / "videos" / f"video-{j}.mp4"
        subprocess.run(["yt-dlp", "-q", "--no-playlist", "-f", "mp4/best", "-o", str(alvo), url], timeout=600, check=False)
    vids = sorted((d / "videos").glob("*"))
    if not vids:
        _est(d, rodando=False, fase="", erro="Não consegui baixar o vídeo. Baixe e suba o arquivo.")
        return 1
    _est(d, fase=f"Estudando {len(vids)} vídeo(s) quadro a quadro, a 30 por segundo (leva uns minutos)")
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "estudo_quadros.py"), "estudar", *map(str, vids),
                        "--saida", str(d / "estudo-quadros"), "--nome", ped.get("nome") or "referência"],
                       capture_output=True, text=True, timeout=7200)
    if r.returncode or not (d / "estudo-quadros" / "ESTUDO-QUADROS.md").is_file():
        _est(d, rodando=False, fase="", erro="O estudo parou: " + (r.stderr or r.stdout)[-300:])
        return 1
    _est(d, rodando=False, fase="", erro="", pronto=True)
    if ped.get("auto"):   # o Estúdio junta ao estilo mais parecido (ou cria um estilo em teste) e só avisa, com Desfazer
        try:
            import auto_juntar
            auto_juntar.estudo(sid)
        except Exception as e:  # noqa: BLE001  se não deu, fica esperando o João
            _est(d, aviso_auto=f"Não consegui decidir sozinho: {str(e)[:160]}")
    return 0


def lista() -> list[dict]:
    out = []
    for d in sorted(PASTA.glob("*"), reverse=True) if PASTA.is_dir() else []:
        if not d.is_dir():
            continue
        e = ler_json(d / "estado.json", {}) or {}
        vids = sorted((d / "videos").glob("*"))
        folha = next(iter(sorted((d / "estudo-quadros" / "folhas").glob("*geral*.jpg"))), None)
        out.append({"id": d.name, "nome": e.get("nome") or d.name, "estado": e, "videos": [rel(v) for v in vids],
                    "folha": rel(folha) if folha else "", "quando": e.get("atualizado", "")})
    return out


def ver(sid: str) -> dict:
    d = PASTA / Path(sid).name
    if not d.is_dir():
        raise ValueError("Estudo não encontrado.")
    item = next(x for x in lista() if x["id"] == d.name)
    md = d / "estudo-quadros" / "ESTUDO-QUADROS.md"
    item["md"] = md.read_text(encoding="utf-8") if md.is_file() else ""
    item["folhas"] = [rel(f) for f in sorted((d / "estudo-quadros" / "folhas").glob("*.jpg"))][:24]
    return item


def juntar(sid: str, slug: str) -> str:
    """Vira referência do estilo `slug`: formatos/<slug>/estudos/NN-nome/ (vídeo, capa, folha, ESTUDO.md e o estudo)."""
    d = PASTA / Path(sid).name
    if not (d / "estudo-quadros" / "ESTUDO-QUADROS.md").is_file():
        raise ValueError("O estudo ainda não terminou.")
    base = RAIZ / "formatos" / slug / "estudos"
    if not (RAIZ / "formatos" / slug / "formato.json").is_file():
        raise ValueError("Estilo não encontrado.")
    base.mkdir(exist_ok=True)
    nome = (ler_json(d / "estado.json", {}) or {}).get("nome") or "referencia"
    alvo = base / f"{len([x for x in base.iterdir() if x.is_dir()]) + 1:02d}-{make_slug(nome, 40)}"
    alvo.mkdir()
    for i, v in enumerate(sorted((d / "videos").glob("*")), 1):
        _clonar(v, alvo / f"video-{i}{v.suffix}")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(v), "-frames:v", "1", "-vf", "scale=-2:640",
                        str(alvo / f"capa-{i}.jpg")], check=False)
    folha = next(iter(sorted((d / "estudo-quadros" / "folhas").glob("*geral*.jpg"))), None)
    if folha:
        shutil.copy2(folha, alvo / "storyboard-1.jpg")
    shutil.copytree(d / "estudo-quadros", alvo / "estudo-quadros")
    ped = ler_json(d / "pedido.json", {}) or {}
    (alvo / "ESTUDO.md").write_text(f"# {nome}\n\nEstudada quadro a quadro em {time.strftime('%d/%m/%Y')}"
                                    + (f" ({', '.join(ped.get('links') or [])})" if ped.get("links") else "")
                                    + ". Medidas e regras com o quadro de prova: `estudo-quadros/ESTUDO-QUADROS.md`. "
                                    "Base de estilo (~70% fundamento), nunca molde.\n", encoding="utf-8")
    _est(d, juntado=str(alvo.relative_to(RAIZ)), juntado_em_estilo=slug)
    return str(alvo.relative_to(RAIZ))


def destino_previsto(slug: str, nome: str = "") -> str:
    """Onde o estudo vai parar se o João confirmar (pra tela mostrar antes)."""
    base = RAIZ / "formatos" / slug / "estudos"
    n = len([x for x in base.iterdir() if x.is_dir()]) + 1 if base.is_dir() else 1
    return f"formatos/{slug}/estudos/{n:02d}-{make_slug(nome or 'referencia', 40)}/"


def rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(RAIZ.resolve()))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["rodar"] and len(a) == 2:
        sys.exit(rodar(a[1]))
    print(json.dumps(lista(), ensure_ascii=False, indent=1))
