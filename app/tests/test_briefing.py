"""Rota "Me ajuda a pensar" (briefing). A chamada do claude é sempre simulada: nenhum teste gasta cota."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'interface'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
from flask import Flask
import briefing_rotas as B

SUGESTOES = {"perguntas": ["Quantos pedidos impossíveis?", "Qual é o produto?", "Quem fecha a cena?", "Quarta pergunta?"],
             "sugestoes": [{"titulo": f"Ideia {i}", "texto": f"Humano pede o impossível {i}.\nClaudio responde seco."} for i in (1, 2, 3, 4)]}
USO = {"input_tokens": 120, "output_tokens": 300, "cache_read_input_tokens": 0}


def resposta_claude(resultado, custo=0.0042, erro=False, codigo=0):
    saida = {"type": "result", "subtype": "success", "is_error": erro, "result": resultado,
             "total_cost_usd": custo, "usage": USO}
    return subprocess.CompletedProcess([], codigo, stdout=json.dumps(saida), stderr="")


class BriefingAjuda(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        B.register(app)
        self.c = app.test_client()
        for alvo, kw in (("briefing_rotas.claude_bin", {"return_value": "/fake/claude"}),
                         ("briefing_rotas._custos.registrar_execucao", {})):
            p = patch(alvo, **kw)
            setattr(self, alvo.rsplit(".", 1)[1], p.start())
            self.addCleanup(p.stop)
        p = patch("briefing_rotas.subprocess.run")
        self.run = p.start()
        self.addCleanup(p.stop)

    def pedir(self, **extra):
        corpo = {"formato": "explicador-3d", "cliente": "Joao", "ideia": "anúncio do plano deus", "entrada": "roteiro"}
        corpo.update(extra)
        return self.c.post("/api/briefing-ajuda", json=corpo)

    def test_caminho_feliz(self):
        self.run.return_value = resposta_claude("```json\n" + json.dumps(SUGESTOES, ensure_ascii=False) + "\n```")
        r = self.pedir()
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(len(d["perguntas"]), 3)                       # corta em 3
        self.assertEqual(len(d["sugestoes"]), 3)                       # corta em 3
        self.assertEqual(set(d["sugestoes"][0]), {"titulo", "texto"})
        cmd, kw = self.run.call_args.args[0], self.run.call_args.kwargs
        self.assertEqual(cmd[0], "/fake/claude")
        for trecho in (["-p"], ["--model", "sonnet"], ["--output-format", "json"], ["--tools", ""]):
            i = cmd.index(trecho[0])
            self.assertEqual(cmd[i:i + len(trecho)], trecho)
        self.assertEqual(kw["timeout"], 180)
        prompt = kw["input"]
        self.assertIn("Explicador 3D", prompt)                            # título do formato
        self.assertIn("Pessoas do base/gente.js", prompt)                   # regra do formato
        self.assertIn("anúncio do plano deus", prompt)                 # ideia do João
        self.registrar_execucao.assert_called_once_with({"provedor": "claude", "modelo": "sonnet"}, 0.0042, USO, None)

    def test_roteiro_vem_com_elenco_e_cenario(self):
        rot = {"perguntas": [], "sugestoes": [{"titulo": "Loja vazia", "texto": "Dono e atendente.", "elenco": ["Dono de ótica, homem, 45 anos, óculos", "Atendente"],
                                               "cenario": "Ótica de rua", "clima": "Limpo", "roteiro": "Atendente: A loja tá vazia!\nDono: Nunca foi o preço."}]}
        self.run.return_value = resposta_claude(json.dumps(rot, ensure_ascii=False))
        d = self.pedir(cliente="Avulso", ideia="roteiro pra marca3").get_json()
        s = d["sugestoes"][0]
        self.assertEqual(s["elenco"][0], "Dono de ótica, homem, 45 anos, óculos")
        self.assertEqual(s["cenario"], "Ótica de rua")
        self.assertNotIn("!", s["roteiro"])                             # o formato não usa exclamação
        prompt = self.run.call_args.kwargs["input"]
        self.assertIn("NARRAÇÃO", prompt)                               # hoje todo estilo de roteiro é narração em off (30-out): sem "Nome: fala"
        self.assertIn("SEM \"Nome:\"", prompt)
        import briefing_rotas as B
        self.assertIn("SÓ quando o tema do vídeo é IA", B.TAREFA_ROTEIRO)   # o roteiro de diálogo continua existindo (formato.json roteiro_modo=dialogo)

    def test_ideia_vazia_e_avulso(self):
        self.run.return_value = resposta_claude(json.dumps(SUGESTOES))
        r = self.pedir(ideia="", cliente="Avulso")
        self.assertTrue(r.get_json()["ok"])
        prompt = self.run.call_args.kwargs["input"]
        self.assertIn("vazio", prompt)
        self.assertNotIn("REGRAS DO CLIENTE", prompt)

    def test_sem_formato_nao_chama_a_ia(self):
        for corpo in ({"formato": ""}, {"formato": "nao-existe"}):
            r = self.pedir(**corpo)
            self.assertEqual(r.status_code, 400)
            self.assertFalse(r.get_json()["ok"])
        self.run.assert_not_called()

    def test_timeout_vira_mensagem_amigavel(self):
        self.run.side_effect = subprocess.TimeoutExpired("claude", 90)
        r = self.pedir()
        self.assertEqual(r.status_code, 502)
        self.assertIn("demorou", r.get_json()["erro"])

    def test_claude_nao_instalado(self):
        self.claude_bin.return_value = None
        r = self.pedir()
        self.assertEqual(r.status_code, 502)
        self.assertIn("Claude Code", r.get_json()["erro"])
        self.run.assert_not_called()

    def test_erro_do_claude_ainda_registra_custo(self):
        self.run.return_value = resposta_claude("Not logged in", erro=True, codigo=1)
        r = self.pedir()
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("Not logged in", r.get_json()["erro"])
        self.registrar_execucao.assert_called_once()

    def test_resposta_fora_do_formato(self):
        self.run.return_value = resposta_claude("Claro! Aqui vão minhas ideias, sem JSON.")
        r = self.pedir()
        self.assertEqual(r.status_code, 502)
        self.assertFalse(r.get_json()["ok"])

    def test_saida_nao_json(self):
        self.run.return_value = subprocess.CompletedProcess([], 1, stdout="boom", stderr="x")
        r = self.pedir()
        self.assertEqual(r.status_code, 502)

    def test_prompt_limita_regras_a_15(self):
        fake = {"formato": [{"id": f"F{i}", "texto": f"regra do formato {i}"} for i in range(20)],
                "cliente": [{"id": f"C{i}", "texto": f"regra do cliente {i}"} for i in range(10)], "cliente_nome": "Joao"}
        with patch("briefing_rotas._fmt.aprendizado", return_value=fake):
            prompt = B.montar_prompt("explicador-3d", "Joao", "", "roteiro")
        regras = [l for l in prompt.splitlines() if l.startswith("- regra do")]
        self.assertEqual(len(regras), 15)
        self.assertIn("- regra do cliente 0", prompt)                  # as do cliente entram primeiro

    def test_extrair_json(self):
        self.assertEqual(B.extrair_json('texto antes {"a": 1} depois'), {"a": 1})
        self.assertEqual(B.extrair_json('```json\n{"a": 2}\n```'), {"a": 2})
        self.assertIsNone(B.extrair_json("nada"))


if __name__ == "__main__":
    unittest.main()
