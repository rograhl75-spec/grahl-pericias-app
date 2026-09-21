import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

from core.config import criar_dados_padrao

_DB = None


def _obter_db():
    global _DB
    if _DB is not None:
        return _DB

    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as exc:
            st.error(f"Erro ao conectar no Firebase. Verifique o st.secrets. Detalhes: {exc}")
            st.stop()

    try:
        _DB = firestore.client()
    except Exception as exc:
        st.error(f"Erro ao inicializar cliente Firestore: {exc}")
        st.stop()

    return _DB


def carregar_dados():
    try:
        docs = _obter_db().collection("processos").stream()
        dados_db = {}
        for doc in docs:
            valor_doc = doc.to_dict() or {}
            for chave, valor_padrao in criar_dados_padrao().items():
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
