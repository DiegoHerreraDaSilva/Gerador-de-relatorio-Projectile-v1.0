"""Testes de integração do backend/app/services/report_persistence.py
contra um reports-mysql REAL (não mockado) — precisa de
`docker compose up -d reports-mysql` + `alembic upgrade head` rodados
antes. Pulados automaticamente se REPORTS_DB_HOST não estiver setado (ver
conftest.py:reports_db_engine)."""
from __future__ import annotations

import concurrent.futures
import os

import pytest
from sqlalchemy import select

from backend.app.db.reports_schema import report_artifacts, report_generation, report_versions, reports
from backend.app.services.report_persistence import (
    begin_generation,
    finish_generation_failure,
    finish_generation_success,
)

pytestmark = pytest.mark.reports_db


def _pkg_data(report_number="SE.TESTE.001", month_label="Julho/2026", hours=8.0):
    return {
        "header": {
            "project_code": report_number,
            "project_name": "Projeto de Teste",
            "location_date": "São Paulo, 01/01/2026",
            "month_label": month_label,
            "signer1_name": "Fulano",
            "signer1_company": "Schwaben Engineering",
            "signer2_name": "Beltrano",
            "signer2_company": "Cliente Teste",
        },
        "groups": [
            {"name": "Grupo A", "performance": 100.0, "activities": [{"description": "Atividade 1", "hours": hours}]}
        ],
        "pacote_scope": None,
        "language": "pt",
        "has_chart_bar": False,
        "has_chart_pie": False,
    }


def test_begin_generation_cria_report_version_snapshot_e_generation(reports_db_engine):
    handle = begin_generation(_pkg_data(), "xlsx", "dherrera", "Diego Herrera")
    assert handle is not None
    assert handle.version_number == 1

    with reports_db_engine.begin() as conn:
        report_row = conn.execute(select(reports).where(reports.c.id == handle.report_id)).first()
        version_row = conn.execute(select(report_versions).where(report_versions.c.id == handle.version_id)).first()
        generation_row = conn.execute(
            select(report_generation).where(report_generation.c.id == handle.generation_id)
        ).first()

    assert report_row is not None
    assert report_row.report_number == "SE.TESTE.001"
    assert version_row is not None
    assert version_row.version_number == 1
    assert generation_row is not None
    assert generation_row.status == "started"


def test_finish_generation_success_marca_sucesso_e_cria_artifact(reports_db_engine, tmp_path):
    handle = begin_generation(_pkg_data(), "xlsx", "dherrera", "Diego Herrera")
    fake_file = tmp_path / "relatorio.xlsx"
    fake_file.write_bytes(b"conteudo fake de teste")

    finish_generation_success(
        handle, str(fake_file), "Relatorio.xlsx", "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    with reports_db_engine.begin() as conn:
        generation_row = conn.execute(
            select(report_generation).where(report_generation.c.id == handle.generation_id)
        ).first()
        artifact_row = conn.execute(
            select(report_artifacts).where(report_artifacts.c.generation_id == handle.generation_id)
        ).first()

    assert generation_row.status == "success"
    assert generation_row.duration_ms is not None
    assert artifact_row is not None
    assert artifact_row.file_size == len(b"conteudo fake de teste")
    assert os.path.exists(artifact_row.storage_path)
    # a cópia é uma cópia — não o mesmo arquivo do tmp_path original
    assert artifact_row.storage_path != str(fake_file)


def test_finish_generation_failure_nunca_deixa_started_pra_sempre(reports_db_engine):
    handle = begin_generation(_pkg_data(), "xlsx", "dherrera", "Diego Herrera")
    finish_generation_failure(handle, ValueError("template corrompido de teste"))

    with reports_db_engine.begin() as conn:
        generation_row = conn.execute(
            select(report_generation).where(report_generation.c.id == handle.generation_id)
        ).first()

    assert generation_row.status == "failed"
    assert "template corrompido" in generation_row.error_message


def test_versoes_sucessivas_sao_imutaveis(reports_db_engine):
    """Guia GUIA_EVOLUCAO_GERADOR_PROJECTILE.md, seção 93: criar v2 nunca
    pode alterar os registros de v1."""
    handle_v1 = begin_generation(_pkg_data(hours=8.0), "xlsx", "dherrera", "Diego Herrera")
    with reports_db_engine.begin() as conn:
        v1_before = dict(
            conn.execute(select(report_versions).where(report_versions.c.id == handle_v1.version_id)).first()._mapping
        )

    handle_v2 = begin_generation(_pkg_data(hours=9.0), "xlsx", "dherrera", "Diego Herrera")

    with reports_db_engine.begin() as conn:
        v1_after = dict(
            conn.execute(select(report_versions).where(report_versions.c.id == handle_v1.version_id)).first()._mapping
        )

    assert handle_v2.report_id == handle_v1.report_id
    assert handle_v2.version_number == handle_v1.version_number + 1
    assert v1_before == v1_after


def test_concorrencia_nao_gera_version_number_duplicado(reports_db_engine):
    """10 chamadas simultâneas pro MESMO relatório — version_number precisa
    ser {1..10} sem duplicata nem lacuna (guia GUIA_EVOLUCAO_GERADOR_PROJECTILE.md,
    seções 94-95)."""

    def _generate(_i):
        return begin_generation(_pkg_data(report_number="SE.CONCORRENCIA.001"), "xlsx", "dherrera", "Diego Herrera")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        handles = list(pool.map(_generate, range(10)))

    assert all(h is not None for h in handles)
    report_ids = {h.report_id for h in handles}
    assert len(report_ids) == 1, "todas as 10 chamadas deviam resolver pro MESMO report_id"

    version_numbers = sorted(h.version_number for h in handles)
    assert version_numbers == list(range(1, 11))
