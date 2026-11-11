"""Aba Custos: vídeo ao vivo (sem duplicar), voz Gemini só é "paga" com prova, 60 dias com arquivo morto. Nada toca nos livros reais."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import custos as C

AGORA = datetime.now().replace(microsecond=0)
F = "%Y-%m-%d %H:%M:%S"


def linha_voz(minutos_atras, ent=200, sai=500, chave="", gaveta="estimado", usd=0.005):
    nome = {"gratis": "Voz Gemini (cota grátis)", "pago": "Voz Gemini (conta paga)"}.get(gaveta, "Voz Gemini (cobrança não confirmada)")
    return {"data": AGORA - timedelta(minutes=minutos_atras), "gaveta": gaveta, "servico": nome, "usd": 0.0 if gaveta == "gratis" else usd,
            "oque": "x", "projeto": "-", "ent": ent, "sai": sai, "chave": chave}


class Livro(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [patch.object(C, n, v) for n, v in (
            ("PASTA", self.tmp), ("LIVRO", self.tmp / "execucoes.jsonl"), ("VIDEOS", self.tmp / "videos.jsonl"),
            ("GEMINI_USO", self.tmp / "gemini_uso.jsonl"), ("ARQUIVO", self.tmp / "arquivo"), ("CACHE_CCUSAGE", self.tmp / "cache"),
            ("_do_cerebro", lambda ini=None: []), ("_da_kie", lambda ini=None: []))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_job_do_app_ao_vivo(self):
        ini = (AGORA - timedelta(minutes=3)).strftime(F)
        job = {"slug": "j1", "cliente": "Joao", "titulo": "Meu vídeo", "formato": "x",
               "execucoes": [{"tipo": "analise", "inicio": ini, "fim": None, "ia": {"provedor": "claude"}}]}
        C.registrar_video_job(job, "em produção")
        job["execucoes"][0].update(fim=AGORA.strftime(F), custo_usd=0.4, tokens={"output_tokens": 900})
        C.registrar_video_job(job, "em produção")
        C.registrar_video_job(job, "pronto")
        linhas = C.ler_jsonl(C.VIDEOS)
        self.assertEqual((len(linhas), linhas[0]["status"], linhas[0]["tabela_usd"]), (1, "pronto", 0.4))
        ini2 = (AGORA + timedelta(seconds=30)).strftime(F)   # ajuste depois de pronto = V2, sem mexer na V1
        job["execucoes"].append({"tipo": "feedback", "inicio": ini2, "fim": None, "ia": {"provedor": "claude"}})
        C.registrar_video_job(job, "em produção")
        self.assertEqual([(l["versao"], l["status"]) for l in C.ler_jsonl(C.VIDEOS)], [("V1", "pronto"), ("V2", "em produção")])

    def test_voz_gemini_so_e_paga_com_prova(self):
        d = AGORA - timedelta(minutes=2)
        with patch.object(C, "_ler_livro", lambda caminho, nome, ini: [
                {"data": d.strftime(F), "chave": "chave 6", "entrada": 200, "saida": 500},
                {"data": d.strftime(F), "chave": "chave 2", "entrada": 210, "saida": 510},
                {"data": d.strftime(F), "chave": "chave 7", "entrada": 220, "saida": 520}]):
            idx = C._indice_chaves_gemini(None)
        got = [C.CHAVES_GEMINI.get(C._chave_do_pedido(idx, d, e, s), "?") for e, s in ((200, 500), (210, 510), (220, 520), (230, 530))]
        self.assertEqual(got, ["pago", "gratis", "?", "?"])   # chave 7 e pedido sem anotação NÃO viram pagos
        self.assertEqual(C._chave_do_pedido(idx, d, 200, 500), "")   # cada anotação casa só uma vez

    def test_itens_de_separa_pago_estimado_gratis(self):
        itens = C._itens_de([linha_voz(1, gaveta="gratis"), linha_voz(2, gaveta="estimado"), linha_voz(3, gaveta="pago")])
        tipos = {i["servico"]: i["tipo"] for i in itens}
        self.assertEqual(tipos, {"Voz Gemini (cota grátis)": "gratis", "Voz Gemini (cobrança não confirmada)": "estimado", "Voz Gemini (conta paga)": "pago"})
        somas = C._somas(itens)
        self.assertEqual((somas["pago_usd"], somas["estimado_usd"]), (0.005, 0.005))

    def test_linha_antiga_com_voz_paga_vira_estimada(self):
        v = {"itens": [{"servico": "Voz (Gemini)", "tipo": "pago", "usd": 0.019, "detalhe": "9 pedidos"}], "status": "pronto", "data": AGORA.strftime(F)}
        r = C._ajustar_versao(v, [], AGORA)
        self.assertEqual((r["pago_usd"], r["estimado_usd"]), (0, 0.019))

    def test_60_dias_vao_pro_arquivo_morto_sem_apagar(self):
        velho = (AGORA - timedelta(days=75)).strftime(F)
        C.append_jsonl(C.VIDEOS, {"projeto": "A", "slug": "a", "cliente": "", "formato": "", "versao": "V1", "data": velho, "itens": [], "tabela_usd": 1, "pago_usd": 0})
        C.append_jsonl(C.VIDEOS, {"projeto": "B", "slug": "b", "cliente": "", "formato": "", "versao": "V1", "data": AGORA.strftime(F), "itens": [], "tabela_usd": 2, "pago_usd": 0})
        (self.tmp / "cache").mkdir()
        cache = self.tmp / "cache" / "ccusage_velho.json"
        cache.write_text("{}")
        import os
        os.utime(cache, (AGORA.timestamp() - 70 * 86400,) * 2)
        self.assertEqual(C.podar(forcar=True), 2)
        self.assertEqual([l["slug"] for l in C.ler_jsonl(C.VIDEOS)], ["b"])
        arq = C.ler_jsonl(C.ARQUIVO / f"{velho[:7]}.jsonl")
        self.assertEqual([l["slug"] for l in arq], ["a"])
        self.assertTrue((C.ARQUIVO / "cache" / "ccusage_velho.json").exists())
        # a página só abre o arquivo morto quando o período pedido é antigo
        self.assertEqual([l["slug"] for l in C._ler_livro(C.VIDEOS, "videos", AGORA - timedelta(days=7))], ["b"])
        self.assertEqual(sorted(l["slug"] for l in C._ler_livro(C.VIDEOS, "videos", None)), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
