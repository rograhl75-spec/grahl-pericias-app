import copy
from datetime import datetime
from pathlib import Path

import streamlit as st

LOGO_FILE = str(Path(__file__).resolve().parent.parent / "logo dourado grahl consultoria.png")


class ConfigurationError(Exception):
    """Erro de configuração obrigatória do app."""


APP_CONFIG_DEFAULTS = {
    "max_api_calls_per_day": 50,
    "max_file_size_mb": 200,
    "max_single_pdf_size_mb": 75,
    "max_pdf_files": 5,
    "max_pdf_pages_total": 3000,
    "max_pdf_chars_total": 1_200_000,
    "claude_chunk_chars": 120_000,
    "claude_max_chunks": 10,
    "claude_chunk_chars_conservative": 80_000,
    "claude_max_chunks_conservative": 15,
    "cloud_conservative_pdf_count_threshold": 2,
    "cloud_conservative_chars_threshold": 600_000,
    "claude_model": "claude-3-5-sonnet-20241022",
    "claude_model_pricing": {
        "claude-3-5-sonnet-20241022": {
            "input_usd_per_million_tokens": 3.00,
            "output_usd_per_million_tokens": 15.00,
        }
    },
    "cost_limit_per_day": 250.00,
    "usd_brl_exchange_rate": 5.00,
    "environment": "production",
}
