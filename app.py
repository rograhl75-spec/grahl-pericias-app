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
import hashlib
import unicodedata
from datetime import datetime

DB_FILE = "processos_db.json"
LOGO_FILE = "logo dourado grahl consultoria.png"
FOTOS_DIR = os.path.abspath("fotos_uploads")

os.makedirs(FOTOS_DIR, exist_ok=True)

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
    if not texto or not isinstance(texto, str):
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

def calcula_altura(texto, min_h):
    if not texto: 
        return min_h
    texto_str = str(texto)
    linhas_quebradas = texto_str.count('\n') + 1
    caracteres_extras_wrap = sum([len(linha) // 80 for linha in texto_str.split('\n')])
    calc = (linhas_quebradas + caracteres_extras_wrap) * 24 + 40
    return max(min_h, calc)

def parse_pre_relatorio(doc):
    dados = {}
    texto_paragrafos = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    texto = texto_paragrafos.replace("**", "").replace("*", "")
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]

    field_matchers = [
        ("número do processo", "processo_num"),
        ("órgão julgador", "orgao_julgador"),
        ("data de autuação", "data_autuacao"),
        ("ajuizamento", "data_autuacao"),
        ("valor da causa", "valor_causa"),
        ("rito processual", "rito_processual"),
        ("reclamante (autor/autora)", "reclamante_nome"),
        ("nome do segurado", "reclamante_nome"),
        ("reclamante", "reclamante_nome"),
        ("reclamada (ré/empresa)", "reclamada_nome"),
        ("empresa / tomador", "reclamada_nome"),
        ("reclamada", "reclamada_nome"),
        ("data de admissão", "data_admissao"),
        ("status do contrato", "status_contrato"),
        ("período imprescrito", "periodo_imprescrito"),
        ("cargo(s) / função(ões)", "cargos"),
        ("profissão / cargo", "profissao_cargo"),
        ("setor / lotação", "setor"),
        ("última remuneração", "ultima_remuneracao"),
        ("objeto da perícia", "objeto_pericia"),
        ("atividades descritas", "atividades_inicial"),
        ("atividades típicas", "relato_inicial"),
        ("agentes nocivos", "agentes_alegados"),
        ("pedidos técnicos", "pedidos_tecnicos"),
        ("preliminares periciais", "preliminares_periciais"),
        ("defesa de mérito", "defesa_merito_sst"),
        ("fase processual", "fase_processual"),
        ("data da vistoria", "campo_data"),
        ("horário", "campo_horario"),
        ("local / endereço", "local_diligencia"),
        ("ltcat", "doc_ltcat"),
        ("laudo de insalubridade", "doc_laudo"),
        ("ppp", "doc_ppp"),
        ("pgr / ppra", "doc_pgr"),
        ("ordens de serviço", "doc_os"),
        ("asos / pcmsos", "doc_asos"),
        ("outros documentos", "doc_outros"),
        ("9.1. quesitos do juízo", "quesitos_juizo"),
        ("quesitos do juízo", "quesitos_juizo"),
        ("9.2. quesitos do reclamante", "quesitos_autor"),
        ("quesitos do reclamante", "quesitos_autor"),
        ("quesitos do autor", "quesitos_autor"),
        ("9.3. quesitos da reclamada", "quesitos_reu"),
        ("quesitos da reclamada", "quesitos_reu"),
        ("quesitos da ré", "quesitos_reu")
    ]
    sorted_matchers = sorted(field_matchers, key=lambda x: len(x[0]), reverse=True)

    current_key = None
    current_buffer = []
    last_entity = None

    def save_current():
        if current_key and current_buffer:
            val = "\n".join(current_buffer).strip()
            if val and "[informação/documento não localizado" not in val.lower():
                dados[current_key] = val

    for linha in linhas:
        if re.match(r'^\d+(\.\d*)*[\s\.\-]+[A-ZÀ-Ú]', linha) and ":" not in linha:
            save_current()
            current_key = None
            current_buffer = []
            continue

        matched = False
        if ":" in linha:
            parts = linha.split(":", 1)
            prefix = parts[0].strip().lower()
            rest = parts[1].strip()

            if "advogado" in prefix:
                save_current()
                if last_entity == "reclamante":
                    dados["reclamante_adv"] = rest
                elif last_entity == "reclamada":
                    dados["reclamada_adv"] = rest
                else:
                    if not dados.get("reclamante_adv"):
                        dados["reclamante_adv"] = rest
                    else:
                        dados["reclamada_adv"] = rest
                current_key = None
                current_buffer = []
                matched = True
                continue

            matched_key = None
            for kw, d_key in sorted_matchers:
                if kw in prefix:
                    matched_key = d_key
                    break

            if matched_key:
                save_current()
                current_key = matched_key
                current_buffer = [rest] if rest else []
                matched = True

                if "reclamante" in matched_key or "autor" in prefix or "segurado" in prefix:
                    last_entity = "reclamante"
                    if rest:
                        m_cpf = re.search(r"(?:CPF/NIT|CPF|NIT|PIS|CPF):\s*([\d\.-]+)", rest, re.IGNORECASE)
                        if m_cpf:
                            dados["reclamante_cpf"] = m_cpf.group(1)
                            dados["reclamante_nome"] = re.sub(r"\((?:CPF/NIT|CPF|NIT|PIS|CPF):.*?\)", "", rest, flags=re.IGNORECASE).strip()
                        else:
                            dados["reclamante_nome"] = rest
                elif "reclamada" in matched_key or ("empresa" in prefix and "reclamada" not in matched_key) or "ré" in prefix or "tomador" in prefix:
                    last_entity = "reclamada"
                    if rest:
                        m_cnpj = re.search(r"CNPJ:\s*([\d\.\-\/]+)", rest, re.IGNORECASE)
                        if m_cnpj:
                            dados["reclamada_cnpj"] = m_cnpj.group(1)
                            dados["reclamada_nome"] = re.sub(r"\(CNPJ:.*?\)", "", rest, flags=re.IGNORECASE).strip()
                        else:
                            dados["reclamada_nome"] = rest

        if not matched and current_key:
            if linha:
                current_buffer.append(linha)

    save_current()

    epis_extraidos = []
    for table in doc.tables:
        if len(table.rows) > 0 and len(table.columns) >= 4:
            hdr = [cell.text.lower() for cell in table.rows[0].cells]
            if any("descri" in h or "epi" in h for h in hdr) and any("c.a" in h or "ca" in h or "cert" in h for h in hdr):
                for row in table.rows[1:]:
                    cells = row.cells
                    desc = cells[0].text.strip() if len(cells) > 0 else ""
                    ca = cells[1].text.strip() if len(cells) > 1 else ""
                    data = cells[2].text.strip() if len(cells) > 2 else ""
                    obs = cells[3].text.strip() if len(cells) > 3 else ""
                    
                    desc = desc.replace("**", "").replace("*", "")
                    if desc and "[extrair" not in desc.lower() and "---" not in desc and "informação" not in desc.lower():
                        epis_extraidos.append({
                            "descricao": desc,
                            "ca": ca,
                            "data_entrega": data,
                            "obs": obs
                        })
                break

    if epis_extraidos:
        dados["quadro_epis"] = epis_extraidos

    return dados

def carregar_dados():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                dados = json.load(f)
                dados_padronizados = {}
                for k, v in dados.items():
                    novo_k = k
                    if k.startswith("Processo_") or k.startswith("Extra_"):
                        num = re.findall(r'\d+', k)
                        if num:
                            novo_k = f"Proc_{int(num[0]):02d}"
                    
                    for k_padrao, v_padrao in dados_padrao.items():
                        if k_padrao not in v:
                            v[k_padrao] = v_padrao
                    dados_padronizados[novo_k] = v
                return dados_padronizados
            except:
                return {}
    return {}

def salvar_dados(dados):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def gerar_proximo_id(db):
    numeros = []
    for k in db.keys():
        if k.startswith("Proc_"):
            try:
                num = int(k.split("_")[1])
                numeros.append(num)
            except:
                pass
    proximo = max(numeros) + 1 if numeros else 1
    return f"Proc_{proximo:02d}"

icon_config = LOGO_FILE if os.path.exists(LOGO_FILE) else "🛡️"
st.set_page_config(page_title="Grahl Consultoria - Perícias e Laudos Previdenciários", page_icon=icon_config, layout="wide")

if "parsed_data" not in st.session_state:
    st.session_state.parsed_data = {}
if "gps_field_main" not in st.session_state:
    st.session_state.gps_field_main = ""
if "confirmar_exclusao_dupla" not in st.session_state:
    st.session_state.confirmar_exclusao_dupla = False
if "menu_opcao" not in st.session_state:
    st.session_state.menu_opcao = "➕ Novo Processo / Caso"

if "gps" in st.query_params:
    st.session_state.gps_field_main = st.query_params["gps"]
    st.query_params.clear()

st.markdown("""
    <style>
    .stApp {
        background-color: #f8fafc;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    section[data-testid="stSidebar"] {
        background-color: #1B365D;
        padding-top: 1.5rem;
    }
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] label {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] .stSelectbox label p {
        color: #E2E8F0 !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }
    /* Estilização dos botões do Painel de Controle no Sidebar */
    section[data-testid="stSidebar"] .stButton button {
        width: 100% !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        color: white !important;
        border: 2px solid rgba(255,255,255,0.25) !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2) !important;
        margin-bottom: 10px !important;
        text-align: left !important;
        transition: all 0.2s ease;
    }
    section[data-testid="stSidebar"] .stButton:nth-of-type(1) button { background-color: #2563EB !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(2) button { background-color: #0D9488 !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(3) button { background-color: #16A34A !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(4) button { background-color: #DC2626 !important; }
    section[data-testid="stSidebar"] .stButton:nth-of-type(5) button { background-color: #9333EA !important; }

    section[data-testid="stSidebar"] .stButton button:hover {
        filter: brightness(1.15) !important;
        transform: translateY(-2px);
    }
    div.block-container {
        padding-top: 2rem;
    }
    h1 {
        color: #1B365D !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }
    h2, h3 {
        color: #1B365D !important;
        font-weight: 700 !important;
    }
    label, .stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label {
        color: #1B365D !important;
        font-weight: 700 !important;
        font-size: 15px !important;
    }
    input, textarea {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        font-size: 16px !important;
    }
    
    /* Configuração de Auto-resize CSS para textareas */
    textarea {
        field-sizing: content !important;
    }
    
    .stButton button {
        background-color: #1B365D !important;
        color: white !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.2rem;
        border: none;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
    }
    .stButton button:hover {
        background-color: #2D4A7C !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #E2E8F0;
        border-radius: 8px 8px 0px 0px;
        color: #1B365D;
        font-weight: 700;
        padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1B365D !important;
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

db_processos = carregar_dados()

col_logo, col_titulo = st.columns([1, 6])
with col_logo:
    logo_encontrado = None
    if os.path.exists(LOGO_FILE):
        logo_encontrado = LOGO_FILE
    else:
        for f in os.listdir("."):
            if "logo" in f.lower() and f.lower().endswith((".jpg", ".png", ".jpeg")):
                logo_encontrado = f
                break
    if logo_encontrado:
        st.image(logo_encontrado, width=140)
    else:
        st.markdown("### 🛡️ **GRAHL**")
        st.caption("Engenharia e Perícias")

with col_titulo:
    st.markdown("<h1 style='margin:0; font-size: 1.7rem;'>Gestão Pericial Trabalhista & Laudos Previdenciários</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748B; margin:0; font-size: 1rem; font-weight: 500;'>Assistência Técnica, Perícias Judiciais e Laudos Extrajudiciais (LTCAT + PPP).</p>", unsafe_allow_html=True)

st.markdown("<hr style='margin-top: 1rem; margin-bottom: 1.5rem; border: none; height: 1px; background-color: #CBD5E1;'>", unsafe_allow_html=True)

# Painel de Controle no Sidebar
st.sidebar.markdown("<h2 style='color: #FFFFFF; font-size: 1.3rem; margin-bottom: 1rem;'>📁 Painel de Controle</h2>", unsafe_allow_html=True)

acoes_menu = [
    "➕ Novo Processo / Caso", 
    "✏️ Dados, Escritório & SST", 
    "🚜 Diligência de Campo & Fotos", 
    "🗑️ Excluir Processo", 
    "📄 Gerar Documento Word Final"
]

for acao in acoes_menu:
    if st.sidebar.button(acao, use_container_width=True):
        st.session_state.menu_opcao = acao
        st.rerun()

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
            
            if (termo_limpo in id_norm or 
                termo_limpo in proc_num_norm or 
                termo_limpo in reclamada_norm or 
                termo_limpo in reclamante_norm):
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
        if empresa:
            label += f" x {empresa}"
        elif num_p:
            label += f" ({num_p})"
        mapa_opcoes[label] = k

    label_selecionado = st.sidebar.selectbox(
        "Processo / Caso Selecionado:",
        options=list(mapa_opcoes.keys())
    )
    processo_id_selecionado = mapa_opcoes.get(label_selecionado, "Nenhum caso cadastrado")

    # MÁGICA 1: ROTEAMENTO AUTOMÁTICO E LIMPEZA DE ESTADO FANTASMA
    if "processo_atual_selecionado" not in st.session_state:
        st.session_state.processo_atual_selecionado = processo_id_selecionado

    if processo_id_selecionado != st.session_state.processo_atual_selecionado:
        st.session_state.processo_atual_selecionado = processo_id_selecionado
        # Se trocar de processo, direciona para a aba principal
        st.session_state.menu_opcao = "✏️ Dados, Escritório & SST"
        st.rerun()

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
    arquivo_importado = st.file_uploader("Selecione o arquivo Word para preenchimento automático", type=["docx"])
    
    if arquivo_importado is not None:
        try:
            doc_ext = Document(arquivo_importado)
            dados_extraidos = parse_pre_relatorio(doc_ext)
            st.session_state.parsed_data = dados_extraidos
            st.success("Documento lido e mapeado com sucesso!")
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

        p_num = st.text_input(lbl_num, value=def_num)
        p_nome = st.text_input(lbl_nome, value=parsed.get("reclamante_nome", ""))
        p_empresa = st.text_input(lbl_emp, value=parsed.get("reclamada_nome", ""))

        st.markdown("<br>", unsafe_allow_html=True)
        submitted_novo = st.form_submit_button("Criar Caso Completo")
        if submitted_novo:
            p_novo = dados_padrao.copy()
            if parsed:
                for k, v in parsed.items():
                    if v:
                        p_novo[k] = v
            
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
            
            db_processos[proximo_id] = p_novo
            salvar_dados(db_processos)
            st.session_state.parsed_data = {}
            st.session_state.processo_atual_selecionado = proximo_id
            st.toast(f"✅ Caso {proximo_id} criado com sucesso!", icon="💾")
            st.rerun()

elif opcao == "✏️ Dados, Escritório & SST":
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Cadastre ou selecione um caso no menu lateral para começar.")
    else:
        p_atual = db_processos[processo_id_selecionado]
        is_prev = "Previdenciário" in p_atual.get("modulo_atuacao", "")
        
        st.markdown(f"<div style='background-color: #E2E8F0; padding: 10px 15px; border-radius: 8px; margin-bottom: 20px;'><b style='color: #1B365D;'>Caso Ativo:</b> {processo_id_selecionado} &nbsp;|&nbsp; <b style='color: #1B365D;'>Módulo:</b> {p_atual.get('modulo_atuacao', '')}</div>", unsafe_allow_html=True)
        
        if is_prev:
            tab1, tab2, tab3, tab4 = st.tabs([
                "1️⃣ Segurado & Tomador", 
                "2️⃣ APR-HO & Extemporaneidade (IN 128)", 
                "3️⃣ Planilha de EPIs & Tema 555", 
                "4️⃣ Metodologia & Enquadramento"
            ])
            
            with tab1:
                st.markdown("### 1. Identificação do Segurado e da Empresa")
                # MÁGICA 2: A CHAVE DO FORMULÁRIO MUDA PARA CADA PROCESSO
                with st.form(f"form_prev_1_{processo_id_selecionado}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        p_atual["reclamante_nome"] = st.text_input("Nome do Segurado", value=p_atual.get("reclamante_nome", ""), key=f"p1_rec_nome_{processo_id_selecionado}")
                        p_atual["reclamante_cpf"] = st.text_input("CPF / NIT / PIS", value=p_atual.get("reclamante_cpf", ""), key=f"p1_rec_cpf_{processo_id_selecionado}")
                        p_atual["segurado_nascimento"] = st.text_input("Data de Nascimento", value=p_atual.get("segurado_nascimento", ""), key=f"p1_nasc_{processo_id_selecionado}")
                        p_atual["profissao_cargo"] = st.text_input("Profissão / Cargo Avaliado", value=p_atual.get("profissao_cargo", ""), key=f"p1_prof_{processo_id_selecionado}")
                    with col2:
                        p_atual["reclamada_nome"] = st.text_input("Razão Social da Empresa / Tomador", value=p_atual.get("reclamada_nome", ""), key=f"p1_emp_{processo_id_selecionado}")
                        p_atual["reclamada_cnpj"] = st.text_input("CNPJ da Empresa", value=p_atual.get("reclamada_cnpj", ""), key=f"p1_cnpj_{processo_id_selecionado}")
                        p_atual["setor"] = st.text_input("Setor / Lotação / Local", value=p_atual.get("setor", ""), key=f"p1_setor_{processo_id_selecionado}")
                        p_atual["data_admissao"] = st.text_input("Período de Trabalho (Admissão - Demissão)", value=p_atual.get("data_admissao", ""), key=f"p1_adm_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    val_relato = p_atual.get("relato_inicial", "")
                    p_atual["relato_inicial"] = st.text_area("Relato Inicial / Atividades Desenvolvidas pelo Segurado", value=val_relato, height=calcula_altura(val_relato, 120), key=f"p1_rel_{processo_id_selecionado}")
                    
                    if st.form_submit_button("💾 Salvar Dados do Segurado"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Dados do Segurado salvos!", icon="💾")

            with tab2:
                st.markdown("### 2. Análise Preliminar de Riscos (APR-HO) & Extemporaneidade (Art. 279 da IN 128/2022)")
                with st.form(f"form_prev_2_{processo_id_selecionado}"):
                    v_fis = p_atual.get("apr_fisicos", "")
                    v_qui = p_atual.get("apr_quimicos", "")
                    v_bio = p_atual.get("apr_biologicos", "")
                    p_atual["apr_fisicos"] = st.text_area("Agentes Físicos Presumidos (Ex: Ruído NHO-01, Calor IBUTG)", value=v_fis, height=calcula_altura(v_fis, 80), key=f"p2_fis_{processo_id_selecionado}")
                    p_atual["apr_quimicos"] = st.text_area("Agentes Químicos (Ex: Hidrocarbonetos, Solventes, LINACH)", value=v_qui, height=calcula_altura(v_qui, 80), key=f"p2_qui_{processo_id_selecionado}")
                    p_atual["apr_biologicos"] = st.text_area("Agentes Biológicos (Se aplicável)", value=v_bio, height=calcula_altura(v_bio, 80), key=f"p2_bio_{processo_id_selecionado}")
                    
                    st.markdown("#### Avaliação de Extemporaneidade (Art. 279, IN 128/2022):")
                    p_atual["extemp_layout"] = st.checkbox("Houve mudança no layout ou organização do ambiente?", value=p_atual.get("extemp_layout", False), key=f"p2_lay_{processo_id_selecionado}")
                    p_atual["extemp_maquinas"] = st.checkbox("Houve substituição de máquinas ou equipamentos?", value=p_atual.get("extemp_maquinas", False), key=f"p2_maq_{processo_id_selecionado}")
                    p_atual["extemp_epc"] = st.checkbox("Houve alteração nas tecnologias de proteção coletiva (EPC)?", value=p_atual.get("extemp_epc", False), key=f"p2_epc_{processo_id_selecionado}")
                    
                    v_ext = p_atual.get("extemp_justificativa", "")
                    p_atual["extemp_justificativa"] = st.text_area("Fundamentação Técnica da Equivalência (Extemporaneidade)", value=v_ext, height=calcula_altura(v_ext, 100), key=f"p2_just_{processo_id_selecionado}")

                    if st.form_submit_button("💾 Salvar APR e Extemporaneidade"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ APR salva com sucesso!", icon="💾")

            with tab3:
                st.markdown("### 3. Planilha de EPIs & Eficácia (Tema 555 STF)")
                st.info("💡 Cadastre os EPIs utilizados, indicando o C.A., periodicidade e eficácia conforme o Tema 555 do STF.")
                
                epis_atuais = p_atual.get("quadro_epis", [])
                df_epis = pd.DataFrame(epis_atuais, columns=["descricao", "ca", "data_entrega", "obs"])
                
                edited_df = st.data_editor(
                    df_epis,
                    column_config={
                        "descricao": st.column_config.TextColumn("Descrição do EPI", width="large", required=True),
                        "ca": st.column_config.TextColumn("C.A.", width="small"),
                        "data_entrega": st.column_config.TextColumn("Periodicidade / Entrega", width="medium"),
                        "obs": st.column_config.TextColumn("Eficácia / Higienização / Tema 555", width="large"),
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    height=300,
                    key=f"ed_epi_prev_{processo_id_selecionado}"
                )

                if st.button("💾 Salvar Tabela de EPIs Previdenciários", key=f"btn_epi_prev_{processo_id_selecionado}"):
                    df_clean = edited_df.fillna("")
                    df_clean = df_clean[df_clean["descricao"].astype(str).str.strip() != ""]
                    p_atual["quadro_epis"] = df_clean.to_dict('records')
                    db_processos[processo_id_selecionado] = p_atual
                    salvar_dados(db_processos)
                    st.toast("✅ Planilha de EPIs salva!", icon="💾")

                st.markdown("<br>", unsafe_allow_html=True)
                with st.form(f"form_prev_epi_{processo_id_selecionado}"):
                    v_epi = p_atual.get("analise_epis_critica", "")
                    p_atual["analise_epis_critica"] = st.text_area("Análise Crítica da Eficácia dos EPIs (Tema 555 STF / Súmula 9 TNU)", value=v_epi, height=calcula_altura(v_epi, 120), key=f"p3_an_epi_{processo_id_selecionado}")
                    if st.form_submit_button("💾 Salvar Análise Crítica"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Análise Crítica salva!", icon="💾")

            with tab4:
                st.markdown("### 4. Metodologia (NHO-01 Fundacentro) & Enquadramento Legal")
                with st.form(f"form_prev_4_{processo_id_selecionado}"):
                    p_atual["enquadramento_legal_prev"] = st.text_input("Enquadramento Legal (Decreto 3.048/99 - Anexo IV)", value=p_atual.get("enquadramento_legal_prev", ""), key=f"p4_enq_{processo_id_selecionado}")
                    v_met = p_atual.get("doc_ltcat", "")
                    p_atual["doc_ltcat"] = st.text_area("Metodologia de Avaliação Ambiental (Ex: Ruído NHO-01, q=5, NEN, Critérios Químicos LINACH)", value=v_met, height=calcula_altura(v_met, 150), key=f"p4_met_{processo_id_selecionado}")
                    
                    if st.form_submit_button("💾 Salvar Metodologia"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Metodologia salva!", icon="💾")

        else:
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "1️⃣ Identificação & Partes", 
                "2️⃣ Contrato & Sínteses", 
                "3️⃣ SST & Documentos", 
                "4️⃣ Planilha de EPIs", 
                "5️⃣ Quesitos Literais"
            ])
            
            with tab1:
                st.markdown("### 1. Papel Profissional, Tipos de Perícia & Identificação")
                with st.form(f"form_sec1_{processo_id_selecionado}"):
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        idx_papel = ["Perito do Juízo", "Assistente Técnico da Reclamante", "Assistente Técnico da Reclamada"].index(p_atual.get("papel_profissional", "Assistente Técnico da Reclamada")) if p_atual.get("papel_profissional") in ["Perito do Juízo", "Assistente Técnico da Reclamante", "Assistente Técnico da Reclamada"] else 2
                        p_atual["papel_profissional"] = st.selectbox("Meu Papel no Processo", ["Perito do Juízo", "Assistente Técnico da Reclamante", "Assistente Técnico da Reclamada"], index=idx_papel, key=f"s1_papel_{processo_id_selecionado}")
                    with col_p2:
                        p_atual["tipos_pericia"] = st.multiselect("Tipos de Perícia Envolvidos", ["Insalubridade (NR-15)", "Periculosidade (NR-16)", "Aposentadoria Especial (PPP/LTCAT)"], default=p_atual.get("tipos_pericia", ["Insalubridade (NR-15)"]), key=f"s1_tipos_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        p_atual["processo_num"] = st.text_input("Número do Processo (CNJ)", value=p_atual.get("processo_num", ""), key=f"s1_num_{processo_id_selecionado}")
                        p_atual["orgao_julgador"] = st.text_input("Órgão Julgador / Vara", value=p_atual.get("orgao_julgador", ""), key=f"s1_org_{processo_id_selecionado}")
                        p_atual["data_autuacao"] = st.text_input("Data de Autuação (Ajuizamento)", value=p_atual.get("data_autuacao", ""), key=f"s1_dt_{processo_id_selecionado}")
                        p_atual["valor_causa"] = st.text_input("Valor da Causa", value=p_atual.get("valor_causa", ""), key=f"s1_val_{processo_id_selecionado}")
                        p_atual["rito_processual"] = st.text_input("Rito Processual", value=p_atual.get("rito_processual", ""), key=f"s1_rito_{processo_id_selecionado}")
                    with col2:
                        p_atual["reclamante_nome"] = st.text_input("Reclamante (Autor/Autora)", value=p_atual.get("reclamante_nome", ""), key=f"s1_rec_nome_{processo_id_selecionado}")
                        p_atual["reclamante_cpf"] = st.text_input("CPF do Reclamante", value=p_atual.get("reclamante_cpf", ""), key=f"s1_rec_cpf_{processo_id_selecionado}")
                        p_atual["reclamante_adv"] = st.text_input("Advogados do Reclamante (Nomes e OAB)", value=p_atual.get("reclamante_adv", ""), key=f"s1_rec_adv_{processo_id_selecionado}")
                        p_atual["reclamada_nome"] = st.text_input("Reclamada (Ré / Empresa)", value=p_atual.get("reclamada_nome", ""), key=f"s1_recd_nome_{processo_id_selecionado}")
                        p_atual["reclamada_cnpj"] = st.text_input("CNPJ da Reclamada", value=p_atual.get("reclamada_cnpj", ""), key=f"s1_recd_cnpj_{processo_id_selecionado}")
                        p_atual["reclamada_adv"] = st.text_input("Advogados da Reclamada (Nomes e OAB)", value=p_atual.get("reclamada_adv", ""), key=f"s1_recd_adv_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Salvar Papel, Identificação e Partes"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Identificação salva!", icon="💾")

            with tab2:
                st.markdown("### 3. Dados do Contrato & 4/5. Sínteses da Inicial e Defesa")
                with st.form(f"form_sec2_{processo_id_selecionado}"):
                    col3, col4 = st.columns(2)
                    with col3:
                        p_atual["data_admissao"] = st.text_input("Data de Admissão", value=p_atual.get("data_admissao", ""), key=f"s2_adm_{processo_id_selecionado}")
                        p_atual["status_contrato"] = st.text_input("Status do Contrato (Demissão / Ativo)", value=p_atual.get("status_contrato", ""), key=f"s2_st_{processo_id_selecionado}")
                        p_atual["periodo_imprescrito"] = st.text_input("Período Imprescrito (Alvo da Perícia)", value=p_atual.get("periodo_imprescrito", ""), key=f"s2_per_{processo_id_selecionado}")
                        p_atual["cargos"] = st.text_input("Cargo(s) / Função(ões)", value=p_atual.get("cargos", ""), key=f"s2_car_{processo_id_selecionado}")
                    with col4:
                        p_atual["setor"] = st.text_input("Setor / Lotação / Local", value=p_atual.get("setor", ""), key=f"s2_set_{processo_id_selecionado}")
                        p_atual["ultima_remuneracao"] = st.text_input("Última Remuneração", value=p_atual.get("ultima_remuneracao", ""), key=f"s2_rem_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    p_atual["objeto_pericia"] = st.text_input("Objeto de Análise / Perícia", value=p_atual.get("objeto_pericia", ""), key=f"s2_obj_{processo_id_selecionado}")
                    
                    v_ati = p_atual.get("atividades_inicial", "")
                    p_atual["atividades_inicial"] = st.text_area("Atividades Descritas na Inicial", value=v_ati, height=calcula_altura(v_ati, 100), key=f"s2_ati_{processo_id_selecionado}")
                    
                    v_age = p_atual.get("agentes_alegados", "")
                    p_atual["agentes_alegados"] = st.text_area("Agentes Nocivos / Riscos Alegados", value=v_age, height=calcula_altura(v_age, 100), key=f"s2_age_{processo_id_selecionado}")
                    
                    v_ped = p_atual.get("pedidos_tecnicos", "")
                    p_atual["pedidos_tecnicos"] = st.text_area("Pedidos Técnicos (Grau, Enquadramento, PPP)", value=v_ped, height=calcula_altura(v_ped, 100), key=f"s2_ped_{processo_id_selecionado}")
                    
                    v_pre = p_atual.get("preliminares_periciais", "")
                    p_atual["preliminares_periciais"] = st.text_area("Preliminares Periciais (Contestação)", value=v_pre, height=calcula_altura(v_pre, 100), key=f"s2_pre_{processo_id_selecionado}")
                    
                    v_def = p_atual.get("defesa_merito_sst", "")
                    p_atual["defesa_merito_sst"] = st.text_area("Defesa de Mérito SST (Contestação)", value=v_def, height=calcula_altura(v_def, 120), key=f"s2_def_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Salvar Contrato e Sínteses"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Contrato e Sínteses salvos!", icon="💾")

            with tab3:
                st.markdown("### 6. Vistoria & 7. Análise de Documentos de SST")
                with st.form(f"form_sec3_{processo_id_selecionado}"):
                    col5, col6, col7 = st.columns(3)
                    with col5:
                        p_atual["fase_processual"] = st.text_input("Fase Processual Atual", value=p_atual.get("fase_processual", ""), key=f"s3_fase_{processo_id_selecionado}")
                    with col6:
                        p_atual["campo_data"] = st.text_input("Data da Vistoria", value=p_atual.get("campo_data", ""), key=f"s3_dt_{processo_id_selecionado}")
                    with col7:
                        p_atual["campo_horario"] = st.text_input("Horário da Vistoria", value=p_atual.get("campo_horario", ""), key=f"s3_hr_{processo_id_selecionado}")
                    
                    p_atual["local_diligencia"] = st.text_input("Local / Endereço da Diligência", value=p_atual.get("local_diligencia", ""), key=f"s3_loc_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    v_ltc = p_atual.get("doc_ltcat", "")
                    p_atual["doc_ltcat"] = st.text_area("Análise do LTCAT", value=v_ltc, height=calcula_altura(v_ltc, 90), key=f"s3_ltc_{processo_id_selecionado}")
                    
                    v_lau = p_atual.get("doc_laudo", "")
                    p_atual["doc_laudo"] = st.text_area("Análise de Laudos Prévios / Paradigmas", value=v_lau, height=calcula_altura(v_lau, 90), key=f"s3_lau_{processo_id_selecionado}")
                    
                    v_ppp = p_atual.get("doc_ppp", "")
                    p_atual["doc_ppp"] = st.text_area("Análise do PPP (Agentes, Responsáveis, EPI)", value=v_ppp, height=calcula_altura(v_ppp, 90), key=f"s3_ppp_{processo_id_selecionado}")
                    
                    v_pgr = p_atual.get("doc_pgr", "")
                    p_atual["doc_pgr"] = st.text_area("Análise do PGR / PPRA / PCMAT", value=v_pgr, height=calcula_altura(v_pgr, 90), key=f"s3_pgr_{processo_id_selecionado}")
                    
                    v_dos = p_atual.get("doc_os", "")
                    p_atual["doc_os"] = st.text_area("Ordens de Serviço e Treinamentos", value=v_dos, height=calcula_altura(v_dos, 90), key=f"s3_os_{processo_id_selecionado}")
                    
                    v_aso = p_atual.get("doc_asos", "")
                    p_atual["doc_asos"] = st.text_area("ASOs / PCMSO (Aptidão e Riscos)", value=v_aso, height=calcula_altura(v_aso, 90), key=f"s3_aso_{processo_id_selecionado}")
                    
                    v_out = p_atual.get("doc_outros", "")
                    p_atual["doc_outros"] = st.text_area("Outros Documentos Relevantes (FISPQs, etc.)", value=v_out, height=calcula_altura(v_out, 90), key=f"s3_out_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Salvar Vistoria e Documentos SST"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Análises de Documentos salvas!", icon="💾")

            with tab4:
                st.markdown("### 8. Quadro de Fornecimento de EPIs & Análise Crítica")
                st.info("💡 **Tabela Inteligente (Estilo Excel):** Dê um duplo clique na célula para editar os itens. Para **Adicionar** um novo EPI, clique na linha com o símbolo '➕'. Para **Excluir**, selecione a linha e aperte 'Delete'.")
                
                epis_atuais = p_atual.get("quadro_epis", [])
                df_epis = pd.DataFrame(epis_atuais, columns=["descricao", "ca", "data_entrega", "obs"])
                
                edited_df = st.data_editor(
                    df_epis,
                    column_config={
                        "descricao": st.column_config.TextColumn("Descrição do EPI fornecido", width="large", required=True),
                        "ca": st.column_config.TextColumn("C.A.", width="small"),
                        "data_entrega": st.column_config.TextColumn("Data Entrega", width="medium"),
                        "obs": st.column_config.TextColumn("Observações", width="large"),
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    height=350,
                    key=f"ed_epi_trab_{processo_id_selecionado}"
                )

                if st.button("💾 Salvar Tabela de EPIs", key=f"btn_save_epi_t_{processo_id_selecionado}"):
                    df_clean = edited_df.fillna("")
                    df_clean = df_clean[df_clean["descricao"].astype(str).str.strip() != ""]
                    p_atual["quadro_epis"] = df_clean.to_dict('records')
                    db_processos[processo_id_selecionado] = p_atual
                    salvar_dados(db_processos)
                    st.toast("✅ Quadro de EPIs salvo!", icon="💾")

                st.markdown("<br>---<br>", unsafe_allow_html=True)

                with st.form(f"form_analise_epi_{processo_id_selecionado}"):
                    v_epi2 = p_atual.get("analise_epis_critica", "")
                    p_atual["analise_epis_critica"] = st.text_area("Síntese e Análise Crítica de EPIs", value=v_epi2, height=calcula_altura(v_epi2, 180), key=f"s4_an_{processo_id_selecionado}")
                    if st.form_submit_button("💾 Salvar Análise Crítica de EPIs"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Análise Crítica salva!", icon="💾")

            with tab5:
                st.markdown("### 9. Quesitos Formulados para a Perícia (Transcrição Literal)")
                with st.form(f"form_quesitos_{processo_id_selecionado}"):
                    v_q1 = p_atual.get("quesitos_juizo", "")
                    p_atual["quesitos_juizo"] = st.text_area("9.1. Quesitos do Juízo", value=v_q1, height=calcula_altura(v_q1, 150), key=f"s5_q1_{processo_id_selecionado}")
                    
                    v_q2 = p_atual.get("quesitos_autor", "")
                    p_atual["quesitos_autor"] = st.text_area("9.2. Quesitos do Reclamante (Autor/Autora)", value=v_q2, height=calcula_altura(v_q2, 250), key=f"s5_q2_{processo_id_selecionado}")
                    
                    v_q3 = p_atual.get("quesitos_reu", "")
                    p_atual["quesitos_reu"] = st.text_area("9.3. Quesitos da Reclamada (Ré / Empresa)", value=v_q3, height=calcula_altura(v_q3, 250), key=f"s5_q3_{processo_id_selecionado}")

                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Salvar Quesitos Literais"):
                        db_processos[processo_id_selecionado] = p_atual
                        salvar_dados(db_processos)
                        st.toast("✅ Quesitos salvos!", icon="💾")

elif opcao == "🚜 Diligência de Campo & Fotos":
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Cadastre ou selecione um caso no menu lateral.")
    else:
        p_atual = db_processos[processo_id_selecionado]
        is_prev = "Previdenciário" in p_atual.get("modulo_atuacao", "")
        st.markdown(f"<div style='background-color: #E2E8F0; padding: 10px 15px; border-radius: 8px; margin-bottom: 20px;'><b style='color: #1B365D;'>Caso Ativo:</b> {processo_id_selecionado} &nbsp;|&nbsp; <b style='color: #1B365D;'>Módulo:</b> {p_atual.get('modulo_atuacao', '')}</div>", unsafe_allow_html=True)

        st.markdown("### 🚜 Vistoria Pericial de Campo, Declarações & Evidências")
        with st.form(f"form_campo_{processo_id_selecionado}"):
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                p_atual["campo_data"] = st.text_input("Data da Vistoria", value=p_atual.get("campo_data", ""), key=f"cp_dt_{processo_id_selecionado}")
            with col_c2:
                p_atual["campo_horario"] = st.text_input("Horário da Vistoria", value=p_atual.get("campo_horario", ""), key=f"cp_hr_{processo_id_selecionado}")

            st.markdown("<br>", unsafe_allow_html=True)
            p_atual["local_diligencia"] = st.text_input("Endereço / Local da Diligência", value=p_atual.get("local_diligencia", ""), key=f"cp_loc_{processo_id_selecionado}")
            
            v_pres = p_atual.get("presentes_pericia", "")
            p_atual["presentes_pericia"] = st.text_area("Pessoas Presentes na Vistoria (Nome e Função)", value=v_pres, height=calcula_altura(v_pres, 80), key=f"cp_pres_{processo_id_selecionado}")
            
            v_ca = p_atual.get("campo_declaracoes_autor", "")
            p_atual["campo_declaracoes_autor"] = st.text_area("Informações prestadas pelo Segurado / Autor", value=v_ca, height=calcula_altura(v_ca, 120), key=f"cp_aut_{processo_id_selecionado}")
            
            v_cr = p_atual.get("campo_declaracoes_reu", "")
            p_atual["campo_declaracoes_reu"] = st.text_area("Informações prestadas pelo Empregador / Acompanhante", value=v_cr, height=calcula_altura(v_cr, 120), key=f"cp_reu_{processo_id_selecionado}")
            
            v_cm = p_atual.get("campo_medicoes", "")
            p_atual["campo_medicoes"] = st.text_area("Medições Realizadas em Campo (Ex: Sonometria NHO-01, IBUTG)", value=v_cm, height=calcula_altura(v_cm, 120), key=f"cp_med_{processo_id_selecionado}")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("💾 Salvar Textos de Campo"):
                db_processos[processo_id_selecionado] = p_atual
                salvar_dados(db_processos)
                st.toast("✅ Textos de campo salvos!", icon="💾")

        st.markdown("<br>---<br>", unsafe_allow_html=True)
        st.markdown("#### 📍 Captura Rápida de GPS (Híbrido: Satélite ou Rede)")
        
        gps_input_val = st.text_input("Coordenada GPS Atual (Sessão Ativa):", value=st.session_state.get("gps_field_main", ""), key=f"gps_input_{processo_id_selecionado}", placeholder="GPS_TARGET_FIELD")
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
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
                    });
                    
                    const photoInputs = window.parent.document.querySelectorAll('input[placeholder="GPS_FOTO"]');
                    photoInputs.forEach(input => {
                        if(!input.value || input.value === "") { 
                            let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, "value").set;
                            nativeInputValueSetter.call(input, coordStr);
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                }

                function getGPS() {
                    var st = document.getElementById("gps_status");
                    st.innerHTML = "Buscando satélites (isso pode levar alguns segundos)...";
                    if (navigator.geolocation) {
                        navigator.geolocation.getCurrentPosition(
                            function(position) {
                                var lat = position.coords.latitude.toFixed(6);
                                var lon = position.coords.longitude.toFixed(6);
                                var coordStr = lat + ", " + lon;
                                st.innerHTML = "✅ GPS Satélite Obtido! Inserido no sistema.";
                                injectGPS(coordStr);
                            },
                            function(error) {
                                st.innerHTML = "Satélite fraco. Tentando via rede 4G/Wi-Fi (rápido)...";
                                navigator.geolocation.getCurrentPosition(
                                    function(position) {
                                        var lat = position.coords.latitude.toFixed(6);
                                        var lon = position.coords.longitude.toFixed(6);
                                        var coordStr = lat + ", " + lon;
                                        st.innerHTML = "✅ GPS Rede Obtido! Inserido no sistema.";
                                        injectGPS(coordStr);
                                    },
                                    function(err2) {
                                        st.innerHTML = "❌ Erro de GPS. Ative a localização no tablet e dê permissão ao navegador.";
                                    },
                                    {timeout: 10000, enableHighAccuracy: false, maximumAge: 60000}
                                );
                            },
                            {timeout: 8000, enableHighAccuracy: true, maximumAge: 0}
                        );
                    } else {
                        st.innerHTML = "Geolocalização não suportada.";
                    }
                }
                
                // Script injetado para auto-expandir caixas de texto em tempo real no tablet
                setInterval(function() {
                    const textareas = window.parent.document.querySelectorAll("textarea");
                    textareas.forEach(ta => {
                        if(ta.scrollHeight > ta.clientHeight) {
                            ta.style.height = 'auto';
                            ta.style.height = ta.scrollHeight + 'px';
                        }
                        ta.addEventListener('input', function() {
                            this.style.height = 'auto';
                            this.style.height = this.scrollHeight + 'px';
                        });
                    });
                }, 1000);
                </script>
            </div>
        """, height=95)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📸 Captura de Evidências Fotográficas")
        
        # Opção 1: Câmera Direta (Webcam no PC / Câmera no Tablet)
        img_camera = st.camera_input("📷 Tirar Foto Direta (Webcam / Câmera do Dispositivo)", key=f"cam_in_{processo_id_selecionado}")
        if img_camera is not None:
            file_bytes = img_camera.getvalue()
            file_hash = hashlib.md5(file_bytes).hexdigest()[:10]
            nome_img = f"{processo_id_selecionado}_{file_hash}_cam.jpg"
            path_img = os.path.join(FOTOS_DIR, nome_img)
            
            if not any(f["path"] == path_img for f in p_atual["campo_fotos"]):
                with open(path_img, "wb") as f:
                    f.write(file_bytes)
                
                gps_auto = st.session_state.get("gps_field_main", "")
                p_atual["campo_fotos"].append({
                    "path": path_img,
                    "gps": gps_auto,
                    "legenda": "Registro fotográfico obtido em diligência pericial."
                })
                salvar_dados(db_processos)
                st.toast("✅ Foto adicionada!", icon="📸")
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        
        # Opção 2: Envio de Arquivos / Galeria
        col_up1, col_up2 = st.columns([3, 1])
        with col_up1:
            fotos_upload = st.file_uploader("📁 Ou Enviar Foto(s) da Galeria / Arquivos", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"up_gal_{processo_id_selecionado}")
        with col_up2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Limpar Todas", key=f"clear_f_{processo_id_selecionado}"):
                p_atual["campo_fotos"] = []
                salvar_dados(db_processos)
                st.toast("✅ Lista de fotos limpa!", icon="🗑️")
                st.rerun()

        if fotos_upload:
            novas_fotos = False
            for img in fotos_upload:
                file_bytes = img.getvalue()
                file_hash = hashlib.md5(file_bytes).hexdigest()[:10]
                nome_img = f"{processo_id_selecionado}_{file_hash}_{img.name}"
                path_img = os.path.join(FOTOS_DIR, nome_img)
                
                if not any(f["path"] == path_img for f in p_atual["campo_fotos"]):
                    with open(path_img, "wb") as f:
                        f.write(file_bytes)
                    
                    gps_auto = st.session_state.get("gps_field_main", "")
                    p_atual["campo_fotos"].append({
                        "path": path_img,
                        "gps": gps_auto,
                        "legenda": "Registro fotográfico obtido em diligência pericial."
                    })
                    novas_fotos = True
            
            if novas_fotos:
                salvar_dados(db_processos)
                st.toast("✅ Foto(s) enviada(s)!", icon="📸")
                st.rerun()

        st.markdown("<br>---<br>", unsafe_allow_html=True)
        col_ger, col_btn_geral = st.columns([2, 1])
        with col_ger:
            st.markdown(f"#### 🖼️ Gerenciar Fotos Cadastradas ({len(p_atual.get('campo_fotos', []))} fotos):")
        with col_btn_geral:
            if st.button("⚡ Salvar GPS em Todas as Fotos", key=f"sv_gps_all_{processo_id_selecionado}"):
                gps_atual_sessao = st.session_state.get("gps_field_main", "")
                if gps_atual_sessao:
                    for f_dict in p_atual["campo_fotos"]:
                        f_dict["gps"] = gps_atual_sessao
                    salvar_dados(db_processos)
                    st.toast("✅ Coordenadas salvas em lote!", icon="📍")
                    st.rerun()
                else:
                    st.warning("Obtenha o GPS no botão acima primeiro.")

        if not p_atual.get("campo_fotos"):
            st.info("Nenhuma foto cadastrada ainda. Envie fotos acima para começar.")
        else:
            for idx, foto_dict in enumerate(p_atual["campo_fotos"]):
                with st.container():
                    col_img, col_dados = st.columns([1, 2])
                    with col_img:
                        if os.path.exists(foto_dict["path"]):
                            st.image(foto_dict["path"], width=220)
                        else:
                            st.warning("[Arquivo não encontrado]")
                    with col_dados:
                        nova_legenda = st.text_input(f"Legenda da Figura {idx+1}", value=foto_dict.get("legenda", ""), key=f"leg_{processo_id_selecionado}_{idx}")
                        novo_gps = st.text_input(f"Coordenadas GPS (Figura {idx+1})", value=foto_dict.get("gps", ""), key=f"gps_{processo_id_selecionado}_{idx}", placeholder="GPS_FOTO")
                        
                        c_salvar, c_del = st.columns(2)
                        with c_salvar:
                            if st.button(f"💾 Atualizar Foto {idx+1}", key=f"sv_f_{processo_id_selecionado}_{idx}"):
                                p_atual["campo_fotos"][idx]["legenda"] = nova_legenda
                                p_atual["campo_fotos"][idx]["gps"] = novo_gps
                                salvar_dados(db_processos)
                                st.toast("✅ Legenda atualizada!", icon="💾")
                                st.rerun()
                        with c_del:
                            if st.button(f"🗑️ Excluir Foto {idx+1}", key=f"del_f_{processo_id_selecionado}_{idx}"):
                                p_atual["campo_fotos"].pop(idx)
                                salvar_dados(db_processos)
                                st.toast("🗑️ Foto removida!")
                                st.rerun()
                    st.markdown("---")

elif opcao == "🗑️ Excluir Processo":
    st.markdown("### Excluir Caso / Processo")
    if not db_processos or processo_id_selecionado == "Nenhum caso cadastrado":
        st.warning("Nenhum caso disponível para exclusão.")
    else:
        p_excluir = db_processos[processo_id_selecionado]
        st.error(f"⚠️ Atenção: Você está prestes a excluir o caso **{processo_id_selecionado}** ({p_excluir.get('reclamante_nome', 'Não informado')}).")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if not st.session_state.confirmar_exclusao_dupla:
            if st.button("🗑️ Solicitar Exclusão Definitiva"):
                st.session_state.confirmar_exclusao_dupla = True
                st.rerun()
        else:
            st.warning("🚨 TEM CERTEZA ABSOLUTA? Esta ação apagará permanentemente todos os dados e fotos deste caso!")
            col_sim, col_nao = st.columns(2)
            with col_sim:
                if st.button("🔴 SIM, EXCLUIR PERMANENTEMENTE"):
                    for f_dict in p_excluir.get("campo_fotos", []):
                        f_path = f_dict.get("path")
                        if f_path and os.path.exists(f_path):
                            try:
                                os.remove(f_path)
                            except:
                                pass
                    del db_processos[processo_id_selecionado]
                    salvar_dados(db_processos)
                    st.session_state.confirmar_exclusao_dupla = False
                    st.toast("🗑️ Processo excluído!", icon="🚨")
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
        
        st.markdown(f"<p style='font-size: 17px;'>Caso selecionado: <b>{processo_id_selecionado}</b> — Segurado/Autor: <i>{p.get('reclamante_nome', '')}</i></p>", unsafe_allow_html=True)
        
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
                
                if not text:
                    text = "[Informação/Documento não localizado nos autos anexados]"
                    
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
            if os.path.exists(LOGO_FILE):
                logo_doc = LOGO_FILE
            else:
                for f in os.listdir("."):
                    if "logo" in f.lower() and f.lower().endswith((".jpg", ".png", ".jpeg")):
                        logo_doc = f
                        break

            if logo_doc:
                p_logo = doc.add_paragraph()
                p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_logo.add_run().add_picture(logo_doc, width=Inches(2.0))
                adicionar_linha_vazia()

            t_main = doc.add_paragraph()
            t_main.alignment = WD_ALIGN_PARAGRAPH.CENTER
            t_main.paragraph_format.line_spacing = 1.5
            
            titulo_doc = "LAUDO TÉCNICO DE CONDIÇÕES AMBIENTAIS DO TRABALHO (LTCAT) & PPP" if is_prev else "PRÉ-RELATÓRIO DE ANÁLISE PROCESSUAL E PERICIAL"
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
                    for h_idx, h_text in enumerate(headers):
                        t_epi.rows[0].cells[h_idx].text = h_text
                    
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
                    ("Número do Processo", p.get('processo_num', '')),
                    ("Órgão Julgador / Vara", p.get('orgao_julgador', '')),
                    ("Data de Autuação (Ajuizamento)", p.get('data_autuacao', '')),
                    ("Valor da Causa", p.get('valor_causa', '')),
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
                    for h_idx, h_text in enumerate(headers):
                        t_epi.rows[0].cells[h_idx].text = h_text
                    
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
                    f_path = foto_dict.get("path")
                    if f_path and os.path.exists(f_path):
                        try:
                            p_img = doc.add_paragraph()
                            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            p_img.add_run().add_picture(f_path, width=Inches(4.5))
                            
                            texto_legenda = foto_dict.get("legenda", "Registro fotográfico.")
                            coords_gps = foto_dict.get("gps", "")
                            if coords_gps:
                                texto_legenda += f" ({coords_gps})"
                            
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
