"""Teste de fumaça dos motores: roda o comando mais barato de cada formato "motor" pronto, numa pasta
temporária, sem rede e sem nada pago (nada de IA, voz ou kie.ai). Cada caso confere que saiu uma imagem
não vazia. Um quadro só por motor. Falta Playwright, Chromium ou ffmpeg: o caso é pulado (skip)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
from _comum import com_venv, rodar_com_limite  # noqa: E402

ESTUDIO = Path(__file__).resolve().parents[2]
FORMATOS = ESTUDIO / "formatos"
PY = sys.executable
TEMPO = 120   # segundos por caso


def _ferramentas_faltando() -> str | None:
    if not shutil.which("ffmpeg"):
        return "ffmpeg não instalado"
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return "Playwright não instalado"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            if not Path(p.chromium.executable_path).exists():
                return "Chromium do Playwright não instalado"
    except Exception as e:  # noqa: BLE001
        return f"Playwright não abre: {str(e)[:80]}"
    return None


FALTA = _ferramentas_faltando()


def _imagem_ok(caminho: Path) -> bool:
    """PNG/JPG que existe, tem tamanho e não é uma cor só."""
    if not caminho.exists() or caminho.stat().st_size < 2000:
        return False
    try:
        from PIL import Image
        im = Image.open(caminho).convert("L")
        lo, hi = im.getextrema()
        return hi - lo > 8
    except ImportError:
        return True


def _pronto(slug: str) -> bool:
    try:
        d = json.loads((FORMATOS / slug / "formato.json").read_text(encoding="utf-8"))
    except OSError:
        return False
    return d.get("tipo") == "motor" and d.get("status") == "pronto"


def _rodar(cmd: list[str], cwd: Path):
    # com limite que não prende: render travado na saída (UE) é morto e abandonado, não segura a suíte
    return rodar_com_limite(cmd, TEMPO, cwd=cwd, capture_output=True, text=True, env=com_venv())


@unittest.skipIf(FALTA, FALTA or "")
class FumacaMotores(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fumaca-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _copiar_base(self, slug: str) -> Path:
        """Motores que gravam ao lado do render.py: roda numa cópia, o repositório não é tocado."""
        dst = self.tmp / slug
        shutil.copytree(FORMATOS / slug / "base", dst, ignore=shutil.ignore_patterns("__pycache__", "quadros"))
        return dst

    def test_documentario(self):
        if not _pronto("documentario"):
            self.skipTest("documentario não é motor pronto")
        base = FORMATOS / "documentario" / "base"
        out = self.tmp / "doc"
        r = _rodar([PY, str(base / "render.py"), "--cenas", str(base / "cenas-modelo.json"), "--out", str(out),
                    "--storyboard", "--sem-som", "--quadro", "3"], ESTUDIO)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-600:])
        self.assertTrue(_imagem_ok(out / "storyboard.jpg"), "storyboard vazio")
        quadros = list((out / "quadros").glob("*.png"))
        self.assertTrue(quadros and _imagem_ok(quadros[0]), "quadro vazio")
