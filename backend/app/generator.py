"""Geração do relatório final preservando 100% do arquivo original (layout, estilos,
logo e assinaturas), editando apenas o XML da planilha de dados diretamente.

Não usamos `openpyxl.save()` para o arquivo final porque ele descarta desenhos
(shapes, caixas de texto, linhas de assinatura) e a logo embutida no cabeçalho/rodapé
do arquivo original. Em vez disso, copiamos o .xlsx original byte-a-byte e substituímos
apenas o XML da planilha (`xl/worksheets/sheet1.xml`), preservando todo o resto
(`xl/drawings`, `xl/media`, relações, tipos de conteúdo etc.).
"""
from __future__ import annotations

import base64
import datetime
import math
import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

class NonFiniteValueError(ValueError):
    """Um número (horas/performance) resultou em NaN/±Infinity — normalmente por
    estouro de soma entre valores individualmente válidos. Subclasse de ValueError,
    mas distinta das demais ValueErrors deste módulo (que sinalizam o TEMPLATE
    corrompido/incompatível, um problema do servidor, não do usuário) para que o
    chamador possa tratar cada caso de forma diferente."""


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "relatorio_final_template.xlsx")
SHEET_PART = "xl/worksheets/sheet1.xml"
DRAWING_PART = "xl/drawings/drawing1.xml"
DRAWING_RELS_PART = "xl/drawings/_rels/drawing1.xml.rels"
CHART_ROWS_RESERVED = 15  # linhas extras empurradas antes da assinatura quando há gráfico
CHART_ROW_LIFT = 3  # sobe o gráfico um pouco em relação à posição-base da assinatura
WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
CONTENT_TYPES_PART = "[Content_Types].xml"
CALC_CHAIN_PART = "xl/calcChain.xml"

GROUP_START_ROW = 15
# linha (0-index, conforme usado nos anchors do drawing1.xml) a partir da qual
# ficam as caixas de assinatura no arquivo original; tudo a partir daqui é
# deslocado conforme o conteúdo gerado for maior/menor que o original.
SIGNATURE_ANCHOR_THRESHOLD = 56
ORIGINAL_LAST_DATA_ROW = 51  # linha da fórmula de performance média no template original

# estilos (atributo s=) reaproveitados do template original, por papel de célula
S_GROUP_NAME = 32
S_GROUP_C = 33
S_LABEL = 17
S_FILLER = 6
S_ACTIVITY_DESC = 9
S_ACTIVITY_C_FORMULA = 30
S_ACTIVITY_HOURS = 17
S_ACTIVITY_PERF = 20
S_CALC_E = 6
S_TOTAL_LABEL = 10
S_TOTAL_VALUE = 14
S_SUM_E = 21
S_RATIO_F = 18


@dataclass
class ActivityInput:
    description: str
    hours: float | None = None  # None => atividade extra, sem apontamento


@dataclass
class GroupInput:
    name: str
    performance: float
    activities: list[ActivityInput] = field(default_factory=list)


@dataclass
class ReportHeader:
    project_code: str
    project_name: str
    location_date: str
    month_label: str  # ex: "Julho/2026"
    signer1_name: str = ""
    signer1_company: str = "Schwaben Engineering"
    signer2_name: str = ""
    signer2_company: str = "Mercedes-Benz do Brasil"


# textos originais do template que identificam cada caixa de assinatura no drawing1.xml
_ORIGINAL_SIGNER1_NAME = "Alberto Moura"
_ORIGINAL_SIGNER1_COMPANY = "Schwaben Engineering"
_ORIGINAL_SIGNER2_NAME = "Wagner Augusto Duarte"
_ORIGINAL_SIGNER2_COMPANY = "Mercedes-Benz do Brasil"


def _fmt_number(value: float) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NonFiniteValueError(f"Valor numérico inválido para o relatório: {value!r}")
        # Formata em ponto fixo (nunca notação científica) antes de tirar os zeros à
        # direita — repr() pode virar notação científica ("1e+20") para números muito
        # grandes/pequenos, e um rstrip("0") ingênuo nesse formato corrói dígitos do
        # EXPOENTE (ex: "1e+20" -> "1e+2", virando 100.0 em vez de 1e20) em vez de só
        # tirar zeros decorativos da parte fracionária.
        text = f"{value:.6f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    return str(value)


def _inline_str_cell(ref: str, style: int, text: str) -> str:
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _number_cell(ref: str, style: int, value: float) -> str:
    return f'<c r="{ref}" s="{style}"><v>{_fmt_number(value)}</v></c>'


def _formula_cell(ref: str, style: int, formula: str) -> str:
    return f'<c r="{ref}" s="{style}"><f>{escape(formula)}</f></c>'


def _empty_cell(ref: str, style: int) -> str:
    return f'<c r="{ref}" s="{style}"/>'


DEFAULT_ROW_HEIGHT = 15
ACTIVITY_ROW_HEIGHT = 21  # um pouco mais alta para dar respiro acima/abaixo do texto da atividade


def _row(number: int, cells: list[str], height: float = DEFAULT_ROW_HEIGHT) -> str:
    cells = sorted(cells, key=lambda c: re.match(r'<c r="([A-Z]+)\d+"', c).group(1))
    return f'<row r="{number}" ht="{height}" customHeight="1">' + "".join(cells) + "</row>"


# tabela "Week/AK/days/Hours/week" do template original (colunas H:K, linhas
# 15-20) — fica nas mesmas linhas onde os grupos são escritos, então precisa
# ser reconstruída a cada relatório: Week sempre 1, AK em branco (preenchido
# manualmente depois, por linha, conforme o adicional aplicável), Days
# calculado a partir do mês do relatório (dias úteis por semana, descontando
# feriados nacionais) e Hours/week com a fórmula original do template.
HOURS_WEEK_TABLE_ROWS = 5

_MESES_PT = [
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _parse_month_label(label: str) -> tuple[int, int] | None:
    """'Julho/2026' -> (2026, 7). Retorna None se o texto não seguir esse padrão
    (ex: o usuário apagou/reescreveu o campo com outro formato)."""
    match = re.match(r"\s*([^/]+?)\s*/\s*(\d{4})\s*$", label or "")
    if not match:
        return None
    month_name = _strip_accents(match.group(1).strip().lower())
    try:
        month = _MESES_PT.index(month_name) + 1
    except ValueError:
        return None
    return int(match.group(2)), month


def _easter_sunday(year: int) -> datetime.date:
    """Algoritmo anônimo gregoriano (Meeus/Jones/Butcher) para a Páscoa — usado
    para derivar os feriados móveis (Carnaval, Sexta-feira Santa, Corpus Christi)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(year, month, day)


def _national_holidays(year: int) -> set[datetime.date]:
    """Feriados nacionais fixos + móveis. Feriados estaduais/municipais não
    entram aqui — ficam de fora até serem pedidos explicitamente."""
    easter = _easter_sunday(year)
    holidays = {
        datetime.date(year, 1, 1),    # Confraternização Universal
        datetime.date(year, 4, 21),   # Tiradentes
        datetime.date(year, 5, 1),    # Dia do Trabalho
        datetime.date(year, 9, 7),    # Independência
        datetime.date(year, 10, 12),  # Nossa Senhora Aparecida
        datetime.date(year, 11, 2),   # Finados
        datetime.date(year, 11, 15),  # Proclamação da República
        datetime.date(year, 12, 25),  # Natal
        easter - datetime.timedelta(days=48),  # Carnaval (segunda)
        easter - datetime.timedelta(days=47),  # Carnaval (terça)
        easter - datetime.timedelta(days=2),   # Sexta-feira Santa
        easter + datetime.timedelta(days=60),  # Corpus Christi
    }
    if year >= 2024:
        holidays.add(datetime.date(year, 11, 20))  # Dia da Consciência Negra (Lei 14.759/2023)
    return holidays


def count_business_days(start: datetime.date, end: datetime.date) -> int:
    """Conta dias úteis (seg-sex, sem feriado nacional) estritamente APÓS
    `start` até `end` inclusive — usado por `email_ingest.py` pra medir quanto
    tempo depois do fechamento do mês um relatório foi enviado. Diferente de
    `_business_days_per_week` (que reparte um único mês em semanas pra tabela
    do relatório): aqui o intervalo é entre duas datas quaisquer, possivelmente
    cruzando anos, então o conjunto de feriados é recalculado por ano
    conforme o cursor avança."""
    if end <= start:
        return 0
    holidays_by_year: dict[int, set[datetime.date]] = {}
    count = 0
    day = start + datetime.timedelta(days=1)
    while day <= end:
        holidays = holidays_by_year.setdefault(day.year, _national_holidays(day.year))
        if day.weekday() < 5 and day not in holidays:
            count += 1
        day += datetime.timedelta(days=1)
    return count


def _business_days_per_week(month_label: str) -> list[int]:
    """Divide o mês do relatório em semanas de calendário (segunda a domingo,
    cortadas nas bordas do mês) e conta, em cada uma, os dias úteis (seg-sex)
    que não caem em feriado nacional. Se o mês precisar de mais de
    HOURS_WEEK_TABLE_ROWS semanas (raro — só quando o mês começa perto do fim
    de semana e tem 31 dias), o excedente é somado na última linha, já que a
    tabela do template só tem esse tanto de linhas. Se o rótulo do mês não for
    reconhecido, retorna tudo zerado em vez de arriscar um valor errado."""
    parsed = _parse_month_label(month_label)
    if parsed is None:
        return [0] * HOURS_WEEK_TABLE_ROWS
    year, month = parsed
    first_day = datetime.date(year, month, 1)
    next_month = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    last_day = next_month - datetime.timedelta(days=1)
    holidays = _national_holidays(year)

    weeks_days: list[int] = []
    cursor = first_day
    while cursor <= last_day:
        week_end = cursor + datetime.timedelta(days=6 - cursor.weekday())
        clipped_end = min(week_end, last_day)
        count = 0
        day = cursor
        while day <= clipped_end:
            if day.weekday() < 5 and day not in holidays:
                count += 1
            day += datetime.timedelta(days=1)
        weeks_days.append(count)
        cursor = clipped_end + datetime.timedelta(days=1)

    if len(weeks_days) > HOURS_WEEK_TABLE_ROWS:
        overflow = sum(weeks_days[HOURS_WEEK_TABLE_ROWS - 1:])
        weeks_days = weeks_days[:HOURS_WEEK_TABLE_ROWS - 1] + [overflow]
    while len(weeks_days) < HOURS_WEEK_TABLE_ROWS:
        weeks_days.append(0)
    return weeks_days


def _hours_week_table_cells(row_number: int, days_per_week: list[int]) -> list[str]:
    if 15 <= row_number <= 19:
        days = days_per_week[row_number - 15]
        return [
            _number_cell(f"H{row_number}", 23, 1),
            _empty_cell(f"I{row_number}", 23),
            _number_cell(f"J{row_number}", 23, days),
            _formula_cell(f"K{row_number}", 23, f"I{row_number}*J{row_number}*$K$13"),
        ]
    if row_number == 20:
        return [
            _inline_str_cell("J20", 24, "total:"),
            _formula_cell("K20", 25, "K15+K16+K17+K18+K19"),
        ]
    return []


def _replace_header_cell(sheet_xml: str, ref: str, style: int, text: str) -> str:
    pattern = re.compile(rf'<c r="{ref}"[^>]*(?:/>|>.*?</c>)')
    replacement = _inline_str_cell(ref, style, text)
    new_xml, count = pattern.subn(replacement, sheet_xml, count=1)
    if count != 1:
        raise ValueError(f"Não encontrei a célula de cabeçalho {ref} no template.")
    return new_xml


def _build_groups_xml(groups: list[GroupInput], month_label: str):
    """Retorna (linhas_xml, merges, ultima_linha_de_dados)."""
    rows_by_number: dict[int, list[str]] = {}
    merges: list[str] = []
    total_hours_cells: list[str] = []
    total_bruto_cells: list[str] = []
    activity_rows: set[int] = set()  # linhas com texto de atividade -> ganham altura extra

    def add_cells(row_number: int, cells: list[str]) -> None:
        rows_by_number.setdefault(row_number, []).extend(cells)

    row = GROUP_START_ROW
    for group in groups:
        real_activities = [a for a in group.activities if a.hours is not None]
        extra_activities = [a for a in group.activities if a.hours is None]
        if not real_activities and not extra_activities:
            # Um grupo sem nenhuma atividade (ex: usuário removeu a última atividade
            # dele na tela) não pode simplesmente sumir do relatório sem deixar
            # rastro — isso apagaria uma categoria de trabalho silenciosamente.
            # Em vez disso, mostra o grupo com uma linha de aviso e 0h.
            extra_activities = [ActivityInput(description="(sem atividades apontadas)", hours=None)]

        header_row = row
        merges.append(f"B{header_row}:C{header_row}")
        add_cells(
            header_row,
            [
                _inline_str_cell(f"B{header_row}", S_GROUP_NAME, group.name),
                _empty_cell(f"C{header_row}", S_GROUP_C),
                _empty_cell(f"D{header_row}", S_FILLER),
                _inline_str_cell(f"E{header_row}", S_LABEL, "Bruto"),
                _inline_str_cell(f"F{header_row}", S_LABEL, "Performance"),
                _empty_cell(f"G{header_row}", S_FILLER),
            ],
        )

        first_row = header_row + 1
        bruto_total = round(sum(a.hours for a in real_activities), 3)

        if real_activities:
            calc_row = first_row + 1
            other_descriptions = [a.description for a in real_activities[1:]] + [a.description for a in extra_activities]

            add_cells(
                first_row,
                [
                    _inline_str_cell(f"B{first_row}", S_ACTIVITY_DESC, real_activities[0].description),
                    _formula_cell(f"C{first_row}", S_ACTIVITY_C_FORMULA, f"E{calc_row}"),
                    _empty_cell(f"D{first_row}", S_FILLER),
                    _number_cell(f"E{first_row}", S_ACTIVITY_HOURS, bruto_total),
                    _number_cell(f"F{first_row}", S_ACTIVITY_PERF, group.performance),
                    _empty_cell(f"G{first_row}", S_FILLER),
                ],
            )

            calc_desc = other_descriptions[0] if other_descriptions else None
            add_cells(
                calc_row,
                [
                    _inline_str_cell(f"B{calc_row}", S_ACTIVITY_DESC, calc_desc) if calc_desc else _empty_cell(f"B{calc_row}", S_ACTIVITY_DESC),
                    _empty_cell(f"C{calc_row}", S_ACTIVITY_C_FORMULA),
                    _empty_cell(f"D{calc_row}", S_FILLER),
                    _formula_cell(f"E{calc_row}", S_CALC_E, f"E{first_row}*F{first_row}"),
                    _empty_cell(f"G{calc_row}", S_FILLER),
                ],
            )

            last_row = calc_row
            for description in other_descriptions[1:]:
                last_row += 1
                add_cells(
                    last_row,
                    [
                        _inline_str_cell(f"B{last_row}", S_ACTIVITY_DESC, description),
                        _empty_cell(f"C{last_row}", S_ACTIVITY_C_FORMULA),
                        _empty_cell(f"D{last_row}", S_FILLER),
                        _empty_cell(f"E{last_row}", S_CALC_E),
                        _empty_cell(f"G{last_row}", S_FILLER),
                    ],
                )

            total_hours_cells.append(f"C{first_row}")
            total_bruto_cells.append(f"E{first_row}")
        else:
            last_row = first_row
            for offset, activity in enumerate(extra_activities):
                target_row = first_row + offset
                add_cells(
                    target_row,
                    [
                        _inline_str_cell(f"B{target_row}", S_ACTIVITY_DESC, activity.description),
                        _empty_cell(f"C{target_row}", S_ACTIVITY_C_FORMULA),
                        _empty_cell(f"D{target_row}", S_FILLER),
                        _empty_cell(f"E{target_row}", S_CALC_E),
                        _empty_cell(f"G{target_row}", S_FILLER),
                    ],
                )
                last_row = target_row

        if last_row > first_row:
            merges.append(f"C{first_row}:C{last_row}")

        activity_rows.update(range(first_row, last_row + 1))

        row = last_row + 2  # uma linha em branco entre grupos

    total_row = row + 1
    total_value = f"=SUM({','.join(total_hours_cells)})" if total_hours_cells else "0"
    add_cells(
        total_row,
        [
            _inline_str_cell(f"B{total_row}", S_TOTAL_LABEL, f"Total de horas {month_label}:"),
            _formula_cell(f"C{total_row}", S_TOTAL_VALUE, total_value.lstrip("=")),
            _inline_str_cell(f"E{total_row}", S_LABEL, "Bruto"),
            _inline_str_cell(f"F{total_row}", S_LABEL, "Performance"),
        ],
    )

    bruto_row = total_row + 1
    bruto_formula = f"SUM({','.join(total_bruto_cells)})" if total_bruto_cells else "0"
    add_cells(
        bruto_row,
        [
            _formula_cell(f"E{bruto_row}", S_SUM_E, bruto_formula),
            _formula_cell(f"F{bruto_row}", S_RATIO_F, f"C{total_row}/E{bruto_row}") if total_bruto_cells else _empty_cell(f"F{bruto_row}", S_RATIO_F),
        ],
    )

    # reconstrói a tabela "Week/AK/days/Hours/week" (colunas H:K) do template
    # original, com os dias úteis do mês do relatório, nas mesmas linhas
    # 15-20 usadas pelos grupos
    days_per_week = _business_days_per_week(month_label)
    for hours_week_row in range(15, 21):
        add_cells(hours_week_row, _hours_week_table_cells(hours_week_row, days_per_week))

    rows = [
        _row(number, cells, height=ACTIVITY_ROW_HEIGHT if number in activity_rows else DEFAULT_ROW_HEIGHT)
        for number, cells in sorted(rows_by_number.items())
    ]
    return rows, merges, bruto_row


def _shift_signature_drawing(drawing_xml: str, offset: int) -> str:
    if offset == 0:
        return drawing_xml

    def _shift(match: re.Match) -> str:
        row_value = int(match.group(1))
        if row_value >= SIGNATURE_ANCHOR_THRESHOLD:
            row_value += offset
        return f"<xdr:row>{row_value}</xdr:row>"

    return re.sub(r"<xdr:row>(\d+)</xdr:row>", _shift, drawing_xml)


def _replace_signature_names(drawing_xml: str, header: ReportHeader) -> str:
    replacements = [
        (_ORIGINAL_SIGNER1_NAME, header.signer1_name),
        (_ORIGINAL_SIGNER1_COMPANY, header.signer1_company),
        (_ORIGINAL_SIGNER2_NAME, header.signer2_name),
        (_ORIGINAL_SIGNER2_COMPANY, header.signer2_company),
    ]
    # Localiza a posição de cada tag original na string intacta ANTES de fazer
    # qualquer substituição. Fazer 4 .replace() encadeados sobre a mesma string
    # (mutando-a a cada passo) tem um bug sutil: se um NOVO valor coincidir com o
    # texto ORIGINAL de uma assinatura ainda não processada (ex: signer1_name
    # recebendo literalmente "Wagner Augusto Duarte", que é o nome original do
    # signer2), o passo seguinte acaba casando com o texto já trocado em vez do
    # texto genuíno, trocando/duplicando nomes entre as duas caixas sem erro.
    spans = []
    for original, new_value in replacements:
        tag = f"<a:t>{escape(original)}</a:t>"
        idx = drawing_xml.find(tag)
        if idx == -1:
            raise ValueError(f"Não encontrei o texto de assinatura '{original}' no template.")
        spans.append((idx, idx + len(tag), new_value))
    spans.sort(key=lambda s: s[0])

    pieces = []
    cursor = 0
    for start, end, new_value in spans:
        pieces.append(drawing_xml[cursor:start])
        pieces.append(f"<a:t>{escape(new_value)}</a:t>")
        cursor = end
    pieces.append(drawing_xml[cursor:])
    return "".join(pieces)


# tamanho fixo em EMU (1 px = 9525 EMU) de cada gráfico embutido, mantendo a
# proporção 1000x560 do canvas, num tamanho menor pra caberem 2 lado a lado
_CHART_CX = 4469000
_CHART_CY = 2502640
_CHART_GAP = 260000  # ~0.28in de respiro entre os 2 gráficos, em EMU


def _embed_chart_images(contents: dict[str, bytes], names: list[str], images: list[bytes], anchor_row: int) -> None:
    """Embute até 2 PNGs de gráfico (gerados no navegador) como imagens no
    drawing da planilha, lado a lado, reaproveitando o mesmo mecanismo que já
    embute a logo (xl/media + relationship + âncora em drawing1.xml) — nunca
    gráfico nativo do Excel, que exigiria autorar xl/charts/ do zero."""
    rels_xml = contents[DRAWING_RELS_PART].decode("utf-8")
    drawing_xml = contents[DRAWING_PART].decode("utf-8")
    pics_xml = ""

    for index, png_bytes in enumerate(images):
        media_name = f"xl/media/imageChart{index}.png"
        rel_id = f"rIdChart{index}"
        # mesma coluna base pros dois, deslocando pelo colOff em EMU (independente
        # da largura da coluna do template) — usar colunas de distância fazia os
        # gráficos ficarem muito separados quando as colunas do template são largas
        col_off = index * (_CHART_CX + _CHART_GAP)

        contents[media_name] = png_bytes
        names.append(media_name)

        new_rel = (
            f'<Relationship Id="{rel_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="../media/imageChart{index}.png"/>'
        )
        rels_xml = rels_xml.replace("</Relationships>", new_rel + "</Relationships>")

        pics_xml += (
            "<xdr:oneCellAnchor>"
            f"<xdr:from><xdr:col>1</xdr:col><xdr:colOff>{col_off}</xdr:colOff>"
            f"<xdr:row>{anchor_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
            f'<xdr:ext cx="{_CHART_CX}" cy="{_CHART_CY}"/>'
            "<xdr:pic>"
            "<xdr:nvPicPr>"
            f'<xdr:cNvPr id="{900 + index}" name="GraficoRelatorio{index}"/>'
            "<xdr:cNvPicPr><a:picLocks noChangeAspect=\"1\"/></xdr:cNvPicPr>"
            "</xdr:nvPicPr>"
            f'<xdr:blipFill><a:blip r:embed="{rel_id}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            "<a:stretch><a:fillRect/></a:stretch></xdr:blipFill>"
            f'<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{_CHART_CX}" cy="{_CHART_CY}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
            "</xdr:pic>"
            "<xdr:clientData/>"
            "</xdr:oneCellAnchor>"
        )

    contents[DRAWING_RELS_PART] = rels_xml.encode("utf-8")
    drawing_xml = drawing_xml.replace("</xdr:wsDr>", pics_xml + "</xdr:wsDr>")
    contents[DRAWING_PART] = drawing_xml.encode("utf-8")


def generate_report(
    header: ReportHeader,
    groups: list[GroupInput],
    output_path: str,
    chart_image_bar_b64: str | None = None,
    chart_image_pie_b64: str | None = None,
) -> str:
    with zipfile.ZipFile(TEMPLATE_PATH) as zin:
        names = zin.namelist()
        contents = {name: zin.read(name) for name in names}

    sheet_xml = contents[SHEET_PART].decode("utf-8")

    sheet_xml = _replace_header_cell(sheet_xml, "B4", 22, "RELATÓRIO DE HORAS")
    sheet_xml = _replace_header_cell(sheet_xml, "B8", 27, header.project_code)
    sheet_xml = _replace_header_cell(sheet_xml, "C8", 8, header.location_date)
    sheet_xml = _replace_header_cell(sheet_xml, "C9", 16, header.project_name)
    sheet_xml = _replace_header_cell(sheet_xml, "B11", 12, f"Relatório de horas referentes ao mês de {header.month_label}")

    data_rows, group_merges, last_data_row = _build_groups_xml(groups, header.month_label)

    start = sheet_xml.index(f'<row r="{GROUP_START_ROW}"')
    end = sheet_xml.index("</sheetData>")
    sheet_xml = sheet_xml[:start] + "".join(data_rows) + sheet_xml[end:]

    all_merges = ["A14:E14"] + group_merges
    merge_xml = f'<mergeCells count="{len(all_merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in all_merges) + "</mergeCells>"
    sheet_xml, merge_count = re.subn(
        r"<mergeCells count=\"\d+\">.*?</mergeCells>", merge_xml, sheet_xml, count=1, flags=re.DOTALL
    )
    if merge_count != 1:
        raise ValueError("Não encontrei o bloco <mergeCells> no template.")

    contents[SHEET_PART] = sheet_xml.encode("utf-8")

    offset = last_data_row - ORIGINAL_LAST_DATA_ROW
    chart_images = [
        base64.b64decode(b64)
        for b64 in (chart_image_bar_b64, chart_image_pie_b64)
        if b64
    ]
    # com gráfico, empurra a assinatura mais pra baixo pra reservar o espaço da imagem
    chart_rows = CHART_ROWS_RESERVED if chart_images else 0
    signature_offset = offset + chart_rows
    if DRAWING_PART in contents:
        drawing_xml = contents[DRAWING_PART].decode("utf-8")
        drawing_xml = _shift_signature_drawing(drawing_xml, signature_offset)
        drawing_xml = _replace_signature_names(drawing_xml, header)
        contents[DRAWING_PART] = drawing_xml.encode("utf-8")
        if chart_images:
            _embed_chart_images(
                contents, names, chart_images,
                anchor_row=SIGNATURE_ANCHOR_THRESHOLD + offset - CHART_ROW_LIFT,
            )

    workbook_xml = contents[WORKBOOK_PART].decode("utf-8")
    workbook_xml, calc_pr_count = re.subn(
        r'<calcPr calcId="(\d+)"/>', r'<calcPr calcId="\1" fullCalcOnLoad="1"/>', workbook_xml
    )
    if calc_pr_count != 1:
        raise ValueError("Não encontrei o elemento <calcPr> no template.")
    print_area_row = SIGNATURE_ANCHOR_THRESHOLD + 5 + signature_offset
    workbook_xml, print_area_count = re.subn(
        r'(<definedName name="_xlnm\.Print_Area"[^>]*>)[^<]*(</definedName>)',
        lambda m: f"{m.group(1)}'Relatório de horas'!$B$8:$C${print_area_row}{m.group(2)}",
        workbook_xml,
    )
    if print_area_count != 1:
        raise ValueError("Não encontrei o Print_Area no template.")
    contents[WORKBOOK_PART] = workbook_xml.encode("utf-8")

    if CALC_CHAIN_PART in contents:
        del contents[CALC_CHAIN_PART]
    workbook_rels = contents[WORKBOOK_RELS_PART].decode("utf-8")
    workbook_rels = re.sub(r'<Relationship[^>]*Target="calcChain\.xml"[^>]*/>', "", workbook_rels)
    contents[WORKBOOK_RELS_PART] = workbook_rels.encode("utf-8")

    content_types = contents[CONTENT_TYPES_PART].decode("utf-8")
    content_types = re.sub(r'<Override PartName="/xl/calcChain\.xml"[^>]*/>', "", content_types)
    contents[CONTENT_TYPES_PART] = content_types.encode("utf-8")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            if name == CALC_CHAIN_PART:
                continue
            zout.writestr(name, contents[name])

    return output_path
