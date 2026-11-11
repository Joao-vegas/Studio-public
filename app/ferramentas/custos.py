#!/usr/bin/env python3
"""
custos — quanto custou, separado em três gavetas: ASSINATURA (já pago, valor fixo), GRÁTIS e PAGO DE VERDADE.

Fontes (só leitura, nada é inventado):
    app/custos/execucoes.jsonl          cada execução de IA do Estúdio (ia.executar grava o valor equivalente na API)
    app/custos/api.jsonl                Claude cobrado da API (crédito do Console): pago de verdade, por fila/tarefa
    app/custos/videos.jsonl             livro de vídeos: projeto → versões (em produção ou pronta)
    app/custos/gemini_uso.jsonl         qual chave do Gemini atendeu cada pedido de voz (prova de conta paga x cota grátis)
    app/custos/arquivo/AAAA-MM.jsonl    arquivo morto: livros guardam só 60 dias, o resto vem pra cá (nada é apagado)
    ~/geracoes/_custos.tsv              imagem e vídeo por IA (kie.ai, skill gerador-imagem-video)
    Cerebro/custos/scripts/<ferramenta>  rastreador do Cérebro (voz Gemini e outras chamadas de API)
    app/custos/assinaturas.json         planos mensais que o João paga (editável na tela Custos)

Claude Code e Codex rodam na assinatura: o valor mostrado "equivale a US$ X" na API, mas já está incluso na assinatura.
"""
from __future__ import annotations

import csv
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import ESTUDIO, agora, append_jsonl, ensure, gravar_json, ler_json, ler_jsonl, rel

PASTA = ESTUDIO / "custos"
LIVRO = PASTA / "execucoes.jsonl"
VIDEOS = PASTA / "videos.jsonl"   # livro de vídeos: uma linha por versão (em produção ou pronta)
API_LIVRO = PASTA / "api.jsonl"   # Claude pela API: via_api.py (filas) e ia.executar (cobrança 'api') gravam aqui
GEMINI_USO = PASTA / "gemini_uso.jsonl"   # qual chave do Gemini atendeu cada pedido (gravado por motion/gemini.py)
ARQUIVO = PASTA / "arquivo"       # arquivo morto: o que passa de 60 dias sai dos livros e vem pra cá (nada é apagado)
DIAS_LIVRO = 60
ASSINATURAS = PASTA / "assinaturas.json"
KIE_TSV = Path.home() / "geracoes" / "_custos.tsv"
CEREBRO = Path("/Users/joaomarcospiki/Cerebro")
PRECOS = CEREBRO / "custos" / "precos.json"   # tabela padrão de preços (cada preço com fonte e data de conferência)
FORMATOS = ESTUDIO.parent / "formatos"
TRACKER = CEREBRO / "custos" / "scripts"
FERRAMENTAS_TRACKER = ("motion", "motion-design", "estudio", "dialogo-3d")   # dialogo-3d: histórico (o livro antigo ainda tem linhas dele)
COTACAO_PADRAO = 5.4
# Chaves do Gemini (app/.env), segundo o comentário de app/ferramentas/motion/gemini.py: "6 = conta paga (01-out); as grátis (1..5)".
# A chave 7 não tem nenhuma anotação de plano: pedido atendido por ela, ou sem anotação de chave, fica "estimado" (não confirmado).
CHAVES_GEMINI = {**{f"chave {i}": "gratis" for i in range(1, 6)}, "chave 6": "pago"}
AO_VIVO = "em produção"
VIVO_MAX_HORAS = 24   # "em produção" sem novidade há mais que isso aparece como "interrompido"

ASSINATURAS_PADRAO = [
    {"nome": "Claude", "plano": "", "valor": 0, "moeda": "USD", "cobre": "Produção e ajustes (Claude Code)"},
    {"nome": "ChatGPT", "plano": "", "valor": 0, "moeda": "USD", "cobre": "Imagens no ChatGPT e GPT/Codex"},
    {"nome": "ElevenLabs", "plano": "", "valor": 0, "moeda": "USD", "cobre": "Voz clonada e transcrição (quando ligar)"},
]

GRATIS_LOCAL = [
    ("ffmpeg", "corta, junta, cor e áudio"),
    ("Motor HTML do Estúdio", "Motion narrado, Documentário"),
    ("HyperFrames", "HTML vira vídeo (Apache 2.0)"),
    ("Remotion", "grátis até 3 pessoas na empresa"),
    ("VoiceStudio (voz local)", "narração dos vídeos por roteiro; reserva ElevenLabs (só com chave e voz)"),
    ("Corte do Estúdio + auto-editor", "silêncio, gaguejo, take repetido"),
    ("Transcrição local (Whisper no Mac)", "tempo por palavra"),
    ("Pexels, Pixabay, Wikimedia, NASA", "b-roll com chave grátis"),
]


def registrar_execucao(sel: dict, usd, tokens, log) -> None:
    if usd is None:
        return
    prov = (sel or {}).get("provedor", "claude")
    if (sel or {}).get("cobranca") == "api" and prov == "claude":   # veio do crédito, não da assinatura
        append_jsonl(API_LIVRO, {"quando": agora(), "fila": "Estúdio", "tarefa": _projeto_do_log(rel(Path(log)) if log else ""),
                                 "modelo": (sel or {}).get("modelo", ""), "usd": float(usd), "estado": "ok"})
        return
    append_jsonl(LIVRO, {"data": agora(), "provedor": prov, "modelo": (sel or {}).get("modelo", ""),
                         "usd": float(usd), "tokens": tokens or {}, "onde": rel(Path(log)) if log else ""})


def assinaturas() -> list[dict]:
    return ler_json(ASSINATURAS, None) or [dict(a) for a in ASSINATURAS_PADRAO]


def salvar_assinaturas(lista: list[dict]) -> None:
    ensure(PASTA)
    limpo = []
    for a in lista:
        nome = str(a.get("nome", "")).strip()
        if not nome:
            continue
        try:
            valor = float(str(a.get("valor") or 0).replace(",", "."))
        except ValueError:
            valor = 0.0
        limpo.append({"nome": nome[:40], "plano": str(a.get("plano", "")).strip()[:40], "valor": valor,
                      "moeda": "BRL" if a.get("moeda") == "BRL" else "USD", "cobre": str(a.get("cobre", "")).strip()[:90]})
    gravar_json(ASSINATURAS, limpo)


def _data(txt: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt.strip()[:len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    return None


def _do_estudio() -> list[dict]:
    out = []
    for r in ler_jsonl(LIVRO):
        d = _data(r.get("data", ""))
        if not d:
            continue
        prov = r.get("provedor", "claude")
        out.append({"data": d, "gaveta": "assinatura", "servico": "Claude Code" if prov == "claude" else "GPT · Codex",
                    "oque": "Produção, análise ou ajuste de vídeo", "projeto": _projeto_do_log(r.get("onde", "")),
                    "usd": float(r.get("usd") or 0)})
    return out


def _da_api() -> list[dict]:
    """Gastos do Claude pela API: pago de verdade. Fila 'Estúdio' = vídeos feitos pela tela; outras = tarefas em lote."""
    out = []
    for r in ler_jsonl(API_LIVRO):
        d = _data(r.get("quando", ""))
        if not d:
            continue
        fila, tarefa = r.get("fila") or "Estúdio", r.get("tarefa") or "-"
        out.append({"data": d, "gaveta": "pago", "servico": "Claude pela API", "oque": f"{fila} · {tarefa}", "projeto": tarefa,
                    "usd": float(r.get("usd") or 0), "fila": fila, "tarefa": tarefa, "api": True})
    return out


def api_por_tarefa(linhas: list[dict]) -> list[dict]:
    """Soma o gasto da API por fila e tarefa, do maior pro menor."""
    g: dict = {}
    for l in linhas:
        if l.get("api"):
            x = g.setdefault((l["fila"], l["tarefa"]), {"fila": l["fila"], "tarefa": l["tarefa"], "usd": 0.0, "n": 0})
            x["usd"] += l["usd"]; x["n"] += 1
    return sorted(g.values(), key=lambda x: -x["usd"])


def _projeto_do_log(onde: str) -> str:
    partes = Path(onde).parts
    if len(partes) > 3 and partes[0] == "app" and partes[1] == "jobs":
        return partes[2]
    if "cortes" in partes:
        return "Corte"
    if "estudos" in partes:
        return "Referência"
    return "Estúdio"


def _da_kie(ini: datetime | None = None) -> list[dict]:
    out = []
    if not KIE_TSV.exists():
        return out
    with KIE_TSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            d = _data(r.get("data", ""))
            if not d or (ini and d < ini) or (r.get("status") or "ok") not in ("ok", ""):
                continue
            try:
                usd = float(r.get("usd") or 0)
            except ValueError:
                continue
            out.append({"data": d, "gaveta": "pago", "servico": "Imagens/vídeo por IA (kie.ai)",
                        "oque": f"{r.get('tipo', '')} · {r.get('modelo', '')}".strip(" ·"),
                        "projeto": r.get("projeto", ""), "usd": usd})
    return out


def registrar_kie(projeto: str, modelo: str, tipo: str, creditos: float, status: str, task: str = "", arquivo: str = "",
                  descricao: str = "") -> None:
    """Uma linha em ~/geracoes/_custos.tsv no mesmo formato do kie.py (1 crédito = US$ 0,005): é daí que a aba Custos lê o gasto da kie.ai.
    Nunca derruba a geração: erro de escrita só vira aviso."""
    try:
        KIE_TSV.parent.mkdir(parents=True, exist_ok=True)
        novo = not KIE_TSV.exists()
        with KIE_TSV.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            if novo:
                w.writerow(["data", "projeto", "modelo", "tipo", "creditos", "usd", "status", "taskId", "arquivo", "descricao"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), projeto or "sem-projeto", modelo, tipo, f"{float(creditos):g}",
                        f"{float(creditos) * 0.005:.4f}", status, task, arquivo.replace(str(Path.home()), "~"), " ".join(descricao.split())[:120]])
    except Exception as e:  # noqa: BLE001
        print(f"aviso: não consegui registrar o custo da kie.ai ({e})", file=sys.stderr)


def _preco_modelo(provedor: str, modelo: str) -> dict | None:
    """Linha do modelo na tabela de preços (precos.json), casando pelo começo do nome. None = modelo fora da tabela."""
    tab = (ler_json(PRECOS, {}) or {}).get(provedor, {})
    if modelo in tab:
        return tab[modelo]
    achou = [k for k in tab if not k.startswith("_") and modelo.startswith(k)]
    return tab[max(achou, key=len)] if achou else None


def _usd_tts_estimado(r: dict) -> float:
    """Voz Gemini: tokens x preço oficial do modelo (tabela precos.json). 0 se o preço não foi confirmado."""
    p = _preco_modelo("gemini", r.get("modelo") or "")
    if not p or p.get("nao_achado"):
        return 0.0
    try:
        return round(int(r.get("prompt_tokens") or 0) * p["input_per_1m"] / 1e6 + int(r.get("completion_tokens") or 0) * p["output_per_1m"] / 1e6, 4)
    except (ValueError, KeyError):
        return 0.0


def _sem_preco(provedor: str, modelo: str) -> bool:
    p = _preco_modelo(provedor, modelo or "")
    return not p or bool(p.get("nao_achado"))


def _indice_chaves_gemini(ini: datetime | None) -> dict:
    """{(entrada, saída): [[quando, chave], ...]} dos pedidos que gemini.py anotou, pra casar com o rastreador do Cérebro."""
    idx: dict = {}
    for r in _ler_livro(GEMINI_USO, "gemini_uso", ini):
        d = _data(r.get("data", ""))
        if d:
            idx.setdefault((int(r.get("entrada") or 0), int(r.get("saida") or 0)), []).append([d, r.get("chave", "")])
    return idx


def _chave_do_pedido(idx: dict, d: datetime, ent: int, sai: int) -> str:
    """Chave que atendeu o pedido (casa por tokens e horário, ±2,5 min; cada anotação casa uma vez só). '' = sem anotação."""
    cands = idx.get((ent, sai), [])
    melhor = min(cands, key=lambda c: abs((d - c[0]).total_seconds()), default=None)
    if melhor and abs((d - melhor[0]).total_seconds()) <= 150:
        cands.remove(melhor)
        return melhor[1]
    return ""


def _do_cerebro(ini: datetime | None = None) -> list[dict]:
    out = []
    try:
        if str(CEREBRO / "scripts") not in sys.path:
            sys.path.append(str(CEREBRO / "scripts"))
        from custos_tracker.tracker import _parse_log_row
    except Exception:
        return out
    idx = _indice_chaves_gemini(ini)
    brutas = []
    for ferramenta in FERRAMENTAS_TRACKER:
        pasta = TRACKER / ferramenta
        if not pasta.is_dir():
            continue
        for md in pasta.glob("*.md"):
            for linha in md.read_text(encoding="utf-8").splitlines():
                r = _parse_log_row(linha)
                if not r:
                    continue
                d = _data(f"{r['data']} {r.get('hora', '')}".strip()) or _data(r["data"])
                if d and (not ini or d >= ini):
                    brutas.append((d, ferramenta, md, r))
    for d, ferramenta, md, r in sorted(brutas, key=lambda x: x[0]):
        api = (r.get("api") or "").lower()
        ent, sai = int(r.get("prompt_tokens") or 0), int(r.get("completion_tokens") or 0)
        usd = float(r["usd"])
        alvo = (r.get("alvo") or "").strip()
        base = {"data": d, "oque": f"{md.stem.replace('_', ' ')} · {r.get('modelo', '')}".strip(" ·"),
                "projeto": alvo if alvo not in ("", "-") else f"Sem projeto · {ferramenta}", "ent": ent, "sai": sai,
                "sem_preco": api in ("gemini", "anthropic", "claude") and _sem_preco("gemini" if api == "gemini" else "anthropic", r.get("modelo") or "")}
        if api == "gemini":
            voz = "tts" in (r.get("modelo") or "")
            if not usd and voz:
                usd = _usd_tts_estimado(r)   # o preço do TTS foi cadastrado depois: estima pelos tokens
            chave = _chave_do_pedido(idx, d, ent, sai)
            plano = CHAVES_GEMINI.get(chave, "")
            nome = "Voz Gemini" if voz else "Gemini (análise)"
            if plano == "gratis" or not usd:
                out.append({**base, "gaveta": "gratis", "servico": f"{nome} (cota grátis)", "usd": 0.0, "chave": chave})
            elif plano == "pago":
                out.append({**base, "gaveta": "pago", "servico": f"{nome} (conta paga)", "usd": usd, "chave": chave, "preco_estimado": True})
            else:
                out.append({**base, "gaveta": "estimado", "servico": f"{nome} (cobrança não confirmada)", "usd": usd, "chave": chave})
            continue
        gaveta = ("gratis" if api == "groq" or usd == 0 else "assinatura" if api in ("anthropic", "claude") else "pago")
        servico = {"groq": "Groq (transcrição)", "openai": "OpenAI", "elevenlabs": "ElevenLabs"}.get(api, api or md.stem)
        out.append({**base, "gaveta": gaveta, "servico": servico, "usd": usd})
    return out


def periodo_inicio(periodo: str, de: str = "", ate: str = "") -> tuple[datetime | None, datetime | None, str]:
    hoje = datetime.now()
    zero = hoje.replace(hour=0, minute=0, second=0, microsecond=0)
    ini_mes = zero.replace(day=1)
    if periodo == "datas" and de:
        a = _data(de); b = _data(ate) if ate else None
        if a:
            fim = (b + timedelta(days=1)) if b else None
            return a, fim, a.strftime("%d/%m") + (" a " + b.strftime("%d/%m/%Y") if b else " em diante")
    if periodo == "hoje":
        return zero, None, "hoje"
    if periodo == "ontem":
        return zero - timedelta(days=1), zero, "ontem"
    if periodo == "7d":
        return zero - timedelta(days=6), None, "últimos 7 dias"
    if periodo == "mes-passado":
        ini = (ini_mes - timedelta(days=1)).replace(day=1)
        return ini, ini_mes, ini.strftime("%m/%Y")
    if periodo == "30d":
        return hoje - timedelta(days=30), None, "últimos 30 dias"
    if periodo == "tudo":
        return None, None, "desde o começo"
    return ini_mes, None, hoje.strftime("%m/%Y")


# ───────────────────────── 60 dias nos livros; o resto vai pro arquivo morto ─────────────────────────

def _ler_livro(caminho: Path, nome: str, ini: datetime | None) -> list[dict]:
    """Linhas do livro. O arquivo morto só é aberto quando o período pedido começa antes do limite de 60 dias."""
    linhas = ler_jsonl(caminho)
    if ini is None or ini < datetime.now() - timedelta(days=DIAS_LIVRO):
        for a in sorted(ARQUIVO.glob("????-??.jsonl")) if ARQUIVO.is_dir() else []:
            try:
                mes = datetime.strptime(a.stem, "%Y-%m")
            except ValueError:
                continue
            if ini and (mes.replace(year=mes.year + (mes.month == 12), month=mes.month % 12 + 1)) <= ini:
                continue   # mês inteiro antes do período pedido
            linhas += [r for r in ler_jsonl(a) if r.get("_livro") == nome]
    return linhas


def podar(forcar: bool = False) -> int:
    """Livros e caches guardam no máximo 60 dias: o mais velho vai pro arquivo morto (app/custos/arquivo), nada é apagado.
    Roda no máximo 1x por hora. Devolve quantas linhas/arquivos foram pro arquivo."""
    marca = ARQUIVO / ".ultima"
    if not forcar and marca.exists() and time.time() - marca.stat().st_mtime < 3600:
        return 0
    limite = datetime.now() - timedelta(days=DIAS_LIVRO)
    movidas = 0
    for caminho, nome in ((LIVRO, "execucoes"), (VIDEOS, "videos"), (GEMINI_USO, "gemini_uso")):
        with _trava():
            linhas = ler_jsonl(caminho)
            velhas = [l for l in linhas if (_data(l.get("data", "")) or datetime.now()) < limite]
            if not velhas:
                continue
            for l in velhas:
                mes = (_data(l.get("data", "")) or limite).strftime("%Y-%m")
                append_jsonl(ARQUIVO / f"{mes}.jsonl", {**l, "_livro": nome})
            ficam = [l for l in linhas if l not in velhas]
            caminho.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in ficam), encoding="utf-8")
            movidas += len(velhas)
    corte = time.time() - DIAS_LIVRO * 86400
    for pasta, sub in ((CACHE_CCUSAGE, "cache"), (PASTA / "_marcas", "marcas")):
        for f in pasta.glob("*.json") if pasta.is_dir() else []:
            if f.stat().st_mtime < corte:
                ensure(ARQUIVO / sub)
                shutil.move(str(f), str(ARQUIVO / sub / f.name))
                movidas += 1
    ensure(ARQUIVO)
    marca.touch()
    return movidas


@contextmanager
def _trava():
    """Trava de arquivo: runner, episodio.py e a página não gravam o livro ao mesmo tempo."""
    ensure(PASTA)
    with (PASTA / ".livro.lock").open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


PROJETOS_CLAUDE = Path.home() / ".claude" / "projects"
PASTAS_CLAUDE_ESTUDIO = ("Skill-Est-dio", "producao-reels", "Motion-design")   # nomes antigos e atual do Estúdio
CACHE_CCUSAGE = ESTUDIO / ".cache"
CACHE_MIN = 10


def _sessoes_do_estudio() -> set[str]:
    ids = set()
    if PROJETOS_CLAUDE.is_dir():
        for d in PROJETOS_CLAUDE.iterdir():
            if d.is_dir() and any(k in d.name for k in PASTAS_CLAUDE_ESTUDIO):
                ids.update(f.stem for f in d.glob("*.jsonl"))
    return ids


_ccusage_fazendo: set[str] = set()


def _atualizar_ccusage(args: list[str], cache: Path) -> None:
    """Roda o ccusage (npx, rede) numa thread de fundo e grava o cache; uma por vez por consulta."""
    import threading
    k = str(cache)
    if k in _ccusage_fazendo:
        return
    _ccusage_fazendo.add(k)

    def _vai():
        try:
            r = subprocess.run(["npx", "--yes", "ccusage@latest", *args], capture_output=True, text=True, timeout=120)
            bruto = json.loads(r.stdout)
            ensure(CACHE_CCUSAGE)
            cache.write_text(json.dumps(bruto), encoding="utf-8")
        except Exception as e:  # noqa: BLE001 — sem rede/ccusage: fica o cache velho
            print(f"(ccusage não atualizou: {e})", file=sys.stderr)
        finally:
            _ccusage_fazendo.discard(k)
    threading.Thread(target=_vai, daemon=True, name="ccusage").start()


def claude_code_conversas(ini: datetime | None, fim: datetime | None) -> dict:
    """Conversas do Claude Code no terminal (ccusage), só as deste projeto. Valor equivalente na API; cache de 10 min.
    Devolve {"n", "usd", "erro"}; se o ccusage falhar, erro vem preenchido e a página segue."""
    args = ["session", "--json"]
    if ini:
        args += ["--since", ini.strftime("%Y%m%d")]
    if fim:
        args += ["--until", (fim - timedelta(seconds=1)).strftime("%Y%m%d")]
    chave = "_".join(a for a in args[2:]) or "tudo"
    cache = CACHE_CCUSAGE / f"ccusage_{chave}.json"
    try:
        if cache.exists():
            bruto = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - cache.stat().st_mtime >= CACHE_MIN * 60:
                _atualizar_ccusage(args, cache)   # velho: mostra o que tem e atualiza em segundo plano (a tela nunca espera o npx/rede)
        else:
            _atualizar_ccusage(args, cache)
            return {"n": 0, "usd": 0.0, "erro": "preparando…"}   # 1ª vez: o npx leva uns segundos; a tela abre já
        meus = _sessoes_do_estudio()
        sess = [s for s in bruto.get("session", []) if s.get("agent", "claude") == "claude" and s.get("period") in meus]
        return {"n": len(sess), "usd": sum(float(s.get("totalCost") or 0) for s in sess), "erro": ""}
    except Exception as e:  # ccusage ausente, sem rede, JSON quebrado: a tela não pode cair por isso
        return {"n": 0, "usd": 0.0, "erro": str(e)[:80] or "falhou"}


# ───────────────────────── textos em linguagem simples ─────────────────────────

def _mi(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}".replace(".", ",") + " mi"
    if n >= 1000:
        return f"{n / 1e3:.1f}".replace(".", ",") + " mil"
    return str(n)


def _us(x: float) -> str:
    x = float(x or 0)
    return "US$ " + (f"{x:.2f}" if x >= 0.1 else f"{x:.3f}" if x >= 0.01 else f"{x:.4f}").replace(".", ",")


def _texto_claude(t: dict, usd: float, modelos: str = "", ao_vivo: bool = False, api: bool = False) -> str:
    total = sum(int(t.get(k) or 0) for k in ("entrada", "saida", "cache_criado", "cache_lido"))
    if not total:
        return "medindo… (atualiza a cada rodada)" if ao_vivo else "não medido separado: a conversa também construiu o formato"
    return (f"{_mi(total)} tokens (entrada {_mi(t.get('entrada'))}, saída {_mi(t.get('saida'))}, "
            f"memória gravada {_mi(t.get('cache_criado'))}, memória relida {_mi(t.get('cache_lido'))}) · "
            + (f"{_us(usd)} · cobrado do crédito da API" if api else f"equivale a {_us(usd)} · já incluso na sua assinatura")
            + (f" · {modelos}" if modelos else ""))


def _itens_de(linhas: list[dict]) -> list[dict]:
    """Junta as linhas de gasto (voz, imagens...) em itens por serviço, com a frase pronta em linguagem simples."""
    grupos: dict = {}
    for l in linhas:
        g = grupos.setdefault(l["servico"], {"gaveta": l["gaveta"], "usd": 0.0, "n": 0, "ent": 0, "sai": 0, "estimado_preco": False, "sem_preco": False})
        g["sem_preco"] = g["sem_preco"] or bool(l.get("sem_preco"))
        g["usd"] += l["usd"]; g["n"] += 1; g["ent"] += l.get("ent", 0); g["sai"] += l.get("sai", 0)
        g["estimado_preco"] = g["estimado_preco"] or bool(l.get("preco_estimado"))
    itens = []
    for servico, g in grupos.items():
        n = g["n"]
        txt = f"{n} pedido{'s' if n != 1 else ''}"
        if g["ent"] + g["sai"]:
            txt += f" · {_mi(g['ent'] + g['sai'])} tokens (entrada {_mi(g['ent'])}, saída {_mi(g['sai'])})"
        if g["gaveta"] == "gratis":
            tipo, txt = "gratis", txt + " · grátis"
        elif g["gaveta"] == "estimado":
            tipo, txt = "estimado", txt + f" · {_us(g['usd'])} estimado: não dá pra confirmar se o Google cobrou"
        else:
            tipo = "pago"
            txt += f" · {_us(g['usd'])}" + (" (conta pelo preço oficial do Gemini; a conta é paga)" if g["estimado_preco"] else "")
        if g["sem_preco"] and g["gaveta"] != "gratis":
            txt += " · preço não confirmado"
        itens.append({"servico": servico, "tipo": tipo, "usd": round(g["usd"], 4), "detalhe": txt})
    return itens


def itens_do_intervalo(de: datetime, ate: datetime, linhas: list[dict] | None = None) -> list[dict]:
    """Voz, imagens/vídeo por IA (kie.ai) e outros gastos entre dois momentos, mais o render (grátis)."""
    ini, fim = de - timedelta(minutes=1), ate + timedelta(minutes=1)
    if linhas is None:
        linhas = _do_cerebro(ini) + _da_kie(ini)
    itens = _itens_de([l for l in linhas if ini <= l["data"] <= fim and l["gaveta"] != "assinatura"])
    itens.append({"servico": "Render", "tipo": "gratis", "usd": 0.0, "detalhe": "grátis (no seu Mac)"})
    return itens


def _somas(itens: list[dict]) -> dict:
    return {"tabela_usd": round(sum(i["usd"] for i in itens if i["tipo"] == "assinatura"), 2),
            "pago_usd": round(sum(i["usd"] for i in itens if i["tipo"] == "pago"), 4),
            "estimado_usd": round(sum(i["usd"] for i in itens if i["tipo"] == "estimado"), 4)}


# ───────────────────────── livro de vídeos (por projeto e versão) ─────────────────────────

def registrar_video(projeto: str, slug: str, cliente: str, formato: str, itens: list[dict], arquivo: str = "",
                    nota: str = "", data: str = "", chave: str = "", status: str = "pronto") -> dict:
    """Grava uma versão no livro (status "em produção" enquanto é feita, "pronto" no fim). A versão (V1, V2...) é automática, por slug.
    `chave` identifica a medição (o início): gravar de novo com a mesma chave substitui a linha, não duplica."""
    with _trava():
        linhas = ler_jsonl(VIDEOS)
        mesma = next((i for i, l in enumerate(linhas) if chave and l.get("slug") == slug and l.get("chave") == chave), None)
        if mesma is not None:
            versao = linhas[mesma]["versao"]
        else:
            versao = f"V{sum(1 for l in _ler_livro(VIDEOS, 'videos', None) if l.get('slug') == slug) + 1}"
        reg = {"projeto": projeto, "slug": slug, "cliente": cliente, "formato": formato, "versao": versao, "status": status,
               "data": data or agora(), "arquivo": arquivo, **_somas(itens), "itens": itens, "nota": nota, "chave": chave, "de": chave}
        if mesma is not None:
            linhas[mesma] = reg
            tmp = VIDEOS.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas), encoding="utf-8")
            os.replace(tmp, VIDEOS)
        else:
            append_jsonl(VIDEOS, reg)
    return reg



def registrar_video_job(job: dict, status: str = "pronto") -> dict | None:
    """Job do app (runner.py): cria a linha quando o job começa ("em produção"), atualiza a cada execução e fecha no fim."""
    vivo = status == AO_VIVO
    anteriores = [l for l in ler_jsonl(VIDEOS) if l.get("slug") == job["slug"] and l.get("cliente") == job["cliente"]
                  and l.get("status", "pronto") == "pronto"]
    corte = anteriores[-1]["data"] if anteriores else ""
    execs = [e for e in job.get("execucoes", []) if e.get("inicio", "") > corte and (e.get("fim") or vivo)]
    if not execs:
        return None
    itens, por_prov = [], {}
    for e in execs:
        prov = (e.get("ia") or {}).get("provedor", "claude")
        if prov == "claude" and (e.get("ia") or {}).get("cobranca") == "api":
            prov = "claude-api"
        g = por_prov.setdefault(prov, {"usd": 0.0, "n": 0, "tok": {"entrada": 0, "saida": 0, "cache_criado": 0, "cache_lido": 0}})
        g["usd"] += float(e.get("custo_usd") or 0); g["n"] += 1
        tk = e.get("tokens") or {}
        for k, o in (("entrada", "input_tokens"), ("saida", "output_tokens"), ("cache_criado", "cache_creation_input_tokens"), ("cache_lido", "cache_read_input_tokens")):
            g["tok"][k] += int(tk.get(o) or 0)
    for prov, g in por_prov.items():
        rod = f"{g['n']} rodada{'s' if g['n'] != 1 else ''} · "
        itens.append({"servico": {"claude": "Claude Code", "claude-api": "Claude pela API"}.get(prov, "GPT · Codex"),
                      "tipo": "pago" if prov == "claude-api" else "assinatura", "usd": round(g["usd"], 4), "tokens": g["tok"],
                      "detalhe": rod + _texto_claude(g["tok"], g["usd"], "", vivo, prov == "claude-api")})
    de = _data(execs[0]["inicio"]) or datetime.now()
    ate = datetime.now() if vivo or not execs[-1].get("fim") else (_data(execs[-1]["fim"]) or datetime.now())
    itens += itens_do_intervalo(de, ate)
    return registrar_video(job.get("titulo") or job["slug"], job["slug"], job["cliente"], job.get("formato") or job.get("modelo", ""),
                           itens, arquivo=job.get("saida", "") if not vivo else "", chave=execs[0]["inicio"],
                           data=agora() if (vivo or status != "pronto") else execs[-1]["fim"], status=status)


ROTULO_FALTA = [("Claude Code", "Claude Code (Claude)"), ("Voz", "Voz (VoiceStudio ou ElevenLabs)"), ("Transcrição", "Transcrição (Groq / Whisper)"),
                ("Imagens", "Imagens/vídeo por IA (kie.ai)"), ("Música", "Música / b-roll"), ("Render", "Render")]


def _categoria(servico: str) -> str:
    n = servico.lower()
    if n.startswith(("claude code", "gpt")):
        return "Claude Code"
    if n.startswith(("voz", "elevenlabs")):
        return "Voz"
    if "groq" in n or "transcri" in n or "whisper" in n:
        return "Transcrição"
    if n.startswith(("imagem", "imagens")):
        return "Imagens"
    if "música" in n or "musica" in n or "b-roll" in n:
        return "Música"
    return "Render" if n.startswith("render") else "Outros"


def _servicos_completos(itens: list[dict]) -> list[dict]:
    """Todo serviço que um vídeo pode usar aparece na lista; o que ninguém registrou vira 'não registrado' (nunca some)."""
    por: dict = {}
    for i in itens:
        por.setdefault(_categoria(i["servico"]), []).append(i)
    out = []
    for cat, rotulo in ROTULO_FALTA:
        if por.get(cat):
            out += por[cat]
        elif cat == "Render":
            out.append({"servico": "Render", "tipo": "gratis", "usd": 0.0, "detalhe": "grátis (no seu Mac)"})
        else:
            out.append({"servico": rotulo, "tipo": "nao_registrado", "usd": 0.0, "detalhe": "não registrado"})
    return out + por.get("Outros", [])


def _ajustar_versao(v: dict, linhas: list[dict], agora_: datetime) -> dict:
    """Prepara uma linha do livro pra tela: gasto ao vivo (voz/imagens) recalculado, textos simples, 'interrompido' se parou."""
    v = dict(v)
    itens = [dict(i) for i in v.get("itens", [])]
    status = v.get("status", "pronto")
    d = _data(v.get("data", ""))
    if status == AO_VIVO and d and agora_ - d > timedelta(hours=VIVO_MAX_HORAS):
        status = "interrompido"
    if status == AO_VIVO and _data(str(v.get("de") or v.get("chave") or "").replace("T", " ")):
        de = _data(str(v.get("de") or v.get("chave")).replace("T", " "))
        itens = [i for i in itens if i["tipo"] == "assinatura"] + itens_do_intervalo(de, agora_, linhas)
    for i in itens:
        if i["tipo"] == "pago" and i["servico"].startswith("Voz (Gemini)"):   # linhas antigas: contavam a voz como paga sem prova
            i["tipo"], i["servico"] = "estimado", "Voz Gemini (cobrança não confirmada)"
            ped = i["detalhe"].split(" · ")[0]
            i["detalhe"] = (ped + " · " if re.match(r"\d+ pedido", ped) else "") + f"{_us(i['usd'])} estimado: não dá pra confirmar se o Google cobrou"
        elif i["servico"] == "Imagem/vídeo por IA (kie.ai)":
            i["servico"] = "Imagens/vídeo por IA (kie.ai)"
        if i["servico"] in ("Claude Code", "GPT · Codex") and i.get("tokens") and sum(int(x or 0) for x in i["tokens"].values()):
            rod = i["detalhe"].split(" · ")[0] if "rodada" in i["detalhe"].split(" · ")[0] else ""
            i["detalhe"] = (rod + " · " if rod else "") + _texto_claude(i["tokens"], i["usd"], i.get("modelos", ""), status == AO_VIVO)
        if i["servico"] == "Render":
            i["detalhe"] = "grátis (no seu Mac)"
    if v.get("formato") != "gastos soltos":
        itens = _servicos_completos(itens)
    v.update(_somas(itens))
    v["itens"], v["status"] = itens, status
    return v


def nome_formato(slug: str) -> str:
    """"dialogo-3d" -> "Diálogo 3D" (título do formato.json); sem arquivo, o próprio slug arrumado."""
    t = (ler_json(FORMATOS / slug / "formato.json", {}) or {}).get("titulo") if slug else ""
    return t or (slug or "").replace("-", " ").capitalize()


OUTROS = "Outros gastos"


def _agrupar(grupos: dict, nome: str, cliente: str, formato: str, v: dict, d: datetime | None) -> None:
    g = grupos.setdefault(nome, {"projeto": nome, "cliente": cliente, "formato": formato, "formato_nome": nome_formato(formato) if formato not in ("", OUTROS) else "",
                                 "tabela": 0.0, "pago": 0.0, "estimado": 0.0, "versoes": [], "ultima": d})
    g["tabela"] += v["tabela_usd"]; g["pago"] += v["pago_usd"]; g["estimado"] += v["estimado_usd"]
    g["versoes"].append({**v, "quando": d})
    if d and (not g["ultima"] or d > g["ultima"]):
        g["ultima"] = d


def _lista_de_projetos(ini, fim, linhas: list[dict]) -> list[dict]:
    """UMA lista: vídeos do livro (projeto → versões) e, no fim, UM item "Outros gastos" com tudo que não é de vídeo nenhum."""
    agora_ = datetime.now()
    grupos: dict = {}
    intervalos = []
    for l in _ler_livro(VIDEOS, "videos", ini):
        d = _data(l.get("data", ""))
        de = _data(str(l.get("de") or l.get("chave") or "").replace("T", " "))
        if de and d:
            intervalos.append((de - timedelta(minutes=1), (agora_ if l.get("status") == AO_VIVO else d) + timedelta(minutes=1)))
        if (ini and (not d or d < ini)) or (fim and d and d >= fim):
            continue
        _agrupar(grupos, l["projeto"], l.get("cliente", ""), l.get("formato", ""), _ajustar_versao(l, linhas, agora_), d)
    for g in grupos.values():
        g["versoes"].sort(key=lambda v: int(re.sub(r"\D", "", v.get("versao", "0")) or 0))
    lista = sorted(grupos.values(), key=lambda g: g["ultima"] or datetime.min, reverse=True)
    soltas = [l for l in linhas if l["gaveta"] in ("pago", "estimado") and not any(a <= l["data"] <= b for a, b in intervalos)]
    if soltas:
        itens = _itens_de(soltas)
        por_origem: dict = {}
        for l in soltas:
            por_origem[re.sub(r"^Sem projeto · ", "", l["projeto"] or "sem projeto")] = por_origem.get(re.sub(r"^Sem projeto · ", "", l["projeto"] or "sem projeto"), 0.0) + l["usd"]
        nota = "Gastos que não pertencem a nenhum vídeo da lista. De onde vieram: " + ", ".join(
            f"{k} ({_us(v)})" for k, v in sorted(por_origem.items(), key=lambda x: -x[1])) + "."
        d = max(l["data"] for l in soltas)
        v = {"versao": "Tudo junto", "status": "pronto", "itens": itens, **_somas(itens), "data": d.strftime("%Y-%m-%d %H:%M:%S"),
             "nota": nota, "arquivo": "", "formato": "gastos soltos"}
        _agrupar(grupos := {}, OUTROS, "", OUTROS, v, d)
        lista.append(grupos[OUTROS])
    return lista


def _txt_preco(p: dict) -> str:
    def us(x):
        t = f"{float(x):.4f}".rstrip("0")
        dec = len(t.split(".")[1]) if "." in t else 0
        return "US$ " + (t + "0" * (2 - dec) if dec < 2 else t).replace(".", ",")
    if p.get("nao_achado"):
        return "preço não confirmado"
    if "input_per_1m" in p:
        t = f"entrada {us(p['input_per_1m'])} · saída {us(p['output_per_1m'])} por 1 milhão de tokens"
        if "cache_read_per_1m" in p:
            t += f" · memória relida {us(p['cache_read_per_1m'])}"
        return t
    if "per_hour_usd" in p:
        return f"{us(p['per_hour_usd'])} por hora de áudio"
    if "per_1k_chars_usd" in p:
        return f"{us(p['per_1k_chars_usd'])} por mil caracteres"
    if "usd" in p:
        return f"{us(p['usd'])} por {p.get('unidade', 'uso')}"
    return "preço não confirmado"


NOMES_PROVEDOR = {"anthropic": "Claude (Anthropic)", "gemini": "Gemini (Google)", "groq": "Groq (transcrição)", "elevenlabs": "ElevenLabs", "kie": "kie.ai (imagem e vídeo)",
                  "openai": "OpenAI", "firecrawl": "Firecrawl", "apify": "Apify"}


def tabela_precos() -> list[dict]:
    """Preços de todos os modelos que o Estúdio usa (os usados primeiro). Sem preço oficial: 'preço não confirmado'."""
    out = []
    for prov, modelos in (ler_json(PRECOS, {}) or {}).items():
        if not isinstance(modelos, dict) or prov.startswith("_") or prov not in ("anthropic", "groq", "elevenlabs", "kie"):   # o Gemini saiu do Estúdio: não lista mais (o histórico segue sendo calculado)
            continue
        for modelo, p in modelos.items():
            if modelo.startswith("_") or not isinstance(p, dict) or not (p.get("fonte") or p.get("nao_achado")):
                continue   # entradas antigas sem fonte oficial não entram na lista
            out.append({"provedor": NOMES_PROVEDOR.get(prov, prov), "modelo": modelo, "preco": _txt_preco(p), "nota": p.get("nota", ""),
                        "fonte": p.get("fonte", ""), "conferido_em": p.get("conferido_em", ""), "nao_achado": bool(p.get("nao_achado")) or not p.get("fonte"),
                        "usado": bool(p.get("usado_no_estudio"))})
    return sorted(out, key=lambda x: (not x["usado"], x["provedor"], x["modelo"]))


def _usos_assinaturas(subs: list[dict], linhas: list[dict], cc: dict) -> list[dict]:
    def conta(*ks):
        return sum(1 for l in linhas if not l.get("api") and any(k in l["servico"].lower() for k in ks))
    out = []
    for a in subs:
        n = a["nome"].lower()
        usos = (conta("claude") + cc["n"] if "claude" in n else conta("gpt", "codex", "openai") if ("gpt" in n or "openai" in n)
                else conta("elevenlabs") if "eleven" in n else conta(n))
        out.append({**a, "usos": usos})
    return out


def dinheiro_que_saiu(tot: dict) -> float:
    """O número grande da aba Custos: só o que foi cobrado de verdade (API, créditos da kie.ai, outros pagos).
    O preço de tabela do plano ('assinatura') e o 'estimado' nunca entram."""
    return round(float(tot.get("pago") or 0), 4)


# ───────────────────────── "Onde cada coisa é cobrada" (Configurações) ─────────────────────────
SEM_MEDIDA = "ainda sem medida"
CATALOGO_KIE = Path.home() / "Projetos" / "Skill" / "Gerador de imagem e vídeo" / "modelos" / "catalogo.md"
ULTIMAS = 20   # a média usa no máximo as últimas N linhas de cada livro


def _media(valores: list[float]) -> tuple[float, int]:
    return (sum(valores) / len(valores), len(valores)) if valores else (0.0, 0)


def _ultimas(linhas: list[dict], campo: str = "data", n: int = ULTIMAS) -> list[dict]:
    return sorted(linhas, key=lambda r: r.get(campo) or "")[-n:]


def _precos_kie() -> list[str]:
    """Linhas 'modelo: preço' da tabela "Os que o João mais usa" do catálogo da skill (só leitura)."""
    try:
        texto = CATALOGO_KIE.read_text(encoding="utf-8")
    except OSError:
        return []
    bloco = texto.split("### Os que o João mais usa", 1)[-1].split("\n###", 1)[0] if "### Os que o João mais usa" in texto else ""
    out = []
    for linha in bloco.splitlines():
        c = [x.strip().replace("`", "").replace("**", "") for x in linha.strip().strip("|").split("|")]
        if len(c) >= 2 and c[0] and not c[0].startswith(("Modelo", "---")) and re.search(r"\d", c[1]):
            out.append(f"{c[0]}: {c[1]}")
    return out[:4]


def _custa_claude_tela(execucoes: list[dict], api: list[dict], videos: list[dict]) -> list[str]:
    linhas = []
    pago, n = _media([float(r.get("usd") or 0) for r in _ultimas([r for r in api if r.get("fila") == "Estúdio" and r.get("estado") == "ok"], "quando")])
    if n:
        linhas.append(f"Uma rodada pela tela saiu em média {_us(pago)} do seu crédito nas últimas {n} rodadas.")
    tab, n = _media([float(r.get("usd") or 0) for r in _ultimas([r for r in execucoes if r.get("provedor", "claude") == "claude"])])
    if n:
        linhas.append(f"Uma rodada no plano equivale a {_us(tab)} de tabela (você não pagou) nas últimas {n} rodadas.")
    por_formato: dict = {}
    for v in sorted(videos, key=lambda r: r.get("data") or ""):
        if v.get("formato"):
            por_formato.setdefault(v["formato"], []).append(v)
    for slug, vs in sorted(por_formato.items(), key=lambda kv: -len(kv[1]))[:3]:
        vs = vs[-5:]
        tab, n = _media([float(v.get("tabela_usd") or 0) for v in vs])
        pago, _ = _media([float(v.get("pago_usd") or 0) for v in vs])
        linhas.append(f"Um vídeo de {nome_formato(slug)}: tabela {_us(tab)}, saiu {_us(pago)} do bolso (média das últimas {n}).")
    return linhas


def _custa_fila(execucoes: list[dict], api: list[dict]) -> list[str]:
    linhas = []
    for modelo in ("opus", "sonnet"):
        m, n = _media([float(r.get("usd") or 0) for r in _ultimas([r for r in api if r.get("fila") != "Estúdio" and r.get("estado") == "ok"
                                                                       and r.get("modelo") == modelo], "quando")])
        if n:
            linhas.append(f"Uma tarefa da fila com {modelo.capitalize()} saiu em média {_us(m)} da API nas últimas {n} tarefas.")
    tab, n = _media([float(r.get("usd") or 0) for r in _ultimas([r for r in execucoes if str(r.get("onde", "")).startswith("fila ")])])
    if n:
        linhas.append(f"Uma tarefa da fila no plano equivale a {_us(tab)} de tabela (você não pagou) nas últimas {n} tarefas.")
    return linhas


def _custa_gemini(uso: list[dict]) -> list[str]:
    hoje = datetime.now()
    sete = [r for r in uso if (d := _data(r.get("data", ""))) and d >= hoje - timedelta(days=7)]
    if not sete:
        return []
    dia = hoje.strftime("%Y-%m-%d")
    gratis = sum(1 for r in sete if CHAVES_GEMINI.get(r.get("chave")) == "gratis")
    pagas = sum(1 for r in sete if CHAVES_GEMINI.get(r.get("chave")) == "pago")
    return [f"{len(sete)} pedidos de voz nos últimos 7 dias ({sum(1 for r in uso if str(r.get('data', '')).startswith(dia))} hoje): "
            f"{gratis} na cota grátis, {pagas} na chave paga, {len(sete) - gratis - pagas} sem confirmar."]


def _custa_kie(tsv: list[dict]) -> list[str]:
    linhas = []
    for tipo, rotulo in (("imagem", "imagem"), ("video", "vídeo")):
        m, n = _media([float(r.get("usd") or 0) for r in tsv[-300:] if r.get("tipo") == tipo and (r.get("status") or "ok") == "ok" and r.get("usd")])
        if n:
            linhas.append(f"Cada {rotulo} custou em média {_us(m)} nas últimas {n} (créditos da kie.ai).")
    return linhas


def onde_e_cobrado(cfg: dict | None = None) -> list[dict]:
    """Um cartão por serviço (usa / cobrado de / custa por uso / como mudar). 'Custa por uso' é média dos livros; sem dado: 'ainda sem medida'."""
    cfg = cfg or {}
    execucoes, api = ler_jsonl(LIVRO), ler_jsonl(API_LIVRO)
    videos, gemini = ler_jsonl(VIDEOS), ler_jsonl(GEMINI_USO)
    try:
        with KIE_TSV.open(encoding="utf-8") as f:
            tsv = list(csv.DictReader(f, delimiter="\t"))
    except OSError:
        tsv = []
    try:
        eleven = [l["usd"] for l in _do_cerebro() if "eleven" in l["servico"].lower() and l["gaveta"] == "pago"]
    except Exception:
        eleven = []
    modelo = (cfg.get("modelo_claude") or "sonnet").capitalize()
    dinheiro = "Crédito da API do Claude (Console). Sai dinheiro de verdade."
    plano = "Limite da semana do seu plano do Claude. Não sai dinheiro: gasta uma parte do limite."
    de_tela = dinheiro if cfg.get("cobranca", "api") != "assinatura" else plano
    de_fila = dinheiro if cfg.get("fila_cobranca", "api") != "assinatura" else plano
    if cfg.get("provedor") == "openai":
        de_tela = "Assinatura do ChatGPT (Codex). Não sai dinheiro por uso."
    kie_precos = _precos_kie()
    media_eleven, n_eleven = _media(eleven)
    cartoes = [
        {"nome": "Claude nos vídeos pela tela", "usa": f"Claude ({modelo}) planeja, monta e confere cada vídeo.", "cobrado": de_tela,
         "custa": _custa_claude_tela(execucoes, api, videos), "mudar": "Configurações → Quem edita os vídeos (modelo e “Cobrar da API”)."},
        {"nome": "Fila de construção do sistema", "usa": "Claude (Sonnet ou Opus) rodando tarefas em lote, pelo via_api.py.", "cobrado": de_fila,
         "custa": _custa_fila(execucoes, api), "mudar": "Configurações → Quem edita os vídeos → “Cobrar a fila da API”."},
        {"nome": "VoiceStudio: voz local", "usa": "voicestudio.py, a voz padrão dos vídeos por roteiro (porta 3900, no seu Mac).",
         "cobrado": "Ninguém: roda local.", "custa": ["R$ 0: grátis."], "gratis": True,
         "mudar": "Configurações → Voz dos vídeos por roteiro."},
        {"nome": "kie.ai: imagem e vídeo", "usa": "kie.py (skill gerador-imagem-video), só com a sua aprovação.",
         "cobrado": "Créditos da própria kie.ai. Não sai da API do Claude nem do plano.",
         "custa": kie_precos + _custa_kie(tsv), "mudar": "Cada geração espera o seu OK. Modelos e preços: catalogo.md da skill."},
        {"nome": "ElevenLabs", "usa": "voz.py, só se você escolher a ElevenLabs como voz (reserva se o VoiceStudio estiver fechado).", "cobrado": "Plano da própria ElevenLabs.",
         "custa": [f"Cada uso custou em média {_us(media_eleven)} nos últimos {n_eleven} usos."] if n_eleven else [],
         "mudar": "Configurações → Voz dos vídeos por roteiro."},
        {"nome": "B-roll (cenas de apoio)", "usa": "get-brolls (YouTube, Pexels, Pixabay, Wikimedia Commons e NASA). O Claude só confere os quadros.",
         "cobrado": "Ninguém: as fontes são grátis. A conferência do Claude entra no custo do vídeo.", "custa": ["R$ 0: grátis."], "gratis": True,
         "mudar": "Chaves da Pexels e Pixabay em Configurações → Serviços e chaves."},
        {"nome": "Render (montar o vídeo)", "usa": "ffmpeg e motores do próprio Estúdio, no seu Mac.", "cobrado": "Ninguém: roda local.",
         "custa": ["R$ 0: grátis."], "gratis": True, "mudar": "Configurações → Avançado → Renders ao mesmo tempo."},
    ]
    hist_gemini = _custa_gemini(gemini)   # o Gemini saiu do Estúdio em 29-out-2026: o cartão só aparece enquanto houver uso recente no livro (o histórico fica)
    if hist_gemini:
        cartoes.insert(3, {"nome": "Voz Gemini (antiga, não é mais usada)", "usa": "Voz do Gemini (Google): o Estúdio não chama mais; isto é só o histórico.",
                           "cobrado": "Cota grátis do Google nas chaves 1 a 5. A chave 6 era conta paga.", "custa": hist_gemini,
                           "mudar": "Nada a fazer: a voz agora é o VoiceStudio."})
    for c in cartoes:
        c["medido"] = bool(c["custa"])
        c["custa"] = c["custa"] or [SEM_MEDIDA]
    return cartoes


def visao(cotacao: float = COTACAO_PADRAO, equivalente_mes_usd: float | None = None) -> dict:
    """Os 3 números do topo da aba Custos: HOJE, ESTE MÊS e a ÚLTIMA FILA, só o que saiu do bolso, cada um com a origem.
    `equivalente_mes_usd`: o que o mês custaria se tudo fosse pela API (o `equivalente_plano_usd` do resumo do mês); sem ele, calcula aqui."""
    if equivalente_mes_usd is None:
        try: equivalente_mes_usd = resumo("mes", cotacao)["equivalente_plano_usd"]
        except Exception: equivalente_mes_usd = 0.0
    agora_ = datetime.now()
    zero = agora_.replace(hour=0, minute=0, second=0, microsecond=0)
    ini_mes = zero.replace(day=1)
    ini_l = ini_mes - timedelta(minutes=1)
    todas = [l for l in _do_estudio() + _da_api() + _do_cerebro(ini_l) + _da_kie(ini_l) if l["data"] >= ini_mes]
    def soma(ini):
        itens = [l for l in todas if l["data"] >= ini and l["gaveta"] == "pago"]
        origem: dict = {}
        for l in itens:
            origem[l["servico"]] = origem.get(l["servico"], 0.0) + l["usd"]
        return {"usd": round(sum(origem.values()), 4), "n": len(itens),
                "origem": sorted(origem.items(), key=lambda x: -x[1])}
    filas: dict = {}
    for l in todas:
        if l.get("api"):
            f = filas.setdefault(l["fila"], {"fila": l["fila"], "usd": 0.0, "n": 0, "ini": l["data"], "fim": l["data"]})
            f["usd"] += l["usd"]; f["n"] += 1; f["ini"] = min(f["ini"], l["data"]); f["fim"] = max(f["fim"], l["data"])
    for f in filas.values():
        if f["fila"] == "api":
            f["fila"] = "Chamadas avulsas pela API"
    lista = sorted(filas.values(), key=lambda f: f["fim"], reverse=True)
    hoje = soma(zero)
    hoje_filas: dict = {}
    for l in todas:
        if l.get("api") and l["data"] >= zero and l["gaveta"] == "pago":
            nome = "Chamadas avulsas pela API" if l["fila"] == "api" else l["fila"]
            hoje_filas[nome] = hoje_filas.get(nome, 0.0) + l["usd"]
    hoje["filas"] = sorted(hoje_filas.items(), key=lambda x: -x[1])
    hoje["fora_de_fila"] = round(max(0.0, hoje["usd"] - sum(hoje_filas.values())), 4)
    dias = sorted({l["data"].day for l in todas if l["gaveta"] == "pago" and l["usd"] > 0 and l["data"] < zero})
    dias_txt = ", ".join(f"{d:02d}" for d in dias)
    if len(dias) > 1:
        dias_txt = dias_txt.rsplit(", ", 1)[0] + " e " + dias_txt.rsplit(", ", 1)[1]
    return {"hoje": hoje, "dias_antes": dias_txt, "mes": soma(ini_mes), "mes_rotulo": agora_.strftime("%m/%Y"), "filas": lista,
            "ultima": lista[0] if lista else None, "cotacao": cotacao,
            "equivalente_mes_usd": round(float(equivalente_mes_usd or 0), 2)}


def resumo(periodo: str = "mes", cotacao: float = COTACAO_PADRAO, de: str = "", ate: str = "", projeto: str = "") -> dict:
    podar()
    ini, fim, rotulo = periodo_inicio(periodo, de, ate)
    ini_l = ini - timedelta(minutes=1) if ini else None
    todas_cb = _do_cerebro(ini_l) + _da_kie(ini_l)
    todas = [l for l in _do_estudio() + _da_api() + todas_cb if (not ini or l["data"] >= ini) and (not fim or l["data"] < fim)]
    lista = _lista_de_projetos(ini, fim, todas_cb)
    projetos = sorted(g["projeto"] for g in lista)
    tot = {"assinatura": 0.0, "gratis": 0.0, "pago": 0.0, "estimado": 0.0}
    por_servico: dict = {}
    if projeto:   # filtrado: os números vêm das versões do projeto escolhido
        lista = [g for g in lista if g["projeto"] == projeto]
        linhas = []
        for g in lista:
            for v in g["versoes"]:
                for i in v["itens"]:
                    gav = i["tipo"]
                    if gav == "nao_registrado":
                        continue   # sem registro: não entra nas somas nem na lista por serviço
                    tot[gav] += i["usd"]
                    s = por_servico.setdefault((gav, i["servico"]), {"gaveta": gav, "servico": i["servico"], "usd": 0.0, "n": 0})
                    s["usd"] += i["usd"]; s["n"] += 1
    else:
        linhas = sorted(todas, key=lambda l: l["data"], reverse=True)
        for l in linhas:
            tot[l["gaveta"]] += l["usd"]
            s = por_servico.setdefault((l["gaveta"], l["servico"]), {"gaveta": l["gaveta"], "servico": l["servico"], "usd": 0.0, "n": 0})
            s["usd"] += l["usd"]; s["n"] += 1
    cc = claude_code_conversas(ini, fim) if not projeto else {"n": 0, "usd": 0.0, "erro": ""}
    if not projeto:
        por_servico[("assinatura", "Claude Code (conversas no terminal)")] = {
            "gaveta": "assinatura", "servico": "Claude Code (conversas no terminal)", "usd": cc["usd"], "n": cc["n"],
            "unidade": "conversas", "erro": cc["erro"]}
    subs = _usos_assinaturas(assinaturas(), todas, cc)
    cot_fixo = lambda a: a["valor"] / cotacao if a.get("moeda") == "BRL" else a["valor"]
    return {
        "dinheiro_saiu_usd": dinheiro_que_saiu(tot), "equivalente_plano_usd": round(tot["assinatura"] + cc["usd"], 2),
        "periodo": periodo, "rotulo": rotulo, "cotacao": cotacao, "linhas": linhas[:300], "n": len(linhas),
        "total": tot, "fixo_usd": sum(cot_fixo(a) for a in subs if a["usos"]), "assinaturas": subs, "gratis_local": GRATIS_LOCAL,
        "por_servico": sorted(por_servico.values(), key=lambda x: (-x["usd"], x["servico"])),
        "videos": lista, "ao_vivo": any(v["status"] == AO_VIVO for g in lista for v in g["versoes"]),
        "api": api_por_tarefa([] if projeto else todas), "projetos": projetos, "projeto": projeto, "de": de, "ate": ate, "dias_livro": DIAS_LIVRO, "precos": tabela_precos(),
    }


if __name__ == "__main__":
    r = resumo(sys.argv[1] if len(sys.argv) > 1 else "mes")
    print(json.dumps({k: v for k, v in r.items() if k not in ("linhas",)}, ensure_ascii=False, indent=1, default=str))
