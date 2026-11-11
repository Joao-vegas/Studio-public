"""Frente 1 da 2.0: vários vídeos de uma vez e aprovar em lote. Tudo em pasta temporária, IA simulada."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_v2
import _comum as C
import producao as P
import andamento
import lotes


class Frente1(unittest.TestCase):
    def setUp(self):
        test_v2.Isolado.setUp(self)   # mesmo ambiente isolado dos testes de integridade
        self.job = lambda *a, **k: test_v2.Isolado.job(self, *a, **k)
        self.stack.enter_context(patch.object(andamento, 'RAIZ', self.root))
        self.stack.enter_context(patch.object(lotes.FMT, 'usar', return_value=('Teste', 'estilo')))
        self.stack.enter_context(patch.object(lotes.FMT, 'carregar', return_value={'titulo': 'Estilo X', 'entrada': 'video'}))
        self.pasta = self.root / 'brutos'
        self.pasta.mkdir()
        for n in ('b.mp4', 'a.mp4', 'c.mov'):
            (self.pasta / n).write_bytes(b'V')
        (self.pasta / 'nota.txt').write_text('x')
        (self.pasta / 'sub').mkdir()
        (self.pasta / 'sub' / 'd.mp4').write_bytes(b'V')

    def test_brutos_da_pasta(self):
        nomes = [p.name for p in lotes.brutos_da_pasta(self.pasta)]
        self.assertEqual(nomes, ['a.mp4', 'b.mp4', 'c.mov'])
        with self.assertRaises(ValueError):
            lotes.brutos_da_pasta(self.root / 'nao-existe')
        vazia = self.root / 'vazia'
        vazia.mkdir()
        with self.assertRaises(ValueError):
            lotes.brutos_da_pasta(vazia)
        self.assertTrue((self.pasta / 'a.mp4').exists())   # não move

    def test_estilo_que_nao_e_video_gravado_e_recusado(self):
        with patch.object(lotes.FMT, 'carregar', return_value={'titulo': 'Filme', 'entrada': 'filmagem'}):
            with self.assertRaises(ValueError):
                lotes.criar_por_estilo('', 'filmagem-x', [self.pasta / 'a.mp4'])

    def test_lote_de_tres_pelo_test_client(self):
        with patch.object(P, 'analisar') as an:
            r = self.client.post('/novo-lote', data={'cliente': '', 'formato': 'x', 'pasta': str(self.pasta),
                                                      'briefing': 'tom direto', 'analisar': '1'})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(an.call_count, 3)
        ls = lotes.listar()
        self.assertEqual(len(ls), 1)
        self.assertEqual(len(ls[0]['jobs']), 3)
        self.assertEqual(ls[0]['formato'], 'x')
        for s in ls[0]['jobs']:
            self.assertEqual(P.carregar('Teste', s)['formato'], 'x')
        self.assertEqual(self.client.get('/lote/' + ls[0]['slug']).status_code, 200)
        self.assertEqual(self.client.get('/lotes').status_code, 200)
        self.assertEqual(self.client.get('/novo-lote').status_code, 200)

    def _espera(self, slug):
        j = self.job('plano', slug)
        img = self.root / f'{slug}-storyboard.jpg'
        img.write_bytes(b'J')
        andamento.registrar('Teste', slug, 'Storyboard pronto', 'esperando', titulo=slug, formato='x', origem='tela', imagem=str(img))
        return j

    def test_aprovar_lista_e_aprova_dois(self):
        self._espera('um')
        self._espera('dois')
        self.job('plano', 'tres')
        andamento.registrar('Teste', 'tres', 'Trabalhando', 'trabalhando', titulo='tres', origem='tela')
        self.assertEqual({i['slug'] for i in lotes.esperando()}, {'um', 'dois'})
        html = self.client.get('/aprovar').get_data(as_text=True)
        self.assertIn('um', html)
        with patch.object(P, 'avancar', return_value='ok') as av:
            r = self.client.post('/aprovar', data={'video': ['Teste/um', 'Teste/dois']})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(av.call_count, 2)
        self.assertEqual(andamento.carregar('Teste', 'um')['respostas'][0]['status'], 'feito')

    def test_erro_de_um_nao_para_os_outros(self):
        self._espera('um')
        self._espera('dois')
        with patch.object(P, 'avancar', side_effect=[RuntimeError('falhou'), 'ok']):
            res = lotes.aprovar_varios([('Teste', 'um'), ('Teste', 'dois')])
        self.assertIn('erro', res[0])
        self.assertTrue(res[1].endswith('ok'))

    def test_sem_storyboard_nao_aprova(self):
        self.job('plano', 'sem')
        andamento.registrar('Teste', 'sem', 'Storyboard pronto', 'esperando', titulo='sem', formato='x', origem='tela')
        html = self.client.get('/aprovar').get_data(as_text=True)
        self.assertIn('Ainda falta uma escolha', html)
        self.assertNotIn('name="video" value="Teste/sem"', html)   # sem checkbox de aprovar (o botão Apagar tem o valor, de propósito)
        with patch.object(P, 'avancar', return_value='ok') as av:
            res = lotes.aprovar_varios([('Teste', 'sem')])
            self.assertEqual(av.call_count, 0)
        self.assertIn('ainda falta uma escolha', res[0])

    def test_folha_sem_storyboard_nao_deixa_aprovar(self):
        import runner
        sb = self.root / 'sb-folha'
        sb.mkdir()
        (sb / 'folha.jpg').write_bytes(b'J')
        self.job('plano', 'folha')
        runner._andamento({'cliente': 'Teste', 'slug': 'folha', 'status': 'plano', 'sandbox': str(sb), 'titulo': 'folha', 'formato': 'x'}, fim=True)
        self.assertFalse(andamento.carregar('Teste', 'folha').get('imagem'))
        self.assertFalse([i for i in lotes.esperando() if i['slug'] == 'folha' and i['pronto']])
        with patch.object(P, 'avancar', return_value='ok') as av:
            res = lotes.aprovar_varios([('Teste', 'folha')])
            self.assertEqual(av.call_count, 0)
        self.assertIn('ainda falta uma escolha', res[0])

    def test_aprovar_vazio(self):
        self.assertIn('Nada esperando você agora.', self.client.get('/aprovar').get_data(as_text=True))
        self.assertEqual(self.client.post('/aprovar', data={}).status_code, 302)


if __name__ == '__main__':
    unittest.main()
