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


def is_versus(message: str) -> bool:
    """"A x B", "A vs B", "A versus B" — comparação entre itens."""
    return bool(_VERSUS.search(_plain(message)))


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


_SHORT_AND = re.compile(r"^(?:e|e se|e no|e na|e em|e o|e a|e pra|e para|agora)\b")


def obviously_follow_up(message: str) -> bool:
    """"e durante o ano?", "e em julho?", "e por colaborador?": curta (até 5
    palavras) e começando com "e"/"agora" é continuação — não depende do
    classificador, que às vezes dizia que não e a pergunta perdia o recorte
    anterior. Pergunta longa que começa com "e" ("e quantas horas o Lucca
    apontou em agosto?") continua passando pelo classificador."""
    text = _plain(message).strip(" ?!.")
    return bool(_SHORT_AND.search(text)) and len(text.split()) <= 5


_RELATIVE_PERIOD = re.compile(
    r"\b(?:mes passado|mes anterior|mes atual|ultimo mes|(?:n?est|n?ess)e mes|ultim[oa]s?\s+\w+|trimestre|"
    r"semestre|ano|anos|anual|hoje|atualmente|periodo|semana)\b"
)
_THIS_YEAR = re.compile(
    r"\b(?:(?:n?est|n?ess)e ano|no ano|ano atual|ano corrente|durante o ano|ao longo do ano"
    r"|(?:n?o )?ano (?:todo|inteiro))\b"
)
_LAST_YEAR = re.compile(r"\b(?:ano passado|ano anterior|ultimo ano fechado)\b")


def mentions_period(message: str) -> bool:
    """A mensagem fala de QUANDO? Medido: o Claude, ao classificar, copiava o
    período da pergunta anterior numa pergunta nova sem período nenhum. Se
    o texto não cita período (e não é continuação), vale o padrão com aviso."""
    text = _plain(message)
    return bool(mentions_month(message) or years_mentioned(message) or _RELATIVE_PERIOD.search(text))


# palavras que aparecem em nome de projeto mas não distinguem um do outro
_NAME_STOPWORDS = {"a", "o", "as", "os", "de", "do", "da", "dos", "das", "e", "em", "para", "projeto", "projetos", "project"}
_NAME_TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")


def name_tokens(text: str) -> set[str]:
    """Palavras que distinguem um nome de projeto/cliente (sem acento, sem "de"/"projeto")."""
    return set(_NAME_TOKEN.findall(_plain(text))) - _NAME_STOPWORDS


def name_sequence(text: str) -> list[str]:
    """Palavras do nome na ordem, sem acento (com "de"/"projeto")."""
    return _NAME_TOKEN.findall(_plain(text))


def matches_phrase(phrase: str, project: str) -> bool:
    """O projeto tem no nome todas as palavras que distinguem a frase
    ("Estribo" casa com "Legislation Package - Estribo 08.2026")."""
    wanted = name_tokens(phrase)
    return bool(wanted) and wanted <= name_tokens(project)


def family_phrases(message: str, selected: list[str], all_projects: list[str]) -> tuple[list[str], list[str]]:
    """O Projectile às vezes abre UM projeto por mês pro mesmo trabalho
    ("Legislation Package - Estribo", "... Estribo 07.2026", "... 08.2026") e
    quem monta a consulta (Jev ou planner) escolhe UM nome da lista. Pra cada
    projeto escolhido, as palavras da pergunta que estão no nome dele viram
    uma frase ("Estribo", "Legislation Package"); se ela casa com mais de um
    projeto, a consulta passa a filtrar pela frase (`project_match`), sem teto
    de quantidade — "Legislation Package" são 38 projetos. Quem escreve
    "estribo 08.2026" continua com um projeto só.
    Devolve (frases, projetos escolhidos que continuam valendo sozinhos)."""
    words = name_tokens(message)
    phrases: list[str] = []
    kept: list[str] = []
    for project in selected:
        shared = words & name_tokens(project)
        family = [p for p in all_projects if shared and shared <= name_tokens(p)]
        if len(family) <= 1:
            kept.append(project)
            continue
        # a frase como está no nome do projeto ("Legislation Package"), na ordem
        seen: list[str] = []
        for word in re.findall(r"[^\W_]+(?:\.[^\W_]+)*", project):
            if _plain(word) in shared and _plain(word) not in [_plain(w) for w in seen]:
                seen.append(word)
        phrase = " ".join(seen)
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases, kept


# palavras do próprio vocabulário do chat — uma frase feita só delas não é
# nome de projeto ("horas por cliente", "não faturáveis", "CAD")
_CHAT_WORDS = {
    "hora", "horas", "h", "mes", "meses", "ano", "anos", "por", "cada", "cliente", "clientes",
    "colaborador", "colaboradores", "pessoa", "pessoas", "pacote", "pacotes", "total", "totais",
    "faturavel", "faturaveis", "faturado", "faturadas", "nao", "sim", "cad", "cae", "centro", "custo",
    "quantas", "quantos", "qual", "quais", "teve", "tem", "foram", "apontadas", "apontou", "trabalhadas",
    "no", "na", "nos", "nas", "com", "sem", "que", "ultimo", "ultimos", "ultima", "ultimas", "time", "equipe",
    "performance", "status", "envio", "enviado", "enviados", "relatorio", "relatorios", "dias", "media",
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
    "novembro", "dezembro", "durante", "ao", "longo", "todo", "inteiro", "atual", "passado",
}
_PROJECT_WORD = re.compile(r"^(?:projeto|projetos|project|projects)$")


def detect_project_phrase(message: str, all_projects: list[str], other_names: list[str]) -> str | None:
    """Pergunta sem nenhum projeto escolhido pelo Jev/planner, mas com um
    trecho que está no nome de projetos ("horas legislation package"):
    esse trecho vira o filtro. Pra não confundir com outra coisa:
    - UMA palavra só vale depois de "projeto" ("projeto estribo") — "horas
      CAD" é centro de custo, não os 8 projetos com CAD no nome;
    - duas ou mais palavras seguidas precisam aparecer SEGUIDAS no nome;
    - trecho só com palavras do chat ("horas por cliente") não conta;
    - trecho que é nome de cliente/colaborador não conta (é filtro deles).
    Vale o trecho mais longo."""
    words = re.findall(r"[^\W_]+(?:\.[^\W_]+)*", message)
    plain = [_plain(w) for w in words]
    sequences = [name_sequence(p) for p in all_projects]
    other_tokens = [name_tokens(n) for n in other_names]
    for size in range(min(6, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            window = plain[start:start + size]
            distinct = set(window) - _NAME_STOPWORDS - _CHAT_WORDS
            if not distinct or window[0] in _NAME_STOPWORDS or window[-1] in _NAME_STOPWORDS:
                continue
            if size == 1 and not (start > 0 and _PROJECT_WORD.match(plain[start - 1])):
                continue
            if any(distinct <= tokens for tokens in other_tokens):
                continue
            for project, seq in zip(all_projects, sequences):
                at = _run_index(seq, window)
                if at is not None:
                    # a grafia do nome do projeto ("Legislation Package"), não a digitada
                    original = re.findall(r"[^\W_]+(?:\.[^\W_]+)*", project)
                    return " ".join(original[at:at + size]) if len(original) == len(seq) else " ".join(words[start:start + size])
    return None


def _run_index(sequence: list[str], window: list[str]) -> int | None:
    n = len(window)
    return next((i for i in range(len(sequence) - n + 1) if sequence[i:i + n] == window), None)


_ONLY_BILLING = re.compile(r"\b(?:so|somente|apenas)(?: as)?(?: horas)? (nao )?faturav(?:el|eis)\b")


def only_billing_type(message: str) -> str | None:
    """"só faturáveis" → billable, "só não faturáveis" → non_billable (o
    planner às vezes esquecia). Só com "só/somente/apenas": "quanto foi não
    faturável" é MEDIDA, e filtrar por ela daria 100% em tudo."""
    found = {("non_billable" if m else "billable") for m in _ONLY_BILLING.findall(_plain(message))}
    return found.pop() if len(found) == 1 else None


_COST_CENTER_WORD = re.compile(r"\b(cad|cae)\b")


def single_cost_center(message: str) -> str | None:
    """"horas CAD por mês" → "CAD" (o planner às vezes esquecia o filtro e
    respondia CAD+CAE). Os dois citados ("CAD x CAE") = comparação, não filtro."""
    found = set(_COST_CENTER_WORD.findall(_plain(message)))
    return found.pop().upper() if len(found) == 1 else None


_EVERYONE = re.compile(r"\b(?:todos|todas|geral|time|equipe)\b")


def asks_everyone(message: str) -> bool:
    """"e no time todo?", "e no geral?" — a continuação pede pra TIRAR o
    recorte, então os filtros da pergunta anterior não são herdados."""
    return bool(_EVERYONE.search(_plain(message)))


def year_phrases(message: str, today) -> list[str]:
    """"no ano"/"este ano" → ano corrente; "ano passado" → o anterior."""
    text = _plain(message)
    if _LAST_YEAR.search(text):
        return [str(today.year - 1)]
    if _THIS_YEAR.search(text):
        return [str(today.year)]
    return []
