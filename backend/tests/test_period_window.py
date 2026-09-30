"""Janela de período de quem não é gerente (`api/period_access.py`):
coordenador e colaborador só veem e filtram os últimos 12 meses e o ano
atual, em todas as rotas. Gerente sem limite. Projectile e bancos falsos."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.api import period_access
from backend.app.api.dependencies import require_session
from backend.app.api.routers import history as history_router
from backend.app.api.routers import management as management_router
from backend.app.api.routers import my_hours as my_hours_router
from backend.app.api.routers import parsing as parsing_router
from backend.app.core import authz
from backend.app.main import app
from backend.app.services import report_queries

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x", "employee_id": "1"}
_COORDINATOR = {"name": "Coordenador", "login": "coord", "email": "c@x", "employee_id": "2"}
_COLLABORATOR = {"name": "Colaborador", "login": "colab", "email": "o@x", "employee_id": "3"}

_MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _label(d: date) -> str:
    return f"{_MONTHS[d.month - 1]}/{d.year}"


def _before_window() -> date:
    start, _ = period_access.window()
    return date(start.year - (start.month == 1), 12 if start.month == 1 else start.month - 1, 1)


@pytest.fixture(autouse=True)
def _roles(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(authz, "COORDINATOR_LOGINS", {"coord"})
    yield
    app.dependency_overrides.pop(require_session, None)


def _client(user) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


# --- a regra -----------------------------------------------------------------


@pytest.mark.parametrize(
    "today, start, end",
    [
        (date(2026, 9, 28), date(2025, 10, 1), date(2026, 12, 31)),
        (date(2027, 1, 5), date(2026, 2, 1), date(2027, 12, 31)),  # virada do ano
        (date(2026, 12, 31), date(2026, 1, 1), date(2026, 12, 31)),  # dezembro: o ano todo
    ],
)
def test_janela_e_os_ultimos_12_meses_e_o_ano_atual(today, start, end):
    assert period_access.window(today) == (start, end)
    assert len(period_access.allowed_months(today)) == (end.year * 12 + end.month) - (start.year * 12 + start.month) + 1
    assert period_access.window_label(date(2026, 9, 28)) == "outubro/2025 a dezembro/2026"


def test_gerente_nao_tem_janela():
    assert period_access.window_for(_MANAGER) is None
    assert period_access.in_window(_MANAGER, "2008-01-01")
    assert not period_access.in_window(_COLLABORATOR, "2025-09-30", today=date(2026, 9, 28))
    assert period_access.in_window(_COLLABORATOR, "2025-10-01", "2026-12-31", today=date(2026, 9, 28))


# --- Gerar relatório (busca no Projectile) -----------------------------------------


def test_colaborador_nao_busca_as_proprias_horas_fora_da_janela(monkeypatch):
    calls = []
    monkeypatch.setattr(parsing_router, "fetch_employee_hours", lambda *a, **k: calls.append(a) or [])
    old = _client(_COLLABORATOR).post("/parse-db", json={"month_label": _label(_before_window())})
    assert old.status_code == 403 and "últimos 12 meses" in old.json()["detail"] and calls == []
    # intervalo que COMEÇA dentro mas não termina: barrado igual
    start, _ = period_access.window()
    crossing = f"{_label(_before_window()).split('/')[0]}/{_before_window().year} a {_label(start)}"
    assert _client(_COLLABORATOR).post("/parse-db", json={"month_label": crossing}).status_code == 403
    # dentro da janela: busca (sem lançamento = 404, mas passou da checagem)
    assert _client(_COLLABORATOR).post("/parse-db", json={"month_label": _label(date.today())}).status_code == 404
    assert len(calls) == 1
    # gerente: qualquer mês
    assert _client(_MANAGER).post("/parse-db", json={"month_label": "Janeiro/2019"}).status_code == 404


def test_coordenador_nao_busca_projeto_nem_lista_clientes_fora_da_janela(monkeypatch):
    monkeypatch.setattr(parsing_router, "fetch_project_hours", lambda *a, **k: [])
    monkeypatch.setattr(management_router, "fetch_project_ids_with_hours", lambda *a, **k: [])
    monkeypatch.setattr(management_router, "fetch_clients_for_projects", lambda ids: [])
    old = _label(_before_window())
    coord = _client(_COORDINATOR)
    assert coord.post("/parse-db-client", json={"project_ids": ["P1"], "month_label": old}).status_code == 403
    assert coord.get("/management/clients-with-hours", params={"month_label": old}).status_code == 403
    assert coord.get("/management/client-projects", params={"client": "X", "month_label": old}).status_code == 403
    assert coord.get("/management/clients-with-hours", params={"month_label": _label(date.today())}).status_code == 200
    assert _client(_MANAGER).get("/management/clients-with-hours", params={"month_label": "Maio/2019"}).status_code == 200


# --- Diagnóstico: amostras fora da janela não se criam, editam nem apagam ------------


def test_coordenador_nao_mexe_em_amostra_fora_da_janela(monkeypatch):
    old = _before_window().strftime("%Y-%m")
    monkeypatch.setattr(management_router, "list_samples", lambda month=None: {"samples": [{"id": "S1", "month": old}], "skipped_messages": []})
    monkeypatch.setattr(management_router, "delete_project_kpi_sample", lambda sample_id: True)
    monkeypatch.setattr(management_router, "update_project_kpi_sample", lambda sample_id, patch: True)
    monkeypatch.setattr(management_router, "list_pacotes_for_project", lambda pid, month: [])
    coord = _client(_COORDINATOR)
    body = {"project_id": "P1", "month": old, "billed_hours": 1, "business_days": 1}
    assert coord.post("/management/kpis/samples", json=body).status_code == 403
    assert coord.patch("/management/kpis/samples/S1", json={"billed_hours": 2}).status_code == 403
    assert coord.delete("/management/kpis/samples/S1").status_code == 403
    assert coord.get("/management/projects/P1/packages", params={"month": old}).status_code == 403
    assert _client(_MANAGER).delete("/management/kpis/samples/S1").status_code == 200


# --- Dashboard de horas: nada antes da janela ---------------------------------------


def test_dashboard_de_horas_nao_devolve_nada_antes_da_janela(monkeypatch):
    starts = []
    old_day = _before_window()

    def daily_totals(start, end, **kw):
        starts.append(start)
        return [{"data": d, "horas": 8.0} for d in (old_day, date.today()) if d.isoformat() >= start]

    monkeypatch.setattr(my_hours_router, "fetch_my_hours", lambda *a, **k: [])
    monkeypatch.setattr(my_hours_router, "fetch_daily_hours_totals", daily_totals)
    monkeypatch.setattr(my_hours_router, "fetch_employee_contracts", lambda employee_id: [])
    monkeypatch.setattr(my_hours_router, "fetch_project_details", lambda ids: {})
    first = period_access.window()[0]

    mine = _client(_COLLABORATOR).get("/my-hours", params={"period": "last_12"}).json()
    assert starts[-1] == first.isoformat()  # nem busca antes
    assert all(p["month"] >= first.strftime("%Y-%m") for p in mine["monthly_series"])
    assert len(mine["monthly_series"]) == 12
    assert all(d >= first.isoformat() for d in mine["outlier_days"])
    assert mine["comparison"] is None  # a janela anterior cai fora

    boss = _client(_MANAGER).get("/my-hours", params={"period": "last_12"}).json()
    assert starts[-1] < first.isoformat() and len(boss["monthly_series"]) == 13


# --- Histórico -------------------------------------------------------------------


def test_historico_nao_lista_nem_abre_relatorio_fora_da_janela(monkeypatch):
    seen = {}

    def list_reports(**kwargs):
        seen.update(kwargs)
        return {"items": [], "page": 1, "page_size": 50, "total": 0}

    old = {"id": "R1", "created_by": "colab", "competence_start": _before_window(), "created_at": datetime(2026, 9, 1)}
    monkeypatch.setattr(report_queries, "list_reports", list_reports)
    monkeypatch.setattr(report_queries, "get_report", lambda report_id: dict(old))
    monkeypatch.setattr(history_router.report_queries, "get_report", lambda report_id: dict(old), raising=False)

    _client(_COLLABORATOR).get("/reports")
    assert seen["competence_from"] == period_access.window()[0]
    assert _client(_COLLABORATOR).get("/reports/R1").status_code == 404
    _client(_MANAGER).get("/reports")
    assert seen["competence_from"] is None
