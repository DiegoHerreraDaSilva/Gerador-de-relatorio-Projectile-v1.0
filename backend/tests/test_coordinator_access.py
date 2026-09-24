"""Papel de coordenador: acessa Gerar relatório (inclusive busca por
cliente/projeto), Dashboard de horas, o próprio Histórico e o Diagnóstico —
nunca o Painel de Gerência, o Analytics nem os KPIs (`/management/kpis`),
nem pela API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import auth, management
from backend.app.api.dependencies import require_manager, require_manager_or_coordinator, require_session
from backend.app.api.routers import analytics as analytics_router
from backend.app.api.routers import management as management_router
from backend.app.api.routers import parsing as parsing_router
from backend.app.main import app

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x"}
_COORDINATOR = {"name": "Coordenador", "login": "coord", "email": "c@x"}
_COLLABORATOR = {"name": "Colaborador", "login": "colab", "email": "o@x"}

_MANAGER_ONLY = {
    ("GET", "/management/kpis"),
    ("POST", "/management/kpis/check-emails"),
    ("PUT", "/management/kpis/{month}"),
    ("GET", "/analytics/summary"),
}


@pytest.fixture(autouse=True)
def _roles(monkeypatch):
    monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(management, "COORDINATOR_LOGINS", {"coord"})
    yield
    app.dependency_overrides.pop(require_session, None)


def _client_as(user: dict) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _access_dependency(route) -> object:
    calls = {dep.call for dep in route.dependant.dependencies}
    for candidate in (require_manager, require_manager_or_coordinator):
        if candidate in calls:
            return candidate
    return None


def test_matriz_de_autorizacao_de_toda_rota_de_gerencia():
    """Toda rota de /management/*, /analytics/* e /parse-db-client precisa
    estar classificada: só gerente, ou gerente+coordenador. Uma rota nova
    sem decisão de acesso explícita faz este teste falhar."""
    routes = [
        *management_router.router.routes,
        *analytics_router.router.routes,
        *[r for r in parsing_router.router.routes if r.path == "/parse-db-client"],
    ]
    assert routes
    for route in routes:
        for method in route.methods:
            dependency = _access_dependency(route)
            expected = require_manager if (method, route.path) in _MANAGER_ONLY else require_manager_or_coordinator
            assert dependency is expected, f"{method} {route.path}: esperado {expected.__name__}"


@pytest.mark.parametrize("path", ["/management/kpis", "/analytics/summary"])
def test_coordenador_nao_ve_kpis_nem_analytics(path):
    response = _client_as(_COORDINATOR).get(path)
    assert response.status_code == 403


def test_colaborador_nao_acessa_o_diagnostico():
    response = _client_as(_COLLABORATOR).get("/management/send-status")
    assert response.status_code == 403


def test_send_status_nao_devolve_numero_de_kpi(monkeypatch):
    """O Diagnóstico do coordenador usa esta rota em vez de /management/kpis
    — nada de horas, faturamento ou performance pode sair por ela."""
    full_result = {
        "months": [{"month": "2026-08", "worked_hours": 100.0, "billed_hours": 90.0, "perf_kpi_pct": -0.1,
                    "nonbillable_hours": 5.0, "elaboration_days": 3.0}],
        "nonbillable_breakdown": [{"month": "2026-08", "package": "Treinamento", "hours": 5.0}],
        "cost_centers": ["CAD", "CAE"],
        "project_send_status": [{"month": "2026-08", "project_id": "P1", "status": "sent"}],
        "available_projects": ["Projeto 1"], "available_clients": ["Cliente"],
        "available_packages": ["Pacote"], "available_persons": ["Fulano"],
        "project_codes": {"Projeto 1": "1564"}, "project_clients": {"Projeto 1": "Cliente"},
    }
    monkeypatch.setattr(management_router, "compute_monthly_kpis", lambda *a, **k: full_result)

    response = _client_as(_COORDINATOR).get("/management/send-status")

    assert response.status_code == 200
    body = response.json()
    assert body["months"] == [{"month": "2026-08"}]
    assert "nonbillable_breakdown" not in body
    assert "cost_centers" not in body
    assert body["project_send_status"] == full_result["project_send_status"]
    assert body["available_persons"] == ["Fulano"]


def test_gerente_continua_com_acesso_aos_kpis(monkeypatch):
    monkeypatch.setattr(management_router, "compute_monthly_kpis", lambda *a, **k: {"months": []})
    assert _client_as(_MANAGER).get("/management/kpis").status_code == 200


@pytest.mark.parametrize(
    ("user", "expected"),
    [(_MANAGER, (True, False)), (_COORDINATOR, (False, True)), (_COLLABORATOR, (False, False))],
)
def test_auth_me_informa_o_papel(user, expected):
    token = auth.create_session(user)
    try:
        response = TestClient(app).get("/auth/me", cookies={"session_token": token})
    finally:
        auth.delete_session(token)
    assert response.status_code == 200
    assert (response.json()["is_manager"], response.json()["is_coordinator"]) == expected


def test_coordinator_logins_sem_env_e_vazio(monkeypatch):
    """Ao contrário das outras allowlists, não há fallback: env vazia não
    pode dar acesso a ninguém por engano."""
    monkeypatch.delenv("COORDINATOR_LOGINS", raising=False)
    assert management._load_coordinator_logins() == set()
    monkeypatch.setenv("COORDINATOR_LOGINS", " Coord , outro ,")
    assert management._load_coordinator_logins() == {"coord", "outro"}
