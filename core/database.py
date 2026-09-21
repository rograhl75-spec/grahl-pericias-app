import logging

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

from core.config import criar_dados_padrao_persistencia


@st.cache_resource
def _obter_db():
    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            cred_dict = dict(st.secrets["firebase"])
            private_key = cred_dict.get("private_key")
            if isinstance(private_key, str):
                cred_dict["private_key"] = private_key.replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception:
            logging.exception("Falha ao inicializar Firebase")
            st.error("Erro ao conectar no Firebase. Verifique o st.secrets.")
            st.stop()

    try:
        return firestore.client()
    except Exception as exc:
        logging.exception("Falha ao inicializar cliente Firestore")
        st.error(f"Erro ao inicializar cliente Firestore: {exc}")
        st.stop()


def carregar_dados():
    try:
        docs = _obter_db().collection("processos").stream()
        dados_padrao = criar_dados_padrao_persistencia()
        dados_db = {}
        for doc in docs:
            valor_doc = doc.to_dict() or {}
            for chave, valor_padrao in dados_padrao.items():
                if chave not in valor_doc:
                    valor_doc[chave] = valor_padrao
            dados_db[doc.id] = valor_doc
        return dados_db
    except Exception as exc:
        st.error(f"Erro ao carregar dados da nuvem: {exc}")
        return {}


def salvar_processo(id_proc, dados_proc):
    try:
        _obter_db().collection("processos").document(id_proc).set(dados_proc)
        return True
    except Exception as exc:
        st.error(f"Erro Crítico de Rede: {exc}")
        return False


def excluir_processo(id_proc):
    try:
        _obter_db().collection("processos").document(id_proc).delete()
    except Exception as exc:
        st.error(f"Erro ao excluir na nuvem: {exc}")


def gerar_proximo_id(db_local):
    numeros = []
    for chave in db_local.keys():
        if chave.startswith("Proc_"):
            sufixo = chave.split("_", 1)[1]
            if sufixo.isdigit():
                numeros.append(int(sufixo))
    proximo = max(numeros) + 1 if numeros else 1
    return f"Proc_{proximo:02d}"
