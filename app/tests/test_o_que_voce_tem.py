"""Novo vídeo: "O que você tem?" (vídeo gravado · só a minha voz · só o roteiro) e a faixa "Rodando agora" do Esperando você."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import servidor  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[1] / "interface" / "templates"


class TestOQueVoceTem(unittest.TestCase):
    def setUp(self):
        self.c = servidor.app.test_client()

    def test_tres_cartoes_e_meu_audio_saiu_da_voz(self):
        html = self.c.get("/criar-agora").get_data(as_text=True)
        for t in ('data-tenho="video"', 'data-tenho="audio"', 'data-tenho="roteiro"', "Vídeo gravado (MP4)", "Só a minha voz (MP3)", "Só o roteiro"):
            self.assertIn(t, html)
        self.assertNotIn("nv-meu-audio-card", html)          # "Meu áudio" não fica mais escondido dentro de "Voz da narração"
        self.assertEqual(html.count('name="audio_narracao"'), 1)
        self.assertIn("Baixar a transcrição", html)

    def test_transcrever_audio(self):
        fake = {"segments": [{"text": " Primeira frase. "}, {"text": "Segunda frase."}], "text": "x", "words": []}
        with patch("fala.groq_transcrever", return_value=fake), patch("corte.chave_groq", return_value="k"):
            r = self.c.post("/api/transcrever-audio", data={"audio": (io.BytesIO(b"abc"), "a.mp3")}, content_type="multipart/form-data")
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["texto"], "Primeira frase.\nSegunda frase.")
        self.assertEqual(self.c.post("/api/transcrever-audio").status_code, 400)

    def test_faixa_rodando_agora(self):
        item = {"estado": "trabalhando", "cliente": "Cliente3", "slug": "teste-x", "titulo": "Vídeo de teste", "etapa": "storyboard",
                "atual": {"texto": "Montando o storyboard"}, "ha": "há 1 min"}
        with patch("andamento.listar", return_value=[item]):
            html = self.c.get("/aprovar").get_data(as_text=True)
        self.assertIn("Rodando agora", html)
        self.assertIn("Vídeo de teste", html)
        self.assertIn("/andamento/Cliente3/teste-x", html)
        with patch("andamento.listar", return_value=[]):
            self.assertNotIn("Rodando agora", self.c.get("/aprovar").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
