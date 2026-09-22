"""Persistência de histórico/versionamento em `reports_db` — chamada pelos
endpoints de geração (`/generate`, `/send-report` em `main.py`).

**Fail-open por padrão** (decisão confirmada com o usuário): nenhuma função
pública aqui deixa uma exceção de infraestrutura escapar. Se `reports_db`
estiver fora do ar, com `REPORTS_DB_ENABLED=false`, ou qualquer outra falha
inesperada, a função loga e devolve `None`/não faz nada — quem chama trata
isso como "sem histórico desta vez", nunca como motivo pra falhar a geração
do arquivo em si (a função central do app, que já funciona sem este banco há
tempo). As exceções de NEGÓCIO continuam subindo normalmente por fora deste
módulo (ex: `NonFiniteValueError` do `generator.py`, tratada em `main.py`).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from ..core.config import get_settings
from ..db.reports_db import get_engine
from ..db.reports_schema import (
    report_activities,
    report_artifacts,
    report_generation,
    report_groups,
    report_source_snapshots,
    report_versions,
    reports,
)
from .snapshot import build_snapshot_data, compute_data_hash, compute_identity_hash, parse_competence_range, snapshot_schema_version

logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "report_artifacts")


def _utcnow() -> datetime:
    # naive UTC (sem tzinfo) — colunas DATETIME(6) do MySQL não guardam
    # timezone; manter consistente em todo o módulo evita comparar aware com
    # naive por engano.
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class GenerationHandle:
    report_id: str
    version_id: str
    version_number: int
    generation_id: str
    _started_monotonic: float


class GenerationGuard:
    """Evita tentar reconectar no reports_db repetidamente dentro do MESMO
    request quando ele já falhou uma vez — sem isso, um `/generate` com N
    pacotes × M formatos multiplicaria o timeout de conexão (3s) por cada
    iteração restante se o container estiver fora do ar. Uma instância por
    request (ver `main.py`), nunca reaproveitada entre requests."""

    def __init__(self) -> None:
        self._unavailable = False

    def begin(
        self, pkg_data: dict, fmt: str, requested_by: str, requested_by_name: str,
        created_from: str = "generate_endpoint",
    ) -> GenerationHandle | None:
        if self._unavailable:
            return None
        handle = begin_generation(pkg_data, fmt, requested_by, requested_by_name, created_from)
        if handle is None:
            self._unavailable = True
        return handle


def begin_generation(
    pkg_data: dict, fmt: str, requested_by: str, requested_by_name: str, created_from: str = "generate_endpoint"
) -> GenerationHandle | None:
    """Transação A: resolve/cria o `report`, grava o snapshot, cria a nova
    versão + grupos/atividades, e abre o registro de `generation` (status
    'started'). Chamar UMA VEZ por (pacote, formato) gerado — a mesma
    granularidade do laço em `generate_endpoint`/`send_report_endpoint`.
    `created_from` é só metadado (`'generate_endpoint'`/`'send_report_endpoint'`).

    Retorna `None` (nunca levanta) se a persistência estiver desligada
    (`REPORTS_DB_ENABLED=false`) ou se qualquer coisa der errado — nesses
    casos, `finish_generation_success`/`finish_generation_failure` recebendo
    `None` também não fazem nada, mantendo o fail-open coerente ponta a
    ponta pra essa chamada específica."""
    if not get_settings().reports_db_enabled:
        return None
    started_monotonic = time.monotonic()
    try:
        return _begin_generation_unsafe(pkg_data, fmt, requested_by, requested_by_name, created_from, started_monotonic)
    except Exception:
        logger.exception(
            "Falha ao persistir início de geração em reports_db — relatório será gerado sem histórico (fail-open)"
        )
        return None


def _begin_generation_unsafe(
    pkg_data: dict, fmt: str, requested_by: str, requested_by_name: str, created_from: str, started_monotonic: float
) -> GenerationHandle:
    header = pkg_data.get("header") or {}
    report_number = header.get("project_code") or ""
    scope = pkg_data.get("pacote_scope")
    competence_label = header.get("month_label") or ""

    identity_hash = compute_identity_hash(report_number, scope, competence_label)
    snapshot_data = build_snapshot_data(pkg_data)
    data_hash = compute_data_hash(snapshot_data)
    competence_start, competence_end = parse_competence_range(competence_label)
    now = _utcnow()

    engine = get_engine()
    with engine.begin() as conn:
        report_id = _find_or_create_report(
            conn, identity_hash, report_number, scope, competence_label,
            competence_start, competence_end, header.get("project_name") or "",
            requested_by, requested_by_name, now,
        )
        version_number = _next_version_number(conn, report_id)
        snapshot_id = str(ULID())
        conn.execute(
            insert(report_source_snapshots).values(
                id=snapshot_id,
                source_system="generate_payload_v1",
                source_query=None,
                source_filters_json=None,
                captured_at=now,
                source_reference=None,
                data_json=snapshot_data,
                data_hash=data_hash,
                schema_version=snapshot_schema_version(),
            )
        )
        version_id = str(ULID())
        _insert_version_with_retry(
            conn, version_id, report_id, version_number, snapshot_id, requested_by, created_from, now
        )
        _insert_groups_and_activities(conn, version_id, pkg_data.get("groups") or [], now)
        generation_id = str(ULID())
        conn.execute(
            insert(report_generation).values(
                id=generation_id,
                report_id=report_id,
                report_version_id=version_id,
                format=fmt,
                requested_by=requested_by,
                started_at=now,
                status="started",
            )
        )

    return GenerationHandle(
        report_id=report_id,
        version_id=version_id,
        version_number=version_number,
        generation_id=generation_id,
        _started_monotonic=started_monotonic,
    )


def _find_or_create_report(
    conn, identity_hash, report_number, scope, competence_label, competence_start, competence_end,
    project_name, requested_by, requested_by_name, now,
) -> str:
    row = conn.execute(
        select(reports.c.id).where(reports.c.identity_hash == identity_hash).with_for_update()
    ).first()
    if row:
        return row.id

    new_id = str(ULID())
    try:
        conn.execute(
            insert(reports).values(
                id=new_id,
                report_number=report_number,
                scope=scope,
                competence_label=competence_label,
                competence_start=competence_start,
                competence_end=competence_end,
                identity_hash=identity_hash,
                project_name_snapshot=project_name,
                status="active",
                current_version_id=None,
                created_by=requested_by,
                created_by_name_snapshot=requested_by_name,
                created_at=now,
                updated_at=now,
            )
        )
        return new_id
    except IntegrityError:
        # outra transação venceu a corrida entre nosso SELECT e nosso INSERT
        # (mesmo identity_hash) — pega o id dela em vez de falhar.
        row = conn.execute(
            select(reports.c.id).where(reports.c.identity_hash == identity_hash).with_for_update()
        ).first()
        if row:
            return row.id
        raise


def _next_version_number(conn, report_id: str) -> int:
    # O lock de `reports.id` (seja pelo SELECT...FOR UPDATE de
    # `_find_or_create_report`, seja pelo próprio INSERT até o commit) já
    # serializa qualquer segunda transação concorrente pra este `report_id`
    # neste ponto — o FOR UPDATE aqui é defesa adicional (belt-and-suspenders),
    # não a única barreira. `UNIQUE(report_id, version_number)` é a segunda
    # camada (ver `_insert_version_with_retry`).
    current_max = conn.execute(
        select(func.max(report_versions.c.version_number))
        .where(report_versions.c.report_id == report_id)
        .with_for_update()
    ).scalar()
    return (current_max or 0) + 1


def _insert_version_with_retry(conn, version_id, report_id, version_number, snapshot_id, created_by, created_from, now):
    values = dict(
        id=version_id,
        report_id=report_id,
        source_snapshot_id=snapshot_id,
        created_by=created_by,
        created_from=created_from,
        change_summary=None,
        state_json=None,
        created_at=now,
    )
    try:
        conn.execute(insert(report_versions).values(version_number=version_number, **values))
    except IntegrityError:
        retry_version_number = _next_version_number(conn, report_id)
        conn.execute(insert(report_versions).values(version_number=retry_version_number, **values))


def _insert_groups_and_activities(conn, version_id: str, groups: list[dict], now) -> None:
    for position, group in enumerate(groups):
        group_id = str(ULID())
        conn.execute(
            insert(report_groups).values(
                id=group_id,
                report_version_id=version_id,
                source_id=None,
                name=group.get("name") or "",
                performance=group.get("performance") or 0,
                position=position,
                created_at=now,
            )
        )
        for act_position, activity in enumerate(group.get("activities") or []):
            conn.execute(
                insert(report_activities).values(
                    id=str(ULID()),
                    report_group_id=group_id,
                    source_id=None,
                    description=activity.get("description") or "",
                    hours=activity.get("hours"),
                    position=act_position,
                    created_at=now,
                )
            )


def finish_generation_success(
    handle: GenerationHandle | None, output_path: str, download_name: str, fmt: str, mime_type: str
) -> None:
    """Transação B (sucesso): copia o artifact pra armazenamento próprio
    (`backend/data/report_artifacts/` — o `output_path` original, em
    `tempfile.gettempdir()`, é removido segundos depois do download),
    calcula o SHA-256, e marca a geração como bem-sucedida."""
    if handle is None:
        return
    try:
        _finish_generation_success_unsafe(handle, output_path, download_name, fmt, mime_type)
    except Exception:
        logger.exception("Falha ao registrar sucesso da geração em reports_db")


def _finish_generation_success_unsafe(handle: GenerationHandle, output_path, download_name, fmt, mime_type) -> None:
    persistent_path = _copy_to_permanent_storage(output_path, handle.report_id, handle.generation_id, fmt)
    file_size = os.path.getsize(persistent_path)
    sha256 = _sha256_file(persistent_path)
    now = _utcnow()
    duration_ms = int((time.monotonic() - handle._started_monotonic) * 1000)

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            update(report_generation)
            .where(report_generation.c.id == handle.generation_id)
            .values(status="success", finished_at=now, duration_ms=duration_ms)
        )
        conn.execute(
            insert(report_artifacts).values(
                id=str(ULID()),
                generation_id=handle.generation_id,
                artifact_type=fmt,
                storage_type="filesystem",
                storage_path=persistent_path,
                file_name=download_name,
                mime_type=mime_type,
                file_size=file_size,
                sha256=sha256,
                created_at=now,
            )
        )
        conn.execute(
            update(reports)
            .where(reports.c.id == handle.report_id)
            .values(current_version_id=handle.version_id, updated_at=now)
        )


def finish_generation_failure(handle: GenerationHandle | None, error: Exception) -> None:
    """Transação B (falha): NUNCA deixa uma `generation` em 'started' pra
    sempre — sempre roda, mesmo dentro de um `except`/`finally` de quem
    chama (ver integração em `main.py`)."""
    if handle is None:
        return
    try:
        _finish_generation_failure_unsafe(handle, error)
    except Exception:
        logger.exception("Falha ao registrar falha da geração em reports_db")


def _finish_generation_failure_unsafe(handle: GenerationHandle, error: Exception) -> None:
    now = _utcnow()
    duration_ms = int((time.monotonic() - handle._started_monotonic) * 1000)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            update(report_generation)
            .where(report_generation.c.id == handle.generation_id)
            .values(
                status="failed",
                finished_at=now,
                duration_ms=duration_ms,
                error_code=type(error).__name__,
                error_message=str(error)[:2000],
            )
        )


def reconcile_orphaned_generations() -> None:
    """Roda no startup do processo (ver `main.py`): qualquer `generation`
    ainda em 'started' nesse momento é, por definição, órfã — o processo
    anterior morreu (crash, kill, queda de energia) antes de conseguir
    marcar sucesso/falha. Fail-open: se o `reports_db` estiver fora do ar
    aqui também, só loga e o boot continua normalmente."""
    if not get_settings().reports_db_enabled:
        return
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                update(report_generation)
                .where(report_generation.c.status == "started")
                .values(
                    status="failed",
                    finished_at=_utcnow(),
                    error_code="ORPHANED_ON_RESTART",
                    error_message="Processo reiniciado com geração em andamento — marcado como falha por reconciliação.",
                )
            )
    except Exception:
        logger.exception("Falha ao reconciliar gerações órfãs em reports_db no startup (fail-open, boot continua)")


def _copy_to_permanent_storage(output_path: str, report_id: str, generation_id: str, fmt: str) -> str:
    dest_dir = os.path.join(_ARTIFACTS_DIR, report_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{generation_id}.{fmt}")
    shutil.copyfile(output_path, dest_path)
    return dest_path


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
