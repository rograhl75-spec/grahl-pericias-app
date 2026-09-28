from __future__ import annotations

import re
from typing import Iterable

from .utils import is_placeholder_text, normalize_multiline_text, remover_acentos

LABELS_TO_BREAK = [
    r"Número do Processo", r"Órgão Julgador / Vara", r"Órgão Julgador", r"Vara",
    r"Data de Autuação", r"Ajuizamento", r"Valor da Causa", r"Rito Processual",
    r"Reclamante \(Autor/Autora\)", r"Reclamante", r"Nome do Segurado",
    r"CPF/NIT", r"CPF", r"CNPJ", r"Data de Nascimento", r"Reclamada \(Ré/Empresa\)",
    r"Reclamada \(Ré / Empresa\)", r"Reclamada", r"Empresa / Tomador", r"Data de Admissão",
    r"Status do Contrato", r"Período Imprescrito", r"Cargo\(s\) / Função\(ões\)",
    r"Profissão / Cargo", r"Setor / Lotação / Local", r"Última Remuneração",
    r"Objeto da Perícia", r"Atividades Descritas", r"Atividades Típicas",
    r"Relato Inicial", r"Agentes Nocivos / Riscos Alegados", r"Agentes Nocivos",
    r"Agentes Físicos", r"Agentes Químicos", r"Agentes Biológicos",
    r"Enquadramento Legal", r"Pedidos Técnicos", r"Preliminares Periciais",
    r"Defesa de Mérito", r"Fase Processual Atual", r"Fase Processual", r"Data da Vistoria",
    r"Horário", r"Local / Endereço", r"LTCAT", r"Laudo de Insalubridade", r"PPP",
    r"PGR / PPRA / PCMAT", r"PGR", r"Ordens de Serviço", r"ASOs / PCMSO", r"ASOs",
    r"Outros Documentos", r"Síntese e Análise", r"9\.1\. Quesitos", r"9\.2\. Quesitos",
    r"9\.3\. Quesitos",
]

FIELD_MATCHERS = [
    ("número do processo", "processo_num"), ("órgão julgador", "orgao_julgador"),
    ("vara", "orgao_julgador"), ("data de autuação", "data_autuacao"),
    ("ajuizamento", "data_autuacao"), ("valor da causa", "valor_causa"),
    ("rito processual", "rito_processual"), ("reclamante", "reclamante_nome"),
    ("nome do segurado", "reclamante_nome"), ("cpf", "reclamante_cpf"), ("nit", "reclamante_cpf"),
    ("data de nascimento", "segurado_nascimento"), ("reclamada", "reclamada_nome"),
    ("empresa / tomador", "reclamada_nome"), ("razão social", "reclamada_nome"), ("cnpj", "reclamada_cnpj"),
    ("data de admissão", "data_admissao"), ("status do contrato", "status_contrato"),
    ("período imprescrito", "periodo_imprescrito"), ("cargo", "cargos"), ("função", "cargos"),
    ("profissão", "profissao_cargo"), ("setor", "setor"), ("lotação", "setor"),
    ("última remuneração", "ultima_remuneracao"), ("objeto da perícia", "objeto_pericia"),
    ("atividades", "atividades_inicial"), ("relato inicial", "relato_inicial"),
    ("agentes nocivos", "agentes_alegados"), ("agentes físicos", "apr_fisicos"),
    ("agentes químicos", "apr_quimicos"), ("agentes biológicos", "apr_biologicos"),
    ("enquadramento legal", "enquadramento_legal_prev"), ("pedidos técnicos", "pedidos_tecnicos"),
    ("preliminares periciais", "preliminares_periciais"), ("defesa de mérito", "defesa_merito_sst"),
    ("fase processual", "fase_processual"), ("data da vistoria", "campo_data"),
    ("horário", "campo_horario"), ("local", "local_diligencia"), ("endereço", "local_diligencia"),
    ("ltcat", "doc_ltcat"), ("laudo", "doc_laudo"), ("ppp", "doc_ppp"), ("pgr", "doc_pgr"),
    ("ppra", "doc_pgr"), ("ordens de serviço", "doc_os"), ("aso", "doc_asos"), ("pcmso", "doc_asos"),
    ("outros documentos", "doc_outros"), ("9.1. quesitos do juízo", "quesitos_juizo"),
    ("9.2. quesitos do reclamante", "quesitos_autor"), ("9.3. quesitos da reclamada", "quesitos_reu"),
]

PROTECTED_KEYS = {
    "reclamante_nome",
    "reclamante_cpf",
    "reclamada_nome",
    "reclamada_cnpj",
    "processo_num",
    "segurado_nascimento",
}


def _clean_value(value: object) -> str:
    cleaned = re.sub(r"_+", "", normalize_multiline_text(value))
    return cleaned.strip(" |")


def _valid_value(value: object) -> bool:
    cleaned = _clean_value(value)
    return bool(cleaned) and not is_placeholder_text(cleaned) and cleaned != "-"


def _table_rows(table) -> Iterable[list[str]]:
    for row in getattr(table, "rows", [])[1:]:
        yield [_clean_value(cell.text) for cell in getattr(row, "cells", [])]


def _extract_tables(doc) -> tuple[list[str], list[dict[str, str]]]:
    empresas_cnis: list[str] = []
    epis_extraidos: list[dict[str, str]] = []
    for table in getattr(doc, "tables", []):
        rows = getattr(table, "rows", [])
        if not rows:
            continue
        headers = [remover_acentos(cell.text) for cell in rows[0].cells]
        is_epi_table = any("descri" in h or "epi" in h for h in headers) and any("ca" in h or "cert" in h for h in headers)
        is_company_table = any(term in h for h in headers for term in ("empresa", "tomador", "vinculo", "vínculo"))

        if is_epi_table:
            for cells in _table_rows(table):
                desc = cells[0] if len(cells) > 0 else ""
                if not _valid_value(desc):
                    continue
                epis_extraidos.append(
                    {
                        "descricao": desc,
                        "ca": cells[1] if len(cells) > 1 else "",
                        "data_entrega": cells[2] if len(cells) > 2 else "",
                        "obs": cells[3] if len(cells) > 3 else "",
                    }
                )
        elif is_company_table:
            for cells in _table_rows(table):
                candidate = cells[1] if len(cells) > 1 else (cells[0] if cells else "")
                if _valid_value(candidate) and "AGRUPAMENTO" not in candidate.upper():
                    empresas_cnis.append(candidate)
    return empresas_cnis, epis_extraidos


def _inject_breaks(texto: str) -> str:
    result = texto
    for label in LABELS_TO_BREAK:
        pattern = rf"(?<!\n)({label}[\s]*:)"
        result = re.sub(pattern, r"\n\1", result, flags=re.IGNORECASE)
    return result


def _extract_identity_fields(texto: str, dados: dict[str, str]) -> None:
    patterns = {
        "reclamante_nome": r"(?:Reclamante \(Autor/Autora\)|Nome do Segurado|Reclamante|Autor/Autora|Nome)[\s:]*([^\n\|]+)",
        "reclamante_cpf": r"(?:CPF/NIT|CPF\s*/\s*NIT|CPF|NIT|PIS)[\s:]*([\d\.\-\/]+(?:\s*/\s*[\d\.\-\/]+)?)",
        "reclamada_nome": r"(?:Reclamada \(Ré/Empresa\)|Reclamada \(Ré / Empresa\)|Razão Social.*?|Empresa / Tomador|Reclamada|Empresa)[\s:]*([^\n\|]+)",
        "reclamada_cnpj": r"CNPJ[\s:]*([\d\.\-\/]+)",
        "processo_num": r"(?:Número do Processo|Processo)[\s:]*([^\n\|]+)",
    }
    for key, pattern in patterns.items():
        for match in re.findall(pattern, texto, re.IGNORECASE):
            value = _clean_value(match)
            if not _valid_value(value):
                continue
            if key == "reclamante_nome":
                value = re.sub(r"\(\s*(?:CPF|NIT|PIS).*?\)?$", "", value, flags=re.IGNORECASE).strip()
                value = value.rstrip("(").strip()
            elif key == "reclamada_nome":
                value = re.sub(r"\(?CNPJ.*$", "", value, flags=re.IGNORECASE).strip()
                value = value.rstrip("(").strip()
            if value and key not in dados:
                dados[key] = value
                break


def parse_pre_relatorio(doc) -> dict[str, object]:
    dados: dict[str, object] = {}
    linhas = [normalize_multiline_text(p.text) for p in getattr(doc, "paragraphs", []) if normalize_multiline_text(p.text)]
    empresas_cnis, epis_extraidos = _extract_tables(doc)
    if epis_extraidos:
        dados["quadro_epis"] = epis_extraidos

    texto = _inject_breaks("\n".join(linhas).replace("**", "").replace("*", ""))
    _extract_identity_fields(texto, dados)

    linhas_limpas = [line.strip() for line in texto.split("\n") if line.strip()]
    current_key: str | None = None
    current_buffer: list[str] = []

    def save_current() -> None:
        nonlocal current_key, current_buffer
        if not current_key or not current_buffer:
            return
        value = _clean_value("\n".join(current_buffer))
        if not _valid_value(value):
            return
        if current_key in PROTECTED_KEYS and dados.get(current_key):
            return
        dados[current_key] = value

    for linha in linhas_limpas:
        if re.match(r"^\d+(\.\d*)*[\s\.\-]+[A-ZÀ-Ú]", linha) and ":" not in linha:
            save_current()
            current_key = None
            current_buffer = []
            continue

        matched = False
        if ":" in linha:
            prefix, rest = [part.strip() for part in linha.split(":", 1)]
            prefix_normalized = remover_acentos(prefix)
            rest_clean = _clean_value(rest)

            if "advogado" in prefix_normalized:
                save_current()
                if _valid_value(rest_clean):
                    if "reclamante" in prefix_normalized:
                        dados["reclamante_adv"] = rest_clean
                    elif "reclamada" in prefix_normalized or "re" in prefix_normalized:
                        dados["reclamada_adv"] = rest_clean
                    elif not dados.get("reclamante_adv"):
                        dados["reclamante_adv"] = rest_clean
                    else:
                        dados["reclamada_adv"] = rest_clean
                current_key = None
                current_buffer = []
                continue

            matched_key = None
            for keyword, dest_key in FIELD_MATCHERS:
                if keyword in prefix_normalized and "acompanhante" not in prefix_normalized:
                    matched_key = dest_key
                    break

            if matched_key:
                save_current()
                current_key = matched_key
                if matched_key == "reclamante_nome":
                    match = re.search(r"(?:CPF|NIT|PIS)[\s:]*([\d\.\-\/]+)", rest_clean, re.IGNORECASE)
                    if match and not dados.get("reclamante_cpf"):
                        dados["reclamante_cpf"] = match.group(1).strip()
                    rest_clean = re.sub(r"\((?:CPF|NIT|PIS).*?\)", "", rest_clean, flags=re.IGNORECASE).strip()
                elif matched_key == "reclamada_nome":
                    match = re.search(r"CNPJ[\s:]*([\d\.\-\/]+)", rest_clean, re.IGNORECASE)
                    if match and not dados.get("reclamada_cnpj"):
                        dados["reclamada_cnpj"] = match.group(1).strip()
                    rest_clean = re.sub(r"\(CNPJ.*?\)", "", rest_clean, flags=re.IGNORECASE).strip()
                current_buffer = [rest_clean] if _valid_value(rest_clean) else []
                matched = True

        if not matched and current_key and _valid_value(linha):
            current_buffer.append(linha)

    save_current()

    if not dados.get("reclamada_nome") and empresas_cnis:
        dados["reclamada_nome"] = empresas_cnis[-1]
    if dados.get("profissao_cargo") and not dados.get("cargos"):
        dados["cargos"] = dados["profissao_cargo"]
    if dados.get("cargos") and not dados.get("profissao_cargo"):
        dados["profissao_cargo"] = dados["cargos"]
    return dados
