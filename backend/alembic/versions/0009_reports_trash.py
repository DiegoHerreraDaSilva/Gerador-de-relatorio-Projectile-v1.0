"""lixeira de relatórios: `reports.deleted_at` / `deleted_by`

Apagar um relatório do Histórico passa a ser "mover pra lixeira" (restaurável por 30 dias, depois purga).
Colunas nulas e opcionais: o código antigo continua funcionando com elas presentes.

Downgrade: os relatórios que estavam na lixeira VOLTAM a aparecer no Histórico (nada é apagado).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=False), nullable=True))
        batch.add_column(sa.Column("deleted_by", sa.String(100), nullable=True))
        batch.create_index("idx_reports_deleted_at", ["deleted_at"])


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.drop_index("idx_reports_deleted_at")
        batch.drop_column("deleted_by")
        batch.drop_column("deleted_at")
