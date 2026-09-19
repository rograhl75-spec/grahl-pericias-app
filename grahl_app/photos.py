from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any

from .constants import PHOTO_DEFAULT_CAPTION
from .utils import normalize_multiline_text, safe_str


def photo_identity_hash(content: bytes | str) -> str:
    raw_bytes: bytes
    if isinstance(content, bytes):
        raw_bytes = content
    else:
        text = safe_str(content)
        try:
            raw_bytes = base64.b64decode(text, validate=True)
        except (ValueError, TypeError):
            raw_bytes = text.encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def decode_photo_base64(base64_value: object) -> bytes:
    text = safe_str(base64_value)
    if not text:
        raise ValueError("Imagem em branco.")
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Imagem em base64 inválida.") from exc


def build_photo_entry(
    file_bytes: bytes,
    *,
    gps: object = "",
    legenda: object = PHOTO_DEFAULT_CAPTION,
    source: str = "upload",
    mime_type: str | None = None,
) -> dict[str, Any]:
    base64_value = base64.b64encode(file_bytes).decode("utf-8")
    entry: dict[str, Any] = {
        "base64": base64_value,
        "gps": normalize_multiline_text(gps),
        "legenda": normalize_multiline_text(legenda) or PHOTO_DEFAULT_CAPTION,
        "hash": photo_identity_hash(file_bytes),
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if mime_type:
        entry["mime_type"] = mime_type
    return entry


def normalize_photo_entry(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if not value.get("base64") and not value.get("path"):
        return None
    normalized: dict[str, Any] = dict(value)
    normalized["gps"] = normalize_multiline_text(value.get("gps", ""))
    normalized["legenda"] = normalize_multiline_text(value.get("legenda", "")) or PHOTO_DEFAULT_CAPTION
    if value.get("base64"):
        normalized["base64"] = safe_str(value.get("base64"))
        normalized["hash"] = safe_str(value.get("hash")) or photo_identity_hash(normalized["base64"])
    return normalized


def photo_exists(photo_list: list[dict[str, Any]], new_entry: dict[str, Any]) -> bool:
    new_hash = safe_str(new_entry.get("hash"))
    new_base64 = safe_str(new_entry.get("base64"))
    for photo in photo_list:
        existing_hash = safe_str(photo.get("hash"))
        if new_hash and existing_hash and new_hash == existing_hash:
            return True
        if new_base64 and safe_str(photo.get("base64")) == new_base64:
            return True
    return False
