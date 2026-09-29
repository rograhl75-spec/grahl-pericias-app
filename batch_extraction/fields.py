"""
Extração de campos por regras (regex).

As regras ficam isoladas neste módulo para evoluírem sem mexer no pipeline:
basta adicionar/alterar itens em :data:`DEFAULT_RULES`. Os nomes dos campos
seguem as chaves já usadas no app (``core/config.py``), facilitando a
importação posterior.

O extrator é incremental (:class:`FieldExtractor.feed`), recebendo uma página
por vez, para não exigir o texto completo do PDF em memória.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Pattern, Tuple

_NOME = r"([A-ZÀ-Ý0-9][^\n]{2,200})"


def _digits(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def normalize_cpf(valor: str) -> str:
    d = _digits(valor)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else valor.strip()


def normalize_cnpj(valor: str) -> str:
    d = _digits(valor)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else valor.strip()


def normalize_processo(valor: str) -> str:
    d = _digits(valor)
    if len(d) == 20:
        return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"
    return valor.strip()


def normalize_nome(valor: str) -> str:
    valor = re.split(r"\s+(?:CPF|CNPJ|RG|CTPS|ADVOGAD[OA]S?|PIS|NIT)\b", valor, maxsplit=1, flags=re.IGNORECASE)[0]
    return re.sub(r"\s+", " ", valor).strip(" -–:;,|")


def normalize_espacos(valor: str) -> str:
    return re.sub(r"\s+", " ", valor).strip(" -–:;,.|")


@dataclass
class FieldRule:
    """Regra de um campo: lista de regex (o 1º grupo é o valor) e normalizador."""

    name: str
    patterns: List[Pattern[str]]
    normalizer: Callable[[str], str] = normalize_espacos
    multiple: bool = False
    description: str = ""


def _p(regex: str, flags: int = 0) -> Pattern[str]:
    return re.compile(regex, flags | re.MULTILINE)


CNJ_REGEX = r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b"
CPF_REGEX = r"\b(\d{3}\.\d{3}\.\d{3}-\d{2})\b"
CNPJ_REGEX = r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b"

DEFAULT_RULES: List[FieldRule] = [
    FieldRule(
        "processo_num",
        [
            _p(r"(?:Processo|PROCESSO|Autos|AUTOS)\s*(?:n[º°o.]*|N[º°O.]*)?\s*:?\s*(\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4})"),
            _p(CNJ_REGEX),
        ],
        normalizer=normalize_processo,
        description="Número CNJ do processo",
    ),
    FieldRule(
        "orgao_julgador",
        [
            _p(r"[ÓO]rg[ãa]o\s+[Jj]ulgador\s*:\s*([^\n]{3,150})", re.IGNORECASE),
            _p(r"(\d{1,3}\s*[ªaº°]?\s*Vara\s+do\s+Trabalho\s+de\s+[A-Za-zÀ-ÿ' ]+?)\s*(?:[-–/,]|$)", re.IGNORECASE),
        ],
        description="Vara / órgão julgador",
    ),
    FieldRule(
        "data_autuacao",
        [
            _p(
                r"(?:Autuado\s+em|Data\s+da\s+autua[çc][ãa]o|Autua[çc][ãa]o|Distribu[íi]do\s+em|"
                r"Data\s+de\s+ajuizamento|Ajuizamento|Ajuizado\s+em)\s*:?\s*(\d{2}/\d{2}/\d{4})",
                re.IGNORECASE,
            ),
        ],
        description="Data de autuação / ajuizamento",
    ),
    FieldRule(
        "valor_causa",
        [_p(r"Valor\s+da\s+causa\s*:?\s*(R\$\s*[\d.]+,\d{2})", re.IGNORECASE)],
        description="Valor da causa",
    ),
    FieldRule(
        "rito_processual",
        [_p(r"\b(?:Classe|CLASSE|Rito|RITO)\s*(?:judicial|processual)?\s*:\s*([^\n]{3,120})", re.IGNORECASE)],
        description="Classe / rito processual",
    ),
    FieldRule(
        "reclamante_nome",
        [_p(r"^\s*(?:RECLAMANTE|Reclamante|AUTORA?|Autora?|REQUERENTE|Requerente)\s*:\s*" + _NOME)],
        normalizer=normalize_nome,
        description="Nome do(a) reclamante/autor(a)",
    ),
    FieldRule(
        "reclamada_nome",
        [
            _p(
                r"^\s*(?:RECLAMAD[OA]S?|Reclamad[oa]s?|R[ÉE]U|R[ée]u|R[ÉE]|REQUERID[OA]|Requerid[oa])\s*:\s*"
                + _NOME
            )
        ],
        normalizer=normalize_nome,
        description="Nome da reclamada/ré",
    ),
    FieldRule(
        "reclamante_cpf",
        [_p(r"CPF(?:/MF)?\s*(?:n[º°o.]*)?\s*:?\s*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b", re.IGNORECASE)],
        normalizer=normalize_cpf,
        description="Primeiro CPF rotulado encontrado (normalmente o do reclamante)",
    ),
    FieldRule(
        "reclamada_cnpj",
        [_p(r"CNP[J)](?:/MF)?\s*(?:n[º°o.]*)?\s*:?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b", re.IGNORECASE)],
        normalizer=normalize_cnpj,
        description="Primeiro CNPJ rotulado encontrado (normalmente o da reclamada)",
    ),
    FieldRule("processos_encontrados", [_p(CNJ_REGEX)], normalizer=normalize_processo, multiple=True),
    FieldRule("cpfs_encontrados", [_p(CPF_REGEX)], normalizer=normalize_cpf, multiple=True),
    FieldRule("cnpjs_encontrados", [_p(CNPJ_REGEX)], normalizer=normalize_cnpj, multiple=True),
]


@dataclass
class _Acumulado:
    valor: Optional[str] = None
    pagina: Optional[int] = None
    valores: List[str] = field(default_factory=list)
    paginas: List[int] = field(default_factory=list)


class FieldExtractor:
    """Aplica as regras página a página e guarda a 1ª ocorrência (ou todas, se ``multiple``)."""

    def __init__(self, rules: Optional[Iterable[FieldRule]] = None, max_values: int = 200):
        self.rules = list(DEFAULT_RULES if rules is None else rules)
        self.max_values = max_values
        self._dados: Dict[str, _Acumulado] = {regra.name: _Acumulado() for regra in self.rules}

    def feed(self, page_number: int, text: str) -> None:
        if not text:
            return
        for regra in self.rules:
            acumulado = self._dados[regra.name]
            if not regra.multiple and acumulado.valor is not None:
                continue
            for padrao in regra.patterns:
                encontrado = self._aplicar(regra, padrao, text, page_number, acumulado)
                if encontrado and not regra.multiple:
                    break

    def _aplicar(self, regra: FieldRule, padrao: Pattern[str], text: str, page: int, acc: _Acumulado) -> bool:
        encontrou = False
        for match in padrao.finditer(text):
            bruto = match.group(1) if match.groups() else match.group(0)
            valor = regra.normalizer(bruto)
            if not valor:
                continue
            encontrou = True
            if not regra.multiple:
                acc.valor, acc.pagina = valor, page
                return True
            if valor not in acc.valores and len(acc.valores) < self.max_values:
                acc.valores.append(valor)
                if page not in acc.paginas:
                    acc.paginas.append(page)
        return encontrou

    def result(self) -> Dict[str, dict]:
        saida: Dict[str, dict] = {}
        for regra in self.rules:
            acc = self._dados[regra.name]
            if regra.multiple:
                saida[regra.name] = {"valor": list(acc.valores), "paginas": list(acc.paginas)}
            else:
                saida[regra.name] = {"valor": acc.valor, "pagina": acc.pagina}
        return saida


def extract_fields(pages: Iterable[Tuple[int, str]], rules: Optional[Iterable[FieldRule]] = None) -> Dict[str, dict]:
    """Atalho: extrai campos de uma sequência ``(numero_pagina, texto)``."""
    extrator = FieldExtractor(rules)
    for numero, texto in pages:
        extrator.feed(numero, texto)
    return extrator.result()
