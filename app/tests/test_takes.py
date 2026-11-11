"""Regressões de busca por trecho, fontes combinadas e mídia opcional."""
import io
import sys
from pathlib import Path
from unittest.mock import patch
import unittest
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent))
import test_v2 as fixtures
import takes, edicao
P,C=fixtures.P,fixtures.C

class Takes(unittest.TestCase):
    setUp=fixtures.Isolado.setUp
    job=fixtures.Isolado.job

    def plan(self):
        j=self.job('plano');P.salvar_plano(j,{'beats':[{'id':b,'tipo':'broll','inicio':0,'fim':3,'fala':b,'escolha':None,'opcoes':[]} for b in ('b1','b2')]})
        return j

    def test_mixed_keeps_search_and_no_paid_generation(self):
        prefs=edicao.preferencias({'usar_broll':'1','origem_broll':'misto','quantidade_broll':'4'})
        j={};edicao.aplicar(j,prefs)
        self.assertEqual(j['escopo_edicao'],'busca')
        self.assertIn('Banco e IA',edicao.instrucao(j))
        self.assertIn('nunca chame geração paga',edicao.instrucao(j))

    def test_targeted_search_is_reviewed_before_mutation(self):
        self.plan()
        with patch.object(P,'rebuscar') as search,patch.object(P,'aprovar_plano') as save:
            r=self.client.post('/job/Teste/video/plano',data={'acao':'buscar:b1'})
        self.assertEqual(r.status_code,200);search.assert_not_called();save.assert_not_called()

    def test_targeted_search_preserves_mixed_source(self):
        j=self.plan();edicao.aplicar(j,{'origem':'misto','quantidade':3});P.salvar(j)
        with patch.object(P,'rebuscar') as search:
            r=self.client.post('/job/Teste/video/plano',data={'acao':'buscar:b1','confirmar_execucao':'1'})
        self.assertEqual(r.status_code,302);search.assert_called_once_with('Teste','video','b1')
        self.assertEqual(P.carregar('Teste','video')['broll_config']['origem'],'misto')
        prompt=P.prompt_rebusca(j,'b1')
        self.assertIn('  - b1',prompt);self.assertNotIn('  - b2',prompt)

    def test_empty_filename_does_not_count_as_preview(self):
        j=self.plan();self.assertIsNone(takes.midia(j,{'arquivo':''}))
        self.assertIsNone(takes.midia(j,{'arquivo':'material'}))
        plan=P.plano(j);plan['beats'][0].update(escolha='x',opcoes=[{'id':'x'}])
        with self.assertRaises(ValueError):takes.validar_escolhas(j,plan)

    def test_own_upload_is_optional_and_does_not_run_ai(self):
        j=self.plan();data=io.BytesIO();Image.new('RGB',(100,100)).save(data,format='PNG');data.seek(0)
        with patch.object(P,'_disparar') as dispatch:
            r=self.client.post('/job/Teste/video/take',data={'beat':'b1','take':(data,'meu-take.png')})
        self.assertEqual(r.status_code,302);dispatch.assert_not_called()
        j=P.carregar('Teste','video');self.assertEqual(j['takes_proprios'][0]['status'],'aguardando_analise')
        self.assertFalse(P.plano(j)['beats'][0]['escolha'])
        with self.assertRaises(ValueError):takes.validar_avaliacao(j,'b1')
        item=j['takes_proprios'][0]
        C.gravar_json(self.root/j['sandbox']/'material/avaliacao-b1.json',{'takes':[{'id':item['id'],'adequado':False,'motivo':'Não corresponde à fala','sheet':item['arquivo']}]})
        takes.validar_avaliacao(j,'b1')
        self.assertFalse(P.carregar('Teste','video')['takes_proprios'][0]['avaliacao']['adequado'])

    def test_recover_previews_requires_review(self):
        self.plan()
        with patch.object(P,'_disparar') as dispatch:
            r=self.client.post('/job/Teste/video/plano',data={'acao':'recuperar:b1'})
        self.assertEqual(r.status_code,200);dispatch.assert_not_called()

if __name__=='__main__':unittest.main()
