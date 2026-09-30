"""Visão do time: o cálculo é puro (dicts no lugar do Projectile) e usa o mesmo calendário do Dashboard pessoal.
Nenhum teste toca o Projectile: as duas consultas são substituídas."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import projectile_db, team_overview
from backend.app.api.dependencies import require_session
from backend.app.core import authz
from backend.app.holidays import business_days_between
from backend.app.main import app

START, END = date(2026, 9, 1), date(2026, 9, 30)
TODAY = date(2026, 9, 30)
CLOSED = [d for d in business_days_between(START, END) if d < TODAY]  # dias úteis encerrados de setembro/2026


def rows(employee_id, days, hours=8.0):
    return [{"employee_id": employee_id, "data": d, "horas": hours} for d in days]


def employee(employee_id, name, cost_center="CAD"):
    return {"employee_id": employee_id, "name": name, "cost_center": cost_center, "filiale": None, "login": name.lower()}


def summarize(employees, daily, today=TODAY):
    return team_overview.summarize(employees, daily, START, END, today)


# --- cálculo ---------------------------------------------------------------------------------------------------


def test_quem_apontou_todo_dia_util_encerrado_nao_tem_lacuna():
    [person] = summarize([employee("1", "Ana")], rows("1", CLOSED))
    assert person["gap_count"] == 0 and person["gap_days"] == []
    assert person["days_worked"] == len(CLOSED) and person["closed_business_days"] == len(CLOSED)
    assert person["hours"] == 8.0 * len(CLOSED) and person["avg_hours_per_day"] == 8.0


def test_dias_uteis_sem_apontamento_sao_a_lacuna_do_mais_recente_pro_mais_antigo():
    skipped = {CLOSED[2], CLOSED[10]}
    worked = [d for d in CLOSED if d not in skipped]
    [person] = summarize([employee("1", "Ana")], rows("1", worked))
    assert person["gap_days"] == sorted((d.isoformat() for d in skipped), reverse=True)
    assert person["gap_count"] == 2


def test_fim_de_semana_trabalhado_conta_nas_horas_mas_nao_vira_dia_util_nem_entra_na_media():
    saturday = date(2026, 9, 5)
    assert saturday.weekday() == 5
    [person] = summarize([employee("1", "Ana")], rows("1", [*CLOSED, saturday]))
    assert person["hours"] == 8.0 * (len(CLOSED) + 1)
    assert person["days_worked"] == len(CLOSED) + 1
    assert person["closed_business_days"] == len(CLOSED) and person["gap_count"] == 0
    assert person["avg_hours_per_day"] == 8.0  # o sábado não puxa a média dos dias úteis


def test_o_dia_em_curso_nunca_e_lacuna():
    [person] = summarize([employee("1", "Ana")], rows("1", [d for d in CLOSED if d != CLOSED[-1]]), today=CLOSED[-1])
    assert CLOSED[-1].isoformat() not in person["gap_days"]  # hoje ainda pode ser apontado


def test_dia_pesado_acima_de_dez_horas():
    days = CLOSED[:3]
    daily = rows("1", days[:2], 11.0) + rows("1", days[2:], 10.0)
    [person] = summarize([employee("1", "Ana")], daily)
    assert person["overload_days"] == 2  # 11 h conta; 10 h exatas não


def test_feriado_nacional_nao_e_dia_util():
    holiday = date(2026, 9, 7)  # Independência
    assert holiday not in CLOSED
    [person] = summarize([employee("1", "Ana")], rows("1", CLOSED))
    assert holiday.isoformat() not in person["gap_days"]


def test_so_entra_quem_apontou_nos_dois_meses_anteriores_ou_no_periodo():
    long_ago = START - timedelta(days=200)
    people = summarize(
        [employee("1", "Ana"), employee("2", "Beto"), employee("3", "Carla"), employee("4", "Dani")],
        rows("1", CLOSED) + rows("2", [long_ago]) + rows("3", [START - timedelta(days=40)]),
    )
    # Beto (só há meses) e Dani (nunca) saíram do time; Carla apontou há 40 dias e está com o mês todo em aberto
    assert {p["name"] for p in people} == {"Ana", "Carla"}
    carla = next(p for p in people if p["name"] == "Carla")
    assert carla["gap_count"] == len(CLOSED) and carla["hours"] == 0 and carla["avg_hours_per_day"] is None


def test_atencao_primeiro_mais_lacunas_depois_menos_horas_depois_nome():
    daily = rows("1", CLOSED) + rows("2", CLOSED[5:]) + rows("3", CLOSED[5:], 4.0)
    people = summarize([employee("1", "Ana"), employee("2", "Beto"), employee("3", "Carla")], daily)
    assert [p["name"] for p in people] == ["Carla", "Beto", "Ana"]  # Carla e Beto têm as mesmas lacunas; Carla, menos horas


def test_horas_zeradas_ou_negativas_nao_contam_como_apontamento():
    [person] = summarize([employee("1", "Ana")], rows("1", CLOSED[:-1]) + rows("1", [CLOSED[-1]], 0.0))
    assert person["gap_days"] == [CLOSED[-1].isoformat()]


def test_data_como_texto_tambem_funciona():
    daily = [{"employee_id": "1", "data": d.isoformat(), "horas": "8.0"} for d in CLOSED]
    [person] = summarize([employee("1", "Ana")], daily)
    assert person["gap_count"] == 0 and person["hours"] == 8.0 * len(CLOSED)


def test_limites_do_mes():
    assert team_overview.month_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert team_overview.month_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    with pytest.raises(ValueError):
        team_overview.month_bounds("2026-13")


# --- rota e autorização -----------------------------------------------------------------------------------------


@pytest.fixture
def team(monkeypatch):
    team_overview._cache.clear()
    calls = {"employees": 0, "totals": 0}

    def employees(start, end):
        calls["employees"] += 1
        return [employee("1", "Ana"), employee("2", "Beto")]

    def totals(start, end):
        calls["totals"] += 1
        return rows("1", CLOSED) + rows("2", CLOSED[4:])

    monkeypatch.setattr(projectile_db, "fetch_engineering_employees", employees)
    monkeypatch.setattr(projectile_db, "fetch_engineering_daily_totals", totals)
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(authz, "COORDINATOR_LOGINS", {"coord"})

    # "hoje" fixo em todo módulo que olha o relógio nesta rota (rota e janela de período de quem não é gerente)
    class FakeDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr("backend.app.api.routers.my_hours.date", FakeDate)
    monkeypatch.setattr("backend.app.api.period_access.date", FakeDate)
    users = {
        "gerente": {"name": "G", "login": "gerente", "email": "g@x", "employee_id": "9"},
        "coord": {"name": "Co", "login": "coord", "email": "c@x", "employee_id": "8"},
        "colab": {"name": "Cl", "login": "colab", "email": "l@x", "employee_id": "7"},
    }

    def as_user(login):
        app.dependency_overrides[require_session] = lambda: users[login]
        return TestClient(app)

    as_user.calls = calls
    yield as_user
    app.dependency_overrides.pop(require_session, None)
    team_overview._cache.clear()


def test_coordenador_e_gerente_veem_o_time_do_mes_atual(team):
    for login in ("coord", "gerente"):
        response = team(login).get("/my-hours/team")
        assert response.status_code == 200, login
        body = response.json()
        assert body["month"] == "2026-09" and [p["name"] for p in body["people"]] == ["Beto", "Ana"]
        assert body["totals"] == {"people": 2, "with_gaps": 1, "hours": body["totals"]["hours"], "overloaded": 0}


def test_colaborador_nao_ve_o_time(team):
    assert team("colab").get("/my-hours/team").status_code == 403


def test_coordenador_so_ve_meses_da_janela_e_gerente_ve_qualquer_um(team):
    assert team("coord").get("/my-hours/team", params={"month": "2024-01"}).status_code == 403
    assert team("gerente").get("/my-hours/team", params={"month": "2024-01"}).status_code == 200


def test_mes_invalido_ou_futuro(team):
    for bad in ("2026-13", "agosto", "2026", "2026-10"):
        assert team("gerente").get("/my-hours/team", params={"month": bad}).status_code == 400, bad


def test_segunda_chamada_no_mesmo_mes_vem_do_cache(team):
    team("gerente").get("/my-hours/team")
    team("coord").get("/my-hours/team")
    assert team.calls == {"employees": 1, "totals": 1}
    team("gerente").get("/my-hours/team", params={"month": "2026-08"})
    assert team.calls["totals"] == 2  # outro mês, outra consulta
