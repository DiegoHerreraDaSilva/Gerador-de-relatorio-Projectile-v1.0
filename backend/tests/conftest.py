"""Garante a raiz do repo no sys.path mesmo se pytest for invocado de um jeito
que não respeite `pythonpath` do pytest.ini (ex: um runner de IDE que ignora
o ini). Idempotente e barato — checagem redundante de propósito com
`pytest.ini:pythonpath`, não um substituto dele."""
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_REPORTS_DB_TEST_NAME = "reports_db_test"


@pytest.fixture
def reports_db_engine(monkeypatch):
    """Engine real contra um schema de TESTE separado (`reports_db_test`),
    nunca o `reports_db` de desenvolvimento — pulado automaticamente
    (`pytest.skip`) se `REPORTS_DB_HOST` não estiver setado, então a suíte
    local roda sem exigir Docker por padrão (ver
    `test_reports_db_persistence.py`/`test_generate_persistence_integration.py`,
    marcados `@pytest.mark.reports_db`).

    Dev local: usa `REPORTS_MYSQL_ROOT_PASSWORD` (do `.env`, se presente)
    pra criar o schema de teste + conceder acesso ao usuário `reports_app`
    de forma idempotente — o usuário criado pelo `docker-compose.yml` só
    tem grant automático no `reports_db` real, não num schema extra.

    CI (`ubuntu-latest`, sem Windows Credential Manager): usa
    `REPORTS_DB_TEST_PASSWORD` (setada só no workflow) via
    `monkeypatch` — a função de produção em `db_credentials.py` nunca
    muda; o serviço `mysql` do CI já cria `reports_db_test`/`reports_app`
    prontos (mesmo mecanismo do `docker-compose.yml` local), então não
    precisa de credencial root ali."""
    from dotenv import load_dotenv

    # idempotente — precisa rodar ANTES do check de REPORTS_DB_HOST porque
    # pydantic-settings lê o .env sozinho (sem popular os.environ), mas
    # este check aqui é um os.environ.get puro; sem isso, REPORTS_DB_HOST
    # só setado no .env (não exportado no shell) faria este fixture pular
    # sempre em dev local, mesmo com o container de pé.
    load_dotenv()

    if not os.environ.get("REPORTS_DB_HOST"):
        pytest.skip(
            "REPORTS_DB_HOST não setado — pulando teste que precisa do reports-mysql real "
            "(rode `docker compose up -d reports-mysql` e defina REPORTS_DB_HOST no .env pra incluir)."
        )

    from backend.app.core.config import get_settings
    from backend.app.db.reports_schema import metadata
    from backend.app.services import audit, report_persistence, report_queries

    settings = get_settings()
    host, port, user = settings.reports_db_host, settings.reports_db_port, settings.reports_db_user

    test_password = os.environ.get("REPORTS_DB_TEST_PASSWORD")
    if test_password:
        password = test_password
    else:
        from backend.app.db_credentials import get_reports_db_password

        password = get_reports_db_password(user)
        root_password = os.environ.get("REPORTS_MYSQL_ROOT_PASSWORD")
        if root_password:
            admin_engine = create_engine(f"mysql+pymysql://root:{root_password}@{host}:{port}/?charset=utf8mb4")
            with admin_engine.begin() as conn:
                conn.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS {_REPORTS_DB_TEST_NAME} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
                conn.execute(text(f"GRANT ALL ON {_REPORTS_DB_TEST_NAME}.* TO '{user}'@'%'"))
                conn.execute(text("FLUSH PRIVILEGES"))
            admin_engine.dispose()

    test_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{_REPORTS_DB_TEST_NAME}?charset=utf8mb4"
    engine = create_engine(test_url, pool_pre_ping=True)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    # report_persistence/report_queries/audit cada um faz `from ..db.reports_db
    # import get_engine` — três bindings independentes da mesma função no
    # namespace de cada módulo. Precisa trocar os três, senão escritas e
    # leituras acabam batendo em bancos diferentes (bug real, encontrado ao
    # rodar os testes de histórico pela primeira vez).
    monkeypatch.setattr(report_persistence, "get_engine", lambda: engine)
    monkeypatch.setattr(report_queries, "get_engine", lambda: engine)
    monkeypatch.setattr(audit, "get_engine", lambda: engine)

    yield engine
    engine.dispose()
