"""report_groups + report_activities

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_groups",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("report_version_id", sa.CHAR(26), sa.ForeignKey("report_versions.id"), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("performance", sa.DECIMAL(10, 2), nullable=False),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "report_activities",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("report_group_id", sa.CHAR(26), sa.ForeignKey("report_groups.id"), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("hours", sa.DECIMAL(10, 2), nullable=True),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("report_activities")
    op.drop_table("report_groups")
