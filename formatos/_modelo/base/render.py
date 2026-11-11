#!/usr/bin/env python3
"""
Motor genérico do Estúdio (nasce do formatos/_modelo: o que o motor do Documentário tem de genérico, sem as regras dele).
O index.html desenha a cena do segundo t (window.seek(t)); este arquivo só captura quadro a quadro (Playwright) e junta
com ffmpeg, com a voz, a música e os efeitos do cenas.json. O formato troca o index.html (o visual) e põe as medidas
dele em checar(); o resto não precisa mexer.

Roda de dentro da pasta copiada (base do formato, modelo do cliente ou sandbox). Tudo que ele grava fica ao lado do
cenas.json (ou em --out): storyboard.jpg, previa-som.m4a, quadros/, qa/ e o vídeo.

  python3 render.py --cenas cenas.json --storyboard    storyboard.jpg (um quadro por cena, com o tempo e a fala) +
                                                       qa/checagem.json + previa-som.m4a; exit 1 com o motivo
  python3 render.py --cenas cenas.json                 o vídeo ("saida" do cenas.json ou video.mp4)
  python3 render.py --cenas cenas.json --quadro 3.5,10 PNGs soltos em quadros/ ("cenas" = um no meio de cada cena)
  python3 render.py --cenas cenas.json --ate 4         só os 4 primeiros segundos (teste.mp4)
  python3 render.py --cenas cenas.json --conferir      qa/folha-comparacao.jpg (exemplo principal em cima, este vídeo
                                                       embaixo) + qa/conferir.json; exit 1 com o motivo em pt-BR
Esquema do cenas.json: README.md (exemplo: cenas-modelo.json).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FORMATO = "_modelo"   # o formatos.py novo troca pelo slug: é daí que vem o exemplo principal da conferência


def _raiz() -> Path:
    for p in (AQUI, *AQUI.parents):
        if (p / "REGRAS.md").is_file() and (p / "formatos").is_dir():
            return p
    return Path.home() / "Projetos" / "Skill" / "Estúdio"


ESTUDIO = _raiz()
W, H, FPS = 1080, 1920, 30


# ───────────────────────────── leitura e plano (sem navegador) ─────────────────────────────

def achar(caminho: str | None, pasta: Path) -> Path | None:
    """Arquivo citado no cenas.json: ao lado dele, no motor ou na raiz do Estúdio."""
    if not caminho:
        return None
    p = Path(str(caminho)).expanduser()
    for c in ([p] if p.is_absolute() else [pasta / p, AQUI / p, ESTUDIO / p]):
        if c.exists():
            return c.resolve()
    return None


def br(x: float) -> str:
    return f"{float(x):.1f}".replace(".", ",")


def duracao_midia(p: Path | None) -> float:
    if not p or not p.exists():
        return 0.0
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip() or 0)
    except ValueError:
        return 0.0


def planejar(doc: dict, pasta: Path) -> dict:
    """Cenas com de/ate (sem "ate": vai até o "de" da próxima; a última até a voz ou "duracao") e o que a página recebe."""
    largura, altura = int(doc.get("largura") or W), int(doc.get("altura") or H)
    brutas = sorted((c for c in doc.get("cenas") or [] if isinstance(c, dict)), key=lambda c: float(c.get("de", 0)))
    voz = achar(doc.get("voz"), pasta)
    fim = float(doc.get("duracao") or 0) or duracao_midia(voz)
    cenas = []
    for i, c in enumerate(brutas):
        de = float(c.get("de", 0))
        prox = float(brutas[i + 1].get("de", de)) if i + 1 < len(brutas) else (fim or de + 3)
        cenas.append({**c, "n": i + 1, "tipo": str(c.get("tipo") or "cena"), "de": round(de, 3),
                      "ate": round(float(c.get("ate") or prox), 3)})
    total = max([c["ate"] for c in cenas] + [fim, 0.0])
    return {"total": round(total, 3), "cenas": cenas, "largura": largura, "altura": altura,
            "fps": int(doc.get("fps") or FPS), "voz": voz}


def checar(doc: dict, pasta: Path, plano: dict) -> dict:
    """O que já dá pra reprovar antes do render. As medidas do formato (do exemplo e das regras) entram aqui."""
    motivos = []
    cenas = plano["cenas"]
    if not cenas:
        motivos.append("O cenas.json não tem nenhuma cena")
    for a, b in zip(cenas, cenas[1:]):
        if b["de"] < a["ate"] - .01:
            motivos.append(f"A cena {b['n']} começa antes da cena {a['n']} terminar")
    for c in cenas:
        if c["ate"] <= c["de"]:
            motivos.append(f"A cena {c['n']} termina antes de começar ({br(c['de'])} s → {br(c['ate'])} s)")
        for k in ("imagem", "video"):
            if isinstance(c.get(k), str) and c[k] and not achar(c[k], pasta):
                motivos.append(f"A cena {c['n']} pede {k} que não existe: {c[k]}")
    if doc.get("voz") and not plano["voz"]:
        motivos.append(f"A voz não foi encontrada: {doc['voz']}")
    mus = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    if mus.get("arquivo") and not achar(mus["arquivo"], pasta):
        motivos.append(f"A música não foi encontrada: {mus['arquivo']}")
    for e in doc.get("efeitos") if isinstance(doc.get("efeitos"), list) else []:
        if isinstance(e, dict) and not achar(e.get("arquivo"), pasta):
            motivos.append(f"O efeito não foi encontrado: {e.get('arquivo')}")
    numeros = {"cenas": len(cenas), "total_s": plano["total"],
               "musica": {"sem": not mus.get("arquivo"), "faixas": [mus["arquivo"]] if mus.get("arquivo") else []},
               "efeitos": {"total": len([e for e in doc.get("efeitos") or [] if isinstance(e, dict)])}}
    return {"ok": not motivos, "motivos": motivos, "numeros": numeros}


def _gravar(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────────── som: voz + música (baixa) + efeitos, -14 LUFS ─────────────────────────────

def montar_som(doc: dict, plano: dict, pasta: Path, dur: float, saida: Path) -> Path | None:
    """Mistura voz, música (volume do cenas.json, padrão 0,12) e efeitos ({"t", "arquivo", "volume"}). None = sem som."""
    entradas, filtros, rotulos = [], [], []
    if plano["voz"]:
        entradas += ["-i", str(plano["voz"])]
        filtros.append(f"[{len(rotulos)}:a]aresample=48000[a{len(rotulos)}]")
        rotulos.append(f"[a{len(rotulos)}]")
    mus = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    arq = achar(mus.get("arquivo"), pasta)
    if arq:
        entradas += ["-ss", str(float(mus.get("inicio_s") or 0)), "-i", str(arq)]
        k = len(rotulos)
        filtros.append(f"[{k}:a]aresample=48000,volume={float(mus.get('volume') or .12)},"
                       f"afade=t=out:st={max(0, dur - 1.5):.2f}:d=1.5[a{k}]")
        rotulos.append(f"[a{k}]")
    for e in doc.get("efeitos") if isinstance(doc.get("efeitos"), list) else []:
        f = achar(e.get("arquivo"), pasta) if isinstance(e, dict) else None
        if not f:
            continue
        k = len(rotulos)
        ms = int(float(e.get("t", 0)) * 1000)
        entradas += ["-i", str(f)]
        filtros.append(f"[{k}:a]aresample=48000,volume={float(e.get('volume') or .3)},adelay={ms}|{ms}[a{k}]")
        rotulos.append(f"[a{k}]")
    if not rotulos:
        return None
    filtros.append("".join(rotulos) + f"amix=inputs={len(rotulos)}:normalize=0:duration=longest,"
                   f"apad,atrim=0:{dur:.3f},loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    saida.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", ";".join(filtros), "-map", "[out]",
                        "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(saida)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("o som não saiu: " + (r.stderr or "").strip()[-300:])
    return saida


# ───────────────────────────── navegador ─────────────────────────────

class _Servidor(http.server.SimpleHTTPRequestHandler):
    """/ = pasta do motor (index.html); /f/<caminho absoluto> = mídia (só dentro das pastas liberadas)."""
    raizes: tuple[Path, ...] = ()

    def translate_path(self, path):
        p = urllib.parse.unquote(path.split("?")[0].split("#")[0])
        if p.startswith("/f/"):
            alvo = Path(p[2:]).resolve()
            if any(alvo == r or r in alvo.parents for r in self.raizes):
                return str(alvo)
            return str(AQUI / "__negado__")
        return super().translate_path(path)

    def log_message(self, *a):
        pass


class _Http(http.server.ThreadingHTTPServer):
    request_queue_size = 512   # vários navegadores pedindo quadros ao mesmo tempo
    daemon_threads = True


def url(p: Path) -> str:
    return "/f" + urllib.parse.quote(str(Path(p).resolve()))


def servir(*raizes: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    _Servidor.raizes = tuple(Path(r).resolve() for r in raizes)
    srv = _Http(("127.0.0.1", 0), functools.partial(_Servidor, directory=str(AQUI)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _pagina(plano: dict, pasta: Path) -> dict:
    """O que a página recebe em window.PLANO: as cenas com a mídia já em /f/... (imagem, video)."""
    cenas = []
    for c in plano["cenas"]:
        c = dict(c)
        for k in ("imagem", "video"):
            if k in c:   # mídia que não existe sai da página (senão o 404 derruba o motor); a checagem avisa
                f = achar(c[k], pasta) if isinstance(c[k], str) else None
                c[k] = url(f) if f else None
        cenas.append(c)
    return {"total": plano["total"], "cenas": cenas, "largura": plano["largura"], "altura": plano["altura"]}


def abrir(p, porta: int, pagina: dict):
    nav = p.chromium.launch()
    pg = nav.new_page(viewport={"width": pagina["largura"], "height": pagina["altura"]}, device_scale_factor=1)
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pg.add_init_script("window.PLANO = " + json.dumps(pagina, ensure_ascii=False) + ";")
    pg.goto(f"http://127.0.0.1:{porta}/index.html")
    try:
        pg.wait_for_function("window.seek && window.pronto", timeout=60000)
    except Exception:
        raise SystemExit("o motor não carregou: " + " | ".join(erros[:3]))
    if erros:
        raise SystemExit("erro no motor: " + erros[0])
    return nav, pg


def _codec() -> list[str]:
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "h264_videotoolbox" in enc:
        return ["-c:v", "h264_videotoolbox", "-b:v", "14M", "-maxrate", "18M", "-bufsize", "28M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]


def _trecho(porta: int, pagina_json: str, f0: int, f1: int, fps: int, saida: str, codec: list[str]) -> str:
    """Um processo: abre o motor e grava os quadros [f0, f1) num mp4 parcial."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            nav, pg = abrir(p, porta, json.loads(pagina_json))
        except SystemExit as e:   # SystemExit num processo filho mata o processo sem avisar o pai
            raise RuntimeError(str(e)) from None
        ff = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps),
                               "-c:v", "mjpeg", "-i", "-", *codec, "-pix_fmt", "yuv420p", "-r", str(fps), saida],
                              stdin=subprocess.PIPE)
        for f in range(f0, f1):
            pg.evaluate("t => seek(t)", f / fps)
            ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
        ff.stdin.close()
        ff.wait()
        nav.close()
    return saida


# ───────────────────────────── storyboard e conferência ─────────────────────────────

def _fonte(tam: int):
    from PIL import ImageFont
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if Path(f).exists():
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}".replace(".", ",")


def _quebrar(txt: str, fonte, largura: int, draw) -> list[str]:
    linhas, cur = [], ""
    for w in txt.split():
        if cur and draw.textlength(cur + " " + w, font=fonte) > largura:
            linhas.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return linhas + [cur] if cur else linhas


def storyboard(pg, plano: dict, out: Path, rodape: list[str], falta: list[str]) -> Path:
    """Um quadro por cena (no fim dela, quando tudo já entrou), 4 colunas: 'N. tipo · 0:12,3' e a fala embaixo.
    Rodapé: o som e, em vermelho, o que a checagem reprova."""
    from io import BytesIO
    from PIL import Image, ImageDraw
    vertical = plano["altura"] >= plano["largura"]
    cw, ch = (360, round(360 * plano["altura"] / plano["largura"])) if vertical else (480, round(480 * plano["altura"] / plano["largura"]))
    faixa, f1, f2 = 150, _fonte(24), _fonte(21)
    cols = max(1, min(4 if vertical else 3, len(plano["cenas"])))
    cel = []
    for c in plano["cenas"]:
        pg.evaluate("t => seek(t)", round(max(c["de"] + .7 * (c["ate"] - c["de"]), c["ate"] - .12), 3))
        im = Image.open(BytesIO(pg.screenshot(type="png"))).convert("RGB").resize((cw, ch), Image.LANCZOS)
        cx = Image.new("RGB", (cw, ch + faixa), (250, 247, 242))
        cx.paste(im, (0, 0))
        d = ImageDraw.Draw(cx)
        d.text((12, ch + 10), f"{c['n']}. {c['tipo']} · {mmss(c['de'])}", font=f1, fill=(30, 30, 30))
        for k, l in enumerate(_quebrar("“" + str(c.get("fala") or c.get("texto") or "(respiro)") + "”", f2, cw - 24, d)[:4]):
            d.text((12, ch + 44 + k * 25), l, font=f2, fill=(70, 60, 60))
        cel.append(cx)
    larg = cols * (cw + 12) + 12
    med = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    fr = _fonte(26)
    linhas = [(l, (240, 236, 228)) for r in rodape for l in _quebrar(r, fr, larg - 32, med)]
    linhas += [(l, (255, 120, 110)) for m in falta[:4] for l in _quebrar("Falta: " + m, fr, larg - 32, med)]
    rod = 30 + 36 * len(linhas)
    n_l = max(1, -(-len(cel) // cols))
    folha = Image.new("RGB", (larg, n_l * (ch + faixa + 12) + 12 + rod), (40, 36, 44))
    for i, cx in enumerate(cel):
        folha.paste(cx, (12 + (i % cols) * (cw + 12), 12 + (i // cols) * (ch + faixa + 12)))
    for k, (l, cor) in enumerate(linhas):
        ImageDraw.Draw(folha).text((16, folha.height - rod + 16 + 36 * k), l, font=fr, fill=cor)
    dst = out / "storyboard.jpg"
    folha.save(dst, quality=88)
    return dst


def som_txt(doc: dict, plano: dict) -> str:
    mus = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    efe = [e for e in doc.get("efeitos") or [] if isinstance(e, dict)] if isinstance(doc.get("efeitos"), list) else []
    return (f"{len(plano['cenas'])} cenas · {mmss(plano['total'])} · voz: {'sim' if plano['voz'] else 'não'} · "
            f"música: {Path(mus['arquivo']).name if mus.get('arquivo') else 'sem'} · efeitos: {len(efe)}")


def exemplo_principal() -> Path | None:
    """O 1º de "exemplos" no formatos/<FORMATO>/formato.json."""
    pasta = ESTUDIO / "formatos" / FORMATO
    try:
        exs = json.loads((pasta / "formato.json").read_text(encoding="utf-8")).get("exemplos") or []
    except (OSError, ValueError):
        return None
    v = pasta / str((exs[0] if exs and isinstance(exs[0], dict) else {}).get("arquivo") or "")
    return v if exs and v.is_file() else None


def _folha(video: Path, destino: Path) -> Path | None:
    """A mesma folha do exemplo (1 quadro a cada 4 s, segundo marcado): formatos.py fazer_folha; sem ele, ffmpeg puro."""
    try:
        sys.path.insert(0, str(ESTUDIO / "app" / "ferramentas"))
        from formatos import fazer_folha
        return fazer_folha(video, destino)
    except Exception:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", "fps=1/4,scale=216:-2,tile=6x4",
                            "-frames:v", "1", str(destino)], capture_output=True)
        return destino if not r.returncode and destino.is_file() else None


def folha_comparacao(video: Path, qa: Path) -> Path | None:
    """Exemplo principal em cima, este vídeo embaixo: o João compara os dois de uma vez."""
    from PIL import Image, ImageDraw
    partes = []
    for rot, v in (("EXEMPLO PRINCIPAL", exemplo_principal()), ("ESTE VÍDEO", video)):
        f = _folha(v, qa / f"_folha-{len(partes)}.jpg") if v else None
        if f:
            partes.append((rot, Image.open(f).convert("RGB")))
            f.unlink()
    if not partes:
        return None
    larg = max(im.width for _, im in partes)
    folha = Image.new("RGB", (larg, sum(im.height + 56 for _, im in partes)), (24, 22, 26))
    y = 0
    for rot, im in partes:
        ImageDraw.Draw(folha).text((14, y + 12), rot, font=_fonte(30), fill=(245, 240, 230))
        folha.paste(im, (0, y + 56))
        y += im.height + 56
    dst = qa / "folha-comparacao.jpg"
    folha.save(dst, quality=86)
    return dst


def conferir(doc: dict, pasta: Path, out: Path, video: Path) -> dict:
    """Reprova sozinho (tamanho, duração, som) e grava qa/conferir.json e qa/folha-comparacao.jpg. O olho no lado a
    lado com o exemplo continua obrigatório: pior que o exemplo não sai."""
    qa = out / "qa"
    plano = planejar(doc, pasta)
    ch = checar(doc, pasta, plano)
    motivos, num = list(ch["motivos"]), dict(ch["numeros"])
    if video.is_file():
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True)
        pr = json.loads(r.stdout or "{}")
        st = next((s for s in pr.get("streams") or [] if s.get("codec_type") == "video"), {})
        tem_som = any(s.get("codec_type") == "audio" for s in pr.get("streams") or [])
        dur = round(float((pr.get("format") or {}).get("duration") or 0), 2)
        num["video"] = {"arquivo": str(video), "largura": st.get("width"), "altura": st.get("height"), "duracao_s": dur}
        if (st.get("width"), st.get("height")) != (plano["largura"], plano["altura"]):
            motivos.append(f"O vídeo tem {st.get('width')}x{st.get('height')}: tem que ser {plano['largura']}x{plano['altura']}")
        if abs(dur - plano["total"]) > .5:
            motivos.append(f"O vídeo tem {br(dur)} s e as cenas somam {br(plano['total'])} s")
        if (plano["voz"] or (doc.get("musica") or {}).get("arquivo")) and not tem_som:
            motivos.append("O vídeo saiu sem som")
        qa.mkdir(parents=True, exist_ok=True)
        f = folha_comparacao(video, qa)
        num["folha"] = str(f) if f else None
        if not exemplo_principal():
            num["aviso"] = "o formato ainda não tem exemplo principal: a folha mostra só este vídeo"
    else:
        num["video"] = None
        motivos.append(f"Vídeo não encontrado: {video} (rode o render antes do --conferir)")
    res = {"ok": not motivos, "motivos": motivos, "numeros": num}
    _gravar(qa / "conferir.json", res)
    return res


# ───────────────────────────── principal ─────────────────────────────

def _cenas_padrao() -> Path:
    for p in (Path.cwd() / "cenas.json", AQUI / "cenas.json"):
        if p.exists():
            return p
    raise SystemExit("cenas.json não encontrado: rode de dentro da pasta do vídeo ou passe --cenas <arquivo> (exemplo: cenas-modelo.json)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Motor do formato (genérico do Estúdio)")
    ap.add_argument("--cenas", type=Path)
    ap.add_argument("--out", type=Path, help="pasta de saída (padrão: a do cenas.json)")
    ap.add_argument("--saida", type=Path, help="mp4 final (padrão: <out>/<saida do cenas.json ou video.mp4>)")
    ap.add_argument("--ate", type=float, help="só os N primeiros segundos (teste.mp4)")
    ap.add_argument("--quadro", help="segundos separados por vírgula ou 'cenas' (um PNG no meio de cada cena)")
    ap.add_argument("--storyboard", action="store_true")
    ap.add_argument("--conferir", action="store_true")
    ap.add_argument("--video", type=Path, help="mp4 a conferir (padrão: o vídeo final)")
    ap.add_argument("--sem-som", action="store_true", help="no --storyboard, não monta a previa-som.m4a")
    ap.add_argument("--processos", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    a = ap.parse_args()
    arq = (a.cenas or _cenas_padrao()).resolve()
    pasta = arq.parent
    out = (a.out or pasta).resolve()
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(arq.read_text(encoding="utf-8"))
    final = (a.saida or out / str(doc.get("saida") or "video.mp4")).resolve()
    if a.conferir:
        r = conferir(doc, pasta, out, (a.video or final).resolve())
        print(f"conferência: {out / 'qa' / 'conferir.json'}" + (f" · folha: {r['numeros'].get('folha')}" if r["numeros"].get("folha") else ""))
        if r["ok"]:
            print("APROVADO pela conferência (agora olhe a folha lado a lado: pior que o exemplo não sai)")
            return
        print("REPROVADO:\n- " + "\n- ".join(r["motivos"]))
        sys.exit(1)
    t_ini = time.time()
    plano = planejar(doc, pasta)
    pagina = _pagina(plano, pasta)
    srv, porta = servir(AQUI, pasta, out, ESTUDIO)
    print(f"duração {plano['total']:.2f}s · {len(plano['cenas'])} cenas")
    if a.quadro or a.storyboard:
        from playwright.sync_api import sync_playwright
        ch = checar(doc, pasta, plano) if a.storyboard else None
        if ch is not None and not a.sem_som:
            try:
                p_som = montar_som(doc, plano, pasta, plano["total"], out / "previa-som.m4a")
                if p_som:
                    print(f"prévia do som: {p_som}")
            except SystemExit as e:
                ch["motivos"].append(f"A prévia do som não saiu: {e}")
        with sync_playwright() as p:
            nav, pg = abrir(p, porta, pagina)
            if ch is not None:
                print(f"storyboard: {storyboard(pg, plano, out, [som_txt(doc, plano)], ch['motivos'])}")
                _gravar(out / "qa" / "checagem.json", {**ch, "ok": not ch["motivos"]})
            if a.quadro:
                d = out / "quadros"
                d.mkdir(exist_ok=True)
                alvos = ([((c["de"] + c["ate"]) / 2, f"{c['n']:02d}-{c['tipo']}") for c in plano["cenas"]] if a.quadro == "cenas"
                         else [(float(x), f"{float(x):06.2f}") for x in a.quadro.split(",") if x.strip()])
                for t, nome in alvos:
                    pg.evaluate("t => seek(t)", t)
                    pg.screenshot(path=str(d / f"{nome}.png"))
                print(f"quadros: {len(alvos)} em {d}")
            nav.close()
        srv.shutdown()
        if ch is not None:
            if ch["motivos"]:
                print("REPROVADO na checagem (corrija o cenas.json e rode o --storyboard de novo):\n- " + "\n- ".join(ch["motivos"]))
                sys.exit(1)
            print("APROVADO na checagem: pode mostrar o storyboard")
        return
    dur = plano["total"] if a.ate is None else min(a.ate, plano["total"])
    if a.ate is not None:
        final = out / "teste.mp4"
    fps = plano["fps"]
    n = max(1, int(round(dur * fps)))
    k = max(1, min(a.processos, n // (fps * 3) or 1))
    lim = [round(n * j / k) for j in range(k + 1)]
    partes = [str(out / f"_parte{j}.mp4") for j in range(k)]
    pagina_json, codec = json.dumps(pagina, ensure_ascii=False), _codec()
    from concurrent.futures import ProcessPoolExecutor
    try:
        with ProcessPoolExecutor(k, mp_context=mp.get_context("spawn")) as ex:
            list(ex.map(_trecho, *zip(*[(porta, pagina_json, lim[j], lim[j + 1], fps, partes[j], codec) for j in range(k)])))
    except Exception as e:
        raise SystemExit(f"o render parou: {e}")
    finally:
        srv.shutdown()
    lista = out / "_partes.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes))
    mudo = out / "_mudo.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo)], check=True)
    trilha = montar_som(doc, plano, pasta, dur, out / "_trilha.m4a")
    if trilha:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mudo), "-i", str(trilha), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mudo), "-c", "copy", "-movflags", "+faststart", str(final)], check=True)
    for p in partes + [str(mudo), str(lista)] + ([str(trilha)] if trilha else []):
        Path(p).unlink(missing_ok=True)
    print(f"quadros: {n} ({k} processos) · total {time.time() - t_ini:.0f}s")
    print(f"pronto: {final}")


if __name__ == "__main__":
    main()
