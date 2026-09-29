"""
Configuração do processamento em lote de PDFs.

Todos os valores possuem padrões seguros e podem ser sobrescritos por variáveis
de ambiente (prefixo ``BATCH_``) ou por flags da linha de comando
(ver ``python extract_batch.py --help``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

_TRUE_VALUES = {"1", "true", "sim", "s", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "nao", "não", "n", "no", "off"}


def _env_str(env: Mapping[str, str], nome: str, padrao: str) -> str:
    valor = env.get(nome)
    return valor.strip() if valor and valor.strip() else padrao


def _env_int(env: Mapping[str, str], nome: str, padrao: int) -> int:
    valor = env.get(nome)
    if valor is None or not valor.strip():
        return padrao
    try:
        return int(valor.strip())
    except ValueError as exc:
        raise ValueError(f"Variável de ambiente {nome} deve ser um número inteiro (recebido: {valor!r}).") from exc


def _env_bool(env: Mapping[str, str], nome: str, padrao: bool) -> bool:
    valor = env.get(nome)
    if valor is None or not valor.strip():
        return padrao
    normalizado = valor.strip().lower()
    if normalizado in _TRUE_VALUES:
        return True
    if normalizado in _FALSE_VALUES:
        return False
    raise ValueError(f"Variável de ambiente {nome} deve ser verdadeiro/falso (recebido: {valor!r}).")


@dataclass
class BatchConfig:
    """Parâmetros do lote. Precisa ser serializável (é enviado ao subprocesso)."""

    input_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "input")
    output_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "output")
    logs_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "logs")
    failed_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "failed")

    # OCR (opcional: se as dependências não existirem, o lote continua com avisos)
    ocr_enabled: bool = True
    ocr_lang: str = "por"
    ocr_dpi: int = 300
    ocr_page_timeout_seconds: int = 120
    max_ocr_pages: int = 500

    # Detecção texto x imagem: páginas com menos caracteres que isso são tratadas como imagem.
    min_chars_per_page: int = 50

    # Limites defensivos (0 desativa o timeout por arquivo)
    file_timeout_seconds: int = 1800
    max_file_size_mb: int = 200
    max_pages: int = 3000
    max_text_chars: int = 5_000_000

    # Saída
    include_text: bool = True
    skip_existing: bool = False
    copy_failed: bool = True

    # Cada PDF roda em um subprocesso isolado (permite timeout real e libera memória ao final).
    use_subprocess: bool = True

    def ensure_dirs(self) -> None:
        """Cria automaticamente todas as pastas necessárias."""
        for pasta in (self.input_dir, self.output_dir, self.logs_dir, self.failed_dir):
            Path(pasta).mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict:
        return {chave: str(valor) if isinstance(valor, Path) else valor for chave, valor in self.__dict__.items()}


def load_config(env: Optional[Mapping[str, str]] = None) -> BatchConfig:
    """Monta a configuração a partir de variáveis de ambiente ``BATCH_*``."""
    env = os.environ if env is None else env
    data_dir = Path(_env_str(env, "BATCH_DATA_DIR", str(DEFAULT_DATA_DIR)))
    padrao = BatchConfig()

    return BatchConfig(
        input_dir=Path(_env_str(env, "BATCH_INPUT_DIR", str(data_dir / "input"))),
        output_dir=Path(_env_str(env, "BATCH_OUTPUT_DIR", str(data_dir / "output"))),
        logs_dir=Path(_env_str(env, "BATCH_LOGS_DIR", str(data_dir / "logs"))),
        failed_dir=Path(_env_str(env, "BATCH_FAILED_DIR", str(data_dir / "failed"))),
        ocr_enabled=_env_bool(env, "BATCH_OCR_ENABLED", padrao.ocr_enabled),
        ocr_lang=_env_str(env, "BATCH_OCR_LANG", padrao.ocr_lang),
        ocr_dpi=_env_int(env, "BATCH_OCR_DPI", padrao.ocr_dpi),
        ocr_page_timeout_seconds=_env_int(env, "BATCH_OCR_PAGE_TIMEOUT", padrao.ocr_page_timeout_seconds),
        max_ocr_pages=_env_int(env, "BATCH_MAX_OCR_PAGES", padrao.max_ocr_pages),
        min_chars_per_page=_env_int(env, "BATCH_MIN_CHARS_PER_PAGE", padrao.min_chars_per_page),
        file_timeout_seconds=_env_int(env, "BATCH_FILE_TIMEOUT", padrao.file_timeout_seconds),
        max_file_size_mb=_env_int(env, "BATCH_MAX_FILE_SIZE_MB", padrao.max_file_size_mb),
        max_pages=_env_int(env, "BATCH_MAX_PAGES", padrao.max_pages),
        max_text_chars=_env_int(env, "BATCH_MAX_TEXT_CHARS", padrao.max_text_chars),
        include_text=_env_bool(env, "BATCH_INCLUDE_TEXT", padrao.include_text),
        skip_existing=_env_bool(env, "BATCH_SKIP_EXISTING", padrao.skip_existing),
        copy_failed=_env_bool(env, "BATCH_COPY_FAILED", padrao.copy_failed),
        use_subprocess=_env_bool(env, "BATCH_USE_SUBPROCESS", padrao.use_subprocess),
    )
