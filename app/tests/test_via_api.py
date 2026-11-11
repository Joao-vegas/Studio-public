"""Fila da API: retoma de onde parou, marca incompleta, divide o teto e limpa órfãs. Não chama o claude."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import via_api


def tarefa(nome, orc=4):
    return {'nome': nome, 'modelo': 'sonnet', 'orcamento_usd': orc, 'prompt': 'faça'}


class Fila(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.chamadas = []

    def tearDown(self):
        self.tmp.cleanup()

    def falso(self, usd=1.0, estado='ok'):
        def rodar(pasta, t, orc=None):
            self.chamadas.append((t['nome'], orc))
            pasta.mkdir(parents=True, exist_ok=True)
            out = {'nome': t['nome'], 'estado': estado, 'usd': usd}
            (pasta / 'custo.json').write_text(json.dumps(out))
            return out
        return rodar

    def fila(self, etapas, teto=50, refazer=()):
        arq = self.base / 'fila.json'
        arq.write_text(json.dumps({'teto_usd': teto, 'etapas': etapas}))
        with patch.object(via_api, 'rodar', side_effect=self.falso()):
            return via_api.fila(arq, refazer)

    def test_retoma_pulando_as_feitas(self):
        (self.base / 'a').mkdir()
        (self.base / 'a' / 'custo.json').write_text(json.dumps({'nome': 'a', 'estado': 'ok', 'usd': 2.0}))
        st = self.fila([[tarefa('a'), tarefa('b')]])
        self.assertEqual([c[0] for c in self.chamadas], ['b'])
        res = st['etapas'][0]['resultados']
        self.assertEqual(res[0]['estado'], 'pulada')
        self.assertEqual(st['gasto_total_usd'], 3.0)

    def test_refazer_forca(self):
        (self.base / 'a').mkdir()
        (self.base / 'a' / 'custo.json').write_text(json.dumps({'nome': 'a', 'estado': 'ok', 'usd': 2.0}))
        self.fila([[tarefa('a')]], refazer=('a',))
        self.assertEqual([c[0] for c in self.chamadas], ['a'])

    def test_teto_dividido_e_sem_credito(self):
        st = self.fila([[tarefa('a', 8), tarefa('b', 2)]], teto=5)
        orc = dict(self.chamadas)
        self.assertEqual(orc, {'a': 4.0, 'b': 1.0})
        self.chamadas.clear()
        for n in 'ab':
            (self.base / n / 'custo.json').unlink()
        st = self.fila([[tarefa('a', 8), tarefa('b', 2)]], teto=0.5)
        self.assertEqual(self.chamadas, [('a', 0.4)])
        self.assertIn('sem crédito', [r['estado'] for r in st['etapas'][0]['resultados']])

    def test_rodando_orfa_vira_interrompida(self):
        (self.base / 'velha').mkdir()
        (self.base / 'velha' / 'custo.json').write_text(json.dumps({'nome': 'velha', 'estado': 'rodando', 'usd': 0}))
        st = self.fila([[tarefa('b')]])
        self.assertEqual(st['interrompidas'], ['velha'])
        self.assertEqual(json.loads((self.base / 'velha' / 'custo.json').read_text())['estado'], 'interrompida')
        self.assertFalse((self.base / 'fila.pid').exists())

    def test_incompleta(self):
        self.assertTrue(via_api.incompleta(''))
        self.assertTrue(via_api.incompleta('Rodando os testes em segundo plano; aviso quando fechar.'))
        self.assertFalse(via_api.incompleta('Feito: 3 itens, testes verdes.'))

    def test_preambulo_tem_as_regras(self):
        for p in ('Sem commit', 'segundo plano', '7655', '10 linhas'):
            self.assertIn(p, via_api.PREAMBULO)


if __name__ == '__main__':
    unittest.main()
