"""
Chamada ao Gemini com rodízio de chaves, exclusivo da skill motion-design.

As chaves moram SÓ no .env do Estúdio (app/.env) (GEMINI_API_KEY_1..7; a 7 e a 6 são da conta paga e vão primeiro), cada uma de um
projeto do Google diferente. Não lê variável de ambiente nem .env de outro projeto,
e nenhum outro script lê este .env.

Ordem: chave 1 → 2 → 3. Cota esgotada (429), chave inválida ou sem permissão
(400/403) pula pra próxima. Erro de servidor (5xx) tenta a mesma chave de novo.
Se todas as chaves falharem num modelo, passa pro próximo modelo da lista.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]  # app/ do Estúdio
ENV = SKILL / ".env"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

_TRACKER = Path("/Users/joaomarcospiki/Cerebro/scripts")
if _TRACKER.exists() and str(_TRACKER) not in sys.path:
    sys.path.append(str(_TRACKER))


def chaves() -> list[tuple[str, str]]:
    """[(nome, chave)] na ordem 1, 2, 3, só as preenchidas."""
    vals = {}
    if ENV.exists():
        for linha in ENV.read_text().splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    # 6 = conta paga (01-out): vai primeiro; as grátis (1..5) ficam de reserva
    out = [(f"chave {i}", vals.get(f"GEMINI_API_KEY_{i}", "")) for i in (7, 6, 1, 2, 3, 4, 5)]
    vistas = set()   # a mesma chave colada em dois números não entra duas vezes no rodízio
    out = [(n, v) for n, v in out if v and not (v in vistas or vistas.add(v))]
    if not out:
        sys.exit(f"Nenhuma chave em {ENV}. Preencha GEMINI_API_KEY_1 (e as reservas 2 e 3).")
    return out


USO = SKILL / "custos" / "gemini_uso.jsonl"


def registrar_chave(nome: str, modelo: str, dados: dict) -> None:
    """Anota QUAL chave atendeu cada pedido (a aba Custos usa isso pra separar conta paga de cota grátis)."""
    try:
        u = (dados or {}).get("usageMetadata") or {}
        USO.parent.mkdir(parents=True, exist_ok=True)
        with USO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "chave": nome, "modelo": modelo,
                                "entrada": int(u.get("promptTokenCount") or 0), "saida": int(u.get("candidatesTokenCount") or 0)},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def registrar(script: str, operacao: str, modelo: str, dados: dict) -> None:
    try:
        from custos_tracker import record_gemini_response
        record_gemini_response(script, operacao, modelo, dados)
    except Exception as e:  # tracker é do Cerebro; fora desta máquina a chamada segue sem ele
        print(f"  (custo não registrado: {e})")


def gerar(corpo: dict, modelos: list[str], script: str, operacao: str) -> tuple[dict, str]:
    """Faz generateContent tentando cada modelo × cada chave. Devolve (resposta, modelo usado)."""
    import requests

    ks = chaves()
    for modelo in modelos:
        for nome, chave in ks:
            for tentativa in range(3):
                try:
                    r = requests.post(URL.format(modelo=modelo), params={"key": chave}, json=corpo, timeout=300)
                except requests.exceptions.RequestException as e:  # API travada: tenta de novo em vez de derrubar tudo
                    print(f"  {nome} · {modelo}: sem resposta ({type(e).__name__}), tentando de novo")
                    time.sleep(8 * (tentativa + 1))
                    continue
                if r.status_code == 200:
                    dados = r.json()
                    print(f"  ok com {nome} · {modelo}")
                    registrar(script, operacao, modelo, dados)
                    registrar_chave(nome, modelo, dados)
                    return dados, modelo
                if r.status_code in (400, 401, 403, 404, 429):
                    print(f"  {nome} · {modelo}: erro {r.status_code}, pulando ({r.text[:120].strip()})")
                    break
                print(f"  {nome} · {modelo}: erro {r.status_code}, tentando de novo")
                time.sleep(8 * (tentativa + 1))
    sys.exit("Todas as chaves e modelos falharam. Veja a cota em aistudio.google.com/rate-limit.")
