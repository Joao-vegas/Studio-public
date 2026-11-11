import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))


class QuebraEquilibrada(unittest.TestCase):
    def test_sem_palavra_sozinha(self):
        from PIL import Image, ImageDraw, ImageFont
        import camada
        d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        fonte = ImageFont.truetype(str(camada.PASTA_FONTES / camada.FONTES[camada.PADRAO["fonte"]]), 60)
        linhas = camada._quebrar(d, "O erro que quase todo mundo comete", fonte, 860)
        self.assertEqual(len(linhas), 2)
        self.assertTrue(all(len(l.split()) > 1 for l in linhas), linhas)


class MeusVideosLink(unittest.TestCase):
    def test_link_vai_pro_andamento_quando_ha_registro(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
        import servidor
        from unittest.mock import patch
        import andamento as A
        j = {"cliente": "Avulso", "slug": "v1", "titulo": "V", "status": "pronto", "criado_em": "2026-10-22", "formato": "x"}
        with patch.object(A, "carregar", lambda c, s: {"id": "x"}), patch("producao.listar", lambda q=None: [j]), \
                patch("producao.reconciliar", lambda *a, **k: None), patch("andamento.listar", lambda: []):
            html = servidor.app.test_client().get("/videos").get_data(as_text=True)
        self.assertIn("/andamento/Avulso/v1", html)


if __name__ == "__main__":
    unittest.main()
