"""Testes de integração de `GET /analytics/summary` — precisa do
reports-mysql real (ver conftest.py:reports_db_engine), mesmo padrão de
test_history_api.py."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import management
from backend.app.main import app, require_session

pytestmark = pytest.mark.reports_db

_MANAGER = {
    "name": "Diego Herrera", "login": "dherrera",
    "email": "diego.herrera@schwaben.com.br", "employee_id": "450", "filiale": None,
}
_NON_MANAGER = {
    "name": "Outro Usuário", "login": "outro.usuario",
    "email": "outro@schwaben.com.br", "employee_id": "999", "filiale": None,
}


def _client_for(user: dict, monkeypatch) -> TestClient:
    monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", {"dherrera"})
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _generate_payload(report_number: str, project_name: str, month_label: str, groups: list[dict]) -> dict:
    return {
        "packages": [
            {
                "header": {
                    "project_code": report_number, "project_name": project_name,
                    "location_date": "São Paulo, 01/01/2026", "month_label": month_label,
                    "signer1_name": "Fulano", "signer1_company": "Schwaben Engineering",
                    "signer2_name": "Beltrano", "signer2_company": "Cliente Teste",
                },
                "groups": groups,
            }
        ],
        "formats": ["xlsx"],
        "include_performance": False,
    }


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(require_session, None)


def test_nao_gerente_recebe_403(reports_db_engine, monkeypatch):
    client = _client_for(_NON_MANAGER, monkeypatch)
    with client:
        response = client.get("/analytics/summary")
    assert response.status_code == 403


def test_summary_agrega_horas_da_versao_atual_e_ignora_versao_antiga(reports_db_engine, monkeypatch):
    manager_client = _client_for(_MANAGER, monkeypatch)
    with manager_client:
        # relatório A, v1: 8h em ENG.
        gen_a1 = manager_client.post(
            "/generate",
            json=_generate_payload(
                "SE.ANALYTICS.001", "Projeto Alpha", "Julho/2026",
                [{"name": "ENG", "performance": 100.0, "activities": [{"description": "Ativ 1", "hours": 8.0}]}],
            ),
        )
        assert gen_a1.status_code == 200

        # relatório A, v2 (mesmo report_number/competência): 10h em ENG — v1
        # não pode mais contar depois que v2 existe.
        gen_a2 = manager_client.post(
            "/generate",
            json=_generate_payload(
                "SE.ANALYTICS.001", "Projeto Alpha", "Julho/2026",
                [{"name": "ENG", "performance": 100.0, "activities": [{"description": "Ativ 1", "hours": 10.0}]}],
            ),
        )
        assert gen_a2.status_code == 200
        assert gen_a2.headers["X-Report-Id"] == gen_a1.headers["X-Report-Id"]

        # relatório B, projeto/competência diferentes: 5h QA + 3h ENG.
        gen_b = manager_client.post(
            "/generate",
            json=_generate_payload(
                "SE.ANALYTICS.002", "Projeto Beta", "Agosto/2026",
                [
                    {"name": "QA", "performance": 100.0, "activities": [{"description": "Testes", "hours": 5.0}]},
                    {"name": "ENG", "performance": 100.0, "activities": [{"description": "Ativ 2", "hours": 3.0}]},
                ],
            ),
        )
        assert gen_b.status_code == 200

        summary = manager_client.get("/analytics/summary")
    assert summary.status_code == 200
    body = summary.json()

    assert body["totals"]["reports"] >= 2
    assert body["totals"]["versions"] >= 3
    assert body["totals"]["artifacts"] >= 3

    hours_by_group = {row["group_name"]: row["hours"] for row in body["hours_by_group"]}
    # ENG: 10 (v2 de A) + 3 (B) = 13 — os 8h da v1 de A NÃO entram.
    assert hours_by_group["ENG"] == pytest.approx(13.0)
    assert hours_by_group["QA"] == pytest.approx(5.0)

    hours_by_project = {row["project_name"]: row["hours"] for row in body["hours_by_project"]}
    assert hours_by_project["Projeto Alpha"] == pytest.approx(10.0)
    assert hours_by_project["Projeto Beta"] == pytest.approx(8.0)

    hours_by_competence = {row["competence_label"]: row["hours"] for row in body["hours_by_competence"]}
    assert hours_by_competence["Julho/2026"] == pytest.approx(10.0)
    assert hours_by_competence["Agosto/2026"] == pytest.approx(8.0)

    gen_stats = body["generation"]
    assert gen_stats["total"] >= 3
    assert gen_stats["failed"] == 0
    assert gen_stats["failure_rate"] == pytest.approx(0.0)
    assert gen_stats["avg_duration_ms"] is not None
    formats = {row["format"] for row in gen_stats["by_format"]}
    assert "xlsx" in formats

    creators = {row["login"]: row["reports"] for row in body["top_creators"]}
    assert creators["dherrera"] >= 2

    assert sum(row["count"] for row in body["reports_over_time"]) >= 2


def test_summary_sem_dado_nenhum_devolve_listas_vazias_sem_erro(reports_db_engine, monkeypatch):
    client = _client_for(_MANAGER, monkeypatch)
    with client:
        response = client.get("/analytics/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"] == {"reports": 0, "versions": 0, "artifacts": 0}
    assert body["hours_by_competence"] == []
    assert body["hours_by_group"] == []
    assert body["hours_by_project"] == []
    assert body["generation"]["total"] == 0
    assert body["generation"]["failure_rate"] is None
    assert body["generation"]["avg_duration_ms"] is None
    assert body["reports_over_time"] == []
    assert body["top_creators"] == []
