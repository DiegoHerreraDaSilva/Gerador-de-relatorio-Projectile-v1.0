"""Intents de RELATÓRIOS GERADOS (reports_db) → handler conhecido →
repository. Não existe caminho aqui pra executar SQL arbitrário: cada
intent tem uma função, e intent fora do catálogo levanta
`UnknownIntentError` antes de tocar em banco. Horas, faturado e status de
envio não passam mais por aqui: são consulta cruzada (`crossquery.py`)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..repositories import report_analytics_repository
from .intents import INTENTS
from .periods import Period, month_label


class UnknownIntentError(ValueError):
    pass


@dataclass(frozen=True)
class Filters:
    period: Period
    client: str | None = None
    employee: str | None = None

    def as_dict(self) -> dict:
        return {"period": self.period.as_metadata(), "client": self.client, "employee": self.employee}


@dataclass
class QueryResult:
    intent: str
    source: str
    unit: str
    dimension: str | None
    filters: Filters
    total: float | None = None
    # `[{"label", "value"}]`, já ordenado; vazio pra intent de número único
    rows: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    truncated: bool = False

    def compact(self) -> dict:
        """Resultado agregado pro Claude — nunca linha crua."""
        return {
            "intent": self.intent, "source": self.source, "unit": self.unit,
            "dimension": self.dimension, "filters": self.filters.as_dict(),
            "total": self.total, "rows": self.rows, "extra": self.extra, "truncated": self.truncated,
        }


def run(intent: str, filters: Filters, _unused=None, max_rows: int = 1000) -> QueryResult:
    spec = INTENTS.get(intent)
    if spec is None:
        raise UnknownIntentError(intent)
    result = QueryResult(intent=intent, source=spec.source, unit=spec.unit, dimension=spec.dimension, filters=filters)
    period = filters.period

    if spec.source != "reports_db":
        raise UnknownIntentError(f"{intent} é consulta cruzada, não intent de relatório")
    if intent == "report_count":
        result.total = report_analytics_repository.count_generated_reports(period.start, period.end)
    elif intent == "reports_by_month":
        result.rows = [
            {**row, "label": month_label(row["label"])}
            for row in report_analytics_repository.generated_reports_by_month(period.start, period.end)
        ]
        result.total = sum(row["value"] for row in result.rows)
    elif intent == "version_count":
        result.total = report_analytics_repository.count_versions(period.start, period.end)
    elif intent == "generation_time":
        data = report_analytics_repository.generation_time(period.start, period.end)
        result.total = round(data["avg_ms"], 0) if data["avg_ms"] is not None else None
        result.rows = [{**row, "value": round(row["value"], 0) if row["value"] is not None else None} for row in data["rows"]]
    elif intent == "generation_failures":
        data = report_analytics_repository.generation_failures(period.start, period.end)
        result.total = data["failed"]
        result.extra = {
            "generations": data["total"],
            "failure_rate_percent": round(data["failed"] / data["total"] * 100, 1) if data["total"] else None,
        }
    elif intent == "report_hours_by_project":
        result.rows = report_analytics_repository.report_hours_by_project(period.start, period.end, max_rows)
        result.total = round(sum(row["value"] for row in result.rows), 2)
    return result
