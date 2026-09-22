"""Consultas de leitura sobre `reports_db` pros endpoints de histórico
(`GET /reports/*`, `GET /artifacts/*/download`).

Ao contrário de `report_persistence.py` (fail-open — nunca pode derrubar a
geração do arquivo), aqui NÃO há fail-open: o único propósito destas
funções é ler o histórico, então se `reports_db` estiver fora do ar, a
exceção sobe pra quem chama decidir o HTTP status (ver `main.py`,
`_log_and_generic_error`)."""
from __future__ import annotations

from sqlalchemy import and_, desc, func, select

from ..db.reports_db import get_engine
from ..db.reports_schema import (
    audit_log,
    report_artifacts,
    report_generation,
    report_versions,
    reports,
)

MAX_PAGE_SIZE = 100


def _paginate(conn, base_query, order_by, page: int, page_size: int) -> tuple[list[dict], int]:
    total = conn.execute(select(func.count()).select_from(base_query.subquery())).scalar_one()
    rows = conn.execute(
        base_query.order_by(order_by).offset((page - 1) * page_size).limit(page_size)
    ).mappings().all()
    return [dict(r) for r in rows], total


def list_reports(
    *, page: int, page_size: int,
    report_number: str | None = None, competence: str | None = None,
    status: str | None = None, created_by: str | None = None,
) -> dict:
    conditions = []
    if report_number:
        conditions.append(reports.c.report_number.ilike(f"%{report_number}%"))
    if competence:
        conditions.append(reports.c.competence_label == competence)
    if status:
        conditions.append(reports.c.status == status)
    if created_by:
        conditions.append(reports.c.created_by == created_by)

    base_query = select(reports)
    if conditions:
        base_query = base_query.where(and_(*conditions))

    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(reports.c.updated_at), page, page_size)
        items = [_with_current_version_number(conn, item) for item in items]

    return {"items": items, "page": page, "page_size": page_size, "total": total}


def _with_current_version_number(conn, report: dict) -> dict:
    version_number = None
    if report.get("current_version_id"):
        row = conn.execute(
            select(report_versions.c.version_number).where(report_versions.c.id == report["current_version_id"])
        ).first()
        version_number = row.version_number if row else None
    return {**report, "current_version_number": version_number}


def get_report(report_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(select(reports).where(reports.c.id == report_id)).mappings().first()
        if row is None:
            return None
        return _with_current_version_number(conn, dict(row))


def list_versions(report_id: str, *, page: int, page_size: int) -> dict:
    base_query = select(report_versions).where(report_versions.c.report_id == report_id)
    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(report_versions.c.version_number), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_version_detail(report_id: str, version_id: str) -> dict | None:
    from ..db.reports_schema import report_source_snapshots

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            select(
                report_versions.c.id, report_versions.c.report_id, report_versions.c.version_number,
                report_versions.c.created_by, report_versions.c.created_from,
                report_versions.c.change_summary, report_versions.c.created_at,
                report_source_snapshots.c.data_json, report_source_snapshots.c.data_hash,
                report_source_snapshots.c.schema_version, report_source_snapshots.c.captured_at,
            )
            .select_from(report_versions.join(report_source_snapshots, report_versions.c.source_snapshot_id == report_source_snapshots.c.id))
            .where(report_versions.c.id == version_id, report_versions.c.report_id == report_id)
        ).mappings().first()
    if row is None:
        return None
    row = dict(row)
    return {
        "id": row["id"], "report_id": row["report_id"], "version_number": row["version_number"],
        "created_by": row["created_by"], "created_from": row["created_from"],
        "change_summary": row["change_summary"], "created_at": row["created_at"],
        "snapshot": {
            "data": row["data_json"], "data_hash": row["data_hash"],
            "schema_version": row["schema_version"], "captured_at": row["captured_at"],
        },
    }


def list_generations(report_id: str, *, page: int, page_size: int) -> dict:
    base_query = (
        select(
            report_generation.c.id, report_generation.c.report_id, report_generation.c.report_version_id,
            report_versions.c.version_number, report_generation.c.format, report_generation.c.requested_by,
            report_generation.c.started_at, report_generation.c.finished_at, report_generation.c.duration_ms,
            report_generation.c.status, report_generation.c.error_code, report_generation.c.error_message,
        )
        .select_from(report_generation.join(report_versions, report_generation.c.report_version_id == report_versions.c.id))
        .where(report_generation.c.report_id == report_id)
    )
    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(report_generation.c.started_at), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def list_artifacts(report_id: str, *, page: int, page_size: int) -> dict:
    base_query = (
        select(
            report_artifacts.c.id, report_artifacts.c.generation_id, report_artifacts.c.artifact_type,
            report_artifacts.c.file_name, report_artifacts.c.mime_type, report_artifacts.c.file_size,
            report_artifacts.c.sha256, report_artifacts.c.created_at,
            report_generation.c.report_version_id, report_versions.c.version_number,
        )
        .select_from(
            report_artifacts
            .join(report_generation, report_artifacts.c.generation_id == report_generation.c.id)
            .join(report_versions, report_generation.c.report_version_id == report_versions.c.id)
        )
        .where(report_generation.c.report_id == report_id)
    )
    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(report_artifacts.c.created_at), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_artifact(artifact_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            select(
                report_artifacts.c.id, report_artifacts.c.storage_path, report_artifacts.c.file_name,
                report_artifacts.c.mime_type, report_artifacts.c.artifact_type,
                report_generation.c.report_id, reports.c.created_by,
            )
            .select_from(
                report_artifacts
                .join(report_generation, report_artifacts.c.generation_id == report_generation.c.id)
                .join(reports, report_generation.c.report_id == reports.c.id)
            )
            .where(report_artifacts.c.id == artifact_id)
        ).mappings().first()
    return dict(row) if row else None


def list_audit_events_for_report(report_id: str, *, page: int, page_size: int) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        version_ids = [r.id for r in conn.execute(select(report_versions.c.id).where(report_versions.c.report_id == report_id))]
        generation_ids = [
            r.id for r in conn.execute(select(report_generation.c.id).where(report_generation.c.report_id == report_id))
        ]
        artifact_ids = []
        if generation_ids:
            artifact_ids = [
                r.id for r in conn.execute(select(report_artifacts.c.id).where(report_artifacts.c.generation_id.in_(generation_ids)))
            ]
        entity_ids = [report_id, *version_ids, *generation_ids, *artifact_ids]
        base_query = select(audit_log).where(audit_log.c.entity_id.in_(entity_ids))
        items, total = _paginate(conn, base_query, desc(audit_log.c.created_at), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}
