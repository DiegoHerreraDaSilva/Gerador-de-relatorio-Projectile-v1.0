"""Teste de integração fim a fim: POST /generate persiste em reports_db —
precisa do reports-mysql real (ver conftest.py:reports_db_engine)."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db.reports_schema import report_artifacts, report_generation, reports
from backend.app.main import app, require_session

pytestmark = pytest.mark.reports_db


def _fake_user() -> dict:
    return {
        "name": "Diego Herrera", "login": "dherrera",
        "email": "diego.herrera@schwaben.com.br", "employee_id": "450", "filiale": None,
    }


@pytest.fixture
def client(reports_db_engine):
    # `reports_db_engine` precisa estar no grafo de dependência ANTES do
    # `TestClient(app)` disparar o evento de startup (que roda
    # reconcile_orphaned_generations) — senão o startup rodaria contra o
    # reports_db de verdade em vez do schema de teste.
    app.dependency_overrides[require_session] = _fake_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(require_session, None)


def _generate_payload() -> dict:
    return {
        "packages": [
            {
                "header": {
                    "project_code": "SE.INTEGRACAO.001",
                    "project_name": "Projeto Integração",
                    "location_date": "São Paulo, 01/01/2026",
                    "month_label": "Julho/2026",
                    "signer1_name": "Fulano",
                    "signer1_company": "Schwaben Engineering",
                    "signer2_name": "Beltrano",
                    "signer2_company": "Cliente Teste",
                },
                "groups": [
                    {
                        "name": "Grupo A",
                        "performance": 100.0,
                        "activities": [{"description": "Atividade 1", "hours": 8.0}],
                    }
                ],
            }
        ],
        "formats": ["xlsx"],
        "include_performance": False,
    }


def test_generate_persiste_report_version_generation_e_artifact(client, reports_db_engine):
    response = client.post("/generate", json=_generate_payload())
    assert response.status_code == 200

    report_id = response.headers.get("X-Report-Id")
    assert report_id, "resposta deveria ter o header X-Report-Id (persistência funcionou)"

    with reports_db_engine.begin() as conn:
        report_row = conn.execute(select(reports).where(reports.c.id == report_id)).first()
        generation_row = conn.execute(
            select(report_generation).where(report_generation.c.report_id == report_id)
        ).first()
        artifact_row = conn.execute(
            select(report_artifacts).where(report_artifacts.c.generation_id == generation_row.id)
        ).first()

    assert report_row is not None
    assert report_row.report_number == "SE.INTEGRACAO.001"
    assert generation_row.status == "success"
    assert artifact_row is not None
    assert os.path.exists(artifact_row.storage_path)
    assert artifact_row.sha256


def test_generate_gera_versoes_sucessivas_pro_mesmo_relatorio(client, reports_db_engine):
    first = client.post("/generate", json=_generate_payload())
    second = client.post("/generate", json=_generate_payload())

    assert first.headers["X-Report-Id"] == second.headers["X-Report-Id"]
    assert int(second.headers["X-Report-Version-Number"]) == int(first.headers["X-Report-Version-Number"]) + 1
