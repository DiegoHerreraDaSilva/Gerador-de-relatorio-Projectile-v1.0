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
from .catalog import BILLING_TYPES, COST_CENTERS, DATASET_DIMENSIONS, DIMENSIONS, MEASURES, STATUSES, THRESHOLD_OPS
from .intents import INTENTS, ROUTES
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
        "project": _nullable_enum(options.get("projects", [])),
        "follow_up": {"type": "boolean"},
    }
    catalog = "\n".join(f"- {name}: {spec.criteria}" for name, spec in INTENTS.items())
    content = (
        f"Classifique a pergunta do gerente.\nMétricas disponíveis:\n{catalog}\n"
        "Rotas: simple_data (número/lista objetiva), simple_with_explanation (pede explicação), "
        "analysis (qualquer cruzamento: duas quebras ao mesmo tempo como 'por cliente e por mês', vários "
        "clientes/projetos/colaboradores, faturado x trabalhado por projeto, corte por valor como 'menos de 100 h', "
        "top N, comparar meses ou itens entre si), general (sobre o app, sem dados), out_of_scope (fora do tema, "
        "pedir para editar/apagar dados, executar SQL, ignorar permissões ou despejar registros brutos).\n"
        "Período: um mês só → month; intervalo de meses (\"de fevereiro a agosto\") → month = primeiro "
        "mês e month_end = último; \"mês passado\", \"últimos 3 meses\" etc. → relative_period.\n"
        "Pergunta sobre horas, pessoas, projetos, clientes, pacotes, dias com apontamento, médias, faturado, "
        "performance ou envio de relatórios é SEMPRE do escopo (nunca out_of_scope): se nenhuma métrica da "
        "lista serve sozinha, use route analysis e intent null.\n"
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


def _catalog_text() -> str:
    datasets = {}
    for name, measure in MEASURES.items():
        datasets.setdefault(measure.dataset, []).append(f"{name} ({measure.description})")
    lines = []
    for dataset, measures in datasets.items():
        dims = ", ".join(DATASET_DIMENSIONS[dataset])
        lines.append(f"- fonte {dataset}: medidas {'; '.join(measures)}. Quebras/filtros possíveis: {dims}.")
    dims = "; ".join(f"{name} = {dim.description}" for name, dim in DIMENSIONS.items())
    return "\n".join(lines) + f"\nDimensões: {dims}."


_QUERY_EXAMPLES = """Exemplos (pergunta → consulta):
- "horas de cada colaborador por projeto em agosto" → measures [hours], group_by [employee, project], month
- "horas por cliente mês a mês" → measures [hours], group_by [client, month]
- "faturado x trabalhado por projeto em agosto" → measures [worked_hours, billed_hours, perf_hours, performance_percent], group_by [project]
- "colaboradores com menos de 100 h em agosto" → measures [hours], group_by [employee], threshold hours lt 100
- "top 5 projetos da Mercedes" → measures [hours], group_by [project], clients [a Mercedes], top_n 5
- "Mercedes x Lauer em julho" → measures [hours], group_by [client], clients [as duas]
- "em quais projetos o Lucca trabalhou" → measures [hours], group_by [project], employees [Lucca]
- "quantas pessoas trabalharam em cada projeto" → measures [employees, hours], group_by [project]
- "% não faturável por colaborador" → measures [non_billable_percent, non_billable_hours], group_by [employee]
- "horas CAD x CAE por mês" → measures [hours], group_by [cost_center, month]
- "horas da Mercedes por colaborador, só faturáveis" → measures [hours], group_by [employee], clients [a Mercedes], billing_type billable
- "quantos dias cada colaborador apontou em agosto" → measures [active_days, hours], group_by [employee]
- "quais projetos não tiveram relatório enviado em agosto" → measures [project_months], group_by [project], statuses [none]
- "taxa de envio por cliente" → measures [send_rate_percent, sent, not_sent], group_by [client]
- "quem trabalhou mais em cada cliente" → measures [hours], group_by [client, employee]"""


def plan_analysis(usage: ClaudeUsage, message: str, previous: dict | None, options: dict) -> dict:
    """Plano da análise — só medidas, dimensões e valores da whitelist.
    Uma ferramenta por análise (`tool_choice: any`), cada uma só com os
    seus campos: com um formulário único misturando campos de análises
    diferentes, o Haiku se confundia (1 em 5 nas medições)."""
    months = list(options["months"])
    measures = list(MEASURES)
    dims = list(DIMENSIONS)
    filters = {
        "clients": _enum_array(options["clients"]),
        "projects": _enum_array(options.get("projects", [])),
        "employees": _enum_array(options["employees"]),
        "packages": _enum_array(options.get("packages", [])),
    }
    tools = [
        {
            "name": "query",
            "description": (
                "Consulta cruzada: 1 a 4 medidas da MESMA fonte, até 2 quebras (group_by), filtros com vários "
                "valores, top N, ordenação e corte por valor (threshold). Use pra rankings, cruzamentos, "
                "'quem/quais', comparar clientes/colaboradores/projetos ENTRE SI num período, listas com status. "
                "Filtro vazio = todos. Campos que não usar ficam null/lista vazia."
            ),
            "input_schema": _schema({
                "measures": {"type": "array", "items": {"type": "string", "enum": measures}, "minItems": 1, "maxItems": 4},
                "group_by": {"type": "array", "items": {"type": "string", "enum": dims}, "maxItems": 2},
                **filters,
                "cost_centers": {"type": "array", "items": {"type": "string", "enum": list(COST_CENTERS)}},
                "billing_type": _nullable_enum(list(BILLING_TYPES)),
                "statuses": {"type": "array", "items": {"type": "string", "enum": list(STATUSES)}},
                "month": _nullable_enum(months),
                "month_end": _nullable_enum(months),
                "relative_period": _nullable_enum(list(RELATIVE_PERIODS)),
                "top_n": {"anyOf": [{"type": "integer", "minimum": 1, "maximum": 100}, {"type": "null"}]},
                "sort_by": _nullable_enum(measures),
                "sort_order": _nullable_enum(["desc", "asc"]),
                "threshold_measure": _nullable_enum(measures),
                "threshold_op": _nullable_enum(list(THRESHOLD_OPS)),
                "threshold_value": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "explain": {"type": "boolean"},
            }),
        },
        {
            "name": "compare_periods",
            "description": (
                "UMA medida em DOIS PERÍODOS DIFERENTES (ex.: 'compare julho e agosto', 'o que cresceu de agosto "
                "pra setembro por projeto', 'a performance melhorou?'). period_a = o mais antigo, period_b = o "
                "mais recente (cada um um mês, ou intervalo com *_month_end). group_by opcional: UMA quebra. "
                "NÃO use pra comparar clientes/colaboradores entre si num período só — isso é query."
            ),
            "input_schema": _schema({
                "measure": {"type": "string", "enum": measures},
                "group_by": _nullable_enum(dims),
                **filters,
                "billing_type": _nullable_enum(list(BILLING_TYPES)),
                "period_a_month": {"type": "string", "enum": months},
                "period_a_month_end": _nullable_enum(months),
                "period_b_month": {"type": "string", "enum": months},
                "period_b_month_end": _nullable_enum(months),
            }),
        },
    ]
    content = (
        "Monte o plano da análise chamando a ferramenta certa.\n"
        f"Catálogo:\n{_catalog_text()}\n{_QUERY_EXAMPLES}\n"
        "Período: um mês → month; intervalo (\"de fevereiro a agosto\") → month + month_end; \"mês passado\", "
        "\"últimos 3 meses\" → relative_period; sem período citado → tudo null (o sistema usa os últimos 12 meses).\n"
        "Medida: sem medida citada (\"Mercedes x Lauer\", \"quem mais trabalhou\"), use hours. Faturado/"
        "performance só quando a pergunta fala de faturamento, faturado ou performance.\n"
        "explain = true só se a pergunta pede interpretação/explicação/opinião (\"o que isso significa\", \"por quê\").\n"
        "Se a mensagem continua a anterior (\"e em julho?\", \"e por projeto?\"), parta da consulta anterior "
        "(campo spec) e mude só o que a mensagem pede.\n"
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
        "no formato brasileiro (3.041,8 h). period_a é o período anterior e period_b o posterior. "
        "Variação de percentual (performance, % não faturável) é em pontos percentuais (p.p.). "
        "Não sugira outras consultas.",
    )


def general_answer(usage: ClaudeUsage, message: str) -> str:
    return _text_call(
        usage,
        "Pergunta geral, sem dados do banco. Se ela precisar de números, diga que o gerente pode perguntar "
        "diretamente (ex.: 'quantas horas por cliente em setembro?'), sem citar valores.\n"
        f"Pergunta: {message}",
    )
