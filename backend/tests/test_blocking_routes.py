"""Rota `async def` que chama banco/arquivo/Graph de forma bloqueante trava o
event loop inteiro (todas as outras requisições esperam). As rotas abaixo são
`def` comuns — o FastAPI as roda numa thread — ou, quando precisam de `await`
(upload em stream), empurram o trabalho bloqueante pra `run_in_threadpool`."""

from __future__ import annotations

import inspect

BLOCKING = {
    "/generate",
    "/send-report",
    "/parse-db",
    "/parse-db-client",
    "/my-hours",
    "/chat",
    "/translate-activities",
    "/reports",
    "/management/kpis",
    "/health",
}


def _routes():
    from .test_coordinator_access import _all_api_routes

    return _all_api_routes()


def test_blocking_routes_are_not_coroutines():
    found = set()
    for route in _routes():
        if route.path in BLOCKING:
            found.add(route.path)
            assert not inspect.iscoroutinefunction(route.endpoint), f"{route.path} bloqueia o event loop"
    assert found == BLOCKING


def test_parse_upload_runs_blocking_work_in_threadpool():
    from backend.app.api.routers import parsing

    source = inspect.getsource(parsing.parse_endpoint)
    assert "run_in_threadpool" in source
