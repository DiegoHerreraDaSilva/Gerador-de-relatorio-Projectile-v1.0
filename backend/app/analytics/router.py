"""Decide rota + intent + filtros. Jev primeiro (se houver TYPESAFE_API_KEY);
Claude quando ele está desligado, falhou, ou não teve confiança suficiente.
O resultado dos dois passa pela MESMA validação: nada que não esteja no
catálogo ou nas listas de opções sobrevive."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..integrations import jev
from . import claude_client
from .intents import INTENTS, ROUTES
from .periods import RELATIVE_PERIODS

logger = logging.getLogger(__name__)

_NONE = "none"

_ROUTE_CRITERIA = {
    "simple_data": "Objective question answered by one number or one list about hours or reports (quantos, quantas, qual o total, liste, por cliente/projeto)",
    "simple_with_explanation": "Question about hours or reports that asks to explain, interpret or comment the numbers (explique, por que, o que significa, comente)",
    "analysis": "Compares two months, or compares named clients/people with each other (compare, comparar, versus, x, cresceu, diminuiu, variação entre)",
    "general": "General question about the app or a concept that needs no data (como funciona, o que é, ajuda)",
    "out_of_scope": "Unrelated to hours/reports, or asks to edit/delete data, run SQL, ignore permissions, or dump all raw records",
}


@dataclass
class Classification:
    route: str
    intent: str | None
    month: str | None
    relative: str | None
    client: str | None
    employee: str | None
    follow_up: bool
    classifier: str  # "jev" | "claude" | "none"
    confidence: float | None = None
    jev_called: bool = False
    month_end: str | None = None


def _questions(options: dict) -> dict:
    """Perguntas sobre a MENSAGEM sozinha — sem a pergunta anterior, que
    enviesava o Jev (ele "herdava" a métrica anterior numa pergunta nova)."""
    questions = {
        "route": jev.choice("Which kind of request is this message?", _ROUTE_CRITERIA),
        "intent": jev.choice(
            "Which metric does the message ask about?",
            {**{name: spec.criteria for name, spec in INTENTS.items()}, _NONE: "None of these metrics"},
        ),
        # mês E período relativo numa pergunta só: separados, o Jev marcava
        # os dois ("últimos 3 meses" + junho) e um contradizia o outro
        "period": jev.choice(
            "Which period does the message ask about? A specific month (if it mentions a range of "
            "months, the FIRST month of the range) or a relative period.",
            {
                **options["months"],
                **{key: text for key, (text, _, _) in RELATIVE_PERIODS.items()},
                _NONE: "No period mentioned",
            },
        ),
        "month_end": jev.choice(
            "If the message mentions a range of months (e.g. 'de fevereiro a agosto'), "
            "which is the LAST month of the range?",
            {**options["months"], _NONE: "No range of months mentioned"},
        ),
    }
    for name, values in (("client", options["clients"]), ("employee", options["employees"])):
        # lista grande demais pro Jev → pergunta sem esse filtro;
        # se a pessoa citar um, a confiança cai e o Claude assume.
        if 1 <= len(values) < jev.MAX_CHOICE_OPTIONS:
            label = "client/customer" if name == "client" else "employee/person"
            questions[name] = jev.choice(
                f"Which {label} does the message restrict the question to, if any?",
                {**{value: value for value in values}, _NONE: f"No specific {label}"},
            )
    return questions


_FOLLOW_UP_QUESTION = {
    "follow_up": jev.noul(
        "Is the message an incomplete continuation of the previous question that only makes sense "
        "with it (e.g. 'e em agosto?', 'e por cliente?', 'e só da Mercedes?')? "
        "A complete new question is NOT a continuation."
    )
}


def _ask_jev(message: str, previous: dict | None, options: dict) -> dict:
    """Uma chamada pra mensagem; se há pergunta anterior, outra — em paralelo
    — só pro "é continuação?", que é a única pergunta que precisa dela."""
    state = json.dumps({"today": options["today"], "message": message}, ensure_ascii=False)
    if previous is None:
        return jev.ask(state, _questions(options))
    follow_state = json.dumps({"previous_question": previous, "message": message}, ensure_ascii=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        main = pool.submit(jev.ask, state, _questions(options))
        follow = pool.submit(jev.ask, follow_state, _FOLLOW_UP_QUESTION)
        return {**main.result(), **follow.result()}


def _weakest(answers: dict, min_confidence: float, min_confidence_none: float) -> tuple[str, float] | None:
    """A resposta que não atinge o limiar, se houver. Escolha de verdade
    (rota, intent, mês, cliente...) precisa de `min_confidence`; "nenhum"
    precisa só de `min_confidence_none` — o Jev é menos seguro quando nada
    se aplica, e um "nenhum" errado é bem mais raro que um valor errado."""
    for name, answer in answers.items():
        chose_nothing = name != "route" and answer.choice in (_NONE, "no")
        threshold = min_confidence_none if chose_nothing else min_confidence
        if answer.confidence < threshold:
            return name, answer.confidence
    return None


def _from_jev(
    message: str, previous: dict | None, options: dict, min_confidence: float, min_confidence_none: float,
) -> Classification | None:
    try:
        answers = _ask_jev(message, previous, options)
    except jev.ClassifierUnavailableError as e:
        logger.info("Jev indisponível, usando Claude: %s", e)
        return None
    if "route" not in answers or "intent" not in answers:
        return None
    weak = _weakest(answers, min_confidence, min_confidence_none)
    if weak:
        logger.info("Jev sem confiança suficiente em %s (%.2f), usando Claude", *weak)
        return None
    lowest = min(answer.confidence for answer in answers.values())

    def pick(name: str) -> str | None:
        answer = answers.get(name)
        return None if answer is None or answer.choice == _NONE else answer.choice

    period = pick("period")
    relative = period if period in RELATIVE_PERIODS else None
    month = None if relative else period
    return Classification(
        route=answers["route"].choice,
        intent=pick("intent"),
        month=month,
        relative=relative,
        client=pick("client"),
        employee=pick("employee"),
        follow_up=pick("follow_up") == "yes",
        classifier="jev",
        month_end=pick("month_end") if month else None,
        confidence=round(lowest, 3),
    )


def _from_claude(usage, message: str, previous: dict | None, options: dict) -> Classification | None:
    try:
        payload = claude_client.interpret(usage, message, previous, options)
    except Exception as e:  # ChatConfigError/ChatUpstreamError — sem classificador disponível
        logger.warning("Claude indisponível pra interpretar a pergunta: %s", e)
        return None
    return Classification(
        route=payload.get("route"),
        intent=payload.get("intent"),
        month=payload.get("month"),
        relative=payload.get("relative_period"),
        client=payload.get("client"),
        employee=payload.get("employee"),
        follow_up=bool(payload.get("follow_up")),
        classifier="claude",
        month_end=payload.get("month_end"),
    )


def _validated(c: Classification, options: dict) -> Classification:
    """Descarta o que não existe — nunca executa com valor inventado."""
    if c.route not in ROUTES:
        c.route = "out_of_scope"
    if c.intent not in INTENTS:
        c.intent = None
    if c.month not in options["months"]:
        c.month = None
    if c.month is None or c.month_end not in options["months"] or c.month_end == c.month:
        c.month_end = None
    if c.relative not in RELATIVE_PERIODS:
        c.relative = None
    if c.client not in options["clients"]:
        c.client = None
    if c.employee not in options["employees"]:
        c.employee = None
    return c


def classify(
    message: str, previous: dict | None, options: dict, min_confidence: float, usage, min_confidence_none: float = 0.40,
) -> Classification:
    jev_called = jev.is_enabled()
    result = _from_jev(message, previous, options, min_confidence, min_confidence_none)
    if result is None:
        result = _from_claude(usage, message, previous, options)
    if result is None:
        result = Classification("unclassified", None, None, None, None, None, False, "none")
    else:
        result = _validated(result, options)
    result.jev_called = jev_called
    return result
