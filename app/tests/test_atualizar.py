"""Atualizações: a lista cobre todas as ferramentas do README, item "auto": False nunca instala sozinho,
e a tela já mostra item novo antes da próxima conferência. Nada de rede: o _r é trocado por um falso."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import atualizar as U

README = Path(__file__).resolve().parents[2] / "README.md"


class Falso:
    """Responde como pip/npm responderiam e guarda cada comando pedido."""
    def __init__(self, respostas):
        self.respostas, self.pedidos = respostas, []

    def __call__(self, cmd, cwd=None, timeout=900):
        self.pedidos.append(cmd)
        for chave, resp in self.respostas.items():
            if chave in " ".join(map(str, cmd)):
                return resp
        return 0, ""


class TestAtualizar(unittest.TestCase):
    def setUp(self):
        p = patch.object(U, "_video_rodando", lambda: False)   # o teste não depende de haver vídeo de verdade rodando
        p.start(); self.addCleanup(p.stop)

    def test_lista_cobre_as_ferramentas_do_readme(self):
        texto = README.read_text(encoding="utf-8")
        nomes = {i["nome"] for i in U.MANIFESTO}
        for ferramenta in ("Claude Code", "Codex", "HyperFrames", "Three.js", "Playwright", "ffmpeg",
                           "auto-editor", "yt-dlp", "get-brolls", "mlx-whisper", "rembg", "OpenCV",
                           "sentence-transformers", "Flask"):
            self.assertIn(ferramenta, texto, f"{ferramenta} sumiu do README")
            self.assertIn(ferramenta, nomes, f"{ferramenta} está no README mas não em Atualizações")
        self.assertTrue(any(i.get("pacote") == "anthropic" for i in U.MANIFESTO))

    def test_pip_sem_auto_so_avisa(self):
        f = Falso({"pip show": (0, "Name: rembg\nVersion: 2.0.85\n"), "index versions": (0, "rembg (2.0.90)\n")})
        with patch.object(U, "_r", f):
            r = U._pip({"nome": "rembg", "tipo": "pip", "pacote": "rembg", "pra": "x", "auto": False})
        self.assertEqual((r["estado"], r["versao"], r["nova"]), ("disponível", "2.0.85", "2.0.90"))
        self.assertFalse(any("install" in c for c in f.pedidos), "não pode instalar sozinho")

    def test_pip_automatico_usa_teste_leve(self):
        f = Falso({"pip show": (0, "Version: 1.0.0\n"), "index versions": (0, "algo (1.0.1)\n")})
        with patch.object(U, "_r", f):
            r = U._pip({"nome": "algo", "tipo": "pip", "pacote": "algo", "pra": "x"})
        self.assertEqual(r["estado"], "atualizada")
        self.assertFalse(any("discover" in c for c in f.pedidos), "o discover inteiro trava")

    def test_npm_sem_auto_so_avisa(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d) / "node_modules" / "three"
            mod.mkdir(parents=True)
            (mod / "package.json").write_text('{"version": "0.186.1"}')
            f = Falso({"view three": (0, "0.187.0\n")})
            with patch.object(U, "_r", f), patch.object(U, "RAIZ", Path(d)):
                r = U._npm({"nome": "Three.js", "tipo": "npm", "pasta": ".", "pacotes": ["three"], "pra": "x", "auto": False})
        self.assertEqual((r["estado"], r["nova"]), ("disponível", "0.187.0"))
        self.assertFalse(any("install" in c for c in f.pedidos))

    def test_cli_global(self):
        ls = json.dumps({"dependencies": {"@openai/codex": {"version": "0.162.0"}}})
        f = Falso({"ls -g": (0, ls), "view @openai/codex": (0, "0.163.0\n")})
        with patch.object(U, "_r", f):
            r = U._npm_global({"nome": "Codex", "tipo": "npm-global", "pacote": "@openai/codex", "pra": "x", "auto": False})
        self.assertEqual((r["estado"], r["versao"], r["nova"]), ("disponível", "0.162.0", "0.163.0"))
        f = Falso({"ls -g": (0, "{}"), "view": (0, "1.0.0\n")})
        with patch.object(U, "_r", f):
            self.assertEqual(U._npm_global({"pacote": "x"})["estado"], "não instalado")

    def test_versao_pequena_com_video_rodando_fica_na_fila_e_nao_instala(self):
        ls = json.dumps({"dependencies": {"@openai/codex": {"version": "0.163.0"}}})
        f = Falso({"ls -g": (0, ls), "view @openai/codex": (0, "0.164.0\n")})
        with patch.object(U, "_r", f), patch.object(U, "_video_rodando", lambda: True):
            r = U._npm_global({"nome": "Codex", "tipo": "npm-global", "pacote": "@openai/codex", "bin": "codex", "pra": "x"})
        self.assertEqual((r["estado"], r["nova"]), ("na fila", "0.164.0"))
        self.assertFalse(any("install" in c for c in f.pedidos))

    def test_cli_pequena_instala_sozinha_e_grande_espera(self):
        ls = json.dumps({"dependencies": {"@openai/codex": {"version": "0.163.0"}}})
        f = Falso({"ls -g": (0, ls), "view @openai/codex": (0, "0.164.0\n"), "prefix": (0, "/x\n")})
        with patch.object(U, "_r", f):
            r = U._npm_global({"nome": "Codex", "tipo": "npm-global", "pacote": "@openai/codex", "bin": "codex", "pra": "x"})
        self.assertEqual(r["estado"], "atualizada")
        f = Falso({"ls -g": (0, ls), "view @openai/codex": (0, "1.0.0\n")})
        with patch.object(U, "_r", f):
            r = U._npm_global({"nome": "Codex", "tipo": "npm-global", "pacote": "@openai/codex", "bin": "codex", "pra": "x"})
        self.assertEqual(r["estado"], "segurada")
        self.assertFalse(any("install" in c for c in f.pedidos))

    def test_brew_revisao_nao_e_versao_nova(self):
        info = json.dumps({"formulae": [{"installed": [{"version": "9.0.2_1"}], "versions": {"stable": "9.0.2"}}]})
        with patch.object(U, "_r", Falso({"info": (0, info)})):
            self.assertEqual(U._brew({"pacote": "ffmpeg", "auto": False})["estado"], "em dia")

    def test_voicestudio_app_nunca_instala_so_avisa(self):
        import io
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(U, "_r", Falso({"defaults": (0, "0.5.6\n")})), \
                patch("urllib.request.urlopen", lambda *a, **k: R(b'{"tag_name": "v0.5.7"}')), patch.object(U.subprocess, "run") as run:
            r = U._app(next(i for i in U.MANIFESTO if i["nome"] == "VoiceStudio"))
        self.assertEqual((r["estado"], r["versao"], r["nova"]), ("disponível", "0.5.6", "0.5.7"))
        run.assert_not_called()

    def test_manifesto_tem_voicestudio_gerador_e_tesseract(self):
        nomes = {i["nome"] for i in U.MANIFESTO}
        self.assertTrue({"VoiceStudio", "Gerador de imagem e vídeo", "tesseract", "get-brolls", "yt-dlp"} <= nomes)

    def test_botao_pip_falhou_volta_tudo(self):
        """Versão nova instalada, teste falha: desfaz o pacote E a dependência que subiu junto."""
        fotos = iter([{"venv": {}, "usuario": {"rembg": "2.0.85", "numpy": "2.4.2"}, "sistema": {}},
                      {"venv": {}, "usuario": {"rembg": "2.0.90", "numpy": "2.5.0", "novo": "1.0"}, "sistema": {}}])
        esc = [("venv", Path("/v"), ["pipv"], []), ("usuario", Path("/u"), ["pipu"], ["--user", "--break-system-packages"]),
               ("sistema", Path("/s"), ["pips"], ["--break-system-packages"])]
        f = Falso({"pip show": (0, "Version: 2.0.85\nLocation: /u\n"), "index versions": (0, "rembg (2.0.90)\n")})
        with patch.object(U, "_r", f), patch.object(U, "_escopos", lambda: esc), \
             patch.object(U, "_foto", lambda: next(fotos)), patch.object(U, "_testar", lambda item: (False, "quebrou")):
            r = U._pip({"nome": "rembg", "tipo": "pip", "pacote": "rembg", "pra": "x", "auto": False}, forcar=True)
        self.assertEqual((r["estado"], r["versao"]), ("segurada", "2.0.85"))
        self.assertIn(["pipu", "install", "-q", "--user", "--break-system-packages", "rembg==2.0.90"], f.pedidos)
        self.assertIn(["pipu", "uninstall", "-y", "--break-system-packages", "novo"], f.pedidos)
        volta = next(c for c in f.pedidos if "--no-deps" in c)
        self.assertEqual(sorted(volta[-2:]), ["numpy==2.4.2", "rembg==2.0.85"])

    def test_botao_pip_passou_reinicia(self):
        esc = [("sistema", Path("/s"), ["pips"], ["--break-system-packages"])]
        f = Falso({"pip show": (0, "Version: 3.1.3\nLocation: /s\n"), "index versions": (0, "flask (3.2.0)\n")})
        with patch.object(U, "_r", f), patch.object(U, "_escopos", lambda: esc), \
             patch.object(U, "_foto", lambda: {}), patch.object(U, "_testar", lambda item: (True, "")):
            r = U._pip({"nome": "Flask", "tipo": "pip", "pacote": "flask", "pra": "x", "auto": False}, forcar=True)
        self.assertEqual((r["estado"], r["versao"], r.get("_reiniciar")), ("atualizada", "3.2.0", True))

    def test_botao_recusa_quando_ocupado_ou_git(self):
        with patch.object(U, "ocupado", lambda: "tem vídeo sendo feito agora"), patch.object(U, "subprocess") as sp:
            self.assertIn("vídeo sendo feito", U.disparar_item("rembg"))
            self.assertIn("não tem botão", U.disparar_item("get-brolls"))
            self.assertIn("não tem botão", U.disparar_item("inventado"))
            sp.Popen.assert_not_called()

    def test_tela_mostra_botao_so_onde_tem_versao_nova(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
        import servidor
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "atualizacoes.json"
            arq.write_text(json.dumps({"quando": "2026-10-10 12:19", "itens": [
                {"nome": "rembg", "versao": "2.0.85", "nova": "2.0.90", "estado": "disponível"},
                {"nome": "ffmpeg", "versao": "8.0.1", "nova": "9.0.2", "estado": "disponível"},
                {"nome": "Flask", "versao": "3.1.3", "nova": "", "estado": "em dia"}]}))
            with patch.object(U, "ESTADO", arq), patch.object(U, "TRAVA", Path(d) / "x.pid"), patch.object(U, "ocupado", lambda: ""):
                html = servidor.app.test_client().get("/config").get_data(as_text=True)
        bloco = html[html.index('id="atualizacoes"'):html.index("Conferir agora")]
        self.assertEqual(bloco.count('name="nome" value="'), 2)
        self.assertIn('value="rembg"', bloco)
        self.assertIn("não volta sozinha", bloco)          # ffmpeg (brew) avisa antes
        self.assertNotIn('value="Flask"', bloco)

    def test_estado_mostra_item_novo_e_some_com_o_tirado(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "atualizacoes.json"
            arq.write_text(json.dumps({"quando": "2026-10-10 12:19", "itens": [
                {"nome": "HyperFrames", "pra": "velho", "versao": "4.0.534", "nova": "", "estado": "em dia"},
                {"nome": "demucs", "pra": "x", "versao": "4.1.0", "nova": "", "estado": "em dia"}]}))
            with patch.object(U, "ESTADO", arq):
                e = U.estado()
        nomes = [i["nome"] for i in e["itens"]]
        self.assertEqual(nomes, [i["nome"] for i in U.MANIFESTO])
        self.assertNotIn("demucs", nomes)
        hf = next(i for i in e["itens"] if i["nome"] == "HyperFrames")
        self.assertEqual((hf["versao"], hf["estado"]), ("4.0.534", "em dia"))
        self.assertNotEqual(hf["pra"], "velho")
        self.assertNotIn("Remotion", nomes)   # saiu em 29-out-2026: nenhum estilo pronto usa
        rembg = next(i for i in e["itens"] if i["nome"] == "rembg")
        self.assertEqual(rembg["estado"], "ainda não conferido")


if __name__ == "__main__":
    unittest.main()
