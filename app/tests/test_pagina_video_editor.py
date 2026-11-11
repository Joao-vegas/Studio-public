"""Página do vídeo pronto (Em andamento): editor por cena primeiro, "Aprovado — e agora?", desfazer aprovação e o miolo do editor
num parcial só. Nada dispara processo de verdade."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import andamento as A
import test_andamento_resposta as T

TEMPLATES = Path(__file__).resolve().parents[1] / "interface" / "templates"
CTX = dict(pasta_ed="clientes/Joao/vegasContent/modelos/m/_sandbox-ep", titulo="Ep", cenas=[], video="", sugestoes=[], tem_material=False,
           tem_gerar=False, tem_narracao=False, modelos=[("", "Sonnet")], esforcos=[("", "Alto")], versoes=[], estado={"rodando": False},
           narr={}, vozes=[], etapas=[], musica={"pode": False})


class UmMioloSo(unittest.TestCase):
    def test_editor_e_pagina_do_video_usam_o_mesmo_parcial(self):
        miolo = (TEMPLATES / "_editor_miolo.html").read_text(encoding="utf-8")
        for pag in ("editor.html", "andamento_ver.html"):
            self.assertIn('{% include "_editor_miolo.html" %}', (TEMPLATES / pag).read_text(encoding="utf-8"), pag)
        self.assertIn("var PASTA = {{ pasta_ed|tojson }}", miolo)
        self.assertNotIn("var PASTA", (TEMPLATES / "editor.html").read_text(encoding="utf-8"))   # sem JS duplicado
        self.assertIn("window.editorFocar", miolo)


class Desfazer(T.Base):
    def test_desfazer_aprovacao_volta_pro_ficou_bom(self):
        A.pronto("Joao", "ep", formato="fala-com-cenas", video="x.mp4")
        self.assertFalse(A.desfazer_aprovacao("Joao", "ep"))   # nada aprovado ainda
        A.responder("Joao", "ep", "aprovar", "")
        self.assertTrue(A.aprovado_em(A.carregar("Joao", "ep")))
        self.assertEqual(A.listar(), [])   # aprovado sai do Em andamento
        self.assertTrue(A.desfazer_aprovacao("Joao", "ep"))
        d = A.carregar("Joao", "ep")
        self.assertEqual(A.aprovado_em(d), "")
        self.assertTrue(d["respostas"][-1]["desfeita"])   # a resposta fica no registro, só marcada
        self.assertEqual([x["slug"] for x in A.listar()], ["ep"])
        self.assertFalse(A.desfazer_aprovacao("Joao", "ep"))


class Pagina(T.Base):
    def setUp(self):
        super().setUp()
        import servidor
        import andamento_rotas as R
        import editor as ED
        self.c = servidor.app.test_client()
        self.pasta = self.raiz / "clientes" / "Joao" / "vegasContent" / "modelos" / "m" / "_sandbox-ep"
        self.pasta.mkdir(parents=True)
        p = patch.object(ED, "pasta", lambda rel: self.pasta if rel else None); p.start(); self.addCleanup(p.stop)
        p = patch.dict(servidor.app.config, {"contexto_editor": lambda pe: dict(CTX)}); p.start(); self.addCleanup(p.stop)
        p = patch.object(sys.modules["producao"], "reconciliar", lambda *a, **k: 0); p.start(); self.addCleanup(p.stop)
        p = patch.object(sys.modules["producao"], "carregar", lambda *a, **k: {}); p.start(); self.addCleanup(p.stop)
        p = patch.object(A, "_avisos_do_video", lambda *a, **k: []); p.start(); self.addCleanup(p.stop)   # sem conferência de arquivo de verdade
        self.pagina = lambda: self.c.get("/andamento/Joao/ep").get_data(as_text=True)

    def pronto(self):
        (self.raiz / "clientes" / "Joao" / "ep.mp4").write_bytes(b"x")
        A.pronto("Joao", "ep", formato="fala-com-cenas", video=str(self.raiz / "clientes" / "Joao" / "ep.mp4"), pasta=self.pasta, titulo="Ep")

    def test_video_pronto_abre_no_editor_com_decisao_no_topo(self):
        self.pronto()
        h = self.pagina()
        self.assertIn('id="pv-decisao"', h)
        self.assertIn('id="ev-claude"', h)          # o painel do editor
        self.assertIn('id="ev-linha"', h)           # a tira de cenas
        self.assertIn('id="pv-quero"', h)
        self.assertNotIn('id="and-resp"', h)        # o cartão antigo some
        self.assertLess(h.index('id="pv-decisao"'), h.index('id="ev-claude"'))
        self.assertLess(h.index('id="ev-claude"'), h.index('id="pv-como"'))   # "Como foi feito" fica no fim
        como = h[h.index('id="pv-como"'):]
        self.assertNotIn("<details class=\"cartao-config pv-como\" id=\"pv-como\" open", h)
        self.assertIn("Passo a passo", como)
        self.assertNotIn("<h2>Vídeo</h2>", h)       # só um player: o do editor

    def test_aprovado_mostra_e_agora_com_cada_acao_e_desfaz(self):
        self.pronto()
        A.responder("Joao", "ep", "aprovar", "")
        h = self.pagina()
        self.assertIn("Aprovado ✓ — e agora?", h)
        for txt in ("Baixar o vídeo", "Mostrar no Finder", "Guardar no iCloud", "Usar como referência do estilo", "Liberar espaço deste vídeo", "Desfazer aprovação"):
            self.assertIn(txt, h, txt)
        self.assertNotIn('id="pv-decisao"', h)
        r = self.c.post("/andamento/Joao/ep/desfazer-aprovacao")
        self.assertEqual(r.status_code, 302)
        h = self.pagina()
        self.assertIn('id="pv-decisao"', h)
        self.assertNotIn("Aprovado ✓ — e agora?", h)

    def test_sem_editor_com_motivo_mostra_o_motivo_e_o_fluxo_de_hoje(self):
        self.pronto()
        with patch.object(sys.modules["editor"], "pasta", lambda rel: None), \
                patch.object(sys.modules["editor"], "motivo_sem_edicao", lambda p: "Este estilo ainda não tem edição por cena."):
            h = self.pagina()
        self.assertIn("Este estilo ainda não tem edição por cena.", h)
        self.assertIn('id="and-resp"', h)
        self.assertNotIn('id="pv-decisao"', h)

    def test_em_producao_mantem_a_tela_de_hoje(self):
        A.passo("Joao", "ep", "Montando o vídeo", formato="fala-com-cenas", titulo="Ep", pasta=self.pasta)
        h = self.pagina()
        self.assertNotIn('id="pv-decisao"', h)
        self.assertNotIn('id="ev-claude"', h)
        self.assertIn('id="and-vivo"', h)
        self.assertIn("Passo a passo", h)


if __name__ == "__main__":
    unittest.main()
