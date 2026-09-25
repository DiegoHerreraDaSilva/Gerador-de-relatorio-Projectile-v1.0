"""Catálogo da consulta cruzada: o que dá pra medir, por onde dá pra
agrupar e filtrar, e em qual conjunto de dados. É a única "linguagem" que o
planner do Claude e o Jev enxergam — nada aqui vira SQL; `crossquery.py`
calcula em Python sobre as linhas que `facts.py` já carregou.

Três conjuntos de dados, porque as fontes não têm as mesmas dimensões:

- `hours`: cada apontamento do Projectile (engenharia CAD+CAE) — tem
  cliente, projeto, colaborador, pacote, mês, centro de custo e se o
  pacote é faturável (`tjob.pExternal`, mesma regra do Painel de Gerência).
- `billing`: trabalhado x faturado por projeto e mês. Faturado vem das
  amostras de e-mail/manuais (`mgmt_kpi_samples`), que são POR PROJETO —
  não existe faturado por colaborador nem por pacote.
- `send_status`: status de envio do relatório por projeto e mês, pela
  mesma função do Diagnóstico (`management.compute_monthly_kpis`)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    name: str
    label: str
    plural: str
    # campo do filtro correspondente na consulta (None = não filtra por ele)
    filter_key: str | None
    description: str


@dataclass(frozen=True)
class Measure:
    name: str
    label: str
    unit: str  # "hours" | "percent" | "count"
    dataset: str
    # soma entre grupos faz sentido (horas sim; percentual/distintos não)
    additive: bool
    description: str


DIMENSIONS: dict[str, Dimension] = {d.name: d for d in [
    Dimension("client", "Cliente", "clientes", "clients", "cliente/customer"),
    Dimension("project", "Projeto", "projetos", "projects", "projeto"),
    Dimension("employee", "Colaborador", "colaboradores", "employees", "colaborador/funcionário/pessoa"),
    Dimension("package", "Pacote de trabalho", "pacotes", "packages", "pacote de trabalho/atividade do Projectile"),
    Dimension("month", "Mês", "meses", None, "mês/competência — evolução no tempo"),
    Dimension("cost_center", "Centro de custo", "centros de custo", "cost_centers", "centro de custo (CAD ou CAE)"),
    Dimension("billing_type", "Tipo", "tipos", "billing_type", "faturável x não faturável"),
    Dimension("status", "Status de envio", "status", "statuses", "status de envio do relatório do projeto no mês"),
]}

MEASURES: dict[str, Measure] = {m.name: m for m in [
    # --- horas apontadas -------------------------------------------------
    Measure("hours", "Horas", "hours", "hours", True, "horas apontadas (trabalhadas)"),
    Measure("billable_hours", "Horas faturáveis", "hours", "hours", True,
            "horas em pacotes faturáveis (projeto externo)"),
    Measure("non_billable_hours", "Horas não faturáveis", "hours", "hours", True,
            "horas em pacotes não faturáveis (internos, treinamento...)"),
    Measure("non_billable_percent", "% não faturável", "percent", "hours", False,
            "percentual das horas que é não faturável"),
    Measure("employees", "Colaboradores", "count", "hours", False, "quantidade de colaboradores distintos com apontamento"),
    Measure("projects", "Projetos", "count", "hours", False, "quantidade de projetos distintos com apontamento"),
    Measure("clients", "Clientes", "count", "hours", False, "quantidade de clientes distintos com apontamento"),
    Measure("active_days", "Dias com apontamento", "count", "hours", False, "dias distintos com alguma hora apontada"),
    Measure("avg_hours_per_employee", "Média por colaborador", "hours", "hours", False,
            "horas divididas pela quantidade de colaboradores distintos"),
    # --- faturamento ---------------------------------------------------
    Measure("worked_hours", "Trabalhadas", "hours", "billing", True, "horas trabalhadas (apontadas) do projeto"),
    Measure("billed_hours", "Faturadas", "hours", "billing", True,
            "horas faturadas (dos relatórios recebidos por e-mail ou marcados à mão)"),
    Measure("perf_hours", "Resultado (h)", "hours", "billing", True,
            "faturadas menos trabalhadas (negativo = trabalhou mais do que faturou)"),
    Measure("performance_percent", "Performance", "percent", "billing", False,
            "(faturadas - trabalhadas) / trabalhadas, em %, igual ao KPI do Painel de Gerência"),
    # --- status de envio ------------------------------------------------
    Measure("project_months", "Projetos no mês", "count", "send_status", True,
            "projetos com hora apontada no mês (um projeto em 3 meses conta 3)"),
    Measure("sent", "Enviados", "count", "send_status", True, "projetos com relatório enviado"),
    Measure("partial", "Parciais", "count", "send_status", True, "projetos com relatório enviado só de parte dos pacotes"),
    Measure("not_sent", "Não enviados", "count", "send_status", True, "projetos sem relatório enviado"),
    Measure("closed", "Fechados", "count", "send_status", True, "projetos/clientes marcados como fechados"),
    Measure("send_rate_percent", "% enviado", "percent", "send_status", False,
            "enviados / (total - fechados), em %"),
]}

DATASET_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "hours": ("client", "project", "employee", "package", "month", "cost_center", "billing_type"),
    "billing": ("client", "project", "month"),
    "send_status": ("client", "project", "month", "status"),
}

DATASET_LABELS = {
    "hours": "Horas apontadas no Projectile (engenharia CAD+CAE)",
    "billing": "Trabalhado (Projectile) x faturado (relatórios recebidos)",
    "send_status": "Status de envio dos relatórios (mesma regra do Diagnóstico)",
}

BILLING_TYPES = {"billable": "Faturável", "non_billable": "Não faturável"}
STATUSES = {"sent": "Enviado", "partial": "Parcial", "none": "Não enviado", "closed": "Fechado"}
COST_CENTERS = ("CAD", "CAE")

MAX_MEASURES = 4
MAX_GROUP_BY = 2
MAX_FILTER_VALUES = 20
MAX_TOP_N = 100
THRESHOLD_OPS = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
