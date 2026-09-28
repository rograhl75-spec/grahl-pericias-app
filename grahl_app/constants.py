from datetime import datetime

LOGO_FILE = "logo dourado grahl consultoria.png"
COLLECTION_PROCESSOS = "processos"
ID_PREFIX = "Proc_"
ID_WIDTH = 2
PHOTO_DEFAULT_CAPTION = "Registro fotográfico obtido em diligência pericial."
NO_CASE_SELECTED = "Nenhum caso cadastrado"

MENU_NEW = "➕ Novo Processo / Caso"
MENU_DATA = "✏️ Dados, Escritório & SST"
MENU_FIELD = "🚜 Diligência de Campo & Fotos"
MENU_DELETE = "🗑️ Excluir Processo"
MENU_DOCX = "📄 Gerar Documento Word Final"
MENU_OPTIONS = [MENU_NEW, MENU_DATA, MENU_FIELD, MENU_DELETE, MENU_DOCX]

MODULE_JUDICIAL = "Perícia Judicial Trabalhista"
MODULE_PREVIDENCIARIO = "Laudo Extrajudicial Previdenciário (LTCAT+PPP)"
MODULE_OPTIONS = [
    "⚖️ Perícia Judicial Trabalhista (SST / Insalubridade / Periculosidade / Aposentadoria Especial)",
    "📄 Laudo Extrajudicial Previdenciário (LTCAT + PPP Extemporâneo/Contemporâneo)",
]

ROLE_OPTIONS = ["Perito do Juízo", "Assistente Técnico da Reclamante", "Assistente Técnico da Reclamada"]
TIPOS_PERICIA_OPTIONS = [
    "Insalubridade (NR-15)",
    "Periculosidade (NR-16)",
    "Aposentadoria Especial (PPP/LTCAT)",
]
TIPOS_PERICIA_DEFAULT = ["Insalubridade (NR-15)", "Aposentadoria Especial (PPP/LTCAT)"]

SESSION_DEFAULTS = {
    "processo_ativo": None,
    "menu_opcao": MENU_NEW,
    "parsed_data": {},
    "gps_field_main": "",
    "confirmar_exclusao_dupla": False,
    "uploader_key": 0,
}


def build_default_data() -> dict:
    hoje = datetime.now().strftime("%d/%m/%Y")
    return {
        "modulo_atuacao": MODULE_JUDICIAL,
        "tipos_pericia": TIPOS_PERICIA_DEFAULT.copy(),
        "papel_profissional": "Assistente Técnico da Reclamada",
        "processo_num": "",
        "orgao_julgador": "Vara do Trabalho de Londrina - PR",
        "data_autuacao": hoje,
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
        "campo_data": hoje,
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


DADOS_PADRAO = build_default_data()
