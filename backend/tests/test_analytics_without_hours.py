"""Chat analítico: "quem NÃO tem horas apontadas". Quem não apontou nada não tem
linha na base de horas, então a resposta vem da lista de engenharia ativa (a
do "Meu time") menos quem tem hora — não da consulta cruzada. Caso real de
2026-10-07: o Jev ignorava o "não" e listava quem TEM horas; "zero horas" virava
o filtro "horas <= 0" e respondia "não encontrei dados"."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app import team_overview
from backend.app.analytics import service, signals
from backend.tests.test_analytics_chat import _ask, _cls, chat  # noqa: F401 — fixture reaproveitada


def _person(employee_id: str, name: str, hours: float, cost_center: str | None = "CAD") -> dict:
    return {"employee_id": employee_id, "name": name, "hours": hours, "cost_center": cost_center}


@pytest.fixture
def team(monkeypatch):
    """`team.months[AAAA-MM]` = pessoas ativas daquele mês; `team.asked` = meses consultados."""
    state = SimpleNamespace(months={}, asked=[])

    def fake_overview(month, today=None):
        state.asked.append(month)
        return {"month": month, "people": state.months.get(month, [])}

    monkeypatch.setattr(team_overview, "team_overview", fake_overview)
    return state


@pytest.mark.parametrize(
    "message",
    [
        "quais colaboradores não tem horas apontadas nesse Mês",
        "quem tem zero horas apontadas nesse mes",
        "quem não apontou horas em agosto?",
        "colaboradores sem apontamento no mês passado",
        "quem está sem horas lançadas",
        "ninguém apontou nada em setembro",
    ],
)
def test_reconhece_pergunta_de_quem_nao_apontou(message):
    assert signals.asks_without_hours(message)


@pytest.mark.parametrize(
    "message",
    [
        "quantas horas tivemos em setembro?",
        "horas por colaborador em outubro",
        "quanto foi não faturável em agosto",
        "projetos sem horas faturáveis",
        "clientes sem horas no mês",
        "quanto o Lucca apontou em 10 horas",
    ],
)
def test_nao_confunde_com_outras_perguntas(message):
    assert not signals.asks_without_hours(message)


def test_lista_quem_esta_zerado_no_mes_atual_sem_claude(chat, team):
    team.months["2026-09"] = [_person("1", "Ana", 40), _person("2", "Carla", 0, "CAE"), _person("3", "Beto", 0)]
    # o Jev errava de propósito: escolhia o atalho que lista quem TEM horas
    chat["cls"] = _cls("simple_data", "total_hours")

    body = _ask("quais colaboradores não tem horas apontadas nesse Mês").json()

    assert body["route"] == "simple_data"
    assert body["metadata"]["claude_calls"] == 0
    assert body["metadata"]["source"] == "projectile"
    assert body["metadata"]["period_label"] == "setembro/2026"
    assert team.asked == ["2026-09"]
    assert "2 de 3 colaboradores" in body["reply"] and "Beto, Carla" in body["reply"]
    assert "Ana" not in body["reply"]
    assert "considerei o mês atual" in body["reply"] and "ainda não terminou" in body["reply"]
    assert body["visualizations"] == []
    [table] = body["tables"]
    assert table["columns"] == ["Colaborador", "Centro de custo"]
    assert table["rows"] == [["Beto", "CAD"], ["Carla", "CAE"]]


def test_mes_citado_na_pergunta_vale(chat, team):
    team.months["2026-08"] = [_person("1", "Ana", 0), _person("2", "Beto", 12)]
    chat["cls"] = _cls("simple_data", "total_hours", "2026-08")

    body = _ask("quem tem zero horas apontadas em agosto").json()

    assert team.asked == ["2026-08"]
    assert body["metadata"]["period_label"] == "agosto/2026"
    assert "1 de 2 colaboradores" in body["reply"] and "Ana" in body["reply"]
    assert "ainda não terminou" not in body["reply"]


def test_todo_mundo_apontou(chat, team):
    team.months["2026-09"] = [_person("1", "Ana", 8), _person("2", "Beto", 3)]
    chat["cls"] = _cls("simple_data", "total_hours")

    body = _ask("quem não tem horas apontadas nesse mês").json()

    assert "Nenhum dos 2 colaboradores" in body["reply"]
    assert body["tables"] == []


def test_varios_meses_so_quem_ficou_zerado_em_todos(chat, team):
    team.months["2026-08"] = [_person("1", "Ana", 0), _person("2", "Beto", 0), _person("3", "Caio", 5)]
    team.months["2026-09"] = [_person("1", "Ana", 0), _person("2", "Beto", 9), _person("3", "Caio", 0)]
    c = SimpleNamespace(month="2026-08", month_end="2026-09", relative=None)

    answer = service._without_hours_answer(c, service.date(2026, 9, 24), SimpleNamespace(analytics_chat_max_months=12))

    assert team.asked == ["2026-08", "2026-09"]
    assert [row[0] for row in answer["tables"][0]["rows"]] == ["Ana"]
    assert "1 de 3 colaboradores" in answer["reply"]


def test_pergunta_de_projeto_sem_horas_continua_na_consulta_cruzada(chat, team):
    chat["cls"] = _cls("simple_data", "total_hours", "2026-09")

    body = _ask("quantas horas tivemos em setembro?").json()

    assert team.asked == []
    assert body["reply"] == "Foram apontadas 13 h em setembro/2026."
