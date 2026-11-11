"""Modelo + esforço no mesmo componente (Novo vídeo, Editar vídeo) e o menu lateral recolhível."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))


class ModeloForca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from servidor import app
        app.testing = True
        cls.c = app.test_client()

    def test_dados_tem_os_tres_claude_e_os_cinco_niveis(self):
        import modelo_forca as m
        d = m.dados(gpt=False)
        self.assertEqual([x["v"] for x in d["modelos"]], ["opus", "sonnet", "haiku"])
        self.assertEqual([n["v"] for n in d["niveis"]], ["low", "medium", "high", "xhigh", "max"])
        self.assertEqual([n["pt"] for n in d["niveis"]], ["Rápido", "Bom", "Forte", "Muito forte", "Ultra"])
        self.assertEqual((d["padrao"]["modelo"], d["padrao"]["esforco"]), ("sonnet", "high"))
        self.assertFalse(d["gpt"])

    def test_gpt_so_se_o_codex_existe(self):
        import ia
        import modelo_forca as m
        antes = ia.codex_bin
        try:
            ia.codex_bin = lambda: None
            self.assertFalse(m.dados(gpt=True)["gpt"])
            ia.codex_bin = lambda: "/bin/codex"
            d = m.dados(gpt=True)
            if d["gpt"]:
                self.assertTrue(d["modelos"][-1]["v"].startswith("gpt:"))
                self.assertTrue(set(d["modelos"][-1]["esforcos"]) <= set(m.ORDEM))
        finally:
            ia.codex_bin = antes

    def test_novo_video_usa_o_componente_com_os_mesmos_campos(self):
        h = self.c.get("/criar-agora").get_data(as_text=True)
        for t in ('data-mf', 'name="ia_modelo"', 'name="ia_esforco"', 'value="sonnet"', 'value="high"', "modelo-forca.js", 'id="nv-exemplos"', "O que o vídeo fala", "Como ele aparece"):
            self.assertIn(t, h, t)
        self.assertIn('id="nav-toggle"', h)
        self.assertIn('data-foco="1"', h)

    def test_editar_video_troca_os_dois_selects_pelo_componente(self):
        import editor as _ed
        import re
        pastas = [m.group(1) for m in re.finditer(r'href="/editar/video\?pasta=([^"]+)"', self.c.get("/editar").get_data(as_text=True))]
        if not pastas:
            self.skipTest("nenhum vídeo editável neste Mac")
        h = self.c.get("/editar/video?pasta=" + pastas[0]).get_data(as_text=True)
        self.assertIn('data-mf', h)
        self.assertIn('name="modelo"', h)
        self.assertIn('name="esforco"', h)
        self.assertNotIn('<select name="esforco"', h)
        self.assertNotIn('<select name="modelo"', h)

    def test_menu_comum_nao_abre_fino_sozinho(self):
        h = self.c.get("/").get_data(as_text=True)
        self.assertNotIn('data-foco="1"', h)
        self.assertIn("estudio-nav", h)

    def test_post_gpt_vira_provedor_openai(self):
        src = (Path(__file__).resolve().parents[1] / "interface" / "simples.py").read_text(encoding="utf-8")
        self.assertIn('startswith("gpt:")', src)


if __name__ == "__main__":
    unittest.main()
