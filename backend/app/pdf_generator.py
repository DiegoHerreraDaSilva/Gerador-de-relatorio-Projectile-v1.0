"""Geração do relatório final em PDF — alternativa ao `.xlsx` de `generator.py`,
pro caso de o usuário escolher "PDF" (ou "PDF" + "Excel") na tela de gerar/
enviar relatório.

Diferente de `generator.py` (que preserva 100% do arquivo `.xlsx` original via
manipulação de ZIP/XML), aqui o PDF é desenhado do zero em Python com
`reportlab` — não é um clone pixel-a-pixel do Excel, mas segue os MESMOS dados
e a mesma regra de cálculo (bruto × performance por grupo, ver
`generator._build_group_rows`), pra bater com o `.xlsx` do mesmo pacote.

Layout: A4 retrato, logo extraída do próprio template `.xlsx`
(`generator.TEMPLATE_PATH`, `xl/media/image2.png`) — fonte única da marca, sem
duplicar um arquivo de logo à parte.
"""
from __future__ import annotations

import base64
import io
import json
import zipfile

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .generator import TEMPLATE_PATH, ActivityInput, GroupInput, ReportHeader, _fmt_number

_LOGO_MEDIA_PART = "xl/media/image2.png"

# chave de metadado customizada (Info dictionary do PDF) onde gravamos os
# mesmos dados que o `.xlsx` grava numa célula oculta (ver
# `generator.HIDDEN_HELPER_COL`) — aqui não precisa de truque de coluna
# escondida, o PDF já tem um lugar nativo pra dado invisível ao leitor.
# `email_ingest.read_pdf_report_data` lê essa chave de volta.
PDF_METADATA_KEY = "/SchwabenReportData"

# mesma identidade visual do resto do app (frontend/src/styles/index.css:20,4)
_ACCENT = colors.HexColor("#0fa8a4")
_ACCENT_DARK = colors.HexColor("#128293")
_TEXT_MUTED = colors.HexColor("#6b7280")
_BORDER = colors.HexColor("#d8dde3")

_MARGIN_H = 18 * mm
_MARGIN_TOP = 16 * mm
_MARGIN_BOTTOM = 20 * mm


def _fmt_hours(value: float) -> str:
    """Mesma validação/arredondamento de `generator._fmt_number` (levanta
    `NonFiniteValueError` pra NaN/±Infinity — mesmo contrato que o `.xlsx`
    usa), só que exibido com vírgula decimal (padrão pt-BR) em vez de ponto,
    já que aqui não existe formatação de célula do Excel pra fazer isso."""
    return f"{_fmt_number(round(value, 3))} h".replace(".", ",")


def _load_logo_reader() -> io.BytesIO:
    with zipfile.ZipFile(TEMPLATE_PATH) as zf:
        return io.BytesIO(zf.read(_LOGO_MEDIA_PART))


def _group_display(group: GroupInput) -> tuple[list[str], float]:
    """(descrições a mostrar, horas do grupo já com performance aplicada) —
    mesma regra de `generator._build_group_rows`: o `.xlsx` final mostra UM
    valor de horas por grupo (bruto × performance), não por atividade."""
    real_activities = [a for a in group.activities if a.hours is not None]
    extra_activities = [a for a in group.activities if a.hours is None]
    if not real_activities and not extra_activities:
        extra_activities = [ActivityInput(description="(sem atividades apontadas)", hours=None)]

    descriptions = [a.description for a in real_activities] + [a.description for a in extra_activities]
    bruto_total = round(sum(a.hours for a in real_activities), 3)
    group_hours = round(bruto_total * group.performance, 3)
    return descriptions, group_hours


def _signature_table(header: ReportHeader) -> Table:
    style = ParagraphStyle("sig", fontName="Helvetica-Bold", fontSize=9, alignment=1, textColor=colors.black)
    company_style = ParagraphStyle("sigCompany", fontName="Helvetica", fontSize=8, alignment=1, textColor=_TEXT_MUTED)

    def _box(name: str, company: str) -> list:
        return [
            Spacer(1, 10 * mm),
            Paragraph(name or "&nbsp;", style),
            Paragraph(company, company_style),
        ]

    content_width = A4[0] - 2 * _MARGIN_H
    gap = 16 * mm
    box_width = (content_width - gap) / 2
    table = Table(
        [[_box(header.signer1_name, header.signer1_company), "", _box(header.signer2_name, header.signer2_company)]],
        colWidths=[box_width, gap, box_width],
    )
    table.setStyle(
        TableStyle(
            [
                # linhas de assinatura só nas colunas 0 e 2 — a coluna 1 (vazia,
                # sem LINEABOVE) garante o espaço entre elas, senão as duas
                # linhas ficam coladas e parecem uma única linha contínua.
                ("LINEABOVE", (0, 0), (0, 0), 0.75, colors.black),
                ("LINEABOVE", (2, 0), (2, 0), 0.75, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _embed_report_metadata(
    pdf_path: str, header: ReportHeader, total_hours: float, pacote_scope: str | None
) -> None:
    """Reabre o PDF recém-escrito e grava um segundo passe só de metadata —
    mesmo espírito de `generator._hide_helper_column` (dado que não pode
    aparecer no documento em si, escrito depois do conteúdo visível já
    fechado). `total_hours` já vem arredondado/validado por `_fmt_hours`
    (mesma regra bruto×performance de `generator.py`) — grava o número, não o
    texto formatado em pt-BR, pra `email_ingest` não precisar re-parsear
    vírgula decimal."""
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    writer.append(reader)
    payload = json.dumps(
        {
            "project_code": header.project_code,
            "project_name": header.project_name,
            "month_label": header.month_label,
            "total_hours": total_hours,
            "pacote_scope": pacote_scope,
        },
        ensure_ascii=False,
    )
    writer.add_metadata({PDF_METADATA_KEY: payload})
    with open(pdf_path, "wb") as f:
        writer.write(f)


def generate_report_pdf(
    header: ReportHeader,
    groups: list[GroupInput],
    output_path: str,
    chart_image_bar_b64: str | None = None,
    chart_image_pie_b64: str | None = None,
    pacote_scope: str | None = None,
) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,  # A4 sem rotação = retrato
        leftMargin=_MARGIN_H,
        rightMargin=_MARGIN_H,
        topMargin=_MARGIN_TOP,
        bottomMargin=_MARGIN_BOTTOM,
        title="Relatório de Horas",
    )

    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16, textColor=_ACCENT_DARK)
    info_style = ParagraphStyle("info", fontName="Helvetica", fontSize=9.5, leading=14, textColor=colors.black)
    info_bold_style = ParagraphStyle("infoBold", parent=info_style, fontName="Helvetica-Bold", fontSize=11)
    group_title_style = ParagraphStyle(
        "groupTitle", fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.white, leading=14
    )
    activity_style = ParagraphStyle("activity", fontName="Helvetica", fontSize=9, leading=13, textColor=colors.black)
    group_hours_style = ParagraphStyle(
        "groupHours", fontName="Helvetica-Bold", fontSize=10, alignment=2, textColor=_ACCENT_DARK
    )
    total_label_style = ParagraphStyle("totalLabel", fontName="Helvetica-Bold", fontSize=11, textColor=colors.white)
    total_value_style = ParagraphStyle(
        "totalValue", fontName="Helvetica-Bold", fontSize=13, alignment=2, textColor=colors.white
    )

    story: list = []

    # logo original é 300x120px (razão 2.5:1, ver xl/media/image2.png no template)
    logo = Image(_load_logo_reader(), width=40 * mm, height=16 * mm)
    logo.hAlign = "LEFT"
    header_table = Table(
        [[logo, Paragraph("RELATÓRIO DE HORAS", title_style)]],
        colWidths=[45 * mm, (A4[0] - 2 * _MARGIN_H - 45 * mm)],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=1.4, color=_ACCENT, spaceAfter=6 * mm))

    story.append(Paragraph(header.project_code, info_bold_style))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(header.project_name, info_style))
    story.append(Paragraph(header.location_date, info_style))
    story.append(Paragraph(f"Relatório de horas referentes ao mês de {header.month_label}", info_style))
    story.append(Spacer(1, 8 * mm))

    grand_total = 0.0
    content_width = A4[0] - 2 * _MARGIN_H
    for group in groups:
        descriptions, group_hours = _group_display(group)
        grand_total += group_hours

        # Cabeçalho do grupo + atividades numa ÚNICA Table (não duas
        # flowables presas por KeepTogether): assim o reportlab pode quebrar
        # a lista de atividades entre páginas normalmente quando um grupo
        # tem muitas linhas, em vez de jogar o grupo inteiro pra página
        # seguinte (deixando a página anterior sem nenhuma hora visível —
        # foi exatamente esse o bug reportado). Sem repeatRows — a barra do
        # nome do grupo NÃO repete quando ele quebra entre páginas, as
        # atividades continuam direto (pedido explícito do usuário).
        table_data = [[Paragraph(group.name, group_title_style), Paragraph(_fmt_hours(group_hours), group_hours_style)]]
        for desc in descriptions:
            table_data.append([Paragraph(f"• {desc}", activity_style), ""])

        style_commands = [
            ("BACKGROUND", (0, 0), (0, 0), _ACCENT_DARK),
            ("BACKGROUND", (1, 0), (1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("VALIGN", (0, 1), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 8),
            ("RIGHTPADDING", (1, 0), (1, 0), 8),
            ("LEFTPADDING", (0, 1), (0, -1), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
        ]
        for row_idx in range(1, len(table_data)):
            style_commands.append(("SPAN", (0, row_idx), (1, row_idx)))
            if row_idx < len(table_data) - 1:
                style_commands.append(("LINEBELOW", (0, row_idx), (-1, row_idx), 0.4, _BORDER))

        group_table = Table(table_data, colWidths=[content_width * 0.72, content_width * 0.28])
        group_table.setStyle(TableStyle(style_commands))
        story.append(group_table)
        story.append(Spacer(1, 5 * mm))

    total_row = Table(
        [[Paragraph(f"Total de horas {header.month_label}:", total_label_style), Paragraph(_fmt_hours(grand_total), total_value_style)]],
        colWidths=[content_width * 0.72, content_width * 0.28],
    )
    total_row.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (1, 0), (1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(total_row)
    story.append(Spacer(1, 6 * mm))

    for chart_b64 in (chart_image_bar_b64, chart_image_pie_b64):
        if not chart_b64:
            continue
        chart_bytes = base64.b64decode(chart_b64)
        chart_img = Image(io.BytesIO(chart_bytes), width=content_width, height=content_width * 0.56)
        chart_img.hAlign = "CENTER"
        story.append(chart_img)
        story.append(Spacer(1, 6 * mm))

    story.append(Spacer(1, 22 * mm))
    story.append(_signature_table(header))

    doc.build(story)
    _embed_report_metadata(output_path, header, grand_total, pacote_scope)
