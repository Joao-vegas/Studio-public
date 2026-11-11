"""Gerar com IA no Editar vídeo: custo, permissão (nonce) e registro de gasto. A kie.ai é SEMPRE simulada: nenhum teste gasta."""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import broll_ia  # noqa: E402
import custos  # noqa: E402
import editor  # noqa: E402
import gerar_ia  # noqa: E402
from _comum import RAIZ  # noqa: E402
from PIL import Image  # noqa: E402



class KieFalsa:
    """Substitui broll_ia.call: guarda cada chamada e responde como a kie.ai."""

    def __init__(self, saldo=1000.0, estado="success", falha_envio=False, creditos=4):
        self.chamadas, self.saldo, self.estado, self.falha_envio, self.creditos = [], saldo, estado, falha_envio, creditos

    def __call__(self, metodo, url, body=None):
        self.chamadas.append((metodo, url, body))
        if url.endswith("/chat/credit"):
            return self.saldo
        if url.endswith("/createTask"):
            if self.falha_envio:
                raise OSError("rede caiu")
            return {"taskId": f"tarefa{len([c for c in self.chamadas if c[1].endswith('/createTask')])}"}
        if "/recordInfo" in url:
            return {"state": self.estado, "creditsConsumed": self.creditos,
                    "resultJson": json.dumps({"resultUrls": ["https://x.test/a.png", "https://x.test/b.png"]})}
        raise AssertionError(url)

    def envios(self):
        return [c for c in self.chamadas if c[0] == "POST"]


def _baixar_falso(url, destino):
    if str(destino).endswith(".mp4"):
        destino.write_bytes(b"mp4")
    else:
        Image.new("RGB", (64, 96), (200, 30, 30)).save(destino, format="PNG")


class Base(unittest.TestCase):
    def setUp(self):
        TMP = Path(tempfile.mkdtemp(prefix=".tmp-teste-gerar-ia-", dir=RAIZ / "app"))   # única por teste: duas suítes juntas não se atropelam
        self.tmp = TMP
        self.p = TMP / "modelos" / "editorial" / "_sandbox-t"
        (self.p / "fotos").mkdir(parents=True)
        Image.new("RGB", (128, 85), (10, 10, 10)).save(self.p / "fotos" / "a.jpg")
        (self.p / "cenas.json").write_text(json.dumps({"duracao": 6, "palavras": "w.json", "largura": 1080, "altura": 1920, "saida": "v.mp4", "cenas": [
            {"tipo": "foto", "de": 0, "imagem": "fotos/a.jpg"}, {"tipo": "texto", "de": 2, "texto": "oi", "forte": []}]}))
        self.tsv = TMP / "_custos.tsv"
        self.kie = KieFalsa()
        for alvo in [(mock.patch.object(broll_ia, "call", self.kie)), (mock.patch.object(broll_ia, "key", return_value="k")),
                            (mock.patch.object(broll_ia, "configured", return_value=True)),
                            (mock.patch.object(broll_ia, "upload", return_value="https://x.test/up.jpg")),
                            (mock.patch.object(gerar_ia, "_baixar", _baixar_falso)),
                            (mock.patch.object(gerar_ia, "_iniciar", lambda f, *a: f(*a))),   # a thread roda na hora
                            (mock.patch.object(gerar_ia, "cliente_de", return_value="Joao")),
                            (mock.patch.object(custos, "KIE_TSV", self.tsv))]:
            alvo.start()
            self.addCleanup(alvo.stop)
        self.addCleanup(shutil.rmtree, TMP, ignore_errors=True)

    def linhas(self):
        if not self.tsv.exists():
            return []
        with self.tsv.open(encoding="utf-8") as f:
            return list(csv.DictReader(f, delimiter="\t"))

    def form(self, **kw):
        return dict({"n": 1, "tipo": "imagem", "prompt": "Foto de uma torcida num estádio", "opcoes": 2}, **kw)


class Custo(Base):
    def test_grok_duas_opcoes_e_um_pedido_de_2_centavos_de_dolar(self):
        o = gerar_ia.orcar(self.p, self.form())
        self.assertEqual((o["modelo"], o["tarefas"], o["opcoes"]), ("grok-imagine/text-to-image", 1, 2))
        self.assertAlmostEqual(o["usd"], 0.02)
        self.assertAlmostEqual(o["brl"], round(0.02 * custos.COTACAO_PADRAO, 2))   # ~R$ 0,11, a cotação da tela de Custos
        self.assertAlmostEqual(o["creditos"], 4)

    def test_quatro_opcoes_do_grok_sao_dois_pedidos(self):
        o = gerar_ia.orcar(self.p, self.form(opcoes=4))
        self.assertEqual((o["tarefas"], o["opcoes"]), (2, 4))
        self.assertAlmostEqual(o["usd"], 0.04)

    def test_z_image_cobra_por_imagem(self):
        o = gerar_ia.orcar(self.p, self.form(modelo="z-image", opcoes=3))
        self.assertEqual((o["tarefas"], o["opcoes"]), (3, 3))
        self.assertAlmostEqual(o["usd"], 0.012)

    def test_gpt_image_comeca_na_qualidade_mais_barata(self):
        o = gerar_ia.orcar(self.p, self.form(modelo="gpt-image-2-5-sunburst-text-to-image", opcoes=1))
        self.assertEqual(o["resolucao"], "1K")
        self.assertAlmostEqual(o["usd"], 0.03)
        self.assertAlmostEqual(gerar_ia.orcar(self.p, self.form(modelo="gpt-image-2-5-sunburst-text-to-image", opcoes=1, resolucao="4K"))["usd"], 0.08)

    def test_video_cobra_por_segundo(self):
        o = gerar_ia.orcar(self.p, self.form(tipo="video", modelo="grok-imagine/image-to-video", duracao=6, opcoes=1))
        self.assertAlmostEqual(o["usd"], 0.0225 * 6)
        o = gerar_ia.orcar(self.p, self.form(tipo="video", modelo="kling-3.0/video", duracao=10, opcoes=2))
        self.assertAlmostEqual(o["usd"], 0.07 * 10 * 2)

    def test_video_sem_imagem_na_cena_nao_orca(self):
        with self.assertRaises(ValueError):
            gerar_ia.orcar(self.p, self.form(n=2, tipo="video"))

    def test_teto_por_pedido(self):
        with mock.patch.object(gerar_ia, "TETO_USD", 0.01), self.assertRaises(ValueError):
            gerar_ia.orcar(self.p, self.form())

    def test_orcar_nao_envia_nada(self):
        gerar_ia.orcar(self.p, self.form())
        gerar_ia.cardapio(self.p, 1)
        self.assertEqual(self.kie.envios(), [])
        self.assertFalse(list((self.p / "editor" / "gerados").glob("*.json")) if (self.p / "editor" / "gerados").exists() else [])

    def test_cardapio_traz_saldo_modelos_e_texto_sugerido(self):
        c = gerar_ia.cardapio(self.p, 1)
        self.assertEqual(c["saldo"]["creditos"], 1000.0)
        self.assertAlmostEqual(c["saldo"]["usd"], 5.0)
        self.assertEqual(c["imagem"]["padrao"], "grok-imagine/text-to-image")
        self.assertIn("z-image", [m["id"] for m in c["imagem"]["modelos"]])
        self.assertTrue(c["imagem_atual"].endswith("fotos/a.jpg"))
        self.assertIn("fotojornalismo", c["prompt"])   # o estilo do Editorial entra no texto sugerido


class Permissao(Base):
    def test_rascunho_nao_envia_e_trava_o_custo(self):
        r = gerar_ia.rascunho(self.p, self.form())
        self.assertEqual(r["status"], "rascunho")
        self.assertTrue(r["nonce"])
        self.assertEqual(self.kie.envios(), [])
        self.assertEqual(self.linhas(), [])
        self.assertEqual(gerar_ia.atualizar(self.p, r["id"])["status"], "rascunho")   # consultar também não manda nada

    def test_sem_nonce_certo_nao_envia(self):
        r = gerar_ia.rascunho(self.p, self.form())
        with self.assertRaises(ValueError):
            gerar_ia.confirmar(self.p, r["id"], "errado")
        self.assertEqual(self.kie.envios(), [])
        self.assertEqual(gerar_ia.carregar(self.p, r["id"])["status"], "rascunho")

    def test_permitir_envia_uma_vez_so(self):
        r = gerar_ia.rascunho(self.p, self.form())
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])      # clique duplo / POST repetido
        self.assertEqual(len(self.kie.envios()), 1)
        corpo = self.kie.envios()[0][2]
        self.assertEqual(corpo["model"], "grok-imagine/text-to-image")
        self.assertEqual(corpo["input"]["aspect_ratio"], "9:16")
        self.assertEqual(gerar_ia.carregar(self.p, r["id"])["status"], "processando")

    def test_sem_chave_falha_antes_de_marcar_envio(self):
        r = gerar_ia.rascunho(self.p, self.form())
        with mock.patch.object(broll_ia, "key", side_effect=ValueError("sem chave")), self.assertRaises(ValueError):
            gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        self.assertEqual(gerar_ia.carregar(self.p, r["id"])["status"], "rascunho")

    def test_saldo_insuficiente_nao_envia(self):
        self.kie.saldo = 1.0
        r = gerar_ia.rascunho(self.p, self.form())
        with self.assertRaises(ValueError):
            gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        self.assertEqual(self.kie.envios(), [])

    def test_envio_sem_confirmacao_vira_incerto_e_nao_reenvia(self):
        self.kie.falha_envio = True
        r = gerar_ia.rascunho(self.p, self.form())
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        g = gerar_ia.carregar(self.p, r["id"])
        self.assertEqual(g["status"], "incerto")
        self.assertEqual(len(self.kie.envios()), 1)           # sem retry
        self.assertEqual(self.linhas(), [])                    # não sabemos se cobrou: nada registrado
        self.assertNotIn("Bearer", json.dumps(g))                # sem chave no registro

    def test_video_envia_a_imagem_da_cena_como_referencia(self):
        r = gerar_ia.rascunho(self.p, self.form(tipo="video", modelo="grok-imagine/image-to-video", duracao=6, opcoes=1, prompt="A torcida se mexe devagar"))
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        corpo = self.kie.envios()[0][2]
        self.assertEqual(corpo["model"], "grok-imagine/image-to-video")
        self.assertEqual(corpo["input"]["image_urls"], ["https://x.test/up.jpg"])
        self.assertEqual(corpo["input"]["duration"], "6")


class Registro(Base):
    def gerar(self, **kw):
        r = gerar_ia.rascunho(self.p, self.form(**kw))
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        return r["id"]

    def test_pronto_baixa_as_opcoes_e_registra_o_gasto_uma_vez(self):
        ident = self.gerar()
        g = gerar_ia.atualizar(self.p, ident)
        self.assertEqual(g["status"], "pronto")
        self.assertEqual(len(g["arquivos"]), 2)
        for a in g["arquivos"]:
            self.assertTrue((self.p / a["arquivo"]).is_file())
            self.assertTrue((self.p / a["arquivo"]).as_posix().endswith(".jpg"))
        gerar_ia.atualizar(self.p, ident)                        # consultar de novo não cobra nem registra de novo
        linhas = self.linhas()
        self.assertEqual(len(linhas), 1)
        l = linhas[0]
        self.assertEqual((l["projeto"], l["modelo"], l["tipo"], l["status"], l["creditos"]), ("Joao", "grok-imagine/text-to-image", "imagem", "ok", "4"))
        self.assertEqual(l["usd"], "0.0200")
        self.assertEqual(l["taskId"], "tarefa1")
        self.assertIn("cena 1", l["descricao"])

    def test_cabecalho_igual_ao_do_kie_py(self):
        self.gerar()
        gerar_ia.atualizar(self.p, gerar_ia.lista(self.p)[0]["id"])
        cab = self.tsv.read_text(encoding="utf-8").splitlines()[0].split("\t")
        self.assertEqual(cab, ["data", "projeto", "modelo", "tipo", "creditos", "usd", "status", "taskId", "arquivo", "descricao"])

    def test_gasto_entra_em_custos(self):
        self.gerar()
        gerar_ia.atualizar(self.p, gerar_ia.lista(self.p)[0]["id"])
        achados = [x for x in custos._da_kie() if x["projeto"] == "Joao"]
        self.assertEqual(len(achados), 1)
        self.assertAlmostEqual(achados[0]["usd"], 0.02)

    def test_registro_guarda_modelo_prompt_e_custo(self):
        ident = self.gerar()
        g = gerar_ia.atualizar(self.p, ident)
        self.assertEqual((g["model"], g["prompt"], g["usd_estimado"], g["cliente"]), ("grok-imagine/text-to-image", "Foto de uma torcida num estádio", 0.02, "Joao"))
        self.assertAlmostEqual(g["tarefas"][0]["creditos_reais"], 4)

    def test_falha_registra_sem_cobrar_e_sem_opcoes(self):
        self.kie.estado, self.kie.creditos = "fail", 0
        g = gerar_ia.atualizar(self.p, self.gerar())
        self.assertEqual((g["status"], g["arquivos"]), ("falhou", []))
        self.assertEqual([(l["status"], l["creditos"]) for l in self.linhas()], [("falhou", "0")])

    def test_video_vira_pasta_de_quadros(self):
        def quadros(mp4, destino):
            destino.mkdir(parents=True)
            (destino / "0001.jpg").write_bytes(b"j")
            return destino / "0001.jpg"
        with mock.patch.object(gerar_ia, "_quadros", quadros):
            g = gerar_ia.atualizar(self.p, self.gerar(tipo="video", modelo="grok-imagine/image-to-video", duracao=6, opcoes=1, prompt="A torcida se mexe devagar"))
        self.assertEqual(g["status"], "pronto")
        self.assertEqual(g["arquivos"][0]["campo"], "quadros_de")
        self.assertTrue((self.p / g["arquivos"][0]["arquivo"] / "0001.jpg").is_file())
        self.assertEqual(self.linhas()[0]["tipo"], "video")

    def test_registrar_kie_cria_arquivo_com_cabecalho(self):
        custos.registrar_kie("Joao", "z-image", "imagem", 0.8, "ok", "t9", "/x/a.jpg", "teste")
        l = self.linhas()
        self.assertEqual((len(l), l[0]["usd"], l[0]["creditos"]), (1, "0.0040", "0.8"))


class Material(Base):
    def pronto(self, **kw):
        r = gerar_ia.rascunho(self.p, self.form(**kw))
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        return gerar_ia.atualizar(self.p, r["id"])

    def test_opcao_gerada_aparece_no_material_e_vira_a_imagem_da_cena(self):
        g = self.pronto()
        grupos = {x["grupo"]: x["itens"] for x in editor.material(self.p)}
        self.assertIn("Gerados por IA", grupos)
        arq = g["arquivos"][1]["arquivo"]
        self.assertIn(arq, [i["arquivo"] for i in grupos["Gerados por IA"]])
        with mock.patch.object(editor.subprocess, "Popen") as popen:
            editor.usar_material(self.p, 2, arq)
        self.assertTrue(popen.called)
        cena = json.loads((self.p / "cenas.json").read_text())["cenas"][1]
        self.assertEqual((cena["tipo"], cena["imagem"]), ("foto", arq))
        self.assertTrue(list((self.p / "editor" / "versoes").glob("v*")))        # virou versão: dá pra voltar

    def test_prompt_do_editor_manda_o_claude_sugerir_em_vez_de_gerar(self):
        txt = editor.prompt(self.p, {"escopo": "cena", "n": 1, "campo": "", "texto": "troca a imagem", "print": ""})
        self.assertIn("sugestao_ia.json", txt)
        self.assertIn("NÃO gere imagem", txt)


class Sugestao(Base):
    def escrever(self, itens):
        (self.p / "editor").mkdir(exist_ok=True)
        (self.p / "editor" / "sugestao_ia.json").write_text(json.dumps(itens))

    def test_cartao_mostra_o_custo_e_nao_gasta(self):
        self.escrever([{"n": 1, "o_que": "Torcedores de camisa azul no estádio lotado", "motivo": "não achei foto real"}])
        s = gerar_ia.sugestoes(self.p)
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["n"], s[0]["modelo"], s[0]["opcoes"]), (1, "grok-imagine/text-to-image", 2))
        self.assertAlmostEqual(s[0]["brl"], round(0.02 * custos.COTACAO_PADRAO, 2))
        self.assertEqual(self.kie.envios(), [])

    def test_sugestao_invalida_ou_dispensada_some(self):
        self.escrever({"sugestoes": [{"n": 9, "o_que": "cena que não existe aqui"}, {"n": 1, "o_que": "curto"},
                                      {"n": 2, "o_que": "Um apartamento simples à noite, luz amarela"}]})
        s = gerar_ia.sugestoes(self.p)
        self.assertEqual([x["n"] for x in s], [2])
        gerar_ia.dispensar(self.p, s[0]["id"])
        self.assertEqual(gerar_ia.sugestoes(self.p), [])

    def test_gerada_a_sugestao_sai_do_cartao(self):
        self.escrever([{"n": 1, "o_que": "Torcedores de camisa azul no estádio lotado"}])
        s = gerar_ia.sugestoes(self.p)[0]
        r = gerar_ia.rascunho(self.p, self.form(prompt=s["o_que"], sugestao=s["id"]))
        self.assertEqual(len(gerar_ia.sugestoes(self.p)), 1)     # só rascunho: o cartão continua até o João permitir
        gerar_ia.confirmar(self.p, r["id"], r["nonce"])
        self.assertEqual(gerar_ia.sugestoes(self.p), [])


class Projeto(unittest.TestCase):
    def test_projeto_do_custo_e_o_cliente(self):
        self.assertEqual(gerar_ia.cliente_de(RAIZ / "clientes" / "Joao" / "vegasContent" / "modelos" / "editorial" / "_sandbox-x"), "Joao")
        self.assertEqual(gerar_ia.cliente_de(RAIZ / "app" / "x"), "sem-cliente")


if __name__ == "__main__":
    unittest.main()
