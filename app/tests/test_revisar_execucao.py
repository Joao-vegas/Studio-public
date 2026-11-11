"""Confirmação de etapa: uma linha com estimativa tirada do histórico, sem o texto de "pode consumir tokens" (30-out-2026)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
P = fixtures.P


class RevisarExecucao(unittest.TestCase):
    job = fixtures.Isolado.job

    def setUp(self):
        fixtures.Isolado.setUp(self)

    def test_estimativa_sai_do_historico_e_da_cobranca(self):
        j = self.job(status='plano')
        j['execucoes'] = [{'tipo': 'analise', 'inicio': '2026-10-30 10:00:00', 'fim': '2026-10-30 10:05:10', 'exit': '0', 'custo_usd': '0.66'},
                          {'tipo': 'analise', 'inicio': '2026-10-30 11:00:00', 'fim': '2026-10-30 11:04:50', 'exit': '0', 'custo_usd': '0.60'},
                          {'tipo': 'analise', 'inicio': '2026-10-30 12:00:00', 'fim': '2026-10-30 12:00:06', 'exit': '1', 'custo_usd': '0'}]
        P.salvar(j)
        with patch('ia.cobranca', return_value='assinatura'):
            self.assertEqual(P.estimativa_etapa('analise'), 'leva uns 5 min · sai da sua assinatura')
        with patch('ia.cobranca', return_value='api'):
            self.assertEqual(P.estimativa_etapa('analise'), 'leva uns 5 min · sai do crédito da API (uns US$ 0,63)')
        with patch('ia.cobranca', return_value='assinatura'):
            self.assertEqual(P.estimativa_etapa('previas'), 'leva alguns minutos · sai da sua assinatura')

    def test_tela_de_confirmacao_sem_texto_tecnico(self):
        j = self.job(status='plano')
        r = self.client.post(f"/job/{j['cliente']}/{j['slug']}/analisar", data={'usar_broll': '0'})
        h = r.get_data(as_text=True)
        self.assertIn('Confirmar e executar', h)
        self.assertNotIn('não há estimativa', h)
        self.assertNotIn('pode consumir tokens', h)
        self.assertRegex(h, r'(Leva|leva) (uns \d+ min|alguns minutos|menos de 1 min) · sai d')


if __name__ == '__main__':
    unittest.main()
