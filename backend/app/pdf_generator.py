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
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .generator import TEMPLATE_PATH, ActivityInput, GroupInput, ReportHeader, _fmt_number, _labels, _translate_month_label

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


def _group_display(group: GroupInput, language: str = "pt") -> tuple[list[str], float]:
    """(descrições a mostrar, horas do grupo já com performance aplicada) —
    mesma regra de `generator._build_group_rows`: o `.xlsx` final mostra UM
    valor de horas por grupo (bruto × performance), não por atividade."""
    real_activities = [a for a in group.activities if a.hours is not None]
    extra_activities = [a for a in group.activities if a.hours is None]
    if not real_activities and not extra_activities:
        extra_activities = [ActivityInput(description=_labels(language)["no_activities"], hours=None)]

    descriptions = [a.description for a in real_activities] + [a.description for a in extra_activities]
    bruto_total = round(sum(a.hours for a in real_activities), 3)
    group_hours = round(bruto_total * group.performance, 3)
    return descriptions, group_hours


def _bruto_performance_cell(
    bruto: float, performance: float, label_style: ParagraphStyle, value_style: ParagraphStyle, language: str = "pt"
) -> Table:
    """Mini-tabela "Bruto | Performance" (cabeçalho pequeno + valores embaixo)
    — mesma informação, na mesma disposição, da caixa `.preview-side-box` do
    preview (ver `PreviewSheet.tsx`). Usada tanto por grupo quanto na linha de
    total, só aparece quando `include_performance=True`."""
    labels = _labels(language)
    table = Table(
        [
            [Paragraph(labels["bruto"], label_style), Paragraph(labels["performance"], label_style)],
            [Paragraph(_fmt_hours(bruto), value_style), Paragraph(_fmt_number(round(performance, 3)).replace(".", ","), value_style)],
        ],
        colWidths=["50%", "50%"],
    )
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                # linha branca semi-transparente — o fundo aqui é sempre escuro
                # (barra do grupo/faixa de total), _BORDER (cinza claro) não
                # teria contraste nenhum.
                ("LINEAFTER", (0, 0), (0, -1), 0.4, colors.Color(1, 1, 1, alpha=0.4)),
            ]
        )
    )
    return table


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
    include_performance: bool = False,
    language: str = "pt",
) -> None:
    labels = _labels(language)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,  # A4 sem rotação = retrato
        leftMargin=_MARGIN_H,
        rightMargin=_MARGIN_H,
        topMargin=_MARGIN_TOP,
        bottomMargin=_MARGIN_BOTTOM,
        title=labels["title"],
    )

    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16, textColor=_ACCENT_DARK)
    info_style = ParagraphStyle("info", fontName="Helvetica", fontSize=9.5, leading=14, textColor=colors.black)
    info_bold_style = ParagraphStyle("infoBold", parent=info_style, fontName="Helvetica-Bold", fontSize=11)
    group_title_style = ParagraphStyle(
        "groupTitle", fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.white, leading=14
    )
    activity_style = ParagraphStyle("activity", fontName="Helvetica", fontSize=9, leading=13, textColor=colors.black)
    group_hours_style = ParagraphStyle(
        "groupHours", fontName="Helvetica-Bold", fontSize=10, alignment=1, textColor=_ACCENT_DARK
    )
    total_label_style = ParagraphStyle("totalLabel", fontName="Helvetica-Bold", fontSize=11, textColor=colors.white)
    total_value_style = ParagraphStyle(
        "totalValue", fontName="Helvetica-Bold", fontSize=13, alignment=2, textColor=colors.white
    )
    # Bruto/Performance (ver `_bruto_performance_cell`) — só usados quando
    # `include_performance=True`; mesmo espírito visual de `.preview-side-header`/
    # `.preview-side-values` do preview: rótulo pequeno e discreto, valor um
    # pouco mais forte. Duas variantes de cor: a caixa da linha de TOTAL fica
    # sobre o fundo escuro `_ACCENT` (texto branco), mas a caixa POR GRUPO
    # fica dentro de uma linha de atividade normal, fundo branco — usar texto
    # branco ali o deixava invisível (branco sobre branco, bug real reportado).
    bp_label_style = ParagraphStyle("bpLabel", fontName="Helvetica", fontSize=6.5, alignment=1, textColor=colors.white)
    bp_value_style = ParagraphStyle("bpValue", fontName="Helvetica-Bold", fontSize=8.5, alignment=1, textColor=colors.white)
    bp_label_style_light = ParagraphStyle("bpLabelLight", parent=bp_label_style, textColor=colors.grey)
    bp_value_style_light = ParagraphStyle("bpValueLight", parent=bp_value_style, textColor=_ACCENT_DARK)

    story: list = []

    # logo original é 300x120px (razão 2.5:1, ver xl/media/image2.png no template)
    logo = Image(_load_logo_reader(), width=40 * mm, height=16 * mm)
    logo.hAlign = "LEFT"
    header_table = Table(
        [[logo, Paragraph(labels["title"], title_style)]],
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
    story.append(Paragraph(
        labels["subtitle"].format(month=_translate_month_label(header.month_label, language)), info_style
    ))
    story.append(Spacer(1, 8 * mm))

    grand_total = 0.0
    grand_bruto = 0.0
    content_width = A4[0] - 2 * _MARGIN_H
    last_col = 2 if include_performance else 1
    col_widths = (
        [content_width * 0.52, content_width * 0.20, content_width * 0.28]
        if include_performance
        else [content_width * 0.72, content_width * 0.28]
    )
    for group in groups:
        descriptions, group_hours = _group_display(group, language)
        grand_total += group_hours
        bruto_total = round(sum(a.hours for a in group.activities if a.hours is not None), 3)
        grand_bruto += bruto_total

        # Cabeçalho do grupo + atividades numa ÚNICA Table (não duas
        # flowables presas por KeepTogether): assim o reportlab pode quebrar
        # a lista de atividades entre páginas normalmente quando um grupo
        # tem muitas linhas, em vez de jogar o grupo inteiro pra página
        # seguinte (deixando a página anterior sem nenhuma hora visível —
        # foi exatamente esse o bug reportado). Sem repeatRows — a barra do
        # nome do grupo NÃO repete quando ele quebra entre páginas, as
        # atividades continuam direto (pedido explícito do usuário).
        #
        # Total de horas fica na ÚLTIMA coluna, mesclada verticalmente ao lado
        # de TODAS as atividades (não na barra do nome) — mesma posição do
        # `.xlsx` (ver `generator._build_group_rows`, mescla "C{first_row}:
        # C{last_row}"), centralizada. Quando `include_performance`, uma
        # coluna extra entre a descrição e a hora mostra Bruto/Performance
        # (ver `_bruto_performance_cell`), mesma informação que
        # `generator.py` grava nas colunas E/F do `.xlsx`.
        def _build_group_table(value_row_idx: int, span_value_col: bool):
            # `value_row_idx` é o índice (em `descriptions`) da linha de
            # atividade que carrega a hora total do grupo (e o Bruto/
            # Performance, se `include_performance`) — normalmente a
            # primeira (0), mas ver comentário abaixo sobre o caso em que a
            # tabela não cabe numa página inteira.
            header_row = [Paragraph(group.name, group_title_style), ""]
            if include_performance:
                header_row.append("")
            data = [header_row]
            for idx, desc in enumerate(descriptions):
                row = [Paragraph(f"• {desc}", activity_style)]
                if include_performance:
                    row.append(_bruto_performance_cell(bruto_total, group.performance, bp_label_style_light, bp_value_style_light, language) if idx == value_row_idx else "")
                row.append(Paragraph(_fmt_hours(group_hours), group_hours_style) if idx == value_row_idx else "")
                data.append(row)

            commands = [
                ("SPAN", (0, 0), (last_col, 0)),
                ("BACKGROUND", (0, 0), (last_col, 0), _ACCENT_DARK),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (0, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("LEFTPADDING", (0, 1), (0, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
            ]
            if len(data) > 1:
                if span_value_col:
                    commands.append(("SPAN", (last_col, 1), (last_col, len(data) - 1)))
                    if include_performance:
                        commands.append(("SPAN", (1, 1), (1, len(data) - 1)))
                commands.append(("VALIGN", (last_col, 1), (last_col, -1), "MIDDLE"))
                commands.append(("ALIGN", (last_col, 1), (last_col, -1), "CENTER"))
                # linha vertical separando a descrição da coluna de horas — só nas
                # linhas de atividade, a barra do nome (linha 0) já é uma cor
                # sólida sem divisão.
                commands.append(("LINEAFTER", (0, 1), (0, -1), 0.5, _BORDER))
                if include_performance:
                    commands.append(("VALIGN", (1, 1), (1, -1), "MIDDLE"))
                    commands.append(("LINEAFTER", (1, 1), (1, -1), 0.5, _BORDER))
            for row_idx in range(1, len(data) - 1):
                commands.append(("LINEBELOW", (0, row_idx), (0, row_idx), 0.4, _BORDER))

            built = Table(data, colWidths=col_widths)
            built.setStyle(TableStyle(commands))
            return built

        # Um SPAN vertical (dentro de `_build_group_table`) torna a tabela
        # INTEIRA um bloco atômico pro reportlab — ele não sabe quebrar uma
        # tabela no meio de uma célula mesclada, então um grupo com muitas
        # atividades (cuja lista sozinha já não cabe numa página inteira)
        # travava com `LayoutError` em vez de simplesmente continuar na
        # próxima página (bug real reportado: grupo com 35 atividades).
        # Mede a altura real (via wrap, mesmo cálculo que o reportlab usa
        # internamente) contra o espaço útil de uma página CHEIA — o maior
        # espaço que a tabela teria disponível em qualquer página — e, se
        # não couber nem assim, reconstrói sem o SPAN: a lista quebra entre
        # páginas normalmente. Sem o SPAN o valor não pode mais ficar
        # verticalmente centralizado ao lado de TODAS as atividades (o
        # reportlab não sabe centralizar algo "no meio de várias páginas"),
        # então ele vai na atividade do meio da lista em vez da primeira —
        # não é o efeito visual original, mas fica mais discreto que
        # simplesmente jogar o valor lá no topo.
        max_frame_height = A4[1] - _MARGIN_TOP - _MARGIN_BOTTOM
        group_table = _build_group_table(0, span_value_col=True)
        _, table_height = group_table.wrap(content_width, 0xFFFFFF)
        if table_height > max_frame_height:
            group_table = _build_group_table(len(descriptions) // 2, span_value_col=False)
            story.append(group_table)
        else:
            # O SPAN da coluna de valor começa na linha 1 (não na 0) — pra
            # ele, a linha 0 (barra do nome do grupo) é um ponto de quebra
            # LEGAL, então o reportlab podia deixar só a barra no fim de uma
            # página e jogar TODAS as atividades pra próxima (bug real
            # reportado: cabeçalho "separado" das atividades, com um vão em
            # branco enorme). Já sabemos (pelo `wrap` acima) que essa tabela
            # cabe inteira numa página — então forçar ela como um bloco único
            # com KeepTogether só pode fazer ela pular INTEIRA pra próxima
            # página quando necessário, nunca quebrar no meio.
            story.append(KeepTogether(group_table))
        story.append(Spacer(1, 5 * mm))

    total_row_cells = [Paragraph(
        labels["total_hours"].format(month=_translate_month_label(header.month_label, language)), total_label_style
    )]
    if include_performance:
        total_performance = grand_total / grand_bruto if grand_bruto > 0 else 0.0
        total_row_cells.append(_bruto_performance_cell(grand_bruto, total_performance, bp_label_style, bp_value_style, language))
    total_row_cells.append(Paragraph(_fmt_hours(grand_total), total_value_style))
    total_row = Table([total_row_cells], colWidths=col_widths)
    total_style_commands = [
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 8),
        ("RIGHTPADDING", (last_col, 0), (last_col, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    if include_performance:
        total_style_commands.append(("ALIGN", (1, 0), (1, 0), "CENTER"))
    total_row.setStyle(TableStyle(total_style_commands))
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
