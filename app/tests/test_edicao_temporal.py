"""Preferências, sequência de aprovação e evidência temporal, sem APIs pagas."""
import copy
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import test_v2 as fixtures
import edicao, pipeline, referencia_frames, referencia_temporal as T, broll_ia as B
P,C=fixtures.P,fixtures.C


class Preferencias(unittest.TestCase):
    setUp=fixtures.Isolado.setUp
    job=fixtures.Isolado.job

    def test_off_is_default_and_ignores_hidden_values(self):
        self.assertEqual(edicao.preferencias({'quantidade_broll':'garbage','origem_broll':'ia'}),{'origem':'nenhum','quantidade':0})

    def test_user_picks_source_and_ceiling(self):
        self.assertEqual(edicao.preferencias({'usar_broll':'1','quantidade_broll':'2','origem_broll':'ia'}),{'origem':'ia','quantidade':2})
        for n in ('0','201','1.5','abc'):
            with self.subTest(n=n),self.assertRaises(ValueError):edicao.preferencias({'usar_broll':'1','quantidade_broll':n})

    def test_render_and_paid_draft_enforce_off(self):
        j=self.job('plano');edicao.aplicar(j,{'origem':'nenhum','quantidade':0});P.salvar(j)
        plan={'aprovado_em':'hoje','beats':[{'id':'b1','tipo':'broll','escolha':'o1','inicio':0,'fim':2,'fala':'teste','opcoes':[]}]}
        P.salvar_plano(j,plan)
        with patch.object(P,'_disparar') as dispatch:
            with self.assertRaises(ValueError):P.renderizar('Teste','video')
            with self.assertRaises(ValueError):P.gerar_previas('Teste','video')
        dispatch.assert_not_called()
        with self.assertRaises(ValueError):B.draft(j,{'beat':'b1','prompt':'Uma cena aqui'})

    def test_disabling_clears_broll_choices_without_generating(self):
        j=self.job('plano');P.salvar_plano(j,{'aprovado_em':'hoje','beats':[{'id':'b1','tipo':'broll','escolha':'o1'}]})
        with patch.object(P,'_disparar') as dispatch:
            response=self.client.post('/job/Teste/video/preferencias',data={})
        self.assertEqual(response.status_code,302);dispatch.assert_not_called()
        updated=P.carregar('Teste','video')
        self.assertEqual(updated['broll_config']['quantidade'],0)
        self.assertIsNone(P.plano(updated)['beats'][0]['escolha'])
        self.assertNotIn('aprovado_em',P.plano(updated))

    def test_pipeline_omits_optional_scenes_and_never_marks_future_done(self):
        j=self.job('novo');j['saida']=None;j['broll_config']={'origem':'nenhum','quantidade':0}
        (self.root/j['sandbox']/'PLANO.json').unlink()
        steps=pipeline.etapas(j)
        self.assertNotIn('cenas',[x['id'] for x in steps])
        self.assertEqual(next(x for x in steps if x['id']=='analise')['estado'],'aguardando')
        self.assertEqual(next(x for x in steps if x['id']=='final')['estado'],'aguardando')

    def test_ia_prompt_plans_but_never_generates(self):
        j=self.job('novo');edicao.aplicar(j,{'origem':'ia','quantidade':2})
        text=P.prompt_analise(j)
        self.assertIn('no máximo 2 trechos',text)
        self.assertIn('Não gerar mídia nesta etapa',text)
        self.assertIn('geracao_sugerida',text)

    def test_local_key_is_not_in_html_or_dependent_on_sibling(self):
        self.assertNotIn('Gerados de imagem',Path(B.__file__).read_text())
        with patch.object(B,'key',return_value='private-test-secret'):
            response=self.client.get('/config')
        self.assertEqual(response.status_code,200)
        self.assertNotIn(b'private-test-secret',response.data)
        self.assertIn(b'kie.ai',response.data.lower())


class ReferenciaTemporal(unittest.TestCase):
    setUp=fixtures.Isolado.setUp

    def sample(self):
        folder=self.root/'frames-test';folder.mkdir()
        video=folder/'original.mp4'
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','testsrc2=size=96x160:rate=10:duration=2.4','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
        index=referencia_frames.extrair(video,folder)
        seconds=T.indexar(index,folder,2.4)
        p={'linha_do_tempo':[{'segundo':x['segundo'],'frame':x['frame'],'tipo':'fala','descricao':'Apresentador no vídeo'} for x in seconds['segundos']],
           'brolls':[{'id':'b1','inicio':.3,'fim':.7,'duracao':.4,'frame_entrada':4,'frame_saida':8,'conteudo':'Cena ilustrativa','funcao':'Explicar a fala','entrada':'corte seco','saida':'retorno ao apresentador','layout':'tela inteira','como_replicar':'insert de 0,4 segundo sincronizado à palavra'}],
           'problemas':[{'inicio':.3,'fim':.7,'frame':5,'problema':'Texto cobre detalhe','impacto':'Oculta o assunto','correcao':'Reposicionar texto'}]}
        return folder,index,seconds,p

    def test_every_second_and_subsecond_cut_are_preserved(self):
        folder,index,seconds,p=self.sample()
        self.assertEqual(index['total_frames'],24)
        self.assertEqual([x['segundo'] for x in seconds['segundos']],[0,1,2])
        self.assertEqual([x['frame'] for x in seconds['segundos']],[1,11,21])
        self.assertTrue((folder/'folhas-segundos/folha-0001.jpg').is_file())
        self.assertTrue(T.validar(p,index,seconds))

    def test_missing_second_false_duration_and_unsupported_evidence_fail(self):
        _,index,seconds,p=self.sample()
        variants=[]
        q=copy.deepcopy(p);q['linha_do_tempo'].pop();variants.append(q)
        q=copy.deepcopy(p);q['brolls'][0]['duracao']=1.5;variants.append(q)
        q=copy.deepcopy(p);q['brolls'][0]['frame_entrada']=1;variants.append(q)
        q=copy.deepcopy(p);q['problemas'][0]['frame']=24;variants.append(q)
        for q in variants:
            with self.assertRaises(ValueError):T.validar(q,index,seconds)

    def test_vfr_repeats_displayed_frame_instead_of_skipping_seconds(self):
        from PIL import Image
        folder=self.root/'vfr';folder.mkdir();Image.new('RGB',(96,160)).save(folder/'f.jpg')
        index={'assinatura':'vfr','frames':[{'n':1,'segundo':0,'arquivo':'f.jpg'},{'n':2,'segundo':2.3,'arquivo':'f.jpg'}]}
        seconds=T.indexar(index,folder,3)
        self.assertEqual([x['frame'] for x in seconds['segundos']],[1,1,1])


if __name__=='__main__':unittest.main()
