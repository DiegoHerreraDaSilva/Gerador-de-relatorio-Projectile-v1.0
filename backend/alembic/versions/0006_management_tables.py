"""management (Painel de Gerência / Diagnóstico) — tabelas mgmt_*

Antes em backend/data/management_kpi.json. Só cria as tabelas: a importação
do JSON existente é um passo separado e explícito
(`python -m backend.app.tools.import_management_json`), pra não acoplar esta
migration ao código vivo da aplicação.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23

"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPTS = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci")


def _exact(length: int):
    return sa.String(length).with_variant(sa.String(length, collation="utf8mb4_bin"), "mysql")


def upgrade() -> None:
    op.create_table(
        "mgmt_manual_entries",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("billed_hours", sa.Double, nullable=True),
        sa.Column("elaboration_days", sa.Double, nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "mgmt_kpi_samples",
        sa.Column("sample_id", _exact(64), primary_key=True),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("email_message_id", _exact(512), nullable=False),
        sa.Column("received_at", sa.String(40), nullable=True),
        sa.Column("sender", sa.String(255), nullable=True),
        sa.Column("report_project_text", sa.Text, nullable=True),
        sa.Column("project_id", _exact(100), nullable=True),
        sa.Column("project_name", sa.String(255), nullable=True),
        sa.Column("match_score", sa.Double, nullable=True),
        sa.Column("month", sa.String(7), nullable=True),
        sa.Column("billed_hours", sa.Double, nullable=True),
        sa.Column("business_days", sa.Double, nullable=True),
        sa.Column("pacote_scope", sa.JSON, nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("edited", sa.Boolean, nullable=False),
        sa.Column("is_duplicate", sa.Boolean, nullable=False),
        sa.Column("extra_json", sa.JSON, nullable=True),
        **_OPTS,
    )
    op.create_index("idx_mgmt_samples_seq", "mgmt_kpi_samples", ["seq"])
    op.create_index("idx_mgmt_samples_message", "mgmt_kpi_samples", ["email_message_id"])
    op.create_index("idx_mgmt_samples_project_month", "mgmt_kpi_samples", ["project_id", "month"])
    op.create_table(
        "mgmt_processed_messages",
        sa.Column("message_id", _exact(512), primary_key=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "mgmt_skipped_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("message_id", _exact(512), nullable=False),
        sa.Column("received_at", sa.String(40), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "mgmt_closed_clients",
        sa.Column("client", _exact(255), primary_key=True),
        **_OPTS,
    )
    op.create_table(
        "mgmt_closed_projects",
        sa.Column("project_id", _exact(100), primary_key=True),
        **_OPTS,
    )
    meta = op.create_table(
        "mgmt_meta",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("value_json", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    # linha usada como mutex por services/management_store.py — criada aqui
    # pra nunca haver corrida entre dois processos tentando criá-la.
    op.bulk_insert(
        meta,
        [{"key": "samples_lock", "value_json": None, "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)}],
    )


def downgrade() -> None:
    for table in (
        "mgmt_meta", "mgmt_closed_projects", "mgmt_closed_clients", "mgmt_skipped_messages",
        "mgmt_processed_messages", "mgmt_kpi_samples", "mgmt_manual_entries",
    ):
        op.drop_table(table)
