"""geração automática de relatórios — tabelas auto_*

Rascunhos mensais gerados pelo sistema (um por competência + projeto), com
revisão/aprovação/envio. Só viram relatório do histórico (`reports`) na
aprovação, quando o gerente já digitou o número.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-28

"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPTS = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci")


def _exact(length: int):
    return sa.String(length).with_variant(sa.String(length, collation="utf8mb4_bin"), "mysql")


def upgrade() -> None:
    settings = op.create_table(
        "auto_settings",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("value_json", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "auto_families",
        sa.Column("project_id", _exact(100), primary_key=True),
        sa.Column("family_key", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "auto_rules",
        sa.Column("family_key", sa.String(255), primary_key=True),
        sa.Column("config_json", sa.JSON, nullable=False),
        sa.Column("updated_by", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "auto_memory",
        sa.Column("family_key", sa.String(255), primary_key=True),
        sa.Column("memory_json", sa.JSON, nullable=False),
        sa.Column("source_auto_report_id", sa.CHAR(26), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_table(
        "auto_runs",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("competence", sa.String(7), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("triggered_by", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("counts_json", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        **_OPTS,
    )
    op.create_table(
        "auto_reports",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("run_id", sa.CHAR(26), nullable=False),
        sa.Column("competence", sa.String(7), nullable=False),
        sa.Column("project_id", _exact(100), nullable=False),
        sa.Column("family_key", sa.String(255), nullable=False),
        sa.Column("project_name", sa.String(255), nullable=False),
        sa.Column("client", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reviewer_login", sa.String(100), nullable=True),
        sa.Column("reviewer_name", sa.String(255), nullable=True),
        sa.Column("draft_json", sa.JSON, nullable=True),
        sa.Column("draft_version", sa.Integer, nullable=False),
        sa.Column("source_hours", sa.Double, nullable=True),
        sa.Column("badges_json", sa.JSON, nullable=True),
        sa.Column("ai_original_json", sa.JSON, nullable=True),
        sa.Column("approved_payload_json", sa.JSON, nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("sent_by", sa.String(100), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("history_links_json", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("competence", "project_id", name="uq_auto_reports_competence_project"),
        **_OPTS,
    )
    op.create_index("idx_auto_reports_competence_status", "auto_reports", ["competence", "status"])
    op.create_table(
        "auto_report_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("auto_report_id", sa.CHAR(26), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor_login", sa.String(100), nullable=True),
        sa.Column("actor_name", sa.String(255), nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        **_OPTS,
    )
    op.create_index("idx_auto_report_events_report", "auto_report_events", ["auto_report_id"])
    # linha usada como mutex por services/auto_generation_store.py — criada
    # aqui pra nunca haver corrida entre dois processos tentando criá-la
    op.bulk_insert(
        settings,
        [{"key": "lock", "value_json": None, "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)}],
    )


def downgrade() -> None:
    op.drop_index("idx_auto_report_events_report", table_name="auto_report_events")
    op.drop_index("idx_auto_reports_competence_status", table_name="auto_reports")
    for table in (
        "auto_report_events", "auto_reports", "auto_runs", "auto_memory",
        "auto_rules", "auto_families", "auto_settings",
    ):
        op.drop_table(table)
