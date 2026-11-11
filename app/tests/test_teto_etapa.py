"""Teto de gasto por etapa: o comando do claude leva o --max-budget-usd do tipo; o job mostra a frase simples. Não chama o claude."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import ia
import runner

SEL = {'provedor': 'claude', 'modelo': 'sonnet', 'esforco': 'medium', 'ultra_mode': False}


def teto(cmd):
    return cmd[cmd.index('--max-budget-usd') + 1] if '--max-budget-usd' in cmd else None


class Teto(unittest.TestCase):
    def cmd(self, tipo, cfg):
        with patch.object(ia, 'config', return_value=cfg), patch.object(ia, 'claude_bin', return_value='/bin/claude'):
            return ia.comando(SEL, tipo)

    def test_padrao_sem_chave_no_config(self):
        self.assertEqual(teto(self.cmd('analise', {})), '2.0')
        self.assertEqual(teto(self.cmd('producao', {})), '1.0')
        self.assertEqual(teto(self.cmd('previas', {})), '0.5')
        self.assertEqual(teto(self.cmd('takes', {})), '1.0')   # tipo sem teto próprio usa 'outro'

    def test_config_manda(self):
        self.assertEqual(teto(self.cmd('analise', {'teto_usd_etapa': {'analise': 3.5}})), '3.5')
        self.assertIsNone(teto(self.cmd('analise', {'teto_usd_etapa': {'analise': 0}})))

    def test_sem_tipo_sem_teto(self):
        self.assertIsNone(teto(self.cmd(None, {})))

    def test_frase_simples_no_job(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'a.log'
            log.write_text('Sessão iniciada\n✖ ' + ia.AVISO_TETO.format(2.0) + '\n✖ Exceeded USD budget\n')
            self.assertEqual(runner._teto_da_etapa(log), ia.AVISO_TETO.format(2.0))
            log.write_text('tudo certo\n')
            self.assertEqual(runner._teto_da_etapa(log), '')


if __name__ == '__main__':
    unittest.main()
