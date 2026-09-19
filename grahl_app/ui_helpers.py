from __future__ import annotations

import streamlit as st

from .utils import calcula_altura, format_missing_field_labels, safe_str


def initialize_session_state(defaults: dict[str, object]) -> None:
    for key, value in defaults.items():
        st.session_state.setdefault(key, value.copy() if isinstance(value, dict) else value)


def render_case_header(process_id: str, process: dict) -> None:
    st.markdown(
        f"<div style='background-color: #E2E8F0; padding: 10px 15px; border-radius: 8px; margin-bottom: 20px;'><b style='color: #1B365D;'>Caso Ativo:</b> {process_id} &nbsp;|&nbsp; <b style='color: #1B365D;'>Módulo:</b> {safe_str(process.get('modulo_atuacao', ''))}</div>",
        unsafe_allow_html=True,
    )


def text_input_value(data: dict, key: str, label: str, widget_key: str, **kwargs):
    return st.text_input(label, value=safe_str(data.get(key, "")), key=widget_key, **kwargs)


def text_area_value(data: dict, key: str, label: str, widget_key: str, *, min_height: int = 100, **kwargs):
    value = safe_str(data.get(key, ""))
    return st.text_area(label, value=value, height=calcula_altura(value, min_height), key=widget_key, **kwargs)


def show_save_feedback(success_message: str, missing_fields: tuple[str, ...] = ()) -> None:
    st.toast(success_message, icon="💾")
    if missing_fields:
        fields = ", ".join(format_missing_field_labels(missing_fields))
        st.warning(f"Caso salvo com pendências de identificação: {fields}.")
