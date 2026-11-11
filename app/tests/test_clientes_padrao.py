"""O padrão de cliente (identidade.json + <x>Content/{entrada,material,modelos,output,transcricoes}, sem .env,
README, automacao, documentacao nem banco-*) fica fixo: os 7 clientes de verdade estão dentro (só leitura), um
cliente criado por novo_cliente.criar nasce dentro, e a conferência pega cada desvio. Nada pago."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import _comum
import clientes_padrao as CP
import novo_cliente

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "app" / "ferramentas" / "clientes_padrao.py"


class ClientesReais(unittest.TestCase):
    def test_os_clientes_de_verdade_estao_no_padrao(self):
        res = CP.conferir_todos(RAIZ / "clientes")
        self.assertGreaterEqual(len(res), 5)  # 7 até 29-out-2026, quando Cliente7, Cliente8 e Cliente4 saíram
        fora = {n: d for n, d in res.items() if d}
        self.assertEqual(fora, {}, f"clientes fora do padrão: {fora}")

    def test_json_pela_linha_de_comando(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--json"], capture_output=True, text=True)
        dados = json.loads(r.stdout)
        self.assertTrue(dados["ok"], dados)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Joao", dados["clientes"])


class EmPastaTemporaria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "clientes").mkdir()
        for alvo in (novo_cliente, _comum):
            p = patch.object(alvo, "RAIZ", self.root)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.base = self.root / "clientes"

    def test_cliente_novo_nasce_no_padrao(self):
        novo_cliente.criar("Maria Teste")
        content = self.base / "MariaTeste" / "mariatesteContent"
        for sub in CP.PASTAS_CONTENT:
            self.assertTrue((content / sub / ".gitkeep").is_file(), sub)
        self.assertEqual(sorted(p.name for p in (self.base / "MariaTeste").iterdir()), ["identidade.json", "mariatesteContent"])
        self.assertEqual(CP.conferir(self.base / "MariaTeste"), [])
        self.assertEqual(CP.conferir_todos(self.base), {"MariaTeste": []})

    def test_pega_cada_desvio(self):
        novo_cliente.criar("Ana")
        c = self.base / "Ana"
        (c / ".env").write_text("X=1")
        (c / "README.md").write_text("x")
        (c / "automacao").mkdir()
        (c / "documentacao").mkdir()
        (c / "anaContent" / "banco-imagens").mkdir()
        (c / "anaContent" / "cortes.json").write_text("{}")
        (c / ".DS_Store").write_text("")       # lixo do macOS é tolerado
        texto = "\n".join(CP.conferir(c))
        for esperado in (".env", "README.md", "automacao", "documentacao", "anaContent/banco-imagens", "anaContent/cortes.json"):
            self.assertIn(esperado, texto)
        self.assertIn("acervo", texto)
        self.assertNotIn(".DS_Store", texto)

    def test_falta_identidade_ou_content(self):
        (self.base / "Vazio").mkdir()
        d = "\n".join(CP.conferir(self.base / "Vazio"))
        self.assertIn("identidade.json", d)
        self.assertIn("Content", d)

    def test_nome_ruim_e_duplicado_sao_recusados_e_nada_nasce(self):
        for ruim in ("", "   ", "..", "../fora", "a/b", "a\\b", ".oculto", "Ana!", "@@", "x" * 50):
            with self.subTest(nome=ruim), self.assertRaises(ValueError) as e:
                novo_cliente.criar(ruim)
            self.assertTrue(str(e.exception))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertFalse((self.root / "fora").exists())
        novo_cliente.criar("Carla")
        for igual in ("Carla", "carla", "CARLA"):
            with self.subTest(nome=igual), self.assertRaises(ValueError) as e:
                novo_cliente.criar(igual)
            self.assertIn("Já existe", str(e.exception))
        self.assertEqual([d.name for d in self.base.iterdir()], ["Carla"])

    def test_nome_com_acento_e_espaco(self):
        c = novo_cliente.criar("Ótica São João")
        self.assertEqual(c["nome"], "OticaSaoJoao")
        self.assertEqual(c["content"].name, "oticasaojoaoContent")
        self.assertEqual(CP.conferir(self.base / "OticaSaoJoao"), [])

    def test_portar_com_origem_inexistente_nao_deixa_cliente_pela_metade(self):
        with self.assertRaises(ValueError):
            novo_cliente.criar("Duda", portar="Ninguem/modelo")
        self.assertFalse((self.base / "Duda").exists())

    def test_completar_cria_so_o_que_falta_e_nao_mexe_no_resto(self):
        novo_cliente.criar("Eva")
        content = self.base / "Eva" / "evaContent"
        (content / "output" / ".gitkeep").unlink()
        (content / "output").rmdir()
        shutil.rmtree(content / "transcricoes")
        (content / "modelos" / "x").mkdir()
        (content / "modelos" / ".gitkeep").unlink()
        (content / "entrada" / "bruto.mp4").write_bytes(b"V")
        (content / "entrada" / ".gitkeep").unlink()
        antes = (content / "entrada" / "bruto.mp4").read_bytes()
        criadas = novo_cliente.completar_content(content)
        self.assertEqual(sorted(c.split("/")[-2] for c in criadas), ["output", "transcricoes"])
        self.assertFalse((content / "modelos" / ".gitkeep").exists(), "pasta com coisa dentro não é mexida")
        self.assertFalse((content / "entrada" / ".gitkeep").exists())
        self.assertEqual((content / "entrada" / "bruto.mp4").read_bytes(), antes)
        self.assertEqual(novo_cliente.completar_content(content), [], "segunda vez não cria nada")
        self.assertEqual(CP.conferir(self.base / "Eva"), [])

    def test_pastas_do_content_podem_faltar_mas_nao_sobrar(self):
        novo_cliente.criar("Bia")
        shutil.rmtree(self.base / "Bia" / "biaContent" / "output")   # pasta que faltar não é desvio
        self.assertEqual(CP.conferir(self.base / "Bia"), [])
        (self.base / "Bia" / "biaContent" / "rascunhos").mkdir()
        self.assertEqual(len(CP.conferir(self.base / "Bia")), 1)


if __name__ == "__main__":
    unittest.main()
