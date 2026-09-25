"""Rotas de histórico de relatórios (`GET /reports/*`,
`GET /artifacts/{id}/download`) — extraído de `main.py`."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ... import management
from ...services import report_queries
from ...services.audit import record_event
from ..dependencies import require_session
from ..errors import GENERIC_REPORTS_DB_ERROR, log_and_generic_error

router = APIRouter()

_MAX_PAGE_SIZE = report_queries.MAX_PAGE_SIZE


def _require_report_access(report: dict, user: dict) -> None:
    """Relatórios pessoais (gerados via /parse-db) só podem ser vistos por
    quem os criou; gerentes veem tudo — mesmo princípio de /parse-db e
    /my-hours: nunca expor dado de uma pessoa pra outra sem ser gerente.
    Referencia `management.MANAGEMENT_PANEL_LOGINS` via atributo do módulo
    (não `from ... import MANAGEMENT_PANEL_LOGINS`) pelo mesmo motivo de
    `api/dependencies.py`: um teste que faz
    `monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", ...)`
    precisa afetar esta checagem também."""
    if user["login"].lower() in management.MANAGEMENT_PANEL_LOGINS:
        return
    if (report.get("created_by") or "").lower() != user["login"].lower():
        raise HTTPException(403, "Sem acesso a este relatório.")


def _get_report_or_404(report_id: str) -> dict:
    try:
        report = report_queries.get_report(report_id)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if report is None:
        raise HTTPException(404, "Relatório não encontrado.")
    return report


@router.get("/reports")
async def list_reports_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    report_number: str | None = None,
    competence: str | None = None,
    status: str | None = None,
    created_by: str | None = None,
    q: str | None = Query(None, max_length=200),
    _user: dict = Depends(require_session),
):
    """`q` = busca geral por Número, Projeto, Competência e Criado por. Pra
    quem não é gerente ela roda DENTRO dos próprios relatórios — nunca amplia
    o recorte de `created_by`."""
    is_mgr = _user["login"].lower() in management.MANAGEMENT_PANEL_LOGINS
    # nunca aceita created_by de quem não é gerente — mesma regra de
    # /parse-db (não confiar em identidade vinda do cliente pra consultar
    # dado de outra pessoa).
    effective_created_by = created_by if is_mgr else _user["login"]
    try:
        return report_queries.list_reports(
            page=page, page_size=page_size, report_number=report_number,
            competence=competence, status=status, created_by=effective_created_by, search=q,
        )
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}")
async def get_report_endpoint(report_id: str, _user: dict = Depends(require_session)):
    report = _get_report_or_404(report_id)
    _require_report_access(report, _user)
    return report


@router.get("/reports/{report_id}/versions")
async def list_report_versions_endpoint(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    _user: dict = Depends(require_session),
):
    report = _get_report_or_404(report_id)
    _require_report_access(report, _user)
    try:
        return report_queries.list_versions(report_id, page=page, page_size=page_size)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}/versions/{version_id}")
async def get_report_version_endpoint(report_id: str, version_id: str, _user: dict = Depends(require_session)):
    report = _get_report_or_404(report_id)
    _require_report_access(report, _user)
    try:
        version = report_queries.get_version_detail(report_id, version_id)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if version is None:
        raise HTTPException(404, "Versão não encontrada.")
    return version


@router.get("/reports/{report_id}/generations")
async def list_report_generations_endpoint(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    _user: dict = Depends(require_session),
):
    report = _get_report_or_404(report_id)
    _require_report_access(report, _user)
    try:
        return report_queries.list_generations(report_id, page=page, page_size=page_size)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}/artifacts")
async def list_report_artifacts_endpoint(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    _user: dict = Depends(require_session),
):
    report = _get_report_or_404(report_id)
    _require_report_access(report, _user)
    try:
        return report_queries.list_artifacts(report_id, page=page, page_size=page_size)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}/audit")
async def get_report_audit_endpoint(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    _user: dict = Depends(require_session),
):
    report = _get_report_or_404(report_id)
    _require_report_access(report, _user)
    try:
        return report_queries.list_audit_events_for_report(report_id, page=page, page_size=page_size)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact_endpoint(artifact_id: str, _user: dict = Depends(require_session)):
    try:
        artifact = report_queries.get_artifact(artifact_id)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if artifact is None:
        raise HTTPException(404, "Artifact não encontrado.")
    _require_report_access(artifact, _user)
    if not os.path.exists(artifact["storage_path"]):
        raise HTTPException(404, "O arquivo deste artifact não existe mais em disco.")
    record_event(
        actor_id=_user["login"], actor_name=_user["name"], action="artifact_downloaded",
        entity_type="report_artifact", entity_id=artifact_id, source="download_endpoint",
    )
    return FileResponse(artifact["storage_path"], filename=artifact["file_name"], media_type=artifact["mime_type"])
