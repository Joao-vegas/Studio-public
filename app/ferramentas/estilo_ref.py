"""Referência rápida (Estúdio 2.0): joga um vídeo ou link e o Estúdio entende o ESTILO sozinho.

medir (ffmpeg, grátis) → transcrever (Groq, se houver chave) → UMA chamada de IA que escreve o estilo.json →
validar + copia_proibida (referência é estilo, nunca cópia: G0 em código) → o João confirma → vira estudo do formato.
Trabalho em app/.estilos/<id>/ com estado.json (analisando|pronto|erro|confirmado)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import unicodedata
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import ESTUDIO, RAIZ, agora, ensure, ffprobe, gravar_json, ler_json, make_slug, rel  # noqa: E402
import formatos  # noqa: E402
import ia  # noqa: E402

ESTILOS = ESTUDIO / ".estilos"
TETO_USD = 0.60          # ia.executar usa o teto da etapa "outro" (Configurações); aqui fica registrado o alvo
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MIN_COPIA = 6            # 6+ palavras seguidas da transcrição dentro do estilo = cópia
FRASE_ERRO = "Não consegui entender este vídeo. Tente de novo ou mande outro."


# ───────────────────────────── medir (sem IA, grátis) ─────────────────────────────

def _cores(video: Path, dur: float, n: int = 5, quadros: int = 12) -> list[str]:
    """As n cores dominantes (hex) de ~12 quadros espalhados pelo vídeo."""
    from PIL import Image
    tmp = ensure(video.parent / "_cores")
    try:
        passo = max(dur, 1.0) / quadros
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps=1/{passo:.3f},scale=96:-2",
                        "-frames:v", str(quadros), str(tmp / "q%02d.png")], capture_output=True, timeout=300)
        imgs = [Image.open(p).convert("RGB") for p in sorted(tmp.glob("q*.png"))]
        if not imgs:
            return []
        w, h = imgs[0].size
        mosaico = Image.new("RGB", (w * len(imgs), h))
        for i, im in enumerate(imgs):
            mosaico.paste(im.resize((w, h)), (i * w, 0))
        q = mosaico.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[: 3 * n]
        usos = sorted(q.getcolors() or [], reverse=True)   # (contagem, índice)
        return ["#%02x%02x%02x" % tuple(pal[3 * i: 3 * i + 3]) for _, i in usos[:n]]
    except Exception:
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _som(video: Path) -> dict:
    """Volume médio e silêncio (ffmpeg): ajuda a dizer se tem música/fala."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af",
                        "volumedetect,silencedetect=noise=-35dB:d=0.5", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=300)
    err = r.stderr or ""
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", err)
    mx = re.search(r"max_volume:\s*(-?[\d.]+) dB", err)
    sil = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", err))
    return {"volume_medio_db": float(m.group(1)) if m else None, "volume_maximo_db": float(mx.group(1)) if mx else None,
            "silencio_s": round(sil, 1)}


def _quadros_grandes(video: Path, destino: Path, dur: float, cortes: list) -> list[str]:
    """Até 5 quadros em 1080 de altura (1 s, meio e +0,5 s depois de até 3 cortes espalhados): vê caixa, cor da legenda e as peças marcantes."""
    ts = [min(1.0, dur / 2), dur / 2]
    if cortes:
        n = len(cortes)
        ts += [cortes[i] + 0.5 for i in dict.fromkeys([n // 4, n // 2, 3 * n // 4])]
    else:
        ts.append(dur * 0.75)
    vistos, unicos = set(), []
    for t in ts:
        k = round(t, 1)
        if k not in vistos:
            vistos.add(k)
            unicos.append(t)
    out = []
    for i, t in enumerate(unicos[:5], 1):
        alvo = destino / f"quadro-{i}.jpg"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0, min(t, max(dur - 0.1, 0))):.2f}",
                        "-i", str(video), "-frames:v", "1", "-vf", "scale=-2:1080", "-q:v", "3", str(alvo)],
                       capture_output=True, timeout=60)
        if alvo.is_file():
            out.append(alvo.name)
    return out


def medir(video: Path | str, destino: Path | None = None) -> dict:
    """Duração, resolução, cortes por segundo, 5 cores, som e a folha de quadros (com o segundo marcado)."""
    video = Path(video)
    destino = ensure(Path(destino) if destino else video.parent)
    m = formatos._medir_referencia(video)
    dur = float(m.get("duracao") or 0)
    m["cortes_por_s"] = round((m.get("cortes") or 0) / dur, 2) if dur else None
    m["cores"] = _cores(video, dur)
    if m.get("som"):
        s = _som(video)
        m.update(s)
        m["silencio_pct"] = round(100 * s["silencio_s"] / dur) if dur else None
    m["quadros"] = _quadros_grandes(video, destino, dur, m.get("cortes_s") or [])
    folha = formatos.fazer_folha(video, destino / "folha.jpg")
    m["folha"] = folha.name if folha else ""
    gravar_json(destino / "medidas.json", m)
    return m


# ───────────────────────────── o esquema do estilo ─────────────────────────────

ESQUEMA = {
    "layout": "lista de faixas da tela 1080x1920: [{nome, y, altura}] em px (uma faixa tela cheia se não divide)",
    "ritmo": {"corte_a_cada_s": "número", "plano_medio_s": "número"},
    "legenda": {"posicao_y_pct": "0-100 (0 topo)", "fonte_aprox": "texto", "cor_hex": "#RRGGBB", "caixa": "texto ou false",
                "destaque_hex": "#RRGGBB da palavra que muda de cor, ou false",
                "palavras_por_vez": "número (0 = sem legenda)", "maiusculas": "true/false"},
    "som": {"musica": "true/false", "clima": "texto", "efeitos": ["lista de texto"]},
    "cores": ["#RRGGBB", "..."],
    "gancho": {"mecanismo": "COMO prende, nunca o texto dito", "ate_s": "número"},
    "formato_sugerido": {"slug": "slug existente ou \"novo\"", "nota": "0-100", "porque": "texto curto", "perto": "(opcional) slug do formato mais próximo quando slug é novo"},
    "estudo_respostas": {"<Titulo>:<n>": "resposta curta com número, uma por pergunta"},
}


def chaves_perguntas() -> list[tuple[str, str]]:
    """[(chave 'Ritmo:0', pergunta)] na ordem do ESTUDO.md."""
    return [(f"{tit}:{i}", q) for tit, qs in formatos.PERGUNTAS_ESTUDO for i, q in enumerate(qs)]


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def erros(estilo) -> list[str]:
    """Tudo que falta ou está errado no estilo (lista vazia = válido)."""
    if not isinstance(estilo, dict):
        return ["o estilo não é um objeto"]
    e: list[str] = []
    for k in ESQUEMA:
        if k not in estilo:
            e.append(f"falta o campo '{k}'")
    if e:
        return e
    lay = estilo["layout"]
    if not isinstance(lay, list) or not lay:
        e.append("layout: lista de faixas vazia")
    else:
        for i, f in enumerate(lay):
            if not isinstance(f, dict) or not _num(f.get("y")) or not _num(f.get("altura")):
                e.append(f"layout[{i}]: faixa precisa de y e altura em px")
    r = estilo["ritmo"]
    for k in ("corte_a_cada_s", "plano_medio_s"):
        if not isinstance(r, dict) or not _num(r.get(k)):
            e.append(f"ritmo.{k}: precisa ser número")
    lg = estilo["legenda"]
    for k in ("posicao_y_pct", "fonte_aprox", "cor_hex", "caixa", "palavras_por_vez", "maiusculas"):   # destaque_hex é opcional
        if not isinstance(lg, dict) or k not in lg:
            e.append(f"legenda.{k}: falta")
    if isinstance(lg, dict):
        if "posicao_y_pct" in lg and not _num(lg["posicao_y_pct"]):
            e.append("legenda.posicao_y_pct: precisa ser número")
        if "palavras_por_vez" in lg and not _num(lg["palavras_por_vez"]):
            e.append("legenda.palavras_por_vez: precisa ser número")
        if "cor_hex" in lg and not HEX.match(str(lg["cor_hex"])):
            e.append("legenda.cor_hex: use #RRGGBB")
        d = lg.get("destaque_hex", False)
        if d not in (False, None, "") and not HEX.match(str(d)):
            e.append("legenda.destaque_hex: use #RRGGBB ou false")
    s = estilo["som"]
    if not isinstance(s, dict) or any(k not in s for k in ("musica", "clima", "efeitos")) or not isinstance(s.get("efeitos"), list):
        e.append("som: precisa de musica, clima e efeitos (lista)")
    c = estilo["cores"]
    if not isinstance(c, list) or not c or not all(HEX.match(str(x)) for x in c):
        e.append("cores: lista de #RRGGBB")
    g = estilo["gancho"]
    if not isinstance(g, dict) or not str(g.get("mecanismo") or "").strip() or not _num(g.get("ate_s")):
        e.append("gancho: precisa de mecanismo (texto) e ate_s (número)")
    fs = estilo["formato_sugerido"]
    if not isinstance(fs, dict) or not str(fs.get("slug") or "").strip() or not _num(fs.get("nota")) \
            or not 0 <= fs.get("nota", -1) <= 100 or not str(fs.get("porque") or "").strip():
        e.append("formato_sugerido: precisa de slug, nota 0-100 e porque")
    if isinstance(fs, dict) and fs.get("perto") not in (None, "") and not isinstance(fs.get("perto"), str):
        e.append("formato_sugerido.perto: precisa ser o slug de um formato (texto)")
    er = estilo["estudo_respostas"]
    if not isinstance(er, dict):
        e.append("estudo_respostas: precisa ser objeto")
    else:
        for k, _ in chaves_perguntas():
            if not str(er.get(k) or "").strip():
                e.append(f"estudo_respostas: falta a resposta '{k}'")
    return e


NOTA_SERVE = 60


def serve(estilo) -> bool:
    """Uma regra só (tela e confirmar): o formato sugerido existe e a nota é de 60 pra cima."""
    fs = (estilo or {}).get("formato_sugerido") if isinstance(estilo, dict) else None
    if not isinstance(fs, dict):
        return False
    slug = str(fs.get("slug") or "").strip()
    nota = fs.get("nota")
    return bool(slug and slug != "novo" and _num(nota) and nota >= NOTA_SERVE and formatos.carregar(slug))


def validar(estilo) -> dict:
    """Levanta ValueError claro se faltar algo; devolve o estilo se estiver ok."""
    e = erros(estilo)
    if e:
        raise ValueError("Estilo incompleto: " + "; ".join(e))
    return estilo


# ───────────────────────────── G0 em código: nada de copiar a fala ─────────────────────────────

def _palavras(txt: str) -> list[str]:
    s = unicodedata.normalize("NFD", str(txt).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", s)


def _textos(o) -> list[str]:
    if isinstance(o, str):
        return [o]
    if isinstance(o, dict):
        return [t for v in o.values() for t in _textos(v)]
    if isinstance(o, (list, tuple)):
        return [t for v in o for t in _textos(v)]
    return []


_ASPAS = re.compile(r"'([^']+)'|\"([^\"]+)\"|“([^”]+)”|‘([^’]+)’")


def _textos_citados(estilo) -> list[str]:
    """Textos de gancho.mecanismo, legenda.* e estudo_respostas (onde fala citada não pode aparecer)."""
    if not isinstance(estilo, dict):
        return []
    g = estilo.get("gancho")
    return _textos([g.get("mecanismo") if isinstance(g, dict) else None, estilo.get("legenda"), estilo.get("estudo_respostas")])


def copia_proibida(estilo, transcricao: str) -> None:
    """Levanta ValueError se há trecho entre aspas com 3+ palavras (com ou sem transcrição) ou 6+ palavras seguidas da transcrição."""
    for t in _textos_citados(estilo):
        for m in _ASPAS.finditer(t):
            trecho = next(x for x in m.groups() if x)
            if len(_palavras(trecho)) >= 3:
                raise ValueError("O estilo cita um trecho falado (“" + trecho[:60] + "…”). Descreva o TIPO de situação, nunca a fala.")
    tw = _palavras(transcricao)
    if len(tw) < MIN_COPIA:
        return
    janelas = {" ".join(tw[i:i + MIN_COPIA]) for i in range(len(tw) - MIN_COPIA + 1)}
    for t in _textos(estilo):
        ew = _palavras(t)
        for i in range(len(ew) - MIN_COPIA + 1):
            if " ".join(ew[i:i + MIN_COPIA]) in janelas:
                raise ValueError("O estilo copia a fala do vídeo (“" + " ".join(ew[i:i + MIN_COPIA]) +
                                 "…”). Descreva COMO é, nunca o que é dito.")


# ───────────────────────────── estado e pasta de trabalho ─────────────────────────────

def pasta(id_: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{8,32}", str(id_ or "")):
        raise ValueError("Referência não encontrada.")
    return ESTILOS / id_


def _parado(d: dict, pasta_: Path, minutos: int = 15) -> bool:
    """Está "analisando" há mais de 15 min e ninguém vivo cuida dela (o Estúdio reiniciou no meio)?"""
    from datetime import datetime
    try:
        idade = (datetime.now() - datetime.strptime(d.get("atualizado_em") or d.get("criado_em") or "", "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return False
    if idade < minutos * 60:
        return False
    try:
        import os
        os.kill(int((pasta_ / "runner.pid").read_text().strip()), 0)
        return False
    except (OSError, ValueError):
        return True


def estado(id_: str) -> dict | None:
    try:
        d = ler_json(pasta(id_) / "estado.json", None)
    except ValueError:
        return None
    if d and d.get("estado") == "analisando" and _parado(d, pasta(id_)):
        d = {**d, "estado": "erro", "erro": "Parou no meio (o Estúdio reiniciou). Clique em Tentar de novo.",
             "atualizado_em": agora()}
        gravar_json(pasta(id_) / "estado.json", d)
    return d


def _salvar(id_: str, **campos) -> dict:
    d = {**(estado(id_) or {}), **campos, "atualizado_em": agora()}
    gravar_json(pasta(id_) / "estado.json", d)
    return d


def nome_curto(st: dict) -> str:
    """Título curto pra lista: o do vídeo, "YouTube · id", "Instagram · id" ou o nome do arquivo."""
    if st.get("titulo"):
        return st["titulo"]
    link = str(st.get("link") or "")
    if link:
        m = re.search(r"(?:shorts/|/reel/|/p/|v=|youtu\.be/)([\w-]+)", link)
        rede = "Instagram" if "instagram" in link else "TikTok" if "tiktok" in link else "YouTube" if "youtu" in link else "Link"
        return f"{rede} · {m.group(1)}" if m else rede
    return Path(str(st.get("origem") or st.get("id") or "referência")).stem


def listar() -> list[dict]:
    itens = sorted((ler_json(p, {}) for p in ESTILOS.glob("*/estado.json")), key=lambda d: d.get("criado_em", ""), reverse=True)
    for d in itens:
        d["nome_curto"] = nome_curto(d)
        fs = (estilo_de(d["id"]).get("formato_sugerido") if d.get("id") and d.get("estado") in ("pronto", "confirmado") else None) or {}
        if d.get("estado") == "confirmado" and d.get("formato"):
            d["formato_nome"] = (formatos.carregar(d["formato"]) or {}).get("titulo") or d["formato"]
        elif fs:
            d["formato_nome"] = ((formatos.carregar(fs.get("slug")) or {}).get("titulo") or "") if serve({"formato_sugerido": fs}) else "pede estilo novo"
    return itens


def estilo_de(id_: str) -> dict:
    return ler_json(pasta(id_) / "estilo.json", {}) or {}


def video_de(id_: str) -> Path | None:
    return next(iter(sorted(pasta(id_).glob("video.*"))), None)


# ───────────────────────────── entender ─────────────────────────────

def _eh_link(s) -> bool:
    return bool(re.match(r"^https?://", str(s).strip()))


def _catalogo_txt() -> str:
    linhas = []
    for f in formatos.listar():
        linhas.append(f"- {f['slug']} · {f.get('titulo', '')} · {f.get('frase', '')} · grupo: {getattr(formatos, 'grupo_de', lambda x: x.get('grupo', '?'))(f)}")
    return "\n".join(linhas)


def _transcricao(video: Path, pasta_: Path, cliente: str) -> tuple[str, str, str]:
    """(texto, aviso, motivo). Só Groq (barato); sem Groq ou se falhar, segue pelas imagens (nunca cai num transcritor pago sem avisar)."""
    import chaves
    if chaves.chave("GROQ_API_KEY", cliente or None):
        try:
            import estudo
            pasta_cli = RAIZ / "clientes" / (cliente or "Avulso")
            estudo.transcrever(video, pasta_, {"pasta": str(pasta_cli)})
            palavras = ler_json(pasta_ / "words.json", []) or []
            txt = " ".join(str(w.get("word", "")).strip() for w in palavras)
            if txt.strip():
                return txt, "", ""
            return "", "Entendi pelas imagens (o vídeo não tem fala ou a escuta falhou).", "sem fala na transcrição"
        except Exception as e:  # noqa: BLE001
            return "", "Entendi pelas imagens (o vídeo não tem fala ou a escuta falhou).", str(e)[:200]
    return "", "Entendi pelas imagens (o vídeo não tem fala ou a escuta falhou).", "sem GROQ_API_KEY"


SEM_AUDIO = 'O vídeo veio SEM ÁUDIO: em "som" ponha musica false, clima "não deu pra ouvir (vídeo sem som)" e efeitos []. Não adivinhe o som.\n'


def _prompt(id_: str, pasta_: Path, m: dict, transcricao: str, obs: str, erro: str) -> str:
    perguntas = "\n".join(f'  "{k}": "{q}"' for k, q in chaves_perguntas())
    return f"""Você é o analista de ESTILO do Estúdio de vídeo do João. Olhe a folha de quadros {rel(pasta_ / m.get('folha', 'folha.jpg'))} (o segundo de cada quadro está escrito no canto) e entenda COMO o vídeo é feito.
Quadros grandes (1080 de altura) pra ver legenda, caixa e cor de perto: {', '.join(rel(pasta_ / q) for q in m.get('quadros', [])) or '(sem)'}. Use ELES pra descrever a legenda (cor do texto, se tem caixa e de que cor, palavra em destaque) e as cores.
Os cortes de cena foram medidos pelo ffmpeg nestes segundos: {m.get('cortes_s') or '(nenhum)'}. Confie nos cortes medidos pro ritmo e pra duração de cada bloco; não estime no olho.
Medidas já tiradas pelo ffmpeg (confie nelas): {json.dumps({k: v for k, v in m.items() if k != 'folha'}, ensure_ascii=False)}
Transcrição da fala (SÓ pra você entender o assunto; NUNCA copie nem cite trecho dela no estilo): {transcricao[:6000] or '(sem transcrição)'}
Formatos que já existem no Estúdio:
{_catalogo_txt()}
Nota 70+ só se o formato serve SEM mudar o que ele tem de essencial (a frase dele). Se falta o essencial (ex.: Fala com cenas sem cenas), slug "novo", nota abaixo de 60, em "perto" o slug do formato mais próximo e em "porque" diga o mais perto.
Referência é ESTILO, nunca cópia: descreva layout, ritmo, legenda, som, cores e o MECANISMO do gancho (como prende), jamais o texto dito nem nomes de pessoas, nem a legenda que aparece nos quadros, nem traduzida, nem entre aspas; descreva o TIPO de situação (ex.: "uma situação do dia a dia"). Se uma palavra da legenda muda de cor, dê a cor em legenda.destaque_hex (senão false).
Escreva SOMENTE o arquivo {rel(pasta_ / 'estilo.json')} (JSON puro, sem comentário) neste esquema:
{json.dumps(ESQUEMA, ensure_ascii=False, indent=1)}
Em "estudo_respostas" use exatamente estas chaves, uma resposta curta com número em cada:
{{
{perguntas}
}}
No gancho, nunca diga o assunto nem a afirmação da fala; diga só o tipo (ex.: "uma afirmação contrária ao senso comum").
{_regua_quadros(pasta_) or REGRA_BASE}
Use os números da régua medida (quando houver) nas respostas de ritmo, legenda e som: eles valem mais que o olho.
{'' if m.get('som') else SEM_AUDIO}Tela 1080x1920 (px). Seja específico e curto; nada de "talvez".{(chr(10) + 'Observação do João pra esta nova tentativa: ' + obs) if obs else ''}{(chr(10) + 'A tentativa anterior foi recusada: ' + erro + '. Corrija.') if erro else ''}"""


def _chamar_ia(id_: str, pasta_: Path, m: dict, transcricao: str, obs: str = "") -> dict:
    """Uma chamada (e uma segunda, só se a primeira vier inválida). Devolve o estilo validado ou levanta ValueError."""
    alvo = pasta_ / "estilo.json"
    s = {**ia.selecao(), "modelo": "sonnet"} if ia.selecao().get("provedor") == "claude" else ia.selecao()
    erro = ""
    for _tentativa in range(2):
        alvo.unlink(missing_ok=True)
        code = ia.executar(_prompt(id_, pasta_, m, transcricao, obs, erro), pasta_ / "execucao.log", pasta_ / "raw.jsonl",
                           pasta_ / "runner.pid", s, tipo="outro")
        try:
            if code or not alvo.is_file():
                raise ValueError("a IA não entregou o estilo.json")
            estilo = json.loads(alvo.read_text(encoding="utf-8"))
            validar(estilo)
            copia_proibida(estilo, transcricao)
            return estilo
        except (ValueError, OSError) as e:
            erro = str(e)[:400]
    raise ValueError(erro)


def _quadro_a_quadro(id_: str, pasta_: Path, video: Path) -> None:
    """O estudo padrão do Estúdio (estudo_quadros.py): planos, transições, câmera em todo quadro, fala, som, números e
    legenda, com regra de número e quadro de prova. Usa a fala já transcrita (não chama o Groq de novo). Nunca derruba a
    referência rápida: se falhar, fica o aviso."""
    try:
        import estudo_quadros
        words = None
        if (pasta_ / "words.json").is_file():
            js = {"words": ler_json(pasta_ / "words.json", []) or [], "segments": ler_json(pasta_ / "segmentos.json", []) or []}
            gravar_json(pasta_ / "fala-palavras.json", js)
            words = {str(video): str(pasta_ / "fala-palavras.json")}
        est = estudo_quadros.estudar([video], pasta_ / "quadros", nome=video.stem, transcrever_fala=False, words=words)
        _salvar(id_, quadros="quadros/ESTUDO-QUADROS.md", base_sugerida=est["conjunto"].get("base_sugerida", ""))
    except Exception as e:  # noqa: BLE001
        _salvar(id_, aviso_quadros=f"Estudo quadro a quadro falhou: {str(e)[:200]}")


def _regua_quadros(pasta_: Path) -> str:
    est = ler_json(pasta_ / "quadros" / "estudo.json", None)
    if not est:
        return ""
    try:
        import estudo_quadros
        base = est.get("conjunto", {}).get("base_sugerida") or "?"
        return (estudo_quadros.resumo_prompt(est, rel(pasta_ / "quadros")) +
                f"\nBase sugerida pelas medidas do quadro: {base}. " + REGRA_BASE + "\n")
    except Exception:  # noqa: BLE001
        return ""


REGRA_BASE = ("REGRA DE ESCOLHA DA BASE: referência de ANIMAÇÃO SEM PESSOA estilo cartoon (cabeção, cor chapada, contorno) → "
              "não há base pronta no catálogo (o Desenho 3D saiu em 29-out-2026): diga que falta base; animação 3D \"realista feia\" estilo jogo antigo (gente low-poly "
              "com rosto de foto, cenário denso, luz de cinema) → explicador-3d (formatos/explicador-3d/base); vídeo com pessoa "
              "gravada → um formato gravado.")


FORMATO_BAIXAR = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"


def _trabalhar(id_: str, fase: str = "tudo", obs: str = "") -> None:
    pasta_ = pasta(id_)
    st = estado(id_) or {}
    try:
        if fase == "tudo":
            _salvar(id_, estado="analisando", passo="Baixando e medindo o vídeo…")
            if st.get("link"):
                dst = pasta_ / "video.mp4"
                r = subprocess.run(["yt-dlp", "--print", "title", "--no-simulate", "-f", FORMATO_BAIXAR, "--merge-output-format", "mp4",
                                    "-o", str(dst), st["link"]], check=False, timeout=300, capture_output=True, text=True)
                if not dst.is_file():
                    _salvar(id_, detalhe=(r.stderr or "")[-400:])
                    raise ValueError("Não consegui baixar o link. Mande o arquivo do vídeo.")
                titulo = ((r.stdout or "").strip().splitlines() or [""])[-1][:80]
                if titulo:
                    _salvar(id_, titulo=titulo)
            video = video_de(id_)
            if not video or not formatos.e_video(video):
                raise ValueError("Isso não parece um vídeo. Mande um MP4 ou MOV.")
            m = medir(video, pasta_)
            _salvar(id_, passo="Ouvindo o que é dito…", medidas=m)
            if m.get("som"):
                txt, aviso, motivo = _transcricao(video, pasta_, st.get("cliente", ""))
            else:
                txt, aviso, motivo = "", "O vídeo veio sem som. Entendi só pelas imagens.", "sem áudio no arquivo"
            (pasta_ / "transcricao.txt").write_text(txt, encoding="utf-8")
            if aviso:
                _salvar(id_, aviso=aviso, detalhe_transcricao=motivo)
            _salvar(id_, passo="Estudando quadro a quadro…")
            _quadro_a_quadro(id_, pasta_, video)
        else:
            m = ler_json(pasta_ / "medidas.json", {}) or {}
            txt = (pasta_ / "transcricao.txt").read_text(encoding="utf-8") if (pasta_ / "transcricao.txt").is_file() else ""
        _salvar(id_, estado="analisando", passo="Entendendo o estilo…")
        estilo = _chamar_ia(id_, pasta_, m, txt, obs)
        _salvar(id_, estado="pronto", passo="", erro="", detalhe="")
        gravar_json(pasta_ / "estilo.json", estilo)
        if (estado(id_) or {}).get("auto"):
            try:
                import auto_juntar
                auto_juntar.referencia(id_)
            except Exception as e:  # noqa: BLE001  se não deu pra decidir, fica esperando o João (Esperando você)
                _salvar(id_, aviso_auto=f"Não consegui decidir sozinho: {str(e)[:160]}")
    except Exception as e:  # noqa: BLE001
        simples = str(e) if isinstance(e, ValueError) and len(str(e)) < 120 and "Estilo incompleto" not in str(e) \
            and "copia" not in str(e) and "estilo.json" not in str(e) else FRASE_ERRO
        _salvar(id_, estado="erro", passo="", erro=simples, detalhe=str(e)[:600])


def entender(video_ou_link, cliente: str = "", esperar: bool = False, gate: bool = False, conjunto: str = "", auto: bool = False, estilo_novo: bool = False) -> str:
    """Começa a entender a referência e devolve o id na hora. Roda numa thread (esperar=True só nos testes)."""
    fonte = str(video_ou_link or "").strip()
    if not fonte:
        raise ValueError("Mande um vídeo ou cole um link.")
    id_ = uuid.uuid4().hex[:12]
    d = ensure(pasta(id_))
    dados = {"id": id_, "cliente": cliente or "", "criado_em": agora(), "estado": "analisando", "passo": "Na fila…"}
    if gate:   # jogada pela tela: para e pede o "Aprovou?" (aparece em Esperando você até confirmar ou descartar)
        dados["gate"] = True
    if conjunto:
        dados["conjunto"] = conjunto
    if auto and not conjunto:   # o Estúdio decide o estilo sozinho e só avisa (auto_juntar.py); set decide no conjunto
        dados["auto"] = True
        if estilo_novo:   # "Criar estilo novo": nasce estilo mesmo que pareça com um que já existe
            dados["estilo_novo"] = True
    if _eh_link(fonte):
        dados["link"] = fonte
        dados["origem"] = fonte
    else:
        src = Path(fonte)
        if not src.is_file():
            raise ValueError("Não achei esse vídeo.")
        _clonar(src, d / ("video" + src.suffix.lower()))   # copia: nunca move o arquivo do João
        dados["origem"] = src.name
    gravar_json(d / "estado.json", dados)
    t = threading.Thread(target=_trabalhar, args=(id_,), daemon=True)
    t.start()
    if esperar:
        t.join()
    return id_


def refazer(id_: str, observacao: str = "", esperar: bool = False) -> None:
    """Nova leitura da IA (mantém medidas e transcrição), levando em conta a observação do João."""
    st = estado(id_)
    if not st or st.get("estado") == "confirmado":
        raise ValueError("Esta referência não pode ser refeita.")
    _salvar(id_, estado="analisando", passo="Entendendo de novo…", erro="")
    t = threading.Thread(target=_trabalhar, args=(id_, "ia", (observacao or "").strip()[:500]), daemon=True)
    t.start()
    if esperar:
        t.join()


# ───────────────────────────── confirmar ─────────────────────────────

def _estudo_respondido(texto: str, respostas: dict) -> str:
    """Preenche cada 'R:' do ESTUDO.md com a resposta da pergunta (mesma ordem de PERGUNTAS_ESTUDO)."""
    chaves = [k for k, _ in chaves_perguntas()]
    out, i = [], 0
    for linha in texto.splitlines():
        if re.match(r"^\s*R:\s*$", linha) and i < len(chaves):
            out.append("  R: " + str(respostas.get(chaves[i], "")).strip().replace("\n", " "))
            i += 1
        else:
            out.append(linha)
    return "\n".join(out) + "\n"


def referencia_repetida(slug: str, video: Path) -> str:
    """Nome da pasta de estudo (formatos/<slug>/estudos/NN-...) que já guarda exatamente este vídeo (mesmo tamanho e sha1), ou ''."""
    import hashlib
    base = formatos.FORMATOS / slug / "estudos"
    tam = Path(video).stat().st_size
    achados = [v for v in sorted(base.glob("*/video-*.*")) if v.is_file() and v.stat().st_size == tam] if base.is_dir() else []
    if not achados:
        return ""
    def sha(p: Path) -> str:
        h = hashlib.sha1()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()
    alvo = sha(Path(video))
    return next((v.parent.name for v in achados if sha(v) == alvo), "")


def confirmar(id_: str, formato_slug: str | None = None, nome: str = "", principal: bool = False) -> dict:
    """Guarda o estilo em formatos/<slug>/estudos/NN-<nome>/. Formato "novo": não cria sozinho; guarda o estilo e a tela oferece o botão "Criar este estilo novo"."""
    st = estado(id_)
    if not st or st.get("estado") != "pronto":
        raise ValueError("Esta referência ainda não está pronta.")
    estilo = estilo_de(id_)
    slug = (formato_slug or "").strip()
    if not slug:
        slug = estilo["formato_sugerido"]["slug"] if serve(estilo) else "novo"
    pasta_ = pasta(id_)
    if slug == "novo" or not formatos.carregar(slug):
        sugestao = make_slug(nome or st.get("origem", "") or "novo-estilo", 40)
        cmd = f"python3 app/ferramentas/formatos.py novo {sugestao} --gravado"
        _salvar(id_, guardado_para_novo=True, comando_novo=cmd)
        return {"ok": False, "novo": True, "comando": cmd, "pasta": rel(pasta_),
                "aviso": "Este estilo pede um formato novo. Guardei o estilo; o formato você decide criar."}
    video = video_de(id_)
    repetido = referencia_repetida(slug, video)
    if repetido:   # 30-out-2026: testes guardaram 05, 06 e 07 (os mesmos cortes) e a régua contaria a mesma referência duas vezes
        raise ValueError(f"Esse vídeo já está guardado no estilo ({repetido}). A régua não conta a mesma referência duas vezes.")
    m = ler_json(pasta_ / "medidas.json", {}) or {}
    nome = nome or Path(st.get("origem", "referencia")).stem or "referencia"
    copia = ensure(pasta_ / "_envio") / video.name
    _clonar(video, copia)   # adicionar_referencia MOVE o arquivo: dá uma cópia pra ele
    d = formatos.adicionar_referencia(slug, [copia], [st["link"]] if st.get("link") else [], nome)
    shutil.rmtree(copia.parent, ignore_errors=True)
    ex = {"arquivo": rel(d / f"video-1{video.suffix.lower()}"), "folha": ""}
    folha = pasta_ / m.get("folha", "folha.jpg")
    if folha.is_file():
        shutil.copy2(folha, d / "folha.jpg")
        ex["folha"] = rel(d / "folha.jpg")
    texto = formatos._texto_estudo(nome, ex, st.get("origem") or "referência rápida", m)
    (d / formatos.ESTUDO).write_text(_estudo_respondido(texto, estilo["estudo_respostas"]), encoding="utf-8")
    shutil.copy2(pasta_ / "estilo.json", d / "estilo.json")
    if (pasta_ / "quadros" / "estudo.json").is_file():   # o estudo quadro a quadro vai junto (a régua com número)
        shutil.copytree(pasta_ / "quadros", d / "estudo-quadros", dirs_exist_ok=True)
    if (pasta_ / "medidas.json").is_file():
        shutil.copy2(pasta_ / "medidas.json", d / "medidas.json")
    if principal:
        formatos.definir_principal(slug, d.name)
    _salvar(id_, estado="confirmado", formato=slug, estudo=rel(d), principal=bool(principal))
    return {"ok": True, "novo": False, "formato": slug, "pasta": rel(d)}


# ───────────────────────────── estudar formato pronto sem ESTUDO.md ─────────────────────────────

def estudar(slug: str) -> dict:
    """Roda `entender` no exemplo-1 do formato e grava o ESTUDO.md respondido. Nunca sobrescreve um ESTUDO.md existente
    com texto (só se não existir ou estiver em branco/vazio). Usa a IA da assinatura (~US$ 0,14); nada pago de kie/voz."""
    pasta_f = formatos.FORMATOS / str(slug or "")
    dados = ler_json(pasta_f / "formato.json", None) if slug and Path(slug).name == slug else None
    if not dados:
        raise ValueError(f"Formato não encontrado: formatos/{slug}/")
    est = pasta_f / formatos.ESTUDO
    if est.is_file() and est.read_text(encoding="utf-8").strip() and formatos.estudo_estado(slug) != "branco":
        return {"slug": slug, "feito": False, "motivo": "já tem ESTUDO.md respondido"}
    exs = [e for e in dados.get("exemplos") or [] if isinstance(e, dict) and e.get("arquivo")]
    if not exs or not (pasta_f / exs[0]["arquivo"]).is_file():
        raise ValueError(f"O formato {slug} não tem exemplo pra estudar.")
    ex = exs[0]
    id_ = entender(str(pasta_f / ex["arquivo"]), "Avulso", esperar=True)
    st = estado(id_) or {}
    if st.get("estado") != "pronto":
        raise ValueError(f"Não consegui estudar {slug}: {st.get('detalhe') or st.get('erro')}")
    estilo = estilo_de(id_)
    m = ler_json(pasta(id_) / "medidas.json", {}) or {}
    texto = formatos._texto_estudo(dados.get("titulo") or slug, ex, str(ex.get("origem") or ex["arquivo"]), m)
    est.write_text(_estudo_respondido(texto, estilo["estudo_respostas"]), encoding="utf-8")
    return {"slug": slug, "feito": True, "estilo": id_, "estudo": rel(est)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Referência rápida: estuda formatos prontos sem ESTUDO.md")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estudar").add_argument("slug", nargs="+")
    a = ap.parse_args()
    for sl in a.slug:
        try:
            print(json.dumps(estudar(sl), ensure_ascii=False))
        except ValueError as ex_:
            print(f"{sl}: {ex_}")
