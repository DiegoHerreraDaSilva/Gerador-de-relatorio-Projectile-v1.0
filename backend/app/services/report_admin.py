"""Exclusão de relatórios do histórico (`DELETE /reports`, só gerente).

Apaga de verdade, numa única transação: arquivos gerados (registro), gerações, atividades,
grupos, versões, snapshots e o próprio relatório. Os arquivos em disco saem DEPOIS do commit
(falha ao remover um arquivo não desfaz a exclusão: vira aviso no log). A trilha de auditoria
(`audit_log`) é mantida e ganha um evento `report_deleted` por relatório — quem apagou o quê
continua consultável. Sem fail-open: banco fora do ar vira erro pra quem chamou.
"""

from __future__ import annotations

import contextlib
import logging
import os

from sqlalchemy import delete, select

from ..db.reports_db import get_engine
from ..db.reports_schema import report_activities, report_artifacts, report_generation, report_groups, report_source_snapshots, report_versions, reports
from . import report_persistence
from .audit import record_event
from .policy import FailurePolicy

logger = logging.getLogger(__name__)

# apagar é ação explícita do gerente: erro sobe (502), nunca é engolido
FAILURE_POLICY = FailurePolicy.FAIL_CLOSED

MAX_DELETE = 200


def _inside_artifacts_dir(path: str) -> bool:
    base = os.path.realpath(report_persistence.ARTIFACTS_DIR)
    target = os.path.realpath(path)
    return target.startswith(base + os.sep)


def delete_reports(report_ids: list[str], actor: dict) -> dict:
    """Apaga os relatórios (ids repetidos contam uma vez). Devolve
    `{deleted: [{id, report_number, project}], not_found: [ids], files_removed, files_failed}`."""
    ids = list(dict.fromkeys(report_ids))
    engine = get_engine()
    deleted: list[dict] = []
    storage_paths: list[str] = []
    with engine.begin() as conn:
        rows = conn.execute(select(reports).where(reports.c.id.in_(ids))).mappings().all()
        found = {r["id"]: dict(r) for r in rows}
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
            deleted.append(
                {
                    "id": report_id,
                    "report_number": report["report_number"],
                    "project": report["project_name_snapshot"],
                    "competence": report["competence_label"],
                    "versions": len(version_ids),
                }
            )

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
        record_event(
            actor_id=actor.get("login", ""),
            actor_name=actor.get("name", ""),
            action="report_deleted",
            entity_type="report",
            entity_id=item["id"],
            source="history_delete",
            metadata={k: item[k] for k in ("report_number", "project", "competence", "versions")},
        )
    return {"deleted": deleted, "not_found": [i for i in ids if i not in found], "files_removed": files_removed, "files_failed": files_failed}
