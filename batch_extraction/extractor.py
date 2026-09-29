"""
Extração de um único PDF, página a página.

Fluxo por página:
1. tenta o texto nativo (``pdfplumber``);
2. se a página tiver pouco texto (provável imagem/escaneada) e o OCR estiver
   disponível, aplica OCR somente nessa página;
3. alimenta o extrator de campos e libera o cache da página.

Assim, mesmo PDFs grandes (dezenas de MB) não são carregados inteiros em memória.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from batch_extraction.config import BatchConfig
from batch_extraction.fields import FieldExtractor
from batch_extraction.ocr import OcrStatus, ocr_page

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
PDF_SIGNATURE = b"%PDF-"
SIGNATURE_SEARCH_BYTES = 1024

STATUS_SUCCESS = "sucesso"
STATUS_PARTIAL = "parcial"
STATUS_FAILED = "falha"


class PdfValidationError(Exception):
    """PDF inválido ou fora dos limites configurados."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(chunk_size), b""):
            digest.update(bloco)
    return digest.hexdigest()


def validate_pdf_file(path: Path, max_size_mb: int) -> int:
    """Valida existência, tamanho e assinatura sem ler o arquivo inteiro. Retorna o tamanho em bytes."""
    if not path.is_file():
        raise PdfValidationError(f"Arquivo não encontrado: {path}")
    tamanho = path.stat().st_size
    if tamanho == 0:
        raise PdfValidationError("Arquivo vazio (0 bytes).")
    if max_size_mb > 0 and tamanho > max_size_mb * 1024 * 1024:
        raise PdfValidationError(
            f"Arquivo com {tamanho / (1024 * 1024):.1f} MB excede o limite de {max_size_mb} MB (BATCH_MAX_FILE_SIZE_MB)."
        )
    with open(path, "rb") as arquivo:
        inicio = arquivo.read(SIGNATURE_SEARCH_BYTES)
    if PDF_SIGNATURE not in inicio:
        raise PdfValidationError("Arquivo não possui assinatura de PDF válida (%PDF-). Pode estar corrompido.")
    return tamanho


def base_result(path: Path) -> dict:
    return {
        "versao_schema": SCHEMA_VERSION,
        "arquivo_origem": path.name,
        "caminho_origem": str(path),
        "tamanho_bytes": None,
        "sha256": None,
        "status": STATUS_FAILED,
        "inicio_processamento": now_iso(),
        "fim_processamento": None,
        "duracao_segundos": None,
        "tipo_pdf": "desconhecido",
        "metodo_extracao": "nenhum",
        "ocr": {"habilitado": False, "disponivel": False, "idioma": None, "paginas_ocr": 0},
        "paginas_total": 0,
        "paginas_processadas": 0,
        "total_caracteres": 0,
        "avisos": [],
        "erros": [],
        "campos_extraidos": {},
        "paginas": [],
    }


def _classify(low_text_pages: int, total: int) -> str:
    if total == 0:
        return "desconhecido"
    if low_text_pages == 0:
        return "texto"
    if low_text_pages == total:
        return "imagem"
    return "misto"


def _method(text_pages: int, ocr_pages: int) -> str:
    if ocr_pages and text_pages:
        return "misto"
    if ocr_pages:
        return "ocr"
    if text_pages:
        return "texto"
    return "nenhum"


def extract_pdf(
    path: Path,
    config: BatchConfig,
    ocr_status: Optional[OcrStatus] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Extrai texto + campos de um PDF e devolve o dicionário estruturado (sem gravar em disco)."""
    import pdfplumber

    path = Path(path)
    resultado = base_result(path)
    avisos: List[str] = resultado["avisos"]
    erros: List[str] = resultado["erros"]
    inicio = datetime.now()

    ocr_status = ocr_status or OcrStatus(False, reason="OCR não verificado.")
    usar_ocr = bool(config.ocr_enabled and ocr_status.available)
    resultado["ocr"] = {
        "habilitado": bool(config.ocr_enabled),
        "disponivel": bool(ocr_status.available),
        "idioma": ocr_status.lang if usar_ocr else None,
        "paginas_ocr": 0,
    }
    if usar_ocr:
        avisos.extend(ocr_status.warnings)

    try:
        resultado["tamanho_bytes"] = validate_pdf_file(path, config.max_file_size_mb)
        resultado["sha256"] = file_sha256(path)

        extrator = FieldExtractor()
        paginas_saida = resultado["paginas"]
        total_chars = 0
        texto_truncado = False
        paginas_pouco_texto = 0
        paginas_texto = 0
        paginas_ocr = 0
        paginas_com_erro = 0
        paginas_sem_ocr = 0
        paginas_ocr_usadas = 0
        paginas_com_texto = 0
        paginas_limitadas = False
        documento_pdfium = None

        try:
            with pdfplumber.open(str(path)) as pdf:
                total_paginas = len(pdf.pages)
                resultado["paginas_total"] = total_paginas
                limite = total_paginas
                if config.max_pages > 0 and total_paginas > config.max_pages:
                    limite = config.max_pages
                    paginas_limitadas = True
                    avisos.append(
                        f"PDF com {total_paginas} páginas; processadas apenas as primeiras {limite} (BATCH_MAX_PAGES)."
                    )

                for indice in range(limite):
                    numero = indice + 1
                    metodo_pagina = "texto"
                    texto = ""
                    pagina = pdf.pages[indice]
                    try:
                        texto = pagina.extract_text() or ""
                    except Exception as exc:
                        paginas_com_erro += 1
                        avisos.append(f"Página {numero}: falha na extração de texto nativo ({exc}).")
                        logger.warning("%s | página %s: falha no texto nativo: %s", path.name, numero, exc)
                    finally:
                        try:
                            pagina.close()
                        except Exception:  # pragma: no cover - defensivo
                            pass

                    if len(texto.strip()) < config.min_chars_per_page:
                        paginas_pouco_texto += 1
                        if usar_ocr and paginas_ocr < config.max_ocr_pages:
                            try:
                                if documento_pdfium is None:
                                    import pypdfium2

                                    documento_pdfium = pypdfium2.PdfDocument(str(path))
                                texto_ocr = ocr_page(
                                    documento_pdfium,
                                    indice,
                                    lang=ocr_status.lang,
                                    dpi=config.ocr_dpi,
                                    timeout_seconds=config.ocr_page_timeout_seconds,
                                )
                                paginas_ocr += 1
                                if len(texto_ocr.strip()) >= len(texto.strip()):
                                    texto = texto_ocr
                                    metodo_pagina = "ocr"
                            except Exception as exc:
                                paginas_com_erro += 1
                                avisos.append(f"Página {numero}: falha no OCR ({exc}).")
                                logger.warning("%s | página %s: falha no OCR: %s", path.name, numero, exc)
                        else:
                            paginas_sem_ocr += 1

                    if texto.strip():
                        paginas_com_texto += 1
                        if metodo_pagina == "ocr":
                            paginas_ocr_usadas += 1
                        else:
                            paginas_texto += 1

                    extrator.feed(numero, texto)
                    caracteres = len(texto)
                    registro = {"numero": numero, "metodo": metodo_pagina, "caracteres": caracteres}
                    if config.include_text:
                        if not texto_truncado and total_chars + caracteres > config.max_text_chars > 0:
                            texto_truncado = True
                            avisos.append(
                                f"Texto excedeu {config.max_text_chars} caracteres; o texto das páginas "
                                f"a partir da {numero} não foi incluído no JSON (campos continuam sendo extraídos)."
                            )
                        if not texto_truncado:
                            registro["texto"] = texto
                    total_chars += caracteres
                    paginas_saida.append(registro)
                    resultado["paginas_processadas"] = numero

                    if progress is not None:
                        progress(numero, limite)
        finally:
            if documento_pdfium is not None:
                documento_pdfium.close()

        resultado["total_caracteres"] = total_chars
        resultado["ocr"]["paginas_ocr"] = paginas_ocr
        resultado["tipo_pdf"] = _classify(paginas_pouco_texto, resultado["paginas_processadas"])
        resultado["metodo_extracao"] = _method(paginas_texto, paginas_ocr_usadas)
        resultado["campos_extraidos"] = extrator.result()

        if paginas_sem_ocr:
            if not config.ocr_enabled:
                motivo = "OCR desativado (BATCH_OCR_ENABLED=0 / --no-ocr)"
            elif not ocr_status.available:
                motivo = f"OCR indisponível: {ocr_status.reason}"
            else:
                motivo = f"limite de páginas com OCR atingido (BATCH_MAX_OCR_PAGES={config.max_ocr_pages})"
            avisos.append(f"{paginas_sem_ocr} página(s) com pouco/nenhum texto não passaram por OCR: {motivo}.")

        if resultado["paginas_total"] == 0:
            erros.append("PDF sem páginas.")
        elif paginas_com_texto == 0:
            erros.append("Nenhum texto extraído do PDF (provavelmente escaneado e sem OCR disponível).")

        if erros:
            resultado["status"] = STATUS_FAILED
        elif paginas_com_erro or paginas_sem_ocr or paginas_limitadas:
            resultado["status"] = STATUS_PARTIAL
        else:
            resultado["status"] = STATUS_SUCCESS
    except PdfValidationError as exc:
        erros.append(str(exc))
        resultado["status"] = STATUS_FAILED
    except Exception as exc:
        logger.exception("Erro ao processar %s", path.name)
        erros.append(f"{type(exc).__name__}: {exc}")
        resultado["status"] = STATUS_FAILED
    finally:
        resultado["fim_processamento"] = now_iso()
        resultado["duracao_segundos"] = round((datetime.now() - inicio).total_seconds(), 2)

    return resultado
