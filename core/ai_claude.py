"""
Integração com Claude 3.5 Sonnet para extração de dados de processos judiciais.
Responsável por enviar PDFs consolidados à IA e retornar dados estruturados.
"""

import anthropic
import streamlit as st
import json
import logging
from typing import Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


def obter_cliente_anthropic():
    """Inicializa e retorna cliente Anthropic usando API key de st.secrets"""
    try:
        api_key = st.secrets["anthropic"]["api_key"]
        return anthropic.Anthropic(api_key=api_key)
    except KeyError:
        st.error("❌ Erro: Chave API Anthropic não configurada em st.secrets")
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


def analisar_processo_judicial(texto_consolidado: str) -> Tuple[Dict, int, int, float]:
    """
    Envia texto consolidado dos PDFs para Claude analisar como perícia judicial.
    
    Args:
        texto_consolidado: Texto de todos os PDFs consolidado
        
    Returns:
        Tupla: (dados_extraidos_dict, tokens_entrada, tokens_saida, custo_real)
    """
    try:
        cliente = obter_cliente_anthropic()
        prompt = carregar_prompt_judicial()
        
        # Exibir status
        with st.spinner("⏳ Analisando processo com Claude 3.5 Sonnet..."):
            resposta = cliente.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n---DOCUMENTOS DO PROCESSO---\n\n{texto_consolidado}"
                    }
                ]
            )
        
        # Extrair tokens e conteúdo
        tokens_entrada = resposta.usage.input_tokens
        tokens_saida = resposta.usage.output_tokens
        conteudo_resposta = resposta.content[0].text
        
        # Calcular custo
        # Input: $3.00 por 1M tokens / Output: $15.00 por 1M tokens
        custo_input = (tokens_entrada / 1_000_000) * 3.00
        custo_saida = (tokens_saida / 1_000_000) * 15.00
        custo_real = custo_input + custo_saida
        
        # Parsear JSON da resposta
        try:
            dados_extraidos = json.loads(conteudo_resposta)
        except json.JSONDecodeError:
            # Se não for JSON puro, tentar extrair JSON do texto
            import re
            match = re.search(r'\{.*\}', conteudo_resposta, re.DOTALL)
            if match:
                dados_extraidos = json.loads(match.group())
            else:
                st.error("❌ Erro ao parsear resposta da IA")
                return {}, tokens_entrada, tokens_saida, custo_real
        
        logger.info(f"Processo analisado com sucesso. Tokens: {tokens_entrada + tokens_saida}, Custo: R${custo_real:.2f}")
        
        return dados_extraidos, tokens_entrada, tokens_saida, custo_real
        
    except anthropic.APIConnectionError as e:
        st.error(f"❌ Erro de conexão com Anthropic: {e}")
        return {}, 0, 0, 0.0
    except anthropic.RateLimitError:
        st.error("❌ Limite de requisições atingido. Tente novamente em alguns segundos.")
        return {}, 0, 0, 0.0
    except anthropic.APIStatusError as e:
        st.error(f"❌ Erro na API Anthropic: {e}")
        return {}, 0, 0, 0.0
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
        logger.exception(f"Erro ao analisar processo: {e}")
        return {}, 0, 0, 0.0


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
