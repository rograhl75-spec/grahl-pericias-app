"""
Interface Streamlit para importação de processos judiciais via PDF com Claude 3.5 Sonnet.
Fluxo completo: upload → validação → processamento → revisão → preenchimento automático
"""

import streamlit as st
import logging
import traceback
import hashlib
from typing import Dict, Tuple
from core.pdf_processor import (
    validar_pdfs,
    consolidar_multiplos_pdfs,
    calcular_total_paginas,
    validar_limite_paginas,
)
from core.ai_claude import analisar_processo_judicial, estimar_custo, estimar_chamadas_necessarias
from core.config import obter_app_config, obter_taxa_cambio_usd_brl
from core.cost_tracker import (
    criar_registro_importacao_ia,
    validar_limite_diario,
    calcular_custo_hoje,
    contar_chamadas_claude_hoje,
    validar_limite_chamadas_claude,
)

logger = logging.getLogger(__name__)

CAMPOS_IMPORTACAO_MAPEADOS = {
    "processo_num": "processo_num",
    "orgao_julgador": "orgao_julgador",
    "data_autuacao": "data_autuacao",
    "valor_causa": "valor_causa",
    "rito_processual": "rito_processual",
    "reclamante_nome": "reclamante_nome",
    "reclamante_cpf": "reclamante_cpf",
    "reclamante_adv": "reclamante_adv",
    "reclamada_nome": "reclamada_nome",
    "reclamada_cnpj": "reclamada_cnpj",
    "reclamada_adv": "reclamada_adv",
    "data_admissao": "data_admissao",
    "status_contrato": "status_contrato",
    "periodo_imprescrito": "periodo_imprescrito",
    "cargos": "cargos",
    "setor": "setor",
    "ultima_remuneracao": "ultima_remuneracao",
    "objeto_pericia": "objeto_pericia",
    "atividades_inicial": "atividades_inicial",
    "agentes_alegados": "agentes_alegados",
    "pedidos_tecnicos": "pedidos_tecnicos",
    "preliminares_periciais": "preliminares_periciais",
    "defesa_merito_sst": "defesa_merito_sst",
    "fase_processual": "fase_processual",
    "campo_data": "campo_data",
    "campo_horario": "campo_horario",
    "local_diligencia": "local_diligencia",
    "doc_ltcat": "doc_ltcat",
    "doc_laudo": "doc_laudo",
    "doc_ppp": "doc_ppp",
    "doc_pgr": "doc_pgr",
    "doc_os": "doc_os",
    "doc_asos": "doc_asos",
    "doc_outros": "doc_outros",
    "quesitos_juizo": "quesitos_juizo",
    "quesitos_autor": "quesitos_autor",
    "quesitos_reu": "quesitos_reu",
    "segurado_nascimento": "segurado_nascimento",
    "profissao_cargo": "profissao_cargo",
    "relato_inicial": "relato_inicial",
    "apr_fisicos": "apr_fisicos",
    "apr_quimicos": "apr_quimicos",
    "apr_biologicos": "apr_biologicos",
    "enquadramento_legal_prev": "enquadramento_legal_prev",
    "presentes_pericia": "presentes_pericia",
    "campo_declaracoes_autor": "campo_declaracoes_autor",
    "campo_declaracoes_reu": "campo_declaracoes_reu",
    "campo_medicoes": "campo_medicoes",
}


def _resumir_arquivos(arquivos_pdf) -> str:
    nomes = [getattr(arquivo, "name", "arquivo_sem_nome") for arquivo in arquivos_pdf or []]
    return ", ".join(nomes) if nomes else "nenhum arquivo"


def _assinatura_arquivos(arquivos_pdf) -> str:
    digest = hashlib.sha256()
    for arquivo in arquivos_pdf or []:
        digest.update(arquivo.name.encode("utf-8", errors="replace"))
        digest.update(arquivo.getvalue())
    return digest.hexdigest()


def _exibir_erro_processamento(
    etapa: str,
    processo_id: str,
    arquivos_pdf,
    erro: Exception,
) -> None:
    arquivos = _resumir_arquivos(arquivos_pdf)
    traceback_formatado = "".join(traceback.format_exception(type(erro), erro, erro.__traceback__))
    logger.error(
        "Falha na importação judicial | etapa=%s | processo=%s | arquivos=%s\n%s",
        etapa,
        processo_id,
        arquivos,
        traceback_formatado,
    )
    st.error(
        f"❌ Falha na etapa '{etapa}'. Revise os PDFs enviados, tente novamente e, se o erro persistir, "
        "consulte os detalhes técnicos abaixo."
    )
    st.caption(f"Processo: {processo_id} • Arquivos: {arquivos}")
    with st.expander("Detalhes técnicos da falha"):
        st.code(traceback_formatado)


def aplicar_dados_importados_ao_processo(p_atual: Dict, dados_extraidos: Dict) -> Tuple[Dict, int]:
    processo_atualizado = dict(p_atual)
    campos_preenchidos = 0

    for campo_app, campo_ia in CAMPOS_IMPORTACAO_MAPEADOS.items():
        valor = dados_extraidos.get(campo_ia)
        if valor and valor != "[Não localizado nos documentos]":
            processo_atualizado[campo_app] = valor
            campos_preenchidos += 1

    if dados_extraidos.get("quadro_epis"):
        processo_atualizado["quadro_epis"] = dados_extraidos.get("quadro_epis", [])

    return processo_atualizado, campos_preenchidos


def exibir_tela_importacao_pdf(
    processo_id_selecionado: str,
    p_atual: Dict,
) -> Tuple[bool, Dict, Dict]:
    """
    Tela completa de importação de PDFs com processamento Claude.
    
    Args:
        processo_id_selecionado: ID do processo ativo
        p_atual: Dados atuais do processo
        
    Returns:
        Tupla: (importado_com_sucesso, dados_do_processo, registro_importacao)
    """
    config = obter_app_config()
    max_pdf_files = int(config.get("max_pdf_files", 5))
    max_size_mb = int(config.get("max_file_size_mb", 200))

    st.markdown("### 📥 Importar Processo Judicial via PDF")
    st.markdown(
        f"Faça upload de até {max_pdf_files} PDFs do processo "
        f"(máx. {max_size_mb}MB no total)."
    )
    
    # ==================== ETAPA 1: UPLOAD ====================
    st.markdown("#### 📄 Passo 1: Selecionar Arquivos PDF")
    
    uploaded_files = st.file_uploader(
        f"Selecione os PDFs (máx {max_pdf_files} arquivos, {max_size_mb}MB total)",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"pdf_uploader_{processo_id_selecionado}"
    )
    
    if not uploaded_files:
        st.session_state.pop(f"pdf_import_review::{processo_id_selecionado}", None)
        st.info(f"👉 Nenhum arquivo selecionado ainda. Faça upload de 1-{max_pdf_files} PDFs para começar.")
        return False, p_atual, {}

    estado_key = f"pdf_import_review::{processo_id_selecionado}"
    assinatura_arquivos = _assinatura_arquivos(uploaded_files)
    revisao_pendente = st.session_state.get(estado_key)
    if revisao_pendente and revisao_pendente.get("assinatura") != assinatura_arquivos:
        st.session_state.pop(estado_key, None)
        revisao_pendente = None
        st.info("Os PDFs foram alterados; a análise anterior foi descartada.")
    
    # ==================== ETAPA 2: VALIDAÇÃO ====================
    st.markdown("#### ✅ Passo 2: Validar Arquivos")
    
    # Validar PDFs
    valido, mensagem = validar_pdfs(uploaded_files)
    
    if not valido:
        st.error(mensagem)
        return False, p_atual, {}
    
    # Mostrar resumo dos arquivos
    col1, col2, col3 = st.columns(3)
    
    with col1:
        try:
            num_paginas = calcular_total_paginas(uploaded_files)
        except Exception as exc:
            _exibir_erro_processamento(
                "inspecionar páginas dos PDFs",
                processo_id_selecionado,
                uploaded_files,
                exc,
            )
            return False, p_atual, {}

    if not revisao_pendente:
            revisao_pendente = {
                "assinatura": assinatura_arquivos,
                "texto_consolidado": texto_consolidado,
                "total_paginas": total_paginas,
                "dados_extraidos": dados_extraidos,
                "tokens_entrada": tokens_entrada,
                "tokens_saida": tokens_saida,
                "custo_real": custo_real,
                "num_chamadas_claude": num_chamadas_claude,
            }
            st.session_state[estado_key] = revisao_pendente
        paginas_validas, mensagem_paginas = validar_limite_paginas(num_paginas)
        if not paginas_validas:
            if mensagem_paginas:
                st.error(mensagem_paginas)
            return False, p_atual, {}
        st.metric("📄 Páginas Total", num_paginas)
    
    with col2:
        tamanho_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)
        st.metric("📦 Tamanho Total", f"{tamanho_mb:.1f} MB")
    
    with col3:
        st.metric("📋 Arquivos", len(uploaded_files))
    
    # Lista de arquivos
    st.markdown("**Arquivos selecionados:**")
    for f in uploaded_files:
        st.write(f"✅ {f.name} ({f.size / 1024:.0f} KB)")
    
    # ==================== ETAPA 3: ESTIMATIVA DE CUSTO ====================
    st.markdown("#### 💰 Passo 3: Estimativa de Custo")
    
    custo_estimado = estimar_custo(num_paginas)
    taxa_cambio = obter_taxa_cambio_usd_brl()
    custo_estimado_brl = custo_estimado * taxa_cambio
    
    try:
        custo_hoje = calcular_custo_hoje()
        chamadas_hoje = contar_chamadas_claude_hoje()
    except Exception as exc:
        st.error(
            "❌ Não foi possível confirmar os limites de uso com o banco. "
            "A análise foi bloqueada para evitar ultrapassar o orçamento."
        )
        logger.exception("Falha ao validar limites diários da importação")
        return False, p_atual, {}
    try:
        limite_diario = max(float(config.get("cost_limit_per_day", 250.00)), 0.0)
    except (TypeError, ValueError):
        limite_diario = 250.00
    try:
        limite_chamadas = max(int(config.get("max_api_calls_per_day", 50)), 0)
    except (TypeError, ValueError):
        limite_chamadas = 50
    
    col_custo1, col_custo2, col_custo3 = st.columns(3)
    
    with col_custo1:
        st.metric("💵 Custo Estimado", f"R$ {custo_estimado_brl:.2f}")
    
    with col_custo2:
        st.metric("📊 Gasto Hoje", f"R$ {custo_hoje:.2f}")
    
    with col_custo3:
        percentual = ((custo_hoje / limite_diario) * 100) if limite_diario > 0 else 0
        cor = "🟢" if percentual < 75 else "🟡" if percentual < 90 else "🔴"
        st.metric(f"{cor} Limite de Custo", f"R$ {limite_diario:.2f}")

    st.caption(
        "O limite diário de custo (R$) é validado separadamente do limite diário de chamadas da API Claude. "
        f"Cotação usada: 1 USD = R$ {taxa_cambio:.2f}."
    )

    col_chamadas1, col_chamadas2, col_chamadas3 = st.columns(3)
    with col_chamadas1:
        st.metric("🔁 Chamadas Hoje", chamadas_hoje)
    with col_chamadas2:
        st.metric("📉 Limite de Chamadas", limite_chamadas)
    with col_chamadas3:
        st.metric("✅ Chamadas Restantes", max(limite_chamadas - chamadas_hoje, 0))
    
    # Validar limite diário
    if revisao_pendente:
        permitido, custo_atual, limite = True, custo_hoje, limite_diario
    else:
        try:
            permitido, custo_atual, limite = validar_limite_diario(custo_estimado_brl)
        except Exception:
            st.error(
                "❌ Não foi possível confirmar o limite diário de custo. "
                "A análise foi bloqueada para evitar ultrapassar o orçamento."
            )
            return False, p_atual, {}
    if not permitido:
        st.error(
            "❌ Esta importação excede o limite diário de custo. "
            f"Gasto atual: R$ {custo_atual:.2f}, "
            f"estimativa desta importação: R$ {custo_estimado_brl:.2f}, "
            f"projeção: R$ {custo_atual + custo_estimado_brl:.2f}, "
            f"limite: R$ {limite:.2f}."
        )
        return False, p_atual, {}
    
    # ==================== ETAPA 4: PROCESSAMENTO ====================
    st.markdown("#### 🔄 Passo 4: Processar com Claude 3.5 Sonnet")
    
    col_btn_processar, col_btn_cancelar = st.columns(2)
    
    with col_btn_processar:
        btn_processar = st.button(
            "🚀 Processar com Claude 3.5 Sonnet",
            type="primary",
            width="stretch",
        )
    
    with col_btn_cancelar:
        if st.button("❌ Cancelar", width="stretch"):
            st.info("Importação cancelada.")
            return False, p_atual, {}
    
    if not btn_processar and not revisao_pendente:
        return False, p_atual, {}
    
    # Processar os PDFs
    st.markdown("---")
    st.markdown("#### ⏳ Processando...")
    
    # 1. Consolidar PDFs
    if revisao_pendente:
        texto_consolidado = revisao_pendente["texto_consolidado"]
        total_paginas = revisao_pendente["total_paginas"]
    else:
        try:
            with st.spinner("📚 Consolidando PDFs..."):
                texto_consolidado, total_paginas = consolidar_multiplos_pdfs(uploaded_files)
        except Exception as exc:
            _exibir_erro_processamento(
                "consolidar os PDFs",
                processo_id_selecionado,
                uploaded_files,
                exc,
            )
            return False, p_atual, {}
    
    if not texto_consolidado:
        st.error(
            "❌ Não foi possível extrair texto legível dos PDFs enviados. "
            "Verifique se os arquivos não estão corrompidos, protegidos ou apenas digitalizados sem OCR."
        )
        st.caption(
            f"Arquivos enviados: {_resumir_arquivos(uploaded_files)}. "
            "Você pode reenviar somente os PDFs válidos ou gerar uma versão com texto pesquisável."
        )
        return False, p_atual, {}

    threshold_conservador_pdf = int(config.get("cloud_conservative_pdf_count_threshold", 2))
    threshold_conservador_chars = int(config.get("cloud_conservative_chars_threshold", 600_000))
    modo_conservador = (
        len(uploaded_files) >= threshold_conservador_pdf
        or len(texto_consolidado) >= threshold_conservador_chars
    )
    if modo_conservador:
        st.warning(
            "⚠️ Para manter estabilidade no Streamlit Cloud, esta importação entrou automaticamente em modo "
            "conservador (processamento em blocos menores)."
        )

    try:
        chamadas_previstas = (
            revisao_pendente["num_chamadas_claude"]
            if revisao_pendente
            else estimar_chamadas_necessarias(
                texto_consolidado,
                modo_conservador=modo_conservador,
            )
        )
    except ValueError as exc:
        logger.warning(
            "Importação judicial não concluída | etapa=%s | processo=%s | arquivos=%s | erro=%s",
            "estimar as chamadas da Claude",
            processo_id_selecionado,
            _resumir_arquivos(uploaded_files),
            exc,
        )
        st.error(f"❌ {exc}")
        st.caption(f"Arquivos enviados: {_resumir_arquivos(uploaded_files)}")
        return False, p_atual, {}
    except Exception as exc:
        _exibir_erro_processamento(
            "estimar as chamadas da Claude",
            processo_id_selecionado,
            uploaded_files,
            exc,
        )
        return False, p_atual, {}

    if revisao_pendente:
        permitido_chamadas, chamadas_ja_usadas, limite_chamadas = True, chamadas_hoje, limite_chamadas
    else:
        try:
            permitido_chamadas, chamadas_ja_usadas, limite_chamadas = validar_limite_chamadas_claude(
                chamadas_previstas
            )
        except Exception:
            st.error(
                "❌ Não foi possível confirmar o limite diário de chamadas. "
                "A análise foi bloqueada para evitar ultrapassar a cota."
            )
            return False, p_atual, {}
    st.info(
        "Esta importação deve usar "
        f"{chamadas_previstas} chamada(s) da Claude "
        "(cada chunk processado e a consolidação final contam separadamente)."
    )
    if not permitido_chamadas:
        st.error(
            "❌ Limite diário de chamadas Claude atingido para esta importação. "
            f"Hoje: {chamadas_ja_usadas}, limite: {limite_chamadas}, "
            f"necessárias: {chamadas_previstas}."
        )
        return False, p_atual, {}

    st.success(f"✅ Texto consolidado com {total_paginas} página(s) legível(is)")
    
    # 2. Enviar para Claude
    st.markdown("---")
    if revisao_pendente:
        dados_extraidos = revisao_pendente["dados_extraidos"]
        tokens_entrada = revisao_pendente["tokens_entrada"]
        tokens_saida = revisao_pendente["tokens_saida"]
        custo_real = revisao_pendente["custo_real"]
        num_chamadas_claude = revisao_pendente["num_chamadas_claude"]
    else:
        try:
            dados_extraidos, tokens_entrada, tokens_saida, custo_real, num_chamadas_claude = analisar_processo_judicial(
                texto_consolidado,
                processo_id=processo_id_selecionado,
                modo_conservador=modo_conservador,
            )
        except Exception as exc:
            _exibir_erro_processamento(
                "processar os PDFs com a Claude",
                processo_id_selecionado,
                uploaded_files,
                exc,
            )
            return False, p_atual, {}
    
    if not dados_extraidos or not isinstance(dados_extraidos, dict):
        logger.warning(
            "Importação judicial não concluída | etapa=%s | processo=%s | arquivos=%s | chamadas=%s",
            "processar os PDFs com a Claude",
            processo_id_selecionado,
            _resumir_arquivos(uploaded_files),
            num_chamadas_claude,
        )
        st.error(
            "❌ A análise da Claude não retornou dados válidos para preencher o processo. "
            "A importação não foi concluída, mas nenhum dado do processo foi alterado."
        )
        st.info(
            "O que fazer:\n"
            "- Se a mensagem acima indicar configuração/API key, verifique "
            "st.secrets['anthropic']['api_key'] nas configurações do app.\n"
            "- Se for erro de conexão, limite ou indisponibilidade da API, aguarde alguns minutos e tente novamente.\n"
            "- Se o problema persistir, tente enviar os PDFs em lotes menores ou preencha os campos manualmente."
        )
        st.caption(f"Processo: {processo_id_selecionado} • Arquivos enviados: {_resumir_arquivos(uploaded_files)}")
        return False, p_atual, {}
    
    custo_real_brl = custo_real * taxa_cambio
    
    st.success(f"✅ Análise concluída!")
    
    # Mostrar custo real
    col_custo_real1, col_custo_real2 = st.columns(2)
    with col_custo_real1:
        st.metric("💵 Custo Real", f"R$ {custo_real_brl:.2f}")
    with col_custo_real2:
        st.metric("🎯 Tokens Usados", f"{tokens_entrada + tokens_saida:,}")
    
    # ==================== ETAPA 5: REVISÃO ====================
    st.markdown("---")
    st.markdown("#### 👁️ Passo 5: Revisar Dados Extraídos")
    
    # Abas de revisão
    tab_resumo, tab_identificacao, tab_contrato, tab_sst, tab_quesitos, tab_raw = st.tabs([
        "📊 Resumo",
        "👤 Identificação",
        "📋 Contrato",
        "🛡️ SST & Documentos",
        "❓ Quesitos",
        "📄 JSON Bruto"
    ])
    
    with tab_resumo:
        st.markdown("**Resumo dos Dados Extraídos:**")
        
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            st.write(f"**Processo:** {dados_extraidos.get('processo_num', '[Não localizado]')}")
            st.write(f"**Reclamante:** {dados_extraidos.get('reclamante_nome', '[Não localizado]')}")
            st.write(f"**Reclamada:** {dados_extraidos.get('reclamada_nome', '[Não localizado]')}")
        
        with col_res2:
            st.write(f"**Órgão Julgador:** {dados_extraidos.get('orgao_julgador', '[Não localizado]')}")
            st.write(f"**Data Autuação:** {dados_extraidos.get('data_autuacao', '[Não localizado]')}")
            st.write(f"**Valor da Causa:** {dados_extraidos.get('valor_causa', '[Não localizado]')}")
    
    with tab_identificacao:
        st.markdown("**Identificação das Partes:**")
        
        col_ident1, col_ident2 = st.columns(2)
        
        with col_ident1:
            st.write("**Reclamante:**")
            st.write(f"- Nome: {dados_extraidos.get('reclamante_nome', '[Não localizado]')}")
            st.write(f"- CPF: {dados_extraidos.get('reclamante_cpf', '[Não localizado]')}")
            st.write(f"- Data Nascimento: {dados_extraidos.get('segurado_nascimento', '[Não localizado]')}")
            st.write(f"- Profissão: {dados_extraidos.get('profissao_cargo', '[Não localizado]')}")
        
        with col_ident2:
            st.write("**Reclamada:**")
            st.write(f"- Empresa: {dados_extraidos.get('reclamada_nome', '[Não localizado]')}")
            st.write(f"- CNPJ: {dados_extraidos.get('reclamada_cnpj', '[Não localizado]')}")
            st.write(f"- Setor: {dados_extraidos.get('setor', '[Não localizado]')}")
    
    with tab_contrato:
        st.markdown("**Dados Contratuais:**")
        
        st.write(f"**Data Admissão:** {dados_extraidos.get('data_admissao', '[Não localizado]')}")
        st.write(f"**Status:** {dados_extraidos.get('status_contrato', '[Não localizado]')}")
        st.write(f"**Período Imprescrito:** {dados_extraidos.get('periodo_imprescrito', '[Não localizado]')}")
        st.write(f"**Cargos:** {dados_extraidos.get('cargos', '[Não localizado]')}")
        st.write(f"**Última Remuneração:** {dados_extraidos.get('ultima_remuneracao', '[Não localizado]')}")
    
    with tab_sst:
        st.markdown("**SST & Análise de Documentos:**")
        
        st.write("**Agentes Nocivos:**")
        st.write(dados_extraidos.get('agentes_alegados', '[Não localizado]'))
        
        st.markdown("---")
        st.write("**Análise LTCAT:**")
        st.write(dados_extraidos.get('doc_ltcat', '[Não localizado]'))
        
        st.markdown("---")
        st.write("**Análise PPP:**")
        st.write(dados_extraidos.get('doc_ppp', '[Não localizado]'))
    
    with tab_quesitos:
        st.markdown("**Quesitos Formulados:**")
        
        st.write("**Quesitos do Juízo:**")
        st.write(dados_extraidos.get('quesitos_juizo', '[Não localizado]'))
        
        st.markdown("---")
        st.write("**Quesitos do Reclamante:**")
        st.write(dados_extraidos.get('quesitos_autor', '[Não localizado]'))
        
        st.markdown("---")
        st.write("**Quesitos da Reclamada:**")
        st.write(dados_extraidos.get('quesitos_reu', '[Não localizado]'))
    
    with tab_raw:
        st.markdown("**JSON Bruto (Para Debug):**")
        import json
        st.json(dados_extraidos)
    
    # ==================== ETAPA 6: CONFIRMAÇÃO ====================
    st.markdown("---")
    st.markdown("#### ✅ Passo 6: Confirmar e Preencher Campos")
    
    col_conf1, col_conf2 = st.columns(2)
    
    with col_conf1:
        btn_confirmar = st.button(
            "✅ Confirmar e Preencher Campos",
            type="primary",
            width="stretch",
        )
    
    with col_conf2:
        btn_descartar = st.button(
            "❌ Descartar",
            width="stretch",
        )
    
    if btn_descartar:
        st.session_state.pop(estado_key, None)
        st.info("Dados descartados. Você pode fazer novo upload.")
        return False, p_atual, {}
    
    if not btn_confirmar:
        return False, p_atual, {}
    
    # Preencher campos do processo
    st.markdown("---")
    st.markdown("#### 📝 Preenchendo Campos Automaticamente...")
    
    try:
        p_atual, campos_preenchidos = aplicar_dados_importados_ao_processo(p_atual, dados_extraidos)

        nomes_arquivos = [f.name for f in uploaded_files]
        registro_importacao = criar_registro_importacao_ia(
            processo_id=processo_id_selecionado,
            nomes_arquivos=nomes_arquivos,
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
            custo_real=custo_real,
            dados_extraidos=dados_extraidos,
            num_chamadas_claude=num_chamadas_claude,
        )
    except Exception as exc:
        _exibir_erro_processamento(
            "preparar os dados para salvar no Firestore",
            processo_id_selecionado,
            uploaded_files,
            exc,
        )
        return False, p_atual, {}

    st.success(f"✅ Importação pronta para salvar! {campos_preenchidos} campos preenchidos automaticamente.")
    st.session_state.pop(estado_key, None)
    return True, p_atual, registro_importacao
