"""Texto da resposta sem LLM (rota `simple_data`). Também é o texto de
reserva quando o Claude falha ou devolve número que não veio dos dados."""
from __future__ import annotations

from .query_engine import QueryResult
from .semantic_model import DIMENSIONS, fmt_hours, fmt_number

_TOP_IN_TEXT = 3


def _scope(result: QueryResult) -> str:
    parts = [result.filters.period.phrase]
    if result.filters.client:
        parts.append(f"cliente {result.filters.client}")
    if result.filters.employee:
        parts.append(f"colaborador {result.filters.employee}")
    return ", ".join(parts)


def _top(result: QueryResult) -> str:
    fmt = fmt_hours if result.unit == "hours" else fmt_number
    items = [f"{row['label']} ({fmt(row['value'])})" for row in result.rows[:_TOP_IN_TEXT]]
    return "; ".join(items)


def format_reply(result: QueryResult) -> str:
    scope = _scope(result)
    intent = result.intent

    if intent == "report_count":
        return f"Foram gerados {fmt_number(result.total)} relatórios {scope}."
    if intent == "version_count":
        return f"Foram criadas {fmt_number(result.total)} versões de relatório {scope}."
    if intent == "generation_failures":
        rate = result.extra.get("failure_rate_percent")
        rate_text = f" ({fmt_number(rate)}% das {fmt_number(result.extra.get('generations'))} gerações)" if rate is not None else ""
        return f"{fmt_number(result.total)} gerações falharam {scope}{rate_text}."
    if intent == "generation_time":
        if result.total is None:
            return f"Nenhuma geração concluída {scope}."
        return f"A geração levou em média {fmt_number(result.total)} ms {scope}."
    if intent == "total_hours":
        return f"Foram apontadas {fmt_hours(result.total)} {scope}."

    if not result.rows:
        return f"Não encontrei dados {scope}."
    dimension = DIMENSIONS.get(result.dimension or "", "item").lower()
    if intent in ("hours_by_competence", "reports_by_month"):
        unit_total = fmt_hours(result.total) if result.unit == "hours" else fmt_number(result.total)
        return f"Total de {unit_total} {scope}, distribuído em {len(result.rows)} meses (detalhe na tabela)."
    total = fmt_hours(result.total) if result.unit == "hours" else fmt_number(result.total)
    more = " Mostrando só os primeiros." if result.truncated else ""
    return (
        f"Total de {total} {scope}, em {len(result.rows)} {dimension}(s). "
        f"Maiores: {_top(result)}.{more}"
    )
