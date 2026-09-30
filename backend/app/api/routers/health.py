"""Saúde do sistema — `/health` (público) e `/health/details` (só gerente).

`/health` é pro monitor externo (Uptime Kuma etc.): responde 200/503 e o
corpo só tem `{"status": "ok"|"degraded"}` — sem topologia, versão ou
detalhe de erro, porque a rota é aberta de propósito (o monitor não faz
login). Cobre só as dependências que derrubam o uso normal: `reports_db`
(Gerência/Diagnóstico/Histórico) e o Projectile (login e busca de horas).

`/health/details` é pra investigação: check por check, com latência, motivo
e o heartbeat do agendador da geração automática. Erro de um check nunca
derruba o endpoint — vira `"ok": false` naquele item."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ... import projectile_db
from ...auto_generation import scheduler
from ...core.config import get_settings
from ...db.reports_db import get_engine
from ..dependencies import require_manager

router = APIRouter()


def _run_check(check) -> dict:
    """Roda um check e devolve `{ok, latency_ms[, error]}` — nunca levanta."""
    started = time.perf_counter()
    try:
        check()
        return {"ok": True, "latency_ms": max(0, int((time.perf_counter() - started) * 1000))}
    except Exception as exc:  # noqa: BLE001 — saúde de um item não derruba o endpoint
        return {"ok": False, "latency_ms": max(0, int((time.perf_counter() - started) * 1000)), "error": type(exc).__name__}


def check_reports_db() -> dict:
    """SELECT 1 no reports_db (o engine já tem `connect_timeout=3`)."""

    def _ping() -> None:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))

    return _run_check(_ping)


def check_projectile() -> dict:
    """SELECT 1 numa conexão emprestada do pool do Projectile."""
    return _run_check(projectile_db.ping)


def check_scheduler() -> dict:
    """Loop do agendador vivo? Se `AUTO_GENERATION_ENABLED=false`, estar
    parado é deliberado (`ok: true`); senão, um heartbeat com mais de 3
    ciclos de idade indica loop morto."""
    settings = get_settings()
    enabled = settings.auto_generation_enabled
    last = scheduler.last_tick_at()
    result = {"ok": True, "enabled": enabled, "last_tick_at": last.isoformat() if last else None}
    if enabled:
        result["ok"] = last is not None and (datetime.now(UTC) - last) < timedelta(seconds=scheduler.POLL_SECONDS * 3)
    return result


@router.get("/health")
def health_endpoint():
    """Liveness + dependências críticas, sem detalhe (endpoint público)."""
    checks = [check_reports_db(), check_projectile()]
    healthy = all(check["ok"] for check in checks)
    return JSONResponse(status_code=200 if healthy else 503, content={"status": "ok" if healthy else "degraded"})


@router.get("/health/details")
def health_details_endpoint(_user: dict = Depends(require_manager)) -> dict:
    """Check por check, com latência e motivo — só gerente (mostra a
    topologia interna: nome dos bancos e estado do agendador)."""
    checks = {"reports_db": check_reports_db(), "projectile": check_projectile(), "scheduler": check_scheduler()}
    healthy = all(check["ok"] for check in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}
