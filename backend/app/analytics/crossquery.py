"""Consulta cruzada do chat analítico: até 3 medidas × até 2 dimensões,
filtros com vários valores, período, top N, ordenação e corte por valor.

Quem monta a consulta (Jev via preset de intent, ou o planner do Claude)
só escolhe NOMES do catálogo (`catalog.py`) e valores das listas de opções
montadas a cada pergunta. `build_spec` descarta tudo o que não existe — com
um aviso em português, nunca em silêncio — e `execute` calcula em Python
sobre as linhas de `facts.DataSources`. Não existe caminho daqui pra SQL.

Regras de negócio (as mesmas do Painel de Gerência/Diagnóstico):
- horas: soma de `tb.pTime` da engenharia CAD+CAE; não faturável =
  pacote com `pExternal = '0'`.
- faturado: soma das amostras de relatório recebido (sem duplicadas). No
  total mensal SEM recorte de cliente/projeto, o ajuste manual do gerente
  tem prioridade (é um total do time, não tem projeto). Resultado e
  performance comparam o faturado com TUDO o que foi trabalhado no mesmo
  recorte e mês (igual ao Painel filtrado por cliente/projeto); mês/recorte
  sem nenhum relatório recebido fica de fora — não vira "-100%".
- status de envio: linha a linha de `compute_monthly_kpis`."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .catalog import (
    BILLING_TYPES,
    COST_CENTERS,
    DATASET_DIMENSIONS,
    DATASET_LABELS,
    DIMENSIONS,
    MAX_FILTER_VALUES,
    MAX_GROUP_BY,
    MAX_MEASURES,
    MAX_TOP_N,
    MEASURES,
    STATUSES,
    THRESHOLD_OPS,
)
from .facts import DataSources
from .periods import RELATIVE_PERIODS, Period, add_months, month_key, month_label, resolve_period
from .semantic_model import fmt_number

# filtro na consulta -> (dimensão, chave da lista de opções)
_LIST_FILTERS = {
    "clients": ("client", "clients"),
    "projects": ("project", "projects"),
    "employees": ("employee", "employees"),
    "packages": ("package", "packages"),
}


class InvalidQueryError(ValueError):
    """Consulta sem nenhuma medida válida — nada pra calcular."""


@dataclass(frozen=True)
class Threshold:
    measure: str
    op: str
    value: float

    def passes(self, value: float | None) -> bool:
        if value is None:
            return False
        return {
            "gt": value > self.value, "gte": value >= self.value,
            "lt": value < self.value, "lte": value <= self.value,
        }[self.op]

    def describe(self) -> str:
        measure = MEASURES[self.measure]
        unit = {"hours": " h", "percent": "%"}.get(measure.unit, "")
        return f"{measure.label.lower()} {THRESHOLD_OPS[self.op]} {fmt_number(self.value)}{unit}"


@dataclass
class QuerySpec:
    dataset: str
    measures: list[str]
    group_by: list[str]
    period: Period
    month: str | None = None
    month_end: str | None = None
    relative: str | None = None
    clients: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    employees: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    cost_centers: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    billing_type: str | None = None
    top_n: int | None = None
    sort_by: str | None = None
    sort_order: str = "desc"
    threshold: Threshold | None = None

    def filter_values(self) -> dict[str, list[str]]:
        """Filtros ativos, com rótulo legível — pra texto e metadados."""
        active = {
            "clients": self.clients, "projects": self.projects, "employees": self.employees,
            "packages": self.packages, "cost_centers": self.cost_centers,
            "statuses": [STATUSES[s] for s in self.statuses],
        }
        if self.billing_type:
            active["billing_type"] = [BILLING_TYPES[self.billing_type]]
        return {key: values for key, values in active.items() if values}

    def as_context(self) -> dict:
        """Formato cru (o mesmo que o planner devolve) — vai pro navegador e
        volta como contexto de conversa, e é revalidado por `build_spec`."""
        return {
            "measures": list(self.measures),
            "group_by": list(self.group_by),
            "clients": list(self.clients), "projects": list(self.projects),
            "employees": list(self.employees), "packages": list(self.packages),
            "cost_centers": list(self.cost_centers), "statuses": list(self.statuses),
            "billing_type": self.billing_type,
            "month": self.month, "month_end": self.month_end, "relative_period": self.relative,
            "top_n": self.top_n, "sort_by": self.sort_by, "sort_order": self.sort_order,
            "threshold_measure": self.threshold.measure if self.threshold else None,
            "threshold_op": self.threshold.op if self.threshold else None,
            "threshold_value": self.threshold.value if self.threshold else None,
        }


def _unique_strings(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(v for v in values if isinstance(v, str)))


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def build_spec(raw: dict, options: dict, today, max_months: int) -> tuple[QuerySpec, list[str]]:
    """Consulta crua (planner/preset/contexto) → consulta validada + avisos.
    Nada que não esteja no catálogo ou nas opções sobrevive."""
    notes: list[str] = []
    measures = [m for m in _unique_strings(raw.get("measures")) if m in MEASURES]
    if not measures:
        raise InvalidQueryError("nenhuma medida válida")
    dataset = MEASURES[measures[0]].dataset
    other = [m for m in measures if MEASURES[m].dataset != dataset]
    measures = [m for m in measures if MEASURES[m].dataset == dataset][:MAX_MEASURES]
    if other:
        notes.append(
            f"{_join([MEASURES[m].label for m in other])} vem de outra fonte e não cruza com "
            f"{_join([MEASURES[m].label.lower() for m in measures])} numa consulta só — mostrei só a primeira parte."
        )
    allowed = DATASET_DIMENSIONS[dataset]
    source = DATASET_LABELS[dataset].split(" (")[0]

    group_by: list[str] = []
    for dim in _unique_strings(raw.get("group_by")):
        if dim not in DIMENSIONS:
            continue
        if dim not in allowed:
            notes.append(f"{source} não tem recorte por {DIMENSIONS[dim].label.lower()} — ignorei esse agrupamento.")
            continue
        group_by.append(dim)
    group_by = group_by[:MAX_GROUP_BY]

    lists: dict[str, list[str]] = {}
    for key, (dim, option_key) in _LIST_FILTERS.items():
        values = _unique_strings(raw.get(key))[:MAX_FILTER_VALUES]
        valid = [v for v in values if v in options.get(option_key, [])]
        unknown = [v for v in values if v not in options.get(option_key, [])]
        if unknown:
            notes.append(f"Não encontrei {_join(unknown)} entre os {DIMENSIONS[dim].plural} com horas no período disponível.")
        if valid and dim not in allowed:
            notes.append(f"{source} não tem recorte por {DIMENSIONS[dim].label.lower()} — ignorei esse filtro.")
            valid = []
        lists[key] = valid
    cost_centers = [c for c in _unique_strings(raw.get("cost_centers")) if c in COST_CENTERS] if "cost_center" in allowed else []
    statuses = [s for s in _unique_strings(raw.get("statuses")) if s in STATUSES] if "status" in allowed else []
    billing_type = raw.get("billing_type") if raw.get("billing_type") in BILLING_TYPES and "billing_type" in allowed else None

    month = raw.get("month") if raw.get("month") in options["months"] else None
    month_end = raw.get("month_end") if month and raw.get("month_end") in options["months"] else None
    relative = raw.get("relative_period") if raw.get("relative_period") in RELATIVE_PERIODS else None
    if month:
        relative = None
    period = resolve_period(month, relative, today, max_months, month_end)

    top_n = raw.get("top_n")
    top_n = top_n if isinstance(top_n, int) and not isinstance(top_n, bool) and 1 <= top_n <= MAX_TOP_N else None
    sort_order = raw.get("sort_order") if raw.get("sort_order") in ("asc", "desc") else "desc"
    sort_by = raw.get("sort_by") if raw.get("sort_by") in measures else None

    threshold = None
    value = raw.get("threshold_value")
    if (
        raw.get("threshold_measure") in measures and raw.get("threshold_op") in THRESHOLD_OPS
        and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    ):
        threshold = Threshold(raw["threshold_measure"], raw["threshold_op"], float(value))

    spec = QuerySpec(
        dataset=dataset, measures=measures, group_by=group_by, period=period,
        month=month, month_end=month_end, relative=relative,
        cost_centers=cost_centers, statuses=statuses, billing_type=billing_type,
        top_n=top_n, sort_by=sort_by, sort_order=sort_order, threshold=threshold, **lists,
    )
    return spec, notes


# --- execução -----------------------------------------------------------------


@dataclass
class CrossRow:
    keys: tuple[str, ...]
    labels: tuple[str, ...]
    values: dict[str, float | None]
    share: float | None = None  # % do total da 1ª medida, quando ela é somável


@dataclass
class CrossResult:
    spec: QuerySpec
    rows: list[CrossRow]
    totals: dict[str, float | None]
    group_count: int  # grupos depois do corte por valor, antes do top N
    truncated: bool
    notes: list[str]
    # top N ou limite de linhas deixaram grupo de fora (total da tabela ≠ total geral)
    cut: bool = False

    @property
    def dataset(self) -> str:
        return self.spec.dataset


def label_for(dim: str, key: str) -> str:
    if dim == "month":
        return month_label(key)
    if dim == "billing_type":
        return BILLING_TYPES.get(key, key)
    if dim == "status":
        return STATUSES.get(key, key)
    return key


def period_months(period: Period) -> list[str]:
    months, cursor = [], period.start.replace(day=1)
    while cursor <= period.end:
        months.append(month_key(cursor))
        cursor = add_months(cursor, 1)
    return months


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


class _HoursAcc:
    __slots__ = ("hours", "billable", "non_billable", "employees", "projects", "clients", "days")

    def __init__(self):
        self.hours = self.billable = self.non_billable = 0.0
        self.employees, self.projects, self.clients, self.days = set(), set(), set(), set()

    def add(self, row) -> None:
        self.hours += row.hours
        if row.billable:
            self.billable += row.hours
        else:
            self.non_billable += row.hours
        self.employees.add(row.employee)
        self.projects.add(row.project_id or row.project)
        self.clients.add(row.client)
        self.days.add(row.day)

    def value(self, measure: str) -> float | None:
        if measure == "hours":
            return round(self.hours, 2)
        if measure == "billable_hours":
            return round(self.billable, 2)
        if measure == "non_billable_hours":
            return round(self.non_billable, 2)
        if measure == "non_billable_percent":
            return round(self.non_billable / self.hours * 100, 1) if self.hours else None
        if measure == "employees":
            return len(self.employees)
        if measure == "projects":
            return len(self.projects)
        if measure == "clients":
            return len(self.clients)
        if measure == "active_days":
            return len(self.days)
        if measure == "avg_hours_per_employee":
            return round(self.hours / len(self.employees), 2) if self.employees else None
        raise KeyError(measure)


class _BillingAcc:
    __slots__ = ("worked", "billed", "worked_with_billed", "cells", "cells_with_billed")

    def __init__(self):
        self.worked = 0.0
        self.billed: float | None = None
        self.worked_with_billed = 0.0
        self.cells = self.cells_with_billed = 0

    def add(self, worked: float, billed: float | None) -> None:
        self.worked += worked
        self.cells += 1
        if billed is not None:
            self.billed = (self.billed or 0.0) + billed
            self.worked_with_billed += worked
            self.cells_with_billed += 1

    def value(self, measure: str) -> float | None:
        if measure == "worked_hours":
            return round(self.worked, 2)
        if measure == "billed_hours":
            return _round(self.billed)
        if self.billed is None:
            return None
        perf = self.billed - self.worked_with_billed
        if measure == "perf_hours":
            return round(perf, 2)
        if measure == "performance_percent":
            return round(perf / self.worked_with_billed * 100, 1) if self.worked_with_billed > 0 else None
        raise KeyError(measure)


class _StatusAcc:
    __slots__ = ("counts",)

    def __init__(self):
        self.counts = {status: 0 for status in STATUSES}

    def add(self, status: str) -> None:
        self.counts[status] = self.counts.get(status, 0) + 1

    def value(self, measure: str) -> float | None:
        total = sum(self.counts.values())
        if measure == "project_months":
            return total
        if measure == "sent":
            return self.counts["sent"]
        if measure == "partial":
            return self.counts["partial"]
        if measure == "not_sent":
            return self.counts["none"]
        if measure == "closed":
            return self.counts["closed"]
        if measure == "send_rate_percent":
            open_items = total - self.counts["closed"]
            return round(self.counts["sent"] / open_items * 100, 1) if open_items else None
        raise KeyError(measure)


def _hours_items(spec: QuerySpec, sources: DataSources):
    period = spec.period
    clients, projects, employees, packages = (set(v) for v in (spec.clients, spec.projects, spec.employees, spec.packages))
    cost_centers = set(spec.cost_centers)
    for r in sources.hours():
        if not period.start <= r.day <= period.end:
            continue
        if (clients and r.client not in clients) or (projects and r.project not in projects):
            continue
        if (employees and r.employee not in employees) or (packages and r.package not in packages):
            continue
        if cost_centers and r.cost_center not in cost_centers:
            continue
        if spec.billing_type == "billable" and not r.billable:
            continue
        if spec.billing_type == "non_billable" and r.billable:
            continue
        keys = {
            "client": r.client, "project": r.project, "employee": r.employee, "package": r.package,
            "month": f"{r.day.year:04d}-{r.day.month:02d}", "cost_center": r.cost_center,
            "billing_type": "billable" if r.billable else "non_billable",
        }
        yield tuple(keys[d] for d in spec.group_by), r


def _billing_cells(spec: QuerySpec, sources: DataSources, notes: list[str]):
    """Células (mês) no total do time, ou (projeto, mês) com recorte de
    cliente/projeto — ver docstring do módulo."""
    months = set(period_months(spec.period))
    clients, projects = set(spec.clients), set(spec.projects)
    team_level = not ({"client", "project"} & set(spec.group_by)) and not clients and not projects
    period = spec.period

    worked: dict[tuple[str, str], float] = {}
    for r in sources.hours():
        if not period.start <= r.day <= period.end or not r.project_id:
            continue
        if (clients and r.client not in clients) or (projects and r.project not in projects):
            continue
        key = (r.project_id, f"{r.day.year:04d}-{r.day.month:02d}")
        worked[key] = worked.get(key, 0.0) + r.hours

    info = sources.project_info()
    billed: dict[tuple[str, str], float] = {}
    for sample in sources.billed_samples():
        if sample.month not in months:
            continue
        details = info.get(sample.project_id, {"name": "Sem projeto", "client": "Sem cliente"})
        if (clients and details["client"] not in clients) or (projects and details["name"] not in projects):
            continue
        key = (sample.project_id, sample.month)
        billed[key] = billed.get(key, 0.0) + sample.billed_hours

    cells = []
    if team_level:
        manual = sources.manual_billed_by_month()
        worked_by_month: dict[str, float] = {}
        billed_by_month: dict[str, float] = {}
        for (_, month), hours in worked.items():
            worked_by_month[month] = worked_by_month.get(month, 0.0) + hours
        for (_, month), hours in billed.items():
            billed_by_month[month] = billed_by_month.get(month, 0.0) + hours
        for month in sorted(months):
            if month not in worked_by_month and month not in billed_by_month and month not in manual:
                continue
            month_billed = manual[month] if month in manual else billed_by_month.get(month)
            cells.append(({"month": month}, worked_by_month.get(month, 0.0), month_billed))
    else:
        # célula = (dimensões pedidas, mês) — a MESMA granularidade do Painel
        # filtrado: faturado do cliente/projeto no mês x TUDO o que ele
        # trabalhou no mês. Célula sem nenhum faturado fica de fora do
        # resultado/performance (não vira -100%).
        cell_dims = [d for d in spec.group_by if d != "month"]
        merged: dict[tuple, list] = {}
        for pid, month in sorted(set(worked) | set(billed)):
            details = info.get(pid, {"name": "Sem projeto", "client": "Sem cliente"})
            dims = {"client": details["client"], "project": details["name"], "month": month}
            key = tuple(dims[d] for d in cell_dims) + (month,)
            cell = merged.setdefault(key, [dims, 0.0, None])
            cell[1] += worked.get((pid, month), 0.0)
            if (pid, month) in billed:
                cell[2] = (cell[2] or 0.0) + billed[(pid, month)]
        cells = [(dims, worked_hours, billed_hours) for dims, worked_hours, billed_hours in merged.values()]

    wants_billed = {"billed_hours", "perf_hours", "performance_percent"} & set(spec.measures)
    missing = sum(1 for _, _, b in cells if b is None)
    if wants_billed and missing:
        cell_labels = [DIMENSIONS[d].label.lower() for d in spec.group_by if d != "month"]
        unit = "meses" if team_level or not cell_labels else f"combinações de {' e '.join(cell_labels)} e mês"
        notes.append(
            f"{missing} de {len(cells)} {unit} com hora apontada não têm faturado informado (relatório não "
            "recebido); resultado e performance consideram só os que têm."
        )
    for dims, worked_hours, billed_hours in cells:
        yield tuple(dims[d] for d in spec.group_by), (worked_hours, billed_hours)


def _status_items(spec: QuerySpec, sources: DataSources):
    months = set(period_months(spec.period))
    clients, projects, statuses = set(spec.clients), set(spec.projects), set(spec.statuses)
    for row in sources.send_status():
        if row.month not in months:
            continue
        if (clients and row.client not in clients) or (projects and row.project not in projects):
            continue
        if statuses and row.status not in statuses:
            continue
        keys = {"client": row.client, "project": row.project, "month": row.month, "status": row.status}
        yield tuple(keys[d] for d in spec.group_by), row.status


def _aggregate(spec: QuerySpec, sources: DataSources, notes: list[str]):
    if spec.dataset == "hours":
        make, items = _HoursAcc, _hours_items(spec, sources)
        feed = lambda acc, item: acc.add(item)  # noqa: E731
    elif spec.dataset == "billing":
        make, items = _BillingAcc, _billing_cells(spec, sources, notes)
        feed = lambda acc, item: acc.add(*item)  # noqa: E731
    else:
        make, items = _StatusAcc, _status_items(spec, sources)
        feed = lambda acc, item: acc.add(item)  # noqa: E731
    groups: dict[tuple, object] = {}
    total = make()
    # faturado: o TOTAL é sempre o número do Painel pro mesmo recorte (célula
    # = mês), mesmo quando as linhas são por projeto/cliente — senão o total
    # somaria só quem tem relatório e não fecharia com trabalhadas/faturadas
    separate_total = spec.dataset == "billing" and bool(set(spec.group_by) - {"month"})
    if separate_total:
        for _, item in _billing_cells(replace(spec, group_by=[]), sources, []):
            feed(total, item)
    for key, item in items:
        if not separate_total:
            feed(total, item)
        acc = groups.get(key)
        if acc is None:
            acc = groups[key] = make()
        feed(acc, item)
    if spec.group_by == ["month"]:
        # série no tempo contínua: mês sem apontamento aparece (zero), não some
        for month in period_months(spec.period):
            groups.setdefault((month,), make())
    return groups, total, make


def _order(spec: QuerySpec, rows: list[CrossRow]) -> list[CrossRow]:
    measure = spec.sort_by or spec.measures[0]
    descending = spec.sort_order == "desc"
    additive = MEASURES[measure].additive

    def by_value(row: CrossRow):
        value = row.values.get(measure)
        return (value is None, -(value or 0) if descending else (value or 0), row.labels)

    if spec.group_by == ["month"] and spec.top_n is None and spec.sort_by is None:
        return sorted(rows, key=lambda row: row.keys)
    if len(spec.group_by) < 2:
        return sorted(rows, key=by_value)
    # duas dimensões: agrupa pela primeira que não é mês ("âncora") e ordena
    # as âncoras pelo total delas; dentro, mês em ordem cronológica
    anchor = 0 if spec.group_by[0] != "month" else 1
    other = 1 - anchor
    anchor_total: dict[str, float] = {}
    for row in rows:
        value = row.values.get(measure) or 0
        key = row.keys[anchor]
        anchor_total[key] = anchor_total.get(key, 0.0) + value if additive else max(anchor_total.get(key, value), value)
    ranked = sorted(anchor_total, key=lambda k: (-anchor_total[k] if descending else anchor_total[k], k))
    rank = {key: i for i, key in enumerate(ranked)}
    if spec.top_n:
        rows = [row for row in rows if rank[row.keys[anchor]] < spec.top_n]
    inner = (lambda row: row.keys[other]) if spec.group_by[other] == "month" else (lambda row: by_value(row))
    return sorted(rows, key=lambda row: (rank[row.keys[anchor]], inner(row)))


def execute(spec: QuerySpec, sources: DataSources, max_rows: int, notes: list[str] | None = None) -> CrossResult:
    notes = list(notes or [])
    groups, total, _ = _aggregate(spec, sources, notes)
    rows = [
        CrossRow(
            keys=key,
            labels=tuple(label_for(dim, k) for dim, k in zip(spec.group_by, key)),
            values={m: acc.value(m) for m in spec.measures},
        )
        for key, acc in groups.items()
    ]
    totals = {m: total.value(m) for m in spec.measures}
    if spec.group_by and spec.group_by != ["month"]:
        # "horas não faturáveis por pacote" não lista os 250 pacotes com zero
        rows = [row for row in rows if any(v not in (None, 0, 0.0) for v in row.values.values())]
    if spec.threshold:
        rows = [row for row in rows if spec.threshold.passes(row.values.get(spec.threshold.measure))]
    group_count = len(rows)
    rows = _order(spec, rows)
    if len(spec.group_by) < 2 and spec.top_n:
        rows = rows[: spec.top_n]
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    cut = truncated or len(rows) < group_count

    first = spec.measures[0]
    total_first = totals.get(first)
    if spec.group_by and MEASURES[first].additive and total_first:
        for row in rows:
            value = row.values.get(first)
            row.share = round(value / total_first * 100, 1) if value is not None else None
    return CrossResult(
        spec=spec, rows=rows, totals=totals, group_count=group_count, truncated=truncated, notes=notes, cut=cut,
    )
