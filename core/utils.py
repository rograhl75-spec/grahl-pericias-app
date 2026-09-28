import io
import unicodedata

from PIL import Image


def remover_acentos(texto):
    if not texto or not isinstance(texto, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def calcula_altura(texto, min_h):
    if not texto:
        return min_h
    texto_str = str(texto)
    linhas_quebradas = texto_str.count("\n") + 1
    caracteres_extras_wrap = sum(len(linha) // 80 for linha in texto_str.split("\n"))
    return max(min_h, (linhas_quebradas + caracteres_extras_wrap) * 24 + 40)


def comprimir_imagem(file_bytes):
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=60, optimize=True)
        return output.getvalue()
    except Exception:
        return file_bytes
