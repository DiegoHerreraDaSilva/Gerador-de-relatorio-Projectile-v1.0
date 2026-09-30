"""Rota de analytics agregado sobre `reports_db` — só gerente, mesmo princípio de
`/management/*`: são métricas operacionais (quem gera mais relatório, taxa
de falha de geração), não dado pessoal de horas.

Sem fail-open: o único propósito desta rota é ler agregações de
`reports_db`, então se o banco estiver fora do ar a falha vira 502 (mesmo
contrato de `/reports/*`, ver `services/report_queries.py`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services import report_queries, system_health
from ..dependencies import require_manager
from ..errors import GENERIC_REPORTS_DB_ERROR, log_and_generic_error

router = APIRouter()


@router.get("/analytics/summary")
def analytics_summary_endpoint(_user: dict = Depends(require_manager)) -> dict:
    try:
        return report_queries.get_analytics_summary()
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/analytics/health")
def analytics_health_endpoint(_user: dict = Depends(require_manager)) -> dict:
    """Saúde do sistema (geração, artefatos em disco, última rodada da
    geração automática, mensagens ignoradas) — só gerente, mesmo contrato de
    erro de `/analytics/summary` (banco fora do ar → 502 genérico)."""
    try:
        return system_health.get_system_health()
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
