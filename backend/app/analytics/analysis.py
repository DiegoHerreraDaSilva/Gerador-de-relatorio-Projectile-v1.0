"""Análises compostas (rota `analysis`). O planner do Claude só escolhe
QUAL análise, métrica, meses e itens; a execução é Python sobre o Query
Engine — variação, diferença e percentuais calculados aqui, nunca pelo modelo.

- compare_periods: mesma métrica em dois meses diferentes;
- compare_items: clientes ou colaboradores citados, entre si, num período."""
from __future__ import annotations

from . import query_engine
from .query_engine import Filters, HoursSource
from .semantic_model import DIMENSIONS, fmt_hours, fmt_number

MAX_CHANGES = 15
MAX_ITEMS = 8
ITEM_INTENTS = {"client": "hours_by_client", "employee": "hours_by_employee"}


def _pct(before: float, after: float) -> float | None:
    return round((after - before) / before * 100, 1) if before else None


def compare_periods(metric: str, filters_a: Filters, filters_b: Filters, hours: HoursSource, max_rows: int) -> dict:
    a = query_engine.run(metric, filters_a, hours, max_rows)
    b = query_engine.run(metric, filters_b, hours, max_rows)
    label_a, label_b = filters_a.period.label, filters_b.period.label
    summary = {
        "analysis": "compare_periods",
        "metric": metric,
        "period_a": label_a,
        "period_b": label_b,
        "client": filters_b.client,
        "employee": filters_b.employee,
        "total_a": a.total,
        "total_b": b.total,
        "total_change": round((b.total or 0) - (a.total or 0), 2),
        "total_change_percent": _pct(a.total or 0, b.total or 0),
    }
    if a.dimension is None:
        return {"summary": summary, "changes": [], "dimension": None}

    values_a = {row["label"]: row["value"] for row in a.rows}
    values_b = {row["label"]: row["value"] for row in b.rows}
    changes = []
    for label in sorted(set(values_a) | set(values_b)):
        before, after = values_a.get(label, 0.0), values_b.get(label, 0.0)
        changes.append({
            "label": label,
            "before": before,
            "after": after,
            "change": round(after - before, 2),
            "change_percent": _pct(before, after),
        })
    changes.sort(key=lambda item: (-abs(item["change"]), item["label"]))
    summary["dimension"] = DIMENSIONS.get(a.dimension, a.dimension)
    summary["top_increases"] = [c for c in changes if c["change"] > 0][:5]
    summary["top_decreases"] = [c for c in changes if c["change"] < 0][:5]
    return {"summary": summary, "changes": changes, "dimension": a.dimension}


def compare_items(kind: str, items: list[str], filters: Filters, hours: HoursSource, max_rows: int) -> dict:
    intent = ITEM_INTENTS[kind]
    result = query_engine.run(intent, filters, hours, max_rows)
    values = {row["label"]: row["value"] for row in result.rows}
    rows = [{"label": item, "value": round(values.get(item, 0.0), 2)} for item in items]
    rows.sort(key=lambda row: (-row["value"], row["label"]))
    selection_total = round(sum(row["value"] for row in rows), 2)
    for row in rows:
        row["percent_of_compared_items"] = round(row["value"] / selection_total * 100, 1) if selection_total else None
    leader, second = rows[0], rows[1]
    summary = {
        "analysis": "compare_items",
        "dimension": DIMENSIONS.get(result.dimension, result.dimension),
        "period": filters.period.label,
        "items": rows,
        "total_of_compared_items": selection_total,
        "leader": leader["label"],
        "difference_leader_vs_second": round(leader["value"] - second["value"], 2),
        "leader_vs_second_percent": _pct(second["value"], leader["value"]),
    }
    return {"summary": summary, "rows": rows, "dimension": result.dimension}


def visualizations(result: dict) -> list[dict]:
    summary = result["summary"]
    if summary["analysis"] == "compare_items":
        return [{
            "type": "horizontal_bar",
            "title": f"Horas por {summary['dimension'].lower()} — {summary['period']}",
            "categories": [row["label"] for row in result["rows"]],
            "series": [{"name": "Horas", "data": [row["value"] for row in result["rows"]]}],
            "unit": "h",
        }]
    if result["dimension"] is None:
        return [{
            "type": "bar",
            "title": f"Horas — {summary['period_a']} x {summary['period_b']}",
            "categories": [summary["period_a"], summary["period_b"]],
            "series": [{"name": "Horas", "data": [summary["total_a"], summary["total_b"]]}],
            "unit": "h",
        }]
    top = result["changes"][:MAX_CHANGES]
    if not top:
        return []
    return [{
        "type": "horizontal_bar",
        "title": f"Variação de horas por {summary['dimension'].lower()} — {summary['period_a']} → {summary['period_b']}",
        "categories": [c["label"] for c in top],
        "series": [{"name": "Variação (h)", "data": [c["change"] for c in top]}],
        "unit": "h",
    }]


def table(result: dict) -> dict | None:
    summary = result["summary"]
    if summary["analysis"] == "compare_items":
        return {
            "title": f"{summary['dimension']} — {summary['period']}",
            "columns": [summary["dimension"], "Horas", "% entre os comparados"],
            "rows": [[row["label"], row["value"], row["percent_of_compared_items"]] for row in result["rows"]],
            "truncated": False,
        }
    if result["dimension"] is None:
        return None
    return {
        "title": f"{summary['dimension']} — {summary['period_a']} x {summary['period_b']}",
        "columns": [summary["dimension"], summary["period_a"], summary["period_b"], "Variação (h)", "Variação (%)"],
        "rows": [[c["label"], c["before"], c["after"], c["change"], c["change_percent"]] for c in result["changes"]],
        "truncated": False,
    }


def fallback_text(result: dict) -> str:
    """Texto sem LLM pra análise — usado se o finalizer falhar ou inventar número."""
    s = result["summary"]
    if s["analysis"] == "compare_items":
        parts = ", ".join(f"{row['label']} {fmt_hours(row['value'])}" for row in result["rows"])
        text = f"Em {s['period']}: {parts}."
        if s["difference_leader_vs_second"] > 0:
            text += (
                f" {s['leader']} teve {fmt_hours(s['difference_leader_vs_second'])} a mais que "
                f"{result['rows'][1]['label']}."
            )
        return text
    pct = s["total_change_percent"]
    pct_text = f" ({'+' if (pct or 0) > 0 else ''}{fmt_number(pct)}%)" if pct is not None else ""
    text = (
        f"De {s['period_a']} para {s['period_b']}, as horas foram de {fmt_hours(s['total_a'])} "
        f"para {fmt_hours(s['total_b'])}{pct_text}."
    )
    if s.get("top_increases"):
        up = s["top_increases"][0]
        text += f" Maior aumento: {up['label']} (+{fmt_hours(up['change'])})."
    if s.get("top_decreases"):
        down = s["top_decreases"][0]
        text += f" Maior queda: {down['label']} ({fmt_hours(down['change'])})."
    return text
