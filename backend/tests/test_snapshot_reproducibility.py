"""Teste de reprodutibilidade do snapshot (GUIA_EVOLUCAO_GERADOR_PROJECTILE.md,
seção 92): reconstruir `ReportHeader`/`GroupInput` a partir de um `data_json`
salvo precisa produzir o mesmo total de horas e continuar gerando um .xlsx
válido — sem precisar de banco (o snapshot é só um dict em memória aqui)."""
from __future__ import annotations

import os

from backend.app.generator import ActivityInput, GroupInput, ReportHeader, generate_report
from backend.app.services.snapshot import build_snapshot_data


def _original_groups() -> list[GroupInput]:
    return [
        GroupInput(
            name="Grupo A",
            performance=100.0,
            activities=[
                ActivityInput(description="Atividade 1", hours=8.0),
                ActivityInput(description="Atividade 2", hours=4.5),
            ],
        ),
        GroupInput(
            name="Grupo B",
            performance=90.0,
            activities=[ActivityInput(description="Atividade 3", hours=2.0)],
        ),
    ]


def _pkg_data_from_groups(groups: list[GroupInput]) -> dict:
    return {
        "header": {
            "project_code": "SE.REPRO.001",
            "project_name": "Projeto Reprodutibilidade",
            "location_date": "São Paulo, 01/01/2026",
            "month_label": "Julho/2026",
            "signer1_name": "Fulano",
            "signer1_company": "Schwaben Engineering",
            "signer2_name": "Beltrano",
            "signer2_company": "Cliente Teste",
        },
        "groups": [
            {
                "name": g.name,
                "performance": g.performance,
                "activities": [{"description": a.description, "hours": a.hours} for a in g.activities],
            }
            for g in groups
        ],
        "pacote_scope": None,
        "language": "pt",
        "has_chart_bar": False,
        "has_chart_pie": False,
    }


def _total_hours(groups: list[GroupInput]) -> float:
    return sum(a.hours or 0 for g in groups for a in g.activities)


def test_snapshot_reconstroi_mesmo_total_de_horas_e_gera_arquivo_valido(tmp_path):
    original_groups = _original_groups()
    snapshot = build_snapshot_data(_pkg_data_from_groups(original_groups))

    reconstructed_header = ReportHeader(**snapshot["header"])
    reconstructed_groups = [
        GroupInput(
            name=g["name"],
            performance=g["performance"],
            activities=[ActivityInput(description=a["description"], hours=a["hours"]) for a in g["activities"]],
        )
        for g in snapshot["groups"]
    ]

    assert _total_hours(reconstructed_groups) == _total_hours(original_groups)

    output_path = str(tmp_path / "relatorio_reconstruido.xlsx")
    generate_report(reconstructed_header, reconstructed_groups, output_path)

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
