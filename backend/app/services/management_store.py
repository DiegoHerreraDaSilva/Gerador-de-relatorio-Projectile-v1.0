"""Persistência dos dados do Painel de Gerência / Diagnóstico em `reports_db`
(tabelas `mgmt_*`), no lugar de `backend/data/management_kpi.json`.

Só persistência: as regras (duplicata, status de envio, KPIs) continuam em
`management.py`. `load_document()` devolve o MESMO formato de dict que o JSON
tinha, pra que a lógica de cálculo não precisasse mudar.

Ao contrário de `report_persistence.py`, aqui NÃO há fail-open: são dados
primários (entradas manuais do gerente, amostras corrigidas à mão). Se
`reports_db` estiver fora do ar, toda função levanta `ManagementStoreError`,
que `main.py` converte em 502 — nunca cai em silêncio pra um arquivo local,
o que faria os dois divergirem."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..db.reports_db import ReportsDbError, get_engine
from ..db.reports_schema import (
    mgmt_closed_clients,
    mgmt_closed_projects,
    mgmt_kpi_samples,
    mgmt_manual_entries,
    mgmt_meta,
    mgmt_processed_messages,
    mgmt_skipped_messages,
)

_LOCK_KEY = "samples_lock"
LEGACY_IMPORT_KEY = "legacy_json_import"

_DATA_TABLES = (
    mgmt_kpi_samples, mgmt_manual_entries, mgmt_processed_messages,
    mgmt_skipped_messages, mgmt_closed_clients, mgmt_closed_projects,
)

_SAMPLE_COLUMNS = (
    "sample_id", "email_message_id", "received_at", "sender", "report_project_text",
    "project_id", "project_name", "match_score", "month", "billed_hours",
    "business_days", "pacote_scope", "source", "edited", "is_duplicate",
)


class ManagementStoreError(RuntimeError):
    """`reports_db` inacessível ao ler/gravar dados do painel de gerência —
    nunca erro do usuário."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def _connect(begin: bool) -> Iterator:
    try:
        engine = get_engine()
        with (engine.begin() if begin else engine.connect()) as conn:
            yield conn
    except (SQLAlchemyError, ReportsDbError) as e:
        raise ManagementStoreError(f"Falha ao acessar dados de gerência em reports_db: {e}") from e


def _sample_to_row(sample: dict) -> dict:
    row = {c: sample.get(c) for c in _SAMPLE_COLUMNS}
    row["edited"] = bool(row["edited"])
    row["is_duplicate"] = bool(row["is_duplicate"])
    extra = {k: v for k, v in sample.items() if k not in _SAMPLE_COLUMNS}
    row["extra_json"] = extra or None
    return row


def _row_to_sample(row) -> dict:
    sample = {c: row[c] for c in _SAMPLE_COLUMNS}
    if row["extra_json"]:
        sample.update(row["extra_json"])
    return sample


def _read_samples(conn) -> list[dict]:
    rows = conn.execute(select(mgmt_kpi_samples).order_by(mgmt_kpi_samples.c.seq)).mappings().all()
    return [_row_to_sample(r) for r in rows]


def load_document() -> dict:
    """Todos os dados no formato do antigo `management_kpi.json`."""
    with _connect(begin=False) as conn:
        manual_entries = {
            r.month: {"billed_hours": r.billed_hours, "elaboration_days": r.elaboration_days}
            for r in conn.execute(select(mgmt_manual_entries).order_by(mgmt_manual_entries.c.month))
        }
        samples = _read_samples(conn)
        processed = [
            r.message_id
            for r in conn.execute(select(mgmt_processed_messages.c.message_id).order_by(mgmt_processed_messages.c.processed_at))
        ]
        skipped = [
            {"message_id": r.message_id, "received_at": r.received_at, "reason": r.reason}
            for r in conn.execute(select(mgmt_skipped_messages).order_by(mgmt_skipped_messages.c.id))
        ]
        closed_clients = [r.client for r in conn.execute(select(mgmt_closed_clients).order_by(mgmt_closed_clients.c.client))]
        closed_projects = [
            r.project_id for r in conn.execute(select(mgmt_closed_projects).order_by(mgmt_closed_projects.c.project_id))
        ]
    return {
        "manual_entries": manual_entries,
        "project_kpi_samples": samples,
        "processed_message_ids": processed,
        "skipped_messages": skipped,
        "closed_clients": closed_clients,
        "closed_projects": closed_projects,
    }


def is_message_processed(message_id: str) -> bool:
    with _connect(begin=False) as conn:
        row = conn.execute(
            select(mgmt_processed_messages.c.message_id).where(mgmt_processed_messages.c.message_id == message_id)
        ).first()
    return row is not None


def get_closed_registry() -> dict:
    with _connect(begin=False) as conn:
        return {
            "closed_clients": [
                r.client for r in conn.execute(select(mgmt_closed_clients).order_by(mgmt_closed_clients.c.client))
            ],
            "closed_projects": [
                r.project_id
                for r in conn.execute(select(mgmt_closed_projects).order_by(mgmt_closed_projects.c.project_id))
            ],
        }


class WriteSession:
    """Uma transação de escrita já serializada pelo lock de `mgmt_meta` —
    toda gravação do painel passa por aqui, então nunca há duas
    leituras-modificações-escritas intercaladas (mesma garantia do
    `threading.RLock` de antes, agora também entre processos)."""

    def __init__(self, conn):
        self._conn = conn
        self._flags_snapshot: dict[str, bool] = {}

    def all_samples(self) -> list[dict]:
        samples = _read_samples(self._conn)
        self._flags_snapshot = {s["sample_id"]: bool(s["is_duplicate"]) for s in samples}
        return samples

    def insert_sample(self, sample: dict) -> None:
        next_seq = (self._conn.execute(select(func.max(mgmt_kpi_samples.c.seq))).scalar() or 0) + 1
        self._conn.execute(insert(mgmt_kpi_samples).values(seq=next_seq, **_sample_to_row(sample)))

    def replace_sample(self, sample: dict) -> None:
        row = _sample_to_row(sample)
        sample_id = row.pop("sample_id")
        self._conn.execute(update(mgmt_kpi_samples).where(mgmt_kpi_samples.c.sample_id == sample_id).values(**row))

    def delete_sample(self, sample_id: str) -> bool:
        result = self._conn.execute(delete(mgmt_kpi_samples).where(mgmt_kpi_samples.c.sample_id == sample_id))
        return result.rowcount > 0

    def save_duplicate_flags(self, samples: list[dict]) -> None:
        """Grava só as flags que mudaram desde o último `all_samples()`."""
        for sample in samples:
            flag = bool(sample.get("is_duplicate"))
            if self._flags_snapshot.get(sample["sample_id"]) == flag:
                continue
            self._conn.execute(
                update(mgmt_kpi_samples)
                .where(mgmt_kpi_samples.c.sample_id == sample["sample_id"])
                .values(is_duplicate=flag)
            )

    def mark_processed(self, message_id: str) -> None:
        exists = self._conn.execute(
            select(mgmt_processed_messages.c.message_id).where(mgmt_processed_messages.c.message_id == message_id)
        ).first()
        if exists is None:
            self._conn.execute(insert(mgmt_processed_messages).values(message_id=message_id, processed_at=_utcnow()))

    def insert_skipped(self, message_id: str, received_at: str, reason: str) -> None:
        self._conn.execute(
            insert(mgmt_skipped_messages).values(
                message_id=message_id, received_at=received_at, reason=reason, created_at=_utcnow(),
            )
        )

    def upsert_manual_entry(self, month: str, billed_hours: float | None, elaboration_days: float | None) -> None:
        values = dict(billed_hours=billed_hours, elaboration_days=elaboration_days, updated_at=_utcnow())
        result = self._conn.execute(
            update(mgmt_manual_entries).where(mgmt_manual_entries.c.month == month).values(**values)
        )
        if result.rowcount == 0:
            self._conn.execute(insert(mgmt_manual_entries).values(month=month, **values))

    def set_closed(self, table, column: str, value: str, closed: bool) -> None:
        col = table.c[column]
        exists = self._conn.execute(select(col).where(col == value)).first() is not None
        if closed and not exists:
            self._conn.execute(insert(table).values({column: value}))
        elif not closed and exists:
            self._conn.execute(delete(table).where(col == value))

    def has_any_data(self) -> bool:
        for table in _DATA_TABLES:
            if self._conn.execute(select(func.count()).select_from(table)).scalar_one():
                return True
        return False

    def snapshot_and_clear(self) -> dict:
        """Lê tudo (no formato do JSON) e apaga as linhas de dados — só pra
        `import_document(replace_existing=True)`, na mesma transação."""
        snapshot = {
            "manual_entries": {
                r.month: {"billed_hours": r.billed_hours, "elaboration_days": r.elaboration_days}
                for r in self._conn.execute(select(mgmt_manual_entries))
            },
            "project_kpi_samples": _read_samples(self._conn),
            "processed_message_ids": [
                r.message_id for r in self._conn.execute(select(mgmt_processed_messages.c.message_id))
            ],
            "skipped_messages": [
                {"message_id": r.message_id, "received_at": r.received_at, "reason": r.reason}
                for r in self._conn.execute(select(mgmt_skipped_messages).order_by(mgmt_skipped_messages.c.id))
            ],
            "closed_clients": [r.client for r in self._conn.execute(select(mgmt_closed_clients))],
            "closed_projects": [r.project_id for r in self._conn.execute(select(mgmt_closed_projects))],
        }
        for table in _DATA_TABLES:
            self._conn.execute(delete(table))
        return snapshot

    def get_meta(self, key: str):
        row = self._conn.execute(select(mgmt_meta.c.value_json).where(mgmt_meta.c.key == key)).first()
        return None if row is None else row.value_json

    def set_meta(self, key: str, value) -> None:
        result = self._conn.execute(
            update(mgmt_meta).where(mgmt_meta.c.key == key).values(value_json=value, updated_at=_utcnow())
        )
        if result.rowcount == 0:
            self._conn.execute(insert(mgmt_meta).values(key=key, value_json=value, updated_at=_utcnow()))


@contextmanager
def write_session() -> Iterator[WriteSession]:
    with _connect(begin=True) as conn:
        locked = conn.execute(
            select(mgmt_meta.c.key).where(mgmt_meta.c.key == _LOCK_KEY).with_for_update()
        ).first()
        if locked is None:
            # a migration 0006 cria essa linha; só falta quando o schema veio
            # de `metadata.create_all` (testes). Se outra conexão criou ao
            # mesmo tempo, o INSERT dela venceu — segue pro lock normalmente.
            try:
                conn.execute(insert(mgmt_meta).values(key=_LOCK_KEY, value_json=None, updated_at=_utcnow()))
            except IntegrityError:
                pass
            conn.execute(select(mgmt_meta.c.key).where(mgmt_meta.c.key == _LOCK_KEY).with_for_update())
        yield WriteSession(conn)


def import_document(
    document: dict, *, source_path: str | None, ignored_keys: dict, replace_existing: bool = False,
) -> dict:
    """Grava um documento já normalizado (formato do JSON antigo) numa
    única transação. Devolve as contagens importadas, ou
    `{"status": "already_imported"}`.

    Se já houver dado de gerência no banco sem registro de importação (ex:
    o backend novo subiu antes da importação e o polling de e-mail
    reprocessou os e-mails — recriando as amostras SEM as correções manuais
    que só o JSON tem), recusa. `replace_existing=True` é a saída
    deliberada pra esse caso: descarta o que está no banco e importa o JSON,
    guardando uma cópia do que foi descartado em `mgmt_meta`."""
    replaced = None
    with write_session() as session:
        if session.get_meta(LEGACY_IMPORT_KEY) is not None:
            return {"status": "already_imported"}
        if session.has_any_data():
            if not replace_existing:
                raise ManagementStoreError(
                    "reports_db já tem dados de gerência sem registro de importação — "
                    "importação recusada pra não misturar com o JSON. Se esses dados vieram só do "
                    "polling de e-mail rodando antes da importação, rode de novo com --replace-existing."
                )
            replaced = session.snapshot_and_clear()
        for month, entry in document["manual_entries"].items():
            session.upsert_manual_entry(month, entry.get("billed_hours"), entry.get("elaboration_days"))
        for sample in document["project_kpi_samples"]:
            session.insert_sample(sample)
        for message_id in document["processed_message_ids"]:
            session.mark_processed(message_id)
        for skipped in document["skipped_messages"]:
            session.insert_skipped(skipped.get("message_id"), skipped.get("received_at"), skipped.get("reason"))
        for client in document["closed_clients"]:
            session.set_closed(mgmt_closed_clients, "client", client, True)
        for project_id in document["closed_projects"]:
            session.set_closed(mgmt_closed_projects, "project_id", project_id, True)
        counts = {
            "manual_entries": len(document["manual_entries"]),
            "project_kpi_samples": len(document["project_kpi_samples"]),
            "processed_message_ids": len(set(document["processed_message_ids"])),
            "skipped_messages": len(document["skipped_messages"]),
            "closed_clients": len(set(document["closed_clients"])),
            "closed_projects": len(set(document["closed_projects"])),
        }
        session.set_meta(
            LEGACY_IMPORT_KEY,
            {
                "imported_at": _utcnow().isoformat(),
                "source_path": source_path,
                "counts": counts,
                # chaves do JSON sem tabela própria (ex: `nonbillable_packages`,
                # lista manual antiga substituída por `tjob.pExternal`) — ficam
                # guardadas aqui em vez de sumirem.
                "ignored_top_level_keys": ignored_keys,
                "replaced_existing_data": replaced,
            },
        )
    result = {"status": "imported", "counts": counts}
    if replaced is not None:
        result["replaced_samples"] = len(replaced["project_kpi_samples"])
    return result
