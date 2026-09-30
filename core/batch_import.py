"""
Consolidação determinística dos resultados da importação de PDFs em lotes.

Cada lote é analisado separadamente pela Claude; aqui os JSONs já normalizados de
cada lote são mesclados sem nova chamada à IA (sem custo nem cota adicionais).

Regras de mesclagem (sempre na ordem dos lotes, que segue a ordem dos arquivos e páginas):
- Valores vazios ou "[Não localizado nos documentos]" são ignorados.
- Valores iguais (ignorando espaços e maiúsculas/minúsculas) são unificados.
- CAMPOS_PRIMEIRO_VALOR (identificação do processo e das partes): vale o primeiro lote
  que informou o campo; valores divergentes de outros lotes são registrados em
  `conflitos` para revisão do usuário.
- CAMPOS_ULTIMO_VALOR (fase processual e agenda da vistoria): vale o último lote, pois
  reflete a peça mais recente; divergências também vão para `conflitos`.
- Demais campos (narrativos, documentos, quesitos): valores distintos são concatenados.
- quadro_epis: itens concatenados, sem duplicar descricao/ca/data_entrega.
- fontes: as referências de cada lote que contribuiu para o valor final são preservadas
  com a identificação do lote; se a Claude não informou fonte, usa-se o intervalo de
  arquivos/páginas do lote.
"""

from typing import Dict, List, Tuple

from core.ai_claude import CAMPOS_TEXTO_EXTRACAO
from core.pdf_processor import descrever_lote

NAO_LOCALIZADO = "[Não localizado nos documentos]"

CAMPOS_PRIMEIRO_VALOR = frozenset({
    "processo_num",
    "orgao_julgador",
    "data_autuacao",
    "valor_causa",
    "rito_processual",
    "reclamante_nome",
    "reclamante_cpf",
    "reclamada_nome",
    "reclamada_cnpj",
    "data_admissao",
    "status_contrato",
    "periodo_imprescrito",
    "ultima_remuneracao",
    "segurado_nascimento",
})

CAMPOS_ULTIMO_VALOR = frozenset({
    "fase_processual",
    "campo_data",
    "campo_horario",
    "local_diligencia",
})

MAX_CHARS_VALOR_CONFLITO = 300


def _valor_util(valor) -> str:
    if valor is None or isinstance(valor, (dict, list)):
        return ""
    texto = str(valor).strip()
    if not texto or texto.startswith("[Não localizado"):
        return ""
    return texto


def _chave(valor: str) -> str:
    return " ".join(valor.split()).casefold()


def _fonte_lote(dados: Dict, campo: str, lote: Dict) -> str:
    indice = lote.get("indice")
    fontes = dados.get("fontes") if isinstance(dados.get("fontes"), dict) else {}
    referencia = _valor_util(fontes.get(campo))
    if referencia:
        return f"{referencia} [lote {indice}]"
    return f"{descrever_lote(lote)} [lote {indice}]"


def _juntar_fontes(fontes: List[str]) -> str:
    unicas = []
    for fonte in fontes:
        if fonte not in unicas:
            unicas.append(fonte)
    return "; ".join(unicas)


def _resumir(valor: str) -> str:
    if len(valor) <= MAX_CHARS_VALOR_CONFLITO:
        return valor
    return valor[: MAX_CHARS_VALOR_CONFLITO - 1] + "…"


def consolidar_resultados_lotes(
    resultados: List[Dict],
    lotes: List[Dict],
) -> Tuple[Dict, Dict[str, List[str]]]:
    """
    Mescla os dados extraídos de cada lote em um único resultado.

    Returns:
        Tupla: (dados_consolidados, conflitos) em que `conflitos` mapeia o campo para a
        lista "Lote N: valor" dos valores divergentes (resumidos) encontrados.
    """
    if not resultados or len(resultados) != len(lotes):
        raise ValueError("Os resultados dos lotes estão incompletos; a importação não foi concluída.")

    consolidado: Dict = {}
    fontes_finais: Dict[str, str] = {}
    conflitos: Dict[str, List[str]] = {}

    for campo in CAMPOS_TEXTO_EXTRACAO:
        distintos: List[Dict] = []
        for dados, lote in zip(resultados, lotes):
            valor = _valor_util((dados or {}).get(campo))
            if not valor:
                continue
            fonte = _fonte_lote(dados, campo, lote)
            existente = next((item for item in distintos if item["chave"] == _chave(valor)), None)
            if existente:
                existente["fontes"].append(fonte)
                existente["lotes"].append(lote.get("indice"))
            else:
                distintos.append({
                    "valor": valor,
                    "chave": _chave(valor),
                    "fontes": [fonte],
                    "lotes": [lote.get("indice")],
                })

        if not distintos:
            consolidado[campo] = NAO_LOCALIZADO
            continue

        if campo in CAMPOS_PRIMEIRO_VALOR or campo in CAMPOS_ULTIMO_VALOR:
            escolhido = distintos[-1] if campo in CAMPOS_ULTIMO_VALOR else distintos[0]
            consolidado[campo] = escolhido["valor"]
            fontes_finais[campo] = _juntar_fontes(escolhido["fontes"])
            if len(distintos) > 1:
                conflitos[campo] = [
                    f"Lote {item['lotes'][0]}: {_resumir(item['valor'])}" for item in distintos
                ]
        else:
            consolidado[campo] = "\n\n".join(item["valor"] for item in distintos)
            fontes_finais[campo] = _juntar_fontes(
                [fonte for item in distintos for fonte in item["fontes"]]
            )

    quadro_epis: List[Dict] = []
    chaves_epis = set()
    fontes_epis: List[str] = []
    for dados, lote in zip(resultados, lotes):
        itens = (dados or {}).get("quadro_epis") or []
        contribuiu = False
        for item in itens:
            if not isinstance(item, dict):
                continue
            normalizado = {
                chave: str(item.get(chave) or "").strip()
                for chave in ("descricao", "ca", "data_entrega", "obs")
            }
            if not any(normalizado.values()):
                continue
            chave_epi = tuple(
                _chave(normalizado[chave]) for chave in ("descricao", "ca", "data_entrega")
            )
            if chave_epi in chaves_epis:
                continue
            chaves_epis.add(chave_epi)
            quadro_epis.append(normalizado)
            contribuiu = True
        if contribuiu:
            fontes_epis.append(_fonte_lote(dados, "quadro_epis", lote))
    consolidado["quadro_epis"] = quadro_epis
    if fontes_epis:
        fontes_finais["quadro_epis"] = _juntar_fontes(fontes_epis)

    consolidado["fontes"] = fontes_finais
    return consolidado, conflitos
