"""Feriados e dias úteis da geração de relatório: nacionais e móveis
(Páscoa via Meeus/Jones/Butcher), estaduais de SP, municipais de Santo
André e pontes — tudo calculado por ano, sem tabela externa.

Extraído de `generator.py`, que REEXPORTA estes nomes (a API de lá
continua valendo: `email_ingest` e o dashboard pessoal usam
`count_business_days`/`business_days_between`/`local_holidays_for_filiale`).
"""

from __future__ import annotations

import datetime
import unicodedata


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _easter_sunday(year: int) -> datetime.date:
    """Algoritmo anônimo gregoriano (Meeus/Jones/Butcher) para a Páscoa — usado
    para derivar os feriados móveis (Carnaval, Sexta-feira Santa, Corpus Christi)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return datetime.date(year, month, day)


def _national_holidays(year: int) -> set[datetime.date]:
    """Feriados nacionais fixos + móveis. Feriados estaduais/municipais não
    entram aqui — ficam de fora até serem pedidos explicitamente."""
    easter = _easter_sunday(year)
    holidays = {
        datetime.date(year, 1, 1),  # Confraternização Universal
        datetime.date(year, 4, 21),  # Tiradentes
        datetime.date(year, 5, 1),  # Dia do Trabalho
        datetime.date(year, 9, 7),  # Independência
        datetime.date(year, 10, 12),  # Nossa Senhora Aparecida
        datetime.date(year, 11, 2),  # Finados
        datetime.date(year, 11, 15),  # Proclamação da República
        datetime.date(year, 12, 25),  # Natal
        easter - datetime.timedelta(days=48),  # Carnaval (segunda)
        easter - datetime.timedelta(days=47),  # Carnaval (terça)
        easter - datetime.timedelta(days=2),  # Sexta-feira Santa
        easter + datetime.timedelta(days=60),  # Corpus Christi
    }
    if year >= 2024:
        holidays.add(datetime.date(year, 11, 20))  # Dia da Consciência Negra (Lei 14.759/2023)
    return holidays


def _sao_paulo_state_holidays(year: int) -> set[datetime.date]:
    """Feriado estadual de São Paulo — 9 de julho, Revolução Constitucionalista
    de 1932 (Lei Estadual nº 9.497/1997). Aplicado a todo o Dashboard de horas
    pessoal (não à geração de relatório nem a `count_business_days`, ver
    `local_holidays_for_filiale`): toda filial observada no Projectile (São
    Paulo, São Bernardo do Campo, Santo André) fica dentro do estado de SP."""
    return {datetime.date(year, 7, 9)}


def _santo_andre_municipal_holidays(year: int) -> set[datetime.date]:
    """Feriado municipal de Santo André — aniversário da cidade, 8 de abril
    (fundação em 1553, Lei Municipal nº 4.148/1973). Só entra pra quem tem
    `temployee.pFiliale` de Santo André, ver `local_holidays_for_filiale`."""
    return {datetime.date(year, 4, 8)}


def is_santo_andre_filiale(filiale: str | None) -> bool:
    """Sem acento/caixa porque o valor real de `temployee.pFiliale` no
    Projectile vem como texto livre (medido: "Santo André - São Paulo")."""
    return bool(filiale) and "santo andre" in _strip_accents(filiale).lower()


def _bridge_days(holidays: set[datetime.date]) -> set[datetime.date]:
    """ "Ponte"/emenda de feriado — prática comum da empresa (não uma regra de
    calendário oficial): feriado numa terça-feira emenda com a segunda-feira
    anterior, feriado numa quinta-feira emenda com a sexta-feira seguinte,
    formando um feriado prolongado de 4 dias. Recebe o conjunto de feriados
    JÁ combinado (nacional + estadual/municipal) pra não perder ponte de
    feriado nacional que caia numa terça/quinta (ex: Corpus Christi é sempre
    quinta)."""
    bridges: set[datetime.date] = set()
    for day in holidays:
        if day.weekday() == 1:  # terça
            bridges.add(day - datetime.timedelta(days=1))
        elif day.weekday() == 3:  # quinta
            bridges.add(day + datetime.timedelta(days=1))
    return bridges


def local_holidays_for_filiale(year: int, filiale: str | None) -> set[datetime.date]:
    """Feriado estadual (SP, sempre) + municipal (Santo André, só se a filial
    do funcionário for de lá) + ponte de qualquer um desses (ou de feriado
    nacional) que caia numa terça/quinta — usado exclusivamente pelo
    Dashboard de horas pessoal (`/my-hours`), nunca por
    `count_business_days`/geração de relatório: aplicar esses feriados
    globalmente mudaria a classificação de atraso de envio
    (`email_ingest.py`) pra funcionários de OUTRAS filiais, que não os têm."""
    holidays = set(_sao_paulo_state_holidays(year))
    if is_santo_andre_filiale(filiale):
        holidays |= _santo_andre_municipal_holidays(year)
    all_holidays = _national_holidays(year) | holidays
    holidays |= _bridge_days(all_holidays)
    return holidays


def business_days_between(start: datetime.date, end: datetime.date, extra_holidays: set[datetime.date] | None = None) -> list[datetime.date]:
    """Dias úteis (seg-sex, sem feriado nacional) de `start` até `end`, ambos
    INCLUSIVE — diferente de `count_business_days`, que exclui o `start` (ver
    o docstring dela). Devolve a lista, não a contagem, porque o Dashboard de
    horas precisa saber QUAIS dias são úteis pra achar os que ficaram sem
    apontamento, não só quantos são.

    `extra_holidays` (opcional) soma feriados estadual/municipal por cima dos
    nacionais — usado só pelo Dashboard de horas pessoal via
    `local_holidays_for_filiale`; sem esse argumento o comportamento é
    idêntico a antes (só feriado nacional), preservando `count_business_days`
    e todo outro chamador existente.

    O intervalo pode cruzar anos, então o conjunto de feriados é recalculado
    por ano conforme o cursor avança."""
    holidays_by_year: dict[int, set[datetime.date]] = {}
    days: list[datetime.date] = []
    day = start
    while day <= end:
        holidays = holidays_by_year.setdefault(day.year, _national_holidays(day.year))
        is_holiday = day in holidays or (extra_holidays is not None and day in extra_holidays)
        if day.weekday() < 5 and not is_holiday:
            days.append(day)
        day += datetime.timedelta(days=1)
    return days


def national_holidays_between(start: datetime.date, end: datetime.date, extra_holidays: set[datetime.date] | None = None) -> list[datetime.date]:
    """Feriados nacionais no intervalo (inclusive), ordenados — usado pra
    marcar a célula do dia no calendário do dashboard como feriado em vez de
    "dia útil sem apontamento". `extra_holidays` funciona igual ao de
    `business_days_between` (opcional, estadual/municipal)."""
    holidays_by_year: dict[int, set[datetime.date]] = {}
    found: list[datetime.date] = []
    day = start
    while day <= end:
        holidays = holidays_by_year.setdefault(day.year, _national_holidays(day.year))
        if day in holidays or (extra_holidays is not None and day in extra_holidays):
            found.append(day)
        day += datetime.timedelta(days=1)
    return found


def count_business_days(start: datetime.date, end: datetime.date) -> int:
    """Conta dias úteis (seg-sex, sem feriado nacional) estritamente APÓS
    `start` até `end` inclusive — usado por `email_ingest.py` pra medir quanto
    tempo depois do fechamento do mês um relatório foi enviado.

    A exclusão do próprio `start` é a semântica de que `email_ingest.py:460` e
    `management.py` dependem — NÃO mudar. Quem quer o intervalo fechado nas
    duas pontas usa `business_days_between`."""
    if end <= start:
        return 0
    return len(business_days_between(start + datetime.timedelta(days=1), end))
