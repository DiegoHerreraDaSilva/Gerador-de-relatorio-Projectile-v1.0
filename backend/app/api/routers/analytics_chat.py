"""`POST /analytics/chat` — chat analítico (só gerente). Separado do
`/chat` de edição do relatório: este lê histórico e horas, nunca mexe no
relatório aberto. Fluxo em `analytics/service.py`."""
from __future__ import annotations

import asyncio

from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError

from ...analytics import export, service
from ...analytics.schemas import AnalyticsChatRequest, ExportRequest
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


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/analytics/chat/export")
async def analytics_chat_export_endpoint(payload: ExportRequest, _user: dict = Depends(require_manager)):
    """Tabela já exibida no chat → .xlsx. Não consulta banco nenhum."""
    content = await asyncio.to_thread(export.build_xlsx, payload)
    filename = export.filename_for(payload.title)
    return Response(
        content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"},
    )
