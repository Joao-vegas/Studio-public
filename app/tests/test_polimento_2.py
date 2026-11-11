"""Polimento v2, volta 2 (22-out-2026): Groq com User-Agent, aspas = fala citada, destaque da legenda, instrução do estudo, quadros."""
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import estilo_ref  # noqa: E402
import estudo
import fala  # noqa: E402
import formatos  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def estilo_ok():
    return {"layout": [{"nome": "a", "y": 0, "altura": 1920}], "ritmo": {"corte_a_cada_s": 3, "plano_medio_s": 3},
            "legenda": {"posicao_y_pct": 50, "fonte_aprox": "x", "cor_hex": "#FFFFFF", "caixa": False,
                        "palavras_por_vez": 2, "maiusculas": True},
            "som": {"musica": False, "clima": "x", "efeitos": []}, "cores": ["#000000"],
            "gancho": {"mecanismo": "abre com uma pergunta", "ate_s": 3},
            "formato_sugerido": {"slug": "frase-fixa", "nota": 90, "porque": "ok"},
            "estudo_respostas": {k: "resposta 1 s" for k, _ in estilo_ref.chaves_perguntas()}}


class Polimento2(unittest.TestCase):
    def test_groq_manda_user_agent(self):
        vistos = []

        def falso(cmd, **k):
            if cmd[0] == "curl":
                vistos.append(cmd[cmd.index("-A") + 1])
                return mock.Mock(returncode=0, stdout='{"words":[],"segments":[]}\n200', stderr="")
            Path(cmd[-1]).write_bytes(b"x")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as t, mock.patch.object(fala.subprocess, "run", falso), \
                mock.patch("_comum.ffprobe", return_value={"duracao": 5}), \
                mock.patch.dict("sys.modules", {"chaves": mock.Mock(chave=lambda *a, **k: "k")}):
            estudo.transcrever(Path(t) / "v.mp4", Path(t), {"pasta": t})
        self.assertEqual(vistos, ["Estudio/2.0"])

    def test_instrucao_do_estudo_tem_8_linhas_R(self):
        ex = {"arquivo": "exemplo-1.mp4", "folha": "f.jpg"}
        txt = formatos._texto_estudo("X", ex, "origem", {"duracao": 10, "som": True})
        self.assertEqual(len(re.findall(r"(?m)^\s*R:", txt)), 8)
        self.assertNotIn("`R:`", txt)

    def test_explicador_estudo_alinhado(self):
        txt = (RAIZ / "formatos/explicador-3d/ESTUDO.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^\s*R: \S", txt)), 8)
        self.assertIn("72%", txt)   # legenda medida quadro a quadro nos 11 shorts do Loaded Dice (29-out-2026)

    def test_fala_entre_aspas_recusada_sem_transcricao(self):
        e = estilo_ok()
        e["gancho"]["mecanismo"] = "abre com 'se alguém te aborda na rua'"
        with self.assertRaises(ValueError):
            estilo_ref.copia_proibida(e, "")
        e["gancho"]["mecanismo"] = "abre com “se alguém te aborda”"
        with self.assertRaises(ValueError):
            estilo_ref.copia_proibida(e, "")
        e["gancho"]["mecanismo"] = "palavra 'GAMBLING' em vermelho"
        estilo_ref.copia_proibida(e, "")

    def test_destaque_hex_opcional(self):
        e = estilo_ok()
        self.assertEqual(estilo_ref.erros(e), [])
        e["legenda"]["destaque_hex"] = "#FFD400"
        self.assertEqual(estilo_ref.erros(e), [])
        e["legenda"]["destaque_hex"] = False
        self.assertEqual(estilo_ref.erros(e), [])
        e["legenda"]["destaque_hex"] = "amarelo"
        self.assertTrue(estilo_ref.erros(e))

    def test_ate_5_quadros_sem_repetir(self):
        tempos = []

        def falso(cmd, **k):
            tempos.append(cmd[cmd.index("-ss") + 1])
            Path(cmd[-1]).write_bytes(b"x")

        with tempfile.TemporaryDirectory() as t, mock.patch.object(estilo_ref.subprocess, "run", falso):
            out = estilo_ref._quadros_grandes(Path("v.mp4"), Path(t), 90, [6, 13, 19, 26, 32, 38, 45, 52])
        self.assertEqual(len(out), 5)
        self.assertEqual(len(set(tempos)), 5)


if __name__ == "__main__":
    unittest.main()
