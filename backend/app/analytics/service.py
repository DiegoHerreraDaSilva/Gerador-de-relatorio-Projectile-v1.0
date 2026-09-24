"""Orquestra uma mensagem do chat analítico:

    classificar (Jev se houver chave → Claude) → validar → rota
      simple_data              → Query Engine → formatter          (0 Claude)
      simple_with_explanation  → Query Engine → Claude explica     (1 Claude)
      analysis                 → Claude planeja → Python calcula → Claude fecha
      general                  → Claude, sem dados
      out_of_scope             → recusa fixa                       (0 Claude)

Texto do Claude com número que não veio dos dados é descartado (grounding)
e vale o texto determinístico. Falha do Claude nunca derruba a resposta
quando já há dado: cai no texto determinístico."""
from __future__ import annotations

import json
import logging
import time
from datetime import date

from ulid import ULID

from ..core.config import get_settings
from ..projectile_db import ProjectileDbError
from ..services.audit import record_event
from . import analysis, claude_client, query_engine, router
from .grounding import allowed_numbers, is_grounded
from .intents import ANALYSES, INTENTS
from .periods import RELATIVE_PERIODS, mentions_month, month_label, month_options, resolve_period, years_mentioned
from .query_engine import Filters, HoursSource
from .response_formatter import format_reply
from .schemas import ChatContext
from .semantic_model import SOURCES
from .visualization import MAX_VISUALIZATIONS, build_table, build_visualizations

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_REPLY = (
    "Só consigo responder perguntas sobre horas apontadas e relatórios gerados — por exemplo, "
    "\"quantas horas por cliente em setembro?\" ou \"quantos relatórios foram gerados este mês?\". "
    "Não altero dados nem executo consultas livres."
)
UNCLASSIFIED_REPLY = (
    "Não consegui entender a pergunta agora. Tente algo como \"total de horas em agosto\", "
    "\"horas por colaborador nos últimos 3 meses\" ou \"compare agosto com setembro\"."
)
NO_INTENT_REPLY = (
    "Não identifiquei qual número você quer. Posso responder sobre: total de horas, horas por cliente, "
    "projeto, colaborador, pacote ou mês; relatórios gerados, versões, tempo e falhas de geração."
)


def _options(today: date, hours: HoursSource, max_months: int) -> tuple[dict, bool]:
    """Opções que o classificador/Claude podem escolher. Se o Projectile estiver fora
    do ar, as perguntas sobre relatórios (reports_db) continuam funcionando."""
    options = {"today": today.isoformat(), "months": month_options(today, max_months), "clients": [], "employees": []}
    try:
        rows = hours.rows()
    except ProjectileDbError as e:
        logger.warning("Projectile indisponível pro chat analítico: %s", e)
        return options, False
    options["clients"] = sorted({r.client for r in rows}, key=str.casefold)
    options["employees"] = sorted({r.employee for r in rows}, key=str.casefold)
    return options, True


def _previous(context: ChatContext | None, options: dict) -> dict | None:
    if context is None or context.last_intent not in INTENTS:
        return None
    f = context.last_filters
    return {
        "intent": context.last_intent,
        "month": f.month if f and f.month in options["months"] else None,
        "month_end": f.month_end if f and f.month and f.month_end in options["months"] else None,
        "relative": f.relative if f and f.relative in RELATIVE_PERIODS else None,
        "client": f.client if f and f.client in options["clients"] else None,
        "employee": f.employee if f and f.employee in options["employees"] else None,
    }


def _apply_follow_up(c: router.Classification, previous: dict | None) -> router.Classification:
    """"E em agosto?" — o que a mensagem nova não disse vem da anterior."""
    if not (c.follow_up and previous):
        return c
    c.intent = c.intent or previous["intent"]
    if not (c.month or c.relative):
        c.month, c.month_end, c.relative = previous["month"], previous["month_end"], previous["relative"]
    c.client = c.client or previous["client"]
    c.employee = c.employee or previous["employee"]
    if c.route in ("general", "out_of_scope", "unclassified") and c.intent:
        c.route = "simple_data"
    return c


_DATA_ROUTES = {"simple_data", "simple_with_explanation", "analysis"}


def _window_reply(years: list[str], options: dict) -> str:
    months = sorted(options["months"])
    return (
        f"Só tenho dados dos últimos {len(months)} meses ({month_label(months[0])} a {month_label(months[-1])}), "
        f"então não consigo responder sobre {', '.join(years)}."
    )


def _apply_years(
    c: router.Classification, years: list[str], message: str, options: dict,
) -> tuple[router.Classification, list[str]]:
    """"horas em 2025" → janeiro a dezembro de 2025 (cortado na janela).
    Vale quando a mensagem cita ano e NENHUM nome de mês — mesmo que o
    classificador tenha escolhido um mês: pra "horas em 2026" o Jev real
    escolhia janeiro/2026."""
    if not years or c.relative or mentions_month(message):
        return c, []
    months = sorted(m for m in options["months"] if years[0] <= m[:4] <= years[-1])
    if not months:
        return c, []
    c.month, c.month_end = months[0], (months[-1] if months[-1] != months[0] else None)
    notes = []
    if months[0] != f"{years[0]}-01":
        notes.append(f"Só há dados a partir de {month_label(months[0])}.")
    return c, notes


def _grounded_text(text: str | None, fallback: str, *payloads) -> tuple[str, bool]:
    if text and is_grounded(text, allowed_numbers(*payloads)):
        return text, True
    if text:
        logger.warning("Texto do Claude descartado: número que não veio dos dados.")
    return fallback, False


_TOP_N = 3


def _compact_for_claude(result: query_engine.QueryResult, max_bytes: int) -> dict:
    """Resultado agregado + as contas que o Claude tentaria fazer de cabeça
    ao interpretar (participação, acumulado, "os 3 maiores somam", "o resto").
    Medido: sem isso ele somava percentuais (e errava — 81,5% onde o certo
    era 95,5%), o grounding descartava o texto e valia o padrão."""
    compact = result.compact()
    if result.total and result.unit == "hours":
        cumulative = 0.0
        rows = []
        for row in compact["rows"]:
            cumulative += row["value"]
            rows.append({
                **row,
                "share_percent": round(row["value"] / result.total * 100, 1),
                "cumulative_share_percent": round(cumulative / result.total * 100, 1),
            })
        compact["rows"] = rows
        # série mês a mês não tem "os 3 maiores" nem "o resto"
        if result.dimension != "competence" and len(result.rows) > _TOP_N:
            top = sum(row["value"] for row in result.rows[:_TOP_N])
            rest = result.total - top
            compact[f"top_{_TOP_N}"] = {
                "hours": round(top, 2), "share_percent": round(top / result.total * 100, 1),
            }
            compact[f"others_after_top_{_TOP_N}"] = {
                "count": len(result.rows) - _TOP_N,
                "hours": round(rest, 2),
                "share_percent": round(rest / result.total * 100, 1),
            }
    while len(json.dumps(compact, ensure_ascii=False).encode()) > max_bytes and len(compact["rows"]) > 5:
        compact["rows"] = compact["rows"][: len(compact["rows"]) // 2]
        compact["truncated"] = True
    return compact


def _data_answer(c, message, today, hours, settings, usage, notes: list[str] | None = None) -> dict:
    spec = INTENTS[c.intent]
    notes = list(notes or [])
    if not (c.month or c.relative):
        notes.append("Como a pergunta não citou período, considerei os últimos 12 meses.")
    client, employee = c.client, c.employee
    if (client or employee) and not {"client", "employee"} & spec.filters:
        notes.append("Esse número não tem recorte por cliente/colaborador — mostrei o total.")
        client = employee = None
    period = resolve_period(c.month, c.relative, today, settings.analytics_chat_max_months, c.month_end)
    filters = Filters(period, client, employee)
    result = query_engine.run(c.intent, filters, hours, settings.analytics_chat_max_rows)
    reply = format_reply(result)
    explained = None
    if c.route == "simple_with_explanation":
        compact = _compact_for_claude(result, settings.analytics_chat_max_claude_payload_bytes)
        try:
            text = claude_client.explain(usage, message, compact)
        except Exception as e:
            logger.warning("Explicação do Claude indisponível: %s", e)
            text = None
        reply, explained = _grounded_text(text, reply, compact)
    if notes:
        reply = f"{reply} {' '.join(notes)}"
    table = build_table(result)
    return {
        "intent": c.intent,
        "reply": reply,
        "visualizations": build_visualizations(result)[:MAX_VISUALIZATIONS],
        "tables": [table] if table else [],
        "source": spec.source,
        "period": filters.period,
        "filters": {"month": c.month, "month_end": c.month_end, "relative": c.relative, "client": client, "employee": employee},
        "explained": explained,
    }


def _compare_periods_answer(plan, message, options, today, hours, settings, usage) -> dict | None:
    metric = plan.get("metric")
    month_a, month_b = plan.get("period_a_month"), plan.get("period_b_month")
    if (
        metric not in INTENTS or INTENTS[metric].source != "projectile"
        or month_a not in options["months"] or month_b not in options["months"]
        or month_a == month_b  # "julho x julho" — comparação sem sentido, variação sempre zero
    ):
        logger.warning("Plano de compare_periods rejeitado: %s", plan)
        return None
    client = plan.get("client") if plan.get("client") in options["clients"] else None
    employee = plan.get("employee") if plan.get("employee") in options["employees"] else None
    max_months = settings.analytics_chat_max_months
    filters_a = Filters(resolve_period(month_a, None, today, max_months), client, employee)
    filters_b = Filters(resolve_period(month_b, None, today, max_months), client, employee)
    result = analysis.compare_periods(metric, filters_a, filters_b, hours, settings.analytics_chat_max_rows)
    return {
        "result": result,
        "intent": metric,
        "period": filters_b.period,
        "period_compared": filters_a.period,
        "filters": {"month": month_b, "month_end": None, "relative": None, "client": client, "employee": employee},
    }


def _compare_items_answer(plan, message, options, today, hours, settings, usage) -> dict | None:
    kind = plan.get("item_kind")
    if kind not in analysis.ITEM_INTENTS:
        logger.warning("Plano de compare_items rejeitado (item_kind): %s", plan)
        return None
    valid = options["clients"] if kind == "client" else options["employees"]
    items = list(dict.fromkeys(item for item in plan.get("items") or [] if item in valid))[: analysis.MAX_ITEMS]
    if len(items) < 2:
        logger.warning("Plano de compare_items rejeitado (menos de 2 itens válidos): %s", plan)
        return None
    month = plan.get("month") if plan.get("month") in options["months"] else None
    month_end = plan.get("month_end") if month and plan.get("month_end") in options["months"] else None
    relative = plan.get("relative_period") if plan.get("relative_period") in RELATIVE_PERIODS else None
    period = resolve_period(month, relative, today, settings.analytics_chat_max_months, month_end)
    result = analysis.compare_items(kind, items, Filters(period), hours, settings.analytics_chat_max_rows)
    return {
        "result": result,
        "intent": analysis.ITEM_INTENTS[kind],
        "period": period,
        "period_compared": None,
        "filters": {"month": month, "month_end": month_end, "relative": relative, "client": None, "employee": None},
    }


_ANALYSIS_HANDLERS = {"compare_periods": _compare_periods_answer, "compare_items": _compare_items_answer}


def _analysis_answer(c, message, previous, options, today, hours, settings, usage) -> dict | None:
    try:
        plan = claude_client.plan_analysis(usage, message, previous, options)
    except Exception as e:
        logger.warning("Planner do Claude indisponível: %s", e)
        return None
    handler = _ANALYSIS_HANDLERS.get(plan.get("analysis"))
    planned = handler(plan, message, options, today, hours, settings, usage) if handler else None
    if planned is None:
        return None
    result = planned["result"]
    try:
        text = claude_client.finalize_analysis(usage, message, result["summary"])
    except Exception as e:
        logger.warning("Finalizer do Claude indisponível: %s", e)
        text = None
    reply, explained = _grounded_text(text, analysis.fallback_text(result), result["summary"])
    table = analysis.table(result)
    return {
        "intent": planned["intent"],
        "analysis": plan["analysis"],
        "reply": reply,
        "visualizations": analysis.visualizations(result)[:MAX_VISUALIZATIONS],
        "tables": [table] if table else [],
        "source": "projectile",
        "period": planned["period"],
        "period_compared": planned["period_compared"],
        "filters": planned["filters"],
        "explained": explained,
    }


def handle(message: str, context: ChatContext | None, user: dict) -> dict:
    started = time.monotonic()
    settings = get_settings()
    today = date.today()
    usage = claude_client.ClaudeUsage()
    conversation_id = context.conversation_id if context and context.conversation_id else str(ULID())
    hours = HoursSource(today, settings.analytics_chat_max_months)
    status = "failed"
    c = None
    answer: dict = {}
    try:
        options, _ = _options(today, hours, settings.analytics_chat_max_months)
        previous = _previous(context, options)
        c = _apply_follow_up(
            router.classify(
                message, previous, options, settings.jev_min_confidence, usage, settings.jev_min_confidence_none,
            ),
            previous,
        )

        years = years_mentioned(message)
        window_years = {key[:4] for key in options["months"]}
        outside = [year for year in years if year not in window_years]
        c, year_notes = _apply_years(c, years, message, options)

        if c.route in _DATA_ROUTES and outside:
            answer = {"reply": _window_reply(outside, options)}
        elif c.route == "unclassified":
            answer = {"reply": UNCLASSIFIED_REPLY}
        elif c.route == "out_of_scope":
            answer = {"reply": OUT_OF_SCOPE_REPLY}
        elif c.route == "general":
            try:
                answer = {"reply": claude_client.general_answer(usage, message) or UNCLASSIFIED_REPLY}
            except Exception as e:
                logger.warning("Resposta geral do Claude indisponível: %s", e)
                answer = {"reply": UNCLASSIFIED_REPLY}
        elif c.route == "analysis":
            answer = _analysis_answer(c, message, previous, options, today, hours, settings, usage) or {
                "reply": "Não consegui montar essa comparação agora. Tente, por exemplo, \"compare horas por cliente de agosto e setembro\" "
                "ou \"compare as horas da Mercedes e da Lauer em julho\"."
            }
        elif c.intent is None:
            answer = {"reply": NO_INTENT_REPLY}
        else:
            answer = _data_answer(c, message, today, hours, settings, usage, year_notes)
        status = "success"
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        record_event(
            actor_id=user["login"], actor_name=user.get("name", ""), action="analytics_chat_query",
            entity_type="analytics_chat", entity_id=conversation_id, source="analytics_chat",
            metadata={
                "message": message[:300],
                "status": status,
                "route": c.route if c else None,
                "intent": answer.get("intent"),
                "filters": answer.get("filters"),
                "classifier": c.classifier if c else None,
                "jev_called": c.jev_called if c else False,
                "jev_confidence": c.confidence if c else None,
                "claude_calls": usage.calls,
                "claude_models": usage.models,
                "tokens_input": usage.input_tokens,
                "tokens_output": usage.output_tokens,
                "latency_ms": latency_ms,
            },
        )

    period = answer.get("period")
    metadata = {
        "source": answer.get("source"),
        "source_label": SOURCES.get(answer.get("source") or "", None),
        **(period.as_metadata() if period else {}),
        "classifier": c.classifier,
        "jev_confidence": c.confidence,
        "claude_calls": usage.calls,
        # True: texto do Claude usado; False: descartado pelo grounding ou
        # Claude falhou (vale o texto determinístico); None: rota sem Claude
        "claude_text_used": answer.get("explained"),
        "latency_ms": latency_ms,
    }
    if answer.get("period_compared"):
        metadata["compared_period_label"] = answer["period_compared"].label
    filters = answer.get("filters")
    return {
        "conversation_id": conversation_id,
        "route": c.route,
        "intent": answer.get("intent"),
        "reply": answer["reply"],
        "visualizations": answer.get("visualizations", []),
        "tables": answer.get("tables", []),
        "metadata": metadata,
        "context": {
            "conversation_id": conversation_id,
            "last_intent": answer.get("intent") if answer.get("intent") in INTENTS else None,
            "last_filters": filters,
        },
    }
