"""Rotas da aba "Geração automática" (`/auto-generation/*`) — todas só
gerente (`require_manager`), classificadas em `_MANAGER_ONLY` da matriz de
`test_coordinator_access.py`. Regra em `backend/app/auto_generation/`."""
from __future__ import annotations

import io
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import ValidationError

from ...auto_generation import builder, service
from ...auto_generation.schemas import (
    ApproveRequest,
    CombinedSendRequest,
    CommentRequest,
    FamilyRequest,
    NumbersRequest,
    ReviewerRequest,
    RunRequest,
    SendRequest,
    SaveDraftRequest,
)
from ... import email_ingest
from ...projectile_db import ProjectileDbError
from ...services.auto_generation_store import VersionConflict
from ...services.report_files import FORMAT_MEDIA_TYPES
from ..dependencies import require_manager
from ..errors import GENERIC_EMAIL_ERROR, log_and_generic_error

router = APIRouter()


def _call(fn, *args, **kwargs):
    """Erros do fluxo → HTTP: 404 inexistente, 409 estado/versão, 400
    aprovação/competência, 422 configuração inválida, 502 Projectile."""
    try:
        return fn(*args, **kwargs)
    except service.NotFound:
        raise HTTPException(404, "Relatório automático não encontrado.")
    except VersionConflict as e:
        raise HTTPException(409, {"message": "O rascunho foi alterado em outro lugar — recarregue.",
                                  "current_version": e.current_version})
    except service.RunInProgress:
        raise HTTPException(409, "Já existe uma geração em andamento pra essa competência.")
    except service.WorkflowError as e:
        raise HTTPException(409, str(e))
    except service.ApprovalRejected as e:
        raise HTTPException(400, {"message": "Não deu pra aprovar.", "errors": e.errors})
    except service.InvalidRequest as e:
        raise HTTPException(400, str(e))
    except builder.InvalidCompetence as e:
        raise HTTPException(400, str(e))
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False))
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    except email_ingest.EmailIngestError as e:
        raise log_and_generic_error(e, generic_message=GENERIC_EMAIL_ERROR)


@router.get("/auto-generation/config")
async def get_config_endpoint(_user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.get_configuration)


@router.put("/auto-generation/config")
async def put_config_endpoint(body: dict, _user: dict = Depends(require_manager)):
    return {"config": await run_in_threadpool(_call, service.set_global_config, body, _user)}


@router.put("/auto-generation/rules/{family_key}")
async def put_rule_endpoint(family_key: str, body: dict, _user: dict = Depends(require_manager)):
    if len(family_key) > 255:
        raise HTTPException(400, "Família inválida.")
    return {"config": await run_in_threadpool(_call, service.set_family_rule, family_key, body, _user)}


@router.delete("/auto-generation/rules/{family_key}")
async def delete_rule_endpoint(family_key: str, _user: dict = Depends(require_manager)):
    await run_in_threadpool(_call, service.set_family_rule, family_key, None, _user)
    return {"ok": True}


@router.put("/auto-generation/families/{project_id}")
async def put_family_endpoint(project_id: str, body: FamilyRequest, _user: dict = Depends(require_manager)):
    await run_in_threadpool(_call, service.set_family_override, project_id, body.family_key, _user)
    return {"ok": True}


@router.get("/auto-generation/competences")
async def list_competences_endpoint(_user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.list_competences)


@router.get("/auto-generation/competences/{competence}")
async def competence_endpoint(competence: str, _user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.competence_view, competence)


@router.get("/auto-generation/competences/{competence}/preview")
async def preview_endpoint(competence: str, _user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.preview, competence)


@router.post("/auto-generation/competences/{competence}/run", status_code=202)
async def run_endpoint(competence: str, body: RunRequest, _user: dict = Depends(require_manager)):
    run = await run_in_threadpool(_call, service.start_run, competence, _user, body.project_ids)
    return {"run": service._public_run(run)}


@router.get("/auto-generation/reports/{report_id}")
async def report_endpoint(report_id: str, _user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.detail, report_id)


@router.put("/auto-generation/reports/{report_id}/draft")
async def save_draft_endpoint(report_id: str, body: SaveDraftRequest, _user: dict = Depends(require_manager)):
    version = await run_in_threadpool(_call, service.save_draft, report_id, body.draft, body.draft_version, _user)
    return {"draft_version": version}


@router.patch("/auto-generation/reports/{report_id}/numbers")
async def numbers_endpoint(report_id: str, body: NumbersRequest, _user: dict = Depends(require_manager)):
    version = await run_in_threadpool(_call, service.set_numbers, report_id, body.numbers, body.draft_version, _user)
    return {"draft_version": version}


@router.post("/auto-generation/reports/{report_id}/approve")
async def approve_endpoint(report_id: str, body: ApproveRequest, _user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.approve, report_id, body.payload, body.draft_version, _user)


@router.post("/auto-generation/reports/{report_id}/skip")
async def skip_endpoint(report_id: str, body: CommentRequest, _user: dict = Depends(require_manager)):
    await run_in_threadpool(_call, service.skip, report_id, _user, body.comment)
    return {"ok": True}


@router.post("/auto-generation/reports/{report_id}/reopen")
async def reopen_endpoint(report_id: str, body: CommentRequest, _user: dict = Depends(require_manager)):
    await run_in_threadpool(_call, service.reopen, report_id, _user, body.comment)
    return {"ok": True}


@router.post("/auto-generation/reports/{report_id}/regenerate")
async def regenerate_endpoint(report_id: str, _user: dict = Depends(require_manager)):
    await run_in_threadpool(_call, service.regenerate, report_id, _user)
    return {"ok": True}


@router.get("/auto-generation/reviewers")
async def reviewers_endpoint(_user: dict = Depends(require_manager)):
    """Quem pode ser atribuído como revisor (engenharia com login)."""
    return {"reviewers": await run_in_threadpool(_call, service.reviewer_candidates)}


@router.put("/auto-generation/reports/{report_id}/reviewer")
async def reviewer_endpoint(report_id: str, body: ReviewerRequest, _user: dict = Depends(require_manager)):
    return await run_in_threadpool(_call, service.assign_reviewer, report_id, body.login, _user)


@router.post("/auto-generation/reports/{report_id}/return")
async def return_endpoint(report_id: str, body: CommentRequest, _user: dict = Depends(require_manager)):
    """Devolve ao revisor com o que precisa mudar."""
    await run_in_threadpool(_call, service.return_to_reviewer, report_id, body.comment, _user)
    return {"ok": True}


@router.get("/auto-generation/reports/{report_id}/send")
async def send_defaults_endpoint(report_id: str, _user: dict = Depends(require_manager)):
    """O que o modal de envio abre preenchido (destinatários do último envio, anexos...)."""
    return await run_in_threadpool(_call, service.send_defaults, report_id, _user)


@router.post("/auto-generation/reports/{report_id}/send")
async def send_endpoint(report_id: str, body: SendRequest, _user: dict = Depends(require_manager)):
    """Envia ao cliente os arquivos aprovados, pela caixa de quem está logado."""
    return await run_in_threadpool(
        _call, service.send_report, report_id, body.to, body.cc, body.subject, body.message, _user, body.formats,
    )


@router.get("/auto-generation/files")
async def bulk_files_endpoint(ids: list[str] = Query(default=[]), _user: dict = Depends(require_manager)):
    """Download em lote: os arquivos aprovados dos relatórios escolhidos num ZIP só."""
    files = await run_in_threadpool(_call, service.approved_files_many, ids)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('Relatórios_Horas.zip')}"})


@router.post("/auto-generation/send")
async def combined_send_endpoint(body: CombinedSendRequest, _user: dict = Depends(require_manager)):
    """Vários relatórios aprovados num e-mail só (cada arquivo um anexo)."""
    return await run_in_threadpool(
        _call, service.send_reports, body.report_ids, body.to, body.cc, body.subject, body.message, _user, body.formats,
    )


@router.get("/auto-generation/reports/{report_id}/files")
async def files_endpoint(report_id: str, _user: dict = Depends(require_manager)):
    """Os arquivos EXATOS que serão enviados (do payload congelado na aprovação)."""
    files = await run_in_threadpool(_call, service.approved_files, report_id)
    if len(files) == 1:
        name, data = files[0]
        ext = name.rsplit(".", 1)[-1]
        return Response(data, media_type=FORMAT_MEDIA_TYPES.get(ext, "application/octet-stream"),
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('Relatórios_Horas.zip')}"})

