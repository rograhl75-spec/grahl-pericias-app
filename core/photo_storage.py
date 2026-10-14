"""Fotos privadas no Firebase Storage; leitura compatível com fotos legadas."""

import base64
import hashlib
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from firebase_admin import storage
from google.api_core.exceptions import PreconditionFailed
from PIL import Image

from core.campo_fotos import foto_hash
from core.config import ConfigurationError
from core.database import _obter_app_firebase


MAX_PHOTO_BYTES = 10 * 1024 * 1024


class FotoStorageError(RuntimeError):
    """Upload/download indisponível; o chamador mantém a fila e informa o usuário."""


def _obter_bucket():
    try:
        nome = os.environ.get("FIREBASE_STORAGE_BUCKET", "").strip()
        if not nome:
            nome = str(st.secrets.get("firebase", {}).get("storage_bucket", "")).strip()
        if not nome or nome.startswith("gs://") or "/" in nome:
            raise ConfigurationError(
                "Configure firebase.storage_bucket ou FIREBASE_STORAGE_BUCKET com o nome "
                "do bucket (sem gs://)."
            )
        return storage.bucket(nome, app=_obter_app_firebase())
    except Exception as exc:
        raise FotoStorageError(f"Firebase Storage indisponível: {exc}") from exc


def metadados_storage(caso_id, foto):
    """Prepara só referências, permitindo verificar o limite antes do upload."""
    dados = base64.b64decode(foto["base64"], validate=True)
    if not dados or len(dados) > MAX_PHOTO_BYTES:
        raise ValueError("Cada foto deve ter até 10 MiB após compressão.")
    with Image.open(io.BytesIO(dados)) as imagem:
        formato = imagem.format
    if formato not in ("JPEG", "PNG"):
        raise ValueError("Use fotos JPEG ou PNG.")
    identidade = foto_hash(foto)
    caso = hashlib.sha256(str(caso_id).encode("utf-8")).hexdigest()
    extensao, mime = ("jpg", "image/jpeg") if formato == "JPEG" else ("png", "image/png")
    return {
        "storage_path": f"campo_fotos/{caso}/{identidade}.{extensao}",
        "hash": identidade,
        "mime_type": mime,
        "size_bytes": len(dados),
        "created_at": foto.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gps": foto.get("gps", ""),
        "legenda": foto.get("legenda", ""),
    }


def enviar_foto(caso_id, foto):
    """Caminho por caso/conteúdo e criação condicional tornam reenvios idempotentes."""
    metadados = metadados_storage(caso_id, foto)
    try:
        blob = _obter_bucket().blob(metadados["storage_path"])
        if not blob.exists(timeout=30):
            try:
                blob.upload_from_string(
                    base64.b64decode(foto["base64"], validate=True),
                    content_type=metadados["mime_type"],
                    if_generation_match=0,
                    timeout=60,
                )
            except PreconditionFailed:
                # Outro reenvio do mesmo conteúdo já criou o objeto.
                pass
        return metadados
    except Exception as exc:
        raise FotoStorageError(f"Não foi possível enviar a foto ao Storage: {exc}") from exc


@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def _baixar_foto_storage(storage_path):
    try:
        dados = _obter_bucket().blob(storage_path).download_as_bytes(
            start=0, end=MAX_PHOTO_BYTES, timeout=60,
        )
        if len(dados) > MAX_PHOTO_BYTES:
            raise ValueError("Foto no Storage excede 10 MiB.")
        return dados
    except Exception as exc:
        raise FotoStorageError(f"Não foi possível ler a foto no Storage: {exc}") from exc


def resolver_bytes_foto(foto):
    """Não torna objetos públicos nem baixa URLs arbitrárias do documento."""
    if foto.get("storage_path"):
        return _baixar_foto_storage(foto["storage_path"])
    if foto.get("base64"):
        return base64.b64decode(foto["base64"], validate=True)
    if foto.get("path"):
        return Path(foto["path"]).read_bytes()
    raise ValueError("Imagem ausente.")
