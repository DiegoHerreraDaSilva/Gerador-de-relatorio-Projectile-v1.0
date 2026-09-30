"""Horas pessoais só por `employee_id` (FK `tjob.pEmployee`). O antigo fallback
`capEmployee LIKE '%nome%'` casava homônimos/nomes parciais e mostrava as horas
de OUTRA pessoa; sem vínculo confiável a resposta é um erro claro (409)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import projectile_db
from backend.app.api.dependencies import require_session
from backend.app.main import app


class _Cursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return []


class _Conn:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _Cursor(self.log)

    def close(self):
        pass


@pytest.fixture
def sql_log(monkeypatch):
    log: list = []
    monkeypatch.setattr(projectile_db, "open_connection", lambda: _Conn(log), raising=False)
    monkeypatch.setattr(projectile_db, "_get_connection", lambda: _Conn(log))
    return log


@pytest.mark.parametrize("fn", ["fetch_employee_hours", "fetch_my_hours", "fetch_daily_hours_totals"])
@pytest.mark.parametrize("missing", [None, "", "   "])
def test_sem_employee_id_nao_consulta_e_levanta_erro_claro(sql_log, fn, missing):
    with pytest.raises(projectile_db.EmployeeNotLinkedError):
        getattr(projectile_db, fn)("2026-08-01", "2026-08-31", employee_id=missing)
    assert sql_log == []


@pytest.mark.parametrize("fn", ["fetch_employee_hours", "fetch_my_hours", "fetch_daily_hours_totals"])
def test_consulta_usa_a_chave_exata_e_nunca_like(sql_log, fn):
    getattr(projectile_db, fn)("2026-08-01", "2026-08-31", employee_id="42")
    sql, params = sql_log[0]
    assert "tj.pEmployee = %s" in sql
    assert "capEmployee LIKE" not in sql
    assert params[0] == "42"


def test_funcoes_nao_aceitam_mais_nome():
    with pytest.raises(TypeError):
        projectile_db.fetch_employee_hours("2026-08-01", "2026-08-31", employee_name="Ana")  # type: ignore[call-arg]


@pytest.fixture
def client_sem_vinculo(monkeypatch):
    user = {"name": "Ana Souza", "login": "ana", "email": "a@x", "employee_id": None, "filiale": None}
    app.dependency_overrides[require_session] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.pop(require_session, None)


def test_my_hours_sem_vinculo_responde_409(client_sem_vinculo):
    response = client_sem_vinculo.get("/my-hours")
    assert response.status_code == 409
    assert "vinculado" in response.json()["detail"]


def test_parse_db_sem_vinculo_responde_409(client_sem_vinculo):
    response = client_sem_vinculo.post("/parse-db", json={"month_label": "Agosto/2026", "mode": "single"})
    assert response.status_code == 409
    assert "vinculado" in response.json()["detail"]
