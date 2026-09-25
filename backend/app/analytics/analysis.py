"""Comparação entre períodos (rota `analysis`, ferramenta `compare_periods`
do planner). Roda a MESMA consulta cruzada nos dois períodos e calcula a
variação em Python — o Claude só escolhe medida, quebra, filtros e meses, e
depois descreve números que já vêm prontos.

Comparar itens entre si num período só ("Mercedes x Lauer em julho") não
é mais uma análise à parte: é uma consulta cruzada com os itens no filtro e
agrupada pela mesma dimensão (`crossquery` + `cross_output._compared_items`)."""
from __future__ import annotations

from . import crossquery
from .catalog import DIMENSIONS, MEASURES
from .cross_output import UNIT_SYMBOL, fmt_value
from .crossquery import QuerySpec
from .facts import DataSources
from .semantic_model import fmt_number

MAX_CHANGES = 15


def _pct(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or not before:
        return None
    return round((after - before) / abs(before) * 100, 1)


def _change(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return round(after - before, 2)


def compare_periods(spec_a: QuerySpec, spec_b: QuerySpec, sources: DataSources, max_rows: int) -> dict:
    a = crossquery.execute(spec_a, sources, max_rows)
    b = crossquery.execute(spec_b, sources, max_rows)
    measure = spec_b.measures[0]
    info = MEASURES[measure]
    total_a, total_b = a.totals.get(measure), b.totals.get(measure)
    summary = {
        "analysis": "compare_periods",
        "measure": info.label,
        "unit": UNIT_SYMBOL[info.unit],
        "period_a": spec_a.period.label,
        "period_b": spec_b.period.label,
        "filters": spec_b.filter_values(),
        "total_a": total_a,
        "total_b": total_b,
        # percentual (performance, % não faturável) varia em pontos, não em %
        "total_change": _change(total_a, total_b),
        "total_change_percent": None if info.unit == "percent" else _pct(total_a, total_b),
    }
    dimension = spec_b.group_by[0] if spec_b.group_by else None
    if dimension is None:
        return {"summary": summary, "changes": [], "dimension": None, "measure": measure}

    empty = 0.0 if info.additive else None
    values_a = {row.labels[0]: row.values.get(measure) for row in a.rows}
    values_b = {row.labels[0]: row.values.get(measure) for row in b.rows}
    changes = []
    for label in sorted(set(values_a) | set(values_b)):
        before, after = values_a.get(label, empty), values_b.get(label, empty)
        changes.append({
            "label": label, "before": before, "after": after,
            "change": _change(before, after),
            "change_percent": None if info.unit == "percent" else _pct(before, after),
        })
    changes.sort(key=lambda item: (item["change"] is None, -abs(item["change"] or 0), item["label"]))
    summary["dimension"] = DIMENSIONS[dimension].label
    summary["top_increases"] = [c for c in changes if (c["change"] or 0) > 0][:5]
    summary["top_decreases"] = [c for c in changes if (c["change"] or 0) < 0][:5]
    return {"summary": summary, "changes": changes, "dimension": dimension, "measure": measure}


def visualizations(result: dict) -> list[dict]:
    summary = result["summary"]
    unit = summary["unit"]
    if result["dimension"] is None:
        if summary["total_a"] is None and summary["total_b"] is None:
            return []
        return [{
            "type": "bar",
            "title": f"{summary['measure']} — {summary['period_a']} x {summary['period_b']}",
            "categories": [summary["period_a"], summary["period_b"]],
            "series": [{"name": summary["measure"], "data": [summary["total_a"], summary["total_b"]]}],
            "unit": unit,
        }]
    top = [c for c in result["changes"] if c["change"] is not None][:MAX_CHANGES]
    if not top:
        return []
    change_unit = "p.p." if unit == "%" else unit
    return [{
        "type": "horizontal_bar",
        "title": (
            f"Variação de {summary['measure'].lower()} por {summary['dimension'].lower()} — "
            f"{summary['period_a']} → {summary['period_b']}"
        ),
        "categories": [c["label"] for c in top],
        "series": [{"name": f"Variação ({change_unit})", "data": [c["change"] for c in top]}],
        "unit": change_unit,
    }]


def table(result: dict) -> dict | None:
    summary = result["summary"]
    if result["dimension"] is None:
        return None
    unit = MEASURES[result["measure"]].unit
    percent = unit == "percent"
    return {
        "title": f"{summary['dimension']} — {summary['period_a']} x {summary['period_b']}",
        "columns": [summary["dimension"], summary["period_a"], summary["period_b"],
                    "Variação (p.p.)" if percent else f"Variação ({summary['unit'] or 'qtd.'})",
                    *([] if percent else ["Variação (%)"])],
        "column_types": ["text", unit, unit, unit, *([] if percent else ["percent"])],
        "rows": [
            [c["label"], c["before"], c["after"], c["change"], *([] if percent else [c["change_percent"]])]
            for c in result["changes"]
        ],
        "totals": ["Total", summary["total_a"], summary["total_b"], summary["total_change"],
                   *([] if percent else [summary["total_change_percent"]])],
        "truncated": False,
    }


def _fmt_change(value: float | None, unit: str) -> str:
    """Variação de percentual é em pontos percentuais, não em %."""
    return f"{fmt_number(value)} p.p." if unit == "percent" else fmt_value(value, unit)


def fallback_text(result: dict) -> str:
    """Texto sem LLM pra análise — usado se o finalizer falhar ou inventar número."""
    s = result["summary"]
    unit = MEASURES[result["measure"]].unit
    before, after = fmt_value(s["total_a"], unit), fmt_value(s["total_b"], unit)
    if unit == "percent" and s["total_change"] is not None:
        sign = "+" if s["total_change"] > 0 else ""
        change = f" ({sign}{fmt_number(s['total_change'])} p.p.)"
    elif s["total_change_percent"] is not None:
        sign = "+" if s["total_change_percent"] > 0 else ""
        change = f" ({sign}{fmt_number(s['total_change_percent'])}%)"
    else:
        change = ""
    label = s["measure"].lower()
    if label == "horas":
        text = f"De {s['period_a']} para {s['period_b']}, as horas foram de {before} para {after}{change}."
    else:
        text = f"De {s['period_a']} para {s['period_b']}, {label} foi de {before} para {after}{change}."
    if s.get("top_increases"):
        up = s["top_increases"][0]
        text += f" Maior aumento: {up['label']} (+{_fmt_change(up['change'], unit)})."
    if s.get("top_decreases"):
        down = s["top_decreases"][0]
        text += f" Maior queda: {down['label']} ({_fmt_change(down['change'], unit)})."
    return text
