"""report_versions

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_versions",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("report_id", sa.CHAR(26), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column(
            "source_snapshot_id", sa.CHAR(26), sa.ForeignKey("report_source_snapshots.id"), nullable=False
        ),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_from", sa.String(30), nullable=False),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("state_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("report_id", "version_number", name="uq_versions_report_number"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("report_versions")
