"""Fluxo do bruto e Kie com provedor simulado: nenhum crédito é consumido."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import MultiDict
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
P, C, servidor = fixtures.P, fixtures.C, fixtures.servidor
import broll_ia as B


class FluxoStudio(unittest.TestCase):
    setUp = fixtures.Isolado.setUp
    job = fixtures.Isolado.job

    def ready(self):
        j = self.job('plano')
        C.gravar_json(self.root / j['sandbox'] / 'PLANO.json', {'beats': [
            {'id': 'b1', 'inicio': 2, 'fim': 5, 'fala': 'Uma cena faz a ideia ficar clara.', 'tipo': 'punch', 'opcoes': []}
        ], 'transcricao': [], 'aprovado_em': 'antes'})
        return j

    def draft(self, j, **fields):
        return B.draft(j, {'beat': 'b1', 'prompt': 'Mãos ajustando equipamento, sem texto.',
                           'ratio': '16:9', 'resolucao': '2K', **fields})

    def image(self, j):
        from PIL import Image
        r = self.draft(j)
        path = B.folder(j) / (r['id'] + '.png')
        Image.new('RGB', (640, 360), '#365568').save(path)
        r.update(status='pronto', arquivo='gerados/' + path.name)
        B.save(j, r)
        return r

    def test_upload_is_storage_only_even_with_old_auto_flag(self):
        with patch.object(P, 'analisar') as analyze, patch.object(servidor, 'UPLOADS', self.est):
            response = self.client.post('/novo-video', data={
                'cliente': 'Teste', 'modelo': 'estilo', 'titulo': 'Bruto', 'rodar': '1',
                'cortar_bruto': '1', 'bruto': (BytesIO(b'raw'), 'raw.mp4')})
        self.assertEqual(response.status_code, 302)
        analyze.assert_not_called()
        self.assertTrue(P.carregar('Teste', 'bruto')['cortar_bruto'])

    def test_expensive_actions_review_before_mutation(self):
        j = self.ready()
        actions = [('/analisar', {}), ('/corte', {'acao':'auto'}), ('/previas', {}),
                   ('/renderizar', {}), ('/plano', {'acao': 'render', 'escolha_b1': 'nova'}),
                   ('/feedback', {'decisao': 'ajustar', 'texto': 'Melhorar a cena'})]
        with patch.object(P, '_disparar') as send, patch.object(P, 'aprovar_plano') as save:
            for path, data in actions:
                with self.subTest(path=path):
                    response = self.client.post('/job/Teste/video' + path, data=data)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('Confirmar e executar esta etapa'.encode(), response.data)
            send.assert_not_called()
            save.assert_not_called()

    def test_analysis_waits_for_cut_and_stores_scope(self):
        j = self.ready();j['cortar_bruto'] = True;P.salvar(j)
        with patch.object(P, 'analisar') as analyze:
            self.client.post('/job/Teste/video/analisar', data={'confirmar_execucao':'1'})
            analyze.assert_not_called()
            j['corte_aplicado']={'arquivo':'cut.mp4'};P.salvar(j)
            self.client.post('/job/Teste/video/analisar', data={'confirmar_execucao':'1'})
            analyze.assert_called_once()
            self.assertEqual(P.carregar('Teste','video')['escopo_edicao'],'essencial')

    def test_draft_never_calls_api_and_price_is_server_owned(self):
        j = self.ready()
        with patch.object(B, 'call') as api:
            r = self.draft(j, usd_estimado='0.001', model='evil')
        api.assert_not_called()
        self.assertEqual(r['usd_estimado'], .05)
        self.assertEqual(r['model'], B.IMAGE_MODEL)
        self.assertEqual(r['input']['aspect_ratio'], '16:9')

    def test_paid_submission_is_once_and_requires_nonce(self):
        j = self.ready();r = self.draft(j)
        with patch.object(B, 'key', return_value='fake'), patch.object(B.threading, 'Thread') as thread:
            with self.assertRaises(ValueError): B.confirm(j, r['id'], 'wrong')
            thread.assert_not_called()
            B.confirm(j, r['id'], r['nonce'])
            B.confirm(j, r['id'], r['nonce'])
            thread.assert_called_once()
            self.assertEqual(B.load(j,r['id'])['status'],'enviando')

    def test_submission_timeout_never_retries(self):
        j=self.ready();r=self.draft(j)
        with patch.object(B,'call',side_effect=TimeoutError) as api:
            B._submit(j,r['id'])
            self.assertEqual(api.call_count,1)
        self.assertEqual(B.load(j,r['id'])['status'],'incerto')

    def test_image_approval_required_and_video_inherits_ratio(self):
        j=self.ready();img=self.image(j)
        form={'tipo':'video','origem':img['id'],'resolucao':'720p','duracao':'6'}
        with self.assertRaises(ValueError):self.draft(j,**form)
        r=self.draft(j,**form,imagem_aprovada='1')
        self.assertEqual(r['ratio'],'16:9')
        self.assertEqual(r['usd_estimado'],.135)
        self.assertEqual(r['input']['duration'],'6')
        self.assertEqual(r['model'],B.VIDEO_MODEL)
        self.assertNotIn('image_urls',r['input'])

    def test_submit_uploads_exact_approved_reference(self):
        j=self.ready();img=self.image(j)
        r=self.draft(j,tipo='video',origem=img['id'],resolucao='720p',duracao='6',imagem_aprovada='1')
        with patch.object(B,'upload',return_value='https://example.com/image.png') as upload, patch.object(B,'call',return_value={'taskId':'task123'}) as api:
            B._submit(j,r['id'])
        self.assertEqual(api.call_args.args[2]['input']['image_urls'],['https://example.com/image.png'])
        upload.assert_called_once_with(self.root/j['sandbox']/img['arquivo'])
        self.assertEqual(B.load(j,r['id'])['task_id'],'task123')

    def test_poll_download_then_use_is_explicit(self):
        j=self.ready();r=self.draft(j);r.update(status='processando',task_id='task123');B.save(j,r)
        from PIL import Image
        image_bytes=BytesIO();Image.new('RGB',(640,360)).save(image_bytes,format='PNG');image_bytes.seek(0)
        response=MagicMock();response.__enter__.return_value=image_bytes
        with patch.object(B,'call',return_value={'state':'success','resultJson':'{"resultUrls":["https://example.com/a.png"]}','creditsConsumed':10}),patch.object(B.urllib.request,'urlopen',return_value=response):
            ready=B.refresh(j,r['id'])
        self.assertEqual(ready['status'],'pronto')
        self.assertFalse(P.plano(j)['beats'][0].get('escolha'))
        B.use(j,r['id']);B.use(j,r['id'])
        plan=P.plano(j)
        self.assertEqual(len(plan['beats'][0]['opcoes']),1)
        self.assertTrue(plan['beats'][0]['opcoes'][0]['gerado_ia'])
        self.assertNotIn('aprovado_em',plan)

    def test_overlay_keeps_original_without_network(self):
        j=self.ready();r=self.image(j);path=self.root/j['sandbox']/r['arquivo'];before=path.read_bytes()
        with patch.object(B,'call') as api:
            result=B.overlay(j,r['id'],'Uma ideia clara','top')
        api.assert_not_called();self.assertEqual(path.read_bytes(),before)
        self.assertNotEqual(result['arquivo'],r['arquivo'])
        self.assertEqual(result['usd_estimado'],0)

    def test_all_generation_screens_render_and_escape(self):
        j=self.ready();r=self.draft(j,prompt='<script>alert(1)</script> cenário seguro')
        for path in ['/job/Teste/video','/job/Teste/video/brolls','/job/Teste/video/brolls/'+r['id'],'/novo-video?corte=x']:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertNotIn(b'<script>alert(1)</script>',response.data)
        r=self.image(j)
        response=self.client.get('/job/Teste/video/brolls/'+r['id'])
        self.assertIn('Aprovar imagem e preparar animação'.encode(),response.data)

    def test_recovery_queries_existing_task_without_create(self):
        j=self.ready();r=self.draft(j);r['status']='incerto';B.save(j,r)
        with patch.object(B,'call',return_value={'model':B.IMAGE_MODEL,'param':{'input':r['input']}}) as api:
            result=B.recover(j,r['id'],'known_task')
        self.assertEqual(api.call_args.args[0],'GET')
        self.assertEqual(result['task_id'],'known_task')
        self.assertEqual(result['status'],'processando')

    def test_recovery_rejects_other_model_or_prompt(self):
        j=self.ready();r=self.draft(j);r['status']='incerto';B.save(j,r)
        for data in [{'model':'wrong'}, {'model':B.IMAGE_MODEL,'param':{'input':{'prompt':'another'}}}]:
            with patch.object(B,'call',return_value=data),self.assertRaises(ValueError):
                B.recover(j,r['id'],'other_task')
        self.assertEqual(B.load(j,r['id'])['status'],'incerto')

    def test_changed_scene_requires_new_review_before_charge(self):
        j=self.ready();r=self.draft(j);plan=P.plano(j);plan['beats'][0]['fim']=9
        C.gravar_json(self.root/j['sandbox']/'PLANO.json',plan)
        with patch.object(B,'key',return_value='fake'),patch.object(B.threading,'Thread') as thread:
            with self.assertRaises(ValueError):B.confirm(j,r['id'],r['nonce'])
        thread.assert_not_called()

    def test_explicit_search_changes_essential_scope(self):
        j=self.ready();j['escopo_edicao']='essencial';P.salvar(j)
        with patch.object(P,'rebuscar') as search:
            self.client.post('/job/Teste/video/plano',data={'acao':'buscar','confirmar_execucao':'1'})
        search.assert_called_once()
        self.assertEqual(P.carregar('Teste','video')['escopo_edicao'],'busca')

    def test_invalid_input_cannot_call_paid_endpoint(self):
        j=self.ready()
        for fields in [{'ratio':'2:7'}, {'resolucao':'9K'}, {'beat':'missing'}, {'tipo':'audio'}, {'prompt':''}]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):self.draft(j,**fields)
        with self.assertRaises(ValueError):B.load(j,'../../config')


if __name__=='__main__':unittest.main()
