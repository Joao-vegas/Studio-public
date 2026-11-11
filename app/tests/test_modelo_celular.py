"""Ficha do modelo no celular: caminho longo em <code> quebra a linha, sem rolagem lateral (30-out-2026)."""
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "interface/static/simples.css"


class ModeloCelular(unittest.TestCase):
    def test_code_quebra_linha(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("#modelo code,.s-main code{overflow-wrap:anywhere", css)
        self.assertIn("\ncode{overflow-wrap:anywhere}", css)

    def test_ficha_nao_abre_rolagem_lateral_a_390px(self):
        """Mede no navegador de verdade (Playwright do próprio Estúdio), se o app estiver no ar; senão pula."""
        import socket
        try:
            socket.create_connection(("127.0.0.1", 7655), 1).close()
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("app fora do ar ou sem Playwright")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 390, "height": 800})
            pg.goto("http://127.0.0.1:7655/cliente/Joao/modelo/faixa-com-cenas")
            pg.evaluate("document.querySelector('#modelo code, .s-main code').textContent='clientes/Joao/vegasContent/modelos/faixa-com-cenas/_sandbox-um-nome-bem-comprido-sem-espaco-nenhum-que-estoura/work/gerado/leg-peito/arquivo.png'")
            largura = pg.evaluate("document.documentElement.scrollWidth")
            b.close()
        self.assertLessEqual(largura, 390)


if __name__ == "__main__":
    unittest.main()
