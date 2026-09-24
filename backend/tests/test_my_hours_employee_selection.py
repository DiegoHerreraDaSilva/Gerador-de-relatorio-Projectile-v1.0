"""Seletor de colaborador no Dashboard de horas: gerente/coordenador podem
ver as horas de alguém de engenharia (CAD+CAE); colaborador comum só vê as
próprias. O `employee_id` vindo do cliente nunca é usado direto — sempre
re-resolvido contra a lista de engenharia no servidor."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import management
from backend.app.api.dependencies import require_session
from backend.app.api.routers import my_hours as my_hours_router
from backend.app.main import app

_COORDINATOR = {"name": "Coordenador", "login": "coord", "email": "c@x", "employee_id": "100", "filiale": None}
_COLLABORATOR = {"name": "Colaborador", "login": "colab", "email": "o@x", "employee_id": "200", "filiale": None}
_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x", "employee_id": "300", "filiale": None}

_ENGINEERING = [
    {"employee_id": "500", "name": "Ana Engenharia", "filiale": "Santo André", "cost_center": "CAD"},
    {"employee_id": "600", "name": "Bruno Engenharia", "filiale": None, "cost_center": "CAE"},
]


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(management, "COORDINATOR_LOGINS", {"coord"})
    monkeypatch.setattr(my_hours_router, "_employees_cache", {"fetched_at": 0.0, "employees": None})
    calls = {"my_hours": [], "employees": 0}

    def _employees(start, end):
        calls["employees"] += 1
        return _ENGINEERING

    def _my_hours(start, end, employee_id=None, employee_name=None):
        calls["my_hours"].append({"employee_id": employee_id, "employee_name": employee_name})
        return []

    monkeypatch.setattr(my_hours_router, "fetch_engineering_employees", _employees)
    monkeypatch.setattr(my_hours_router, "fetch_my_hours", _my_hours)
    monkeypatch.setattr(my_hours_router, "fetch_daily_hours_totals", lambda *a, **k: [])
    monkeypatch.setattr(my_hours_router, "fetch_employee_contracts", lambda employee_id: [])
    monkeypatch.setattr(my_hours_router, "fetch_project_details", lambda ids: {})
    yield calls
    app.dependency_overrides.pop(require_session, None)


def _client_as(user: dict) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def test_sem_employee_id_continua_mostrando_o_proprio_usuario(_setup):
    response = _client_as(_COLLABORATOR).get("/my-hours")

    assert response.status_code == 200
    assert response.json()["employee"] == {"employee_id": "200", "name": "Colaborador"}
    assert _setup["my_hours"][0]["employee_id"] == "200"
    assert _setup["employees"] == 0


def test_colaborador_nao_ve_horas_de_outra_pessoa(_setup):
    response = _client_as(_COLLABORATOR).get("/my-hours", params={"employee_id": "500"})

    assert response.status_code == 403
    assert _setup["my_hours"] == []


def test_colaborador_pode_passar_o_proprio_id(_setup):
    assert _client_as(_COLLABORATOR).get("/my-hours", params={"employee_id": "200"}).status_code == 200


@pytest.mark.parametrize("user", [_COORDINATOR, _MANAGER])
def test_coordenador_e_gerente_veem_alguem_de_engenharia(_setup, user):
    response = _client_as(user).get("/my-hours", params={"employee_id": "500"})

    assert response.status_code == 200
    assert response.json()["employee"] == {"employee_id": "500", "name": "Ana Engenharia"}
    assert _setup["my_hours"][0] == {"employee_id": "500", "employee_name": "Ana Engenharia"}


def test_filial_vem_do_projectile_e_muda_o_feriado_municipal(_setup):
    """A filial não vem do cliente nem da sessão de quem está olhando: é a
    do colaborador escolhido, e decide o feriado de Santo André."""
    response = _client_as(_COORDINATOR).get("/my-hours", params={"employee_id": "500"})

    assert "Santo André" in response.json()["business_days"]["note"]


def test_id_fora_da_engenharia_da_404(_setup):
    response = _client_as(_COORDINATOR).get("/my-hours", params={"employee_id": "999"})

    assert response.status_code == 404
    assert _setup["my_hours"] == []


def test_lista_de_colaboradores_so_para_gerente_ou_coordenador(_setup):
    assert _client_as(_COLLABORATOR).get("/my-hours/employees").status_code == 403

    response = _client_as(_COORDINATOR).get("/my-hours/employees")
    assert response.status_code == 200
    employees = response.json()["employees"]
    assert [e["name"] for e in employees] == ["Ana Engenharia", "Bruno Engenharia"]
    assert "filiale" not in employees[0]


def test_lista_de_colaboradores_usa_cache(_setup):
    client = _client_as(_COORDINATOR)
    client.get("/my-hours/employees")
    client.get("/my-hours", params={"employee_id": "600"})
    client.get("/my-hours/employees")

    assert _setup["employees"] == 1
