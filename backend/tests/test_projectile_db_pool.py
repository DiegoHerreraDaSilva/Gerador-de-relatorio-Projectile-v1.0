"""Testes do pool de conexões do Projectile (Fase 6 do
GUIA_EVOLUCAO_GERADOR_PROJECTILE.md). Usam um stub de conexão em vez do
MySQL real — o objetivo aqui é travar a MECÂNICA de empréstimo/devolução
(`_borrowed_connection`), não repetir cobertura de query (isso já está em
test_projectile_db_group_hours.py). Validação end-to-end contra um MySQL de
verdade (reuso de conexão, fila sob concorrência, reconexão após queda) foi
feita manualmente contra o container `reports-mysql` antes deste commit —
ver notas do commit da Fase 6."""
from __future__ import annotations

import threading

import pytest

from backend.app import projectile_db


class _FakeConn:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return _FakeCursor()

    def close(self):
        self.closed = True


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


def test_borrowed_connection_sem_conn_pega_do_pool_e_devolve_ao_sair(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr(projectile_db, "_get_connection", lambda: fake)

    with projectile_db._borrowed_connection() as conn:
        assert conn is fake
        assert not fake.closed
    assert fake.closed


def test_borrowed_connection_com_conn_explicita_nao_devolve(monkeypatch):
    """Quem passou `conn` é dono dela (ex: `management.compute_monthly_kpis`
    reaproveitando entre várias chamadas do mesmo request) — a função
    chamada não pode devolvê-la ao pool no meio do caminho."""
    fake = _FakeConn()

    with projectile_db._borrowed_connection(fake) as conn:
        assert conn is fake
    assert not fake.closed


def test_borrowed_connection_devolve_mesmo_quando_a_query_falha(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr(projectile_db, "_get_connection", lambda: fake)

    with pytest.raises(ValueError):
        with projectile_db._borrowed_connection():
            raise ValueError("falha simulada durante a query")
    assert fake.closed


def test_get_connection_propaga_erro_de_conexao_como_projectile_db_error(monkeypatch):
    import pymysql

    class _FakePool:
        def connection(self):
            raise pymysql.MySQLError("conexão recusada")

    monkeypatch.setattr(projectile_db, "_get_pool", lambda: _FakePool())

    with pytest.raises(projectile_db.ProjectileDbError):
        projectile_db._get_connection()


def test_get_pool_usa_tamanho_configurado_em_settings(monkeypatch):
    captured = {}

    class _FakePooledDB:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(projectile_db, "_pool", None)
    monkeypatch.setattr(projectile_db, "PooledDB", _FakePooledDB)
    monkeypatch.setattr(
        projectile_db, "_connection_kwargs",
        lambda: {"host": "h", "user": "u", "password": "p", "database": "d", "port": 3306},
    )
    monkeypatch.setattr(
        projectile_db, "get_settings",
        lambda: type("S", (), {"projectile_sys_client_id": "0", "projectile_db_pool_size": 7})(),
    )

    projectile_db._get_pool()

    assert captured["maxconnections"] == 7
    assert captured["maxcached"] == 7
    assert captured["blocking"] is True
    assert captured["ping"] == 1


def test_get_pool_e_thread_safe_na_inicializacao(monkeypatch):
    """Várias threads chamando `_get_pool()` ao mesmo tempo (ex: request
    normal + polling de e-mail em background) devem enxergar a MESMA
    instância — sem isso, duas chamadas concorrentes na primeira inicialização
    poderiam criar dois pools distintos."""
    monkeypatch.setattr(projectile_db, "_pool", None)

    build_calls = []

    class _FakePooledDB:
        def __init__(self, **kwargs):
            build_calls.append(1)

    monkeypatch.setattr(projectile_db, "PooledDB", _FakePooledDB)
    monkeypatch.setattr(
        projectile_db, "_connection_kwargs",
        lambda: {"host": "h", "user": "u", "password": "p", "database": "d", "port": 3306},
    )
    monkeypatch.setattr(
        projectile_db, "get_settings",
        lambda: type("S", (), {"projectile_sys_client_id": "0", "projectile_db_pool_size": 5})(),
    )

    results = []

    def worker():
        results.append(projectile_db._get_pool())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(build_calls) == 1
    assert len({id(r) for r in results}) == 1
