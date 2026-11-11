"""Grupo 1 · motor do Documentário: receita (formato.json + esteira), kit de cenas, áudio, conferência e regras.

Só leitura nos arquivos reais; o que roda o motor grava em pasta temporária. Sem navegador (o render de verdade
é conferido à mão com `render.py --storyboard/--conferir`), sem rede, nada pago."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
import formatos  # noqa: E402
from _comum import com_venv, rodar_com_limite  # noqa: E402

DOC = RAIZ / 'formatos' / 'documentario'
BASE = DOC / 'base'
CLIENTE4 = RAIZ / 'clientes' / 'Cliente4' / 'cliente4Content' / 'modelos' / 'documentario'
PY = sys.executable


def _motor():
    spec = importlib.util.spec_from_file_location('render_doc_teste', BASE / 'render.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _motor()


def _ler(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def _modelo():
    return _ler(BASE / 'cenas-modelo.json')


class Receita(unittest.TestCase):
    def test_formato_pronto_com_esteira_do_contrato(self):
        f = _ler(DOC / 'formato.json')
        self.assertEqual(f['status'], 'pronto')
        self.assertEqual(f['esteira']['motor'], 'render.py')
        est = formatos.esteira({**f, 'slug': 'documentario'})
        self.assertIsNotNone(est, 'esteira malformada: a tela não deixaria usar o formato')
        self.assertEqual([e['id'] for e in est['etapas']], ['briefing', 'preparar', 'fora', 'cenas', 'storyboard', 'video', 'conferir'])
        fora = next(e for e in est['etapas'] if e['id'] == 'fora')
        for trecho in ('get-brolls', 'acervo', 'Nunca a própria pessoa', 'no storyboard'):
            self.assertIn(trecho, fora['faz'])
        motor = f['esteira']['motor_arquivos']   # o que o Estúdio leva da base pro cliente e pra sandbox
        for n in ('render.py', 'index.html', 'fontes', 'audio/sfx'):
            self.assertIn(n, motor)
        self.assertTrue(all((BASE / n).exists() for n in motor), motor)
        self.assertNotIn('audio/musicas', motor)
        self.assertEqual([e['id'] for e in est['etapas'] if e['aprovar']], ['briefing', 'storyboard'])   # o passo 0 se aprova na conversa
        self.assertEqual(est['etapas'][est['parada']]['andamento'], 'storyboard')
        for nome, flag in (('storyboard', '--storyboard'), ('conferir', '--conferir')):
            self.assertIn(flag, est['comandos'][nome])
            self.assertIn('render.py', est['comandos'][nome])
        self.assertTrue(all(e['faz'] for e in est['etapas']))

    def test_passos_e_musica_pro_joao(self):
        f = _ler(DOC / 'formato.json')
        self.assertEqual(len(f['passos']), 4)
        self.assertTrue(all(len(p) <= 110 for p in f['passos']))
        musica = next(u for u in f['usa'] if u['oque'] == 'Música')
        self.assertEqual(musica['quem'], 'Mixkit, já guardadas no Estúdio, mais busca no Mixkit')

    def test_como_fazer_nao_manda_usar_o_motor_do_motion(self):
        txt = (DOC / 'COMO-FAZER.md').read_text(encoding='utf-8')
        self.assertNotIn('motion-narrado/base', txt)
        for flag in ('--storyboard', '--conferir'):
            self.assertIn(flag, txt)

    def test_regras_gerais_g11_tem_a_excecao_do_documentario(self):
        g11 = next(l for l in (RAIZ / 'REGRAS.md').read_text(encoding='utf-8').splitlines() if l.startswith('| G11 |'))
        self.assertIn('documentário', g11)
        self.assertIn('zero golpe', g11)


class Regras(unittest.TestCase):
    def _conferir(self, arq, minimo_ids=()):
        d = _ler(arq)
        regras = d['regras']
        self.assertLessEqual(len(regras), 24)
        ids = [r['id'] for r in regras]
        self.assertEqual(len(ids), len(set(ids)))
        for r in regras:
            self.assertLessEqual(len(r['texto']), 600, r['id'])
            self.assertRegex(r.get('desde', ''), r'^\d{4}-\d{2}-\d{2}$', r['id'])
        for i in minimo_ids:
            self.assertIn(i, ids)
        return d

    def test_regras_do_formato(self):
        self._conferir(DOC / 'aprendizado' / 'regras.json', (
            'tela-ate-2-5s', 'imagem-literal', 'rosto-35', 'gancho-construcao', 'texto-contorno-sombra',
            'frase-centraliza', 'recorte-do-bruto', 'musica-mixkit-audivel', 'efeitos-suaves-zero-golpe'))
        for l in (DOC / 'aprendizado' / 'historico.jsonl').read_text(encoding='utf-8').splitlines():
            e = json.loads(l)
            self.assertTrue({'tipo', 'categoria', 'texto', 'origem', 'createdAt', 'job'} <= set(e))

    @unittest.skipUnless(CLIENTE4.is_dir(), 'Cliente removido em 29-out-2026 (Cliente4 foi pra lixeira); teste sem base.')
    def test_regras_do_cliente4(self):
        d = self._conferir(CLIENTE4 / 'aprendizado' / 'regras.json', ('cara-do-cliente4', 'cenas-literais-cliente4', 'musica-do-cliente4'))
        self.assertEqual(d['formato'], 'documentario')
        cara = next(r for r in d['regras'] if r['id'] == 'cara-do-cliente4')['texto']
        for x in ('#7fe6a9', '#d9a441', '#ff8b7a', 'Tinos 700'):   # a cor do projeto dele ("usa a cor dele", 09-out)
            self.assertIn(x, cara)


class Acervo(unittest.TestCase):
    def test_catalogo_de_musicas(self):
        cat = _ler(BASE / 'audio' / 'catalogo.json')
        ms = cat['musicas']
        self.assertEqual(len(ms), 38)
        self.assertIn('Mixkit', cat['licenca'])
        self.assertEqual(sorted(m['id'] for m in ms if m['status'] == 'rejeitada'), ['32', '473', '614', '623', '970'])
        for m in ms:
            self.assertTrue((BASE / m['arquivo']).is_file(), m['arquivo'])
            self.assertIn('banda_media_aguda', m)

    def test_efeitos_e_fontes(self):
        sfx = {p.name for p in (BASE / 'audio' / 'sfx').iterdir()}
        for n in ('typing', 'key-press', 'whoosh-short', 'click-soft', 'pop', 'riser'):
            self.assertIn(f'{n}.mp3', sfx)
        self.assertIn('CREDITS.md', sfx)
        for f in ('Tinos-Bold.ttf', 'Caveat.ttf'):
            self.assertTrue((BASE / 'fontes' / f).is_file())

    @unittest.skipUnless(CLIENTE4.is_dir(), 'Cliente removido em 29-out-2026 (Cliente4 foi pra lixeira); teste sem base.')
    def test_copia_do_cliente4_tem_o_mesmo_motor(self):
        h = lambda p: hashlib.sha1(p.read_bytes()).hexdigest()
        for n in ('render.py', 'index.html', 'README.md', 'cenas-modelo.json', 'audio/catalogo.json', 'fontes/Tinos-Bold.ttf'):
            self.assertEqual(h(CLIENTE4 / n), h(BASE / n), n)
        self.assertEqual(_ler(CLIENTE4 / 'ficha.json')['formato'], 'documentario')


class Plano(unittest.TestCase):
    def test_modelo_tem_os_9_tipos_com_tempos_e_acentos(self):
        p = R.planejar(_modelo(), BASE)
        self.assertEqual({c['tipo'] for c in p['cenas']}, set(R.TIPOS))
        self.assertEqual(p['avisos'], [])
        self.assertTrue(all(c['ate'] - c['de'] <= R.TELA_MAX + 1e-6 for c in p['cenas']))
        txt = ' '.join(tk['txt'] for c in p['cenas'] for tk in c['tokens'])
        for palavra in ('gíria', 'manhã', 'preço'):
            self.assertIn(palavra, txt.lower())
        frase = next(c for c in p['cenas'] if c['tipo'] == 'frase')
        self.assertTrue(any(tk['k'] == 'dor' for tk in frase['tokens']))
        for c in p['cenas']:   # cada palavra entra em ordem e dentro da cena
            ss = [tk['s'] for tk in c['tokens']]
            self.assertEqual(ss, sorted(ss))

    def test_efeitos_suaves_espacados_no_teto_do_exemplo_e_nenhum_golpe(self):
        """V2 do Cliente4: 108 efeitos em 2 min (46 teclados, 41 passagens), demais. O exemplo-1 tem 16 em 1:23."""
        p = R.planejar(_modelo(), BASE)
        ev = p['eventos']
        self.assertTrue(ev)
        self.assertLessEqual(len(ev), R.teto_efeitos(p['total']))
        self.assertTrue(all(b['t'] - a['t'] >= R.EFEITO_ESPACO_S - 1e-6 for a, b in zip(ev, ev[1:])))
        self.assertEqual(ev[0]['som'], 'typing')   # o som principal é o teclado da tela de texto, como no exemplo
        self.assertEqual(R.teto_efeitos(119.6), 24)
        longo = {**_modelo(), 'duracao': None, 'cenas': [dict(c, de=c['de'] + k * 22.2) for k in range(5) for c in _modelo()['cenas']]}
        pl = R.planejar(longo, BASE)
        self.assertLessEqual(len(pl['eventos']), R.teto_efeitos(pl['total']))
        self.assertGreater(pl['eventos'][-1]['t'], pl['total'] * .7)   # o teto se espalha pelo vídeo todo
        self.assertTrue({e['som'] for e in p['eventos']} <= set(R.SONS))
        self.assertFalse({e['som'] for e in p['eventos']} & R.GOLPES)
        self.assertTrue(all(.1 <= v <= .2 for _, v in R.SONS.values()))
        sem = R.planejar({**_modelo(), 'efeitos': False}, BASE)
        self.assertEqual(sem['eventos'], [])

    def test_marcas_do_caderno_terminam_dentro_da_cena(self):
        p = R.planejar(_modelo(), BASE)
        for c in p['cenas']:
            for it in c.get('itens') or []:
                self.assertLessEqual(it['tm'], c['ate'] - .3)
            if c.get('circulo'):
                self.assertLessEqual(c['circulo']['t'], c['ate'] - .5)

    def test_musica_trocando_no_meio_e_sem_musica(self):
        segs = R.segmentos_musica({'musica': [{'arquivo': 'a.mp3', 'de': 0}, {'arquivo': 'b.mp3', 'de': 40}]}, 90)
        self.assertEqual([(s['de'], s['ate']) for s in segs], [(0, 40), (40, 90)])
        self.assertEqual(R.segmentos_musica({'musica': None}, 90), [])

    def test_pausas_e_numero_brasileiro(self):
        ws = [{'w': 'a', 's': 0.0, 'e': 0.4}, {'w': 'b', 's': 2.0, 'e': 2.4}]
        jan = R.pausas(ws, 3.5)
        self.assertEqual(len(jan), 2)
        for (a, b), (ea, eb) in zip(jan, [(0.65, 1.95), (2.65, 3.45)]):
            self.assertAlmostEqual(a, ea)
            self.assertAlmostEqual(b, eb)
        self.assertEqual(R.br(2.5), '2,5')
        self.assertEqual(R.mmss(72.34), '1:12,3')

    def test_caminho_relativo_acha_a_base_do_formato(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(R.achar('demo/voz.wav', Path(t)), (BASE / 'demo' / 'voz.wav').resolve())


class Checagem(unittest.TestCase):
    """O que a prova do Vídeo 1 V2 do Cliente4 mostrou (nota 7/10): agora o motor reprova sozinho, já no --storyboard."""

    def test_modelo_do_kit_passa_na_checagem(self):
        ch = R.checar(_modelo(), BASE)
        self.assertEqual(ch['motivos'], [])
        self.assertLessEqual(ch['numeros']['pessoa_na_tela_pct'], R.PESSOA_TELA_MAX * 100)
        self.assertEqual(ch['numeros']['cenas_de_fora'], 2)

    def test_polaroid_da_propria_pessoa_e_falta_de_cena_de_fora_reprovam(self):
        doc = _modelo()
        doc['cenas'] = [{k: v for k, v in c.items() if k != 'imagem'} if c['tipo'] in ('polaroid', 'filme') else c for c in doc['cenas']]
        ch = R.checar(doc, BASE)
        m = ' | '.join(ch['motivos'])
        self.assertIn('Cena 5 (Polaroid, 0:07,9) mostra a própria pessoa', m)
        self.assertIn('Cena 9 (Filme', m)
        self.assertIn('Só 0 cena(s) de fora', m)
        self.assertIn('A pessoa aparece em', m)
        self.assertGreater(ch['numeros']['pessoa_na_tela_pct'], R.PESSOA_TELA_MAX * 100)
        mesmo = {**_modelo(), 'cenas': [dict(c, imagem='demo/pessoa.jpg') if c['tipo'] == 'polaroid' else c for c in _modelo()['cenas']]}
        self.assertIn('mostra a própria pessoa', ' | '.join(R.checar(mesmo, BASE)['motivos']))   # o bruto pelo caminho também conta

    def test_relogio_so_com_hora_na_fala(self):
        for txt, ok in (('Das onze da noite às cinco da manhã.', True), ('fico até 23h', True), ('de madrugada', True),
                        ('isso o tempo inteiro.', False), ('tempo todo pra', False), ('', False)):
            self.assertEqual(R.hora_na_fala(txt), ok, txt)
        doc = _modelo()   # a bifurcação ("Só que aí vem uma bifurcação.") vira relógio: ninguém falou hora
        doc['cenas'] = [dict(tipo='relogio', de=c['de'], de_hora='08:00', ate_hora='18:00') if c['tipo'] == 'traco' else c
                        for c in doc['cenas']]
        m = ' | '.join(R.checar(doc, BASE)['motivos'])
        self.assertIn('Cena 7 (Relógio, 0:12,8): a fala não diz hora', m)
        self.assertIn('inventa 08:00', m)
        self.assertNotIn('Cena 4 (Relógio', m)   # "das onze da noite às cinco da manhã" é hora

    def test_ultima_cena_conta_ate_o_fim_do_video(self):
        m = ' | '.join(R.checar({**_modelo(), 'duracao': 25}, BASE)['motivos'])
        self.assertIn('Cena 11 (Frase, 0:20,5) fica 4,5 s na tela (a última cena vai até o fim do vídeo)', m)

    def test_cenas_de_fora_pedidas_pela_duracao(self):
        # o exemplo (82,8 s) tem 4; com 1 a cada 30 s, 2 min pediam só as 4 já escolhidas e ninguém buscava cena nova
        self.assertEqual([R.fora_minimo(t) for t in (22, 44, 60, 82.8, 119.6)], [1, 1, 3, 4, 6])

    def test_numeros_do_kit_e_sons_das_cenas(self):
        n = R.checar(_modelo(), BASE)['numeros']
        self.assertLessEqual(n['frase_pct'], R.FRASE_MAX * 100)
        self.assertGreaterEqual(n['objetos_pct'], R.OBJETOS_MIN * 100)
        self.assertEqual(n['frases_seguidas_max'], 2)
        self.assertEqual(n['imagens_repetidas'], [])
        self.assertEqual(set(n['efeitos']['sons_das_cenas']), set(R.SONS))
        sem_relogio = {**_modelo(), 'cenas': [c for c in _modelo()['cenas'] if c['tipo'] != 'relogio']}
        self.assertNotIn('tique', R.checar(sem_relogio, BASE)['numeros']['efeitos']['sons_das_cenas'])
        desligado = {**_modelo(), 'efeitos': ['typing']}   # som desmarcado continua na lista: o chip não some da tela
        self.assertIn('tique', R.checar(desligado, BASE)['numeros']['efeitos']['sons_das_cenas'])

    def test_frase_demais_seguidas_e_poucos_objetos_reprovam(self):
        """Storyboard refeito do V2 do Cliente4: 43% de frase, 4 seguidas (CAIXA, TURNOVER, EXTREMAMENTE, DANOSO) e 19% de
        objetos. O motor só pedia 6 tipos; pra baixar a pessoa na tela, a frase era o caminho mais fácil."""
        doc = _modelo()
        doc['cenas'] = [dict(c, tipo='frase') if c['tipo'] in ('caderno', 'traco', 'jornal', 'filme') else c for c in doc['cenas']]
        ch = R.checar(doc, BASE)
        m = ' | '.join(ch['motivos'])
        self.assertIn('Frase em fundo liso ocupa', m)
        self.assertIn('Construções de objeto', m)
        self.assertIn('frases seguidas (cenas 6 a 11', m)
        self.assertGreater(ch['numeros']['frase_pct'], R.FRASE_MAX * 100)
        self.assertLess(ch['numeros']['objetos_pct'], R.OBJETOS_MIN * 100)
        self.assertEqual(ch['numeros']['frases_seguidas_max'], 6)
        self.assertNotIn('Troque recortes por frase', m)

    def test_a_mesma_imagem_duas_vezes_reprova(self):
        """V2 refeito: 9 recortes de só 5 quadros (72, 105 e 111 duas vezes; o 21 no jornal e num recorte)."""
        doc = {**_modelo(), 'video': 'bruto-que-nao-precisa-existir.mp4'}
        doc['cenas'] = [dict(c) for c in doc['cenas']]
        por = {c['tipo']: c for c in doc['cenas']}
        por['recorte']['quadro_s'] = 21
        por['jornal']['quadro_s'] = 21.8          # a menos de 2 s: a mesma foto
        por['relogio']['quadro_s'] = 40
        m = ' | '.join(R.checar(doc, BASE)['motivos'])
        self.assertIn('A mesma imagem aparece 2 vezes: cenas 2, 8 (quadro 0:21,0', m)
        por['jornal']['quadro_s'] = 30
        self.assertNotIn('A mesma imagem', ' | '.join(R.checar(doc, BASE)['motivos']))
        dois = {**_modelo(), 'cenas': [dict(c, imagem='demo/polaroid.jpg') if c['tipo'] == 'filme' else c for c in _modelo()['cenas']]}
        self.assertIn('A mesma imagem aparece 2 vezes: cenas 5, 9 (polaroid.jpg)', ' | '.join(R.checar(dois, BASE)['motivos']))
        self.assertEqual(R.checar(_modelo(), BASE)['numeros']['imagens_repetidas'], [])   # foto única do bruto não conta

    def test_tela_que_corta_a_ideia_palavra_fora_da_fala_e_fim_fraco(self):
        for fala, palavra in (('barganha o', 'o'), ('área do', 'do'), ('Ele não quer trabalhar e', 'e'),
                              ('um desafio muito', 'muito'), ('ele é,', None), ('o preço.', None), ('', None), ('Isso é dono', None)):
            self.assertEqual(R.termina_no_meio(fala), palavra, fala)
        doc = _modelo()
        doc['cenas'] = [dict(c) for c in doc['cenas']]
        doc['cenas'][9]['de'] = 17.5                # a frase 10 começa no meio de "Chega uma hora que | não cabe mais."
        doc['cenas'][10]['de'] = 21.0               # a última tela fica só com "se constrói.", sem a LIBERDADE
        m = ' | '.join(R.checar(doc, BASE)['motivos'])
        self.assertIn('Cena 9 (Filme, 0:16,6) termina em "que"', m)
        self.assertIn('a palavra-chave "liberdade" não está na fala dela ("se constrói.")', m)
        self.assertIn('O fim é fraco: a última tela com fala (cena 11, "se constrói.")', m)

    def test_frase_na_tela_sem_virgula_no_fim(self):
        doc = {**_modelo(), 'cenas': [dict(c) for c in _modelo()['cenas']]}
        doc['cenas'][0]['texto'] = 'Correria é gíria de malandro,'
        c = R.planejar(doc, BASE)['cenas'][0]
        self.assertEqual(c['tokens'][-1]['txt'], 'MALANDRO')
        self.assertTrue(c['fala'])

    def test_folha_do_broll_com_o_segundo_de_cada_quadro(self):
        with tempfile.TemporaryDirectory() as t:
            v = Path(t) / 'broll.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=10:d=6',
                            '-pix_fmt', 'yuv420p', str(v)], check=True, timeout=60)
            f = R.folha_broll(v, Path(t) / 'qa' / 'folha-broll.jpg', marcado=3.0)
            self.assertTrue(f.is_file())
            r = rodar_com_limite([PY, str(BASE / 'render.py'), '--folha-broll', str(v), '--out', t], 120, capture_output=True, text=True, env=com_venv())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('folha-broll.jpg', r.stdout)

    def test_quadro_do_storyboard_com_a_ultima_palavra_inteira(self):
        c = {'de': 10.0, 'ate': 12.0, 'tokens': [{'e': 10.8}, {'e': 11.98}]}
        self.assertEqual(R.instante_storyboard(c), 11.98)    # antes: 11,88 e saía "CARREI▌"
        self.assertEqual(R.instante_storyboard({'de': 0, 'ate': 2.0, 'tokens': []}), 1.88)
        self.assertEqual(R.instante_storyboard({'de': 0, 'ate': 1.0}), 0.88)
        p = R.planejar(_modelo(), BASE)
        for c in p['cenas']:
            t = R.instante_storyboard(c)
            self.assertTrue(c['de'] <= t < c['ate'])
            self.assertTrue(all(tk['e'] <= t + 1e-6 for tk in c['tokens']), c['n'])

    def test_efeito_que_a_copia_nao_tem_vem_da_base(self):
        self.assertEqual(R.arquivo_sfx('tique.mp3'), BASE / 'audio' / 'sfx' / 'tique.mp3')
        with tempfile.TemporaryDirectory() as t:   # cópia sem audio/sfx (como a sandbox antiga sem o tique.mp3)
            (Path(t) / 'render.py').write_bytes((BASE / 'render.py').read_bytes())
            spec = importlib.util.spec_from_file_location('render_copia_teste', Path(t) / 'render.py')
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            pop = m.arquivo_sfx('pop.mp3')   # o solto de sempre ou uma variante do rodízio (audio/sfx/pop/), sempre da base do formato
            self.assertIn(pop.parent, (m.BASE_FORMATO / 'audio' / 'sfx', m.BASE_FORMATO / 'audio' / 'sfx' / 'pop'))
            self.assertTrue(pop.is_file())

    def test_checagem_do_storyboard_grava_o_som_e_mede_a_musica(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            doc = _modelo()
            ch = R.checagem_storyboard(doc, R.planejar(doc, BASE), BASE, out)
            self.assertEqual(ch['motivos'], [])
            som = out / 'previa-som.m4a'
            self.assertTrue(som.is_file())
            self.assertAlmostEqual(R.duracao_midia(som), 22.19, delta=.3)
            self.assertGreaterEqual(ch['numeros']['musica']['pausas_db'], R.MUSICA_MIN_DB)
            res = _ler(out / 'qa' / 'checagem.json')
            self.assertTrue(res['ok'])
            ruim = {**doc, 'cenas': [{'tipo': 'pessoa', 'de': 0}]}
            ch = R.checagem_storyboard(ruim, R.planejar(ruim, BASE), BASE, out, som=False)
            self.assertFalse(_ler(out / 'qa' / 'checagem.json')['ok'])
            self.assertTrue(any('3 primeiros segundos' in x for x in ch['motivos']))


class ProvaV2Nota75(unittest.TestCase):
    """O storyboard do V2 do Cliente4 (nota 7,5 contra o exemplo): o motor reprova sozinho o que o João viu."""

    def _m(self, doc, pasta=BASE):
        return ' | '.join(R.checar(doc, pasta)['motivos'])

    def test_palavra_chave_fraca_e_fim_pendurado(self):
        for kw, fraca in (('vezes', True), ('todo', True), ('muito grande', True), ('diretamente', True),
                          ('barganha', False), ('prejuízo', False), ('TUDO', False), ('turnover', False)):
            self.assertEqual(R.chave_fraca(kw), fraca, kw)
        doc = {**_modelo(), 'cenas': [dict(c) for c in _modelo()['cenas']]}
        doc['cenas'][9] = dict(doc['cenas'][9], destaque=['isso'])   # "E isso acontece com você."
        self.assertIn('"ISSO" é palavra-chave fraca', self._m(doc))
        doc = {**_modelo(), 'cenas': [dict(c) for c in _modelo()['cenas']]}
        doc['cenas'][9]['texto'] = 'E isso acontece diretamente com ele'
        doc['cenas'][10] = dict(doc['cenas'][10], texto='diretamente com ele', destaque=['diretamente'])
        m = self._m(doc)
        self.assertIn('O fim fica pendurado', m)
        self.assertIn('"DIRETAMENTE" é palavra-chave fraca', m)

    def test_caderno_sem_lista_e_tela_no_meio_da_ideia(self):
        doc = {**_modelo(), 'cenas': [dict(c) for c in _modelo()['cenas']]}
        cad = next(c for c in doc['cenas'] if c['tipo'] == 'caderno')
        cad['itens'] = cad['itens'][:1]
        self.assertIn('caderno é lista, com 2 itens ou mais', self._m(doc))
        ws = [{'w': 'uma', 's': 0.0, 'e': .2}, {'w': 'habilidade', 's': .2, 'e': .6}, {'w': 'muito', 's': .62, 'e': .8},
              {'w': 'grande.', 's': .85, 'e': 1.2}, {'w': 'Pra', 's': 2.0, 'e': 2.1}]
        self.assertEqual(R.comeca_no_meio({'de': .62, 'ate': 1.9}, ws), 'habilidade')
        self.assertIsNone(R.comeca_no_meio({'de': 2.0, 'ate': 3.0}, ws))   # depois do ponto (e da pausa)
        self.assertEqual(R.oracoes(ws), [(0, 3), (4, 4)])

    def test_mesmo_clipe_banco_de_imagem_e_origem(self):
        doc = {**_modelo(), 'cenas': [dict(c, imagem='demo/polaroid.jpg') if c['tipo'] == 'filme' else c for c in _modelo()['cenas']]}
        self.assertIn('O clipe polaroid.jpg entra 2 vezes', self._m(doc))
        banco = {**_modelo(), 'cenas': [dict(c, origem='Pexels 12345 (escritório)') if c['tipo'] == 'polaroid' else c
                                         for c in _modelo()['cenas']]}
        self.assertIn('é de banco de imagem (Pexels', self._m(banco))
        sem = {**_modelo(), 'cenas': [{k: v for k, v in c.items() if k != 'origem'} for c in _modelo()['cenas']]}
        self.assertIn('Cenas de fora sem "origem" (cenas 5, 9)', self._m(sem))
        a = {'tipo': 'filme', 'i': 3, 'de': 10, 'ate': 12.4, 'video': 'x.mp4', 'inicio_s': 1.0}
        self.assertTrue(R._continua(a, dict(a, i=4, de=12.4, ate=14, inicio_s=3.4)))   # o mesmo plano emendado conta 1
        self.assertFalse(R._continua(a, dict(a, i=4, de=12.4, ate=14, inicio_s=9.0)))

    def test_filme_e_polaroid_alternam_recorte_demais_e_tela_que_para_no_meio(self):
        # prova das 22h do V2 do Cliente4: 13 de 14 cenas de fora em filme, 6 recortes iguais, "mas também envolve" + "uma carga"
        ws = [{'w': 'mas', 's': 0.0, 'e': .2}, {'w': 'também', 's': .2, 'e': .5}, {'w': 'envolve', 's': .5, 'e': .9},
              {'w': 'uma', 's': .95, 'e': 1.1}, {'w': 'carga.', 's': 1.1, 'e': 1.5}, {'w': 'e', 's': 1.55, 'e': 1.6}]
        self.assertEqual(R.segue_na_proxima({'de': 0.0, 'ate': .95}, ws), 'uma')
        self.assertIsNone(R.segue_na_proxima({'de': 0.0, 'ate': 1.55}, ws))   # fechou no ponto
        ws[4]['w'] = 'carga'
        self.assertIsNone(R.segue_na_proxima({'de': 0.0, 'ate': 1.55}, ws))   # a seguinte abre outra ideia ("e")
        self.assertTrue(R.chave_fraca('maioria'))
        self.assertEqual([R.recorte_maximo(t) for t in (22, 60, 118)], [1, 2, 4])
        doc = {**_modelo(), 'cenas': [dict(c) for c in _modelo()['cenas']]}
        doc['cenas'][3] = {'tipo': 'recorte', 'de': doc['cenas'][3]['de'], 'quadro_s': 9.0}
        self.assertIn('2 recortes do bruto (cenas 2, 4)', self._m(doc))
        doc = {**_modelo(), 'cenas': [dict(c) for c in _modelo()['cenas']]}
        doc['cenas'][4] = dict(doc['cenas'][4], tipo='filme')
        doc['cenas'][5] = {'tipo': 'filme', 'de': doc['cenas'][5]['de'], 'imagem': 'formatos/documentario/exemplo-1.jpg', 'origem': 'teste'}
        self.assertIn('Das 3 cenas de fora, 3 são filme na tira de jornal e 0 polaroid', self._m(doc))

    def test_papel_claro_e_escuro_se_alternam(self):
        self.assertEqual([R.claro_minimo(t) for t in (22, 60, 82.8, 119.6)], [0, 1, 2, 3])
        self.assertTrue(R.tela_clara({'tipo': 'caderno'}))
        self.assertFalse(R.tela_clara({'tipo': 'caderno', 'tom': 'escuro'}))
        self.assertTrue(R.tela_clara({'tipo': 'polaroid', 'fundo': 'papel'}))

    def test_legenda_abaixo_do_queixo(self):
        rosto = {'x': .25, 'y': .41, 'w': .47, 'h': .26, 'olhos': 3, 'nitidez': 300, 'aspecto': .5625}   # selfie do Cliente4
        for plano in ('aberto', 'close'):
            c = {'plano': plano, 'foco': [.45, .24]}
            R.enquadrar_pessoa(c, [{'rosto': rosto}], {'legenda_y': 1290})
            self.assertGreaterEqual(c['leg_y'], c['queixo_y'] + R.LEG_MARGEM)
            self.assertGreaterEqual(c['leg_y'] - c['queixo_y'], R.folga_legenda(c['rosto_px'], minima=True))   # no peito
            self.assertLessEqual(c['leg_y'], R.LEG_MAX_Y)
        baixo = dict(rosto, y=.5)   # queixo baixo demais: o zoom sobe o rosto
        c = {'plano': 'aberto', 'foco': [.45, .24]}
        R.enquadrar_pessoa(c, [{'rosto': baixo}], {'legenda_y': 1290})
        self.assertLessEqual(c['leg_y'], R.LEG_MAX_Y)
        self.assertGreater(c['zoom'][1], 1.1)
        c = {'plano': 'close', 'foco': [.45, .24]}
        R.enquadrar_pessoa(c, [], {'legenda_y': 1290})   # sem rosto achado: como antes
        self.assertEqual((c['leg_y'], c['queixo_y']), (1290, None))

    def test_cor_do_cliente(self):
        """O V2 do Cliente4 saiu dourado e vermelho com a cor dele já no identidade.json ("usa a cor dele")."""
        with tempfile.TemporaryDirectory() as t:
            cli = Path(t) / 'clientes' / 'X'
            sb = cli / 'xContent' / 'modelos' / 'documentario' / '_sandbox-v'
            sb.mkdir(parents=True)
            (cli / 'identidade.json').write_text(json.dumps({'papeis': {'destaque': '#7fe6a9', 'dor': '#ff8b7a',
                                                                         'empresa_lideranca': '#d9a441', 'fundo': '#0c110e'}}), encoding='utf-8')
            sem = {k: v for k, v in _modelo().items() if k != 'cores'}
            sem['cenas'] = [{'tipo': 'frase', 'de': 0, 'empresa': ['malandro']}] + sem['cenas'][1:]
            pl = R.planejar(sem, sb)
            self.assertEqual([pl['cores'][k] for k in ('marca', 'dor', 'empresa', 'fundo')], ['#7fe6a9', '#ff8b7a', '#d9a441', '#0c110e'])
            self.assertIn('empresa', [tk['k'] for tk in pl['cenas'][0]['tokens']])
            self.assertNotIn('Cores do cenas.json', self._m(sem, sb))
            self.assertIn('Cores do cenas.json que não são as do cliente (marca #86CBFF', self._m(_modelo(), sb))
        self.assertEqual(R.planejar(_modelo(), BASE)['cores']['marca'], '#86CBFF')   # sem cliente: as do cenas.json

    def test_musica_aprovada_na_tela_com_os_trechos(self):
        doc = {**_modelo(), 'musica': [{'arquivo': 'audio/musicas/52.mp3', 'inicio_s': 0, 'de': 0},
                                       {'arquivo': 'audio/musicas/1167.mp3', 'inicio_s': 0, 'de': 12.0}]}
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / 'PLANO.json').write_text(json.dumps({'musica': {'escolha': 'm1', 'opcoes': [
                {'id': 'm1', 'arquivo': 'work/musica/52.mp3'}]}}), encoding='utf-8')
            m = ' | '.join(R.checar(doc, p)['motivos'])
            self.assertIn('guarda só a 1ª', m)
            (p / 'PLANO.json').write_text(json.dumps({'musica': {'escolha': 'm1', 'opcoes': [
                {'id': 'm1', 'arquivo': 'work/musica/52.mp3', 'trechos': doc['musica']}]}}), encoding='utf-8')
            ch = R.checar(doc, p)
            self.assertFalse(any('música' in x.lower() and 'tela' in x for x in ch['motivos']), ch['motivos'])
            self.assertEqual([(x['de'], x['ate']) for x in ch['numeros']['musica']['trechos']], [(0, 12.0), (12.0, 22.19)])
            so1 = {**doc, 'musica': {'arquivo': 'audio/musicas/52.mp3', 'inicio_s': 0}}   # o render sairia só com a 1ª
            self.assertIn('não é a que o João aprovou na tela', ' | '.join(R.checar(so1, p)['motivos']))
        self.assertEqual(len(R.segmentos_musica(doc, 6)), 1)   # --ate 6: a 2ª faixa nem começa


class Conferencia(unittest.TestCase):
    def test_cenas_ruim_reprova_com_motivos_em_portugues(self):
        ruim = {'titulo': 'Ruim', 'saida': 'ruim.mp4', 'video': 'demo/pessoa.jpg', 'voz': 'demo/voz.wav', 'palavras': 'demo/palavras.json',
                'duracao': 10, 'musica': None, 'efeitos': True,
                'cenas': [{'tipo': 'pessoa', 'de': 0}, {'tipo': 'pessoa', 'de': 2}, {'tipo': 'pessoa', 'de': 6}, {'tipo': 'pessoa', 'de': 8}]}
        with tempfile.TemporaryDirectory() as t:
            arq = Path(t) / 'cenas.json'
            arq.write_text(json.dumps(ruim, ensure_ascii=False), encoding='utf-8')
            r = rodar_com_limite([PY, str(BASE / 'render.py'), '--cenas', str(arq), '--conferir'], 120, capture_output=True, text=True, env=com_venv())
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('REPROVADO', r.stdout)
            res = _ler(Path(t) / 'qa' / 'conferir.json')
        m = ' | '.join(res['motivos'])
        for trecho in ('4,0 s na tela', '100% do vídeo', 'construção', '3 primeiros segundos', 'Sem música', 'Sem efeitos'):
            self.assertIn(trecho, m)
        self.assertFalse(res['ok'])
        self.assertEqual(res['numeros']['rosto_pct'], 100.0)

    def _mudo(self, t, plano=None, **extra):
        """cenas-modelo sem música e sem efeitos numa pasta temporária + um mp4 1080x1920 que se mexe (testsrc2)."""
        pasta = Path(t)
        (pasta / 'cenas.json').write_text(json.dumps({**_modelo(), 'musica': None, 'efeitos': False, **extra},
                                                     ensure_ascii=False), encoding='utf-8')
        if plano is not None:
            (pasta / 'PLANO.json').write_text(json.dumps(plano, ensure_ascii=False), encoding='utf-8')
        video = pasta / 'mudo.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=5:d=22.4',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(video)], check=True, timeout=60)
        r = rodar_com_limite([PY, str(BASE / 'render.py'), '--cenas', str(pasta / 'cenas.json'), '--conferir', '--video', str(video)], 180,
                             capture_output=True, text=True, env=com_venv())
        return r, _ler(pasta / 'qa' / 'conferir.json')

    def test_sem_musica_e_sem_efeito_escolhidos_na_tela_aprova(self):
        with tempfile.TemporaryDirectory() as t:
            r, res = self._mudo(t, {'musica': {'sem': True, 'escolha': {'sem': True}, 'opcoes': []}, 'sfx_ligado': False})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('APROVADO', r.stdout)
        self.assertTrue(res['ok'], res['motivos'])
        self.assertEqual(res['numeros']['musica'], {'sem': True, 'por': 'escolha do João'})
        self.assertEqual(res['numeros']['efeitos']['desligados_por'], 'escolha do João')

    def test_mudo_sem_plano_continua_reprovando(self):
        with tempfile.TemporaryDirectory() as t:
            r, res = self._mudo(t)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        m = ' | '.join(res['motivos'])
        self.assertIn('Sem música', m)
        self.assertIn('Sem efeitos', m)

    def test_plano_sem_a_escolha_nao_libera(self):
        """PLANO com música escolhida e efeitos ligados (o padrão): faltar os dois no cenas.json reprova."""
        with tempfile.TemporaryDirectory() as t:
            r, res = self._mudo(t, {'musica': {'escolha': 'm1', 'opcoes': [{'id': 'm1'}]}, 'sfx_ligado': True})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(any('Sem música' in x for x in res['motivos']))
        self.assertTrue(any('Sem efeitos' in x for x in res['motivos']))

    def test_por_de_volta_o_que_o_joao_tirou_reprova(self):
        with tempfile.TemporaryDirectory() as t:
            r, res = self._mudo(t, {'musica': {'sem': True}, 'sfx_ligado': False},
                                musica={'arquivo': 'audio/musicas/1154.mp3', 'inicio_s': 20}, efeitos=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        m = ' | '.join(res['motivos'])
        self.assertIn('"Sem música" na tela', m)
        self.assertIn('desligou os efeitos', m)

    def test_golpe_reprova_mesmo_com_efeitos_desligados(self):
        doc = {**_modelo(), 'musica': None, 'efeitos': False}
        doc['cenas'] = [dict(c) for c in doc['cenas']]
        doc['cenas'][1]['golpe'] = True
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / 'PLANO.json').write_text(json.dumps({'musica': {'sem': True}, 'sfx_ligado': False}), encoding='utf-8')
            res = R.conferir(doc, Path(t), Path(t), Path(t) / 'nao-existe.mp4')
        self.assertTrue(any('golpe' in x for x in res['motivos']), res['motivos'])
        self.assertFalse(any('Sem música' in x or 'Sem efeitos' in x for x in res['motivos']))

    def test_escolha_da_tela_le_os_formatos_do_plano(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            self.assertEqual(R.escolha_da_tela(p), {'sem_musica': False, 'sem_efeitos': False})
            (p / 'PLANO.json').write_text('{quebrado', encoding='utf-8')
            self.assertEqual(R.escolha_da_tela(p), {'sem_musica': False, 'sem_efeitos': False})
            for musica in ('sem', {'sem': True}, {'escolha': {'sem': True}}):
                (p / 'PLANO.json').write_text(json.dumps({'musica': musica}), encoding='utf-8')
                self.assertTrue(R.escolha_da_tela(p)['sem_musica'], musica)
            (p / 'PLANO.json').write_text(json.dumps({'musica': {'sem': False}, 'sfx_ligado': False}), encoding='utf-8')
            self.assertEqual(R.escolha_da_tela(p), {'sem_musica': False, 'sem_efeitos': True})

    def test_musica_rejeitada_reprova(self):
        doc = {**_modelo(), 'musica': {'arquivo': 'audio/musicas/614.mp3', 'inicio_s': 0}}
        with tempfile.TemporaryDirectory() as t:
            res = R.conferir(doc, BASE, Path(t), Path(t) / 'nao-existe.mp4')
        self.assertTrue(any('614 foi rejeitada' in x for x in res['motivos']))


if __name__ == '__main__':
    unittest.main()
