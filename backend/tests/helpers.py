"""Helpers compartilhados entre os módulos de teste — nada aqui é teste em si
(sem `test_` no nome do arquivo, pytest não coleta)."""
from __future__ import annotations

from backend.app.generator import ActivityInput, GroupInput, ReportHeader, generate_report
from backend.app.pdf_generator import generate_report_pdf


def make_report(
    tmp_path,
    *,
    project_code: str = "PC-001",
    project_name: str = "Projeto Teste",
    month_label: str = "Julho/2026",
    groups: list[GroupInput],
    filename: str = "relatorio.xlsx",
    pacote_scope: str | None = None,
) -> str:
    """Gera um .xlsx de fixture real via `generator.generate_report` — o
    mesmo caminho de código de produção usado pelo app de verdade — em vez de
    um mock ad-hoc. `resolve_total_hours`/`read_project_identity` (em
    `email_ingest.py`) dependem exatamente da forma de fórmula que esta
    função escreve, então fixtures geradas por ela são a fonte mais realista
    possível para os testes que travam esse contrato."""
    header = ReportHeader(
        project_code=project_code,
        project_name=project_name,
        location_date="São Paulo, 01/01/2026",
        month_label=month_label,
    )
    output_path = str(tmp_path / filename)
    generate_report(header, groups, output_path, pacote_scope=pacote_scope)
    return output_path


def make_report_pdf(
    tmp_path,
    *,
    project_code: str = "PC-001",
    project_name: str = "Projeto Teste",
    month_label: str = "Julho/2026",
    groups: list[GroupInput],
    filename: str = "relatorio.pdf",
    pacote_scope: str | None = None,
) -> str:
    """Mesma ideia de `make_report`, gerando um .pdf real via
    `pdf_generator.generate_report_pdf` em vez do .xlsx."""
    header = ReportHeader(
        project_code=project_code,
        project_name=project_name,
        location_date="São Paulo, 01/01/2026",
        month_label=month_label,
    )
    output_path = str(tmp_path / filename)
    generate_report_pdf(header, groups, output_path, pacote_scope=pacote_scope)
    return output_path
