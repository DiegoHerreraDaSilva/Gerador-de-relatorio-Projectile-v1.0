"""Trilha de auditoria em `reports_db` — quem fez o quê, quando, em qual
entidade (guia GUIA_EVOLUCAO_GERADOR_PROJECTILE.md, seção 27).

Mesma disciplina fail-open de `report_persistence.py`: registrar auditoria
NUNCA pode derrubar a operação de negócio sendo auditada — uma falha aqui é
logada e ignorada, nunca propagada."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import insert
from ulid import ULID

from ..core.config import get_settings
from ..db.reports_db import get_engine
from ..db.reports_schema import audit_log

logger = logging.getLogger(__name__)


def record_event(
    *,
    actor_id: str,
    actor_name: str,
    action: str,
    entity_type: str,
    entity_id: str,
    source: str,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
    conn=None,
) -> None:
    """Registra 1 evento de auditoria. Se `conn` for passada (uma conexão já
    dentro de uma transação em andamento, ver `report_persistence.py`), o
    INSERT entra nela — vira parte atômica da mesma operação que está sendo
    auditada. Sem `conn`, abre sua própria transação curta.

    Nunca levanta: qualquer falha (reports_db fora do ar, desligado via
    REPORTS_DB_ENABLED) é logada e ignorada."""
    if not get_settings().reports_db_enabled:
        return
    try:
        values = dict(
            id=str(ULID()),
            actor_id=actor_id,
            actor_name_snapshot=actor_name,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            before_json=before,
            after_json=after,
            metadata_json=metadata,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        if conn is not None:
            conn.execute(insert(audit_log).values(**values))
        else:
            engine = get_engine()
            with engine.begin() as new_conn:
                new_conn.execute(insert(audit_log).values(**values))
    except Exception:
        logger.exception("Falha ao registrar evento de auditoria em reports_db (fail-open)")
