"""Camada de tela inteira no motor HTML (30-out-2026): o grão do Editorial era um <canvas> de 1/3 do tamanho com só
`inset: 0`, e canvas não estica com inset: o grão ficou num retângulo no canto de cima à esquerda (mancha cinza no fundo
liso da cena de ícone, visto pelo João no blockbuster-e-a-netflix). Todo canvas posto em cima do quadro inteiro tem de
declarar width e height 100%."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _regra(css: str, id_: str) -> str:
    m = re.search(r"#" + re.escape(id_) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def _canvas_sem_esticar(html: str) -> list[str]:
    """ids de <canvas> com regra `inset: 0` (camada da tela inteira) sem width/height 100%."""
    ruins = []
    for id_ in re.findall(r"<canvas[^>]*\bid=\"([^\"]+)\"", html):
        r = _regra(html, id_)
        if re.search(r"\binset:\s*0\b", r) and not (re.search(r"\bwidth:\s*100%", r) and re.search(r"\bheight:\s*100%", r)):
            ruins.append(id_)
    return ruins


class GraoTelaInteira(unittest.TestCase):
    def test_canvas_de_tela_inteira_estica_nos_motores(self):
        for f in sorted((RAIZ / "formatos").glob("*/base/**/*.html")):
            with self.subTest(arquivo=str(f.relative_to(RAIZ))):
                self.assertEqual(_canvas_sem_esticar(f.read_text(encoding="utf-8", errors="ignore")), [])

    def test_copia_do_motor_nos_clientes_tambem(self):
        for f in sorted((RAIZ / "clientes").glob("*/*Content/modelos/*/index.html")):
            with self.subTest(arquivo=str(f.relative_to(RAIZ))):
                self.assertEqual(_canvas_sem_esticar(f.read_text(encoding="utf-8", errors="ignore")), [])

    def test_a_checagem_pega_o_erro_de_antes(self):
        antes = '<style>#grao { position: absolute; inset: 0; z-index: 30; }</style><canvas id="grao"></canvas>'
        depois = '<style>#grao { position: absolute; inset: 0; width: 100%; height: 100%; }</style><canvas id="grao"></canvas>'
        self.assertEqual(_canvas_sem_esticar(antes), ["grao"])
        self.assertEqual(_canvas_sem_esticar(depois), [])


if __name__ == "__main__":
    unittest.main()
