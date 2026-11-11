"""Cartão 'Quem edita os vídeos': modelo único que define o provedor, chaves de API coladas (nunca de volta), cobrança por
provedor e 'Chaves e onde estão'. Sem rede e sem crédito: cliente falso em tudo."""
import io
import json
import logging
import os
import stat
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

AQUI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AQUI / 'ferramentas'), str(AQUI / 'interface')]
import chaves
import ia
import producao
import via_api

SEGREDO = 'sk-segredo-que-nunca-pode-aparecer-ZZ99'
SEGREDO2 = 'gsk-outro-segredo-que-tambem-nao-aparece-QQ77'
CATALOGO = [{'id': 'gpt-6.1-sol', 'nome': 'GPT-6.1-Sol', 'visivel': True, 'descricao': 'Latest workhorse model for coding.', 'esforcos': ['low']},
            {'id': 'gpt-6-astra', 'nome': 'GPT-6-Astra', 'visivel': True, 'descricao': 'Frontier intelligence for the most demanding work.', 'esforcos': []},
            {'id': 'gpt-escondido', 'nome': 'Escondido', 'visivel': False, 'descricao': 'Legacy coding model.', 'esforcos': []}]


class FalsaResposta(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Modelo(unittest.TestCase):
    def test_escolher_modelo_define_o_provedor_e_mantem_os_campos_antigos(self):
        cfg = ia.aplicar_modelo({'provedor': 'claude', 'modelo_claude': 'opus', 'modelo_gpt': ''}, 'gpt:gpt-6.1-sol')
        self.assertEqual((cfg['provedor'], cfg['modelo_gpt'], cfg['modelo_claude']), ('openai', 'gpt-6.1-sol', 'opus'))
        cfg = ia.aplicar_modelo(cfg, 'claude:sonnet')
        self.assertEqual((cfg['provedor'], cfg['modelo_claude'], cfg['modelo_gpt']), ('claude', 'sonnet', 'gpt-6.1-sol'))
        cfg = ia.aplicar_modelo(cfg, 'gpt:')   # padrão da conta
        self.assertEqual((cfg['provedor'], cfg['modelo_gpt']), ('openai', ''))
        self.assertEqual(ia.aplicar_modelo({'provedor': 'claude'}, None), {'provedor': 'claude'})
        self.assertEqual(ia.aplicar_modelo({'provedor': 'claude'}, 'lixo'), {'provedor': 'claude'})

    def test_versao_vem_do_id_real(self):
        self.assertEqual(ia.nome_do_id('claude-sonnet-5-5'), 'Sonnet 5.5')
        self.assertEqual(ia.nome_do_id('claude-opus-5-5'), 'Opus 5.5')
        self.assertEqual(ia.nome_do_id('claude-haiku-4-5-20251001'), 'Haiku 4.5')
        self.assertEqual(ia.nome_do_id('qualquer-coisa'), 'qualquer-coisa')

    def test_versao_aprendida_do_claude_vale_mais_que_a_semente(self):
        with tempfile.TemporaryDirectory() as t, patch.object(ia, 'APRENDIDOS', Path(t) / 'm.json'):
            self.assertEqual(ia.id_claude('sonnet'), 'claude-sonnet-5-5')
            ia.aprender_modelo_claude('sonnet', 'claude-sonnet-5-6')
            self.assertEqual(ia.nome_claude('sonnet'), 'Sonnet 5.6')
            ia.aprender_modelo_claude('sonnet', 'lixo[1m]')   # id estranho não entra
            self.assertEqual(ia.id_claude('sonnet'), 'claude-sonnet-5-6')

    def test_uma_lista_so_de_modelos_do_claude(self):
        self.assertIs(producao.MODELOS_CLAUDE, ia.MODELOS_CLAUDE)

    def test_opcoes_agrupadas_com_versao_frase_e_custo(self):
        with tempfile.TemporaryDirectory() as t, patch.object(ia, 'APRENDIDOS', Path(t) / 'm.json'), patch.object(ia, 'catalogo', return_value=CATALOGO):
            g = ia.opcoes_modelo({'provedor': 'claude', 'modelo_claude': 'sonnet', 'modelo_gpt': ''})
        self.assertEqual([x['provedor'] for x in g], ['claude', 'openai'])
        claude = {i['valor']: i for i in g[0]['itens']}
        self.assertEqual(claude['claude:sonnet']['nome'], 'Claude Sonnet 5.5')
        self.assertEqual(claude['claude:sonnet']['id'], 'claude-sonnet-5-5')
        self.assertEqual(claude['claude:haiku']['id'], 'claude-haiku-4-5-20251001')
        self.assertEqual([claude[k]['custo'] for k in ('claude:opus', 'claude:sonnet', 'claude:haiku')], ['caro', 'médio', 'barato'])
        self.assertTrue(claude['claude:sonnet']['atual'])
        gpt = {i['valor']: i for i in g[1]['itens']}
        self.assertIn('gpt:gpt-6.1-sol', gpt)
        self.assertNotIn('gpt:gpt-escondido', gpt)   # só o que o Codex lista
        self.assertEqual(gpt['gpt:gpt-6-astra']['custo'], 'caro')
        self.assertFalse(any(i['atual'] for i in g[1]['itens']))

    def test_gpt_escolhido_fora_da_lista_continua_aparecendo(self):
        with patch.object(ia, 'catalogo', return_value=CATALOGO):
            g = ia.opcoes_modelo({'provedor': 'openai', 'modelo_gpt': 'gpt-escondido', 'modelo_claude': 'opus'})
        atual = [i for i in g[1]['itens'] if i['atual']]
        self.assertEqual([i['valor'] for i in atual], ['gpt:gpt-escondido'])

    def test_linha_agora(self):
        with patch('chaves.configurada', return_value=False):
            self.assertEqual(ia.agora({'provedor': 'claude', 'modelo_claude': 'sonnet'}), 'Claude Sonnet 5.5 · pelo plano do Claude Code')
            self.assertEqual(ia.agora({'provedor': 'openai', 'modelo_gpt': 'gpt-6.1-sol', 'cobranca_gpt': 'api'}), 'gpt-6.1-sol · pelo login do ChatGPT')
        with patch('chaves.configurada', return_value=True):
            self.assertIn('pela API da Anthropic', ia.agora({'provedor': 'claude', 'modelo_claude': 'opus'}))
            self.assertIn('pela API da OpenAI', ia.agora({'provedor': 'openai', 'modelo_gpt': 'x', 'cobranca_gpt': 'api'}))


class Cobranca(unittest.TestCase):
    def test_gpt_sem_chave_fica_desligado(self):
        with patch('chaves.configurada', return_value=False):
            self.assertEqual(ia.cobranca({'provedor': 'openai', 'cobranca_gpt': 'api'}), 'assinatura')
            e = ia.estado_cobranca({'cobranca_gpt': 'api'})['openai']
        self.assertFalse(e['ligada'])
        self.assertEqual(e['texto'], 'cole a chave acima')

    def test_gpt_com_chave_e_ligado_so_se_o_joao_ligar(self):
        with patch('chaves.configurada', return_value=True):
            self.assertEqual(ia.cobranca({'provedor': 'openai', 'cobranca_gpt': 'api'}), 'api')
            self.assertEqual(ia.cobranca({'provedor': 'openai'}), 'assinatura')
            self.assertEqual(ia.estado_cobranca({'cobranca_gpt': 'api'})['openai']['texto'], 'este vídeo vai cobrar do seu crédito da OpenAI')
            self.assertEqual(ia.estado_cobranca({'cobranca': 'api'})['anthropic']['texto'], 'este vídeo vai cobrar do seu crédito da Anthropic')
            self.assertEqual(ia.estado_cobranca({'cobranca': 'assinatura'})['anthropic']['texto'], 'usa o plano (Claude Code ou login do ChatGPT)')

    def test_codex_recebe_a_chave_so_no_ambiente_do_processo(self):
        with patch.object(chaves, 'ler', return_value=SEGREDO):
            e = ia.ambiente({'provedor': 'openai', 'modelo': '', 'cobranca': 'api'})
            self.assertEqual(e['CODEX_API_KEY'], SEGREDO)
            self.assertNotIn('CODEX_API_KEY', ia.ambiente({'provedor': 'openai', 'modelo': '', 'cobranca': 'assinatura'}))
        with patch.object(chaves, 'ler', return_value=''):
            with self.assertRaises(ValueError) as c:
                ia.ambiente({'provedor': 'openai', 'modelo': '', 'cobranca': 'api'})
        self.assertIn('falta a chave da OpenAI', str(c.exception))

    def test_config_valida_cobranca_gpt(self):
        with self.assertRaises(ValueError):
            ia.validar({**ia.DEFAULTS, 'cobranca_gpt': 'qualquer'})


class Chaves(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.arqs = {'anthropic': Path(self.t.name) / 'cfg' / 'anthropic_api_key', 'openai': Path(self.t.name) / 'cfg' / 'openai_api_key'}

    def tearDown(self): self.t.cleanup()

    def test_anthropic_e_o_mesmo_arquivo_do_via_api(self):
        self.assertEqual(chaves.ARQUIVOS['anthropic'], via_api.CHAVE)
        self.assertEqual(chaves.ARQUIVOS['openai'].name, 'openai_api_key')

    def test_salva_com_permissao_600_e_devolve_so_o_final(self):
        fim = chaves.salvar('openai', SEGREDO, self.arqs)
        self.assertEqual(fim, '…ZZ99')
        self.assertNotIn(SEGREDO, fim)
        arq = self.arqs['openai']
        self.assertEqual(stat.S_IMODE(arq.stat().st_mode), 0o600)
        self.assertEqual(arq.read_text().strip(), SEGREDO)

    def test_chave_ruim_da_erro_simples_sem_repetir_o_valor(self):
        for ruim in ('', 'curta', 'tem espaco no meio da chave que e longa'):
            with self.assertRaises(ValueError) as c:
                chaves.salvar('anthropic', ruim, self.arqs)
            self.assertNotIn('espaco no meio', str(c.exception))
        self.assertFalse(self.arqs['anthropic'].exists())

    def test_openai_funcionou_custa_zero_e_nao_chama_rede_de_verdade(self):
        pedidos = []
        def abrir(req, timeout=0):
            pedidos.append(req)
            return FalsaResposta(json.dumps({'data': [{'id': 'a'}, {'id': 'b'}]}).encode())
        r = chaves.salvar_e_testar('openai', SEGREDO, abrir=abrir, arquivos=self.arqs)
        self.assertTrue(r['ok']); self.assertEqual(r['custo'], 0.0); self.assertEqual(r['final'], '…ZZ99')
        self.assertTrue(r['texto'].startswith('Funcionou'))
        self.assertTrue(pedidos[0].full_url.endswith('/v1/models'))   # listar modelos é grátis
        self.assertNotIn(SEGREDO, json.dumps(r))

    def test_openai_erros_em_portugues_simples(self):
        def http(code):
            def abrir(req, timeout=0): raise urllib.error.HTTPError(req.full_url, code, 'x', {}, None)
            return abrir
        r = chaves.testar_openai(SEGREDO, http(401))
        self.assertFalse(r['ok']); self.assertIn('não aceitou', r['texto']); self.assertNotIn(SEGREDO, r['texto'])
        self.assertIn('limite ou falta de crédito', chaves.testar_openai(SEGREDO, http(429))['texto'])
        def sem_rede(req, timeout=0): raise urllib.error.URLError('sem rede')
        self.assertIn('internet', chaves.testar_openai(SEGREDO, sem_rede)['texto'])

    def test_claude_usa_o_teste_do_via_api_com_a_chave_nova_e_mostra_o_custo(self):
        vistos = []
        def rodar(api_key=None):
            vistos.append(api_key); return {'estado': 'ok', 'usd': 0.0412}
        r = chaves.salvar_e_testar('anthropic', SEGREDO, rodar=rodar, arquivos=self.arqs)
        self.assertEqual(vistos, [SEGREDO])
        self.assertTrue(r['ok']); self.assertAlmostEqual(r['custo'], 0.0412)
        self.assertEqual(chaves.usd(r['custo']), 'US$ 0,04')

    def test_claude_erro_nunca_repete_a_chave(self):
        r = chaves.testar_claude(SEGREDO, lambda api_key=None: {'estado': 'erro', 'usd': 0, 'erro': 'Invalid API key ' + SEGREDO})
        self.assertFalse(r['ok']); self.assertIn('não aceitou', r['texto']); self.assertNotIn(SEGREDO, r['texto'])
        r = chaves.testar_claude(SEGREDO, lambda api_key=None: {'estado': 'erro', 'usd': 0, 'erro': 'saiu estranho ' + SEGREDO})
        self.assertNotIn(SEGREDO, r['texto'])

    def test_via_api_testar_dados_aceita_chave(self):
        with patch.object(via_api, 'rodar', return_value={'estado': 'ok', 'fonte': 'ANTHROPIC_API_KEY', 'usd': 0.01}) as m:
            self.assertEqual(via_api.testar_dados('k')['estado'], 'ok')
        self.assertEqual(m.call_args.kwargs['api_key'], 'k')
        with patch.dict(os.environ, {}, clear=True), patch.object(via_api, 'cobranca_fila', return_value='assinatura'):
            self.assertEqual(via_api.ambiente('k')['ANTHROPIC_API_KEY'], 'k')   # forçar a chave vale até com a fila no plano

    def test_final_mostra_so_quatro_caracteres(self):
        with patch.object(chaves, 'ARQUIVOS', self.arqs), patch.object(chaves, 'ENV_APP', Path(self.t.name) / 'app.env'), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(chaves.final('openai'), '')
            chaves.salvar('openai', SEGREDO, self.arqs)
            self.assertEqual(chaves.final('openai'), '…ZZ99')
            self.assertTrue(chaves.configurada('openai'))


class Inventario(unittest.TestCase):
    def monta(self, t):
        t = Path(t); (t / 'app').mkdir(); (t / 'clientes/A').mkdir(parents=True); (t / 'clientes/B').mkdir(parents=True)
        (t / 'app/.env').write_text(f'KIE_API_KEY={SEGREDO}\nGROQ_API_KEY=\nPIXABAY_API_KEY={SEGREDO2}\nGEMINI_API_KEY_6=outra-chave-sem-repeticao-12345\n')
        for c in 'AB': (t / f'clientes/{c}/.env').write_text(f'GROQ_API_KEY={SEGREDO2}\nOPENAI_API_KEY={SEGREDO}\n')
        (t / 'gb.env').write_text('PEXELS_API_KEY=pexels-chave-qualquer-12345\n')
        return dict(raiz=t, estudio=t / 'app', gb_env=t / 'gb.env', gerador=t / 'nao-existe.env', pasta_chaves=t / 'cfg')

    def test_so_sim_ou_nao_e_caminho_nunca_o_valor(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {}, clear=True):
            inv = chaves.inventario(**self.monta(t))
        txt = json.dumps(inv, ensure_ascii=False)
        for v in (SEGREDO, SEGREDO2, 'pexels-chave-qualquer', 'outra-chave-sem-repeticao'):
            self.assertNotIn(v, txt)
        por = {l['nome']: l for l in inv['linhas']}
        self.assertEqual(por['Pexels']['configurada'], 'sim')
        self.assertEqual(por['ElevenLabs']['configurada'], 'não')
        self.assertIn('não configurada', por['ElevenLabs']['onde'][0])
        self.assertNotIn('Gemini (Google)', por)   # o Gemini saiu do Estúdio: nem aparece na lista (a chave antiga fica no arquivo, sem uso)
        self.assertTrue(any(a.startswith('repetida') for a in por['Groq']['avisos']))   # 2 clientes, mesmo valor
        self.assertIn('clientes/<Nome>/.env (A, B)', por['Groq']['onde'])
        self.assertIn('Mixkit', inv['sem_chave'])

    def test_ambiente_aparece_como_onde_sem_valor(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, {'ANTHROPIC_API_KEY': SEGREDO}, clear=True):
            inv = chaves.inventario(**self.monta(t))
        self.assertNotIn(SEGREDO, json.dumps(inv))
        self.assertIn('no ambiente do Estúdio', {l['nome']: l for l in inv['linhas']}['Anthropic (Claude)']['onde'])


class Tela(unittest.TestCase):
    """A página e a rota de chave, com o config.json e a pasta de chaves numa pasta temporária."""
    def setUp(self):
        import servidor
        self.t = tempfile.TemporaryDirectory()
        t = Path(self.t.name)
        self.arqs = {'anthropic': t / 'cfg/anthropic_api_key', 'openai': t / 'cfg/openai_api_key'}
        self.cfg = t / 'config.json'
        self.cfg.write_text(json.dumps({'provedor': 'claude', 'modelo_claude': 'opus', 'modelo_gpt': '', 'cobranca': 'api'}))
        self.env = t / 'app.env'
        self.patches = [patch.object(chaves, 'ARQUIVOS', self.arqs), patch.object(chaves, 'ENV_APP', self.env), patch.object(ia, 'CONFIG', self.cfg),
                        patch.object(ia, 'APRENDIDOS', t / 'm.json'), patch.object(ia, 'catalogo', return_value=CATALOGO),
                        patch.dict(os.environ, {k: v for k, v in os.environ.items() if k not in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY')}, clear=True)]
        for p in self.patches: p.start()
        self.c = servidor.app.test_client()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.t.cleanup()

    def pagina(self): return self.c.get('/config').get_data(as_text=True)

    def test_pagina_tem_um_seletor_so_e_sem_cartoes_antigos(self):
        h = self.pagina()
        self.assertIn('Agora: <b>Claude Opus 5.5 · pelo plano do Claude Code</b>', h)
        self.assertIn('claude-opus-5-5', h); self.assertIn('GPT-6.1-Sol', h)
        self.assertNotIn('Modelo do GPT', h); self.assertNotIn('Modelo do Claude', h)
        self.assertNotIn('<details style="margin-top:12px"><summary class="sub">Modelo do GPT', h)
        self.assertEqual(h.count('name="modelo" '), len(CATALOGO) - 1 + 3 + 1)   # 3 Claude + padrão + os 2 GPT listados

    def test_cobranca_gpt_sem_chave_aparece_desligada_com_a_frase(self):
        h = self.pagina()
        self.assertIn('cole a chave acima', h)
        self.assertRegex(h, r'name="cobrar_api_gpt"[^>]*disabled')

    def test_escolher_gpt_grava_provedor_e_mantem_modelo_claude(self):
        self.c.post('/config', data={'secao': 'ia', 'modelo': 'gpt:gpt-6-astra', 'esforco': 'high'})
        cfg = json.loads(self.cfg.read_text())
        self.assertEqual((cfg['provedor'], cfg['modelo_gpt'], cfg['modelo_claude']), ('openai', 'gpt-6-astra', 'opus'))
        self.assertIn('Agora: <b>gpt-6-astra · pelo login do ChatGPT</b>', self.pagina())

    def test_formulario_antigo_continua_funcionando(self):
        self.c.post('/config', data={'secao': 'ia', 'provedor': 'openai', 'modelo_claude': 'sonnet', 'modelo_gpt': 'gpt-6-sol', 'esforco': 'medium'})
        cfg = json.loads(self.cfg.read_text())
        self.assertEqual((cfg['provedor'], cfg['modelo_claude'], cfg['modelo_gpt']), ('openai', 'sonnet', 'gpt-6-sol'))

    def test_chave_colada_nunca_volta_pra_tela_nem_pro_log(self):
        logs = io.StringIO(); h = logging.StreamHandler(logs); raiz = logging.getLogger(); raiz.addHandler(h)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err), patch.object(chaves, 'testar_openai', return_value={'ok': True, 'texto': 'Funcionou (3 modelos na conta)', 'custo': 0.0}):
                r = self.c.post('/config/chave/openai', data={'chave': SEGREDO}, follow_redirects=True)
        finally:
            raiz.removeHandler(h)
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Funcionou', html); self.assertIn('Custo do teste: US$ 0,00', html); self.assertIn('termina em …ZZ99', html)
        for onde in (html, logs.getvalue(), out.getvalue(), err.getvalue(), self.cfg.read_text()):
            self.assertNotIn(SEGREDO, onde)
        self.assertEqual(chaves.ler_env(self.env)['OPENAI_API_KEY'], SEGREDO)   # a chave mora em app/.env
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_com_chave_a_caixa_liga_e_mostra_a_frase_do_provedor(self):
        chaves.salvar('openai', SEGREDO, self.arqs)
        self.c.post('/config', data={'secao': 'ia', 'modelo': 'gpt:', 'esforco': 'medium', 'cobranca_gpt_enviada': '1', 'cobrar_api_gpt': '1'})
        h = self.pagina()
        self.assertEqual(json.loads(self.cfg.read_text())['cobranca_gpt'], 'api')
        self.assertIn('este vídeo vai cobrar do seu crédito da OpenAI', h)
        self.assertIn('pela API da OpenAI (seu crédito)', h)
        self.assertNotIn(SEGREDO, h)

    def test_erro_do_teste_aparece_em_portugues_simples(self):
        def recusa(req, timeout=0): raise urllib.error.HTTPError(req.full_url, 401, 'x', {}, None)
        with patch('urllib.request.urlopen', recusa):   # nenhuma chamada de rede de verdade
            r = self.c.post('/config/chave/openai', data={'chave': SEGREDO}, follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn('✗ A OpenAI não aceitou essa chave', html); self.assertIn('Custo do teste: US$ 0,00', html); self.assertNotIn(SEGREDO, html)


if __name__ == '__main__':
    unittest.main()
