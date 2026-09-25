"""Sinais determinísticos de que a pergunta pede mais do que o atalho
simples que o Jev escolheu — aí ela vai pro planner do Claude, que monta a
consulta cruzada inteira.

Medido na calibração de 2026-09-24 (perguntas reais): o Jev escolhia com
confiança alta o atalho mais parecido e perdia a quebra ou o filtro extra —
"pessoas EM CADA CLIENTE" virava só a contagem de pessoas; "não faturável
POR COLABORADOR" virava o total; "SÓ FATURÁVEIS" sumia. Não dá pra pedir
isso ao Jev (ele só escolhe entre opções), então a checagem é por texto."""
from __future__ import annotations

import re

from .periods import _plain, mentions_month, years_mentioned

# palavra depois de "por"/"cada" → dimensão
_DIMENSION_WORDS = {
    "cliente": "client", "clientes": "client",
    "projeto": "project", "projetos": "project",
    "colaborador": "employee", "colaboradores": "employee", "pessoa": "employee", "pessoas": "employee",
    "funcionario": "employee", "funcionarios": "employee", "engenheiro": "employee", "engenheiros": "employee",
    "pacote": "package", "pacotes": "package", "atividade": "package", "atividades": "package",
    "mes": "month", "meses": "month",
    "centro": "cost_center", "cad": "cost_center", "cae": "cost_center",
    "status": "status",
}
_BREAKDOWN = re.compile(r"\b(?:por|cada)\s+(?:cada\s+)?([a-z]+)")
_MONTHLY = re.compile(r"\bmes a mes\b|\bmensal(?:mente)?\b")
_THRESHOLD = re.compile(r"\b(?:menos|mais|acima|abaixo|pelo menos|no minimo|no maximo|superior|inferior)\s+(?:a\s+|de\s+|que\s+)?\d")
_TOP = re.compile(r"\btop\s*\d|\b(?:os|as)\s+\d+\s+(?:maiores|menores|primeir)")
_VERSUS = re.compile(r"\s(?:x|vs\.?|versus)\s")
_BILLING_FILTER = re.compile(r"\b(?:so|somente|apenas)\s+(?:as\s+|os\s+)?(?:horas\s+)?(?:nao\s+)?faturave")


def asked_dimensions(message: str) -> set[str]:
    text = _plain(message)
    dims = {_DIMENSION_WORDS[w] for w in _BREAKDOWN.findall(text) if w in _DIMENSION_WORDS}
    if _MONTHLY.search(text):
        dims.add("month")
    return dims


def needs_planner(message: str, preset_group_by: list[str]) -> bool:
    """True se a mensagem pede quebra, corte, top N, comparação ou filtro que
    o atalho (`preset_group_by`) não cobre."""
    text = _plain(message)
    if asked_dimensions(message) - set(preset_group_by):
        return True
    return any(pattern.search(text) for pattern in (_THRESHOLD, _TOP, _VERSUS, _BILLING_FILTER))


# "e em julho?", "e só da Mercedes?", "o que isso significa?", "agora por cliente"
_CONTINUATION_START = re.compile(r"^(?:e|agora|mesma coisa|o mesmo|idem|entao|so|somente|apenas)\b")
_REFERENCE = re.compile(
    r"\b(?:isso|isto|esse|essa|esses|essas|este|esta|disso|nisso|desse|dessa|nesse|nessa|deles|delas|"
    r"mesmo periodo|mesma coisa|mesmos|anterior|acima)\b"
)


def looks_like_follow_up(message: str) -> bool:
    """Trava pro "é continuação?" do Jev/Claude: medido, os dois marcavam
    pergunta completa como continuação ("status de envio de agosto" logo
    depois de uma pergunta sobre a Lauer) e ela herdava filtro e período da
    anterior. Continuação de verdade começa com "e ...", aponta pra anterior
    ("isso", "esse", "mesmo período") ou é curtíssima ("compara com julho")."""
    text = _plain(message).strip(" ?!.")
    return bool(_CONTINUATION_START.search(text) or _REFERENCE.search(text) or len(text.split()) <= 3)


_RELATIVE_PERIOD = re.compile(
    r"\b(?:mes passado|mes anterior|mes atual|ultimo mes|(?:n?est|n?ess)e mes|ultim[oa]s?\s+\w+|trimestre|"
    r"semestre|ano|anos|anual|hoje|atualmente|periodo|semana)\b"
)
_THIS_YEAR = re.compile(r"\b(?:(?:n?est|n?ess)e ano|no ano|ano atual|ano corrente)\b")
_LAST_YEAR = re.compile(r"\b(?:ano passado|ano anterior|ultimo ano fechado)\b")


def mentions_period(message: str) -> bool:
    """A mensagem fala de QUANDO? Medido: o Claude, ao classificar, copiava o
    período da pergunta anterior numa pergunta nova sem período nenhum. Se
    o texto não cita período (e não é continuação), vale o padrão com aviso."""
    text = _plain(message)
    return bool(mentions_month(message) or years_mentioned(message) or _RELATIVE_PERIOD.search(text))


def year_phrases(message: str, today) -> list[str]:
    """"no ano"/"este ano" → ano corrente; "ano passado" → o anterior."""
    text = _plain(message)
    if _LAST_YEAR.search(text):
        return [str(today.year - 1)]
    if _THIS_YEAR.search(text):
        return [str(today.year)]
    return []
