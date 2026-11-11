"""O bloco "O que ele usa e quanto custa": lista declarada no formato.json, reserva genérica e a chave "total"."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import formatos

DECLARADOS = ("fala-com-cenas", "tela-dividida", "pessoa-no-cantinho", "documentario")


class Previsao(unittest.TestCase):
    def test_formatos_do_catalogo_declaram_o_que_usam(self):
        for slug in DECLARADOS:
            f = formatos.carregar(slug)
            self.assertTrue(formatos._usos_declarados(f), slug)
            self.assertEqual(len(formatos._usos_declarados(f)), len(f["usa"]), f"{slug}: item incompleto ou tipo inválido")
            self.assertTrue(f.get("estimativa"), slug)
            p = formatos.previsao(slug)
            self.assertEqual(p["usa"][0][0], "Edição e conferência (IA)")
            self.assertTrue(all(len(u) == 3 and u[2] in formatos.TIPOS_USO for u in p["usa"]), slug)
            self.assertIn("Pago de verdade", p["total"])

    def test_pago_declarado_entra_no_total(self):
        usa = [{"oque": "Fotos por API", "quem": "Z-Image na kie.ai", "tipo": "pago", "usd": 0.06}, {"oque": "Montagem", "quem": "ffmpeg", "tipo": "gratis"}]
        with patch.object(formatos, "carregar", return_value={"entrada": "roteiro", "motor": "HTML", "usa": usa}):
            p = formatos.previsao("qualquer")
        self.assertEqual(p["pago_minimo"], 0.0)
        self.assertEqual(p["pago_tipico"], 0.06)
        self.assertIn("US$ 0,06", p["total"])

    def test_sem_usa_cai_na_lista_generica(self):
        with patch.object(formatos, "carregar", return_value={"entrada": "roteiro", "motor": "HTML"}):
            p = formatos.previsao("qualquer")
        nomes = [u[0] for u in p["usa"]]
        self.assertIn("Narração", nomes)
        self.assertIn("Cenas geradas por IA", nomes)
        self.assertIn("total", p)

    def test_item_invalido_e_ignorado(self):
        f = {"entrada": "video", "usa": [{"oque": "Bom", "quem": "x", "tipo": "gratis"},
                                          {"oque": "Sem tipo", "quem": "x"},
                                          {"oque": "Tipo ruim", "quem": "x", "tipo": "talvez"}, "lixo"]}
        with patch.object(formatos, "carregar", return_value=f):
            p = formatos.previsao("x")
        self.assertEqual([u[0] for u in p["usa"]], ["Edição e conferência (IA)", "Bom"])


if __name__ == "__main__":
    unittest.main()
