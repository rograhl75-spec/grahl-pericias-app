"""Fotos de campo: identidade estável, deduplicação e limite do documento."""

import base64
import hashlib
import json
from pathlib import Path


# Limite do documento: textos, referências e fotos legadas em base64.
# Os bytes de fotos novas ficam no Storage. O orçamento deixa margem.
FIRESTORE_DOC_LIMIT_BYTES = 1_048_576
DOC_SIZE_BUDGET_BYTES = 1_000_000
LEGENDA_PADRAO = "Registro fotográfico."


def foto_hash(foto):
    if not isinstance(foto, dict):
        foto = {}
    if foto.get("base64"):
        try:
            dados = base64.b64decode(foto["base64"], validate=True)
        except (ValueError, TypeError):
            dados = str(foto["base64"]).encode("utf-8")
        return hashlib.sha256(dados).hexdigest()
    if foto.get("hash"):
        return foto["hash"]
    if foto.get("path"):
        try:
            return hashlib.sha256(Path(foto["path"]).read_bytes()).hexdigest()
        except OSError:
            pass
    return hashlib.sha256(str(foto.get("storage_path") or foto.get("path", "")).encode("utf-8")).hexdigest()


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
    conhecidas = {foto_hash(f) for f in list(salvas or []) + list(pendentes or [])
                  if isinstance(f, dict)}
    fila = list(pendentes or [])
    adicionadas = duplicadas = 0
    for foto in novas:
        identidade = foto_hash(foto)
        if identidade in conhecidas:
            duplicadas += 1
            continue
        conhecidas.add(identidade)
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


def resumo_armazenamento(dados_caso, pendentes=None, limite=DOC_SIZE_BUDGET_BYTES):
    """Conta referências/legado e estima o documento, sem bytes novos do Storage."""
    dados_caso = dados_caso or {}
    usados = estimar_tamanho_documento(dados_caso)
    return {
        "salvas": len(list(dados_caso.get("campo_fotos", []) or [])),
        "storage": sum(bool(f.get("storage_path")) for f in dados_caso.get("campo_fotos", []) or []),
        "legadas": sum(not f.get("storage_path") for f in dados_caso.get("campo_fotos", []) or []),
        "pendentes": len(list(pendentes or [])),
        "bytes_usados": usados,
        "bytes_limite": limite,
        "fracao_usada": min(usados / limite, 1.0) if limite else 1.0,
    }
