from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .constants import DADOS_PADRAO, ID_PREFIX, ID_WIDTH, MODULE_PREVIDENCIARIO

STRING_KEYS = {key for key, value in DADOS_PADRAO.items() if isinstance(value, str)}
BOOL_KEYS = {key for key, value in DADOS_PADRAO.items() if isinstance(value, bool)}
LIST_KEYS = {key for key, value in DADOS_PADRAO.items() if isinstance(value, list)}
EPI_KEYS = ("descricao", "ca", "data_entrega", "obs")
PHOTO_KEYS = ("base64", "gps", "legenda")
PLACEHOLDER_PATTERNS = (
    "[informação",
    "[extrair",
    "não localizado",
    "nao localizado",
    "preencher",
    "xxx",
    "---",
)


@dataclass(frozen=True)
class ValidationResult:
    missing_required_fields: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_required_fields


FIELD_LABELS = {
    "reclamante_nome": "Nome do Segurado / Reclamante",
    "reclamante_cpf": "CPF / NIT / PIS do Segurado / Reclamante",
    "reclamada_nome": "Empresa / Reclamada",
    "reclamada_cnpj": "CNPJ da Empresa / Reclamada",
    "processo_num": "Número do Processo / Identificação",
}


REQUIRED_FIELDS_FOR_GENERATION = {
    "default": ("reclamante_nome", "reclamada_nome", "processo_num"),
    MODULE_PREVIDENCIARIO: ("reclamante_nome", "reclamada_nome", "processo_num"),
}


def safe_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def safe_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sim", "yes", "on"}
    return bool(value)


def normalize_multiline_text(value: object) -> str:
    text = safe_str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def is_placeholder_text(value: object) -> bool:
    normalized = remover_acentos(normalize_multiline_text(value))
    if not normalized:
        return True
    return any(pattern in normalized for pattern in PLACEHOLDER_PATTERNS)


def normalize_epi_list(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        record = {key: normalize_multiline_text(item.get(key, "")) for key in EPI_KEYS}
        if record["descricao"]:
            normalized.append(record)
    return normalized


def normalize_photo_list(value: object) -> list[dict[str, object]]:
    from .photos import normalize_photo_entry

    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        normalized_entry = normalize_photo_entry(item)
        if normalized_entry:
            normalized.append(normalized_entry)
    return normalized


def normalize_process_data(data: dict | None, defaults: dict | None = None) -> dict:
    base_defaults = copy.deepcopy(defaults or DADOS_PADRAO)
    original = data or {}
    normalized = {**base_defaults}

    for key, value in original.items():
        if key in STRING_KEYS:
            normalized[key] = normalize_multiline_text(value)
        elif key in BOOL_KEYS:
            normalized[key] = safe_bool(value)
        elif key == "quadro_epis":
            normalized[key] = normalize_epi_list(value)
        elif key == "campo_fotos":
            normalized[key] = normalize_photo_list(value)
        elif key in LIST_KEYS:
            normalized[key] = list(value) if isinstance(value, list) else copy.deepcopy(base_defaults.get(key, []))
        else:
            normalized[key] = value

    normalized["quadro_epis"] = normalize_epi_list(normalized.get("quadro_epis"))
    normalized["campo_fotos"] = normalize_photo_list(normalized.get("campo_fotos"))
    for key in STRING_KEYS:
        normalized[key] = normalize_multiline_text(normalized.get(key, ""))
    return normalized


def clone_process_data(data: dict | None) -> dict:
    return normalize_process_data(copy.deepcopy(data or {}))


def merge_with_defaults(data: dict | None) -> dict:
    return normalize_process_data(data)


def remover_acentos(texto: object) -> str:
    if not texto or not isinstance(texto, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def calcula_altura(texto: object, min_h: int) -> int:
    texto_str = safe_str(texto)
    if not texto_str:
        return min_h
    linhas_quebradas = texto_str.count("\n") + 1
    caracteres_extras_wrap = sum(len(linha) // 80 for linha in texto_str.split("\n"))
    return max(min_h, (linhas_quebradas + caracteres_extras_wrap) * 24 + 40)


def generate_next_process_id(existing_ids: Iterable[str]) -> str:
    numeros: list[int] = []
    for process_id in existing_ids:
        if not isinstance(process_id, str) or not process_id.startswith(ID_PREFIX):
            continue
        suffix = process_id[len(ID_PREFIX):].strip()
        match = re.fullmatch(r"(\d+)", suffix)
        if match:
            numeros.append(int(match.group(1)))
    proximo = (max(numeros) + 1) if numeros else 1
    return f"{ID_PREFIX}{proximo:0{ID_WIDTH}d}"


def sanitize_output_filename(name: object, prefix: str = "Documento_Oficial") -> str:
    cleaned = normalize_multiline_text(name).replace("\n", " ")
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned[:80] or "Caso"
    return f"{prefix}_{cleaned}.docx"


def validate_process_data(data: dict | None, *, for_generation: bool = False) -> ValidationResult:
    normalized = normalize_process_data(data)
    if not for_generation:
        return ValidationResult(missing_required_fields=())

    module = normalized.get("modulo_atuacao") or ""
    required_fields = REQUIRED_FIELDS_FOR_GENERATION["default"]
    if module == MODULE_PREVIDENCIARIO:
        required_fields = REQUIRED_FIELDS_FOR_GENERATION[MODULE_PREVIDENCIARIO]
    missing = tuple(field for field in required_fields if not normalize_multiline_text(normalized.get(field, "")))
    return ValidationResult(missing_required_fields=missing)


def format_missing_field_labels(fields: Iterable[str]) -> list[str]:
    return [FIELD_LABELS.get(field, field) for field in fields]
