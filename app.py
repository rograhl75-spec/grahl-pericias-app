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
    "campo_Esse comportamento de voltar sempre para o "processo 1" ou entrar em loop é um sintoma clássico de perda de variáveis durante o recarregamento da interface, algo muito comum em aplicações Streamlit.

Como o framework executa o código de cima a baixo a cada clique ou interação na tela, qualquer variável de controle de estado (como a que define qual processo está aberto) que não esteja guardada no `st.session_state` será resetada para o valor inicial.

Para resolver isso, você precisa garantir que o aplicativo "lembre" em qual processo você está utilizando o estado da sessão.

**Como verificar e corrigir:**

Procure no seu código onde você define qual processo/caso deve aparecer na tela e certifique-se de que a lógica segue este padrão:

```python
import streamlit as st

# 1. Inicialize a variável de controle apenas se ela não existir no session_state
if 'processo_atual' not in st.session_state:
    st.session_state.processo_atual = 1

# 2. Use a variável do session_state para carregar os dados corretos na tela
st.write(f"Editando o Processo/Caso: {st.session_state.processo_atual}")

# 3. Ao salvar ou avançar, atualize o valor no session_state e force o recarregamento
if st.button("Salvar e ir para o próximo"):
    st.session_state.processo_atual += 1
    st.rerun()
