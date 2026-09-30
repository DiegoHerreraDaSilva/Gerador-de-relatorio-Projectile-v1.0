"""Lixeira e exclusão de relatórios do histórico (`DELETE /reports`, `POST /reports/restore`,
`DELETE /reports/trash`; só gerente).

Apagar = MOVER PRA LIXEIRA (`reports.deleted_at`): some do Histórico, dos downloads e do Analytics, mas
versões, arquivos e snapshots ficam intactos e dá pra restaurar por `TRASH_DAYS` dias. Depois disso (ou quando o
gerente escolhe "apagar definitivamente") a purga apaga de verdade, numa transação: arquivos registrados, gerações,
atividades, grupos, versões, snapshots e o relatório; os arquivos em disco saem DEPOIS do commit (falha ao
remover um arquivo não desfaz a exclusão: vira aviso no log). A trilha de auditoria (`audit_log`) é mantida e
ganha `report_trashed`, `report_restored` e `report_deleted` (purga). Sem fail-open: banco fora do ar vira erro.
"""

from __future__ import annotations

import contextlib
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update

from ..db.reports_db import get_engine
from ..db.reports_schema import report_activities, report_artifacts, report_generation, report_groups, report_source_snapshots, report_versions, reports
from . import report_persistence
from .audit import record_event
from .policy import FailurePolicy

logger = logging.getLogger(__name__)

# apagar é ação explícita do gerente: erro sobe (502), nunca é engolido
FAILURE_POLICY = FailurePolicy.FAIL_CLOSED

MAX_DELETE = 200
TRASH_DAYS = 30


def _inside_artifacts_dir(path: str) -> bool:
    base = os.path.realpath(report_persistence.ARTIFACTS_DIR)
    target = os.path.realpath(path)
    return target.startswith(base + os.sep)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _audit(actor: dict, action: str, item: dict) -> None:
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action=action,
        entity_type="report",
        entity_id=item["id"],
        source="history_delete",
        metadata={k: item[k] for k in ("report_number", "project", "competence", "versions") if k in item},
    )


def _describe(report: dict, versions: int | None = None) -> dict:
    item = {"id": report["id"], "report_number": report["report_number"], "project": report["project_name_snapshot"], "competence": report["competence_label"]}
    if versions is not None:
        item["versions"] = versions
    return item


def trash_reports(report_ids: list[str], actor: dict) -> dict:
    """Move pra lixeira (ids repetidos contam uma vez; o que já está lá ou não existe vai em `not_found`).
    Nada é apagado: só `deleted_at`/`deleted_by`."""
    ids = list(dict.fromkeys(report_ids))
    now = _now()
    trashed: list[dict] = []
    with get_engine().begin() as conn:
        rows = conn.execute(select(reports).where(reports.c.id.in_(ids), reports.c.deleted_at.is_(None))).mappings().all()
        for row in rows:
            conn.execute(update(reports).where(reports.c.id == row["id"]).values(deleted_at=now, deleted_by=actor.get("login", "")))
            trashed.append(_describe(dict(row)))
    for item in trashed:
        _audit(actor, "report_trashed", item)
    found = {t["id"] for t in trashed}
    return {"trashed": trashed, "not_found": [i for i in ids if i not in found]}


def restore_reports(report_ids: list[str], actor: dict) -> dict:
    """Tira da lixeira. O que não está na lixeira (ou não existe) vai em `not_found`."""
    ids = list(dict.fromkeys(report_ids))
    restored: list[dict] = []
    with get_engine().begin() as conn:
        rows = conn.execute(select(reports).where(reports.c.id.in_(ids), reports.c.deleted_at.is_not(None))).mappings().all()
        for row in rows:
            conn.execute(update(reports).where(reports.c.id == row["id"]).values(deleted_at=None, deleted_by=None))
            restored.append(_describe(dict(row)))
    for item in restored:
        _audit(actor, "report_restored", item)
    found = {r["id"] for r in restored}
    return {"restored": restored, "not_found": [i for i in ids if i not in found]}


def _purge(ids: list[str], actor: dict, *, only_trashed: bool) -> dict:
    """Apaga de verdade. `only_trashed`: só o que já está na lixeira (o caminho do gerente); a purga
    automática passa os ids já filtrados por data."""
    engine = get_engine()
    deleted: list[dict] = []
    storage_paths: list[str] = []
    with engine.begin() as conn:
        query = select(reports).where(reports.c.id.in_(ids))
        if only_trashed:
            query = query.where(reports.c.deleted_at.is_not(None))
        found = {r["id"]: dict(r) for r in conn.execute(query).mappings().all()}
        for report_id, report in found.items():
            version_rows = conn.execute(
                select(report_versions.c.id, report_versions.c.source_snapshot_id).where(report_versions.c.report_id == report_id)
            ).all()
            version_ids = [v.id for v in version_rows]
            snapshot_ids = [v.source_snapshot_id for v in version_rows]
            generation_ids = [g.id for g in conn.execute(select(report_generation.c.id).where(report_generation.c.report_id == report_id))]
            if generation_ids:
                storage_paths += [
                    a.storage_path for a in conn.execute(select(report_artifacts.c.storage_path).where(report_artifacts.c.generation_id.in_(generation_ids)))
                ]
                conn.execute(delete(report_artifacts).where(report_artifacts.c.generation_id.in_(generation_ids)))
                conn.execute(delete(report_generation).where(report_generation.c.id.in_(generation_ids)))
            if version_ids:
                group_ids = [g.id for g in conn.execute(select(report_groups.c.id).where(report_groups.c.report_version_id.in_(version_ids)))]
                if group_ids:
                    conn.execute(delete(report_activities).where(report_activities.c.report_group_id.in_(group_ids)))
                    conn.execute(delete(report_groups).where(report_groups.c.id.in_(group_ids)))
                conn.execute(delete(report_versions).where(report_versions.c.id.in_(version_ids)))
            if snapshot_ids:
                conn.execute(delete(report_source_snapshots).where(report_source_snapshots.c.id.in_(snapshot_ids)))
            conn.execute(delete(reports).where(reports.c.id == report_id))
            deleted.append(_describe(report, len(version_ids)))

    files_removed = files_failed = 0
    report_dirs: set[str] = set()
    for path in storage_paths:
        try:
            if _inside_artifacts_dir(path) and os.path.exists(path):
                os.remove(path)
                files_removed += 1
                report_dirs.add(os.path.dirname(path))
        except OSError:
            files_failed += 1
            logger.warning("Não consegui remover o arquivo %s", path)
    for directory in report_dirs:
        with contextlib.suppress(OSError):
            os.rmdir(directory)  # só se ficou vazia

    for item in deleted:
        _audit(actor, "report_deleted", item)
    return {
        "deleted": deleted,
        "not_found": [i for i in ids if i not in {d["id"] for d in deleted}],
        "files_removed": files_removed,
        "files_failed": files_failed,
    }


def purge_reports(report_ids: list[str], actor: dict) -> dict:
    """ "Apagar definitivamente": só o que já está na lixeira (o que está vivo vai em `not_found`)."""
    return _purge(list(dict.fromkeys(report_ids)), actor, only_trashed=True)


SYSTEM_ACTOR = {"login": "sistema", "name": "Sistema"}


def purge_expired(now: datetime | None = None, days: int = TRASH_DAYS) -> int:
    """Purga o que está na lixeira há mais de `days` dias (chamada pelo agendador, uma vez por dia). Devolve
    quantos relatórios foram apagados."""
    cutoff = (now or _now()) - timedelta(days=days)
    with get_engine().connect() as conn:
        ids = [r.id for r in conn.execute(select(reports.c.id).where(reports.c.deleted_at.is_not(None), reports.c.deleted_at < cutoff))]
    total = 0
    for start in range(0, len(ids), MAX_DELETE):
        total += len(_purge(ids[start : start + MAX_DELETE], SYSTEM_ACTOR, only_trashed=True)["deleted"])
    return total
