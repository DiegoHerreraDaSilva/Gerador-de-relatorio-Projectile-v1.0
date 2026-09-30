"""Aquecimento do pool do Projectile: o servidor segura ~20 s em toda conexão NOVA, então as conexões
são abertas em paralelo em segundo plano no boot. Sem rede: a conexão é simulada."""

from __future__ import annotations

import threading
import time

from backend.app import projectile_db


class _FakeConn:
    def __init__(self, log):
        self.log = log
        self.closed = False

    def close(self):
        self.closed = True
        self.log["returned"] += 1


def _install(monkeypatch, delay=0.05, fail=False):
    log = {"concurrent": 0, "max": 0, "opened": 0, "returned": 0}
    lock = threading.Lock()

    def fake_get_connection():
        if fail:
            raise projectile_db.ProjectileDbError("fora do ar")
        with lock:
            log["concurrent"] += 1
            log["max"] = max(log["max"], log["concurrent"])
        time.sleep(delay)  # o handshake lento
        with lock:
            log["concurrent"] -= 1
            log["opened"] += 1
        return _FakeConn(log)

    monkeypatch.setattr(projectile_db, "_get_connection", fake_get_connection)
    return log


def test_abre_as_conexoes_ao_mesmo_tempo_e_devolve_todas(monkeypatch):
    log = _install(monkeypatch)
    opened = projectile_db.warm_pool(3)
    assert opened == 3 and log["opened"] == 3
    assert log["max"] == 3, "precisa abrir em paralelo: em série seriam 3 × 20 s"
    assert log["returned"] == 3


def test_respeita_o_tamanho_do_pool(monkeypatch):
    monkeypatch.setattr(projectile_db, "get_settings", lambda: type("S", (), {"projectile_db_pool_size": 2})())
    log = _install(monkeypatch)
    assert projectile_db.warm_pool(10) == 2 and log["opened"] == 2


def test_banco_fora_do_ar_nao_levanta(monkeypatch):
    _install(monkeypatch, fail=True)
    assert projectile_db.warm_pool(3) == 0


def test_o_boot_nao_espera_nem_aquece_sem_host(monkeypatch):
    """Sem PROJECTILE_DB_HOST o hook não faz nada; com ele, dispara em segundo plano."""
    import asyncio

    from backend.app import main

    calls = []
    monkeypatch.setattr(main.projectile_db, "warm_pool", lambda: calls.append(1))
    monkeypatch.delenv("PROJECTILE_DB_HOST", raising=False)
    asyncio.run(main._warm_projectile_pool())
    assert calls == []

    monkeypatch.setenv("PROJECTILE_DB_HOST", "x")
    monkeypatch.setenv("PROJECTILE_DB_WARMUP", "false")
    asyncio.run(main._warm_projectile_pool())
    assert calls == []  # desligado por variável

    monkeypatch.setenv("PROJECTILE_DB_WARMUP", "true")

    async def run():
        await main._warm_projectile_pool()
        await asyncio.sleep(0.1)  # o executor roda fora do loop

    asyncio.run(run())
    assert calls == [1]
