"""VoiceStudio sem janela: o Estúdio sobe só o backend (nunca o aplicativo), diz a verdade sobre o estado da voz
(ligando, ocupado, desligada, instalar) e a tela Vozes mostra a mensagem certa. Backend simulado em localhost; nada abre de verdade."""
import json
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import voicestudio as V


class FalsoBackend:
    """/health e /v1/audio/speech simulados; `modo` muda a resposta."""
    def __init__(self):
        self.modo = {"health": (200, {"status": "ok"}), "fala": (200, b"mp3")}
        modo = self.modo

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _resp(self, cod, corpo, extra=None):
                dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
                self.send_response(cod)
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):
                self._resp(*modo["health"])

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                cod, corpo = modo["fala"]
                self._resp(cod, corpo, {"Retry-After": "30"} if cod == 503 else None)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def parar(self):
        self.srv.shutdown()
        self.srv.server_close()


def porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        V._ABRIU["quando"] = 0.0
        V._SUBIU.update(quando=0.0, proc=None)
        V.TESTANDO["forcar"] = True
        self.addCleanup(V.TESTANDO.update, forcar=False)
        for alvo, valor in (("EM_CURSO", t / "em-curso"), ("LOG_SEM_TELA", t / "voz.log"), ("RUNTIME", t / "runtime")):
            p = mock.patch.object(V, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        self.runtime = t / "runtime"

    def instalar(self):
        proj = self.runtime / "project"
        (proj / ".venv" / "bin").mkdir(parents=True)
        (proj / ".venv" / "bin" / "python").write_text("")
        (proj / "backend").mkdir()
        (proj / "backend" / "main.py").write_text("")
        (proj / ".runtime-ready").write_text("x")

    def url(self, porta):
        p = mock.patch.dict("os.environ", {"VOICESTUDIO_URL": f"http://127.0.0.1:{porta}"})
        p.start()
        self.addCleanup(p.stop)


class EstadoDaVoz(Base):
    def test_no_ar(self):
        fb = FalsoBackend(); self.addCleanup(fb.parar); self.url(fb.porta)
        self.assertEqual(V.estado()["estado"], "no_ar")

    def test_ligando_quando_o_health_devolve_503_starting(self):
        fb = FalsoBackend(); self.addCleanup(fb.parar); self.url(fb.porta)
        fb.modo["health"] = (503, {"status": "starting"})
        e = V.estado()
        self.assertEqual(e["estado"], "ligando")
        self.assertEqual(e["texto"], "Ligando a voz (uns 10 s)…")

    def test_ocupado_de_verdade_quando_o_estudio_esta_gerando(self):
        fb = FalsoBackend(); self.addCleanup(fb.parar); self.url(fb.porta)
        marca = V._marcar_em_curso()
        self.assertEqual(V.estado()["estado"], "ocupado")
        self.assertEqual(V.estado()["texto"], "Gerando outra voz, já volto.")
        V._soltar_em_curso(marca)
        self.assertEqual(V.estado()["estado"], "no_ar")

    def test_ocupado_quando_a_porta_atende_mas_nao_responde(self):
        with mock.patch.object(V.urllib.request, "urlopen", side_effect=socket.timeout("lento")):
            self.assertEqual(V._health(), "ocupado")
            self.assertEqual(V.estado()["estado"], "ocupado")

    def test_fora_do_ar_tem_botao_ligar_quando_o_runtime_existe(self):
        self.url(porta_livre()); self.instalar()
        e = V.estado()
        self.assertEqual(e["estado"], "fora")
        self.assertTrue(e["pode_ligar"])

    def test_runtime_nunca_instalado_pede_pra_abrir_o_voicestudio_uma_vez(self):
        self.url(porta_livre())
        e = V.estado()
        self.assertEqual(e["estado"], "instalar")
        self.assertIn("uma vez pra instalar", e["texto"])
        self.assertFalse(e["pode_ligar"])


class SobeSemJanela(Base):
    def test_fora_do_ar_sobe_o_backend_sem_janela_e_nao_abre_o_app(self):
        self.url(3900); self.instalar()
        respostas = iter(["fora", "fora", "fora"])
        with mock.patch.object(V, "_health", side_effect=lambda: next(respostas, "fora")), \
                mock.patch.object(V, "no_ar", side_effect=[False, False, False, True]), \
                mock.patch.object(V.subprocess, "Popen") as pop, mock.patch.object(V.subprocess, "run") as run, mock.patch("time.sleep"):
            pop.return_value.poll.return_value = None
            self.assertTrue(V.garantir_no_ar(60))
        run.assert_not_called()                                   # o aplicativo (open -a) não é chamado
        args, kw = pop.call_args
        self.assertEqual(args[0][1:], ["-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "3900"])
        self.assertTrue(args[0][0].endswith(".venv/bin/python"))
        self.assertTrue(kw["start_new_session"])
        self.assertEqual(kw["env"]["OMNIVOICE_PORT"], "3900")
        self.assertTrue(kw["cwd"].endswith("project"))

    def test_ligando_nao_sobe_outro(self):
        self.url(3900); self.instalar()
        with mock.patch.object(V, "_health", return_value="ligando"), mock.patch.object(V, "no_ar", side_effect=[False, True]), \
                mock.patch.object(V.subprocess, "Popen") as pop, mock.patch.object(V.subprocess, "run") as run, mock.patch("time.sleep"):
            self.assertTrue(V.garantir_no_ar(60))
        pop.assert_not_called(); run.assert_not_called()

    def test_runtime_nao_instalado_abre_o_aplicativo_como_plano_b(self):
        self.url(3900)
        with mock.patch.object(V, "_health", return_value="fora"), mock.patch.object(V, "no_ar", return_value=False), \
                mock.patch.object(V.subprocess, "Popen") as pop, mock.patch.object(V.subprocess, "run") as run, mock.patch("time.sleep"):
            self.assertFalse(V.garantir_no_ar(60))
        pop.assert_not_called()
        self.assertEqual(run.call_args[0][0], ["open", "-g", "-j", "-a", "VoiceStudio"])

    def test_backend_que_morre_ao_subir_cai_no_plano_b(self):
        self.url(3900); self.instalar()
        ticks = iter([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30])
        with mock.patch.object(V, "_health", return_value="fora"), mock.patch.object(V, "no_ar", side_effect=[False] * 3 + [True]), \
                mock.patch.object(V.subprocess, "Popen") as pop, mock.patch.object(V.subprocess, "run") as run, mock.patch("time.sleep"):
            pop.return_value.poll.return_value = 1                # saiu na hora
            self.assertTrue(V.garantir_no_ar(60))
        self.assertEqual(run.call_args[0][0], ["open", "-g", "-j", "-a", "VoiceStudio"])

    def test_url_de_outra_maquina_nunca_sobe_nada(self):
        with mock.patch.dict("os.environ", {"VOICESTUDIO_URL": "http://10.0.0.5:3900"}):
            self.instalar()
            with mock.patch.object(V.subprocess, "Popen") as pop:
                self.assertFalse(V.subir_sem_janela())
            pop.assert_not_called()

    def test_nao_lanca_duas_vezes_em_90_segundos(self):
        self.url(3900); self.instalar()
        with mock.patch.object(V.subprocess, "Popen") as pop:
            pop.return_value.poll.return_value = None
            V.subir_sem_janela(); V.subir_sem_janela()
        self.assertEqual(pop.call_count, 1)

    def test_botao_ligar_lanca_e_devolve_ligando(self):
        self.url(porta_livre()); self.instalar()
        with mock.patch.object(V.subprocess, "Popen") as pop:
            pop.return_value.poll.return_value = None
            e = V.ligar_em_segundo_plano()
        self.assertEqual(e["estado"], "ligando")
        self.assertEqual(pop.call_count, 1)

    def test_sem_nada_o_subir_nao_roda_em_teste(self):
        V.TESTANDO["forcar"] = False
        self.instalar()
        with mock.patch.object(V.subprocess, "Popen") as pop:
            self.assertFalse(V.subir_sem_janela())
        pop.assert_not_called()


class MensagensDeErro(Base):
    def test_503_com_retry_after_vira_gerando_outra_voz(self):
        fb = FalsoBackend(); self.addCleanup(fb.parar); self.url(fb.porta)
        fb.modo["fala"] = (503, {"detail": "busy"})
        with self.assertRaises(V.VozOcupada) as e:
            V._pedido("oi", "default", "mp3")
        self.assertIn("Gerando outra voz, já volto", str(e.exception))
        self.assertEqual(V.estado()["estado"], "ocupado")           # a tela, ao perguntar, vê o mesmo

    def test_porta_fechada_vira_fora_do_ar_e_nao_ocupado(self):
        self.url(porta_livre())
        with self.assertRaises(V.VozForaDoAr):
            V._pedido("oi", "default", "mp3")

    def test_explicar_usa_o_estado(self):
        self.url(porta_livre()); self.instalar()
        self.assertIn("desligada", V.explicar(ValueError("<urlopen error [Errno 61]>")))
        fb = FalsoBackend(); self.addCleanup(fb.parar); self.url(fb.porta)
        self.assertEqual(V.explicar(ValueError("outro erro")), "outro erro")
        self.assertEqual(V.explicar(V.VozOcupada("x")), "Gerando outra voz, já volto.")

    def test_falar_fora_do_ar_nao_instalado_manda_abrir_uma_vez(self):
        self.url(porta_livre())
        with mock.patch.object(V, "garantir_no_ar", return_value=False):
            with self.assertRaises(V.VozForaDoAr) as e:
                V.falar("oi", Path(self.tmp.name) / "x.mp3")
        self.assertIn("uma vez pra instalar", str(e.exception))


class TelaVozes(Base):
    def test_rotas_de_estado_e_ligar(self):
        import servidor
        c = servidor.app.test_client()
        with mock.patch.object(V, "estado", return_value={"estado": "ligando", "texto": V.MSG_LIGANDO, "pode_ligar": False}):
            j = c.get("/api/voz/estado").get_json()
            self.assertEqual(j["estado"], "ligando")
            self.assertEqual(j["texto"], "Ligando a voz (uns 10 s)…")
        with mock.patch.object(V, "ligar_em_segundo_plano", return_value={"estado": "ligando", "texto": V.MSG_LIGANDO, "pode_ligar": False}) as lig:
            self.assertEqual(c.post("/api/voz/ligar").get_json()["estado"], "ligando")
            lig.assert_called_once()

    def test_pagina_mostra_cada_situacao(self):
        import servidor
        c = servidor.app.test_client()
        casos = {"fora": ("A voz está desligada.", True), "ocupado": ("Gerando outra voz, já volto.", False),
                 "ligando": ("Ligando a voz (uns 10 s)…", False), "instalar": ("Abra o VoiceStudio uma vez pra instalar a voz.", False)}
        for est, (txt, pode) in casos.items():
            with mock.patch.object(V, "estado", return_value={"estado": est, "texto": txt, "pode_ligar": pode}), \
                    mock.patch.object(V, "no_ar", return_value=False), mock.patch.object(V, "vozes", return_value=[]):
                r = c.get("/vozes")
                self.assertEqual(r.status_code, 200, est)
                self.assertIn(txt, r.get_data(as_text=True), est)
                self.assertIn(f'data-estado="{est}"', r.get_data(as_text=True))

    def test_nao_sobra_a_frase_antiga_de_ocupado_pra_tudo(self):
        raiz = Path(__file__).resolve().parents[1] / "interface"
        for f in list((raiz / "templates").glob("*.html")) + list((raiz / "static").glob("vozes-ui.js")):
            self.assertNotIn("VoiceStudio ocupado, tente de novo", f.read_text(), f.name)


if __name__ == "__main__":
    unittest.main()
