from __future__ import annotations

import streamlit as st
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError, RetryError

from .constants import COLLECTION_PROCESSOS
from .firebase_app import get_firestore_client
from .utils import generate_next_process_id, normalize_process_data


@st.cache_data(ttl=30, show_spinner=False)
def load_processes() -> dict[str, dict]:
    db = get_firestore_client()
    dados_db: dict[str, dict] = {}
    docs = db.collection(COLLECTION_PROCESSOS).stream()
    for doc in docs:
        dados_db[doc.id] = normalize_process_data(doc.to_dict() or {})
    return dados_db


def clear_process_cache() -> None:
    load_processes.clear()


def fetch_process_ids_uncached() -> list[str]:
    db = get_firestore_client()
    return [doc.id for doc in db.collection(COLLECTION_PROCESSOS).stream()]


def save_process(process_id: str, process_data: dict) -> None:
    db = get_firestore_client()
    try:
        db.collection(COLLECTION_PROCESSOS).document(process_id).set(normalize_process_data(process_data))
    except (GoogleAPICallError, RetryError, ValueError) as exc:
        raise RuntimeError(f"Erro ao salvar o processo {process_id} na nuvem: {exc}") from exc
    clear_process_cache()


def delete_process(process_id: str) -> None:
    db = get_firestore_client()
    try:
        db.collection(COLLECTION_PROCESSOS).document(process_id).delete()
    except (GoogleAPICallError, RetryError, ValueError) as exc:
        raise RuntimeError(f"Erro ao excluir o processo {process_id} na nuvem: {exc}") from exc
    clear_process_cache()


def create_process_with_auto_id(process_data: dict, *, max_attempts: int = 5) -> str:
    db = get_firestore_client()
    for _ in range(max_attempts):
        current_ids = fetch_process_ids_uncached()
        process_id = generate_next_process_id(current_ids)
        try:
            db.collection(COLLECTION_PROCESSOS).document(process_id).create(normalize_process_data(process_data))
        except AlreadyExists:
            clear_process_cache()
            continue
        except (GoogleAPICallError, RetryError, ValueError) as exc:
            raise RuntimeError(f"Erro ao criar processo automaticamente: {exc}") from exc
        clear_process_cache()
        return process_id
    raise RuntimeError("Não foi possível gerar um novo ID único para o processo. Tente novamente.")
