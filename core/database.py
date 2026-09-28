import logging

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

from core.config import (
    ConfigurationError,
    criar_dados_padrao_persistencia,
    obter_credenciais_firebase,
)


@st.cache_resource
def _obter_db():
    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            cred_dict = obter_credenciais_firebase()
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except ConfigurationError as exc:
            st.error(f"Configuração do Firebase incompleta: {exc}")
            st.stop()
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


def _normalizar_dados_processo(dados_proc):
    if not isinstance(dados_proc, dict):
        raise ValueError("Os dados do processo devem ser um dicionário.")

    dados_normalizados = criar_dados_padrao_persistencia()
    dados_normalizados.update(dados_proc)
    return dados_normalizados


def salvar_processo(id_proc, dados_proc):
    try:
        dados_normalizados = _normalizar_dados_processo(dados_proc)
        _obter_db().collection("processos").document(id_proc).set(dados_normalizados)
        return True
    except Exception as exc:
        logging.exception("Falha ao salvar processo %s", id_proc)
        st.error(f"Erro Crítico de Rede: {exc}")
        return False


def salvar_processo_com_importacao(id_proc, dados_proc, registro_importacao):
    try:
        if not isinstance(registro_importacao, dict):
            raise ValueError("O registro de importação deve ser um dicionário.")

        dados_normalizados = _normalizar_dados_processo(dados_proc)
        db = _obter_db()
        batch = db.batch()

        processo_ref = db.collection("processos").document(id_proc)
        importacao_ref = db.collection("importacoes_ia").document()

        batch.set(processo_ref, dados_normalizados)
        batch.set(importacao_ref, registro_importacao)
        batch.commit()
        return True
    except Exception as exc:
        logging.exception("Falha ao salvar processo importado %s", id_proc)
        st.error(f"Erro ao salvar processo importado: {exc}")
        return False


def excluir_processo(id_proc):
    try:
        _obter_db().collection("processos").document(id_proc).delete()
    except Exception as exc:
        st.error(f"Erro ao excluir na nuvem: {exc}")


def estimar_proximo_id_local(db_local):
    numeros = []
    for chave in db_local.keys():
        if chave.startswith("Proc_"):
            sufixo = chave.split("_", 1)[1]
            if sufixo.isdigit():
                numeros.append(int(sufixo))
    proximo = max(numeros) + 1 if numeros else 1
    return f"Proc_{proximo:02d}"


def gerar_proximo_id(db_local=None):
    try:
        db = _obter_db()
        contador_ref = db.collection("app_meta").document("processos_counter")
        transacao = db.transaction()

        @firestore.transactional
        def _incrementar_contador(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            atual = 0
            if snapshot.exists:
                valor = snapshot.to_dict().get("ultimo_numero")
                if isinstance(valor, int):
                    atual = valor
            proximo = atual + 1
            transaction.set(ref, {"ultimo_numero": proximo}, merge=True)
            return proximo

        proximo_numero = _incrementar_contador(transacao, contador_ref)
        return f"Proc_{proximo_numero:02d}"
    except Exception:
        logging.exception("Falha ao gerar ID atômico do processo. Usando fallback local.")
        return estimar_proximo_id_local(db_local or {})
