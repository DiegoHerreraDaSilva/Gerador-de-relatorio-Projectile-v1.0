"""Roda como processo SEPARADO do backend (via CLI `alembic`), então não
herda o `load_dotenv()` de `main.py:23` nem o `sys.path` que
`backend.app.main` normalmente tem — este arquivo precisa dos dois
explicitamente, mesmo truque de `backend/tests/conftest.py`."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import get_settings
from backend.app.db.reports_schema import metadata
from backend.app.db_credentials import DbCredentialsError, get_reports_db_password

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _reports_db_url() -> str:
    import os

    settings = get_settings()
    # CI (ubuntu-latest) não tem Windows Credential Manager — mesma saída de
    # REPORTS_DB_TEST_PASSWORD usada pelo fixture de teste (conftest.py),
    # setada só no workflow, nunca em dev local.
    password = os.environ.get("REPORTS_DB_TEST_PASSWORD")
    if not password:
        try:
            password = get_reports_db_password(settings.reports_db_user)
        except DbCredentialsError as e:
            raise SystemExit(
                f"Não foi possível ler a senha do reports_db no Windows Credential Manager: {e}\n"
                "Suba o container (docker compose up -d reports-mysql) e guarde a senha no "
                "keyring antes de rodar migrations (ver docker-compose.yml)."
            ) from e
    return (
        f"mysql+pymysql://{settings.reports_db_user}:{password}"
        f"@{settings.reports_db_host}:{settings.reports_db_port}/{settings.reports_db_name}"
        "?charset=utf8mb4"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_reports_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _reports_db_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
