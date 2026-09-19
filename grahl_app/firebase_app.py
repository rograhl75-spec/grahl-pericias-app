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
        st.error("Firebase não configurado corretamente. Verifique `st.secrets['firebase']`.")
        st.stop()
    except ValueError as exc:
        st.error(f"Erro ao inicializar o Firebase: {exc}")
        st.stop()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao conectar ao Firebase: {exc}")
        st.stop()
