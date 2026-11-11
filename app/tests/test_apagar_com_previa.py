"""Ver antes de apagar: o painel "o que vai pra Lixeira" lista tudo com miniatura, tamanho, o que é e "Mostrar no Finder".
Só olha (nada é movido), só serve/abre o que está dentro do Estúdio, e todo Apagar usa o mesmo painel."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import espaco as E
import test_espaco as TE

INTERFACE = Path(__file__).resolve().parents[1] / "interface"


class Previa(TE.Base):
    def test_lista_tudo_do_video_com_tamanho_explicacao_e_miniatura_e_nao_move_nada(self):
        sb, mp4, jd = self.video("v1")
        r = E.previa(videos=["Joao/v1"])
        self.assertTrue(r["ok"])
        itens = [i for g in r["grupos"] for i in g["itens"]]
        por_nome = {i["nome"]: i for i in itens}
        self.assertIn("v1.mp4", por_nome)
        pronto = por_nome["v1.mp4"]
        self.assertEqual((pronto["kind"], pronto["bytes"]), ("video", 4_000_000))
        self.assertIn("vídeo pronto", pronto["explica"].lower())
        rasc = por_nome[sb.name]                                   # o rascunho: pasta com o bruto e o trabalho dentro, pra assistir
        self.assertEqual(rasc["kind"], "pasta")
        self.assertTrue(any(d["kind"] == "video" and d["caminho"].endswith(".mp4") for d in rasc["dentro"]))
        self.assertGreater(rasc["n_arquivos"], 3)
        for i in itens:
            self.assertTrue(i["explica"] and i["tamanho"] and i["rotulo"], i)
            self.assertFalse(Path(i["caminho"]).is_absolute())
        self.assertEqual(r["bytes"], sum(i["bytes"] for i in itens))
        for p in (sb, mp4, jd):                                    # só olhou
            self.assertTrue(p.exists())
        self.assertFalse(self.lixo.exists())

    def test_gravacao_enviada_e_explicada(self):
        self.video("v2")
        up = self.raiz / "app" / ".uploads"
        up.mkdir(parents=True)
        (up / "b.mp4").write_bytes(b"b" * 3_000_000)
        TE.velho(up)
        r = E.previa(videos=["Joao/v2"])
        textos = [i["explica"] for g in r["grupos"] for i in g["itens"]]
        self.assertTrue(any("gravação que você enviou" in t for t in textos))

    def test_arquivo_solto_musica_tem_play_e_explicacao(self):
        m = self.raiz / "acervo" / "itens" / "som" / "m.mp3"
        m.parent.mkdir(parents=True)
        m.write_bytes(b"m" * 2000)
        r = E.previa(musicas=["acervo/itens/som/m.mp3"])
        i = r["grupos"][0]["itens"][0]
        self.assertEqual((i["kind"], i["rotulo"]), ("audio", "Música"))
        self.assertIn("Lixeira", i["explica"])
        r2 = E.previa(arquivos=["acervo/itens/som/m.mp3"], explica="Efeito sonoro do acervo.")
        self.assertEqual(r2["grupos"][0]["itens"][0]["explica"], "Efeito sonoro do acervo.")

    def test_grupos_montados_pela_tela_juntam_o_mesmo_video_e_levam_o_aviso(self):
        sb, _, _ = self.video("v3")
        g = [{"titulo": "V3", "rotulo": "A gravação original", "explica": "x", "aviso": "Confira.", "caminhos": [str((sb / "bruto").relative_to(self.raiz))]},
             {"titulo": "V3", "rotulo": "Quadros", "explica": "y", "caminhos": [str((sb / "quadros").relative_to(self.raiz))]}]
        r = E.previa(grupos=g)
        self.assertEqual(len(r["grupos"]), 1)
        self.assertEqual([i["rotulo"] for i in r["grupos"][0]["itens"]], ["A gravação original", "Quadros"])
        self.assertEqual(r["grupos"][0]["itens"][0]["aviso"], "Confira.")

    def test_caminho_de_fora_ou_que_sumiu_nao_entra(self):
        fora = Path(self.tmp.name).parent / "fora.mp4"
        r = E.previa(arquivos=[str(fora), "nao/existe.mp4", "../fora.mp4"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["n"], 0)

    def test_liberar_espaco_explica_cada_item_em_portugues(self):
        self.video("v4")
        x = E.itens_liberaveis()
        itens = [i for g in x["grupos"] for v in g["videos"] for i in v["itens"]]
        bruto = next(i for i in itens if i["tipo"] == "bruto")
        self.assertIn("gravação original", bruto["explica"])
        self.assertIn("vídeo pronto continua", bruto["explica"])
        self.assertTrue(all(i["explica"] for i in itens))


class DentroDoEstudio(TE.Base):
    def test_aceita_relativo_e_absoluto_de_dentro(self):
        f = self.raiz / "acervo" / "a.mp4"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"x")
        self.assertEqual(E.dentro_do_estudio("acervo/a.mp4"), f.resolve())
        self.assertEqual(E.dentro_do_estudio(str(f)), f.resolve())

    def test_recusa_ponto_ponto_fora_vazio_e_atalho_pra_fora(self):
        (self.raiz / "acervo").mkdir()
        fora = Path(self.tmp.name).parent / "segredo.mp4"
        fora.write_bytes(b"s")
        self.addCleanup(lambda: fora.unlink() if fora.exists() else None)
        (self.raiz / "acervo" / "atalho.mp4").symlink_to(fora)
        for ruim in ("acervo/../../segredo.mp4", "../segredo.mp4", str(fora), "", "   ", "/etc/hosts", "acervo/atalho.mp4", "acervo/nao-existe.mp4"):
            with self.assertRaises(ValueError, msg=ruim):
                E.dentro_do_estudio(ruim)


class Rotas(TE.Base):
    def setUp(self):
        super().setUp()
        import servidor
        self.c = servidor.app.test_client()

    def test_mostrar_no_finder_roda_open_R_so_dentro_do_estudio(self):
        f = self.raiz / "acervo" / "a.mp4"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"x")
        with patch.object(E.subprocess, "run") as run:
            r = self.c.post("/espaco/finder", data={"caminho": "acervo/a.mp4"})
            self.assertEqual((r.status_code, r.get_json()["ok"]), (200, True))
            self.assertEqual(run.call_args[0][0], ["open", "-R", str(f.resolve())])

    def test_mostrar_no_finder_recusa_de_fora(self):
        fora = Path(self.tmp.name).parent / "fora.txt"
        fora.write_text("x")
        self.addCleanup(lambda: fora.unlink() if fora.exists() else None)
        with patch.object(E.subprocess, "run") as run:
            for ruim in (str(fora), "../fora.txt", "/etc/hosts", "acervo/../../fora.txt", ""):
                r = self.c.post("/espaco/finder", data={"caminho": ruim})
                self.assertEqual(r.status_code, 400, ruim)
                self.assertFalse(r.get_json()["ok"])
            run.assert_not_called()
            # um caminho ruim no meio recusa o pedido inteiro: nada abre
            (self.raiz / "acervo").mkdir()
            (self.raiz / "acervo" / "ok.mp4").write_bytes(b"x")
            r = self.c.post("/espaco/finder", data={"caminho": ["acervo/ok.mp4", "/etc/hosts"]})
            self.assertEqual(r.status_code, 400)
            run.assert_not_called()

    def test_arquivo_serve_so_midia_de_dentro(self):
        (self.raiz / "acervo").mkdir()
        (self.raiz / "acervo" / "a.mp4").write_bytes(b"v" * 5000)
        (self.raiz / "acervo" / "dados.json").write_text("{}")
        (self.raiz / "app").mkdir(exist_ok=True)
        (self.raiz / "app" / ".env").write_text("CHAVE=1")
        r = self.c.get("/espaco/arquivo?c=acervo/a.mp4", headers={"Range": "bytes=0-99"})
        self.assertEqual((r.status_code, len(r.data)), (206, 100))        # o vídeo toca e pula (Range)
        for ruim in ("acervo/dados.json", "app/.env", "../x.mp4", "/etc/hosts", "acervo", ""):
            self.assertEqual(self.c.get("/espaco/arquivo", query_string={"c": ruim}).status_code, 404, ruim)

    def test_previa_por_video_e_por_arquivo_e_por_json(self):
        self.video("v5")
        j = self.c.get("/espaco/previa?video=Joao/v5").get_json()
        self.assertTrue(j["ok"])
        self.assertTrue(j["grupos"][0]["itens"])
        (self.raiz / "acervo").mkdir(exist_ok=True)
        (self.raiz / "acervo" / "m.mp3").write_bytes(b"m")
        j = self.c.get("/espaco/previa", query_string={"arquivo": "acervo/m.mp3", "explica": "Música do acervo."}).get_json()
        self.assertEqual(j["grupos"][0]["itens"][0]["kind"], "audio")
        j = self.c.post("/espaco/previa", json={"grupos": [{"titulo": "T", "rotulo": "R", "explica": "E", "caminhos": ["acervo/m.mp3"]}]}).get_json()
        self.assertEqual(j["grupos"][0]["itens"][0]["rotulo"], "R")
        vazio = self.c.get("/espaco/previa?video=Joao/nao-existe").get_json()
        self.assertFalse(vazio["ok"])
        self.assertTrue(vazio["erro"])

    def test_previa_nunca_apaga(self):
        sb, mp4, jd = self.video("v6")
        self.c.get("/espaco/previa?video=Joao/v6")
        self.c.get("/espaco/previa?rascunho=" + str(sb.relative_to(self.raiz)))
        self.assertTrue(sb.exists() and mp4.exists() and jd.exists())

    def test_tela_liberar_espaco_tem_ver_e_finder_por_item(self):
        self.video("v7")
        h = self.c.get("/espaco").get_data(as_text=True)
        self.assertIn("data-ap-ver=", h)
        self.assertIn("data-ap-finder=", h)
        self.assertIn(">Ver</button>", h)
        self.assertIn("Mostrar no Finder", h)
        self.assertNotIn("confirm(", h)


class UmPainelSoEmTodoLugar(unittest.TestCase):
    def test_nenhum_apagar_de_video_usa_confirm_do_navegador(self):
        js = (INTERFACE / "static" / "studio.js").read_text()
        for marca in ("form[data-apagar]", "form[data-apagar-lote]"):
            trecho = js[js.index(marca):js.index(marca) + 1500]
            self.assertNotIn("confirm(", trecho.split("document.querySelectorAll('[data-marcar-todos]')")[0], marca)
        self.assertIn("data-apagar-previa", js)
        self.assertIn("EstudioApagar", js)
        self.assertIn("Mandar pra Lixeira", js)
        self.assertIn("Mostrar no Finder", js)

    def test_o_form_de_cada_apagar_chama_o_painel(self):
        t = INTERFACE / "templates"
        ui = (t / "_apagar_ui.html").read_text()
        self.assertIn("data-apagar-lote", ui)
        self.assertIn("macro apagar_form", ui)
        for nome in ("job.html", "corte_detalhe.html"):               # os que usavam o confirm com tamanho
            self.assertIn("data-apagar=", (t / nome).read_text(), nome)
        self.assertIn("EstudioApagar.abrir", (t / "espaco.html").read_text())

    def test_macro_apagar_form_para_usar_com_um_data(self):
        import servidor
        with servidor.app.test_request_context("/"):
            from flask import render_template_string
            h = render_template_string(
                '{% from "_apagar_ui.html" import apagar_form %}{{ apagar_form("/x/apagar", "/espaco/previa?arquivo=a.mp3&explica=Musica", "Apagar", {"id": "7"}) }}')
        self.assertIn('data-apagar-previa="/espaco/previa?arquivo=a.mp3&amp;explica=Musica"', h)
        self.assertIn('name="id" value="7"', h)


if __name__ == "__main__":
    unittest.main()
