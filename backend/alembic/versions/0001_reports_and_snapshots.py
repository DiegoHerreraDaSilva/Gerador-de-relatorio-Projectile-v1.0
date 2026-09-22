"""reports + report_source_snapshots

Revision ID: 0001
Revises:
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("report_number", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(255), nullable=True),
        sa.Column("competence_label", sa.String(60), nullable=False),
        sa.Column("competence_start", sa.Date, nullable=True),
        sa.Column("competence_end", sa.Date, nullable=True),
        sa.Column("identity_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("project_name_snapshot", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_version_id", sa.CHAR(26), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_by_name_snapshot", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_reports_report_number", "reports", ["report_number"])
    op.create_index("idx_reports_competence", "reports", ["competence_start"])

    op.create_table(
        "report_source_snapshots",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_query", sa.Text, nullable=True),
        sa.Column("source_filters_json", sa.JSON, nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=True),
        sa.Column("data_json", sa.JSON, nullable=False),
        sa.Column("data_hash", sa.CHAR(64), nullable=False),
        sa.Column("schema_version", sa.String(30), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_snapshots_hash", "report_source_snapshots", ["data_hash"])


def downgrade() -> None:
    op.drop_table("report_source_snapshots")
    op.drop_table("reports")
