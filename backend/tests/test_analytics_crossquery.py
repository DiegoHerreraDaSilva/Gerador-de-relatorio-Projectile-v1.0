"""Motor da consulta cruzada (`analytics/crossquery.py`) com dados fixos —
os totais dá pra conferir de cabeça. Sem banco, sem IA."""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.analytics import crossquery
from backend.app.analytics.facts import BilledSample, SendStatusRow
from backend.app.analytics.periods import month_options
from backend.app.repositories.engineering_hours_repository import HoursRow

TODAY = date(2026, 9, 24)


def _row(day, hours, pid, employee, package, *, cost_center="CAD", billable=True):
    project, client = {"P1": ("Projeto Um", "ACME"), "P2": ("Projeto Dois", "Beta")}[pid]
    return HoursRow(day, hours, pid, project, client, employee, package, cost_center, billable)


ROWS = [
    _row(date(2026, 8, 10), 5.0, "P1", "Ana Souza", "Pacote A"),
    _row(date(2026, 9, 5), 8.0, "P1", "Ana Souza", "Pacote A"),
    _row(date(2026, 9, 6), 3.0, "P2", "Bruno Lima", "Pacote B", cost_center="CAE", billable=False),
    _row(date(2026, 9, 7), 2.0, "P1", "Bruno Lima", "Pacote C"),
]


class FakeSources:
    def __init__(self, rows=ROWS, samples=(), manual=None, status=()):
        self._rows, self._samples, self._manual, self._status = rows, list(samples), manual or {}, list(status)

    def hours(self):
        return self._rows

    def billed_samples(self):
        return self._samples

    def manual_billed_by_month(self):
        return self._manual

    def project_info(self):
        return {"P1": {"name": "Projeto Um", "client": "ACME"}, "P2": {"name": "Projeto Dois", "client": "Beta"}}

    def send_status(self):
        return self._status


OPTIONS = {
    "months": month_options(TODAY, 12),
    "clients": ["ACME", "Beta"],
    "employees": ["Ana Souza", "Bruno Lima"],
    "projects": ["Projeto Dois", "Projeto Um"],
    "packages": ["Pacote A", "Pacote B", "Pacote C"],
}


def run(raw, sources=None):
    spec, notes = crossquery.build_spec(raw, OPTIONS, TODAY, 12)
    return crossquery.execute(spec, sources or FakeSources(), 1000, notes)


def table(result):
    return [(row.labels, row.values) for row in result.rows]


# --- horas -------------------------------------------------------------------


def test_horas_por_cliente_com_participacao():
    result = run({"measures": ["hours"], "group_by": ["client"], "month": "2026-09"})
    assert table(result) == [(("ACME",), {"hours": 10.0}), (("Beta",), {"hours": 3.0})]
    assert [row.share for row in result.rows] == [76.9, 23.1]
    assert result.totals == {"hours": 13.0}


def test_duas_dimensoes_cliente_por_mes_ordena_pelo_total_do_cliente():
    result = run({"measures": ["hours"], "group_by": ["client", "month"], "relative_period": "last_3_months"})
    assert [(row.labels, row.values["hours"]) for row in result.rows] == [
        (("ACME", "agosto/2026"), 5.0), (("ACME", "setembro/2026"), 10.0), (("Beta", "setembro/2026"), 3.0),
    ]


def test_varios_colaboradores_no_filtro_e_contagens_distintas():
    result = run({"measures": ["hours", "projects", "active_days"], "group_by": ["employee"],
                  "employees": ["Ana Souza", "Bruno Lima"]})
    assert table(result) == [
        (("Ana Souza",), {"hours": 13.0, "projects": 1, "active_days": 2}),
        (("Bruno Lima",), {"hours": 5.0, "projects": 2, "active_days": 2}),
    ]


def test_nao_faturavel_e_percentual():
    result = run({"measures": ["non_billable_hours", "non_billable_percent"], "month": "2026-09"})
    assert result.totals == {"non_billable_hours": 3.0, "non_billable_percent": 23.1}
    by_type = run({"measures": ["hours"], "group_by": ["billing_type"], "month": "2026-09"})
    assert table(by_type) == [(("Faturável",), {"hours": 10.0}), (("Não faturável",), {"hours": 3.0})]


def test_centro_de_custo_e_pacote():
    result = run({"measures": ["hours"], "group_by": ["cost_center"], "packages": ["Pacote B", "Pacote C"]})
    assert table(result) == [(("CAD",), {"hours": 2.0}), (("CAE",), {"hours": 3.0})][::-1]


def test_corte_por_valor_e_top_n():
    below = run({"measures": ["hours"], "group_by": ["employee"],
                 "threshold_measure": "hours", "threshold_op": "lt", "threshold_value": 6})
    assert table(below) == [(("Bruno Lima",), {"hours": 5.0})]
    top = run({"measures": ["hours"], "group_by": ["client"], "top_n": 1})
    assert table(top) == [(("ACME",), {"hours": 15.0})]
    assert top.group_count == 2


def test_serie_mensal_tem_mes_sem_hora_como_zero_em_ordem_cronologica():
    result = run({"measures": ["hours"], "group_by": ["month"], "month": "2026-07", "month_end": "2026-09"})
    assert [(row.labels[0], row.values["hours"]) for row in result.rows] == [
        ("julho/2026", 0.0), ("agosto/2026", 5.0), ("setembro/2026", 13.0),
    ]


def test_media_por_colaborador():
    result = run({"measures": ["avg_hours_per_employee"], "month": "2026-09"})
    assert result.totals == {"avg_hours_per_employee": 6.5}


# --- validação --------------------------------------------------------------


def test_consulta_sem_medida_valida_e_recusada():
    with pytest.raises(crossquery.InvalidQueryError):
        crossquery.build_spec({"measures": ["drop table"]}, OPTIONS, TODAY, 12)


def test_valor_desconhecido_e_dimensao_indisponivel_viram_aviso():
    spec, notes = crossquery.build_spec(
        {"measures": ["billed_hours"], "group_by": ["employee", "project"], "clients": ["Inventada SA"]},
        OPTIONS, TODAY, 12,
    )
    assert spec.group_by == ["project"] and spec.clients == []
    assert any("Inventada SA" in note for note in notes)
    assert any("colaborador" in note for note in notes)


def test_medidas_de_fontes_diferentes_nao_se_misturam():
    spec, notes = crossquery.build_spec({"measures": ["hours", "billed_hours"]}, OPTIONS, TODAY, 12)
    assert spec.measures == ["hours"] and notes


def test_contexto_volta_como_a_mesma_consulta():
    spec, _ = crossquery.build_spec(
        {"measures": ["hours"], "group_by": ["client", "month"], "employees": ["Ana Souza"],
         "month": "2026-08", "month_end": "2026-09", "top_n": 5,
         "threshold_measure": "hours", "threshold_op": "gt", "threshold_value": 1},
        OPTIONS, TODAY, 12,
    )
    again, _ = crossquery.build_spec(spec.as_context(), OPTIONS, TODAY, 12)
    assert again == spec


# --- faturamento --------------------------------------------------------------

SAMPLES = [BilledSample("P1", "2026-09", 9.0)]


def test_total_do_time_usa_ajuste_manual_e_bate_com_o_painel():
    result = run({"measures": ["worked_hours", "billed_hours", "performance_percent"], "group_by": ["month"],
                  "month": "2026-08", "month_end": "2026-09"},
                 FakeSources(samples=SAMPLES, manual={"2026-08": 4.0}))
    assert table(result) == [
        (("agosto/2026",), {"worked_hours": 5.0, "billed_hours": 4.0, "performance_percent": -20.0}),
        (("setembro/2026",), {"worked_hours": 13.0, "billed_hours": 9.0, "performance_percent": -30.8}),
    ]


def test_por_projeto_sem_relatorio_nao_vira_menos_cem_por_cento():
    result = run({"measures": ["worked_hours", "billed_hours", "perf_hours", "performance_percent"],
                  "group_by": ["project"], "month": "2026-09"}, FakeSources(samples=SAMPLES))
    assert table(result) == [
        (("Projeto Um",), {"worked_hours": 10.0, "billed_hours": 9.0, "perf_hours": -1.0, "performance_percent": -10.0}),
        (("Projeto Dois",), {"worked_hours": 3.0, "billed_hours": None, "perf_hours": None, "performance_percent": None}),
    ]
    # o TOTAL é o número do Painel pro recorte (faturado 9 x tudo trabalhado
    # no mês, 13) — não a soma só de quem tem relatório (-1)
    assert result.totals == {"worked_hours": 13.0, "billed_hours": 9.0, "perf_hours": -4.0,
                             "performance_percent": -30.8}
    assert any("não têm faturado" in note for note in result.notes)


def test_ajuste_manual_nao_vale_com_recorte_de_cliente():
    result = run({"measures": ["billed_hours"], "clients": ["ACME"], "month": "2026-08"},
                 FakeSources(samples=SAMPLES, manual={"2026-08": 4.0}))
    assert result.totals == {"billed_hours": None}


# --- status de envio --------------------------------------------------------------

STATUS = [
    SendStatusRow("P1", "Projeto Um", "ACME", "2026-09", "sent"),
    SendStatusRow("P2", "Projeto Dois", "Beta", "2026-09", "none"),
    SendStatusRow("P1", "Projeto Um", "ACME", "2026-08", "none"),
]


def test_status_de_envio_por_status_e_taxa():
    result = run({"measures": ["project_months", "send_rate_percent"], "group_by": ["status"], "month": "2026-09"},
                 FakeSources(status=STATUS))
    assert sorted(table(result)) == [(("Enviado",), {"project_months": 1, "send_rate_percent": 100.0}),
                                     (("Não enviado",), {"project_months": 1, "send_rate_percent": 0.0})]
    assert result.totals["send_rate_percent"] == 50.0


def test_projetos_nao_enviados_no_periodo():
    result = run({"measures": ["project_months"], "group_by": ["project"], "statuses": ["none"],
                  "relative_period": "last_3_months"}, FakeSources(status=STATUS))
    assert table(result) == [(("Projeto Dois",), {"project_months": 1}), (("Projeto Um",), {"project_months": 1})]


def test_performance_do_cliente_compara_com_tudo_o_que_ele_trabalhou_como_o_painel():
    """Painel filtrado por cliente: faturado do cliente no mês x TODAS as horas
    do cliente no mês — inclusive de projeto sem relatório recebido."""
    rows = ROWS + [HoursRow(date(2026, 9, 8), 4.0, "P3", "Projeto Três", "ACME", "Ana Souza", "Pacote D")]

    class Sources(FakeSources):
        def project_info(self):
            return {**super().project_info(), "P3": {"name": "Projeto Três", "client": "ACME"}}

    result = run({"measures": ["worked_hours", "billed_hours", "perf_hours", "performance_percent"],
                  "group_by": ["client"], "month": "2026-09"}, Sources(rows=rows, samples=SAMPLES))
    assert table(result)[0] == (("ACME",), {"worked_hours": 14.0, "billed_hours": 9.0, "perf_hours": -5.0,
                                            "performance_percent": -35.7})
    assert table(result)[1][1]["performance_percent"] is None  # Beta: nenhum relatório → sem performance
