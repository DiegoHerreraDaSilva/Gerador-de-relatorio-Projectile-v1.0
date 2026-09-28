"""Família de projeto: o que se repete de um mês pro outro.

O Projectile abre UM projeto por mês pro mesmo trabalho ("Legislation
Package - Estribo 07.2026", "... 08.2026") e o mesmo vale pros pacotes de
trabalho ("1546.7.3-001 Legislation Package - Câmera - ATEGO 08.2026"). Regra
e memória presas ao `project_id`/nome exato teriam de ser refeitas todo mês —
por isso a chave é o nome SEM a data, junto com o cliente."""
from __future__ import annotations

import html
import re
import unicodedata

# "08.2026", "08/2026" como palavra solta (não pega "1546.7.3-001" nem "2025/2026")
_DATE_TOKEN = re.compile(r"(?<![\w.])(?:0[1-9]|1[0-2])[./](?:19|20)\d{2}(?![\w.])")
_SPACES = re.compile(r"\s+")
_EDGE_PUNCT = " -_–—.,;:/"


def clean(text: str | None) -> str:
    """Nome como aparece na tela: entidades HTML desfeitas (o Projectile tem
    `&amp;#...` duplo) e espaços normalizados."""
    return _SPACES.sub(" ", html.unescape(html.unescape(str(text or "")))).strip()


def strip_date(text: str | None) -> str:
    """Nome sem o sufixo de mês/ano: "Legislation Package - Estribo 08.2026"
    → "Legislation Package - Estribo"."""
    without = _DATE_TOKEN.sub(" ", clean(text))
    return _SPACES.sub(" ", without).strip(_EDGE_PUNCT)


def normalize_key(text: str | None) -> str:
    """Chave de comparação: sem data, sem acento, sem diferença de caixa."""
    base = unicodedata.normalize("NFD", strip_date(text).casefold())
    return "".join(ch for ch in base if unicodedata.category(ch) != "Mn")


def family_key(client: str | None, project_name: str | None) -> str:
    """`cliente|nome sem data` normalizados — até 255 caracteres (coluna)."""
    return f"{normalize_key(client) or '-'}|{normalize_key(project_name)}"[:255]


def family_label(project_name: str | None) -> str:
    return strip_date(project_name) or clean(project_name)
