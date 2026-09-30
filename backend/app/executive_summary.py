"""Resumo executivo do mês (Painel de Gerência, só gerente).

Os NÚMEROS saem sempre de Python, da mesma função do Painel (`management.compute_monthly_kpis`): horas
trabalhadas e faturadas, performance, não faturável, prazo de elaboração, variação sobre o mês anterior e o
status de envio dos relatórios. O texto tem duas origens, e o usuário vê qual foi:

- **automático** (`deterministic_text`): frases montadas dos números — sempre funciona, sem IA;
- **Claude** (opcional): reescreve em tom executivo, recebendo SÓ os números agregados (nenhum nome de cliente
  vai pra fora), e o texto só vale se TODO número dele veio dos fatos (`analytics.grounding.is_grounded`). Sem
  chave, falha da API ou número inventado: cai no texto automático, com o motivo.

As pendências de envio (nomes de cliente) são acrescentadas localmente depois, nunca passam pela IA. Regra do
projeto mantida: IA explica, não calcula."""

from __future__ import annotations

import logging
import os
from datetime import date

from . import management
from .analytics import claude_client, grounding
from .auto_generation import builder

logger = logging.getLogger(__name__)

WINDOW_MONTHS = 12
MAX_PENDING_CLIENTS = 5


class SummaryError(ValueError):
    """Mês inválido ou fora da janela do Painel (vira 400 na rota)."""


def previous_month(month: str) -> str:
    year, m = (int(part) for part in month.split("-"))
    return f"{year - 1}-12" if m == 1 else f"{year}-{m - 1:02d}"


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100, 1)


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def build_facts(kpis: dict, month: str) -> dict:
    """Os fatos do mês a partir do resultado de `compute_monthly_kpis`. Função pura (sem banco) — testável com
    um dict. Levanta `SummaryError` se o mês não está no resultado."""
    rows = {row["month"]: row for row in kpis.get("months", [])}
    row = rows.get(month)
    if row is None:
        raise SummaryError("Mês fora da janela do Painel (últimos 12 meses).")
    prev = rows.get(previous_month(month))

    worked = row["worked_hours"]
    worked_delta = None
    if prev and prev["worked_hours"] > 0:
        worked_delta = _r((worked - prev["worked_hours"]) / prev["worked_hours"] * 100)
    perf, prev_perf = row.get("perf_kpi_pct"), (prev or {}).get("perf_kpi_pct")
    perf_delta = _r((perf - prev_perf) * 100) if perf is not None and prev_perf is not None else None

    status_rows = [r for r in kpis.get("project_send_status", []) if r["month"] == month]
    counts = {status: sum(1 for r in status_rows if r["status"] == status) for status in ("sent", "partial", "none", "closed")}
    pending: dict[str, int] = {}
    for r in status_rows:
        if r["status"] in ("none", "partial"):
            pending[r["client"]] = pending.get(r["client"], 0) + 1
    pending_clients = [{"client": c, "projects": n} for c, n in sorted(pending.items(), key=lambda item: (-item[1], item[0].casefold()))]

    return {
        "month": month,
        "month_label": builder.month_label(month),
        "worked_hours": _r(worked),
        "billed_hours": _r(row.get("billed_hours")),
        "performance_pct": _pct(perf),
        "nonbillable_hours": _r(row.get("nonbillable_hours")),
        "nonbillable_pct": _pct(row.get("nonbillable_kpi_pct")),
        "elaboration_days": _r(row.get("elaboration_days")),
        "previous_month_label": builder.month_label(previous_month(month)) if prev else None,
        "worked_delta_pct": worked_delta,
        "performance_delta_pts": perf_delta,
        "send": {**counts, "total": sum(counts.values()), "pending_projects": counts["partial"] + counts["none"]},
        "pending_clients": pending_clients,
    }


def _num(value: float, digits: int = 1) -> str:
    """Formato brasileiro: 3.041,8."""
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _variation(delta: float | None, unit: str, label: str | None) -> str:
    if delta is None or not label:
        return ""
    if delta == 0:
        return f", igual a {label}"
    direction = "acima" if delta > 0 else "abaixo"
    return f", {_num(abs(delta))}{unit} {direction} de {label}"


def pending_line(facts: dict) -> str:
    """ "Pendências por cliente: A (2), B (1)". Nomes só aqui, localmente — a IA nunca os vê."""
    clients = facts["pending_clients"]
    if not clients:
        return ""
    shown = ", ".join(f"{c['client']} ({c['projects']})" for c in clients[:MAX_PENDING_CLIENTS])
    extra = len(clients) - MAX_PENDING_CLIENTS
    return f"Pendências por cliente: {shown}" + (f" e mais {extra}." if extra > 0 else ".")


def deterministic_text(facts: dict) -> str:
    """O resumo sem IA: só os números dos fatos, em frases."""
    label = facts["month_label"]
    prev = facts["previous_month_label"]
    parts = [f"Em {label}, a engenharia apontou {_num(facts['worked_hours'])} h{_variation(facts['worked_delta_pct'], '%', prev)}."]
    if facts["billed_hours"] is None:
        parts.append("Ainda não há horas faturadas registradas para o mês, então a performance não pôde ser calculada.")
    else:
        sentence = f"Foram faturadas {_num(facts['billed_hours'])} h"
        if facts["performance_pct"] is not None:
            sentence += f", performance de {_num(facts['performance_pct'])}%"
            sentence += _variation(facts["performance_delta_pts"], " p.p.", prev)
        parts.append(sentence + ".")
    if facts["nonbillable_pct"] is not None:
        parts.append(f"As horas não faturáveis somaram {_num(facts['nonbillable_hours'])} h ({_num(facts['nonbillable_pct'])}% do total).")
    if facts["elaboration_days"] is not None:
        parts.append(f"O prazo médio de elaboração foi de {_num(facts['elaboration_days'])} dias úteis.")
    send = facts["send"]
    if send["total"]:
        if send["pending_projects"] == 0:
            parts.append(f"Todos os {send['total'] - send['closed']} relatórios do mês foram enviados." if send["total"] > send["closed"] else "")
        else:
            parts.append(
                f"Dos {send['total']} projetos do mês, {send['sent']} tiveram o relatório enviado e {send['pending_projects']} ainda estão sem envio completo."
            )
    return " ".join(p for p in parts if p)


def _ai_facts(facts: dict) -> dict:
    """O que o Claude recebe: números agregados, sem nomes de cliente."""
    return {k: v for k, v in facts.items() if k != "pending_clients"}


def ai_text(facts: dict) -> str | None:
    """O texto do Claude, ou `None` se não deu (sem chave, API fora, número inventado). Nunca levanta."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    payload = _ai_facts(facts)
    try:
        text = claude_client.summarize(claude_client.ClaudeUsage(), payload)
    except Exception:  # noqa: BLE001 — resumo é conforto (sem chave, API fora...), nunca derruba a tela
        logger.warning("Claude indisponível para o resumo executivo", exc_info=True)
        return None
    if not text or not grounding.is_grounded(text, grounding.allowed_numbers(payload)):
        logger.info("Texto do Claude descartado no resumo executivo: número fora dos fatos")
        return None
    return text


def generate(month: str, use_ai: bool = True, today: date | None = None) -> dict:
    """Fatos + texto do mês. `source`: "claude" ou "automatico"; `ai_note` explica quando a IA não foi usada."""
    today = today or date.today()
    if len(month) != 7 or month[4] != "-" or not month[:4].isdigit() or not month[5:].isdigit() or not 1 <= int(month[5:]) <= 12:
        raise SummaryError("Mês inválido (use AAAA-MM).")
    if month > today.strftime("%Y-%m"):
        raise SummaryError("Esse mês ainda não começou.")
    kpis = management.compute_monthly_kpis(months=WINDOW_MONTHS)
    facts = build_facts(kpis, month)
    automatic = deterministic_text(facts)
    text, source, note = automatic, "automatico", None
    if use_ai:
        written = ai_text(facts)
        if written:
            text, source = written, "claude"
        else:
            note = "A IA não pôde redigir agora; este é o texto automático, com os mesmos números."
    line = pending_line(facts)
    return {"month": month, "facts": facts, "text": f"{text}\n\n{line}" if line else text, "source": source, "ai_note": note}
