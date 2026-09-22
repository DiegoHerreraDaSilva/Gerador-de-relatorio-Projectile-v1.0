"""Rota de analytics agregado sobre `reports_db` (Fase 9 do
GUIA_EVOLUCAO_GERADOR_PROJECTILE.md) — só gerente, mesmo princípio de
`/management/*`: são métricas operacionais (quem gera mais relatório, taxa
de falha de geração), não dado pessoal de horas.

Sem fail-open: o único propósito desta rota é ler agregações de
`reports_db`, então se o banco estiver fora do ar a falha vira 502 (mesmo
contrato de `/reports/*`, ver `services/report_queries.py`)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services import report_queries
from ..dependencies import require_manager
from ..errors import GENERIC_REPORTS_DB_ERROR, log_and_generic_error

router = APIRouter()


@router.get("/analytics/summary")
async def analytics_summary_endpoint(_user: dict = Depends(require_manager)) -> dict:
    try:
        return report_queries.get_analytics_summary()
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
