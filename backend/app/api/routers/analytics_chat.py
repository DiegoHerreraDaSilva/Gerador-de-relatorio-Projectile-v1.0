"""`POST /analytics/chat` — chat analítico (só gerente). Separado do
`/chat` de edição do relatório: este lê histórico e horas, nunca mexe no
relatório aberto. Fluxo em `analytics/service.py`."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError

from ...analytics import service
from ...analytics.schemas import AnalyticsChatRequest
from ...db.reports_db import ReportsDbError
from ...projectile_db import ProjectileDbError
from ..dependencies import require_manager
from ..errors import GENERIC_DB_ERROR, GENERIC_REPORTS_DB_ERROR, log_and_generic_error

router = APIRouter()


@router.post("/analytics/chat")
async def analytics_chat_endpoint(payload: AnalyticsChatRequest, _user: dict = Depends(require_manager)):
    try:
        # consultas e chamadas HTTP bloqueantes — fora do event loop
        return await asyncio.to_thread(service.handle, payload.message, payload.context, _user)
    except ProjectileDbError as e:
        raise log_and_generic_error(e, generic_message=GENERIC_DB_ERROR)
    except (SQLAlchemyError, ReportsDbError) as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
