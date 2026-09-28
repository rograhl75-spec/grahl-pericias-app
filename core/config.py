import copy
from datetime import datetime
from pathlib import Path

import streamlit as st

LOGO_FILE = str(Path(__file__).resolve().parent.parent / "logo dourado grahl consultoria.png")


class ConfigurationError(Exception):
    """Erro de configuração obrigatória do app."""


APP_CONFIG_DEFAULTS = {
    "max_api_calls_per_day": 50,
    "max_file_size_mb": 200,
    "max_single_pdf_size_mb": 75,
    "max_pdf_files": 5,
    "max_pdf_pages_total": 1200,
    "max_pdf_chars_total": 600_000,
    "claude_chunk_chars": 120_000,
    "claude_max_chunks": 6,
    "claude_model": "claude-3-5-sonnet-20241022",
    "cost_limit_per_day": 250.00,
    "usd_brl_exchange_rate": 5.00,
    "environment": "production",
}

FIREBASE_REQUIRED_FIELDS = (
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "token_uri",
)

_DADOS_PADRAO = {
    "modulo_atuacao": "Perícia Judicial Trabalhista",
    "tipos_pericia": ["Insalubridade (NR-15)", "Aposentadoria Especial (PPP/LTCAT)"],
    "papel_profissional": "Assistente Técnico da Reclamada",
    "processo_num": "",
    "orgao_julgador": "Vara do Trabalho de Londrina - PR",
    "data_autuacao": "",
    "valor_causa": "",
    "rito_processual": "Ordinário / Sumaríssimo",
    "reclamante_nome": "",
    "reclamante_cpf": "",
    "reclamante_adv": "",
    "reclamada_nome": "",
    "reclamada_cnpj": "",
    "reclamada_adv": "",
    "data_admissao": "",
    "status_contrato": "Ativo",
    "periodo_imprescrito": "",
    "cargos": "",
    "setor": "",
    "ultima_remuneracao": "",
    "objeto_pericia": "Insalubridade, Periculosidade e/ou Aposentadoria Especial",
    "atividades_inicial": "",
    "agentes_alegados": "",
    "pedidos_tecnicos": "",
    "preliminares_periciais": "",
    "defesa_merito_sst": "",
    "fase_processual": "Aguardando diligência pericial",
    "campo_data": "",
    "campo_horario": "14:00",
    "local_diligencia": "",
    "presentes_pericia": "",
    "doc_ltcat": "",
    "doc_laudo": "",
    "doc_ppp": "",
    "doc_pgr": "",
    "doc_os": "",
    "doc_asos": "",
    "doc_outros": "",
    "quadro_epis": [],
    "analise_epis_critica": "",
    "quesitos_juizo": "",
    "quesitos_autor": "",
    "quesitos_reu": "",
    "segurado_nascimento": "",
    "profissao_cargo": "",
    "relato_inicial": "",
    "apr_fisicos": "Ruído contínuo ou intermitente (NHO-01)",
    "apr_quimicos": "Hidrocarbonetos / Solventes / Produtos químicos da atividade",
    "apr_biologicos": "Agentes biológicos (se aplicável)",
    "enquadramento_legal_prev": "Decreto 3.048/99 (Anexo IV)",
    "extemp_layout": False,
    "extemp_maquinas": False,
    "extemp_epc": False,
    "extemp_justificativa": "As condições ambientais, layout e tecnologias mantêm-se inalteradas em relação ao período pretendido (Art. 279, IN 128/2022).",
    "campo_declaracoes_autor": "",
    "campo_declaracoes_reu": "",
    "campo_medicoes": "",
    "campo_fotos": [],
}


def criar_dados_padrao():
    dados = copy.deepcopy(_DADOS_PADRAO)
    data_atual = datetime.now().strftime("%d/%m/%Y")
    dados["data_autuacao"] = data_atual
    dados["campo_data"] = data_atual
    return dados


def criar_dados_padrao_persistencia():
    return copy.deepcopy(_DADOS_PADRAO)


def _valor_placeholder(valor):
    if valor is None:
        return True

    if not isinstance(valor, str):
        return False

    valor_limpo = valor.strip()
    if not valor_limpo:
        return True

    valor_lower = valor_limpo.lower()
    placeholders = (
        "your_",
        "replace_",
        "example",
        "<",
        "cole_",
        "insira_",
    )
    return any(token in valor_lower for token in placeholders)


def obter_app_config():
    config = copy.deepcopy(APP_CONFIG_DEFAULTS)
    try:
        config.update(dict(st.secrets.get("app", {})))
    except Exception:
        pass
    return config


def obter_taxa_cambio_usd_brl() -> float:
    try:
        taxa = float(obter_app_config().get("usd_brl_exchange_rate", 5.00))
        return max(taxa, 0.0)
    except (TypeError, ValueError):
        return 5.00


def obter_api_key_anthropic():
    api_key = str(st.secrets.get("anthropic", {}).get("api_key", "")).strip()
    if _valor_placeholder(api_key):
        raise ConfigurationError(
            "Configure st.secrets['anthropic']['api_key'] com uma chave válida da Anthropic."
        )
    return api_key


def obter_credenciais_firebase():
    try:
        cred_dict = dict(st.secrets.get("firebase", {}))
    except Exception:
        cred_dict = {}

    campos_faltantes = [
        campo for campo in FIREBASE_REQUIRED_FIELDS if _valor_placeholder(cred_dict.get(campo))
    ]
    if campos_faltantes:
        campos = ", ".join(campos_faltantes)
        raise ConfigurationError(
            f"Configure st.secrets['firebase'] com os campos obrigatórios: {campos}."
        )

    private_key = cred_dict.get("private_key")
    if isinstance(private_key, str):
        cred_dict["private_key"] = private_key.replace("\\n", "\n")

    return cred_dict
