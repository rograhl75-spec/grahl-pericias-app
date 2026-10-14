"""Fotos de campo: identidade estável, deduplicação e limite do documento."""

import base64
import hashlib
import json


# Limite documentado do Firestore para um único documento (1 MiB). As fotos
# ficam embutidas (base64) no documento do caso, por isso há um teto real de
# armazenamento por caso. O orçamento abaixo deixa margem para metadados.
FIRESTORE_DOC_LIMIT_BYTES = 1_048_576
DOC_SIZE_BUDGET_BYTES = 1_000_000
LEGENDA_PADRAO = "Registro fotográfico."


def foto_hash(foto):
    base64_value = foto.get("base64", "") if isinstance(foto, dict) else ""
    return hashlib.sha256(str(base64_value).encode("utf-8")).hexdigest()


def ids_fotos(fotos):
    """IDs estáveis por conteúdo (não por posição), únicos mesmo com duplicatas legadas."""
    vistos = {}
    ids = []
    for foto in fotos or []:
        base = foto_hash(foto)[:16]
        ocorrencia = vistos.get(base, 0)
        vistos[base] = ocorrencia + 1
        ids.append(f"{base}_{ocorrencia}")
    return ids


def criar_foto(bytes_imagem, gps=""):
    return {
        "base64": base64.b64encode(bytes_imagem).decode("utf-8"),
        "gps": gps or "",
        "legenda": LEGENDA_PADRAO,
    }


def adicionar_pendentes(salvas, pendentes, novas):
    """Inclui novas fotos na fila sem duplicar fotos salvas ou já pendentes."""
    conhecidas = {f.get("base64") for f in list(salvas or []) + list(pendentes or [])
                  if isinstance(f, dict)}
    fila = list(pendentes or [])
    adicionadas = duplicadas = 0
    for foto in novas:
        if foto.get("base64") in conhecidas:
            duplicadas += 1
            continue
        conhecidas.add(foto.get("base64"))
        fila.append(foto)
        adicionadas += 1
    return fila, adicionadas, duplicadas


def estimar_tamanho_documento(dados):
    return len(json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8"))


def separar_por_limite(dados_base, pendentes, limite=DOC_SIZE_BUDGET_BYTES):
    """Retorna (cabem, excedentes) mantendo a ordem de captura."""
    fotos = list(dados_base.get("campo_fotos", []) or [])
    tamanho = estimar_tamanho_documento({**dados_base, "campo_fotos": fotos})
    cabem = []
    for indice, foto in enumerate(pendentes):
        acrescimo = estimar_tamanho_documento(foto) + 2
        if tamanho + acrescimo > limite:
            return cabem, list(pendentes[indice:])
        tamanho += acrescimo
        cabem.append(foto)
    return cabem, []
