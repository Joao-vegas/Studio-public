"""Conectar uma chave em Configurações grava em app/.env (nunca no real nos testes) e nunca mostra o valor."""
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ferramentas"))
import chaves

SEGREDO = "kie-teste-0123456789-ZZ99"


class Gravar(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.env = Path(self.t.name) / "app.env"
        self.env.write_text("GROQ_API_KEY=gsk-original-0000\n")
        self.p = patch.object(chaves, "ENV_APP", self.env); self.p.start()   # NUNCA o app/.env real

    def tearDown(self): self.p.stop(); self.t.cleanup()

    def test_grava_sem_apagar_as_outras_e_so_mostra_o_final(self):
        fim = chaves.gravar_chave("kie_api_key", SEGREDO, espelhar=False)
        self.assertEqual(fim, "…ZZ99")
        d = chaves.ler_env(self.env)
        self.assertEqual(d["KIE_API_KEY"], SEGREDO)
        self.assertEqual(d["GROQ_API_KEY"], "gsk-original-0000")
        self.assertEqual(oct(self.env.stat().st_mode & 0o777), "0o600")

    def test_recusa_nome_desconhecido_valor_vazio_e_com_espaco(self):
        for nome, valor in (("ROOT_PASSWORD", SEGREDO), ("KIE_API_KEY", ""), ("KIE_API_KEY", "com espaco no meio 123"), ("KIE_API_KEY", "curta")):
            with self.assertRaises(ValueError) as c: chaves.gravar_chave(nome, valor, espelhar=False)
            self.assertNotIn(SEGREDO, str(c.exception))

    def test_gemini_nao_e_mais_conectado_pela_tela(self):
        """O Gemini saiu do Estúdio (29-out-2026): a tela recusa a chave dele. As que já estão no app/.env não são tocadas."""
        with self.assertRaises(ValueError): chaves.gravar_chave("GEMINI_API_KEY_8", SEGREDO, espelhar=False)
        self.assertNotIn("GEMINI_API_KEY_8", chaves.ler_env(self.env))


if __name__ == "__main__":
    unittest.main()
