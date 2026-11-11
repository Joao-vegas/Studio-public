"""Visual sem fundo vazio (30-out-2026, correção do João com print).

Editorial: ícone com emoji sobre degradê cinza ("coisas meio broxantes", Spotify 0:03 e globo 0:23): peça sem foto própria ganha fundo vivo
(a imagem da cena vizinha, desfocada) e o --conferir reprova ícone sem imagem e cena em fundo liso sem imagem.
Documentário: o jornal falso (cabeçalho BALCÃO, linhas cinza, borda rasgada, caixa datilografada) saiu, e o b-roll pequeno demais pra tela
(clipe de 712 px esticado 1,7x) passa a ser medido e tratado. Só lê os motores reais; o que grava vai pra pasta temporária; sem navegador."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
EDI = RAIZ / "formatos" / "editorial" / "base"
DOC = RAIZ / "formatos" / "documentario" / "base"


def _carregar(nome: str, arq: Path):
    spec = importlib.util.spec_from_file_location(nome, arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = _carregar("render_editorial_visual_teste", EDI / "render.py")
D = _carregar("render_documentario_visual_teste", DOC / "render.py")


def _jpg(pasta: Path, nome: str, w: int, h: int, cor=(120, 90, 60)) -> str:
    from PIL import Image
    Image.new("RGB", (w, h), cor).save(pasta / nome, quality=90)
    return nome


def _cena(tipo: str, de: float, **kw) -> dict:
    return {"tipo": tipo, "de": de, **kw}


class FundoVivoEditorial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)
        for n in ("a.jpg", "b.jpg", "c.jpg"):
            _jpg(self.p, n, 1200, 800)

    def tearDown(self):
        self.tmp.cleanup()

    def _plano(self, cenas, **kw):
        return E.planejar({"cenas": cenas, "duracao": 12, **kw}, self.p)["cenas"]

    def test_texto_sem_imagem_pega_a_foto_da_cena_vizinha(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("texto", 2, texto="oi"), _cena("foto", 4, imagem="b.jpg")])
        self.assertEqual(cs[1]["fundo_vivo"], "a.jpg", "empate: a anterior (a foto continua desfocada atrás da peça)")

    def test_a_mais_proxima_ganha(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("foto", 1, imagem="b.jpg"), _cena("foto", 2, imagem="c.jpg"),
                          _cena("icone", 3, imagem="a.jpg"), _cena("venn", 4, rotulos=["x", "y"]), _cena("foto", 5, imagem="b.jpg")])
        self.assertEqual(cs[4]["fundo_vivo"], "a.jpg", "a cena 4 está a 1 de distância do ícone com a.jpg e a 1 da foto b.jpg: vence a anterior")

    def test_foto_vale_mais_que_print(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("print", 1, imagem="b.jpg"), _cena("contador", 2, de_n=1, ate_n=2)])
        self.assertEqual(cs[2]["fundo_vivo"], "a.jpg", "o print (página branca) só entra se não houver foto por perto")
        so_print = self._plano([_cena("print", 0, imagem="b.jpg"), _cena("texto", 1, texto="oi")])
        self.assertEqual(so_print[1]["fundo_vivo"], "b.jpg")

    def test_clipe_vira_o_quadro_do_meio(self):
        q = self.p / "clipes" / "q-x"
        q.mkdir(parents=True)
        for k in range(5):
            _jpg(q, f"{k:05d}.jpg", 540, 960)
        cs = self._plano([_cena("clipe", 0, quadros_de="clipes/q-x"), _cena("texto", 2, texto="oi")])
        self.assertEqual(cs[1]["fundo_vivo"], "clipes/q-x#meio")
        self.assertEqual(E._fundo_arquivo("clipes/q-x#meio", self.p).name, "00002.jpg")

    def test_fundo_liso_so_quando_a_cena_pede(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("texto", 2, texto="oi", fundo="liso")])
        self.assertNotIn("fundo_vivo", cs[1])
        self.assertEqual(E.checar_fundo(cs)[0], [], "pediu liso: não reprova")
        self.assertTrue(E.checar_fundo(cs)[1], "mas avisa")

    def test_peca_que_ja_tem_imagem_nao_muda(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("texto", 2, texto="oi", imagem="b.jpg"), _cena("contador", 3, imagem="c.jpg")])
        self.assertNotIn("fundo_vivo", cs[1])
        self.assertNotIn("fundo_vivo", cs[2])

    def test_sem_nenhuma_imagem_reprova(self):
        cs = self._plano([_cena("texto", 0, texto="oi"), _cena("texto", 2, texto="tchau")])
        rep, _ = E.checar_fundo(cs)
        self.assertEqual(len(rep), 2)
        self.assertIn("fundo liso sem imagem", rep[0])

    def test_com_vizinha_nao_reprova(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("texto", 2, texto="oi"), _cena("icone", 3, imagem="b.jpg", rotulo="x")])
        self.assertEqual(E.checar_fundo(cs)[0], [])

    def test_icone_com_emoji_reprova(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("icone", 2, simbolo="🎵", rotulo="Spotify")])
        rep, _ = E.checar_fundo(cs)
        self.assertEqual(len(rep), 1)
        self.assertIn("emoji", rep[0])
        self.assertIn("logo real", rep[0])

    def test_icone_com_imagem_passa(self):
        cs = self._plano([_cena("foto", 0, imagem="a.jpg"), _cena("icone", 2, imagem="b.jpg", rotulo="Spotify")])
        self.assertEqual(E.checar_fundo(cs)[0], [])

    def test_checar_do_motor_inclui_a_regra(self):
        doc = {"cenas": [_cena("foto", 0, imagem="a.jpg"), _cena("icone", 2, simbolo="🌎", rotulo="x")], "duracao": 4}
        ch = E.checar(doc, self.p, E.planejar(doc, self.p))
        self.assertTrue(any("emoji" in m for m in ch["motivos"]), ch["motivos"])

    def test_logo_com_transparencia_entra_colorida_sobre_disco(self):
        from PIL import Image
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        for x in range(60, 140):
            for y in range(60, 140):
                im.putpixel((x, y), (30, 215, 96, 255))   # verde Spotify
        im.save(self.p / "spotify-logo.png")
        est = E._estilo_icone({}, self.p / "spotify-logo.png")
        self.assertTrue(est["logo"])
        self.assertEqual(est["disco"], "escuro", "logo clara/colorida: disco escuro")
        im2 = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        for x in range(60, 140):
            for y in range(60, 140):
                im2.putpixel((x, y), (10, 10, 10, 255))
        im2.save(self.p / "preta-logo.png")
        self.assertEqual(E._estilo_icone({}, self.p / "preta-logo.png")["disco"], "claro", "logo preta: disco claro")

    def test_foto_comum_no_icone_nao_vira_logo(self):
        self.assertFalse(E._estilo_icone({}, self.p / "a.jpg")["logo"])
        self.assertTrue(E._estilo_icone({"logo": True}, self.p / "a.jpg")["logo"], "logo: true no cenas.json manda")

    def test_pagina_recebe_url_e_brilho(self):
        plano = E.planejar({"cenas": [_cena("foto", 0, imagem="a.jpg"), _cena("texto", 2, texto="oi")], "duracao": 4}, self.p)
        pg = E._pagina(plano, self.p)
        self.assertTrue(pg["cenas"][1]["fundo_vivo"].startswith("/f/"))
        self.assertTrue(0 < pg["cenas"][1]["fundo_lum"] < 1)

    def test_html_do_motor_desenha_o_fundo_vivo(self):
        h = (EDI / "index.html").read_text(encoding="utf-8")
        for trecho in (".fundo-vivo", "c.fundo_vivo", "c._fv", "icone-logo"):
            self.assertIn(trecho, h)
        self.assertNotIn("fundo cinza liso", h)

    def test_rotulo_legivel_e_grao_sutil(self):
        h = (EDI / "index.html").read_text(encoding="utf-8")
        self.assertIn(".cena.fv .rotulo", h, "halo escuro atrás do texto sobre o fundo vivo")
        self.assertIn("--forte-claro", h)
        self.assertIn("fundo-banda", h)
        m = re.search(r"#grao\s*\{[^}]*opacity:\s*([.\d]+)", h)
        self.assertLessEqual(float(m.group(1)), .14, "grão sutil: a .32 sujava o fundo desfocado")
        self.assertGreaterEqual(float(m.group(1)), .08)

    def test_exemplo_do_formato_nao_manda_emoji(self):
        ex = (EDI / "exemplos" / "grupo-por-crenca-gera.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r'"tipo": "icone"[^\n]*"simbolo"', ex))
        readme = (EDI / "README.md").read_text(encoding="utf-8")
        self.assertIn("Emoji não vale", readme)
        self.assertIn("Fundo vivo", readme)
        como = (EDI.parent / "COMO-FAZER.md").read_text(encoding="utf-8")
        self.assertIn("nunca leva emoji", como)

    def test_pedido_da_producao_e_do_editor_dizem_sem_emoji(self):
        f = json.loads((EDI.parent / "formato.json").read_text(encoding="utf-8"))
        cenas = next(e for e in f["esteira"]["etapas"] if e["id"] == "cenas")
        self.assertIn("NUNCA leva emoji", cenas["faz"])
        sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
        import editor
        self.assertIn("NUNCA emoji", editor.MOTORES["editorial"]["dicas"])

    def test_motor_das_copias_do_avulso_tem_a_conferencia(self):
        pasta = RAIZ / "clientes" / "Avulso" / "avulsoContent" / "modelos" / "editorial"
        if not pasta.is_dir():
            self.skipTest("cliente Avulso não está nesta máquina")
        for r in [pasta / "render.py", *sorted(pasta.glob("_sandbox-*/render.py"))]:
            with self.subTest(arquivo=str(r.relative_to(RAIZ))):
                self.assertIn("def checar_fundo", r.read_text(encoding="utf-8"))


class JornalLimpoDocumentario(unittest.TestCase):
    def test_jornal_falso_saiu(self):
        h = (DOC / "index.html").read_text(encoding="utf-8")
        for morto in ("BALCÃO'", "EDIÇÃO DE HOJE", "jornalURL", "JORNAL_DIVS"):
            self.assertNotIn(morto, h)
        # filme, jornal e rodapé sem borda rasgada nem caixa datilografada
        corpo = h[h.index("const TIPOS"):] if "const TIPOS" in h else h
        self.assertNotIn("clipPath = rasgado", corpo)
        self.assertNotIn("div('faixa'", h)

    def test_rodape_sem_cursor_nem_tarja(self):
        h = (DOC / "index.html").read_text(encoding="utf-8")
        self.assertIn("datilografa(c.tokens, t, false, true)", h)
        self.assertIn("semCursor", h)

    def test_filme_e_polaroid_tem_fundo_vivo(self):
        h = (DOC / "index.html").read_text(encoding="utf-8")
        self.assertIn("function fundoVivo", h)
        self.assertIn("fv-img", h)
        self.assertGreaterEqual(h.count("fundoVivo(el"), 2, "filme e polaroid")
        self.assertIn("c.foco", h, "foto vertical na faixa: foco do rosto")

    def test_fundo_jornal_e_so_css(self):
        h = (DOC / "index.html").read_text(encoding="utf-8")
        self.assertIn(".f-jornal::before", h)
        self.assertIn("feTurbulence", h)


class ResolucaoDoBroll(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _doc(self, w: int, h: int, tipo="polaroid", chave="video", **kw):
        _jpg(self.p, "b.jpg", w, h)   # arquivo de teste; "video" = tratado como clipe (2x), "imagem" = foto (Real-ESRGAN 4x)
        c = {"tipo": tipo, "i": 0, "n": 1, "de": 0.0, "ate": 2.0, chave: "b.jpg", "origem": "teste", **kw}
        return c, self.p / "b.jpg"

    def test_polaroid_grande_nao_e_esticada(self):
        c, f = self._doc(1600, 1000)
        r = D.avaliar_resolucao(c, f, (0, 0, 1, 1))
        self.assertLessEqual(r["esticado"], D.UPSCALE_MAX)
        self.assertFalse(r["ampliada"])

    def test_filme_de_712px_passa_pelo_tratamento_e_fica_ok(self):
        c, f = self._doc(712, 480, tipo="filme")
        r = D.avaliar_resolucao(c, f, (0, 0, 1, 1))
        self.assertGreater(r["esticado"], 1.5, "o caso do Kodak: 1080 px na tela pra 712 de arquivo")
        self.assertTrue(r["ampliada"])
        self.assertLessEqual(r["depois_do_upscale"], D.UPSCALE_FINAL_MAX)

    def test_filme_de_712px_sem_upscale_reprova(self):
        c, f = self._doc(712, 480, tipo="filme", ampliar=False)
        r = D.avaliar_resolucao(c, f, (0, 0, 1, 1))
        self.assertGreater(r["depois_do_upscale"], D.UPSCALE_FINAL_MAX)

    def test_clipe_minusculo_reprova_mesmo_com_tratamento(self):
        c, f = self._doc(320, 240, tipo="filme")
        r = D.avaliar_resolucao(c, f, (0, 0, 1, 1))
        self.assertGreater(r["depois_do_upscale"], D.UPSCALE_FINAL_MAX)

    def test_foto_pequena_passa_pelo_real_esrgan_4x(self):
        c, f = self._doc(320, 240, tipo="filme", chave="imagem")
        r = D.avaliar_resolucao(c, f, (0, 0, 1, 1))
        self.assertEqual(r["upscale"], 4)
        self.assertLessEqual(r["depois_do_upscale"], D.UPSCALE_FINAL_MAX)

    def test_corte_conta(self):
        c, f = self._doc(1280, 720, tipo="filme")
        inteiro = D.avaliar_resolucao(c, f, (0, 0, 1, 1))["esticado"]
        cortado = D.avaliar_resolucao(c, f, (0.25, 0, 0.5, 1))["esticado"]
        self.assertGreater(cortado, inteiro, "cortar metade da largura estica o dobro")

    def test_checar_do_documentario_reprova_clipe_pequeno(self):
        base = json.loads((DOC / "cenas-modelo.json").read_text(encoding="utf-8"))
        origem = json.dumps(base)
        self.assertIn("filme", origem)
        # o cenas-modelo usa a mídia de demo (grande o bastante): a 3j não reprova nada dele
        ch = D.checar(base, DOC)
        self.assertFalse([m for m in ch["motivos"] if "esticado" in m], ch["motivos"])

    def test_filtro_do_clipe_ampliado(self):
        f = D.filtro_clipe_ampliado(712, 480, 1424)
        for parte in ("hqdn3d", "scale=1424", "lanczos", "unsharp", "format=gray"):
            self.assertIn(parte, f)
        self.assertNotIn("contrast=1.12", f, "o P&B antigo chapava a sombra do filme colorido")

    def test_ffmpeg_aceita_o_filtro(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            fonte, saida = t / "in.mp4", t / "out.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=1", str(fonte)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(fonte), "-frames:v", "1", "-vf",
                            "crop=iw*1:ih*1:iw*0:ih*0," + D.filtro_clipe_ampliado(320, 240, 640), str(saida)], check=True)
            from PIL import Image
            with Image.open(saida) as im:
                self.assertEqual(im.size[0], 640)

    def test_a_checagem_do_jornal_so_olhava_o_rosto(self):
        """A 3i (jornal borrado) mede o rosto da cena `jornal`; o b-roll do filme/polaroid nunca era medido. A 3j mede."""
        fonte = (DOC / "render.py").read_text(encoding="utf-8")
        self.assertIn("3j. b-roll com resolução", fonte)
        self.assertIn("avaliar_resolucao(c, f, corte)", fonte)

    def test_motor_da_copia_do_avulso_tem_a_resolucao(self):
        pasta = RAIZ / "clientes" / "Avulso" / "avulsoContent" / "modelos" / "documentario"
        if not pasta.is_dir():
            self.skipTest("cliente Avulso não está nesta máquina")
        for r in [pasta / "render.py", *sorted(pasta.glob("_sandbox-*/render.py"))]:
            with self.subTest(arquivo=str(r.relative_to(RAIZ))):
                self.assertIn("def avaliar_resolucao", r.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
