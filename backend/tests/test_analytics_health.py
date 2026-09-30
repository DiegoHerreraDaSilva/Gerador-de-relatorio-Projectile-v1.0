"""Testes do painel de Saúde: `GET /analytics/health` (autorização e
contrato de erro) e as funções que o alimentam (`report_queries.
get_generation_health`/`get_artifacts_on_disk` e `system_health.
get_system_health`).

Os testes de agregação usam SQLite só com a tabela `report_generation` (a
query não usa nada específico de MySQL), sem Docker; os de disco usam
`tmp_path`. Nada aqui toca o Projectile."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert

from backend.app.api.dependencies import require_session
from backend.app.api.errors import GENERIC_REPORTS_DB_ERROR
from backend.app.core import authz
from backend.app.db.reports_schema import report_generation
from backend.app.main import app
from backend.app.services import report_queries, system_health

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x"}
_COORDINATOR = {"name": "Coordenador", "login": "coord", "email": "c@x"}

_NOW = datetime(2026, 9, 29, 12, 0, 0)  # naive UTC, como as colunas do banco


def _row(row_id: str, status: str, started: datetime, duration_ms: int | None = None, error_code: str | None = None, error_message: str | None = None) -> dict:
    return {
        "id": row_id,
        "report_id": "R" * 26,
        "report_version_id": "V" * 26,
        "format": "xlsx",
        "requested_by": "dherrera",
        "started_at": started,
        "finished_at": started,
        "duration_ms": duration_ms,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
    }


@pytest.fixture
def generation_engine(monkeypatch):
    engine = create_engine("sqlite://")
    report_generation.create(engine)
    monkeypatch.setattr(report_queries, "get_engine", lambda: engine)
    return engine


def _insert(engine, rows: list[dict]) -> None:
    with engine.begin() as conn:
        conn.execute(insert(report_generation), rows)


def test_geracao_agrega_janela_falhas_e_p95(generation_engine):
    _insert(
        generation_engine,
        [
            _row("01", "success", _NOW - timedelta(days=1), duration_ms=1000),
            _row("02", "success", _NOW - timedelta(days=2), duration_ms=2000),
            _row("03", "success", _NOW - timedelta(days=3), duration_ms=3000),
            _row("04", "failed", _NOW - timedelta(hours=1), error_code="E_GEN", error_message="boom"),
            _row("05", "failed", _NOW - timedelta(days=45), error_message="fora da janela"),
        ],
    )

    health = report_queries.get_generation_health(now=_NOW)

    assert health["window_days"] == 30
    assert health["total"] == 4  # a falha de 45 dias atrás não conta
    assert health["failed"] == 1
    assert health["failure_rate"] == pytest.approx(0.25)
    assert health["avg_duration_ms"] == pytest.approx(2000.0)
    assert health["p95_duration_ms"] == pytest.approx(3000.0)
    assert health["last_failure"]["error_message"] == "boom"
    assert health["last_failure"]["format"] == "xlsx"


def test_geracao_sem_dados_nao_inventa_numero(generation_engine):
    health = report_queries.get_generation_health(now=_NOW)
    assert health["total"] == 0
    assert health["failure_rate"] is None
    assert health["avg_duration_ms"] is None
    assert health["p95_duration_ms"] is None
    assert health["last_failure"] is None


def test_artefatos_em_disco_soma_tamanho(tmp_path):
    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "a.xlsx").write_bytes(b"12345")
    (tmp_path / "r1" / "b.pdf").write_bytes(b"123")
    (tmp_path / "r2").mkdir()
    (tmp_path / "r2" / "c.xlsx").write_bytes(b"1")

    result = report_queries.get_artifacts_on_disk(str(tmp_path))

    assert result == {"count": 3, "bytes": 9}


def test_artefatos_em_pasta_inexistente_e_zero(tmp_path):
    assert report_queries.get_artifacts_on_disk(str(tmp_path / "nao-existe")) == {"count": 0, "bytes": 0}


def test_system_health_compõe_as_partes(monkeypatch):
    monkeypatch.setattr(
        system_health,
        "report_queries",
        SimpleNamespace(get_generation_health=lambda: {"total": 10, "failed": 1}, get_artifacts_on_disk=lambda: {"count": 4, "bytes": 400}),
    )
    monkeypatch.setattr(
        system_health,
        "store",
        SimpleNamespace(
            list_runs=lambda: [{"competence": "2026-08", "status": "done", "triggered_by": "sistema", "started_at": None, "finished_at": None, "error": None}]
        ),
    )
    monkeypatch.setattr(
        system_health, "management", SimpleNamespace(list_samples=lambda: {"skipped_messages": [{"received_at": "2026-09-01T10:00:00", "reason": "sem anexo"}]})
    )

    health = system_health.get_system_health()

    assert health["generation"] == {"total": 10, "failed": 1}
    assert health["artifacts"] == {"count": 4, "bytes": 400}
    assert health["auto_generation"]["competence"] == "2026-08"
    assert health["auto_generation"]["status"] == "done"
    assert health["skipped_messages"] == {"count": 1, "last_received_at": "2026-09-01T10:00:00", "last_reason": "sem anexo"}
    assert health["checked_at"]


def test_system_health_sem_rodada_nem_ignoradas(monkeypatch):
    monkeypatch.setattr(
        system_health, "report_queries", SimpleNamespace(get_generation_health=lambda: {}, get_artifacts_on_disk=lambda: {"count": 0, "bytes": 0})
    )
    monkeypatch.setattr(system_health, "store", SimpleNamespace(list_runs=lambda: []))
    monkeypatch.setattr(system_health, "management", SimpleNamespace(list_samples=lambda: {"skipped_messages": []}))

    health = system_health.get_system_health()

    assert health["auto_generation"] is None
    assert health["skipped_messages"] == {"count": 0, "last_received_at": None, "last_reason": None}


@pytest.fixture(autouse=True)
def _roles(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    yield
    app.dependency_overrides.pop(require_session, None)


def test_analytics_health_sem_sessao_401_e_coordenador_403():
    assert TestClient(app).get("/analytics/health").status_code == 401
    app.dependency_overrides[require_session] = lambda: _COORDINATOR
    assert TestClient(app).get("/analytics/health").status_code == 403


def test_analytics_health_gerente_recebe_o_payload(monkeypatch):
    fake = {
        "generation": {"total": 1},
        "artifacts": {"count": 0, "bytes": 0},
        "auto_generation": None,
        "skipped_messages": {"count": 0},
        "checked_at": "2026-09-29T12:00:00+00:00",
    }
    monkeypatch.setattr(system_health, "get_system_health", lambda: fake)
    app.dependency_overrides[require_session] = lambda: _MANAGER

    response = TestClient(app).get("/analytics/health")

    assert response.status_code == 200
    assert response.json() == fake


def test_analytics_health_banco_fora_vira_502_generico(monkeypatch):
    def _boom():
        raise RuntimeError("reports_db fora do ar")

    monkeypatch.setattr(system_health, "get_system_health", _boom)
    app.dependency_overrides[require_session] = lambda: _MANAGER

    response = TestClient(app).get("/analytics/health")

    assert response.status_code == 502
    assert response.json()["detail"] == GENERIC_REPORTS_DB_ERROR
