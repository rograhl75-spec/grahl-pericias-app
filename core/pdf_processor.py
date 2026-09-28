"""
Extração de texto de arquivos PDF para análise com Claude.
Suporta múltiplos PDFs consolidados em um único texto.
"""

import pdfplumber
import streamlit as st
import logging
from typing import List, Tuple
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile

from core.config import obter_app_config

logger = logging.getLogger(__name__)


@contextmanager
def _arquivo_pdf_temporario(arquivo, prefixo: str):
    suffix = Path(arquivo.name).suffix or ".pdf"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefixo, dir="/tmp")
    try:
        temp.write(arquivo.getbuffer())
        temp.close()
        yield temp.name
    finally:
        try:
            os.remove(temp.name)
        except OSError:
            pass


def extrair_texto_pdf(caminho_pdf: str) -> Tuple[str, int]:
    """
    Extrai texto completo de um arquivo PDF.
    
    Args:
        caminho_pdf: Caminho do arquivo PDF
        
    Returns:
        Tupla: (texto_extraido, numero_de_paginas)
    """
    try:
        texto_completo = ""
        num_paginas = 0
        
        with pdfplumber.open(caminho_pdf) as pdf:
            num_paginas = len(pdf.pages)
            
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto_completo += f"\n--- PÁGINA {num_pagina} ---\n"
                    texto_completo += texto_pagina
                    texto_completo += "\n"
        
        logger.info(f"PDF extraído com sucesso: {caminho_pdf} ({num_paginas} páginas)")
        return texto_completo, num_paginas
        
    except pdfplumber.PDFError as e:
        st.error(f"❌ Erro ao ler PDF: {e}")
        logger.error(f"Erro ao extrair PDF {caminho_pdf}: {e}")
        return "", 0
    except Exception as e:
        st.error(f"❌ Erro inesperado ao processar PDF: {e}")
        logger.exception(f"Erro ao processar {caminho_pdf}: {e}")
        return "", 0


def consolidar_multiplos_pdfs(arquivos_pdf: List) -> Tuple[str, int]:
    """
    Extrai e consolida texto de múltiplos arquivos PDF em um único documento.
    
    Args:
        arquivos_pdf: Lista de objetos de arquivo do Streamlit
        
    Returns:
        Tupla: (texto_consolidado, total_paginas)
    """
    texto_consolidado = ""
    total_paginas = 0
    max_chars_total = int(obter_app_config().get("max_pdf_chars_total", 600_000))
    
    for idx, arquivo in enumerate(arquivos_pdf, 1):
        try:
            with _arquivo_pdf_temporario(arquivo, f"temp_pdf_{idx}_") as temp_path:
                texto, num_paginas = extrair_texto_pdf(temp_path)

            total_paginas += num_paginas

            if texto:
                cabecalho = f"\n\n{'='*80}\nARQUIVO {idx}: {arquivo.name}\n{'='*80}\n\n"
                tamanho_projetado = len(texto_consolidado) + len(cabecalho) + len(texto)
                if tamanho_projetado > max_chars_total:
                    raise ValueError(
                        f"O texto consolidado excede o limite seguro de {max_chars_total:,} caracteres."
                    )

                texto_consolidado += cabecalho + texto

                logger.info(
                    "PDF consolidado com sucesso",
                    extra={
                        "arquivo": arquivo.name,
                        "paginas": num_paginas,
                        "tamanho_bytes": arquivo.size,
                    },
                )
                    
        except Exception as e:
            st.error(f"❌ Erro ao processar {arquivo.name}: {e}")
            logger.exception("Erro ao consolidar PDF %s", arquivo.name)
            continue
    
    return texto_consolidado, total_paginas


def validar_pdfs(arquivos_pdf: List) -> Tuple[bool, str]:
    """
    Valida se os arquivos PDFs são válidos antes do processamento.
    
    Args:
        arquivos_pdf: Lista de objetos de arquivo
        
    Returns:
        Tupla: (válido, mensagem_erro)
    """
    config = obter_app_config()

    # Validar quantidade
    max_arquivos = int(config.get("max_pdf_files", 5))
    if len(arquivos_pdf) > max_arquivos:
        return False, f"❌ Máximo de {max_arquivos} PDFs permitidos. Você enviou {len(arquivos_pdf)}."
    
    # Validar tamanho total
    max_size_mb = int(config.get("max_file_size_mb", 200))
    max_size_bytes = max_size_mb * 1024 * 1024
    max_por_arquivo_mb = int(config.get("max_single_pdf_size_mb", 75))
    max_por_arquivo_bytes = max_por_arquivo_mb * 1024 * 1024
    
    tamanho_total = sum(arquivo.size for arquivo in arquivos_pdf)
    if tamanho_total > max_size_bytes:
        tamanho_total_mb = tamanho_total / (1024 * 1024)
        return False, f"❌ Tamanho total de {tamanho_total_mb:.1f}MB excede limite de {max_size_mb}MB."
    
    # Validar se são PDFs e respeitam o limite por arquivo
    for arquivo in arquivos_pdf:
        if arquivo.size > max_por_arquivo_bytes:
            tamanho_mb = arquivo.size / (1024 * 1024)
            return False, (
                f"❌ O arquivo '{arquivo.name}' tem {tamanho_mb:.1f}MB e excede o limite "
                f"individual de {max_por_arquivo_mb}MB."
            )

        if not arquivo.name.lower().endswith(".pdf"):
            return False, f"❌ Arquivo '{arquivo.name}' não é um PDF válido."
        
        # Verificação da assinatura mágica do PDF
        assinatura = bytes(arquivo.getbuffer()[:5])
        if assinatura != b"%PDF-":
            return False, f"❌ Arquivo '{arquivo.name}' não possui assinatura válida de PDF."
    
    return True, "✅ Validação OK"


def validar_limite_paginas(total_paginas: int) -> Tuple[bool, str]:
    max_paginas = int(obter_app_config().get("max_pdf_pages_total", 3000))

    if total_paginas < 0:
        return False, "❌ Não foi possível calcular o total de páginas dos PDFs enviados."

    if total_paginas > max_paginas:
        return False, (
            f"❌ O conjunto possui {total_paginas} páginas e excede o limite seguro "
            f"de {max_paginas} páginas."
        )

    return True, ""


def calcular_total_paginas(arquivos_pdf: List) -> int:
    """
    Calcula o número total de páginas sem extrair texto (apenas validação).
    
    Args:
        arquivos_pdf: Lista de objetos de arquivo
        
    Returns:
        Total de páginas
    """
    total = 0
    for arquivo in arquivos_pdf:
        try:
            with _arquivo_pdf_temporario(arquivo, "temp_count_") as temp_path:
                with pdfplumber.open(temp_path) as pdf:
                    if not pdf.pages:
                        raise ValueError("PDF sem páginas legíveis.")
                    total += len(pdf.pages)
        except Exception as exc:
            st.error(f"❌ Não foi possível inspecionar '{arquivo.name}': {exc}")
            logger.exception("Falha ao calcular páginas do PDF %s", arquivo.name)
            return -1
    
    return total
