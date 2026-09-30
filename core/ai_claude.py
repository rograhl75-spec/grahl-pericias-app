"""
Integração com Claude 3.5 Sonnet para extração de dados de processos judiciais.
Responsável por enviar PDFs consolidados à IA e retornar dados estruturados.
"""

import json
import logging
import math
import re
from typing import Dict, List, Tuple

import anthropic
import streamlit as st

from core.config import ConfigurationError, obter_api_key_anthropic, obter_app_config
from core.cost_tracker import registrar_chamada_claude, validar_limite_chamadas_claude

logger = logging.getLogger(__name__)


def obter_cliente_anthropic():
    """
    Inicializa e retorna cliente Anthropic usando API key de st.secrets.

    Não interrompe o app (sem st.stop()): em caso de falha lança exceção controlada
    para que o chamador exiba mensagem amigável e mantenha a sessão ativa.

    Raises:
        ConfigurationError: API key ausente/inválida ou secrets indisponíveis.
        RuntimeError: falha ao criar o cliente Anthropic.
    """
    try:
        api_key = obter_api_key_anthropic()
    except ConfigurationError as exc:
        logger.error("Configuração Anthropic inválida | etapa=obter_api_key | erro=%s", exc)
        raise
    except Exception as exc:
        logger.error(
            "Falha ao ler configuração Anthropic | etapa=obter_api_key | tipo=%s | erro=%s",
            type(exc).__name__,
            exc,
        )
        raise ConfigurationError(
            "Não foi possível ler st.secrets['anthropic']['api_key']. Verifique os secrets do app."
        ) from exc

    try:
        return anthropic.Anthropic(api_key=api_key)
    except Exception as exc:
        logger.error(
            "Falha ao inicializar cliente Anthropic | etapa=criar_cliente | tipo=%s | erro=%s",
            type(exc).__name__,
            exc,
        )
        raise RuntimeError(f"Não foi possível inicializar o cliente Anthropic: {type(exc).__name__}") from exc


def carregar_prompt_judicial():
    """Carrega o prompt pré-definido para perícias judiciais"""
    prompt = """Você é um Especialista em Engenharia/Medicina de Segurança do Trabalho e Assistente Jurídico Avançado.

Analise os documentos fornecidos e extraia as informações conforme estrutura abaixo.
Se uma informação não for localizada, use: "[Não localizado nos documentos]"

RETORNE APENAS UM JSON VÁLIDO COM A SEGUINTE ESTRUTURA (sem markdown, sem explicações adicionais):

{
  "processo_num": "número do processo",
  "orgao_julgador": "órgão julgador / vara",
  "data_autuacao": "data de autuação",
  "valor_causa": "valor da causa",
  "rito_processual": "rito processual",
  "reclamante_nome": "nome completo reclamante",
  "reclamante_cpf": "CPF reclamante",
  "reclamante_adv": "advogados reclamante com OAB",
  "reclamada_nome": "razão social reclamada",
  "reclamada_cnpj": "CNPJ reclamada",
  "reclamada_adv": "advogados reclamada com OAB",
  "data_admissao": "data de admissão",
  "status_contrato": "status do contrato (demitido/ativo)",
  "periodo_imprescrito": "período imprescrito (calcule 5 anos retroativos à autuação)",
  "cargos": "cargos/funções exercidas",
  "setor": "setor/lotação/local",
  "ultima_remuneracao": "última remuneração",
  "objeto_pericia": "objeto da perícia",
  "atividades_inicial": "atividades descritas",
  "agentes_alegados": "agentes nocivos/riscos alegados",
  "pedidos_tecnicos": "pedidos técnicos",
  "preliminares_periciais": "preliminares periciais",
  "defesa_merito_sst": "defesa de mérito SST",
  "fase_processual": "fase processual atual",
  "campo_data": "data da vistoria",
  "campo_horario": "horário da vistoria",
  "local_diligencia": "local/endereço da diligência",
  "doc_ltcat": "análise do LTCAT",
  "doc_laudo": "análise de laudos",
  "doc_ppp": "análise do PPP",
  "doc_pgr": "análise do PGR/PPRA",
  "doc_os": "análise de ordens de serviço",
  "doc_asos": "análise de ASOs",
  "doc_outros": "outros documentos",
  "quesitos_juizo": "quesitos do juízo (transcrição literal)",
  "quesitos_autor": "quesitos do reclamante (transcrição literal)",
  "quesitos_reu": "quesitos da reclamada (transcrição literal)",
  "quadro_epis": [
    {
      "descricao": "descrição do EPI",
      "ca": "número CA",
      "data_entrega": "data de entrega",
      "obs": "observações"
    }
  ],
  "relato_inicial": "relato inicial",
  "profissao_cargo": "profissão/cargo",
  "segurado_nascimento": "data de nascimento",
  "apr_fisicos": "agentes físicos",
  "apr_quimicos": "agentes químicos",
  "apr_biologicos": "agentes biológicos",
  "enquadramento_legal_prev": "enquadramento legal",
  "presentes_pericia": "pessoas presentes na vistoria",
  "campo_declaracoes_autor": "declarações do autor",
  "campo_declaracoes_reu": "declarações da reclamada",
  "campo_medicoes": "medições realizadas"
}

REGRAS OBRIGATÓRIAS:
1. Fidelidade aos autos - extraia APENAS o que está nos documentos
2. Período imprescrito = Data de Autuação - 5 anos exatos
3. Transcrição literal de quesitos (nunca resuma)
4. Se não localizar, use: "[Não localizado nos documentos]"
5. RETORNE APENAS JSON VÁLIDO, sem markdown ou explicações
"""
    return prompt


def _parsear_json_resposta(conteudo_resposta: str) -> Dict:
    if not isinstance(conteudo_resposta, str) or not conteudo_resposta.strip():
        raise ValueError("Resposta da IA vazia.")

    texto = conteudo_resposta.strip()
    try:
        dado = json.loads(texto)
        if isinstance(dado, dict):
            return dado
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for indice, char in enumerate(texto):
        if char != "{":
            continue
        try:
            dado, _ = decoder.raw_decode(texto[indice:])
            if isinstance(dado, dict):
                return dado
        except json.JSONDecodeError:
            continue

    logger.error("Resposta da Claude sem JSON válido: %s", texto[:500])
    raise ValueError("Resposta da IA não retornou JSON válido.")


def _dividir_texto_em_chunks(texto: str, limite_chars: int, max_chunks: int) -> List[str]:
    if len(texto) <= limite_chars:
        return [texto]

    marcadores = re.split(r'(?=\n--- PÁGINA \d+ ---|\n={80}\nARQUIVO \d+:)', texto)
    segmentos = [segmento for segmento in marcadores if segmento.strip()]
    if not segmentos:
        segmentos = [texto]

    chunks = []
    chunk_atual = ""

    for segmento in segmentos:
        if len(segmento) > limite_chars:
            inicio = 0
            while inicio < len(segmento):
                fim = min(inicio + limite_chars, len(segmento))
                parte = segmento[inicio:fim]
                if chunk_atual.strip():
                    chunks.append(chunk_atual)
                    chunk_atual = ""
                chunks.append(parte)
                inicio = fim
            continue

        if len(chunk_atual) + len(segmento) > limite_chars and chunk_atual.strip():
            chunks.append(chunk_atual)
            chunk_atual = segmento
        else:
            chunk_atual += segmento

    if chunk_atual.strip():
        chunks.append(chunk_atual)

    if len(chunks) > max_chunks:
        raise ValueError(
            f"O processo gerou {len(chunks)} blocos de análise, acima do limite configurado de {max_chunks}. "
            "Reduza o volume de PDFs ou ajuste os limites do app."
        )

    return chunks


def _resolver_parametros_chunk(
    texto_consolidado: str,
    config: Dict,
    modo_conservador: bool = False,
) -> Tuple[int, int, bool]:
    limite_padrao = int(config.get("claude_chunk_chars", 120_000))
    max_chunks_padrao = int(config.get("claude_max_chunks", 10))
    limite_conservador = int(config.get("claude_chunk_chars_conservative", 80_000))
    max_chunks_conservador = int(config.get("claude_max_chunks_conservative", 15))
    limite_chars_cloud = int(config.get("cloud_conservative_chars_threshold", 600_000))
    pdf_count_threshold = int(config.get("cloud_conservative_pdf_count_threshold", 2))

    precisa_conservador = modo_conservador or len(texto_consolidado) >= limite_chars_cloud
    if not precisa_conservador:
        return limite_padrao, max_chunks_padrao, False

    limite_escolhido = min(limite_padrao, limite_conservador)
    chunks_minimos = max(1, math.ceil(len(texto_consolidado) / max(limite_escolhido, 1)))
    max_chunks_escolhido = max(max_chunks_padrao, max_chunks_conservador, chunks_minimos)

    logger.warning(
        "Ativando processamento conservador de PDFs (texto=%s chars, limiar_chars=%s, limiar_pdfs=%s)",
        len(texto_consolidado),
        limite_chars_cloud,
        pdf_count_threshold,
    )
    return limite_escolhido, max_chunks_escolhido, True


def _executar_chamada_claude(
    cliente,
    model: str,
    conteudo: str,
    processo_id: str,
    etapa: str,
) -> Tuple[str, int, int, float]:
    resposta = cliente.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": conteudo}],
    )

    partes_texto = []
    for bloco in getattr(resposta, "content", []) or []:
        texto_bloco = getattr(bloco, "text", None)
        if isinstance(texto_bloco, str) and texto_bloco.strip():
            partes_texto.append(texto_bloco)
    if not partes_texto:
        raise ValueError("Resposta da IA vazia ou sem conteúdo textual.")

    usage = getattr(resposta, "usage", None)
    tokens_entrada = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_saida = int(getattr(usage, "output_tokens", 0) or 0)
    custo_input = (tokens_entrada / 1_000_000) * 3.00
    custo_saida = (tokens_saida / 1_000_000) * 15.00
    custo_real = custo_input + custo_saida

    registrar_chamada_claude(
        processo_id=processo_id,
        etapa=etapa,
        sucesso=True,
        detalhes={
            "model": model,
            "tokens_entrada": tokens_entrada,
            "tokens_saida": tokens_saida,
        },
    )

    return "\n".join(partes_texto), tokens_entrada, tokens_saida, custo_real


def _prompt_chunk_judicial(prompt_base: str, indice: int, total: int, texto_chunk: str) -> str:
    return (
        f"{prompt_base}\n\n"
        "Você receberá apenas uma parte dos documentos. Extraia somente o que estiver presente "
        "neste trecho e use '[Não localizado nos documentos]' para campos ausentes.\n"
        f"Trecho {indice} de {total}.\n\n"
        f"---DOCUMENTOS DO PROCESSO (TRECHO {indice}/{total})---\n\n{texto_chunk}"
    )


def _prompt_consolidacao_jsons(prompt_base: str, jsons_parciais: List[Dict]) -> str:
    return (
        f"{prompt_base}\n\n"
        "A seguir estão JSONs parciais extraídos de diferentes trechos do mesmo processo. "
        "Consolide tudo em um único JSON final.\n"
        "Regras adicionais:\n"
        "1. Não invente informações.\n"
        "2. Quando houver conflito, prefira o valor mais específico e completo.\n"
        "3. Preserve a transcrição literal dos quesitos.\n"
        "4. Remova duplicidades óbvias em 'quadro_epis'.\n\n"
        f"JSONS PARCIAIS:\n{json.dumps(jsons_parciais, ensure_ascii=False)}"
    )


def estimar_chamadas_necessarias(texto_consolidado: str, modo_conservador: bool = False) -> int:
    config = obter_app_config()
    limite_chars, max_chunks, _ = _resolver_parametros_chunk(
        texto_consolidado=texto_consolidado,
        config=config,
        modo_conservador=modo_conservador,
    )
    chunks = _dividir_texto_em_chunks(texto_consolidado, limite_chars, max_chunks)
    return len(chunks) if len(chunks) == 1 else len(chunks) + 1


def analisar_processo_judicial(
    texto_consolidado: str,
    processo_id: str = "processo_sem_id",
    modo_conservador: bool = False,
) -> Tuple[Dict, int, int, float, int]:
    """
    Envia texto consolidado dos PDFs para Claude analisar como perícia judicial.

    Args:
        texto_consolidado: Texto de todos os PDFs consolidado

    Returns:
        Tupla: (dados_extraidos_dict, tokens_entrada, tokens_saida, custo_real, num_chamadas)
    """
    etapa = "inicializar_cliente"
    try:
        cliente = obter_cliente_anthropic()
    except ConfigurationError as exc:
        logger.error(
            "Análise judicial abortada | processo=%s | etapa=%s | tipo=%s | erro=%s",
            processo_id,
            etapa,
            type(exc).__name__,
            exc,
        )
        st.error(
            "❌ A integração com a Claude não está configurada corretamente. "
            "Verifique st.secrets['anthropic']['api_key'] nas configurações do app (Streamlit Cloud → Settings → Secrets). "
            f"Detalhe: {exc}"
        )
        return {}, 0, 0, 0.0, 0
    except Exception as exc:
        logger.error(
            "Análise judicial abortada | processo=%s | etapa=%s | tipo=%s | erro=%s",
            processo_id,
            etapa,
            type(exc).__name__,
            exc,
        )
        st.error(
            "❌ Não foi possível conectar à Claude neste momento. "
            "Tente novamente em alguns minutos; o app continua disponível para uso manual."
        )
        return {}, 0, 0, 0.0, 0

    try:
        etapa = "preparar_analise"
        prompt = carregar_prompt_judicial()
        config = obter_app_config()
        model = config.get("claude_model", "claude-3-5-sonnet-20241022")
        limite_chars, max_chunks, conservador_ativo = _resolver_parametros_chunk(
            texto_consolidado=texto_consolidado,
            config=config,
            modo_conservador=modo_conservador,
        )
        if conservador_ativo:
            st.warning(
                "⚠️ Ambiente em modo conservador para estabilidade: o processo será analisado em blocos menores."
            )
        chunks = _dividir_texto_em_chunks(texto_consolidado, limite_chars, max_chunks)
        chamadas_previstas = len(chunks) if len(chunks) == 1 else len(chunks) + 1

        permitido, chamadas_hoje, limite_chamadas = validar_limite_chamadas_claude(chamadas_previstas)
        if not permitido:
            st.error(
                "❌ Limite diário de chamadas Claude atingido. "
                f"Hoje: {chamadas_hoje}, limite: {limite_chamadas}, necessárias: {chamadas_previstas}."
            )
            return {}, 0, 0, 0.0, 0

        total_tokens_entrada = 0
        total_tokens_saida = 0
        custo_total = 0.0

        # Exibir status
        with st.spinner("⏳ Analisando processo com Claude 3.5 Sonnet..."):
            if len(chunks) == 1:
                etapa = "analise_final"
                conteudo_resposta, tokens_entrada, tokens_saida, custo_real = _executar_chamada_claude(
                    cliente=cliente,
                    model=model,
                    conteudo=f"{prompt}\n\n---DOCUMENTOS DO PROCESSO---\n\n{texto_consolidado}",
                    processo_id=processo_id,
                    etapa="analise_final",
                )
                total_tokens_entrada += tokens_entrada
                total_tokens_saida += tokens_saida
                custo_total += custo_real
                dados_extraidos = _parsear_json_resposta(conteudo_resposta)
            else:
                jsons_parciais = []
                for indice, chunk in enumerate(chunks, start=1):
                    etapa = f"analise_chunk_{indice}"
                    conteudo_resposta, tokens_entrada, tokens_saida, custo_real = _executar_chamada_claude(
                        cliente=cliente,
                        model=model,
                        conteudo=_prompt_chunk_judicial(prompt, indice, len(chunks), chunk),
                        processo_id=processo_id,
                        etapa=f"analise_chunk_{indice}",
                    )
                    total_tokens_entrada += tokens_entrada
                    total_tokens_saida += tokens_saida
                    custo_total += custo_real
                    jsons_parciais.append(_parsear_json_resposta(conteudo_resposta))

                etapa = "consolidacao_final"
                conteudo_resposta, tokens_entrada, tokens_saida, custo_real = _executar_chamada_claude(
                    cliente=cliente,
                    model=model,
                    conteudo=_prompt_consolidacao_jsons(prompt, jsons_parciais),
                    processo_id=processo_id,
                    etapa="consolidacao_final",
                )
                total_tokens_entrada += tokens_entrada
                total_tokens_saida += tokens_saida
                custo_total += custo_real
                dados_extraidos = _parsear_json_resposta(conteudo_resposta)

        logger.info(
            "Processo analisado com sucesso. Chamadas: %s, Tokens: %s, Custo: R$%.2f",
            chamadas_previstas,
            total_tokens_entrada + total_tokens_saida,
            custo_total,
        )

        return dados_extraidos, total_tokens_entrada, total_tokens_saida, custo_total, chamadas_previstas
    except ValueError as exc:
        logger.warning(
            "Falha controlada na análise judicial | processo=%s | etapa=%s | tipo=%s | erro=%s",
            processo_id,
            etapa,
            type(exc).__name__,
            exc,
        )
        st.error(f"❌ {exc}")
        return {}, 0, 0, 0.0, 0
    except anthropic.APIConnectionError as e:
        logger.error(
            "Erro de conexão com Anthropic | processo=%s | etapa=%s | tipo=%s | erro=%s",
            processo_id,
            etapa,
            type(e).__name__,
            e,
        )
        registrar_chamada_claude(processo_id, "erro_conexao", False, {"erro": str(e), "etapa": etapa})
        st.error(f"❌ Erro de conexão com Anthropic: {e}")
        return {}, 0, 0, 0.0, 0
    except anthropic.RateLimitError as e:
        logger.warning(
            "Rate limit Anthropic | processo=%s | etapa=%s | tipo=%s | erro=%s",
            processo_id,
            etapa,
            type(e).__name__,
            e,
        )
        registrar_chamada_claude(processo_id, "rate_limit", False, {"etapa": etapa})
        st.error("❌ Limite de requisições atingido. Tente novamente em alguns segundos.")
        return {}, 0, 0, 0.0, 0
    except anthropic.AuthenticationError as e:
        logger.error(
            "Autenticação Anthropic recusada | processo=%s | etapa=%s | tipo=%s | status=%s",
            processo_id,
            etapa,
            type(e).__name__,
            getattr(e, "status_code", None),
        )
        registrar_chamada_claude(processo_id, "erro_autenticacao", False, {"etapa": etapa})
        st.error(
            "❌ A API key da Anthropic foi recusada. "
            "Atualize st.secrets['anthropic']['api_key'] com uma chave válida e tente novamente."
        )
        return {}, 0, 0, 0.0, 0
    except anthropic.APIStatusError as e:
        logger.error(
            "Erro de status na API Anthropic | processo=%s | etapa=%s | tipo=%s | status=%s | erro=%s",
            processo_id,
            etapa,
            type(e).__name__,
            getattr(e, "status_code", None),
            e,
        )
        registrar_chamada_claude(processo_id, "erro_status_api", False, {"erro": str(e), "etapa": etapa})
        st.error(f"❌ Erro na API Anthropic: {e}")
        return {}, 0, 0, 0.0, 0
    except Exception as e:
        logger.exception(
            "Erro inesperado ao analisar processo | processo=%s | etapa=%s | tipo=%s | erro=%s",
            processo_id,
            etapa,
            type(e).__name__,
            e,
        )
        registrar_chamada_claude(processo_id, "erro_inesperado", False, {"erro": str(e), "etapa": etapa})
        st.error(f"❌ Erro inesperado: {e}")
        return {}, 0, 0, 0.0, 0


def estimar_custo(num_paginas: int) -> float:
    """
    Estima o custo baseado no número de páginas do PDF.
    Aproximação: 250 tokens por página.
    """
    tokens_estimados_entrada = num_paginas * 250
    tokens_estimados_saida = 5000  # Média de resposta
    
    custo_input = (tokens_estimados_entrada / 1_000_000) * 3.00
    custo_saida = (tokens_estimados_saida / 1_000_000) * 15.00
    
    return custo_input + custo_saida
