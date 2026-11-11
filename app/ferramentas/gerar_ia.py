#!/usr/bin/env python3
"""
gerar_ia — gerar imagem ou vídeo por IA (kie.ai) DENTRO do Editar vídeo, por cena. PLANO-2.0.

    orçamento (grátis, só conta)  →  rascunho (guarda o custo congelado + nonce)  →  Permitir (nonce)  →  UMA createTask por tarefa
    →  as opções aparecem como miniaturas  →  o João clica numa e ela entra na cena (editor.usar_material: vira versão nova)

Regras (do João): nunca gera sem o clique dele com o custo na tela; sem retry de createTask (envio sem confirmação = "incerto",
não reenvia); chave nunca em log. Reusa o cardápio, o corpo do pedido, a chamada e o upload do broll_ia.py.
Arquivos: <pasta>/editor/gerados/<id>.json (o registro: modelo, prompt, custo, origem) + <id>-K.jpg / <id>-K.mp4 (+ <id>-K-quadros/).
O gasto entra em ~/geracoes/_custos.tsv (formato do kie.py, projeto = cliente) via custos.registrar_kie: é de lá que a aba Custos lê.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import secrets
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import broll_ia  # noqa: E402
import editor as _ed  # noqa: E402
from _comum import RAIZ, gravar_json, ler_json  # noqa: E402

CRED_USD = 0.005                 # 1 crédito da kie.ai = US$ 0,005 (o kie.py usa o mesmo número)
SALDO_URL = "https://api.kie.ai/api/v1/chat/credit"
TETO_USD = 2.0                   # um único pedido nunca passa disso (≈ R$ 11): proteção contra clique errado
ESTILO_PADRAO = ("Foto realista de fotojornalismo/documentário, vertical, luz natural, assunto bem claro e literal, "
                 "sem texto, sem logotipo, sem marca d'água, nada com cara de banco de imagem.")


def cotacao() -> float:
    """A cotação que a tela de Custos usa."""
    import custos
    return float(custos.COTACAO_PADRAO)


def pasta_gerados(p: Path) -> Path:
    return p / "editor" / "gerados"


def cliente_de(p: Path) -> str:
    """O cliente dono da pasta (clientes/<Nome>/...): é o 'projeto' do registro de custo."""
    try:
        partes = p.resolve().relative_to(RAIZ.resolve()).parts
    except ValueError:
        return "sem-cliente"
    return partes[1] if len(partes) > 1 and partes[0] == "clientes" else "sem-cliente"


def tem_gerar(p: Path) -> bool:
    """Só os formatos em que a imagem da cena se troca pelo material (hoje o Editorial) geram por aqui."""
    return bool(_ed.spec(p).get("gerar_ia", _ed.spec(p).get("material", True))) and not _ed.gravado(p)


# ───────────────────────── saldo, cardápio e orçamento (nada disso gasta) ─────────────────────────

def saldo() -> dict | None:
    """O saldo da kie.ai (leitura grátis). None = sem chave ou não respondeu."""
    if not broll_ia.configured():
        return None
    try:
        d = broll_ia.call("GET", SALDO_URL)
        cr = 0.0 if isinstance(d, dict) else float(d)
    except Exception:  # noqa: BLE001
        return None
    usd = cr * CRED_USD
    return {"creditos": cr, "usd": round(usd, 3), "brl": round(usd * cotacao(), 2)}


def _cena(p: Path, n: int) -> tuple[dict, dict]:
    doc = _ed._doc(p)
    cs = doc.get("cenas") or []
    if not 1 <= n <= len(cs):
        raise ValueError("Clique numa cena primeiro.")
    return doc, cs[n - 1]


def _imagem_da_cena(p: Path, cena: dict) -> Path | None:
    img = cena.get("imagem")
    if isinstance(img, str) and img and (p / img).is_file():
        return p / img
    return None


def ratio_do_video(doc: dict) -> str:
    w, h = float(doc.get("largura") or 1080), float(doc.get("altura") or 1920)
    return "9:16" if h > w * 1.2 else "16:9" if w > h * 1.2 else "1:1"


def prompt_sugerido(p: Path, n: int) -> str:
    """O texto já pronto: a fala da cena + o estilo do formato. O João edita antes de permitir."""
    fala = (_ed.cenas(p)[n - 1].get("fala") or "").strip()
    estilo = _ed.spec(p).get("prompt_ia") or ESTILO_PADRAO
    base = f"Cena de um vídeo curto cuja fala é: “{fala}”. Mostre isso de forma literal e específica. " if fala else ""
    return (base + estilo).strip()


def _nome_res(spec: dict) -> list[dict]:
    return [{"id": r, "usd": u} for r, u in spec["usd"].items()]


def cardapio(p: Path, n: int) -> dict:
    """Tudo que a caixa 'Gerar com IA' precisa pra abrir: modelos com preço, texto sugerido, imagem atual, saldo e cotação."""
    doc, cena = _cena(p, n)
    img = _imagem_da_cena(p, cena)
    return {
        "n": n, "cotacao": cotacao(), "ratio": ratio_do_video(doc), "prompt": prompt_sugerido(p, n),
        "configurado": broll_ia.configured(), "saldo": saldo(),
        "imagem_atual": _ed.rel(img) if img else "",
        "imagem": {"padrao": broll_ia.IMAGE_SUGERIDO, "modelos": [
            {"id": k, "nome": v["nome"], "nota": v["nota"], "resolucoes": _nome_res(v), "por_tarefa": v.get("por_tarefa", 1)}
            for k, v in broll_ia.MODELOS_IMAGEM.items()]},
        "video": {"padrao": broll_ia.VIDEO_SUGERIDO, "modelos": [
            {"id": k, "nome": v["nome"], "nota": v["nota"], "resolucoes": _nome_res(v), "duracoes": list(v["duracoes"])}
            for k, v in broll_ia.MODELOS_VIDEO.items()]},
    }


def orcar(p: Path, form: dict, exigir_prompt: bool = False) -> dict:
    """Quanto vai custar, sem gravar nem enviar nada. Levanta ValueError se o pedido não fecha."""
    try:
        n = int(form.get("n") or 0)
    except (TypeError, ValueError):
        n = 0
    doc, cena = _cena(p, n)
    tipo = form.get("tipo", "imagem")
    if tipo not in ("imagem", "video"):
        raise ValueError("Escolha imagem ou vídeo.")
    catalogo = broll_ia.MODELOS_IMAGEM if tipo == "imagem" else broll_ia.MODELOS_VIDEO
    modelo = form.get("modelo") if form.get("modelo") in catalogo else (
        broll_ia.IMAGE_SUGERIDO if tipo == "imagem" else broll_ia.VIDEO_SUGERIDO)
    spec = catalogo[modelo]
    res = form.get("resolucao")
    if res not in spec["usd"]:
        res = min(spec["usd"], key=spec["usd"].get) if tipo == "imagem" else ("720p" if "720p" in spec["usd"] else next(iter(spec["usd"])))
    prompt = (form.get("prompt") or "").strip()
    if exigir_prompt and not 10 <= len(prompt) <= (15000 if tipo == "imagem" else 4000):
        raise ValueError("Descreva o que gerar (mínimo 10 caracteres" + ("" if tipo == "imagem" else ", máximo 4.000") + ").")
    try:
        opcoes = int(form.get("opcoes") or (2 if tipo == "imagem" else 1))
    except (TypeError, ValueError):
        opcoes = 1
    opcoes = max(1, min(opcoes, 4 if tipo == "imagem" else 2))
    duracao = None
    if tipo == "video":
        try:
            duracao = int(form.get("duracao") or spec["duracoes"][0])
        except (TypeError, ValueError):
            duracao = 0
        if duracao not in spec["duracoes"]:
            duracao = spec["duracoes"][0]
        if not _imagem_da_cena(p, cena):
            raise ValueError("Esta cena não tem uma imagem pra animar. Ponha ou gere uma imagem nela primeiro.")
        por_tarefa = 1
        usd_tarefa = spec["usd"][res] * duracao
    else:
        por_tarefa = spec.get("por_tarefa", 1)
        usd_tarefa = spec["usd"][res]
    tarefas = math.ceil(opcoes / por_tarefa)
    usd = round(usd_tarefa * tarefas, 4)
    if usd > TETO_USD:
        raise ValueError(f"Pedido caro demais (US$ {usd:.2f}). O teto por pedido é US$ {TETO_USD:.2f}: peça menos opções.")
    cot = cotacao()
    return {"n": n, "tipo": tipo, "modelo": modelo, "nome": spec["nome"], "resolucao": res, "duracao": duracao, "prompt": prompt,
            "opcoes": tarefas * por_tarefa, "tarefas": tarefas, "por_tarefa": por_tarefa, "usd_tarefa": round(usd_tarefa, 4),
            "usd": usd, "brl": round(usd * cot, 2), "creditos": round(usd / CRED_USD, 2), "cotacao": cot,
            "ratio": ratio_do_video(doc), "preco_em": broll_ia.PRICE_DATE}


# ───────────────────────── registro (rascunho → permitido → gerando → pronto) ─────────────────────────

def _caminho(p: Path, ident: str) -> Path:
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", str(ident)):
        raise ValueError("Geração inválida.")
    return pasta_gerados(p) / f"{ident}.json"


def carregar(p: Path, ident: str) -> dict:
    f = _caminho(p, ident)
    if not f.is_file():
        raise ValueError("Geração não encontrada.")
    return json.loads(f.read_text(encoding="utf-8"))


def _salvar(p: Path, r: dict) -> None:
    gravar_json(_caminho(p, r["id"]), r)


@contextmanager
def _trava(p: Path):
    pasta_gerados(p).mkdir(parents=True, exist_ok=True)
    with (pasta_gerados(p) / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def publico(r: dict) -> dict:
    """O que a tela pode ver (sem o nonce nem o corpo do pedido)."""
    out = {k: v for k, v in r.items() if k not in ("nonce", "input")}
    out["arquivos"] = [a for t in r.get("tarefas", []) for a in t.get("arquivos", [])]
    return out


def rascunho(p: Path, form: dict) -> dict:
    """Congela o custo e devolve o nonce. NADA vai pra kie.ai aqui."""
    if not tem_gerar(p):
        raise ValueError("Este formato não gera imagem por aqui: peça pelo Claude.")
    o = orcar(p, form, exigir_prompt=True)
    doc, cena = _cena(p, o["n"])
    origem = _imagem_da_cena(p, cena) if o["tipo"] == "video" else None
    if o["tipo"] == "imagem":
        inp = broll_ia.entrada_imagem(o["modelo"], o["prompt"], o["ratio"], o["resolucao"])
    else:
        inp = broll_ia.entrada_video(o["modelo"], o["prompt"], o["ratio"], o["resolucao"], o["duracao"])
    r = {"id": uuid.uuid4().hex, "created": datetime.now(timezone.utc).isoformat(), "status": "rascunho",
         "nonce": secrets.token_urlsafe(32), "n": o["n"], "fala": (_ed.cenas(p)[o["n"] - 1].get("fala") or ""),
         "tipo": o["tipo"], "model": o["modelo"], "nome": o["nome"], "prompt": o["prompt"], "ratio": o["ratio"],
         "resolucao": o["resolucao"], "duracao": o["duracao"], "opcoes": o["opcoes"], "tarefas_n": o["tarefas"],
         "usd_estimado": o["usd"], "usd_tarefa": o["usd_tarefa"], "brl_estimado": o["brl"], "creditos_estimados": o["creditos"],
         "cotacao": o["cotacao"], "preco_em": o["preco_em"], "cliente": cliente_de(p), "sugestao": str(form.get("sugestao") or ""),
         "origem_imagem": _ed.rel(origem) if origem else "", "input": inp, "tarefas": []}
    _salvar(p, r)
    return dict(publico(r), nonce=r["nonce"])


def _iniciar(alvo, *args) -> None:
    threading.Thread(target=alvo, args=args, daemon=True).start()


def confirmar(p: Path, ident: str, nonce: str) -> dict:
    """O 'Permitir e gerar': só com o nonce do rascunho, só uma vez (clique duplo ou POST repetido não cobra duas vezes)."""
    broll_ia.key()   # sem chave configurada: falha antes de marcar qualquer envio
    with _trava(p):
        r = carregar(p, ident)
        if not secrets.compare_digest(r["nonce"], str(nonce)):
            raise ValueError("Permissão inválida. Abra a caixa de novo.")
        if r["status"] != "rascunho":
            return publico(r)
        s = saldo()
        if s is not None and s["creditos"] < r["creditos_estimados"]:
            raise ValueError(f"Saldo da kie.ai insuficiente ({s['creditos']:g} créditos; este pedido usa ~{r['creditos_estimados']:g}).")
        r.update(status="enviando", enviado_em=datetime.now(timezone.utc).isoformat())
        _salvar(p, r)
    _iniciar(_enviar, p, ident)
    return publico(r)


def _enviar(p: Path, ident: str) -> None:
    """Uma createTask por tarefa, cada uma UMA vez. Envio sem resposta confirmada = 'incerto' (pode ter cobrado), nunca reenvia."""
    try:
        r = carregar(p, ident)
        url = None
        if r["tipo"] == "video":
            try:
                url = broll_ia.upload(RAIZ / r["origem_imagem"])
            except Exception:  # noqa: BLE001
                with _trava(p):
                    r = carregar(p, ident)
                    r.update(status="falhou", erro="Não consegui mandar a imagem da cena pra kie.ai. Nada foi cobrado.")
                    _salvar(p, r)
                return
        for i in range(r["tarefas_n"]):
            inp = dict(r["input"])
            if url and r["model"].startswith("bytedance/seedance"):
                inp["first_frame_url"] = url
            elif url:
                inp["image_urls"] = [url]
            try:
                data = broll_ia.call("POST", broll_ia.BASE + "/createTask", {"model": r["model"], "input": inp})
                task = data.get("taskId")
                if not isinstance(task, str) or not task:
                    raise ValueError("sem taskId")
                t = {"status": "processando", "task_id": task, "arquivos": []}
            except Exception:  # noqa: BLE001
                t = {"status": "incerto", "arquivos": [],
                     "erro": "Não deu pra confirmar o envio. Confira na kie.ai antes de tentar de novo; pode haver cobrança. Nada foi reenviado."}
            with _trava(p):
                r = carregar(p, ident)
                r["tarefas"].append(t)
                r["status"] = "processando"
                _salvar(p, r)
        with _trava(p):
            r = carregar(p, ident)
            if not any(t["status"] == "processando" for t in r["tarefas"]):
                r["status"] = "incerto"
                r["erro"] = r["tarefas"][0].get("erro", "") if r["tarefas"] else "Envio sem confirmação."
            _salvar(p, r)
    except Exception:  # noqa: BLE001
        with _trava(p):
            r = carregar(p, ident)
            r.update(status="incerto", erro="Não foi possível confirmar o envio. Confira na kie.ai antes de tentar de novo; pode haver cobrança. Nada foi reenviado.")
            _salvar(p, r)


def _baixar(url: str, destino: Path) -> None:
    import shutil
    import urllib.request
    with urllib.request.urlopen(url, timeout=120) as resp, destino.open("wb") as out:
        shutil.copyfileobj(resp, out)
    if not destino.stat().st_size:
        raise ValueError("Arquivo vazio.")


def _quadros(mp4: Path, destino: Path) -> Path:
    """O vídeo gerado vira a pasta de quadros a 30 fps que o motor lê no 'quadros_de' (igual aos clipes). Devolve o 1º quadro."""
    destino.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                        "fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-q:v", "3",
                        str(destino / "%04d.jpg")], capture_output=True, text=True)
    primeiro = destino / "0001.jpg"
    if r.returncode or not primeiro.is_file():
        raise ValueError("Não consegui abrir o vídeo gerado.")
    return primeiro


def _guardar_resultado(p: Path, r: dict, k: int, url: str) -> dict:
    """Baixa a opção k. Imagem vira JPG; vídeo vira .mp4 + pasta de quadros."""
    d = pasta_gerados(p)
    if r["tipo"] == "imagem":
        from PIL import Image
        bruto = d / f"{r['id']}-{k}.download"
        _baixar(url, bruto)
        dest = d / f"{r['id']}-{k}.jpg"
        with Image.open(bruto) as im:
            im.convert("RGB").save(dest, format="JPEG", quality=92)
        bruto.unlink(missing_ok=True)
        return {"arquivo": str(dest.relative_to(p)), "mini": _ed.rel(dest), "campo": "imagem"}
    mp4 = d / f"{r['id']}-{k}.mp4"
    _baixar(url, mp4)
    pasta_q = d / f"{r['id']}-{k}-quadros"
    primeiro = _quadros(mp4, pasta_q)
    return {"arquivo": str(pasta_q.relative_to(p)), "mini": _ed.rel(primeiro),
            "campo": "quadros_de", "video": _ed.rel(mp4)}


def _registrar_custo(p: Path, r: dict, t: dict, status: str, creditos: float) -> None:
    import custos
    arq = (t.get("arquivos") or [{}])[0].get("mini", "")
    custos.registrar_kie(r["cliente"], r["model"], r["tipo"], creditos, status, t.get("task_id", ""),
                         str(RAIZ / arq) if arq else "", f"Estúdio · editar vídeo · cena {r['n']}: {r['prompt']}")
    t["registrado"] = True


def atualizar(p: Path, ident: str) -> dict:
    """Consulta as tarefas já enviadas (nunca cria tarefa nova), baixa o que ficou pronto e registra o gasto uma única vez."""
    from urllib.parse import urlencode
    with _trava(p):
        r = carregar(p, ident)
        if r["status"] != "processando":
            return publico(r)
        k = sum(len(t.get("arquivos", [])) for t in r["tarefas"])
        for t in r["tarefas"]:
            if t["status"] != "processando":
                continue
            try:
                data = broll_ia.call("GET", broll_ia.BASE + "/recordInfo?" + urlencode({"taskId": t["task_id"]}))
            except Exception:  # noqa: BLE001
                continue   # a consulta falhou agora: tenta de novo no próximo toque (isso não cria tarefa)
            estado = data.get("state")
            real = data.get("creditsConsumed")
            if estado == "fail":
                t.update(status="falhou", erro="A geração falhou na kie.ai.")
                if not t.get("registrado"):
                    _registrar_custo(p, r, t, "falhou", float(real or 0))
            elif estado == "success":
                res = data.get("resultJson") or {}
                if isinstance(res, str):
                    res = json.loads(res)
                urls = res.get("resultUrls") or res.get("result_urls") or []
                if isinstance(urls, str):
                    urls = [urls]
                urls = [u for u in urls if isinstance(u, str) and u.startswith("https://")]
                if not urls:
                    continue
                try:
                    for u in urls:
                        k += 1
                        t["arquivos"].append(_guardar_resultado(p, r, k, u))
                except Exception as e:  # noqa: BLE001
                    t.update(status="falhou", erro="Gerou, mas não consegui baixar: " + str(e)[:120])
                else:
                    t["status"] = "pronto"
                if not t.get("registrado"):
                    _registrar_custo(p, r, t, "ok", float(real) if real is not None else r["usd_tarefa"] / CRED_USD)
                    t["creditos_reais"] = float(real) if real is not None else None
        if not any(t["status"] == "processando" for t in r["tarefas"]):
            r["status"] = "pronto" if any(t.get("arquivos") for t in r["tarefas"]) else (
                "falhou" if any(t["status"] == "falhou" for t in r["tarefas"]) else "incerto")
            if r["status"] != "pronto":
                r["erro"] = next((t.get("erro") for t in r["tarefas"] if t.get("erro")), "Não saiu nenhuma opção.")
        _salvar(p, r)
        return publico(r)


def lista(p: Path) -> list[dict]:
    """As gerações deste vídeo (mais novas primeiro), sem o rascunho que ninguém permitiu."""
    out = []
    for f in pasta_gerados(p).glob("*.json"):
        r = ler_json(f, None)
        if isinstance(r, dict) and r.get("status") not in (None, "rascunho"):
            out.append(publico(r))
    return sorted(out, key=lambda r: r["created"], reverse=True)


def itens(p: Path) -> list[dict]:
    """O que o painel 'Material' mostra do que já foi gerado (mesmo formato dos outros itens do editor.material)."""
    out = []
    for r in lista(p):
        for a in r["arquivos"]:
            out.append({"arquivo": a["arquivo"], "mini": a["mini"], "campo": a["campo"],
                        "origem": f"IA · {r['nome']} · {r['prompt'][:90]}"})
    return out


# ───────────────────────── sugestão do Claude: "não achei imagem pra esta cena" ─────────────────────────
# O Claude do editor não gera nada. Quando falta imagem boa, escreve editor/sugestao_ia.json; o Estúdio mostra o cartão com o custo
# e só o clique do João gera.

def _sid(n: int, o_que: str) -> str:
    return hashlib.sha1(f"{n}|{o_que}".encode("utf-8")).hexdigest()[:10]


def sugestoes(p: Path) -> list[dict]:
    if not tem_gerar(p):
        return []
    bruto = ler_json(p / "editor" / "sugestao_ia.json", [])
    if isinstance(bruto, dict):
        bruto = bruto.get("sugestoes") or []
    if not isinstance(bruto, list):
        return []
    feitas = {r.get("sugestao") for r in lista(p) if r.get("sugestao")}
    dispensadas = set(ler_json(p / "editor" / "sugestao_ia.dispensadas.json", []) or [])
    nc = len(_ed._doc(p).get("cenas") or [])
    out = []
    for s in bruto[:6]:
        if not isinstance(s, dict):
            continue
        try:
            n = int(s.get("n"))
        except (TypeError, ValueError):
            continue
        o_que = str(s.get("o_que") or "").strip()
        sid = _sid(n, o_que)
        if not 1 <= n <= nc or len(o_que) < 10 or sid in feitas or sid in dispensadas:
            continue
        try:
            orc = orcar(p, {"n": n, "tipo": "imagem", "prompt": o_que, "opcoes": 2,
                            "modelo": s.get("modelo") if s.get("modelo") in broll_ia.MODELOS_IMAGEM else broll_ia.IMAGE_SUGERIDO})
        except ValueError:
            continue
        out.append({"id": sid, "n": n, "o_que": o_que, "motivo": str(s.get("motivo") or "")[:200], "modelo": orc["modelo"],
                    "nome": orc["nome"], "opcoes": orc["opcoes"], "usd": orc["usd"], "brl": orc["brl"]})
    return out


def dispensar(p: Path, sid: str) -> None:
    f = p / "editor" / "sugestao_ia.dispensadas.json"
    d = list(ler_json(f, []) or [])
    if sid not in d:
        d.append(sid)
    gravar_json(f, d)


if __name__ == "__main__":
    print("Use pela tela: Editar vídeo → Gerar com IA.", file=sys.stderr)
