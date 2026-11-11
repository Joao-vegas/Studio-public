"""Efeitos sonoros por som: a tela mostra um chip por TIPO de som, o João desmarca, o motor do Documentário obedece.

Antes: um chip por momento (dezenas de 'typing · 0:12') e o motor só aceitava "efeitos": true/false, então desmarcar
um chip não mudava nada no vídeo. Tudo em pasta temporária; sem navegador, sem rede, nada pago."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_esteira as G2                      # noqa: E402  (só as bases; os testes de lá não rodam aqui)
import test_grupo_1_motor_do_doc as G1         # noqa: E402
import test_grupo_3_tela_m_sica_tela as G3     # noqa: E402
import edicao                                  # noqa: E402

R, BASE, P, C = G1.R, G1.BASE, G2.P, G2.C


def _modelo():
    return G1._modelo()


class MotorPorSom(unittest.TestCase):
    def test_lista_toca_so_os_sons_ligados_nos_mesmos_momentos(self):
        """O motor escolhe os efeitos no ritmo do exemplo (16 em 1:23) entre os sons ligados: o desmarcado não toca e os
        outros entram nos momentos deles (o teclado com a frase, o clique no círculo, a passagem na troca)."""
        doc = _modelo()
        p = R.planejar(doc, BASE)
        todos = p['eventos']
        self.assertTrue(todos and {e['som'] for e in todos} <= set(R.SONS))
        self.assertLessEqual(len(todos), R.teto_efeitos(p['total']))
        momentos = {(e['t'], e['som']) for e in R.candidatos_de_efeito(p['cenas'])}
        so = R.planejar({**doc, 'efeitos': ['whoosh-short', 'click']}, BASE)['eventos']   # 'click' = click-soft
        self.assertTrue(so)
        self.assertTrue({e['som'] for e in so} <= {'whoosh-short', 'click-soft'})
        self.assertTrue(all((e['t'], e['som']) in momentos for e in so))
        self.assertEqual(R.planejar({**doc, 'efeitos': True}, BASE)['eventos'], todos)
        self.assertEqual(R.planejar({k: v for k, v in doc.items() if k != 'efeitos'}, BASE)['eventos'], todos)
        for nada in (False, None, []):
            self.assertEqual(R.planejar({**doc, 'efeitos': nada}, BASE)['eventos'], [], nada)

    def test_aceita_os_itens_do_plano_e_ignora_som_que_nao_existe(self):
        itens = [{'id': 'typing', 'som': 'typing', 'ligado': True}, {'id': 'pop', 'som': 'pop', 'ligado': False}]
        self.assertEqual(R.sons_ligados(itens), {'typing'})
        self.assertEqual(R.sons_ligados(['Whoosh', 'tique', 'trovao']), {'whoosh-short', 'tique'})
        self.assertEqual(R.sons_ligados({'typing': True, 'pop': False}), {'typing'})

    def test_rodape_do_storyboard_diz_quais_sons(self):
        self.assertIn('efeitos suaves ligados', R._musica_txt({'musica': None, 'efeitos': True}))
        self.assertIn('sem efeitos', R._musica_txt({'musica': None, 'efeitos': False}))
        self.assertIn('efeitos: teclado, passagem', R._musica_txt({'musica': None, 'efeitos': ['typing', 'whoosh-short']}))

    def test_conferir_reprova_som_desmarcado_e_aprova_sem_ele(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            plano = {'sfx_ligado': True, 'sfx': [{'id': s, 'som': s, 'ligado': s != 'pop'} for s in R.SONS]}
            (t / 'PLANO.json').write_text(json.dumps(plano), encoding='utf-8')
            doc = {**_modelo(), 'musica': None}
            m = ' | '.join(R.conferir(doc, t, t, t / 'x.mp4')['motivos'])
            self.assertIn('desmarcou na tela: pop', m)
            res = R.conferir({**doc, 'efeitos': [s for s in R.SONS if s != 'pop']}, t, t, t / 'x.mp4')
            self.assertFalse([x for x in res['motivos'] if 'efeito' in x.lower() or 'desmarcou' in x], res['motivos'])
            self.assertEqual(res['numeros']['efeitos']['sons_desligados_na_tela'], ['pop'])
            self.assertNotIn('pop', res['numeros']['efeitos']['por_som'])

    def test_todo_som_desmarcado_vale_sem_efeitos(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'PLANO.json').write_text(json.dumps({'sfx_ligado': True, 'sfx': [{'id': 'typing', 'ligado': False}]}), encoding='utf-8')
            self.assertTrue(R.escolha_da_tela(t)['sem_efeitos'])
            (t / 'PLANO.json').write_text(json.dumps({'sfx_ligado': True, 'sfx': []}), encoding='utf-8')
            self.assertFalse(R.escolha_da_tela(t)['sem_efeitos'])


class PromptPorSom(G2.Base):
    def setUp(self):
        super().setUp()
        self.criar_formato()
        self.j = self.job_formato()
        edicao.aplicar(self.j, {'origem': 'misto', 'quantidade': 5})
        P.salvar(self.j)
        self.j = P.carregar('Teste', 'video')

    def test_aprovacao_pede_um_por_som_e_depois_passa_a_lista(self):
        a = P.prompt_esteira(self.j, 'ate_aprovacao')
        self.assertIn('UM POR TIPO de som', a)
        self.assertIn('"id": "whoosh-short"', a)
        self.assertIn('"titulo": "Passagem quando muda o fundo"', a)   # o motor só toca a passagem quando o fundo muda
        self.assertNotIn('Passagem na troca de cena', a)
        self.assertNotIn('"t": 4.0', a)
        d = P.prompt_esteira(self.j, 'depois')
        self.assertIn('"efeitos": a LISTA dos sons ligados', d)
        self.assertNotIn('pra desligar um só', d)


class TelaPorSom(G3.Base):
    def test_um_chip_por_som_sem_tempo_e_o_motor_obedece(self):
        j = self.job('plano')
        sb = self.root / j['sandbox']
        C.gravar_json(sb / 'PLANO.json', {'transcricao': [], 'sfx_ligado': True, 'beats': [
            {'id': 'b1', 'inicio': 1, 'fim': 3, 'fala': 'uma cena', 'tipo': 'broll', 'escolha': None,
             'opcoes': [{'id': 'b1-1', 'titulo': 'Só a folha', 'sheet': 'brolls/b1-1-sheet.jpg', 'url': 'https://x'}]}],
            'sfx': [{'id': 'typing', 'som': 'typing', 'titulo': 'Teclado na frase', 'motivo': 'quando a frase aparece', 'ligado': True},
                    {'id': 'whoosh-short', 'som': 'whoosh-short', 'titulo': 'Passagem na troca de cena', 'ligado': True}]})
        (sb / 'brolls/b1-1-sheet.jpg').write_bytes(b'JPG')
        t = self.client.get('/job/Teste/video').get_data(as_text=True)
        self.assertIn('name="sfx" value="typing"', t)
        self.assertIn('<span>Teclado na frase</span>', t)          # sem " · 0:12"
        self.assertIn('Cada som vale pro vídeo todo', t)
        self.assertIn('title="quando a frase aparece"', t)
        r = self.client.post('/job/Teste/video/plano', data={'acao': 'salvar', 'escolha_b1': 'nenhum', 'sfx_bloco': '1',
                                                             'sfx_ligado': '1', 'sfx': ['whoosh-short']})
        self.assertEqual(r.status_code, 302)
        p = P.plano(P.carregar('Teste', 'video'))
        self.assertEqual([(s['id'], s['ligado']) for s in p['sfx']], [('typing', False), ('whoosh-short', True)])
        self.assertTrue(p['sfx_ligado'])
        self.assertEqual(R.sons_ligados(p['sfx']), {'whoosh-short'})       # o que a IA passa pro cenas.json
        self.assertEqual(R.sons_desligados_na_tela(sb), {'typing'})        # o que o --conferir cobra


if __name__ == '__main__':
    unittest.main()
