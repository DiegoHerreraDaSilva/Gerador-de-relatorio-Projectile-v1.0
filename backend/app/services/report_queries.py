"""Consultas de leitura sobre `reports_db` pros endpoints de histórico
(`GET /reports/*`, `GET /artifacts/*/download`).

Ao contrário de `report_persistence.py` (fail-open — nunca pode derrubar a
geração do arquivo), aqui NÃO há fail-open: o único propósito destas
funções é ler o histórico, então se `reports_db` estiver fora do ar, a
exceção sobe pra quem chama decidir o HTTP status (ver `main.py`,
`_log_and_generic_error`)."""

from __future__ import annotations

import math
import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, desc, func, or_, select

from ..db.reports_db import get_engine
from ..db.reports_schema import audit_log, report_activities, report_artifacts, report_generation, report_groups, report_versions, reports
from . import report_persistence

MAX_PAGE_SIZE = 100
# teto da busca geral: termos demais só viram uma consulta cara sem ganho
MAX_SEARCH_TERMS = 8

# colunas que a busca geral do Histórico cobre — as mesmas que a tabela
# mostra: Número, Projeto, Competência (com o escopo/pacote, que aparece
# junto dela) e Criado por (nome e login)
_SEARCH_COLUMNS = (
    reports.c.report_number,
    reports.c.project_name_snapshot,
    reports.c.competence_label,
    reports.c.scope,
    reports.c.created_by_name_snapshot,
    reports.c.created_by,
)


def _search_condition(search: str):
    """Cada palavra precisa aparecer em ALGUMA das colunas ("julho mercedes"
    acha o relatório de julho do projeto Mercedes). `%`/`_` digitados são
    literais (`autoescape`), e a comparação ignora maiúsculas."""
    terms = search.split()[:MAX_SEARCH_TERMS]
    if not terms:
        return None
    return and_(*(or_(*(func.lower(column).contains(term.lower(), autoescape=True) for column in _SEARCH_COLUMNS)) for term in terms))


def _paginate(conn, base_query, order_by, page: int, page_size: int) -> tuple[list[dict], int]:
    total = conn.execute(select(func.count()).select_from(base_query.subquery())).scalar_one()
    terms = order_by if isinstance(order_by, (list, tuple)) else [order_by]
    rows = conn.execute(base_query.order_by(*terms).offset((page - 1) * page_size).limit(page_size)).mappings().all()
    return [dict(r) for r in rows], total


def _own_version(viewer: str):
    """Versão criada por `viewer` (login, sem diferenciar caixa)."""
    return func.lower(report_versions.c.created_by) == viewer.lower()


def viewer_has_access(report_id: str, viewer: str) -> bool:
    """Quem não é gerente só vê o que ELE gerou: o `report` é a identidade
    compartilhada (número + escopo + competência), mas versões, gerações,
    arquivos e auditoria são de quem as criou. Vale também pro histórico
    antigo, sem backfill: a versão 1 já guarda o `created_by` de quem a criou."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(select(report_versions.c.id).where(report_versions.c.report_id == report_id, _own_version(viewer)).limit(1)).first()
    return row is not None


# colunas ordenáveis da lista (nome da tela -> expressão); `versao` é montada por usuário
SORT_COLUMNS = ("numero", "projeto", "competencia", "versao", "criado_por", "atualizado")
MAX_IDS = 1000


def _sort_order(sort: str | None, order: str, visible_to: str | None):
    """Ordem da lista. Sempre desempata por `id` (paginação estável)."""
    direction = (lambda col: col.asc()) if order == "asc" else (lambda col: col.desc())
    if sort == "numero":
        terms = [direction(func.lower(reports.c.report_number))]
    elif sort == "projeto":
        terms = [direction(func.lower(reports.c.project_name_snapshot))]
    elif sort == "competencia":
        terms = [direction(reports.c.competence_start), direction(reports.c.competence_label)]
    elif sort == "criado_por":
        terms = [direction(func.lower(reports.c.created_by_name_snapshot))]
    elif sort == "versao":
        if visible_to:
            number = (
                select(func.max(report_versions.c.version_number))
                .where(report_versions.c.report_id == reports.c.id, _own_version(visible_to))
                .correlate(reports)
                .scalar_subquery()
            )
        else:
            number = select(report_versions.c.version_number).where(report_versions.c.id == reports.c.current_version_id).correlate(reports).scalar_subquery()
        terms = [direction(number)]
    else:  # "atualizado" (padrão: mais recente primeiro)
        terms = [direction(reports.c.updated_at)] if sort else [desc(reports.c.updated_at)]
    return [*terms, reports.c.id]


def _list_conditions(
    *,
    report_number: str | None,
    competence: str | None,
    status: str | None,
    created_by: str | None,
    search: str | None,
    competence_from: date | None,
    visible_to: str | None,
    trash: bool = False,
) -> list:
    # lixeira: a lista normal só tem o que está vivo; a lixeira (só gerente, garantido na rota) só o apagado
    conditions = [reports.c.deleted_at.is_not(None) if trash else reports.c.deleted_at.is_(None)]
    if visible_to:
        # só relatórios em que o usuário criou ao menos uma versão
        conditions.append(select(report_versions.c.id).where(report_versions.c.report_id == reports.c.id, _own_version(visible_to)).exists())
    if competence_from is not None:
        # janela de quem não é gerente (ver `api/period_access.py`); relatório
        # sem competência reconhecida vale pela data em que foi gerado
        conditions.append(
            or_(reports.c.competence_start >= competence_from, and_(reports.c.competence_start.is_(None), reports.c.created_at >= competence_from))
        )
    if search and (condition := _search_condition(search)) is not None:
        conditions.append(condition)
    if report_number:
        conditions.append(reports.c.report_number.ilike(f"%{report_number}%"))
    if competence:
        conditions.append(reports.c.competence_label == competence)
    if status:
        conditions.append(reports.c.status == status)
    if created_by:
        conditions.append(reports.c.created_by == created_by)
    return conditions


def list_reports(
    *,
    page: int,
    page_size: int,
    report_number: str | None = None,
    competence: str | None = None,
    status: str | None = None,
    created_by: str | None = None,
    search: str | None = None,
    competence_from: date | None = None,
    visible_to: str | None = None,
    viewer_name: str | None = None,
    sort: str | None = None,
    order: str = "desc",
    trash: bool = False,
) -> dict:
    conditions = _list_conditions(
        report_number=report_number,
        competence=competence,
        status=status,
        created_by=created_by,
        search=search,
        competence_from=competence_from,
        visible_to=visible_to,
        trash=trash,
    )
    base_query = select(reports)
    if conditions:
        base_query = base_query.where(and_(*conditions))

    engine = get_engine()
    with engine.connect() as conn:
        default_order = _sort_order(sort, order, visible_to)
        if trash and not sort:
            default_order = [desc(reports.c.deleted_at), reports.c.id]  # lixeira: o apagado mais recentemente primeiro
        items, total = _paginate(conn, base_query, default_order, page, page_size)
        items = [_with_current_version_number(conn, item, visible_to) for item in items]
        if visible_to:
            # quem criou o registro pode ser outra pessoa: não aparece pra quem só vê o próprio
            items = [{**item, "created_by": visible_to, "created_by_name_snapshot": viewer_name or visible_to} for item in items]

    return {"items": items, "page": page, "page_size": page_size, "total": total}


def list_report_ids(
    *,
    report_number: str | None = None,
    competence: str | None = None,
    status: str | None = None,
    created_by: str | None = None,
    search: str | None = None,
    competence_from: date | None = None,
    visible_to: str | None = None,
    trash: bool = False,
) -> dict:
    """Ids de TODOS os relatórios do filtro (pro "selecionar todos"), até `MAX_IDS`."""
    conditions = _list_conditions(
        report_number=report_number,
        competence=competence,
        status=status,
        created_by=created_by,
        search=search,
        competence_from=competence_from,
        visible_to=visible_to,
        trash=trash,
    )
    query = select(reports.c.id)
    if conditions:
        query = query.where(and_(*conditions))
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        ids = [r.id for r in conn.execute(query.order_by(desc(reports.c.updated_at), reports.c.id).limit(MAX_IDS))]
    return {"ids": ids, "total": total, "truncated": total > len(ids)}


def _with_current_version_number(conn, report: dict, viewer: str | None = None) -> dict:
    version_number = None
    if viewer:
        # a "versão atual" de quem não é gerente é a mais recente DELE
        own = conn.execute(
            select(report_versions.c.id, report_versions.c.version_number)
            .where(report_versions.c.report_id == report["id"], _own_version(viewer))
            .order_by(desc(report_versions.c.version_number))
            .limit(1)
        ).first()
        return {**report, "current_version_id": own.id if own else None, "current_version_number": own.version_number if own else None}
    if report.get("current_version_id"):
        row = conn.execute(select(report_versions.c.version_number).where(report_versions.c.id == report["current_version_id"])).first()
        version_number = row.version_number if row else None
    return {**report, "current_version_number": version_number}


def get_report(report_id: str, viewer: str | None = None) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(select(reports).where(reports.c.id == report_id, reports.c.deleted_at.is_(None))).mappings().first()
        if row is None:
            return None
        return _with_current_version_number(conn, dict(row), viewer)


def list_versions(report_id: str, *, page: int, page_size: int, viewer: str | None = None) -> dict:
    base_query = select(report_versions).where(report_versions.c.report_id == report_id)
    if viewer:
        base_query = base_query.where(_own_version(viewer))
    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(report_versions.c.version_number), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_version_detail(report_id: str, version_id: str, viewer: str | None = None) -> dict | None:
    from ..db.reports_schema import report_source_snapshots

    engine = get_engine()
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(
                    report_versions.c.id,
                    report_versions.c.report_id,
                    report_versions.c.version_number,
                    report_versions.c.created_by,
                    report_versions.c.created_from,
                    report_versions.c.change_summary,
                    report_versions.c.created_at,
                    report_source_snapshots.c.data_json,
                    report_source_snapshots.c.data_hash,
                    report_source_snapshots.c.schema_version,
                    report_source_snapshots.c.captured_at,
                )
                .select_from(report_versions.join(report_source_snapshots, report_versions.c.source_snapshot_id == report_source_snapshots.c.id))
                .where(report_versions.c.id == version_id, report_versions.c.report_id == report_id, *([_own_version(viewer)] if viewer else []))
            )
            .mappings()
            .first()
        )
    if row is None:
        return None
    row = dict(row)
    return {
        "id": row["id"],
        "report_id": row["report_id"],
        "version_number": row["version_number"],
        "created_by": row["created_by"],
        "created_from": row["created_from"],
        "change_summary": row["change_summary"],
        "created_at": row["created_at"],
        "snapshot": {"data": row["data_json"], "data_hash": row["data_hash"], "schema_version": row["schema_version"], "captured_at": row["captured_at"]},
    }


def list_generations(report_id: str, *, page: int, page_size: int, viewer: str | None = None) -> dict:
    base_query = (
        select(
            report_generation.c.id,
            report_generation.c.report_id,
            report_generation.c.report_version_id,
            report_versions.c.version_number,
            report_generation.c.format,
            report_generation.c.requested_by,
            report_generation.c.started_at,
            report_generation.c.finished_at,
            report_generation.c.duration_ms,
            report_generation.c.status,
            report_generation.c.error_code,
            report_generation.c.error_message,
        )
        .select_from(report_generation.join(report_versions, report_generation.c.report_version_id == report_versions.c.id))
        .where(report_generation.c.report_id == report_id)
    )
    if viewer:
        base_query = base_query.where(func.lower(report_generation.c.requested_by) == viewer.lower())
    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(report_generation.c.started_at), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def list_artifacts(report_id: str, *, page: int, page_size: int, viewer: str | None = None) -> dict:
    base_query = (
        select(
            report_artifacts.c.id,
            report_artifacts.c.generation_id,
            report_artifacts.c.artifact_type,
            report_artifacts.c.file_name,
            report_artifacts.c.mime_type,
            report_artifacts.c.file_size,
            report_artifacts.c.sha256,
            report_artifacts.c.created_at,
            report_generation.c.report_version_id,
            report_versions.c.version_number,
        )
        .select_from(
            report_artifacts.join(report_generation, report_artifacts.c.generation_id == report_generation.c.id).join(
                report_versions, report_generation.c.report_version_id == report_versions.c.id
            )
        )
        .where(report_generation.c.report_id == report_id)
    )
    if viewer:
        base_query = base_query.where(func.lower(report_generation.c.requested_by) == viewer.lower())
    engine = get_engine()
    with engine.connect() as conn:
        items, total = _paginate(conn, base_query, desc(report_artifacts.c.created_at), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_artifact(artifact_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(
                    report_artifacts.c.id,
                    report_artifacts.c.storage_path,
                    report_artifacts.c.file_name,
                    report_artifacts.c.mime_type,
                    report_artifacts.c.artifact_type,
                    report_generation.c.report_id,
                    report_generation.c.requested_by,
                    reports.c.competence_start,
                    reports.c.created_at,
                )
                .select_from(
                    report_artifacts.join(report_generation, report_artifacts.c.generation_id == report_generation.c.id).join(
                        reports, report_generation.c.report_id == reports.c.id
                    )
                )
                .where(report_artifacts.c.id == artifact_id, reports.c.deleted_at.is_(None))
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def _current_version_activities_join():
    """Base de junção reports→versão ATUAL→grupos→atividades — usada por
    toda agregação de horas do Analytics. Filtra pela versão CORRENTE de
    cada relatório (`reports.current_version_id`), não por todas as
    versões: sem isso, editar/reenviar um relatório duplicaria as horas da
    versão antiga junto com a nova."""
    return (
        reports.join(
            report_versions,
            and_(
                report_versions.c.report_id == reports.c.id,
                report_versions.c.id == reports.c.current_version_id,
                reports.c.deleted_at.is_(None),  # relatório na lixeira não conta nas horas
            ),
        )
        .join(report_groups, report_groups.c.report_version_id == report_versions.c.id)
        .join(report_activities, report_activities.c.report_group_id == report_groups.c.id)
    )


def _hours_breakdown(conn, group_col, label_key: str, *, limit: int | None = None, order_by=None) -> list[dict]:
    hours_sum = func.sum(report_activities.c.hours)
    query = (
        select(group_col.label(label_key), hours_sum.label("hours"))
        .select_from(_current_version_activities_join())
        .group_by(group_col)
        .order_by(order_by if order_by is not None else desc(hours_sum))
    )
    if limit:
        query = query.limit(limit)
    rows = conn.execute(query).mappings().all()
    return [{label_key: r[label_key], "hours": float(r["hours"] or 0)} for r in rows]


def _generation_stats(conn) -> dict:
    total = conn.execute(select(func.count()).select_from(report_generation)).scalar_one()
    failed = conn.execute(select(func.count()).select_from(report_generation).where(report_generation.c.status == "failed")).scalar_one()
    overall_avg = conn.execute(select(func.avg(report_generation.c.duration_ms)).where(report_generation.c.status == "success")).scalar_one()
    by_format_rows = (
        conn.execute(
            select(report_generation.c.format, func.avg(report_generation.c.duration_ms).label("avg_ms"), func.count().label("count"))
            .where(report_generation.c.status == "success")
            .group_by(report_generation.c.format)
        )
        .mappings()
        .all()
    )
    return {
        "total": total,
        "failed": failed,
        "failure_rate": (failed / total) if total else None,
        "avg_duration_ms": float(overall_avg) if overall_avg is not None else None,
        "by_format": [
            {"format": r["format"], "avg_duration_ms": float(r["avg_ms"]) if r["avg_ms"] is not None else None, "count": r["count"]} for r in by_format_rows
        ],
    }


def _reports_created_per_month(conn) -> list[dict]:
    # date_format é específico de MySQL — aceitável aqui: reports_db nunca
    # roda em outro dialeto (ver docstring de reports_schema.py).
    period = func.date_format(reports.c.created_at, "%Y-%m").label("period")
    rows = conn.execute(select(period, func.count().label("count")).where(reports.c.deleted_at.is_(None)).group_by(period).order_by(period)).mappings().all()
    return [{"period": r["period"], "count": r["count"]} for r in rows]


def _top_creators(conn, limit: int = 10) -> list[dict]:
    rows = (
        conn.execute(
            select(reports.c.created_by, reports.c.created_by_name_snapshot, func.count().label("count"))
            .where(reports.c.deleted_at.is_(None))
            .group_by(reports.c.created_by, reports.c.created_by_name_snapshot)
            .order_by(desc(func.count()))
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return [{"login": r["created_by"], "name": r["created_by_name_snapshot"], "reports": r["count"]} for r in rows]


def get_analytics_summary() -> dict:
    """Resumo agregado pro painel de Analytics — só
    gerente (ver `require_manager` em `api/routers/analytics.py`). Fica
    esparso/vazio até acumular meses de uso real; cada seção devolve lista
    vazia (não erro) quando não há dado, e o frontend trata isso como
    estado vazio explícito."""
    engine = get_engine()
    with engine.connect() as conn:
        return {
            "totals": {
                "reports": conn.execute(select(func.count()).select_from(reports)).scalar_one(),
                "versions": conn.execute(select(func.count()).select_from(report_versions)).scalar_one(),
                "artifacts": conn.execute(select(func.count()).select_from(report_artifacts)).scalar_one(),
            },
            "hours_by_competence": _hours_breakdown(conn, reports.c.competence_label, "competence_label", order_by=func.min(reports.c.competence_start)),
            "hours_by_group": _hours_breakdown(conn, report_groups.c.name, "group_name", limit=15),
            "hours_by_project": _hours_breakdown(conn, reports.c.project_name_snapshot, "project_name", limit=15),
            "generation": _generation_stats(conn),
            "reports_over_time": _reports_created_per_month(conn),
            "top_creators": _top_creators(conn),
        }


def get_generation_health(*, window_days: int = 30, now: datetime | None = None) -> dict:
    """Geração de arquivos nos últimos `window_days` dias (painel de Saúde,
    só gerente): tentativas, falhas, latência (média e p95) e a última falha
    com motivo. O p95 é calculado em Python — o MySQL não tem função de
    percentil e a janela é pequena (só geração recente).

    `now` é naive UTC pra bater com as colunas DATETIME do banco (ver
    `report_persistence._utcnow`)."""
    since = (now or datetime.now(UTC).replace(tzinfo=None)) - timedelta(days=window_days)
    engine = get_engine()
    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(
                    report_generation.c.status,
                    report_generation.c.duration_ms,
                    report_generation.c.format,
                    report_generation.c.error_code,
                    report_generation.c.error_message,
                    report_generation.c.started_at,
                )
                .where(report_generation.c.started_at >= since)
                .order_by(desc(report_generation.c.started_at))
            )
            .mappings()
            .all()
        )

    total = len(rows)
    failed = [row for row in rows if row["status"] == "failed"]
    durations = sorted(float(row["duration_ms"]) for row in rows if row["status"] == "success" and row["duration_ms"] is not None)
    # nearest-rank: o p95 é o valor na posição ceil(0,95 × n)
    p95 = durations[math.ceil(0.95 * len(durations)) - 1] if durations else None
    last = failed[0] if failed else None
    return {
        "window_days": window_days,
        "total": total,
        "failed": len(failed),
        "failure_rate": (len(failed) / total) if total else None,
        "avg_duration_ms": (sum(durations) / len(durations)) if durations else None,
        "p95_duration_ms": p95,
        "last_failure": (
            {"started_at": last["started_at"], "format": last["format"], "error_code": last["error_code"], "error_message": last["error_message"]}
            if last
            else None
        ),
    }


def get_artifacts_on_disk(directory: str | None = None) -> dict:
    """Conta e soma os bytes dos arquivos de artifact em DISCO (não no
    banco). A diferença banco × disco é justamente o que o painel de Saúde
    precisa enxergar (arquivo órfão que ninguém apaga)."""
    root_dir = directory or report_persistence.ARTIFACTS_DIR
    count = 0
    total_bytes = 0
    for root, _dirs, files in os.walk(root_dir):
        for name in files:
            try:
                total_bytes += os.path.getsize(os.path.join(root, name))
                count += 1
            except OSError:
                continue
    return {"count": count, "bytes": total_bytes}


def list_audit_events_for_report(report_id: str, *, page: int, page_size: int, viewer: str | None = None) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        version_query = select(report_versions.c.id).where(report_versions.c.report_id == report_id)
        generation_query = select(report_generation.c.id).where(report_generation.c.report_id == report_id)
        if viewer:
            version_query = version_query.where(_own_version(viewer))
            generation_query = generation_query.where(func.lower(report_generation.c.requested_by) == viewer.lower())
        version_ids = [r.id for r in conn.execute(version_query)]
        generation_ids = [r.id for r in conn.execute(generation_query)]
        artifact_ids = []
        if generation_ids:
            artifact_ids = [r.id for r in conn.execute(select(report_artifacts.c.id).where(report_artifacts.c.generation_id.in_(generation_ids)))]
        entity_ids = [report_id, *version_ids, *generation_ids, *artifact_ids]
        base_query = select(audit_log).where(audit_log.c.entity_id.in_(entity_ids))
        if viewer:
            # o evento do próprio relatório (entity = report_id) é de quem agiu
            base_query = base_query.where(func.lower(audit_log.c.actor_id) == viewer.lower())
        items, total = _paginate(conn, base_query, desc(audit_log.c.created_at), page, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}
