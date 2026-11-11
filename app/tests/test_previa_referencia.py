"""Em andamento → "Quero alterar" → referências: miniatura toca prévia muda (mouse/toque), clique continua abrindo o player grande."""
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import _comum
import andamento as A

ESTATICO = Path(__file__).resolve().parents[1] / "interface" / "static"
REFS = [{"video": "formatos/dialogo-3d/exemplo-1.mp4", "nome": "Exemplo 1", "principal": True, "poster": ""},
        {"video": "formatos/dialogo-3d/exemplo-2.mp4", "nome": "Exemplo 2", "principal": False, "poster": ""}]


class PreviaReferencia(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name)
        (raiz / "formatos" / "dialogo-3d" / "aprendizado").mkdir(parents=True)
        for alvo, valor in (("andamento.RAIZ", raiz), ("_comum.RAIZ", raiz), ("_comum.ESTUDIO", raiz / "app")):
            m, a = alvo.split(".")
            p = patch.object(sys.modules[m], a, valor)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(A, "referencias", lambda formato: REFS)
        p.start()
        self.addCleanup(p.stop)
        import servidor
        A.espera("Joao", "ep", "Storyboard pronto", formato="dialogo-3d", titulo="Ep")
        self.html = servidor.app.test_client().get("/andamento/Joao/ep").get_data(as_text=True)

    def test_botoes_mantem_o_que_ja_existia(self):
        botoes = re.findall(r'<button[^>]*class="and-ref"[^>]*>', self.html)
        self.assertEqual(len(botoes), 2)
        for b, r in zip(botoes, REFS):
            self.assertIn('data-video="/arquivo/' + r["video"] + '"', b)
            self.assertIn('data-rel="' + r["video"] + '"', b)
        for ident in ('name="ref"', 'name="segundo"', 'id="and-marcar"', 'id="and-ref-limpa"'):
            self.assertIn(ident, self.html)

    def test_dica_e_script_da_previa_na_pagina(self):
        self.assertIn('class="and-ref-dica', self.html)
        self.assertIn('Passe o mouse em cima pra ver o vídeo', self.html)
        self.assertIn('previa-ref.js', self.html)

    def test_script_previa_e_muda_e_so_um_por_vez(self):
        js = (ESTATICO / "previa-ref.js").read_text()
        for trecho in ("v.muted = true", "v.loop = true", "v.playsInline = true", "v.preload = 'none'", "mouseover", "mouseout", "touchstart"):
            self.assertIn(trecho, js)
        self.assertEqual(js.count("function para()"), 1)   # toca() sempre para() a anterior antes de começar
        self.assertRegex(js, r"function toca\(b\) \{\s+if \(tocando === b\) return;\s+para\(\);")
        self.assertIn(".and-ref-previa", (ESTATICO / "simples.css").read_text())


if __name__ == "__main__":
    unittest.main()
