from __future__ import annotations

import firebase_admin
import streamlit as st
from firebase_admin import credentials, firestore, get_app


@st.cache_resource(show_spinner=False)
def get_firestore_client():
    try:
        return firestore.client(app=get_app())
    except ValueError:
        pass

    try:
        firebase_config = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_config)
        app = firebase_admin.initialize_app(cred)
        return firestore.client(app=app)
    except KeyError:
        raise RuntimeError("Firebase não configurado corretamente. Verifique `st.secrets['firebase']`.") from None
    except ValueError as exc:
        raise RuntimeError(f"Erro ao inicializar o Firebase: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Falha ao conectar ao Firebase: {exc}") from exc
