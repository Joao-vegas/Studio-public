"""
Prepara a narração do motion pra animação.

<projeto>/audio/voz-bruta.wav → corta a direção que o TTS leu antes do texto → encurta pausas
longas → acelera (--tempo, padrão 1.08) → nivela o volume → audio/voz.wav → whisper local →
audio/palavras.json (tempo de cada palavra, é disso que a timeline se ancora).

Serve também pra voz gravada pelo João: é só pôr o arquivo em audio/voz-bruta.wav.

Uso: python3 ~/Projetos/Skill/Estúdio/app/ferramentas/motion/preparar_audio.py --pasta <projeto> [--tempo 1.0]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio import inicio_do_texto, limpar_cauda_arquivo, nivelar, norm, palavras  # noqa: E402

try:
    sys.path.append("/Users/joaomarcospiki/Cerebro/scripts")
    from limpar_runtime import registrar_cleanup_no_atexit
except ImportError:
    registrar_cleanup_no_atexit = lambda: None  # noqa: E731


def main() -> None:
    registrar_cleanup_no_atexit()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True, type=Path)
    ap.add_argument("--tempo", type=float, default=1.08)
    a = ap.parse_args()
    A = a.pasta / "audio"
    roteiro = (a.pasta / "roteiro.txt").read_text()

    corte = inicio_do_texto(A / "voz-bruta.wav", roteiro)
    print(f"instrução lida até {corte:.2f}s")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(corte), "-i", str(A / "voz-bruta.wav"), "-af",
                    "silenceremove=stop_periods=-1:stop_duration=0.55:stop_threshold=-45dB:stop_silence=0.45,"
                    f"apad=pad_dur=0.3,atempo={a.tempo}", "-ar", "48000", str(A / "voz.wav")], check=True)
    nivelar(A / "voz.wav")
    # G10: rajada de ruído isolada no fim (depois de pausa) sai antes do whisper, que senão a "ouve" como palavra.
    rajada = limpar_cauda_arquivo(A / "voz.wav")
    if rajada:
        print(f"G10: removi rajada de ruído de {rajada:.2f}s no fim da voz")
    final = palavras(A / "voz.wav")
    # O whisper inventa frase no silêncio do fim: corta depois da última palavra do roteiro.
    ultima = norm(roteiro.split()[-1])
    fins = [k for k, w in enumerate(final) if norm(w["w"]) == ultima]
    # S5c: o TTS às vezes lê o fim do roteiro duas vezes (bloco curto no final). Corta na ocorrência
    # da última palavra cuja contagem bate com o tamanho do roteiro, não na última.
    n_rot = len(roteiro.split())
    if len(final) > n_rot * 1.06:
        sys.exit(f"PARE: whisper ouviu {len(final)} palavras, roteiro tem {n_rot}. A voz tem trecho a mais (direção lida ou repetição). Gere a narração de novo.")
    if fins:
        final = final[:min(fins, key=lambda k: abs(k + 1 - n_rot)) + 1]
    # S3: o TTS solta um estalo de ruído depois da última palavra (soa "TV falhando"). Corta tudo depois dela.
    fim = final[-1]["e"] + 0.12
    corte_fim = A / "voz-corte.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(A / "voz.wav"), "-af",
                    f"atrim=0:{fim},afade=t=out:st={fim - 0.08}:d=0.08,apad=pad_dur=0.3", str(corte_fim)], check=True)
    corte_fim.replace(A / "voz.wav")
    (A / "palavras.json").write_text(json.dumps(final, ensure_ascii=False))
    print(" ".join(f"{k}:{w['w']}@{w['s']}" for k, w in enumerate(final)))


if __name__ == "__main__":
    main()
