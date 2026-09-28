"""
Rastreamento de custos de API Claude e histórico de importações.
Registra todas as requisições no Firebase para auditoria e relatórios.
"""

import streamlit as st
import logging
from datetime import datetime
from typing import Dict, List
from core.database import _obter_db

logger = logging.getLogger(__name__)


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
        
        # Converter custo para reais (aproximação: 1 USD = 5.00 BRL)
        custo_brl = custo_real * 5.00
        
        registro = {
            "processo_id": processo_id,
            "data_importacao": datetime.now().isoformat(),
            "arquivos": nomes_arquivos,
            "num_arquivos": len(nomes_arquivos),
            "tokens_entrada": tokens_entrada,
            "tokens_saida": tokens_saida,
            "tokens_total": tokens_entrada + tokens_saida,
            "custo_usd": round(custo_real, 4),
            "custo_brl": round(custo_brl, 2),
            "campos_completados": contar_campos_preenchidos(dados_extraidos),
            "confianca_extracao": calcular_confianca(dados_extraidos),
            "status": "sucesso"
        }
        
        # Salvar em coleção "importacoes_ia"
        db.collection("importacoes_ia").add(registro)
        
        logger.info(f"Importação registrada: {processo_id} - R$ {custo_brl:.2f}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao registrar importação: {e}")
        st.error(f"⚠️ Erro ao registrar custo: {e}")
        return False


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
            "limite_diario": st.secrets.get("app", {}).get("cost_limit_per_day", 250.00)
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


def validar_limite_diario() -> tuple:
    """
    Verifica se o limite diário de API foi atingido.
    
    Returns:
        Tupla: (permitido: bool, custo_atual: float, limite: float)
    """
    custo_hoje = calcular_custo_hoje()
    limite = st.secrets.get("app", {}).get("cost_limit_per_day", 250.00)
    
    return custo_hoje < limite, custo_hoje, limite


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
