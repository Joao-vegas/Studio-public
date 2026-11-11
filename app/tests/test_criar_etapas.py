"""Frente C da melhoria geral (22-out-2026): o Criar em 5 passos com nome e as etapas do vídeo dizendo quem age.
Flask test client; nada pago, nada gravado em clientes/ nem em app/jobs/."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
import pipeline
import producao as P


class CriarEmCincoPassos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import servidor
        cls.html = servidor.app.test_client().get('/criar').get_data(as_text=True)

    def test_pagina_abre_com_cinco_passos_nomeados(self):
        self.assertIn('data-passo="5"', self.html)
        self.assertNotIn('data-passo="6"', self.html)
        for nome in ('O que você tem', 'Estilo', 'Pra quem', 'Material', 'Criar'):
            self.assertIn(nome, self.html)
        self.assertIn('class="trilha"', self.html)   # Palco 2.0: trilha com 5 círculos no lugar das pílulas

    def test_uma_so_grade_de_formatos(self):
        self.assertEqual(self.html.count('id="grade-escolha"'), 1)
        self.assertNotIn('grade-todos', self.html)
        self.assertIn('id="ir-formatos"', self.html)

    def test_referencia_e_so_de_estilo(self):
        self.assertIn('referência de estilo', self.html)
        self.assertNotIn('O que copiar dela', self.html)
        self.assertIn('O que você gostou nela', self.html)

    def test_criar_vira_botao_so_no_passo_5(self):
        passo4 = self.html.split('data-passo="4"')[1].split('data-passo="5"')[0]
        passo5 = self.html.split('data-passo="5"')[1]
        self.assertIn('id="continuar-material"', passo4)
        self.assertNotIn('type="submit"', passo4)
        self.assertIn('type="submit"', passo5)

    def test_campos_do_formulario_nao_mudaram(self):
        for nome in ('formato', 'cliente', 'videos', 'roteiro', 'cortar', 'ref', 'ref_pasta', 'segundo', 'ref_copiar',
                     'referencia', 'referencia_link', 'legenda', 'descartavel', 'titulo', 'briefing'):
            self.assertRegex(self.html, r'name="%s"' % nome)

    def test_aviso_do_corte(self):
        self.assertIn('já entra cortado', self.html)


def _job():
    return {'sandbox': 'app/jobs/_inexistente/x', 'cliente': 'Avulso', 'slug': 'x', 'status': 'plano',
            'cortar_bruto': True, 'broll_config': {'origem': 'busca', 'quantidade': 5}}


class EtapasDoVideo(unittest.TestCase):
    def etapas(self, **mudar):
        j = dict(_job(), **mudar)
        with mock.patch.object(P, '_esteira', return_value=None), mock.patch.object(P, 'plano', return_value={'beats': []}), \
                mock.patch.object(P, 'corte_rodando', return_value=False), mock.patch.object(P, 'corte_json', return_value={'segmentos': []}):
            return pipeline.etapas(j)

    def test_etapa_de_aprovacao_diz_voce_aprova(self):
        lista = self.etapas()
        self.assertIn('Você aprova', [e['quem'] for e in lista])
        self.assertTrue(all(e['quem'] in ('Estúdio faz', 'Você aprova', 'Você olha') for e in lista))

    def test_etapa_atual_e_a_primeira_que_pede_o_joao(self):
        lista = self.etapas()
        self.assertEqual(pipeline.etapa_atual(lista), next(e['id'] for e in lista if e['sua_vez']))
        self.assertEqual([e['id'] for e in lista if e['atual']], [pipeline.etapa_atual(lista)])

    def test_etapa_do_corte_aponta_pro_editor_na_mao(self):
        lista = self.etapas()
        corte = next(e for e in lista if e.get('editor_corte'))
        self.assertIn('corrigir na mão', corte['detalhe'])

    def test_sem_corte_nao_oferece_o_editor_na_etapa(self):
        self.assertFalse([e for e in self.etapas(cortar_bruto=False) if e.get('editor_corte')])

    def test_sem_nada_pendente_nao_tem_etapa_atual(self):
        self.assertIsNone(pipeline.etapa_atual([{'id': 'a', 'estado': 'pronto'}]))


class PaginaDoVideoMostraQuem(unittest.TestCase):
    def test_template_usa_quem_e_nao_a_conta_velha(self):
        t = (RAIZ / 'app/interface/templates/job.html').read_text(encoding='utf-8')
        self.assertIn('process-quem', t)
        self.assertIn('Sua vez:', t)
        self.assertNotIn("set etapa = 1 if st in", t)
        self.assertFalse(re.search(r'set etapa = [45]', t))

    def test_linha_morta_do_corte_manual_saiu(self):
        t = (RAIZ / 'app/interface/simples.py').read_text(encoding='utf-8')
        self.assertEqual(t.count('video = rel('), 1)


if __name__ == '__main__':
    unittest.main()
