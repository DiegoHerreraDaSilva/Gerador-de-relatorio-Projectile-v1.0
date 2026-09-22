"""Schema do `reports_db` — banco PRÓPRIO de histórico/versionamento de
relatórios, separado do MySQL do Projectile (nunca há JOIN entre os dois).

SQLAlchemy Core (Table + MetaData), não ORM — consistente com o resto do
projeto, que manipula dado diretamente sem camada de abstração pesada
(`parser.py`/`generator.py`/`management.py`). `metadata` é o alvo de
autogenerate do Alembic (ver backend/alembic/env.py).

Cada `report` (relatório lógico) tem 1+ `report_versions` imutáveis; cada
versão referencia um `report_source_snapshot` (o payload exato recebido por
`/generate`, nunca uma reconsulta ao Projectile — ver plano de implementação)
e tem seus próprios `report_groups`/`report_activities`. Cada tentativa de
geração de arquivo (`report_generation`, granularidade por formato — xlsx e
pdf são chamadas independentes) produz no máximo 1 `report_artifact`.

Sem tabela `report_packages`: no payload real de `/generate`
(`ReportPackagePayload` em main.py), cada "pacote" já É um relatório inteiro
e independente (tem seu próprio header/signers), não uma coleção dentro de
um relatório maior — `report_groups.report_version_id` referencia
`report_versions.id` direto."""
from __future__ import annotations

from sqlalchemy import (
    CHAR,
    DECIMAL,
    JSON,
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

reports = Table(
    "reports",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("report_number", String(100), nullable=False),
    Column("scope", String(255), nullable=True),
    Column("competence_label", String(60), nullable=False),
    Column("competence_start", Date, nullable=True),
    Column("competence_end", Date, nullable=True),
    Column("identity_hash", CHAR(64), nullable=False, unique=True),
    Column("project_name_snapshot", String(255), nullable=False),
    Column("status", String(20), nullable=False, server_default="active"),
    # Sem FK: dependência circular com report_versions (a v1 só existe depois
    # que `reports` existe) — integridade garantida pela aplicação, sempre
    # escrita dentro da mesma transação que cria a versão.
    Column("current_version_id", CHAR(26), nullable=True),
    Column("created_by", String(100), nullable=False),
    Column("created_by_name_snapshot", String(255), nullable=False),
    Column("created_at", DateTime(timezone=False), nullable=False),
    Column("updated_at", DateTime(timezone=False), nullable=False),
    Index("idx_reports_report_number", "report_number"),
    Index("idx_reports_competence", "competence_start"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

report_source_snapshots = Table(
    "report_source_snapshots",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("source_system", String(50), nullable=False),
    Column("source_query", Text, nullable=True),
    Column("source_filters_json", JSON, nullable=True),
    Column("captured_at", DateTime(timezone=False), nullable=False),
    Column("source_reference", String(255), nullable=True),
    Column("data_json", JSON, nullable=False),
    Column("data_hash", CHAR(64), nullable=False),
    Column("schema_version", String(30), nullable=False),
    Index("idx_snapshots_hash", "data_hash"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

report_versions = Table(
    "report_versions",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("report_id", CHAR(26), ForeignKey("reports.id"), nullable=False),
    Column("version_number", Integer, nullable=False),
    Column("source_snapshot_id", CHAR(26), ForeignKey("report_source_snapshots.id"), nullable=False),
    Column("created_by", String(100), nullable=False),
    Column("created_from", String(30), nullable=False),
    Column("change_summary", Text, nullable=True),
    Column("state_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=False), nullable=False),
    UniqueConstraint("report_id", "version_number", name="uq_versions_report_number"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

report_groups = Table(
    "report_groups",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("report_version_id", CHAR(26), ForeignKey("report_versions.id"), nullable=False),
    Column("source_id", String(64), nullable=True),
    Column("name", String(255), nullable=False),
    Column("performance", DECIMAL(10, 2), nullable=False),
    Column("position", SmallInteger, nullable=False),
    Column("created_at", DateTime(timezone=False), nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

report_activities = Table(
    "report_activities",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("report_group_id", CHAR(26), ForeignKey("report_groups.id"), nullable=False),
    Column("source_id", String(64), nullable=True),
    Column("description", String(500), nullable=False),
    Column("hours", DECIMAL(10, 2), nullable=True),
    Column("position", SmallInteger, nullable=False),
    Column("created_at", DateTime(timezone=False), nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

report_generation = Table(
    "report_generation",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("report_id", CHAR(26), ForeignKey("reports.id"), nullable=False),
    Column("report_version_id", CHAR(26), ForeignKey("report_versions.id"), nullable=False),
    Column("format", String(10), nullable=False),
    Column("requested_by", String(100), nullable=False),
    Column("started_at", DateTime(timezone=False), nullable=False),
    Column("finished_at", DateTime(timezone=False), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    Column("status", String(20), nullable=False),
    Column("error_code", String(50), nullable=True),
    Column("error_message", Text, nullable=True),
    Index("idx_generation_status", "status"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

report_artifacts = Table(
    "report_artifacts",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("generation_id", CHAR(26), ForeignKey("report_generation.id"), nullable=False),
    Column("artifact_type", String(10), nullable=False),
    Column("storage_type", String(20), nullable=False, server_default="filesystem"),
    Column("storage_path", String(500), nullable=False),
    Column("file_name", String(255), nullable=False),
    Column("mime_type", String(150), nullable=False),
    Column("file_size", BigInteger, nullable=False),
    Column("sha256", CHAR(64), nullable=False),
    Column("created_at", DateTime(timezone=False), nullable=False),
    Index("idx_artifacts_sha256", "sha256"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)
