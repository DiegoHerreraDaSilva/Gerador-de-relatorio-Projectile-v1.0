"""Helpers usados por mais de um router — não cabem em nenhum router
específico. Extraído de `main.py`."""
from __future__ import annotations

import calendar

from fastapi import HTTPException

from ..generator import parse_month_label, parse_period_label


def resolve_month_range(month_label: str) -> tuple[str, str]:
    """1º dia do mês inicial até o último dia do mês final. Aceita tanto um
    mês único ("Julho/2026") quanto uma label de PERÍODO ("Julho a
    Novembro/2026", "Dezembro/2025 a Fevereiro/2026", ver
    `generator.parse_period_label`) — mês único é tentado primeiro, sem
    mudança de comportamento pro caso de sempre. Usado por `parsing.py`
    (`/parse-db`, `/parse-db-client`) e `management.py`
    (`/management/clients-with-hours`, `/management/client-projects`)."""
    parsed_month = parse_month_label(month_label)
    if parsed_month:
        start_year, start_month = end_year, end_month = parsed_month
    else:
        parsed_period = parse_period_label(month_label)
        if not parsed_period:
            raise HTTPException(
                400,
                f'Mês/período de referência inválido: "{month_label}" '
                '(use o formato "Julho/2026" ou "Julho a Novembro/2026").',
            )
        (start_year, start_month), (end_year, end_month) = parsed_period
    start_date = f"{start_year:04d}-{start_month:02d}-01"
    end_date = f"{end_year:04d}-{end_month:02d}-{calendar.monthrange(end_year, end_month)[1]:02d}"
    return start_date, end_date


def build_parse_response(packages, issues) -> dict:
    """Formato de resposta comum a `/parse`, `/parse-db` e `/parse-db-client`
    (`parsing.py`) — os três produzem a mesma forma `{packages, issues}` a
    partir de `list[WorkPackage]`/`list[RowIssue]`."""
    return {
        "packages": [
            {
                "key": pkg.key,
                "project_name": pkg.project_name,
                "groups": [
                    {
                        "name": g.name,
                        "total_hours": g.total_hours,
                        "activities": [{"description": a.description, "hours": a.hours} for a in g.activities],
                    }
                    for g in pkg.groups
                ],
            }
            for pkg in packages
        ],
        "issues": [
            {
                "row": i.row,
                "reason": i.reason,
                "message": i.message,
                "raw_hours": i.raw_hours,
                "raw_description": i.raw_description,
            }
            for i in issues
        ],
    }
