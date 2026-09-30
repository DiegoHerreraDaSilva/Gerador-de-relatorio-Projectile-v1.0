"""Rotas de histórico de relatórios (`GET /reports/*`,
`GET /artifacts/{id}/download`) — extraído de `main.py`."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ...core import authz
from ...services import report_queries
from ...services.audit import record_event
from .. import period_access
from ..dependencies import require_session
from ..errors import GENERIC_REPORTS_DB_ERROR, log_and_generic_error

router = APIRouter()

_MAX_PAGE_SIZE = report_queries.MAX_PAGE_SIZE


def _viewer(user: dict) -> str | None:
    """Login que limita o que se vê; `None` = gerente, vê tudo."""
    return None if authz.is_manager(user) else user["login"]


def _check_window(user: dict, start) -> None:
    # fora da janela (últimos 12 meses e o ano atual): some pra quem não é gerente
    if start is not None and not period_access.in_window(user, start):
        raise HTTPException(404, "Relatório não encontrado.")


def _require_report_access(report: dict, user: dict) -> None:
    """O `report` é a identidade compartilhada (número + escopo + competência);
    quem não é gerente só acessa se ELE criou ao menos uma versão e, dentro
    dele, só vê o que ele mesmo gerou (versões, gerações, arquivos e auditoria
    filtram pelo mesmo login). Gerente vê tudo — mesmo princípio de /parse-db
    e /my-hours: nunca expor dado de uma pessoa pra outra. Gerente vem de
    `core.authz` (função chamada na hora, nunca um set importado)."""
    if authz.is_manager(user):
        return
    try:
        allowed = report_queries.viewer_has_access(report["id"], user["login"])
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if not allowed:
        raise HTTPException(403, "Sem acesso a este relatório.")
    _check_window(user, report.get("competence_start") or report.get("created_at"))


def _get_report_or_404(report_id: str, user: dict) -> dict:
    try:
        report = report_queries.get_report(report_id, viewer=_viewer(user))
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if report is None:
        raise HTTPException(404, "Relatório não encontrado.")
    return report


@router.get("/reports")
def list_reports_endpoint(
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
    viewer = _viewer(_user)
    # nunca aceita created_by de quem não é gerente — mesma regra de
    # /parse-db (não confiar em identidade vinda do cliente pra consultar
    # dado de outra pessoa); ele só enxerga o que ele mesmo gerou.
    effective_created_by = created_by if viewer is None else None
    limits = period_access.window_for(_user)
    try:
        return report_queries.list_reports(
            page=page,
            page_size=page_size,
            report_number=report_number,
            competence=competence,
            status=status,
            created_by=effective_created_by,
            search=q,
            competence_from=limits[0] if limits else None,
            visible_to=viewer,
            viewer_name=_user.get("name"),
        )
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}")
def get_report_endpoint(report_id: str, _user: dict = Depends(require_session)):
    report = _get_report_or_404(report_id, _user)
    _require_report_access(report, _user)
    return report


@router.get("/reports/{report_id}/versions")
def list_report_versions_endpoint(
    report_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE), _user: dict = Depends(require_session)
):
    report = _get_report_or_404(report_id, _user)
    _require_report_access(report, _user)
    try:
        return report_queries.list_versions(report_id, page=page, page_size=page_size, viewer=_viewer(_user))
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}/versions/{version_id}")
def get_report_version_endpoint(report_id: str, version_id: str, _user: dict = Depends(require_session)):
    report = _get_report_or_404(report_id, _user)
    _require_report_access(report, _user)
    try:
        version = report_queries.get_version_detail(report_id, version_id, viewer=_viewer(_user))
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if version is None:
        raise HTTPException(404, "Versão não encontrada.")
    return version


@router.get("/reports/{report_id}/generations")
def list_report_generations_endpoint(
    report_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE), _user: dict = Depends(require_session)
):
    report = _get_report_or_404(report_id, _user)
    _require_report_access(report, _user)
    try:
        return report_queries.list_generations(report_id, page=page, page_size=page_size, viewer=_viewer(_user))
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}/artifacts")
def list_report_artifacts_endpoint(
    report_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE), _user: dict = Depends(require_session)
):
    report = _get_report_or_404(report_id, _user)
    _require_report_access(report, _user)
    try:
        return report_queries.list_artifacts(report_id, page=page, page_size=page_size, viewer=_viewer(_user))
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/reports/{report_id}/audit")
def get_report_audit_endpoint(
    report_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE), _user: dict = Depends(require_session)
):
    report = _get_report_or_404(report_id, _user)
    _require_report_access(report, _user)
    try:
        return report_queries.list_audit_events_for_report(report_id, page=page, page_size=page_size, viewer=_viewer(_user))
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact_endpoint(artifact_id: str, _user: dict = Depends(require_session)):
    try:
        artifact = report_queries.get_artifact(artifact_id)
    except Exception as e:
        raise log_and_generic_error(e, generic_message=GENERIC_REPORTS_DB_ERROR)
    if artifact is None:
        raise HTTPException(404, "Artifact não encontrado.")
    viewer = _viewer(_user)
    # arquivo é de quem mandou gerar: outro usuário do mesmo relatório não baixa
    if viewer is not None:
        if (artifact.get("requested_by") or "").lower() != viewer.lower():
            raise HTTPException(403, "Sem acesso a este relatório.")
        _check_window(_user, artifact.get("competence_start") or artifact.get("created_at"))
    if not os.path.exists(artifact["storage_path"]):
        raise HTTPException(404, "O arquivo deste artifact não existe mais em disco.")
    record_event(
        actor_id=_user["login"],
        actor_name=_user["name"],
        action="artifact_downloaded",
        entity_type="report_artifact",
        entity_id=artifact_id,
        source="download_endpoint",
    )
    return FileResponse(artifact["storage_path"], filename=artifact["file_name"], media_type=artifact["mime_type"])
