"""Resumo executivo do mês: números em Python (dict falso no lugar do `compute_monthly_kpis`), texto automático
sempre disponível, IA opcional e só aceita se todo número veio dos fatos. Claude e Projectile sempre falsos."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import executive_summary as es
from backend.app import management
from backend.app.analytics import claude_client
from backend.app.api.dependencies import require_session
from backend.app.core import authz
from backend.app.main import app

TODAY = date(2026, 9, 30)


def month(key, worked=1000.0, billed=1100.0, perf=0.1, nonbill=200.0, nonbill_pct=0.2, days=4.0):
    return {
        "month": key,
        "worked_hours": worked,
        "billed_hours": billed,
        "perf_kpi_pct": perf,
        "nonbillable_hours": nonbill,
        "nonbillable_kpi_pct": nonbill_pct,
        "elaboration_days": days,
    }


def send_row(m, client, status, project="P"):
    return {"month": m, "project_id": f"{client}-{project}", "project_name": project, "client": client, "status": status}


KPIS = {
    "months": [month("2026-08", worked=1200.0, billed=1320.0, perf=0.1, days=4.5), month("2026-07", worked=1000.0, billed=1050.0, perf=0.05)],
    "project_send_status": [
        send_row("2026-08", "Mercedes", "sent", "A"),
        send_row("2026-08", "Mercedes", "none", "B"),
        send_row("2026-08", "Lauer", "partial", "C"),
        send_row("2026-08", "Lauer", "none", "D"),
        send_row("2026-08", "MBB", "closed", "E"),
        send_row("2026-07", "Mercedes", "none", "Z"),  # outro mês: não conta
    ],
}


# --- fatos -----------------------------------------------------------------------------------------------------


def test_fatos_do_mes_e_variacao_sobre_o_anterior():
    facts = es.build_facts(KPIS, "2026-08")
    assert facts["month_label"] == "Agosto/2026" and facts["previous_month_label"] == "Julho/2026"
    assert facts["worked_hours"] == 1200.0 and facts["billed_hours"] == 1320.0
    assert facts["performance_pct"] == 10.0
    assert facts["worked_delta_pct"] == 20.0  # (1200 - 1000) / 1000
    assert facts["performance_delta_pts"] == 5.0  # 10% - 5%
    assert facts["elaboration_days"] == 4.5


def test_status_de_envio_so_do_mes_e_pendencias_por_cliente():
    send = es.build_facts(KPIS, "2026-08")["send"]
    assert send == {"sent": 1, "partial": 1, "none": 2, "closed": 1, "total": 5, "pending_projects": 3}
    pending = es.build_facts(KPIS, "2026-08")["pending_clients"]
    assert pending == [{"client": "Lauer", "projects": 2}, {"client": "Mercedes", "projects": 1}]  # mais pendências primeiro


def test_mes_sem_anterior_ou_com_anterior_zerado_nao_inventa_variacao():
    alone = es.build_facts({"months": [month("2026-08")], "project_send_status": []}, "2026-08")
    assert alone["worked_delta_pct"] is None and alone["previous_month_label"] is None
    zero = es.build_facts({"months": [month("2026-08"), month("2026-07", worked=0.0)], "project_send_status": []}, "2026-08")
    assert zero["worked_delta_pct"] is None


def test_janeiro_compara_com_dezembro():
    assert es.previous_month("2026-01") == "2025-12"
    assert es.previous_month("2026-03") == "2026-02"


def test_mes_fora_do_resultado_e_erro():
    with pytest.raises(es.SummaryError):
        es.build_facts(KPIS, "2024-01")


def test_sem_faturado_a_performance_fica_nula_e_o_texto_diz_isso():
    facts = es.build_facts({"months": [month("2026-08", billed=None, perf=None)], "project_send_status": []}, "2026-08")
    assert facts["billed_hours"] is None and facts["performance_pct"] is None
    assert "não há horas faturadas" in es.deterministic_text(facts)


# --- texto automático -------------------------------------------------------------------------------------------


def test_texto_automatico_tem_os_numeros_no_formato_brasileiro():
    text = es.deterministic_text(es.build_facts(KPIS, "2026-08"))
    assert "1.200,0 h" in text and "20,0% acima de Julho/2026" in text
    assert "performance de 10,0%" in text and "5,0 p.p. acima de Julho/2026" in text
    assert "4,5 dias úteis" in text
    assert "3 ainda estão sem envio completo" in text


def test_linha_de_pendencias_lista_os_clientes_e_corta_em_cinco():
    facts = es.build_facts(KPIS, "2026-08")
    assert es.pending_line(facts) == "Pendências por cliente: Lauer (2), Mercedes (1)."
    many = {**facts, "pending_clients": [{"client": f"C{i}", "projects": 1} for i in range(8)]}
    assert es.pending_line(many).endswith("e mais 3.")
    assert es.pending_line({**facts, "pending_clients": []}) == ""


# --- a IA é opcional e conferida --------------------------------------------------------------------------------


@pytest.fixture
def fake_kpis(monkeypatch):
    monkeypatch.setattr(management, "compute_monthly_kpis", lambda months, **kw: KPIS)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-falsa")


def test_texto_do_claude_so_vale_com_numeros_dos_fatos(fake_kpis, monkeypatch):
    monkeypatch.setattr(claude_client, "summarize", lambda usage, facts: "Agosto teve 1.200,0 h, 20% a mais que julho, com performance de 10%.")
    result = es.generate("2026-08", today=TODAY)
    assert result["source"] == "claude" and result["ai_note"] is None
    assert result["text"].startswith("Agosto teve 1.200,0 h")


def test_numero_inventado_descarta_o_claude_e_usa_o_texto_automatico(fake_kpis, monkeypatch):
    monkeypatch.setattr(claude_client, "summarize", lambda usage, facts: "Agosto teve 1.800,0 h, um recorde.")  # 1800 não existe nos fatos
    result = es.generate("2026-08", today=TODAY)
    assert result["source"] == "automatico" and "1.200,0 h" in result["text"]
    assert "texto automático" in result["ai_note"]


def test_claude_fora_do_ar_ou_sem_chave_cai_no_texto_automatico(fake_kpis, monkeypatch):
    def down(usage, facts):
        raise RuntimeError("API fora")

    monkeypatch.setattr(claude_client, "summarize", down)
    assert es.generate("2026-08", today=TODAY)["source"] == "automatico"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    called = []
    monkeypatch.setattr(claude_client, "summarize", lambda *a: called.append(1) or "x")
    assert es.generate("2026-08", today=TODAY)["source"] == "automatico" and called == []  # sem chave nem tenta


def test_sem_pedir_ia_nem_chama_o_claude(fake_kpis, monkeypatch):
    monkeypatch.setattr(claude_client, "summarize", lambda *a: pytest.fail("não devia chamar"))
    result = es.generate("2026-08", use_ai=False, today=TODAY)
    assert result["source"] == "automatico" and result["ai_note"] is None


def test_nenhum_nome_de_cliente_vai_para_a_ia(fake_kpis, monkeypatch):
    seen = {}
    monkeypatch.setattr(claude_client, "summarize", lambda usage, facts: seen.update(facts=facts) or "Agosto teve 1.200,0 h.")
    result = es.generate("2026-08", today=TODAY)
    payload = json.dumps(seen["facts"], ensure_ascii=False)
    assert "Mercedes" not in payload and "Lauer" not in payload and "pending_clients" not in payload
    assert "Lauer (2)" in result["text"]  # os nomes entram só depois, localmente


def test_mes_invalido_ou_futuro(fake_kpis):
    for bad in ("2026-13", "agosto", "2026-8", "2026-10"):
        with pytest.raises(es.SummaryError):
            es.generate(bad, today=TODAY)


# --- a rota (só gerente) ----------------------------------------------------------------------------------------


@pytest.fixture
def client(fake_kpis, monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(claude_client, "summarize", lambda usage, facts: "Agosto teve 1.200,0 h.")
    users = {"gerente": {"name": "G", "login": "gerente", "email": "g@x"}, "colab": {"name": "C", "login": "colab", "email": "c@x"}}

    def as_user(login):
        app.dependency_overrides[require_session] = lambda: users[login]
        return TestClient(app)

    yield as_user
    app.dependency_overrides.pop(require_session, None)


def test_rota_devolve_fatos_texto_e_origem(client, monkeypatch):
    monkeypatch.setattr(es, "date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    response = client("gerente").get("/management/executive-summary", params={"month": "2026-08"})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "claude" and body["facts"]["worked_hours"] == 1200.0 and "Lauer (2)" in body["text"]


def test_rota_sem_ia_e_mes_invalido(client, monkeypatch):
    monkeypatch.setattr(es, "date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    assert client("gerente").get("/management/executive-summary", params={"month": "2026-08", "use_ai": "false"}).json()["source"] == "automatico"
    assert client("gerente").get("/management/executive-summary", params={"month": "2024-01"}).status_code == 400
    assert client("gerente").get("/management/executive-summary", params={"month": "agosto"}).status_code == 422


def test_rota_so_para_gerente(client):
    assert client("colab").get("/management/executive-summary", params={"month": "2026-08"}).status_code == 403
