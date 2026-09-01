"""Painel de gerência — KPIs de engenharia (horas trabalhadas, faturadas e não
faturáveis), reconstruindo dentro do app um relatório que hoje só existe num
Power BI separado. Ver `backend/app/projectile_db.py:fetch_engineering_hours`
pra fonte dos dados automáticos (banco do Projectile).

Fórmulas confirmadas com o usuário e validadas batendo os números de um
relatório Power BI de referência:
- Trabalhadas = soma de horas dos centros de custo CAD+CAE no mês (banco).
- Faturadas = input manual do gerente (não existe no Projectile).
- Perf. H = Faturadas - Trabalhadas (calculado).
- KPI % (performance) = Perf. H / Trabalhadas.
- Horas NãoFat = soma de horas cujo pacote de trabalho tem `tjob.pExternal =
  '0'`. Chegou a existir uma lista manual de nomes de pacote (ex:
  "Treinamento") pra essa classificação, mas uma auditoria estatística nesta
  sessão mostrou que `pExternal` bate de forma consistente pros pacotes que
  importam de verdade (ativos hoje e com apontamento nos últimos 12 meses —
  0 inconsistência nos dois recortes testados); o campo só é confuso no
  histórico antigo/fechado, fora do que qualquer período do painel consulta
  na prática. `pExternal` é mais confiável que qualquer lista mantida à mão
  e não precisa de manutenção.
- KPI % (não faturável) = Horas NãoFat / Trabalhadas.
- Elaboração dos relatórios (dias) = 100% input manual, sem fórmula.

Persistência: os valores manuais precisam sobreviver a reinícios do backend,
diferente do resto do app (que só usa `tempfile`, sem nada persistente).
Guarda isso num único JSON simples em `backend/data/management_kpi.json` —
não é um banco, só um arquivo, no mesmo nível de simplicidade do resto do
projeto.
"""
from __future__ import annotations

import calendar
import json
import os
import time
from datetime import date

from .projectile_db import (
    fetch_clients_for_projects,
    fetch_engineering_hours,
    fetch_project_ids_for_clients,
    fetch_project_ids_for_names,
    fetch_project_names_for_ids,
    open_connection,
)

MANAGEMENT_PANEL_LOGINS = {"dherrera"}

# times/centros de custo de engenharia disponíveis pro filtro — o usuário
# confirmou que "CAD + CAE juntos" é a equipe (não existe um valor literal
# "Engenharia" no Projectile, ver investigação de schema desta sessão).
ENGINEERING_COST_CENTERS = ["CAD", "CAE"]

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DATA_FILE = os.path.join(_DATA_DIR, "management_kpi.json")

_DEFAULT_DATA = {"manual_entries": {}}

# cache em memória das linhas cruas de `fetch_engineering_hours` por
# intervalo de datas — essa query é o gargalo real do painel (~50s neste
# MySQL legado, nenhuma tabela do join usa índice no lado certo). Sem esse
# cache, cada troca de filtro (Centro de Custo/Cliente/Projeto/Competência)
# refazia a mesma busca lenta; com ele, só a primeira busca de um período
# paga esse custo — o resto é filtrado em Python, na hora.
_HOURS_CACHE: dict[tuple[str, str], dict] = {}
_CACHE_TTL_SECONDS = 15 * 60


def _get_cached_rows(start_date: str, end_date: str, force_refresh: bool = False, conn=None) -> list[dict]:
    key = (start_date, end_date)
    entry = _HOURS_CACHE.get(key)
    if not force_refresh and entry and (time.time() - entry["fetched_at"]) < _CACHE_TTL_SECONDS:
        return entry["rows"]
    rows = fetch_engineering_hours(start_date, end_date, conn=conn)
    _HOURS_CACHE[key] = {"fetched_at": time.time(), "rows": rows}
    return rows


def _load_data() -> dict:
    if not os.path.exists(_DATA_FILE):
        return {"manual_entries": {}}
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("manual_entries", {})
    return data


def _save_data(data: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_manual_entry(month: str, billed_hours: float | None, elaboration_days: float | None) -> None:
    data = _load_data()
    data["manual_entries"][month] = {"billed_hours": billed_hours, "elaboration_days": elaboration_days}
    _save_data(data)


def _add_months(base: date, delta: int) -> date:
    month_index = base.month - 1 + delta
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def compute_monthly_kpis(
    months: int,
    year: int | None = None,
    cost_centers: list[str] | None = None,
    clients: list[str] | None = None,
    projects: list[str] | None = None,
    force_refresh: bool = False,
) -> dict:
    data = _load_data()
    manual_entries: dict = data["manual_entries"]

    active_cost_centers = cost_centers or ENGINEERING_COST_CENTERS

    # dois modos de período: "ano" fechado (Jan-Dez de um ano específico) ou
    # os últimos N meses corridos a partir de hoje (padrão).
    if year is not None:
        range_start = date(year, 1, 1)
        range_end = date(year, 12, 31)
        month_keys = sorted({date(year, m, 1).strftime("%Y-%m") for m in range(1, 13)}, reverse=True)
    else:
        today = date.today()
        range_start = _add_months(date(today.year, today.month, 1), -(months - 1))
        range_end_day = calendar.monthrange(today.year, today.month)[1]
        range_end = date(today.year, today.month, range_end_day)
        month_keys = sorted({_add_months(range_start, i).strftime("%Y-%m") for i in range(months)}, reverse=True)

    # uma única conexão pras 4 consultas pequenas + a busca cara (quando não
    # está em cache) — a conexão em si é persistente/reaproveitada entre
    # requisições (ver `projectile_db._get_connection`), então isso só deixa
    # explícito que essas chamadas usam a mesma conexão do início ao fim
    # deste request, sem reabrir uma pra cada lookup.
    conn = open_connection()

    # Cliente e Projeto resolvem pro mesmo mecanismo de filtro
    # (tj.pProject IN (...), ver fetch_engineering_hours) — com os dois
    # ativos ao mesmo tempo, só entra quem atende AMBOS (interseção dos
    # IDs de projeto).
    client_project_ids = fetch_project_ids_for_clients(clients, conn=conn) if clients else None
    project_name_ids = fetch_project_ids_for_names(projects, conn=conn) if projects else None
    if client_project_ids is not None and project_name_ids is not None:
        project_ids = sorted(set(client_project_ids) & set(project_name_ids))
    else:
        project_ids = client_project_ids if client_project_ids is not None else project_name_ids
    allowed_project_ids = set(project_ids) if project_ids is not None else None
    cost_center_keywords = [cc.casefold() for cc in active_cost_centers]

    # a busca cara já vem com TODO o CAD+CAE do período, cacheada por
    # intervalo de datas — Centro de Custo/Cliente/Projeto são recortes
    # em Python sobre esse mesmo resultado, sem voltar no banco.
    all_rows = _get_cached_rows(range_start.isoformat(), range_end.isoformat(), force_refresh, conn=conn)

    buckets: dict[str, dict] = {}
    available_project_ids: set[str] = set()
    for row in all_rows:
        row_cost_center = (row.get("cost_center") or "").casefold()
        if not any(kw in row_cost_center for kw in cost_center_keywords):
            continue
        project_id = row.get("project_id")
        if allowed_project_ids is not None and project_id not in allowed_project_ids:
            continue
        row_date = row.get("data")
        month_key = row_date.strftime("%Y-%m") if hasattr(row_date, "strftime") else str(row_date)[:7]
        hours = round(float(row.get("horas") or 0), 3)
        if project_id:
            available_project_ids.add(project_id)
        bucket = buckets.setdefault(month_key, {"worked_hours": 0.0, "nonbillable_hours": 0.0})
        bucket["worked_hours"] += hours
        if row.get("external") == "0":
            bucket["nonbillable_hours"] += hours

    available_projects = fetch_project_names_for_ids(sorted(available_project_ids), conn=conn)
    available_clients = fetch_clients_for_projects(sorted(available_project_ids), conn=conn)

    result_months = []
    for month_key in month_keys:
        bucket = buckets.get(month_key, {"worked_hours": 0.0, "nonbillable_hours": 0.0})
        worked_hours = round(bucket["worked_hours"], 2)
        nonbillable_hours = round(bucket["nonbillable_hours"], 2)
        manual = manual_entries.get(month_key) or {}
        billed_hours = manual.get("billed_hours")
        elaboration_days = manual.get("elaboration_days")

        perf_hours = round(billed_hours - worked_hours, 2) if billed_hours is not None else None
        perf_kpi_pct = (perf_hours / worked_hours) if perf_hours is not None and worked_hours > 0 else None
        nonbillable_kpi_pct = (nonbillable_hours / worked_hours) if worked_hours > 0 else None

        result_months.append({
            "month": month_key,
            "worked_hours": worked_hours,
            "billed_hours": billed_hours,
            "perf_hours": perf_hours,
            "perf_kpi_pct": perf_kpi_pct,
            "elaboration_days": elaboration_days,
            "nonbillable_hours": nonbillable_hours,
            "nonbillable_kpi_pct": nonbillable_kpi_pct,
        })

    return {
        "months": result_months,
        "cost_centers": ENGINEERING_COST_CENTERS,
        "available_projects": available_projects,
        "available_clients": available_clients,
    }
