"""Polimento v2, volta 10: erro 500 em português, estilo pronto nunca oculto, favorita respeita a janela, Hoje com origem,
barra sem etapa fantasma, título e formato do Em andamento."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import andamento  # noqa: E402
import custos  # noqa: E402
import formatos  # noqa: E402
import musica_busca  # noqa: E402


class Erro500(unittest.TestCase):
    def test_500_em_portugues(self):
        import servidor
        app = servidor.app
        app.config["PROPAGATE_EXCEPTIONS"] = False

        def explode():
            raise RuntimeError("boom")
        with mock.patch.dict(app.view_functions, {"home": explode}):
            r = app.test_client().get("/")
        self.assertEqual(r.status_code, 500)
        self.assertIn("Algo deu errado", r.get_data(as_text=True))
        self.assertNotIn("Internal Server Error", r.get_data(as_text=True))


class Catalogo(unittest.TestCase):
    def test_pronto_nunca_e_oculto(self):
        ruins = [f["slug"] for f in formatos.listar(ocultos=True) if f.get("status") == "pronto" and f.get("oculto")]
        self.assertEqual(ruins, [])


class FavoritaNaJanela(unittest.TestCase):
    def _rodar(self, usados):
        def item(slug, fonte="biblioteca"):
            return {"slug": slug, "arquivo": f"{slug}.mp3", "fonte": fonte, "motivo": ""}
        cands = [item("fav"), item("nova1"), item("nova2")]
        rec = [{"chave": s, "job": "x"} for s in usados]
        with mock.patch("uso_midia.recentes", return_value=rec), mock.patch("uso_midia.contagem_geral", return_value={}), \
                mock.patch("acervo.favoritos", return_value=[{"slug": "fav"}]), \
                mock.patch.object(musica_busca, "_chave_do_item", lambda it: it["slug"]), \
                mock.patch.object(musica_busca, "_nota", lambda it, clima: 0), \
                mock.patch.object(musica_busca, "reprovadas", return_value=(set(), set())), \
                mock.patch.object(musica_busca, "usadas_recentemente", return_value=[]):
            return [c["slug"] for c in musica_busca._rodizio(cands, "musica", "Cli", "", 1, "job1")]

    def test_favorita_usada_recentemente_perde_pra_faixa_nova(self):
        self.assertNotEqual(self._rodar(["fav"]), ["fav"])

    def test_favorita_sem_uso_recente_sai_primeiro(self):
        self.assertEqual(self._rodar([]), ["fav"])


class HojeComOrigem(unittest.TestCase):
    def test_duas_filas_hoje_e_uma_ontem(self):
        agora = datetime.now()
        if agora.day == 1:
            self.skipTest("sem 'ontem' dentro do mês")
        def lin(dt, fila, usd):
            return {"data": dt, "gaveta": "pago", "servico": "Claude API", "usd": usd, "api": True, "fila": fila}
        todas = [lin(agora, "polimento-v2", 2.0), lin(agora, "versao-2", 1.0), lin(agora - timedelta(days=1), "api", 4.0)]
        with mock.patch.object(custos, "_do_estudio", return_value=todas), mock.patch.object(custos, "_da_api", return_value=[]), \
                mock.patch.object(custos, "_do_cerebro", return_value=[]), mock.patch.object(custos, "_da_kie", return_value=[]):
            v = custos.visao()
        self.assertEqual(dict(v["hoje"]["filas"]), {"polimento-v2": 2.0, "versao-2": 1.0})
        self.assertEqual(v["hoje"]["fora_de_fila"], 0)
        self.assertEqual(v["dias_antes"], f"{(agora - timedelta(days=1)).day:02d}")
        self.assertIn("Chamadas avulsas pela API", [f["fila"] for f in v["filas"]])


class EmAndamento(unittest.TestCase):
    def test_etapa_pulada_nao_aparece(self):
        etapas = [{"id": "a", "titulo": "A", "estado": "pronto"}, {"id": "b", "titulo": "B", "estado": "aguardando"},
                  {"id": "c", "titulo": "C", "estado": "pronto"}]
        d = {"estado": "pronto"}
        with mock.patch("pipeline.etapas", return_value=etapas):
            andamento._barra_pelo_pipeline(d, {"x": 1})
        self.assertEqual([e["id"] for e in d["barra"]], ["a", "c"])

    def test_titulo_bonito_e_formato_pela_pasta(self):
        d = {"cliente": "Avulso", "slug": "bruto-teste-2", "titulo": "bruto-teste-2", "formato": "",
             "pasta": "clientes/Avulso/avulsoContent/modelos/caixinha-de-perguntas/_sandbox-x", "passos": [],
             "inicio": "2026-10-22 10:00:00", "atualizado": "2026-10-22 10:00:00", "estado": "pronto"}
        d = andamento._enfeitar(d)
        self.assertEqual(d["titulo"], "Bruto teste 2")
        self.assertEqual(d["formato"], "caixinha-de-perguntas")
        self.assertEqual(d["tempo_total"], "")


if __name__ == "__main__":
    unittest.main()
