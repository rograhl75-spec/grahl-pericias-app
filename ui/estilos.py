import streamlit as st


def aplicar_estilos():
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
    .stButton button { background-color: #1B365D !important; color: white !important; font-weight: 700 !important; border-radius: 8px !important; padding: 0.5rem 1.2rem; border: none; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); transition: all 0.3s ease; }
    .stButton button:hover { background-color: #2D4A7C !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #E2E8F0; border-radius: 8px 8px 0px 0px; color: #1B365D; font-weight: 700; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #1B365D !important; color: white !important; }
    .campo-inline-error {
        color: #B91C1C;
        font-size: 0.88rem;
        font-weight: 600;
        margin: -0.2rem 0 0.5rem 0;
    }
    .campo-shortcuts-title {
        color: #1B365D;
        font-size: 0.95rem;
        font-weight: 700;
        margin: 0.75rem 0 0.5rem 0;
    }
    @media (max-width: 768px) {
        div.block-container { padding: 1rem 0.85rem 3rem 0.85rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 6px; overflow-x: auto; }
        .stTabs [data-baseweb="tab"] { min-width: 180px; padding: 10px 14px; }
        .stButton button {
            min-height: 44px;
        }
    }
    </style>
    """,
        unsafe_allow_html=True,
    )
