"""Regressões de integridade e fluxo. Fixtures temporárias; sem chamadas pagas de IA."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'interface'))
import servidor
import _comum as C
import producao as P
import arquivo as A
import ia, fila, regras, acervo, semantica, lotes, estudo, aprendizado, novo_cliente, ficha, material

class Isolado(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.stack=contextlib.ExitStack()
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.stack.close)
        self.est=self.root/'app';self.est.mkdir();self.jobs=self.est/'jobs'
        self.content=self.root/'clientes/Teste/testeContent';self.mod=self.content/'modelos/estilo';(self.mod/'aprendizado').mkdir(parents=True)
        (self.mod/'README.md').write_text('modelo de teste');C.gravar_json(self.mod/'ficha.json',{'comando':'anterior'})
        C.gravar_json(self.mod/'aprendizado/regras.json',{'regras':[]})
        for module in (C,P,A,ia,servidor,estudo,aprendizado,novo_cliente,ficha,material):
            if hasattr(module,'RAIZ'):self.stack.enter_context(patch.object(module,'RAIZ',self.root))
        for module in (C,P):self.stack.enter_context(patch.object(module,'JOBS',self.jobs))
        self.stack.enter_context(patch.object(C,'ESTUDIO',self.est))
        for module in (C,A):self.stack.enter_context(patch.object(module,'CACHE',self.est/'.cache'))
        self.stack.enter_context(patch.object(ia,'CONFIG',self.est/'config.json'))
        self.stack.enter_context(patch.object(P,'CONFIG',ia.CONFIG))
        self.stack.enter_context(patch.object(fila,'FILA',self.est/'fila.json'))
        self.stack.enter_context(patch.object(fila,'LOCK',self.est/'.fila.lock'))
        self.stack.enter_context(patch.object(fila,'ESTUDIO',self.est))
        self.stack.enter_context(patch.object(acervo,'ACERVO',self.root/'acervo/itens'))
        self.stack.enter_context(patch.object(semantica,'INDICE',self.root/'acervo/indice.json'))
        self.stack.enter_context(patch.object(semantica,'BROLLS',self.root/'acervo'))
        self.stack.enter_context(patch.object(lotes,'LOTES',self.est/'lotes'))
        self.stack.enter_context(patch.object(lotes,'ESTUDIO',self.est))
        self.stack.enter_context(patch.object(estudo,'ESTUDOS',self.est/'estudos'))
        self.stack.enter_context(patch.object(fila,'iniciar'))
        self.stack.enter_context(patch.object(ia,'disponivel',return_value=True))
        self.stack.enter_context(patch.object(semantica,'encoder',return_value=None))
        self.stack.enter_context(patch.object(servidor,'thumb_cache',return_value=None))
        self.client=servidor.app.test_client()

    def job(self,status='aprovado',slug='video'):
        sb=self.mod/('_sandbox-'+slug);(sb/'bruto').mkdir(parents=True);(sb/'work').mkdir();(sb/'material').mkdir();(sb/'brolls').mkdir()
        (sb/'bruto/raw.mp4').write_bytes(b'RAW');(sb/'work/words.json').write_text('[]')
        (sb/'PLANO.json').write_text('{"beats": [], "transcricao": []}')
        (sb/'BRIEF.md').write_text('brief');(sb/'RESULTADO.md').write_text('resultado')
        (sb/'comando.sh').write_text('bash gerar.sh --legy 1270')
        final=self.content/'output/estilo'/(slug+'.mp4');final.parent.mkdir(parents=True,exist_ok=True);final.write_bytes(b'FINAL')
        j=dict(cliente='Teste',modelo='estilo',slug=slug,titulo='Meu vídeo',status=status,sandbox=str(sb.relative_to(self.root)),
               bruto=str((sb/'bruto/raw.mp4').relative_to(self.root)),saida=str(final.relative_to(self.root)),saida_esperada=str(final.relative_to(self.root)),
               versoes=[],versao=1,feedbacks=[{'decisao':'aprovado','texto':'','em':'2026','categoria':'qa'}],execucoes=[],criado_em='2026-09-17',briefing='')
        P.salvar(j);return P.carregar('Teste',slug)

    def test_media_policy_without_briefing(self):
        j=self.job('novo')
        for build in (P.prompt_analise,P.prompt_producao,P.prompt_rebusca,P.prompt_previa):
            with self.subTest(prompt=build.__name__):
                text=build(j)
                self.assertIn(P.POLITICA_BROLL,text)
                self.assertNotIn('traga 2 opções',text)
                self.assertNotIn('traga 2-3 opções',text)
                self.assertNotIn('nenhuma fonte pode passar',text)
        for build in (P.prompt_analise,P.prompt_producao):
            text=build(j)
            self.assertIn(P.POLITICA_MUSICA,text)
            self.assertNotIn('Sem pedido no briefing, use a música da ficha',text)
        P.analisar('Teste','video')
        queued=Path(fila.ler()[0]['prompt']).read_text()
        self.assertIn(P.POLITICA_MUSICA,queued)
        self.assertIn('POLÍTICA DO ACERVO VISUAL',queued)
        self.assertIn('MÚSICA tem política separada',queued)

    def test_export_full_and_cleanup(self):
        j=self.job();r=A.exportar('Teste','video',self.root/'Mac')
        self.assertEqual(r['status'],'exportado');self.assertTrue((Path(r['pasta_mac'])/'bruto/raw.mp4').is_file())
        self.assertTrue((Path(r['pasta_mac'])/'final/video.mp4').is_file());self.assertTrue((self.root/j['sandbox']).exists())
        self.assertTrue(r['modelo_estrategico_atualizado']);self.assertEqual(C.ler_json(self.mod/'ficha.json')['comando'],'bash gerar.sh --legy 1270')
        r=A.limpar('Teste','video');self.assertEqual(r['status'],'arquivado');self.assertFalse((self.root/j['sandbox']).exists())
        self.assertEqual([p.name for p in P._pasta_job('Teste','video').iterdir()],['job.json'])
        self.assertEqual(self.client.get('/job/Teste/video').status_code,200)

    def test_export_requires_approval(self):
        self.job('concluido')
        with self.assertRaises(ValueError):A.exportar('Teste','video',self.root/'Mac')

    def test_tampered_copy_preserves_source(self):
        j=self.job();r=A.exportar('Teste','video',self.root/'Mac');(Path(r['pasta_mac'])/'final/video.mp4').write_bytes(b'BROKEN')
        with self.assertRaises(ValueError):A.limpar('Teste','video')
        self.assertTrue((self.root/j['saida']).exists());self.assertTrue((self.root/j['sandbox']).exists())

    def test_changed_source_blocks_cleanup(self):
        j=self.job();A.exportar('Teste','video',self.root/'Mac');(self.root/j['saida']).write_bytes(b'NEW')
        with self.assertRaises(ValueError):A.limpar('Teste','video')
        self.assertTrue((self.root/j['sandbox']).exists())

    def test_export_no_space(self):
        j=self.job()
        with patch('arquivo.shutil.disk_usage',return_value=type('Disk',(),{'free':1})()):
            with self.assertRaises(ValueError):A.exportar('Teste','video',self.root/'Mac')
        self.assertTrue((self.root/j['saida']).exists());self.assertEqual(P.carregar('Teste','video')['status'],'aprovado')

    def test_queue_snapshot_and_no_duplicates(self):
        j=self.job('novo');fila.enfileirar(j,'Teste','analise','plano');fila.enfileirar(j,'Teste','analise','plano')
        self.assertEqual(len(fila.ler()),1);self.assertEqual(P.carregar('Teste','video')['status'],'na_fila')
        C.gravar_json(ia.CONFIG,{**ia.DEFAULTS,'provedor':'openai','modelo_gpt':'gpt-personalizado'})
        self.assertEqual(fila.ler()[0]['ia']['provedor'],'claude');fila.cancelar('Teste','video')
        self.assertEqual(fila.ler()[0]['estado'],'cancelado')

    def test_priority_and_limits(self):
        for i in range(5):fila.enfileirar(self.job('novo',f'v{i}'),'prompt','analise','plano')
        fila.priorizar('Teste','v4');self.assertEqual(fila.ler()[0]['slug'],'v4')
        with patch.object(fila.subprocess,'Popen') as pop:
            pop.return_value.pid=os.getpid();fila.ciclo()
            self.assertEqual(pop.call_count,3)
        self.assertEqual(sum(x['estado']=='na_fila' for x in fila.ler()),2)

    def test_render_needs_approved_takes(self):
        j=self.job('plano')
        with self.assertRaises(ValueError):P.renderizar('Teste','video')
        P.aprovar_plano('Teste','video',{},{});P.renderizar('Teste','video');self.assertEqual(len(fila.ler()),1)

    def test_background_timeout_is_failure_even_with_exit_zero(self):
        import io
        from unittest.mock import MagicMock
        proc=MagicMock()
        proc.stdin=MagicMock()
        proc.stdout=io.StringIO('Background tasks still running after 600s; terminating.\n'+json.dumps({'type':'result','is_error':False})+'\n')
        proc.wait.return_value=0;proc.poll.return_value=0
        with patch.object(ia,'comando',return_value=['fake']),patch.object(ia.subprocess,'Popen',return_value=proc) as spawn:
            code=ia.executar('teste',self.root/'run.log',self.root/'run.jsonl',self.root/'pid',
                             {'provedor':'claude','modelo':'sonnet'})
        self.assertEqual(code,1)
        self.assertEqual(spawn.call_args.kwargs['env']['CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS'],'0')

    def test_video_visible_when_execution_failed(self):
        j=self.job('erro')
        response=self.client.get('/job/Teste/video')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'/arquivo/'+j['saida'].encode(),response.data)
        self.assertIn('revisão pendente',response.text)

    def test_renderer_does_not_take_other_job(self):
        from datetime import datetime
        j=self.job();start=datetime.now();other=self.content/'output/estilo/other.mp4';other.write_bytes(b'other')
        self.assertFalse(P._detectar_saida(j,start,'producao'));self.assertNotEqual(j['saida'],str(other.relative_to(self.root)))

    def test_approved_feedback_with_text(self):
        self.job('concluido');P.feedback('Teste','video','aprovado','Manter legenda abaixo do queixo','legenda')
        self.assertEqual(fila.ler()[0]['tipo'],'feedback');self.assertEqual(P.carregar('Teste','video')['feedbacks'][-1]['decisao'],'aprovado')

    def test_catalog_and_commands(self):
        with patch.object(ia,'codex_bin',return_value='/bin/codex'),patch.object(ia,'catalogo',return_value=[{'id':'gpt-test','esforcos':['high','ultra']}]):
            cmd=ia.comando({'provedor':'openai','modelo':'gpt-test','ultra_mode':True})
        self.assertIn('gpt-test',cmd);self.assertIn('model_reasoning_effort="ultra"',cmd)
        self.assertIn('workspace-write',cmd);self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',cmd)

    def test_reasoning_effort_selection(self):
        catalog=[{'id':'gpt-test','esforcos':['low','medium','high','xhigh']}]
        with patch.object(ia,'codex_bin',return_value='/bin/codex'),patch.object(ia,'catalogo',return_value=catalog):
            s={'provedor':'openai','modelo':'gpt-test','ultra_mode':False,'esforco':'medium'}
            self.assertIn('model_reasoning_effort="medium"',ia.comando(s))
            self.assertIn('model_reasoning_effort="xhigh"',ia.comando({**s,'ultra_mode':True}))
            self.assertFalse(any('model_reasoning_effort' in x for x in ia.comando({**s,'esforco':'max'})))

    def test_worker_rechecks_arrival_during_shutdown(self):
        with patch.object(fila,'ciclo',side_effect=[False,False]) as cycle,patch.object(fila,'ler',side_effect=[[{'estado':'na_fila'}],[]]):
            fila.worker()
        self.assertEqual(cycle.call_count,2)

    def test_reference_retry_only_resumes_owned_model(self):
        d={'slug':'ref-teste','cliente':'Teste','status':'erro','fase_erro':'construir',
           'nome_aprovado':'estilo','criado_em':'2026-09-17'}
        estudo.salvar(d)
        with self.assertRaises(ValueError):estudo.iniciar(d['slug'],'construir','estilo')
        C.gravar_json(self.mod/'.estudo-origem.json',{'slug':d['slug']})
        with patch.object(estudo.subprocess,'Popen') as pop:
            pop.return_value.pid=123456;estudo.iniciar(d['slug'],'construir','estilo')
        saved=estudo.carregar(d['slug'])
        self.assertEqual(saved['status'],'construindo');self.assertNotIn('fase_erro',saved)

    def test_batch_delete_retains_jobs_that_failed(self):
        self.job();l={'slug':'lote-teste','cliente':'Teste','jobs':['video']}
        C.gravar_json(lotes.LOTES/(l['slug']+'.json'),l)
        with patch.object(P,'apagar',side_effect=ValueError('Vídeo ocupado')):
            result=lotes.acao(l,'apagar')
        self.assertIn('Vídeo ocupado',result[0]);self.assertEqual(lotes.carregar(l['slug'])['jobs'],['video'])

    def test_rules_cover_values_restore_history(self):
        p=self.mod/'aprendizado/regras.json';h=p.with_name('historico.jsonl');h.write_text('histórico intacto\n')
        original={'regras':[{'id':'a','categoria':'legenda','peso':10,'texto':'legy 1270; usar /tmp/words.json'},
                              {'id':'b','categoria':'legenda','peso':5,'texto':'Use https://example.org/a e fonte #FF1234'}]}
        C.gravar_json(p,original);before=p.read_bytes();regras.consolidar(p);new=C.ler_json(p)
        self.assertEqual(regras.validar(original,new),[]);self.assertEqual(len(new['regras']),1)
        self.assertEqual(h.read_text(),'histórico intacto\n');regras.restaurar(p);self.assertEqual(p.read_bytes(),before)
        new['regras'][0]['texto']='legy';self.assertTrue(regras.validar(original,new))

    def test_aprendizado_video_aberto_segura_o_historico(self):
        """Histórico de vídeo ainda aberto não pode ser arquivado — ele ainda vai conferir a peça."""
        ap=self.mod/'aprendizado'
        C.append_jsonl(ap/'historico.jsonl',{'tipo':'feedback','texto':'a legenda subiu demais','origem':'usuario'})
        self.jobs.mkdir(parents=True,exist_ok=True)
        (self.jobs/'Teste/video1').mkdir(parents=True)
        C.gravar_json(self.jobs/'Teste/video1/job.json',{'cliente':'Teste','modelo':'estilo','slug':'video1','status':'feedback'})
        vai,fica=aprendizado.pendentes(ap)
        self.assertEqual((len(vai),len(fica)),(0,1))
        aprendizado.arquivar_historico(ap)
        self.assertEqual(len(aprendizado.historico(ap)),1)
        # fechado o vídeo, o cru sai da frente mas continua recuperável no arquivo
        C.gravar_json(self.jobs/'Teste/video1/job.json',{'cliente':'Teste','modelo':'estilo','slug':'video1','status':'arquivado'})
        r=aprendizado.fechar(ap,'video1',com_ia=False)
        self.assertEqual(r['arquivadas'],1)
        self.assertEqual(aprendizado.historico(ap),[])
        self.assertTrue(any(p.stat().st_size>0 for p in (ap/'arquivo').glob('historico-*.jsonl')))

    def test_aprendizado_nao_deixa_sumir_valor_concreto(self):
        """Enxugar corta narrativa, nunca medida: a substituição é recusada se um valor sumir."""
        ap=self.mod/'aprendizado'
        C.gravar_json(ap/'regras.json',{'regras':[{'id':'legenda','categoria':'legenda','peso':9,
            'texto':'Legenda em --legy 1270 com fontsize 50, pedido dele em 14/08.'}]})
        with self.assertRaises(ValueError):
            aprendizado.substituir(ap,[{'id':'legenda','categoria':'legenda','peso':9,'texto':'Legenda mais abaixo.'}])
        novo=[{'id':'legenda','categoria':'legenda','peso':9,'texto':'Legenda em --legy 1270, fontsize 50.'}]
        self.assertEqual(aprendizado.substituir(ap,novo)['para'],1)

    def test_remover_modelo_vai_pra_lixeira_e_volta(self):
        """Remover não apaga: o modelo, os vídeos e a linha do CLAUDE.md voltam inteiros."""
        (self.content/'output/estilo').mkdir(parents=True)
        (self.content/'output/estilo/pronto.mp4').write_bytes(b'0'*10)
        (self.root/'CLAUDE.md').write_text('| Teste | `estilo` | `Teste/testeContent/modelos/estilo/aprendizado/` |\n')
        self.jobs.mkdir(parents=True,exist_ok=True);(self.jobs/'Teste/v1').mkdir(parents=True)
        C.gravar_json(self.jobs/'Teste/v1/job.json',{'cliente':'Teste','modelo':'estilo','slug':'v1','status':'feedback'})
        with self.assertRaises(ValueError):          # vídeo em aberto trava a remoção
            novo_cliente.remover_modelo('Teste','estilo')
        C.gravar_json(self.jobs/'Teste/v1/job.json',{'cliente':'Teste','modelo':'estilo','slug':'v1','status':'arquivado'})
        r=novo_cliente.remover_modelo('Teste','estilo','não é a cara do cliente')
        self.assertFalse(self.mod.exists())
        self.assertNotIn('modelos/estilo/aprendizado',(self.root/'CLAUDE.md').read_text())
        itens=novo_cliente.lixeira()
        self.assertEqual((len(itens),itens[0]['videos'],itens[0]['pode_voltar']),(1,1,True))
        novo_cliente.restaurar_modelo(r['id'])
        self.assertTrue((self.mod/'ficha.json').exists())
        self.assertTrue((self.content/'output/estilo/pronto.mp4').exists())
        self.assertIn('modelos/estilo/aprendizado',(self.root/'CLAUDE.md').read_text())
        self.assertEqual(novo_cliente.lixeira(),[])

    def test_apagar_da_lixeira_e_caminho_seguro(self):
        (self.root/'CLAUDE.md').write_text('| Teste | `estilo` | `Teste/testeContent/modelos/estilo/aprendizado/` |\n')
        r=novo_cliente.remover_modelo('Teste','estilo')
        for ident in ('..','x/y','nao-existe'):
            with self.assertRaises(ValueError):C.lixeira_item(ident)
        self.assertTrue(novo_cliente.apagar_da_lixeira(r['id']))
        self.assertEqual(novo_cliente.lixeira(),[])

    def test_assets_do_modelo_trocar_remover_restaurar(self):
        """Asset é o material fixo do modelo: dá pra trocar, tirar (lixeira) e trazer de volta."""
        a=self.mod/'assets/musica';a.mkdir(parents=True)
        (a/'bed.mp3').write_bytes(b'0'*2048)
        (self.mod/'gerar.sh').write_text('ffmpeg -i assets/musica/bed.mp3')
        itens=ficha.assets(self.mod)
        self.assertEqual((len(itens),itens[0]['tipo'],itens[0]['usado_por']),(1,'audio',['gerar.sh']))
        with self.assertRaises(ValueError):                  # citado por script: renomear quebraria
            ficha.renomear_asset(self.mod,'musica/bed.mp3','outro-nome')
        for ruim in ('../segredo.mp3','/etc/passwd'):
            with self.assertRaises(ValueError):ficha.caminho_asset(self.mod,ruim)
        novo=self.root/'nova.mp3';novo.write_bytes(b'1'*512)
        r=ficha.subir_asset(self.mod,novo,'bed','musica')     # mesmo nome: substitui e guarda o velho
        self.assertEqual((self.mod/'assets/musica/bed.mp3').read_bytes(),b'1'*512)
        self.assertTrue(r['substituiu'])
        rem=ficha.remover_asset(self.mod,'musica/bed.mp3',cliente='Teste',modelo='estilo')
        self.assertFalse((self.mod/'assets/musica/bed.mp3').exists())
        self.assertEqual(ficha.assets(self.mod),[])
        ficha.restaurar_asset(rem['id'])
        self.assertEqual((self.mod/'assets/musica/bed.mp3').read_bytes(),b'1'*512)
        # o asset substituído continua recuperável, e a lixeira lista os dois tipos de item
        self.assertTrue(any(x['tipo']=='asset' for x in novo_cliente.lixeira()))

    def test_templates_do_cliente_viram_material_do_video(self):
        """Template do cliente é reusável: marcar copia pro vídeo e o original continua lá."""
        cli=C.cliente('Teste')
        col=material.criar(cli,'Marca3','capas e provas','produto')
        origem=self.root/'capa.png';origem.write_bytes(b'x'*64)
        material.subir(cli,col['slug'],origem)
        self.assertEqual(material.colecoes(cli)[0]['n'],1)
        copias=material.copiar_para(cli,[col['slug']],self.root/'tmp')
        self.assertEqual(len(copias),1)
        self.assertTrue((self.content/'material'/col['slug']/'capa.png').exists())  # copiou, não moveu
        for ruim in ('../x.png','a/../../y.png'):
            with self.assertRaises(ValueError):material.caminho(cli,col['slug'],ruim)
        r=material.remover_item(cli,col['slug'],'capa.png')
        self.assertEqual(material.colecoes(cli)[0]['n'],0)
        material.restaurar(r['id'])
        self.assertEqual(material.colecoes(cli)[0]['n'],1)
        rc=material.remover_colecao(cli,col['slug'])
        self.assertEqual(material.colecoes(cli),[])
        material.restaurar(rc['id'])
        self.assertEqual(len(material.colecoes(cli)),1)

    def test_referencia_briefing_com_pontos(self):
        b=estudo.briefing_com_pontos('copia o ritmo',['ritmo','xxx'],{'ritmo':'corte seco'},'12s — virada')
        self.assertIn('Ritmo e cortes',b);self.assertIn('corte seco',b);self.assertIn('12s — virada',b)
        self.assertNotIn('xxx',b)
        self.assertEqual(estudo.briefing_com_pontos('só isso',[],{},''),'só isso')

    def test_remover_projeto_inteiro_vai_pra_lixeira_e_volta(self):
        """Projeto removido leva modelos, templates e o registro dos vídeos — e volta inteiro."""
        (self.root/'CLAUDE.md').write_text('| Teste | `estilo` | `Teste/testeContent/modelos/estilo/aprendizado/` |\n')
        self.jobs.mkdir(parents=True,exist_ok=True);(self.jobs/'Teste/v1').mkdir(parents=True)
        C.gravar_json(self.jobs/'Teste/v1/job.json',{'cliente':'Teste','modelo':'estilo','slug':'v1','status':'feedback'})
        with self.assertRaises(ValueError):                  # vídeo em aberto trava
            novo_cliente.remover_cliente('Teste')
        C.gravar_json(self.jobs/'Teste/v1/job.json',{'cliente':'Teste','modelo':'estilo','slug':'v1','status':'arquivado'})
        r=novo_cliente.remover_cliente('Teste','não vai rolar')
        self.assertFalse((self.root/'Teste').exists())
        self.assertFalse((self.jobs/'Teste').exists())
        self.assertNotIn('modelos/estilo/aprendizado',(self.root/'CLAUDE.md').read_text())
        item=[x for x in novo_cliente.lixeira() if x['tipo']=='cliente'][0]
        self.assertTrue(item['pode_voltar'])
        novo_cliente.restaurar(r['id'])
        self.assertTrue((self.mod/'ficha.json').exists())
        self.assertTrue((self.jobs/'Teste/v1/job.json').exists())
        self.assertIn('modelos/estilo/aprendizado',(self.root/'CLAUDE.md').read_text())

    def test_asset_do_motor_sabe_se_ja_esta_no_acervo(self):
        """O arquivo do motor mostra se já está no acervo — e mandar de novo não duplica."""
        a=self.mod/'assets/musica';a.mkdir(parents=True)
        (a/'bed.mp3').write_bytes(b'musica'*300)
        with patch.object(acervo,'ACERVO',self.root/'acervo/itens'), \
             patch.object(acervo,'descrever',lambda slug: True):
            self.assertIsNone(ficha.assets(self.mod)[0]['no_acervo'])
            r=ficha.asset_pro_acervo(self.mod,'musica/bed.mp3',cliente='Teste',modelo='estilo')
            self.assertFalse(r.get('ja_estava'))
            self.assertIn('musica',r['tags'])
            self.assertEqual(ficha.assets(self.mod)[0]['no_acervo'],r['slug'])
            de_novo=ficha.asset_pro_acervo(self.mod,'musica/bed.mp3',cliente='Teste',modelo='estilo')
            self.assertTrue(de_novo['ja_estava'])
            self.assertEqual(len(acervo.listar()),1)

    def test_acervo_separa_musica_de_efeito(self):
        """Cama e efeito não moram na mesma gaveta: quem decide é a duração, não o nome da pasta."""
        self.assertEqual(acervo._tipo('.mp3', Path('x/bed.mp3'), 120.0), 'musica')
        self.assertEqual(acervo._tipo('.mp3', Path('x/bed.mp3'), 0.4), 'sfx')      # curto = efeito
        self.assertEqual(acervo._tipo('.mp3', Path('sfx/whoosh.mp3'), None), 'sfx')  # sem duração, o nome
        self.assertEqual(acervo._tipo('.mp3', Path('musica/cama.mp3'), None), 'musica')
        self.assertEqual(acervo._tipo('.png', Path('a.png')), 'imagem')
        self.assertTrue(all(acervo.eh_audio(t) for t in ('musica', 'sfx', 'audio')))
        self.assertIn(('musica', 'Músicas'), acervo.TIPOS)
        self.assertIn(('sfx', 'Efeitos sonoros'), acervo.TIPOS)

    def test_card_do_acervo_resume_a_descricao(self):
        """A descrição da IA tem 1.000+ caracteres: no card entra o resumo, o resto fica dobrado."""
        longa = "Instrumental sem voz com pulsos graves. " * 30
        self.assertLessEqual(len(acervo.resumo_curto({'descricao': longa})), 195)
        self.assertTrue(acervo.resumo_curto({'descricao': longa}).endswith(('.', '…')))
        curta = "Cama tensa e curta."
        self.assertEqual(acervo.resumo_curto({'descricao': curta}), curta)
        # sem prosa, a primeira linha da análise técnica já diz o essencial
        self.assertEqual(acervo.resumo_curto({'resumo_audio': '90s · 86 BPM\ntimbre: grave 0.3'}),
                         '90s · 86 BPM')
        self.assertEqual(acervo.resumo_curto({}), '')

    def test_acervo_classifica_como_soa_pelo_audio(self):
        """70 arquivos chamados opF-coldcase: sem classificar pelo som, não dá pra escolher."""
        import musica
        grave_constante={'duracao_s':120,'bpm':100,'bpm_confianca':0.4,'faixa_dinamica_lu':2,
                         'bandas_geral':{'grave':0.6,'medio':0.3,'agudo':0.1}}
        self.assertEqual(musica.caracteristicas(grave_constante)['clima'],'tensa')
        cresce={'duracao_s':180,'bpm':100,'bpm_confianca':0.4,'faixa_dinamica_lu':12,
                'bandas_geral':{'grave':0.3,'medio':0.5,'agudo':0.2},'pico_energia_s':160}
        c=musica.caracteristicas(cresce)
        self.assertEqual(c['clima'],'épica');self.assertTrue(c['cresce'])
        efeito={'duracao_s':0.4,'bandas_geral':{'grave':0.3,'medio':0.4,'agudo':0.3}}
        self.assertEqual(musica.caracteristicas(efeito)['formato'],'efeito')
        self.assertNotIn('clima',musica.caracteristicas(efeito))   # efeito não tem clima
        self.assertEqual(musica.caracteristicas({}),{})
        self.assertIn('cresce no fim',musica.como_soa(c))

    def test_corte_remove_repeticao_mesmo_sem_errei_falado(self):
        """Ele refaz o take sem avisar e 15s depois: exigir marcador falado deixava tudo passar."""
        import corte
        segs=[{'i':0,'t0':0,'t1':4,'texto':'e nesse tipo de caso vem uma perícia médica'},
              {'i':1,'t0':5,'t1':9,'texto':'com um profissional indicado pela justiça ele avalia se a função contribuiu'},
              {'i':2,'t0':20,'t1':24,'texto':'E nesse tipo de caso vem uma perícia médica.'},
              {'i':3,'t0':25,'t1':33,'texto':'Um profissional indicado pela justiça avalia se a função que você exercia contribuiu'}]
        fora=corte._fora_por_repeticao(segs)
        self.assertEqual(sorted(fora),[0,1])            # saem as PRIMEIRAS versões
        # negação diferente = fala diferente, não é repetição
        oposto=[{'i':0,'t0':0,'t1':3,'texto':'não é do dia para a noite'},
                {'i':1,'t0':5,'t1':8,'texto':'é do dia para a noite'}]
        self.assertEqual(corte._fora_por_repeticao(oposto),{})
        # falso começo: ele para no meio e completa depois
        falso=[{'i':0,'t0':0,'t1':2,'texto':'achar que parou quando está'},
               {'i':1,'t0':9,'t1':13,'texto':'achar que parou quando está o processo continua tramitando'}]
        self.assertIn(0,corte._fora_por_repeticao(falso))

    def test_corte_apara_gaguejo_da_emenda(self):
        """Ele começa a frase, para e recomeça: '…tá? Primeira' + 'Primeira, se o serviço…'.

        Os textos inteiros são diferentes, então nenhuma regra de segmento pega — mas no vídeo a
        palavra sai duas vezes. A cauda tem que ser aparada no tempo da palavra, sem perder o resto.
        """
        import corte
        pal=lambda t0,t1,p:{'t0':t0,'t1':t1,'p':p}
        palavras=[pal(23.3,23.8,'E'),pal(23.8,24.6,'olha'),pal(24.6,25.0,'coisas,'),
                  pal(25.0,25.2,'tá?'),pal(25.2,25.68,'Primeira'),
                  pal(27.5,28.0,'Primeira,'),pal(28.0,28.9,'se'),pal(28.9,33.0,'serviço')]
        lista=[{'i':4,'t0':23.3,'t1':25.68,'texto':'E olha coisas, tá? Primeira','manter':True,'motivo':'fala boa'},
               {'i':5,'t0':27.5,'t1':33.0,'texto':'Primeira, se serviço','manter':True,'motivo':'fala boa'}]
        self.assertEqual(corte._aparar_emendas(lista,palavras),1)
        self.assertLess(lista[0]['t1'],25.68)                  # a cauda saiu
        self.assertNotIn('Primeira',lista[0]['texto'])         # e o texto acompanhou
        self.assertTrue(lista[0]['manter'])                    # sem perder o resto da fala
        self.assertEqual(corte.emendas_gaguejando(lista,palavras),[])
        # quando o trecho é SÓ o falso começo, ele sai inteiro
        so=[{'i':0,'t0':10,'t1':10.5,'texto':'Primeira','manter':True,'motivo':'fala boa'},
            {'i':1,'t0':12,'t1':15,'texto':'Primeira, se serviço','manter':True,'motivo':'fala boa'}]
        corte._aparar_emendas(so,[pal(10,10.5,'Primeira'),pal(12,12.4,'Primeira,'),pal(12.4,15,'serviço')])
        self.assertFalse(so[0]['manter'])

    def test_guarda_aceita_aparo_e_recusa_invencao(self):
        """Aparar a cauda é legítimo; mexer no começo, ampliar ou inventar palavra continua barrado."""
        from corte_qualidade import validar
        fonte=[{'i':0,'texto':'E ele olha as duas coisas, tá? Primeira','t0':23.28,'t1':25.68}]
        validar({'segmentos':[{'i':0,'texto':'E ele olha as duas coisas, tá?','t0':23.28,'t1':25.26,'manter':True}]},fonte)
        for ruim in ({'texto':'E ele olha as duas coisas, tá? Primeira vez'},   # inventou palavra
                     {'texto':'olha as duas coisas, tá? Primeira'},            # cortou o começo
                     {'t0':23.6},                                              # mexeu na borda inicial
                     {'t1':26.9}):                                             # ampliou além do gravado
            with self.assertRaises(ValueError):
                validar({'segmentos':[{**fonte[0],'manter':True,**ruim}]},fonte)
        # e a negação continua protegida: tirar o "Não" do começo inverte o sentido
        neg=[{'i':0,'texto':'Não desista.','t0':0,'t1':1}]
        with self.assertRaises(ValueError):
            validar({'segmentos':[{'i':0,'texto':'desista.','t0':0,'t1':1,'manter':True}]},neg)

    def test_semantic_text_fallback_incremental(self):
        path=acervo.ACERVO/'clip';path.mkdir(parents=True);C.gravar_json(path/'meta.json',{'titulo':'Relógio com pressa','tags':['tempo'],'descricao':'prazo acabando','tipo':'video'})
        first=semantica.reindexar();second=semantica.reindexar();self.assertEqual(second['alterados'],0)
        self.assertTrue(semantica.consultar('o tempo está acabando'));self.assertEqual(semantica.politica('não usa o acervo'),'ignorar')

    def test_templates_states(self):
        j=self.job('concluido')
        for status in ('novo','na_fila','plano','plano_aprovado','concluido','aprovado','erro','exportado'):
            j['status']=status;P.salvar(j)
            self.assertEqual(self.client.get('/job/Teste/video').status_code,200,status)
        for path in ('/','/config','/novo-lote','/lotes','/referencias','/nova-referencia','/arquivo'):
            self.assertEqual(self.client.get(path).status_code,200,path)

    def test_modelo_com_regra_sem_categoria_abre(self):
        C.gravar_json(self.mod/'aprendizado/regras.json',{'regras':[
            {'id':'antiga','texto':'Preserve a fala.'},
            {'id':'nova','categoria':'audio','peso':8,'texto':'Normalize a voz.'},
            {'id':'sem-valor','categoria':None,'texto':'Confira as emendas.'}]})
        response=self.client.get('/cliente/Teste/modelo/estilo')
        self.assertEqual(response.status_code,200)
        self.assertIn('Preserve a fala.',response.get_data(as_text=True))

    def test_path_validation(self):
        with self.assertRaises(ValueError):P._pasta_job('..','x')
        with self.assertRaises(ValueError):A.seguro(self.root/'../outside')
        self.assertIsNone(C.modelo(C.cliente('Teste'),'../estilo'))

    def test_batch_reuses_bruto_with_copies(self):
        raw=self.root/'bruto.mp4';raw.write_bytes(b'raw')
        l=lotes.criar('Teste','Variações','brief',[dict(bruto=raw,modelo='estilo',titulo='v1'),dict(bruto=raw,modelo='estilo',titulo='v2')])
        self.assertEqual(len(l['jobs']),2);self.assertTrue(raw.exists())
        self.assertNotEqual(P.carregar('Teste',l['jobs'][0])['bruto'],P.carregar('Teste',l['jobs'][1])['bruto'])

if __name__=='__main__':unittest.main()
