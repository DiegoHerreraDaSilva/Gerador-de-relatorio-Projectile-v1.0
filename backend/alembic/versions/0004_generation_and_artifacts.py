"""report_generation + report_artifacts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_generation",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("report_id", sa.CHAR(26), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("report_version_id", sa.CHAR(26), sa.ForeignKey("report_versions.id"), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_generation_status", "report_generation", ["status"])

    op.create_table(
        "report_artifacts",
        sa.Column("id", sa.CHAR(26), primary_key=True),
        sa.Column("generation_id", sa.CHAR(26), sa.ForeignKey("report_generation.id"), nullable=False),
        sa.Column("artifact_type", sa.String(10), nullable=False),
        sa.Column("storage_type", sa.String(20), nullable=False, server_default="filesystem"),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_artifacts_sha256", "report_artifacts", ["sha256"])


def downgrade() -> None:
    op.drop_table("report_artifacts")
    op.drop_table("report_generation")
