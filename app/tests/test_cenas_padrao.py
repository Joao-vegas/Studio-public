"""Tela dividida: número de cenas pela duração do bruto (1 a cada 10 s, entre 3 e 12); a escolha da tela manda."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import edicao

REGRA = {'campo': 'cenas', 'quantidade': 8, 'cenas_por_segundo': 0.1, 'minimo': 3, 'maximo': 12}


class Cenas(unittest.TestCase):
    def qtd(self, prefs, dur, regra=REGRA):
        job = {'formato': 'tela-dividida', 'broll_config': prefs}
        with patch.object(edicao, 'regra_cenas', return_value=regra), patch.object(edicao, 'duracao_bruto', return_value=dur):
            return edicao.quantidade(job)

    def test_pela_duracao(self):
        padrao = {'origem': 'busca', 'quantidade': 8, 'do_formato': True}
        self.assertEqual(self.qtd(padrao, 83), 8)
        self.assertEqual(self.qtd(padrao, 30), 3)
        self.assertEqual(self.qtd(padrao, 120), 12)
        self.assertEqual(self.qtd(padrao, 400), 12)

    def test_sem_duracao_usa_o_fixo(self):
        self.assertEqual(self.qtd({'origem': 'busca', 'quantidade': 8, 'do_formato': True}, 0), 8)

    def test_escolha_da_tela_manda(self):
        self.assertEqual(self.qtd({'origem': 'busca', 'quantidade': 5, 'na_tela': True}, 120), 5)

    def test_sem_regra_fica_o_salvo(self):
        self.assertEqual(self.qtd({'origem': 'busca', 'quantidade': 4}, 120, regra={}), 4)

    def test_pedido_a_ia(self):
        job = {'formato': 'tela-dividida', 'broll_config': {'origem': 'busca', 'quantidade': 8, 'do_formato': True}}
        with patch.object(edicao, 'regra_cenas', return_value=REGRA), patch.object(edicao, 'duracao_bruto', return_value=60):
            self.assertIn('6 cenas de apoio', edicao.instrucao_esteira(job))
        job['broll_config'] = {'origem': 'nenhum', 'quantidade': 0}
        self.assertEqual(edicao.instrucao_esteira(job), '')

    def test_formulario_marca_na_tela(self):
        p = edicao.preferencias({'usar_broll': '1', 'origem_broll': 'busca', 'quantidade_broll': '11', 'na_tela': '1'})
        self.assertEqual(p, {'origem': 'busca', 'quantidade': 11, 'na_tela': True})

    def test_formato_declara_a_regra(self):
        import formatos
        f = formatos.carregar('tela-dividida') or {}
        r = next(e for e in f.get('escolhas', []) if e.get('campo') == 'cenas')
        self.assertEqual((r['cenas_por_segundo'], r['minimo']), (0.1, 3))
        self.assertNotIn('maximo', r, 'Tela dividida não tem teto de cenas: cobre o vídeo inteiro conforme a fala')
        self.assertEqual(edicao.cenas_pela_duracao(r, 180), 18)


if __name__ == '__main__':
    unittest.main()


sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_v2 as fixtures  # noqa: E402


class PaginaDoVideo(unittest.TestCase):
    setUp = fixtures.Isolado.setUp
    tearDown = getattr(fixtures.Isolado, 'tearDown', lambda self: None)
    job = fixtures.Isolado.job

    def test_quantidade_na_pagina_e_salva(self):
        j = self.job('plano')
        j['formato'] = 'tela-dividida'
        j['broll_config'] = {'origem': 'busca', 'quantidade': 8, 'do_formato': True}
        fixtures.P.salvar(j)
        r = self.client.get('/job/Teste/video')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('8 cenas no máximo', html)   # sem bruto de verdade: o fixo do formato
        self.assertIn('<option value="11"', html)
        r = self.client.post('/job/Teste/video/preferencias', data={'usar_broll': '1', 'na_tela': '1', 'origem_broll': 'busca',
                                                                    'quantidade_broll': '10'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(edicao.quantidade(fixtures.P.carregar('Teste', 'video')), 10)
