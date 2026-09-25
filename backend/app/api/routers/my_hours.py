"""Rota do dashboard pessoal (`/my-hours`) — extraído de `main.py`."""
from __future__ import annotations

import html
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ...generator import (
    business_days_between,
    is_santo_andre_filiale,
    local_holidays_for_filiale,
    national_holidays_between,
)
from ...hours_analytics import (
    daily_stats,
    day_matched_comparison,
    expected_hours_for_days,
    format_hhmm,
    gap_days,
    monthly_series,
    outlier_days,
    parse_hhmm,
    resolve_reference,
)
from ...projectile_db import (
    ProjectileDbError,
    fetch_daily_hours_totals,
    fetch_employee_contracts,
    fetch_engineering_employees,
    fetch_my_hours,
    fetch_project_details,
)
from ..dependencies import is_coordinator, is_manager, require_manager_or_coordinator, require_session
from ..errors import log_and_generic_error

router = APIRouter()

_MY_HOURS_PERIOD_MONTHS = {"current_month": 1, "last_3": 3, "last_6": 6, "last_12": 12}


def _my_hours_date_range(period: str) -> tuple[date, date]:
    """(início, fim) do período pedido — sempre até HOJE (não faz sentido
    pedir horas de um dia que ainda não aconteceu), voltando N meses
    completos a partir do mês corrente. `current_month` = só o mês corrente
    (o caso de uso principal: "como estou indo esse mês")."""
    today = date.today()
    months_back = _MY_HOURS_PERIOD_MONTHS[period]
    month_index = today.month - 1 - (months_back - 1)
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1), today


_BILLING_CLASS = {"1": "externo", "0": "interno"}

# Janela do histórico longo, independente do período exibido: alimenta a
# tendência de 13 meses, o baseline empírico de jornada (até 365 dias) e os
# percentis diários. Sem isso, "Mês atual" zeraria a tendência e o baseline.
_MY_HOURS_HISTORY_DAYS = 400


def _unescape_twice(value: object) -> str:
    """`html.unescape` em ponto fixo (2 passes) — o Projectile tem texto com
    entidade dupla (`&amp;#243;`), em que um passe só devolveria `&#243;`."""
    text = html.unescape(str(value or ""))
    return html.unescape(text)


_EMPLOYEES_CACHE_TTL_SECONDS = 15 * 60
_employees_cache: dict[str, object] = {"fetched_at": 0.0, "employees": None}


def _engineering_employees() -> list[dict]:
    """Quem gerente/coordenador pode escolher: engenharia (CAD+CAE) com
    apontamento na mesma janela do histórico do dashboard. Cache de 15 min
    (mesma ideia de `management._get_cached_rows`) — trocar de pessoa no
    seletor não pode custar uma consulta nova no Projectile a cada clique."""
    cached = _employees_cache["employees"]
    if cached is not None and time.time() - float(_employees_cache["fetched_at"]) < _EMPLOYEES_CACHE_TTL_SECONDS:
        return cached  # type: ignore[return-value]
    today = date.today()
    employees = fetch_engineering_employees(
        (today - timedelta(days=_MY_HOURS_HISTORY_DAYS)).isoformat(), today.isoformat()
    )
    _employees_cache.update(fetched_at=time.time(), employees=employees)
    return employees


def _resolve_target(user: dict, employee_id: str | None) -> tuple[str | None, str, str | None]:
    """(employee_id, nome, filial) de quem o dashboard vai mostrar.

    Sem `employee_id` (ou o próprio): o usuário da sessão, como sempre foi.
    De outra pessoa: só gerente/coordenador, e só alguém da lista de
    engenharia — o id vindo do cliente nunca é usado direto, sempre
    re-resolvido aqui (mesmo princípio de `/parse-db`). A filial vem do
    Projectile, não do cliente: ela muda o feriado municipal nos dias úteis."""
    own_id = str(user.get("employee_id") or "").strip() or None
    if not employee_id or employee_id == own_id:
        return own_id, user["name"], user.get("filiale")
    if not (is_manager(user) or is_coordinator(user)):
        raise HTTPException(403, "Sem acesso às horas de outro colaborador.")
    try:
        employees = _engineering_employees()
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    target = next((e for e in employees if e["employee_id"] == employee_id), None)
    if target is None:
        raise HTTPException(404, "Colaborador não encontrado na engenharia (CAD/CAE).")
    return target["employee_id"], target["name"], target["filiale"]


@router.get("/my-hours/employees")
async def my_hours_employees_endpoint(_user: dict = Depends(require_manager_or_coordinator)):
    """Lista do seletor de colaborador do Dashboard de horas."""
    try:
        employees = _engineering_employees()
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    return {
        "employees": [
            {"employee_id": e["employee_id"], "name": e["name"], "cost_center": e["cost_center"]}
            for e in employees
        ]
    }


def _entry_times(row: dict) -> tuple[str | None, str | None]:
    """`ttimebit.pStart`/`pEnd` validados para "HH:MM". Um span negativo
    (fim antes do início, virada de meia-noite) invalida os DOIS lados: exibir
    só uma ponta faria a faixa de jornada do dia ser desenhada errada."""
    start, end = parse_hhmm(row.get("inicio")), parse_hhmm(row.get("fim"))
    if start is not None and end is not None and end < start:
        return None, None
    return format_hhmm(start), format_hhmm(end)


@router.get("/my-hours")
async def my_hours_endpoint(
    period: str = "current_month",
    employee_id: str | None = None,
    _user: dict = Depends(require_session),
):
    """Dashboard de horas — por padrão do PRÓPRIO usuário logado (mesma
    regra de `/parse-db`: nunca confia em identidade vinda do cliente).
    `employee_id` de outra pessoa só vale pra gerente/coordenador, e só pra
    alguém de engenharia (ver `_resolve_target`).

    Devolve os lançamentos do período MAIS o contexto que o frontend não pode
    derivar deles: a lista de dias úteis (pra achar os que ficaram sem
    apontamento — um dia sem apontamento é uma linha que não existe), a
    referência de jornada com a FONTE (contrato/histórico/calendário), a série
    de 13 meses e a comparação com a janela anterior de mesmo número de dias
    úteis.

    `reference.allows_percentage` é a chave que autoriza percentual na tela:
    só jornada de contrato declarado permite afirmar aderência. Medido que o
    usuário de referência não tem contrato cadastrado e pratica 6 h/dia, então
    aplicar as 8 h do calendário mostraria 76% de cumprimento num mês
    integralmente cumprido."""
    if period not in _MY_HOURS_PERIOD_MONTHS:
        raise HTTPException(400, f"Período inválido: {period!r} (use current_month/last_3/last_6/last_12).")
    start_date, end_date = _my_hours_date_range(period)
    today = date.today()
    employee_id, employee_name, filiale = _resolve_target(_user, employee_id)

    # feriado estadual (SP, sempre) + municipal (Santo André, se for a
    # filial da pessoa) — só neste dashboard pessoal, nunca em
    # count_business_days/geração de relatório (ver docstring da função).
    def extra_holidays_for_year(year: int) -> set[date]:
        return local_holidays_for_filiale(year, filiale)

    try:
        rows = fetch_my_hours(
            start_date.isoformat(), end_date.isoformat(),
            employee_id=employee_id, employee_name=employee_name,
        )
        history_rows = fetch_daily_hours_totals(
            (today - timedelta(days=_MY_HOURS_HISTORY_DAYS)).isoformat(), end_date.isoformat(),
            employee_id=employee_id, employee_name=employee_name,
        )
        contracts = fetch_employee_contracts(employee_id) if employee_id else []
        project_ids = sorted({r["project_id"] for r in rows if r.get("project_id")})
        project_details = fetch_project_details(project_ids) if project_ids else {}
    except ProjectileDbError as e:
        raise log_and_generic_error(e)

    daily_totals = {
        (r["data"] if isinstance(r["data"], date) else date.fromisoformat(str(r["data"]))): float(r["horas"] or 0)
        for r in history_rows
    }

    entries = []
    for i, r in enumerate(rows):
        entry_date = r["data"] if isinstance(r["data"], date) else date.fromisoformat(str(r["data"]))
        start_hhmm, end_hhmm = _entry_times(r)
        entries.append({
            # `ttimebit` não expõe PK utilizável nesta query; o ordinal do
            # resultado é estável dentro de um payload porque a query tem
            # ORDER BY determinístico (pDate, pStart).
            "id": f"{i}-{entry_date.isoformat()}-{start_hhmm or ''}",
            "date": entry_date.isoformat(),
            "start": start_hhmm,
            "end": end_hhmm,
            "hours": float(r["horas"] or 0),
            "pacote": _unescape_twice(r.get("pacote")),
            "observacao": _unescape_twice(r.get("observacao")),
            "project_id": r.get("project_id"),
            "project_name": _unescape_twice(
                (project_details.get(r.get("project_id")) or {}).get("name")
            ) or "Sem projeto",
            "client": _unescape_twice(
                (project_details.get(r.get("project_id")) or {}).get("client")
            ) or None,
            "top_project": _unescape_twice(r.get("top_project")) or None,
            "cost_center": r.get("cost_center"),
            # tri-estado deliberado: `external != "0"` empurrava NULL e
            # qualquer valor inesperado pra "faturável", inventando receita.
            "billing_class": _BILLING_CLASS.get(str(r.get("external") or ""), "nao_classificado"),
        })

    # o recorte pode cruzar a virada do ano (last_12 em janeiro, por exemplo)
    # — resolve o feriado extra por ano em vez de um conjunto único.
    extra_period = extra_holidays_for_year(start_date.year) | extra_holidays_for_year(end_date.year)
    period_business = business_days_between(start_date, end_date, extra_holidays=extra_period)
    closed_business = [d for d in period_business if d < today]
    month_start = date(today.year, today.month, 1)
    month_end = date(today.year + (today.month == 12), (today.month % 12) + 1, 1) - timedelta(days=1)
    month_business = business_days_between(
        month_start, month_end, extra_holidays=extra_holidays_for_year(today.year)
    )

    reference = resolve_reference(contracts, daily_totals, today)

    return {
        "period": period,
        # de quem são estes dados — a tela confere contra a pessoa escolhida
        # pra não mostrar uma resposta atrasada de uma seleção anterior.
        "employee": {"employee_id": employee_id, "name": employee_name},
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "today": today.isoformat(),
        "entries": entries,
        "business_days": {
            "list": [d.isoformat() for d in period_business],
            "closed": [d.isoformat() for d in closed_business],
            "count": len(period_business),
            "closed_count": len(closed_business),
            "month_total": len(month_business),
            "month_remaining": sum(1 for d in month_business if d >= today),
            "holidays": [
                d.isoformat()
                for d in national_holidays_between(start_date, end_date, extra_holidays=extra_period)
            ],
            "source": "national_hardcoded",
            "note": (
                "seg–sex, feriados nacionais, estadual de São Paulo"
                + (", municipal de Santo André" if is_santo_andre_filiale(filiale) else "")
                + " + ponte (feriado em terça/quinta emenda com segunda/sexta)"
            ),
        },
        "reference": reference,
        "expected": {
            "closed": expected_hours_for_days(closed_business, reference),
            "period": expected_hours_for_days(period_business, reference),
            "month": expected_hours_for_days(month_business, reference),
        },
        "gap_days": [d.isoformat() for d in gap_days(closed_business, daily_totals)],
        "outlier_days": sorted(d.isoformat() for d in outlier_days(daily_totals)),
        "monthly_series": monthly_series(daily_totals, today, extra_holidays_for_year=extra_holidays_for_year),
        "comparison": day_matched_comparison(
            daily_totals, start_date, end_date, today, extra_holidays_for_year=extra_holidays_for_year
        ),
        "daily_stats": daily_stats(daily_totals, today),
    }
