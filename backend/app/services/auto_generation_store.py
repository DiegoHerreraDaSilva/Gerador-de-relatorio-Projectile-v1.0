"""Persistência da geração automática em `reports_db` (tabelas `auto_*`).

Mesmo princípio de `management_store.py`: dado PRIMÁRIO (rascunhos editados
pelo revisor/gerente, números digitados, aprovações), então NÃO há fail-open —
banco fora do ar vira `AutoGenerationStoreError`, que é um
`ManagementStoreError` e `main.py` já responde 502 genérico pra ele. Toda
escrita passa por `write_session()` (lock numa linha de `auto_settings`, que
também serializa entre processos)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..db.reports_db import ReportsDbError, get_engine
from ..db.reports_schema import reports as reports_table
from ..db.reports_schema import (
    auto_families,
    auto_memory,
    auto_report_events,
    auto_reports,
    auto_rules,
    auto_runs,
    auto_settings,
)
from .management_store import ManagementStoreError

_LOCK_KEY = "lock"
CONFIG_KEY = "config"

# colunas "leves" da lista (sem o rascunho nem o payload congelado, que podem
# ter centenas de KB com os gráficos)
_LIST_COLUMNS = [c for c in auto_reports.c if c.name not in ("draft_json", "approved_payload_json", "ai_original_json")]


class AutoGenerationStoreError(ManagementStoreError):
    """`reports_db` inacessível ao ler/gravar a geração automática."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def _connect(begin: bool) -> Iterator:
    try:
        engine = get_engine()
        with (engine.begin() if begin else engine.connect()) as conn:
            yield conn
    except (SQLAlchemyError, ReportsDbError) as e:
        raise AutoGenerationStoreError(f"Falha ao acessar a geração automática em reports_db: {e}") from e


# --- leitura ------------------------------------------------------------------


def get_config() -> dict:
    with _connect(begin=False) as conn:
        row = conn.execute(select(auto_settings.c.value_json).where(auto_settings.c.key == CONFIG_KEY)).first()
    return dict(row.value_json or {}) if row else {}


def get_rules() -> dict[str, dict]:
    with _connect(begin=False) as conn:
        return {r.family_key: dict(r.config_json or {}) for r in conn.execute(select(auto_rules))}


def get_family_overrides() -> dict[str, str]:
    with _connect(begin=False) as conn:
        return {r.project_id: r.family_key for r in conn.execute(select(auto_families))}


def get_memories(family_keys: list[str] | None = None) -> dict[str, dict]:
    query = select(auto_memory)
    if family_keys is not None:
        if not family_keys:
            return {}
        query = query.where(auto_memory.c.family_key.in_(family_keys))
    with _connect(begin=False) as conn:
        return {r.family_key: dict(r.memory_json or {}) for r in conn.execute(query)}


def list_runs() -> list[dict]:
    with _connect(begin=False) as conn:
        return [dict(r) for r in conn.execute(select(auto_runs).order_by(auto_runs.c.competence.desc())).mappings()]


def get_run(competence: str) -> dict | None:
    with _connect(begin=False) as conn:
        row = conn.execute(select(auto_runs).where(auto_runs.c.competence == competence)).mappings().first()
    return dict(row) if row else None


def list_reports(competence: str) -> list[dict]:
    with _connect(begin=False) as conn:
        rows = conn.execute(
            select(*_LIST_COLUMNS).where(auto_reports.c.competence == competence).order_by(auto_reports.c.project_name)
        ).mappings().all()
    return [dict(r) for r in rows]


def list_drafts(competence: str) -> list[dict]:
    """Id, status e rascunho de cada relatório da competência — pra validar
    número único na rodada."""
    with _connect(begin=False) as conn:
        rows = conn.execute(
            select(auto_reports.c.id, auto_reports.c.status, auto_reports.c.draft_json)
            .where(auto_reports.c.competence == competence)
        ).mappings().all()
    return [dict(r) for r in rows]


def find_history_numbers(numbers: list[str]) -> list[tuple[str, str, str]]:
    """(número, projeto, competência) de relatórios do HISTÓRICO que já usam
    algum desses números — pra barrar número digitado errado na aprovação."""
    if not numbers:
        return []
    with _connect(begin=False) as conn:
        rows = conn.execute(
            select(reports_table.c.report_number, reports_table.c.project_name_snapshot,
                   reports_table.c.competence_label)
            .where(reports_table.c.report_number.in_(numbers))
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def get_report(report_id: str) -> dict | None:
    with _connect(begin=False) as conn:
        row = conn.execute(select(auto_reports).where(auto_reports.c.id == report_id)).mappings().first()
    return dict(row) if row else None


def list_assigned(login: str, statuses: tuple[str, ...], competence_from: str | None = None) -> list[dict]:
    """Relatórios atribuídos a `login` (sem diferenciar caixa: o login da
    sessão vem de `auser.rLogin` e o do revisor de `temployee.pLogin`).
    `competence_from` ("AAAA-MM") corta as competências mais antigas."""
    query = select(*_LIST_COLUMNS).where(
        func.lower(auto_reports.c.reviewer_login) == login.lower(), auto_reports.c.status.in_(statuses),
    )
    if competence_from:
        query = query.where(auto_reports.c.competence >= competence_from)
    with _connect(begin=False) as conn:
        rows = conn.execute(
            query.order_by(auto_reports.c.competence.desc(), auto_reports.c.project_name)
        ).mappings().all()
    return [dict(r) for r in rows]


def count_by_status(statuses: tuple[str, ...], reviewer_login: str | None = None,
                    competence_from: str | None = None) -> int:
    query = select(func.count()).select_from(auto_reports).where(auto_reports.c.status.in_(statuses))
    if reviewer_login is not None:
        query = query.where(func.lower(auto_reports.c.reviewer_login) == reviewer_login.lower())
    if competence_from:
        query = query.where(auto_reports.c.competence >= competence_from)
    with _connect(begin=False) as conn:
        return int(conn.execute(query).scalar_one())


def latest_comments(report_ids: list[str], actions: tuple[str, ...]) -> dict[str, dict]:
    """Último evento com comentário de cada relatório (entre `actions`) —
    o "o que precisa mudar" da devolução, a observação de quem revisou."""
    if not report_ids:
        return {}
    with _connect(begin=False) as conn:
        rows = conn.execute(
            select(auto_report_events)
            .where(auto_report_events.c.auto_report_id.in_(report_ids), auto_report_events.c.action.in_(actions))
            .order_by(auto_report_events.c.id)
        ).mappings().all()
    out: dict[str, dict] = {}
    for r in rows:
        out[r["auto_report_id"]] = {
            "action": r["action"], "comment": r["comment"], "actor_name": r["actor_name"], "created_at": r["created_at"],
            "metadata": r["metadata_json"],
        }
    return out


def list_events(report_id: str) -> list[dict]:
    with _connect(begin=False) as conn:
        rows = conn.execute(
            select(auto_report_events)
            .where(auto_report_events.c.auto_report_id == report_id)
            .order_by(auto_report_events.c.id)
        ).mappings().all()
    return [dict(r) for r in rows]


# --- escrita ------------------------------------------------------------------


class VersionConflict(Exception):
    """O rascunho mudou desde que o cliente o leu (trava otimista)."""

    def __init__(self, current_version: int):
        super().__init__(f"rascunho mudou (versão atual {current_version})")
        self.current_version = current_version


class WriteSession:
    def __init__(self, conn):
        self._conn = conn

    def set_config(self, config: dict) -> None:
        self._upsert_setting(CONFIG_KEY, config)

    def _upsert_setting(self, key: str, value) -> None:
        result = self._conn.execute(
            update(auto_settings).where(auto_settings.c.key == key).values(value_json=value, updated_at=utcnow())
        )
        if result.rowcount == 0:
            self._conn.execute(insert(auto_settings).values(key=key, value_json=value, updated_at=utcnow()))

    def set_rule(self, family_key: str, config: dict | None, actor: str) -> None:
        self._conn.execute(delete(auto_rules).where(auto_rules.c.family_key == family_key))
        if config:
            self._conn.execute(insert(auto_rules).values(
                family_key=family_key, config_json=config, updated_by=actor, updated_at=utcnow(),
            ))

    def set_family_override(self, project_id: str, family_key: str | None, actor: str) -> None:
        self._conn.execute(delete(auto_families).where(auto_families.c.project_id == project_id))
        if family_key:
            self._conn.execute(insert(auto_families).values(
                project_id=project_id, family_key=family_key, updated_by=actor, updated_at=utcnow(),
            ))

    def set_memory(self, family_key: str, memory: dict, source_report_id: str) -> None:
        self._conn.execute(delete(auto_memory).where(auto_memory.c.family_key == family_key))
        self._conn.execute(insert(auto_memory).values(
            family_key=family_key, memory_json=memory, source_auto_report_id=source_report_id, updated_at=utcnow(),
        ))

    def get_run_for_update(self, competence: str) -> dict | None:
        row = self._conn.execute(
            select(auto_runs).where(auto_runs.c.competence == competence).with_for_update()
        ).mappings().first()
        return dict(row) if row else None

    def insert_run(self, run: dict) -> None:
        self._conn.execute(insert(auto_runs).values(**run))

    def update_run(self, run_id: str, **fields) -> None:
        self._conn.execute(update(auto_runs).where(auto_runs.c.id == run_id).values(**fields))

    def existing_project_ids(self, competence: str) -> set[str]:
        return {
            r.project_id
            for r in self._conn.execute(select(auto_reports.c.project_id).where(auto_reports.c.competence == competence))
        }

    def insert_report(self, report: dict) -> None:
        now = utcnow()
        self._conn.execute(insert(auto_reports).values(created_at=now, updated_at=now, **report))

    def get_report_for_update(self, report_id: str) -> dict | None:
        row = self._conn.execute(
            select(auto_reports).where(auto_reports.c.id == report_id).with_for_update()
        ).mappings().first()
        return dict(row) if row else None

    def update_report(self, report_id: str, expected_version: int | None = None, bump_version: bool = False, **fields) -> int:
        """Grava `fields`; com `expected_version`, só se o rascunho ainda estiver
        nessa versão (senão `VersionConflict`). Devolve a versão resultante."""
        current = self._conn.execute(
            select(auto_reports.c.draft_version).where(auto_reports.c.id == report_id)
        ).scalar_one()
        if expected_version is not None and expected_version != current:
            raise VersionConflict(current)
        new_version = current + 1 if bump_version else current
        self._conn.execute(
            update(auto_reports).where(auto_reports.c.id == report_id)
            .values(draft_version=new_version, updated_at=utcnow(), **fields)
        )
        return new_version

    def add_event(self, report_id: str, action: str, actor: dict | None, comment: str | None = None,
                  metadata: dict | None = None) -> None:
        self._conn.execute(insert(auto_report_events).values(
            auto_report_id=report_id, action=action,
            actor_login=(actor or {}).get("login"), actor_name=(actor or {}).get("name"),
            comment=comment, metadata_json=metadata, created_at=utcnow(),
        ))


@contextmanager
def write_session() -> Iterator[WriteSession]:
    with _connect(begin=True) as conn:
        locked = conn.execute(
            select(auto_settings.c.key).where(auto_settings.c.key == _LOCK_KEY).with_for_update()
        ).first()
        if locked is None:
            # a migration 0007 cria essa linha; só falta quando o schema veio de
            # `metadata.create_all` (testes)
            try:
                conn.execute(insert(auto_settings).values(key=_LOCK_KEY, value_json=None, updated_at=utcnow()))
            except IntegrityError:
                pass
            conn.execute(select(auto_settings.c.key).where(auto_settings.c.key == _LOCK_KEY).with_for_update())
        yield WriteSession(conn)
