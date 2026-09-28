"""
Extração de texto de arquivos PDF para análise com Claude.
Suporta múltiplos PDFs consolidados em um único texto.
"""

import pdfplumber
import streamlit as st
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


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
    
    for idx, arquivo in enumerate(arquivos_pdf, 1):
        try:
            # Salvar arquivo temporariamente
            temp_path = f"/tmp/temp_pdf_{idx}_{arquivo.name}"
            with open(temp_path, "wb") as f:
                f.write(arquivo.getbuffer())
            
            # Extrair texto
            texto, num_paginas = extrair_texto_pdf(temp_path)
            total_paginas += num_paginas
            
            # Adicionar ao consolidado com separador
            if texto:
                texto_consolidado += f"\n\n{'='*80}\n"
                texto_consolidado += f"ARQUIVO {idx}: {arquivo.name}\n"
                texto_consolidado += f"{'='*80}\n\n"
                texto_consolidado += texto
            
            # Limpar arquivo temporário
            import os
            try:
                os.remove(temp_path)
            except:
                pass
                
        except Exception as e:
            st.error(f"❌ Erro ao processar {arquivo.name}: {e}")
            logger.error(f"Erro ao processar {arquivo.name}: {e}")
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
    # Validar quantidade
    max_arquivos = st.secrets.get("app", {}).get("max_pdf_files", 5)
    if len(arquivos_pdf) > max_arquivos:
        return False, f"❌ Máximo de {max_arquivos} PDFs permitidos. Você enviou {len(arquivos_pdf)}."
    
    # Validar tamanho total
    max_size_mb = st.secrets.get("app", {}).get("max_file_size_mb", 200)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    tamanho_total = sum(arquivo.size for arquivo in arquivos_pdf)
    if tamanho_total > max_size_bytes:
        tamanho_total_mb = tamanho_total / (1024 * 1024)
        return False, f"❌ Tamanho total de {tamanho_total_mb:.1f}MB excede limite de {max_size_mb}MB."
    
    # Validar se são PDFs
    for arquivo in arquivos_pdf:
        if not arquivo.name.lower().endswith(".pdf"):
            return False, f"❌ Arquivo '{arquivo.name}' não é um PDF válido."
    
    return True, "✅ Validação OK"


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
            temp_path = f"/tmp/temp_count_{arquivo.name}"
            with open(temp_path, "wb") as f:
                f.write(arquivo.getbuffer())
            
            with pdfplumber.open(temp_path) as pdf:
                total += len(pdf.pages)
            
            import os
            try:
                os.remove(temp_path)
            except:
                pass
        except:
            pass
    
    return total
