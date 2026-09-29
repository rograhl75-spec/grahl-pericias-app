"""Pipeline de extração de dados de PDFs em lote (texto nativo + OCR opcional)."""

from batch_extraction.config import BatchConfig, load_config
from batch_extraction.processor import run_batch

__all__ = ["BatchConfig", "load_config", "run_batch"]
