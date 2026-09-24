"""Resultado → contrato de visualização (JSON) que o React desenha. Regras
determinísticas, sem chamada de IA: número único → `kpi`; série no tempo →
`line`; ranking (cliente, projeto, pessoa, pacote) → `horizontal_bar`;
categorias curtas (formato) → `bar`. Toda resposta com linhas também tem
tabela — o gráfico é pra olhar, a tabela é pra conferir.

A IA nunca manda HTML/SVG/JS; no máximo o planner pede um tipo, e isto aqui
valida e monta."""
from __future__ import annotations

from .query_engine import QueryResult
from .semantic_model import DIMENSIONS, UNITS

VISUALIZATION_TYPES = ("kpi", "bar", "horizontal_bar", "line", "table")
MAX_BAR_CATEGORIES = 15
MAX_LINE_POINTS = 24
MAX_VISUALIZATIONS = 3

_METRIC_LABEL = {"hours": "Horas", "count": "Quantidade", "ms": "Tempo médio (ms)"}


def _title(result: QueryResult, base: str) -> str:
    return f"{base} — {result.filters.period.label}"


def build_visualizations(result: QueryResult) -> list[dict]:
    metric = _METRIC_LABEL.get(result.unit, "Valor")
    if result.dimension is None:
        if result.total is None:
            return []
        return [{
            "type": "kpi",
            "title": _title(result, metric),
            "value": result.total,
            "unit": UNITS.get(result.unit, ""),
        }]

    rows = [row for row in result.rows if row.get("value") is not None]
    if not rows:
        return []
    dimension = DIMENSIONS.get(result.dimension, "Item")

    if result.dimension in ("competence", "month"):
        points = rows[-MAX_LINE_POINTS:]
        chart_type = "line" if len(points) > 1 else "bar"
        return [{
            "type": chart_type,
            "title": _title(result, f"{metric} por {dimension.lower()}"),
            "categories": [row["label"] for row in points],
            "series": [{"name": metric, "data": [row["value"] for row in points]}],
            "unit": UNITS.get(result.unit, ""),
        }]

    top = rows[:MAX_BAR_CATEGORIES]
    chart_type = "bar" if result.dimension == "format" else "horizontal_bar"
    title = f"{metric} por {dimension.lower()}"
    if len(rows) > len(top):
        title += f" (top {len(top)} de {len(rows)})"
    return [{
        "type": chart_type,
        "title": _title(result, title),
        "categories": [row["label"] for row in top],
        "series": [{"name": metric, "data": [row["value"] for row in top]}],
        "unit": UNITS.get(result.unit, ""),
    }]


def build_table(result: QueryResult) -> dict | None:
    if result.dimension is None or not result.rows:
        return None
    metric = _METRIC_LABEL.get(result.unit, "Valor")
    return {
        "title": f"{DIMENSIONS.get(result.dimension, 'Item')} — {result.filters.period.label}",
        "columns": [DIMENSIONS.get(result.dimension, "Item"), metric],
        "rows": [[row["label"], row["value"]] for row in result.rows],
        "truncated": result.truncated,
    }
