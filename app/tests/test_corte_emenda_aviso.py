"""Recortar vídeo: o aviso de "emenda gaguejando" só aparece quando ainda há o que aparar (30-out-2026)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import corte

pal = lambda t0, t1, p: {"t0": t0, "t1": t1, "p": p}
PALAVRAS = [pal(0.0, 0.5, "Vou"), pal(0.5, 3.38, "falar"), pal(3.40, 3.46, "o"), pal(5.0, 5.1, "o"), pal(5.1, 6.0, "processo")]


class AvisoDeEmenda(unittest.TestCase):
    def test_cauda_ja_aparada_nao_avisa(self):
        # t1 = fim de "falar" + 0,06: o "o" do fim já saiu; a palavra de 60 ms na margem não pode acusar de novo
        lista = [{"i": 0, "t0": 0.0, "t1": 3.44, "manter": True}, {"i": 1, "t0": 5.0, "t1": 6.0, "manter": True}]
        self.assertEqual(corte.emendas_gaguejando(lista, PALAVRAS), [])

    def test_cauda_por_aparar_avisa_com_o_momento(self):
        lista = [{"i": 0, "t0": 0.0, "t1": 3.5, "manter": True}, {"i": 1, "t0": 5.0, "t1": 6.0, "manter": True}]
        achados = corte.emendas_gaguejando(lista, PALAVRAS)
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["t1"], 3.5)
        self.assertEqual(achados[0]["texto"], "o")

    def test_tela_em_portugues_simples(self):
        html = (Path(__file__).resolve().parents[1] / "interface/templates/corte_detalhe.html").read_text(encoding="utf-8")
        self.assertNotIn("gaguejando.</b>", html)
        self.assertNotIn("A proposta automática apara", html)
        self.assertIn("Perto de", html)


if __name__ == "__main__":
    unittest.main()
