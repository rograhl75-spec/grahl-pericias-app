"""Single renderer for the active extrajudicial workflow."""

import copy
import hashlib
import io
import json

import pandas as pd
import streamlit as st
from docx import Document

from core.extrajudicial import (
    CNIS_COLUMNS, IMPORT_FIELDS, SELECT_FIELDS, TABLE_FIELDS, TEXT_FIELDS,
    apply_import, export_payload, invalidate_review, legacy_state,
    parse_cnis_csv, parse_docx, parse_json, review, text, validate,
    final_errors,
)


def render_extrajudicial(case_id, data, save, legacy_parser):
    prefix = f"extra_{case_id}_"
    st.caption("Preenchimento e geração manuais, sem IA. APR presumida não comprova exposição. "
               "Dados PPP são apoio técnico, não PPP oficial assinado.")
    _render_import(prefix, data, lambda candidate: save(case_id, candidate), legacy_parser)
    if data.get("data_admissao") and not data.get("cnis_periodos"):
        st.info("Período legado preservado. Cadastre os períodos estruturados para a revisão final.")

    candidate = copy.deepcopy(data)
    with st.form(prefix + "dados"):
        tabs = st.tabs(["1️⃣ Identificação & CNIS", "2️⃣ APR & Planejamento",
                        "3️⃣ Vistoria & Exposição", "4️⃣ LTCAT & Revisão"])

        def fields(keys):
            for key in keys:
                value = text(data.get(key))
                widget = st.text_area if key in NARRATIVES else st.text_input
                candidate[key] = widget(TEXT_FIELDS[key], value=value, key=prefix + key)

        def select(key, label):
            options = list(SELECT_FIELDS[key])
            value = (legacy_state(data, key.removesuffix("_estado"))
                     if key.endswith("_estado") else data.get(key, options[0]))
            if value not in options:
                options.append(text(value))
            candidate[key] = st.selectbox(
                label, options, index=options.index(value), key=prefix + key,
            )

        def table(key, help_text):
            st.caption(help_text)
            rows = data.get(key, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                st.error(f"{key}: estrutura legada inválida; corrija antes de salvar.")
                return
            columns = TABLE_FIELDS[key]
            edited = st.data_editor(
                pd.DataFrame(rows, columns=columns).fillna(""),
                num_rows="dynamic", key=prefix + key, width="stretch",
                column_config={column: st.column_config.TextColumn(column) for column in columns},
            )
            records = edited.fillna("").to_dict("records")
            candidate[key] = [
                {column: text(row[column]).strip() for column in columns}
                for row in records if any(text(value).strip() for value in row.values())
            ]

        with tabs[0]:
            fields(("reclamante_nome", "reclamante_cpf", "segurado_nascimento",
                    "profissao_cargo", "reclamada_nome", "reclamada_cnpj", "setor",
                    "data_admissao", "estabelecimento_endereco", "estabelecimento_cnae"))
            select("estabelecimento_grau_risco", "Grau de risco")
            select("natureza_laudo", "Natureza do laudo")
            select("modo_temporal", "Modo temporal")
            st.subheader("Períodos CNIS")
            table("cnis_periodos", "periodo_id: identificador único e estável (ex.: P1). "
                  "Datas AAAA-MM-DD; fim vazio = em aberto. Condição: CLT, Autônomo, "
                  "Cooperado, Outro ou Não informado. CNPJ opcional (14 dígitos).")
            fields(("relato_inicial",))
        with tabs[1]:
            st.subheader("APR presumida — hipóteses a verificar, não constatações")
            fields(("apr_fisicos", "apr_quimicos", "apr_biologicos",
                    "fontes_documentais", "roteiro_vistoria", "doc_ppp", "doc_pgr", "doc_outros"))
        with tabs[2]:
            st.info("Data, presença, declarações, medições, fotos, GPS, câmera e voz "
                    "continuam na tela compartilhada 🚜 Diligência de Campo & Fotos.")
            fields(("profissiografia_real", "agentes_observados", "medidas_epc"))
            st.subheader("Registros ambientais por período — suporte ao PPP")
            table("avaliacoes_ambientais", "Referencie periodo_id do CNIS. tipo: F, Q ou B. "
                  "epc/epi: eficácia Sim, Não ou Não informado; nunca presumida. "
                  "Intensidade/unidade podem ficar vazias em avaliação qualitativa. "
                  "Registre fonte, via, exposição, método, instrumento/calibração e responsável.")
            st.subheader("Extemporaneidade — não inferir equivalência da ausência de informação")
            select("extemp_layout_estado", "Houve mudança no layout?")
            select("extemp_maquinas_estado", "Houve substituição de máquinas?")
            select("extemp_epc_estado", "Houve alteração em EPCs?")
            fields(("extemp_evidencias", "extemp_justificativa"))
            table("quadro_epis", "EPIs: descrição, CA, entrega/periodicidade e evidências de eficácia.")
            fields(("analise_epis_critica",))
        with tabs[3]:
            fields(("responsavel_nome", "responsavel_conselho", "responsavel_art",
                    "enquadramento_legal_prev", "doc_ltcat", "conclusao_tecnica"))
            st.caption("Salve primeiro. Alterações em evidências ou conclusão invalidam a revisão. "
                       "A revisão é uma ação explícita abaixo; rascunhos podem permanecer incompletos.")
        submitted = st.form_submit_button("💾 Salvar rascunho extrajudicial", type="primary")
    if submitted:
        errors = validate(candidate)
        if errors:
            for error in errors:
                st.error(error)
        elif save(case_id, invalidate_review(candidate)):
            st.success("Rascunho salvo.")
            st.rerun()

    errors = final_errors(data)
    st.caption("Revisão final pendente" if errors else "Revisão final válida para as evidências salvas")
    with st.expander("Pendências para o documento final", expanded=bool(errors)):
        for error in errors:
            st.write("• " + error)
    confirmed = st.checkbox("Revisei os dados salvos, evidências e conclusão técnica",
                            key=prefix + "confirmar_revisao")
    if st.button("✅ Registrar revisão profissional", key=prefix + "revisar",
                 disabled=not confirmed):
        try:
            candidate = review(data)
            if save(case_id, candidate):
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.download_button(
        "📤 Exportar dados estruturados (JSON)", json.dumps(export_payload(data), ensure_ascii=False, indent=2),
        file_name=f"Extrajudicial_{case_id}.json", mime="application/json", key=prefix + "json",
    )


NARRATIVES = {
    "relato_inicial", "profissiografia_real", "apr_fisicos", "apr_quimicos",
    "apr_biologicos", "fontes_documentais", "roteiro_vistoria", "agentes_observados",
    "medidas_epc", "extemp_evidencias", "extemp_justificativa", "analise_epis_critica",
    "enquadramento_legal_prev", "doc_ltcat", "conclusao_tecnica", "doc_ppp", "doc_pgr", "doc_outros",
}


def _render_import(prefix, data, save, legacy_parser):
    with st.expander("📥 Importar e revisar antes de aplicar"):
        upload = st.file_uploader("DOCX, CNIS CSV ou dados JSON", type=["docx", "csv", "json"],
                                 key=prefix + "import")
        if upload is None:
            return
        try:
            raw = upload.getvalue()
            if upload.name.lower().endswith(".csv"):
                incoming = {"cnis_periodos": parse_cnis_csv(raw)}
            elif upload.name.lower().endswith(".json"):
                incoming = parse_json(raw)
            else:
                incoming = parse_docx(Document(io.BytesIO(raw)), legacy_parser)
            digest = hashlib.sha256(raw).hexdigest()[:16]
            st.write("Prévia: nenhum dado foi salvo. Campos selecionados substituem o conteúdo atual, "
                     "inclusive valores vazios e tabelas inteiras. Fotos, IDs e revisão não são importados.")
            st.json(incoming)
            selectable = sorted(set(incoming) & IMPORT_FIELDS)
            selected = st.multiselect("Campos a aplicar", selectable, default=[],
                                      key=prefix + "campos_" + digest)
            confirm = st.checkbox("Confirmo a substituição dos campos selecionados",
                                  key=prefix + "aplicar_confirm_" + digest)
            if st.button("Aplicar importação revisada", key=prefix + "aplicar_" + digest,
                         disabled=not (confirm and selected)):
                candidate = apply_import(data, incoming, selected, confirmed=confirm)
                if save(candidate):
                    for key in list(st.session_state):
                        if key.startswith(prefix):
                            del st.session_state[key]
                    st.rerun()
        except Exception as exc:
            st.error(f"Importação rejeitada: {exc}")
