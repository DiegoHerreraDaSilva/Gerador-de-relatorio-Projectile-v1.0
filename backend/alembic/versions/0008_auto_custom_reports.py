"""geração personalizada: `auto_reports.kind`/`scope_json` e `run_id` opcional

Relatório personalizado (recorte livre de colaborador/cliente/projeto/pacote,
período qualquer) entra na mesma esteira do automático, mas não nasce de uma
rodada mensal.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("auto_reports") as batch:
        batch.add_column(sa.Column("kind", sa.String(10), nullable=False, server_default="mensal"))
        batch.add_column(sa.Column("scope_json", sa.JSON, nullable=True))
        batch.alter_column("run_id", existing_type=sa.CHAR(26), nullable=True)


def downgrade() -> None:
    # relatório personalizado não tem rodada: sai antes de voltar `run_id` a NOT NULL
    op.execute("DELETE FROM auto_report_events WHERE auto_report_id IN (SELECT id FROM auto_reports WHERE kind = 'avulso')")
    op.execute("DELETE FROM auto_reports WHERE kind = 'avulso'")
    with op.batch_alter_table("auto_reports") as batch:
        batch.alter_column("run_id", existing_type=sa.CHAR(26), nullable=False)
        batch.drop_column("scope_json")
        batch.drop_column("kind")
