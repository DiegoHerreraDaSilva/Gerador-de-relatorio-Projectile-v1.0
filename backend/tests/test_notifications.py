"""Notificações por e-mail da geração automática: destinatário resolvido no
Projectile, links, opt-out, fail-open e o gate de Graph configurado."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app import notifications

_REPORT = {
    "id": "R1",
    "project_name": "Legislation Package - Estribo",
    "competence": "2026-08",
    "reviewer_login": "Colab",
    "reviewer_name": "Colaborador do Projectile",
}
_REVIEWER = {"login": "Colab", "name": "Colaborador do Projectile"}
_MANAGER = {"login": "gerente", "name": "Gerente", "email": "gerente@x"}


@pytest.fixture
def enviados(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(notifications, "_enabled", lambda: True)
    monkeypatch.setattr(notifications, "_sender_for", lambda actor: "s@x")
    monkeypatch.setattr(
        notifications.projectile_db,
        "fetch_user_emails",
        lambda logins: {login.strip().lower(): f"{login.strip().lower()}@x" for login in logins if login.strip().lower() != "dherrera"},
    )
    monkeypatch.setattr(notifications.email_ingest, "send_report_email", lambda **kw: sent.append(kw))
    return sent


def test_atribuicao_notifica_o_revisor_com_link(enviados):
    notifications.notify_reviewer_assigned(_REPORT, _REVIEWER, _MANAGER)

    assert len(enviados) == 1
    email = enviados[0]
    assert email["to_email"] == ["colab@x"]
    assert email["sender_email"] == "s@x"
    assert "revisar" in email["subject"].lower()
    assert "view=my-reviews&report=R1" in email["body_text"]
    assert email["attachments"] == []


def test_devolucao_notifica_com_o_comentario(enviados):
    notifications.notify_reviewer_returned(_REPORT, "ajuste as horas do sábado", _MANAGER)

    assert len(enviados) == 1
    assert "devolvido" in enviados[0]["subject"].lower()
    assert "ajuste as horas do sábado" in enviados[0]["body_text"]


def test_aprovacao_pendente_notifica_os_gerentes(enviados, monkeypatch):
    monkeypatch.setattr(notifications.authz, "MANAGEMENT_PANEL_LOGINS", {"gerente", "outro", "dherrera"})

    notifications.notify_awaiting_approval(_REPORT, _REVIEWER)

    assert len(enviados) == 1
    email = enviados[0]
    assert sorted(email["to_email"]) == ["gerente@x", "outro@x"]  # dherrera sem e-mail não entra
    assert "aprovação" in email["subject"].lower()
    assert "view=auto-generation&report=R1" in email["body_text"]


def test_opt_out_nao_envia(enviados, monkeypatch):
    monkeypatch.setattr(notifications, "_enabled", lambda: False)

    notifications.notify_reviewer_assigned(_REPORT, _REVIEWER, _MANAGER)
    notifications.notify_reviewer_returned(_REPORT, "x", _MANAGER)
    notifications.notify_awaiting_approval(_REPORT, _REVIEWER)

    assert enviados == []


def test_sem_email_do_destinatario_nao_envia(enviados, monkeypatch):
    monkeypatch.setattr(notifications.projectile_db, "fetch_user_emails", lambda logins: {})

    notifications.notify_reviewer_assigned(_REPORT, _REVIEWER, _MANAGER)

    assert enviados == []


def test_falha_no_envio_e_fail_open(monkeypatch):
    monkeypatch.setattr(notifications, "_enabled", lambda: True)
    monkeypatch.setattr(notifications, "_sender_for", lambda actor: "s@x")
    monkeypatch.setattr(notifications.projectile_db, "fetch_user_emails", lambda logins: {"colab": "colab@x"})

    def _boom(**kw):
        raise RuntimeError("Graph fora do ar")

    monkeypatch.setattr(notifications.email_ingest, "send_report_email", _boom)

    notifications.notify_reviewer_assigned(_REPORT, _REVIEWER, _MANAGER)  # não levanta


def test_enabled_exige_graph_configurado(monkeypatch):
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    assert notifications._enabled() is False


def test_enabled_respeita_o_padrao_geral(monkeypatch):
    monkeypatch.setenv("AZURE_CLIENT_ID", "app-id")
    monkeypatch.setattr(notifications.store, "get_config", lambda: {"notify_email": False})
    assert notifications._enabled() is False

    monkeypatch.setattr(notifications.store, "get_config", lambda: {})
    assert notifications._enabled() is True  # default do DEFAULTS é ligado


def test_link_usa_a_base_configurada(monkeypatch):
    monkeypatch.setattr(notifications, "get_settings", lambda: SimpleNamespace(app_base_url="https://relatorios.x/"))

    assert notifications._link("my-reviews", "R1") == "https://relatorios.x/?view=my-reviews&report=R1"
