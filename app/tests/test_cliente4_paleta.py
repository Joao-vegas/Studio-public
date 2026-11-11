import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


_P = Path(__file__).resolve().parents[2] / 'clientes/Cliente4/cliente4Content/modelos/dividido-mascara/paleta.py'


class PaletaCliente4(unittest.TestCase):
    @unittest.skipUnless(_P.is_file(), 'Cliente removido em 29-out-2026 (Cliente4 foi pra lixeira); teste sem base.')
    def test_ficha_editada_muda_cor_do_render(self):
        path = Path(__file__).resolve().parents[2] / 'clientes/Cliente4/cliente4Content/modelos/dividido-mascara/paleta.py'
        spec = importlib.util.spec_from_file_location('paleta_cliente4', path)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.assertEqual(modulo.destaque(), (4, 108, 73))
        with tempfile.TemporaryDirectory() as temp:
            ficha = Path(temp) / 'ficha.json'
            ficha.write_text(json.dumps({'paleta': [{'cor': '#123456', 'uso': 'palavra de destaque nos cards'}]}))
            self.assertEqual(modulo.destaque(ficha), (18, 52, 86))
            ficha.write_text('{"paleta": []}')
            with self.assertRaises(ValueError):
                modulo.destaque(ficha)
