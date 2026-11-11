"""O formato diz como o vídeo dele funciona (esteira.cenas, copiar_motor, voz, folha e som.*.usa) e o código obedece.

Antes o pedido à IA e a tela supunham o motor do Documentário pra todo formato: o Diálogo 3D recebia "monte o cenas.json
com get-brolls", "PLANO.json com 2 a 3 faixas" e "a voz sai do narracao_tts", a tela dizia "vídeo feito antes da esteira"
porque nunca existe cenas.json lá, e o conserto da base apagava o index.html (as cenas) do Como funciona.
Fixtures temporárias: nada pago, nada de rede, nenhum formato real é mexido."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
from test_esteira import Base, ETAPAS, video
import corte, edicao, formatos, musica_busca as MB, simples

P, C = fixtures.P, fixtures.C


def etapas_3d():
    return [dict(e, comando='app/.venv/bin/python formatos/d3/base/episodio.py <sandbox> --sem-abrir') if e['id'] == 'storyboard'
            else e for e in ETAPAS]


class Base3D(Base):
    """Um formato no jeito do Diálogo 3D: episodio.json, motor rodando da base, sem música, sem efeitos, voz do motor."""

    def criar_3d(self, slug='d3', **esteira):
        d = self.criar_formato(slug=slug, exemplo=False, base_extra=['episodio.py'])
        dados = C.ler_json(d / 'formato.json')
        dados['entrada'] = 'roteiro'
        dados['som'] = {'musica': {'usa': False, 'de_onde': ''}, 'efeitos': {'usa': False, 'de_onde': ''}}
        dados['esteira'] = {'etapas': etapas_3d(), 'cenas': 'episodio.json', 'copiar_motor': False, 'voz': 'motor',
                            'folha': 'folha.jpg', 'motor_arquivos': ['episodio.py', 'render.py', 'index.html'],
                            'comandos': {'storyboard': 'app/.venv/bin/python formatos/d3/base/episodio.py <sandbox> --sem-abrir',
                                         'render': 'app/.venv/bin/python formatos/d3/base/episodio.py <sandbox> --final --sem-abrir',
                                         'conferir': 'app/.venv/bin/python formatos/d3/base/render.py --pasta <sandbox> --conferir'},
                            **esteira}
        C.gravar_json(d / 'formato.json', dados)
        return d

    def job_3d(self, slug='d3'):
        j = self.job_formato(formato=slug)
        j['entrada'] = 'roteiro'
        P.salvar(j)
        return P.carregar('Teste', 'video')


class EsteiraDeclara(Base3D):
    def test_campos_normalizados_e_padrao_do_documentario(self):
        est = formatos.esteira({'esteira': {'etapas': ETAPAS}})
        self.assertEqual((est['cenas'], est['copiar_motor'], est['voz'], est['folha'], est['musica'], est['efeitos']),
                         ('cenas.json', True, 'narracao', 'qa/folha-comparacao.jpg', True, True))
        self.assertTrue(formatos.motor_padrao(est))
        f = {'som': {'musica': {'usa': False}, 'efeitos': {'usa': True}},
             'esteira': {'etapas': ETAPAS, 'cenas': 'episodio.json', 'copiar_motor': False, 'voz': 'sem',
                         'folha': ['qa/folha-h.jpg', 'qa/folha-v.jpg']}}
        est = formatos.esteira(f)
        self.assertEqual((est['cenas'], est['copiar_motor'], est['voz'], est['folha'], est['folhas'], est['musica'], est['efeitos']),
                         ('episodio.json', False, 'sem', 'qa/folha-h.jpg', ['qa/folha-h.jpg', 'qa/folha-v.jpg'], False, True))
        self.assertFalse(formatos.motor_padrao(est))
        ruim = formatos.esteira({'esteira': {'etapas': ETAPAS, 'cenas': '../fora.json', 'voz': 'cantada', 'folha': '/tmp/x.jpg'}})
        self.assertEqual((ruim['cenas'], ruim['voz'], ruim['folha']), ('cenas.json', 'narracao', 'qa/folha-comparacao.jpg'))

    def test_marcadores_modelo_e_saida_no_comando(self):
        sb = 'clientes/T/tContent/modelos/m/_sandbox-v'
        self.assertEqual(formatos.na_sandbox('zsh <modelo>/gerar.sh --dir <sandbox>', sb),
                         'zsh clientes/T/tContent/modelos/m/gerar.sh --dir clientes/T/tContent/modelos/m/_sandbox-v')
        self.assertEqual(formatos.na_sandbox('zsh ../gerar.sh --dir . --out <saida>', sb, saida='clientes/T/out/v.mp4'),
                         f'cd "{sb}" && zsh ../gerar.sh --dir . --out {self.root}/clientes/T/out/v.mp4')
        self.assertEqual(formatos.na_sandbox('node ../g.js <id>', sb), f'cd "{sb}" && node ../g.js <id>')   # <id> fica pra IA

    def test_validar_confere_o_script_do_modelo_visto_da_sandbox(self):
        self.assertEqual(formatos._arquivos_do_comando('zsh ../gerar.sh --dir .'), [('base', 'gerar.sh')])
        self.assertEqual(formatos._arquivos_do_comando('python3 <modelo>/render.py cfg.json'), [('base', 'render.py')])
        self.assertEqual(formatos._arquivos_do_comando('python3 app/ferramentas/x.py <sandbox>'), [('raiz', 'app/ferramentas/x.py')])
        d = self.criar_formato(slug='grav', exemplo=False)
        dados = C.ler_json(d / 'formato.json')
        dados.update(tipo='gravado', base='clientes/Teste/testeContent/modelos/estilo',
                     esteira={'etapas': ETAPAS, 'comandos': {'render': 'zsh ../gerar.sh --dir .'}})
        C.gravar_json(d / 'formato.json', dados)
        self.assertIn('usa <sandbox>/gerar.sh, que não está na base', ' | '.join(formatos.validar('grav')))
        (self.mod / 'gerar.sh').write_text('#!/bin/zsh\necho --dir\n')
        self.assertNotIn('gerar.sh', ' | '.join(formatos.validar('grav')))

    def test_render_do_gerar_respeita_zsh_e_dir(self):
        g = self.mod / 'gerar.sh'
        self.assertEqual(formatos.render_do_gerar(g), '')
        g.write_text('#!/bin/zsh\n# --dir PASTA do vídeo\n')
        self.assertEqual(formatos.render_do_gerar(g), 'zsh ../gerar.sh --dir .')
        g.write_text('echo render')
        self.assertEqual(formatos.render_do_gerar(g), 'bash ../gerar.sh')


class PromptDoFormato(Base3D):
    def setUp(self):
        super().setUp()
        self.criar_3d()
        self.j = self.job_3d()
        self.sb = self.j['sandbox']

    def test_ate_aprovacao_sem_cenas_json_sem_musica_sem_rsync(self):
        a = P.prompt_esteira(self.j, 'ate_aprovacao')
        for trecho in (f'{self.sb}/episodio.json', 'roda direto da base', '"sfx": []', '"sfx_ligado": false',
                       '"musica": {"sem": true', 'não usa música', 'a voz sai do próprio motor do formato',
                       'formatos/d3/base/episodio.py ' + self.sb + ' --sem-abrir', '"cenas": "episodio.json"'):
            self.assertIn(trecho, a)
        for trecho in ('cenas.json"', 'get-brolls', 'rsync', 'previa-som', 'APROVADO na checagem', 'musica_busca.py',
                       'Passagem quando muda o fundo', 'motion/narracao_tts.py', '{sb}'):
            self.assertNotIn(trecho, a)

    def test_depois_usa_o_arquivo_e_a_folha_do_formato(self):
        d = P.prompt_esteira(self.j, 'depois')
        self.assertIn(f'Se {self.sb}/episodio.json não existir', d)
        self.assertNotIn(f'{self.sb}/cenas.json', d)
        self.assertIn(f'{self.sb}/folha.jpg', d)
        self.assertNotIn('qa/folha-comparacao.jpg', d)
        self.assertIn('não usa música nem efeitos', d)
        self.assertNotIn('motor na sandbox', d)
        self.assertIn('--final --sem-abrir', d)
        self.assertIn('(exit 0 = aprovado)', d)

    def test_camadas_respeitam_a_voz_do_formato(self):
        txt = P.camadas_de_regra(self.j)
        self.assertIn('A voz sai do próprio motor do formato', txt)
        self.assertNotIn('Gere a narração', txt)
        f = C.ler_json(self.formatos / 'd3/formato.json')
        f['esteira']['voz'] = 'sem'
        C.gravar_json(self.formatos / 'd3/formato.json', f)
        self.assertIn('Este formato não tem narração', P.camadas_de_regra(self.j))

    def test_sem_efeitos_so_com_musica(self):
        f = C.ler_json(self.formatos / 'd3/formato.json')
        f['som']['musica']['usa'] = True
        C.gravar_json(self.formatos / 'd3/formato.json', f)
        a, d = P.prompt_esteira(self.j, 'ate_aprovacao'), P.prompt_esteira(self.j, 'depois')
        self.assertIn('musica_busca.py do-cliente', a)
        self.assertIn('"sfx": []', a)
        self.assertIn('musica.sem=true: sem música.', d)
        self.assertNotIn('use só sfx ligados', d)
        self.assertIn('Passe a música escolhida pro motor', d)

    def test_texto_comum_respeita_o_som_do_formato(self):
        """O texto comum pedia "a mesma variedade de cenas, música e efeitos" até pro Diálogo 3D (sem música nem efeito)."""
        self.assertEqual(P._o_que_o_exemplo_tem(False, False), 'cenas')
        self.assertEqual(P._o_que_o_exemplo_tem(True, False), 'cenas e música')
        self.assertEqual(P._o_que_o_exemplo_tem(True, True), 'cenas, música e efeitos')
        self.assertNotIn('inclusive música', P.prompt_esteira(self.j, 'depois'))
        fb = P.prompt_feedback(self.j, {'decisao': 'aprovado', 'texto': 'bom'})
        self.assertNotIn('Se envolver música', fb)
        self.assertIn('não usa música nem efeitos', fb)


class DocumentarioIgual(Base):
    def test_documentario_continua_igual(self):
        self.criar_formato()
        j = self.job_formato()
        a, d = P.prompt_esteira(j, 'ate_aprovacao'), P.prompt_esteira(j, 'depois')
        for trecho in ('rsync -a --update', 'APROVADO na checagem', 'previa-som.m4a', 'get-brolls', 'Passagem quando muda o fundo',
                       'pro João (use estes números no ANALISE.md)', 'Cada cena de fora leva "origem"', '"cenas": "cenas.json"'):
            self.assertIn(trecho, a)
        # a faixa com trechos: o "musica" do cenas.json é a lista inteira, com arquivo, inicio_s e de
        self.assertIn('vira a LISTA inteira, um item por trecho com\n  "arquivo", "inicio_s" e "de"', d)
        self.assertNotIn('"musica": {"arquivo", "inicio_s"}\n  ou null', d)
        self.assertIn('folha-video <render.mp4>', d)


class MotorDaBase(Base3D):
    def test_copiar_motor_false_nao_copia_nada(self):
        self.criar_3d()
        j = self.job_3d()
        self.assertEqual(P.atualizar_motor(j), {'modelo': [], 'sandbox': []})
        self.assertFalse((self.mod / 'episodio.py').exists())
        self.assertFalse((self.root / j['sandbox'] / 'episodio.py').exists())

    def test_usar_cria_so_a_pasta_do_modelo(self):
        self.criar_3d(slug='d3')
        dados = C.ler_json(self.formatos / 'd3/formato.json')
        dados['modelos'] = ['d3-novo']
        C.gravar_json(self.formatos / 'd3/formato.json', dados)
        self.assertEqual(formatos.usar('d3', 'Teste'), ('Teste', 'd3-novo'))
        dst = self.content / 'modelos/d3-novo'
        self.assertEqual(sorted(p.name for p in dst.iterdir()), ['aprendizado', 'ficha.json'])
        self.assertEqual(C.ler_json(dst / 'ficha.json')['roda_da_base'], 'formatos/d3/base')

    def test_arquivo_do_video_na_sandbox_nunca_e_trocado(self):
        """Motor em que o index.html é motor E as cenas do vídeo (o antigo Como funciona). O conserto da base não pode apagar o vídeo."""
        d = self.criar_formato(exemplo=False)
        dados = C.ler_json(d / 'formato.json')
        dados['esteira'] = {'etapas': ETAPAS, 'cenas': 'index.html'}
        C.gravar_json(d / 'formato.json', dados)
        j = self.job_formato()
        sb = self.root / j['sandbox']
        (sb / 'index.html').write_text('as cenas deste vídeo')
        os.utime(sb / 'index.html', (1_000_000_000, 1_000_000_000))   # base mais nova que o vídeo
        feito = P.atualizar_motor(j)
        self.assertIn('render.py', feito['sandbox'])
        self.assertNotIn('index.html', feito['sandbox'])
        self.assertEqual((sb / 'index.html').read_text(), 'as cenas deste vídeo')
        (sb / 'index.html').unlink()   # sem o arquivo, a 1ª cópia vem do modelo
        self.assertIn('index.html', P.atualizar_motor(j)['sandbox'])

    def test_rodada_guarda_o_arquivo_do_video(self):
        self.criar_3d()
        j = self.job_3d()
        sb = self.root / j['sandbox']
        (sb / 'episodio.json').write_text('{"falas": []}')
        destino = P.guardar_rodada(j)
        self.assertTrue(destino.name.startswith('episodio-') and destino.suffix == '.json')
        self.assertEqual(destino.read_text(), '{"falas": []}')


class TelaDoFormato(Base3D):
    def test_storyboard_do_3d_aprova_sem_cenas_json_e_sem_bloco_de_musica(self):
        self.criar_3d()
        j = self.job_3d()
        j['status'] = 'plano'
        P.salvar(j)
        sb = self.root / j['sandbox']
        C.gravar_json(sb / 'PLANO.json', {'beats': [], 'transcricao': [], 'musica': {'sem': True, 'opcoes': []}, 'sfx': []})
        (sb / 'storyboard.jpg').write_bytes(b'JPG')
        (sb / 'episodio.json').write_text('{}')
        t = self.client.get('/job/Teste/video').get_data(as_text=True)
        self.assertNotIn('feito antes dos passos do formato', t)
        self.assertNotIn('id="musica"', t)
        (sb / 'episodio.json').unlink()
        self.assertIn('feito antes dos passos do formato', self.client.get('/job/Teste/video').get_data(as_text=True))

    def test_formato_que_nao_roda_pela_tela_avisa_no_criar(self):
        self.criar_formato(slug='papel', status='receita', exemplo=False)
        self.assertFalse(formatos.carregar('papel')['na_tela'])
        self.criar_formato(slug='pronto-sim', exemplo=False)
        self.assertTrue(formatos.carregar('pronto-sim')['na_tela'])
        t = self.client.get('/criar').get_data(as_text=True)
        self.assertIn('data-formato="papel" data-entrada="video" data-titulo="Doc Teste" data-na-tela="0"', t)
        self.assertIn('só pelo chat', t)
        self.assertIn('ainda não roda pela tela. Peça pelo chat', t)
        self.assertIn('Este formato ainda não roda pela tela', self.client.get('/formato/papel').get_data(as_text=True))

    def test_so_cortar_mostra_o_roteiro_e_o_menu_leva_aos_cortes(self):
        t = self.client.get('/criar').get_data(as_text=True)
        self.assertIn('<div class="campo" data-mostrar="roteiro cortar">', t)
        self.assertIn('Recortar vídeo', t)

    def test_material_aceita_musica_e_pdf(self):
        self.job('novo')
        t = self.client.get('/job/Teste/video').get_data(as_text=True)
        self.assertIn('accept="image/*,video/*,audio/*,application/pdf,.pdf"', t)


class GravadoComStoryboardProprio(Base):
    def test_ferramenta_generica_nao_escreve_por_cima(self):
        d = self.criar_formato(slug='cine', exemplo=False)
        dados = C.ler_json(d / 'formato.json')
        dados.update(tipo='gravado', esteira={'etapas': ETAPAS, 'comandos': {'storyboard': 'python3 <sandbox>/storyboard.py',
                                                                             'render': 'python3 <sandbox>/render.py',
                                                                             'conferir': 'python3 <sandbox>/conferir.py'}})
        C.gravar_json(d / 'formato.json', dados)
        self.assertTrue(formatos.storyboard_proprio(dados))
        self.assertFalse(formatos.storyboard_proprio({**dados, 'esteira': {'etapas': ETAPAS}}))
        j = self.job_formato(formato='cine')
        with patch.object(P.subprocess, 'run') as run:
            P._storyboard_da_ferramenta(j)
        run.assert_not_called()
        txt = P.camadas_de_regra(j)
        self.assertIn(f'Conferência do formato: `python3 {j["sandbox"]}/conferir.py` (só entrega com exit 0)', txt)
        self.assertIn('../x é o arquivo x do modelo', txt)


class CenasDeApoio(Base):
    def test_formatos_sem_b_roll_de_fora_nao_perguntam(self):
        for slug in ('documentario',):
            self.assertNotIn('cenas', [e['campo'] for e in formatos.escolhas({'slug': slug})], slug)

    def test_quantidade_que_o_formato_pede(self):
        f = {'escolhas': [{'campo': 'cenas', 'rotulo': 'Cenas de baixo', 'tipo': 'um', 'opcoes': ['B-roll real (grátis)'],
                           'quantidade': 8}]}
        self.assertEqual(formatos.quantidade_cenas(f), 8)
        self.assertIsNone(formatos.quantidade_cenas({'escolhas': [{'campo': 'cenas', 'quantidade': 40}]}))
        self.assertEqual(simples._cenas_da_chip('B-roll real (grátis)', 8), {'origem': 'busca', 'quantidade': 8, 'do_formato': True})
        self.assertEqual(simples._cenas_da_chip('B-roll real (grátis)'), {'origem': 'busca', 'quantidade': 3})
        j = self.job('novo')
        j['broll_config'] = {'origem': 'busca', 'quantidade': 8, 'do_formato': True}
        txt = edicao.instrucao(j)
        self.assertIn('até 8 cenas de apoio', txt)
        self.assertNotIn('mantenha o bruto', txt)
        j['broll_config'] = {'origem': 'busca', 'quantidade': 3}
        self.assertIn('mantenha o bruto', edicao.instrucao(j))

    def test_evento_aceita_fotos_junto_dos_videos(self):
        self.stack.enter_context(patch.object(simples, 'UPLOADS', self.est))
        d = self.criar_formato(slug='evento', exemplo=False, modelos=('estilo',))
        dados = C.ler_json(d / 'formato.json')
        dados.update(entrada='filmagem', tipo='gravado')
        dados.pop('esteira')
        C.gravar_json(d / 'formato.json', dados)
        clip = video(self.root / 'clip.mp4')
        r = self.client.post('/criar', data={'formato': 'evento', 'cliente': 'Teste', 'titulo': 'Festa',
                                             'videos': [(clip.open('rb'), 'clip.mp4'), (io.BytesIO(b'JPG'), 'logo.jpg')]},
                             content_type='multipart/form-data')
        self.assertEqual(r.status_code, 302)
        j = P.carregar('Teste', 'festa')
        self.assertTrue(any(m.endswith('logo.jpg') for m in j['materiais']))
        self.assertTrue(j['bruto'].endswith('clip.mp4'))


class FolhaDeQualquerVideo(Base):
    def test_cli_folha_video(self):
        v = video(self.root / 'render.mp4', dur=9)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = formatos.main(['folha-video', str(v), str(self.root / 'qa/folha.jpg')])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / 'qa/folha.jpg').is_file())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(formatos.main(['folha-video', str(self.root / 'nao.mp4'), str(self.root / 'x.jpg')]), 1)


class Corte(Base):
    def test_chave_do_groq_no_lugar_novo(self):
        (self.root / 'clientes/Teste/.env').write_text('GROQ_API_KEY="nova"\n')
        with patch.object(corte, 'RAIZ', self.root), patch.dict(os.environ, {'GROQ_API_KEY': ''}):
            self.assertEqual(corte.chave_groq('Teste'), 'nova')
            self.assertEqual(corte.chave_groq('Ninguem'), '')

    def test_transcricao_de_outro_video_nao_volta_como_se_fosse_esta(self):
        work = self.root / 'w'
        work.mkdir()
        bruto, cortado = video(self.root / 'bruto.mp4', dur=3), video(self.root / 'cortado.mp4', dur=2)
        palavras = [{'word': w, 'start': i * .3, 'end': i * .3 + .25} for i, w in enumerate('uma frase com várias palavras boas'.split())]
        falso = lambda v, w: {'words': palavras, 'motor': 'scribe-verbatim'}
        with patch.object(corte, '_scribe', side_effect=falso):
            corte.transcrever(bruto, work)
            self.assertEqual(C.ler_json(work / 'words.json')['fonte']['arquivo'], 'bruto.mp4')
            self.assertEqual(corte._de_outro_video(work / 'words.json', bruto), '')
            self.assertEqual(corte._de_outro_video(work / 'words.json', cortado), 'bruto.mp4')
            (work / 'CORTE.json').write_text('{"segmentos": []}')
            with self.assertRaises(RuntimeError):            # o corte do bruto depende dessa transcrição: não estraga
                corte.transcrever(cortado, work)
            (work / 'CORTE.json').unlink()
            corte.transcrever(cortado, work)                 # sem corte: guarda a antiga e transcreve de novo
        self.assertEqual(C.ler_json(work / 'words.json')['fonte']['arquivo'], 'cortado.mp4')
        self.assertTrue(list(work.glob('_transcricao-anterior-*/words.json')))


class MusicaComDeEAte(Base):
    def test_tela_mostra_de_e_ate_quando_o_motor_mediu(self):
        sb = self.root / self.job('plano')['sandbox']
        C.gravar_json(sb / 'cenas.json', {'musica': [{'arquivo': 'audio/musicas/364.mp3', 'inicio_s': 0, 'de': 0},
                                                    {'arquivo': 'audio/musicas/1154.mp3', 'inicio_s': 0, 'de': 76.96}]})
        j = P.carregar('Teste', 'video')
        lista = [{'id': 'm1', 'arquivo': 'work/musica/364.mp3', 'titulo': 'Sombria'},
                 {'id': 'm2', 'arquivo': 'work/musica/1154.mp3', 'titulo': 'Reaching Out'}]
        with patch.object(MB, '_raiz', return_value=self.root):
            MB._amarrar_trechos(j, lista)
            self.assertEqual(lista[0]['troca_txt'], 'troca pra Reaching Out em 1:17')
            (sb / 'qa').mkdir(exist_ok=True)
            C.gravar_json(sb / 'qa/checagem.json', {'numeros': {'musica': {'trechos': [
                {'arquivo': 'audio/musicas/364.mp3', 'inicio_s': 0, 'de': 0, 'ate': 76.96},
                {'arquivo': 'audio/musicas/1154.mp3', 'inicio_s': 0, 'de': 76.96, 'ate': 123.4}]}}})
            lista = [{'id': 'm1', 'arquivo': 'work/musica/364.mp3', 'titulo': 'Sombria'},
                     {'id': 'm2', 'arquivo': 'work/musica/1154.mp3', 'titulo': 'Reaching Out'}]
            MB._amarrar_trechos(j, lista)
        self.assertEqual(lista[0]['troca_txt'], 'toca de 0:00 até 1:17, depois Reaching Out de 1:17 até 2:03')
        self.assertTrue(all('ate' not in t for t in lista[0]['trechos']))   # o "ate" é só pra mostrar


if __name__ == '__main__':
    unittest.main()
