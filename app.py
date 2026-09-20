import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from docx import Document
from docx.shared import Inches, Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from PIL import Image
import json
import os
import io
import re
import base64
import unicodedata
from datetime import datetime

# --- CONFIGURAÇÃO FIREBASE NUVEM ---
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    try:
        cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error("Erro ao conectar no Firebase. Verifique o st.secrets.")

db = firestore.client()
# -----------------------------------

LOGO_FILE = "logo dourado grahl consultoria.png"

dados_padrao = {
    "modulo_atuacao": "Perícia Judicial Trabalhista",
    "tipos_pericia": ["Insalubridade (NR-15)", "Aposentadoria Especial (PPP/LTCAT)"],
    "papel_profissional": "Assistente Técnico da Reclamada",
    "processo_num": "",
    "orgao_julgador": "Vara do Trabalho de Londrina - PR",
    "data_autuacao": datetime.now().strftime("%d/%m/%Y"),
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
    "campo_data": datetime.now().strftime("%d/%m/%Y"),
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
    "campo_fotos": []
}

def remover_acentos(texto):
    if not texto or not isinstance(texto, str): return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

def calcula_altura(texto, min_h):
    if not texto: return min_h
    texto_str = str(texto)
    linhas_quebradas = texto_str.count('\n') + 1
    caracteres_extras_wrap = sum([len(linha) // 80 for linha in texto_str.split('\n')])
    return max(min_h, (linhas_quebradas + caracteres_extras_wrap) * 24 + 40)

# === MOTOR DE EXTRAÇÃO DUPLO (TAGS IA + TEXTO NATURAL) ===
def parse_pre_relatorio(doc):
    dados = {}
    texto_completo = ""
    linhas = []
    
    for p in doc.paragraphs:
        texto_completo += p.text + "\n"
        if p.text.strip(): linhas.append(p.text.strip())
        
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join([c.text.strip() for c in row.cells if c.text.strip()])
            if row_text:
                texto_completo += row_text + "\n"
                linhas.append(row_text)

    # 1. MOTOR DE TAGS DA IA (Prioridade Máxima)
    if "[START_" in texto_completo:
        def extrair_bloco(nome_tag):
            padrao = r"\[START_" + nome_tag + r"\](.*?)\[END_" + nome_tag + r"\]"
            match = re.search(padrao, texto_completo, re.DOTALL | re.IGNORECASE)
            if match:
                bloco = match.group(1).strip()
                if "[informação" in bloco.lower() or "não consta" in bloco.lower() or bloco.lower() in ["n/a", "na", "-"]:
                    return ""
                return bloco
            return ""

        dados["modulo_atuacao"] = extrair_bloco("MODULO")
        papel = extrair_bloco("PAPEL").lower()
        if "extrajudicial" in papel or "consultor" in papel: dados["papel_profissional"] = "Perito Extrajudicial / Consultor"
        elif "reclamante" in papel or "autor" in papel: dados["papel_profissional"] = "Assistente Técnico da Reclamante"
        elif "assistente" in papel or "reclamada" in papel: dados["papel_profissional"] = "Assistente Técnico da Reclamada"
        elif papel: dados["papel_profissional"] = "Perito do Juízo"
        
        dados["processo_num"] = extrair_bloco("PROCESSO_NUM")
        dados["orgao_julgador"] = extrair_bloco("ORGAO_JULGADOR")
        dados["data_autuacao"] = extrair_bloco("DATA_AUTUACAO")
        dados["valor_causa"] = extrair_bloco("VALOR_CAUSA")
        dados["rito_processual"] = extrair_bloco("RITO")
        
        dados["reclamante_nome"] = extrair_bloco("RECLAMANTE_NOME")
        dados["reclamante_cpf"] = extrair_bloco("RECLAMANTE_CPF")
        dados["reclamante_adv"] = extrair_bloco("RECLAMANTE_ADV")
        dados["segurado_nascimento"] = extrair_bloco("NASCIMENTO")
        
        dados["reclamada_nome"] = extrair_bloco("RECLAMADA_NOME")
        dados["reclamada_cnpj"] = extrair_bloco("RECLAMADA_CNPJ")
        dados["reclamada_adv"] = extrair_bloco("RECLAMADA_ADV")
        
        dados["data_admissao"] = extrair_bloco("DATA_ADMISSAO")
        dados["status_contrato"] = extrair_bloco("STATUS_CONTRATO")
        dados["periodo_imprescrito"] = extrair_bloco("PERIODO_IMPRESCRITO")
        
        cargos = extrair_bloco("CARGOS")
        dados["cargos"] = cargos
        dados["profissao_cargo"] = cargos
        
        dados["setor"] = extrair_bloco("SETOR")
        dados["ultima_remuneracao"] = extrair_bloco("ULTIMA_REMUNERACAO")
        dados["objeto_pericia"] = extrair_bloco("OBJETO_PERICIA")
        
        relato = extrair_bloco("RELATO_INICIAL")
        dados["atividades_inicial"] = relato
        dados["relato_inicial"] = relato
        
        dados["agentes_alegados"] = extrair_bloco("AGENTES_ALEGADOS")
        dados["apr_fisicos"] = extrair_bloco("APR_FISICOS")
        dados["apr_quimicos"] = extrair_bloco("APR_QUIMICOS")
        dados["apr_biologicos"] = extrair_bloco("APR_BIOLOGICOS")
        dados["enquadramento_legal_prev"] = extrair_bloco("ENQUADRAMENTO")
        
        dados["pedidos_tecnicos"] = extrair_bloco("PEDIDOS_TECNICOS")
        dados["preliminares_periciais"] = extrair_bloco("PRELIMINARES")
        dados["defesa_merito_sst"] = extrair_bloco("DEFESA_MERITO")
        
        dados["fase_processual"] = extrair_bloco("FASE_PROCESSUAL")
        dados["campo_data"] = extrair_bloco("DATA_VISTORIA")
        dados["campo_horario"] = extrair_bloco("HORARIO_VISTORIA")
        dados["local_diligencia"] = extrair_bloco("LOCAL_VISTORIA")
        
        dados["doc_ltcat"] = extrair_bloco("DOC_LTCAT")
        dados["doc_laudo"] = extrair_bloco("DOC_LAUDO")
        dados["doc_ppp"] = extrair_bloco("DOC_PPP")
        dados["doc_pgr"] = extrair_bloco("DOC_PGR")
        dados["doc_os"] = extrair_bloco("DOC_OS")
        dados["doc_asos"] = extrair_bloco("DOC_ASOS")
        dados["doc_outros"] = extrair_bloco("DOC_OUTROS")
        dados["analise_epis_critica"] = extrair_bloco("SINTESE_EPIS")
        
        dados["quesitos_juizo"] = extrair_bloco("QUESITOS_JUIZO")
        dados["quesitos_autor"] = extrair_bloco("QUESITOS_AUTOR")
        dados["quesitos_reu"] = extrair_bloco("QUESITOS_REU")

        quadro_epis_texto = extrair_bloco("QUADRO_EPIS")
        epis_extraidos = []
        if quadro_epis_texto:
            linhas_epi = quadro_epis_texto.strip().split('\n')
            for linha in linhas_epi:
                if '|' in linha and '---' not in linha and 'descri' not in linha.lower() and 'c.a' not in linha.lower() and 'ca' not in linha.lower():
                    parts = [p.strip() for p in linha.split('|')]
                    if len(parts) >= 2:
                        desc = parts[0]
                        ca = parts[1]
                        data = parts[2] if len(parts) > 2 else ""
                        obs = parts[3] if len(parts) > 3 else ""
                        if desc and "[informação" not in desc.lower() and "n/a" not in desc.lower():
                            epis_extraidos.append({"descricao": desc, "ca": ca, "data_entrega": data, "obs": obs})
        dados["quadro_epis"] = epis_extraidos
        
        return dados

    # 2. MOTOR DE TEXTO NATURAL (Fallback para documentos de escritório sem tags)
    texto = "\n".join(linhas).replace("**", "").replace("*", "")

    def get_single(padrao):
        m = re.search(r"(?:" + padrao + r")[\s]*[:|][\s]*([^\n]+)", texto, re.IGNORECASE)
        if m:
            v = m.group(1).replace("_", "").strip()
            if v and "[informação" not in v.lower(): return v
        return ""

    def get_multi(padrao, next_sections):
        lookahead = r"(?=\n\d+\.\s*|(?:" + "|".join(next_sections) + r")|$)"
        m = re.search(r"(?:" + padrao + r")[\s]*[:|]?[\s]*(.*?)" + lookahead, texto, re.IGNORECASE | re.DOTALL)
        if m:
            v = m.group(1).replace("_", "").strip()
            if v and "[informação" not in v.lower(): return v
        return ""

    dados["processo_num"] = get_single(r"Número do Processo|Processo")
    dados["orgao_julgador"] = get_single(r"Órgão Julgador / Vara|Órgão Julgador")
    dados["data_autuacao"] = get_single(r"Data de Autuação.*?Ajuizamento.*?|Data de Autuação")
    dados["valor_causa"] = get_single(r"Valor da Causa")
    dados["rito_processual"] = get_single(r"Rito Processual")

    rec = get_single(r"Reclamante \(Autor/Autora\)|Reclamante|Nome do Segurado|Nome")
    if rec:
        m_cpf = re.search(r"\((?:CPF|NIT|PIS)\s*([\d\.\-\/]+)\)", rec, re.IGNORECASE)
        if m_cpf:
            dados["reclamante_cpf"] = m_cpf.group(1)
            rec = re.sub(r"\((?:CPF|NIT|PIS).*?\)", "", rec, flags=re.IGNORECASE).strip()
        dados["reclamante_nome"] = rec
    if not dados.get("reclamante_cpf"): dados["reclamante_cpf"] = get_single(r"CPF / NIT / PIS|CPF/NIT|CPF")

    recd = get_single(r"Reclamada \(Ré/Empresa\)|Razão Social da Empresa / Tomador|Reclamada|Razão Social")
    if recd:
        m_cnpj = re.search(r"CNPJ[\s:]*([\d\.\-\/]+)", recd, re.IGNORECASE)
        if m_cnpj:
            dados["reclamada_cnpj"] = m_cnpj.group(1)
            recd = re.sub(r"\(?CNPJ.*?\)?", "", recd, flags=re.IGNORECASE).strip()
        dados["reclamada_nome"] = recd.strip(" ()-")
    if not dados.get("reclamada_cnpj"): dados["reclamada_cnpj"] = get_single(r"CNPJ da Empresa|CNPJ")

    advs = re.findall(r"Advogados[\s]*[:|][\s]*([^\n]+)", texto, re.IGNORECASE)
    if len(advs) >= 1: dados["reclamante_adv"] = advs[0].strip()
    if len(advs) >= 2: dados["reclamada_adv"] = advs[1].strip()

    dados["data_admissao"] = get_single(r"Data de Admissão|Período Avaliado")
    dados["status_contrato"] = get_single(r"Status do Contrato")
    dados["periodo_imprescrito"] = get_single(r"Período Imprescrito.*?Alvo da Perícia.*?")
    cargo = get_single(r"Cargo\(s\) / Função\(ões\)|Profissão / Cargo Avaliado|Profissão / Cargo")
    if cargo:
        dados["cargos"] = cargo
        dados["profissao_cargo"] = cargo
    dados["segurado_nascimento"] = get_single(r"Data de Nascimento")
    dados["setor"] = get_single(r"Setor / Lotação.*?|Setor")
    dados["ultima_remuneracao"] = get_single(r"Última Remuneração.*?")
    dados["objeto_pericia"] = get_single(r"Objeto da Perícia|Objeto de Análise / Perícia|Objetivo")

    paradas = [r"Agentes Nocivos", r"Agentes Físicos", r"Pedidos Técnicos", r"Preliminares Periciais", r"Defesa de Mérito", r"Fase Processual", r"Data da Vistoria", r"Local / Endereço", r"Análise do LTCAT", r"Laudo de Insalubridade", r"Análise do PPP", r"Análise do PGR", r"Ordens de Serviço", r"ASOs / PCMSO", r"Outros Documentos", r"Síntese e Análise", r"9\.1", r"9\.2", r"9\.3", r"Pessoas Presentes", r"Informações prestadas", r"Medições Realizadas"]
    
    dados["atividades_inicial"] = get_multi(r"Atividades Descritas.*?|Atividades Típicas.*?|Relato das Atividades.*?|Relato Inicial.*?", paradas)
    if not dados.get("relato_inicial"): dados["relato_inicial"] = dados.get("atividades_inicial", "")

    dados["agentes_alegados"] = get_multi(r"Agentes Nocivos / Riscos Alegados|Agentes Nocivos", paradas)
    dados["apr_fisicos"] = get_multi(r"Agentes Físicos", paradas)
    dados["apr_quimicos"] = get_multi(r"Agentes Químicos", paradas)
    dados["apr_biologicos"] = get_multi(r"Agentes Biológicos", paradas)
    dados["enquadramento_legal_prev"] = get_multi(r"Enquadramento Legal", paradas)
    
    dados["pedidos_tecnicos"] = get_multi(r"Pedidos Técnicos", paradas)
    dados["preliminares_periciais"] = get_multi(r"Preliminares Periciais", paradas)
    dados["defesa_merito_sst"] = get_multi(r"Defesa de Mérito \(SST\)", paradas)

    dados["fase_processual"] = get_multi(r"Fase Processual Atual", paradas)
    dados["campo_data"] = get_multi(r"Data da Vistoria", paradas)
    dados["campo_horario"] = get_multi(r"Horário|Horário da Vistoria", paradas)
    dados["local_diligencia"] = get_multi(r"Local / Endereço", paradas)

    dados["doc_ltcat"] = get_multi(r"LTCAT", paradas)
    dados["doc_laudo"] = get_multi(r"LAUDO DE INSALUBRIDADE / PERICULOSIDADE.*?", paradas)
    dados["doc_ppp"] = get_multi(r"PPP.*?", paradas)
    dados["doc_pgr"] = get_multi(r"PGR / PPRA / PCMAT", paradas)
    dados["doc_os"] = get_multi(r"ORDENS DE SERVIÇO.*?", paradas)
    dados["doc_asos"] = get_multi(r"ASOs / PCMSO", paradas)
    dados["doc_outros"] = get_multi(r"Outros Documentos Relevantes", paradas)

    dados["analise_epis_critica"] = get_multi(r"Síntese e Análise Crítica de EPIs", paradas)

    paradas_quesitos = [r"\n9\.2\.", r"\n9\.3\.", r"\n10\.\s+LEVANTAMENTOS", r"\nPessoas Presentes"]
    dados["quesitos_juizo"] = get_multi(r"9\.1\.\s+Quesitos do Juízo", [r"\n9\.2\."])
    dados["quesitos_autor"] = get_multi(r"9\.2\.\s+Quesitos do Reclamante.*?", [r"\n9\.3\."])
    dados["quesitos_reu"] = get_multi(r"9\.3\.\s+Quesitos da Reclamada.*?", [r"\n10\.\s+LEVANTAMENTOS", r"\nPessoas Presentes"])

    # Extração das Tabelas de EPIs
    epis_extraidos = []
    for table in doc.tables:
        if len(table.rows) > 0:
            hdr = [cell.text.lower() for cell in table.rows[0].cells]
            if any("descri" in h or "epi" in h for h in hdr) and any("c.a" in h or "ca" in h for h in hdr):
                for row in table.rows[1:]:
                    cells = row.cells
                    desc = cells[0].text.strip() if len(cells) > 0 else ""
                    ca = cells[1].text.strip() if len(cells) > 1 else ""
                    data = cells[2].text.strip() if len(cells) > 2 else ""
                    obs = cells[3].text.strip() if len(cells) > 3 else ""
                    desc = desc.replace("**", "").replace("*", "")
                    if desc and "[informação" not in desc.lower() and desc != "-":
                        epis_extraidos.append({"descricao": desc, "ca": ca, "data_entrega": data, "obs": obs})
    if epis_extraidos: dados["quadro_epis"] = epis_extraidos

    return dados

# --- FUNÇÕES DE BANCO DE DADOS EM NUVEM ---
def carregar_dados():
    try:
        docs = db.collection('processos').stream()
        dados_db = {}
        for doc in docs:
            v = doc.to_dict()
            k = doc.id
            for k_padrao, v_padrao in dados_padrao.items():
                if k_padrao not in v: v[k_padrao] = v_padrao
            dados_db[k] = v
        return dados_db
    except:
        return {}

def salvar_processo(id_proc, dados_proc):
    try: db.collection('processos').document(id_proc).set(dados_proc)
    except Exception as e: st.error(f"Erro ao salvar na nuvem: {e}")

def excluir_processo(id_proc):
    try: db.collection('processos').document(id_proc).delete()
    except Exception as e: st.error(f"Erro ao excluir na nuvem: {e}")

def gerar_proximo_id(db_local):
    numeros = []
    for k in db_local.keys():
        if k.startswith("Proc_"):
            try: numeros.append(int(k.split("_")[1]))
            except: pass
    proximo = max(numeros) + 1 if numeros else 1
    return f"Proc_{proximo:02d}"

icon_config = LOGO_FILE if os.path.exists(LOGO_FILE) else "🛡️"
st.set_page_config(page_title="Grahl Consultoria - Perícias", page_icon=icon_config, layout="wide")

if "processo_ativo" not in st.session_state: st.session_state.processo_ativo = None
if "menu_opcao" not in st.session_state: st.session_state.menu_opcao = "➕ Novo Processo / Caso"
if "parsed_data" not in st.session_state: st.session_state.parsed_data = {}
if "gps_field_main" not in st.session_state: st.session_state.gps_field_main = ""
if "confirmar_exclusao_dupla" not in st.session_state: st.session_state.confirmar_exclusao_dupla = False
if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0  

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    section[data-testid="stSidebar"] { background-color: #1B365D; padding-top: 1.5rem; }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] label { color: #FFFFFF !important; }
    section[data-testid="stSidebar"] .stSelectbox label p { color: #E2E8F0 !important; font-size: 16px !important; font-weight: 600 !important; }
    section[data-testid="stSidebar"] .stButton button {
        width: 100% !important; border-radius: 12px !important; padding: 14px 18px !important;
        font-size: 15px !important; font-weight: 700 !important; color: white !important;
        border: 2px solid rgba(255,255,255,0.25) !important; box-shadow: 0 4px 6px rgba(0,0,0,0.2) !important;
        margin-bottom: 10px !important; text-align: left !important; transition: all 0.2s ease;
    }
    section[data-testid="stSidebar"] .stButton:nth-of-type(1) button { background-color: #2563EB !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(2) button { background-color: #0D9488 !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(3) button { background-color: #16A34A !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(4) button { background-color: #DC2626 !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(5) button { background-color: #9333EA !important; }
    section[data-testid="stSidebar"] .stButton button:hover { filter: brightness(1.15) !important; transform: translateY(-2px); }
    div.block-container { padding-top: 2rem; }
    h1 { color: #1B365D !important; font-weight: 800 !important; letter-spacing: -0.5px; }
    h2, h3 { color: #1B365D !important; font-weight: 700 !important; }
    label, .stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label { color: #1B365D !important; font-weight: 700 !important; font-size: 15px !important; }
    input, textarea { background-color: #FFFFFF !important; border: 1px solid #CBD5E1 !important; border-radius: 8px !important; font-size: 16px !important; }
    textarea { field-sizing: content !important; }
    .stButton button { background-color: #1B365D !important; color: white !important; font-weight: 700 !important; border-radius: 8px !important; padding: 0.5rem 1.2rem; border: none; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); transition: all 0.3s ease; }
    .stButton button:hover { background-color: #2D4A7C !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #E2E8F0; border-radius: 8px 8px 0px 0px; color: #1B365D; font-weight: 700; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #1B365D !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

db_processos = carregar_dados()

col_logo, col_titulo = st.columns([1, 6])
with col_logo:
    logo_encontrado = LOGO_FILE if os.path.exists(LOGO_FILE) else None
    if logo_encontrado: st.image(logo_encontrado, width=140)
    else: st.markdown("### 🛡️ **GRAHL**")

with col_titulo:
    st.markdown("<h1 style='margin:0; font-size: 1.7rem;'>Gestão Pericial Trabalhista & Extrajudicial</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748B; margin:0; font-size: 1rem; font-weight: 500;'>Assistência Técnica, Perícias Judiciais e Laudos Previdenciários.</p>", unsafe_allow_html=True)

st.markdown("<hr style='margin-top: 1rem; margin-bottom: 1.5rem; border: none; height: 1px; background-color: #CBD5E1;'>", unsafe_allow_html=True)

def trocar_menu(acao): st.session_state.menu_opcao = acao

st.sidebar.markdown("<h2 style='color: #FFFFFF; font-size: 1.3rem; margin-bottom: 1rem;'>📁 Painel de Controle</h2>", unsafe_allow_html=True)
acoes_menu = ["➕ Novo Processo / Caso", "✏️ Dados, Escritório & SST", "🚜 Diligência de Campo & Fotos", "🗑️ Excluir Processo", "📄 Gerar Documento Word Final"]
for acao in acoes_menu: st.sidebar.button(acao, on_click=trocar_menu, args=(acao,), use_container_width=True)

opcao = st.session_state.menu_opcao

st.sidebar.markdown("<hr style='border: none; height: 1px; background-color: rgba(255,255,255,0.2); margin: 1.5rem 0;'>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='color: #FFFFFF; font-weight: 600; font-size: 14px; margin-bottom: 0.3rem;'>🔎 Pesquisa Rápida:</p>", unsafe_allow_html=True)

termo_busca_geral = st.sidebar.text_input("Busca", placeholder="ID, Processo, Nome ou Empresa...", label_visibility="collapsed").strip()
processos_filtrados = []
termo_limpo = remover_acentos(termo_busca_geral)

if db_processos:
    for k, v in db_processos.items():
        if not termo_limpo:
            processos_filtrados.append(k)
        else:
            id_norm = remover_acentos(k)
            proc_num_norm = remover_acentos(str(v.get("processo_num", "")))
            reclamada_norm = remover_acentos(str(v.get("reclamada_nome", "")))
            reclamante_norm = remover_acentos(str(v.get("reclamante_nome", "")))
            if (termo_limpo in id_norm or termo_limpo in proc_num_norm or termo_limpo in reclamada_norm or termo_limpo in reclamante_norm):
                processos_filtrados.append(k)

st.sidebar.markdown("<br>", unsafe_allow_html=True)

if processos_filtrados:
    mapa_opcoes = {}
    for k in processos_filtrados:
        v = db_processos[k]
        nome = v.get("reclamante_nome", "Sem Nome")
        empresa = v.get("reclamada_nome", "")
        num_p = v.get("processo_num", "")
        label = f"[{k}] {nome}"
        if empresa: label += f" x {empresa}"
        elif num_p: label += f" ({num_p})"
        mapa_opcoes[label] = k

    if st.session_state.processo_ativo not in processos_filtrados:
        st.session_state.processo_ativo = processos_filtrados[0]
        
    lista_chaves = list(mapa_opcoes.keys())
    idx_selecionado = 0
    for i, rotulo in enumerate(lista_chaves):
        if mapa_opcoes[rotulo] == st.session_state.processo_ativo:
            idx_selecionado = i
            break

    def atualizar_processo():
        rotulo_escolhido = st.session_state.caixa_pesquisa
        novo_id = mapa_opcoes[rotulo_escolhido]
        st.session_state.processo_ativo = novo_id
        st.session_state.menu_opcao = "✏️ Dados, Escritório & SST"

    st.sidebar.selectbox("Processo / Caso Selecionado:", options=lista_chaves, index=idx_selecionado, key="caixa_pesquisa", on_change=atualizar_processo)
    processo_id_selecionado = st.session_state.processo_ativo
else:
    st.sidebar.warning("⚠️ Nenhum caso encontrado.")
    processo_id_selecionado = "Nenhum caso cadastrado"

if opcao == "➕ Novo Processo / Caso":
    st.markdown("### Cadastrar Novo Caso ou Processo")
    proximo_id = gerar_proximo_id(db_processos)
    st.info(f"✨ O próximo ID gerado automaticamente é: **{proximo_id}**")

    st.markdown("<br>", unsafe_allow_html=True)
    modulo_escolhido = st.radio("Selecione o Módulo de Atuação:", [
        "⚖️ Perícia Judicial Trabalhista (SST / Insalubridade / Periculosidade / Aposentadoria Especial)", 
        "📄 Laudo Extrajudicial Previdenciário (LTCAT + PPP Extemporâneo/Contemporâneo)"
    ])

    is_prev_mod = "Previdenciário" in modulo_escolhido

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📥 Importar Documento Base (.docx)")
    arquivo_importado = st.file_uploader("Selecione o arquivo Word (com ou sem tags da IA).", type=["docx"], key=f"uploader_{st.session_state.uploader_key}")
    
    if arquivo_importado is not None:
        try:
            doc_ext = Document(arquivo_importado)
            dados_extraidos = parse_pre_relatorio(doc_ext)
            st.session_state.parsed_data = dados_extraidos
            
            key_num = f"novo_num_{st.session_state.uploader_key}"
            key_nome = f"novo_nome_{st.session_state.uploader_key}"
            key_emp = f"novo_emp_{st.session_state.uploader_key}"
            
            st.session_state[key_num] = dados_extraidos.get("processo_num", "") or ""
            st.session_state[key_nome] = dados_extraidos.get("reclamante_nome", "") or ""
            st.session_state[key_emp] = dados_extraidos.get("reclamada_nome", "") or ""
            
            st.success("🤖 Documento lido com sucesso pelo Motor Híbrido!")
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("form_novo"):
        parsed = st.session_state.get("parsed_data", {})
        if is_prev_mod:
            lbl_num = "Identificação / Protocolo ou NIT/CPF"
            lbl_nome = "Nome do Segurado"
            lbl_emp = "Empresa / Tomador / Empregador"
            def_num = parsed.get("processo_num", "Extrajudicial Previdenciário")
        else:
            lbl_num = "Número do Processo (CNJ)"
            lbl_nome = "Reclamante (Autor/Autora)"
            lbl_emp = "Reclamada (Ré / Empresa)"
            def_num = parsed.get("processo_num", "")

        p_num = st.text_input(lbl_num, value=def_num, key=f"novo_num_{st.session_state.uploader_key}")
        p_nome = st.text_input(lbl_nome, value=parsed.get("reclamante_nome", ""), key=f"novo_nome_{st.session_state.uploader_key}")
        p_empresa = st.text_input(lbl_emp, value=parsed.get("reclamada_nome", ""), key=f"novo_emp_{st.session_state.uploader_key}")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.form_submit_button("Criar Caso Completo"):
            p_novo = dados_padrao.copy()
            if parsed:
                for k, v in parsed.items():
                    if v: p_novo[k] = v
            if is_prev_mod:
                p_novo["modulo_atuacao"] = "Laudo Extrajudicial Previdenciário (LTCAT+PPP)"
                p_novo["reclamante_nome"] = p_nome
                p_novo["reclamada_nome"] = p_empresa
                p_novo["processo_num"] = p_num
            else:
                p_novo["modulo_atuacao"] = "Perícia Judicial Trabalhista"
                p_novo["reclamante_nome"] = p_nome
                p_novo["reclamada_nome"] = p_empresa
                p_novo["processo_num"] = p_num
            
            salvar_processo(proximo_id, p_novo)
            st.session_state.parsed_data = {}
            st.session_state.uploader_key += 1
            st.session_state.processo_ativo = proximo_id
            st.session_state.menu_opcao = "✏️ Dados, Escritório & SST"
            st.toast(f"✅ Caso {proximo_id} criado com sucesso!", icon="💾")
            st.rerun()

elif opcao == "✏️ Dados, Escritório & SST":
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Cadastre ou selecione um caso no menu lateral para começar.")
    else:
        p_atual = db_processos[processo_id_selecionado]
        is_prev = "Previdenciário" in p_atual.get("modulo_atuacao", "")
        
        st.markdown(f"<div style='background-color: #E2E8F0; padding: 10px 15px; border-radius: 8px; margin-bottom: 20px;'><b style='color: #1B365D;'>Caso Ativo:</b> {processo_id_selecionado} &nbsp;|&nbsp; <b style='color: #1B365D;'>Papel:</b> {p_atual.get('papel_profissional', 'Não Definido')}</div>", unsafe_allow_html=True)
        
        if is_prev:
            tab1, tab2, tab3, tab4 = st.tabs(["1️⃣ Segurado & Tomador", "2️⃣ APR-HO & Extemporaneidade", "3️⃣ Planilha de EPIs", "4️⃣ Metodologia & Enquadramento"])
            with tab1:
                st.markdown("### 1. Identificação do Segurado e da Empresa")
                with st.form(f"fp_1_{processo_id_selecionado}"):
                    roles = ["Perito do Juízo", "Assistente Técnico da Reclamante", "Assistente Técnico da Reclamada", "Perito Extrajudicial / Consultor"]
                    atual_role = p_atual.get("papel_profissional", "Perito Extrajudicial / Consultor")
                    if atual_role not in roles: roles.append(atual_role)
                    p_atual["papel_profissional"] = st.selectbox("Meu Papel", roles, index=roles.index(atual_role))
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        p_atual["reclamante_nome"] = st.text_input("Nome do Segurado", value=p_atual.get("reclamante_nome", ""))
                        p_atual["reclamante_cpf"] = st.text_input("CPF / NIT / PIS", value=p_atual.get("reclamante_cpf", ""))
                        p_atual["segurado_nascimento"] = st.text_input("Data de Nascimento", value=p_atual.get("segurado_nascimento", ""))
                        p_atual["profissao_cargo"] = st.text_input("Profissão / Cargo Avaliado", value=p_atual.get("profissao_cargo", ""))
                    with col2:
                        p_atual["reclamada_nome"] = st.text_input("Razão Social da Empresa / Tomador", value=p_atual.get("reclamada_nome", ""))
                        p_atual["reclamada_cnpj"] = st.text_input("CNPJ da Empresa", value=p_atual.get("reclamada_cnpj", ""))
                        p_atual["setor"] = st.text_input("Setor / Lotação / Local", value=p_atual.get("setor", ""))
                        p_atual["data_admissao"] = st.text_input("Período de Trabalho (Admissão - Demissão)", value=p_atual.get("data_admissao", ""))

                    st.markdown("<br>", unsafe_allow_html=True)
                    val_relato = p_atual.get("relato_inicial", "")
                    p_atual["relato_inicial"] = st.text_area("Relato Inicial / Atividades Desenvolvidas pelo Segurado", value=val_relato, height=calcula_altura(val_relato, 120))
                    
                    if st.form_submit_button("💾 Salvar Dados do Segurado"):
                        salvar_processo(processo_id_selecionado, p_atual)
                        st.toast("✅ Dados salvos!", icon="💾")

            with tab2:
                st.markdown("### 2. Análise Preliminar de Riscos (APR-HO) & Extemporaneidade")
                with st.form(f"fp_2_{processo_id_selecionado}"):
                    v_fis = p_atual.get("apr_fisicos", "")
                    v_qui = p_atual.get("apr_quimicos", "")
                    v_bio = p_atual.get("apr_biologicos", "")
                    p_atual["apr_fisicos"] = st.text_area("Agentes Físicos Presumidos", value=v_fis, height=calcula_altura(v_fis, 80))
                    p_atual["apr_quimicos"] = st.text_area("Agentes Químicos", value=v_qui, height=calcula_altura(v_qui, 80))
                    p_atual["apr_biologicos"] = st.text_area("Agentes Biológicos", value=v_bio, height=calcula_altura(v_bio, 80))
                    
                    st.markdown("#### Avaliação de Extemporaneidade (Art. 279, IN 128/2022):")
                    p_atual["extemp_layout"] = st.checkbox("Houve mudança no layout ou organização?", value=p_atual.get("extemp_layout", False))
                    p_atual["extemp_maquinas"] = st.checkbox("Houve substituição de máquinas?", value=p_atual.get("extemp_maquinas", False))
                    p_atual["extemp_epc"] = st.checkbox("Houve alteração em EPCs?", value=p_atual.get("extemp_epc", False))
                    
                    v_ext = p_atual.get("extemp_justificativa", "")
                    p_atual["extemp_justificativa"] = st.text_area("Fundamentação de Equivalência", value=v_ext, height=calcula_altura(v_ext, 100))

                    if st.form_submit_button("💾 Salvar APR"):
                        salvar_processo(processo_id_selecionado, p_atual)
                        st.toast("✅ APR salva!", icon="💾")

            with tab3:
                st.markdown("### 3. Planilha de EPIs & Eficácia (Tema 555 STF)")
                epis_atuais = p_atual.get("quadro_epis", [])
                df_epis = pd.DataFrame(epis_atuais, columns=["descricao", "ca", "data_entrega", "obs"])
                edited_df = st.data_editor(
                    df_epis,
                    column_config={
                        "descricao": st.column_config.TextColumn("Descrição do EPI", width="large", required=True),
                        "ca": st.column_config.TextColumn("C.A.", width="small"),
                        "data_entrega": st.column_config.TextColumn("Periodicidade / Entrega", width="medium"),
                        "obs": st.column_config.TextColumn("Eficácia / Tema 555", width="large"),
                    },
                    num_rows="dynamic", use_container_width=True, height=300
                )

                if st.button("💾 Salvar Tabela de EPIs", key=f"btn_pe_{processo_id_selecionado}"):
                    df_clean = edited_df.fillna("")
                    df_clean = df_clean[df_clean["descricao"].astype(str).str.strip() != ""]
                    p_atual["quadro_epis"] = df_clean.to_dict('records')
                    salvar_processo(processo_id_selecionado, p_atual)
                    st.toast("✅ Planilha salva!", icon="💾")

                st.markdown("<br>", unsafe_allow_html=True)
                with st.form(f"form_prev_epi_{processo_id_selecionado}"):
                    v_epi = p_atual.get("analise_epis_critica", "")
                    p_atual["analise_epis_critica"] = st.text_area("Análise Crítica de EPIs", value=v_epi, height=calcula_altura(v_epi, 120))
                    if st.form_submit_button("💾 Salvar Análise"):
                        salvar_processo(processo_id_selecionado, p_atual)

            with tab4:
                st.markdown("### 4. Metodologia & Enquadramento")
                with st.form(f"form_prev_4_{processo_id_selecionado}"):
                    p_atual["enquadramento_legal_prev"] = st.text_input("Enquadramento Legal", value=p_atual.get("enquadramento_legal_prev", ""))
                    v_met = p_atual.get("doc_ltcat", "")
                    p_atual["doc_ltcat"] = st.text_area("Metodologia de Avaliação", value=v_met, height=calcula_altura(v_met, 150))
                    
                    if st.form_submit_button("💾 Salvar Metodologia"):
                        salvar_processo(processo_id_selecionado, p_atual)

        else:
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["1️⃣ Identificação & Partes", "2️⃣ Contrato & Sínteses", "3️⃣ SST & Documentos", "4️⃣ Planilha de EPIs", "5️⃣ Quesitos"])
            with tab1:
                st.markdown("### 1. Papel Profissional, Tipos de Perícia & Identificação")
                with st.form(f"ft_1_{processo_id_selecionado}"):
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        roles = ["Perito do Juízo", "Assistente Técnico da Reclamante", "Assistente Técnico da Reclamada", "Perito Extrajudicial / Consultor"]
                        atual_role = p_atual.get("papel_profissional", "Perito do Juízo")
                        if atual_role not in roles: roles.append(atual_role)
                        p_atual["papel_profissional"] = st.selectbox("Meu Papel", roles, index=roles.index(atual_role))
                    with col_p2:
                        p_atual["tipos_pericia"] = st.multiselect("Tipos de Perícia", ["Insalubridade (NR-15)", "Periculosidade (NR-16)", "Aposentadoria Especial (PPP/LTCAT)"], default=p_atual.get("tipos_pericia", ["Insalubridade (NR-15)"]))

                    st.markdown("<br>", unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        p_atual["processo_num"] = st.text_input("Número do Processo (CNJ)", value=p_atual.get("processo_num", ""))
                        p_atual["orgao_julgador"] = st.text_input("Órgão Julgador / Vara", value=p_atual.get("orgao_julgador", ""))
                        p_atual["data_autuacao"] = st.text_input("Data de Autuação (Ajuizamento)", value=p_atual.get("data_autuacao", ""))
                        p_atual["valor_causa"] = st.text_input("Valor da Causa", value=p_atual.get("valor_causa", ""))
                        p_atual["rito_processual"] = st.text_input("Rito Processual", value=p_atual.get("rito_processual", ""))
                    with col2:
                        p_atual["reclamante_nome"] = st.text_input("Reclamante (Autor/Autora)", value=p_atual.get("reclamante_nome", ""))
                        p_atual["reclamante_cpf"] = st.text_input("CPF do Reclamante", value=p_atual.get("reclamante_cpf", ""))
                        p_atual["reclamante_adv"] = st.text_input("Advogados do Reclamante", value=p_atual.get("reclamante_adv", ""))
                        p_atual["reclamada_nome"] = st.text_input("Reclamada (Ré / Empresa)", value=p_atual.get("reclamada_nome", ""))
                        p_atual["reclamada_cnpj"] = st.text_input("CNPJ da Reclamada", value=p_atual.get("reclamada_cnpj", ""))
                        p_atual["reclamada_adv"] = st.text_input("Advogados da Reclamada", value=p_atual.get("reclamada_adv", ""))

                    if st.form_submit_button("💾 Salvar Identificação"):
                        salvar_processo(processo_id_selecionado, p_atual)
                        st.toast("✅ Salvo!", icon="💾")

            with tab2:
                st.markdown("### 2. Contrato & Sínteses")
                with st.form(f"ft_2_{processo_id_selecionado}"):
                    col3, col4 = st.columns(2)
                    with col3:
                        p_atual["data_admissao"] = st.text_input("Data de Admissão", value=p_atual.get("data_admissao", ""))
                        p_atual["status_contrato"] = st.text_input("Status do Contrato", value=p_atual.get("status_contrato", ""))
                        p_atual["periodo_imprescrito"] = st.text_input("Período Imprescrito", value=p_atual.get("periodo_imprescrito", ""))
                        p_atual["cargos"] = st.text_input("Cargo(s) / Função(ões)", value=p_atual.get("cargos", ""))
                    with col4:
                        p_atual["setor"] = st.text_input("Setor / Lotação / Local", value=p_atual.get("setor", ""))
                        p_atual["ultima_remuneracao"] = st.text_input("Última Remuneração", value=p_atual.get("ultima_remuneracao", ""))

                    p_atual["objeto_pericia"] = st.text_input("Objeto da Perícia", value=p_atual.get("objeto_pericia", ""))
                    v_ati = p_atual.get("atividades_inicial", "")
                    p_atual["atividades_inicial"] = st.text_area("Atividades Descritas na Inicial", value=v_ati, height=calcula_altura(v_ati, 100))
                    v_age = p_atual.get("agentes_alegados", "")
                    p_atual["agentes_alegados"] = st.text_area("Agentes Nocivos / Riscos Alegados", value=v_age, height=calcula_altura(v_age, 100))
                    v_ped = p_atual.get("pedidos_tecnicos", "")
                    p_atual["pedidos_tecnicos"] = st.text_area("Pedidos Técnicos", value=v_ped, height=calcula_altura(v_ped, 100))
                    v_pre = p_atual.get("preliminares_periciais", "")
                    p_atual["preliminares_periciais"] = st.text_area("Preliminares Periciais", value=v_pre, height=calcula_altura(v_pre, 100))
                    v_def = p_atual.get("defesa_merito_sst", "")
                    p_atual["defesa_merito_sst"] = st.text_area("Defesa de Mérito SST", value=v_def, height=calcula_altura(v_def, 120))

                    if st.form_submit_button("💾 Salvar Contrato e Sínteses"):
                        salvar_processo(processo_id_selecionado, p_atual)

            with tab3:
                st.markdown("### 3. Vistoria & Análise de Documentos")
                with st.form(f"ft_3_{processo_id_selecionado}"):
                    col5, col6, col7 = st.columns(3)
                    with col5: p_atual["fase_processual"] = st.text_input("Fase Processual Atual", value=p_atual.get("fase_processual", ""))
                    with col6: p_atual["campo_data"] = st.text_input("Data da Vistoria", value=p_atual.get("campo_data", ""))
                    with col7: p_atual["campo_horario"] = st.text_input("Horário da Vistoria", value=p_atual.get("campo_horario", ""))
                    
                    p_atual["local_diligencia"] = st.text_input("Local da Diligência", value=p_atual.get("local_diligencia", ""))
                    
                    v_ltc = p_atual.get("doc_ltcat", "")
                    p_atual["doc_ltcat"] = st.text_area("LTCAT", value=v_ltc, height=calcula_altura(v_ltc, 90))
                    v_lau = p_atual.get("doc_laudo", "")
                    p_atual["doc_laudo"] = st.text_area("Laudos Prévios / Paradigmas", value=v_lau, height=calcula_altura(v_lau, 90))
                    v_ppp = p_atual.get("doc_ppp", "")
                    p_atual["doc_ppp"] = st.text_area("PPP", value=v_ppp, height=calcula_altura(v_ppp, 90))
                    v_pgr = p_atual.get("doc_pgr", "")
                    p_atual["doc_pgr"] = st.text_area("PGR / PPRA / PCMAT", value=v_pgr, height=calcula_altura(v_pgr, 90))
                    v_dos = p_atual.get("doc_os", "")
                    p_atual["doc_os"] = st.text_area("Ordens de Serviço e Treinamentos", value=v_dos, height=calcula_altura(v_dos, 90))
                    v_aso = p_atual.get("doc_asos", "")
                    p_atual["doc_asos"] = st.text_area("ASOs / PCMSO", value=v_aso, height=calcula_altura(v_aso, 90))
                    v_out = p_atual.get("doc_outros", "")
                    p_atual["doc_outros"] = st.text_area("Outros Documentos", value=v_out, height=calcula_altura(v_out, 90))

                    if st.form_submit_button("💾 Salvar Análise"):
                        salvar_processo(processo_id_selecionado, p_atual)

            with tab4:
                st.markdown("### 4. Quadro de Fornecimento de EPIs")
                epis_atuais = p_atual.get("quadro_epis", [])
                df_epis = pd.DataFrame(epis_atuais, columns=["descricao", "ca", "data_entrega", "obs"])
                edited_df = st.data_editor(
                    df_epis,
                    column_config={
                        "descricao": st.column_config.TextColumn("Descrição do EPI", width="large", required=True),
                        "ca": st.column_config.TextColumn("C.A.", width="small"),
                        "data_entrega": st.column_config.TextColumn("Data Entrega", width="medium"),
                        "obs": st.column_config.TextColumn("Observações", width="large"),
                    },
                    num_rows="dynamic", use_container_width=True, height=350
                )

                if st.button("💾 Salvar Tabela EPIs", key=f"btn_st_{processo_id_selecionado}"):
                    df_clean = edited_df.fillna("")
                    df_clean = df_clean[df_clean["descricao"].astype(str).str.strip() != ""]
                    p_atual["quadro_epis"] = df_clean.to_dict('records')
                    salvar_processo(processo_id_selecionado, p_atual)
                    st.toast("✅ EPIs salvos!", icon="💾")

                with st.form(f"ft_4_epi_{processo_id_selecionado}"):
                    v_epi2 = p_atual.get("analise_epis_critica", "")
                    p_atual["analise_epis_critica"] = st.text_area("Síntese Crítica de EPIs", value=v_epi2, height=calcula_altura(v_epi2, 180))
                    if st.form_submit_button("💾 Salvar Síntese"):
                        salvar_processo(processo_id_selecionado, p_atual)

            with tab5:
                st.markdown("### 5. Quesitos")
                with st.form(f"ft_5_{processo_id_selecionado}"):
                    v_q1 = p_atual.get("quesitos_juizo", "")
                    p_atual["quesitos_juizo"] = st.text_area("Quesitos do Juízo", value=v_q1, height=calcula_altura(v_q1, 150))
                    v_q2 = p_atual.get("quesitos_autor", "")
                    p_atual["quesitos_autor"] = st.text_area("Quesitos do Reclamante (Autor/Autora)", value=v_q2, height=calcula_altura(v_q2, 250))
                    v_q3 = p_atual.get("quesitos_reu", "")
                    p_atual["quesitos_reu"] = st.text_area("Quesitos da Reclamada (Ré / Empresa)", value=v_q3, height=calcula_altura(v_q3, 250))

                    if st.form_submit_button("💾 Salvar Quesitos"):
                        salvar_processo(processo_id_selecionado, p_atual)
                        st.toast("✅ Salvo!", icon="💾")

elif opcao == "🚜 Diligência de Campo & Fotos":
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Cadastre ou selecione um caso no menu lateral.")
    else:
        p_atual = db_processos[processo_id_selecionado]
        st.markdown(f"<div style='background-color: #E2E8F0; padding: 10px 15px; border-radius: 8px; margin-bottom: 20px;'><b style='color: #1B365D;'>Caso Ativo:</b> {processo_id_selecionado} &nbsp;|&nbsp; <b style='color: #1B365D;'>Papel:</b> {p_atual.get('papel_profissional', '')}</div>", unsafe_allow_html=True)

        st.markdown("### 🚜 Vistoria Pericial de Campo")
        with st.form(f"f_campo_{processo_id_selecionado}"):
            col_c1, col_c2 = st.columns(2)
            with col_c1: p_atual["campo_data"] = st.text_input("Data da Vistoria", value=p_atual.get("campo_data", ""))
            with col_c2: p_atual["campo_horario"] = st.text_input("Horário da Vistoria", value=p_atual.get("campo_horario", ""))

            p_atual["local_diligencia"] = st.text_input("Endereço da Diligência", value=p_atual.get("local_diligencia", ""))
            
            v_pres = p_atual.get("presentes_pericia", "")
            p_atual["presentes_pericia"] = st.text_area("Pessoas Presentes", value=v_pres, height=calcula_altura(v_pres, 80))
            v_ca = p_atual.get("campo_declaracoes_autor", "")
            p_atual["campo_declaracoes_autor"] = st.text_area("Declarações do Segurado / Autor", value=v_ca, height=calcula_altura(v_ca, 120))
            v_cr = p_atual.get("campo_declaracoes_reu", "")
            p_atual["campo_declaracoes_reu"] = st.text_area("Declarações do Empregador", value=v_cr, height=calcula_altura(v_cr, 120))
            v_cm = p_atual.get("campo_medicoes", "")
            p_atual["campo_medicoes"] = st.text_area("Medições Realizadas", value=v_cm, height=calcula_altura(v_cm, 120))

            if st.form_submit_button("💾 Salvar de Campo"):
                salvar_processo(processo_id_selecionado, p_atual)
                st.toast("✅ Textos de campo salvos!", icon="💾")

        st.markdown("<br>---<br>", unsafe_allow_html=True)
        st.markdown("#### 📍 Captura Rápida de GPS")
        gps_input_val = st.text_input("Coordenada GPS Atual:", value=st.session_state.get("gps_field_main", ""), placeholder="GPS_TARGET_FIELD")
        if gps_input_val != st.session_state.get("gps_field_main", ""):
            st.session_state.gps_field_main = gps_input_val

        components.html("""
            <div style="background: #E2E8F0; padding: 12px; border-radius: 8px; text-align: center; font-family: sans-serif;">
                <button onclick="getGPS()" style="background-color: #1B365D; color: white; border: none; padding: 12px 20px; border-radius: 6px; font-weight: bold; font-size: 15px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">📍 Obter GPS do Tablet Agora</button>
                <p id="gps_status" style="margin-top: 8px; font-weight: bold; color: #1B365D; font-size: 13px;"></p>
                <script>
                function injectGPS(coordStr) {
                    const mainInputs = window.parent.document.querySelectorAll('input[placeholder="GPS_TARGET_FIELD"]');
                    mainInputs.forEach(input => {
                        let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, "value").set;
                        nativeInputValueSetter.call(input, coordStr);
                        input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
                    });
                    const photoInputs = window.parent.document.querySelectorAll('input[placeholder="GPS_FOTO"]');
                    photoInputs.forEach(input => {
                        if(!input.value || input.value === "") { 
                            let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, "value").set;
                            nativeInputValueSetter.call(input, coordStr);
                            input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                }
                function getGPS() {
                    var st = document.getElementById("gps_status"); st.innerHTML = "Buscando satélites...";
                    if (navigator.geolocation) {
                        navigator.geolocation.getCurrentPosition(
                            function(position) {
                                var coordStr = position.coords.latitude.toFixed(6) + ", " + position.coords.longitude.toFixed(6);
                                st.innerHTML = "✅ GPS Obtido!"; injectGPS(coordStr);
                            },
                            function(error) {
                                st.innerHTML = "Tentando via rede 4G...";
                                navigator.geolocation.getCurrentPosition(
                                    function(position) {
                                        var coordStr = position.coords.latitude.toFixed(6) + ", " + position.coords.longitude.toFixed(6);
                                        st.innerHTML = "✅ GPS Obtido!"; injectGPS(coordStr);
                                    },
                                    function(err2) { st.innerHTML = "❌ Erro de GPS."; },
                                    {timeout: 10000, enableHighAccuracy: false, maximumAge: 60000}
                                );
                            }, {timeout: 8000, enableHighAccuracy: true, maximumAge: 0}
                        );
                    } else { st.innerHTML = "Geolocalização não suportada."; }
                }
                setInterval(function() {
                    const textareas = window.parent.document.querySelectorAll("textarea");
                    textareas.forEach(ta => {
                        if(ta.scrollHeight > ta.clientHeight) { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; }
                        ta.addEventListener('input', function() { this.style.height = 'auto'; this.style.height = this.scrollHeight + 'px'; });
                    });
                }, 1000);
                </script>
            </div>
        """, height=95)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📸 Captura de Evidências Fotográficas")
        
        img_camera = st.camera_input("📷 Tirar Foto Direta")
        if img_camera is not None:
            file_bytes = img_camera.getvalue()
            b64_encoded = base64.b64encode(file_bytes).decode('utf-8')
            gps_auto = st.session_state.get("gps_field_main", "")
            p_atual["campo_fotos"].append({ "base64": b64_encoded, "gps": gps_auto, "legenda": "Registro fotográfico." })
            salvar_processo(processo_id_selecionado, p_atual)
            st.toast("✅ Foto capturada!", icon="📸")
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        
        col_up1, col_up2 = st.columns([3, 1])
        with col_up1: fotos_upload = st.file_uploader("📁 Ou Enviar Foto(s) Galeria", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
        with col_up2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Limpar Todas"):
                p_atual["campo_fotos"] = []
                salvar_processo(processo_id_selecionado, p_atual)
                st.rerun()

        if fotos_upload:
            novas_fotos = False
            for img in fotos_upload:
                file_bytes = img.getvalue()
                b64_encoded = base64.b64encode(file_bytes).decode('utf-8')
                if not any(f.get("base64") == b64_encoded for f in p_atual["campo_fotos"]):
                    gps_auto = st.session_state.get("gps_field_main", "")
                    p_atual["campo_fotos"].append({ "base64": b64_encoded, "gps": gps_auto, "legenda": "Registro fotográfico." })
                    novas_fotos = True
            if novas_fotos:
                salvar_processo(processo_id_selecionado, p_atual)
                st.rerun()

        st.markdown("<br>---<br>", unsafe_allow_html=True)
        col_ger, col_btn_geral = st.columns([2, 1])
        with col_ger: st.markdown(f"#### 🖼️ Gerenciar Fotos ({len(p_atual.get('campo_fotos', []))} fotos):")
        with col_btn_geral:
            if st.button("⚡ Salvar GPS em Todas"):
                gps_atual_sessao = st.session_state.get("gps_field_main", "")
                if gps_atual_sessao:
                    for f_dict in p_atual["campo_fotos"]: f_dict["gps"] = gps_atual_sessao
                    salvar_processo(processo_id_selecionado, p_atual)
                    st.rerun()

        if not p_atual.get("campo_fotos"):
            st.info("Nenhuma foto cadastrada.")
        else:
            for idx, foto_dict in enumerate(p_atual["campo_fotos"]):
                with st.container():
                    col_img, col_dados = st.columns([1, 2])
                    with col_img:
                        if "base64" in foto_dict:
                            st.image(base64.b64decode(foto_dict["base64"]), width=220)
                        else:
                            st.warning("[Imagem não encontrada]")
                    with col_dados:
                        nova_legenda = st.text_input(f"Legenda {idx+1}", value=foto_dict.get("legenda", ""), key=f"lg_{idx}")
                        novo_gps = st.text_input(f"GPS {idx+1}", value=foto_dict.get("gps", ""), key=f"cg_{idx}", placeholder="GPS_FOTO")
                        
                        c_salvar, c_del = st.columns(2)
                        with c_salvar:
                            if st.button(f"💾 Atualizar {idx+1}"):
                                p_atual["campo_fotos"][idx]["legenda"] = nova_legenda
                                p_atual["campo_fotos"][idx]["gps"] = novo_gps
                                salvar_processo(processo_id_selecionado, p_atual)
                                st.rerun()
                        with c_del:
                            if st.button(f"🗑️ Excluir {idx+1}"):
                                p_atual["campo_fotos"].pop(idx)
                                salvar_processo(processo_id_selecionado, p_atual)
                                st.rerun()
                    st.markdown("---")

elif opcao == "🗑️ Excluir Processo":
    st.markdown("### Excluir Caso / Processo")
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Nenhum caso disponível.")
    else:
        p_excluir = db_processos[processo_id_selecionado]
        st.error(f"⚠️ Atenção: Você está prestes a excluir o caso **{processo_id_selecionado}**.")
        
        if not st.session_state.confirmar_exclusao_dupla:
            if st.button("🗑️ Solicitar Exclusão Definitiva"):
                st.session_state.confirmar_exclusao_dupla = True
                st.rerun()
        else:
            st.warning("🚨 TEM CERTEZA ABSOLUTA?")
            col_sim, col_nao = st.columns(2)
            with col_sim:
                if st.button("🔴 SIM, EXCLUIR PERMANENTEMENTE"):
                    excluir_processo(processo_id_selecionado)
                    st.session_state.confirmar_exclusao_dupla = False
                    st.session_state.processo_ativo = None
                    st.rerun()
            with col_nao:
                if st.button("❌ Cancelar"):
                    st.session_state.confirmar_exclusao_dupla = False
                    st.rerun()

elif opcao == "📄 Gerar Documento Word Final":
    st.markdown("### Geração do Documento Final em Word (.docx)")
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Selecione um caso válido no menu lateral.")
    else:
        p = db_processos[processo_id_selecionado]
        is_prev = "Previdenciário" in p.get("modulo_atuacao", "")
        st.markdown(f"<p style='font-size: 17px;'>Caso: <b>{processo_id_selecionado}</b> — Segurado: <i>{p.get('reclamante_nome', '')}</i></p>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📥 Gerar e Baixar Documento Oficial (.docx)"):
            doc = Document()
            for section in doc.sections:
                section.top_margin = Cm(3.0)
                section.left_margin = Cm(3.0)
                section.bottom_margin = Cm(2.0)
                section.right_margin = Cm(2.0)

            def adicionar_linha_vazia():
                p_v = doc.add_paragraph()
                p_v.paragraph_format.line_spacing = 1.5
                return p_v

            def add_bullet_inline(doc_obj, title, text):
                p_b = doc_obj.add_paragraph()
                p_b.paragraph_format.line_spacing = 1.5
                p_b.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r_title = p_b.add_run(f"• {title}: ")
                r_title.bold = True
                r_title.font.name = 'Abadi'
                r_title.font.size = Pt(11)
                r_text = p_b.add_run(f"{text if text else '[Informação não localizada]'}")
                r_text.font.name = 'Abadi'
                r_text.font.size = Pt(11)

            def add_topic_block(doc_obj, title, text):
                p_title = doc_obj.add_paragraph()
                p_title.paragraph_format.line_spacing = 1.5
                p_title.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r_title = p_title.add_run(f"• {title}:")
                r_title.bold = True
                r_title.font.name = 'Abadi'
                r_title.font.size = Pt(11)
                if not text: text = "[Informação não localizada]"
                for linha in text.split("\n"):
                    if linha.strip():
                        p_text = doc_obj.add_paragraph()
                        p_text.paragraph_format.line_spacing = 1.5
                        p_text.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        r_text = p_text.add_run(linha.strip())
                        r_text.font.name = 'Abadi'
                        r_text.font.size = Pt(11)

            def adicionar_titulo(texto, level=2):
                h = doc.add_heading(level=level)
                h.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                h.paragraph_format.space_before = Pt(18)
                h.paragraph_format.space_after = Pt(6)
                h.paragraph_format.line_spacing = 1.5
                run = h.add_run(texto)
                run.font.name = 'Abadi'
                run.font.size = Pt(14) if level <= 2 else Pt(12)
                run.bold = True
                run.font.color.rgb = RGBColor(27, 54, 93)

            def definir_largura_tabela_100(tabela):
                tblPr = tabela._tbl.tblPr
                tblW = OxmlElement('w:tblW')
                tblW.set(qn('w:w'), '5000')
                tblW.set(qn('w:type'), 'pct')
                tblPr.append(tblW)

            logo_doc = None
            if os.path.exists(LOGO_FILE): logo_doc = LOGO_FILE
            if logo_doc:
                p_logo = doc.add_paragraph()
                p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_logo.add_run().add_picture(logo_doc, width=Inches(2.0))
                adicionar_linha_vazia()

            t_main = doc.add_paragraph()
            t_main.alignment = WD_ALIGN_PARAGRAPH.CENTER
            t_main.paragraph_format.line_spacing = 1.5
            
            titulo_doc = "LAUDO TÉCNICO PERICIAL (LTCAT/PPP)" if is_prev else "PRÉ-RELATÓRIO DE ANÁLISE PROCESSUAL E PERICIAL"
            r_t = t_main.add_run(titulo_doc)
            r_t.bold = True
            r_t.font.name = 'Abadi'
            r_t.font.size = Pt(15)
            r_t.font.color.rgb = RGBColor(27, 54, 93)
            
            p_papel = doc.add_paragraph()
            p_papel.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_papel.paragraph_format.line_spacing = 1.5
            r_p1 = p_papel.add_run(f"Módulo: {p.get('modulo_atuacao', '')}\n")
            r_p2 = p_papel.add_run(f"Profissional: {p.get('papel_profissional', 'Perito / Consultor')}")
            for r in [r_p1, r_p2]:
                r.bold = True
                r.font.name = 'Abadi'
                r.font.size = Pt(11)

            if is_prev:
                adicionar_titulo("1. IDENTIFICAÇÃO DO SEGURADO E DA EMPRESA", level=2)
                add_bullet_inline(doc, "Nome do Segurado", p.get('reclamante_nome', ''))
                add_bullet_inline(doc, "CPF / NIT / PIS", p.get('reclamante_cpf', ''))
                add_bullet_inline(doc, "Data de Nascimento", p.get('segurado_nascimento', ''))
                add_bullet_inline(doc, "Profissão / Cargo", p.get('profissao_cargo', ''))
                add_bullet_inline(doc, "Razão Social da Empresa", p.get('reclamada_nome', ''))
                add_bullet_inline(doc, "CNPJ", p.get('reclamada_cnpj', ''))
                add_bullet_inline(doc, "Setor / Lotação", p.get('setor', ''))
                add_bullet_inline(doc, "Período Avaliado", p.get('data_admissao', ''))

                adicionar_titulo("2. PROFISSIOGRAFIA E DESCRIÇÃO DAS ATIVIDADES", level=2)
                add_topic_block(doc, "Relato das Atividades e Rotina Diária", p.get('relato_inicial', ''))

                adicionar_titulo("3. IDENTIFICAÇÃO DOS AGENTES NOCIVOS (DECRETO 3.048/99)", level=2)
                add_topic_block(doc, "Agentes Físicos", p.get('apr_fisicos', ''))
                add_topic_block(doc, "Agentes Químicos", p.get('apr_quimicos', ''))
                add_topic_block(doc, "Agentes Biológicos", p.get('apr_biologicos', ''))
                add_bullet_inline(doc, "Enquadramento Legal", p.get('enquadramento_legal_prev', ''))

                adicionar_titulo("4. METODOLOGIA E PROCEDIMENTOS DE AVALIAÇÃO (IN 128 / NHO-01)", level=2)
                add_topic_block(doc, "Critérios Técnicos e Metodológicos", p.get('doc_ltcat', ''))

                adicionar_titulo("5. AVALIAÇÃO DE EXTEMPORANEIDADE (ART. 279 DA IN 128/2022)", level=2)
                p_ext = doc.add_paragraph()
                p_ext.paragraph_format.line_spacing = 1.5
                p_ext.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p_ext.add_run(f"• Mudança de layout: {'Sim' if p.get('extemp_layout') else 'Não'}\n")
                p_ext.add_run(f"• Substituição de máquinas: {'Sim' if p.get('extemp_maquinas') else 'Não'}\n")
                p_ext.add_run(f"• Alteração em EPC: {'Sim' if p.get('extemp_epc') else 'Não'}\n")
                for run in p_ext.runs:
                    run.font.name = 'Abadi'
                    run.font.size = Pt(11)
                add_topic_block(doc, "Fundamentação de Equivalência", p.get('extemp_justificativa', ''))

                adicionar_titulo("6. MEDIDAS DE PROTEÇÃO E EFICÁCIA DE EPI (TEMA 555 STF)", level=2)
                quadro_epis = p.get('quadro_epis', [])
                if quadro_epis:
                    t_epi = doc.add_table(rows=len(quadro_epis) + 1, cols=4)
                    definir_largura_tabela_100(t_epi)
                    headers = ["Descrição do EPI", "C.A.", "Periodicidade", "Observações / Eficácia"]
                    for h_idx, h_text in enumerate(headers): t_epi.rows[0].cells[h_idx].text = h_text
                    
                    for r_idx, epi in enumerate(quadro_epis, start=1):
                        t_epi.rows[r_idx].cells[0].text = epi.get('descricao', '')
                        t_epi.rows[r_idx].cells[1].text = epi.get('ca', '')
                        t_epi.rows[r_idx].cells[2].text = epi.get('data_entrega', '')
                        t_epi.rows[r_idx].cells[3].text = epi.get('obs', '')

                    for i, row in enumerate(t_epi.rows):
                        for cell in row.cells:
                            tcPr = cell._tc.get_or_add_tcPr()
                            for p_cell in cell.paragraphs:
                                p_cell.paragraph_format.line_spacing = 1.15
                                for run in p_cell.runs:
                                    run.font.name = 'Abadi'
                                    run.font.size = Pt(8.5)
                            if i == 0:
                                shd = parse_xml(r'<w:shd {} w:fill="1B365D"/>'.format(nsdecls('w')))
                                tcPr.append(shd)
                                for p_cell in cell.paragraphs:
                                    for run in p_cell.runs:
                                        run.font.color.rgb = RGBColor(255, 255, 255)
                                        run.bold = True
                            else:
                                if i % 2 == 0:
                                    shd = parse_xml(r'<w:shd {} w:fill="F2F2F2"/>'.format(nsdecls('w')))
                                    tcPr.append(shd)
                else:
                    p_sem = doc.add_paragraph("[Nenhum EPI registrado]")
                    p_sem.paragraph_format.line_spacing = 1.5
                    p_sem.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p_sem.runs[0].font.name = 'Abadi'
                    p_sem.runs[0].font.size = Pt(11)

                adicionar_linha_vazia()
                add_topic_block(doc, "Análise Crítica da Eficácia dos EPIs", p.get('analise_epis_critica', ''))

                adicionar_titulo("7. CONCLUSÃO TÉCNICA (LTCAT & DADOS PARA O PPP)", level=2)
                p_conc = doc.add_paragraph()
                p_conc.paragraph_format.line_spacing = 1.5
                p_conc.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r_c = p_conc.add_run("Conclui-se que as atividades desenvolvidas pelo segurado expuseram-no de forma habitual e permanente aos agentes nocivos acima descritos, preenchendo os requisitos legais para o reconhecimento do tempo de serviço especial.")
                r_c.font.name = 'Abadi'
                r_c.font.size = Pt(11)

            else:
                adicionar_titulo("1. IDENTIFICAÇÃO DO PROCESSO", level=2)
                dados_ident = [
                    ("Número do Processo", p.get('processo_num', '')), ("Órgão Julgador / Vara", p.get('orgao_julgador', '')),
                    ("Data de Autuação (Ajuizamento)", p.get('data_autuacao', '')), ("Valor da Causa", p.get('valor_causa', '')),
                    ("Rito Processual", p.get('rito_processual', ''))
                ]
                t_id = doc.add_table(rows=len(dados_ident) + 1, cols=2)
                definir_largura_tabela_100(t_id)
                t_id.rows[0].cells[0].text = "Parâmetro"
                t_id.rows[0].cells[1].text = "Descrição"
                for idx, (k, v) in enumerate(dados_ident, start=1):
                    t_id.rows[idx].cells[0].text = k
                    t_id.rows[idx].cells[1].text = v or "[Informação não localizada]"

                for i, row in enumerate(t_id.rows):
                    for cell in row.cells:
                        tcPr = cell._tc.get_or_add_tcPr()
                        for p_cell in cell.paragraphs:
                            p_cell.paragraph_format.line_spacing = 1.15
                            for run in p_cell.runs:
                                run.font.name = 'Abadi'
                                run.font.size = Pt(9)
                        if i == 0:
                            shd = parse_xml(r'<w:shd {} w:fill="1B365D"/>'.format(nsdecls('w')))
                            tcPr.append(shd)
                            for p_cell in cell.paragraphs:
                                for run in p_cell.runs:
                                    run.font.color.rgb = RGBColor(255, 255, 255)
                                    run.bold = True
                        else:
                            if i % 2 == 0:
                                shd = parse_xml(r'<w:shd {} w:fill="F2F2F2"/>'.format(nsdecls('w')))
                                tcPr.append(shd)
                adicionar_linha_vazia()

                adicionar_titulo("2. QUALIFICAÇÃO DAS PARTES", level=2)
                add_bullet_inline(doc, "Reclamante (Autor/Autora)", f"{p.get('reclamante_nome', '')} (CPF: {p.get('reclamante_cpf', '')})")
                add_bullet_inline(doc, "Advogados", p.get('reclamante_adv', ''))
                add_bullet_inline(doc, "Reclamada (Ré/Empresa)", f"{p.get('reclamada_nome', '')} (CNPJ: {p.get('reclamada_cnpj', '')})")
                add_bullet_inline(doc, "Advogados", p.get('reclamada_adv', ''))

                adicionar_titulo("3. DADOS DO CONTRATO DE TRABALHO", level=2)
                add_bullet_inline(doc, "Data de Admissão", p.get('data_admissao', ''))
                add_bullet_inline(doc, "Status do Contrato", p.get('status_contrato', ''))
                add_bullet_inline(doc, "Período Imprescrito", p.get('periodo_imprescrito', ''))
                add_bullet_inline(doc, "Cargo(s) / Função(ões)", p.get('cargos', ''))
                add_bullet_inline(doc, "Setor / Lotação / Local", p.get('setor', ''))
                add_bullet_inline(doc, "Última Remuneração", p.get('ultima_remuneracao', ''))

                adicionar_titulo("4. SÍNTESE TÉCNICA DA PETIÇÃO INICIAL", level=2)
                add_bullet_inline(doc, "Objeto da Perícia", p.get('objeto_pericia', ''))
                add_topic_block(doc, "Atividades Descritas", p.get('atividades_inicial', ''))
                add_topic_block(doc, "Agentes Nocivos / Riscos Alegados", p.get('agentes_alegados', ''))
                add_topic_block(doc, "Pedidos Técnicos", p.get('pedidos_tecnicos', ''))

                adicionar_titulo("5. SÍNTESE TÉCNICA DA CONTESTAÇÃO", level=2)
                add_topic_block(doc, "Preliminares Periciais", p.get('preliminares_periciais', ''))
                add_topic_block(doc, "Defesa de Mérito (SST)", p.get('defesa_merito_sst', ''))

                adicionar_titulo("6. STATUS E DADOS DA VISTORIA", level=2)
                add_bullet_inline(doc, "Fase Processual Atual", p.get('fase_processual', ''))
                add_bullet_inline(doc, "Data da Vistoria", p.get('campo_data', ''))
                add_bullet_inline(doc, "Horário", p.get('campo_horario', ''))
                add_bullet_inline(doc, "Local / Endereço", p.get('local_diligencia', ''))

                adicionar_titulo("7. ANÁLISE DOS DOCUMENTOS DE SST NOS AUTOS", level=2)
                add_topic_block(doc, "LTCAT", p.get('doc_ltcat', ''))
                add_topic_block(doc, "Laudo de Insalubridade / Periculosidade", p.get('doc_laudo', ''))
                add_topic_block(doc, "PPP (Perfil Profissiográfico Previdenciário)", p.get('doc_ppp', ''))
                add_topic_block(doc, "PGR / PPRA / PCMAT", p.get('doc_pgr', ''))
                add_topic_block(doc, "Ordens de Serviço (OS) / Treinamentos", p.get('doc_os', ''))
                add_topic_block(doc, "ASOs / PCMSO", p.get('doc_asos', ''))
                add_topic_block(doc, "Outros Documentos Relevantes", p.get('doc_outros', ''))

                adicionar_titulo("8. FORNECIMENTO DE EQUIPAMENTOS DE PROTEÇÃO (EPIs)", level=2)
                quadro_epis = p.get('quadro_epis', [])
                if quadro_epis:
                    t_epi = doc.add_table(rows=len(quadro_epis) + 1, cols=4)
                    definir_largura_tabela_100(t_epi)
                    headers = ["Descrição do EPI", "C.A.", "Data de Entrega", "Observações"]
                    for h_idx, h_text in enumerate(headers): t_epi.rows[0].cells[h_idx].text = h_text
                    
                    for r_idx, epi in enumerate(quadro_epis, start=1):
                        t_epi.rows[r_idx].cells[0].text = epi.get('descricao', '')
                        t_epi.rows[r_idx].cells[1].text = epi.get('ca', '')
                        t_epi.rows[r_idx].cells[2].text = epi.get('data_entrega', '')
                        t_epi.rows[r_idx].cells[3].text = epi.get('obs', '')

                    for i, row in enumerate(t_epi.rows):
                        for cell in row.cells:
                            tcPr = cell._tc.get_or_add_tcPr()
                            for p_cell in cell.paragraphs:
                                p_cell.paragraph_format.line_spacing = 1.15
                                for run in p_cell.runs:
                                    run.font.name = 'Abadi'
                                    run.font.size = Pt(8.5)
                            if i == 0:
                                shd = parse_xml(r'<w:shd {} w:fill="1B365D"/>'.format(nsdecls('w')))
                                tcPr.append(shd)
                                for p_cell in cell.paragraphs:
                                    for run in p_cell.runs:
                                        run.font.color.rgb = RGBColor(255, 255, 255)
                                        run.bold = True
                            else:
                                if i % 2 == 0:
                                    shd = parse_xml(r'<w:shd {} w:fill="F2F2F2"/>'.format(nsdecls('w')))
                                    tcPr.append(shd)
                else:
                    p_sem = doc.add_paragraph("[Nenhum EPI cadastrado para este processo]")
                    p_sem.paragraph_format.line_spacing = 1.5
                    p_sem.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p_sem.runs[0].font.name = 'Abadi'
                    p_sem.runs[0].font.size = Pt(11)

                adicionar_linha_vazia()
                add_topic_block(doc, "Síntese e Análise Crítica de EPIs", p.get('analise_epis_critica', ''))

                adicionar_titulo("9. QUESITOS FORMULADOS PARA A PERÍCIA", level=2)
                add_topic_block(doc, "9.1. Quesitos do Juízo", p.get('quesitos_juizo', ''))
                add_topic_block(doc, "9.2. Quesitos do Reclamante", p.get('quesitos_autor', ''))
                add_topic_block(doc, "9.3. Quesitos da Reclamada", p.get('quesitos_reu', ''))

                adicionar_titulo("10. LEVANTAMENTOS DE CAMPO (DILIGÊNCIA & EVIDÊNCIAS)", level=2)
                add_topic_block(doc, "Pessoas Presentes na Vistoria", p.get('presentes_pericia', ''))
                add_topic_block(doc, "Informações prestadas pelo Autor", p.get('campo_declaracoes_autor', ''))
                add_topic_block(doc, "Informações prestadas pelo Ré", p.get('campo_declaracoes_reu', ''))
                add_topic_block(doc, "Medições Realizadas", p.get('campo_medicoes', ''))

            if p.get("campo_fotos"):
                adicionar_titulo("REGISTROS FOTOGRÁFICOS DE CAMPO", level=3)
                for idx, foto_dict in enumerate(p["campo_fotos"]):
                    if "base64" in foto_dict:
                        try:
                            p_img = doc.add_paragraph()
                            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            img_stream = io.BytesIO(base64.b64decode(foto_dict["base64"]))
                            p_img.add_run().add_picture(img_stream, width=Inches(4.5))
                            
                            texto_legenda = foto_dict.get("legenda", "Registro fotográfico.")
                            coords_gps = foto_dict.get("gps", "")
                            if coords_gps: texto_legenda += f" ({coords_gps})"
                            
                            p_leg = doc.add_paragraph(f"Figura {idx+1}: {texto_legenda}")
                            p_leg.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            p_leg.paragraph_format.line_spacing = 1.5
                            for run in p_leg.runs:
                                run.font.name = 'Abadi'
                                run.font.size = Pt(9)
                                run.italic = True
                            adicionar_linha_vazia()
                        except Exception as e:
                            pass

            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            st.toast("✅ Documento Word Finalizado!", icon="📄")
            st.download_button(
                label="📥 Baixar Documento Oficial (.docx)",
                data=buffer,
                file_name=f"Documento_Oficial_{p.get('reclamante_nome','Caso').replace(' ','_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
