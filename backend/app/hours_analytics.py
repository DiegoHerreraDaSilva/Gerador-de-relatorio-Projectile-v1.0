"""Cálculo das métricas do Dashboard de horas pessoal.

Funções puras (sem banco, sem I/O) para dar teste unitário ao pedaço mais
delicado do dashboard: a linha de base contra a qual as horas apontadas são
comparadas. Errar essa base é pior que não mostrar a métrica — um percentual
de utilização calculado contra uma jornada que não é a do funcionário mente
com aparência de precisão.

Por que existe uma cascata em vez de "8 horas": medido neste banco que
`temployeecontract` tem jornada real para 564 dos 578 contratos, mas NÃO tem
registro para o usuário de referência (estagiário, `pStatus='Trainee'`), cuja
jornada real observada é 6,0 h/dia em 21 de 21 dias úteis. Aplicar as 8 h de
`tcalendar.pWorkingHoursDay` nesse caso mostraria 75% de utilização para
alguém que cumpre a jornada integralmente.

Regra central do módulo: só `source == "contract"` autoriza percentual na
tela (`allows_percentage`). Jornada estimada serve pra desenhar referência
tracejada e comparar com o próprio histórico — nunca pra afirmar "você
cumpriu X% da sua jornada", porque a jornada não é conhecida.
"""
from __future__ import annotations

import datetime
import statistics
from typing import Iterable, Literal, Sequence

from .generator import _national_holidays, business_days_between

JourneySource = Literal["contract", "empirical", "calendar", "none"]

# Fonte usada quando nem contrato nem histórico existem. Vem de
# `tcalendar.pWorkingHoursDay` (medido: 8.0, calendário único "Kalender Sao
# Paulo"), mas fica como parâmetro para o chamador poder passar o valor lido
# do banco em vez de confiar nesta constante.
DEFAULT_CALENDAR_DAILY_HOURS = 8.0

# Janela e piso do baseline empírico. A janela curta (120 dias) é preferida
# porque reflete a jornada atual; se não houver dias suficientes nela, amplia
# pra um ano com um piso menor. Abaixo do piso final a mediana é instável
# demais (ex: quem voltou de férias com 3 dias no período) e cairia num falso
# "sua jornada é 2h/dia" — nesse caso a fonte vira "calendar"/"none".
EMPIRICAL_WINDOW_DAYS = 120
EMPIRICAL_MIN_DAYS = 20
EMPIRICAL_WIDE_WINDOW_DAYS = 365
EMPIRICAL_WIDE_MIN_DAYS = 10

# Divergência a partir da qual a tela mostra nota comparando contrato e
# padrão medido. Não troca a referência (contrato declarado ganha), só avisa.
DIVERGENCE_NOTE_THRESHOLD_HOURS = 1.0

_LABELS = {
    "contract": "Contrato",
    "empirical": "Estimado do seu histórico",
    "calendar": "Padrão da empresa (calendário)",
    "none": "Sem referência de jornada",
}


# --------------------------------------------------------------------------
# jornada / referência
# --------------------------------------------------------------------------
def contract_weekday_hours(
    day: datetime.date, contracts: Iterable[dict]
) -> dict[int, float] | None:
    """Jornada semanal (`{0..6 -> horas}`, 0=segunda) do contrato vigente em
    `day`, ou `None` se nenhum contrato cobre a data ou se o que cobre tem
    jornada toda zerada.

    `contracts` tem o formato de `projectile_db.fetch_employee_contracts`.
    `end=None` significa contrato em aberto (medido: é o caso do contrato
    corrente de um funcionário ativo). Percorre em ordem e devolve o último
    que cobre a data — os contratos vêm ordenados por `pContractBegin`, então
    o último a casar é o mais recente, o que importa quando vigências se
    sobrepõem por erro de cadastro.

    O descarte da jornada toda zerada é deliberado: a linha existe mas todos
    os `pPlannedTime*` vieram NULL (14 dos 578 contratos medidos). Tratar isso
    como "contrato de 0 h/dia" faria a tela afirmar que qualquer hora apontada
    é 100% de excedente."""
    found: dict[int, float] | None = None
    for contract in contracts:
        begin, end = contract.get("begin"), contract.get("end")
        if begin is not None and day < begin:
            continue
        if end is not None and day > end:
            continue
        weekday_hours = contract.get("weekday_hours") or {}
        if sum(weekday_hours.values()) <= 0:
            continue
        found = weekday_hours
    return found


def empirical_daily_baseline(
    daily_totals: dict[datetime.date, float],
    today: datetime.date,
) -> tuple[float, int, int] | None:
    """Jornada praticada pelo próprio funcionário:
    `(horas_por_dia, dias_na_amostra, tamanho_da_janela)` ou `None`.

    Mediana e não média porque este banco tem lançamento de 0,17 h: dias
    parciais puxam a média pra baixo e criariam crédito falso de ~0,16 h/dia
    (~40 h/ano no caso medido). A mediana devolve o dia típico.

    Só considera dias ÚTEIS com apontamento e anteriores a hoje (o dia em
    curso está incompleto por definição). Tenta a janela curta com piso alto;
    se não alcançar, amplia a janela e baixa o piso. Arredonda a 0,25 h — a
    jornada real é um número redondo, e mediana crua tipo 5,97 dá falsa
    precisão."""
    for window, minimum in (
        (EMPIRICAL_WINDOW_DAYS, EMPIRICAL_MIN_DAYS),
        (EMPIRICAL_WIDE_WINDOW_DAYS, EMPIRICAL_WIDE_MIN_DAYS),
    ):
        start = today - datetime.timedelta(days=window)
        sample = [
            hours
            for day, hours in daily_totals.items()
            if start <= day < today and day.weekday() < 5 and hours > 0
        ]
        if len(sample) >= minimum:
            median = statistics.median(sample)
            return round(median * 4) / 4, len(sample), window
    return None


def resolve_reference(
    contracts: Sequence[dict],
    daily_totals: dict[datetime.date, float],
    today: datetime.date,
    reference_day: datetime.date | None = None,
    calendar_daily: float | None = DEFAULT_CALENDAR_DAILY_HOURS,
) -> dict:
    """Resolve a referência de jornada pela cascata contrato → histórico →
    calendário → nenhuma, no formato do bloco `reference` de `/my-hours`.

    `reference_day` é a data usada pra escolher a vigência de contrato
    (default: hoje). Devolve sempre as 7 posições de `hours_per_weekday`
    (0=segunda) pra o frontend nunca precisar chutar dia da semana.

    `allows_percentage` é a única chave que autoriza percentual na tela: só
    contrato declarado permite afirmar aderência. Com jornada estimada a tela
    desenha a referência e compara com o próprio histórico, mas não afirma
    percentual de cumprimento."""
    day = reference_day or today
    contract_hours = contract_weekday_hours(day, contracts)
    empirical = empirical_daily_baseline(daily_totals, today)

    if contract_hours:
        per_weekday = [round(float(contract_hours.get(i, 0.0)), 2) for i in range(7)]
        worked = [h for h in per_weekday if h > 0]
        per_day = round(sum(worked) / len(worked), 2) if worked else 0.0
        note = None
        if empirical and abs(empirical[0] - per_day) > DIVERGENCE_NOTE_THRESHOLD_HOURS:
            note = f"contrato {_hours_pt(per_day)} · seu padrão medido ~{_hours_pt(empirical[0])}"
        return {
            "source": "contract",
            "hours_per_weekday": per_weekday,
            "hours_per_day": per_day,
            "allows_percentage": True,
            "sample_days": None,
            "window_days": None,
            "label": _LABELS["contract"],
            "divergence_note": note,
        }

    if empirical:
        per_day, sample_days, window = empirical
        return {
            "source": "empirical",
            "hours_per_weekday": [per_day] * 5 + [0.0, 0.0],
            "hours_per_day": per_day,
            "allows_percentage": False,
            "sample_days": sample_days,
            "window_days": window,
            "label": _LABELS["empirical"],
            "divergence_note": None,
        }

    if calendar_daily and calendar_daily > 0:
        return {
            "source": "calendar",
            "hours_per_weekday": [round(calendar_daily, 2)] * 5 + [0.0, 0.0],
            "hours_per_day": round(calendar_daily, 2),
            "allows_percentage": False,
            "sample_days": None,
            "window_days": None,
            "label": _LABELS["calendar"],
            "divergence_note": None,
        }

    return {
        "source": "none",
        "hours_per_weekday": None,
        "hours_per_day": None,
        "allows_percentage": False,
        "sample_days": None,
        "window_days": None,
        "label": _LABELS["none"],
        "divergence_note": None,
    }


def _hours_pt(value: float) -> str:
    """"8.0" -> "8 h"; "6.5" -> "6,5 h" — só pra compor a nota de divergência
    no idioma da interface."""
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} h"


def expected_hours_for_days(days: Iterable[datetime.date], reference: dict) -> float | None:
    """Soma das horas esperadas nos dias informados, ou `None` quando não há
    referência. Feriado nacional não chega aqui: quem chama passa a lista de
    dias úteis de `generator.business_days_between`, que já os exclui."""
    per_weekday = reference.get("hours_per_weekday")
    if not per_weekday:
        return None
    return round(sum(float(per_weekday[d.weekday()]) for d in days), 2)


# --------------------------------------------------------------------------
# séries e estatísticas
# --------------------------------------------------------------------------
def daily_stats(
    daily_totals: dict[datetime.date, float], today: datetime.date, window_days: int = 60
) -> dict:
    """Percentis das horas dos dias com apontamento na janela recente — usados
    pra projetar o fim do mês como FAIXA (p25–p75), não como número único.

    Uma projeção de ponto sugere precisão que não existe; a faixa comunica a
    variação real do dia a dia."""
    start = today - datetime.timedelta(days=window_days)
    sample = sorted(h for d, h in daily_totals.items() if start <= d < today and h > 0)
    if not sample:
        return {"p25": None, "median": None, "p75": None, "n": 0, "window_days": window_days}
    return {
        "p25": round(percentile(sample, 0.25), 2),
        "median": round(percentile(sample, 0.50), 2),
        "p75": round(percentile(sample, 0.75), 2),
        "n": len(sample),
        "window_days": window_days,
    }


def percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Percentil por interpolação linear numa lista JÁ ordenada. Escrito à mão
    em vez de `statistics.quantiles` porque aquele exige n>=2 e estoura com um
    único dia de dado, que é exatamente o estado do mês em curso no dia 1."""
    if not sorted_values:
        raise ValueError("lista vazia")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = fraction * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return float(sorted_values[low]) * (1 - weight) + float(sorted_values[high]) * weight


def monthly_series(
    daily_totals: dict[datetime.date, float], today: datetime.date, months: int = 13
) -> list[dict]:
    """Uma entrada por mês (os `months-1` fechados mais o corrente), sempre
    ignorando o período selecionado na tela.

    Ignorar o seletor é decisão de desenho: com "Mês atual" selecionado, uma
    tendência restrita ao período mostraria uma coluna só. E o mês corrente vem
    marcado `partial=True` porque comparar 4 dias contra meses fechados é o
    erro de leitura mais fácil de cometer nessa tela."""
    result: list[dict] = []
    year, month = today.year, today.month
    cursor = [(year, month)]
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        cursor.append((year, month))

    for y, m in reversed(cursor):
        first = datetime.date(y, m, 1)
        last = datetime.date(y + (m == 12), (m % 12) + 1, 1) - datetime.timedelta(days=1)
        business = business_days_between(first, last)
        closed = [d for d in business if d < today]
        in_month = {d: h for d, h in daily_totals.items() if first <= d <= last}
        days_worked = sum(1 for h in in_month.values() if h > 0)
        result.append({
            "month": f"{y:04d}-{m:02d}",
            "hours": round(sum(in_month.values()), 2),
            "days_worked": days_worked,
            "business_days": len(business),
            "business_days_closed": len(closed),
            "partial": (y, m) == (today.year, today.month),
            # mês sem nenhum lançamento NÃO é mês de zero hora: é mês sem
            # informação (admissão posterior, licença, ou simplesmente fora do
            # histórico). Uma coluna de altura zero afirmaria "trabalhou
            # nada", que é diferente — o frontend desenha como "sem dado".
            "no_data": days_worked == 0,
        })
    return result


def day_matched_comparison(
    daily_totals: dict[datetime.date, float],
    start: datetime.date,
    end: datetime.date,
    today: datetime.date,
) -> dict | None:
    """Compara o período com a janela anterior de MESMO número de dias úteis
    encerrados, não com o mês anterior fechado.

    Sem isso, "mês atual" no dia 4 compara 4 dias contra 21 e sempre acusa
    queda de ~80% — exatamente o falso alarme que o print original produzia.
    Aqui a comparação é dia útil contra dia útil.

    Devolve `None` quando não há dia útil encerrado no período ou quando a
    janela anterior não tem apontamento nenhum (dividir por zero produziria
    "-100%" pra quem só não trabalhava ainda)."""
    closed = [d for d in business_days_between(start, end) if d < today]
    if not closed:
        return None

    previous: list[datetime.date] = []
    day = start - datetime.timedelta(days=1)
    while len(previous) < len(closed):
        if day.weekday() < 5 and day not in _national_holidays(day.year):
            previous.append(day)
        day -= datetime.timedelta(days=1)
        if (start - day).days > 400:  # guarda contra loop infinito
            break
    if not previous:
        return None

    current_hours = round(sum(daily_totals.get(d, 0.0) for d in closed), 2)
    previous_hours = round(sum(daily_totals.get(d, 0.0) for d in previous), 2)
    if previous_hours <= 0:
        return None

    delta = round(current_hours - previous_hours, 2)
    oldest = min(previous)
    return {
        "label": f"mesmos {len(closed)} dias úteis desde {oldest.strftime('%d/%m')}",
        "hours": previous_hours,
        "delta_hours": delta,
        "delta_pct": round(delta / previous_hours, 4),
    }


def gap_days(
    business_days_closed: Iterable[datetime.date], daily_totals: dict[datetime.date, float]
) -> list[datetime.date]:
    """Dias úteis já encerrados sem nenhuma hora apontada, mais recentes
    primeiro. O dia em curso nunca entra — quem chama já filtrou por `< today`.

    Esta é a única métrica da tela que a tabela de lançamentos é incapaz de
    mostrar por construção: um dia sem apontamento é uma linha que não
    existe."""
    return sorted(
        (d for d in business_days_closed if daily_totals.get(d, 0.0) <= 0), reverse=True
    )


def outlier_days(
    daily_totals: dict[datetime.date, float], min_sample: int = 10
) -> set[datetime.date]:
    """Dias cujo total se afasta do padrão do próprio funcionário, por desvio
    absoluto mediano (MAD) — robusto a poucos dias extremos, diferente do
    desvio padrão. Conjunto vazio se a amostra for menor que `min_sample`,
    porque com poucos dias qualquer variação parece anomalia."""
    sample = [h for h in daily_totals.values() if h > 0]
    if len(sample) < min_sample:
        return set()
    median = statistics.median(sample)
    mad = statistics.median([abs(h - median) for h in sample])
    # 1,4826 converte MAD em estimador consistente do desvio padrão; o piso de
    # 1 h evita marcar tudo como anômalo em quem aponta 6,00 h todo dia (MAD=0).
    threshold = max(1.5 * 1.4826 * mad, 1.0)
    return {d for d, h in daily_totals.items() if h > 0 and abs(h - median) > threshold}


def parse_hhmm(value: str | None) -> int | None:
    """`ttimebit.pStart`/`pEnd` ("HHMM", varchar(4)) para minutos desde a
    meia-noite. Medido 100% preenchido nos 11.278 lançamentos de 2026, mas
    aparecem valores fora do padrão no histórico, então tudo que não casar
    volta `None` em vez de estourar."""
    text = str(value or "").strip()
    if len(text) != 4 or not text.isdigit():
        return None
    hour, minute = int(text[:2]), int(text[2:])
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def format_hhmm(minutes: int | None) -> str | None:
    """Minutos desde a meia-noite para "HH:MM" — formato que vai pro payload,
    já pronto pra exibir (o frontend não deve reformatar hora)."""
    if minutes is None:
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
