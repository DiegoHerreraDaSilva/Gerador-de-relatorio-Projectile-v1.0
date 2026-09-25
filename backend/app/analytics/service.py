"""Orquestra uma mensagem do chat analítico:

    classificar (Jev se houver chave → Claude) → validar → rota
      simple_data              → atalho da intent → consulta cruzada → texto fixo  (0 Claude)
      simple_with_explanation  → idem → Claude explica o resultado já agregado        (1 Claude)
      analysis                 → planner do Claude monta a consulta cruzada inteira
                                 (query) ou a comparação de períodos → Python calcula
      general                  → Claude, sem dados
      out_of_scope             → recusa fixa                                            (0 Claude)

Relatórios gerados (reports_db) têm handler próprio (`query_engine.py`);
horas, faturado e status de envio passam pela consulta cruzada
(`crossquery.py`), com a mesma regra do Painel de Gerência/Diagnóstico.

Texto do Claude com número que não veio dos dados é descartado e vale o
texto determinístico (grounding). Falha do Claude nunca derruba uma
resposta que já tem dado."""
from __future__ import annotations

import logging
import time
from datetime import date

from ulid import ULID

from ..core.config import get_settings
from ..projectile_db import ProjectileDbError
from ..services.audit import record_event
from . import analysis, claude_client, cross_output, crossquery, query_engine, router, signals
from .catalog import BILLING_TYPES, COST_CENTERS
from .facts import DataSources
from .grounding import allowed_numbers, is_grounded
from .intents import INTENTS
from .periods import RELATIVE_PERIODS, mentions_month, month_label, month_options, resolve_period, years_mentioned
from .query_engine import Filters
from .response_formatter import format_reply
from .schemas import ChatContext
from .semantic_model import SOURCES
from .visualization import MAX_VISUALIZATIONS, build_table, build_visualizations

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_REPLY = (
    "Só consigo responder perguntas sobre horas apontadas, faturado, status de envio e relatórios gerados — por "
    "exemplo, \"quantas horas por cliente em setembro?\" ou \"faturado x trabalhado por projeto em agosto\". "
    "Não altero dados nem executo consultas livres."
)
UNCLASSIFIED_REPLY = (
    "Não consegui entender a pergunta agora. Tente algo como \"total de horas em agosto\", "
    "\"horas de cada colaborador por projeto nos últimos 3 meses\" ou \"compare agosto com setembro\"."
)
NO_ANALYSIS_REPLY = (
    "Não consegui montar essa consulta agora. Tente, por exemplo, \"horas de cada colaborador por projeto em "
    "agosto\", \"compare horas por cliente de agosto e setembro\" ou \"Mercedes x Lauer em julho\"."
)
NO_PERIOD_NOTE = "Como a pergunta não citou período, considerei os últimos 12 meses."

_DATA_ROUTES = {"simple_data", "simple_with_explanation", "analysis"}
SOURCE_BY_DATASET = {"hours": "projectile", "billing": "billing", "send_status": "send_status"}


def _options(today: date, sources: DataSources, max_months: int) -> tuple[dict, bool]:
    """Opções que o classificador/Claude podem escolher. Se o Projectile estiver fora
    do ar, as perguntas sobre relatórios (reports_db) continuam funcionando."""
    options = {
        "today": today.isoformat(), "months": month_options(today, max_months),
        "clients": [], "employees": [], "projects": [], "packages": [],
    }
    try:
        rows = sources.hours()
    except ProjectileDbError as e:
        logger.warning("Projectile indisponível pro chat analítico: %s", e)
        return options, False
    for key, attr in (("clients", "client"), ("employees", "employee"), ("projects", "project"), ("packages", "package")):
        options[key] = sorted({getattr(r, attr) for r in rows}, key=str.casefold)
    return options, True


def _previous(context: ChatContext | None, options: dict) -> dict | None:
    if context is None:
        return None
    intent = context.last_intent if context.last_intent in INTENTS else None
    spec = context.last_spec.model_dump() if context.last_spec else None
    if intent is None and spec is None:
        return None
    f = context.last_filters
    return {
        "intent": intent,
        "month": f.month if f and f.month in options["months"] else None,
        "month_end": f.month_end if f and f.month and f.month_end in options["months"] else None,
        "relative": f.relative if f and f.relative in RELATIVE_PERIODS else None,
        "client": f.client if f and f.client in options["clients"] else None,
        "employee": f.employee if f and f.employee in options["employees"] else None,
        "project": f.project if f and f.project in options["projects"] else None,
        "spec": spec,
    }


_INHERITED_FILTERS = ("clients", "projects", "project_match", "employees", "packages")


def _apply_follow_up(c: router.Classification, previous: dict | None, message: str = "") -> router.Classification:
    """"E em agosto?" — o que a mensagem nova não disse vem da anterior. Se
    a anterior foi um cruzamento (sem intent simples), o planner continua a
    partir da consulta anterior (`previous["spec"]`).

    Filtros de VÁRIOS valores da consulta anterior (4 projetos "Estribo", 2
    clientes) também são herdados, em `c.inherited`: `last_filters` só guarda
    filtro de um valor, e sem isso "e durante o ano?" perdia o recorte e
    respondia o time inteiro. Não herda se a pergunta pede o todo."""
    if not (c.follow_up and previous):
        return c
    spec = previous.get("spec") or {}
    if not signals.asks_everyone(message):
        c.inherited = {key: list(spec[key]) for key in _INHERITED_FILTERS if spec.get(key)}
    if previous["intent"] is None and previous.get("spec"):
        c.route = "analysis"
        return c
    c.intent = c.intent or previous["intent"]
    if not (c.month or c.relative):
        c.month, c.month_end, c.relative = previous["month"], previous["month_end"], previous["relative"]
    c.client = c.client or previous["client"]
    c.employee = c.employee or previous["employee"]
    c.project = c.project or previous.get("project")
    if c.route in ("general", "out_of_scope", "unclassified") and c.intent:
        c.route = "simple_data"
    return c


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
    if not years or mentions_month(message):
        return c, []
    months = sorted(m for m in options["months"] if years[0] <= m[:4] <= years[-1])
    if not months:
        return c, []
    # ano escrito no texto é mais específico que o período relativo que o
    # classificador escolheu (o Jev marcava "último ano" pra "no ano")
    c.relative = None
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


def _context_filters(spec: crossquery.QuerySpec) -> dict:
    """Filtros de um valor só, no formato que o Jev/follow-up simples usa."""
    def one(values):
        return values[0] if len(values) == 1 else None

    return {
        "month": spec.month, "month_end": spec.month_end, "relative": spec.relative,
        "client": one(spec.clients), "employee": one(spec.employees), "project": one(spec.projects),
    }


def _with_project_family(raw: dict, message: str, options: dict) -> tuple[dict, list[str]]:
    """Nome de projeto pela metade → filtro "nome contém" (`project_match`):
    - projeto escolhido pelo Jev/planner cujo nome, no trecho que a pergunta
      citou, é compartilhado por outros ("estribo" → os 4 Estribo);
    - nenhum projeto escolhido, mas a pergunta tem um trecho de nome de
      projeto ("horas legislation package") — antes, somava os 87 projetos.
    Com aviso de quantos projetos entraram."""
    if raw.get("project_match"):
        # projeto que já está dentro de uma frase herdada não aparece duas vezes
        kept = [p for p in raw.get("projects") or []
                if not any(signals.matches_phrase(ph, p) for ph in raw["project_match"])]
        return {**raw, "projects": kept}, []
    selected = [p for p in (raw.get("projects") or []) if p in options["projects"]]
    if selected:
        phrases, kept = signals.family_phrases(message, selected, options["projects"])
    else:
        phrase = signals.detect_project_phrase(
            message, options["projects"], [*options["clients"], *options["employees"]])
        phrases, kept = ([phrase] if phrase else []), []
    if not phrases:
        return raw, []
    # sem aviso à parte: o recorte da resposta já diz "projetos com “Estribo” no nome (4)"
    return {**raw, "projects": kept, "project_match": phrases}, []


def _without_unasked_project_split(raw: dict, message: str) -> dict:
    """"horas nos projetos Legislation Package - Encapsulamento, mês a mês":
    já filtra por nome de projeto e não pede "por projeto" — o planner às
    vezes quebrava por projeto também, e como o Projectile abre um projeto
    por mês, virava 6 linhas com um pico cada. Comparação ("A x B") e "por
    projeto"/"cada projeto" continuam quebrando."""
    group_by = raw.get("group_by") or []
    if (
        raw.get("project_match") and "project" in group_by
        and "project" not in signals.asked_dimensions(message) and not signals.is_versus(message)
    ):
        return {**raw, "group_by": [d for d in group_by if d != "project"]}
    return raw


def _with_cost_center(raw: dict, message: str) -> dict:
    """Pergunta que cita só CAD ou só CAE, ou pede "só faturáveis", filtra
    por isso se quem montou a consulta esqueceu (e não está agrupando por
    essa mesma dimensão)."""
    center = signals.single_cost_center(message)
    # "vazio" = nenhum valor VÁLIDO: o planner às vezes devolve "all"/"none"
    valid_centers = [c for c in raw.get("cost_centers") or [] if c in COST_CENTERS]
    if center and not valid_centers and "cost_center" not in (raw.get("group_by") or []):
        raw = {**raw, "cost_centers": [center]}
    billing = signals.only_billing_type(message)
    if billing and raw.get("billing_type") not in BILLING_TYPES and "billing_type" not in (raw.get("group_by") or []):
        raw = {**raw, "billing_type": billing}
    return raw


def _cross_answer(raw: dict, message: str, today: date, sources: DataSources, settings, usage, options: dict,
                  *, explain: bool, intent: str | None, notes: list[str] | None = None) -> dict:
    raw, family_notes = _with_project_family(raw, message, options)
    raw = _without_unasked_project_split(_with_cost_center(raw, message), message)
    spec, spec_notes = crossquery.build_spec(raw, options, today, settings.analytics_chat_max_months)
    all_notes = list(notes or []) + family_notes + spec_notes
    if not (spec.month or spec.relative):
        all_notes.append(NO_PERIOD_NOTE)
    result = crossquery.execute(spec, sources, settings.analytics_chat_max_rows, all_notes)
    reply = cross_output.format_reply(result)
    explained = None
    if explain:
        compact = cross_output.compact_for_claude(result, settings.analytics_chat_max_claude_payload_bytes)
        try:
            text = claude_client.explain(usage, message, compact)
        except Exception as e:
            logger.warning("Explicação do Claude indisponível: %s", e)
            text = None
        reply, explained = _grounded_text(text, reply, compact)
        if explained and result.notes:
            reply = f"{reply} {' '.join(result.notes)}"
    return {
        "intent": intent,
        "reply": reply,
        "visualizations": cross_output.build_visualizations(result)[: cross_output.MAX_VISUALIZATIONS],
        "tables": cross_output.build_tables(result),
        "source": SOURCE_BY_DATASET[spec.dataset],
        "period": spec.period,
        "filters": _context_filters(spec),
        "spec": spec,
        "explained": explained,
    }


def _reports_answer(c, message, today, settings, usage, notes: list[str]) -> dict:
    """Relatórios gerados (reports_db) — handler fixo, sem recorte de cliente/pessoa."""
    notes = list(notes)
    if not (c.month or c.relative):
        notes.append(NO_PERIOD_NOTE)
    if c.client or c.employee or c.project:
        notes.append("Esse número não tem recorte por cliente/projeto/colaborador — mostrei o total.")
    period = resolve_period(c.month, c.relative, today, settings.analytics_chat_max_months, c.month_end)
    result = query_engine.run(c.intent, Filters(period), None, settings.analytics_chat_max_rows)
    reply = format_reply(result)
    explained = None
    if c.route == "simple_with_explanation":
        compact = result.compact()
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
        "source": "reports_db",
        "period": period,
        "filters": {"month": c.month, "month_end": c.month_end, "relative": c.relative,
                    "client": None, "employee": None, "project": None},
        "explained": explained,
    }


def _inherit(raw: dict, c: router.Classification, message: str) -> None:
    """Filtro que a pergunta nova não trouxe vem da anterior (`c.inherited`).
    Também vale quando quem montou a consulta pegou só UM PEDAÇO do recorte
    anterior sem a pergunta citar nenhum desses nomes (o planner copiava 1
    dos 4 projetos "Estribo" em "e durante o ano?"). Se a pergunta cita o
    nome ("e só o estribo 07.2026?"), vale o que ela escolheu."""
    words = signals.name_tokens(message)
    named_project = any(words & signals.name_tokens(p) for p in raw.get("projects") or [])
    for key, values in c.inherited.items():
        if key == "project_match" and named_project:
            continue  # "e só o estribo 07.2026?" — a pergunta escolheu o projeto
        chosen = raw.get(key) or []
        named = any(words & signals.name_tokens(value) for value in chosen)
        if not chosen or (set(chosen) < set(values) and not named):
            raw[key] = values



def _data_answer(c, message, today, sources, settings, usage, options, notes: list[str]) -> dict:
    spec = INTENTS[c.intent]
    if spec.source == "reports_db":
        return _reports_answer(c, message, today, settings, usage, notes)
    raw = {
        **spec.preset,
        "clients": [c.client] if c.client else [],
        "employees": [c.employee] if c.employee else [],
        "projects": [c.project] if c.project else [],
        "month": c.month, "month_end": c.month_end, "relative_period": c.relative,
    }
    _inherit(raw, c, message)
    return _cross_answer(raw, message, today, sources, settings, usage, options,
                         explain=c.route == "simple_with_explanation", intent=c.intent, notes=notes)


_QUERY_KEYS = (
    "measures", "group_by", "clients", "projects", "project_match", "employees", "packages", "cost_centers", "statuses",
    "billing_type", "month", "month_end", "relative_period", "top_n", "sort_by", "sort_order",
    "threshold_measure", "threshold_op", "threshold_value",
)
_FILTER_KEYS = ("clients", "projects", "project_match", "employees", "packages", "billing_type")


def _compare_periods_answer(plan, message, options, today, sources, settings, usage) -> dict | None:
    months = options["months"]
    a_start, b_start = plan.get("period_a_month"), plan.get("period_b_month")
    if a_start not in months or b_start not in months:
        logger.warning("Plano de compare_periods rejeitado (mês): %s", plan)
        return None
    a_end = plan.get("period_a_month_end") if plan.get("period_a_month_end") in months else None
    b_end = plan.get("period_b_month_end") if plan.get("period_b_month_end") in months else None
    base, family_notes = _with_project_family({key: plan.get(key) for key in _FILTER_KEYS}, message, options)
    base["measures"] = [plan.get("measure")]
    base["group_by"] = [plan["group_by"]] if plan.get("group_by") else []
    max_months = settings.analytics_chat_max_months
    try:
        spec_a, _ = crossquery.build_spec({**base, "month": a_start, "month_end": a_end}, options, today, max_months)
        spec_b, notes = crossquery.build_spec({**base, "month": b_start, "month_end": b_end}, options, today, max_months)
    except crossquery.InvalidQueryError:
        logger.warning("Plano de compare_periods rejeitado (medida): %s", plan)
        return None
    if spec_a.period == spec_b.period:  # "julho x julho" — variação sempre zero
        logger.warning("Plano de compare_periods rejeitado (mesmo período): %s", plan)
        return None
    if spec_a.period.start > spec_b.period.start:  # o planner inverteu a ordem
        spec_a, spec_b = spec_b, spec_a
    result = analysis.compare_periods(spec_a, spec_b, sources, settings.analytics_chat_max_rows)
    try:
        text = claude_client.finalize_analysis(usage, message, result["summary"])
    except Exception as e:
        logger.warning("Finalizer do Claude indisponível: %s", e)
        text = None
    reply, explained = _grounded_text(text, analysis.fallback_text(result), result["summary"])
    notes = family_notes + notes
    if notes:
        reply = f"{reply} {' '.join(notes)}"
    table = analysis.table(result)
    return {
        "intent": None,
        "analysis": "compare_periods",
        "reply": reply,
        "visualizations": analysis.visualizations(result)[:MAX_VISUALIZATIONS],
        "tables": [table] if table else [],
        "source": SOURCE_BY_DATASET[spec_b.dataset],
        "period": spec_b.period,
        "period_compared": spec_a.period,
        "filters": _context_filters(spec_b),
        "spec": spec_b,
        "explained": explained,
    }


def _escalate_to_planner(c: router.Classification, message: str) -> router.Classification:
    """Pergunta de dados que o atalho simples não cobre → planner:
    - sem intent (o Jev/Claude viu que é sobre dados, mas nenhum atalho serve:
      "em quais projetos o Lucca trabalhou", "quantos dias o Luciano apontou");
    - com sinais de cruzamento que o atalho perderia (`signals.needs_planner`)."""
    if c.route not in ("simple_data", "simple_with_explanation"):
        return c
    spec = INTENTS.get(c.intent) if c.intent else None
    if spec is None or (spec.preset is not None and signals.needs_planner(message, spec.preset["group_by"])):
        c.route = "analysis"
    return c


def _analysis_answer(c, message, previous, options, today, sources, settings, usage, notes,
                     wants_explanation: bool = False, period_allowed: bool = True,
                     year_period: tuple[str, str | None] | None = None) -> dict | None:
    try:
        plan = claude_client.plan_analysis(usage, message, previous, options)
    except Exception as e:
        logger.warning("Planner do Claude indisponível: %s", e)
        return None
    if not isinstance(plan, dict):
        logger.warning("Plano rejeitado (formato): %r", plan)
        return None
    if plan.get("analysis") == "compare_periods":
        return _compare_periods_answer(plan, message, options, today, sources, settings, usage)
    if plan.get("analysis") != "query":
        logger.warning("Plano rejeitado (análise desconhecida): %s", plan)
        return None
    raw = {key: plan.get(key) for key in _QUERY_KEYS}
    _inherit(raw, c, message)  # o planner às vezes esquece o recorte da pergunta anterior
    if not period_allowed:  # pergunta sem período: o planner não inventa um
        raw["month"] = raw["month_end"] = raw["relative_period"] = None
    if year_period:
        raw["month"], raw["month_end"], raw["relative_period"] = year_period[0], year_period[1], None
    if not (raw.get("month") or raw.get("relative_period")) and (c.month or c.relative):
        # o planner às vezes esquece o período que o Jev/Claude já tinha
        # achado ("nos últimos 6 meses", "em 2026" → jan-set/2026)
        raw["month"], raw["month_end"], raw["relative_period"] = c.month, c.month_end, c.relative
    try:
        answer = _cross_answer(raw, message, today, sources, settings, usage, options,
                               explain=bool(plan.get("explain")) or wants_explanation, intent=None, notes=notes)
    except crossquery.InvalidQueryError:
        logger.warning("Plano de consulta rejeitado (sem medida válida): %s", plan)
        return None
    answer["analysis"] = "query"
    return answer


def handle(message: str, context: ChatContext | None, user: dict) -> dict:
    started = time.monotonic()
    settings = get_settings()
    today = date.today()
    usage = claude_client.ClaudeUsage()
    conversation_id = context.conversation_id if context and context.conversation_id else str(ULID())
    sources = DataSources(today, settings.analytics_chat_max_months)
    status = "failed"
    c = None
    answer: dict = {}
    try:
        options, _ = _options(today, sources, settings.analytics_chat_max_months)
        previous = _previous(context, options)
        c = router.classify(
            message, previous, options, settings.jev_min_confidence, usage, settings.jev_min_confidence_none,
        )
        # o classificador marcava pergunta completa como continuação — a
        # trava por texto só deixa passar o que tem cara de continuação
        c.follow_up = c.follow_up and signals.looks_like_follow_up(message)
        if previous and signals.obviously_follow_up(message):
            c.follow_up = True
        period_in_message = signals.mentions_period(message)
        if not c.follow_up and not period_in_message:
            # período só vem do texto (ou da pergunta anterior, se continuação):
            # o Claude copiava o período da anterior numa pergunta nova
            c.month = c.month_end = c.relative = None
        c = _apply_follow_up(c, previous, message)

        years = years_mentioned(message) or signals.year_phrases(message, today)
        window_years = {key[:4] for key in options["months"]}
        outside = [year for year in years if year not in window_years]
        c, year_notes = _apply_years(c, years, message, options)
        # ano citado vale no planner também (senão "no ano" era jan-set/2026 no
        # atalho e "últimos 12 meses" no planner)
        year_period = (c.month, c.month_end) if years and c.month and not mentions_month(message) else None
        wants_explanation = c.route == "simple_with_explanation"
        c = _escalate_to_planner(c, message)

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
            # a pergunta anterior só vai pro planner se esta CONTINUA aquela —
            # senão ele herdava filtro dela numa pergunta nova (medido: "status
            # de envio de agosto" saía filtrado pelo cliente da pergunta anterior)
            answer = _analysis_answer(
                c, message, previous if c.follow_up else None, options, today, sources, settings, usage,
                year_notes, wants_explanation, period_in_message or c.follow_up, year_period,
            ) or {"reply": NO_ANALYSIS_REPLY}
        else:
            answer = _data_answer(c, message, today, sources, settings, usage, options, year_notes)
        status = "success"
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        spec = answer.get("spec")
        record_event(
            actor_id=user["login"], actor_name=user.get("name", ""), action="analytics_chat_query",
            entity_type="analytics_chat", entity_id=conversation_id, source="analytics_chat",
            metadata={
                "message": message[:300],
                "status": status,
                "route": c.route if c else None,
                "intent": answer.get("intent"),
                "analysis": answer.get("analysis"),
                "filters": answer.get("filters"),
                "spec": spec.as_context() if spec else None,
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
    spec = answer.get("spec")
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
            "last_filters": answer.get("filters"),
            "last_spec": spec.as_context() if spec else None,
        },
    }
