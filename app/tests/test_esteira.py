"""Grupo 2 · a tela segue a esteira do formato + exemplo vivo.

Fixtures temporárias (FORMATOS, clientes, jobs, acervo): nada pago, nada no formato real."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
import acervo, edicao, fila, formatos, pipeline
P, C, A = fixtures.P, fixtures.C, fixtures.A

REAL_DOC = formatos.FORMATOS / 'documentario' / 'formato.json'   # o formato real: nenhum teste pode mexer nele

ETAPAS = [
    {'id': 'fala', 'titulo': 'Transcrever a fala', 'andamento': 'preparar', 'faz': 'Transcrever com tempo por palavra.'},
    {'id': 'cenas-frase', 'titulo': 'Cenas por frase', 'andamento': 'storyboard', 'faz': 'Uma cena por frase, até 2,5 s.'},
    {'id': 'storyboard', 'titulo': 'Storyboard', 'andamento': 'storyboard', 'faz': 'Folha com a fala de cada cena.', 'aprovar': True},
    {'id': 'render', 'titulo': 'Vídeo', 'andamento': 'video', 'faz': 'Renderizar no motor HTML.'},
    {'id': 'conferir', 'titulo': 'Conferência', 'andamento': 'conferencia', 'faz': 'Comparar com o exemplo principal.'},
]
IDS = [e['id'] for e in ETAPAS]


def video(p, dur=2.5):
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=108x192:rate=10:duration={dur}',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(p)], check=True, capture_output=True)
    return p


class Base(unittest.TestCase):
    job = fixtures.Isolado.job

    def setUp(self):
        fixtures.Isolado.setUp(self)
        self.formatos = self.root / 'formatos'
        self.formatos.mkdir()
        self.stack.enter_context(patch.object(formatos, 'FORMATOS', self.formatos))
        self.stack.enter_context(patch.object(formatos, 'RAIZ', self.root))

    def criar_formato(self, slug='doc-teste', esteira=True, motor=True, status='pronto', modelos=('estilo',), exemplo=True, base_extra=None):
        d = self.formatos / slug
        (d / 'aprendizado').mkdir(parents=True, exist_ok=True)
        (d / 'base').mkdir(exist_ok=True)
        if motor:
            (d / 'base/render.py').write_text('print("motor")')
            (d / 'base/index.html').write_text('<html></html>')
        for nome in base_extra or []:
            (d / 'base' / nome).write_text('x')
        (d / 'COMO-FAZER.md').write_text('# Como fazer')
        dados = {'titulo': 'Doc Teste', 'frase': 'Fundo escuro.', 'entrada': 'video', 'motor': 'HTML', 'status': status,
                 'modelos': list(modelos), 'base': f'formatos/{slug}/base', 'exemplos': []}
        if exemplo:
            video(d / 'exemplo-1.mp4')
            dados['exemplos'] = [{'arquivo': 'exemplo-1.mp4', 'poster': 'exemplo-1.jpg', 'legenda': 'Correria', 'origem': 'antigo.mp4'}]
        if esteira:
            dados['esteira'] = {'etapas': ETAPAS}
        C.gravar_json(d / 'formato.json', dados)
        return d

    def job_formato(self, status='novo', formato='doc-teste'):
        j = self.job(status)
        j['formato'] = formato
        P.salvar(j)
        return P.carregar('Teste', 'video')


class Esteira(Base):
    def test_valida_etapas_e_aprovar(self):
        self.assertIsNone(formatos.esteira(None))
        self.assertIsNone(formatos.esteira({'titulo': 'x'}))
        est = formatos.esteira({'esteira': {'etapas': ETAPAS}})
        self.assertEqual([e['id'] for e in est['etapas']], IDS)
        self.assertEqual(est['parada'], 2)
        self.assertEqual([e['id'] for e in est['depois']], ['render', 'conferir'])
        self.assertIn('render.py --storyboard', formatos.comando(est, 'storyboard', 'sb'))
        self.assertEqual(formatos.esteira({'esteira': ETAPAS})['parada'], 2)              # só a lista também vale
        sem_aprovar = [{k: v for k, v in e.items() if k != 'aprovar'} for e in ETAPAS]
        aprovar_texto = [dict(e, aprovar='sim') if e.get('aprovar') else e for e in ETAPAS]
        repetida = ETAPAS + [ETAPAS[0]]
        andamento_ruim = [dict(ETAPAS[0], andamento='voando')] + ETAPAS[1:]
        sem_titulo = [dict(ETAPAS[0], titulo='')] + ETAPAS[1:]
        for ruim in (sem_aprovar, aprovar_texto, repetida, andamento_ruim, sem_titulo, [], 'x'):
            with self.subTest(ruim=str(ruim)[:40]):
                self.assertIsNone(formatos.esteira({'esteira': {'etapas': ruim}}))

    def test_comandos_do_formato_trocam_os_padrao(self):
        est = formatos.esteira({'esteira': {'etapas': ETAPAS, 'comandos': {'render': 'node <sandbox>/render.js'}}})
        self.assertEqual(formatos.comando(est, 'render', 'a/sb'), 'node a/sb/render.js')
        self.assertIn('--conferir', formatos.comando(est, 'conferir', 'a/sb'))
        com_comando = [dict(e, comando='python3 render.py --storyboard --cenas cenas.json') if e.get('aprovar') else e for e in ETAPAS]
        est = formatos.esteira({'esteira': com_comando})                         # comando da etapa, relativo: roda na sandbox
        self.assertEqual(formatos.comando(est, 'storyboard', 'a/sb'), 'cd "a/sb" && python3 render.py --storyboard --cenas cenas.json')
        self.assertEqual(formatos.comando(est, 'render', 'a/sb'), 'python3 a/sb/render.py --cenas a/sb/cenas.json')

    def test_criar_nao_pergunta_cenas_de_apoio_no_formato_com_esteira(self):
        self.assertNotIn('cenas', [e['campo'] for e in formatos.escolhas({'slug': 'novo', 'esteira': ETAPAS})])
        self.assertIn('cenas', [e['campo'] for e in formatos.escolhas({'slug': 'novo'})])

    def test_esteira_do_job_por_formato_e_por_modelo(self):
        self.criar_formato(exemplo=False)
        self.assertEqual(formatos.esteira_do_job({'formato': 'doc-teste'})['slug'], 'doc-teste')
        self.assertEqual(formatos.esteira_do_job({'formato': '', 'modelo': 'estilo'})['slug'], 'doc-teste')
        self.assertIsNone(formatos.esteira_do_job({}))
        self.assertIsNone(formatos.esteira_do_job({'formato': '../x'}))


class Usar(Base):
    def test_base_vazia_recusa_e_nao_copia(self):
        d = self.criar_formato(motor=False, modelos=('doc-novo',), exemplo=False)
        with self.assertRaises(ValueError) as e:
            formatos.usar('doc-teste', 'Teste')
        self.assertEqual(str(e.exception), formatos.NAO_PRONTO)
        self.assertFalse((self.content / 'modelos/doc-novo').exists())
        self.assertTrue((d / 'base').is_dir())

    def test_status_que_nao_e_pronto_recusa(self):
        self.criar_formato(status='receita', modelos=('doc-novo',), exemplo=False)
        with self.assertRaises(ValueError):
            formatos.usar('doc-teste', 'Teste')
        self.assertFalse((self.content / 'modelos/doc-novo').exists())

    def test_base_com_motor_copia(self):
        self.criar_formato(modelos=('doc-novo',), exemplo=False)
        self.assertEqual(formatos.usar('doc-teste', 'Teste'), ('Teste', 'doc-novo'))
        dst = self.content / 'modelos/doc-novo'
        self.assertTrue((dst / 'render.py').is_file() and (dst / 'index.html').is_file())
        self.assertEqual(C.ler_json(dst / 'aprendizado/regras.json')['regras'], [])

    def test_formato_sem_esteira_mantem_o_comportamento(self):
        self.criar_formato(esteira=False, motor=False, status='receita', modelos=('doc-novo',), exemplo=False, base_extra=['gerar.sh'])
        self.assertEqual(formatos.usar('doc-teste', 'Teste'), ('Teste', 'doc-novo'))
        self.assertTrue((self.content / 'modelos/doc-novo/gerar.sh').is_file())

    def test_formato_sem_esteira_com_base_vazia_nao_copia_pasta_vazia(self):
        self.criar_formato(esteira=False, motor=False, modelos=('doc-novo',), exemplo=False)
        with self.assertRaises(ValueError):
            formatos.usar('doc-teste', 'Teste')
        self.assertFalse((self.content / 'modelos/doc-novo').exists())

    def test_cliente_que_ja_tem_a_variante_usa_a_dele(self):
        self.criar_formato(esteira=False, exemplo=False)
        self.assertEqual(formatos.usar('doc-teste', 'Teste'), ('Teste', 'estilo'))


class Prompts(Base):
    NAO_PODE = ('no máximo', 'mantenha o bruto', 'ESCOPO ESSENCIAL', 'ATÉ 3 OPÇÕES REAIS')

    def setUp(self):
        super().setUp()
        self.criar_formato()
        self.j = self.job_formato()
        edicao.aplicar(self.j, {'origem': 'misto', 'quantidade': 5})
        P.salvar(self.j)
        self.j = P.carregar('Teste', 'video')

    def test_aplicar_marca_escopo_esteira(self):
        self.assertEqual(self.j['escopo_edicao'], 'esteira')
        bruto = self.root / 'novo.mp4'
        bruto.write_bytes(b'raw')
        novo = P.criar('Teste', 'estilo', bruto, 'Outro', formato='doc-teste')
        self.assertEqual(novo['escopo_edicao'], 'esteira')

    def test_analise_segue_a_receita(self):
        text = P.prompt_analise(self.j)
        for trecho in ('render.py --storyboard', 'exemplo', 'aprendizado', 'formatos/doc-teste/formato.json', '"esteira"',
                       '--etapa preparar', 'PARA AQUI', 'andamento.py espera', 'musica_busca.py do-cliente "Teste"', '--fonte mixkit',
                       'exemplo-1-folha.jpg', '"cenas": "cenas.json"', "--exclude '_sandbox*'"):
            self.assertIn(trecho, text)
        for trecho in self.NAO_PODE + ('README.md', 'outros modelos não valem', 'POLÍTICA DO ACERVO VISUAL'):
            self.assertNotIn(trecho, text)
        self.assertNotIn(P.POLITICA_BROLL, text)
        self.assertTrue((self.formatos / 'doc-teste/exemplo-1-folha.jpg').is_file())

    def test_fila_recebe_so_a_receita(self):
        P.analisar('Teste', 'video')
        queued = Path(fila.ler()[0]['prompt']).read_text()
        for trecho in self.NAO_PODE + ('POLÍTICA DO ACERVO VISUAL', 'PREFERÊNCIA DO USUÁRIO'):
            self.assertNotIn(trecho, queued)
        self.assertNotIn(P.POLITICA_BROLL, queued)
        self.assertIn('FALA E CONTINUIDADE', queued)       # DIRETRIZES
        self.assertIn('ANDAMENTO (o João', queued)         # ANDAMENTO
        self.assertIn('render.py --storyboard', queued)
        self.assertNotIn('storyboard.py', queued.replace('render.py --storyboard', ''))

    def test_fase_depois_confere_e_leva_musica(self):
        P.salvar_plano(self.j, {'beats': [], 'aprovado_em': 'hoje'})
        text = P._prompt_producao_com_plano(self.j)
        for trecho in ('--conferir', 'musica.sem=true: sem música; use só sfx ligados', 'cenas.json', 'até 3 vezes',
                       'qa/folha-comparacao.jpg', self.j['saida_esperada'], 'RESULTADO.json'):
            self.assertIn(trecho, text)
        for trecho in self.NAO_PODE + ('README',):
            self.assertNotIn(trecho, text)
        self.assertIn('--conferir', P.prompt_esteira(self.j, 'depois'))
        with self.assertRaises(ValueError):
            P.prompt_esteira(self.j, 'qualquer')

    def test_fase_depois_sem_cenas_json_refaz_as_etapas_ate_o_storyboard(self):
        """Vídeo feito antes da esteira não tem cenas.json: aprovar ou ajustar monta as cenas antes do render."""
        sb = self.j['sandbox']
        aviso = f'Se {sb}/cenas.json não existir (vídeo feito antes da esteira), faça antes as etapas 1 a 3'
        for text in (P.prompt_esteira(self.j, 'depois'),
                     P.prompt_feedback(self.j, {'decisao': 'ajustar', 'texto': 'mais música'})):
            self.assertIn(aviso, text)
            self.assertIn(f'render.py --storyboard --cenas {sb}/cenas.json', text)
            self.assertLess(text.index(aviso), text.index(f'render.py --cenas {sb}/cenas.json`'))

    def test_rodada_nova_monta_do_zero_e_guarda_a_anterior(self):
        """Storyboard refeito do V2 do Cliente4: saiu em 2 min editando o cenas.json da prova anterior, sem cena de fora nova,
        e a música que trocava no meio virou uma escolha só na tela."""
        sb = self.root / self.j['sandbox']
        (sb / 'cenas.json').write_text('{"cenas": []}')
        text = P.prompt_analise(self.j)
        for trecho in ('RODADA NOVA, PLANO NOVO', 'work/rodadas/', 'Nunca parta dele', '"trechos"', 'EXATAMENTE a música do cenas.json'):
            self.assertIn(trecho, text)
        self.assertIn('"trechos"', P.prompt_esteira(self.j, 'depois'))
        P.analisar('Teste', 'video')
        guardadas = list((sb / 'work/rodadas').glob('cenas-*.json'))
        self.assertEqual(len(guardadas), 1)
        self.assertEqual(guardadas[0].read_text(), '{"cenas": []}')
        self.assertTrue((sb / 'cenas.json').is_file())   # cópia: nada some da sandbox

    def test_sandbox_no_passo_da_receita_vira_a_pasta_do_video(self):
        f = C.ler_json(self.formatos / 'doc-teste/formato.json')
        f['esteira']['etapas'][0]['faz'] = 'Rodar python3 <sandbox>/render.py --folha-broll <sandbox>/brolls/x.mp4.'
        C.gravar_json(self.formatos / 'doc-teste/formato.json', f)
        sb = self.j['sandbox']
        self.assertIn(f'python3 {sb}/render.py --folha-broll {sb}/brolls/x.mp4', P.prompt_analise(self.j))

    def test_fala_sai_da_ferramenta_e_respeita_o_corte(self):
        sb = self.j['sandbox']
        text = P.prompt_analise(self.j)
        self.assertIn(f'corte.py transcrever "{self.j["bruto"]}" "{sb}/work"', text)
        self.j['corte_aplicado'] = {'arquivo': f'{sb}/work/joao.mp4'}   # cortado: o words.json de work/ é do bruto original
        text = P.prompt_analise(self.j)
        self.assertIn(f'corte.py transcrever "{sb}/work/joao.mp4" "{sb}/work/fala-cortada"', text)
        self.assertIn('ENTRADA: vídeo gravado ' + f'{sb}/work/joao.mp4', text)
        self.assertIn('copie antes pra', P.prompt_esteira(self.j, 'depois'))   # música do acervo entra na sandbox
        self.j['entrada'] = 'roteiro'
        self.assertNotIn('corte.py transcrever', P.prompt_analise(self.j))

    def test_feedback_refaz_pela_esteira(self):
        text = P.prompt_feedback(self.j, {'decisao': 'ajustar', 'texto': 'mais música'})
        self.assertIn('--conferir', text)
        self.assertIn('video-v2.mp4', text)
        self.assertIn('mais música', text)
        self.assertNotIn(P.POLITICA_MUSICA, text)
        aprovado = P.prompt_feedback(self.j, {'decisao': 'aprovado', 'texto': 'ficou bom'})
        self.assertNotIn('--conferir', aprovado)

    def test_camadas_cita_exemplo_principal_e_comando_do_motor(self):
        text = P.camadas_de_regra(self.j)
        self.assertIn('EXEMPLO PRINCIPAL', text)
        self.assertIn('formatos/doc-teste/exemplo-1.mp4', text)
        self.assertIn('exemplo-1-folha.jpg', text)
        self.assertIn('render.py --storyboard', text)
        self.assertNotIn('gere <sandbox>/storyboard.jpg', text)


class MotorSempreAtual(Base):
    """A sandbox do Vídeo 1 V2 do Cliente4 ficou com o render.py velho (rsync --ignore-existing): o conserto da base não
    chegava. Agora base → modelo do cliente → sandbox, só o motor e só o que estiver mais novo, a cada disparo."""

    def setUp(self):
        super().setUp()
        self.d = self.criar_formato(exemplo=False, base_extra=['README.md'])
        (self.d / 'base/fontes').mkdir()
        (self.d / 'base/fontes/Tinos.ttf').write_text('fonte')
        (self.d / 'base/audio/musicas').mkdir(parents=True)
        (self.d / 'base/audio/musicas/1.mp3').write_text('musica pesada')   # fora da lista: nunca vai pra sandbox
        dados = C.ler_json(self.d / 'formato.json')
        dados['esteira']['motor_arquivos'] = ['render.py', 'index.html', 'README.md', 'fontes', '../fora']
        C.gravar_json(self.d / 'formato.json', dados)
        self.j = self.job_formato()
        self.sb = self.root / self.j['sandbox']

    def _velho(self, p, txt):
        import os
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
        os.utime(p, (1_000_000_000, 1_000_000_000))

    def test_conserto_da_base_chega_no_cliente_e_na_sandbox(self):
        self._velho(self.mod / 'render.py', 'motor velho do cliente')
        self._velho(self.sb / 'render.py', 'motor velho da sandbox')
        (self.sb / 'cenas.json').write_text('{"do": "video"}')
        (self.sb / 'README.md').write_text('feito agora na sandbox')   # mais novo na sandbox: fica
        feito = P.atualizar_motor(self.j)
        self.assertIn('render.py', feito['modelo'])
        self.assertIn('fontes/Tinos.ttf', feito['sandbox'])
        self.assertEqual((self.mod / 'render.py').read_text(), 'print("motor")')
        self.assertEqual((self.sb / 'render.py').read_text(), 'print("motor")')
        self.assertTrue((self.sb / 'fontes/Tinos.ttf').is_file())
        self.assertEqual((self.sb / 'cenas.json').read_text(), '{"do": "video"}')
        self.assertEqual((self.sb / 'README.md').read_text(), 'feito agora na sandbox')
        self.assertFalse((self.sb / 'audio').exists())
        self.assertEqual(P.atualizar_motor(self.j), {'modelo': [], 'sandbox': []})   # nada mais novo: não copia de novo

    def test_disparo_atualiza_o_motor_e_o_prompt_nao_congela_a_copia(self):
        self._velho(self.sb / 'render.py', 'motor velho da sandbox')
        P.analisar('Teste', 'video')
        self.assertEqual((self.sb / 'render.py').read_text(), 'print("motor")')
        text = P.prompt_analise(self.j)
        self.assertIn('rsync -a --update', text)
        self.assertNotIn('--ignore-existing', text)
        for trecho in ('APROVADO na checagem', 'previa-som.m4a', '77 s = 1:17', 'Nunca edite o'):
            self.assertIn(trecho, text)

    def test_sem_esteira_nao_mexe(self):
        self.criar_formato(slug='simples', esteira=False, exemplo=False, modelos=('outro',))
        self._velho(self.sb / 'render.py', 'motor velho da sandbox')
        self.assertEqual(P.atualizar_motor(dict(self.j, formato='simples')), {'modelo': [], 'sandbox': []})
        self.assertEqual((self.sb / 'render.py').read_text(), 'motor velho da sandbox')


class CenasJaEscolhidas(Base):
    def test_cena_que_o_joao_escolheu_em_outro_video_volta_no_pedido(self):
        self.criar_formato(exemplo=False)
        velho = self.job('aprovado', slug='v1')
        src = self.root / velho['sandbox'] / 'work/src'
        src.mkdir(parents=True)
        (src / 'r-GFmH0EK9Y.mp4').write_bytes(b'mp4')
        P.salvar_plano(velho, {'beats': [{'id': 'b1', 'tipo': 'broll', 'fala': 'ele barganha', 'escolha': 'b1-1', 'opcoes': [
            {'id': 'b1-1', 'titulo': 'The Office – negociação', 'url': 'https://www.youtube.com/watch?v=r-GFmH0EK9Y', 'trecho': '96-102'},
            {'id': 'b1-2', 'titulo': 'Não escolhida', 'url': 'https://www.youtube.com/watch?v=xxxxxxx'}]}]})
        j = self.job_formato()
        itens = P.brolls_escolhidos('Teste', ignorar=j['slug'])
        self.assertEqual([i['titulo'] for i in itens], ['The Office – negociação'])
        self.assertTrue(itens[0]['arquivo'].endswith('work/src/r-GFmH0EK9Y.mp4'))
        text = P.prompt_analise(j)
        self.assertIn('CENAS QUE O JOÃO JÁ ESCOLHEU PRA ESTE CLIENTE', text)
        self.assertIn('The Office – negociação', text)
        self.assertNotIn('Não escolhida', text)


class SemEsteira(Base):
    def test_storyboard_sai_da_ferramenta(self):
        self.criar_formato(slug='simples', esteira=False, exemplo=False)
        j = self.job_formato(formato='simples')
        text = P.camadas_de_regra(j)
        self.assertIn('python3 app/ferramentas/storyboard.py ' + j['sandbox'], text)
        self.assertIn('nunca desenhe storyboard com script próprio', text)
        self.assertNotIn('gere <sandbox>/storyboard.jpg', text)
        P.analisar('Teste', 'video')
        queued = Path(fila.ler()[0]['prompt']).read_text()
        self.assertIn('storyboard.py', queued)
        self.assertIn('POLÍTICA DO ACERVO VISUAL', queued)

    def test_prompt_de_analise_igual_ao_de_antes(self):
        j = self.job('novo')
        esperado = (SNAPSHOT_ANALISE.replace('{RAIZ}', str(self.root)).replace('{SKILL_BROLL}', C.rel(P.SKILL_BROLL))
                    .replace('{POLITICA_MUSICA}', P.POLITICA_MUSICA).replace('{POLITICA_BROLL}', P.POLITICA_BROLL)
                    .replace('{ESQUEMA_PLANO}', P.ESQUEMA_PLANO))
        self.assertEqual(P.prompt_analise(j), esperado)

    def test_prompt_essencial_tem_regra_curta_de_musica(self):
        j = self.job('novo')
        edicao.aplicar(j, {'origem': 'nenhum', 'quantidade': 0})
        text = P.prompt_analise(j)
        self.assertIn('MÚSICA (só leitura, sem download', text)
        self.assertIn('música', text)
        self.assertIn('musica_busca.py do-cliente "Teste"', text)

    def test_politica_de_musica_na_ordem(self):
        pm = P.POLITICA_MUSICA
        ordem = [pm.index(x) for x in ('0) Do cliente', '1) Acervo', '2) Mixkit', '3) Jamendo')]
        self.assertEqual(ordem, sorted(ordem))
        self.assertIn('--fonte mixkit', pm)
        self.assertIn('Freesound é SÓ pra efeito', pm)
        self.assertIn('sem melodia', pm)
        self.assertIn('"sfx"', P.ESQUEMA_PLANO)
        self.assertIn('"sfx_ligado"', P.ESQUEMA_PLANO)
        self.assertIn('"opcoes"', P.ESQUEMA_PLANO)


class Edicao(Base):
    def test_esteira_sai_do_caminho(self):
        self.criar_formato(exemplo=False)
        j = self.job_formato('plano')
        j['broll_config'] = {'origem': 'misto', 'quantidade': 5}
        self.assertEqual(edicao.instrucao(j), '')
        plan = {'beats': [{'id': f'b{i}', 'tipo': 'broll', 'escolha': f'b{i}-1', 'opcoes': [{'id': f'b{i}-1'}]} for i in range(20)]}
        edicao.validar(j, plan)   # 20 cenas: sem teto

    def test_misto_traz_geracao_sugerida_em_todo_beat(self):
        j = self.job('novo')
        edicao.aplicar(j, {'origem': 'misto', 'quantidade': 4})
        text = edicao.instrucao(j)
        self.assertIn('Em TODO beat de broll', text)
        self.assertIn('geracao_sugerida', text)
        self.assertIn('nunca chame geração paga', text)
        self.assertEqual(j['escopo_edicao'], 'busca')


class ExemploVivo(Base):
    def setUp(self):
        super().setUp()
        self.mtime_real = REAL_DOC.stat().st_mtime if REAL_DOC.exists() else None
        self.d = self.criar_formato()

    def real_intacto(self):
        if self.mtime_real is not None:
            self.assertEqual(REAL_DOC.stat().st_mtime, self.mtime_real)

    def test_promover_poe_no_topo_e_mantem_os_antigos(self):
        novo = video(self.root / 'aprovado.mp4', 4.5)
        r = formatos.promover_exemplo('doc-teste', novo, 'Aprovado · Teste', origem=str(novo), job='app/jobs/Teste/video')
        dados = C.ler_json(self.d / 'formato.json')
        self.assertEqual(dados['exemplos'][0]['arquivo'], 'exemplo-2.mp4')
        self.assertEqual(dados['exemplos'][1]['arquivo'], 'exemplo-1.mp4')
        for nome in ('exemplo-2.mp4', 'exemplo-2.jpg', 'exemplo-2-folha.jpg'):
            self.assertTrue((self.d / nome).is_file(), nome)
        self.assertEqual(r['folha'], 'exemplo-2-folha.jpg')
        hist = [json.loads(x) for x in (self.d / 'aprendizado/historico.jsonl').read_text().splitlines()]
        self.assertEqual((hist[-1]['tipo'], hist[-1]['job']), ('exemplo', 'app/jobs/Teste/video'))
        self.assertEqual(formatos.carregar('doc-teste')['exemplos'][0]['folha_rel'], 'formatos/doc-teste/exemplo-2-folha.jpg')
        j = self.job_formato()
        for text in (P.prompt_analise(j), P.camadas_de_regra(j)):
            self.assertIn('formatos/doc-teste/exemplo-2.mp4', text)
            self.assertIn('exemplo-2-folha.jpg', text)
        self.real_intacto()

    def test_promover_de_novo_so_volta_pro_topo(self):
        novo = video(self.root / 'aprovado.mp4')
        formatos.promover_exemplo('doc-teste', novo, 'Primeiro', origem='x/aprovado.mp4')
        formatos.promover_exemplo('doc-teste', self.d / 'exemplo-1.mp4', 'De volta', origem='antigo.mp4')
        formatos.promover_exemplo('doc-teste', novo, 'De novo', origem='x/aprovado.mp4')
        exs = C.ler_json(self.d / 'formato.json')['exemplos']
        self.assertEqual([e['arquivo'] for e in exs], ['exemplo-2.mp4', 'exemplo-1.mp4'])
        self.assertEqual(exs[0]['legenda'], 'De novo')
        self.assertFalse((self.d / 'exemplo-3.mp4').exists())

    def test_cli_exemplo(self):
        novo = video(self.root / 'pelo-cli.mp4')
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            formatos.main(['exemplo', 'doc-teste', str(novo), '--legenda', 'Pelo CLI'])
        self.assertIn('exemplo principal de doc-teste', saida.getvalue())
        exs = C.ler_json(self.d / 'formato.json')['exemplos']
        self.assertEqual((exs[0]['arquivo'], exs[0]['legenda']), ('exemplo-2.mp4', 'Pelo CLI'))
        self.assertEqual(exs[0]['origem'], str(novo.resolve()))

    def test_folha_so_gera_uma_vez(self):
        fo = formatos.folha_exemplo('doc-teste', 0)
        self.assertEqual(fo.name, 'exemplo-1-folha.jpg')
        antes = fo.stat().st_mtime_ns
        self.assertEqual(formatos.folha_exemplo('doc-teste', 0).stat().st_mtime_ns, antes)
        self.assertIsNone(formatos.folha_exemplo('doc-teste', 5))
        self.assertIsNone(formatos.folha_exemplo('nao-existe', 0))

    def test_exportar_como_exemplo_promove_no_formato(self):
        j = self.job_formato('aprovado')
        video(self.root / j['saida'], 3)
        r = A.exportar('Teste', 'video', self.root / 'Mac', exemplo=True)
        exs = C.ler_json(self.d / 'formato.json')['exemplos']
        self.assertEqual(exs[0]['arquivo'], 'exemplo-2.mp4')
        self.assertEqual(exs[0]['origem'], str(Path(r['pasta_mac']) / 'final/video.mp4'))
        self.assertEqual(r['exemplo_formato'], 'formatos/doc-teste/exemplo-2.mp4')
        self.assertTrue((self.mod / 'demos/exemplo-video-0.jpg').is_file())   # os 3 quadros do modelo continuam
        self.real_intacto()

    def test_exportar_sem_marcar_exemplo_nao_promove(self):
        j = self.job_formato('aprovado')
        video(self.root / j['saida'], 3)
        A.exportar('Teste', 'video', self.root / 'Mac')
        self.assertEqual(len(C.ler_json(self.d / 'formato.json')['exemplos']), 1)


class MusicaSfx(Base):
    def setUp(self):
        super().setUp()
        self.j = self.job('plano')
        item = self.root / 'acervo/itens/faixa-calma'
        item.mkdir(parents=True)
        C.gravar_json(item / 'meta.json', {'slug': 'faixa-calma', 'tipo': 'musica', 'usos': []})
        P.salvar_plano(self.j, {'beats': [], 'musica': {
            'opcoes': [{'id': 'm1', 'arquivo': 'acervo/itens/faixa-calma/clip.mp3', 'fonte': 'acervo', 'acervo_slug': 'faixa-calma',
                        'inicio_s': 0, 'fim_s': 30, 'motivo': 'calma'},
                       {'id': 'm2', 'arquivo': 'work/musica/mixkit.mp3', 'fonte': 'mixkit', 'inicio_s': 5, 'fim_s': 40, 'motivo': 'tensa'}],
            'escolha': 'm1'},
            'sfx': [{'id': 's1', 'som': 'whoosh', 't': 1.0, 'ligado': True}, {'id': 's2', 'som': 'click', 't': 2.0, 'ligado': True}],
            'sfx_ligado': True})

    def plano(self):
        return P.plano(P.carregar('Teste', 'video'))

    def test_sem_musica(self):
        P.aprovar_plano('Teste', 'video', {}, {}, musica='sem')
        m = self.plano()['musica']
        self.assertEqual(m['escolha'], {'sem': True})
        self.assertTrue(m['sem'])
        self.assertNotIn('arquivo', m)
        self.assertEqual(len(m['opcoes']), 2)
        self.assertFalse([x for x in P.itens_para_acervo(P.carregar('Teste', 'video')) if x['beat'] == 'musica'])

    def test_escolhe_outra_faixa(self):
        P.aprovar_plano('Teste', 'video', {}, {}, musica='m2')
        m = self.plano()['musica']
        self.assertEqual(m['escolha'], 'm2')
        self.assertEqual((m['arquivo'], m['fonte'], m['inicio_s']), ('work/musica/mixkit.mp3', 'mixkit', 5))
        self.assertNotIn('acervo_slug', m)
        with self.assertRaises(ValueError):
            P.aprovar_plano('Teste', 'video', {}, {}, musica='m9')

    def test_faixa_do_acervo_registra_uso(self):
        P.aprovar_plano('Teste', 'video', {}, {}, musica='m1')
        usos = C.ler_json(self.root / 'acervo/itens/faixa-calma/meta.json')['usos']
        self.assertEqual([(u['cliente'], u['job']) for u in usos], [('Teste', 'video')])

    def test_liga_so_os_efeitos_escolhidos(self):
        P.aprovar_plano('Teste', 'video', {}, {}, sfx=['s1'])
        p = self.plano()
        self.assertEqual([(s['id'], s['ligado']) for s in p['sfx']], [('s1', True), ('s2', False)])
        self.assertTrue(p['sfx_ligado'])
        self.assertEqual(p['musica']['escolha'], 'm1')                      # musica=None não mexe
        P.aprovar_plano('Teste', 'video', {}, {}, sfx=[])
        self.assertFalse(self.plano()['sfx_ligado'])
        P.aprovar_plano('Teste', 'video', {}, {}, sfx=['s2', 's9'])          # id que não existe é ignorado
        self.assertEqual([s['ligado'] for s in self.plano()['sfx']], [False, True])

    def test_formato_da_tela_tambem_vale(self):
        """A tela (Grupo 3) manda {'sem': True}, a opção inteira (pode vir do catálogo) e {'ligado', 'ativos'}."""
        P.aprovar_plano('Teste', 'video', {}, {}, musica={'sem': True}, sfx={'ligado': False, 'ativos': ['s1']})
        p = self.plano()
        self.assertEqual(p['musica']['escolha'], {'sem': True})
        self.assertEqual(([s['ligado'] for s in p['sfx']], p['sfx_ligado']), ([True, False], False))
        nova = {'id': 'cat-1', 'titulo': 'Do catálogo', 'arquivo': 'acervo/itens/faixa-calma/clip.mp3', 'fonte': 'acervo',
                'acervo_slug': 'faixa-calma', 'inicio_s': None, 'usada_txt': ''}
        P.aprovar_plano('Teste', 'video', {}, {}, musica=nova)
        m = self.plano()['musica']
        self.assertEqual((m['escolha'], m['titulo'], m['arquivo']), ('cat-1', 'Do catálogo', 'acervo/itens/faixa-calma/clip.mp3'))
        self.assertEqual([o['id'] for o in m['opcoes']], ['m1', 'm2', 'cat-1'])
        self.assertNotIn('usada_txt', m)
        self.assertTrue(C.ler_json(self.root / 'acervo/itens/faixa-calma/meta.json')['usos'])
        P.aprovar_plano('Teste', 'video', {}, {}, musica={'id': 'm2', 'titulo': 'Tensa'})   # já está no plano: vale a do plano
        m = self.plano()['musica']
        self.assertEqual((m['escolha'], m['arquivo']), ('m2', 'work/musica/mixkit.mp3'))
        with self.assertRaises(ValueError):
            P.aprovar_plano('Teste', 'video', {}, {}, musica={'id': 'x', 'titulo': 'sem arquivo'})

    def test_faixa_antiga_do_topo_vira_alternativa(self):
        P.salvar_plano(self.j, {'beats': [], 'musica': {'opcao': 'work/musica/antiga.mp3', 'arquivo': 'work/musica/antiga.mp3',
                                                        'origem': 'acervo', 'motivo': 'da IA'}})
        P.aprovar_plano('Teste', 'video', {}, {}, musica='sem')
        m = self.plano()['musica']
        self.assertEqual(m['opcoes'][0]['arquivo'], 'work/musica/antiga.mp3')
        P.aprovar_plano('Teste', 'video', {}, {}, musica='plano')
        m = self.plano()['musica']
        self.assertEqual((m['escolha'], m['arquivo']), ('plano', 'work/musica/antiga.mp3'))
        self.assertNotIn('sem', m)
        self.assertEqual(len(m['opcoes']), 1)

    def test_sem_mudar_nada_continua_como_antes(self):
        P.aprovar_plano('Teste', 'video', {}, {})
        p = self.plano()
        self.assertEqual(p['musica']['escolha'], 'm1')
        self.assertEqual(p['musica']['arquivo'], 'acervo/itens/faixa-calma/clip.mp3')   # a da IA sobe pro topo
        self.assertEqual(len(p['musica']['opcoes']), 2)
        self.assertTrue(C.ler_json(self.root / 'acervo/itens/faixa-calma/meta.json')['usos'])
        self.assertTrue(all(s['ligado'] for s in p['sfx']))
        self.assertEqual(P.carregar('Teste', 'video')['status'], 'plano_aprovado')
        P.aprovar_plano('Teste', 'video', {}, {}, musica='sem')
        P.aprovar_plano('Teste', 'video', {}, {})                            # "sem música" continua sem
        self.assertEqual(self.plano()['musica']['escolha'], {'sem': True})

    def test_storyboard_da_ferramenta_roda_e_nunca_trava(self):
        P.aprovar_plano('Teste', 'video', {}, {})                            # sem storyboard.py: segue normal
        ferramenta = self.root / 'app/ferramentas/storyboard.py'
        ferramenta.parent.mkdir(parents=True, exist_ok=True)
        ferramenta.write_text('import sys, pathlib; pathlib.Path(sys.argv[1], "storyboard.jpg").write_text("ok")')
        P.aprovar_plano('Teste', 'video', {}, {})
        self.assertTrue((self.root / self.j['sandbox'] / 'storyboard.jpg').is_file())
        ferramenta.write_text('raise SystemExit("quebrou")')
        self.assertEqual(P.aprovar_plano('Teste', 'video', {}, {})['status'], 'plano_aprovado')
        with patch.object(P.subprocess, 'run', side_effect=subprocess.TimeoutExpired('storyboard', 60)):
            self.assertEqual(P.aprovar_plano('Teste', 'video', {}, {})['status'], 'plano_aprovado')

    def test_formato_com_esteira_nao_usa_a_ferramenta(self):
        self.criar_formato(exemplo=False)
        j = P.carregar('Teste', 'video')
        j['formato'] = 'doc-teste'
        P.salvar(j)
        ferramenta = self.root / 'app/ferramentas/storyboard.py'
        ferramenta.parent.mkdir(parents=True, exist_ok=True)
        ferramenta.write_text('import sys, pathlib; pathlib.Path(sys.argv[1], "storyboard.jpg").write_text("ok")')
        P.aprovar_plano('Teste', 'video', {}, {})
        self.assertFalse((self.root / j['sandbox'] / 'storyboard.jpg').exists())


class Barra(Base):
    def estados(self, j):
        return [(x['id'], x['estado']) for x in pipeline.etapas(j)]

    def test_esteira_mostra_os_passos_do_formato(self):
        self.criar_formato(exemplo=False)
        j = self.job_formato()
        j['saida'] = None
        steps = pipeline.etapas(j)
        self.assertEqual([x['id'] for x in steps], IDS)
        self.assertEqual([x['titulo'] for x in steps], [e['titulo'] for e in ETAPAS])
        self.assertFalse({'cenas', 'previa'} & {x['id'] for x in steps})
        self.assertEqual([x['estado'] for x in steps], ['pronto', 'aguardando', 'aguardando', 'aguardando', 'aguardando'])
        sb = self.root / j['sandbox']
        (sb / 'storyboard.jpg').write_bytes(b'jpg')
        self.assertEqual(self.estados(j)[2], ('storyboard', 'revisar'))
        P.salvar_plano(j, {'beats': [], 'aprovado_em': 'hoje'})
        self.assertEqual([e for _, e in self.estados(j)], ['pronto', 'pronto', 'pronto', 'aguardando', 'aguardando'])
        j.update(rodando=True, execucoes=[{'tipo': 'producao'}])
        render = pipeline.etapas(j)[3]
        self.assertEqual((render['estado'], render['detalhe']), ('rodando', 'Fazendo o vídeo agora'))
        j.update(rodando=False, saida=P.carregar('Teste', 'video')['saida_esperada'], status='concluido')
        self.assertEqual(self.estados(j)[4], ('conferir', 'atencao'))            # entregue sem qa/conferir.json
        (sb / 'qa').mkdir(exist_ok=True)
        (sb / 'qa/conferir.json').write_text('{"ok": true}')
        ultimo = pipeline.etapas(j)[-1]
        self.assertEqual((ultimo['estado'], ultimo['detalhe']), ('revisar', 'Assista e aprove o vídeo'))
        j['status'] = 'aprovado'
        self.assertEqual([e for _, e in self.estados(j)], ['pronto'] * 5)
        j['status'] = 'erro'
        P.salvar_plano(j, {'beats': []})
        j['saida'] = None
        self.assertEqual(self.estados(j)[2], ('storyboard', 'atencao'))

    def test_plano_aprovado_sem_o_jpg_conta_como_aprovado(self):
        self.criar_formato(exemplo=False)
        j = self.job_formato()
        j['saida'] = None
        P.salvar_plano(j, {'beats': [], 'aprovado_em': 'hoje'})
        self.assertEqual([e for _, e in self.estados(j)], ['pronto', 'pronto', 'pronto', 'aguardando', 'aguardando'])

    def test_esteira_analisando_mostra_o_storyboard_em_andamento(self):
        self.criar_formato(exemplo=False)
        j = self.job_formato()
        j.update(saida=None, rodando=True, execucoes=[{'tipo': 'analise'}])
        self.assertEqual([e for _, e in self.estados(j)], ['pronto', 'rodando', 'aguardando', 'aguardando', 'aguardando'])

    def test_corte_da_fala_nao_repete_o_preparar_da_esteira(self):
        self.criar_formato(exemplo=False)
        j = self.job_formato()
        j.update(saida=None, cortar_bruto=True)
        titulos = [x['titulo'] for x in pipeline.etapas(j)]
        self.assertEqual(titulos[0], 'Cortar a fala')
        self.assertEqual(len([t for t in titulos if t.lower().startswith('preparar')]), 0)
        com_preparar = [dict(ETAPAS[0], titulo='Preparar a fala')] + ETAPAS[1:]
        self.assertNotIn('Preparar fala', [x['titulo'] for x in pipeline._etapas_esteira(j, formatos.esteira({'esteira': com_preparar}))])

    def test_sem_esteira_mesma_lista_de_antes(self):
        j = self.job('novo')
        self.assertEqual([x['id'] for x in pipeline.etapas(j)], ['bruto', 'fala', 'analise', 'cenas', 'previa', 'final'])
        j['broll_config'] = {'origem': 'nenhum', 'quantidade': 0}
        self.assertEqual([x['id'] for x in pipeline.etapas(j)], ['bruto', 'fala', 'analise', 'previa', 'final'])
        j.update(rodando=True, execucoes=[{'tipo': 'producao'}])
        final = pipeline.etapas(j)[-1]
        self.assertEqual((final['estado'], final['detalhe']), ('rodando', 'Fazendo o vídeo agora'))


# Prompt de análise de um formato SEM esteira, gerado pelo código de antes da esteira (09-out-2026).
# As políticas que a mudança de música trocou de propósito entram como {POLITICA_MUSICA}/{ESQUEMA_PLANO}.
SNAPSHOT_ANALISE = """Você está no Estúdio (raiz: {RAIZ}). ETAPA 1 de um vídeo pelo Estúdio: ANALISAR e PROPOR OS TAKES. NÃO renderize o vídeo final nesta etapa.

CLIENTE: Teste (pasta clientes/Teste)   MODELO: estilo (pasta clientes/Teste/testeContent/modelos/estilo)
BRUTO: clientes/Teste/testeContent/modelos/estilo/_sandbox-video/bruto/raw.mp4   SANDBOX: clientes/Teste/testeContent/modelos/estilo/_sandbox-video   BRIEFING: (sem briefing)
B-ROLLS JÁ SEPARADOS DO ACERVO:
  (nenhum)
CAMADAS EXTRAS PEDIDAS (modelos-camada do mesmo cliente a somar nesta edição): (nenhuma — mas se o briefing pedir algo como "switches do iPhone"/"hook de texto", trate como camada)

O QUE FAZER:
0. TRANSCRIÇÃO PRIMEIRO, sempre: nada de propor beat antes de ter o words.json. A transcrição vai inteira no PLANO.json (campo transcricao) pro João ler.
1. Leia clientes/Teste/testeContent/modelos/estilo/ficha.json, clientes/Teste/testeContent/modelos/estilo/aprendizado/regras.json INTEIRO e clientes/Teste/testeContent/modelos/estilo/README.md. Regras de outros modelos não valem.
2. Prepare o bruto como o modelo exige (ex.: clientes/Teste/testeContent/modelos/estilo/_sandbox-video/work/joao.mp4 1080x1920, rotação conferida) — SE já existir clientes/Teste/testeContent/modelos/estilo/_sandbox-video/work/joao.mp4 vindo do corte do bruto (etapa 0), use ESSE arquivo e a transcrição dele, não o bruto original — e transcreva com GROQ (GROQ_API_KEY no app/.env; se clientes/Teste/.env tiver uma, ela vale) salvando clientes/Teste/testeContent/modelos/estilo/_sandbox-video/work/words.json. Não estime tempos: use o words.json.
2c. CITAÇÃO COM ÁUDIO (só quando o briefing pedir, ex.: "depois que eu falo X, põe o Lula falando isso"):
   use `python3 app/ferramentas/fala.py missao "<quem>" "<o que ele diz>" --limite 5` — ele busca vídeos,
   baixa a LEGENDA com tempos e devolve o SEGUNDO EXATO em que a frase é dita, com link `?t=`. Confirme com
   `fala.py achar <url> "<frase>"` e baixe só o trecho com `fala.py cortar <url> <t0> <t1> <saida.mp4>`.
   O beat vira tipo "citacao" com "com_audio": true e o bloco "citacao" preenchido (quem, frase, fonte, t0/t1).
   Se o João pedir várias épocas/pessoas ("no primeiro mandato", "em 2018", "puxa do Trump também"), faça uma
   missão por pedido e traga um beat de citação para cada, em ordem cronológica, mostrando a repetição da narrativa.
   NUNCA invente a frase: só entra o que aparece na legenda/transcrição da fonte, com o tempo conferido.

3. ENTIDADES AUTOMÁTICAS: varra a transcrição e liste todo nome próprio, marca, produto, lugar, jornal, notícia e número citado (ex.: "Lula", "Trump", "Folha", "Clinicorp"). Para cada um, a busca é AUTOMÁTICA e obrigatória — o João não vai pedir; ele espera que "falou Lula → aparece o Lula". FONTE LITERAL primeiro: se a fala cita uma pessoa, marca, produto, jornal, notícia ou dado, a opção principal tem que ser a FONTE REAL (vídeo da pessoa, print da matéria com manchete legível, tela do site, gráfico oficial) — só depois vêm cenas ilustrativas.
   Divida a fala em trechos e proponha os BEATS conforme a ficha e as regras do modelo (ritmo, tipos permitidos, política de b-roll). Para cada beat de b-roll traga ATÉ 3 OPÇÕES REAIS, seguindo a skill {SKILL_BROLL}: a busca principal é FORA, com get-brolls em todas as fontes (YouTube, Pexels, Pixabay, Commons, NASA — varie as fontes entre os beats) e site/canal oficial quando a fala cita marca/produto; os itens do acervo que o João separou entram como opção, e se nada foi separado o acervo é só mais um lugar pra olhar, nunca o único. Para CADA opção gere prévia visual dentro da sandbox: um contact sheet (12 frames) e um GIF curto, com caminhos RELATIVOS à sandbox (ex.: brolls/b1-1-sheet.jpg, brolls/b1-1.gif). Use `~/.claude/skills/get-brolls/.venv/bin/python ~/.claude/skills/get-brolls/scripts/gb.py preview --project clientes/Teste/testeContent/modelos/estilo/_sandbox-video` (os arquivos saem em clientes/Teste/testeContent/modelos/estilo/_sandbox-video/brolls/previews/ — referencie esse caminho) ou ffmpeg direto para clipes do acervo. OLHE os frames antes de propor: reprove watermark, rosto indevido, legenda queimada, baixa qualidade; escreva no campo "verificado" o que conferiu.
4. Para beats de card/impacto proponha o texto_card (com *palavra* destacada) no tempo exato da fala. Para punch, só a janela. Para cada CAMADA extra pedida, leia a ficha/regras da pasta dela (mesmo cliente, modelos/<camada>/) e proponha beats do tipo "camada" com o campo "camada": "<modelo>" e o conteúdo dela (ex.: switches: lista de labels+emoji e o tempo em que cada um liga), sem opções de b-roll.
5. Escolha a música conforme a política abaixo.
{POLITICA_MUSICA}
{POLITICA_BROLL}
6. Escreva clientes/Teste/testeContent/modelos/estilo/_sandbox-video/PLANO.json EXATAMENTE neste esquema (JSON válido, UTF-8):
{ESQUEMA_PLANO}
6b. ORDEM DAS OPÇÕES: em cada beat, a opção que você recomenda vai SEMPRE em primeiro lugar (b1-1 é a recomendada). O "Seguir direto" (sem o João escolher) usa a 1ª opção; se quiser dizer qual é a recomendada, marque também "recomendada": "<id>" no beat.
7. Não peça confirmação. Ao terminar, escreva também clientes/Teste/testeContent/modelos/estilo/_sandbox-video/ANALISE.md com um resumo em português do que propôs e por quê (o João vai ler na tela).
"""


if __name__ == '__main__':
    unittest.main()
