"""Trava o comportamento de `backend/app/projectile_db.group_hours` — função
pura (sem I/O de banco), então testada diretamente contra listas de dicts no
formato que `fetch_engineering_hours`/`fetch_employee_hours` devolvem
(chaves: data, observacao, horas, pacote, funcionario)."""
from __future__ import annotations

import pytest

from backend.app.projectile_db import group_hours


def test_group_hours_normal_rows():
    rows = [
        {"data": "2026-07-01", "observacao": "ENG - Atividade normal", "horas": 3.0, "pacote": "Proj A", "funcionario": "Fulano"},
        {"data": "2026-07-02", "observacao": "QA - Testes", "horas": 1.5, "pacote": "Proj A", "funcionario": "Fulano"},
    ]

    packages, issues = group_hours(rows, split_by_package=False)

    assert issues == []
    assert len(packages) == 1
    groups_by_name = {g.name: g for g in packages[0].groups}
    assert set(groups_by_name) == {"ENG", "QA"}
    assert groups_by_name["ENG"].activities[0].hours == pytest.approx(3.0, abs=1e-3)
    assert groups_by_name["QA"].activities[0].hours == pytest.approx(1.5, abs=1e-3)


def test_group_hours_decodes_html_entities_in_observacao():
    rows = [
        {"observacao": "relat&#243;rio - Ativ", "horas": 2.0, "pacote": "Proj A"},
    ]

    packages, issues = group_hours(rows, split_by_package=False)

    assert issues == []
    group = packages[0].groups[0]
    assert group.name == "relatório"  # html.unescape("relat&#243;rio") == "relatório"
    assert group.activities[0].description == "Ativ"


def test_group_hours_row_without_separator_groups_under_geral():
    """Diferente de `parser.parse_projectile_export` (onde falta de "-"/"_"
    é um RowIssue), aqui o dado real do Projectile costuma ter observações
    sem separador (ex: códigos como "2542A012") — decisão deliberada do
    código: agrupa como "Geral" em vez de descartar ou marcar aviso."""
    rows = [
        {"observacao": "2542A012", "horas": 4.0, "pacote": "Proj A"},
    ]

    packages, issues = group_hours(rows, split_by_package=False)

    assert issues == []
    group = packages[0].groups[0]
    assert group.name == "Geral"
    assert group.activities[0].description == "2542A012"
    assert group.activities[0].hours == pytest.approx(4.0, abs=1e-3)


def test_group_hours_duplicate_descriptions_case_insensitive_sum_instead_of_duplicating():
    rows = [
        {"observacao": "ENG - Atividade um", "horas": 2.0, "pacote": "Proj A"},
        {"observacao": "ENG - atividade UM", "horas": 1.5, "pacote": "Proj A"},
        {"observacao": "ENG - Atividade dois", "horas": 1.0, "pacote": "Proj A"},
    ]

    packages, issues = group_hours(rows, split_by_package=False)

    assert issues == []
    group = packages[0].groups[0]
    assert group.name == "ENG"
    assert len(group.activities) == 2  # "Atividade um"/"atividade UM" somaram, não duplicaram
    activities_by_desc = {a.description.casefold(): a for a in group.activities}
    assert activities_by_desc["atividade um"].hours == pytest.approx(3.5, abs=1e-3)
    assert activities_by_desc["atividade dois"].hours == pytest.approx(1.0, abs=1e-3)


def test_group_hours_zero_or_negative_hours_rows_are_dropped():
    rows = [
        {"observacao": "ENG - Atividade valida", "horas": 2.0, "pacote": "Proj A"},
        {"observacao": "ENG - Atividade zerada", "horas": 0.0, "pacote": "Proj A"},
    ]

    packages, issues = group_hours(rows, split_by_package=False)

    group = packages[0].groups[0]
    assert len(group.activities) == 1
    assert group.activities[0].description == "Atividade valida"
