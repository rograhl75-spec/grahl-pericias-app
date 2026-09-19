import os
from copy import deepcopy
from zipfile import BadZipFile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from grahl_app.constants import (
    DADOS_PADRAO,
    LOGO_FILE,
    MENU_DATA,
    MENU_DELETE,
    MENU_DOCX,
    MENU_FIELD,
    MENU_NEW,
    MENU_OPTIONS,
    MODULE_JUDICIAL,
    MODULE_OPTIONS,
    MODULE_PREVIDENCIARIO,
    NO_CASE_SELECTED,
    ROLE_OPTIONS,
    SESSION_DEFAULTS,
    TIPOS_PERICIA_DEFAULT,
    TIPOS_PERICIA_OPTIONS,
)
from grahl_app.documents import build_document_bytes
from grahl_app.parser import parse_pre_relatorio
from grahl_app.photos import build_photo_entry, decode_photo_base64, photo_exists
from grahl_app.storage import create_process_with_auto_id, delete_process, load_processes, save_process
from grahl_app.ui_helpers import (
    initialize_session_state,
    render_case_header,
    show_save_feedback,
    text_area_value,
    text_input_value,
)
from grahl_app.utils import (
    clone_process_data,
    format_missing_field_labels,
    generate_next_process_id,
    normalize_epi_list,
    normalize_process_data,
    remover_acentos,
    sanitize_output_filename,
    validate_process_data,
)

icon_config = LOGO_FILE if os.path.exists(LOGO_FILE) else "🛡️"
st.set_page_config(page_title="Grahl Consultoria - Perícias e Laudos Previdenciários", page_icon=icon_config, layout="wide")
initialize_session_state(SESSION_DEFAULTS)


st.markdown(
    """
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
    .stButton button {
        background-color: #1B365D !important; color: white !important; font-weight: 700 !important;
        border-radius: 8px !important; padding: 0.5rem 1.2rem; border: none;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); transition: all 0.3s ease;
    }
    .stButton button:hover { background-color: #2D4A7C !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #E2E8F0; border-radius: 8px 8px 0px 0px; color: #1B365D; font-weight: 700; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #1B365D !important; color: white !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def trocar_menu(acao: str) -> None:
    st.session_state.menu_opcao = acao


def save_with_feedback(process_id: str, process_data: dict, success_message: str) -> bool:
    normalized = normalize_process_data(process_data)
    validation = validate_process_data(normalized, for_generation=False)
    try:
        save_process(process_id, normalized)
    except RuntimeError as exc:
        st.error(str(exc))
        return False
    show_save_feedback(success_message, validation.missing_required_fields)
    return True


def render_epi_editor(process_data: dict, *, process_id: str, editor_key: str, button_key: str, button_label: str, success_message: str, previdenciario: bool = False) -> None:
    epis_atuais = normalize_epi_list(process_data.get("quadro_epis", []))
    df_epis = pd.DataFrame(epis_atuais, columns=["descricao", "ca", "data_entrega", "obs"])
    edited_df = st.data_editor(
        df_epis,
        column_config={
            "descricao": st.column_config.TextColumn("Descrição do EPI" if previdenciario else "Descrição do EPI fornecido", width="large", required=True),
            "ca": st.column_config.TextColumn("C.A.", width="small"),
            "data_entrega": st.column_config.TextColumn("Periodicidade / Entrega" if previdenciario else "Data Entrega", width="medium"),
            "obs": st.column_config.TextColumn("Eficácia / Higienização / Tema 555" if previdenciario else "Observações", width="large"),
        },
        num_rows="dynamic",
        use_container_width=True,
        height=300 if previdenciario else 350,
        key=editor_key,
    )
    if st.button(button_label, key=button_key):
        df_clean = edited_df.fillna("")
        df_clean = df_clean[df_clean["descricao"].astype(str).str.strip() != ""]
        updated = clone_process_data(process_data)
        updated["quadro_epis"] = normalize_epi_list(df_clean.to_dict("records"))
        if save_with_feedback(process_id, updated, success_message):
            st.rerun()


def render_logo_and_title() -> None:
    col_logo, col_titulo = st.columns([1, 6])
    with col_logo:
        if os.path.exists(LOGO_FILE):
            st.image(LOGO_FILE, width=140)
        else:
            st.markdown("### 🛡️ **GRAHL**")
    with col_titulo:
        st.markdown("<h1 style='margin:0; font-size: 1.7rem;'>Gestão Pericial Trabalhista & Laudos Previdenciários</h1>", unsafe_allow_html=True)
        st.markdown("<p style='color: #64748B; margin:0; font-size: 1rem; font-weight: 500;'>Assistência Técnica, Perícias Judiciais e Laudos Extrajudiciais (LTCAT + PPP).</p>", unsafe_allow_html=True)
    st.markdown("<hr style='margin-top: 1rem; margin-bottom: 1.5rem; border: none; height: 1px; background-color: #CBD5E1;'>", unsafe_allow_html=True)


render_logo_and_title()
try:
    db_processos = load_processes()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

st.sidebar.markdown("<h2 style='color: #FFFFFF; font-size: 1.3rem; margin-bottom: 1rem;'>📁 Painel de Controle</h2>", unsafe_allow_html=True)
for acao in MENU_OPTIONS:
    st.sidebar.button(acao, on_click=trocar_menu, args=(acao,), use_container_width=True)

opcao = st.session_state.menu_opcao
st.sidebar.markdown("<hr style='border: none; height: 1px; background-color: rgba(255,255,255,0.2); margin: 1.5rem 0;'>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='color: #FFFFFF; font-weight: 600; font-size: 14px; margin-bottom: 0.3rem;'>🔎 Pesquisa Rápida:</p>", unsafe_allow_html=True)
termo_busca_geral = st.sidebar.text_input("Busca", placeholder="ID, Processo, Nome ou Empresa...", label_visibility="collapsed").strip()
termo_limpo = remover_acentos(termo_busca_geral)

processos_filtrados: list[str] = []
for process_id, process_data in db_processos.items():
    if not termo_limpo:
        processos_filtrados.append(process_id)
        continue
    id_norm = remover_acentos(process_id)
    proc_num_norm = remover_acentos(str(process_data.get("processo_num", "")))
    reclamada_norm = remover_acentos(str(process_data.get("reclamada_nome", "")))
    reclamante_norm = remover_acentos(str(process_data.get("reclamante_nome", "")))
    if termo_limpo in id_norm or termo_limpo in proc_num_norm or termo_limpo in reclamada_norm or termo_limpo in reclamante_norm:
        processos_filtrados.append(process_id)

st.sidebar.markdown("<br>", unsafe_allow_html=True)
processo_id_selecionado = NO_CASE_SELECTED

if processos_filtrados:
    mapa_opcoes: dict[str, str] = {}
    for process_id in processos_filtrados:
        process_data = db_processos[process_id]
        nome = process_data.get("reclamante_nome", "Sem Nome")
        empresa = process_data.get("reclamada_nome", "")
        num_p = process_data.get("processo_num", "")
        label = f"[{process_id}] {nome}"
        if empresa:
            label += f" x {empresa}"
        elif num_p:
            label += f" ({num_p})"
        mapa_opcoes[label] = process_id

    if st.session_state.processo_ativo not in processos_filtrados:
        st.session_state.processo_ativo = processos_filtrados[0]

    lista_chaves = list(mapa_opcoes.keys())
    idx_selecionado = next((i for i, rotulo in enumerate(lista_chaves) if mapa_opcoes[rotulo] == st.session_state.processo_ativo), 0)

    def atualizar_processo() -> None:
        rotulo_escolhido = st.session_state.caixa_pesquisa
        st.session_state.processo_ativo = mapa_opcoes.get(rotulo_escolhido)
        if st.session_state.processo_ativo:
            st.session_state.menu_opcao = MENU_DATA
            st.session_state.confirmar_exclusao_dupla = False

    st.sidebar.selectbox("Processo / Caso Selecionado:", options=lista_chaves, index=idx_selecionado, key="caixa_pesquisa", on_change=atualizar_processo)
    processo_id_selecionado = st.session_state.processo_ativo or NO_CASE_SELECTED
else:
    st.session_state.processo_ativo = None
    st.session_state.confirmar_exclusao_dupla = False
    st.sidebar.warning("⚠️ Nenhum caso encontrado.")


if opcao == MENU_NEW:
    st.markdown("### Cadastrar Novo Caso ou Processo")
    st.info(f"✨ O próximo ID gerado automaticamente é: **{generate_next_process_id(db_processos.keys())}**")
    st.markdown("<br>", unsafe_allow_html=True)
    modulo_escolhido = st.radio("Selecione o Módulo de Atuação:", MODULE_OPTIONS)
    is_prev_mod = "Previdenciário" in modulo_escolhido

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📥 Importar Documento Base (.docx)")
    arquivo_importado = st.file_uploader("Selecione o arquivo Word para preenchimento automático", type=["docx"], key=f"uploader_{st.session_state.uploader_key}")
    if arquivo_importado is not None:
        try:
            doc_ext = Document(arquivo_importado)
            st.session_state.parsed_data = parse_pre_relatorio(doc_ext)
            st.success("Documento lido e mapeado com sucesso!")
        except (PackageNotFoundError, BadZipFile, ValueError) as exc:
            st.error(f"Erro ao ler o arquivo Word informado: {exc}")

    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("form_novo"):
        parsed = deepcopy(st.session_state.get("parsed_data", {}))
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
            p_novo = clone_process_data(DADOS_PADRAO)
            for key, value in parsed.items():
                if value not in (None, "", []):
                    p_novo[key] = value
            p_novo["modulo_atuacao"] = MODULE_PREVIDENCIARIO if is_prev_mod else MODULE_JUDICIAL
            p_novo["reclamante_nome"] = p_nome
            p_novo["reclamada_nome"] = p_empresa
            p_novo["processo_num"] = p_num
            try:
                novo_id = create_process_with_auto_id(p_novo)
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.session_state.parsed_data = {}
                st.session_state.uploader_key += 1
                st.session_state.processo_ativo = novo_id
                st.session_state.menu_opcao = MENU_DATA
                show_save_feedback(f"✅ Caso {novo_id} criado com sucesso!", validate_process_data(p_novo).missing_required_fields)
                st.rerun()

elif opcao == MENU_DATA:
    if not db_processos or processo_id_selecionado == NO_CASE_SELECTED:
        st.warning("Cadastre ou selecione um caso no menu lateral para começar.")
    else:
        p_atual = clone_process_data(db_processos[processo_id_selecionado])
        is_prev = "Previdenciário" in p_atual.get("modulo_atuacao", "")
        render_case_header(processo_id_selecionado, p_atual)

        if is_prev:
            tab1, tab2, tab3, tab4 = st.tabs(["1️⃣ Segurado & Tomador", "2️⃣ APR-HO & Extemporaneidade", "3️⃣ Planilha de EPIs", "4️⃣ Metodologia & Enquadramento"])
            with tab1:
                st.markdown("### 1. Identificação do Segurado e da Empresa")
                with st.form(f"fp_1_{processo_id_selecionado}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        reclamante_nome = text_input_value(p_atual, "reclamante_nome", "Nome do Segurado", f"p1_rn_{processo_id_selecionado}")
                        reclamante_cpf = text_input_value(p_atual, "reclamante_cpf", "CPF / NIT / PIS", f"p1_rc_{processo_id_selecionado}")
                        segurado_nascimento = text_input_value(p_atual, "segurado_nascimento", "Data de Nascimento", f"p1_sn_{processo_id_selecionado}")
                        profissao_cargo = text_input_value(p_atual, "profissao_cargo", "Profissão / Cargo Avaliado", f"p1_pc_{processo_id_selecionado}")
                    with col2:
                        reclamada_nome = text_input_value(p_atual, "reclamada_nome", "Razão Social da Empresa / Tomador", f"p1_rnm_{processo_id_selecionado}")
                        reclamada_cnpj = text_input_value(p_atual, "reclamada_cnpj", "CNPJ da Empresa", f"p1_rcj_{processo_id_selecionado}")
                        setor = text_input_value(p_atual, "setor", "Setor / Lotação / Local", f"p1_st_{processo_id_selecionado}")
                        data_admissao = text_input_value(p_atual, "data_admissao", "Período de Trabalho (Admissão - Demissão)", f"p1_da_{processo_id_selecionado}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    relato_inicial = text_area_value(p_atual, "relato_inicial", "Relato Inicial / Atividades Desenvolvidas pelo Segurado", f"p1_ri_{processo_id_selecionado}", min_height=120)
                    if st.form_submit_button("💾 Salvar Dados do Segurado"):
                        updated = clone_process_data(p_atual)
                        updated.update({
                            "reclamante_nome": reclamante_nome,
                            "reclamante_cpf": reclamante_cpf,
                            "segurado_nascimento": segurado_nascimento,
                            "profissao_cargo": profissao_cargo,
                            "reclamada_nome": reclamada_nome,
                            "reclamada_cnpj": reclamada_cnpj,
                            "setor": setor,
                            "data_admissao": data_admissao,
                            "relato_inicial": relato_inicial,
                        })
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Dados do Segurado salvos!"):
                            st.rerun()

            with tab2:
                st.markdown("### 2. Análise Preliminar de Riscos (APR-HO) & Extemporaneidade")
                with st.form(f"fp_2_{processo_id_selecionado}"):
                    apr_fisicos = text_area_value(p_atual, "apr_fisicos", "Agentes Físicos Presumidos (Ex: Ruído NHO-01, Calor IBUTG)", f"p2_af_{processo_id_selecionado}", min_height=80)
                    apr_quimicos = text_area_value(p_atual, "apr_quimicos", "Agentes Químicos (Ex: Hidrocarbonetos, Solventes, LINACH)", f"p2_aq_{processo_id_selecionado}", min_height=80)
                    apr_biologicos = text_area_value(p_atual, "apr_biologicos", "Agentes Biológicos (Se aplicável)", f"p2_ab_{processo_id_selecionado}", min_height=80)
                    st.markdown("#### Avaliação de Extemporaneidade (Art. 279, IN 128/2022):")
                    extemp_layout = st.checkbox("Houve mudança no layout ou organização do ambiente?", value=p_atual.get("extemp_layout", False), key=f"p2_el_{processo_id_selecionado}")
                    extemp_maquinas = st.checkbox("Houve substituição de máquinas ou equipamentos?", value=p_atual.get("extemp_maquinas", False), key=f"p2_em_{processo_id_selecionado}")
                    extemp_epc = st.checkbox("Houve alteração nas tecnologias de proteção coletiva (EPC)?", value=p_atual.get("extemp_epc", False), key=f"p2_ee_{processo_id_selecionado}")
                    extemp_justificativa = text_area_value(p_atual, "extemp_justificativa", "Fundamentação Técnica da Equivalência (Extemporaneidade)", f"p2_ej_{processo_id_selecionado}", min_height=100)
                    if st.form_submit_button("💾 Salvar APR e Extemporaneidade"):
                        updated = clone_process_data(p_atual)
                        updated.update({
                            "apr_fisicos": apr_fisicos,
                            "apr_quimicos": apr_quimicos,
                            "apr_biologicos": apr_biologicos,
                            "extemp_layout": extemp_layout,
                            "extemp_maquinas": extemp_maquinas,
                            "extemp_epc": extemp_epc,
                            "extemp_justificativa": extemp_justificativa,
                        })
                        if save_with_feedback(processo_id_selecionado, updated, "✅ APR salva com sucesso!"):
                            st.rerun()

            with tab3:
                st.markdown("### 3. Planilha de EPIs & Eficácia (Tema 555 STF)")
                render_epi_editor(p_atual, process_id=processo_id_selecionado, editor_key=f"ed_pe_{processo_id_selecionado}", button_key=f"btn_pe_{processo_id_selecionado}", button_label="💾 Salvar Tabela de EPIs Previdenciários", success_message="✅ Planilha de EPIs salva!", previdenciario=True)
                st.markdown("<br>", unsafe_allow_html=True)
                with st.form(f"form_prev_epi_{processo_id_selecionado}"):
                    analise_epis_critica = text_area_value(p_atual, "analise_epis_critica", "Análise Crítica da Eficácia dos EPIs (Tema 555 STF / Súmula 9 TNU)", f"p3_aec_{processo_id_selecionado}", min_height=120)
                    if st.form_submit_button("💾 Salvar Análise Crítica"):
                        updated = clone_process_data(p_atual)
                        updated["analise_epis_critica"] = analise_epis_critica
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Análise Crítica salva!"):
                            st.rerun()

            with tab4:
                st.markdown("### 4. Metodologia (NHO-01 Fundacentro) & Enquadramento Legal")
                with st.form(f"form_prev_4_{processo_id_selecionado}"):
                    enquadramento_legal_prev = text_input_value(p_atual, "enquadramento_legal_prev", "Enquadramento Legal (Decreto 3.048/99 - Anexo IV)", f"p4_elp_{processo_id_selecionado}")
                    doc_ltcat = text_area_value(p_atual, "doc_ltcat", "Metodologia de Avaliação Ambiental (Ex: Ruído NHO-01, q=5, NEN, Critérios Químicos LINACH)", f"p4_dl_{processo_id_selecionado}", min_height=150)
                    if st.form_submit_button("💾 Salvar Metodologia"):
                        updated = clone_process_data(p_atual)
                        updated.update({"enquadramento_legal_prev": enquadramento_legal_prev, "doc_ltcat": doc_ltcat})
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Metodologia salva!"):
                            st.rerun()
        else:
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["1️⃣ Identificação & Partes", "2️⃣ Contrato & Sínteses", "3️⃣ SST & Documentos", "4️⃣ Planilha de EPIs", "5️⃣ Quesitos Literais"])
            with tab1:
                st.markdown("### 1. Papel Profissional, Tipos de Perícia & Identificação")
                with st.form(f"ft_1_{processo_id_selecionado}"):
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        papel_index = ROLE_OPTIONS.index(p_atual.get("papel_profissional")) if p_atual.get("papel_profissional") in ROLE_OPTIONS else 2
                        papel_profissional = st.selectbox("Meu Papel no Processo", ROLE_OPTIONS, index=papel_index, key=f"s1_pp_{processo_id_selecionado}")
                    with col_p2:
                        tipos_pericia = st.multiselect("Tipos de Perícia Envolvidos", TIPOS_PERICIA_OPTIONS, default=p_atual.get("tipos_pericia", TIPOS_PERICIA_DEFAULT), key=f"s1_tp_{processo_id_selecionado}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        processo_num = text_input_value(p_atual, "processo_num", "Número do Processo (CNJ)", f"s1_pn_{processo_id_selecionado}")
                        orgao_julgador = text_input_value(p_atual, "orgao_julgador", "Órgão Julgador / Vara", f"s1_oj_{processo_id_selecionado}")
                        data_autuacao = text_input_value(p_atual, "data_autuacao", "Data de Autuação (Ajuizamento)", f"s1_da_{processo_id_selecionado}")
                        valor_causa = text_input_value(p_atual, "valor_causa", "Valor da Causa", f"s1_vc_{processo_id_selecionado}")
                        rito_processual = text_input_value(p_atual, "rito_processual", "Rito Processual", f"s1_rp_{processo_id_selecionado}")
                    with col2:
                        reclamante_nome = text_input_value(p_atual, "reclamante_nome", "Reclamante (Autor/Autora)", f"s1_rn_{processo_id_selecionado}")
                        reclamante_cpf = text_input_value(p_atual, "reclamante_cpf", "CPF do Reclamante", f"s1_rc_{processo_id_selecionado}")
                        reclamante_adv = text_input_value(p_atual, "reclamante_adv", "Advogados do Reclamante (Nomes e OAB)", f"s1_ra_{processo_id_selecionado}")
                        reclamada_nome = text_input_value(p_atual, "reclamada_nome", "Reclamada (Ré / Empresa)", f"s1_rdn_{processo_id_selecionado}")
                        reclamada_cnpj = text_input_value(p_atual, "reclamada_cnpj", "CNPJ da Reclamada", f"s1_rdc_{processo_id_selecionado}")
                        reclamada_adv = text_input_value(p_atual, "reclamada_adv", "Advogados da Reclamada (Nomes e OAB)", f"s1_rda_{processo_id_selecionado}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Salvar Papel, Identificação e Partes"):
                        updated = clone_process_data(p_atual)
                        updated.update({
                            "papel_profissional": papel_profissional,
                            "tipos_pericia": tipos_pericia,
                            "processo_num": processo_num,
                            "orgao_julgador": orgao_julgador,
                            "data_autuacao": data_autuacao,
                            "valor_causa": valor_causa,
                            "rito_processual": rito_processual,
                            "reclamante_nome": reclamante_nome,
                            "reclamante_cpf": reclamante_cpf,
                            "reclamante_adv": reclamante_adv,
                            "reclamada_nome": reclamada_nome,
                            "reclamada_cnpj": reclamada_cnpj,
                            "reclamada_adv": reclamada_adv,
                        })
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Identificação salva!"):
                            st.rerun()

            with tab2:
                st.markdown("### 3. Dados do Contrato & 4/5. Sínteses da Inicial e Defesa")
                with st.form(f"ft_2_{processo_id_selecionado}"):
                    col3, col4 = st.columns(2)
                    with col3:
                        data_admissao = text_input_value(p_atual, "data_admissao", "Data de Admissão", f"s2_da_{processo_id_selecionado}")
                        status_contrato = text_input_value(p_atual, "status_contrato", "Status do Contrato (Demissão / Ativo)", f"s2_sc_{processo_id_selecionado}")
                        periodo_imprescrito = text_input_value(p_atual, "periodo_imprescrito", "Período Imprescrito (Alvo da Perícia)", f"s2_pi_{processo_id_selecionado}")
                        cargos = text_input_value(p_atual, "cargos", "Cargo(s) / Função(ões)", f"s2_c_{processo_id_selecionado}")
                    with col4:
                        setor = text_input_value(p_atual, "setor", "Setor / Lotação / Local", f"s2_s_{processo_id_selecionado}")
                        ultima_remuneracao = text_input_value(p_atual, "ultima_remuneracao", "Última Remuneração", f"s2_ur_{processo_id_selecionado}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    objeto_pericia = text_input_value(p_atual, "objeto_pericia", "Objeto de Análise / Perícia", f"s2_op_{processo_id_selecionado}")
                    atividades_inicial = text_area_value(p_atual, "atividades_inicial", "Atividades Descritas na Inicial", f"s2_ai_{processo_id_selecionado}", min_height=100)
                    agentes_alegados = text_area_value(p_atual, "agentes_alegados", "Agentes Nocivos / Riscos Alegados", f"s2_aa_{processo_id_selecionado}", min_height=100)
                    pedidos_tecnicos = text_area_value(p_atual, "pedidos_tecnicos", "Pedidos Técnicos (Grau, Enquadramento, PPP)", f"s2_pt_{processo_id_selecionado}", min_height=100)
                    preliminares_periciais = text_area_value(p_atual, "preliminares_periciais", "Preliminares Periciais (Contestação)", f"s2_pp_{processo_id_selecionado}", min_height=100)
                    defesa_merito_sst = text_area_value(p_atual, "defesa_merito_sst", "Defesa de Mérito SST (Contestação)", f"s2_dm_{processo_id_selecionado}", min_height=120)
                    if st.form_submit_button("💾 Salvar Contrato e Sínteses"):
                        updated = clone_process_data(p_atual)
                        updated.update({
                            "data_admissao": data_admissao,
                            "status_contrato": status_contrato,
                            "periodo_imprescrito": periodo_imprescrito,
                            "cargos": cargos,
                            "setor": setor,
                            "ultima_remuneracao": ultima_remuneracao,
                            "objeto_pericia": objeto_pericia,
                            "atividades_inicial": atividades_inicial,
                            "agentes_alegados": agentes_alegados,
                            "pedidos_tecnicos": pedidos_tecnicos,
                            "preliminares_periciais": preliminares_periciais,
                            "defesa_merito_sst": defesa_merito_sst,
                        })
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Contrato e Sínteses salvos!"):
                            st.rerun()

            with tab3:
                st.markdown("### 6. Vistoria & 7. Análise de Documentos de SST")
                with st.form(f"ft_3_{processo_id_selecionado}"):
                    col5, col6, col7 = st.columns(3)
                    with col5:
                        fase_processual = text_input_value(p_atual, "fase_processual", "Fase Processual Atual", f"s3_fp_{processo_id_selecionado}")
                    with col6:
                        campo_data = text_input_value(p_atual, "campo_data", "Data da Vistoria", f"s3_cd_{processo_id_selecionado}")
                    with col7:
                        campo_horario = text_input_value(p_atual, "campo_horario", "Horário da Vistoria", f"s3_ch_{processo_id_selecionado}")
                    local_diligencia = text_input_value(p_atual, "local_diligencia", "Local / Endereço da Diligência", f"s3_ld_{processo_id_selecionado}")
                    st.markdown("<br>", unsafe_allow_html=True)
                    doc_ltcat = text_area_value(p_atual, "doc_ltcat", "Análise do LTCAT", f"s3_dl_{processo_id_selecionado}", min_height=90)
                    doc_laudo = text_area_value(p_atual, "doc_laudo", "Análise de Laudos Prévios / Paradigmas", f"s3_dlau_{processo_id_selecionado}", min_height=90)
                    doc_ppp = text_area_value(p_atual, "doc_ppp", "Análise do PPP (Agentes, Responsáveis, EPI)", f"s3_dppp_{processo_id_selecionado}", min_height=90)
                    doc_pgr = text_area_value(p_atual, "doc_pgr", "Análise do PGR / PPRA / PCMAT", f"s3_dpgr_{processo_id_selecionado}", min_height=90)
                    doc_os = text_area_value(p_atual, "doc_os", "Ordens de Serviço e Treinamentos", f"s3_dos_{processo_id_selecionado}", min_height=90)
                    doc_asos = text_area_value(p_atual, "doc_asos", "ASOs / PCMSO (Aptidão e Riscos)", f"s3_daso_{processo_id_selecionado}", min_height=90)
                    doc_outros = text_area_value(p_atual, "doc_outros", "Outros Documentos Relevantes (FISPQs, etc.)", f"s3_dout_{processo_id_selecionado}", min_height=90)
                    if st.form_submit_button("💾 Salvar Vistoria e Documentos SST"):
                        updated = clone_process_data(p_atual)
                        updated.update({
                            "fase_processual": fase_processual,
                            "campo_data": campo_data,
                            "campo_horario": campo_horario,
                            "local_diligencia": local_diligencia,
                            "doc_ltcat": doc_ltcat,
                            "doc_laudo": doc_laudo,
                            "doc_ppp": doc_ppp,
                            "doc_pgr": doc_pgr,
                            "doc_os": doc_os,
                            "doc_asos": doc_asos,
                            "doc_outros": doc_outros,
                        })
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Análises de Documentos salvas!"):
                            st.rerun()

            with tab4:
                st.markdown("### 8. Quadro de Fornecimento de EPIs & Análise Crítica")
                render_epi_editor(p_atual, process_id=processo_id_selecionado, editor_key=f"ed_et_{processo_id_selecionado}", button_key=f"btn_st_{processo_id_selecionado}", button_label="💾 Salvar Tabela de EPIs", success_message="✅ Quadro de EPIs salvo!")
                st.markdown("<br>---<br>", unsafe_allow_html=True)
                with st.form(f"ft_4_epi_{processo_id_selecionado}"):
                    analise_epis_critica = text_area_value(p_atual, "analise_epis_critica", "Síntese e Análise Crítica de EPIs", f"s4_aec_{processo_id_selecionado}", min_height=180)
                    if st.form_submit_button("💾 Salvar Análise Crítica de EPIs"):
                        updated = clone_process_data(p_atual)
                        updated["analise_epis_critica"] = analise_epis_critica
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Análise Crítica salva!"):
                            st.rerun()

            with tab5:
                st.markdown("### 9. Quesitos Formulados para a Perícia (Transcrição Literal)")
                with st.form(f"ft_5_{processo_id_selecionado}"):
                    quesitos_juizo = text_area_value(p_atual, "quesitos_juizo", "9.1. Quesitos do Juízo", f"s5_qj_{processo_id_selecionado}", min_height=150)
                    quesitos_autor = text_area_value(p_atual, "quesitos_autor", "9.2. Quesitos do Reclamante (Autor/Autora)", f"s5_qa_{processo_id_selecionado}", min_height=250)
                    quesitos_reu = text_area_value(p_atual, "quesitos_reu", "9.3. Quesitos da Reclamada (Ré / Empresa)", f"s5_qr_{processo_id_selecionado}", min_height=250)
                    if st.form_submit_button("💾 Salvar Quesitos Literais"):
                        updated = clone_process_data(p_atual)
                        updated.update({
                            "quesitos_juizo": quesitos_juizo,
                            "quesitos_autor": quesitos_autor,
                            "quesitos_reu": quesitos_reu,
                        })
                        if save_with_feedback(processo_id_selecionado, updated, "✅ Quesitos salvos!"):
                            st.rerun()

elif opcao == MENU_FIELD:
    if not db_processos or processo_id_selecionado == NO_CASE_SELECTED:
        st.warning("Cadastre ou selecione um caso no menu lateral.")
    else:
        p_atual = clone_process_data(db_processos[processo_id_selecionado])
        render_case_header(processo_id_selecionado, p_atual)
        st.markdown("### 🚜 Vistoria Pericial de Campo, Declarações & Evidências")
        with st.form(f"f_campo_{processo_id_selecionado}"):
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                campo_data = text_input_value(p_atual, "campo_data", "Data da Vistoria", f"cd_cd_{processo_id_selecionado}")
            with col_c2:
                campo_horario = text_input_value(p_atual, "campo_horario", "Horário da Vistoria", f"cd_ch_{processo_id_selecionado}")
            st.markdown("<br>", unsafe_allow_html=True)
            local_diligencia = text_input_value(p_atual, "local_diligencia", "Endereço / Local da Diligência", f"cd_ld_{processo_id_selecionado}")
            presentes_pericia = text_area_value(p_atual, "presentes_pericia", "Pessoas Presentes na Vistoria (Nome e Função)", f"cd_pp_{processo_id_selecionado}", min_height=80)
            campo_declaracoes_autor = text_area_value(p_atual, "campo_declaracoes_autor", "Informações prestadas pelo Segurado / Autor", f"cd_cda_{processo_id_selecionado}", min_height=120)
            campo_declaracoes_reu = text_area_value(p_atual, "campo_declaracoes_reu", "Informações prestadas pelo Empregador / Acompanhante", f"cd_cdr_{processo_id_selecionado}", min_height=120)
            campo_medicoes = text_area_value(p_atual, "campo_medicoes", "Medições Realizadas em Campo (Ex: Sonometria NHO-01, IBUTG)", f"cd_cm_{processo_id_selecionado}", min_height=120)
            if st.form_submit_button("💾 Salvar Textos de Campo"):
                updated = clone_process_data(p_atual)
                updated.update({
                    "campo_data": campo_data,
                    "campo_horario": campo_horario,
                    "local_diligencia": local_diligencia,
                    "presentes_pericia": presentes_pericia,
                    "campo_declaracoes_autor": campo_declaracoes_autor,
                    "campo_declaracoes_reu": campo_declaracoes_reu,
                    "campo_medicoes": campo_medicoes,
                })
                if save_with_feedback(processo_id_selecionado, updated, "✅ Textos de campo salvos!"):
                    st.rerun()

        st.markdown("<br>---<br>", unsafe_allow_html=True)
        st.markdown("#### 📍 Captura Rápida de GPS")
        gps_input_val = st.text_input("Coordenada GPS Atual (Sessão Ativa):", value=st.session_state.get("gps_field_main", ""), key=f"cd_gps_{processo_id_selecionado}", placeholder="GPS_TARGET_FIELD")
        if gps_input_val != st.session_state.get("gps_field_main", ""):
            st.session_state.gps_field_main = gps_input_val

        components.html(
            """
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
                                st.innerHTML = "✅ GPS Satélite Obtido!"; injectGPS(coordStr);
                            },
                            function(error) {
                                st.innerHTML = "Tentando via rede 4G/Wi-Fi (rápido)...";
                                navigator.geolocation.getCurrentPosition(
                                    function(position) {
                                        var coordStr = position.coords.latitude.toFixed(6) + ", " + position.coords.longitude.toFixed(6);
                                        st.innerHTML = "✅ GPS Rede Obtido!"; injectGPS(coordStr);
                                    },
                                    function(err2) { st.innerHTML = "❌ Erro de GPS. Ative a localização no tablet."; },
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
            """,
            height=95,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📸 Captura de Evidências Fotográficas")
        current_photos = clone_process_data(p_atual).get("campo_fotos", [])

        img_camera = st.camera_input("📷 Tirar Foto Direta (Webcam / Câmera do Dispositivo)", key=f"cam_in_{processo_id_selecionado}")
        if img_camera is not None:
            new_entry = build_photo_entry(img_camera.getvalue(), gps=st.session_state.get("gps_field_main", ""), source="camera", mime_type=getattr(img_camera, "type", None))
            if photo_exists(current_photos, new_entry):
                st.info("Esta foto já estava cadastrada para o caso ativo.")
            else:
                updated = clone_process_data(p_atual)
                updated.setdefault("campo_fotos", []).append(new_entry)
                if save_with_feedback(processo_id_selecionado, updated, "✅ Foto capturada e guardada na nuvem!"):
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        col_up1, col_up2 = st.columns([3, 1])
        with col_up1:
            fotos_upload = st.file_uploader("📁 Ou Enviar Foto(s) da Galeria / Arquivos", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"up_gal_{processo_id_selecionado}")
        with col_up2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Limpar Todas", key=f"cl_f_{processo_id_selecionado}"):
                updated = clone_process_data(p_atual)
                updated["campo_fotos"] = []
                if save_with_feedback(processo_id_selecionado, updated, "✅ Lista de fotos limpa!"):
                    st.rerun()

        if fotos_upload:
            updated = clone_process_data(p_atual)
            novas_fotos = False
            for image_file in fotos_upload:
                new_entry = build_photo_entry(image_file.getvalue(), gps=st.session_state.get("gps_field_main", ""), source="upload", mime_type=getattr(image_file, "type", None))
                if not photo_exists(updated["campo_fotos"], new_entry):
                    updated["campo_fotos"].append(new_entry)
                    novas_fotos = True
            if novas_fotos:
                if save_with_feedback(processo_id_selecionado, updated, "✅ Foto(s) enviada(s) para a nuvem!"):
                    st.rerun()
            else:
                st.info("Nenhuma nova foto foi adicionada; os arquivos enviados já existiam no caso.")

        st.markdown("<br>---<br>", unsafe_allow_html=True)
        col_ger, col_btn_geral = st.columns([2, 1])
        with col_ger:
            st.markdown(f"#### 🖼️ Gerenciar Fotos Cadastradas ({len(current_photos)} fotos):")
        with col_btn_geral:
            if st.button("⚡ Salvar GPS em Todas as Fotos", key=f"svgps_{processo_id_selecionado}"):
                gps_atual_sessao = st.session_state.get("gps_field_main", "")
                if gps_atual_sessao:
                    updated = clone_process_data(p_atual)
                    for foto in updated["campo_fotos"]:
                        foto["gps"] = gps_atual_sessao
                    if save_with_feedback(processo_id_selecionado, updated, "✅ Coordenadas salvas em lote!"):
                        st.rerun()
                else:
                    st.warning("Obtenha o GPS no botão acima primeiro.")

        if not current_photos:
            st.info("Nenhuma foto cadastrada ainda. Envie fotos acima para começar.")
        else:
            for idx, foto_dict in enumerate(current_photos):
                with st.container():
                    col_img, col_dados = st.columns([1, 2])
                    with col_img:
                        try:
                            st.image(decode_photo_base64(foto_dict.get("base64")), width=220)
                        except ValueError as exc:
                            st.warning(f"[Imagem inválida: {exc}]")
                    with col_dados:
                        nova_legenda = st.text_input(f"Legenda da Figura {idx+1}", value=foto_dict.get("legenda", ""), key=f"lg_{processo_id_selecionado}_{idx}")
                        novo_gps = st.text_input(f"Coordenadas GPS (Figura {idx+1})", value=foto_dict.get("gps", ""), key=f"cg_{processo_id_selecionado}_{idx}", placeholder="GPS_FOTO")
                        c_salvar, c_del = st.columns(2)
                        with c_salvar:
                            if st.button(f"💾 Atualizar Foto {idx+1}", key=f"updf_{processo_id_selecionado}_{idx}"):
                                updated = clone_process_data(p_atual)
                                updated["campo_fotos"][idx]["legenda"] = nova_legenda
                                updated["campo_fotos"][idx]["gps"] = novo_gps
                                if save_with_feedback(processo_id_selecionado, updated, "✅ Legenda atualizada!"):
                                    st.rerun()
                        with c_del:
                            if st.button(f"🗑️ Excluir Foto {idx+1}", key=f"delf_{processo_id_selecionado}_{idx}"):
                                updated = clone_process_data(p_atual)
                                updated["campo_fotos"].pop(idx)
                                if save_with_feedback(processo_id_selecionado, updated, "🗑️ Foto removida!"):
                                    st.rerun()
                    st.markdown("---")

elif opcao == MENU_DELETE:
    st.markdown("### Excluir Caso / Processo")
    if not db_processos or processo_id_selecionado == NO_CASE_SELECTED:
        st.warning("Nenhum caso disponível para exclusão.")
    else:
        p_excluir = clone_process_data(db_processos[processo_id_selecionado])
        st.error(f"⚠️ Atenção: Você está prestes a excluir o caso **{processo_id_selecionado}** ({p_excluir.get('reclamante_nome', 'Não informado')}).")
        st.markdown("<br>", unsafe_allow_html=True)
        if not st.session_state.confirmar_exclusao_dupla:
            if st.button("🗑️ Solicitar Exclusão Definitiva"):
                st.session_state.confirmar_exclusao_dupla = True
                st.rerun()
        else:
            st.warning("🚨 TEM CERTEZA ABSOLUTA? Esta ação apagará permanentemente todos os dados deste caso na nuvem!")
            col_sim, col_nao = st.columns(2)
            with col_sim:
                if st.button("🔴 SIM, EXCLUIR PERMANENTEMENTE"):
                    try:
                        delete_process(processo_id_selecionado)
                    except RuntimeError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.confirmar_exclusao_dupla = False
                        st.session_state.processo_ativo = None
                        st.toast("🗑️ Processo excluído da nuvem!", icon="🚨")
                        st.rerun()
            with col_nao:
                if st.button("❌ Cancelar"):
                    st.session_state.confirmar_exclusao_dupla = False
                    st.rerun()

elif opcao == MENU_DOCX:
    st.markdown("### Geração do Documento Final em Word (.docx)")
    if not db_processos or processo_id_selecionado == NO_CASE_SELECTED:
        st.warning("Selecione um caso válido no menu lateral.")
    else:
        p = clone_process_data(db_processos[processo_id_selecionado])
        st.markdown(f"<p style='font-size: 17px;'>Caso selecionado: <b>{processo_id_selecionado}</b> — Segurado/Autor: <i>{p.get('reclamante_nome', '')}</i></p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📥 Gerar e Baixar Documento Oficial (.docx)"):
            validation = validate_process_data(p, for_generation=True)
            if not validation.is_valid:
                fields = ", ".join(format_missing_field_labels(validation.missing_required_fields))
                st.warning(f"Preencha os campos obrigatórios antes da geração do documento: {fields}.")
            else:
                try:
                    buffer, warnings = build_document_bytes(p)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Erro ao gerar documento: {exc}")
                else:
                    if warnings:
                        for warning in warnings:
                            st.warning(warning)
                    st.toast("✅ Documento Word Finalizado!", icon="📄")
                    st.download_button(
                        label="📥 Baixar Documento Oficial (.docx)",
                        data=buffer,
                        file_name=sanitize_output_filename(p.get("reclamante_nome", "Caso")),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
