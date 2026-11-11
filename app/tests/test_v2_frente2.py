"""2.0, Frente 2: catálogo de estilos (grupos, escondidos, telas com vídeo). Rotas pelo test client; nada é gravado."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
import formatos


class Catalogo(unittest.TestCase):
    def test_dois_grupos_sem_ocultos(self):
        cat = formatos.catalogo()
        self.assertEqual([g['grupo'] for g in cat], ['falando', 'animacao'])
        ocultos = {f['slug'] for f in formatos.ocultos()}
        vistos = [c['slug'] for g in cat for c in g['formatos']]
        self.assertTrue(vistos)
        self.assertFalse(ocultos & set(vistos))
        self.assertIn('pessoa-no-cantinho', ocultos)
        for g in cat:
            for c in g['formatos']:
                for k in ('slug', 'titulo', 'frase', 'video_exemplo', 'poster', 'estilos'):
                    self.assertIn(k, c)
                self.assertTrue(c['video_exemplo'], c['slug'])

    def test_todo_formato_tem_grupo_e_ordem(self):
        for f in formatos.listar(ocultos=True):
            self.assertIn(f.get('grupo'), ('falando', 'animacao'), f['slug'])
            self.assertIsInstance(f.get('ordem'), int, f['slug'])

    def test_estilos_do_cliente(self):
        self.assertEqual(formatos.estilos_do_cliente(''), [])
        self.assertIn('fala-com-cenas', formatos.estilos_do_cliente('Joao'))


class Telas(unittest.TestCase):
    def setUp(self):
        import servidor
        self.c = servidor.app.test_client()

    def _get(self, url):
        r = self.c.get(url)
        self.assertEqual(r.status_code, 200, url)
        return r.get_data(as_text=True)

    def test_formatos(self):
        h = self._get('/formatos')
        self.assertIn('<video', h)
        self.assertIn('Pessoa falando', h)
        self.assertIn('Usar este estilo', h)
        self.assertIn('/novo-lote?formato=fala-com-cenas', h)
        self.assertIn('Mais formatos (em teste)', h)

    def test_formato(self):
        h = self._get('/formato/fala-com-cenas')
        self.assertIn('<video', h)
        self.assertIn('Usar este estilo', h)

    def test_criar(self):
        h = self._get('/criar')
        self.assertIn('<video', h)
        self.assertIn('/novo-lote', h)
        self.assertIn('Animação', h)

    def test_home_n_esperando(self):
        import simples
        capt = {}
        orig = simples.render_template
        def falso(nome, **kw):
            capt.update(kw)
            return orig(nome, **kw)
        simples.render_template = falso
        try:
            self._get('/')
        finally:
            simples.render_template = orig
        self.assertIn('n_esperando', capt)
        self.assertIsInstance(capt['n_esperando'], int)


if __name__ == '__main__':
    unittest.main()


class CriarEstiloNovo(unittest.TestCase):
    """"Criar este estilo novo": nome que já existe nunca sequestra o formato pronto; o novo nasce escondido."""

    def test_nome_existente_ganha_sufixo_e_nasce_oculto(self):
        import tempfile
        from unittest.mock import patch
        import servidor
        import estilo_ref
        tmp = Path(tempfile.mkdtemp())
        criados = []

        def novo(slug, titulo=''):
            d = tmp / slug
            d.mkdir()
            (d / 'formato.json').write_text('{"slug": "%s"}' % slug, encoding='utf-8')
            criados.append(slug)
            return d

        pronto = {'slug': 'fala-com-cenas'}
        with patch.object(estilo_ref, 'estado', return_value={'origem': 'x.mp4', 'estado': 'pronto'}), \
             patch.object(formatos, 'carregar', side_effect=lambda s: pronto if s == 'fala-com-cenas' else None), \
             patch.object(formatos, 'novo_formato', side_effect=novo), \
             patch.object(estilo_ref, 'confirmar', return_value={'ok': True, 'formato': 'x'}) as conf:
            r = servidor.app.test_client().post('/referencia-rapida/abc/criar-estilo', data={'nome': 'Fala com cenas'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(criados, ['fala-com-cenas-2'])
        self.assertEqual(conf.call_args[0][1], 'fala-com-cenas-2')
        self.assertTrue(formatos.ler_json(tmp / 'fala-com-cenas-2' / 'formato.json')['oculto'])
