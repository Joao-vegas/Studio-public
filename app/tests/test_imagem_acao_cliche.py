"""G6 (30-out-2026): imagem clichê de banco, imagem quase igual (mesmo de arquivo diferente) e fala com ação sem vídeo da ação.
O CLIP é simulado (cor da imagem = vetor, frase = assunto): o teste não carrega modelo nenhum."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import casar_imagem as C

# vetor de cada "assunto" (8 dimensões): 0 câmera, 2 pessoa, 3 loja, 4 banco (foto posando), 5 real (notícia), 6 ruído do ângulo
def _n(v):
    v = np.array(v, dtype=float)
    return v / np.linalg.norm(v)


VEC = {
    "camera": _n([1, 0, 0, 0, 0, 0, 0, 0]),
    "camera_b": _n([1, 0, 0, 0, 0, 0, 0.45, 0]),    # o mesmo protótipo em outro quadro: cosseno 0,91 com "camera"
    "camera_c": _n([1, 0, 0, 0, 0, 0, 1.2, 0]),     # outro ângulo, outro contexto: cosseno 0,64
    "pessoa": _n([0, 0, 1, 0, 0, 0, 0, 0]),
    "loja": _n([0, 0, 0, 1, 0, 0, 0, 0]),
    "banco": _n([0, 0, 0, 0, 1, 0, 0, 0]),
    "real": _n([0, 0, 0, 0, 0, 1, 0, 0]),
    "meio": _n([0, 0, 0, 0, 0.7071 * 1.025, 0.7071 * 0.975, 0, 0]),   # margem ~0,035: só passa do limite com fonte de banco
}
COR = {k: (10 + 25 * i, 200 - 20 * i, 30 + 10 * i) for i, k in enumerate(VEC)}


def _emb_img(imgs):
    out = []
    for im in imgs:
        px = im.convert("RGB").getpixel((2, 2))
        out.append(VEC[min(COR, key=lambda k: sum((a - b) ** 2 for a, b in zip(COR[k], px)))])
    return np.array(out)


def _emb_txt(txts):
    out = []
    for t in txts:
        if t in C.CLICHE_NEG:
            out.append(VEC["banco"])
        elif t in C.CLICHE_POS:
            out.append(VEC["real"])
        else:
            tl = t.lower()
            nome = next((a for a, p in (("camera", "câmera"), ("loja", "loja"), ("pessoa", "engenheiro")) if p in tl), "pessoa")
            out.append(VEC[nome])
    return np.array(out)


def _foto(pasta: Path, nome: str, assunto: str) -> str:
    Image.new("RGB", (64, 64), COR[assunto]).save(pasta / nome)
    return nome


class Falso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        for alvo, f in (("_emb_imagens", _emb_img), ("_emb_textos", _emb_txt), ("_rosto", lambda im: None)):
            p = patch.object(C, alvo, f)
            p.start()
            self.addCleanup(p.stop)
        C._EMB.clear()
        C._TXT_CLICHE.clear()
        self.addCleanup(C._TXT_CLICHE.clear)

    def tearDown(self):
        self.tmp.cleanup()

    def _sandbox(self, cenas: list[dict], frases: list[tuple[str, float]]) -> Path:
        palavras = []
        for txt, t0 in frases:
            for i, w in enumerate(txt.split()):
                palavras.append({"word": w, "start": round(t0 + i * .3, 2), "end": round(t0 + i * .3 + .25, 2)})
        (self.pasta / "work").mkdir(exist_ok=True)
        (self.pasta / "work" / "words.json").write_text(json.dumps({"words": palavras}))
        (self.pasta / "cenas.json").write_text(json.dumps({"palavras": "work/words.json", "duracao": 40, "cenas": cenas}))
        return self.pasta


class TestCliche(Falso):
    def test_foto_de_banco_e_cliche_e_foto_real_nao(self):
        a, b = _foto(self.pasta, "pose.jpg", "banco"), _foto(self.pasta, "caso.jpg", "real")
        self.assertTrue(C.avaliar_cliche(self.pasta / a)["cliche"])
        r = C.avaliar_cliche(self.pasta / b)
        self.assertFalse(r["cliche"])
        self.assertLess(r["margem"], 0)

    def test_fonte_de_banco_soma_na_nota(self):
        m = _foto(self.pasta, "meio.jpg", "meio")
        sem = C.avaliar_cliche(self.pasta / m)
        com = C.avaliar_cliche(self.pasta / m, banco="pexels")
        self.assertFalse(sem["cliche"])           # 0,035 < 0,05
        self.assertTrue(com["cliche"])            # 0,035 + 0,02
        self.assertAlmostEqual(com["nota"] - sem["nota"], C.BONUS_BANCO, places=2)

    def test_fonte_banco_pelo_nome_pelo_origem_json_e_pela_cena(self):
        self.assertEqual(C.fonte_banco(self.pasta / "x-pexels-3.jpg"), "pexels")
        self.assertEqual(C.fonte_banco(self.pasta / "x.jpg", {"origem": "https://www.pixabay.com/x"}), "pixabay")
        (self.pasta / "origem.json").write_text(json.dumps({"aviso": [{"arquivo": "aviso.jpg", "pagina": "https://www.pexels.com/photo/a", "licenca": "Pexels License"}],
                                                          "reed": [{"arquivo": "reed.jpg", "pagina": "https://commons.wikimedia.org/x", "licenca": "CC BY"}]}))
        self.assertEqual(C.fonte_banco(self.pasta / "aviso.jpg"), "pexels")
        self.assertEqual(C.fonte_banco(self.pasta / "reed.jpg"), "")
        self.assertEqual(C.fonte_banco(self.pasta / "stockholm-0.jpg"), "")   # "stockholm" não é banco

    def test_conferir_marca_cliche_e_agrupa_as_cenas_da_mesma_imagem(self):
        a, b = _foto(self.pasta, "pose.jpg", "banco"), _foto(self.pasta, "caso.jpg", "real")
        sb = self._sandbox([{"tipo": "foto", "de": 0, "imagem": a}, {"tipo": "foto", "de": 0.8, "imagem": a}, {"tipo": "foto", "de": 5, "imagem": b}],
                           [("O engenheiro mostrou a invenção.", 0), ("O engenheiro voltou depois.", 5)])
        ach = [x for x in C.conferir_cenas(sb)["achados"] if x["tipo"] == "cliche"]
        self.assertEqual(len(ach), 1)
        self.assertEqual(ach[0]["cenas"], [1, 2])
        self.assertIn("clichê", ach[0]["texto"])
        self.assertIn("momento real", ach[0]["conserto"])

    def test_quadros_de_um_clipe_contam_uma_imagem_so(self):
        q = self.pasta / "clipes" / "q-carteira"
        q.mkdir(parents=True)
        for i in range(3):
            _foto(q, f"{i:04d}.jpg", "banco")
        (self.pasta / "clipes" / "origem.json").write_text(json.dumps({"carteira": {"url": "https://www.pexels.com/video/1", "titulo": "carteira"}}))
        sb = self._sandbox([{"tipo": "clipe", "de": 0, "quadros_de": "clipes/q-carteira"}], [("O empresário manda dinheiro.", 0)])
        ach = [x for x in C.conferir_cenas(sb)["achados"] if x["tipo"] == "cliche"]
        self.assertEqual(len(ach), 1)
        self.assertIn("pexels", ach[0]["texto"])


class TestQuaseIgual(Falso):
    def _cenas(self, a: str, b: str, dt: float, mesma_frase: bool = False):
        sb = self._sandbox([{"tipo": "foto", "de": 0, "imagem": a}, {"tipo": "foto", "de": dt, "imagem": b}],
                           [("A câmera digital nasceu em 1975.", 0)] if mesma_frase else [("A câmera digital nasceu em 1975.", 0), ("A câmera foi mostrada aos chefes.", dt)])
        return [x for x in C.conferir_cenas(sb)["achados"] if x["tipo"] in ("quase_igual", "mesma_imagem")]

    def test_protótipo_em_dois_quadros_de_arquivos_diferentes_e_marcado(self):
        a, b = _foto(self.pasta, "q2.jpg", "camera"), _foto(self.pasta, "q4.jpg", "camera_b")
        ach = self._cenas(a, b, 5.0)
        self.assertEqual([x["cenas"] for x in ach], [[1, 2]])
        self.assertEqual(ach[0]["tipo"], "quase_igual")
        self.assertIn("quase a mesma imagem", ach[0]["texto"])
        self.assertGreaterEqual(ach[0]["cos"], C.QUASE_IGUAL[0][1])

    def test_mesmo_assunto_com_outro_angulo_passa(self):
        a, b = _foto(self.pasta, "q2.jpg", "camera"), _foto(self.pasta, "q4.jpg", "camera_c")
        self.assertEqual(self._cenas(a, b, 5.0), [])

    def test_longe_no_tempo_so_conta_se_for_quase_identica(self):
        a, b = _foto(self.pasta, "q2.jpg", "camera"), _foto(self.pasta, "q4.jpg", "camera_b")
        self.assertEqual(self._cenas(a, b, 10.0), [])    # 0,91 a 10 s: pede 0,92
        self.assertEqual(len(self._cenas(a, a, 10.0)), 1)   # a mesma foto reaproveitada 10 s depois
        self.assertEqual([x for x in self._cenas(a, a, 20.0) if x["tipo"] == "quase_igual"], [])    # fora da janela de 15 s (cena vizinha idêntica é outra regra)

    def test_mesma_frase_segura_a_foto(self):
        a = _foto(self.pasta, "q2.jpg", "camera")
        self.assertEqual(self._cenas(a, a, 1.0, mesma_frase=True), [])

    def test_clipe_pelo_quadro_do_meio_de_arquivos_diferentes(self):
        # dois clipes diferentes cujo quadro do meio é o mesmo protótipo
        for nome, assunto in (("a.mp4", "camera"), ("b.mp4", "camera_b")):
            (self.pasta / nome).write_bytes(b"x")
        quadros = {"a.mp4": Image.new("RGB", (64, 64), COR["camera"]), "b.mp4": Image.new("RGB", (64, 64), COR["camera_b"])}
        sb = self._sandbox([{"tipo": "filme", "de": 0, "ate": 3, "video": "a.mp4", "inicio_s": 10}, {"tipo": "filme", "de": 4, "ate": 7, "video": "b.mp4", "inicio_s": 3}],
                           [("A câmera digital nasceu em 1975.", 0), ("A câmera foi mostrada aos chefes.", 4)])
        with patch.object(C, "quadro_de_video", lambda v, t, largura=640: quadros[Path(v).name]):
            ach = [x for x in C.conferir_cenas(sb)["achados"] if x["tipo"] == "quase_igual"]
        self.assertEqual([x["cenas"] for x in ach], [[1, 2]])


class TestAcao(Falso):
    def test_acao_da_fala(self):
        self.assertIn("manda dinheiro", C.acao_da_fala("Tem empresário que manda dinheiro do bolso pra anúncio."))
        self.assertTrue(C.acao_da_fala("Você riria de uma proposta de 50 milhões?"))
        self.assertTrue(C.acao_da_fala("Ela assinou o contrato."))
        for sem in ("O nome dele era Steve Sasson.", "Foi o engenheiro da Kodak, em 1975.", "Elizabeth Holmes abriu a Theranos em 2003.",
                    "Isso mostra que o mercado mudou."):
            self.assertEqual(C.acao_da_fala(sem), "", sem)   # "abriu"/"mostra" não são ação filmável; "riu" dentro de "abriu" não conta

    def test_acao_com_foto_parada_vira_aviso_e_com_clipe_nao(self):
        a = _foto(self.pasta, "x.jpg", "real")
        sb = self._sandbox([{"tipo": "foto", "de": 0, "imagem": a}, {"tipo": "clipe", "de": 6, "quadros_de": "clipes/q-x"}],
                           [("Tem empresário que manda dinheiro todo mês.", 0), ("O outro empresário também manda dinheiro.", 6)])
        q = self.pasta / "clipes" / "q-x"
        q.mkdir(parents=True)
        _foto(q, "0001.jpg", "real")
        ach = [x for x in C.conferir_cenas(sb)["achados"] if x["tipo"] == "acao_sem_video"]
        self.assertEqual([x["cenas"] for x in ach], [[1]])
        self.assertIn("manda dinheiro", ach[0]["texto"])
        self.assertIn("clipe", ach[0]["conserto"])


class TestRevisao(unittest.TestCase):
    def test_revisao_mapeia_cliche_e_repeticao_e_ignora_o_aviso_de_acao(self):
        import revisao
        self.assertIn("imagem_cliche", revisao.FALHAS)
        with tempfile.TemporaryDirectory() as d:
            sb = Path(d)
            (sb / "cenas.json").write_text("{}")
            fake = {"cenas": [{"n": 1, "de": 0.0}, {"n": 2, "de": 3.0}, {"n": 3, "de": 6.0}, {"n": 4, "de": 9.0}],
                    "achados": [{"cena": 1, "tipo": "cliche", "texto": "c1", "conserto": "x"}, {"cena": 2, "tipo": "quase_igual", "texto": "c2", "conserto": "x"},
                                {"cena": 3, "tipo": "acao_sem_video", "texto": "c3", "conserto": "x"}, {"cena": 4, "tipo": "nao_casa", "texto": "c4", "conserto": "x"}]}
            with patch.object(C, "conferir_cenas", return_value=fake):
                out = revisao.imagens_x_fala({"sandbox": sb, "gravado": False})
        self.assertEqual([o["tipo"] for o in out], ["imagem_cliche", "imagem_repetida", "imagem_nao_casa"])
        self.assertTrue(all(o["regra_furou"] == "G6" and o["causa"] for o in out))


class TestTexto(unittest.TestCase):
    """A regra e o pedido da produção carregam o que o João pediu (30-out-2026)."""

    raiz = Path(__file__).resolve().parents[2]

    def test_g6_e_formatos_pedem_acao_em_video_real_viral_e_sem_repetir(self):
        g6 = next(l for l in (self.raiz / "REGRAS.md").read_text(encoding="utf-8").splitlines() if l.startswith("| G6 "))
        for termo in ("vídeo da ação", "banco", "clichê", "quase igual"):
            self.assertIn(termo, g6)
        for slug in ("editorial", "documentario"):
            f = (self.raiz / "formatos" / slug / "formato.json").read_text(encoding="utf-8")
            self.assertIn("vídeo da ação", f, slug)
            self.assertIn("clichê", f, slug)
            self.assertIn("vídeo da ação", (self.raiz / "formatos" / slug / "COMO-FAZER.md").read_text(encoding="utf-8"), slug)
            regras = json.loads((self.raiz / "formatos" / slug / "aprendizado" / "regras.json").read_text(encoding="utf-8"))
            lista = regras["regras"] if isinstance(regras, dict) else regras
            self.assertTrue(any("vídeo da ação" in json.dumps(r, ensure_ascii=False) for r in lista), slug)

    def test_dicas_do_editar_video(self):
        import editor
        for slug in ("editorial", "documentario"):
            d = editor.MOTORES[slug]["dicas"]
            self.assertIn("vídeo da ação", d, slug)
            self.assertIn("clichê", d, slug)


if __name__ == "__main__":
    unittest.main()
