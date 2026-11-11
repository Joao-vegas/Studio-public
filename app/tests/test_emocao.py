"""Voz com emoção (PLANO-2.0, item 6): marcar a emoção por frase, escolher o perfil por bloco, mapa de variações e o gate
(a variação e o trecho do João só viram perfil com o Aprovou). VoiceStudio e Claude mockados; nada pago, nada gerado."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import emocao as E
import emocao_joao as EJ


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mapa = self.tmp / "vozes-emocao.json"
        self.amostras = self.tmp / "amostras"
        for alvo, valor in ((E, {"MAPA": self.mapa, "AMOSTRAS": self.amostras}), (EJ, {"SAIDA": self.amostras / "joao"})):
            for k, v in valor.items():
                p = patch.object(alvo, k, v); p.start(); self.addCleanup(p.stop)

    def aprovada(self, voz, emo, perfil):
        E.registrar_aprovada(voz, emo, perfil)


class Frases(Base):
    def test_frases_quebram_por_linha_e_por_ponto(self):
        self.assertEqual(E.frases("Você entrou por fato? Pensa.\n\nA maioria nunca pensou nisso."),
                         ["Você entrou por fato?", "Pensa.", "A maioria nunca pensou nisso."])

    def test_heuristica(self):
        self.assertEqual(E.heuristica("Será que é coincidência?"), "pergunta")
        self.assertEqual(E.heuristica("Isso é um absurdo total."), "indignado")
        self.assertEqual(E.heuristica("Vem cá, chega mais perto."), "segredo")
        self.assertEqual(E.heuristica("Anota isso."), "firme")


class Marcar(Base):
    def test_claude_marca_uma_emocao_por_frase(self):
        r = "Pronto: {\"emocoes\": [\"pergunta\", \"firme\", \"calmo\"]}"
        linhas = E.marcar("Entrou por fato ou crença?\nPensa bem.\nA maioria nunca parou pra pensar.", chamar=lambda p: r)
        self.assertEqual([l["emocao"] for l in linhas], ["pergunta", "firme", "calmo"])
        self.assertEqual(linhas[0]["texto"], "Entrou por fato ou crença?")

    def test_prompt_lista_as_frases_e_as_emocoes(self):
        vistos = []
        E.marcar("Um.\nDois.", chamar=lambda p: vistos.append(p))
        self.assertIn("1. Um.", vistos[0]); self.assertIn("2. Dois.", vistos[0])
        for e in E.ORDEM:
            self.assertIn(e, vistos[0])

    def test_resposta_ruim_cai_na_heuristica(self):
        for ruim in (None, "não sei", "{\"emocoes\": [\"firme\"]}", "{\"emocoes\": 3}"):
            linhas = E.marcar("Será?\nPensa.", chamar=lambda p, r=ruim: r)
            self.assertEqual([l["emocao"] for l in linhas], ["pergunta", "firme"])

    def test_emocao_inventada_vira_calmo(self):
        linhas = E.marcar("Um.\nDois.", chamar=lambda p: "{\"emocoes\": [\"furioso\", \"animado\"]}")
        self.assertEqual([l["emocao"] for l in linhas], ["calmo", "animado"])


class Arquivo(Base):
    def test_grava_ao_lado_do_roteiro_e_alinha_com_a_edicao(self):
        pasta = self.tmp / "v"; pasta.mkdir()
        (pasta / "roteiro.txt").write_text("Será?\nPensa.\n", encoding="utf-8")
        E.gravar(pasta, [{"texto": "Será?", "emocao": "segredo"}, {"texto": "Pensa.", "emocao": "indignado"}])
        self.assertEqual([l["emocao"] for l in E.ler(pasta)], ["segredo", "indignado"])
        (pasta / "roteiro.txt").write_text("Será?\nPensa.\nMais uma frase nova que acabou de chegar aqui.\n", encoding="utf-8")
        lidas = E.ler(pasta)   # a frase nova ganha a heurística; as que ele já trocou ficam
        self.assertEqual([l["emocao"] for l in lidas[:2]], ["segredo", "indignado"])
        self.assertEqual(len(lidas), 3)

    def test_trocar_checa_o_tamanho(self):
        pasta = self.tmp / "v"; pasta.mkdir()
        (pasta / "roteiro.txt").write_text("Um.\nDois.\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            E.trocar(pasta, ["firme"])
        self.assertEqual([l["emocao"] for l in E.trocar(pasta, ["firme", "animado"])], ["firme", "animado"])

    def test_sem_arquivo_nao_ha_emocao(self):
        pasta = self.tmp / "v"; pasta.mkdir()
        self.assertEqual(E.ler(pasta, "Um.\n"), [])


class PerfilPorBloco(Base):
    def test_sem_variacao_aprovada_usa_a_voz_normal(self):
        self.assertEqual(E.perfil_da_emocao("v1", "animado"), "v1")

    def test_aguardando_nao_vale_so_aprovada(self):
        d = E.mapa(); d["vozes"]["v1"] = {"animado": {"status": "aguardando", "perfil": "p9"}}; E._salvar(d)
        self.assertEqual(E.perfil_da_emocao("v1", "animado"), "v1")
        self.aprovada("v1", "animado", "p1")
        self.assertEqual(E.perfil_da_emocao("v1", "animado"), "p1")
        self.assertEqual(E.perfil_da_emocao("v1", "calmo"), "v1")   # outra emoção sem variação: normal
        self.assertEqual(E.perfil_da_emocao("outra", "animado"), "outra")

    def test_grupos_junta_frases_seguidas_do_mesmo_perfil(self):
        self.aprovada("v1", "firme", "pF"); self.aprovada("v1", "pergunta", "pP")
        ls = [{"texto": "Você entrou por fato ou por crença, de verdade?", "emocao": "pergunta"},
              {"texto": "Pensa bem nisso antes de responder rápido.", "emocao": "pergunta"},
              {"texto": "Isso não é opinião, é fato que se repete.", "emocao": "firme"},
              {"texto": "A gente segue sem pressa nessa história.", "emocao": "calmo"}]
        self.assertEqual([p for p, _ in E.grupos(ls, "v1")], ["pP", "pF", "v1"])
        self.assertIn("Pensa bem", E.grupos(ls, "v1")[0][1])

    def test_frase_curta_gruda_na_anterior(self):
        self.aprovada("v1", "firme", "pF")
        ls = [{"texto": "A gente segue sem pressa nessa história toda aqui.", "emocao": "calmo"}, {"texto": "Anota.", "emocao": "firme"}]
        self.assertEqual(len(E.grupos(ls, "v1")), 1)

    def test_narrar_chama_a_voz_de_cada_bloco_e_cola(self):
        self.aprovada("v1", "firme", "pF")
        chamadas = []

        def falar(texto, arq, voz):
            chamadas.append((voz, texto)); Path(arq).write_bytes(b"x"); return arq
        ls = [{"texto": "Isso não é opinião, é fato que se repete sempre.", "emocao": "firme"},
              {"texto": "A gente segue sem pressa nessa história toda aqui.", "emocao": "calmo"}]
        with patch.object(E.subprocess, "run") as run:
            E.narrar(ls, "v1", self.tmp / "voz.mp3", falar=falar)
        self.assertEqual([v for v, _ in chamadas], ["pF", "v1"])
        self.assertIn("concat", run.call_args[0][0])

    def test_sem_variacao_e_um_pedido_so(self):
        chamadas = []
        ls = [{"texto": "Isso não é opinião, é fato que se repete sempre.", "emocao": "firme"},
              {"texto": "A gente segue sem pressa nessa história toda aqui.", "emocao": "calmo"}]
        E.narrar(ls, "v1", self.tmp / "voz.mp3", falar=lambda t, a, v: chamadas.append((v, t)))
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0][0], "v1")

    def test_variacao_que_falha_cai_na_voz_normal(self):
        self.aprovada("v1", "firme", "pF")
        vozes = []

        def falar(texto, arq, voz):
            vozes.append(voz)
            if voz == "pF":
                raise ValueError("perfil não existe")
            Path(arq).write_bytes(b"x")
        ls = [{"texto": "Isso não é opinião, é fato que se repete sempre.", "emocao": "firme"},
              {"texto": "A gente segue sem pressa nessa história toda aqui.", "emocao": "calmo"}]
        with patch.object(E.subprocess, "run"):
            E.narrar(ls, "v1", self.tmp / "voz.mp3", falar=falar)
        self.assertEqual(vozes, ["pF", "v1", "v1"])

    def test_narrar_pasta_sem_emocoes_e_o_roteiro_inteiro(self):
        pasta = self.tmp / "v"; pasta.mkdir()
        (pasta / "roteiro.txt").write_text("Um.\nDois.\n", encoding="utf-8")
        chamadas = []
        E.narrar_pasta(pasta, "v1", self.tmp / "o.mp3", falar=lambda t, a, v: chamadas.append((t, v)))
        self.assertEqual(chamadas, [("Um.\nDois.\n", "v1")])


class Variacoes(Base):
    """Amostras e aprovação: o perfil só nasce no Aprovou."""

    def setUp(self):
        super().setUp()
        self.chamadas = []

        def multipart(caminho, campos, arquivos=None, timeout=0):
            self.chamadas.append((caminho, dict(campos)))
            return b"w" * 30000 if caminho == "/generate" else b'{"id": "novo123"}'
        import vozes
        p = patch.object(vozes, "_multipart", multipart); p.start(); self.addCleanup(p.stop)
        p = patch.object(E.subprocess, "run", lambda cmd, **k: Path(cmd[-1]).write_bytes(b"mp3")); p.start(); self.addCleanup(p.stop)

    def test_amostra_fica_aguardando_e_nao_cria_perfil(self):
        E.gerar_amostra("v1", "animado", "Narrador grave")
        self.assertEqual([c[0] for c in self.chamadas], ["/generate"])
        self.assertEqual(E.variacoes("v1")["animado"]["status"], "aguardando")
        self.assertEqual(E.perfil_da_emocao("v1", "animado"), "v1")

    def test_amostra_fala_o_texto_da_emocao_com_a_voz_dela(self):
        E.gerar_amostra("v1", "indignado", "Voz qualquer")
        c = self.chamadas[0][1]
        self.assertEqual(c["profile_id"], "v1"); self.assertEqual(c["language"], "pt")
        self.assertIn("absurdo", c["text"]); self.assertGreater(c["speed"], 1)

    def test_segredo_usa_whisper_quando_a_descricao_da_voz_e_conhecida(self):
        E.gerar_amostra("v1", "segredo", "Narrador grave")
        c = self.chamadas[0][1]
        self.assertIn("whisper", c["instruct"]); self.assertNotIn("profile_id", c)
        self.chamadas.clear()
        E.gerar_amostra("v2", "segredo", "Voz sem descrição")
        self.assertNotIn("instruct", self.chamadas[0][1])

    def test_aprovou_cria_o_perfil_com_o_nome_da_emocao(self):
        E.gerar_amostra("v1", "animado", "Narrador grave")
        pid = E.aprovar("v1", "animado", "Narrador grave")
        self.assertEqual(pid, "novo123")
        self.assertEqual(self.chamadas[-1][0], "/profiles")
        self.assertEqual(self.chamadas[-1][1]["name"], "Narrador grave · animado")
        self.assertEqual(E.perfil_da_emocao("v1", "animado"), "novo123")
        self.assertEqual(E.aprovar("v1", "animado"), "novo123")   # clicar de novo não cria outro
        self.assertEqual(len([c for c in self.chamadas if c[0] == "/profiles"]), 1)

    def test_aprovar_sem_amostra_recusa(self):
        with self.assertRaises(ValueError):
            E.aprovar("v1", "calmo")

    def test_refazer_muda_a_semente_e_nao_mexe_na_aprovada(self):
        E.gerar_amostra("v1", "calmo", "Voz")
        E.recusar("v1", "calmo", "Voz")
        self.assertEqual(E.variacoes("v1")["calmo"]["semente"], 8)
        E.aprovar("v1", "calmo", "Voz")
        with self.assertRaises(ValueError):
            E.recusar("v1", "calmo", "Voz")

    def test_voz_do_joao_nao_ganha_emocao_sintetica(self):
        with self.assertRaises(ValueError):
            E.gerar_amostras(E.VOZ_JOAO)
        with self.assertRaises(ValueError):
            E.gerar_amostras("x", nome_voz="João Vegas")


class TrechosDoJoao(Base):
    def janelas(self):
        import random
        r = random.Random(3)
        ws = []
        for i in range(30):
            ws.append({"video": "v.mp4", "ini": i * 20.0, "fim": i * 20.0 + 14, "fala": 0.8, "vol": -30 + r.random(), "tom": r.random(), "var": 2 + r.random() * 0.2,
                       "ritmo": 3 + r.random() * 0.2, "subidas": 0, "pausas": 3, "taxa_sobe": 0.0})
        ws[5].update(vol=-18, tom=4, var=5, ritmo=5)      # alto, agudo, variado, rápido -> animado
        ws[9].update(vol=-45, ritmo=1.5, tom=-1)           # baixíssimo e devagar -> segredo
        ws[14].update(taxa_sobe=0.9)                        # frases que sobem -> pergunta
        return ws

    def test_candidatos_por_emocao_sem_repetir_trecho(self):
        c = EJ.candidatos(self.janelas())
        self.assertEqual(c["animado"][0]["ini"], 100.0)
        self.assertEqual(c["pergunta"][0]["ini"], 280.0)
        self.assertEqual(c["segredo"][0]["ini"], 180.0)
        vistos = [(x["video"], x["ini"]) for lista in c.values() for x in lista]
        self.assertEqual(len(vistos), len(set(vistos)))   # um trecho não serve a duas emoções

    def test_poucos_dados_nao_inventam_candidato(self):
        self.assertEqual(EJ.candidatos(self.janelas()[:3]), {})

    def test_candidato_nao_cria_perfil_sozinho(self):
        d = E.mapa(); d["candidatos"][E.VOZ_JOAO] = {"animado": [{"id": "abc", "video": "x.mp4", "ini": 1.0, "fim": 15.0, "texto": "oi", "status": "candidato"}]}; E._salvar(d)
        self.assertEqual(E.perfil_da_emocao(E.VOZ_JOAO, "animado"), E.VOZ_JOAO)
        self.assertEqual(E.painel([{"id": E.VOZ_JOAO, "nome": "João Vegas", "pt": True}])[0]["emocoes"][3]["candidatos"][0]["id"], "abc")

    def test_usar_so_no_aprovou_cria_joao_animado(self):
        d = E.mapa(); d["candidatos"][E.VOZ_JOAO] = {"animado": [{"id": "abc", "video": "x.mp4", "ini": 1.0, "fim": 15.0, "texto": "oi", "status": "candidato"}]}; E._salvar(d)
        criados = []
        with patch.object(EJ, "_cortar", lambda v, i, f, destino, wav=False: Path(destino).write_bytes(b"w")):
            pid = EJ.usar("animado", "abc", clonar=lambda nome, audio: criados.append(nome) or "perfJ")
        self.assertEqual(pid, "perfJ"); self.assertEqual(criados, ["João · animado"])
        self.assertEqual(E.perfil_da_emocao(E.VOZ_JOAO, "animado"), "perfJ")
        self.assertEqual(E.painel([{"id": E.VOZ_JOAO, "nome": "João Vegas", "pt": True}])[0]["emocoes"][3]["candidatos"], [])
        with self.assertRaises(ValueError):
            EJ.usar("animado", "naoexiste", clonar=lambda n, a: "x")

    def test_gravacao_do_joao_vira_a_variacao(self):
        pid = EJ.usar_gravacao("segredo", self.tmp / "a.m4a", clonar=lambda nome, audio: "perfS")
        self.assertEqual(pid, "perfS"); self.assertEqual(E.perfil_da_emocao(E.VOZ_JOAO, "segredo"), "perfS")

    def test_quando_nao_acha_a_tela_pede_para_gravar_com_texto_sugerido(self):
        self.assertEqual(set(EJ.TEXTO_GRAVAR), set(E.ORDEM))
        self.assertTrue(all(len(t.split()) >= 20 for t in EJ.TEXTO_GRAVAR.values()))


class ListaDeVozes(Base):
    def test_variacao_de_emocao_nao_aparece_como_voz_a_parte(self):
        import vozes
        self.aprovada("v1", "animado", "pA")
        perfis = [{"id": "v1", "name": "Narrador", "language": "Portuguese"}, {"id": "pA", "name": "Narrador · animado", "language": "Portuguese"}]
        with patch.object(vozes, "_get", lambda c, t=8: perfis):
            self.assertEqual([v["id"] for v in vozes.lista()], ["v1"])


class CriarGravaEmocoes(Base):
    """O Criar deixa o emocoes.json ao lado do roteiro.txt: o que o João trocou na tela, ou o que o Claude marca ao criar."""

    def criar(self, extra):
        import simples
        from servidor import app
        sb = self.tmp / "sb"; sb.mkdir(exist_ok=True)
        (sb / "roteiro.txt").write_text("Será que é fato?\nPensa bem nisso agora.\n", encoding="utf-8")

        def criar_falso(cli, mod, bruto, titulo, briefing, *a, **kw):
            return {"cliente": cli, "modelo": mod, "slug": "x", "sandbox": str(sb), "bruto": str(sb / "roteiro.txt"), "briefing": briefing, "materiais": []}
        with patch.object(simples._fmt, "usar", return_value=("Cliente2", "explicador-3d")), \
                patch.object(simples._prod, "criar", side_effect=criar_falso), patch.object(simples._prod, "salvar"), \
                patch.object(simples._prod, "brief_md", return_value=""), \
                patch.object(E, "_chamar_claude", lambda p, timeout=120: "{\"emocoes\": [\"pergunta\", \"segredo\"]}"):
            r = app.test_client().post("/criar", data={"formato": "explicador-3d", "cliente": "Cliente2", "roteiro": "Será que é fato?\nPensa bem nisso agora.", **extra})
        self.assertEqual(r.status_code, 302)
        return E.ler(sb, "Será que é fato?\nPensa bem nisso agora.")

    def test_sem_marcacao_da_tela_o_claude_marca_ao_criar(self):
        self.assertEqual([l["emocao"] for l in self.criar({})], ["pergunta", "segredo"])

    def test_o_que_o_joao_trocou_na_tela_vale(self):
        import json
        marcadas = json.dumps([{"texto": "Será que é fato?", "emocao": "indignado"}, {"texto": "Pensa bem nisso agora.", "emocao": "calmo"}])
        self.assertEqual([l["emocao"] for l in self.criar({"emocoes": marcadas})], ["indignado", "calmo"])


class Rotas(Base):
    def test_marcar_pela_api_e_painel_na_tela(self):
        from servidor import app
        c = app.test_client()
        with patch.object(E, "_chamar_claude", lambda p, timeout=120: "{\"emocoes\": [\"pergunta\", \"firme\"]}"):
            r = c.post("/api/emocoes/marcar", json={"roteiro": "Será?\nPensa."}).get_json()
        self.assertTrue(r["ok"]); self.assertEqual([l["emocao"] for l in r["linhas"]], ["pergunta", "firme"])
        self.assertEqual(c.post("/api/emocoes/marcar", json={"roteiro": " "}).status_code, 400)
        self.assertEqual(c.post("/vozes/emocao/amostra", data={"voz": "v", "emocao": "furioso"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
