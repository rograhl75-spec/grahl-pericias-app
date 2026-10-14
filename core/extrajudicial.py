"""Manual extrajudicial records, validation and non-destructive interchange."""

import copy
import csv
import hashlib
import io
import json
import re
from datetime import datetime


CNIS_COLUMNS = (
    "periodo_id", "inicio", "fim", "empresa", "cnpj", "condicao",
    "cargo", "setor", "atividade",
)
ENV_COLUMNS = (
    "periodo_id", "tipo", "agente", "intensidade", "unidade", "metodo",
    "fonte", "via", "exposicao", "epc", "epi", "ca", "responsavel",
    "conselho", "instrumento", "calibracao",
)
UNKNOWN = "Não informado"
CHOICES = (UNKNOWN, "Sim", "Não")
TEXT_FIELDS = {
    "reclamante_nome": "Nome do Segurado",
    "reclamante_cpf": "CPF / NIT / PIS",
    "segurado_nascimento": "Data de Nascimento",
    "profissao_cargo": "Profissão / Cargo Avaliado",
    "reclamada_nome": "Razão Social da Empresa / Tomador",
    "reclamada_cnpj": "CNPJ da Empresa",
    "setor": "Setor / Lotação / Local",
    "data_admissao": "Período de Trabalho (legado)",
    "estabelecimento_endereco": "Endereço do estabelecimento",
    "estabelecimento_cnae": "CNAE",
    "responsavel_nome": "Nome do responsável técnico",
    "responsavel_conselho": "Conselho / UF / número",
    "responsavel_art": "ART / responsabilidade técnica aplicável",
    "relato_inicial": "Relato inicial / atividades declaradas",
    "profissiografia_real": "Profissiografia observada / rotina / máquinas / ambiente",
    "apr_fisicos": "Agentes físicos presumidos (APR)",
    "apr_quimicos": "Agentes químicos presumidos (APR)",
    "apr_biologicos": "Agentes biológicos presumidos (APR)",
    "fontes_documentais": "Fontes documentais, datas, origem e limitações",
    "roteiro_vistoria": "Roteiro de vistoria / documentos a solicitar",
    "agentes_observados": "Agentes efetivamente observados e evidências",
    "medidas_epc": "EPCs instalados / funcionamento / evidência de eficácia",
    "extemp_evidencias": "Evidências históricas / mudanças / comparação por período",
    "extemp_justificativa": "Fundamentação de equivalência e limitações",
    "analise_epis_critica": "Análise crítica de EPIs / entrega / troca / higiene / eficácia",
    "enquadramento_legal_prev": "Enquadramento legal e critérios aplicáveis aos períodos",
    "doc_ltcat": "Metodologia de avaliação / procedimentos / limitações",
    "conclusao_tecnica": "Conclusão técnica do profissional (não automática)",
    "doc_ppp": "PPP apresentado / análise documental",
    "doc_pgr": "PGR apresentado / análise documental",
    "doc_outros": "Outros documentos",
}
SELECT_FIELDS = {
    "natureza_laudo": (UNKNOWN, "Individual", "Coletivo"),
    "modo_temporal": (UNKNOWN, "Contemporâneo", "Extemporâneo", "Misto"),
    "estabelecimento_grau_risco": (UNKNOWN, "1", "2", "3", "4"),
    "extemp_layout_estado": CHOICES,
    "extemp_maquinas_estado": CHOICES,
    "extemp_epc_estado": CHOICES,
}
TABLE_FIELDS = {
    "cnis_periodos": CNIS_COLUMNS,
    "avaliacoes_ambientais": ENV_COLUMNS,
    "quadro_epis": ("descricao", "ca", "data_entrega", "obs"),
}
IMPORT_FIELDS = set(TEXT_FIELDS) | set(SELECT_FIELDS) | set(TABLE_FIELDS) | {
    "processo_num", "papel_profissional", "extemp_layout", "extemp_maquinas", "extemp_epc",
    "campo_data", "campo_horario", "local_diligencia", "presentes_pericia",
    "campo_declaracoes_autor", "campo_declaracoes_reu", "campo_medicoes",
}
BOOL_FIELDS = {"extemp_layout", "extemp_maquinas", "extemp_epc"}
SCHEMA = "grahl-extrajudicial-v1"
DOCX_MARKER = "GRAHL_DADOS_ESTRUTURADOS_V1"


def text(value):
    return "" if value is None else str(value)


def new_defaults():
    """Only new extrajudicial cases: never migrate legacy conclusions or APR."""
    data = {key: "" for key in TEXT_FIELDS}
    data.update({key: UNKNOWN for key in SELECT_FIELDS})
    data.update({key: [] for key in TABLE_FIELDS})
    data.update({
        "papel_profissional": "Perito Extrajudicial / Consultor",
        "extemp_layout": None, "extemp_maquinas": None, "extemp_epc": None,
        "revisado_profissional": False, "revisao_evidencias": "",
    })
    return data


def evidence_hash(data):
    evidence = {key: data[key] for key in IMPORT_FIELDS | {"campo_fotos"} if key in data}
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def invalidate_review(data):
    result = copy.deepcopy(data)
    if result.get("revisao_evidencias") != evidence_hash(result):
        result["revisado_profissional"] = False
        result["revisao_evidencias"] = ""
    return result


def legacy_state(data, name):
    key = f"{name}_estado"
    if key in data:
        return data[key]
    value = data.get(name)
    return "Sim" if value is True else "Não" if value is False else UNKNOWN


def defaults_for_existing(data):
    result = new_defaults()
    for key in BOOL_FIELDS:
        if isinstance(data.get(key), bool):
            result[f"{key}_estado"] = legacy_state(data, key)
    return result


def _date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("formato AAAA-MM-DD")
    return datetime.strptime(value, "%Y-%m-%d").date()


def validate(data, final=False):
    errors = []
    for key in (set(TEXT_FIELDS) | (IMPORT_FIELDS - set(TABLE_FIELDS) - BOOL_FIELDS - set(SELECT_FIELDS))):
        if key in data and not isinstance(data[key], str):
            errors.append(f"{key}: texto esperado.")
    for key, options in SELECT_FIELDS.items():
        if key in data and data[key] not in options:
            errors.append(f"{key}: opção inválida.")
    for key, columns in TABLE_FIELDS.items():
        rows = data.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            errors.append(f"{key}: tabela inválida.")
            continue
        for index, row in enumerate(rows, 1):
            if set(row) - set(columns) or any(
                not isinstance(value, str) for value in row.values()
            ):
                errors.append(f"{key}, linha {index}: colunas ou valores inválidos.")
    periods = data.get("cnis_periodos", [])
    if not isinstance(periods, list) or any(not isinstance(r, dict) for r in periods):
        periods = []
    ids = set()
    for index, row in enumerate(periods, 1):
        prefix = f"CNIS, linha {index}"
        ident = text(row.get("periodo_id")).strip()
        if not ident or ident in ids:
            errors.append(f"{prefix}: periodo_id obrigatório e único.")
        ids.add(ident)
        for field in ("inicio", "empresa", "condicao", "cargo", "setor", "atividade"):
            if not text(row.get(field)).strip():
                errors.append(f"{prefix}: {field} obrigatório.")
        try:
            start = _date(text(row.get("inicio")))
            if row.get("fim") and _date(text(row["fim"])) < start:
                errors.append(f"{prefix}: fim anterior ao início.")
        except (ValueError, TypeError):
            errors.append(f"{prefix}: datas devem ser válidas no formato AAAA-MM-DD.")
        if row.get("condicao") not in ("CLT", "Autônomo", "Cooperado", "Outro", UNKNOWN):
            errors.append(f"{prefix}: condição inválida.")
        if row.get("cnpj") and (
            not re.fullmatch(r"[\d./-]+", text(row["cnpj"]))
            or len(re.sub(r"\D", "", text(row["cnpj"]))) != 14
        ):
            errors.append(f"{prefix}: CNPJ deve conter 14 dígitos.")
    env = data.get("avaliacoes_ambientais", [])
    if not isinstance(env, list) or any(not isinstance(r, dict) for r in env):
        env = []
    for index, row in enumerate(env, 1):
        prefix = f"Avaliação ambiental, linha {index}"
        if row.get("periodo_id") not in ids:
            errors.append(f"{prefix}: periodo_id não existe no CNIS.")
        if row.get("tipo") not in ("F", "Q", "B"):
            errors.append(f"{prefix}: tipo deve ser F, Q ou B.")
        for field in ("agente", "metodo", "fonte", "via", "exposicao"):
            if not text(row.get(field)).strip():
                errors.append(f"{prefix}: {field} obrigatório.")
        for field in ("epc", "epi"):
            if row.get(field) not in CHOICES:
                errors.append(f"{prefix}: {field} deve ser Sim, Não ou Não informado.")
        if final:
            for field in ("responsavel", "conselho"):
                if not text(row.get(field)).strip():
                    errors.append(f"{prefix}: {field} obrigatório para revisão final.")
    if final:
        for key in ("reclamante_nome", "reclamante_cpf", "reclamada_nome",
                    "responsavel_nome", "responsavel_conselho", "doc_ltcat",
                    "conclusao_tecnica", "fontes_documentais"):
            if not text(data.get(key)).strip():
                errors.append(f"{TEXT_FIELDS[key]}: obrigatório para revisão final.")
        for key in ("natureza_laudo", "modo_temporal"):
            if data.get(key, UNKNOWN) == UNKNOWN:
                errors.append(f"{key}: selecione uma opção para revisão final.")
        if not periods:
            errors.append("Cadastre os períodos CNIS antes da revisão final.")
        if data.get("modo_temporal") in ("Extemporâneo", "Misto"):
            for key in ("extemp_evidencias", "extemp_justificativa"):
                if not text(data.get(key)).strip():
                    errors.append(f"{TEXT_FIELDS[key]}: obrigatório para laudo extemporâneo.")
        if not env and not text(data.get("agentes_observados")).strip():
            errors.append("Registre avaliações ambientais ou explique a ausência de agentes observados.")
    return errors


def final_errors(data):
    errors = validate(data, final=True)
    try:
        unchanged = data.get("revisao_evidencias") == evidence_hash(data)
    except (TypeError, ValueError):
        unchanged = False
    if data.get("revisado_profissional") is not True or not unchanged:
        errors.append("A revisão profissional está pendente ou foi invalidada por alterações.")
    return errors


def review(data):
    errors = validate(data, final=True)
    if errors:
        raise ValueError("\n".join(errors))
    result = copy.deepcopy(data)
    result["revisado_profissional"] = True
    result["revisao_evidencias"] = evidence_hash(result)
    return result


def parse_cnis_csv(raw):
    try:
        source = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        reader = csv.DictReader(io.StringIO(source), strict=True)
        if reader.fieldnames != list(CNIS_COLUMNS):
            raise ValueError("Cabeçalho CSV deve ser exatamente: " + ",".join(CNIS_COLUMNS))
        rows = list(reader)
        if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("CSV vazio ou com número incorreto de colunas.")
        errors = validate({"cnis_periodos": rows})
        if errors:
            raise ValueError("\n".join(errors))
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(f"CSV inválido (UTF-8, separador vírgula): {exc}") from exc


def export_payload(data):
    return {"schema": SCHEMA, "dados": {
        key: copy.deepcopy(data[key]) for key in sorted(IMPORT_FIELDS) if key in data
    }}


def recognized_import(data):
    if not isinstance(data, dict):
        raise ValueError("O documento deve conter um objeto de campos reconhecidos.")
    result = {}
    for key, value in data.items():
        if key not in IMPORT_FIELDS:
            continue
        if key in TABLE_FIELDS:
            if not isinstance(value, list):
                raise ValueError(f"{key}: lista esperada.")
        elif key in BOOL_FIELDS:
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{key}: booleano esperado.")
        elif not isinstance(value, str):
            raise ValueError(f"{key}: texto esperado.")
        result[key] = copy.deepcopy(value)
    if not result:
        raise ValueError("Nenhum campo reconhecido para importar.")
    errors = validate(result)
    if errors:
        raise ValueError("\n".join(errors))
    return result


def parse_json(raw):
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("JSON inválido.") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("Formato esperado: " + SCHEMA)
    return recognized_import(payload.get("dados"))


def parse_docx(doc, legacy_parser):
    lines = [paragraph.text for paragraph in doc.paragraphs]
    for index, line in enumerate(lines):
        if line == DOCX_MARKER:
            if index + 1 >= len(lines):
                raise ValueError("Bloco estruturado incompleto.")
            return parse_json(lines[index + 1])
    # The legacy parser emits empty defaults even for absent labels. Only the
    # structured payload can distinguish deliberate clears from missing fields.
    parsed = {key: value for key, value in legacy_parser(doc).items()
              if value is False or bool(value)}
    return recognized_import(parsed)


def apply_import(current, incoming, selected, confirmed=False):
    """Apply only explicitly reviewed fields; never replace revision, IDs or photos."""
    if not confirmed:
        raise ValueError("Confirme a revisão antes de aplicar.")
    safe = recognized_import(incoming)
    if not set(selected) <= set(safe):
        raise ValueError("Seleção contém campo não reconhecido.")
    result = copy.deepcopy(current)
    for key in selected:
        result[key] = copy.deepcopy(safe[key])
    errors = validate(result)
    if errors:
        raise ValueError("\n".join(errors))
    return invalidate_review(result)
