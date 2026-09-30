"""Testes de `/health` (público) e `/health/details` (só gerente) — ver
`api/routers/health.py`. Nada aqui toca banco: os checks são monkeypatched
(os de verdade são cobertos ponta a ponta no ambiente)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import require_session
from backend.app.api.routers import health as health_router
from backend.app.core import authz
from backend.app.main import app

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x"}
_COORDINATOR = {"name": "Coordenador", "login": "coord", "email": "c@x"}


def _ok() -> dict:
    return {"ok": True, "latency_ms": 1}


def _fail() -> dict:
    return {"ok": False, "latency_ms": 1, "error": "OperationalError"}


@pytest.fixture(autouse=True)
def _roles(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    yield
    app.dependency_overrides.pop(require_session, None)


def _client_as(user: dict) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _patch_checks(monkeypatch, reports_db: dict, projectile: dict) -> None:
    monkeypatch.setattr(health_router, "check_reports_db", lambda: reports_db)
    monkeypatch.setattr(health_router, "check_projectile", lambda: projectile)


def test_health_publico_ok_sem_login(monkeypatch):
    _patch_checks(monkeypatch, _ok(), _ok())
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_degraded_quando_reports_db_falha(monkeypatch):
    _patch_checks(monkeypatch, _fail(), _ok())
    response = TestClient(app).get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded"}


def test_health_degraded_quando_projectile_falha(monkeypatch):
    _patch_checks(monkeypatch, _ok(), _fail())
    response = TestClient(app).get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded"}


def test_health_publico_nao_vaza_detalhe(monkeypatch):
    _patch_checks(monkeypatch, _fail(), _fail())
    body = TestClient(app).get("/health").json()
    assert set(body.keys()) == {"status"}


def test_details_sem_sessao_401_e_coordenador_403(monkeypatch):
    _patch_checks(monkeypatch, _ok(), _ok())
    assert TestClient(app).get("/health/details").status_code == 401
    assert _client_as(_COORDINATOR).get("/health/details").status_code == 403


def test_details_mostra_check_por_check(monkeypatch):
    _patch_checks(monkeypatch, _ok(), _fail())
    monkeypatch.setattr(health_router, "check_scheduler", lambda: {"ok": True, "enabled": True, "last_tick_at": "2026-09-29T12:00:00+00:00"})
    body = _client_as(_MANAGER).get("/health/details").json()
    assert body["status"] == "degraded"  # um check falhando marca o status
    assert body["checks"]["reports_db"]["ok"] is True
    assert body["checks"]["projectile"] == {"ok": False, "latency_ms": 1, "error": "OperationalError"}
    assert body["checks"]["scheduler"]["last_tick_at"]


def test_check_scheduler_desligado_e_considerado_ok(monkeypatch):
    monkeypatch.setattr(health_router, "get_settings", lambda: SimpleNamespace(auto_generation_enabled=False))
    monkeypatch.setattr(health_router, "scheduler", SimpleNamespace(POLL_SECONDS=300, last_tick_at=lambda: None))
    result = health_router.check_scheduler()
    assert result == {"ok": True, "enabled": False, "last_tick_at": None}


def test_check_scheduler_heartbeat_velho_fica_degraded(monkeypatch):
    agora = datetime.now(UTC)
    monkeypatch.setattr(health_router, "get_settings", lambda: SimpleNamespace(auto_generation_enabled=True))
    monkeypatch.setattr(health_router, "scheduler", SimpleNamespace(POLL_SECONDS=300, last_tick_at=lambda: agora - timedelta(minutes=30)))
    result = health_router.check_scheduler()
    assert result["ok"] is False
    assert result["enabled"] is True


def test_check_scheduler_heartbeat_recente_e_ok(monkeypatch):
    agora = datetime.now(UTC)
    monkeypatch.setattr(health_router, "get_settings", lambda: SimpleNamespace(auto_generation_enabled=True))
    monkeypatch.setattr(health_router, "scheduler", SimpleNamespace(POLL_SECONDS=300, last_tick_at=lambda: agora - timedelta(seconds=30)))
    assert health_router.check_scheduler()["ok"] is True
