"""Velocidade (30-out-2026): a tela não pode travar. Memo curto, cache dos estáticos, tarefas em segundo plano, nada de pasta fixa nos testes."""
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1]
RAIZ = APP.parent
sys.path.insert(0, str(APP / "ferramentas"))
sys.path.insert(0, str(APP / "interface"))
import _comum  # noqa: E402
import custos  # noqa: E402
import preparar  # noqa: E402


class MemoCurto(unittest.TestCase):
    def test_dentro_do_bloco_varre_uma_vez(self):
        with _comum.memo_curto():
            a, b = _comum.clientes(), _comum.clientes()
        self.assertIs(a, b)

    def test_fora_do_bloco_sempre_le_de_novo(self):
        self.assertIsNot(_comum.clientes(), _comum.clientes())

    def test_bloco_acaba_e_o_memo_some(self):
        with _comum.memo_curto():
            _comum.clientes()
        self.assertIsNone(getattr(_comum._memo, "d", None))

    def test_lista_de_videos_nao_repete_a_varredura(self):
        import editor
        import formatos
        n = {"c": 0}
        real = _comum.clientes.__wrapped__

        def conta():
            n["c"] += 1
            return real()
        with mock.patch.object(formatos, "_clientes", _comum.memoizado(conta)), _comum.memo_curto():
            editor.videos()
        self.assertLessEqual(n["c"], 5, "a lista de vídeos varreu clientes/ várias vezes (era ~6 mil)")

    def test_lista_de_videos_abre_rapido(self):
        import editor
        t = time.time()
        with _comum.memo_curto():
            editor.videos()
        self.assertLess(time.time() - t, 3.0)


class SegundoPlano(unittest.TestCase):
    def test_tarefa_nao_roda_duas_vezes_junto(self):
        solta = threading.Event()
        chamadas = []
        self.assertTrue(preparar._tarefa("t-vel", lambda: (chamadas.append(1), solta.wait(5))))
        self.assertTrue(preparar.fazendo("t-vel"))
        self.assertFalse(preparar._tarefa("t-vel", lambda: chamadas.append(2)))
        solta.set()
        for _ in range(50):
            if not preparar.fazendo("t-vel"):
                break
            time.sleep(.05)
        self.assertEqual(chamadas, [1])

    def test_erro_na_tarefa_nao_derruba_nem_trava(self):
        def quebra():
            raise RuntimeError("x")
        with mock.patch("sys.stderr"):
            preparar._tarefa("t-erro", quebra)
            for _ in range(50):
                if not preparar.fazendo("t-erro"):
                    break
                time.sleep(.05)
        self.assertFalse(preparar.fazendo("t-erro"))

    def test_capa_de_arquivo_que_nao_existe_nao_faz_nada(self):
        self.assertFalse(preparar.capa(Path("/nao/existe.mp4")))
        self.assertFalse(preparar.capa_pronta(Path("/nao/existe.mp4")))

    def test_ccusage_primeira_vez_nao_espera_a_rede(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(custos, "CACHE_CCUSAGE", Path(d)), \
                mock.patch.object(custos, "_atualizar_ccusage") as bg, mock.patch.object(custos.subprocess, "run", side_effect=AssertionError("rede na tela")):
            r = custos.claude_code_conversas(None, None)
        self.assertEqual(r["erro"], "preparando…")
        bg.assert_called_once()

    def test_ccusage_cache_velho_mostra_o_que_tem(self):
        import json
        import os
        with tempfile.TemporaryDirectory() as d, mock.patch.object(custos, "CACHE_CCUSAGE", Path(d)), \
                mock.patch.object(custos, "_atualizar_ccusage") as bg, mock.patch.object(custos, "_sessoes_do_estudio", return_value={"a"}):
            c = Path(d) / "ccusage_tudo.json"
            c.write_text(json.dumps({"session": [{"agent": "claude", "period": "a", "totalCost": 2.5}]}))
            os.utime(c, (1, 1))   # velhíssimo
            r = custos.claude_code_conversas(None, None)
        self.assertEqual((r["n"], r["usd"], r["erro"]), (1, 2.5, ""))
        bg.assert_called_once()


class Estaticos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import servidor
        cls.c = servidor.app.test_client()

    def test_css_com_versao_fica_no_navegador(self):
        r = self.c.get("/static/estilo.css?v=123")
        self.assertIn("immutable", r.headers.get("Cache-Control", ""))

    def test_pagina_continua_sem_cache(self):
        r = self.c.get("/api/health")
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")


class Carregar_so_o_necessario(unittest.TestCase):
    T = APP / "interface" / "templates"

    def test_lista_de_videos_so_baixa_no_play(self):
        for nome in ("aprovar.html", "editor_lista.html", "estudar.html", "cliente.html", "estilo_novo.html"):
            txt = (self.T / nome).read_text(encoding="utf-8")
            for tag in re.findall(r"<video\b[^>]*>", txt):
                self.assertNotIn('preload="metadata"', tag, f"{nome}: {tag[:90]}")

    def test_imagens_lazy(self):
        falta = []
        for f in self.T.glob("*.html"):
            for tag in re.findall(r"<img\b[^>]*>", f.read_text(encoding="utf-8")):
                if "loading=" not in tag:
                    falta.append(f.name)
        self.assertEqual(falta, [])

    def test_render_do_editorial_espera_so_o_html(self):
        txt = (RAIZ / "formatos" / "editorial" / "base" / "render.py").read_text(encoding="utf-8")
        self.assertIn('wait_until="domcontentloaded"', txt)


class TestesSemPastaFixa(unittest.TestCase):
    def test_nenhum_teste_usa_pasta_temporaria_fixa(self):
        for f in (APP / "tests").glob("test_*.py"):
            if f.name == Path(__file__).name:
                continue
            txt = f.read_text(encoding="utf-8")
            for linha in txt.splitlines():
                if re.match(r"\s*TMP\s*=", linha):
                    self.assertIn("mkdtemp", linha, f"{f.name}: pasta temporária fixa -> {linha.strip()[:80]}")


if __name__ == "__main__":
    unittest.main()
