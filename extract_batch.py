#!/usr/bin/env python3
"""
Extração de dados de PDFs em lote.

Uso rápido:
    python extract_batch.py

Coloque os PDFs em ``data/input/``. As pastas ``data/input``, ``data/output``,
``data/logs`` e ``data/failed`` são criadas automaticamente. Para cada PDF é
gerado um JSON em ``data/output/`` e, ao final, um relatório em ``data/logs/``.

Veja todas as opções com ``python extract_batch.py --help``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from batch_extraction.config import load_config  # noqa: E402
from batch_extraction.processor import logger, run_batch, setup_logging  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrai dados de todos os PDFs de uma pasta (texto nativo + OCR) e gera um JSON por arquivo.",
        epilog="Todas as opções também podem ser definidas por variáveis de ambiente BATCH_* (ver README).",
    )
    parser.add_argument("--input", dest="input_dir", help="Pasta com os PDFs (padrão: data/input)")
    parser.add_argument("--output", dest="output_dir", help="Pasta dos JSONs (padrão: data/output)")
    parser.add_argument("--logs", dest="logs_dir", help="Pasta de logs e relatórios (padrão: data/logs)")
    parser.add_argument("--failed", dest="failed_dir", help="Pasta para cópia dos PDFs com falha (padrão: data/failed)")
    parser.add_argument("--recursive", action="store_true", help="Procura PDFs também em subpastas da entrada")
    parser.add_argument("--no-ocr", action="store_true", help="Desativa o OCR (somente texto nativo)")
    parser.add_argument("--ocr-lang", help="Idioma(s) do Tesseract, ex.: por ou por+eng (padrão: por)")
    parser.add_argument("--ocr-dpi", type=int, help="Resolução do OCR em DPI (padrão: 300)")
    parser.add_argument("--max-ocr-pages", type=int, help="Máximo de páginas com OCR por PDF (padrão: 500)")
    parser.add_argument("--min-chars", type=int, help="Mín. de caracteres para considerar a página como texto (padrão: 50)")
    parser.add_argument("--timeout", type=int, help="Tempo máximo por PDF em segundos; 0 = sem limite (padrão: 1800)")
    parser.add_argument("--max-pages", type=int, help="Máximo de páginas processadas por PDF (padrão: 3000)")
    parser.add_argument("--max-size-mb", type=int, help="Tamanho máximo por PDF em MB (padrão: 200)")
    parser.add_argument("--no-text", action="store_true", help="Não inclui o texto das páginas no JSON (apenas campos)")
    parser.add_argument("--skip-existing", action="store_true", help="Pula PDFs que já têm JSON com sucesso/parcial")
    parser.add_argument("--no-copy-failed", action="store_true", help="Não copia PDFs com falha para data/failed")
    parser.add_argument("--no-subprocess", action="store_true", help="Processa no mesmo processo (sem timeout real; p/ depuração)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log detalhado (DEBUG)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ValueError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    for atributo in ("input_dir", "output_dir", "logs_dir", "failed_dir"):
        valor = getattr(args, atributo)
        if valor:
            setattr(config, atributo, Path(valor).expanduser().resolve())

    opcionais = {
        "ocr_lang": args.ocr_lang,
        "ocr_dpi": args.ocr_dpi,
        "max_ocr_pages": args.max_ocr_pages,
        "min_chars_per_page": args.min_chars,
        "file_timeout_seconds": args.timeout,
        "max_pages": args.max_pages,
        "max_file_size_mb": args.max_size_mb,
    }
    for atributo, valor in opcionais.items():
        if valor is not None:
            setattr(config, atributo, valor)
    if args.no_ocr:
        config.ocr_enabled = False
    if args.no_text:
        config.include_text = False
    if args.skip_existing:
        config.skip_existing = True
    if args.no_copy_failed:
        config.copy_failed = False
    if args.no_subprocess:
        config.use_subprocess = False

    config.ensure_dirs()
    log_file = Path(config.logs_dir) / f"extracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(log_file, verbose=args.verbose)

    try:
        relatorio = run_batch(config, recursive=args.recursive, log_file=log_file, verbose=args.verbose)
    except KeyboardInterrupt:
        logger.warning("Interrompido pelo usuário. JSONs já gerados foram mantidos.")
        return 130

    return 1 if relatorio["falha"] else 0


if __name__ == "__main__":
    sys.exit(main())
