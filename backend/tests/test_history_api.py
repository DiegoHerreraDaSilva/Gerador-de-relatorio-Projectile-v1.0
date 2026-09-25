"""Testes de integração dos endpoints de histórico (`GET /reports/*`) e
download de artifact — precisa do reports-mysql real (ver
conftest.py:reports_db_engine)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import management
from backend.app.main import app, require_session

pytestmark = pytest.mark.reports_db

_OWNER = {
    "name": "Diego Herrera", "login": "dherrera",
    "email": "diego.herrera@schwaben.com.br", "employee_id": "450", "filiale": None,
}
_OTHER_NON_MANAGER = {
    "name": "Outro Usuário", "login": "outro.usuario",
    "email": "outro@schwaben.com.br", "employee_id": "999", "filiale": None,
}


def _client_for(user: dict, monkeypatch) -> TestClient:
    # allowlist fixa e determinística pro teste — não depende do
    # MANAGEMENT_PANEL_LOGINS real do .env.
    monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", {"dherrera"})
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _generate_payload(
    report_number: str, project_name: str = "Projeto Histórico", month_label: str = "Julho/2026",
) -> dict:
    return {
        "packages": [
            {
                "header": {
                    "project_code": report_number, "project_name": project_name,
                    "location_date": "São Paulo, 01/01/2026", "month_label": month_label,
                    "signer1_name": "Fulano", "signer1_company": "Schwaben Engineering",
                    "signer2_name": "Beltrano", "signer2_company": "Cliente Teste",
                },
                "groups": [
                    {"name": "Grupo A", "performance": 100.0, "activities": [{"description": "Atividade 1", "hours": 8.0}]}
                ],
            }
        ],
        "formats": ["xlsx"],
        "include_performance": False,
    }


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(require_session, None)


def test_fluxo_completo_de_historico(reports_db_engine, monkeypatch):
    client = _client_for(_OWNER, monkeypatch)
    with client:
        gen_response = client.post("/generate", json=_generate_payload("SE.HIST.001"))
        assert gen_response.status_code == 200
        report_id = gen_response.headers["X-Report-Id"]

        list_response = client.get("/reports")
        assert list_response.status_code == 200
        assert any(r["id"] == report_id for r in list_response.json()["items"])

        detail = client.get(f"/reports/{report_id}")
        assert detail.status_code == 200
        assert detail.json()["report_number"] == "SE.HIST.001"
        assert detail.json()["current_version_number"] == 1

        versions = client.get(f"/reports/{report_id}/versions")
        assert versions.status_code == 200
        assert versions.json()["total"] == 1
        version_id = versions.json()["items"][0]["id"]

        version_detail = client.get(f"/reports/{report_id}/versions/{version_id}")
        assert version_detail.status_code == 200
        assert version_detail.json()["snapshot"]["data"]["header"]["project_code"] == "SE.HIST.001"

        generations = client.get(f"/reports/{report_id}/generations")
        assert generations.status_code == 200
        assert generations.json()["items"][0]["status"] == "success"

        artifacts = client.get(f"/reports/{report_id}/artifacts")
        assert artifacts.status_code == 200
        artifact_id = artifacts.json()["items"][0]["id"]

        audit_events = client.get(f"/reports/{report_id}/audit").json()["items"]
        actions = {e["action"] for e in audit_events}
        assert {"report_created", "report_version_created", "report_generated"} <= actions

        download = client.get(f"/artifacts/{artifact_id}/download")
        assert download.status_code == 200
        assert len(download.content) > 0

        audit_events_after = client.get(f"/reports/{report_id}/audit").json()["items"]
        assert any(e["action"] == "artifact_downloaded" for e in audit_events_after)


def test_versoes_sucessivas_aparecem_no_historico(reports_db_engine, monkeypatch):
    client = _client_for(_OWNER, monkeypatch)
    with client:
        first = client.post("/generate", json=_generate_payload("SE.HIST.VERSOES.001"))
        second = client.post("/generate", json=_generate_payload("SE.HIST.VERSOES.001"))
        report_id = first.headers["X-Report-Id"]
        assert second.headers["X-Report-Id"] == report_id

        versions = client.get(f"/reports/{report_id}/versions").json()
        assert versions["total"] == 2
        version_numbers = sorted(v["version_number"] for v in versions["items"])
        assert version_numbers == [1, 2]


def test_nao_gerente_nao_ve_relatorio_de_outra_pessoa(reports_db_engine, monkeypatch):
    owner_client = _client_for(_OWNER, monkeypatch)
    with owner_client:
        gen_response = owner_client.post("/generate", json=_generate_payload("SE.HIST.PRIVADO.001"))
    report_id = gen_response.headers["X-Report-Id"]
    app.dependency_overrides.pop(require_session, None)

    other_client = _client_for(_OTHER_NON_MANAGER, monkeypatch)
    with other_client:
        response = other_client.get(f"/reports/{report_id}")
        assert response.status_code == 403

        list_response = other_client.get("/reports")
        assert list_response.status_code == 200
        assert not any(r["id"] == report_id for r in list_response.json()["items"])


def test_gerente_ve_relatorio_de_outra_pessoa(reports_db_engine, monkeypatch):
    owner_client = _client_for(_OWNER, monkeypatch)
    with owner_client:
        gen_response = owner_client.post("/generate", json=_generate_payload("SE.HIST.GERENTE.001"))
    report_id = gen_response.headers["X-Report-Id"]
    app.dependency_overrides.pop(require_session, None)

    manager = {**_OTHER_NON_MANAGER, "login": "dherrera"}
    manager_client = _client_for(manager, monkeypatch)
    with manager_client:
        response = manager_client.get(f"/reports/{report_id}")
        assert response.status_code == 200


def test_busca_geral_por_numero_projeto_competencia_e_criado_por(reports_db_engine, monkeypatch):
    client = _client_for(_OWNER, monkeypatch)
    with client:
        client.post("/generate", json=_generate_payload("SE.BUSCA.001", "Mercedes Accelo", "Março/2026"))
        client.post("/generate", json=_generate_payload("SE.BUSCA.002", "Lauer Fundição", "Abril/2026"))

        def numbers(q: str) -> list[str]:
            response = client.get("/reports", params={"q": q, "page_size": 100})
            assert response.status_code == 200
            return sorted(r["report_number"] for r in response.json()["items"] if r["report_number"].startswith("SE.BUSCA"))

        assert numbers("se.busca.002") == ["SE.BUSCA.002"]          # número, sem diferenciar maiúscula
        assert numbers("accelo") == ["SE.BUSCA.001"]               # projeto
        assert numbers("Abril/2026") == ["SE.BUSCA.002"]           # competência
        assert numbers("Diego Herrera") == ["SE.BUSCA.001", "SE.BUSCA.002"]  # criado por (nome)
        assert numbers("dherrera") == ["SE.BUSCA.001", "SE.BUSCA.002"]       # criado por (login)
        assert numbers("março mercedes") == ["SE.BUSCA.001"]       # cada palavra em alguma coluna
        assert numbers("março lauer") == []
        assert numbers("100%") == []                               # % é literal, não curinga


def test_busca_de_nao_gerente_fica_nos_proprios_relatorios(reports_db_engine, monkeypatch):
    owner_client = _client_for(_OWNER, monkeypatch)
    with owner_client:
        owner_client.post("/generate", json=_generate_payload("SE.BUSCA.PRIVADO.001"))
    app.dependency_overrides.pop(require_session, None)

    other_client = _client_for(_OTHER_NON_MANAGER, monkeypatch)
    with other_client:
        response = other_client.get("/reports", params={"q": "SE.BUSCA.PRIVADO.001"})
        assert response.status_code == 200
        assert response.json()["items"] == []
