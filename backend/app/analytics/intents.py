"""Whitelist de intents do chat analítico. Intent que não está aqui NÃO
executa consulta nenhuma, venha do Jev, do Claude ou do contexto enviado
pelo navegador."""
from __future__ import annotations

from dataclasses import dataclass

ROUTES = ("simple_data", "simple_with_explanation", "analysis", "general", "out_of_scope")


@dataclass(frozen=True)
class IntentSpec:
    name: str
    source: str  # "reports_db" | "projectile"
    # descrição pro Jev/Claude — inglês primeiro (o Jev acerta mais em inglês),
    # com os termos em português que o gerente usa.
    criteria: str
    dimension: str | None  # None = resultado é um número só
    unit: str  # chave de semantic_model.UNITS
    filters: frozenset[str]  # "period" | "client" | "employee"


_PROJECTILE_FILTERS = frozenset({"period", "client", "employee"})
_REPORTS_FILTERS = frozenset({"period"})

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
        IntentSpec(
            "total_hours", "projectile",
            "ONE total number of logged hours, no breakdown, optionally for one client or person (quantas horas, total de horas, horas da Mercedes, horas no mês passado)",
            None, "hours", _PROJECTILE_FILTERS,
        ),
        IntentSpec(
            "hours_by_client", "projectile",
            "A LIST of logged hours per client/customer (horas por cliente, quais clientes)",
            "client", "hours", _PROJECTILE_FILTERS,
        ),
        IntentSpec(
            "hours_by_project", "projectile",
            "A LIST of logged hours per project (horas por projeto, quais projetos)",
            "project", "hours", _PROJECTILE_FILTERS,
        ),
        IntentSpec(
            "hours_by_employee", "projectile",
            "A LIST of logged hours per employee/person (horas por colaborador/funcionário, quem trabalhou mais)",
            "employee", "hours", _PROJECTILE_FILTERS,
        ),
        IntentSpec(
            "hours_by_package", "projectile",
            "A LIST of logged hours per work package/activity (horas por pacote de trabalho/atividade)",
            "package", "hours", _PROJECTILE_FILTERS,
        ),
        IntentSpec(
            "hours_by_competence", "projectile",
            "A LIST of logged hours month by month, only when a monthly breakdown or evolution is asked (horas por mês, mês a mês, evolução)",
            "competence", "hours", _PROJECTILE_FILTERS,
        ),
    ]
}

# análises compostas (rota "analysis") — só o planner do Claude escolhe entre
# estas; cada uma é uma função Python em analysis.py, nunca SQL.
ANALYSES = {
    "compare_periods": "Compare two DIFFERENT periods (month vs month) for one hours metric and show what grew or shrank",
    "compare_items": "Compare specific clients or specific employees with each other in ONE period (Mercedes x Lauer em julho)",
}
