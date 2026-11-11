"""Ajuste 1 do polimento-v2: produção em massa ponta a ponta."""
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
import lotes  # noqa: E402
import pendencias  # noqa: E402


def ler(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


class Polimento1(unittest.TestCase):
    def test_titulo_sem_prefixo_do_upload(self):
        self.assertEqual(re.sub(r"^[0-9a-f]{8}-", "", "a1b2c3d4-meu-video"), "meu-video")
        self.assertIn("re.sub(r'^[0-9a-f]{8}-'", ler("app/ferramentas/lotes.py"))

    def test_arquivo_invalido_nao_derruba(self):
        v2 = ler("app/interface/v2.py")
        self.assertNotIn("files=[upload(f,VIDEO_EXTS)", v2)
        self.assertIn("Pulei ", v2)

    def test_contagem_separa_aprovados(self):
        c = lotes.contagem({"cliente": "Nenhum", "jobs": []})
        self.assertEqual(set(c), {"fila", "esperando", "pra_ver", "aprovados"})

    def test_esperando_tem_tipo(self):
        for i in lotes.esperando():
            self.assertIn(i["tipo"], ("storyboard", "video") + tuple(pendencias.ROTULOS))

    def test_textos_e_classes(self):
        self.assertIn("img.storyboard", ler("app/interface/static/estilo.css"))
        self.assertIn("confira e aprove", ler("app/ferramentas/runner.py"))
        self.assertNotIn("A IA copia daquele trecho", ler("app/interface/templates/andamento_ver.html"))
        self.assertIn("Ver o passo anterior", ler("app/interface/templates/_andamento.html"))
        self.assertIn("opcoes_frase", ler("app/interface/templates/aprovar.html"))  # Frase fixa saiu (29-out); a opção segue na tela de aprovar

    def test_telas(self):
        sys.path.insert(0, str(RAIZ / "app" / "interface"))
        import servidor
        c = servidor.app.test_client()
        self.assertEqual(c.get("/aprovar").status_code, 200)
        self.assertEqual(c.get("/lotes").status_code, 200)
        for l in lotes.listar()[:3]:
            self.assertEqual(c.get("/lote/" + l["slug"]).status_code, 200)
        r = c.post("/novo-lote", data={"formato": "frase-fixa", "cliente": "Avulso"}, content_type="multipart/form-data")
        self.assertIn(r.status_code, (302, 200))
        import io
        r = c.post("/novo-lote", data={"formato": "frase-fixa", "cliente": "Avulso", "brutos": (io.BytesIO(b"x"), "a.txt")},
                   content_type="multipart/form-data")
        self.assertIn(r.status_code, (302, 200))   # .txt é pulado, não dá 500


if __name__ == "__main__":
    unittest.main()
