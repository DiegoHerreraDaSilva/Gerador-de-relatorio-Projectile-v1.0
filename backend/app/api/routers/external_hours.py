"""Horas externas (`/parse-external`): lê a planilha própria de colaboradores que não
apontam no Projectile e devolve as linhas já validadas — o frontend decide em que
pacote/grupo do relatório aberto cada uma entra. Só gerente e coordenador.

Rota de upload é `async def` (precisa do `await` do stream), então a leitura do .xlsx
vai por `run_in_threadpool`; o modelo é `def` comum (a thread é do FastAPI)."""

from __future__ import annotations

import os
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ... import external_hours
from ...services import audit
from ..dependencies import require_manager_or_coordinator
from . import parsing

router = APIRouter()

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_upload(tmp_path: str):
    parsing._reject_if_oversized_uncompressed(tmp_path)
    return external_hours.parse_external_hours(tmp_path)


@router.post("/parse-external")
async def parse_external_endpoint(file: UploadFile = File(...), user: dict = Depends(require_manager_or_coordinator)):
    tmp_path = await parsing._stream_upload_to_tempfile(file, parsing._MAX_UPLOAD_BYTES)
    try:
        rows, issues = await run_in_threadpool(_parse_upload, tmp_path)
    except zipfile.BadZipFile:
        raise HTTPException(400, "O arquivo enviado não é um .xlsx válido.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        os.remove(tmp_path)

    # só contagens: nada do conteúdo da planilha vai pra auditoria
    await run_in_threadpool(
        audit.record_event,
        actor_id=user["login"],
        actor_name=user.get("name", ""),
        action="external_hours_parsed",
        entity_type="external_hours",
        entity_id=user["login"],
        source="external_hours",
        metadata={"rows": len(rows), "issues": len(issues), "hours": round(sum(r.hours for r in rows), 3)},
    )
    return {"rows": [r.as_dict() for r in rows], "issues": [i.as_dict() for i in issues]}


@router.get("/parse-external/template")
def external_hours_template(_user: dict = Depends(require_manager_or_coordinator)):
    return Response(
        content=external_hours.build_template(), media_type=_XLSX, headers={"Content-Disposition": 'attachment; filename="modelo-horas-externas.xlsx"'}
    )
