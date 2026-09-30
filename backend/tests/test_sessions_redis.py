"""Store de sessão/rate-limit de `auth.py`: caminho em memória (default) e o
caminho Redis com `fakeredis` (sem exigir container)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import fakeredis
import pytest

from backend.app import auth


@pytest.fixture(autouse=True)
def _memory_store():
    auth.reset_store_for_tests()
    yield
    auth.reset_store_for_tests()


def _botar_na_redis(monkeypatch) -> fakeredis.FakeRedis:
    client = fakeredis.FakeRedis(decode_responses=True)
    auth.reset_store_for_tests(auth._RedisStore(client))
    return client


def test_sessao_em_memoria_cria_le_e_apaga():
    token = auth.create_session({"login": "dherrera", "name": "Diego"})

    assert auth.get_session(token)["login"] == "dherrera"

    auth.delete_session(token)
    assert auth.get_session(token) is None
    assert auth.get_session(None) is None


def test_sessao_em_memoria_expirada_some(monkeypatch):
    token = auth.create_session({"login": "dherrera"})
    store = auth._get_store()
    value, _expires = store._data[f"session:{token}"]
    value["expires_at"] = 0  # já expirou

    assert auth.get_session(token) is None
    assert f"session:{token}" not in store._data


def test_rate_limit_trava_apos_cinco_falhas_e_limpa_no_sucesso():
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth.register_login_failure("10.0.0.1")

    with pytest.raises(auth.RateLimitError):
        auth.check_rate_limit("10.0.0.1")

    auth.register_login_success("10.0.0.1")
    auth.check_rate_limit("10.0.0.1")  # não levanta


def test_rate_limit_libera_depois_do_bloqueio(monkeypatch):
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth.register_login_failure("10.0.0.1")
    store = auth._get_store()
    entry, _expires = store._data["login_fail:10.0.0.1"]
    entry["locked_until"] = time.time() - 1  # o bloqueio venceu (timestamp real, no passado)

    auth.check_rate_limit("10.0.0.1")  # não levanta e reseta a contagem
    assert "login_fail:10.0.0.1" not in store._data


def test_sessao_no_redis_sobrevive_e_ganha_ttl(monkeypatch):
    client = _botar_na_redis(monkeypatch)

    token = auth.create_session({"login": "dherrera", "name": "Diego"})

    assert auth.get_session(token)["name"] == "Diego"
    assert client.ttl(f"session:{token}") > 0

    auth.delete_session(token)
    assert auth.get_session(token) is None


def test_rate_limit_no_redis_trava_e_limpa(monkeypatch):
    client = _botar_na_redis(monkeypatch)

    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth.register_login_failure("10.0.0.2")

    assert client.ttl("login_fail:10.0.0.2") > 0
    with pytest.raises(auth.RateLimitError):
        auth.check_rate_limit("10.0.0.2")

    auth.register_login_success("10.0.0.2")
    auth.check_rate_limit("10.0.0.2")  # não levanta


def test_build_store_redis_exige_url(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(sessions_backend="redis", redis_url=""))
    monkeypatch.setattr(auth, "get_redis_client", lambda: None)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        auth._build_store()


def test_build_store_backend_invalido(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(sessions_backend="arquivo", redis_url=""))

    with pytest.raises(RuntimeError, match="inválido"):
        auth._build_store()


def test_build_store_default_e_memoria(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(sessions_backend="memory", redis_url=""))

    assert isinstance(auth._build_store(), auth._MemoryStore)


def test_build_store_redis_com_url_usa_cliente(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(sessions_backend="redis", redis_url="redis://x"))
    monkeypatch.setattr(auth, "get_redis_client", lambda: client)

    store = auth._build_store()

    assert isinstance(store, auth._RedisStore)
