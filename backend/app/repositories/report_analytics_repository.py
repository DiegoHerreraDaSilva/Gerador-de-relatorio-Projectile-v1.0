"""SQL do chat analítico sobre o `reports_db`. Só leitura e só agregação —
nunca devolve linha crua. Não é fail-open (mesmo princípio de
`services/report_queries.py`): a função só lê, então falha sobe.

Datas: gerações/versões filtram pela data do EVENTO (`started_at`,
`created_at`); horas dos relatórios filtram pela COMPETÊNCIA do relatório.
Sempre só a versão atual de cada relatório nas horas (mesma regra do
Analytics)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, desc, distinct, func, select

from ..db.reports_db import get_engine
from ..db.reports_schema import (
    report_activities,
    report_generation,
    report_groups,
    report_versions,
    reports,
)


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    # timestamps do reports_db são UTC ingênuo; o fim é exclusivo (dia seguinte)
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def count_generated_reports(start: date, end: date) -> int:
    """Relatórios DISTINTOS com ao menos uma geração bem-sucedida no período
    — xlsx e pdf do mesmo relatório contam uma vez."""
    lo, hi = _bounds(start, end)
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count(distinct(report_generation.c.report_id))).where(
                report_generation.c.status == "success",
                report_generation.c.started_at >= lo,
                report_generation.c.started_at < hi,
            )
        ).scalar_one()


def generated_reports_by_month(start: date, end: date) -> list[dict]:
    lo, hi = _bounds(start, end)
    # date_format é MySQL — reports_db nunca roda em outro dialeto
    period = func.date_format(report_generation.c.started_at, "%Y-%m").label("month")
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(period, func.count(distinct(report_generation.c.report_id)).label("count"))
            .where(
                report_generation.c.status == "success",
                report_generation.c.started_at >= lo,
                report_generation.c.started_at < hi,
            )
            .group_by(period)
            .order_by(period)
        ).mappings().all()
    return [{"label": r["month"], "value": r["count"]} for r in rows]


def count_versions(start: date, end: date) -> int:
    lo, hi = _bounds(start, end)
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count()).select_from(report_versions).where(
                report_versions.c.created_at >= lo, report_versions.c.created_at < hi,
            )
        ).scalar_one()


def generation_time(start: date, end: date) -> dict:
    lo, hi = _bounds(start, end)
    where = (
        report_generation.c.status == "success",
        report_generation.c.started_at >= lo,
        report_generation.c.started_at < hi,
    )
    with get_engine().connect() as conn:
        overall = conn.execute(select(func.avg(report_generation.c.duration_ms)).where(*where)).scalar_one()
        by_format = conn.execute(
            select(
                report_generation.c.format,
                func.avg(report_generation.c.duration_ms).label("avg_ms"),
                func.count().label("count"),
            )
            .where(*where)
            .group_by(report_generation.c.format)
            .order_by(report_generation.c.format)
        ).mappings().all()
    return {
        "avg_ms": float(overall) if overall is not None else None,
        "rows": [
            {"label": r["format"].upper(), "value": float(r["avg_ms"]) if r["avg_ms"] is not None else None, "count": r["count"]}
            for r in by_format
        ],
    }


def generation_failures(start: date, end: date) -> dict:
    lo, hi = _bounds(start, end)
    in_period = (report_generation.c.started_at >= lo, report_generation.c.started_at < hi)
    with get_engine().connect() as conn:
        total = conn.execute(select(func.count()).select_from(report_generation).where(*in_period)).scalar_one()
        failed = conn.execute(
            select(func.count()).select_from(report_generation).where(
                report_generation.c.status == "failed", *in_period,
            )
        ).scalar_one()
    return {"total": total, "failed": failed}


def report_hours_by_project(start: date, end: date, limit: int) -> list[dict]:
    hours = func.sum(report_activities.c.hours)
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(reports.c.project_name_snapshot.label("label"), hours.label("value"))
            .select_from(
                reports
                .join(
                    report_versions,
                    and_(report_versions.c.report_id == reports.c.id, report_versions.c.id == reports.c.current_version_id),
                )
                .join(report_groups, report_groups.c.report_version_id == report_versions.c.id)
                .join(report_activities, report_activities.c.report_group_id == report_groups.c.id)
            )
            .where(reports.c.competence_start >= start, reports.c.competence_start <= end)
            .group_by(reports.c.project_name_snapshot)
            .order_by(desc(hours))
            .limit(limit)
        ).mappings().all()
    return [{"label": r["label"], "value": float(r["value"] or 0)} for r in rows]
