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
    Boolean,
    Column,
    Date,
    DateTime,
    Double,
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


def _exact_string(length: int):
    """VARCHAR com comparação exata (binária) no MySQL. O collation padrão
    das tabelas (`utf8mb4_unicode_ci`) ignora maiúsculas/minúsculas, e ids
    do Microsoft Graph diferenciam isso: dois `message_id` distintos só na
    caixa colidiriam como a mesma chave. `with_variant` mantém o tipo
    neutro em outros dialetos (SQLite dos testes não conhece esse collation)."""
    return String(length).with_variant(String(length, collation="utf8mb4_bin"), "mysql")

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

# Auditoria — trilha de "quem fez o quê, quando, em qual
# entidade". Escrita sempre fail-open (mesmo padrão de report_persistence),
# nunca pode derrubar a operação de negócio que está sendo auditada.
audit_log = Table(
    "audit_log",
    metadata,
    Column("id", CHAR(26), primary_key=True),
    Column("actor_id", String(100), nullable=False),
    Column("actor_name_snapshot", String(255), nullable=False),
    Column("action", String(50), nullable=False),
    Column("entity_type", String(30), nullable=False),
    Column("entity_id", CHAR(26), nullable=False),
    Column("source", String(30), nullable=False),
    Column("before_json", JSON, nullable=True),
    Column("after_json", JSON, nullable=True),
    Column("metadata_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=False), nullable=False),
    Index("idx_audit_entity", "entity_type", "entity_id"),
    Index("idx_audit_actor", "actor_id"),
    Index("idx_audit_created_at", "created_at"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

# Dados do Painel de Gerência / Diagnóstico, antes em
# backend/data/management_kpi.json — uma tabela por seção daquele documento.
# Diferente do histórico de relatórios, isto é dado PRIMÁRIO (entradas
# manuais do gerente, amostras corrigidas à mão): não há fail-open, ver
# services/management_store.py. Horas/dias em DOUBLE (não DECIMAL) pra
# reproduzir exatamente o float que o JSON guardava.
_MYSQL_TABLE_OPTS = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci")

mgmt_manual_entries = Table(
    "mgmt_manual_entries",
    metadata,
    Column("month", String(7), primary_key=True),
    Column("billed_hours", Double, nullable=True),
    Column("elaboration_days", Double, nullable=True),
    Column("updated_at", DateTime(timezone=False), nullable=False),
    **_MYSQL_TABLE_OPTS,
)

mgmt_kpi_samples = Table(
    "mgmt_kpi_samples",
    metadata,
    Column("sample_id", _exact_string(64), primary_key=True),
    # ordem de inserção (a posição na lista do JSON antigo) — desempate de
    # `_recompute_duplicate_flags` quando duas amostras têm o mesmo
    # `received_at`; sem isso a ordem de leitura seria indefinida.
    Column("seq", BigInteger, nullable=False),
    Column("email_message_id", _exact_string(512), nullable=False),
    # texto ISO exatamente como o JSON guardava — a ordenação e a detecção de
    # duplicata usam comparação de string, não de data.
    Column("received_at", String(40), nullable=True),
    Column("sender", String(255), nullable=True),
    Column("report_project_text", Text, nullable=True),
    Column("project_id", _exact_string(100), nullable=True),
    Column("project_name", String(255), nullable=True),
    Column("match_score", Double, nullable=True),
    Column("month", String(7), nullable=True),
    Column("billed_hours", Double, nullable=True),
    Column("business_days", Double, nullable=True),
    Column("pacote_scope", JSON, nullable=True),
    Column("source", String(20), nullable=False),
    Column("edited", Boolean, nullable=False, default=False),
    Column("is_duplicate", Boolean, nullable=False, default=False),
    # qualquer chave da amostra que não tenha coluna própria — a migração
    # não pode descartar dado em silêncio.
    Column("extra_json", JSON, nullable=True),
    Index("idx_mgmt_samples_seq", "seq"),
    Index("idx_mgmt_samples_message", "email_message_id"),
    Index("idx_mgmt_samples_project_month", "project_id", "month"),
    **_MYSQL_TABLE_OPTS,
)

mgmt_processed_messages = Table(
    "mgmt_processed_messages",
    metadata,
    Column("message_id", _exact_string(512), primary_key=True),
    Column("processed_at", DateTime(timezone=False), nullable=False),
    **_MYSQL_TABLE_OPTS,
)

mgmt_skipped_messages = Table(
    "mgmt_skipped_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("message_id", _exact_string(512), nullable=False),
    Column("received_at", String(40), nullable=True),
    Column("reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=False), nullable=False),
    **_MYSQL_TABLE_OPTS,
)

mgmt_closed_clients = Table(
    "mgmt_closed_clients",
    metadata,
    Column("client", _exact_string(255), primary_key=True),
    **_MYSQL_TABLE_OPTS,
)

mgmt_closed_projects = Table(
    "mgmt_closed_projects",
    metadata,
    Column("project_id", _exact_string(100), primary_key=True),
    **_MYSQL_TABLE_OPTS,
)

# Linha única usada como mutex (`SELECT ... FOR UPDATE`) pra toda escrita
# que precisa ler TODAS as amostras antes de gravar (recalcular flags de
# duplicata) — substitui o `threading.RLock` de antes e, ao contrário dele,
# também serializa entre processos. Também guarda quando/de onde veio a
# importação do JSON antigo (idempotência de `import_legacy_json`).
mgmt_meta = Table(
    "mgmt_meta",
    metadata,
    Column("key", String(50), primary_key=True),
    Column("value_json", JSON, nullable=True),
    Column("updated_at", DateTime(timezone=False), nullable=False),
    **_MYSQL_TABLE_OPTS,
)
