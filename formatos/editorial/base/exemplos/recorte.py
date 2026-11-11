# Pessoa sem fundo (PNG) pra cena "recorte": rembg com o modelo isnet-general-use. Uso: python3 recorte.py <foto> <saida.png>
import sys
from pathlib import Path
from rembg import new_session, remove
from PIL import Image
src, dst = Path(sys.argv[1]), Path(sys.argv[2]); dst.parent.mkdir(parents=True, exist_ok=True)
img = remove(Image.open(src).convert("RGB"), session=new_session("isnet-general-use"))
img.crop(img.getbbox()).save(dst); print(dst, img.size)
