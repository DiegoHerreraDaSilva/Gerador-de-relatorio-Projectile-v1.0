import datetime

import pytest

from backend.app.hours_analytics import (
    contract_weekday_hours,
    daily_stats,
    day_matched_comparison,
    empirical_daily_baseline,
    expected_hours_for_days,
    format_hhmm,
    gap_days,
    monthly_series,
    outlier_days,
    parse_hhmm,
    percentile,
    resolve_reference,
)
from backend.app.generator import business_days_between, national_holidays_between

FULL_TIME = {0: 8.0, 1: 8.0, 2: 8.0, 3: 8.0, 4: 8.0, 5: 0.0, 6: 0.0}
TODAY = datetime.date(2026, 9, 4)


def _contract(begin, end, weekday_hours=None):
    return {"begin": begin, "end": end, "weekday_hours": weekday_hours or FULL_TIME}


def _daily(days_hours: dict[str, float]) -> dict[datetime.date, float]:
    return {datetime.date.fromisoformat(d): h for d, h in days_hours.items()}


def _intern_history(days: int = 90, hours: float = 6.0) -> dict[datetime.date, float]:
    """Histórico sintético no padrão medido do estagiário: `hours` em todo dia
    útil, terminando na véspera de TODAY."""
    totals: dict[datetime.date, float] = {}
    day = TODAY - datetime.timedelta(days=1)
    while len(totals) < days:
        if day.weekday() < 5:
            totals[day] = hours
        day -= datetime.timedelta(days=1)
    return totals


class TestBusinessDaysBetween:
    def test_inclui_as_duas_pontas(self):
        days = business_days_between(datetime.date(2026, 8, 3), datetime.date(2026, 8, 7))
        assert len(days) == 5
        assert days[0] == datetime.date(2026, 8, 3)
        assert days[-1] == datetime.date(2026, 8, 7)

    def test_exclui_fim_de_semana(self):
        days = business_days_between(datetime.date(2026, 8, 8), datetime.date(2026, 8, 9))
        assert days == []

    def test_agosto_2026_tem_21_dias_uteis(self):
        # casa com o medido no banco: 21 dias com apontamento de 21 úteis
        days = business_days_between(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31))
        assert len(days) == 21

    def test_exclui_feriado_nacional(self):
        # 2026-09-07 (Independência) cai numa segunda
        days = business_days_between(datetime.date(2026, 9, 7), datetime.date(2026, 9, 7))
        assert days == []

    def test_feriados_no_intervalo(self):
        assert national_holidays_between(
            datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)
        ) == [datetime.date(2026, 9, 7)]


class TestContractWeekdayHours:
    def test_sem_contrato_devolve_none(self):
        assert contract_weekday_hours(datetime.date(2026, 8, 3), []) is None

    def test_contrato_em_aberto_cobre_data_futura(self):
        assert contract_weekday_hours(
            datetime.date(2026, 8, 3), [_contract(datetime.date(2023, 11, 1), None)]
        ) == FULL_TIME

    def test_data_antes_do_inicio_nao_casa(self):
        assert contract_weekday_hours(
            datetime.date(2025, 12, 31), [_contract(datetime.date(2026, 1, 1), None)]
        ) is None

    def test_data_depois_do_fim_nao_casa(self):
        contracts = [_contract(datetime.date(2022, 1, 1), datetime.date(2022, 12, 31))]
        assert contract_weekday_hours(datetime.date(2026, 8, 3), contracts) is None

    def test_escolhe_a_vigencia_correta_entre_varias(self):
        meio = {0: 4.0, 1: 4.0, 2: 4.0, 3: 4.0, 4: 4.0, 5: 0.0, 6: 0.0}
        contracts = [
            _contract(datetime.date(2022, 3, 21), datetime.date(2023, 1, 31), meio),
            _contract(datetime.date(2023, 2, 1), None, FULL_TIME),
        ]
        assert contract_weekday_hours(datetime.date(2022, 6, 1), contracts) == meio
        assert contract_weekday_hours(datetime.date(2026, 8, 3), contracts) == FULL_TIME

    def test_contrato_com_jornada_toda_zerada_nao_conta(self):
        # 14 dos 578 contratos medidos têm pPlannedTime* todo NULL: tratar como
        # "contrato de 0h" faria qualquer hora apontada virar 100% de excedente
        zerado = {i: 0.0 for i in range(7)}
        contracts = [_contract(datetime.date(2020, 1, 1), None, zerado)]
        assert contract_weekday_hours(datetime.date(2026, 8, 3), contracts) is None


class TestEmpiricalBaseline:
    def test_poucos_dias_nao_gera_baseline(self):
        assert empirical_daily_baseline(_intern_history(days=5), TODAY) is None

    def test_mediana_das_horas_diarias(self):
        per_day, sample, window = empirical_daily_baseline(_intern_history(), TODAY)
        assert per_day == 6.0
        assert sample >= 20
        assert window == 120

    def test_mediana_ignora_dias_parciais(self):
        # o banco tem lançamento de 0,17 h; a média cairia, a mediana não
        history = _intern_history(days=40)
        for day in list(history)[:5]:
            history[day] = 0.5
        assert empirical_daily_baseline(history, TODAY)[0] == 6.0

    def test_dia_em_curso_nao_entra_na_amostra(self):
        history = _intern_history()
        history[TODAY] = 0.25  # dia incompleto
        assert empirical_daily_baseline(history, TODAY)[0] == 6.0

    def test_amplia_a_janela_quando_a_curta_nao_alcanca(self):
        # 12 dias, todos há mais de 120 dias: cai na janela larga (piso 10)
        totals = {}
        day = TODAY - datetime.timedelta(days=200)
        while len(totals) < 12:
            if day.weekday() < 5:
                totals[day] = 7.0
            day += datetime.timedelta(days=1)
        per_day, sample, window = empirical_daily_baseline(totals, TODAY)
        assert (per_day, sample, window) == (7.0, 12, 365)

    def test_arredonda_para_quarto_de_hora(self):
        history = {d: 5.97 for d in _intern_history()}
        assert empirical_daily_baseline(history, TODAY)[0] == 6.0

    def test_sem_dado(self):
        assert empirical_daily_baseline({}, TODAY) is None


class TestResolveReference:
    def test_contrato_tem_precedencia_e_autoriza_percentual(self):
        ref = resolve_reference(
            [_contract(datetime.date(2023, 1, 1), None)], _intern_history(), TODAY
        )
        assert ref["source"] == "contract"
        assert ref["hours_per_day"] == 8.0
        assert ref["allows_percentage"] is True
        assert ref["hours_per_weekday"] == [8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0]

    def test_contrato_divergente_do_historico_gera_nota(self):
        ref = resolve_reference(
            [_contract(datetime.date(2023, 1, 1), None)], _intern_history(hours=6.0), TODAY
        )
        assert ref["divergence_note"] == "contrato 8 h · seu padrão medido ~6 h"

    def test_historico_nao_autoriza_percentual(self):
        # é o caso REAL do usuário de referência: sem contrato cadastrado
        ref = resolve_reference([], _intern_history(), TODAY)
        assert ref["source"] == "empirical"
        assert ref["hours_per_day"] == 6.0
        assert ref["allows_percentage"] is False
        assert ref["sample_days"] >= 20

    def test_calendario_e_o_penultimo_recurso(self):
        ref = resolve_reference([], {}, TODAY, calendar_daily=8.0)
        assert ref["source"] == "calendar"
        assert (ref["hours_per_day"], ref["allows_percentage"]) == (8.0, False)

    def test_sem_nenhuma_fonte_zera_a_referencia(self):
        ref = resolve_reference([], {}, TODAY, calendar_daily=None)
        assert ref["source"] == "none"
        assert ref["hours_per_day"] is None
        assert ref["hours_per_weekday"] is None
        assert ref["allows_percentage"] is False

    def test_fim_de_semana_sempre_zerado_sem_contrato(self):
        ref = resolve_reference([], _intern_history(), TODAY)
        assert ref["hours_per_weekday"][5] == 0.0
        assert ref["hours_per_weekday"][6] == 0.0


class TestExpectedHoursForDays:
    def test_soma_do_mes_do_estagiario_bate_com_o_medido(self):
        # agosto/2026: 21 dias úteis x 6h = 126h, contra 126,94h realmente
        # apontadas (medido no banco) -> a cascata empírica acerta a base
        ref = resolve_reference([], _intern_history(), TODAY)
        days = business_days_between(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31))
        assert expected_hours_for_days(days, ref) == pytest.approx(126.0)

    def test_contrato_de_8h_daria_168h_no_mesmo_mes(self):
        # o erro que a cascata evita: 126,94/168 = 76% e um deficit fantasma
        # de 41h num mes que foi integralmente cumprido
        ref = resolve_reference([_contract(datetime.date(2023, 1, 1), None)], {}, TODAY)
        days = business_days_between(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31))
        assert expected_hours_for_days(days, ref) == pytest.approx(168.0)

    def test_sem_referencia_devolve_none(self):
        ref = resolve_reference([], {}, TODAY, calendar_daily=None)
        assert expected_hours_for_days([datetime.date(2026, 8, 3)], ref) is None


class TestGapDays:
    def test_dia_sem_apontamento_e_detectado(self):
        closed = business_days_between(datetime.date(2026, 8, 3), datetime.date(2026, 8, 7))
        totals = _daily({"2026-08-03": 6.0, "2026-08-05": 6.0, "2026-08-07": 6.0})
        assert gap_days(closed, totals) == [
            datetime.date(2026, 8, 6), datetime.date(2026, 8, 4)
        ]

    def test_mais_recente_primeiro(self):
        closed = business_days_between(datetime.date(2026, 8, 3), datetime.date(2026, 8, 7))
        assert gap_days(closed, {})[0] == datetime.date(2026, 8, 7)

    def test_agosto_do_usuario_real_nao_tem_lacuna(self):
        closed = business_days_between(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31))
        assert gap_days(closed, {d: 6.0 for d in closed}) == []

    def test_dia_com_zero_horas_conta_como_lacuna(self):
        closed = [datetime.date(2026, 8, 3)]
        assert gap_days(closed, _daily({"2026-08-03": 0.0})) == [datetime.date(2026, 8, 3)]


class TestDayMatchedComparison:
    def test_compara_mesmo_numero_de_dias_uteis(self):
        # mês em curso com 3 dias úteis encerrados: compara com 3, não com 21
        totals = _daily({
            "2026-09-01": 6.0, "2026-09-02": 6.0, "2026-09-03": 6.0,
            "2026-08-27": 5.0, "2026-08-28": 5.0, "2026-08-31": 5.0,
        })
        result = day_matched_comparison(
            totals, datetime.date(2026, 9, 1), datetime.date(2026, 9, 4), TODAY
        )
        assert result["hours"] == 15.0
        assert result["delta_hours"] == 3.0
        assert result["delta_pct"] == pytest.approx(0.2)
        assert "3 dias úteis" in result["label"]

    def test_sem_dia_encerrado_devolve_none(self):
        result = day_matched_comparison(
            {}, datetime.date(2026, 9, 4), datetime.date(2026, 9, 4), datetime.date(2026, 9, 4)
        )
        assert result is None

    def test_janela_anterior_vazia_devolve_none(self):
        # evita anunciar "-100%" pra quem simplesmente ainda não trabalhava
        totals = _daily({"2026-09-01": 6.0})
        assert day_matched_comparison(
            totals, datetime.date(2026, 9, 1), datetime.date(2026, 9, 4), TODAY
        ) is None


class TestMonthlySeries:
    def test_devolve_13_meses_terminando_no_corrente(self):
        series = monthly_series(_intern_history(), TODAY)
        assert len(series) == 13
        assert series[-1]["month"] == "2026-09"
        assert series[0]["month"] == "2025-09"

    def test_so_o_mes_corrente_e_parcial(self):
        series = monthly_series(_intern_history(), TODAY)
        assert series[-1]["partial"] is True
        assert all(m["partial"] is False for m in series[:-1])

    def test_agosto_traz_21_dias_uteis(self):
        series = monthly_series(_intern_history(), TODAY)
        agosto = next(m for m in series if m["month"] == "2026-08")
        assert agosto["business_days"] == 21
        assert agosto["days_worked"] == 21
        assert agosto["hours"] == pytest.approx(126.0)

    def test_mes_sem_dado_aparece_marcado_e_nao_como_zero(self):
        # "0 h" e "sem informação" são estados diferentes: o usuário real foi
        # admitido em dez/2025, então set-nov/2025 não são meses de zero hora
        series = monthly_series({}, TODAY)
        assert len(series) == 13
        assert all(m["no_data"] is True for m in series)

    def test_mes_com_dado_nao_e_marcado_como_sem_dado(self):
        series = monthly_series(_intern_history(), TODAY)
        agosto = next(m for m in series if m["month"] == "2026-08")
        assert agosto["no_data"] is False


class TestDailyStats:
    def test_percentis_do_padrao_regular(self):
        stats = daily_stats(_intern_history(), TODAY)
        assert (stats["p25"], stats["median"], stats["p75"]) == (6.0, 6.0, 6.0)
        assert stats["n"] > 0

    def test_sem_dado_devolve_nulos(self):
        stats = daily_stats({}, TODAY)
        assert stats["median"] is None and stats["n"] == 0

    def test_percentil_com_um_unico_valor(self):
        # statistics.quantiles estoura com n=1; este é o estado do dia 1º
        assert percentile([6.0], 0.25) == 6.0

    def test_percentil_interpola(self):
        assert percentile([2.0, 4.0], 0.5) == 3.0


class TestOutlierDays:
    def test_amostra_pequena_nao_marca_nada(self):
        assert outlier_days(_daily({"2026-08-03": 12.0, "2026-08-04": 6.0})) == set()

    def test_dia_muito_fora_do_padrao_e_marcado(self):
        history = _intern_history(days=30)
        atipico = datetime.date(2026, 8, 12)
        history[atipico] = 14.0
        assert atipico in outlier_days(history)

    def test_padrao_perfeitamente_regular_nao_gera_falso_positivo(self):
        # MAD=0 em quem aponta 6,00h todo dia: sem o piso de 1h, qualquer
        # variação mínima viraria anomalia
        history = _intern_history(days=30)
        assert outlier_days(history) == set()


class TestHhmm:
    @pytest.mark.parametrize("value,minutes", [
        ("0900", 540), ("1601", 961), ("0000", 0), ("2359", 1439), ("0847", 527),
    ])
    def test_valores_reais(self, value, minutes):
        assert parse_hhmm(value) == minutes

    @pytest.mark.parametrize("value", [None, "", "9:00", "900", "abcd", "2460", "1099", "12345"])
    def test_valor_invalido_volta_none(self, value):
        assert parse_hhmm(value) is None

    def test_formata_para_exibicao(self):
        assert format_hhmm(527) == "08:47"
        assert format_hhmm(961) == "16:01"
        assert format_hhmm(None) is None
