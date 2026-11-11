#!/usr/bin/env python3
"""
checar_cauda: confere a regra G10 (nada de ruído depois da última palavra) num vídeo ou áudio pronto.

    python3 checar_cauda.py <arquivo.mp4|wav> [--fim-fala <s>]

--fim-fala: onde termina a última palavra de verdade (ex.: do tempos.json). Uma palavra final curta depois de pausa
("Não.") parece rajada pra quem só olha o volume; com o fim da fala, só conta como ruído o que vem DEPOIS dela.

Imprime "OK" ou "AVISO: ..." e sai com código 1 se houver aviso. Avisa quando:
  - há uma rajada curta (< 0,6 s) isolada depois de uma pausa >= 0,2 s abaixo de -45 dB (o estalo "TV falhando");
  - ou os últimos 0,2 s têm sinal acima de -60 dB (o fim devia ser silêncio puro).
Vídeo com música até o último frame cai no 2º aviso: aí olhe se é a música (esperado) ou a voz.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "motion"))
from audio import LIM_CAUDA_DB, analisar_cauda  # noqa: E402

SR = 48000


def checar(arq: Path, fim_fala: float | None = None) -> tuple[bool, str]:
    import numpy as np

    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq), "-vn", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True)
    if r.returncode or not r.stdout:
        return False, f"AVISO: não consegui extrair áudio de {arq.name}"
    a = analisar_cauda(np.frombuffer(r.stdout, np.float32), SR)
    total = len(r.stdout) / 4 / SR
    if a["rajada_dur"] is not None and fim_fala is not None and a["rajada_ini"] < fim_fala + 0.05:
        a["rajada_dur"] = None   # a "rajada" é a última palavra (curta, depois de pausa), não ruído
    if a["rajada_dur"] is not None:
        return False, (f"AVISO: ruído de {a['rajada_dur']:.2f} s depois da última fala "
                       f"(começa em {a['rajada_ini']:.2f} s de {total:.2f} s)")
    if a["ultimos_db"] > LIM_CAUDA_DB:
        return False, f"AVISO: ruído nos últimos 0,2 s ({a['ultimos_db']:.0f} dB, o fim devia estar abaixo de {LIM_CAUDA_DB:.0f} dB)"
    return True, "OK"


def fechar(arq: Path, backup: Path | None = None) -> str:
    """Fim do áudio com ruído nos últimos 0,2 s (G10; visto 30-out no Explicador 3D e no Documentário: -25 dB)? Remonta o mp4 com fade-out e
    fade-out no som e o vídeo intacto (-c:v copy). Guarda o original em `backup` (nada é apagado). Devolve o que fez ('' = nada)."""
    ok, msg = checar(arq)
    if ok or "últimos 0,2 s" not in msg:
        return ""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arq)],
                               capture_output=True, text=True).stdout.strip() or 0)
    if dur < 1:
        return ""
    tmp = arq.with_name(arq.stem + ".cauda.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(arq), "-c:v", "copy", "-af", f"afade=t=out:st={dur - .55:.3f}:d=0.3",
                        "-c:a", "aac", "-b:a", "192k", str(tmp)], capture_output=True)
    if r.returncode or not tmp.is_file() or not checar(tmp)[0]:
        tmp.unlink(missing_ok=True)
        return ""
    if backup:
        backup.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(arq, backup)
    tmp.replace(arq)
    return "fade de 0,3 s e silêncio nos últimos 0,25 s do áudio (ruído no fim)"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--fim-fala", type=float)
    ap.add_argument("--fechar", action="store_true", help="se o fim tiver ruído, põe fade-out e silêncio no fim (original vai pra <arquivo>.antes-cauda.mp4)")
    a = ap.parse_args()
    if a.fechar:
        arq = a.arquivo.expanduser()
        print(fechar(arq, arq.with_suffix(".antes-cauda.mp4")) or "nada a fazer")
    ok, msg = checar(a.arquivo.expanduser(), a.fim_fala)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
