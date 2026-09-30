"""Testes do logging estruturado, do request-id e do handler global de erro —
ver `backend/app/core/logging.py` e `main.py`.

Nada aqui toca banco: `/auth/me` sem sessão responde 401 em memória, e o
erro não tratado é forçado por monkeypatch."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.api.routers import auth as auth_router
from backend.app.core import logging as app_logging


def test_sanitize_request_id_aceita_id_seguro():
    assert app_logging.sanitize_request_id("abc-123.XYZ_9") == "abc-123.XYZ_9"


def test_sanitize_request_id_rejeita_id_inseguro_e_gera_outro():
    for bad in ["", "com espaco", "linha\nquebrada", "acao\rvolta", "x" * 65, "çã"]:
        novo = app_logging.sanitize_request_id(bad)
        assert novo != bad
        assert len(novo) == 16  # token_hex(8)


def test_sanitize_request_id_sem_header_gera_id_novo():
    novo = app_logging.sanitize_request_id(None)
    assert len(novo) == 16


def test_json_formatter_gera_json_valido_com_request_id():
    app_logging.set_request_id("rid-teste")
    record = logging.LogRecord("teste", logging.INFO, __file__, 1, "mensagem", None, None)
    record.request_id = app_logging.get_request_id()
    payload = json.loads(app_logging.JsonFormatter().format(record))
    assert payload["message"] == "mensagem"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "teste"
    assert payload["request_id"] == "rid-teste"
    assert payload["ts"]


def test_resposta_ganha_x_request_id_gerado():
    client = TestClient(main.app)
    response = client.get("/auth/me")
    assert response.status_code == 401
    request_id = response.headers.get("X-Request-Id")
    assert request_id and len(request_id) == 16


def test_x_request_id_do_cliente_e_ecoado():
    client = TestClient(main.app)
    response = client.get("/auth/me", headers={"X-Request-Id": "cliente-123"})
    assert response.status_code == 401
    assert response.headers["X-Request-Id"] == "cliente-123"


def test_erro_nao_tratado_vira_500_json_com_o_mesmo_request_id(monkeypatch):
    def _boom(_token):
        raise RuntimeError("falha proposital do teste")

    monkeypatch.setattr(auth_router, "get_session", _boom)
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/auth/me", headers={"X-Request-Id": "erro-123"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Erro interno inesperado. Tente de novo em instantes."
    assert response.headers["X-Request-Id"] == "erro-123"


def test_requisicao_lenta_gera_aviso(monkeypatch, caplog):
    # 0 = loga toda requisição (semântica documentada em core/config.py), o
    # que torna o teste determinístico sem depender do relógio.
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(slow_request_ms=0))
    client = TestClient(main.app)
    with caplog.at_level(logging.WARNING):
        response = client.get("/auth/me")
    assert response.status_code == 401
    assert any("lenta" in record.getMessage() for record in caplog.records)
