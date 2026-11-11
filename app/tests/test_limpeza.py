"""Limpeza de 09-out: código morto na lixeira, _norm numa cópia só e motores que não quebram se o Cérebro mudar de lugar."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
import _comum
import corte
import fala


class Limpeza(unittest.TestCase):
    def test_codigo_morto_na_lixeira(self):
        for nome, antes in (('_catalogo_inicial.py', 'app/ferramentas'), ('home.html', 'app/interface/templates')):
            self.assertFalse((RAIZ / antes / nome).exists())
            self.assertTrue((RAIZ / 'app/.lixeira/codigo-morto-2026-10' / nome).exists())

    def test_norm_uma_copia_so(self):
        self.assertIs(fala._norm, _comum._norm)
        self.assertIs(corte._norm, _comum._norm)
        self.assertEqual(_comum._norm('Ação, É!'), 'acao  e ')


if __name__ == '__main__':
    unittest.main()
