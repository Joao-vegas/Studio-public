"""Repositórios e motores (29-out-2026): todo item do MANIFESTO tem cartão, o Remotion global saiu e o INVENTARIO existe."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
import atualizar as U
import repositorios as R


class TestRepositorios(unittest.TestCase):
    def test_todo_item_do_manifesto_tem_cartao(self):
        nomes = {r["nome"] for r in R.REGISTRO}
        for i in U.MANIFESTO:
            self.assertIn(i["nome"], nomes, f"{i['nome']} está em Atualizações mas sem cartão em Repositórios e motores")

    def test_cartao_tem_serve_usado_origem(self):
        for r in R.REGISTRO:
            self.assertTrue(r["serve"] and r["usado"], r["nome"])
            self.assertTrue(r["origem"].startswith("https://"), r["nome"])

    def test_cartoes_montam_com_estado_dado(self):
        c = R.cartoes({"itens": [{"nome": "Flask", "versao": "3.1.3", "nova": "", "estado": "em dia", "tipo": "pip"}]})
        flask = next(x for x in c if x["nome"] == "Flask")
        self.assertEqual((flask["versao"], flask["situacao"]), ("3.1.3", "em dia"))
        self.assertEqual(len(c), len(R.REGISTRO))
        estudio = next(x for x in c if x["nome"] == "Estúdio (este)")
        self.assertIn("Joao-vegas/Studio", estudio["origem"])

    def test_remotion_global_aposentado(self):
        self.assertFalse((RAIZ / "app/motores/remotion").exists(), "o Remotion global foi pro backup em 29-out-2026")
        self.assertNotIn("Remotion", {i["nome"] for i in U.MANIFESTO})
        self.assertIn("Mundo 3d", next(r for r in R.REGISTRO if r["nome"].startswith("Remotion"))["usado"])

    def test_get_brolls_explica_que_e_de_outro_autor(self):
        gb = next(r for r in R.REGISTRO if r["nome"] == "get-brolls")
        self.assertIn("engenheirodevideo", gb["origem"])
        self.assertIn("fork", gb["nota"])

    def test_inventario_e_regra_de_motor_escritos(self):
        self.assertTrue((RAIZ / "app/motores/INVENTARIO.md").exists())
        self.assertIn("HTML próprio", (RAIZ / "CLAUDE.md").read_text(encoding="utf-8").split("## Qual motor")[1][:1500])


if __name__ == "__main__":
    unittest.main()
