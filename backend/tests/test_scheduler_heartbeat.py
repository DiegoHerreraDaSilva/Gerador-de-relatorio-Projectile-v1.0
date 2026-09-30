"""Heartbeat do agendador entre processos: no Docker o loop roda no `worker` e o /health/details no `web`,
então a prova de vida vai pro Redis (sem Redis, a variável local de sempre)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import fakeredis
import pytest

from backend.app import worker
from backend.app.auto_generation import scheduler
from backend.app.core import config


@pytest.fixture
def redis_shared(monkeypatch):
    """Um Redis compartilhado entre 'processos' (o fake é um só); o estado local é zerado pra simular o web."""
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(scheduler, "get_redis_client", lambda: client)
    monkeypatch.setattr(scheduler, "_last_tick_at", None)
    return client


def _enabled(monkeypatch, enabled=True):
    monkeypatch.setattr(scheduler, "get_settings", lambda: SimpleNamespace(auto_generation_enabled=enabled))


def test_o_web_enxerga_o_heartbeat_gravado_pelo_worker(redis_shared, monkeypatch):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    scheduler.record_tick(now)  # o worker acorda e grava
    monkeypatch.setattr(scheduler, "_last_tick_at", None)  # o web nunca rodou o loop
    assert scheduler.last_tick_at() == now


def test_sem_redis_vale_a_variavel_local(monkeypatch):
    monkeypatch.setattr(scheduler, "get_redis_client", lambda: None)
    monkeypatch.setattr(scheduler, "_last_tick_at", None)
    assert scheduler.last_tick_at() is None
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    scheduler.record_tick(now)
    assert scheduler.last_tick_at() == now


def test_vale_o_mais_recente_entre_o_local_e_o_do_redis(redis_shared):
    old = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    new = old + timedelta(minutes=5)
    redis_shared.set(scheduler.HEARTBEAT_KEY, new.isoformat())
    scheduler._last_tick_at = old
    assert scheduler.last_tick_at() == new


def test_redis_fora_do_ar_nao_derruba_o_agendador(monkeypatch):
    def broken():
        raise ConnectionError("redis caiu")

    monkeypatch.setattr(scheduler, "get_redis_client", broken)
    monkeypatch.setattr(scheduler, "_last_tick_at", None)
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    scheduler.record_tick(now)  # não levanta
    assert scheduler.last_tick_at() == now  # cai no local


def test_heartbeat_fresco_velho_e_desligado(redis_shared, monkeypatch):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    _enabled(monkeypatch)
    assert scheduler.heartbeat_is_fresh(now) is False  # nunca acordou
    scheduler.record_tick(now - timedelta(minutes=2))
    assert scheduler.heartbeat_is_fresh(now) is True
    scheduler.record_tick(now - timedelta(minutes=16))  # mais de 3 ciclos de 5 min
    assert scheduler.heartbeat_is_fresh(now) is False
    _enabled(monkeypatch, enabled=False)
    assert scheduler.heartbeat_is_fresh(now) is True  # parado de propósito não é falha


def test_worker_check_sai_com_0_ou_1(redis_shared, monkeypatch):
    _enabled(monkeypatch)
    assert worker.check() == 1
    scheduler.record_tick()
    assert worker.check() == 0


def test_worker_run_com_check_nao_sobe_os_loops(redis_shared, monkeypatch):
    _enabled(monkeypatch)
    scheduler.record_tick()
    monkeypatch.setattr(sys, "argv", ["worker", "--check"])
    with pytest.raises(SystemExit) as exit_info:
        worker.run()
    assert exit_info.value.code == 0


def test_compose_de_producao_monta_os_artefatos_e_testa_o_worker():
    import pathlib

    text = (pathlib.Path(config.__file__).resolve().parents[3] / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert text.count("backend_data:/app/backend/data") == 2, "web e worker compartilham o mesmo volume"
    assert "backend_data:\n" in text
    assert "backend.app.worker\", \"--check\"" in text
