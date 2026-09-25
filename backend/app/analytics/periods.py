"""Períodos que o chat entende. A granularidade é o MÊS (competência) de
propósito: o Jev só escolhe entre opções dadas (não extrai datas), então o
período vira perguntas de escolha — um mês (ou o primeiro de um intervalo),
o último mês do intervalo, ou um período relativo — com opções montadas aqui."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

MONTH_NAMES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
MONTH_NAMES_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

RELATIVE_PERIODS = {
    "current_month": ("this month / este mês / mês atual", 1, 0),
    "last_month": ("last month / mês passado / mês anterior", 1, 1),
    "last_3_months": ("last 3 months / últimos 3 meses / trimestre", 3, 0),
    "last_6_months": ("last 6 months / últimos 6 meses / semestre", 6, 0),
    "last_12_months": ("last 12 months / últimos 12 meses / último ano", 12, 0),
}
DEFAULT_RELATIVE = "last_12_months"


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str

    def as_metadata(self) -> dict:
        return {"period_start": self.start.isoformat(), "period_end": self.end.isoformat(), "period_label": self.label}

    @property
    def phrase(self) -> str:
        """"em setembro/2026" ou "de julho/2026 a setembro/2026" — pro texto."""
        return f"de {self.label}" if " a " in self.label else f"em {self.label}"


def add_months(base: date, delta: int) -> date:
    index = base.year * 12 + base.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def _month_end(first: date) -> date:
    return add_months(first, 1) - timedelta(days=1)


def month_key(first: date) -> str:
    return f"{first.year:04d}-{first.month:02d}"


def month_label(key: str) -> str:
    year, month = key.split("-")
    return f"{MONTH_NAMES_PT[int(month) - 1]}/{year}"


def month_options(today: date, months: int) -> dict[str, str]:
    """`{"2026-09": "September 2026 (setembro de 2026)", ...}` — os últimos
    `months` meses, mais recente primeiro. A descrição em inglês vem primeiro
    porque o Jev acerta mais em inglês (docs da TypeSafe)."""
    current = date(today.year, today.month, 1)
    options = {}
    for i in range(months):
        first = add_months(current, -i)
        options[month_key(first)] = (
            f"{MONTH_NAMES_EN[first.month - 1]} {first.year} "
            f"({MONTH_NAMES_PT[first.month - 1]} de {first.year})"
        )
    return options


def _parse_month(key: str, oldest: date, current: date) -> date:
    year, mon = (int(part) for part in key.split("-"))
    first = date(year, mon, 1)
    if not oldest <= first <= current:
        raise ValueError(f"Mês fora da janela permitida: {key}")
    return first


_YEAR = re.compile(r"\b(20\d{2})\b")


def years_mentioned(message: str) -> list[str]:
    """Anos citados na mensagem ("em 2025", "de 2024 a 2025"). Determinístico
    de propósito: o Jev só escolhe entre os meses da janela, então um ano fora
    dela (ou um ano inteiro) nunca vira opção pra ele. `\b` evita pegar
    números colados em texto, como "PP2030"."""
    return sorted(set(_YEAR.findall(message)))


def _plain(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(ch) != "Mn")


_MONTH_NAMES_PLAIN = sorted({_plain(n) for n in MONTH_NAMES_PT} | {_plain(n)[:3] for n in MONTH_NAMES_PT}, key=len, reverse=True)
_MONTH_WORD = re.compile(r"\b(" + "|".join(_MONTH_NAMES_PLAIN) + r")\b")


def mentions_month(message: str) -> bool:
    """Cita um mês pelo nome ("março", "marco", "ago/2025")?"""
    return bool(_MONTH_WORD.search(_plain(message)))


def resolve_period(
    month: str | None, relative: str | None, today: date, max_months: int, month_end: str | None = None,
) -> Period:
    """Mês específico (ou intervalo `month`..`month_end`) tem prioridade sobre
    período relativo; sem nenhum, últimos 12 meses (a resposta sempre diz
    qual período usou). Valida contra a janela permitida — quem chama já
    filtrou pelas opções, mas isto é a última barreira."""
    current = date(today.year, today.month, 1)
    oldest = add_months(current, -(max_months - 1))
    if month:
        first = _parse_month(month, oldest, current)
        last = _parse_month(month_end, oldest, current) if month_end else first
        if last < first:  # "de agosto a fevereiro" — ordem invertida na frase
            first, last = last, first
        if first == last:
            return Period(first, _month_end(first), month_label(month_key(first)))
        label = f"{month_label(month_key(first))} a {month_label(month_key(last))}"
        return Period(first, _month_end(last), label)
    key = relative or DEFAULT_RELATIVE
    if key not in RELATIVE_PERIODS:
        raise ValueError(f"Período desconhecido: {key}")
    _, span, offset = RELATIVE_PERIODS[key]
    last_first = add_months(current, -offset)
    first = add_months(last_first, -(span - 1))
    # até o fim do mês, não até hoje: o Painel conta apontamento lançado com
    # data futura no mês corrente (medido: 32 h em setembro/2026)
    end = _month_end(last_first)
    if span == 1:
        label = month_label(month_key(first))
    else:
        label = f"{month_label(month_key(first))} a {month_label(month_key(last_first))}"
    return Period(first, end, label)
