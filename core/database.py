import logging

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

from core.config import (
    ConfigurationError,
    criar_dados_padrao_persistencia,
    obter_credenciais_firebase,
)


logger = logging.getLogger(__name__)


class FirebaseIndisponivelError(RuntimeError):
    """Falha controlada de configuração/conexão do Firebase/Firestore.

    Nunca interrompe o app (sem st.stop()): os chamadores capturam a exceção,
    exibem mensagem amigável e seguem com retorno seguro. Exceções não são
    armazenadas pelo st.cache_resource, então a conexão é re-tentada no
    próximo rerun.
    """


class ProcessoAlteradoError(RuntimeError):
    """O processo mudou desde sua última leitura."""


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
            logger.error("Configuração do Firebase incompleta: %s", exc)
            raise FirebaseIndisponivelError(
                f"Configuração do Firebase incompleta: {exc}"
            ) from exc
        except Exception as exc:
            logger.exception("Falha ao inicializar Firebase")
            raise FirebaseIndisponivelError(
                "Erro ao conectar no Firebase. Verifique st.secrets['firebase']."
            ) from exc

    try:
        return firestore.client()
    except Exception as exc:
        logger.exception("Falha ao inicializar cliente Firestore")
        raise FirebaseIndisponivelError(
            f"Erro ao inicializar cliente Firestore: {exc}"
        ) from exc


def carregar_dados():
    try:
        docs = _obter_db().collection("processos").stream()
        dados_padrao = criar_dados_padrao_persistencia()
        dados_db = {}
        revisoes_sessao = st.session_state.setdefault("_process_revision_snapshot", {})
        for doc in docs:
            valor_doc = doc.to_dict() or {}
            revisao_atual = int(valor_doc.get("_revision", 0) or 0)
            revisao_esperada = revisoes_sessao.setdefault(doc.id, revisao_atual)
            for chave, valor_padrao in dados_padrao.items():
                if chave not in valor_doc:
                    valor_doc[chave] = valor_padrao
            valor_doc["_revision"] = revisao_esperada
            dados_db[doc.id] = valor_doc
        st.session_state["firebase_load_error"] = ""
        return dados_db
    except FirebaseIndisponivelError as exc:
        st.session_state["firebase_load_error"] = str(exc)
        st.error(
            f"⚠️ Banco de dados indisponível: {exc} "
            "O app continua funcionando, mas os dados não serão carregados nem salvos na nuvem."
        )
        return {}
    except Exception as exc:
        st.session_state["firebase_load_error"] = str(exc)
        logger.exception("Falha ao carregar dados do Firestore")
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
        esperada = int(dados_proc.get("_revision", 0) or 0)
        db = _obter_db()
        ref = db.collection("processos").document(id_proc)
        transaction = db.transaction()

        @firestore.transactional
        def _salvar(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            revisao_atual = int((snapshot.to_dict() or {}).get("_revision", 0) or 0) if snapshot.exists else 0
            if revisao_atual != esperada:
                raise ProcessoAlteradoError(
                    "Este processo foi alterado por outro usuário desde que você o abriu. "
                    "Recarregue os dados antes de salvar novamente."
                )
            dados_normalizados["_revision"] = esperada + 1
            transaction.set(ref, dados_normalizados)
            return esperada + 1

        nova_revisao = _salvar(transaction, ref)
        st.session_state.setdefault("_process_revision_snapshot", {})[id_proc] = nova_revisao
        return True
    except Exception as exc:
        logging.exception("Falha ao salvar processo %s", id_proc)
        if isinstance(exc, ProcessoAlteradoError):
            st.error(str(exc))
        else:
            st.error(f"Erro Crítico de Rede: {exc}")
        return False


def salvar_processo_com_importacao(id_proc, dados_proc, registro_importacao):
    try:
        if not isinstance(registro_importacao, dict):
            raise ValueError("O registro de importação deve ser um dicionário.")

        dados_normalizados = _normalizar_dados_processo(dados_proc)
        esperada = int(dados_proc.get("_revision", 0) or 0)
        db = _obter_db()
        transaction = db.transaction()

        processo_ref = db.collection("processos").document(id_proc)
        importacao_ref = db.collection("importacoes_ia").document()

        @firestore.transactional
        def _salvar_importacao(transaction):
            snapshot = processo_ref.get(transaction=transaction)
            revisao_atual = int((snapshot.to_dict() or {}).get("_revision", 0) or 0) if snapshot.exists else 0
            if revisao_atual != esperada:
                raise ProcessoAlteradoError(
                    "Este processo foi alterado por outro usuário durante a importação. "
                    "Recarregue os dados e confirme a importação novamente."
                )
            dados_normalizados["_revision"] = esperada + 1
            transaction.set(processo_ref, dados_normalizados)
            transaction.set(importacao_ref, registro_importacao)
            return esperada + 1

        nova_revisao = _salvar_importacao(transaction)
        st.session_state.setdefault("_process_revision_snapshot", {})[id_proc] = nova_revisao
        return True
    except Exception as exc:
        logging.exception("Falha ao salvar processo importado %s", id_proc)
        if isinstance(exc, ProcessoAlteradoError):
            st.error(str(exc))
        else:
            st.error(f"Erro ao salvar processo importado: {exc}")
        return False


def excluir_processo(id_proc):
    try:
        _obter_db().collection("processos").document(id_proc).delete()
    except Exception as exc:
        logger.exception("Falha ao excluir processo %s", id_proc)
        st.error(f"Erro ao excluir na nuvem: {exc}")


def _obter_maior_numero_processo(chaves_processos):
    maior_numero = 0
    for chave in chaves_processos:
        if not isinstance(chave, str) or not chave.startswith("Proc_"):
            continue
        sufixo = chave.split("_", 1)[1]
        if sufixo.isdigit():
            maior_numero = max(maior_numero, int(sufixo))
    return maior_numero


def estimar_proximo_id_local(db_local):
    proximo = _obter_maior_numero_processo((db_local or {}).keys()) + 1
    return f"Proc_{proximo:02d}"


def gerar_proximo_id(db_local=None):
    try:
        db = _obter_db()
        contador_ref = db.collection("app_meta").document("processos_counter")
        transacao = db.transaction()
        maior_local = _obter_maior_numero_processo((db_local or {}).keys())

        @firestore.transactional
        def _incrementar_contador(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            atual = 0
            if snapshot.exists:
                valor = snapshot.to_dict().get("ultimo_numero")
                if isinstance(valor, int):
                    atual = valor
            proximo = max(atual, maior_local) + 1
            transaction.set(ref, {"ultimo_numero": proximo}, merge=True)
            return proximo

        proximo_numero = _incrementar_contador(transacao, contador_ref)
        return f"Proc_{proximo_numero:02d}"
    except Exception:
        logging.exception("Falha ao gerar ID atômico do processo. Usando fallback local.")
        return estimar_proximo_id_local(db_local or {})
