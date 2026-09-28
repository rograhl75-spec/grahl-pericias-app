from datetime import datetime


FIELD_RECORD_FIELDS = (
    {
        "key": "campo_data",
        "widget_key_prefix": "cd",
        "label": "1. Data da Vistoria *",
        "voice_label": "Data da Vistoria",
        "placeholder": "Digite ou dite a data da vistoria",
        "widget": "text_input",
        "required": True,
    },
    {
        "key": "campo_horario",
        "widget_key_prefix": "ch",
        "label": "2. Horário da Vistoria *",
        "voice_label": "Horário da Vistoria",
        "placeholder": "Digite ou dite o horário da vistoria",
        "widget": "text_input",
        "required": True,
    },
    {
        "key": "local_diligencia",
        "widget_key_prefix": "ld",
        "label": "3. Local da Vistoria *",
        "voice_label": "Local da Vistoria",
        "placeholder": "Digite ou dite o local da vistoria",
        "widget": "text_input",
        "required": True,
        "remember": True,
    },
    {
        "key": "presentes_pericia",
        "widget_key_prefix": "pp",
        "label": "4. Pessoas Presentes",
        "voice_label": "Pessoas Presentes",
        "placeholder": "Digite ou dite as pessoas presentes na vistoria",
        "widget": "text_area",
        "min_height": 80,
        "remember": True,
    },
    {
        "key": "campo_declaracoes_autor",
        "widget_key_prefix": "cda",
        "label": "5. Informações do Segurado / Autor",
        "voice_label": "Informações do Segurado / Autor",
        "placeholder": "Digite ou dite as informações do segurado ou autor",
        "widget": "text_area",
        "min_height": 120,
    },
    {
        "key": "campo_declaracoes_reu",
        "widget_key_prefix": "cdr",
        "label": "6. Informações do Empregador / Acompanhante",
        "voice_label": "Informações do Empregador / Acompanhante",
        "placeholder": "Digite ou dite as informações do empregador ou acompanhante",
        "widget": "text_area",
        "min_height": 120,
    },
    {
        "key": "campo_medicoes",
        "widget_key_prefix": "cm",
        "label": "7. Medições Realizadas",
        "voice_label": "Medições Realizadas",
        "placeholder": "Digite ou dite as medições realizadas em campo",
        "widget": "text_area",
        "min_height": 120,
    },
)


FIELD_RECORD_KEYS = tuple(field["key"] for field in FIELD_RECORD_FIELDS)
FIELD_RECORD_REQUIRED_KEYS = tuple(
    field["key"] for field in FIELD_RECORD_FIELDS if field.get("required")
)
FIELD_RECORD_REMEMBERED_KEYS = tuple(
    field["key"] for field in FIELD_RECORD_FIELDS if field.get("remember")
)


def obter_campos_registro_campo(dados_processo):
    return {
        key: str((dados_processo or {}).get(key, "") or "")
        for key in FIELD_RECORD_KEYS
    }


def validar_registro_campo(dados_processo):
    dados = obter_campos_registro_campo(dados_processo)
    erros = {}

    if not dados["campo_data"].strip():
        erros["campo_data"] = "Informe a data da vistoria."
    else:
        try:
            datetime.strptime(dados["campo_data"].strip(), "%d/%m/%Y")
        except ValueError:
            erros["campo_data"] = "Use o formato DD/MM/AAAA."

    if not dados["campo_horario"].strip():
        erros["campo_horario"] = "Informe o horário da vistoria."
    else:
        try:
            datetime.strptime(dados["campo_horario"].strip(), "%H:%M")
        except ValueError:
            erros["campo_horario"] = "Use o formato HH:MM."

    if not dados["local_diligencia"].strip():
        erros["local_diligencia"] = "Informe o local da vistoria."

    return erros


def atualizar_campos_memorizados(memorizados_atuais, dados_processo):
    atualizados = dict(memorizados_atuais or {})
    dados = obter_campos_registro_campo(dados_processo)

    for key in FIELD_RECORD_REMEMBERED_KEYS:
        valor = dados.get(key, "").strip()
        if valor:
            atualizados[key] = valor

    return atualizados
