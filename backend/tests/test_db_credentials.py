"""Credenciais de banco: o caminho por variável de ambiente (containers)
tem prioridade sobre o keyring, e a ausência dos dois vira DbCredentialsError
com mensagem que diz o que fazer."""

from __future__ import annotations

import pytest

from backend.app import db_credentials


def test_env_tem_prioridade_sobre_keyring(monkeypatch):
    monkeypatch.setenv("PROJECTILE_DB_PASSWORD", "senha-do-ambiente")
    monkeypatch.setattr(db_credentials.keyring, "get_password", lambda *a: pytest.fail("não deveria ler o keyring"))

    assert db_credentials.get_projectile_db_password("dashboards.board") == "senha-do-ambiente"


def test_env_tem_prioridade_reports(monkeypatch):
    monkeypatch.setenv("REPORTS_DB_PASSWORD", "outra-senha")

    assert db_credentials.get_reports_db_password("reports_app") == "outra-senha"


def test_sem_env_e_sem_keyring_explica(monkeypatch):
    monkeypatch.delenv("REPORTS_DB_PASSWORD", raising=False)
    monkeypatch.setattr(db_credentials.keyring, "get_password", lambda *a: None)

    with pytest.raises(db_credentials.DbCredentialsError) as exc:
        db_credentials.get_reports_db_password("reports_app")
    assert "REPORTS_DB_PASSWORD" in str(exc.value) or "Credential Manager" in str(exc.value)


def test_keyring_sem_backend_nao_vaza_excecao_crua(monkeypatch):
    monkeypatch.delenv("PROJECTILE_DB_PASSWORD", raising=False)

    def _sem_backend(*_a):
        raise RuntimeError("NoKeyringError")

    monkeypatch.setattr(db_credentials.keyring, "get_password", _sem_backend)

    with pytest.raises(db_credentials.DbCredentialsError, match="PROJECTILE_DB_PASSWORD"):
        db_credentials.get_projectile_db_password("dashboards.board")
