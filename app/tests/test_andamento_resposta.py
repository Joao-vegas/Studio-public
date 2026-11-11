"""Aba Em andamento: resposta do João (aprovar / pedir ajuste) e barra de etapas que não regride. Nada dispara processo de verdade."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import _comum
import andamento as A


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        (raiz / "formatos" / "dialogo-3d" / "aprendizado").mkdir(parents=True)
        self.raiz = raiz
        self.hist = raiz / "formatos" / "dialogo-3d" / "aprendizado" / "historico.jsonl"
        for alvo, valor in (("andamento.RAIZ", raiz), ("_comum.RAIZ", raiz), ("_comum.ESTUDIO", raiz / "app")):
            m, a = alvo.split(".")
            p = patch.object(sys.modules[m], a, valor)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def linhas(self):
        return [json.loads(x) for x in self.hist.read_text().splitlines()] if self.hist.exists() else []


class BannerEspera(Base):
    def test_nota_ou_aprendido_depois_da_espera_nao_troca_o_banner(self):
        A.espera("Joao", "ep", "Storyboard pronto: aprove ou peça ajuste", formato="dialogo-3d", titulo="Ep", imagem="x.jpg")
        A.nota("Joao", "ep", "Aprendido: a legenda fica abaixo do queixo.")
        A.passo("Joao", "ep", "Aprendido: sombra na legenda.")
        d = A.carregar("Joao", "ep")
        self.assertEqual(d["estado"], "esperando")
        self.assertEqual(d["atual"]["texto"], "Storyboard pronto: aprove ou peça ajuste")
        self.assertEqual(d["etapa"], "aprovacao")
        self.assertEqual([p["texto"][:9] for p in d["passos"]], ["Storyboar", "Aprendido", "Aprendido"])

    def test_passo_normal_depois_da_espera_volta_a_trabalhar(self):
        A.espera("Joao", "ep", "Storyboard pronto", formato="dialogo-3d", titulo="Ep")
        A.passo("Joao", "ep", "Renderizando o vídeo final")
        d = A.carregar("Joao", "ep")
        self.assertEqual((d["estado"], d["atual"]["texto"]), ("trabalhando", "Renderizando o vídeo final"))


class Responder(Base):
    def setUp(self):
        super().setUp()
        A.espera("Joao", "ep", "Storyboard pronto", formato="dialogo-3d", titulo="Ep")

    def test_ajustar_grava_resposta_e_historico_com_referencia(self):
        d, i = A.responder("Joao", "ep", "ajustar", "  fala rápida no segundo 12 ", ref="formatos/dialogo-3d/estudos/x.mp4", segundo="12.34")
        self.assertEqual(i, 0)
        r = d["respostas"][0]
        self.assertEqual((r["decisao"], r["texto"], r["status"], r["segundo"], r["etapa_no_momento"]),
                         ("ajustar", "fala rápida no segundo 12", "enviado", 12.3, "aprovacao"))
        h = self.linhas()[0]
        self.assertEqual((h["tipo"], h["categoria"], h["origem"]), ("feedback", "geral", "usuario"))
        self.assertEqual(h["referencia"], {"ref": "formatos/dialogo-3d/estudos/x.mp4", "segundo": 12.3})

    def test_ajustar_sem_texto_e_decisao_invalida_falham(self):
        with self.assertRaises(ValueError):
            A.responder("Joao", "ep", "ajustar", "  ")
        with self.assertRaises(ValueError):
            A.responder("Joao", "ep", "talvez", "x")
        self.assertEqual(self.linhas(), [])

    def test_aprovar_vira_aprovacao_sem_referencia(self):
        A.responder("Joao", "ep", "aprovar")
        h = self.linhas()[0]
        self.assertEqual(h["tipo"], "aprovacao")
        self.assertNotIn("referencia", h)

    def test_marcar_resposta_e_bloqueio_enquanto_aplica(self):
        _, i = A.responder("Joao", "ep", "ajustar", "mais devagar")
        self.assertTrue(A.marcar_resposta("Joao", "ep", i, "aplicando"))
        self.assertTrue(A.carregar("Joao", "ep")["aplicando"])
        with self.assertRaises(ValueError):
            A.responder("Joao", "ep", "aprovar")
        A.marcar_resposta("Joao", "ep", i, "feito")
        self.assertFalse(A.carregar("Joao", "ep")["aplicando"])
        A.responder("Joao", "ep", "aprovar")
        self.assertFalse(A.marcar_resposta("Joao", "ep", 99, "feito"))

    def test_aplicando_velho_nao_trava(self):
        _, i = A.responder("Joao", "ep", "ajustar", "mais devagar")
        A.marcar_resposta("Joao", "ep", i, "aplicando")
        p = A._arq("Joao", "ep")
        d = json.loads(p.read_text())
        d["respostas"][0]["em"] = "2020-01-01 10:00:00"
        p.write_text(json.dumps(d))
        A.responder("Joao", "ep", "aprovar")

    def test_formato_sem_pasta_de_aprendizado_so_registra_no_andamento(self):
        A.espera("Joao", "outro", "pronto?", formato="nao-existe")
        A.responder("Joao", "outro", "ajustar", "x")
        self.assertEqual(self.linhas(), [])

    def test_pasta_gravada_como_relativa_e_nota_nao_muda_estado(self):
        (self.raiz / "clientes" / "Joao" / "ep").mkdir(parents=True)
        d = A.passo("Joao", "ep", "Montando", pasta=self.raiz / "clientes" / "Joao" / "ep")
        self.assertEqual(d["pasta"], "clientes/Joao/ep")
        A.espera("Joao", "ep", "Storyboard pronto")
        d = A.nota("Joao", "ep", "Aprendido: x")
        self.assertEqual((d["estado"], d["passos"][-1]["texto"], d["passos"][-1]["estado"]), ("esperando", "Aprendido: x", "feito"))
        self.assertEqual(d["passos"][-2]["estado"], "esperando")


class Rota(Base):
    def setUp(self):
        super().setUp()
        import servidor   # o app real: a página usa o base.html completo
        import andamento_rotas as R
        self.R = R
        self.c = servidor.app.test_client()
        self.pasta = self.raiz / "clientes" / "Joao" / "vegasContent" / "output" / "dialogo-3d" / "ep"
        self.pasta.mkdir(parents=True)
        (self.pasta / "episodio.json").write_text("{}")
        self.chamadas = []
        p = patch.object(R, "ajustar_storyboard_da_tela", lambda *a: self.chamadas.append(a) or False)
        p.start()
        self.addCleanup(p.stop)

    def post(self, **dados):
        return self.c.post("/andamento/Joao/ep/responder", data=dados)

    def test_aprovar_video_pronto_so_registra(self):
        A.pronto("Joao", "ep", formato="dialogo-3d", pasta=self.pasta)
        self.post(decisao="aprovar")
        self.assertEqual(self.chamadas, [])
        self.assertEqual(A.carregar("Joao", "ep")["respostas"][0]["status"], "feito")
        self.assertEqual(self.linhas()[0]["tipo"], "aprovacao")

    def test_ajustar_sem_texto_nao_dispara(self):
        A.espera("Joao", "ep", "Storyboard pronto", formato="dialogo-3d", pasta=self.pasta)
        self.post(decisao="ajustar", texto="")
        self.assertEqual(self.chamadas, [])
        self.assertNotIn("respostas", json.loads(A._arq("Joao", "ep").read_text()))

    def test_outro_formato_so_anota(self):
        A.pronto("Joao", "ep", formato="fala-com-cenas")
        self.post(decisao="ajustar", texto="x")
        self.assertEqual(self.chamadas, [])
        self.assertEqual(A.carregar("Joao", "ep")["respostas"][0]["status"], "feito")

    def test_nao_aceita_resposta_enquanto_aplica_nem_enquanto_trabalha(self):
        A.espera("Joao", "ep", "Storyboard pronto", formato="dialogo-3d", pasta=self.pasta)
        self.post(decisao="ajustar", texto="a")
        A.marcar_resposta("Joao", "ep", 0, "aplicando")
        self.post(decisao="ajustar", texto="b")
        self.assertEqual(len(A.carregar("Joao", "ep")["respostas"]), 1)
        A.passo("Joao", "ep", "Montando")
        A.marcar_resposta("Joao", "ep", 0, "feito")
        self.post(decisao="aprovar")
        self.assertEqual(len(A.carregar("Joao", "ep")["respostas"]), 1)

    def test_pagina_mostra_cartao_so_quando_pode_responder(self):
        A.espera("Joao", "ep", "Storyboard pronto", formato="dialogo-3d", pasta=self.pasta)
        html = self.c.get("/andamento/Joao/ep").get_data(as_text=True)
        self.assertIn("O storyboard ficou bom?", html)
        self.assertNotRegex(html, r'id="and-resp"[^>]*hidden')
        A.passo("Joao", "ep", "Montando")
        html = self.c.get("/andamento/Joao/ep").get_data(as_text=True)
        self.assertRegex(html, r'id="and-resp"[^>]*hidden')


class BarraNaoVolta(Base):
    def test_etapa_menor_no_meio_da_rodada_nao_regride(self):
        A.passo("Cliente4", "v", "Produzindo o vídeo final", etapa="video")
        d = A.passo("Cliente4", "v", "Lendo as regras do formato", etapa="preparar")
        self.assertEqual(d["etapa"], "video")
        self.assertEqual(d["passos"][-1]["texto"], "Lendo as regras do formato")
        self.assertEqual(d["passos"][-1]["etapa"], "video")

    def test_avanca_normalmente(self):
        A.passo("Cliente4", "v", "a", etapa="preparar")
        self.assertEqual(A.passo("Cliente4", "v", "b", etapa="video")["etapa"], "video")

    def test_recomeco_depois_de_pronto_ou_erro_volta(self):
        A.pronto("Cliente4", "v")
        self.assertEqual(A.passo("Cliente4", "v", "de novo", etapa="preparar")["etapa"], "preparar")
        A.passo("Cliente4", "v", "x", etapa="video")
        A.erro("Cliente4", "v", "quebrou")
        self.assertEqual(A.passo("Cliente4", "v", "de novo", etapa="storyboard")["etapa"], "storyboard")

    def test_ajuste_depois_de_esperando_pode_voltar_ao_storyboard(self):
        A.espera("Cliente4", "v", "Storyboard pronto")
        self.assertEqual(A.passo("Cliente4", "v", "Ajustando", etapa="storyboard")["etapa"], "storyboard")


if __name__ == "__main__":
    unittest.main()
