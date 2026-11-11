"""Uso direto pelo app: tudo que cria algo para e pergunta "Aprovou?" (referência, set, estilo novo, variações, estudo,
virar referência, Aprendi) e a lista Esperando você junta tudo. Pasta temporária, IA simulada, nada pago."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_v2
import test_v2_frente3 as F3
import _comum as C
import andamento
import aprendi
import auto_juntar
import estilo_novo
import estilo_ref
import estudos_tela
import formatos
import lotes
import pendencias
import ref_conjunto
import remover
import variacoes

REAL = Path(__file__).resolve().parents[2]


def ia_variacoes(qtd=3):
    def _executar(prompt, log, raw, pid, s=None, on_event=None, tipo=None):
        itens = [{"titulo": f"Variação {i}", "ideia": f"ideia nova {i} sobre outro assunto", "gancho": f"gancho novo número {i}",
                  "roteiro_curto": f"linha um {i}\nlinha dois {i}", "plano_corte": "", "mantem": "ritmo de 38 cortes por minuto",
                  "muda": f"ângulo {i}"} for i in range(1, qtd + 1)]
        (Path(log).parent / "variacoes.json").write_text(json.dumps({"variacoes": itens}), encoding="utf-8")
        return 0
    return _executar


class Base(unittest.TestCase):
    """Ambiente isolado + estilos/estudos/variações/formatos numa pasta temporária."""

    def setUp(self):
        test_v2.Isolado.setUp(self)
        self.job = lambda *a, **k: test_v2.Isolado.job(self, *a, **k)
        fm = self.root / "formatos"
        shutil.copytree(REAL / "formatos" / "_modelo", fm / "_modelo")
        (fm / "teste-f3").mkdir()
        (fm / "teste-f3" / "formato.json").write_text(json.dumps({"titulo": "Teste", "frase": "x", "tipo": "motor"}))
        self.video = self.root / "ref.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=10:duration=3", "-f", "lavfi",
                        "-i", "sine=frequency=300:duration=3", "-shortest", "-pix_fmt", "yuv420p", str(self.video)], check=True)
        for o, a, v in ((estilo_ref, "ESTILOS", self.root / "app/.estilos"), (formatos, "FORMATOS", fm),
                        (estudos_tela, "PASTA", self.root / "app/.estudos"), (remover, "RAIZ", self.root),
                        (estudos_tela, "RAIZ", self.root)):
            self.stack.enter_context(mock.patch.object(o, a, v))
        self.stack.enter_context(mock.patch.object(estilo_ref, "_transcricao", lambda v, p, c: (F3.FALA, "", "")))
        self.stack.enter_context(mock.patch.object(estilo_ref.ia, "executar", F3.ia_falsa(F3.estilo_ok())))
        (self.root / "REGRAS.md").write_text("| ID | Regra | Como checar |\n|---|---|---|\n| G1 | Texto nunca em cima de texto | quadros |\n| G2 | Legenda curta | folha |\n")
        self.client.application.config["TESTING"] = True

    def ref(self, **kw):
        return estilo_ref.entender(self.video, "", esperar=True, **kw)


class AprendiTest(Base):
    def test_gate_regra_so_grava_no_ok(self):
        j = self.job("pronto", "v1")
        regras = self.mod / "aprendizado/regras.json"
        r = aprendi.propor("Teste", "v1", "Quero alterar: a cor da legenda tem que ser amarela, não branca.", modelo="estilo", titulo="Meu vídeo")
        self.assertEqual(r["estado"], "pendente")
        self.assertEqual(r["camada"], "cliente")                       # cor = gosto do cliente
        self.assertEqual(json.loads(regras.read_text())["regras"], [])  # nada gravado antes do OK
        self.assertIn("Aprendi:", aprendi.frase(r))
        self.assertIn("vale pra este cliente", aprendi.frase(r))
        hist = (self.mod / "aprendizado/historico.jsonl").read_text()
        self.assertIn("cor da legenda", hist)                          # passo 1 da REGRA Nº 2: linha bruta
        aprendi.propor("Teste", "v1", "Quero alterar: a cor da legenda tem que ser amarela, não branca.", modelo="estilo")
        self.assertEqual(len(aprendi.pendentes("Teste", "v1")), 1)     # o mesmo pedido não duplica
        aprendi.confirmar(r["id"])
        rs = json.loads(regras.read_text())["regras"]
        self.assertEqual(len(rs), 1)
        self.assertIn("amarela", rs[0]["texto"])
        self.assertIn("legenda tem que ser amarela", rs[0]["origem"])  # a frase do João vai na origem
        self.assertEqual(aprendi.pendentes(), [])
        # outro pedido do mesmo assunto REESCREVE a regra, nunca duplica
        r2 = aprendi.propor("Teste", "v1", "A cor da legenda amarela tem que ser mais forte, quase dourada.", modelo="estilo")
        self.assertEqual(r2["parecida"]["id"], rs[0]["id"])
        aprendi.confirmar(r2["id"])
        rs2 = json.loads(regras.read_text())["regras"]
        self.assertEqual(len(rs2), 1)
        self.assertIn("dourada", rs2[0]["texto"])

    def test_nao_e_isso_troca_camada_e_geral_vai_pro_regras_md(self):
        self.job("pronto", "v2")
        r = aprendi.propor("Teste", "v2", "Em todo vídeo a música nunca pode cobrir a voz.", modelo="estilo")
        self.assertEqual(r["camada"], "geral")
        r = aprendi.ajustar(r["id"], "A música nunca cobre a voz, em nenhum vídeo.", "geral")
        self.assertEqual(aprendi.carregar(r["id"])["regra"], "A música nunca cobre a voz, em nenhum vídeo.")
        self.assertNotIn("G3", (self.root / "REGRAS.md").read_text())   # ainda pendente
        aprendi.confirmar(r["id"])
        md = (self.root / "REGRAS.md").read_text()
        self.assertIn("| G3 |", md)
        self.assertIn("cobre a voz", md)
        # camada estilo sem estilo no vídeo é recusada; descartar não grava
        r3 = aprendi.propor("Teste", "v2", "O corte do gancho tem que ser mais rápido.", modelo="estilo")
        self.assertEqual(r3["camada"], "cliente")                        # sem estilo: cliente
        with self.assertRaises(ValueError):
            aprendi.ajustar(r3["id"], None, "estilo")
        aprendi.descartar(r3["id"])
        self.assertEqual(json.loads((self.mod / "aprendizado/regras.json").read_text())["regras"], [])
        with self.assertRaises(ValueError):
            aprendi.confirmar(r3["id"])

    def test_camada_estilo_grava_no_formato(self):
        self.job("pronto", "v3")
        (formatos.FORMATOS / "teste-f3" / "aprendizado").mkdir()
        r = aprendi.propor("Teste", "v3", "O ritmo dos cortes tem que acelerar no meio do vídeo.", formato="teste-f3", modelo="estilo")
        self.assertEqual(r["camada"], "estilo")
        aprendi.confirmar(r["id"])
        d = json.loads((formatos.FORMATOS / "teste-f3" / "aprendizado/regras.json").read_text())
        self.assertEqual(len(d["regras"]), 1)

    def test_tela_quero_alterar_mostra_aprendi_e_ok_grava(self):
        self.job("pronto", "v4")
        andamento.registrar("Teste", "v4", "Pronto", "pronto", titulo="Meu vídeo", formato="", origem="tela", video="clientes/Teste/testeContent/output/estilo/v4.mp4")
        r = self.client.post("/andamento/Teste/v4/responder", data={"decisao": "ajustar", "texto": "A cor da legenda tem que ser amarela."})
        self.assertEqual(r.status_code, 302)
        pend = aprendi.pendentes("Teste", "v4")
        self.assertEqual(len(pend), 1)
        html = self.client.get("/andamento/Teste/v4").get_data(as_text=True)
        self.assertIn("Aprendi:", html)
        self.assertIn("Não é isso", html)
        self.assertIn(">OK<", html)
        self.assertEqual(json.loads((self.mod / "aprendizado/regras.json").read_text())["regras"], [])
        r = self.client.post(f"/aprendi/{pend[0]['id']}/ajustar", data={"regra": "Legenda sempre amarela.", "camada": "cliente", "guardar": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(json.loads((self.mod / "aprendizado/regras.json").read_text())["regras"][0]["texto"], "Legenda sempre amarela.")
        self.assertEqual(aprendi.pendentes(), [])


class PendenciasTest(Base):
    def test_esperando_lista_tudo(self):
        # referência jogada pela tela (gate) pronta -> aparece; sem gate (chamada de código) não
        id_ = self.ref(gate=True)
        self.ref()
        # estudo pronto com gate
        d = estudos_tela.PASTA / "e1"
        (d / "estudo-quadros" / "folhas").mkdir(parents=True)
        (d / "estudo-quadros/ESTUDO-QUADROS.md").write_text("x")
        C.gravar_json(d / "estado.json", {"nome": "Estudo teste", "pronto": True, "rodando": False, "gate": True})
        # regra aprendida pendente
        self.job("pronto", "v5")
        aprendi.propor("Teste", "v5", "A cor da legenda tem que ser amarela.", modelo="estilo", titulo="Meu vídeo")
        # estilo novo
        slug = estilo_novo.criar(id_, "legenda amarela teste")
        # variações propostas
        ref2 = self.ref(gate=True)
        with mock.patch.object(variacoes.ia, "executar", ia_variacoes()):
            vid = variacoes.propor([ref2], esperar=True)
        tipos = {i["tipo"]: i for i in pendencias.itens()}
        self.assertEqual(set(tipos), {"referencia", "estudo", "regra", "estilo_novo", "variacoes"})
        self.assertEqual(tipos["referencia"]["id"], ref2)
        self.assertTrue(tipos["referencia"]["imagem"].endswith("folha.jpg"))
        self.assertEqual(tipos["estilo_novo"]["id"], slug)
        itens = lotes.esperando()
        self.assertEqual(len(itens), 5)
        html = self.client.get("/aprovar").get_data(as_text=True)
        for t in ("1 vídeo de referência que eu estudei", "Estudo pronto: juntar a qual estilo?", "ideias de vídeo nesse estilo", "Estilo novo", "Aprendi:", "Se você aprovar:"):
            self.assertIn(t, html)
        self.assertIn("Ver o que entendi", html)
        self.assertIn("Escolher o estilo", html)
        self.assertIn("Ver as ideias", html)
        # confirmar a referência tira da lista
        estilo_ref.confirmar(ref2, "teste-f3", "x")
        self.assertNotIn("referencia", {i["tipo"] for i in pendencias.itens()})
        # variações: aprovar uma tira o item só quando todas respondidas
        for n in (1, 2, 3):
            variacoes.decidir(vid, n, "aprovar" if n == 1 else "recusar")
        self.assertNotIn("variacoes", {i["tipo"] for i in pendencias.itens()})


class ReferenciaTest(Base):
    def test_telas_regua_e_aprovou(self):
        id_ = self.ref(gate=True)
        html = self.client.get(f"/referencia-rapida/{id_}").get_data(as_text=True)
        self.assertIn("Aprovou?", html)
        self.assertIn("Sim, confirmar e guardar", html)
        self.assertIn("Descartar", html)
        self.assertIn("Não vou copiar", html)
        self.assertIn("Quero 3 ideias de vídeo nesse estilo", html)
        # descartar vai pra lixeira (não apaga)
        r = self.client.post(f"/referencia-rapida/{id_}/descartar")
        self.assertEqual(r.status_code, 302)
        self.assertFalse((estilo_ref.ESTILOS / id_).exists())

    def test_set_de_dois_videos_uma_regua_e_variacoes(self):
        v2 = self.root / "ref2.mp4"
        shutil.copy2(self.video, v2)
        with mock.patch("estudo_quadros.estudar", return_value={"conjunto": {"base_sugerida": "x"}}) as est:
            cid = ref_conjunto.criar([str(self.video), str(v2)], "", "meu set", esperar=True)
        junta = [c for c in est.call_args_list if len(c.args[0]) == 2]            # 2 chamadas de 1 vídeo (cada ref) + 1 de 2
        self.assertEqual(len(junta), 1)                                          # a régua junta os dois
        self.assertEqual(len({Path(p).name for p in junta[0].args[0]}), 2)       # nomes distintos
        s = ref_conjunto.situacao(cid)
        self.assertTrue(s["todas_prontas"] and len(s["itens"]) == 2)
        html = self.client.get(f"/referencia-rapida/set/{cid}").get_data(as_text=True)
        self.assertIn("Sim, confirmar o set", html)
        self.assertIn("Quero 3 ideias de vídeo nesse estilo", html)
        tipos = [i for i in pendencias.itens() if i["tipo"] == "referencia"]
        self.assertEqual(len(tipos), 1)                                        # o set é UM item (não dois)
        self.assertEqual(tipos[0]["url"], f"/referencia-rapida/set/{cid}")
        with mock.patch.object(variacoes.ia, "executar", ia_variacoes()):
            vid = variacoes.propor([r for r in s["conjunto"]["refs"]], esperar=True)
        st = variacoes.estado(vid)
        self.assertEqual(st["estado"], "proposta")
        self.assertEqual(len(st["variacoes"]), 3)
        self.assertEqual({v["estado"] for v in st["variacoes"]}, {"proposta"})
        html = self.client.get(f"/variacoes/{vid}").get_data(as_text=True)
        self.assertIn("Fazer este vídeo", html)                                # o clique aqui é o Aprovou?
        self.assertIn("ideias de vídeo nesse estilo", html)
        with self.assertRaises(ValueError):
            variacoes.roteiro_de(vid, 1)                                       # nada aprovado ainda
        r = self.client.post(f"/variacoes/{vid}/1/aprovar")
        self.assertIn("/criar-agora?variacao=", r.headers["Location"])          # abre o Criar já preenchido
        html = self.client.get(f"/variacoes/{vid}").get_data(as_text=True)
        self.assertIn("Abrir no Criar", html)
        self.assertEqual(variacoes.roteiro_de(vid, 1)["titulo"], "Variação 1")
        criar = self.client.get(f"/criar-agora?variacao={vid}:1").get_data(as_text=True)
        self.assertIn("linha um 1", criar)                                      # o Criar chega com o roteiro escrito
        # descartar o set manda tudo pra lixeira
        self.client.post(f"/referencia-rapida/set/{cid}/descartar")
        self.assertFalse(ref_conjunto.pasta(cid).exists())

    def test_variacao_que_copia_a_fala_e_recusada(self):
        id_ = self.ref(gate=True)

        def copia(prompt, log, raw, pid, s=None, on_event=None, tipo=None):
            itens = [{"titulo": "x", "ideia": "i", "gancho": "hoje eu vou te mostrar como dobrar suas vendas em trinta dias",
                      "roteiro_curto": "a", "mantem": "m", "muda": "n"}] * 3
            (Path(log).parent / "variacoes.json").write_text(json.dumps({"variacoes": itens}))
            return 0
        with mock.patch.object(variacoes.ia, "executar", copia):
            vid = variacoes.propor([id_], esperar=True)
        self.assertEqual(variacoes.estado(vid)["estado"], "erro")


class EstiloNovoTest(Base):
    def test_nasce_em_teste_e_so_vira_pronto_no_aprovou(self):
        id_ = self.ref(gate=True)
        html = self.client.get(f"/referencia-rapida/{id_}").get_data(as_text=True)
        slug = estilo_novo.criar(id_, "legenda amarela")
        f = formatos.carregar(slug)
        self.assertTrue(f["oculto"] and f["em_teste"] and f["status"] == "receita")
        self.assertNotIn(slug, [x["slug"] for x in formatos.listar()])         # fora do Criar
        self.assertEqual(estilo_novo.estado(slug)["primeiro_video"]["estado"], "a_propor")
        with self.assertRaises(ValueError):
            estilo_novo.aprovar_video(slug)                                     # sem vídeo, sem aprovar
        with mock.patch.object(variacoes.ia, "executar", ia_variacoes(1)):
            estilo_novo.propor_primeiro(slug, esperar=True)
        self.assertEqual(estilo_novo.estado(slug)["primeiro_video"]["estado"], "proposta")
        self.assertIn("Aprovar a proposta", self.client.get(f"/estilo-novo/{slug}").get_data(as_text=True))
        estilo_novo.aprovar_proposta(slug)
        estilo_novo.registrar_video(slug, self.video)
        pv = estilo_novo.estado(slug)["primeiro_video"]
        self.assertEqual(pv["estado"], "esperando")
        self.assertIn("estilo_novo", {i["tipo"] for i in pendencias.itens()})
        self.assertIn("Sim, aprovei", self.client.get(f"/estilo-novo/{slug}").get_data(as_text=True))
        faltas = estilo_novo.aprovar_video(slug)
        # um estilo de teste recém-nascido não cumpre o contrato: não vira pronto, e continua em teste
        self.assertTrue(faltas)
        self.assertNotEqual(formatos.carregar(slug)["status"], "pronto")
        self.assertTrue(formatos.carregar(slug)["em_teste"])
        # pedir ajuste volta a "ajustar" e continua em teste
        estilo_novo.pedir_ajuste(slug, "o gancho está lento")
        self.assertEqual(estilo_novo.estado(slug)["primeiro_video"]["estado"], "ajustar")
        remover.remover_estilo(slug)                                            # tira o estilo de teste pra lixeira
        self.assertFalse((formatos.FORMATOS / slug).exists())

    def test_rota_criar_estilo_nao_vira_pronto(self):
        id_ = self.ref(gate=True)
        r = self.client.post(f"/referencia-rapida/{id_}/criar-estilo", data={"nome": "estilo rota"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/estilo-novo/estilo-rota", r.headers["Location"])
        f = formatos.carregar("estilo-rota")
        self.assertTrue(f["em_teste"] and f["status"] != "pronto")


class EstudarEVirarReferencia(Base):
    def _estudo(self):
        d = estudos_tela.PASTA / "e2"
        (d / "videos").mkdir(parents=True)
        (d / "estudo-quadros/folhas").mkdir(parents=True)
        shutil.copy2(self.video, d / "videos/video-1.mp4")
        (d / "estudo-quadros/ESTUDO-QUADROS.md").write_text("# estudo")
        C.gravar_json(d / "estado.json", {"nome": "Estudo teste", "pronto": True, "rodando": False, "gate": True})
        return "e2"

    def test_juntar_pede_confirmacao(self):
        sid = self._estudo()
        r = self.client.post(f"/estudar/{sid}/juntar", data={"formato": "teste-f3"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("juntar=teste-f3", r.headers["Location"])
        self.assertFalse((formatos.FORMATOS / "teste-f3" / "estudos").exists())   # nada guardado ainda
        html = self.client.get(f"/estudar/{sid}?juntar=teste-f3").get_data(as_text=True)
        self.assertIn("Aprovou?", html)
        self.assertIn("formatos/teste-f3/estudos/01-", html)
        self.assertIn("estudo", {i["tipo"] for i in pendencias.itens()})
        self.client.post(f"/estudar/{sid}/juntar", data={"formato": "teste-f3", "confirmar": "1"})
        self.assertTrue(any((formatos.FORMATOS / "teste-f3" / "estudos").iterdir()))
        self.assertNotIn("estudo", {i["tipo"] for i in pendencias.itens()})       # juntado sai da lista

    def test_virar_referencia_pede_confirmacao(self):
        j = self.job("concluido", "v6")
        j["formato"] = "teste-f3"
        j["saida"] = str(self.content.relative_to(self.root) / "output/estilo/v6.mp4")
        shutil.copy2(self.video, self.root / j["saida"])
        import producao
        producao.salvar(j)
        html = self.client.get("/videos/Teste/v6/virar-referencia").get_data(as_text=True)
        self.assertIn("Guardar como referência?", html)
        self.assertIn("formatos/teste-f3/estudos/01-", html)
        self.assertFalse((formatos.FORMATOS / "teste-f3" / "estudos").exists())
        self.client.post("/videos/Teste/v6/virar-referencia")                      # sem confirmar: não guarda
        self.assertFalse((formatos.FORMATOS / "teste-f3" / "estudos").exists())
        self.client.post("/videos/Teste/v6/virar-referencia", data={"confirmar": "1"})
        self.assertTrue(any((formatos.FORMATOS / "teste-f3" / "estudos").iterdir()))


class AutonomiaTest(Base):
    """O Estúdio decide sozinho a qual estilo juntar e só avisa, com Desfazer (a aprovação do João fica pro vídeo final)."""

    def test_referencia_junta_sozinha_e_desfaz(self):
        id_ = self.ref(gate=True, auto=True)
        st = estilo_ref.estado(id_)
        self.assertEqual(st["estado"], "confirmado")
        self.assertEqual(st["auto_feito"]["formato"], "teste-f3")
        self.assertNotIn("referencia", {i["tipo"] for i in pendencias.itens()})   # não pede decisão
        av = [i for i in pendencias.itens() if i["tipo"] == "aviso"]
        self.assertEqual(len(av), 1)
        self.assertEqual(av[0]["titulo"], "Juntei ao Teste")
        self.assertEqual([a["label"] for a in av[0]["acoes"]], ["Tá bom", "Desfazer"])
        html = self.client.get("/aprovar").get_data(as_text=True)
        self.assertIn("Juntei ao Teste", html)
        self.assertIn("Desfazer", html)
        self.assertTrue(any((formatos.FORMATOS / "teste-f3" / "estudos").iterdir()))
        self.client.post(f"/auto/ref/{id_}/desfazer")
        self.assertEqual(estilo_ref.estado(id_)["estado"], "pronto")                # voltou pro João decidir
        self.assertFalse(any((formatos.FORMATOS / "teste-f3" / "estudos").iterdir()))   # foi pra lixeira
        tipos = {i["tipo"] for i in pendencias.itens()}
        self.assertIn("referencia", tipos)
        self.assertNotIn("aviso", tipos)

    def test_ok_some_o_aviso_e_mantem(self):
        id_ = self.ref(gate=True, auto=True)
        self.client.post(f"/auto/ref/{id_}/ok")
        self.assertNotIn("aviso", {i["tipo"] for i in pendencias.itens()})
        self.assertEqual(estilo_ref.estado(id_)["estado"], "confirmado")

    def test_sem_estilo_parecido_nasce_estilo_novo_em_teste(self):
        estilo = F3.estilo_ok(formato_sugerido={"slug": "novo", "nota": 20, "porque": "nada serve"})
        with mock.patch.object(estilo_ref.ia, "executar", F3.ia_falsa(estilo)):
            id_ = self.ref(gate=True, auto=True)
        info = estilo_ref.estado(id_)["auto_feito"]
        self.assertTrue(info["novo"])
        f = formatos.carregar(info["formato"])
        self.assertTrue(f["em_teste"] and f["oculto"] and f["status"] != "pronto")
        self.assertIn("Criei o estilo novo", [i["titulo"] for i in pendencias.itens() if i["tipo"] == "aviso"][0])
        self.client.post(f"/auto/ref/{id_}/desfazer")
        self.assertIsNone(formatos.carregar(info["formato"]))                       # o estilo de teste foi pra lixeira

    def test_estudo_junta_sozinho(self):
        d = estudos_tela.PASTA / "e3"
        (d / "videos").mkdir(parents=True)
        (d / "estudo-quadros/folhas").mkdir(parents=True)
        shutil.copy2(self.video, d / "videos/video-1.mp4")
        (d / "estudo-quadros/ESTUDO-QUADROS.md").write_text("# estudo")
        C.gravar_json(d / "estado.json", {"nome": "Estudo Auto", "pronto": True, "rodando": False, "gate": True})
        info = auto_juntar.estudo("e3")
        self.assertTrue(info["novo"])                                               # sem estudo parecido: estilo novo em teste
        self.assertNotIn("estudo", {i["tipo"] for i in pendencias.itens()})
        self.assertEqual([i["tipo"] for i in pendencias.itens()].count("aviso"), 1)
        auto_juntar.desfazer("estudo", "e3")
        self.assertIn("estudo", {i["tipo"] for i in pendencias.itens()})
        self.assertIsNone(formatos.carregar(info["formato"]))


if __name__ == "__main__":
    unittest.main()
