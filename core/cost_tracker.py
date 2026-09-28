"""
Rastreamento de custos de API Claude e histórico de importações.
Registra todas as requisições no Firebase para auditoria e relatórios.
"""

import streamlit as st
import logging
from datetime import datetime
from typing import Dict, List

from core.config import obter_app_config, obter_taxa_cambio_usd_brl
from core.database import _obter_db

logger = logging.getLogger(__name__)


def _normalizar_inteiro_nao_negativo(valor, padrao: int = 0) -> int:
    try:
        return max(int(valor), 0)
    except (TypeError, ValueError):
        return padrao


def _normalizar_float_nao_negativo(valor, padrao: float = 0.0) -> float:
    try:
        return max(float(valor), 0.0)
    except (TypeError, ValueError):
        return padrao


def registrar_importacao_ia(
    processo_id: str,
    nomes_arquivos: List[str],
    tokens_entrada: int,
    tokens_saida: int,
    custo_real: float,
    dados_extraidos: Dict
) -> bool:
    """
    Registra uma importação de processo no Firestore para rastreamento de custos.
    
    Args:
        processo_id: ID do processo (ex: Proc_01)
        nomes_arquivos: Lista de nomes dos PDFs importados
        tokens_entrada: Tokens de entrada usados
        tokens_saida: Tokens de saída usados
        custo_real: Custo real em dólares
        dados_extraidos: Dados estruturados extraídos
        
    Returns:
        bool: True se registrado com sucesso
    """
    try:
        db = _obter_db()
        registro = criar_registro_importacao_ia(
            processo_id=processo_id,
            nomes_arquivos=nomes_arquivos,
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
            custo_real=custo_real,
            dados_extraidos=dados_extraidos,
        )
        db.collection("importacoes_ia").add(registro)
        
        logger.info(
            "Importação registrada: %s - R$ %.2f",
            processo_id,
            registro.get("custo_brl", 0.0),
        )
        return True
        
    except Exception as e:
        logger.error(f"Erro ao registrar importação: {e}")
        st.error(f"⚠️ Erro ao registrar custo: {e}")
        return False


def criar_registro_importacao_ia(
    processo_id: str,
    nomes_arquivos: List[str],
    tokens_entrada: int,
    tokens_saida: int,
    custo_real: float,
    dados_extraidos: Dict,
    num_chamadas_claude: int = 1,
) -> Dict:
    arquivos = []
    for nome in nomes_arquivos:
        if nome is None:
            continue
        nome_limpo = str(nome).strip()
        if nome_limpo:
            arquivos.append(nome_limpo)
    tokens_entrada = _normalizar_inteiro_nao_negativo(tokens_entrada)
    tokens_saida = _normalizar_inteiro_nao_negativo(tokens_saida)
    custo_real = _normalizar_float_nao_negativo(custo_real)
    num_chamadas_claude = _normalizar_inteiro_nao_negativo(num_chamadas_claude, 1)
    custo_brl = custo_real * obter_taxa_cambio_usd_brl()
    return {
        "processo_id": processo_id,
        "data_importacao": datetime.now().isoformat(),
        "arquivos": arquivos,
        "num_arquivos": len(arquivos),
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "tokens_total": tokens_entrada + tokens_saida,
        "custo_usd": round(custo_real, 4),
        "custo_brl": round(custo_brl, 2),
        "campos_completados": contar_campos_preenchidos(dados_extraidos),
        "confianca_extracao": calcular_confianca(dados_extraidos),
        "num_chamadas_claude": num_chamadas_claude,
        "status": "sucesso",
    }


def obter_historico_importacoes(limite: int = 50) -> List[Dict]:
    """
    Obtém histórico das últimas importações de IA.
    
    Args:
        limite: Número máximo de registros
        
    Returns:
        Lista de importações ordenadas por data (mais recentes primeiro)
    """
    try:
        db = _obter_db()
        docs = db.collection("importacoes_ia").order_by(
            "data_importacao", 
            direction="DESCENDING"
        ).limit(limite).stream()
        
        importacoes = []
        for doc in docs:
            dados = doc.to_dict()
            dados["id"] = doc.id
            importacoes.append(dados)
        
        return importacoes
        
    except Exception as e:
        logger.error(f"Erro ao obter histórico: {e}")
        return []


def calcular_custo_mensal() -> Dict:
    """
    Calcula o custo total de importações do mês atual.
    
    Returns:
        Dict com estatísticas de custo
    """
    try:
        from datetime import datetime, timedelta
        
        db = _obter_db()
        agora = datetime.now()
        inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        docs = db.collection("importacoes_ia").where(
            "data_importacao", ">=", inicio_mes.isoformat()
        ).stream()
        
        total_custo_brl = 0.0
        total_tokens = 0
        total_processos = 0
        
        for doc in docs:
            dados = doc.to_dict()
            total_custo_brl += dados.get("custo_brl", 0)
            total_tokens += dados.get("tokens_total", 0)
            total_processos += 1
        
        custo_medio = total_custo_brl / total_processos if total_processos > 0 else 0
        
        return {
            "periodo": f"{agora.strftime('%B/%Y')}",
            "total_processos": total_processos,
            "total_tokens": total_tokens,
            "total_custo_brl": round(total_custo_brl, 2),
            "custo_medio_por_processo": round(custo_medio, 2),
            "limite_diario": obter_app_config().get("cost_limit_per_day", 250.00),
        }
        
    except Exception as e:
        logger.error(f"Erro ao calcular custo mensal: {e}")
        return {
            "periodo": "N/A",
            "total_processos": 0,
            "total_tokens": 0,
            "total_custo_brl": 0.0,
            "custo_medio_por_processo": 0.0
        }


def calcular_custo_hoje() -> float:
    """
    Calcula o custo das importações de hoje.
    
    Returns:
        Custo total em reais
    """
    try:
        from datetime import datetime
        
        db = _obter_db()
        agora = datetime.now()
        inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        
        docs = db.collection("importacoes_ia").where(
            "data_importacao", ">=", inicio_dia.isoformat()
        ).stream()
        
        total_custo = 0.0
        for doc in docs:
            dados = doc.to_dict()
            total_custo += dados.get("custo_brl", 0)
        
        return round(total_custo, 2)
        
    except Exception as e:
        logger.error(f"Erro ao calcular custo de hoje: {e}")
        return 0.0


def validar_limite_diario(custo_adicional_brl: float = 0.0) -> tuple:
    """
    Verifica se o limite diário de custo (R$) foi atingido.
    Este limite é sobre GASTO em reais, complementar ao limite de
    QUANTIDADE de chamadas verificado em validar_limite_chamadas_claude().
    
    Returns:
        Tupla: (permitido: bool, custo_atual: float, limite: float)
    """
    custo_hoje = calcular_custo_hoje()
    custo_adicional_brl = _normalizar_float_nao_negativo(custo_adicional_brl)
    limite = _normalizar_float_nao_negativo(
        obter_app_config().get("cost_limit_per_day", 250.00),
        250.00,
    )
    
    return (custo_hoje + custo_adicional_brl) <= limite, custo_hoje, limite


def registrar_chamada_claude(
    processo_id: str,
    etapa: str,
    sucesso: bool,
    detalhes: Dict | None = None,
):
    """
    Registra uma chamada individual à API Claude (cada chunk ou consolidação
    conta como uma chamada). Usado para controlar o limite diário de
    REQUISIÇÕES (max_api_calls_per_day), independente do custo em R$.
    """
    try:
        registro = {
            "processo_id": processo_id,
            "data_chamada": datetime.now().isoformat(),
            "etapa": etapa,
            "sucesso": sucesso,
            "detalhes": detalhes or {},
        }
        _obter_db().collection("claude_api_calls").add(registro)
    except Exception as exc:
        logger.warning("Não foi possível registrar chamada Claude: %s", exc)


def contar_chamadas_claude_hoje() -> int:
    """Conta quantas chamadas à API Claude já foram feitas hoje (UTC/local do servidor)."""
    try:
        agora = datetime.now()
        inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        docs = _obter_db().collection("claude_api_calls").where(
            "data_chamada", ">=", inicio_dia.isoformat()
        ).stream()
        return sum(1 for _ in docs)
    except Exception as exc:
        logger.error("Erro ao contar chamadas Claude de hoje: %s", exc)
        return 0


def validar_limite_chamadas_claude(chamadas_previstas: int = 1) -> tuple:
    """
    Verifica se realizar `chamadas_previstas` novas chamadas à API Claude
    ainda respeitaria o limite diário configurado em `max_api_calls_per_day`.

    Importante: para processos grandes que são divididos em vários "chunks",
    cada chunk + a chamada de consolidação final contam como chamadas
    separadas. Por isso a estimativa de chamadas é calculada antes de
    iniciar o processamento (ver core/ai_claude.py).

    Returns:
        Tupla: (permitido: bool, chamadas_hoje: int, limite: int)
    """
    chamadas_hoje = contar_chamadas_claude_hoje()
    limite = _normalizar_inteiro_nao_negativo(
        obter_app_config().get("max_api_calls_per_day", 50),
        50,
    )
    chamadas_previstas = _normalizar_inteiro_nao_negativo(chamadas_previstas, 1)
    permitido = (chamadas_hoje + chamadas_previstas) <= limite
    return permitido, chamadas_hoje, limite


def contar_campos_preenchidos(dados: Dict) -> int:
    """
    Conta quantos campos foram preenchidos nos dados extraídos.
    
    Args:
        dados: Dicionário com dados extraídos
        
    Returns:
        Número de campos com valores não-vazios
    """
    campos_preenchidos = 0
    for valor in dados.values():
        if valor and valor != "[Não localizado nos documentos]":
            if isinstance(valor, list):
                campos_preenchidos += len(valor)
            else:
                campos_preenchidos += 1
    return campos_preenchidos


def calcular_confianca(dados: Dict) -> float:
    """
    Calcula score de confiança da extração (0-100%).
    Baseado na quantidade de campos preenchidos vs total de campos esperados.
    
    Args:
        dados: Dicionário com dados extraídos
        
    Returns:
        Score de confiança (0.0 a 1.0)
    """
    campos_totais = len(dados)
    if campos_totais == 0:
        return 0.0
    
    campos_preenchidos = contar_campos_preenchidos(dados)
    confianca = campos_preenchidos / campos_totais
    
    return round(confianca, 2)


def exportar_historico_csv(limite: int = 100) -> str:
    """
    Gera CSV com histórico de importações para download.
    
    Args:
        limite: Número máximo de registros
        
    Returns:
        String formatada como CSV
    """
    importacoes = obter_historico_importacoes(limite)
    
    if not importacoes:
        return "Sem dados para exportar"
    
    # Header
    csv_content = "Data,Processo,Arquivos,Tokens,Custo (R$),Campos Completos,Confiança (%)\n"
    
    # Linhas
    for imp in importacoes:
        data = imp.get("data_importacao", "N/A")[:10]  # Apenas a data
        processo = imp.get("processo_id", "N/A")
        num_arquivos = imp.get("num_arquivos", 0)
        tokens = imp.get("tokens_total", 0)
        custo = imp.get("custo_brl", 0)
        campos = imp.get("campos_completados", 0)
        confianca = int(imp.get("confianca_extracao", 0) * 100)
        
        csv_content += f"{data},{processo},{num_arquivos},{tokens},R${custo:.2f},{campos},{confianca}%\n"
    
    return csv_content
