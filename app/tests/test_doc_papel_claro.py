"""Documentário: a exceção "estilo": {"papel_claro": false} do modelo do cliente.

O exemplo alterna papel claro e escuro (2 telas claras em 1:23) e o --conferir cobra isso. Cliente que recusou papel
claro (a Vegas recusou papel claro + azul na Cartilha) põe "papel_claro": false no estilo e a checagem sai, com o
motivo anotado nos números. Só lê o motor real (formatos/documentario/base); nada é gravado."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_grupo_1_motor_do_doc as G1   # noqa: E402  (só o motor e o cenas-modelo; os testes de lá não rodam aqui)

R, BASE, _modelo = G1.R, G1.BASE, G1._modelo


def _clara(motivos):
    return [m for m in motivos if "tela(s) clara(s)" in m]


class PapelClaro(unittest.TestCase):
    def setUp(self):
        base = _modelo()
        # 1:23 como o exemplo e nenhuma tela clara (o caderno no escuro)
        self.doc = {**base, "duracao": 82.8, "cenas": [dict(c, tom="escuro") if c["tipo"] == "caderno" else c
                                                       for c in base["cenas"]]}

    def test_sem_tela_clara_reprova(self):
        ch = R.checar(self.doc, BASE)
        self.assertTrue(_clara(ch["motivos"]), ch["motivos"])
        self.assertEqual(ch["numeros"]["telas_claras"], 0)
        self.assertNotIn("telas_claras_dispensadas", ch["numeros"])

    def test_cliente_que_recusou_papel_claro_nao_e_cobrado(self):
        doc = {**self.doc, "estilo": {**(self.doc.get("estilo") or {}), "papel_claro": False}}
        ch = R.checar(doc, BASE)
        self.assertEqual(_clara(ch["motivos"]), [])
        self.assertIn("papel_claro: false", ch["numeros"]["telas_claras_dispensadas"])

    def test_so_false_dispensa(self):
        for valor in (True, None, "nao", 0):
            with self.subTest(valor=valor):
                doc = {**self.doc, "estilo": {**(self.doc.get("estilo") or {}), "papel_claro": valor}}
                self.assertTrue(_clara(R.checar(doc, BASE)["motivos"]))


if __name__ == "__main__":
    unittest.main()
