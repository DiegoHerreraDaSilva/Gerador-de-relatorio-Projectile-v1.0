"""Lembretes de relatório parado (opt-in): a decisão é pura e o ciclo roda com Graph e Projectile falsos.
Nenhum e-mail real sai: `notifications.send_checked` é substituído em todo teste."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from backend.app import notifications, projectile_db
from backend.app.auto_generation import reminders, scheduler
from backend.app.core import authz
from backend.app.db.reports_schema import auto_reports
from backend.app.services import auto_generation_store as store

from .test_auto_generation import _assign, _run, auto_db, reviewers  # noqa: F401 — fixtures reaproveitadas

NOW = datetime(2026, 10, 7, 12, 0)


def item(id="r1", status="em_revisao", reviewer="colab", updated=NOW - timedelta(days=5), **extra):
    return {
        "id": id,
        "status": status,
        "reviewer_login": reviewer,
        "reviewer_name": "Colaborador",
        "project_name": f"Projeto {id}",
        "competence": "2026-09",
        "updated_at": updated,
        **extra,
    }


# --- decisão pura ------------------------------------------------------------------------------------------


def test_dono_do_relatorio_parado():
    assert reminders.owner_of(item(status="em_revisao", reviewer="colab")) == "reviewer"
    assert reminders.owner_of(item(status="devolvido", reviewer="colab")) == "reviewer"
    assert reminders.owner_of(item(status="revisado", reviewer="colab")) == "manager"  # aguardando aprovação
    assert reminders.owner_of(item(status="em_revisao", reviewer="")) == "manager"  # sem revisor, o gerente revisa


def test_so_lembra_depois_de_n_dias_sem_acao():
    assert reminders.plan([item(updated=NOW - timedelta(days=2))], {}, NOW, 3) == []
    due = reminders.plan([item(updated=NOW - timedelta(days=3))], {}, NOW, 3)
    assert [d["id"] for d in due] == ["r1"] and due[0]["n"] == 1 and due[0]["idle_days"] == 3


def test_estado_que_nao_espera_ninguem_nao_entra():
    for status in ("aprovado", "enviado", "pulado", "erro", "gerando"):
        assert reminders.plan([item(status=status)], {}, NOW, 3) == []


def test_nao_repete_antes_de_n_dias_do_ultimo_lembrete():
    last = {"r1": {"created_at": NOW - timedelta(days=1), "metadata": {"n": 1}}}
    assert reminders.plan([item()], last, NOW, 3) == []  # parado há 5, mas lembrado ontem
    older = {"r1": {"created_at": NOW - timedelta(days=3), "metadata": {"n": 1}}}
    due = reminders.plan([item()], older, NOW, 3)
    assert due[0]["n"] == 2


def test_no_maximo_tres_lembretes_por_relatorio():
    last = {"r1": {"created_at": NOW - timedelta(days=10), "metadata": {"n": reminders.MAX_REMINDERS}}}
    assert reminders.plan([item()], last, NOW, 3) == []
    ok = {"r1": {"created_at": NOW - timedelta(days=10), "metadata": {"n": reminders.MAX_REMINDERS - 1}}}
    assert reminders.plan([item()], ok, NOW, 3)[0]["n"] == reminders.MAX_REMINDERS


def test_o_e_mail_consolidado_lista_tudo_do_mais_parado_ao_menos():
    due = reminders.plan([item("a", updated=NOW - timedelta(days=4)), item("b", updated=NOW - timedelta(days=9))], {}, NOW, 3)
    subject, body = reminders.digest("reviewer", "Ana", due)
    assert subject == "Lembrete: 2 relatórios esperando sua revisão"
    assert body.index("Projeto b") < body.index("Projeto a")
    assert "view=my-reviews&report=b" in body and "sem ação há 9 dias" in body
    single, _ = reminders.digest("manager", "Gerência", due[:1])
    assert single == "Lembrete: 1 relatório esperando você"


# --- o ciclo completo (banco SQLite, Graph e Projectile falsos) -------------------------------------------------


@pytest.fixture
def mail(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(notifications, "_enabled", lambda: True)
    monkeypatch.setattr(notifications, "system_sender", lambda: "agente@x")
    monkeypatch.setattr(notifications, "send_checked", lambda sender, to, subject, body: sent.append({"to": to, "subject": subject, "body": body}) or True)
    monkeypatch.setattr(projectile_db, "fetch_user_emails", lambda logins: {login.lower(): f"{login.lower()}@x" for login in logins})
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    return sent


def _turn_on(days=3):
    with store.write_session() as s:
        s.set_config({"reminders_enabled": True, "reminder_after_days": days})


def _age(days):
    with store.get_engine().begin() as conn:
        conn.execute(update(auto_reports).values(updated_at=store.utcnow() - timedelta(days=days)))


def test_desligado_por_padrao_nao_manda_nada(auto_db, mail):
    _run()
    _age(10)
    assert reminders.run()["reason"] == "desligado"
    assert mail == []


def test_sem_graph_nao_roda(auto_db, mail, monkeypatch):
    monkeypatch.setattr(notifications, "_enabled", lambda: False)
    _run()
    _turn_on()
    _age(10)
    assert reminders.run()["reason"] == "sem e-mail"
    assert mail == []


def test_manda_um_e_mail_consolidado_por_pessoa_e_registra_o_lembrete(auto_db, reviewers, mail):
    items = _run()
    assert _assign(items["E8"]["id"], "colab").status_code == 200
    mail.clear()  # o aviso de atribuição usa o mesmo envio falso
    _turn_on()
    _age(5)
    summary = reminders.run()
    assert summary["reason"] == "ok" and summary["sent"] == 2  # o revisor e a gerência
    by_to = {tuple(m["to"]): m for m in mail}
    assert ("colab@x",) in by_to and ("gerente@x",) in by_to
    assert "1 relatório esperando sua revisão" in by_to[("colab@x",)]["subject"]
    assert "esperando você" in by_to[("gerente@x",)]["subject"]  # os outros projetos não têm revisor
    events = store.list_events(items["E8"]["id"])
    assert events[-1]["action"] == "reminder_sent" and events[-1]["metadata_json"]["n"] == 1


def test_no_mesmo_dia_nao_repete_e_depois_de_n_dias_volta(auto_db, reviewers, mail):
    items = _run()
    _assign(items["E8"]["id"], "colab")
    _turn_on()
    _age(5)
    assert reminders.run()["reminders"] >= 1
    mail.clear()
    assert reminders.run()["reason"] == "nada parado"  # acabou de ser lembrado
    assert mail == []
    future = store.utcnow() + timedelta(days=4)
    second = reminders.run(now=future)
    assert second["reason"] == "ok"
    assert store.list_events(items["E8"]["id"])[-1]["metadata_json"]["n"] == 2


def test_qualquer_acao_zera_a_espera(auto_db, reviewers, mail):
    items = _run()
    _assign(items["E8"]["id"], "colab")
    mail.clear()
    _turn_on()
    _age(1)  # acabou de mexer: nada parado
    assert reminders.run()["reason"] == "nada parado"
    assert mail == []


def test_envio_que_o_graph_recusou_nao_registra_lembrete(auto_db, reviewers, mail, monkeypatch):
    items = _run()
    _assign(items["E8"]["id"], "colab")
    _turn_on()
    _age(5)
    monkeypatch.setattr(notifications, "send_checked", lambda *a, **k: False)
    summary = reminders.run()
    assert summary["sent"] == 0 and summary["reminders"] == 0
    assert all(e["action"] != "reminder_sent" for e in store.list_events(items["E8"]["id"]))  # tenta de novo amanhã


def test_destinatario_sem_email_no_projectile_e_pulado(auto_db, reviewers, mail, monkeypatch):
    items = _run()
    _assign(items["E8"]["id"], "colab")
    mail.clear()
    _turn_on()
    _age(5)
    monkeypatch.setattr(projectile_db, "fetch_user_emails", lambda logins: {})
    assert reminders.run()["sent"] == 0 and mail == []


# --- quando o agendador roda ------------------------------------------------------------------------------------


def _sp(year, month, day, hour):
    return datetime(year, month, day, hour, 0, tzinfo=scheduler.TIMEZONE)


def test_so_roda_em_dia_util_depois_das_8h(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "_last_reminder_day", None)
    monkeypatch.setattr(reminders, "run", lambda: calls.append(1) or {"reason": "ok", "sent": 1, "reminders": 1})
    assert scheduler.remind_daily(_sp(2026, 10, 7, 7)) is None  # quarta, antes das 8h
    assert scheduler.remind_daily(_sp(2026, 10, 10, 9)) is None  # sábado
    assert scheduler.remind_daily(_sp(2026, 10, 11, 9)) is None  # domingo
    assert calls == []
    assert scheduler.remind_daily(_sp(2026, 10, 7, 8))["reason"] == "ok"  # quarta, 8h
    assert scheduler.remind_daily(_sp(2026, 10, 7, 15)) is None  # mesmo dia: não repete
    assert scheduler.remind_daily(_sp(2026, 10, 8, 9)) is not None  # dia seguinte
    assert len(calls) == 2


def test_desligado_nao_consome_o_dia(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_reminder_day", None)
    states = iter([{"reason": "desligado", "sent": 0, "reminders": 0}, {"reason": "ok", "sent": 1, "reminders": 1}])
    monkeypatch.setattr(reminders, "run", lambda: next(states))
    assert scheduler.remind_daily(_sp(2026, 10, 7, 8))["reason"] == "desligado"
    assert scheduler.remind_daily(_sp(2026, 10, 7, 9))["reason"] == "ok"  # ligou no meio do dia: roda hoje mesmo


def test_falha_nos_lembretes_nao_derruba_o_agendador(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_reminder_day", None)

    def broken():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(reminders, "run", broken)
    assert scheduler.remind_daily(_sp(2026, 10, 7, 9)) is None  # não levanta
    monkeypatch.setattr(reminders, "run", lambda: {"reason": "ok", "sent": 0, "reminders": 0})
    assert scheduler.remind_daily(_sp(2026, 10, 7, 10)) is not None  # falhou: o dia não foi marcado
