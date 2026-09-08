import datetime

from backend.app.generator import (
    business_days_between,
    is_santo_andre_filiale,
    local_holidays_for_filiale,
    national_holidays_between,
)


class TestIsSantoAndreFiliale:
    def test_valor_real_medido_no_projectile(self):
        assert is_santo_andre_filiale("Santo André - São Paulo") is True

    def test_sem_acento_ainda_casa(self):
        assert is_santo_andre_filiale("Santo Andre - SP") is True

    def test_outra_filial_nao_casa(self):
        assert is_santo_andre_filiale("São Paulo") is False
        assert is_santo_andre_filiale("São Bernardo do Campo - MBBras") is False

    def test_none_nao_casa(self):
        assert is_santo_andre_filiale(None) is False

    def test_string_vazia_nao_casa(self):
        assert is_santo_andre_filiale("") is False


class TestLocalHolidaysForFiliale:
    def test_feriado_estadual_sempre_entra(self):
        # 9 de julho, Revolução Constitucionalista (Lei Estadual 9.497/1997) —
        # aplicado a qualquer filial, todas medidas dentro do estado de SP
        holidays = local_holidays_for_filiale(2026, "São Bernardo do Campo - MBBras")
        assert datetime.date(2026, 7, 9) in holidays

    def test_feriado_municipal_so_pra_santo_andre(self):
        # 8 de abril, aniversário da cidade (Lei Municipal 4.148/1973)
        santo_andre = local_holidays_for_filiale(2026, "Santo André - São Paulo")
        outra_filial = local_holidays_for_filiale(2026, "São Paulo")
        assert datetime.date(2026, 4, 8) in santo_andre
        assert datetime.date(2026, 4, 8) not in outra_filial

    def test_sem_filial_tem_o_estadual_mais_a_ponte(self):
        # 9 de julho de 2026 é quinta -- emenda com a sexta (10/07). Não usa
        # igualdade estrita de conjunto porque feriado NACIONAL em terça/
        # quinta também gera ponte (ver TestBridgeDays) -- aqui só confirma
        # que o estadual e a ponte dele estão presentes.
        holidays = local_holidays_for_filiale(2026, None)
        assert {datetime.date(2026, 7, 9), datetime.date(2026, 7, 10)} <= holidays


class TestBridgeDays:
    def test_feriado_na_quinta_emenda_com_a_sexta(self):
        # 9 de julho de 2026 é quinta
        holidays = local_holidays_for_filiale(2026, None)
        assert datetime.date(2026, 7, 10) in holidays

    def test_feriado_nacional_na_terca_emenda_com_a_segunda(self):
        # Tiradentes (21/04) em 2026 cai numa terça -- emenda com 20/04
        holidays = local_holidays_for_filiale(2026, None)
        assert datetime.date(2026, 4, 21).weekday() == 1
        assert datetime.date(2026, 4, 20) in holidays

    def test_feriado_na_quarta_nao_gera_ponte(self):
        # 8 de abril de 2026 (municipal de Santo André) é quarta -- sem ponte
        holidays = local_holidays_for_filiale(2026, "Santo André - São Paulo")
        assert datetime.date(2026, 4, 7) not in holidays
        assert datetime.date(2026, 4, 9) not in holidays


class TestBusinessDaysBetweenComExtraHolidays:
    def test_sem_extra_holidays_comportamento_identico_a_antes(self):
        # 9 de julho de 2026 é uma quinta -- sem o argumento novo, continua
        # sendo dia útil normal (nenhum chamador existente pode quebrar)
        days = business_days_between(datetime.date(2026, 7, 9), datetime.date(2026, 7, 9))
        assert days == [datetime.date(2026, 7, 9)]

    def test_com_extra_holidays_exclui_o_feriado_estadual(self):
        extra = local_holidays_for_filiale(2026, "Santo André - São Paulo")
        days = business_days_between(
            datetime.date(2026, 7, 9), datetime.date(2026, 7, 9), extra_holidays=extra
        )
        assert days == []

    def test_com_extra_holidays_exclui_o_municipal_de_santo_andre(self):
        # 8 de abril de 2026 é uma quarta-feira
        extra = local_holidays_for_filiale(2026, "Santo André - São Paulo")
        days = business_days_between(
            datetime.date(2026, 4, 8), datetime.date(2026, 4, 8), extra_holidays=extra
        )
        assert days == []

    def test_municipal_nao_afeta_quem_nao_e_de_santo_andre(self):
        extra = local_holidays_for_filiale(2026, "São Paulo")
        days = business_days_between(
            datetime.date(2026, 4, 8), datetime.date(2026, 4, 8), extra_holidays=extra
        )
        assert days == [datetime.date(2026, 4, 8)]


class TestNationalHolidaysBetweenComExtraHolidays:
    def test_marca_o_feriado_estadual_quando_passado(self):
        extra = local_holidays_for_filiale(2026, "São Paulo")
        found = national_holidays_between(
            datetime.date(2026, 7, 1), datetime.date(2026, 7, 31), extra_holidays=extra
        )
        assert datetime.date(2026, 7, 9) in found

    def test_sem_extra_holidays_nao_marca_feriado_estadual(self):
        found = national_holidays_between(datetime.date(2026, 7, 1), datetime.date(2026, 7, 31))
        assert datetime.date(2026, 7, 9) not in found
