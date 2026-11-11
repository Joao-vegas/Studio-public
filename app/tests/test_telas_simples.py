"""Telas simples (Referências numa porta só, página do estilo, Biblioteca): rotas antigas redirecionam, o menu tem UMA
entrada de referências, o estilo explica como as referências são usadas e os números viram frase."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import frase_estilo as fe
import storyboard_estilo as sbe
import servidor


class Telas(unittest.TestCase):
    def setUp(self):
        servidor.app.config["TESTING"] = True
        self.c = servidor.app.test_client()

    def test_rotas_antigas_redirecionam_pra_referencias(self):
        for u in ("/referencia-rapida", "/estudar"):
            r = self.c.get(u)
            self.assertEqual(r.status_code, 302, u)
            self.assertIn("/referencias", r.headers["Location"])

    def test_menu_tem_uma_entrada_de_referencias(self):
        html = self.c.get("/referencias").get_data(as_text=True)
        self.assertNotIn("Jogar uma referência", html)
        self.assertNotIn("Estudar um vídeo", html)
        self.assertIn("Jogar um vídeo", html)
        self.assertIn('id="jogar"', html)

    def test_paginas_dao_200(self):
        for u in ("/referencias", "/acervo", "/acervo?tipo=imagem", "/acervo?tipo=musica", "/acervo?tipo=sfx", "/formatos", "/formato/editorial"):
            self.assertEqual(self.c.get(u).status_code, 200, u)

    def test_estilo_explica_as_referencias(self):
        html = self.c.get("/formato/editorial").get_data(as_text=True)
        self.assertIn("Como as referências são usadas", html)
        self.assertIn("mistura leve", html)
        self.assertIn("Usar como principal", html)
        self.assertNotIn("Estilos salvos", html)

    def test_biblioteca_abre_em_videos_com_duas_acoes(self):
        html = self.c.get("/acervo").get_data(as_text=True)
        self.assertIn("Buscar (grátis)", html)
        self.assertIn("Gerar com IA (pago, com o preço antes)", html)
        self.assertIn("Vídeos", html)
        self.assertIn("Efeitos", html)


class Frases(unittest.TestCase):
    def test_ritmo_em_frase(self):
        self.assertEqual(fe.ritmo(1), "corte rápido (troca a cada ~1,0 s)")
        self.assertTrue(fe.ritmo(2.5).startswith("ritmo médio"))
        self.assertTrue(fe.ritmo(8).startswith("ritmo calmo"))
        self.assertEqual(fe.ritmo(None), "")

    def test_frase_da_referencia(self):
        t = fe.da_referencia({"ritmo": {"corte_a_cada_s": 1}, "legenda": {"palavras_por_vez": 1}, "som": {"musica": True}})
        self.assertIn("Corte rápido", t)
        self.assertIn("legenda de 1 palavra por vez", t)
        self.assertIn("com música", t)
        self.assertEqual(fe.da_referencia({}), "")

    def test_numeros_do_ritmo_viram_frase(self):
        fr = sbe.frases_do_ritmo({"media_s": 1.0, "por_min": 56}, {"pct_quadros_andando": 80})
        self.assertEqual(fr[0], "Corte rápido: troca de imagem a cada ~1,0 s")
        self.assertIn("câmera", fr[1])
        self.assertEqual(sbe.frases_do_ritmo({}, {}), [])


if __name__ == "__main__":
    unittest.main()
