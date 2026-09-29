"""
OCR opcional para páginas escaneadas (imagem).

Usa ``pypdfium2`` (já instalado junto com o ``pdfplumber``) para renderizar a
página e ``pytesseract`` + binário ``tesseract`` para reconhecer o texto.
Se algo estiver ausente, :func:`check_ocr` informa o motivo e o lote continua
sem OCR (degradação graciosa).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OcrStatus:
    available: bool
    lang: str = ""
    reason: str = ""
    warnings: List[str] = field(default_factory=list)


def check_ocr(requested_lang: str = "por") -> OcrStatus:
    """Verifica se o OCR pode ser usado e escolhe o idioma disponível."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return OcrStatus(False, reason="Pacote Python 'pytesseract' não instalado (pip install -r requirements.txt).")

    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return OcrStatus(False, reason="Pacote Python 'pypdfium2' não instalado (pip install -r requirements.txt).")

    import pytesseract

    if shutil.which(pytesseract.pytesseract.tesseract_cmd) is None and shutil.which("tesseract") is None:
        return OcrStatus(
            False,
            reason=(
                "Programa 'tesseract' não encontrado no sistema. Instale o Tesseract OCR "
                "(ver README, seção Solução de problemas) ou defina TESSERACT_CMD."
            ),
        )

    try:
        idiomas = set(pytesseract.get_languages(config=""))
    except Exception as exc:  # pragma: no cover - depende do sistema
        return OcrStatus(False, reason=f"Falha ao consultar o Tesseract: {exc}")

    solicitados = [parte for parte in requested_lang.split("+") if parte]
    faltando = [idioma for idioma in solicitados if idioma not in idiomas]
    if not faltando:
        return OcrStatus(True, lang=requested_lang)

    aviso = (
        f"Idioma(s) OCR {', '.join(faltando)} não instalado(s) no Tesseract "
        f"(disponíveis: {', '.join(sorted(idiomas)) or 'nenhum'})."
    )
    if "eng" in idiomas:
        return OcrStatus(True, lang="eng", warnings=[aviso + " Usando 'eng' (qualidade menor para acentuação)."])
    return OcrStatus(False, reason=aviso)


def configure_tesseract_cmd(cmd: Optional[str]) -> None:
    """Permite apontar o executável do Tesseract (útil no Windows)."""
    if not cmd:
        return
    try:
        import pytesseract
    except ImportError:
        return
    pytesseract.pytesseract.tesseract_cmd = cmd


def ocr_page(pdf_document, page_index: int, lang: str, dpi: int, timeout_seconds: int) -> str:
    """Renderiza uma única página e aplica OCR (uma página por vez para poupar memória)."""
    import pytesseract

    page = pdf_document[page_index]
    bitmap = None
    image = None
    try:
        bitmap = page.render(scale=max(dpi, 72) / 72)
        image = bitmap.to_pil()
        return pytesseract.image_to_string(image, lang=lang, timeout=timeout_seconds or 0) or ""
    finally:
        if image is not None:
            image.close()
        if bitmap is not None:
            bitmap.close()
        page.close()
