#!/usr/bin/env python3
"""
corte_manual — quando o corte automático erra, o João marca na mão: "corta daqui até aqui".

Recebe a lista de trechos a TIRAR (início, fim em segundos), monta os trechos que ficam e reencoda
num arquivo só (H.264 + AAC, leve). Roda em segundo plano; o andamento fica em <pasta>/.manual.json.

    python3 corte_manual.py origem.mp4 saida.mp4 "[[3.2,5.0],[40.1,44.8]]"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import agora, ffprobe, gravar_json, ler_json


def manter(duracao: float, remover: list) -> list[tuple[float, float]]:
    cortes = sorted((max(0.0, float(a)), min(duracao, float(b))) for a, b in remover if float(b) > float(a))
    fica, t = [], 0.0
    for a, b in cortes:
        if a > t + 0.04:
            fica.append((t, a))
        t = max(t, b)
    if duracao > t + 0.04:
        fica.append((t, duracao))
    return fica


def combinar(tirar: list, devolver: list) -> list[list[float]]:
    """Une os trechos a tirar e subtrai os que o João devolveu (devolver pode partir um corte ao meio).
    Resultado ordenado, sem trecho menor que 0,05 s: é o `remover` que o Aplicar envia."""
    def une(lista):
        out = []
        for a, b in sorted((float(a), float(b)) for a, b in lista if float(b) > float(a)):
            if out and a <= out[-1][1]:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return out
    fica = une(tirar)
    for da, db in une(devolver):
        novo = []
        for a, b in fica:
            if db <= a or da >= b:
                novo.append([a, b])
                continue
            if da > a:
                novo.append([a, da])
            if db < b:
                novo.append([db, b])
        fica = novo
    return [[round(a, 3), round(b, 3)] for a, b in fica if b - a >= 0.05]


def picos(video: Path, por_segundo: int = 50) -> list[float]:
    """Altura (0 a 1) do som em cada fatia de 1/por_segundo s: a forma de onda do editor.
    Cache em app/.cache/onda/ (refaz se o vídeo mudou). Sem áudio: lista vazia."""
    video = Path(video)
    import hashlib
    cache = Path(__file__).resolve().parents[1] / ".cache" / "onda" / (hashlib.sha1(str(video.resolve()).encode()).hexdigest() + ".json")
    chave = {"arquivo": video.name, "mtime": video.stat().st_mtime, "por_segundo": por_segundo}
    c = ler_json(cache, {}) or {}
    if c.get("chave") == chave:
        return c.get("picos") or []
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "8000",
                        "-f", "s16le", "-"], capture_output=True, timeout=300)
    dados = r.stdout or b""
    jan = 8000 // por_segundo
    n = len(dados) // 2
    res = []
    if n:
        import array
        amostras = array.array("h")
        amostras.frombytes(dados[: n * 2])
        for i in range(0, n, jan):
            res.append(round(max(abs(x) for x in amostras[i:i + jan]) / 32768, 3))
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        gravar_json(cache, {"chave": chave, "picos": res})
    except OSError:
        pass
    return res


def aplicar(origem: Path, saida: Path, remover: list) -> dict:
    info = ffprobe(origem)
    dur = float(info.get("duracao") or 0)
    if not dur:
        raise ValueError("Não consegui ler a duração do vídeo.")
    fica = manter(dur, remover)
    if not fica:
        raise ValueError("Você marcou o vídeo inteiro pra sair.")
    partes, rotulos = [], ""
    for i, (a, b) in enumerate(fica):
        partes.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        partes.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:st=0:d=0.015,afade=t=out:st={max(0, b - a - 0.015):.3f}:d=0.015[a{i}]")
        rotulos += f"[v{i}][a{i}]"
    filtro = ";".join(partes) + f";{rotulos}concat=n={len(fica)}:v=1:a=1[v][a]"
    tmp = saida.with_name(saida.stem + ".parcial.mp4")
    # chip do Mac primeiro (o libx264 num bruto 4K levava minutos); se não der, o libx264 mais rápido
    for cod in (["-c:v", "h264_videotoolbox", "-b:v", "12M", "-allow_sw", "1"],
                ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20"]):
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(origem), "-filter_complex", filtro,
                            "-map", "[v]", "-map", "[a]", *cod, "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(tmp)],
                           capture_output=True, text=True)
        if not r.returncode and tmp.exists():
            break
    if r.returncode or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise ValueError("O ffmpeg falhou: " + (r.stderr or "")[-400:])
    antes = None
    if saida.exists():
        antes = saida.with_name(saida.stem + f"-antes-{agora().replace(':', '').replace(' ', '-')}.mp4")
        saida.rename(antes)   # o corte de antes fica guardado como versão (o "Voltar ao corte anterior" usa)
    tmp.rename(saida)
    return {"trechos_tirados": len(remover), "ficou_s": round(sum(b - a for a, b in fica), 2),
            "original_s": round(dur, 2), "arquivo": str(saida), "antes": str(antes) if antes else ""}


def estado(pasta: Path) -> dict:
    """O corte roda numa thread do servidor: se o Estúdio reiniciou no meio, ele morreu junto.
    Sem isso o "rodando" ficava pra sempre e a tela recarregava sem parar."""
    d = ler_json(pasta / ".manual.json", {}) or {}
    if d.get("rodando") and d.get("pid") != os.getpid():
        d = {**d, "rodando": False, "ok": False, "erro": "O corte parou no meio (o Estúdio reiniciou). Clique em Aplicar o corte de novo."}
        gravar_json(pasta / ".manual.json", d)
    return d


def disparar(origem: Path, saida: Path, remover: list, pasta: Path, depois=None) -> None:
    """Roda em segundo plano; `depois(resultado)` atualiza o registro do vídeo quando termina."""
    if estado(pasta).get("rodando"):
        raise ValueError("Já tem um corte manual rodando neste vídeo.")
    prev = estado(pasta)
    hist = list(prev.get("historico") or [])
    gravar_json(pasta / ".manual.json", {"rodando": True, "inicio": agora(), "remover": remover, "pid": os.getpid(), "historico": hist})

    def trabalho():
        try:
            res = aplicar(origem, saida, remover)
            if prev.get("ok") and prev.get("remover") is not None and res.get("antes"):   # cada Aplicar guarda o corte de antes
                hist.append({"remover": prev["remover"], "fim": prev.get("fim"), "trechos_tirados": prev.get("trechos_tirados"),
                             "ficou_s": prev.get("ficou_s"), "original_s": prev.get("original_s"), "video": res["antes"]})
            if depois:
                depois(res)
            gravar_json(pasta / ".manual.json", {"rodando": False, "fim": agora(), "ok": True, **res, "remover": remover, "historico": hist})
        except Exception as e:
            gravar_json(pasta / ".manual.json", {"rodando": False, "fim": agora(), "ok": False, "erro": str(e), "remover": remover, "historico": hist})

    threading.Thread(target=trabalho, daemon=True).start()


def voltar(saida: Path, pasta: Path, depois=None) -> dict:
    """Volta um passo: o corte de antes (lista de trechos + vídeo) vira o atual. Nada é apagado: o corte desfeito
    fica ao lado como `-desfeito-<hora>.mp4` e o de antes continua guardado."""
    import shutil
    est = estado(pasta)
    hist = list(est.get("historico") or [])
    if est.get("rodando"):
        raise ValueError("Espere o corte terminar.")
    if not hist:
        raise ValueError("Não tem corte anterior pra voltar.")
    ent = hist[-1]
    antes = Path(ent.get("video") or "")
    if not antes.is_file():
        raise ValueError("O vídeo do corte anterior não está mais na pasta.")
    if saida.exists():
        saida.rename(saida.with_name(saida.stem + f"-desfeito-{agora().replace(':', '').replace(' ', '-')}.mp4"))
    shutil.copy2(antes, saida)
    res = {"trechos_tirados": ent.get("trechos_tirados"), "ficou_s": ent.get("ficou_s"), "original_s": ent.get("original_s"), "arquivo": str(saida)}
    if depois:
        depois(res)
    gravar_json(pasta / ".manual.json", {"rodando": False, "fim": agora(), "ok": True, **res, "remover": ent["remover"], "historico": hist[:-1]})
    return res


if __name__ == "__main__":
    print(json.dumps(aplicar(Path(sys.argv[1]), Path(sys.argv[2]), json.loads(sys.argv[3])), ensure_ascii=False))
