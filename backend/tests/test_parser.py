"""Trava o comportamento de `backend/app/parser.parse_projectile_export`."""
from __future__ import annotations

import os

import pytest
from openpyxl import Workbook

from backend.app.parser import parse_projectile_export

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE_XLSX = os.path.join(REPO_ROOT, "backend", "templates", "exemplo_projectile.xlsx")

HEADER = ["Dados", "Horário", "Hs", "Observação", "Projeto", "Pacote de Trabalho"]


def _build_export(rows: list[list], *, header_row_offset: int = 0) -> "Workbook":
    """Monta um workbook sintético com o layout de colunas que
    `parser._find_header_row`/`parse_projectile_export` esperam: linha de
    cabeçalho contendo ["Dados", "Horário", "Hs", ...] seguida das linhas de
    apontamento. `header_row_offset` insere linhas de lixo antes do
    cabeçalho, para exercitar a busca de `_find_header_row` (que não assume
    que o cabeçalho está na linha 1)."""
    wb = Workbook()
    ws = wb.active
    for _ in range(header_row_offset):
        ws.append(["lixo antes do cabeçalho"])
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    return wb


@pytest.mark.skipif(
    not os.path.exists(FIXTURE_XLSX),
    reason=(
        "backend/templates/exemplo_projectile.xlsx não existe neste checkout "
        "(está no .gitignore, é um fixture de teste manual local — ver "
        "CLAUDE.md seção Testing). Sem ele, este teste específico é pulado; "
        "os demais testes deste arquivo usam fixtures sintéticas equivalentes."
    ),
)
def test_parse_projectile_export_real_fixture_returns_single_package_in_single_mode():
    packages, issues = parse_projectile_export(FIXTURE_XLSX, split_by_package=False)

    assert len(packages) == 1


def test_parse_projectile_export_well_formed_rows(tmp_path):
    wb = _build_export(
        [
            ["01/07/2026", "08:00", 2.5, "ENG - Atividade um", "Projeto X", ""],
            ["02/07/2026", "08:00", 1.5, "ENG - Atividade um", "Projeto X", ""],
            ["03/07/2026", "08:00", 3.0, "QA - Testes finais", "Projeto X", ""],
        ],
        header_row_offset=1,  # confirma que _find_header_row não assume linha 1
    )
    path = str(tmp_path / "well_formed.xlsx")
    wb.save(path)

    packages, issues = parse_projectile_export(path, split_by_package=False)

    assert issues == []
    assert len(packages) == 1
    pkg = packages[0]
    assert pkg.project_name == "Projeto X"
    groups_by_name = {g.name: g for g in pkg.groups}
    assert set(groups_by_name) == {"ENG", "QA"}
    # linhas 1 e 2 têm mesma Observação (case-insensitive) -> soma em vez de duplicar
    eng_activities = groups_by_name["ENG"].activities
    assert len(eng_activities) == 1
    assert eng_activities[0].description == "Atividade um"
    assert eng_activities[0].hours == pytest.approx(4.0, abs=1e-3)


def test_parse_projectile_export_row_without_separator_raises_issue_not_crash(tmp_path):
    wb = _build_export(
        [
            ["01/07/2026", "08:00", 2.0, "ENG - Atividade normal", "Projeto Y", ""],
            ["02/07/2026", "08:00", 3.0, "SemSeparadorNenhum", "Projeto Y", ""],
        ]
    )
    path = str(tmp_path / "sem_separador.xlsx")
    wb.save(path)

    packages, issues = parse_projectile_export(path, split_by_package=False)

    # não deve crashar; a linha malformada vira um RowIssue, não uma exceção
    assert len(issues) == 1
    assert issues[0].reason == "sem_separador"
    assert issues[0].row == 3  # cabeçalho na linha 1 (sem offset), dado na linha 3
    # a linha válida continua sendo processada normalmente
    assert len(packages) == 1
    assert packages[0].groups[0].activities[0].hours == pytest.approx(2.0, abs=1e-3)


def test_parse_projectile_export_decimal_comma_in_hs(tmp_path):
    wb = _build_export(
        [
            ["01/07/2026", "08:00", "2,5", "ENG - Atividade com vírgula", "Projeto Z", ""],
        ]
    )
    path = str(tmp_path / "virgula.xlsx")
    wb.save(path)

    packages, issues = parse_projectile_export(path, split_by_package=False)

    assert issues == []
    assert packages[0].groups[0].activities[0].hours == pytest.approx(2.5, abs=1e-3)
