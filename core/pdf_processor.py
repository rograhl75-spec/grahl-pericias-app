"""
Extração de texto de arquivos PDF para análise com Claude.
Suporta múltiplos PDFs consolidados em um único texto.
"""

import logging
from contextlib import contextmanager
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import pdfplumber
import streamlit as st

from core.config import obter_app_config

logger = logging.getLogger(__name__)


def _formatar_inteiro(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def tamanho_arquivo_seguro(arquivo) -> int:
    """Retorna o tamanho do upload em bytes sem propagar falhas do objeto de arquivo."""
    try:
        return max(int(getattr(arquivo, "size", 0) or 0), 0)
    except (TypeError, ValueError):
        logger.warning("Não foi possível ler o tamanho do arquivo enviado.")
        return 0


def _primeiros_bytes(arquivo, quantidade: int) -> bytes:
    """Lê com segurança os primeiros bytes de um upload do Streamlit."""
    for metodo in ("getbuffer", "getvalue"):
        leitor = getattr(arquivo, metodo, None)
        if not callable(leitor):
            continue
        try:
            conteudo = leitor()
        except Exception:
            logger.exception("Falha ao ler conteúdo do arquivo enviado via %s", metodo)
            continue
        try:
            return bytes(conteudo[:quantidade])
        except Exception:
            logger.exception("Conteúdo do arquivo enviado em formato inesperado (%s)", metodo)
    return b""


@contextmanager
def _arquivo_pdf_temporario(arquivo, prefixo: str):
    nome = getattr(arquivo, "name", "arquivo_sem_nome")
    suffix = Path(nome).suffix or ".pdf"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefixo, dir="/tmp")
    try:
        try:
            conteudo = arquivo.getbuffer()
        except Exception as exc:
            logger.exception("Falha ao obter o conteúdo do arquivo enviado %s", nome)
            raise ValueError(
                f"Não foi possível ler o conteúdo de '{nome}'. "
                "Reenvie o arquivo ou substitua por uma versão íntegra do PDF."
            ) from exc
        temp.write(conteudo)
        temp.close()
        yield temp.name
    finally:
        try:
            os.remove(temp.name)
        except OSError:
            pass


def extrair_texto_pdf(caminho_pdf: str, max_chars: Optional[int] = None) -> Tuple[str, int]:
    """
    Extrai texto completo de um arquivo PDF.
    
    Args:
        caminho_pdf: Caminho do arquivo PDF
        
    Returns:
        Tupla: (texto_extraido, numero_de_paginas)
    """
    try:
        partes_texto = []
        total_chars = 0
        num_paginas = 0
        
        with pdfplumber.open(caminho_pdf) as pdf:
            num_paginas = len(pdf.pages)
            
            for num_pagina, pagina in enumerate(pdf.pages, 1):
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    bloco_pagina = f"\n--- PÁGINA {num_pagina} ---\n{texto_pagina}\n"
                    total_chars += len(bloco_pagina)
                    if max_chars is not None and total_chars > max_chars:
                        raise ValueError(
                            "O conteúdo textual extraído ultrapassou o limite configurado para importação."
                        )
                    partes_texto.append(bloco_pagina)
        
        logger.info(f"PDF extraído com sucesso: {caminho_pdf} ({num_paginas} páginas)")
        return "".join(partes_texto), num_paginas
        
    except ValueError:
        raise
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
    partes_consolidadas = []
    total_chars = 0
    total_paginas = 0
    max_chars_total = int(obter_app_config().get("max_pdf_chars_total", 1_200_000))
    
    for idx, arquivo in enumerate(arquivos_pdf, 1):
        nome_arquivo = getattr(arquivo, "name", "arquivo_sem_nome")
        try:
            with _arquivo_pdf_temporario(arquivo, f"temp_pdf_{idx}_") as temp_path:
                chars_restantes = max(max_chars_total - total_chars, 0)
                texto, num_paginas = extrair_texto_pdf(temp_path, max_chars=chars_restantes)

            if num_paginas <= 0:
                logger.warning("PDF ignorado por falha de leitura: %s", nome_arquivo)
                raise ValueError(
                    f"O arquivo '{nome_arquivo}' não pôde ser lido ou não possui páginas válidas. "
                    "Remova-o ou envie uma versão íntegra do PDF; nenhum arquivo foi enviado à análise."
                )

            if not texto.strip():
                logger.warning("PDF ignorado por não conter texto extraível: %s", nome_arquivo)
                raise ValueError(
                    f"O arquivo '{nome_arquivo}' não possui texto legível para análise automática. "
                    "Gere uma versão com OCR antes de reenviar; nenhum arquivo foi enviado à análise."
                )

            total_paginas += num_paginas

            cabecalho = f"\n\n{'='*80}\nARQUIVO {idx}: {nome_arquivo}\n{'='*80}\n\n"
            tamanho_projetado = total_chars + len(cabecalho) + len(texto)
            if tamanho_projetado > max_chars_total:
                raise ValueError(
                    "O texto consolidado dos PDFs ultrapassa o limite de "
                    f"{_formatar_inteiro(max_chars_total)} caracteres para uma única importação. "
                    "Remova alguns arquivos, selecione menos páginas ou divida o processo em lotes menores."
                )

            partes_consolidadas.append(cabecalho)
            partes_consolidadas.append(texto)
            total_chars = tamanho_projetado
            del texto

            logger.info(
                "PDF consolidado com sucesso",
                extra={
                    "arquivo": nome_arquivo,
                    "paginas": num_paginas,
                    "tamanho_bytes": tamanho_arquivo_seguro(arquivo),
                },
            )

        except ValueError:
            raise
        except Exception as e:
            st.error(f"❌ Erro ao processar {nome_arquivo}: {e}")
            logger.exception("Erro ao consolidar PDF %s", nome_arquivo)
            continue

    return "".join(partes_consolidadas), total_paginas


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
    
    tamanho_total = sum(tamanho_arquivo_seguro(arquivo) for arquivo in arquivos_pdf)
    if tamanho_total > max_size_bytes:
        tamanho_total_mb = tamanho_total / (1024 * 1024)
        return False, f"❌ Tamanho total de {tamanho_total_mb:.1f}MB excede limite de {max_size_mb}MB."
    
    # Validar se são PDFs e respeitam o limite por arquivo
    for arquivo in arquivos_pdf:
        tamanho_arquivo = tamanho_arquivo_seguro(arquivo)
        if tamanho_arquivo > max_por_arquivo_bytes:
            tamanho_mb = tamanho_arquivo / (1024 * 1024)
            return False, (
                f"❌ O arquivo '{getattr(arquivo, 'name', 'arquivo_sem_nome')}' tem {tamanho_mb:.1f}MB e excede o limite "
                f"individual de {max_por_arquivo_mb}MB."
            )

        nome_arquivo = getattr(arquivo, "name", "arquivo_sem_nome")
        if not nome_arquivo.lower().endswith(".pdf"):
            return False, f"❌ Arquivo '{nome_arquivo}' não é um PDF válido."

        assinatura = _primeiros_bytes(arquivo, 5)
        if not assinatura:
            return False, (
                f"❌ Não foi possível ler o conteúdo de '{nome_arquivo}'. "
                "Reenvie o arquivo ou substitua por uma versão íntegra do PDF."
            )
        if assinatura != b"%PDF-":
            return False, f"❌ Arquivo '{nome_arquivo}' não possui assinatura válida de PDF."
    
    return True, "✅ Validação OK"


def validar_limite_paginas(total_paginas: int) -> Tuple[bool, str]:
    max_paginas = int(obter_app_config().get("max_pdf_pages_total", 3000))

    if total_paginas < 0:
        return False, "❌ Não foi possível calcular o total de páginas dos PDFs enviados."

    if total_paginas > max_paginas:
        return False, (
            f"❌ Os PDFs enviados somam {_formatar_inteiro(total_paginas)} páginas e ultrapassam o limite "
            f"de importação de {_formatar_inteiro(max_paginas)} páginas. Remova alguns arquivos, "
            "selecione menos páginas ou divida o processo em lotes menores antes de tentar novamente."
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
    encontrou_pdf_valido = False
    for arquivo in arquivos_pdf:
        try:
            with _arquivo_pdf_temporario(arquivo, "temp_count_") as temp_path:
                with pdfplumber.open(temp_path) as pdf:
                    if not pdf.pages:
                        raise ValueError("PDF sem páginas legíveis.")
                    total += len(pdf.pages)
                    encontrou_pdf_valido = True
        except Exception as exc:
            nome_arquivo = getattr(arquivo, "name", "arquivo_sem_nome")
            logger.exception("Falha ao calcular páginas do PDF %s", nome_arquivo)
            raise ValueError(
                f"Não foi possível inspecionar '{nome_arquivo}': {exc}. "
                "Corrija ou remova o arquivo antes de continuar."
            ) from exc

    if not encontrou_pdf_valido:
        return -1
    
    return total
