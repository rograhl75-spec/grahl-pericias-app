"""
Extração de texto de arquivos PDF para análise com Claude.
Suporta múltiplos PDFs consolidados em um único texto.
"""

import logging
from contextlib import contextmanager
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber
import streamlit as st

from core.config import APP_CONFIG_DEFAULTS, obter_app_config

logger = logging.getLogger(__name__)


class LimiteTextoPDFExcedido(ValueError):
    """O texto extraído dos PDFs ultrapassou `max_pdf_chars_total`."""


def _formatar_inteiro(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def obter_limite_chars_total() -> int:
    """Limite configurado de caracteres para uma importação (padrão em APP_CONFIG_DEFAULTS)."""
    padrao = int(APP_CONFIG_DEFAULTS["max_pdf_chars_total"])
    try:
        return max(int(obter_app_config().get("max_pdf_chars_total", padrao)), 0)
    except (TypeError, ValueError):
        logger.warning("Valor inválido para max_pdf_chars_total; usando o padrão %s.", padrao)
        return padrao


def mensagem_limite_chars_excedido(max_chars_total: int, nome_arquivo: Optional[str] = None) -> str:
    """Mensagem única para o bloqueio por limite de caracteres, com orientação de como proceder."""
    origem = f" ao ler o arquivo '{nome_arquivo}'" if nome_arquivo else ""
    return (
        f"O texto extraído dos PDFs ultrapassou{origem} o limite de "
        f"{_formatar_inteiro(max_chars_total)} caracteres por importação (max_pdf_chars_total). "
        "Nenhum dado foi importado e o processo não foi alterado. "
        "Para continuar, divida o processo em lotes menores (por exemplo, importe PARTE_1 e "
        "PARTE_2 em importações separadas), remova peças desnecessárias ou gere PDFs apenas com "
        "as páginas relevantes e tente novamente."
    )


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


def _bloco_pagina(num_pagina: int, texto_pagina: str) -> str:
    return f"\n--- PÁGINA {num_pagina} ---\n{texto_pagina}\n"


def extrair_texto_pdf(caminho_pdf: str, max_chars: Optional[int] = None) -> Tuple[str, int]:
    """
    Extrai texto completo de um arquivo PDF.
    
    Args:
        caminho_pdf: Caminho do arquivo PDF
        max_chars: Limite de caracteres; ao ultrapassá-lo a extração é interrompida
            com LimiteTextoPDFExcedido (nunca há truncamento silencioso).
        
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
                try:
                    texto_pagina = pagina.extract_text()
                finally:
                    # Libera o cache de objetos da página para limitar o uso de memória.
                    pagina.close()
                if texto_pagina:
                    bloco_pagina = _bloco_pagina(num_pagina, texto_pagina)
                    total_chars += len(bloco_pagina)
                    if max_chars is not None and total_chars > max_chars:
                        raise LimiteTextoPDFExcedido(mensagem_limite_chars_excedido(max_chars))
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
    max_chars_total = obter_limite_chars_total()
    
    for idx, arquivo in enumerate(arquivos_pdf, 1):
        nome_arquivo = getattr(arquivo, "name", "arquivo_sem_nome")
        cabecalho = f"\n\n{'='*80}\nARQUIVO {idx}: {nome_arquivo}\n{'='*80}\n\n"
        try:
            with _arquivo_pdf_temporario(arquivo, f"temp_pdf_{idx}_") as temp_path:
                chars_restantes = max(max_chars_total - total_chars - len(cabecalho), 0)
                try:
                    texto, num_paginas = extrair_texto_pdf(temp_path, max_chars=chars_restantes)
                except LimiteTextoPDFExcedido as exc:
                    raise LimiteTextoPDFExcedido(
                        mensagem_limite_chars_excedido(max_chars_total, nome_arquivo)
                    ) from exc

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

            tamanho_projetado = total_chars + len(cabecalho) + len(texto)
            if tamanho_projetado > max_chars_total:
                raise LimiteTextoPDFExcedido(
                    mensagem_limite_chars_excedido(max_chars_total, nome_arquivo)
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
            # Falha fechada: nunca importar parcialmente os demais arquivos.
            logger.exception("Erro ao consolidar PDF %s", nome_arquivo)
            raise ValueError(
                f"Não foi possível processar o arquivo '{nome_arquivo}' ({type(e).__name__}). "
                "Nenhum dado foi importado; reenvie o arquivo ou substitua por uma versão íntegra do PDF."
            ) from e

    return "".join(partes_consolidadas), total_paginas


def obter_max_lotes() -> int:
    """Quantidade máxima de lotes da importação em lotes (padrão em APP_CONFIG_DEFAULTS)."""
    padrao = int(APP_CONFIG_DEFAULTS["max_pdf_batches"])
    try:
        return max(int(obter_app_config().get("max_pdf_batches", padrao)), 1)
    except (TypeError, ValueError):
        logger.warning("Valor inválido para max_pdf_batches; usando o padrão %s.", padrao)
        return padrao


def _cabecalho_lote(idx: int, nome: str, pagina_inicio: int, pagina_fim: int, total_paginas: int) -> str:
    # Mantém o marcador "ARQUIVO N:" reconhecido pelo divisor de chunks da Claude e
    # informa o nome real do arquivo e as páginas originais para as 'fontes'.
    return (
        f"\n\n{'='*80}\nARQUIVO {idx}: {nome} "
        f"(páginas {pagina_inicio} a {pagina_fim} de {total_paginas})\n{'='*80}\n\n"
    )


def descrever_lote(lote: Dict) -> str:
    """Descrição curta dos arquivos/páginas de um lote (sem conteúdo textual)."""
    partes = [
        f"{parte.get('arquivo', 'arquivo_sem_nome')} (págs. {parte.get('pagina_inicio')}–{parte.get('pagina_fim')})"
        for parte in lote.get("partes", [])
    ]
    return "; ".join(partes) if partes else "nenhum arquivo"


def mensagem_limite_lotes_excedido(max_chars_lote: int, max_lotes: int) -> str:
    return (
        "Os PDFs enviados não cabem na importação em lotes: seriam necessários mais de "
        f"{max_lotes} lote(s) de até {_formatar_inteiro(max_chars_lote)} caracteres "
        "(max_pdf_batches x max_pdf_chars_total). Nenhum dado foi importado e o processo não foi "
        "alterado. Remova peças desnecessárias ou gere PDFs apenas com as páginas relevantes."
    )


def planejar_lotes_pdf(
    arquivos_pdf: List,
    max_chars_lote: Optional[int] = None,
    max_lotes: Optional[int] = None,
) -> List[Dict]:
    """
    Divide os PDFs em lotes sequenciais de intervalos de páginas, cada um com no máximo
    `max_chars_lote` caracteres (mesma contagem usada na extração do lote).

    Apenas o tamanho do texto de cada página é mantido; o texto é descartado logo após
    a medição. Nunca trunca: uma página maior que o lote ou lotes acima de `max_lotes`
    geram LimiteTextoPDFExcedido.

    Returns:
        Lista de lotes: {"indice", "partes": [{"arquivo_idx", "arquivo", "pagina_inicio",
        "pagina_fim", "total_paginas_arquivo"}], "chars", "paginas"}
    """
    max_chars_lote = obter_limite_chars_total() if max_chars_lote is None else int(max_chars_lote)
    max_lotes = obter_max_lotes() if max_lotes is None else int(max_lotes)
    lotes: List[Dict] = []
    atual: Optional[Dict] = None

    for idx, arquivo in enumerate(arquivos_pdf, 1):
        nome_arquivo = getattr(arquivo, "name", "arquivo_sem_nome")
        chars_arquivo = 0
        try:
            with _arquivo_pdf_temporario(arquivo, f"temp_plano_lote_{idx}_") as temp_path:
                with pdfplumber.open(temp_path) as pdf:
                    total_paginas_arquivo = len(pdf.pages)
                    if total_paginas_arquivo <= 0:
                        raise ValueError(
                            f"O arquivo '{nome_arquivo}' não pôde ser lido ou não possui páginas válidas. "
                            "Remova-o ou envie uma versão íntegra do PDF; nenhum arquivo foi enviado à análise."
                        )
                    # Cabeçalho com o maior intervalo possível: o real nunca é maior.
                    tamanho_cabecalho = len(
                        _cabecalho_lote(
                            idx, nome_arquivo, total_paginas_arquivo, total_paginas_arquivo, total_paginas_arquivo
                        )
                    )
                    for num_pagina, pagina in enumerate(pdf.pages, 1):
                        try:
                            texto_pagina = pagina.extract_text()
                        finally:
                            pagina.close()
                        if not texto_pagina:
                            continue
                        tamanho = len(_bloco_pagina(num_pagina, texto_pagina))
                        del texto_pagina
                        chars_arquivo += tamanho

                        parte = None
                        if atual and atual["partes"] and atual["partes"][-1]["arquivo_idx"] == idx:
                            parte = atual["partes"][-1]
                        custo = tamanho + (0 if parte else tamanho_cabecalho)
                        if atual is None or atual["chars"] + custo > max_chars_lote:
                            if tamanho + tamanho_cabecalho > max_chars_lote:
                                raise LimiteTextoPDFExcedido(
                                    f"A página {num_pagina} do arquivo '{nome_arquivo}' sozinha ultrapassa o "
                                    f"limite de {_formatar_inteiro(max_chars_lote)} caracteres por lote "
                                    "(max_pdf_chars_total). Nenhum dado foi importado e o processo não foi alterado."
                                )
                            if len(lotes) >= max_lotes:
                                raise LimiteTextoPDFExcedido(
                                    mensagem_limite_lotes_excedido(max_chars_lote, max_lotes)
                                )
                            atual = {"indice": len(lotes) + 1, "partes": [], "chars": 0, "paginas": 0}
                            lotes.append(atual)
                            parte = None
                            custo = tamanho + tamanho_cabecalho
                        if parte is None:
                            parte = {
                                "arquivo_idx": idx,
                                "arquivo": nome_arquivo,
                                "pagina_inicio": num_pagina,
                                "pagina_fim": num_pagina,
                                "total_paginas_arquivo": total_paginas_arquivo,
                            }
                            atual["partes"].append(parte)
                        parte["pagina_fim"] = num_pagina
                        atual["chars"] += custo
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("Erro ao planejar lotes do PDF %s", nome_arquivo)
            raise ValueError(
                f"Não foi possível processar o arquivo '{nome_arquivo}' ({type(exc).__name__}). "
                "Nenhum dado foi importado; reenvie o arquivo ou substitua por uma versão íntegra do PDF."
            ) from exc

        if chars_arquivo == 0:
            raise ValueError(
                f"O arquivo '{nome_arquivo}' não possui texto legível para análise automática. "
                "Gere uma versão com OCR antes de reenviar; nenhum arquivo foi enviado à análise."
            )

    for lote in lotes:
        lote["paginas"] = sum(
            parte["pagina_fim"] - parte["pagina_inicio"] + 1 for parte in lote["partes"]
        )
    return lotes


def extrair_texto_lote(
    arquivos_pdf: List,
    lote: Dict,
    max_chars: Optional[int] = None,
) -> Tuple[str, int]:
    """
    Extrai somente as páginas de um lote planejado por `planejar_lotes_pdf`, com o nome
    real do arquivo e a numeração original das páginas. Falha fechada se os arquivos
    mudaram ou se o texto ultrapassar `max_chars` (sem truncar).
    """
    max_chars = obter_limite_chars_total() if max_chars is None else int(max_chars)
    partes_texto: List[str] = []
    total_chars = 0
    total_paginas = 0

    for parte in lote.get("partes", []):
        idx = int(parte["arquivo_idx"])
        nome_esperado = parte["arquivo"]
        if idx < 1 or idx > len(arquivos_pdf):
            raise ValueError(
                f"O arquivo '{nome_esperado}' do lote {lote.get('indice')} não está mais entre os PDFs enviados."
            )
        arquivo = arquivos_pdf[idx - 1]
        nome_arquivo = getattr(arquivo, "name", "arquivo_sem_nome")
        if nome_arquivo != nome_esperado:
            raise ValueError(
                f"Os PDFs enviados foram alterados durante a importação em lotes ('{nome_esperado}')."
            )
        pagina_inicio = int(parte["pagina_inicio"])
        pagina_fim = int(parte["pagina_fim"])
        total_paginas_arquivo = int(parte["total_paginas_arquivo"])

        cabecalho = _cabecalho_lote(idx, nome_arquivo, pagina_inicio, pagina_fim, total_paginas_arquivo)
        total_chars += len(cabecalho)
        partes_texto.append(cabecalho)
        try:
            with _arquivo_pdf_temporario(arquivo, f"temp_lote_{idx}_") as temp_path:
                with pdfplumber.open(temp_path) as pdf:
                    if len(pdf.pages) != total_paginas_arquivo:
                        raise ValueError(
                            f"O arquivo '{nome_arquivo}' foi alterado durante a importação em lotes."
                        )
                    for num_pagina in range(pagina_inicio, pagina_fim + 1):
                        pagina = pdf.pages[num_pagina - 1]
                        try:
                            texto_pagina = pagina.extract_text()
                        finally:
                            pagina.close()
                        if not texto_pagina:
                            continue
                        bloco = _bloco_pagina(num_pagina, texto_pagina)
                        total_chars += len(bloco)
                        if total_chars > max_chars:
                            raise LimiteTextoPDFExcedido(
                                mensagem_limite_chars_excedido(max_chars, nome_arquivo)
                            )
                        partes_texto.append(bloco)
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("Erro ao extrair lote do PDF %s", nome_arquivo)
            raise ValueError(
                f"Não foi possível extrair as páginas {pagina_inicio}–{pagina_fim} de '{nome_arquivo}' "
                f"({type(exc).__name__}). Nenhum dado foi importado."
            ) from exc
        total_paginas += pagina_fim - pagina_inicio + 1

    return "".join(partes_texto), total_paginas


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
    max_paginas = int(
        obter_app_config().get("max_pdf_pages_total", APP_CONFIG_DEFAULTS["max_pdf_pages_total"])
    )

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
