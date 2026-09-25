"""Resultado da consulta cruzada → gráficos, tabelas, texto sem IA e o
resumo agregado que vai pro Claude. Tudo determinístico: a IA nunca escolhe
tipo de gráfico nem manda HTML/SVG — a forma do resultado decide.

Gráficos (contrato em `frontend/.../VisualizationRenderer.tsx`):
- sem dimensão → `kpi` (um por medida);
- mês → `line` (uma série por medida de mesma unidade);
- tipo/centro de custo/status com uma medida somável → `donut`;
- ranking → `horizontal_bar` (várias medidas de mesma unidade = barras agrupadas);
- duas dimensões com mês → `line` multissérie (até 5 + "Outros") ou
  `heatmap` quando há muitas linhas;
- duas categorias → `horizontal_bar` empilhado (até 5 séries + "Outros"),
  ou `heatmap` pra medida que não soma (percentual, contagem distinta).

Cor segue a série, nunca o ranking, e a cauda vira "Outros" em vez de
ciclar a paleta (o total continua fechando)."""
from __future__ import annotations

import json

from .catalog import DATASET_LABELS, DIMENSIONS, MEASURES, STATUSES
from .crossquery import CrossResult, CrossRow, label_for, period_months
from .semantic_model import fmt_hours, fmt_number

UNIT_SYMBOL = {"hours": "h", "percent": "%", "count": ""}
SMALL_DIMENSIONS = {"billing_type", "cost_center", "status"}
MAX_BARS = 15
MAX_STACK_CATEGORIES = 12
MAX_SERIES = 5
MAX_HEATMAP_ROWS = 20
MAX_PIVOT_COLUMNS = 13
MAX_VISUALIZATIONS = 4
OTHERS = "Outros"
_TOP_IN_TEXT = 3


def fmt_value(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "hours":
        return fmt_hours(value)
    if unit == "percent":
        return f"{fmt_number(value)}%"
    return fmt_number(value)


def _title(result: CrossResult, base: str) -> str:
    return f"{base} — {result.spec.period.label}"


def _by_unit(measures: list[str]) -> list[list[str]]:
    groups: dict[str, list[str]] = {}
    for m in measures:
        groups.setdefault(MEASURES[m].unit, []).append(m)
    return list(groups.values())


def _chart_label(measures: list[str]) -> str:
    return " x ".join(MEASURES[m].label for m in measures)


def _ranked_values(result: CrossResult, index: int, measure: str) -> list[str]:
    """Valores da dimensão `index` ordenados pelo total da medida (soma se
    somável, maior valor se não)."""
    totals: dict[str, float] = {}
    for row in result.rows:
        value = row.values.get(measure) or 0
        key = row.labels[index]
        totals[key] = totals.get(key, 0.0) + value if MEASURES[measure].additive else max(totals.get(key, value), value)
    return sorted(totals, key=lambda k: (-totals[k], k))


def _column_order(result: CrossResult, index: int, measure: str) -> list[str]:
    dim = result.spec.group_by[index]
    if dim == "month":
        return [label_for("month", m) for m in period_months(result.spec.period)]
    if dim == "status":
        present = {row.labels[index] for row in result.rows}
        return [label for label in STATUSES.values() if label in present]
    return _ranked_values(result, index, measure)


def _cell_map(result: CrossResult, measure: str) -> dict[tuple[str, str], float | None]:
    return {(row.labels[0], row.labels[1]): row.values.get(measure) for row in result.rows}


def _series_with_others(result: CrossResult, row_index: int, col_values: list[str], row_values: list[str], measure: str):
    """Séries (uma por valor de `row_index`) sobre as categorias
    `col_values`; além de MAX_SERIES, soma o resto em "Outros"."""
    cells = _cell_map(result, measure)
    additive = MEASURES[measure].additive

    def cell(series_value: str, category: str):
        key = (series_value, category) if row_index == 0 else (category, series_value)
        value = cells.get(key)
        return (value or 0.0) if additive else value

    # nunca mais que MAX_SERIES com cor própria: a paleta tem 5 cores + a de
    # "Outros", e a 6ª série repetia a cor da 1ª (mesmo se o resto for 1 só)
    shown = row_values[:MAX_SERIES]
    series = [{"name": value, "data": [cell(value, c) for c in col_values]} for value in shown]
    rest = [value for value in row_values if value not in shown]
    if rest and additive:
        series.append({
            "name": OTHERS, "tail": True,
            "data": [round(sum(cell(value, c) or 0 for value in rest), 2) for c in col_values],
        })
    return series


def _heatmap(result: CrossResult, row_index: int, measure: str, title: str) -> dict:
    col_index = 1 - row_index
    rows = _ranked_values(result, row_index, measure)[:MAX_HEATMAP_ROWS]
    columns = _column_order(result, col_index, measure)
    cells = _cell_map(result, measure)
    additive = MEASURES[measure].additive

    def cell(r, c):
        value = cells.get((r, c) if row_index == 0 else (c, r))
        return (value or 0.0) if additive and value is None else value

    return {
        "type": "heatmap",
        "title": title,
        "rows": rows,
        "columns": columns,
        "values": [[cell(r, c) for c in columns] for r in rows],
        "unit": UNIT_SYMBOL[MEASURES[measure].unit],
    }


def build_visualizations(result: CrossResult) -> list[dict]:
    spec = result.spec
    dims = spec.group_by
    if not dims:
        return [
            {"type": "kpi", "title": _title(result, MEASURES[m].label), "value": result.totals[m],
             "unit": UNIT_SYMBOL[MEASURES[m].unit]}
            for m in spec.measures if result.totals.get(m) is not None
        ][:MAX_VISUALIZATIONS]
    if not result.rows:
        return []

    if len(dims) == 1:
        dim = DIMENSIONS[dims[0]]
        rows = result.rows
        if dims[0] == "month":
            charts = []
            for group in _by_unit(spec.measures):
                charts.append({
                    "type": "line" if len(rows) > 1 else "bar",
                    "title": _title(result, f"{_chart_label(group)} por mês"),
                    "categories": [row.labels[0] for row in rows],
                    "series": [{"name": MEASURES[m].label, "data": [row.values.get(m) for row in rows]} for m in group],
                    "unit": UNIT_SYMBOL[MEASURES[group[0]].unit],
                })
            return charts[:MAX_VISUALIZATIONS]
        first = spec.measures[0]
        if dims[0] in SMALL_DIMENSIONS and len(spec.measures) == 1 and MEASURES[first].additive:
            return [{
                "type": "donut",
                "title": _title(result, f"{MEASURES[first].label} por {dim.label.lower()}"),
                "categories": [row.labels[0] for row in rows],
                "series": [{"name": MEASURES[first].label, "data": [row.values.get(first) for row in rows]}],
                "unit": UNIT_SYMBOL[MEASURES[first].unit],
            }]
        top = rows[:MAX_BARS]
        suffix = f" (top {len(top)} de {result.group_count})" if result.group_count > len(top) else ""
        charts = []
        for group in _by_unit(spec.measures):
            values = [[row.values.get(m) for row in top] for m in group]
            if all(v is None for serie in values for v in serie):
                continue
            charts.append({
                "type": "horizontal_bar",
                "title": _title(result, f"{_chart_label(group)} por {dim.label.lower()}{suffix}"),
                "categories": [row.labels[0] for row in top],
                "series": [{"name": MEASURES[m].label, "data": data} for m, data in zip(group, values)],
                "unit": UNIT_SYMBOL[MEASURES[group[0]].unit],
            })
        return charts[:MAX_VISUALIZATIONS]

    # duas dimensões — o gráfico usa a 1ª medida; a tabela mostra todas
    measure = spec.measures[0]
    info = MEASURES[measure]
    d1, d2 = (DIMENSIONS[d] for d in dims)
    title = _title(result, f"{info.label} por {d1.label.lower()} e {d2.label.lower()}")
    if "month" in dims:
        other_index = 0 if dims[1] == "month" else 1
        others = _ranked_values(result, other_index, measure)
        months = _column_order(result, 1 - other_index, measure)
        if len(others) <= MAX_SERIES + 1 or (info.additive and len(others) <= 12):
            return [{
                "type": "line",
                "title": title,
                "categories": months,
                "series": _series_with_others(result, other_index, months, others, measure),
                "unit": UNIT_SYMBOL[info.unit],
            }]
        return [_heatmap(result, other_index, measure, title)]
    if not info.additive:
        return [_heatmap(result, 0, measure, title)]
    categories = _ranked_values(result, 0, measure)[:MAX_STACK_CATEGORIES]
    series_values = _ranked_values(result, 1, measure)
    series = _series_with_others(result, 1, categories, series_values, measure)
    suffix = f" (top {len(categories)})" if len(_ranked_values(result, 0, measure)) > len(categories) else ""
    return [{
        "type": "horizontal_bar",
        "stacked": True,
        "title": title + suffix,
        "categories": categories,
        "series": series,
        "unit": UNIT_SYMBOL[info.unit],
    }]


# --- tabelas --------------------------------------------------------------


def build_tables(result: CrossResult) -> list[dict]:
    spec = result.spec
    dims = spec.group_by
    if not dims:
        if len(spec.measures) < 2:
            return []
        return [{
            "title": _title(result, "Resumo"),
            "columns": ["Medida", "Valor"],
            "column_types": ["text", "text"],
            "rows": [[MEASURES[m].label, fmt_value(result.totals[m], MEASURES[m].unit)] for m in spec.measures],
            "truncated": False,
        }]
    if not result.rows:
        return []
    measure_types = [MEASURES[m].unit for m in spec.measures]
    first = spec.measures[0]
    total_label = "Total exibido" if result.cut else "Total"

    if len(dims) == 1:
        dim = DIMENSIONS[dims[0]]
        with_share = MEASURES[first].additive and any(row.share is not None for row in result.rows)
        share_label = "% do total" if len(spec.measures) == 1 else f"% do total ({MEASURES[first].label.lower()})"
        columns = [dim.label] + [MEASURES[m].label for m in spec.measures] + ([share_label] if with_share else [])
        types = ["text"] + measure_types + (["percent"] if with_share else [])
        rows = [
            [row.labels[0]] + [row.values.get(m) for m in spec.measures] + ([row.share] if with_share else [])
            for row in result.rows
        ]
        totals = ["Total"] + [result.totals.get(m) for m in spec.measures] + ([100.0 if with_share else None] if with_share else [])
        return [{
            "title": _title(result, f"{dim.label}"),
            "columns": columns, "column_types": types, "rows": rows,
            "totals": totals if not result.cut else None,
            "truncated": result.truncated,
        }]

    # duas dimensões: tabela cruzada quando dá (1 medida, colunas poucas)
    column_index = None
    if len(spec.measures) == 1:
        if "month" in dims:
            column_index = dims.index("month")
        else:
            counts = [len({row.labels[i] for row in result.rows}) for i in (0, 1)]
            candidate = 1 if counts[1] <= counts[0] else 0
            if counts[candidate] <= MAX_PIVOT_COLUMNS:
                column_index = candidate
    if column_index is not None:
        row_index = 1 - column_index
        info = MEASURES[first]
        columns_values = _column_order(result, column_index, first)[:MAX_PIVOT_COLUMNS]
        row_values = list(dict.fromkeys(row.labels[row_index] for row in result.rows))
        cells = _cell_map(result, first)

        def cell(r, c):
            value = cells.get((r, c) if row_index == 0 else (c, r))
            return (value if value is not None else 0.0) if info.additive else value

        rows = []
        for r in row_values:
            values = [cell(r, c) for c in columns_values]
            rows.append([r] + values + ([round(sum(v or 0 for v in values), 2)] if info.additive else []))
        totals = None
        if info.additive:
            column_totals = [round(sum(row[i + 1] or 0 for row in rows), 2) for i in range(len(columns_values))]
            totals = [total_label] + column_totals + [round(sum(column_totals), 2)]
        return [{
            "title": _title(result, f"{info.label} — {DIMENSIONS[dims[row_index]].label} x {DIMENSIONS[dims[column_index]].label}"),
            "columns": [DIMENSIONS[dims[row_index]].label] + columns_values + (["Total"] if info.additive else []),
            "column_types": ["text"] + [info.unit] * len(columns_values) + ([info.unit] if info.additive else []),
            "rows": rows,
            "totals": totals,
            "truncated": result.truncated,
        }]

    columns = [DIMENSIONS[d].label for d in dims] + [MEASURES[m].label for m in spec.measures]
    rows = [list(row.labels) + [row.values.get(m) for m in spec.measures] for row in result.rows]
    totals = [total_label, ""] + [result.totals.get(m) for m in spec.measures]
    return [{
        "title": _title(result, " x ".join(DIMENSIONS[d].label for d in dims)),
        "columns": columns,
        "column_types": ["text", "text"] + measure_types,
        "rows": rows,
        "totals": totals if not result.cut else None,
        "truncated": result.truncated,
    }]


# --- texto sem IA -------------------------------------------------------------

_FILTER_LABELS = {
    "clients": ("cliente", "clientes"),
    "projects": ("projeto", "projetos"),
    "employees": ("colaborador", "colaboradores"),
    "packages": ("pacote", "pacotes"),
    "cost_centers": ("centro de custo", "centros de custo"),
    "statuses": ("status", "status"),
    "billing_type": ("só horas", "só horas"),
}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def scope_phrase(result: CrossResult) -> str:
    parts = [result.spec.period.phrase]
    for key, values in result.spec.filter_values().items():
        singular, plural = _FILTER_LABELS[key]
        if key == "billing_type":
            parts.append("só horas faturáveis" if values[0] == "Faturável" else "só horas não faturáveis")
        else:
            # "com “Estribo” no nome (4)" já são vários projetos
            many = len(values) > 1 or (key == "projects" and bool(result.spec.project_match))
            parts.append(f"{plural if many else singular} {_join(values)}")
    return ", ".join(parts)


def _count(n: int, dim) -> str:
    return f"{n} {dim.label.lower() if n == 1 else dim.plural}"


def _value(row: CrossRow, measure: str) -> str:
    return fmt_value(row.values.get(measure), MEASURES[measure].unit)


def _compared_items(result: CrossResult) -> bool:
    """"Mercedes x Lauer em julho": agrupou pela mesma dimensão que filtrou,
    com 2 a 8 itens."""
    spec = result.spec
    if len(spec.group_by) != 1:
        return False
    key = DIMENSIONS[spec.group_by[0]].filter_key
    values = getattr(spec, key, None) if key in ("clients", "projects", "employees", "packages") else None
    return bool(values) and 2 <= len(values) <= 8 and len(result.rows) >= 2


def _cap(text: str) -> str:
    return text[0].upper() + text[1:]


def _totals_line(result: CrossResult) -> str:
    """"trabalhadas 3.083,2 h; faturadas 2.728,8 h; performance -11,5%"."""
    if result.spec.measures == ["hours"]:
        return fmt_hours(result.totals.get("hours"))
    return "; ".join(
        f"{MEASURES[m].label.replace(' (h)', '').lower()} {fmt_value(result.totals.get(m), MEASURES[m].unit)}"
        for m in result.spec.measures if result.totals.get(m) is not None
    )


def _leaders(result: CrossResult, measure: str, limit: int = 4) -> str:
    """"quem trabalhou mais EM CADA cliente": o maior da 2ª dimensão dentro
    de cada valor da 1ª (na ordem da tabela)."""
    best: dict[str, CrossRow] = {}
    for row in result.rows:
        value = row.values.get(measure)
        current = best.get(row.labels[0])
        if value is not None and (current is None or value > (current.values.get(measure) or 0)):
            best[row.labels[0]] = row
    items = [f"{anchor}: {row.labels[1]} ({_value(row, measure)})" for anchor, row in list(best.items())[:limit]]
    more = f" e mais {len(best) - limit}" if len(best) > limit else ""
    return "; ".join(items) + more


def _send_status_reply(result: CrossResult, scope: str, notes: str) -> str:
    """Status por projeto: quantos em cada status e QUAIS não foram enviados
    — é o que a pergunta "quais projetos não enviaram?" quer saber."""
    spec = result.spec
    status_index = spec.group_by.index("status")
    other = spec.group_by[1 - status_index] if len(spec.group_by) == 2 else None
    counts: dict[str, int] = {}
    pending: list[str] = []
    for row in result.rows:
        status = row.labels[status_index]
        counts[status] = counts.get(status, 0) + int(row.values.get("project_months") or 0)
        if other and row.keys[status_index] == "none":
            pending.append(row.labels[1 - status_index])
    plural = {"Enviado": "enviados", "Parcial": "parciais", "Não enviado": "não enviados", "Fechado": "fechados"}
    ordered = [
        f"{counts[label]} {label.lower() if counts[label] == 1 else plural[label]}"
        for label in STATUSES.values() if counts.get(label)
    ]
    total = sum(counts.values())
    text = f"{_cap(scope)}: {', '.join(ordered)} (de {total} {'projeto' if total == 1 else 'projetos'} com hora)."
    if pending:
        shown = pending[:8]
        more = f" e mais {len(pending) - len(shown)}" if len(pending) > len(shown) else ""
        text += f" Não enviados: {', '.join(shown)}{more}."
    return text + notes


def format_reply(result: CrossResult) -> str:
    spec = result.spec
    first = spec.measures[0]
    info = MEASURES[first]
    scope = scope_phrase(result)
    notes = f" {' '.join(result.notes)}" if result.notes else ""
    threshold = f"Com {spec.threshold.describe()}: " if spec.threshold else ""
    only_hours = spec.measures == ["hours"]

    if not spec.group_by:
        if only_hours:
            return f"Foram apontadas {fmt_hours(result.totals['hours'])} {scope}.{notes}"
        return f"{_cap(scope)}: {_totals_line(result)}.{notes}"

    if not result.rows:
        return f"{threshold}Não encontrei dados {scope}.{notes}"

    if spec.dataset == "send_status" and "status" in spec.group_by and spec.measures == ["project_months"]:
        return _send_status_reply(result, scope, notes)

    if len(spec.group_by) == 1:
        dim = DIMENSIONS[spec.group_by[0]]
        if _compared_items(result) and info.unit == "hours":
            parts = ", ".join(f"{row.labels[0]} {_value(row, first)}" for row in result.rows)
            text = f"{_cap(scope)}: {parts}."
            leader, second = result.rows[0], result.rows[1]
            difference = (leader.values.get(first) or 0) - (second.values.get(first) or 0)
            if difference > 0:
                text += f" {leader.labels[0]} teve {fmt_hours(round(difference, 2))} a mais que {second.labels[0]}."
            return text + notes
        if spec.group_by == ["month"] and not spec.top_n and not spec.sort_by:
            valued = [row for row in result.rows if row.values.get(first) is not None]
            if not valued:
                return f"Não encontrei dados {scope}.{notes}"
            best = max(valued, key=lambda row: row.values[first])
            if info.additive and only_hours:
                return (
                    f"Total de {fmt_hours(result.totals[first])} {scope}, distribuído em "
                    f"{len(result.rows)} meses (detalhe na tabela). Maior: {best.labels[0]} ({_value(best, first)}).{notes}"
                )
            if info.additive:
                return (
                    f"{_cap(scope)}: {_totals_line(result)}, em {len(result.rows)} meses. "
                    f"Maior {info.label.lower()}: {best.labels[0]} ({_value(best, first)}).{notes}"
                )
            worst = min(valued, key=lambda row: row.values[first])
            return (
                f"{info.label} por mês {scope}: maior em {best.labels[0]} ({_value(best, first)}), "
                f"menor em {worst.labels[0]} ({_value(worst, first)}).{notes}"
            )
        # ranking: a lista segue a medida pela qual foi ordenado
        sort_measure = spec.sort_by or first
        order = "Maiores" if spec.sort_order == "desc" else "Menores"
        if sort_measure != first or not only_hours:
            order += f" em {MEASURES[sort_measure].label.lower()}"
        top = "; ".join(f"{row.labels[0]} ({_value(row, sort_measure)})" for row in result.rows[:_TOP_IN_TEXT])
        more = " Mostrando só os primeiros." if result.truncated else ""
        count = _count(result.group_count, dim)
        if threshold:
            return f"{threshold}{count} {scope}. {order}: {top}.{more}{notes}"
        if only_hours:
            return f"Total de {fmt_hours(result.totals[first])} {scope}, em {count}. {order}: {top}.{more}{notes}"
        totals = _totals_line(result)
        totals = f" Total: {totals}." if totals else ""
        return f"{_cap(count)} {scope}.{totals} {order}: {top}.{more}{notes}"

    d1, d2 = (DIMENSIONS[d] for d in spec.group_by)
    count1 = len({row.labels[0] for row in result.rows})
    count2 = len({row.labels[1] for row in result.rows})
    best = max((row for row in result.rows if row.values.get(first) is not None),
               key=lambda row: row.values[first], default=None)
    text = (
        f"{threshold}{info.label} por {d1.label.lower()} e {d2.label.lower()} {scope}: "
        f"{_count(count1, d1)} x {_count(count2, d2)}."
    )
    if "month" not in spec.group_by and info.additive and count1 > 1:
        text += f" Maior {d2.label.lower()} em cada {d1.label.lower()} — {_leaders(result, first)}."
    elif best:
        text += f" Maior combinação: {best.labels[0]} — {best.labels[1]} ({_value(best, first)})."
    totals = _totals_line(result)
    if totals:
        text += f" Total: {totals}."
    return text + notes


# --- resumo pro Claude -----------------------------------------------------------


def compact_for_claude(result: CrossResult, max_bytes: int) -> dict:
    """Só números já calculados — participação, acumulado, top 3 e o resto,
    totais por dimensão. O Claude não soma nem calcula percentual (ver
    `_SYSTEM`); o grounding descarta o texto se ele tentar."""
    spec = result.spec
    first = spec.measures[0]
    additive = MEASURES[first].additive
    total_first = result.totals.get(first)
    rows, cumulative = [], 0.0
    for row in result.rows:
        item = {
            "dims": {DIMENSIONS[d].label: label for d, label in zip(spec.group_by, row.labels)},
            "values": {MEASURES[m].label: row.values.get(m) for m in spec.measures},
        }
        if row.share is not None and len(spec.group_by) == 1:
            cumulative += row.values.get(first) or 0
            item["share_percent"] = row.share
            item["cumulative_share_percent"] = round(cumulative / total_first * 100, 1) if total_first else None
        rows.append(item)
    compact = {
        "source": DATASET_LABELS[spec.dataset],
        "period": spec.period.label,
        "filters": spec.filter_values(),
        "threshold": spec.threshold.describe() if spec.threshold else None,
        "measures": {MEASURES[m].label: {"unit": UNIT_SYMBOL[MEASURES[m].unit], "meaning": MEASURES[m].description}
                     for m in spec.measures},
        "group_by": [DIMENSIONS[d].label for d in spec.group_by],
        "totals": {MEASURES[m].label: result.totals.get(m) for m in spec.measures},
        "groups": result.group_count,
        "rows": rows,
        "notes": result.notes,
    }
    if len(spec.group_by) == 1 and additive and total_first and len(result.rows) > 3 and spec.group_by != ["month"]:
        top = sum(row.values.get(first) or 0 for row in result.rows[:3])
        rest = total_first - top
        compact["top_3"] = {"value": round(top, 2), "share_percent": round(top / total_first * 100, 1)}
        compact["others_after_top_3"] = {
            "count": result.group_count - 3, "value": round(rest, 2),
            "share_percent": round(rest / total_first * 100, 1),
        }
    if len(spec.group_by) == 2 and additive:
        for index, dim in enumerate(spec.group_by):
            totals: dict[str, float] = {}
            for row in result.rows:
                totals[row.labels[index]] = round(totals.get(row.labels[index], 0.0) + (row.values.get(first) or 0), 2)
            compact[f"total_by_{dim}"] = dict(sorted(totals.items(), key=lambda kv: -kv[1]))
    while len(json.dumps(compact, ensure_ascii=False).encode()) > max_bytes and len(compact["rows"]) > 5:
        compact["rows"] = compact["rows"][: len(compact["rows"]) // 2]
        compact["rows_truncated"] = True
    return compact
