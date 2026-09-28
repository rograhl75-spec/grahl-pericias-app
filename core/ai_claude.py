"""
Integração com Claude 3.5 Sonnet para extração de dados de processos judiciais.
Responsável por enviar PDFs consolidados à IA e retornar dados estruturados.
"""

import anthropic
import streamlit as st
import json
import logging
import re
from typing import Dict, List, Tuple

from core.config import ConfigurationError, obter_api_key_anthropic, obter_app_config
from core.cost_tracker import registrar_chamada_claude, validar_limite_chamadas_claude

logger = logging.getLogger(__name__)


def obter_cliente_anthropic():
    """Inicializa e retorna cliente Anthropic usando API key de st.secrets"""
    try:
        api_key = obter_api_key_anthropic()
        return anthropic.Anthropic(api_key=api_key)
    except ConfigurationError as exc:
        st.error(f"❌ Configuração Anthropic inválida: {exc}")
        st.stop()
    except Exception as e:
        st.error(f"❌ Erro ao conectar com Anthropic: {e}")
        st.stop()


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
    try:
        return json.loads(conteudo_resposta)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', conteudo_resposta, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.error("Resposta da Claude sem JSON válido: %s", conteudo_resposta[:500])
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

    tokens_entrada = resposta.usage.input_tokens
    tokens_saida = resposta.usage.output_tokens
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

    return resposta.content[0].text, tokens_entrada, tokens_saida, custo_real


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


def estimar_chamadas_necessarias(texto_consolidado: str) -> int:
    config = obter_app_config()
    limite_chars = int(config.get("claude_chunk_chars", 120_000))
    max_chunks = int(config.get("claude_max_chunks", 6))
    chunks = _dividir_texto_em_chunks(texto_consolidado, limite_chars, max_chunks)
    return len(chunks) if len(chunks) == 1 else len(chunks) + 1


def analisar_processo_judicial(
    texto_consolidado: str,
    processo_id: str = "processo_sem_id",
) -> Tuple[Dict, int, int, float, int]:
    """
    Envia texto consolidado dos PDFs para Claude analisar como perícia judicial.

    Args:
        texto_consolidado: Texto de todos os PDFs consolidado

    Returns:
        Tupla: (dados_extraidos_dict, tokens_entrada, tokens_saida, custo_real, num_chamadas)
    """
    try:
        cliente = obter_cliente_anthropic()
        prompt = carregar_prompt_judicial()
        config = obter_app_config()
        model = config.get("claude_model", "claude-3-5-sonnet-20241022")
        limite_chars = int(config.get("claude_chunk_chars", 120_000))
        max_chunks = int(config.get("claude_max_chunks", 6))
        chunks = _dividir_texto_em_chunks(texto_consolidado, limite_chars, max_chunks)
        chamadas_previstas = estimar_chamadas_necessarias(texto_consolidado)

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
        st.error(f"❌ {exc}")
        return {}, 0, 0, 0.0, 0
    except anthropic.APIConnectionError as e:
        registrar_chamada_claude(processo_id, "erro_conexao", False, {"erro": str(e)})
        st.error(f"❌ Erro de conexão com Anthropic: {e}")
        return {}, 0, 0, 0.0, 0
    except anthropic.RateLimitError:
        registrar_chamada_claude(processo_id, "rate_limit", False, {})
        st.error("❌ Limite de requisições atingido. Tente novamente em alguns segundos.")
        return {}, 0, 0, 0.0, 0
    except anthropic.APIStatusError as e:
        registrar_chamada_claude(processo_id, "erro_status_api", False, {"erro": str(e)})
        st.error(f"❌ Erro na API Anthropic: {e}")
        return {}, 0, 0, 0.0, 0
    except Exception as e:
        registrar_chamada_claude(processo_id, "erro_inesperado", False, {"erro": str(e)})
        st.error(f"❌ Erro inesperado: {e}")
        logger.exception(f"Erro ao analisar processo: {e}")
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
