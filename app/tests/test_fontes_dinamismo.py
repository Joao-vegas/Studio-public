"""Fontes grátis (fontes_gratis, Openverse na busca de música), ferramentas locais (midia_local) e a checagem mecânica de
dinamismo do conferir_video (REGRAS.md G26). Sem rede: as APIs são trocadas por respostas fixas."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app/ferramentas"))


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


class Dinamismo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        enc = ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18"]
        cls.parado = t / "parado.mp4"      # 8 s de imagem congelada
        _ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=1", "-frames:v", "1", str(t / "q.png")])
        _ffmpeg(["-loop", "1", "-i", str(t / "q.png"), "-t", "8", "-r", "30", *enc, str(cls.parado)])
        cls.mexido = t / "mexido.mp4"      # 9 s com movimento contínuo e um corte seco a cada 3 s
        for i, filtro in enumerate(("null", "negate", "hue=h=120")):
            _ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=3", "-vf", filtro, *enc, str(t / f"p{i}.mp4")])
        (t / "lista.txt").write_text("".join(f"file '{t}/p{i}.mp4'\n" for i in range(3)))
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(t / "lista.txt"), "-c", "copy", str(cls.mexido)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_mede_o_trecho_parado(self):
        import conferir_video as c
        m = c.medir_dinamismo(self.parado)
        self.assertGreaterEqual(m["parado_max_s"], 6.5)        # 8 s menos o último segundo
        self.assertEqual(m["trocas"], 0)
        self.assertEqual(m["andando_pct"], 0.0)

    def test_mede_o_video_mexido(self):
        import conferir_video as c
        m = c.medir_dinamismo(self.mexido)
        self.assertEqual(m["parado_max_s"], 0.0)
        self.assertGreaterEqual(m["trocas"], 2)                  # os dois cortes secos
        self.assertGreater(m["andando_pct"], 95)
        self.assertLessEqual(m["sem_troca_max_s"], 3.3)

    def test_marca_parado_demais_e_deixa_o_mexido_passar(self):
        import conferir_video as c
        av, _ = c.checar_dinamismo(self.parado, None)
        self.assertTrue(any(a.startswith("Parado demais") for a in av), av)
        av, num = c.checar_dinamismo(self.mexido, None)
        self.assertEqual(av, [])
        self.assertIn("regua", num)

    def test_regua_vem_do_estilo(self):
        import conferir_video as c
        ed = c.regua_dinamismo("editorial")                      # régua medida: 56 planos/min, plano mediano 0,5 s
        self.assertEqual(ed["sem_troca_max_s"], 2.6)
        self.assertGreater(ed["trocas_min"], 20)
        self.assertIsNone(c.regua_dinamismo("caixinha-de-perguntas")["sem_troca_max_s"])   # sem cena de apoio: só o parado
        self.assertEqual(c.regua_dinamismo("faixa-com-cenas")["sem_troca_max_s"], c.SEM_TROCA_PADRAO_S)
        self.assertIsNone(c.regua_dinamismo(None)["sem_troca_max_s"])

    def test_estilo_rapido_reprova_plano_longo_sem_troca(self):
        import conferir_video as c
        falso = {"duracao_s": 30.0, "trocas": 3, "trocas_por_min": 6.0, "parado_max_s": 0.0, "parado_em_s": 0.0,
                 "sem_troca_max_s": 16.0, "sem_troca_em_s": 4.0, "andando_pct": 99.0}   # além do pior plano das referências (11,3 s)
        av, _ = c.checar_dinamismo(Path("x.mp4"), "editorial", medida=falso)
        self.assertTrue(any(a.startswith("Sem troca visual") for a in av), av)
        self.assertTrue(any(a.startswith("Poucas trocas") for a in av), av)

    def test_faixa_com_cenas_com_16_s_sem_troca_reprova(self):
        import conferir_video as c
        real = {"duracao_s": 60.0, "trocas": 6, "trocas_por_min": 6.0, "parado_max_s": 0.0, "parado_em_s": 0.0,
                "sem_troca_max_s": 16.0, "sem_troca_em_s": 20.0, "andando_pct": 99.0}
        av, num = c.checar_dinamismo(Path("x.mp4"), "faixa-com-cenas", medida=real)
        self.assertEqual(av, ["Sem troca visual por 16.0 s em 20 s (o estilo aguenta 12.0 s)"])   # uma casa decimal nos dois números
        self.assertEqual(num["regua"]["sem_troca_max_s"], 12.0)

    def test_parado_com_texto_acendendo_nao_conta_como_parado(self):
        import conferir_video as c
        t = Path(self.tmp.name)
        v = t / "texto.mp4"   # fundo liso e uma 'palavra' (caixinha) nova a cada 0,5 s: pouca diferença média, mas muda de verdade
        caixas = ",".join(f"drawbox=x={20 + (i % 3) * 100}:y={30 + i * 40}:w=70:h=14:color=white:t=fill:enable='gte(t,{i * .5})'" for i in range(14))
        _ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=360x640:r=30:d=8", "-vf", caixas, "-pix_fmt", "yuv420p", str(v)])
        m = c.medir_dinamismo(v)
        self.assertLess(m["parado_max_s"], 1.0, m)

    def test_referencias_de_cada_estilo_passam_na_checagem_do_proprio_estilo(self):
        """As referências SÃO a régua: toda checagem de ritmo passa em todo exemplo-*.mp4 do próprio estilo."""
        import conferir_video as c
        exemplos = sorted((RAIZ / "formatos").glob("*/exemplo-*.mp4"))
        if not exemplos:
            self.skipTest("sem exemplo-*.mp4")
        falhas = []
        for v in exemplos:
            av, _ = c.checar_dinamismo(v, v.parent.name)
            if av:
                falhas.append(f"{v.parent.name}/{v.name}: {av}")
        self.assertEqual(falhas, [])

    def test_medida_das_referencias_fica_em_cache_por_sha(self):
        import conferir_video as c
        from unittest import mock
        ex = sorted((RAIZ / "formatos" / "faixa-com-cenas").glob("exemplo-*.mp4"))
        if not ex:
            self.skipTest("sem exemplo-*.mp4")
        c.medidas_das_referencias("faixa-com-cenas")           # garante o cache
        with mock.patch.object(c, "medir_dinamismo", side_effect=AssertionError("mediu de novo")):
            self.assertEqual(len(c.medidas_das_referencias("faixa-com-cenas")), len(ex))


class FontesGratis(unittest.TestCase):
    def test_openverse_filtra_e_registra_licenca(self):
        import fontes_gratis as f
        orig = f._json
        f._json = lambda url, *a, **k: {"results": [
            {"title": "Praça", "foreign_landing_url": "https://flickr.com/p/1", "url": "https://live.staticflickr.com/1.jpg", "creator": "Ana",
             "license": "by", "license_version": "2.0", "width": 500, "height": 375, "source": "flickr"}]}
        try:
            r = f.img_openverse("praça", 3)
        finally:
            f._json = orig
        self.assertEqual(r[0]["licenca"], "BY 2.0")
        self.assertEqual(r[0]["fonte"], "openverse/flickr")
        self.assertEqual(r[0]["autor"], "Ana")

    def test_commons_descarta_nc_e_nd(self):
        import fontes_gratis as f
        mk = lambda lic: {"title": "File:x.jpg", "index": 1, "imageinfo": [{"url": "u", "thumburl": "t", "descriptionurl": "p", "width": 1, "height": 1,  # noqa: E731
                                                                          "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": "A"}}}]}
        orig = f._json
        f._json = lambda *a, **k: {"query": {"pages": {"1": mk("CC BY-NC 4.0"), "2": mk("CC BY-ND 2.0"), "3": mk("CC BY-SA 4.0")}}}
        try:
            r = f.img_commons("x", 5)
        finally:
            f._json = orig
        self.assertEqual([i["licenca"] for i in r], ["CC BY-SA 4.0"])

    def test_archive_so_licenca_declarada(self):
        import fontes_gratis as f
        orig = f._json
        docs = [{"identifier": "a", "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/"},
                {"identifier": "b", "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"},
                {"identifier": "c", "licenseurl": "https://creativecommons.org/licenses/by/4.0/"}]
        f._json = lambda *a, **k: {"response": {"docs": docs}}
        try:
            r = f._archive_docs("x", 5, "movies")
        finally:
            f._json = orig
        self.assertEqual({d["identifier"] for d in r}, {"a", "c"})
        self.assertEqual(f._lic_url("https://creativecommons.org/licenses/by/4.0/"), "CC BY 4.0")

    def test_situacao_diz_o_que_ficou_de_fora(self):
        import fontes_gratis as f
        nomes = {x["fonte"]: x for x in f.situacao()}
        self.assertIn("fora", nomes["loc.gov"]["chave"])
        self.assertIn("openverse", nomes)

    def test_openverse_na_busca_de_musica(self):
        import musica_busca as m
        self.assertIn("openverse", [x["id"] for x in m.FONTES])
        orig = m._get_json
        m._get_json = lambda *a, **k: {"results": [
            {"id": "1", "title": "Dark", "duration": 96000, "license": "by-sa", "license_version": "3.0", "provider": "jamendo",
             "foreign_landing_url": "https://www.jamendo.com/track/1", "url": "https://prod-1.storage.jamendo.com/?trackid=1&format=mp32", "creator": "X"},
            {"id": "2", "title": "ND", "duration": 96000, "license": "by-nd", "provider": "jamendo",
             "foreign_landing_url": "https://www.jamendo.com/track/2", "url": "https://prod-1.storage.jamendo.com/?trackid=2&format=mp32"},
            {"id": "3", "title": "Host ruim", "duration": 9000, "license": "cc0", "provider": "x",
             "foreign_landing_url": "https://exemplo.com/3", "url": "https://exemplo.com/3.mp3"}]}
        try:
            g = m.buscar_openverse("dark", 5)
        finally:
            m._get_json = orig
        self.assertEqual([i["id"] for i in g["itens"]], ["1"])      # sem ND, sem host fora da lista
        self.assertTrue(g["itens"][0]["comercial"])


@unittest.skipUnless((RAIZ / "app/modelos-locais/ferramentas/depth-anything-v2-small-q.onnx").exists(), "modelo de profundidade não baixado (midia_local.py baixar)")
class MidiaLocal(unittest.TestCase):
    def _foto(self, pasta: Path, w=640, h=480) -> Path:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (w, h), (90, 140, 200))
        d = ImageDraw.Draw(im)
        d.rectangle((w // 3, h // 4, 2 * w // 3, h), fill=(200, 80, 60))
        d.ellipse((w // 2 - 40, h // 3 - 40, w // 2 + 40, h // 3 + 40), fill=(240, 220, 200))
        p = pasta / "foto.jpg"
        im.save(p)
        return p

    def test_upscale_nao_mexe_em_foto_grande(self):
        import midia_local as ml
        with tempfile.TemporaryDirectory() as t:
            foto = self._foto(Path(t), 1600, 900)
            r = ml.upscale(foto, Path(t) / "saida.jpg", 1400)
            self.assertFalse(r["ampliada"])
            self.assertTrue((Path(t) / "saida.jpg").is_file())

    def test_parallax_gera_quadros_diferentes(self):
        import midia_local as ml
        import numpy as np
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            foto = self._foto(Path(t))
            n = ml.parallax(foto, Path(t) / "q", 0.5, "dir", 1.0, 30)
            self.assertEqual(n, 16)
            a = np.asarray(Image.open(Path(t) / "q/00001.jpg").convert("L"), dtype=float)
            b = np.asarray(Image.open(Path(t) / f"q/{n:05d}.jpg").convert("L"), dtype=float)
            self.assertEqual(a.shape, (1920, 1080))
            self.assertGreater(abs(a - b).mean(), 1.0)             # a câmera andou de fato

    def test_motor_do_editorial_troca_foto_por_clipe(self):
        spec = importlib.util.spec_from_file_location("editorial_render_t", RAIZ / "formatos/editorial/base/render.py")
        r = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(r)
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t)
            self._foto(pasta)
            plano = {"cenas": [{"n": 1, "tipo": "foto", "de": 0, "ate": 0.5, "imagem": "foto.jpg", "parallax": True},
                               {"n": 2, "tipo": "foto", "de": 0.5, "ate": 1.0, "imagem": "foto.jpg"}]}
            avisos = []
            r.aplicar_locais(plano, pasta, avisos)
            self.assertEqual(avisos, [])
            c1, c2 = plano["cenas"]
            self.assertEqual(c1["tipo"], "clipe")
            self.assertTrue(Path(c1["quadros_de"]).is_dir())
            self.assertEqual(c2["tipo"], "foto")                  # sem "parallax" segue como foto


if __name__ == "__main__":
    unittest.main()
