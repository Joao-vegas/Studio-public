"""Contrato de formato (formatos/CONTRATO.md): todo formato PRONTO passa no validar(); o formatos/_modelo também.

Os formatos de verdade só são LIDOS (validar() não grava nada). O resto usa formatos temporários (test_esteira.Base):
nada pago, nada no catálogo real."""
import contextlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures   # noqa: F401  (põe app/ferramentas no caminho)
import formatos
from test_esteira import Base, ETAPAS

C, P = fixtures.C, fixtures.P
REAL = formatos.FORMATOS          # o catálogo de verdade (antes de qualquer patch dos testes temporários)


def _reais() -> list[tuple[str, str]]:
    """(slug, status) de cada formato do catálogo de verdade, inclusive os ocultos."""
    out = []
    for d in sorted(REAL.iterdir()):
        if d.is_dir() and not d.name.startswith((".", "_")) and (d / "formato.json").is_file():
            out.append((d.name, (json.loads((d / "formato.json").read_text(encoding="utf-8")) or {}).get("status", "")))
    return out


class ContratoDosFormatosDeVerdade(unittest.TestCase):
    def test_modelo_cumpre_o_contrato(self):
        self.assertEqual(formatos.validar("_modelo"), [])

    def test_todo_formato_pronto_cumpre_o_contrato(self):
        for slug, status in _reais():
            if status != "pronto":
                continue
            with self.subTest(formato=slug):
                faltas = formatos.validar(slug)
                if faltas:
                    self.fail(f"{slug} está \"pronto\" mas não cumpre formatos/CONTRATO.md "
                              f"(python3 app/ferramentas/formatos.py validar {slug}):\n  - " + "\n  - ".join(faltas))

    def test_receitas_aparecem_na_lista(self):
        """Receita pode ter falta: o teste só lista (não reprova)."""
        linhas = []
        for slug, status in _reais():
            faltas = formatos.validar(slug)
            self.assertIsInstance(faltas, list)
            self.assertTrue(all(isinstance(x, str) and x for x in faltas))
            if status != "pronto" and faltas:
                linhas.append(f"  {slug} ({status or 'sem status'}): " + "; ".join(faltas))
        if linhas:
            print("\nFormatos em receita com falta no contrato (não reprova):\n" + "\n".join(linhas), file=sys.stderr)

    def test_formatos_reais_declaram_declaram_material_e_o_passo_0(self):
        """Pronto ou receita: todo formato de hoje passa nos itens novos do contrato (material_aceito e passo 0)."""
        reais = _reais()
        self.assertGreaterEqual(len(reais), 8)
        for slug, _status in reais + [("_modelo", "receita")]:
            with self.subTest(formato=slug):
                novas = [x for x in formatos.validar(slug) if "material_aceito" in x or "passo 0" in x]
                self.assertEqual(novas, [])
        ex = json.loads((REAL / "explicador-3d/formato.json").read_text(encoding="utf-8"))
        self.assertNotIn("mockup", ex["material_aceito"])   # o motor do Explicador 3D não tem lugar pra mockup

    def test_todo_formato_tem_status_e_o_status_vale(self):
        for slug, status in _reais():
            with self.subTest(formato=slug):
                self.assertIn(status, formatos.STATUS)


COMO = "# Como fazer\n\n" + "\n".join(f"{i}. **{e['titulo']}.** {e['faz']}" for i, e in enumerate(ETAPAS, 1)) + "\n\n## Som e cena de apoio\n\nMúsica calma; sem efeito; sem cena de apoio.\n"
SOM = {"musica": {"usa": True, "de_onde": "Mixkit grátis", "clima": "calma", "volume": "baixa", "quando_nao": "no gancho"},
       "efeitos": {"usa": False, "de_onde": ""}}
APOIO = {"usa": False, "quando_nao": "sempre"}
PEDE = [{"campo": "video", "rotulo": "Vídeo gravado", "tipo": "arquivo_ou_link", "obrigatorio": True, "principal": True}]
BRIEF = {"id": "briefing", "titulo": "Briefing", "andamento": "preparar", "aprovar": True,
         "faz": "Ler o BRIEFING DESTE VÍDEO e usar o material liberado no papel marcado."}
PASSOS = [BRIEF] + ETAPAS     # o passo 0 (briefing) e os passos do formato


class Contrato(Base):
    def formato_ok(self, slug="doc-ok", tipo="motor"):
        d = self.criar_formato(slug=slug, modelos=(slug,))
        self.mexer(d, tipo=tipo, proporcao="9:16", som=SOM, apoio=APOIO, pede=PEDE, esteira={"etapas": PASSOS}, material_aceito=["foto-pessoa", "print"],
                   layouts=["cheio"], legenda={"desligavel": False, "motivo": "Já sai sem legenda."})
        (d / "COMO-FAZER.md").write_text(COMO, encoding="utf-8")
        C.gravar_json(d / "aprendizado/regras.json", {"regras": [{"id": "cena-curta", "titulo": "Cena até 2,5 s",
                                                                  "texto": "Nenhuma cena passa de 2,5 s."}]})
        self.assertTrue(formatos.fazer_folha(d / "exemplo-1.mp4", d / "exemplo-1-folha.jpg"))
        return d

    def formato_gravado(self, slug="grav", render="bash <sandbox>/gerar.sh", status="pronto"):
        (self.mod / "gerar.sh").write_text("echo render")
        (self.root / "app/ferramentas").mkdir(parents=True, exist_ok=True)
        (self.root / "app/ferramentas/storyboard.py").write_text("print('storyboard')"); (self.root / "app/ferramentas/conferir_video.py").write_text("print('conferir')")
        d = self.formato_ok(slug=slug, tipo="gravado")
        shutil.rmtree(d / "base")
        est = {"etapas": PASSOS, **({"comandos": {"render": render}} if render else {})}
        self.mexer(d, base="clientes/Teste/testeContent/modelos/estilo", modelos=["estilo"], esteira=est, status=status,
                   motor="ffmpeg + PIL")
        return d

    def mexer(self, d, **campos):
        dados = C.ler_json(d / "formato.json")
        for k, v in campos.items():
            if v is None:
                dados.pop(k, None)
            else:
                dados[k] = v
        C.gravar_json(d / "formato.json", dados)

    def faltas(self, slug="doc-ok"):
        return " | ".join(formatos.validar(slug))


class Validar(Contrato):
    def test_formato_completo_nao_tem_falta(self):
        self.formato_ok()
        self.assertEqual(formatos.validar("doc-ok"), [])

    def test_formato_que_nao_existe(self):
        self.assertIn("não encontrado", self.faltas("nao-existe"))
        self.assertIn("não encontrado", self.faltas("../x"))

    def test_basico_status_e_tipo(self):
        d = self.formato_ok()
        self.mexer(d, tipo=None, status="quase", entrada="podcast", proporcao=None)
        txt = self.faltas()
        for esperado in ('"tipo"', '"status"', '"entrada"', '"proporcao"'):
            self.assertIn(esperado, txt)

    def test_sem_esteira(self):
        d = self.formato_ok()
        self.mexer(d, esteira=None)
        self.assertIn('falta a "esteira"', self.faltas())

    def test_esteira_malformada_e_etapa_sem_faz(self):
        d = self.formato_ok()
        self.mexer(d, esteira={"etapas": [{"id": "a", "titulo": "A"}]})   # sem aprovar
        self.assertIn("malformada", self.faltas())
        etapas = [dict(e) for e in ETAPAS]
        etapas[1].pop("faz")
        etapas[0].pop("andamento")
        self.mexer(d, esteira={"etapas": etapas})
        txt = self.faltas()
        self.assertIn('"Cenas por frase" sem "faz"', txt)
        self.assertIn('"Transcrever a fala" sem "andamento"', txt)

    def test_a_primeira_parada_e_o_storyboard(self):
        d = self.formato_ok()
        etapas = [dict(e) for e in ETAPAS]
        etapas[0]["aprovar"] = True   # para na fala, antes do storyboard
        self.mexer(d, esteira={"etapas": etapas})
        self.assertIn("tem que ser o storyboard", self.faltas())

    def test_depois_do_storyboard_vem_video_e_por_ultimo_a_conferencia(self):
        d = self.formato_ok()
        self.mexer(d, esteira={"etapas": ETAPAS[:3]})
        txt = self.faltas()
        self.assertIn("etapa do vídeo", txt)
        self.assertIn("conferência", txt)

    def test_motor_incompleto_ou_base_fora_do_formato(self):
        d = self.formato_ok()
        (d / "base/index.html").unlink()
        self.assertIn("falta index.html", self.faltas())
        self.mexer(d, base="clientes/Teste/testeContent/modelos/estilo")
        self.assertIn("formatos/doc-ok/base", self.faltas())

    def test_comando_com_arquivo_que_nao_existe(self):
        d = self.formato_ok()
        self.mexer(d, esteira={"etapas": ETAPAS, "comandos": {"render": "python3 <sandbox>/motor2.py",
                                                               "conferir": "python3 app/ferramentas/nao_tem.py <sandbox>"}})
        txt = self.faltas()
        self.assertIn("<sandbox>/motor2.py", txt)
        self.assertIn("app/ferramentas/nao_tem.py", txt)

    def test_exemplo_principal_precisa_de_folha_e_legenda(self):
        d = self.formato_ok()
        (d / "exemplo-1-folha.jpg").unlink()
        self.assertIn("python3 app/ferramentas/formatos.py folha doc-ok", self.faltas())
        dados = C.ler_json(d / "formato.json")
        dados["exemplos"][0]["legenda"] = ""
        dados["exemplos"].append({"arquivo": "exemplo-9.mp4"})
        C.gravar_json(d / "formato.json", dados)
        txt = self.faltas()
        self.assertIn('sem "legenda"', txt)
        self.assertIn("exemplo 2 (exemplo-9.mp4)", txt)

    def test_sem_exemplo_fica_receita(self):
        """Receita sem exemplo não é falta; pronto sem exemplo é (só o oculto pode esperar o exemplo)."""
        d = self.formato_ok()
        self.mexer(d, exemplos=[])
        self.assertIn('"pronto" sem exemplo', self.faltas())
        self.mexer(d, status="receita")
        self.assertEqual(formatos.validar("doc-ok"), [])
        self.mexer(d, status="pronto", oculto=True)
        self.assertEqual(formatos.validar("doc-ok"), [])

    def test_sem_material_aceito_nao_passa(self):
        d = self.formato_ok()
        self.mexer(d, material_aceito=None)
        self.assertIn('falta "material_aceito"', self.faltas())
        self.mexer(d, material_aceito="logo")
        self.assertIn('falta "material_aceito"', self.faltas())
        self.mexer(d, material_aceito=["logo", "holograma"])
        self.assertIn("não conhece: holograma", self.faltas())
        self.mexer(d, material_aceito=[])            # não usa material nenhum: vale
        self.assertEqual(formatos.validar("doc-ok"), [])

    def test_passo_0_briefing_vem_primeiro_e_nao_e_a_parada(self):
        d = self.formato_ok()
        est = formatos.esteira(C.ler_json(d / "formato.json"))
        self.assertEqual(est["etapas"][0]["id"], "briefing")
        self.assertEqual(est["etapas"][est["parada"]]["id"], "storyboard")   # a tela continua parando no storyboard
        self.mexer(d, esteira={"etapas": ETAPAS})                              # sem o passo 0
        self.assertIn('falta o passo 0 "briefing"', self.faltas())
        self.mexer(d, esteira={"etapas": ETAPAS[:1] + [BRIEF] + ETAPAS[1:]})   # fora do começo
        self.assertIn('falta o passo 0 "briefing"', self.faltas())
        self.mexer(d, esteira={"etapas": [{**BRIEF, "aprovar": False}] + ETAPAS})
        self.assertIn('falta o passo 0 "briefing"', self.faltas())

    def test_som_diz_se_usa_e_de_onde_vem(self):
        d = self.formato_ok()
        self.mexer(d, som=None)
        self.assertIn('falta "som"', self.faltas())
        self.mexer(d, som={"musica": {"usa": True, "de_onde": ""}, "efeitos": {}})
        txt = self.faltas()
        self.assertIn("som.musica", txt)
        self.assertIn("som.efeitos", txt)

    def test_regras_com_titulo(self):
        d = self.formato_ok()
        C.gravar_json(d / "aprendizado/regras.json", {"regras": [{"id": "a", "texto": "x"}, {"id": "a", "titulo": "B", "texto": "y"}]})
        txt = self.faltas()
        self.assertIn('"a" sem "titulo"', txt)
        self.assertIn("duas vezes", txt)
        (d / "aprendizado/regras.json").unlink()
        self.assertIn("aprendizado/regras.json", self.faltas())

    def test_regras_md_precisa_de_titulos(self):
        d = self.formato_ok()
        (d / "aprendizado/regras.md").write_text("| ID | Regra |\n|---|---|\n| M1 | Cena curta. |\n| M2 | Música alta. |\n")
        C.gravar_json(d / "aprendizado/titulos.json", {"M1": "Cena curta"})
        self.assertIn("M2", self.faltas())
        C.gravar_json(d / "aprendizado/titulos.json", {"M1": "Cena curta", "M2": "Música alta"})
        self.assertEqual(formatos.validar("doc-ok"), [])

    def test_como_fazer_curto_e_na_ordem_da_esteira(self):
        d = self.formato_ok()
        (d / "COMO-FAZER.md").unlink()
        self.assertIn("falta o COMO-FAZER.md", self.faltas())
        linhas = COMO.splitlines()
        (d / "COMO-FAZER.md").write_text("\n".join(linhas[:2] + [linhas[3], linhas[2]] + linhas[4:]))   # 2 antes do 1
        self.assertIn('passo "Cenas por frase"', self.faltas())
        (d / "COMO-FAZER.md").write_text(COMO + "linha\n" * formatos.COMO_FAZER_MAX_LINHAS)
        self.assertIn("linhas: até", self.faltas())

    def test_pronto_nao_tem_sobra_do_modelo(self):
        d = self.formato_ok()
        (d / "COMO-FAZER.md").write_text(COMO + f"\n{formatos.MARCA_MODELO} quando usar\n")
        (d / "base/render.py").write_text(f"# {formatos.MARCA_MODELO} esqueleto")
        txt = self.faltas()
        self.assertIn("COMO-FAZER.md", txt)
        self.assertIn("base/render.py", txt)
        self.mexer(d, status="receita")   # receita pode ter: ainda está sendo construída
        self.assertEqual(formatos.validar("doc-ok"), [])


class Gravado(Contrato):
    def test_gravado_completo_nao_tem_falta(self):
        self.formato_gravado()
        self.assertEqual(formatos.validar("grav"), [])

    def test_gravado_declara_o_render(self):
        self.formato_gravado(render="")
        self.assertIn("esteira.comandos.render", self.faltas("grav"))
        self.formato_gravado(slug="grav2", render="bash <sandbox>/nao-tem.sh")
        self.assertIn("<sandbox>/nao-tem.sh", self.faltas("grav2"))

    def test_gravado_aponta_uma_base_que_existe(self):
        d = self.formato_gravado()
        self.mexer(d, base="clientes/Teste/testeContent/modelos/nao-tem")
        self.assertIn("não existe ou está vazia", self.faltas("grav"))
        self.mexer(d, base="")
        self.assertIn('"base" vazio', self.faltas("grav"))

    def test_gravado_continua_na_tela_de_video_gravado(self):
        """Declarar os passos não troca a tela: escolha das cenas continua, usar() não pede motor, a IA recebe os passos."""
        self.formato_gravado(status="receita")
        f = formatos.carregar("grav")
        self.assertFalse(formatos.segue_esteira(f))
        self.assertIsNone(formatos.esteira_do_job({"formato": "grav"}))
        self.assertIn("cenas", [e["campo"] for e in formatos.escolhas(f)])
        self.assertEqual(formatos.usar("grav", "Teste"), ("Teste", "estilo"))
        self.assertEqual(formatos.esteira(f)["comandos"]["storyboard"], formatos.COMANDOS_GRAVADO["storyboard"])
        j = self.job_formato(formato="grav")
        self.assertFalse(fixtures.servidor._esteira(j))   # página do vídeo: a de vídeo gravado
        self.assertIsNone(P._esteira(j))
        txt = P.camadas_de_regra(j)
        self.assertIn("PASSOS DO FORMATO", txt)
        self.assertIn("gerar.sh", txt)
        self.assertIn("app/ferramentas/storyboard.py", txt)

    def test_motor_continua_seguindo_a_esteira(self):
        self.formato_ok()
        f = formatos.carregar("doc-ok")
        self.assertTrue(formatos.segue_esteira(f))
        self.assertEqual(formatos.esteira_do_job({"formato": "doc-ok"})["slug"], "doc-ok")
        self.assertNotIn("cenas", [e["campo"] for e in formatos.escolhas(f)])


class Modelo(Contrato):
    def setUp(self):
        super().setUp()
        shutil.copytree(REAL / "_modelo", self.formatos / "_modelo", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "app/ferramentas").mkdir(parents=True, exist_ok=True)
        (self.root / "app/ferramentas/storyboard.py").write_text("print('storyboard')"); (self.root / "app/ferramentas/conferir_video.py").write_text("print('conferir')")

    def test_modelo_fica_fora_do_catalogo(self):
        self.assertNotIn("_modelo", [f["slug"] for f in formatos.listar(ocultos=True)])

    def test_formato_novo_sem_material_aceito_nao_passa(self):
        formatos.novo_formato("sem-lista", titulo="Sem lista")
        d = self.formatos / "sem-lista"
        self.assertIsInstance(C.ler_json(d / "formato.json")["material_aceito"], list)   # nasce com a do _modelo
        self.mexer(d, material_aceito=None)
        self.assertIn('falta "material_aceito"', self.faltas("sem-lista"))

    def test_formato_novo_de_motor_nasce_do_modelo_e_cumpre(self):
        d = formatos.novo_formato("meu-formato", titulo="Meu formato")
        self.assertEqual(formatos.validar("meu-formato"), [])
        dados = C.ler_json(d / "formato.json")
        self.assertEqual((dados["tipo"], dados["status"], dados["base"], dados["modelos"]),
                         ("motor", "receita", "formatos/meu-formato/base", ["meu-formato"]))
        self.assertTrue((d / "base/render.py").is_file() and (d / "base/index.html").is_file())
        self.assertEqual(C.ler_json(d / "aprendizado/regras.json")["regras"], [])
        self.assertTrue((d / "COMO-FAZER.md").read_text().startswith("# Como fazer: Meu formato"))
        self.mexer(d, status="pronto")   # pronto exige trocar o que é do modelo
        self.assertIn(formatos.MARCA_MODELO, self.faltas("meu-formato"))

    def test_formato_novo_gravado_nasce_do_modelo_e_cumpre(self):
        (self.mod / "gerar.sh").write_text("echo render")
        d = formatos.novo_formato("meu-gravado", titulo="Meu gravado", tipo_="gravado",
                                  base="clientes/Teste/testeContent/modelos/estilo", modelo="estilo",
                                  render="bash <sandbox>/gerar.sh")
        self.assertEqual(formatos.validar("meu-gravado"), [])
        dados = C.ler_json(d / "formato.json")
        self.assertEqual((dados["tipo"], dados["base"]), ("gravado", "clientes/Teste/testeContent/modelos/estilo"))
        self.assertFalse((d / "base").exists())
        self.assertNotIn("motor_arquivos", dados["esteira"])

    def test_nome_invalido_ou_repetido_recusa(self):
        for nome in ("_outro", "Meu Formato", "", "a/b"):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                formatos.novo_formato(nome)
        formatos.novo_formato("repetido")
        with self.assertRaises(ValueError):
            formatos.novo_formato("repetido")

    def test_formato_de_referencia_nasce_do_modelo(self):
        from test_esteira import video
        (self.mod / "gerar.sh").write_text("echo render")
        ref = video(self.root / "ref.mp4")
        d = formatos.registrar_de_referencia("de-referencia", {"titulo": "De referência", "resumo": "Você e cenas.",
                                                               "motor": "ffmpeg + PIL"}, "Teste", self.mod, ref)
        dados = C.ler_json(d / "formato.json")
        self.assertEqual((dados["tipo"], dados["status"], dados["modelos"]), ("gravado", "receita", ["de-referencia"]))
        # a sandbox (<modelo>/_sandbox-<slug>) não tem cópia do gerar.sh: o render roda o do modelo, ../gerar.sh
        self.assertEqual(dados["esteira"]["comandos"]["render"], "bash ../gerar.sh")
        self.assertTrue((d / "exemplo-1-folha.jpg").is_file())
        self.assertEqual(formatos.validar("de-referencia"), [])


class Cli(Contrato):
    def rodar(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = formatos.main(["validar", *args])
        return code, out.getvalue()

    def test_um_formato(self):
        self.formato_ok()
        self.assertEqual(self.rodar("doc-ok"), (0, "ok    doc-ok (pronto)\n"))
        self.mexer(self.formatos / "doc-ok", som=None)
        code, txt = self.rodar("doc-ok")
        self.assertEqual(code, 1)
        self.assertIn('falta "som"', txt)

    def test_todos_so_reprova_pronto(self):
        self.formato_ok()
        d = self.formato_ok(slug="em-obra")
        self.mexer(d, status="receita", som=None)
        code, txt = self.rodar("--todos")
        self.assertEqual(code, 0)
        self.assertIn("aviso em-obra (receita)", txt)
        self.mexer(d, status="pronto")
        self.assertEqual(self.rodar()[0], 1)   # sem slug = todos


if __name__ == "__main__":
    unittest.main()
