"""DOCX sections shared by both document entry points, without inferred findings."""

import json

from docx import Document
from docx.shared import Inches, Pt, RGBColor

from core.config import LOGO_FILE
from core.extrajudicial import (
    CNIS_COLUMNS, DOCX_MARKER, ENV_COLUMNS, TEXT_FIELDS, export_payload,
    final_errors, legacy_state, text, validate,
)


def append_extrajudicial(doc, data, preliminary=False):
    """Append report body; calling exporter retains branding and photo handling."""
    doc.styles["Normal"].font.name = "Abadi"
    doc.styles["Normal"].font.size = Pt(11)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        doc.styles[name].font.color.rgb = RGBColor(27, 54, 93)

    def block(title, value):
        doc.add_heading(title, level=2)
        doc.add_paragraph(text(value) or "[Não informado — não presumido]")

    def fields(keys):
        for key in keys:
            doc.add_paragraph(f"{TEXT_FIELDS[key]}: {text(data.get(key)) or '[Não informado]'}")

    def table(title, rows, columns):
        doc.add_heading(title, level=2)
        if not rows:
            doc.add_paragraph("[Nenhum registro estruturado; consulte informações legadas]")
            return
        if len(columns) > 6:
            for index, row in enumerate(rows, 1):
                doc.add_heading(f"Registro {index} — período {text(row.get('periodo_id'))}", level=3)
                result = doc.add_table(rows=0, cols=2)
                result.style = "Table Grid"
                for column in columns:
                    cells = result.add_row().cells
                    cells[0].text = column
                    cells[1].text = text(row.get(column)) or "[Não informado]"
            return
        result = doc.add_table(rows=1, cols=len(columns))
        result.style = "Table Grid"
        for cell, column in zip(result.rows[0].cells, columns):
            cell.text = column
        for row in rows:
            for cell, column in zip(result.add_row().cells, columns):
                cell.text = text(row.get(column))

    block("1. NATUREZA, IDENTIFICAÇÃO E RESPONSABILIDADE TÉCNICA",
          f"Natureza: {data.get('natureza_laudo', 'Não informado')}\n"
          f"Modo temporal: {data.get('modo_temporal', 'Não informado')}\n"
          f"Grau de risco: {data.get('estabelecimento_grau_risco', 'Não informado')}")
    fields(("reclamante_nome", "reclamante_cpf", "segurado_nascimento", "profissao_cargo",
            "reclamada_nome", "reclamada_cnpj", "setor", "data_admissao",
            "estabelecimento_endereco", "estabelecimento_cnae",
            "responsavel_nome", "responsavel_conselho", "responsavel_art"))
    table("2. DELIMITAÇÃO DOS PERÍODOS CNIS / PROFISSIOGRAFIA POR PERÍODO",
          data.get("cnis_periodos", []), CNIS_COLUMNS)
    block("3. RELATO INICIAL / ATIVIDADES DECLARADAS", data.get("relato_inicial"))
    block("PROFISSIOGRAFIA REAL / AMBIENTE / ROTINA", data.get("profissiografia_real"))
    block("4. APR PRESUMIDA — HIPÓTESES, NÃO AGENTES COMPROVADOS",
          "\n".join(f"{TEXT_FIELDS[key]}: {text(data.get(key)) or '[Não informado]'}"
                    for key in ("apr_fisicos", "apr_quimicos", "apr_biologicos")))
    block("FONTES DOCUMENTAIS E LIMITAÇÕES", data.get("fontes_documentais"))
    block("ROTEIRO DE VISTORIA / DOCUMENTOS A SOLICITAR", data.get("roteiro_vistoria"))
    fields(("doc_ppp", "doc_pgr", "doc_outros"))
    block("5. AGENTES OBSERVADOS E EVIDÊNCIAS", data.get("agentes_observados"))
    table("REGISTROS AMBIENTAIS POR PERÍODO", data.get("avaliacoes_ambientais", []), ENV_COLUMNS)
    block("6. METODOLOGIA DE AVALIAÇÃO", data.get("doc_ltcat"))
    block("ENQUADRAMENTO LEGAL / CRITÉRIOS POR PERÍODO", data.get("enquadramento_legal_prev"))
    block("7. EXTEMPORANEIDADE — VERIFICAÇÃO HISTÓRICA",
          "\n".join(f"{label}: {legacy_state(data, key)}" for key, label in (
              ("extemp_layout", "Mudança de layout"),
              ("extemp_maquinas", "Substituição de máquinas"), ("extemp_epc", "Alteração de EPC"))))
    block("EVIDÊNCIAS DE COMPARAÇÃO HISTÓRICA", data.get("extemp_evidencias"))
    block("FUNDAMENTAÇÃO DE EQUIVALÊNCIA / LIMITAÇÕES", data.get("extemp_justificativa"))
    block("8. EPC E MEDIDAS DE CONTROLE", data.get("medidas_epc"))
    table("REGISTROS DE EPI", data.get("quadro_epis", []), ("descricao", "ca", "data_entrega", "obs"))
    block("ANÁLISE CRÍTICA DE EPI", data.get("analise_epis_critica"))
    block("9. DILIGÊNCIA / DECLARAÇÕES / MEDIÇÕES",
          "\n".join(f"{label}: {text(data.get(key)) or '[Não informado]'}" for key, label in (
              ("campo_data", "Data"), ("campo_horario", "Horário"), ("local_diligencia", "Local"),
              ("presentes_pericia", "Presentes"), ("campo_declaracoes_autor", "Declarações do segurado"),
              ("campo_declaracoes_reu", "Declarações do empregador"), ("campo_medicoes", "Medições"))))
    block("10. CONCLUSÃO TÉCNICA DO PROFISSIONAL", data.get("conclusao_tecnica"))
    block("11. DADOS DE APOIO AO PPP — NÃO É PPP OFICIAL ASSINADO",
          "Dados administrativos na seção 1; atividades e períodos na seção 2; "
          "agentes, técnica, exposição, EPC/EPI, CA e responsáveis na seção 5. "
          "Necessária conferência, emissão e assinatura pelos responsáveis legais. "
          "Este documento não constitui reconhecimento automático de tempo especial.")
    block("12. REVISÃO E ASSINATURA",
          "RASCUNHO / PRÉ-PERICIAL — revisão final pendente" if preliminary
          else "Evidências e conclusão revisadas pelo profissional no aplicativo. "
               "Documento gerado manualmente, sem assinatura digital. Assinatura: ____________________")
    if preliminary:
        block("CHECKLIST PRÉ-PERICIAL",
              "[ ] Conferir períodos e documentos\n[ ] Verificar fontes geradoras e rotina\n"
              "[ ] Conferir instrumento e calibração\n[ ] Documentar mudanças históricas\n"
              "[ ] Conferir EPC, entrega, troca, higiene, CA e uso de EPI\n"
              "[ ] Fotografar ambiente, máquinas, rótulos e medições\n[ ] Revisar conclusão")
    doc.add_heading("DADOS ESTRUTURADOS PARA REIMPORTAÇÃO (SEM FOTOS / REVISÃO)", level=2)
    doc.add_paragraph(DOCX_MARKER)
    doc.add_paragraph(json.dumps(export_payload(data), ensure_ascii=False))


def build_extrajudicial_bytes(data, preliminary=False):
    import io
    from pathlib import Path
    from core.photo_storage import resolver_bytes_foto

    errors = validate(data) if preliminary else final_errors(data)
    if errors:
        raise ValueError("\n".join(errors))
    doc = Document()
    if Path(LOGO_FILE).is_file():
        doc.add_picture(LOGO_FILE, width=Inches(2))
    doc.add_heading("GRAHL PERÍCIAS", level=0)
    doc.add_heading("RELATÓRIO PRÉ-PERICIAL / RASCUNHO" if preliminary
                    else "LAUDO TÉCNICO DE CONDIÇÕES AMBIENTAIS DO TRABALHO (LTCAT)", level=1)
    append_extrajudicial(doc, data, preliminary=preliminary)
    warnings = []
    for index, photo in enumerate(data.get("campo_fotos", []), 1):
        try:
            doc.add_picture(io.BytesIO(resolver_bytes_foto(photo)), width=Inches(4.5))
            doc.add_paragraph(f"Figura {index}: {text(photo.get('legenda'))} {text(photo.get('gps'))}")
        except Exception as exc:
            warnings.append(f"Foto {index} não incluída: {exc}")
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer, warnings
