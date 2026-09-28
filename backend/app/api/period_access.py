"""Janela de período de quem NÃO é gerente (coordenador e colaborador):
os últimos 12 meses corridos (o mês atual e os 11 anteriores) e o ano atual
inteiro — decisão do usuário (2026-09-28): fora disso, nada se vê nem se
filtra, em nenhuma tela. Gerente não tem limite.

Uma regra só, usada por todas as rotas (busca no Projectile, Diagnóstico,
Dashboard de horas, Histórico, Minhas revisões) — a tela só esconde; quem
barra de verdade é o backend. O ano atual está sempre dentro dos últimos 12
meses até o mês corrente; ele só estende a janela pros meses que ainda vão
chegar (um relatório de novembro preparado em outubro)."""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from .dependencies import is_manager

_MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro")


def window(today: date | None = None) -> tuple[date, date]:
    """(1º dia de 11 meses atrás, 31/12 do ano atual)."""
    today = today or date.today()
    index = today.year * 12 + today.month - 1 - 11
    return date(index // 12, index % 12 + 1, 1), date(today.year, 12, 31)


def window_for(user: dict, today: date | None = None) -> tuple[date, date] | None:
    """A janela de `user`; None = gerente (sem limite)."""
    return None if is_manager(user) else window(today)


def window_label(today: date | None = None) -> str:
    start, end = window(today)
    return f"{_MONTHS[start.month - 1]}/{start.year} a {_MONTHS[end.month - 1]}/{end.year}"


def error_message(today: date | None = None) -> str:
    return f"Fora do período permitido: só os últimos 12 meses e o ano atual ({window_label(today)})."


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def in_window(user: dict, start: date | str, end: date | str | None = None, today: date | None = None) -> bool:
    limits = window_for(user, today)
    if limits is None:
        return True
    first, last = limits
    return first <= _as_date(start) and _as_date(end if end is not None else start) <= last


def check_range(user: dict, start: date | str, end: date | str | None = None, today: date | None = None) -> None:
    """403 se o intervalo [start, end] sai da janela (gerente sempre passa)."""
    if not in_window(user, start, end, today):
        raise HTTPException(403, error_message(today))


def check_month(user: dict, month: str | None, today: date | None = None) -> None:
    """Mesma checagem pra um mês "AAAA-MM" (None = sem mês, passa)."""
    if month:
        check_range(user, f"{month[:7]}-01", today=today)


def allowed_months(today: date | None = None) -> list[str]:
    """"AAAA-MM" da janela, do mais antigo ao mais novo."""
    start, end = window(today)
    months, index = [], start.year * 12 + start.month - 1
    while index <= end.year * 12 + end.month - 1:
        months.append(f"{index // 12:04d}-{index % 12 + 1:02d}")
        index += 1
    return months
