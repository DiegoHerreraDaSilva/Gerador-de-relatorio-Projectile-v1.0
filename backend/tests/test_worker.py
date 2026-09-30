"""Papéis do processo (PROCESS_ROLE) e o worker de background: quem roda os
loops de e-mail/agendador em cada topologia (NSSM single-process vs
containers web+worker)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.app import main, worker


def _role(monkeypatch, role: str) -> None:
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(process_role=role))


@pytest.mark.parametrize(("role", "esperado"), [("all", True), ("worker", True), ("web", False), ("ALL", True), (" Worker ", True)])
def test_jobs_enabled_por_papel(monkeypatch, role, esperado):
    _role(monkeypatch, role)
    assert worker.jobs_enabled() is esperado


def test_papel_invalido_falha_alto(monkeypatch):
    _role(monkeypatch, "servidor")
    with pytest.raises(RuntimeError, match="PROCESS_ROLE"):
        worker.process_role()


def test_worker_run_recusa_papel_web(monkeypatch):
    _role(monkeypatch, "web")
    with pytest.raises(RuntimeError, match="worker"):
        worker.run()


def test_hook_web_nao_sobe_os_loops_quando_papel_nao_manda(monkeypatch):
    chamados = []

    async def fake_loop():
        chamados.append(True)

    monkeypatch.setattr(main, "_poll_emails_loop", fake_loop)
    monkeypatch.setattr(main, "_auto_scheduler_loop", fake_loop)
    monkeypatch.setattr(main, "jobs_enabled", lambda: False)

    async def cenario():
        await main._start_email_polling()
        await main._start_auto_scheduler()
        await asyncio.sleep(0)

    asyncio.run(cenario())
    assert chamados == []


def test_hook_web_sobe_os_loops_quando_o_papel_deixa(monkeypatch):
    chamados = []

    async def fake_loop():
        chamados.append(True)

    monkeypatch.setattr(main, "_poll_emails_loop", fake_loop)
    monkeypatch.setattr(main, "_auto_scheduler_loop", fake_loop)
    monkeypatch.setattr(main, "jobs_enabled", lambda: True)

    async def cenario():
        await main._start_email_polling()
        await main._start_auto_scheduler()
        await asyncio.sleep(0)

    asyncio.run(cenario())
    assert chamados == [True, True]
