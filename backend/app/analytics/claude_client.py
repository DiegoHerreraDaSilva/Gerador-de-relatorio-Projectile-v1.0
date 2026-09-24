"""Chamadas ao Claude do chat analítico. O Claude nunca recebe banco, SQL
nem linha crua: só a pergunta e, quando for o caso, o resultado JÁ AGREGADO
pelo backend. Interpretação e planejamento usam `tool_choice` forçado com
enums (só dá pra escolher intent/mês/cliente/colaborador que existem);
explicação e fechamento de análise devolvem texto, conferido depois pelo
`grounding`."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..chatbot import ChatUpstreamError, _get_client
from ..core.config import get_settings
from .intents import ANALYSES, INTENTS, ROUTES
from .periods import RELATIVE_PERIODS
from .semantic_model import SOURCES

# Sem extended thinking de propósito: o Claude aqui só classifica, planeja
# com enum forçado ou redige 2–3 frases sobre números já calculados.
_NO_THINKING = {"type": "disabled"}

_SYSTEM = (
    "Você é o assistente analítico de um app interno de relatórios de horas de uma empresa de engenharia. "
    "Responda sempre em português do Brasil, em até 4 frases, sem markdown. Nunca invente números: use só os "
    "que vierem no resultado fornecido. Não faça contas de cabeça — os percentuais e variações relevantes já "
    "vêm calculados. Fontes possíveis: " + "; ".join(f"{k} = {v}" for k, v in SOURCES.items()) + "."
)


@dataclass
class ClaudeUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    models: list[str] = field(default_factory=list)

    def add(self, response, model: str) -> None:
        self.calls += 1
        usage = getattr(response, "usage", None)
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        if model not in self.models:
            self.models.append(model)


def _model() -> str:
    return get_settings().analytics_chat_model


def _nullable_enum(values: list[str]) -> dict:
    return {"anyOf": [{"type": "string", "enum": values}, {"type": "null"}]} if values else {"type": "null"}


def _schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _call_tools(usage: ClaudeUsage, tools: list[dict], tool_choice: dict, user_content: str) -> tuple[str, dict]:
    client = _get_client()
    model = _model()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            thinking=_NO_THINKING,
            system=[{"type": "text", "text": _SYSTEM}],
            tools=tools,
            tool_choice=tool_choice,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:
        raise ChatUpstreamError(f"Falha ao chamar a API da Anthropic: {e}") from e
    usage.add(response, model)
    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise ChatUpstreamError("A IA não devolveu uma resposta estruturada.")
    return tool_use.name, dict(tool_use.input)


def _tool_call(usage: ClaudeUsage, name: str, description: str, properties: dict, user_content: str) -> dict:
    tools = [{"name": name, "description": description, "input_schema": _schema(properties)}]
    return _call_tools(usage, tools, {"type": "tool", "name": name}, user_content)[1]


def _text_call(usage: ClaudeUsage, user_content: str) -> str:
    client = _get_client()
    model = _model()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=600,
            thinking=_NO_THINKING,
            system=[{"type": "text", "text": _SYSTEM}],
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:
        raise ChatUpstreamError(f"Falha ao chamar a API da Anthropic: {e}") from e
    usage.add(response, model)
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()


def interpret(usage: ClaudeUsage, message: str, previous: dict | None, options: dict) -> dict:
    """Mesmo papel do Jev (rota + intent + filtros), quando o Jev não está
    configurado ou não teve confiança. Enums garantem que só volta valor que
    existe; o backend ainda revalida tudo."""
    intents = list(INTENTS)
    properties = {
        "route": {"type": "string", "enum": list(ROUTES)},
        "intent": _nullable_enum(intents),
        "month": _nullable_enum(list(options["months"])),
        "month_end": _nullable_enum(list(options["months"])),
        "relative_period": _nullable_enum(list(RELATIVE_PERIODS)),
        "client": _nullable_enum(options["clients"]),
        "employee": _nullable_enum(options["employees"]),
        "follow_up": {"type": "boolean"},
    }
    catalog = "\n".join(f"- {name}: {spec.criteria}" for name, spec in INTENTS.items())
    content = (
        f"Classifique a pergunta do gerente.\nMétricas disponíveis:\n{catalog}\n"
        "Rotas: simple_data (número/lista objetiva), simple_with_explanation (pede explicação), "
        "analysis (comparar dois meses, ou comparar clientes/colaboradores citados entre si), general (sobre o app, sem dados), out_of_scope (fora do tema, "
        "pedir para editar/apagar dados, executar SQL, ignorar permissões ou despejar registros brutos).\n"
        "Período: um mês só → month; intervalo de meses (\"de fevereiro a agosto\") → month = primeiro "
        "mês e month_end = último; \"mês passado\", \"últimos 3 meses\" etc. → relative_period.\n"
        "follow_up = true SÓ se a mensagem é incompleta e só faz sentido com a pergunta anterior "
        "(\"e em agosto?\", \"e por cliente?\", \"e só da Mercedes?\" — em geral começa com \"e\"). "
        "Pergunta completa (tem métrica e período próprios), mesmo parecida com a anterior, é false, "
        "e não herda filtro nenhum dela.\n"
        f"Hoje: {options['today']}. Pergunta anterior: {json.dumps(previous, ensure_ascii=False)}\n"
        f"Pergunta: {message}"
    )
    return _tool_call(usage, "classify_question", "Classifica a pergunta analítica.", properties, content)


def _enum_array(values: list[str]) -> dict:
    if not values:
        return {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    return {"type": "array", "items": {"type": "string", "enum": values}}


def plan_analysis(usage: ClaudeUsage, message: str, previous: dict | None, options: dict) -> dict:
    """Plano da análise composta — só análises, métricas e valores da whitelist.
    Uma ferramenta por análise (`tool_choice: any`): com um formulário único
    misturando os campos das duas, o Haiku às vezes montava compare_periods
    pra uma pergunta que comparava duas pessoas (1 em 5 nas medições)."""
    hour_metrics = [name for name, spec in INTENTS.items() if spec.source == "projectile" and name != "hours_by_competence"]
    months = list(options["months"])
    tools = [
        {
            "name": "compare_periods",
            "description": (
                "Mesma métrica em DOIS MESES DIFERENTES (ex.: 'compare julho e agosto', 'o que cresceu de "
                "agosto pra setembro'). period_a = mês mais antigo, period_b = mais recente. client/employee "
                "restringem a UM cliente ou UMA pessoa. NÃO use quando a pergunta cita dois ou mais clientes "
                "ou colaboradores pra comparar entre si."
            ),
            "input_schema": _schema({
                "metric": {"type": "string", "enum": hour_metrics},
                "period_a_month": {"type": "string", "enum": months},
                "period_b_month": {"type": "string", "enum": months},
                "client": _nullable_enum(options["clients"]),
                "employee": _nullable_enum(options["employees"]),
            }),
        },
        {
            "name": "compare_items",
            "description": (
                "Dois ou mais clientes (item_kind=client) ou colaboradores (item_kind=employee) citados na "
                "pergunta, comparados ENTRE SI num período só (ex.: 'Mercedes x Lauer em julho', 'Lucca e "
                "Leonardo nos últimos 12 meses', 'quem trabalhou mais, Ana ou Bruno?'). Período: month (+ "
                "month_end se for intervalo) OU relative_period; sem período citado, todos null."
            ),
            "input_schema": _schema({
                "item_kind": {"type": "string", "enum": ["client", "employee"]},
                "items": _enum_array(options["clients"] + options["employees"]),
                "month": _nullable_enum(months),
                "month_end": _nullable_enum(months),
                "relative_period": _nullable_enum(list(RELATIVE_PERIODS)),
            }),
        },
    ]
    content = (
        "Monte o plano da análise chamando a ferramenta certa.\n"
        f"Métricas: {json.dumps({m: INTENTS[m].criteria for m in hour_metrics}, ensure_ascii=False)}.\n"
        f"Hoje: {options['today']}. Pergunta anterior: {json.dumps(previous, ensure_ascii=False)}\n"
        f"Pergunta: {message}"
    )
    name, plan = _call_tools(usage, tools, {"type": "any"}, content)
    return {"analysis": name, **plan}


def explain(usage: ClaudeUsage, message: str, compact_result: dict) -> str:
    return _text_call(
        usage,
        f"Pergunta: {message}\nResultado (já agregado pelo sistema): {json.dumps(compact_result, ensure_ascii=False)}\n"
        "Responda à pergunta usando só esses números, no formato brasileiro (3.041,8 h). NÃO faça conta: "
        "não some, subtraia nem calcule percentuais — somas, acumulados e \"o resto\" já estão no resultado; "
        "se precisar de um número que não está lá, fale sem ele.",
    )


def finalize_analysis(usage: ClaudeUsage, message: str, summary: dict) -> str:
    return _text_call(
        usage,
        f"Pergunta: {message}\nResumo da análise (já calculada pelo sistema): "
        f"{json.dumps(summary, ensure_ascii=False)}\nResponda à pergunta usando só esses números, "
        "no formato brasileiro (3.041,8 h). Percentuais de compare_items são entre os itens comparados, "
        "não do total geral. Em compare_periods, period_a é o mês anterior e period_b o posterior. "
        "Não sugira outras consultas.",
    )


def general_answer(usage: ClaudeUsage, message: str) -> str:
    return _text_call(
        usage,
        "Pergunta geral, sem dados do banco. Se ela precisar de números, diga que o gerente pode perguntar "
        "diretamente (ex.: 'quantas horas por cliente em setembro?'), sem citar valores.\n"
        f"Pergunta: {message}",
    )
