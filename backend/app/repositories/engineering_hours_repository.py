"""Horas apontadas da engenharia (CAD+CAE) pro chat analítico. Não faz
consulta nova: reaproveita `management._get_cached_rows` (a mesma busca do
Painel de Gerência, cache de 15 min) e só resolve cliente/nome de projeto em
lote. Agregação e filtros ficam em Python sobre essas linhas."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date

from .. import management
from ..projectile_db import fetch_project_details


@dataclass(frozen=True)
class HoursRow:
    day: date
    hours: float
    project_id: str | None
    project: str
    client: str
    employee: str
    package: str


def _clean(value) -> str:
    return html.unescape(html.unescape(str(value or ""))).strip()


def load_rows(start: date, end: date) -> list[HoursRow]:
    """Linhas de horas de engenharia entre `start` e `end` (inclusive).
    `management._get_cached_rows` é referenciado via atributo do módulo — os
    testes trocam essa função por dados fixos."""
    raw = management._get_cached_rows(start.isoformat(), end.isoformat())
    project_ids = sorted({r["project_id"] for r in raw if r.get("project_id")})
    details = fetch_project_details(project_ids) if project_ids else {}
    rows = []
    for r in raw:
        row_date = r.get("data")
        day = row_date if isinstance(row_date, date) else date.fromisoformat(str(row_date)[:10])
        info = details.get(r.get("project_id")) or {}
        rows.append(HoursRow(
            day=day,
            hours=round(float(r.get("horas") or 0), 3),
            project_id=r.get("project_id"),
            project=_clean(info.get("name")) or "Sem projeto",
            client=_clean(info.get("client")) or "Sem cliente",
            employee=_clean(r.get("person")) or "Sem nome",
            package=_clean(r.get("pacote")) or "Sem pacote",
        ))
    return rows
