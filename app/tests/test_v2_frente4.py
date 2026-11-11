"""Estúdio 2.0, Frente 4: visual único. CSS com um só :root, sem hex solto, menu lateral aberto em grupos, Início com 3 botões."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
STATIC = RAIZ / 'app' / 'interface' / 'static'
HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')


def _css(nome):
    return (STATIC / nome).read_text(encoding='utf-8')


class Css(unittest.TestCase):
    def test_um_so_root(self):
        self.assertEqual(len(re.findall(r':root', _css('estilo.css'))), 1)
        for n in ('simples.css', 'studio.css', 'briefing.css'):
            self.assertNotIn(':root', _css(n), n)

    def test_tema_escuro_so_no_estilo(self):
        self.assertIn('[data-theme=dark]', _css('estilo.css'))
        for n in ('simples.css', 'studio.css', 'briefing.css'):
            self.assertNotRegex(_css(n), r'\[data-theme=dark\]\s*\{', n)

    def test_sem_hex_solto_fora_do_estilo(self):
        for n in ('simples.css', 'studio.css', 'briefing.css'):
            self.assertEqual(HEX.findall(_css(n)), [], n)

    def test_variaveis_combinadas(self):
        css = _css('estilo.css')
        for v in ('--bg', '--painel', '--linha', '--txt', '--txt2', '--ac', '--ok', '--espera', '--erro', '--e1', '--e7', '--raio', '--sombra', '--t1', '--t4'):
            self.assertRegex(css, re.escape(v) + r'\s*:', v)
        self.assertIn('#e11d2a', css)
        self.assertIn('Inter', css)

    def test_componentes_combinados(self):
        css = _css('estilo.css')
        for c in ('.grade-cards', '.card-video', '.lado-a-lado', '.btn.grande', '.selo.ok', '.selo.espera', '.selo.erro', '.vazio', '.passo-dica'):
            self.assertIn(c, css, c)
        self.assertIn('minmax(220px', css)
        self.assertIn('min-height: 48px', css)


class Telas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from servidor import app
        app.testing = True
        cls.c = app.test_client()

    def test_telas_respondem_200_com_menu_novo(self):
        for rota in ('/', '/criar', '/formatos', '/andamento', '/videos', '/clientes', '/custos', '/referencias', '/lotes'):
            r = self.c.get(rota)
            self.assertEqual(r.status_code, 200, rota)
            h = r.get_data(as_text=True)
            for href in ('href="/criar-agora"', 'href="/aprovar"', 'href="/formatos"', 'href="/videos"', 'href="/clientes"', 'href="/referencias"', 'href="/custos"', 'href="/config"'):
                self.assertIn(href, h, f'{rota}: {href}')
            for nome in ('Início', 'Criar', 'Esperando você', 'Estilos', 'Meus vídeos', 'Clientes', 'Mais'):
                self.assertIn(nome, h, f'{rota}: {nome}')

    def test_menu_aberto_com_grupos_e_uma_linha_de_explicacao(self):
        """Respiro 3.0: acabou o "Mais" escondido: tudo à vista no menu lateral, em grupos, cada item com a linha que diz o que é."""
        h = self.c.get('/').get_data(as_text=True)
        menu = h[h.index('<aside'):h.index('</aside>')]
        self.assertNotIn('class="s-mais"', menu)
        self.assertNotIn('<script', menu)   # sem JS novo no menu
        for grupo in ('Criar', 'Meu trabalho', 'Ferramentas', 'Biblioteca', 'Conta'):
            self.assertIn(f'<p class="s-grupo-titulo">{grupo}</p>', menu, grupo)
        for nome, dica, href in (('Recortar vídeo', 'Tira silêncio e erro do bruto', '/cortes'),
                                 ('Referências', 'Jogue um vídeo', '/referencias'), ('Biblioteca', 'Músicas, efeitos e b-rolls', '/acervo'),
                                 ('Vozes', 'Ouvir e escolher a narração', '/vozes'),
                                 ('Em andamento', 'sendo feito', '/andamento'), ('Custos', 'Quanto cada vídeo gastou', '/custos'),
                                 ('Configurações', 'IA, voz', '/config')):
            self.assertIn(f'href="{href}"', menu, href)
            self.assertIn(f'<b>{nome}</b><small>', menu, nome)
            self.assertIn(dica, menu, dica)
        for saiu in ('/elenco', '/novo-lote', '/editar', '/melhorias'):   # menu enxuto (30-out): cada um tem outra porta
            self.assertNotIn(f'href="{saiu}"', menu, saiu)
        self.assertNotIn('Estudar um vídeo', menu)   # referências numa porta só
        self.assertNotIn('Jogar uma referência', menu)

    def test_inicio_tem_3_botoes(self):
        h = self.c.get('/').get_data(as_text=True)
        for href in ('/criar-agora', '/novo-lote', '/referencias#jogar'):
            self.assertRegex(h, r'class="botao-grande[^"]*" href="' + re.escape(href) + '"')

    def test_menu_marca_a_pagina_atual(self):
        h = self.c.get('/formatos').get_data(as_text=True)
        self.assertRegex(h, r'href="/formatos" class="s-item ativo"')


if __name__ == '__main__':
    unittest.main()
