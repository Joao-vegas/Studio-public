"""Grupo 3 · tela: música e efeitos escolhíveis, storyboard legível (padrão do Diálogo 3D), menos confusão.
Tudo em pasta temporária; nada pago, nada de rede (a busca real do Mixkit/SoundCloud é rodada à mão)."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
P, C, servidor = fixtures.P, fixtures.C, fixtures.servidor
import formatos
import musica_busca as MB
import storyboard as SB
import simples

TEM_FFMPEG = bool(shutil.which("ffmpeg"))


def video_teste(destino: Path, segundos: int = 12) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=360x640:rate=10",
                    "-t", str(segundos), "-pix_fmt", "yuv420p", str(destino)], check=True, timeout=60)
    return destino


class Base(unittest.TestCase):
    setUp_v2 = fixtures.Isolado.setUp
    job = fixtures.Isolado.job

    def setUp(self):
        self.setUp_v2()
        self.stack.enter_context(patch.object(formatos, "FORMATOS", self.root / "formatos"))
        self.stack.enter_context(patch.object(formatos, "RAIZ", self.root))
        self.stack.enter_context(patch.object(MB, "ACERVO", self.root / "acervo/itens"))
        self.stack.enter_context(patch.object(MB, "JOBS", self.jobs))
        self.stack.enter_context(patch.object(MB, "TMP", self.root / "acervo/.tmp/musica-busca"))
        self.stack.enter_context(patch.object(simples, "UPLOADS", self.est))

    def formato(self, slug, esteira=False):
        d = self.root / "formatos" / slug
        d.mkdir(parents=True)
        dados = {"titulo": slug.title(), "modelos": ["estilo"], "entrada": "video"}
        if esteira:
            dados["esteira"] = {"etapas": [{"id": "storyboard", "titulo": "Storyboard", "aprovar": True}]}
        C.gravar_json(d / "formato.json", dados)

    def faixa(self, rel_path):
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ID3" + b"\0" * 2048)
        return p


class MusicaDoCliente(Base):
    def test_do_cliente_so_devolve_as_faixas_do_cliente_pedido(self):
        self.faixa("clientes/Ana/anaContent/modelos/reel/assets/musica/bed-calma.mp3")
        self.faixa("clientes/Ana/anaContent/modelos/outro/assets/musica/tema.wav")
        self.faixa("clientes/Ana/anaContent/banco-musicas/legado.mp3")   # banco de cliente não é mais fonte
        self.faixa("clientes/Bia/biaContent/modelos/reel/assets/musica/segredo-da-bia.mp3")
        self.faixa("clientes/Bia/biaContent/modelos/outro/assets/musica/outro-segredo.mp3")
        itens = MB.do_cliente("Ana")
        self.assertEqual(sorted(Path(i["arquivo"]).name for i in itens), ["bed-calma.mp3", "tema.wav"])
        self.assertTrue(all(i["arquivo"].startswith("clientes/Ana/") for i in itens))
        self.assertFalse([i for i in MB.do_cliente("Ana") if "Bia" in i["arquivo"] or "segredo" in i["arquivo"]])
        self.assertEqual(MB.do_cliente("../Bia"), [])
        self.assertEqual(MB.do_cliente("Ninguem"), [])

    def test_formato_traz_o_catalogo_sem_as_rejeitadas(self):
        self.faixa("formatos/doc/base/audio/musicas/31.mp3")
        self.faixa("formatos/doc/base/audio/musicas/32.mp3")
        C.gravar_json(self.root / "formatos/doc/base/audio/catalogo.json", {"musicas": [
            {"id": "31", "arquivo": "audio/musicas/31.mp3", "nome": "Calma boa", "clima": "calma", "status": "aprovada"},
            {"id": "32", "arquivo": "audio/musicas/32.mp3", "nome": "Ruim", "clima": "animada", "status": "rejeitada"}]})
        itens = MB.do_cliente("Teste", "doc")
        self.assertEqual([(i["titulo"], i["fonte"]) for i in itens], [("Calma boa", "formato")])

    def test_opcoes_marcam_a_ja_usada_e_variam_a_fonte(self):
        usada = self.faixa("clientes/Teste/testeContent/modelos/estilo/assets/musica/bed-documental.mp3")
        self.faixa("clientes/Teste/testeContent/modelos/estilo/assets/musica/bed-outra.mp3")
        self.faixa("formatos/doc/base/audio/musicas/40.mp3")
        anterior = self.job("aprovado", "anterior")
        C.gravar_json(self.root / anterior["sandbox"] / "PLANO.json",
                      {"beats": [], "musica": {"opcao": str(usada.relative_to(self.root)), "titulo": "bed documental"}})
        ops = MB.opcoes("Teste", "documentary", n=3, ignorar="video", formato="doc")
        self.assertEqual(ops[0]["fonte"], "cliente")                                  # ordem: cliente, Biblioteca, formato
        self.assertEqual(ops[0]["arquivo"].rsplit("/", 1)[-1], "bed-outra.mp3")
        self.assertEqual(ops[1]["fonte"], "formato")                                  # (Biblioteca vazia aqui)
        self.assertIn("já usada em", ops[-1]["usada_txt"])

    def test_baixa_so_a_faixa_escolhida_na_sandbox(self):
        j = self.job("plano")

        def falso(url, destino):
            destino.write_bytes(b"ID3" + b"\0" * 4096)
            return destino
        with patch.object(MB, "_baixar", side_effect=falso) as baixar:
            p = MB.baixar_externa("https://assets.mixkit.co/music/682/682.mp3", j["sandbox"], "mixkit", "Classical vibes 2")
            self.assertEqual(p, (self.root / j["sandbox"] / "work/musica/externa/classical-vibes-2.mp3").resolve())
            MB.baixar_externa("https://assets.mixkit.co/music/682/682.mp3", j["sandbox"], "mixkit", "Classical vibes 2")
            self.assertEqual(baixar.call_count, 1)                     # já baixada: não baixa de novo
            with self.assertRaises(ValueError):
                MB.baixar_externa("https://malicioso.com/x.mp3", j["sandbox"], "mixkit", "x")
            with self.assertRaises(ValueError):
                MB.baixar_externa("https://assets.mixkit.co/music/1/1.mp3", "../fora", "mixkit", "x")

    def test_mixkit_le_a_lista_da_pagina(self):
        html = ('<script type="application/ld+json">{"@graph":[{"@type":"ItemList","itemListElement":['
                '{"@type":"MusicRecording","name":"Classical vibes 2","byArtist":"Grigoriy","duration":"PT1M53S",'
                '"url":"https://assets.mixkit.co/music/682/682.mp3","genre":"Film Score"}]}]}</script>')
        it = MB._mixkit_itens(html, "musica", "https://mixkit.co/free-stock-music/tag/documentary/")[0]
        self.assertEqual((it["titulo"], it["baixar"], it["duracao"], it["comercial"]),
                         ("Classical vibes 2", "https://assets.mixkit.co/music/682/682.mp3", 113.0, True))
        self.assertTrue(MB._host_ok(it["baixar"], "mixkit"))
        self.assertEqual(it["chave"], "mixkit:music:682")


@unittest.skipUnless(TEM_FFMPEG, "precisa do ffmpeg")
class Storyboard(Base):
    def sandbox(self):
        j = self.job("plano")
        sb = self.root / j["sandbox"]
        video_teste(sb / "work/joao.mp4", 12)
        video_teste(sb / "brolls/clips/b1-1.mp4", 4)
        from PIL import Image
        Image.new("RGB", (900, 600), (10, 10, 10)).save(sb / "brolls/b1-1-sheet.jpg")
        Image.new("RGB", (900, 600), (10, 10, 10)).save(sb / "brolls/b3-1-sheet.jpg")
        C.gravar_json(sb / "PLANO.json", {
            "transcricao": [{"t0": 0, "t1": 2, "texto": "Oi, você gestão."}, {"t0": 9, "t1": 12, "texto": "Até mais."}],
            "musica": {"titulo": "Cama calma", "inicio_s": 10, "fim_s": 40},
            "beats": [
                {"id": "b1", "inicio": 2, "fim": 4, "fala": "você gestão", "tipo": "broll", "escolha": "b1-1",
                 "opcoes": [{"id": "b1-1", "titulo": "Cena", "arquivo": "brolls/clips/b1-1.mp4", "sheet": "brolls/b1-1-sheet.jpg"}]},
                {"id": "c1", "inicio": 4, "fim": 6, "fala": "o que era vergonha", "tipo": "card", "texto_card": "O que era *vergonha*."},
                {"id": "b3", "inicio": 6, "fim": 7, "fala": "só a folha", "tipo": "broll",
                 "opcoes": [{"id": "b3-1", "titulo": "Só sheet", "sheet": "brolls/b3-1-sheet.jpg"}]},
                {"id": "p1", "inicio": 7, "fim": 9, "fala": "presta atenção", "tipo": "punch"}]})
        return sb

    def test_folha_sem_buraco_sem_sheet_e_card_desenhado(self):
        sb = self.sandbox()
        r = SB.gerar(sb)
        self.assertTrue((sb / "storyboard.jpg").is_file())
        q = r["quadros"]
        self.assertFalse([x for x in q if "-sheet" in x["fonte"]])
        self.assertEqual(q[0]["t0"], 0.0)
        for a, b in zip(q, q[1:]):                                  # linha do tempo inteira
            self.assertAlmostEqual(a["t1"], b["t0"], places=1)
        self.assertGreaterEqual(q[-1]["t1"], 11.9)
        self.assertEqual(next(x for x in q if x["tipo"] == "card")["fonte"], "desenho")
        self.assertEqual(next(x for x in q if x["beat"] == "b3")["fonte"], "sem-previa")
        self.assertEqual(next(x for x in q if x["beat"] == "b1")["fonte"], "brolls/clips/b1-1.mp4")
        from PIL import Image, ImageStat
        folha = Image.open(sb / "storyboard.jpg").convert("L")
        i = next(k for k, x in enumerate(q) if x["tipo"] == "card")
        x0, y0 = SB.GAP + (i % SB.COLS) * (SB.CW + SB.GAP), SB.GAP + (i // SB.COLS) * (SB.CH + SB.FAIXA + SB.GAP)
        self.assertGreater(ImageStat.Stat(folha.crop((x0, y0, x0 + SB.CW, y0 + SB.CH))).mean[0], 150)   # nunca preto
        self.assertFalse(SB.desatualizado(sb))
        C.gravar_json(sb / "PLANO.json", {**C.ler_json(sb / "PLANO.json"), "observacoes": "mudou"})
        import os
        os.utime(sb / "PLANO.json", (9e9, 9e9))
        self.assertTrue(SB.desatualizado(sb))

    def test_acento_nao_vira_glifo_vazio(self):
        from PIL import Image, ImageDraw, ImageFont, ImageChops
        f = SB.fonte(22)
        self.assertIsInstance(f, ImageFont.FreeTypeFont)

        def desenho(txt):
            im = Image.new("L", (300, 40), 255)
            ImageDraw.Draw(im).text((4, 4), txt, font=f, fill=0)
            return im
        vazio = desenho("\U000F0000")                               # código sem glifo: a caixinha
        for letra in "êã":
            self.assertIsNotNone(ImageChops.difference(desenho(letra), vazio).getbbox(), letra)
        self.assertIsNotNone(ImageChops.difference(desenho("você gestão"), desenho("voc\U000F0000 gest\U000F0000o")).getbbox())

    def test_sem_fonte_da_erro_claro(self):
        SB.fonte.cache_clear()
        try:
            with patch.object(SB, "PASTAS_FONTES", [self.root / "sem-fontes"]):
                with self.assertRaises(RuntimeError) as e:
                    SB.fonte(22)
            self.assertIn("Barlow", str(e.exception))
        finally:
            SB.fonte.cache_clear()


class TelaDoJob(Base):
    def plano(self, j, **extra):
        C.gravar_json(self.root / j["sandbox"] / "PLANO.json", {"transcricao": [], "beats": [
            {"id": "b1", "inicio": 1, "fim": 3, "fala": "uma cena", "tipo": "broll", "escolha": None,
             "opcoes": [{"id": "b1-1", "titulo": "Só a folha", "sheet": "brolls/b1-1-sheet.jpg", "url": "https://x"}]},
            {"id": "c1", "inicio": 3, "fim": 5, "fala": "virou sucesso", "tipo": "card", "texto_card": "O que era *vergonha*"}],
            **extra})
        (self.root / j["sandbox"] / "brolls/b1-1-sheet.jpg").write_bytes(b"JPG")

    def html(self, slug="video"):
        r = self.client.get(f"/job/Teste/{slug}")
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_bloco_de_musica_com_player_sem_musica_e_buscar_outra(self):
        j = self.job("plano")
        self.faixa(j["sandbox"] + "/work/musica/calma.mp3")
        self.plano(j, musica={"escolha": "m1", "opcoes": [{"id": "m1", "titulo": "Calma", "arquivo": "work/musica/calma.mp3",
                                                           "motivo": "cama leve", "inicio_s": 5, "fim_s": 30}]},
                   sfx=[{"id": "s1", "som": "whoosh", "t": 1.0}])
        t = self.html()
        self.assertIn("<audio", t)
        self.assertIn("#t=5,30", t)
        self.assertIn("Sem música", t)
        self.assertIn("Buscar outra", t)
        self.assertIn("job=Teste/video", t.replace("%2F", "/"))
        self.assertIn('name="sfx" value="s1"', t)
        self.assertIn('name="sfx_ligado"', t)

    def test_salvar_sem_musica_grava_no_plano(self):
        j = self.job("plano")
        self.plano(j, musica={"opcao": "work/musica/x.mp3", "titulo": "X"})
        r = self.client.post("/job/Teste/video/plano", data={"acao": "salvar", "musica": "sem", "escolha_b1": "nenhum",
                                                             "escolha_c1": "c1", "sfx_bloco": "1"})
        self.assertEqual(r.status_code, 302)
        p = P.plano(P.carregar("Teste", "video"))
        self.assertTrue(p["musica"].get("sem"))
        self.assertNotIn("arquivo", p["musica"])
        self.assertFalse(p["sfx_ligado"])

    def test_escolher_faixa_do_cliente_pela_tela(self):
        j = self.job("plano")
        f = self.faixa("clientes/Teste/testeContent/modelos/estilo/assets/musica/bed-calma.mp3")
        self.plano(j)
        t = self.html()
        ident = MB.id_faixa(str(f.relative_to(self.root)))
        self.assertIn(f'value="{ident}"', t)                         # a música do cliente aparece pra escolher
        self.client.post("/job/Teste/video/plano", data={"acao": "salvar", "musica": ident, "escolha_b1": "nenhum", "escolha_c1": "c1"})
        m = P.plano(P.carregar("Teste", "video"))["musica"]
        self.assertEqual((m["escolha"], m["arquivo"]), (ident, str(f.relative_to(self.root))))

    def test_busca_de_musica_do_video_usa_neste_video(self):
        j = self.job("plano")
        f = self.faixa("clientes/Teste/testeContent/modelos/estilo/assets/musica/bed-calma.mp3")
        self.faixa("clientes/Outro/outroContent/modelos/x/assets/musica/nao-aparece.mp3")
        self.plano(j)
        r = self.client.get("/musica?job=Teste/video")
        t = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Usar neste vídeo", t)
        self.assertIn("bed-calma.mp3", t)
        self.assertNotIn("nao-aparece", t)
        r = self.client.post("/musica/usar", data={"job": "Teste/video", "arquivo": str(f.relative_to(self.root)), "fonte": "cliente"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/job/Teste/video#musica"))
        self.assertEqual(P.plano(P.carregar("Teste", "video"))["musica"]["titulo"], "Bed calma")
        outro = self.faixa("clientes/Outro/outroContent/modelos/x/assets/musica/nao-aparece.mp3")
        self.client.post("/musica/usar", data={"job": "Teste/video", "arquivo": str(outro.relative_to(self.root))})
        self.assertEqual(P.plano(P.carregar("Teste", "video"))["musica"]["titulo"], "Bed calma")    # de outro cliente não entra

    def test_formato_com_esteira_so_mostra_o_storyboard(self):
        self.formato("fake", esteira=True)
        j = self.job("plano")
        j["formato"] = "fake"
        j["broll_config"] = {"origem": "misto", "quantidade": 3}
        P.salvar(j)
        self.plano(j)
        (self.root / j["sandbox"] / "storyboard.jpg").write_bytes(b"JPG")
        (self.root / j["sandbox"] / "cenas.json").write_text("{}")   # storyboard feito pela esteira
        t = self.html()
        self.assertIn("Aprovar e fazer o vídeo", t)
        self.assertNotIn("Monte o storyboard de novo", t)
        self.assertNotIn("De onde vêm as cenas", t)
        self.assertNotIn("Criar b-roll", t)
        self.assertNotIn("Criar cena com IA", t)
        self.assertNotIn("Preferências da edição", t)
        self.assertIn('name="escolha_b1" value="b1-1"', t)          # aprovar o storyboard aprova a sugestão que ele mostra
        self.assertIn("storyboard-grande", t)

    def test_som_do_storyboard_e_efeito_que_a_sandbox_nao_tem(self):
        """V2 do Cliente4: o PLANO apontava audio/sfx/tique.mp3 que a sandbox não tinha e o ▶ do tique sumia; música e
        efeitos só eram ouvidos no render. Agora o som vem da base do formato e a previa-som.m4a toca na tela."""
        self.formato("fake", esteira=True)
        tique = self.faixa("formatos/fake/base/audio/sfx/tique.mp3")
        j = self.job("plano")
        j["formato"] = "fake"
        P.salvar(j)
        self.plano(j, sfx=[{"id": "tique", "som": "tique", "titulo": "Tique do relógio", "arquivo": "audio/sfx/tique.mp3"},
                           {"id": "pop", "som": "pop", "titulo": "Pop", "arquivo": "audio/sfx/pop.mp3"}])
        itens = {i["id"]: i["arquivo"] for i in MB.efeitos_do_plano(j, P.plano(j))["itens"]}
        self.assertEqual(itens, {"tique": str(tique.relative_to(self.root)), "pop": ""})   # pop não existe em lugar nenhum
        sb = self.root / j["sandbox"]
        (sb / "storyboard.jpg").write_bytes(b"JPG")
        (sb / "cenas.json").write_text("{}")
        t = self.html()
        self.assertIn('aria-label="Ouvir Tique do relógio"', t)
        self.assertNotIn("previa-som", t)
        (sb / "previa-som.m4a").write_bytes(b"\0" * 64)
        t = self.html()
        self.assertIn("Ouça como vai soar", t)
        self.assertIn("previa-som.m4a", t)

    def test_musica_que_troca_no_meio_e_chips_so_dos_sons_das_cenas(self):
        """V2 refeito do Cliente4: o cenas.json tocava 364 → 1154, mas a tela tinha uma escolha só (m1 = 364 até 1:17) e
        aprovar renderizaria só a 364; o chip "Tique do relógio" aparecia num vídeo sem relógio."""
        self.formato("fake", esteira=True)
        j = self.job("plano")
        j["formato"] = "fake"
        P.salvar(j)
        sb = self.root / j["sandbox"]
        self.faixa(j["sandbox"] + "/work/musica/364.mp3")
        self.faixa(j["sandbox"] + "/work/musica/1154.mp3")
        self.plano(j, musica={"escolha": "m1", "opcoes": [
            {"id": "m1", "arquivo": "work/musica/364.mp3", "inicio_s": 0, "fim_s": 76.96, "motivo": "sombria"},
            {"id": "m2", "arquivo": "work/musica/1154.mp3", "titulo": "Reaching Out", "inicio_s": 0, "fim_s": 118.9}]},
            sfx=[{"id": "typing", "som": "typing", "titulo": "Teclado na frase"},
                 {"id": "tique", "som": "tique", "titulo": "Tique do relógio"}])
        C.gravar_json(sb / "cenas.json", {"musica": [{"arquivo": "audio/musicas/364.mp3", "inicio_s": 0, "de": 0},
                                                    {"arquivo": "audio/musicas/1154.mp3", "inicio_s": 0, "de": 76.96}]})
        (sb / "storyboard.jpg").write_bytes(b"JPG")
        self.assertIn("Tique do relógio", self.html())          # storyboard antigo, sem a lista do motor: mostra tudo
        (sb / "qa").mkdir(exist_ok=True)
        C.gravar_json(sb / "qa/checagem.json", {"numeros": {"efeitos": {"sons_das_cenas": ["typing", "whoosh-short"]}}})
        t = self.html()
        self.assertIn("troca pra Reaching Out em 1:17", t)
        self.assertIn('name="sfx" value="typing"', t)
        self.assertNotIn("Tique do relógio", t)
        self.client.post("/job/Teste/video/plano", data={"acao": "salvar", "musica": "m1", "escolha_b1": "nenhum", "escolha_c1": "c1"})
        m = P.plano(P.carregar("Teste", "video"))["musica"]
        self.assertEqual(m["escolha"], "m1")
        self.assertEqual([(Path(x["arquivo"]).stem, x["de"]) for x in m["trechos"]], [("364", 0), ("1154", 76.96)])

    def test_esteira_nao_diz_so_o_seu_bruto_nem_escolher_takes(self):
        """Documentário nasce com broll 'nenhum', mas é cheio de construções: o canto diz 'Passos do estilo'."""
        self.formato("fake", esteira=True)
        j = self.job("plano")
        j.update(formato="fake", broll_config={"origem": "nenhum", "quantidade": 0})
        P.salvar(j)
        self.plano(j)
        t = self.html()
        self.assertIn("Passos do estilo", t)
        self.assertNotIn("Só o seu bruto", t)
        self.assertIn("Aprovar o storyboard", t)                    # selo do status
        self.assertNotIn("Escolher takes", t)

    def test_esteira_sem_cenas_json_pede_storyboard_novo(self):
        """Vídeo feito antes da esteira (sem cenas.json): nada de aprovar o storyboard velho; o botão monta de novo."""
        self.formato("fake", esteira=True)
        j = self.job("concluido")
        j["formato"] = "fake"
        P.salvar(j)
        self.plano(j)
        (self.root / j["sandbox"] / "storyboard.jpg").write_bytes(b"JPG")
        t = self.html()
        self.assertNotIn("Aprovar e fazer o vídeo", t)
        self.assertIn("Monte o storyboard de novo", t)
        self.assertIn('formaction="/job/Teste/video/analisar"', t)
        self.assertNotIn('name="sfx_ligado"', t)                    # música e efeitos vêm com o storyboard novo
        with patch.object(P, "analisar") as analisar:
            r = self.client.post("/job/Teste/video/analisar", data={"confirmar_execucao": "1", "escolha_b1": "b1-1"})
        self.assertEqual(r.status_code, 302)
        analisar.assert_called_once_with("Teste", "video")

    def test_formato_sem_esteira_continua_com_as_preferencias(self):
        self.formato("simples")
        j = self.job("plano")
        j["formato"] = "simples"
        P.salvar(j)
        self.plano(j)
        t = self.html()
        self.assertIn("De onde vêm as cenas", t)
        self.assertIn("Cenas reais (internet, grátis)", t)
        self.assertIn("Aprovar e fazer o vídeo", t)
        self.assertNotIn("Produzir", t.split("Trecho por trecho", 1)[1].split("</form>", 1)[0])

    def test_esteira_nao_zera_as_cenas_ao_montar(self):
        self.formato("fake", esteira=True)
        j = self.job("novo")
        j.update(formato="fake", broll_config={"origem": "busca", "quantidade": 4})
        P.salvar(j)
        with patch.object(P, "analisar"):
            self.client.post("/job/Teste/video/analisar", data={"confirmar_execucao": "1"})
        self.assertEqual(P.carregar("Teste", "video")["broll_config"]["origem"], "busca")

    def test_ia_so_em_cena_de_apoio_e_capa_nunca_e_o_sheet(self):
        self.formato("simples")
        j = self.job("plano")
        j.update(formato="simples", broll_config={"origem": "misto", "quantidade": 3})
        P.salvar(j)
        self.plano(j)
        t = self.html()
        self.assertEqual(t.count("Criar cena com IA (paga, você vê o custo antes)"), 1)   # só no b1, nunca no card
        card = t.split('id="c1"', 1)[1].split('class="beat"', 1)[0]
        self.assertNotIn("Criar cena com IA", card)
        self.assertNotIn('class="gif-op" src="/arquivo/' + j["sandbox"] + '/brolls/b1-1-sheet.jpg"', t)
        self.assertIn("Prévia indisponível", t)
        self.assertIn('class="sheet"', t)                            # a folha fica só em "frames"
        self.assertIn('<b class="destaque-card"', t)
        self.assertIn(">vergonha</b>", t)
        self.assertNotIn("*vergonha*", t)
        self.assertIn("Cena de apoio", t)
        self.assertIn("Frase na tela", t)

    def test_titulo_quando_o_storyboard_ja_foi_aprovado(self):
        j = self.job("plano_aprovado")
        self.plano(j)
        self.assertIn("Storyboard aprovado · fazendo o vídeo", self.html())

    def test_buscar_com_so_ia_avisa_que_virou_as_duas(self):
        j = self.job("plano")
        j["broll_config"] = {"origem": "ia", "quantidade": 3}
        P.salvar(j)
        self.plano(j)
        with patch.object(P, "rebuscar"):
            r = self.client.post("/job/Teste/video/plano", data={"acao": "buscar", "confirmar_execucao": "1",
                                                                 "escolha_b1": "nenhum", "escolha_c1": "c1"},
                                 follow_redirects=True)
        self.assertIn("As duas", r.get_data(as_text=True))
        self.assertEqual(P.carregar("Teste", "video")["broll_config"]["origem"], "misto")

    def test_chip_de_cenas_vira_preferencia_da_edicao(self):
        self.formato("simples")
        with patch.object(simples._fmt, "usar", return_value=("Teste", "estilo")):
            r = self.client.post("/criar", data={"formato": "simples", "cliente": "Teste", "titulo": "Chip",
                                                 "escolha__cenas": "B-roll real (grátis)",
                                                 "videos": (io.BytesIO(b"raw"), "raw.mp4")})
        self.assertEqual(r.status_code, 302)
        j = P.carregar("Teste", "chip")
        self.assertEqual(j["broll_config"]["origem"], "busca")
        self.assertEqual(simples._cenas_da_chip("Gerada por IA (pago, centavos)")["origem"], "ia")
        self.assertEqual(simples._cenas_da_chip("Sem cenas de apoio")["origem"], "nenhum")
        self.assertIsNone(simples._cenas_da_chip(""))


if __name__ == "__main__":
    unittest.main()
