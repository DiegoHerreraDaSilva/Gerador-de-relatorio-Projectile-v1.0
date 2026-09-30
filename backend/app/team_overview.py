"""Visão do time (gerente e coordenador): por pessoa de engenharia, como o mês está indo em apontamento.

Mesmos cálculos de calendário do Dashboard pessoal (`/my-hours`): dias úteis sem feriado nacional nem o estadual/
municipal da filial da pessoa, e "dia sem apontamento" = dia útil JÁ ENCERRADO sem nenhuma hora
(`hours_analytics.gap_days`). Nada aqui é novo dado: é o que o coordenador já vê pessoa a pessoa no seletor de
colaborador do Dashboard, só que numa tabela só, com quem precisa de atenção no topo.

Quem entra: engenharia (CAD+CAE) com apontamento nos 2 meses anteriores ao período — gente que saiu da empresa
não vira uma linha de "60 dias sem apontamento". Função pura (`summarize`), sem banco, pra testar com dicts."""

from __future__ import annotations

import time
from datetime import date, timedelta

from . import projectile_db
from .holidays import business_days_between, local_holidays_for_filiale
from .hours_analytics import gap_days

# dia com mais horas que isto conta como "dia pesado" (sobrecarga possível); é sinal, não regra de negócio
OVERLOAD_HOURS = 10.0
# quanto antes do período olhar pra decidir se a pessoa está ativa
ACTIVE_LOOKBACK_DAYS = 62

_CACHE_TTL_SECONDS = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}


def month_bounds(month: str) -> tuple[date, date]:
    """Primeiro e último dia de "AAAA-MM". Levanta ValueError se o texto não é um mês."""
    year, m = (int(part) for part in month.split("-"))
    first = date(year, m, 1)
    last = date(year + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    return first, last


def summarize(employees: list[dict], daily_rows: list[dict], start: date, end: date, today: date) -> list[dict]:
    """Uma linha por pessoa ativa, com a atenção primeiro (mais dias sem apontamento, depois menos horas).
    `daily_rows`: `{employee_id, data, horas}` (uma linha por pessoa e dia, de antes do período até `end`)."""
    by_person: dict[str, dict[date, float]] = {}
    for row in daily_rows:
        day = row["data"] if isinstance(row["data"], date) else date.fromisoformat(str(row["data"]))
        by_person.setdefault(str(row["employee_id"]), {})[day] = float(row["horas"] or 0)

    lookback_start = start - timedelta(days=ACTIVE_LOOKBACK_DAYS)
    people = []
    for employee in employees:
        totals = by_person.get(employee["employee_id"], {})
        if not any(hours > 0 and lookback_start <= day <= end for day, hours in totals.items()):
            continue  # sem nenhum apontamento recente: provavelmente não está mais no time
        extra = local_holidays_for_filiale(start.year, employee.get("filiale")) | local_holidays_for_filiale(end.year, employee.get("filiale"))
        closed = [d for d in business_days_between(start, end, extra_holidays=extra) if d < today]
        in_period = {day: hours for day, hours in totals.items() if start <= day <= end and hours > 0}
        gaps = gap_days(closed, in_period)
        hours = round(sum(in_period.values()), 2)
        worked_closed = len(closed) - len(gaps)
        people.append(
            {
                "employee_id": employee["employee_id"],
                "name": employee["name"],
                "cost_center": employee.get("cost_center"),
                "hours": hours,
                "days_worked": len(in_period),
                "closed_business_days": len(closed),
                "gap_days": [d.isoformat() for d in gaps],
                "gap_count": len(gaps),
                # média sobre os dias úteis encerrados em que houve apontamento (None se ainda não há dia encerrado)
                "avg_hours_per_day": round(sum(h for d, h in in_period.items() if d in set(closed)) / worked_closed, 2) if worked_closed else None,
                "overload_days": sum(1 for h in in_period.values() if h > OVERLOAD_HOURS),
            }
        )
    people.sort(key=lambda p: (-p["gap_count"], p["hours"], p["name"].casefold()))
    return people


def team_overview(month: str, today: date | None = None) -> dict:
    """O mês (AAAA-MM) do time. Cache de 15 min por mês — trocar de aba não custa uma consulta nova no Projectile."""
    today = today or date.today()
    cached = _cache.get(month)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    start, end = month_bounds(month)
    lookback = start - timedelta(days=ACTIVE_LOOKBACK_DAYS)
    employees = projectile_db.fetch_engineering_employees((today - timedelta(days=400)).isoformat(), today.isoformat())
    rows = projectile_db.fetch_engineering_daily_totals(lookback.isoformat(), min(end, today).isoformat())
    people = summarize(employees, rows, start, end, today)
    result = {
        "month": month,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "today": today.isoformat(),
        "people": people,
        "totals": {
            "people": len(people),
            "with_gaps": sum(1 for p in people if p["gap_count"] > 0),
            "hours": round(sum(p["hours"] for p in people), 2),
            "overloaded": sum(1 for p in people if p["overload_days"] > 0),
        },
    }
    _cache[month] = (time.time(), result)
    return result
