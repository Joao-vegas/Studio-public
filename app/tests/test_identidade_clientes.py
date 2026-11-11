"""Todo cliente tem o seu identidade.json, no mesmo formato do Cliente4."""
import json
import re
import unittest
from pathlib import Path

CLIENTES = Path(__file__).resolve().parents[2] / "clientes"
# Confere todo cliente que existe na pasta clientes/ (no repositório público vem só o Avulso de exemplo).
NOMES = sorted(p.name for p in CLIENTES.iterdir() if (p / "identidade.json").exists()) if CLIENTES.exists() else []
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
CHAVES = {"cliente", "fonte", "cores", "papeis", "uso", "fontes"}


class IdentidadeClientes(unittest.TestCase):
    def carregar(self, nome):
        caminho = CLIENTES / nome / "identidade.json"
        self.assertTrue(caminho.exists(), f"{nome}: falta identidade.json")
        return json.loads(caminho.read_text(encoding="utf-8"))

    def test_cada_cliente(self):
        for nome in NOMES:
            with self.subTest(cliente=nome):
                d = self.carregar(nome)
                self.assertEqual(set(d) - {"palavras", "voz"}, CHAVES)   # opcionais: "palavras" (vocabulário pro Groq, G5) e "voz" (perfil da narração, voz.voz_do_cliente)
                self.assertEqual(d["cliente"], nome)
                self.assertTrue(d["cores"])
                for cor in d["cores"]:
                    self.assertRegex(cor, HEX)
                self.assertTrue(d["papeis"])
                for papel, cor in d["papeis"].items():
                    self.assertRegex(cor, HEX, f"{nome}.{papel}")
                for chave in ("fonte", "uso", "fontes"):
                    self.assertIsInstance(d[chave], str)
                    self.assertTrue(d[chave].strip())


if __name__ == "__main__":
    unittest.main()
