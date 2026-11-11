"""Editar o vídeo por cena (PLANO-2.0 item 1): a IA só muda o alcance marcado; o resto volta sozinho."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import editor  # noqa: E402

DOC = {"duracao": 6, "palavras": "w.json", "cenas": [
    {"tipo": "foto", "de": 0, "imagem": "a.jpg", "mov": "in"},
    {"tipo": "texto", "de": 2, "texto": "Agora responde rápido:", "forte": ["rápido:"], "tempos": [2, 2.3, 2.7]},
    {"tipo": "foto", "de": 4, "imagem": "b.jpg", "texto": "oi"}]}


class Fiel(unittest.TestCase):
    def test_elemento_so_muda_o_campo_e_os_juntos(self):
        depois = json.loads(json.dumps(DOC))
        depois["cenas"][2].update(imagem="c.jpg", foco=[.3, .5], texto="mudou")
        depois["cenas"][0]["mov"] = "dir"
        ok, avisos = editor._fiel(DOC, depois, {"escopo": "elemento", "n": 3, "campo": "imagem"})
        self.assertEqual(ok["cenas"][2]["imagem"], "c.jpg")
        self.assertEqual(ok["cenas"][2]["foco"], [.3, .5])          # foco anda junto com a imagem
        self.assertEqual(ok["cenas"][2]["texto"], "oi")             # texto não foi marcado: volta
        self.assertEqual(ok["cenas"][0]["mov"], "in")               # outra cena: volta
        self.assertEqual(len(avisos), 2)

    def test_cena_nao_muda_o_tempo_da_fala(self):
        depois = json.loads(json.dumps(DOC))
        depois["cenas"][0].update(de=1.5, tipo="cartao")
        ok, _ = editor._fiel(DOC, depois, {"escopo": "cena", "n": 1, "campo": ""})
        self.assertEqual((ok["cenas"][0]["tipo"], ok["cenas"][0]["de"]), ("cartao", 0))

    def test_cena_apagada_nao_aceita(self):
        depois = dict(DOC, cenas=DOC["cenas"][:1])
        ok, avisos = editor._fiel(DOC, depois, {"escopo": "cena", "n": 3, "campo": ""})
        self.assertEqual(ok, DOC)
        self.assertTrue(avisos)


class Trecho(unittest.TestCase):
    def test_trecho_aceita_so_as_cenas_marcadas(self):
        depois = json.loads(json.dumps(DOC))
        depois["cenas"][0]["mov"] = "dir"
        depois["cenas"][1].update(texto="novo", de=9)
        depois["cenas"][2]["imagem"] = "z.jpg"
        ok, avisos = editor._fiel(DOC, depois, {"escopo": "trecho", "n": 2, "n_fim": 3})
        self.assertEqual(ok["cenas"][0]["mov"], "in")
        self.assertEqual((ok["cenas"][1]["texto"], ok["cenas"][1]["de"]), ("novo", 2))
        self.assertEqual(ok["cenas"][2]["imagem"], "z.jpg")
        self.assertTrue(avisos)


class Tempos(unittest.TestCase):
    def test_texto_novo_acende_na_palavra_falada(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "w.json").write_text(json.dumps({"words": [{"word": "Agora", "start": 2.0}, {"word": "responde", "start": 2.3},
                                                               {"word": "rápido:", "start": 2.7}]}))
            doc = json.loads(json.dumps(DOC))
            doc["cenas"][1]["texto"] = "Responde rápido:"
            editor._tempos(Path(d), doc)
            self.assertEqual(doc["cenas"][1]["tempos"], [2.3, 2.7])


class Alteracao(unittest.TestCase):
    def test_alteracao_e_sonnet_alto_salvo_escolha_do_pedido(self):
        import ia
        s = ia.para_alteracao({"provedor": "claude", "modelo": "opus", "esforco": "medium"})
        self.assertEqual((s["modelo"], s["esforco"]), ("sonnet", "high"))
        s = ia.para_alteracao({"provedor": "claude", "modelo": "opus"}, modelo="haiku", esforco="low")
        self.assertEqual((s["modelo"], s["esforco"]), ("haiku", "low"))


# ───────────────────────── Explicador 3D e Documentário: a camada por formato ─────────────────────────

EXPL = {"duracao": 6, "elenco": {"dentista": {"base": "dentista"}}, "mundos": {"cons": {"tipo": "consultorio", "gente": [
            {"quem": "dentista", "id": "dentista"}]}}, "cenas": [
    {"mundo": "cons", "de": 0, "fala": "Você é dentista", "palavras": [{"w": "Você", "s": 0, "e": .3}],
     "lugar": {"dentista": {"pos": [0, 0], "rosto": "feliz"}}, "cam": {"de": [0, 1, 2], "para": [0, 1, 1.8], "olha": [0, 1, 0], "fov": 44},
     "acoes": [{"quem": "dentista", "em": .4, "rosto": "presuncoso"}]},
    {"mundo": "cons", "de": 2, "fala": "e todo mundo te conhece", "lugar": {"dentista": {"pos": [1, 0]}},
     "cam": {"de": [1, 1, 2], "para": [1, 1, 1.8], "olha": [1, 1, 0], "fov": 50}, "trans": "dissolve"},
    {"mundo": "cons", "de": 4, "fala": "mas ninguém chega", "lugar": {"dentista": {"pos": [2, 0]}},
     "cam": {"de": [2, 1, 2], "para": [2, 1, 1.8], "olha": [2, 1, 0], "fov": 50}}]}


def _copia(d):
    return json.loads(json.dumps(d))


class ExplicadorFiel(unittest.TestCase):
    J = editor.MOTORES["explicador-3d"]["juntos"]
    ADIT = editor.MOTORES["explicador-3d"]["aditivos"]

    def test_acao_so_muda_a_acao(self):
        depois = _copia(EXPL)
        depois["cenas"][0]["acoes"][0]["rosto"] = "surpreso"
        depois["cenas"][0]["cam"]["fov"] = 30                      # câmera não foi marcada: volta
        depois["cenas"][1]["acoes"] = [{"quem": "dentista", "em": .2, "pose": "acena"}]   # outra cena: volta
        ok, avisos = editor._fiel(EXPL, depois, {"escopo": "elemento", "n": 1, "campo": "acoes"}, self.J, self.ADIT)
        self.assertEqual(ok["cenas"][0]["acoes"][0]["rosto"], "surpreso")
        self.assertEqual(ok["cenas"][0]["cam"]["fov"], 44)
        self.assertNotIn("acoes", ok["cenas"][1])
        self.assertEqual(len(avisos), 2)

    def test_trocar_o_lugar_leva_junto_personagens_camera_e_acoes(self):
        depois = _copia(EXPL)
        depois["cenas"][1].update(mundo="cid", lugar={"dentista": {"pos": [9, 9]}}, cam={"de": [9, 1, 2], "para": [9, 1, 1], "olha": [9, 1, 0], "fov": 50},
                                  trans="corte")
        ok, _ = editor._fiel(EXPL, depois, {"escopo": "elemento", "n": 2, "campo": "mundo"}, self.J, self.ADIT)
        self.assertEqual((ok["cenas"][1]["mundo"], ok["cenas"][1]["lugar"]["dentista"]["pos"]), ("cid", [9, 9]))
        self.assertEqual(ok["cenas"][1]["trans"], "dissolve")      # a transição não anda com o lugar

    def test_fala_nunca_muda_nem_o_tempo(self):
        depois = _copia(EXPL)
        depois["cenas"][2].update(fala="outra coisa", de=3.2, trans="wipe")
        ok, _ = editor._fiel(EXPL, depois, {"escopo": "cena", "n": 3, "campo": ""}, self.J, self.ADIT)
        self.assertEqual(ok["cenas"][2]["de"], 4)
        self.assertEqual(ok["cenas"][2]["trans"], "wipe")           # na cena inteira vale o que ele mudou

    def test_personagem_novo_entra_mas_o_que_existe_nao_muda(self):
        depois = _copia(EXPL)
        depois["elenco"]["medica"] = {"base": "medica"}
        depois["elenco"]["dentista"] = {"base": "vovo"}             # mexeu no que já existia: não vale
        depois["mundos"]["cons"]["gente"].append({"quem": "medica", "id": "medica"})
        depois["cenas"][0]["lugar"]["medica"] = {"pos": [1, 1]}
        ok, avisos = editor._fiel(EXPL, depois, {"escopo": "elemento", "n": 1, "campo": "lugar"}, self.J, self.ADIT)
        self.assertEqual(ok["elenco"], {"dentista": {"base": "dentista"}, "medica": {"base": "medica"}})
        self.assertEqual([g["id"] for g in ok["mundos"]["cons"]["gente"]], ["dentista", "medica"])
        self.assertIn("medica", ok["cenas"][0]["lugar"])

    def test_mexer_no_elenco_sem_acrescentar_volta_e_avisa(self):
        depois = _copia(EXPL)
        depois["elenco"]["dentista"] = {"base": "vovo"}
        ok, avisos = editor._fiel(EXPL, depois, {"escopo": "cena", "n": 1, "campo": ""}, self.J, self.ADIT)
        self.assertEqual(ok["elenco"], EXPL["elenco"])
        self.assertTrue(any("elenco" in a for a in avisos))

    def test_video_todo_aceita_tudo(self):
        depois = _copia(EXPL)
        depois["elenco"]["dentista"] = {"base": "vovo"}
        ok, _ = editor._fiel(EXPL, depois, {"escopo": "video"}, self.J, self.ADIT)
        self.assertEqual(ok, depois)


class OutrosFormatos(unittest.TestCase):
    def _sandbox(self, raiz: Path, formato: str, doc: dict, render_na_pasta: bool) -> Path:
        p = raiz / "clientes" / "C" / "cContent" / "modelos" / formato / "_sandbox-x"
        p.mkdir(parents=True)
        (p / "cenas.json").write_text(json.dumps(doc), encoding="utf-8")
        if render_na_pasta:
            (p / "render.py").write_text("# aceita --quadro\n", encoding="utf-8")
        else:
            b = raiz / "formatos" / formato / "base"
            b.mkdir(parents=True)
            (b / "render.py").write_text("# aceita --quadro\n", encoding="utf-8")
        return p

    def test_lista_e_cenas_do_explicador_com_o_render_da_base(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz, "explicador-3d", dict(EXPL, titulo="Vídeo de teste"), render_na_pasta=False)
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: "explicador-3d"):
                vs = editor.videos()
                self.assertEqual([(v["titulo"], v["formato"]) for v in vs], [("Vídeo de teste", "explicador-3d")])
                self.assertIsNotNone(editor.pasta(editor.rel(p)))
                self.assertEqual(editor.render_de(p), raiz / "formatos" / "explicador-3d" / "base" / "render.py")
                cs = editor.cenas(p)
                self.assertEqual(cs[0]["tipo_rotulo"], "Consultório")
                self.assertEqual(cs[0]["fala"], "Você é dentista")
                self.assertEqual([e["rotulo"] for e in cs[0]["elementos"]], ["Lugar", "Personagens", "Ação", "Câmera"])
                self.assertIn("Ação", [e["rotulo"] for e in cs[1]["elementos"]])   # mesmo sem ter ação: dá pra pôr
                self.assertEqual([e["id"] for e in editor.etapas(p)], ["video"])
                self.assertFalse(editor.narracao(p)["pode"])
                self.assertIn("--cenas", editor._cmd(p)[1:][1])
                self.assertEqual(editor._cmd(p, "--quadro", "1")[-2:], ["--quadro", "1"])

    def test_documentario_usa_os_rotulos_dele(self):
        from unittest import mock
        doc = {"duracao": 6, "palavras": "w.json", "cenas": [{"tipo": "jornal", "de": 0, "nome": "Ana", "cargo": "Dona", "quadro_s": 1},
                                                           {"tipo": "frase", "de": 3, "destaque": ["lucro"]}]}
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz, "documentario", doc, render_na_pasta=True)
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: "documentario"):
                cs = editor.cenas(p)
                self.assertEqual((cs[0]["tipo_rotulo"], cs[1]["tipo_rotulo"]), ("Jornal", "Frase"))
                self.assertEqual([e["rotulo"] for e in cs[0]["elementos"]], ["Nome", "Cargo", "Quadro escolhido"])
                ok, _ = editor._fiel(doc, dict(doc, cenas=[dict(doc["cenas"][0], nome="Bia", cargo="X", quadro_s=2), doc["cenas"][1]]),
                                     {"escopo": "elemento", "n": 1, "campo": "nome"}, editor.spec(p)["juntos"])
                self.assertEqual((ok["cenas"][0]["nome"], ok["cenas"][0]["cargo"], ok["cenas"][0]["quadro_s"]), ("Bia", "X", 1))

    def test_pasta_sem_render_nem_base_nao_aparece(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = raiz / "clientes" / "C" / "cContent" / "modelos" / "explicador-3d" / "_sandbox-x"
            p.mkdir(parents=True)
            (p / "cenas.json").write_text(json.dumps(EXPL), encoding="utf-8")
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: "explicador-3d"):
                self.assertEqual(editor.videos(), [])
                self.assertIsNone(editor.pasta(editor.rel(p)))

    def test_formato_desconhecido_segue_como_o_editorial(self):
        from unittest import mock
        with mock.patch.object(editor, "formato_da_pasta", lambda q: "qualquer-outro"):
            self.assertIs(editor.spec(Path("/x")), editor.MOTORES["editorial"])


# ───────────────────────── gravado: Faixa com cenas (a cena é um trecho do PLANO.json) ─────────────────────────

PLANO = {"estilo": "gancho-legenda", "frase": "SABE AQUELA MÚSICA|QUE VOCÊ JÁ NÃO|AGUENTA MAIS?", "faixa_ate": 8.65,
         "janelas": [[0.0, 3.0, "S", "/a/um.mp4", 2], [3.0, 5.7, "C", "/a/dois.mp4", 1], [9.0, 12.0, "S", "/a/tres.mp4", 0.5]],
         "trocas": {"meta": "Meta"}, "pausas_cortadas": [[8.56, 8.91]]}


class FaixaComCenas(unittest.TestCase):
    def _sandbox(self, raiz: Path, plano=PLANO) -> Path:
        p = raiz / "clientes" / "C" / "cContent" / "modelos" / "faixa-com-cenas" / "_sandbox-x"
        (p / "work").mkdir(parents=True)
        (p / "PLANO.json").write_text(json.dumps(plano), encoding="utf-8")
        (p / "work" / "joao.mp4").write_bytes(b"")
        (p.parent / "gerar.py").write_text("", encoding="utf-8")
        return p

    def _ctx(self, raiz):
        from unittest import mock
        return (mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: "faixa-com-cenas"),
                mock.patch.object(editor, "_duracao_video", lambda f: 15.0))

    def test_ida_e_volta_do_plano_nao_muda_nada(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                doc = editor._doc(p)
                self.assertEqual([x["tipo"] for x in doc["cenas"]], ["dividido", "cheia", "joao", "dividido", "joao"])
                self.assertEqual([x["de"] for x in doc["cenas"]], [0, 3, 5.7, 9, 12])   # o que sobra entre as janelas e no fim é o João
                self.assertEqual(doc["duracao"], 15)
                editor._gravar(p, doc)
                self.assertEqual(json.loads((p / "PLANO.json").read_text(encoding="utf-8")), PLANO)

    def test_gravar_troca_tela_e_clipe_e_deixa_o_resto_do_plano(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                doc = editor._doc(p)
                doc["cenas"][1].update(tipo="dividido", clipe="/a/novo.mp4", inicio=4)
                doc["cenas"][2].update(tipo="cheia", clipe="/a/joao-no-meio.mp4")   # o João vira cena de tela cheia
                doc["cenas"][3]["tipo"] = "joao"                                    # e a janela 3 vira só o João
                doc["frase"] = "OUTRA|FRASE"
                editor._gravar(p, doc)
                novo = json.loads((p / "PLANO.json").read_text(encoding="utf-8"))
                self.assertEqual(novo["janelas"], [[0, 3, "S", "/a/um.mp4", 2], [3, 5.7, "S", "/a/novo.mp4", 4],
                                                   [5.7, 9, "C", "/a/joao-no-meio.mp4", 0]])
                self.assertEqual((novo["frase"], novo["trocas"], novo["faixa_ate"]), ("OUTRA|FRASE", {"meta": "Meta"}, 8.65))
                self.assertNotIn("cenas", novo)
                self.assertNotIn("duracao", novo)

    def test_elementos_e_miniatura_do_gravado(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                cs = editor.cenas(p)
                self.assertEqual((cs[0]["tipo_rotulo"], cs[1]["tipo_rotulo"], cs[2]["tipo_rotulo"]), ("Dividido", "Cena em tela cheia", "Só o João"))
                self.assertEqual([e["campo"] for e in cs[0]["elementos"]], ["tipo", "clipe", "inicio", "frase", "crop_y_fixo"])
                self.assertEqual([e["campo"] for e in cs[2]["elementos"]], ["tipo", "clipe", "frase", "crop_y_fixo"])   # cena só do João aceita clipe
                self.assertTrue(editor.pasta(editor.rel(p)))
                self.assertEqual(editor.fonte(p).name, "PLANO.json")
                self.assertEqual(len(editor.videos()), 1)

    def test_fiel_elemento_clipe_leva_o_ponto_do_clipe_e_nada_mais(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois["cenas"][1].update(clipe="/a/novo.mp4", inicio=7, tipo="dividido", de=4.4)
                depois["cenas"][0]["clipe"] = "/a/fora.mp4"
                depois["frase"] = "NÃO PODE"
                sp = editor.spec(p)
                ok, avisos = editor._fiel(antes, depois, {"escopo": "elemento", "n": 2, "campo": "clipe"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["cenas"][1]["clipe"], ok["cenas"][1]["inicio"]), ("/a/novo.mp4", 7))
                self.assertEqual((ok["cenas"][1]["tipo"], ok["cenas"][1]["de"]), ("cheia", 3))      # tela e tempo da fala não foram marcados
                self.assertEqual(ok["cenas"][0]["clipe"], "/a/um.mp4")                              # outra cena volta
                self.assertEqual(ok["frase"], PLANO["frase"])                                       # a frase é do topo: só no elemento "frase"
                self.assertTrue(avisos)

    def test_fiel_frase_so_aceita_a_frase(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois.update(frase="NOVA|FRASE", faixa_ate=99)
                depois["cenas"][0]["tipo"] = "cheia"
                sp = editor.spec(p)
                ok, avisos = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "frase"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["frase"], ok["faixa_ate"], ok["cenas"][0]["tipo"]), ("NOVA|FRASE", 8.65, "dividido"))
                self.assertTrue(avisos)
                # e o pedido de cena nunca mexe na frase
                ok, _ = editor._fiel(antes, depois, {"escopo": "cena", "n": 1, "campo": ""}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["frase"], ok["cenas"][0]["tipo"]), (PLANO["frase"], "cheia"))

    def test_fiel_tempo_da_fala_nao_muda_nem_no_video_todo(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois["cenas"][1].update(de=3.5, clipe="/a/x.mp4")
                ok, _ = editor._fiel(antes, depois, {"escopo": "video", "n": None, "campo": ""}, {}, (), {}, True)
                self.assertEqual((ok["cenas"][1]["de"], ok["cenas"][1]["clipe"]), (3, "/a/x.mp4"))
                ok, avisos = editor._fiel(antes, dict(depois, cenas=depois["cenas"][:2]), {"escopo": "video", "n": None, "campo": ""}, {}, (), {}, True)
                self.assertEqual((ok, bool(avisos)), (antes, True))

    def test_versao_guarda_o_plano_e_volta(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                v1 = editor.guardar_versao(p, "original")
                self.assertTrue((p / "editor" / "versoes" / v1 / "PLANO.json").is_file())
                doc = editor._doc(p)
                doc["frase"] = "MUDOU"
                editor._gravar(p, doc)
                editor.voltar(p, v1)
                self.assertEqual(json.loads((p / "PLANO.json").read_text(encoding="utf-8"))["frase"], PLANO["frase"])
                self.assertEqual(len(editor.versoes(p)), 2)   # nada apagado: a v1 continua e a volta virou v2

    def test_prompt_do_gravado_manda_editar_so_a_lista_de_cenas(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b, c = self._ctx(raiz)
            with a, b, c:
                t = editor.prompt(p, {"escopo": "elemento", "n": 1, "n_fim": None, "campo": "frase", "texto": "troca", "print": ""})
                self.assertIn("editor/cenas.json", t)
                self.assertIn("TOPO do arquivo", t)
                self.assertNotIn("render.py", t)


if __name__ == "__main__":
    unittest.main()
