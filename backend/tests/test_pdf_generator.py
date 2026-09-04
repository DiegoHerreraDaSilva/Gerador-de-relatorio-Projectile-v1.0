"""Trava as garantias básicas do PDF gerado (`pdf_generator.py`): é um PDF de
verdade, A4 retrato, e o total de horas bate com a mesma regra de cálculo
(bruto × performance por grupo) que `generator.py`/`test_generator.py` já
travam pro `.xlsx` — os dois formatos precisam concordar no mesmo número."""
from __future__ import annotations

import json

from pypdf import PdfReader

from backend.app.generator import ActivityInput, GroupInput
from backend.app.pdf_generator import PDF_METADATA_KEY

from .helpers import make_report_pdf


def test_pdf_starts_with_pdf_signature(tmp_path):
    groups = [GroupInput(name="Grupo A", performance=1.0, activities=[ActivityInput("Ativ 1", 10.0)])]
    pdf_path = make_report_pdf(tmp_path, groups=groups)
    with open(pdf_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_pdf_page_is_a4_portrait(tmp_path):
    groups = [GroupInput(name="Grupo A", performance=1.0, activities=[ActivityInput("Ativ 1", 10.0)])]
    pdf_path = make_report_pdf(tmp_path, groups=groups)
    reader = PdfReader(pdf_path)
    box = reader.pages[0].mediabox
    width, height = float(box.width), float(box.height)
    assert width < height, "página devia ser retrato (largura < altura)"
    # A4 = 595 x 842 pt — folga de alguns pontos por causa de arredondamento
    assert abs(width - 595.28) < 2
    assert abs(height - 841.89) < 2


def test_pdf_total_hours_matches_bruto_times_performance(tmp_path):
    """Mesmo fixture de `test_generator.py::report_path` — Grupo A (bruto 10h,
    performance 1.1 => 11h) e Grupo B (bruto 8h, performance 0.9 => 7.2h),
    total esperado 18.2h, mesma regra que o `.xlsx` aplica em
    `generator._build_group_rows`."""
    groups = [
        GroupInput(
            name="Grupo A",
            performance=1.1,
            activities=[ActivityInput("Ativ 1", 10.0), ActivityInput("Extra sem apontamento", None)],
        ),
        GroupInput(name="Grupo B", performance=0.9, activities=[ActivityInput("Ativ 2", 8.0)]),
    ]
    pdf_path = make_report_pdf(tmp_path, groups=groups, month_label="Julho/2026")
    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert "Total de horas Julho/2026:" in text
    # 10*1.1 = 11,0 h ; 8*0.9 = 7,2 h ; total = 18,2 h — vírgula decimal (pt-BR)
    assert "11 h" in text or "11,0 h" in text
    assert "7,2 h" in text
    assert "18,2 h" in text


def test_pdf_metadata_carries_identity_and_total_hours(tmp_path):
    """`email_ingest.read_pdf_report_data` lê essa chave de volta pra fazer,
    pro `.pdf`, o mesmo que `resolve_total_hours`/`read_project_identity`
    fazem pro `.xlsx` — sem fórmula nem célula, o total já vem calculado
    (mesma regra bruto×performance) e a identidade do projeto vem junto."""
    groups = [
        GroupInput(name="Grupo A", performance=1.1, activities=[ActivityInput("Ativ 1", 10.0)]),
        GroupInput(name="Grupo B", performance=0.9, activities=[ActivityInput("Ativ 2", 8.0)]),
    ]
    pdf_path = make_report_pdf(
        tmp_path,
        project_code="1546.6.4",
        project_name="Sangam - Cabina Bruta",
        month_label="Julho/2026",
        groups=groups,
    )
    reader = PdfReader(pdf_path)
    data = json.loads(reader.metadata[PDF_METADATA_KEY])

    assert data["project_code"] == "1546.6.4"
    assert data["project_name"] == "Sangam - Cabina Bruta"
    assert data["month_label"] == "Julho/2026"
    assert data["total_hours"] == 18.2  # 10*1.1 + 8*0.9, mesma conta de test_pdf_total_hours_matches_bruto_times_performance
    assert data["pacote_scope"] is None


def test_pdf_metadata_carries_pacote_scope_when_set(tmp_path):
    groups = [GroupInput(name="Grupo A", performance=1.0, activities=[ActivityInput("Ativ 1", 10.0)])]
    pacote_text = "1546.6.4-002 Legislation Package - Sangam - Cabina Bruta - 07.2026"
    pdf_path = make_report_pdf(tmp_path, groups=groups, pacote_scope=pacote_text)
    reader = PdfReader(pdf_path)
    data = json.loads(reader.metadata[PDF_METADATA_KEY])

    assert data["pacote_scope"] == pacote_text


def test_pdf_empty_group_gets_placeholder_not_dropped(tmp_path):
    """Mesma regra do `.xlsx`: um grupo sem nenhuma atividade não pode
    desaparecer silenciosamente do relatório (ver `generator._build_group_rows`)."""
    groups = [GroupInput(name="Grupo Vazio", performance=1.0, activities=[])]
    pdf_path = make_report_pdf(tmp_path, groups=groups)
    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Grupo Vazio" in text
    assert "sem atividades apontadas" in text
