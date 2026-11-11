#!/usr/bin/env python3
"""
voz — quem narra os formatos por roteiro. Três caminhos, escolhidos em Configurações:

    voicestudio voz local e grátis (VoiceStudio, porta 3900); padrão. Fora do ar, cai pra ElevenLabs só se houver chave E voz;
                senão para com o erro claro "VoiceStudio fechado: abra ele" (o Gemini saiu do Estúdio em 29-out-2026)
    elevenlabs  voz da ElevenLabs, inclusive a SUA voz clonada (ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID)
    gravada     você grava a narração e sobe o arquivo

A chave nunca vai pro navegador nem pro git: mora só no app/.env.

    python3 voz.py falar "texto" saida.mp3          # usa a voz padrão
    python3 voz.py clonar "Minha voz" a.m4a b.m4a   # cria a voz clonada na ElevenLabs e salva o ID
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO, gravar_json, ler_json

ENV = ESTUDIO / ".env"
CONFIG = ESTUDIO / "config.json"
API = "https://api.elevenlabs.io/v1"
MODELO_ELEVEN = "eleven_multilingual_v2"
PADROES = {"voicestudio": "VoiceStudio (grátis, no seu Mac)", "elevenlabs": "ElevenLabs (sua voz clonada ou uma voz da biblioteca)",
           "gravada": "Eu gravo a narração"}


def _env() -> dict:
    out = {}
    if ENV.exists():
        for l in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _gravar_env(novos: dict) -> None:
    linhas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    feitos = set()
    for i, l in enumerate(linhas):
        if "=" in l and not l.lstrip().startswith("#"):
            k = l.split("=", 1)[0].strip()
            if k in novos:
                linhas[i] = f"{k}={novos[k]}"; feitos.add(k)
    for k, v in novos.items():
        if k not in feitos:
            linhas.append(f"{k}={v}")
    ENV.write_text("\n".join(linhas).rstrip() + "\n", encoding="utf-8")
    os.chmod(ENV, 0o600)


def _padrao_valido(p) -> str:
    """Padrão salvo que não existe mais (ex.: 'gemini', tirado em 29-out-2026) vira VoiceStudio."""
    return p if p in PADROES else "voicestudio"


def status() -> dict:
    e = _env()
    cfg = ler_json(CONFIG, {}) or {}
    return {
        "padrao": _padrao_valido(cfg.get("voz_padrao")),
        "voicestudio": {"voz": cfg.get("voz_voicestudio", "default")},
        "elevenlabs": {"chave": bool(e.get("ELEVENLABS_API_KEY")), "voice_id": e.get("ELEVENLABS_VOICE_ID", ""),
                       "nome_voz": cfg.get("voz_eleven_nome", "")},
        "padroes": PADROES,
    }


def salvar(padrao: str | None = None, chave: str = "", voice_id: str | None = None, voz_voicestudio: str = "") -> None:
    novos = {}
    if chave.strip():
        novos["ELEVENLABS_API_KEY"] = chave.strip()
    if voice_id is not None and voice_id.strip() != _env().get("ELEVENLABS_VOICE_ID", ""):
        novos["ELEVENLABS_VOICE_ID"] = voice_id.strip()
    if novos:
        _gravar_env(novos)
    cfg = ler_json(CONFIG, {}) or {}
    if padrao in PADROES:
        cfg["voz_padrao"] = padrao
    if voz_voicestudio.strip():
        cfg["voz_voicestudio"] = voz_voicestudio.strip()
    gravar_json(CONFIG, cfg)


def _pedido(caminho: str, dados: bytes | None = None, tipo: str = "application/json", metodo: str = "GET"):
    chave = _env().get("ELEVENLABS_API_KEY")
    if not chave:
        raise ValueError("Coloque a chave da ElevenLabs em Configurações → Voz.")
    req = urllib.request.Request(API + caminho, data=dados, method=metodo,
                                 headers={"xi-api-key": chave, "Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "ignore")[:300]
        raise ValueError(f"ElevenLabs respondeu {e.code}: {corpo}") from None


def verificar() -> str:
    d = json.loads(_pedido("/user/subscription"))
    return f"Plano {d.get('tier', '?')}: {d.get('character_count', 0)} de {d.get('character_limit', 0)} caracteres usados no mês."


def clonar(nome: str, arquivos: list[Path]) -> str:
    """Clone instantâneo: 1 a 3 minutos de áudio limpo, só a sua voz."""
    if not arquivos:
        raise ValueError("Envie pelo menos um áudio com a sua voz (1 a 3 minutos, sem música).")
    fronteira = uuid.uuid4().hex
    partes = [f'--{fronteira}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{nome or "Minha voz"}\r\n'.encode()]
    for a in arquivos:
        mime = mimetypes.guess_type(a.name)[0] or "audio/mpeg"
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="files"; filename="{a.name}"\r\n'
                      f'Content-Type: {mime}\r\n\r\n'.encode() + a.read_bytes() + b"\r\n")
    partes.append(f"--{fronteira}--\r\n".encode())
    d = json.loads(_pedido("/voices/add", b"".join(partes), f"multipart/form-data; boundary={fronteira}", "POST"))
    vid = d.get("voice_id")
    if not vid:
        raise ValueError("A ElevenLabs não devolveu o ID da voz.")
    _gravar_env({"ELEVENLABS_VOICE_ID": vid})
    cfg = ler_json(CONFIG, {}) or {}
    cfg["voz_eleven_nome"] = nome or "Minha voz"; cfg["voz_padrao"] = "elevenlabs"
    gravar_json(CONFIG, cfg)
    return vid


def falar_eleven(texto: str, saida: Path) -> Path:
    vid = _env().get("ELEVENLABS_VOICE_ID")
    if not vid:
        raise ValueError("Escolha ou clone uma voz da ElevenLabs em Configurações → Voz.")
    corpo = json.dumps({"text": texto, "model_id": MODELO_ELEVEN,
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}).encode()
    audio = _pedido(f"/text-to-speech/{vid}?output_format=mp3_44100_128", corpo, "application/json", "POST")
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_bytes(audio)
    _limpar_cauda_mp3(saida)
    return saida


def motor_escolhido(cliente: str | None = None) -> str:
    """Motor que vai falar de fato: o padrão (ou o do cliente); VoiceStudio fora do ar cai pra ElevenLabs
    só com chave E voz; sem isso fica 'voicestudio' e o `falar` para com o erro claro. 'gravada' nunca é trocada."""
    padrao = status()["padrao"]
    if cliente:
        padrao = _padrao_valido((voz_do_cliente(cliente) or {}).get("motor") or padrao)
    if padrao != "voicestudio":
        return padrao
    import voicestudio
    if voicestudio.garantir_no_ar(60):   # fora do ar: sobe o backend sem janela e espera até 60 s
        return "voicestudio"
    st = status()
    if st["elevenlabs"]["chave"] and st["elevenlabs"]["voice_id"]:
        return "elevenlabs"
    return "voicestudio"  # sem reserva: o `falar` mostra "VoiceStudio fechado: abra ele"


def voz_do_cliente(cliente: str) -> dict:
    """`voz` do identidade.json do cliente ({motor, id}); vazio se não tiver."""
    from _comum import RAIZ
    for f in (RAIZ / "clientes" / cliente).glob("identidade.json"):
        v = (ler_json(f, {}) or {}).get("voz")
        if isinstance(v, dict):
            return v
    return {}


MSG_VS_FECHADO = "A voz não subiu sozinha. Abra o VoiceStudio (aplicativo) uma vez e tente de novo."


def falar(texto: str, saida: Path, voz: str | None = None, cliente: str | None = None) -> Path:
    """Voz única: VoiceStudio → ElevenLabs (só com chave e voz). Devolve o arquivo (mp3).
    O motor usado vai pro stderr (log)."""
    saida = Path(saida)
    motor = motor_escolhido(cliente)
    if motor == "voicestudio":
        import voicestudio
        if not voicestudio.no_ar():
            raise ValueError(MSG_VS_FECHADO)
        v = voz or (voz_do_cliente(cliente).get("id") if cliente else None) or status()["voicestudio"]["voz"]
        print("voz: VoiceStudio (grátis)", file=sys.stderr)
        return voicestudio.falar(texto, saida.with_suffix(".mp3"), v)
    if motor == "elevenlabs":
        print("voz: ElevenLabs", file=sys.stderr)
        return falar_eleven(texto, saida.with_suffix(".mp3"))
    raise ValueError("A voz deste vídeo é gravada por você: suba o áudio da narração.")


def _limpar_cauda_mp3(arq: Path) -> None:
    """G10: tira a rajada de ruído do fim da voz. Só reescreve o mp3 se achou algo; qualquer falha deixa o original."""
    try:
        import subprocess
        import numpy as np
        sys.path.insert(0, str(Path(__file__).resolve().parent / "motion"))
        from audio import analisar_cauda, limpar_cauda
        sr = 44100
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                             capture_output=True, check=True).stdout
        x = np.frombuffer(pcm, np.float32)
        if analisar_cauda(x, sr)["rajada_dur"] is None:
            return
        tmp = arq.with_suffix(".limpo.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ac", "1", "-ar", str(sr), "-i", "-",
                        "-codec:a", "libmp3lame", "-q:a", "2", str(tmp)], input=limpar_cauda(x, sr).tobytes(), check=True)
        tmp.replace(arq)
    except Exception as e:  # noqa: BLE001
        print(f"aviso: não consegui limpar o fim da voz ({e})", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "falar":
        print(falar(sys.argv[2], Path(sys.argv[3])))
    elif len(sys.argv) >= 4 and sys.argv[1] == "clonar":
        print(clonar(sys.argv[2], [Path(x) for x in sys.argv[3:]]))
    elif len(sys.argv) == 2 and sys.argv[1] == "verificar":
        print(verificar())
    else:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
