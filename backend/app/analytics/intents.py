"""Whitelist de intents do chat analítico. Intent que não está aqui NÃO
executa consulta nenhuma, venha do Jev, do Claude ou do contexto enviado
pelo navegador.

Duas famílias:
- relatórios gerados (`source="reports_db"`): handler próprio em
  `query_engine.py`, SQL fixo do `reports_db`;
- horas / faturado / status de envio: cada intent é só um ATALHO (`preset`)
  pra uma consulta cruzada (`crossquery.py`) — é o que o Jev consegue
  escolher sozinho, com um filtro de cada. Pergunta que cruza mais coisa
  (duas dimensões, vários itens, corte por valor) vai pro planner do Claude,
  que monta a consulta cruzada inteira."""
from __future__ import annotations

from dataclasses import dataclass, field

ROUTES = ("simple_data", "simple_with_explanation", "analysis", "general", "out_of_scope")


@dataclass(frozen=True)
class IntentSpec:
    name: str
    source: str  # "reports_db" | "projectile" | "billing" | "send_status"
    # descrição pro Jev/Claude — inglês primeiro (o Jev acerta mais em inglês),
    # com os termos em português que o gerente usa.
    criteria: str
    dimension: str | None  # None = resultado é um número só
    unit: str  # chave de semantic_model.UNITS
    filters: frozenset[str]  # "period" | "client" | "employee" | "project"
    # consulta cruzada equivalente ({"measures", "group_by"}); None = reports_db
    preset: dict | None = field(default=None, hash=False, compare=False)


_HOURS_FILTERS = frozenset({"period", "client", "employee", "project"})
_PROJECT_FILTERS = frozenset({"period", "client", "project"})
_REPORTS_FILTERS = frozenset({"period"})
_BILLING = ["worked_hours", "billed_hours", "perf_hours", "performance_percent"]


def _hours(name, criteria, measures, group_by=(), dimension=None, unit="hours"):
    return IntentSpec(name, "projectile", criteria, dimension, unit, _HOURS_FILTERS,
                      {"measures": list(measures), "group_by": list(group_by)})


INTENTS: dict[str, IntentSpec] = {
    spec.name: spec
    for spec in [
        IntentSpec(
            "report_count", "reports_db",
            "ONE total count of generated reports, no breakdown (quantos relatórios foram gerados/emitidos)",
            None, "count", _REPORTS_FILTERS,
        ),
        IntentSpec(
            "reports_by_month", "reports_db",
            "A LIST of report counts month by month, only when a monthly breakdown is asked (relatórios por mês, mês a mês)",
            "month", "count", _REPORTS_FILTERS,
        ),
        IntentSpec(
            "version_count", "reports_db",
            "How many report versions were created (quantas versões de relatório)",
            None, "count", _REPORTS_FILTERS,
        ),
        IntentSpec(
            "generation_time", "reports_db",
            "How long report generation takes (tempo de geração dos relatórios)",
            "format", "ms", _REPORTS_FILTERS,
        ),
        IntentSpec(
            "generation_failures", "reports_db",
            "How many report generations failed (falhas/erros na geração)",
            None, "count", _REPORTS_FILTERS,
        ),
        IntentSpec(
            "report_hours_by_project", "reports_db",
            "Hours inside generated reports per project (horas nos relatórios gerados por projeto)",
            "project", "hours", _REPORTS_FILTERS,
        ),
        _hours(
            "total_hours",
            "ONE total number of logged hours, no breakdown, optionally for one client, project or person "
            "(quantas horas, total de horas, horas da Mercedes, horas no mês passado)",
            ["hours"],
        ),
        _hours("hours_by_client", "A LIST of logged hours per client/customer (horas por cliente, quais clientes)",
               ["hours"], ["client"], "client"),
        _hours("hours_by_project", "A LIST of logged hours per project (horas por projeto, quais projetos)",
               ["hours"], ["project"], "project"),
        _hours("hours_by_employee",
               "A LIST of logged hours per employee/person (horas por colaborador/funcionário, quem trabalhou mais)",
               ["hours"], ["employee"], "employee"),
        _hours("hours_by_package",
               "A LIST of logged hours per work package/activity (horas por pacote de trabalho/atividade)",
               ["hours"], ["package"], "package"),
        _hours("hours_by_competence",
               "A LIST of logged hours month by month, only when a monthly breakdown or evolution is asked "
               "(horas por mês, mês a mês, evolução)",
               ["hours"], ["month"], "month"),
        _hours("non_billable_hours",
               "Non-billable hours and their percentage (horas não faturáveis, quanto não é faturável, horas internas)",
               ["non_billable_hours", "non_billable_percent"]),
        _hours("hours_by_billing_type",
               "Split of hours into billable vs non-billable (faturável x não faturável, divisão das horas)",
               ["hours"], ["billing_type"], "billing_type"),
        _hours("active_days",
               "How many days someone/the team logged hours (quantos dias apontou/trabalhou, dias com apontamento)",
               ["active_days", "hours"], unit="count"),
        _hours("employee_count",
               "How many people logged hours (quantos colaboradores/pessoas apontaram horas)",
               ["employees"], unit="count"),
        IntentSpec(
            "billing_summary", "billing",
            "ONE summary of billed vs worked hours and performance, no breakdown "
            "(horas faturadas, faturado, performance do mês, quanto faturamos)",
            None, "hours", _PROJECT_FILTERS, {"measures": _BILLING, "group_by": []},
        ),
        IntentSpec(
            "performance_by_month", "billing",
            "Billed vs worked hours and performance month by month (performance por mês, evolução do faturado)",
            "month", "hours", _PROJECT_FILTERS, {"measures": _BILLING, "group_by": ["month"]},
        ),
        IntentSpec(
            "performance_by_project", "billing",
            "Billed vs worked hours and performance per project (performance por projeto, faturado por projeto)",
            "project", "hours", _PROJECT_FILTERS, {"measures": _BILLING, "group_by": ["project"]},
        ),
        IntentSpec(
            "performance_by_client", "billing",
            "Billed vs worked hours and performance per client (performance por cliente, faturado por cliente)",
            "client", "hours", _PROJECT_FILTERS, {"measures": _BILLING, "group_by": ["client"]},
        ),
        IntentSpec(
            "send_status", "send_status",
            "How many project reports were sent, partially sent or not sent (status de envio, relatórios enviados)",
            "status", "count", _PROJECT_FILTERS,
            {"measures": ["project_months"], "group_by": ["status"]},
        ),
        IntentSpec(
            "send_status_by_project", "send_status",
            "Which projects had their report sent or not (quais projetos foram/não foram enviados)",
            "project", "count", _PROJECT_FILTERS,
            {"measures": ["project_months"], "group_by": ["project", "status"]},
        ),
    ]
}

# análises compostas (rota "analysis") — o planner do Claude escolhe entre
# estas; cada uma é uma função Python, nunca SQL.
ANALYSES = {
    "query": "Cross query: up to 4 measures, up to 2 breakdowns, several filters, top N, thresholds",
    "compare_periods": "Compare two DIFFERENT periods for one measure and show what grew or shrank",
}
