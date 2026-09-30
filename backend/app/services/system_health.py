"""Saúde do sistema pro painel de Analytics (só gerente): composição de
geração de arquivos, artefatos em disco, última rodada da geração automática
e mensagens ignoradas pelo polling de e-mail.

Só leitura. Falha de `reports_db` sobe pro router virar 502 — mesmo
princípio de `report_queries.py`: a função existe só pra informar, então
silenciar seria pior que falhar alto."""

from __future__ import annotations

from datetime import UTC, datetime

from .. import management
from . import auto_generation_store as store
from . import report_queries


def get_system_health() -> dict:
    runs = store.list_runs()  # já vem ordenado por competência desc
    run = runs[0] if runs else None
    skipped = management.list_samples().get("skipped_messages") or []
    last_skipped = skipped[0] if skipped else None  # list_samples ordena por received_at desc
    return {
        "generation": report_queries.get_generation_health(),
        "artifacts": report_queries.get_artifacts_on_disk(),
        "auto_generation": (
            {
                "competence": run.get("competence"),
                "status": run.get("status"),
                "triggered_by": run.get("triggered_by"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "error": run.get("error"),
            }
            if run
            else None
        ),
        "skipped_messages": {
            "count": len(skipped),
            "last_received_at": last_skipped.get("received_at") if last_skipped else None,
            "last_reason": last_skipped.get("reason") if last_skipped else None,
        },
        "checked_at": datetime.now(UTC).isoformat(),
    }
