"""
Orquestração do lote: descoberta dos PDFs, isolamento por arquivo (subprocesso
com timeout), gravação do JSON de saída, cópia dos que falharam e relatório final.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import queue as queue_module
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from batch_extraction.config import BatchConfig
from batch_extraction.extractor import STATUS_FAILED, STATUS_PARTIAL, STATUS_SUCCESS, base_result, extract_pdf
from batch_extraction.ocr import OcrStatus, check_ocr, configure_tesseract_cmd

logger = logging.getLogger("batch_extraction")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(processName)s | %(message)s"
_NOISY_LOGGERS = ("pdfminer", "pdfplumber", "PIL", "pypdfium2")
_MAX_MSG = 2000


def setup_logging(log_file: Optional[Path], verbose: bool = False) -> None:
    """Configura log no console e em arquivo (append)."""
    raiz = logging.getLogger()
    for handler in list(raiz.handlers):
        raiz.removeHandler(handler)
        handler.close()
    raiz.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    raiz.addHandler(console)

    if log_file is not None:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        arquivo = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        arquivo.setFormatter(formatter)
        raiz.addHandler(arquivo)

    for nome in _NOISY_LOGGERS:
        logging.getLogger(nome).setLevel(logging.ERROR)


def discover_pdfs(input_dir: Path, recursive: bool = False) -> List[Path]:
    padrao = input_dir.rglob("*") if recursive else input_dir.glob("*")
    return sorted(p for p in padrao if p.is_file() and p.suffix.lower() == ".pdf")


def output_name(pdf_path: Path, input_dir: Path) -> str:
    """Nome do JSON de saída; em modo recursivo inclui as subpastas para evitar colisões."""
    try:
        relativo = pdf_path.relative_to(input_dir)
    except ValueError:
        relativo = Path(pdf_path.name)
    partes = list(relativo.parent.parts) + [relativo.stem]
    return "__".join(partes) + ".json"


def write_json_atomic(destino: Path, dados: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".tmp")
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    os.replace(temporario, destino)


def _summary(resultado: dict, output_path: Path) -> dict:
    return {
        "arquivo": resultado.get("arquivo_origem"),
        "status": resultado.get("status"),
        "metodo_extracao": resultado.get("metodo_extracao"),
        "tipo_pdf": resultado.get("tipo_pdf"),
        "paginas_total": resultado.get("paginas_total"),
        "paginas_processadas": resultado.get("paginas_processadas"),
        "paginas_ocr": (resultado.get("ocr") or {}).get("paginas_ocr", 0),
        "duracao_segundos": resultado.get("duracao_segundos"),
        "saida": str(output_path),
        "avisos": [str(a)[:_MAX_MSG] for a in resultado.get("avisos", [])[:20]],
        "erros": [str(e)[:_MAX_MSG] for e in resultado.get("erros", [])[:20]],
    }


def process_file(pdf_path: Path, config: BatchConfig, ocr_status: OcrStatus, output_path: Path) -> dict:
    """Extrai um PDF, grava o JSON e devolve um resumo pequeno (seguro para enviar entre processos)."""
    ultimo_log = [0.0]

    def progresso(atual: int, total: int) -> None:
        agora = time.monotonic()
        if atual == total or agora - ultimo_log[0] >= 10:
            ultimo_log[0] = agora
            logger.info("   %s: página %s/%s", pdf_path.name, atual, total)

    resultado = extract_pdf(pdf_path, config, ocr_status, progress=progresso)
    write_json_atomic(output_path, resultado)
    return _summary(resultado, output_path)


def _worker(pdf_path: str, config: BatchConfig, ocr_status: OcrStatus, output_path: str,
            log_file: Optional[str], verbose: bool, fila) -> None:
    setup_logging(Path(log_file) if log_file else None, verbose)
    configure_tesseract_cmd(os.environ.get("TESSERACT_CMD"))
    try:
        resumo = process_file(Path(pdf_path), config, ocr_status, Path(output_path))
    except Exception as exc:  # pragma: no cover - rede de segurança
        logger.exception("Falha inesperada no subprocesso para %s", pdf_path)
        resumo = {"arquivo": Path(pdf_path).name, "status": STATUS_FAILED, "erros": [f"{type(exc).__name__}: {exc}"[:_MAX_MSG]]}
    fila.put(resumo)


def _failure_result(pdf_path: Path, output_path: Path, mensagem: str, inicio: datetime) -> dict:
    resultado = base_result(pdf_path)
    fim = datetime.now().astimezone()
    resultado["inicio_processamento"] = inicio.isoformat(timespec="seconds")
    resultado["fim_processamento"] = fim.isoformat(timespec="seconds")
    resultado["duracao_segundos"] = round((fim - inicio).total_seconds(), 2)
    resultado["erros"].append(mensagem)
    try:
        resultado["tamanho_bytes"] = pdf_path.stat().st_size
    except OSError:
        pass
    write_json_atomic(output_path, resultado)
    return _summary(resultado, output_path)


def run_isolated(pdf_path: Path, config: BatchConfig, ocr_status: OcrStatus, output_path: Path,
                 log_file: Optional[Path], verbose: bool = False) -> dict:
    """Executa um PDF em subprocesso: se travar além do timeout, é encerrado e o lote segue."""
    inicio = datetime.now().astimezone()
    contexto = multiprocessing.get_context("spawn")
    fila = contexto.Queue()
    processo = contexto.Process(
        target=_worker,
        args=(str(pdf_path), config, ocr_status, str(output_path), str(log_file) if log_file else None, verbose, fila),
        name=f"pdf-{pdf_path.stem[:30]}",
        daemon=True,
    )
    processo.start()
    timeout = config.file_timeout_seconds if config.file_timeout_seconds > 0 else None
    limite = time.monotonic() + timeout if timeout else None
    resumo = None
    expirou = False
    while True:
        try:
            resumo = fila.get(timeout=1)
            break
        except queue_module.Empty:
            pass
        except (EOFError, OSError):  # pragma: no cover - processo morreu abruptamente
            break
        if not processo.is_alive():
            try:
                resumo = fila.get(timeout=1)
            except (queue_module.Empty, EOFError, OSError):
                resumo = None
            break
        if limite is not None and time.monotonic() >= limite:
            expirou = True
            break

    processo.join(0 if expirou else 5)
    if processo.is_alive():
        processo.terminate()
        processo.join(10)
        if processo.is_alive():  # pragma: no cover - defensivo
            processo.kill()
            processo.join()
    fila.close()

    if resumo is not None:
        return resumo

    if expirou:
        mensagem = (
            f"Tempo limite de {config.file_timeout_seconds}s excedido (BATCH_FILE_TIMEOUT / --timeout); "
            "processamento interrompido."
        )
    else:
        mensagem = f"Subprocesso encerrado inesperadamente (código {processo.exitcode}); possível falta de memória."
    logger.error("%s: %s", pdf_path.name, mensagem)
    return _failure_result(pdf_path, output_path, mensagem, inicio)


def _copy_failed(pdf_path: Path, failed_dir: Path, nome_saida: str) -> Optional[Path]:
    destino = failed_dir / (Path(nome_saida).stem + pdf_path.suffix)
    try:
        shutil.copy2(pdf_path, destino)
        return destino
    except OSError as exc:
        logger.warning("Não foi possível copiar %s para %s: %s", pdf_path.name, failed_dir, exc)
        return None


def run_batch(config: BatchConfig, recursive: bool = False, log_file: Optional[Path] = None,
              verbose: bool = False, ocr_status: Optional[OcrStatus] = None) -> dict:
    """Processa todos os PDFs da pasta de entrada, um por vez. Nunca interrompe o lote por falha individual."""
    config.ensure_dirs()
    inicio_lote = datetime.now()
    carimbo = inicio_lote.strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 70)
    logger.info("Início do lote de extração de PDFs")
    logger.info("Entrada: %s | Saída: %s", config.input_dir, config.output_dir)
    logger.info("Logs: %s | Falhas: %s", config.logs_dir, config.failed_dir)

    if ocr_status is None:
        if config.ocr_enabled:
            configure_tesseract_cmd(os.environ.get("TESSERACT_CMD"))
            ocr_status = check_ocr(config.ocr_lang)
        else:
            ocr_status = OcrStatus(False, reason="OCR desativado por configuração.")
    if config.ocr_enabled and ocr_status.available:
        logger.info("OCR disponível (idioma: %s).", ocr_status.lang)
        for aviso in ocr_status.warnings:
            logger.warning(aviso)
    elif config.ocr_enabled:
        logger.warning("OCR INDISPONÍVEL: %s PDFs escaneados não terão texto extraído.", ocr_status.reason)
    else:
        logger.info("OCR desativado por configuração.")

    pdfs = discover_pdfs(Path(config.input_dir), recursive=recursive)
    total = len(pdfs)
    logger.info("%s PDF(s) encontrado(s) em %s", total, config.input_dir)
    if total == 0:
        logger.warning("Nenhum PDF para processar. Coloque os arquivos em: %s", config.input_dir)

    resultados: List[dict] = []
    for indice, pdf_path in enumerate(pdfs, 1):
        saida = Path(config.output_dir) / output_name(pdf_path, Path(config.input_dir))
        tamanho_mb = pdf_path.stat().st_size / (1024 * 1024) if pdf_path.exists() else 0
        prefixo = f"[{indice}/{total}]"

        if config.skip_existing and saida.exists():
            try:
                with open(saida, encoding="utf-8") as arquivo:
                    status_anterior = json.load(arquivo).get("status")
            except (OSError, ValueError):
                status_anterior = None
            if status_anterior in (STATUS_SUCCESS, STATUS_PARTIAL):
                logger.info("%s %s já processado (%s); pulando.", prefixo, pdf_path.name, status_anterior)
                resultados.append({"arquivo": pdf_path.name, "status": "pulado", "saida": str(saida), "avisos": [], "erros": []})
                continue

        logger.info("%s Processando %s (%.1f MB)...", prefixo, pdf_path.name, tamanho_mb)
        try:
            if config.use_subprocess:
                resumo = run_isolated(pdf_path, config, ocr_status, saida, log_file, verbose)
            else:
                resumo = process_file(pdf_path, config, ocr_status, saida)
        except Exception as exc:
            logger.exception("%s Erro inesperado em %s", prefixo, pdf_path.name)
            resumo = _failure_result(pdf_path, saida, f"{type(exc).__name__}: {exc}", datetime.now().astimezone())

        status = resumo.get("status")
        if status == STATUS_FAILED:
            logger.error("%s FALHA: %s -> %s", prefixo, pdf_path.name, "; ".join(resumo.get("erros", [])) or "erro desconhecido")
            if config.copy_failed:
                copia = _copy_failed(pdf_path, Path(config.failed_dir), saida.name)
                if copia:
                    resumo["copia_falha"] = str(copia)
        else:
            logger.info(
                "%s %s: %s | método=%s | tipo=%s | páginas=%s/%s | OCR=%s | %.1fs",
                prefixo, status.upper() if status else "?", pdf_path.name, resumo.get("metodo_extracao"),
                resumo.get("tipo_pdf"), resumo.get("paginas_processadas"), resumo.get("paginas_total"),
                resumo.get("paginas_ocr"), resumo.get("duracao_segundos") or 0,
            )
        for aviso in resumo.get("avisos", []):
            logger.warning("   aviso: %s", aviso)
        resultados.append(resumo)

    fim_lote = datetime.now()
    contagem: Dict[str, int] = {}
    for item in resultados:
        contagem[item.get("status") or "desconhecido"] = contagem.get(item.get("status") or "desconhecido", 0) + 1

    relatorio = {
        "inicio": inicio_lote.astimezone().isoformat(timespec="seconds"),
        "fim": fim_lote.astimezone().isoformat(timespec="seconds"),
        "duracao_segundos": round((fim_lote - inicio_lote).total_seconds(), 2),
        "total_arquivos": total,
        "sucesso": contagem.get(STATUS_SUCCESS, 0),
        "parcial": contagem.get(STATUS_PARTIAL, 0),
        "falha": contagem.get(STATUS_FAILED, 0),
        "pulado": contagem.get("pulado", 0),
        "ocr": {"habilitado": config.ocr_enabled, "disponivel": ocr_status.available,
                "idioma": ocr_status.lang or None, "motivo_indisponivel": ocr_status.reason or None},
        "configuracao": config.as_dict(),
        "log": str(log_file) if log_file else None,
        "arquivos": resultados,
    }
    caminho_relatorio = Path(config.logs_dir) / f"relatorio_lote_{carimbo}.json"
    write_json_atomic(caminho_relatorio, relatorio)
    relatorio["relatorio_path"] = str(caminho_relatorio)

    logger.info("=" * 70)
    logger.info(
        "RESUMO: %s arquivo(s) | sucesso=%s | parcial=%s | falha=%s | pulado=%s | %.1fs",
        total, relatorio["sucesso"], relatorio["parcial"], relatorio["falha"], relatorio["pulado"],
        relatorio["duracao_segundos"],
    )
    for item in resultados:
        if item.get("status") == STATUS_FAILED:
            logger.info("   FALHOU: %s -> %s", item.get("arquivo"), "; ".join(item.get("erros", [])))
    logger.info("JSONs em: %s", config.output_dir)
    logger.info("Relatório do lote: %s", caminho_relatorio)
    if log_file:
        logger.info("Log detalhado: %s", log_file)
    logger.info("=" * 70)
    return relatorio
