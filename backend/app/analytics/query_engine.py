"""Intent validada → handler conhecido → repository. Não existe caminho
aqui pra executar SQL arbitrário: cada intent do catálogo tem uma função, e
intent fora do catálogo levanta `UnknownIntentError` antes de tocar em banco.
Toda soma/média/contagem acontece aqui ou no SQL do repository, nunca no
modelo de IA."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from ..repositories import engineering_hours_repository, report_analytics_repository
from ..repositories.engineering_hours_repository import HoursRow
from .intents import INTENTS
from .periods import Period, add_months, month_key, month_label


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


class HoursSource:
    """Carrega as horas de engenharia uma vez por requisição, na janela
    fixa do chat (sempre a mesma → acerta o cache de 15 min do management)."""

    def __init__(self, today: date, max_months: int):
        current = date(today.year, today.month, 1)
        self.window_start = add_months(current, -(max_months - 1))
        self.window_end = today
        self._rows: list[HoursRow] | None = None

    def rows(self) -> list[HoursRow]:
        if self._rows is None:
            self._rows = engineering_hours_repository.load_rows(self.window_start, self.window_end)
        return self._rows


def _filtered(source: HoursSource, filters: Filters) -> list[HoursRow]:
    period = filters.period
    return [
        r for r in source.rows()
        if period.start <= r.day <= period.end
        and (filters.client is None or r.client == filters.client)
        and (filters.employee is None or r.employee == filters.employee)
    ]


def _grouped(rows: list[HoursRow], key, max_rows: int, *, chronological: bool = False) -> tuple[list[dict], bool]:
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[key(r)] += r.hours
    items = [{"label": label, "value": round(value, 2)} for label, value in totals.items()]
    if chronological:
        items.sort(key=lambda item: item["label"])
    else:
        items.sort(key=lambda item: (-item["value"], item["label"]))
    return items[:max_rows], len(items) > max_rows


def run(intent: str, filters: Filters, hours: HoursSource, max_rows: int) -> QueryResult:
    spec = INTENTS.get(intent)
    if spec is None:
        raise UnknownIntentError(intent)
    result = QueryResult(intent=intent, source=spec.source, unit=spec.unit, dimension=spec.dimension, filters=filters)
    period = filters.period

    if spec.source == "projectile":
        rows = _filtered(hours, filters)
        result.total = round(sum(r.hours for r in rows), 2)
        grouping = {
            "hours_by_client": lambda r: r.client,
            "hours_by_project": lambda r: r.project,
            "hours_by_employee": lambda r: r.employee,
            "hours_by_package": lambda r: r.package,
            "hours_by_competence": lambda r: month_key(date(r.day.year, r.day.month, 1)),
        }
        if intent in grouping:
            result.rows, result.truncated = _grouped(
                rows, grouping[intent], max_rows, chronological=intent == "hours_by_competence",
            )
            if intent == "hours_by_competence":
                result.rows = [{**row, "label": month_label(row["label"])} for row in result.rows]
        return result

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
