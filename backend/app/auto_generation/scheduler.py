"""Agendador da rodada mensal da geração automática (fase 4).

No dia e na hora escolhidos (padrão: dia 1, 06:00, America/Sao_Paulo) gera os
rascunhos do MÊS QUE FECHOU — e os pedidos da geração personalizada, que
`service._execute_run` já leva junto. Só gera rascunhos; nunca envia nada.

A decisão é uma função PURA (`decide`), testada sem relógio nem banco. O loop
(`loop`/`tick`) só lê o estado, pergunta a ela e chama `service.start_run`, que
já é idempotente e seguro entre processos (`auto_runs.competence` UNIQUE +
`SELECT … FOR UPDATE`): dois processos ou dois ticks nunca geram duas vezes.

**Recuperação:** passou do horário e o servidor estava desligado → dispara assim
que ele voltar. O alvo é sempre o mês ANTERIOR ao de agora, então um mês
perdido não roda sozinho depois que o seguinte começa (o botão continua lá).
**Sem martelar:** uma tentativa por hora e no máximo 5 por competência (o Projectile
fora do ar não vira um loop de rodadas falhas)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..core.config import get_settings
from ..services import auto_generation_store as store
from ..services.audit import record_event
from . import builder, rules, service

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Sao_Paulo")
POLL_SECONDS = 300
RETRY_AFTER = timedelta(minutes=60)
MAX_ATTEMPTS = 5
SYSTEM_ACTOR = {"login": "sistema", "name": "Agendador"}

# heartbeat do loop pro /health/details: None = o loop nunca acordou neste
# processo (acabou de subir, ou o startup não rodou).
_last_tick_at: datetime | None = None


def last_tick_at() -> datetime | None:
    """Quando o loop acordou pela última vez (UTC, com tzinfo). Não confundir
    com `scheduler_state.last_attempt_at`: aquele só existe quando uma rodada
    chegou a ser TENTADA; este prova que o loop está vivo mesmo em mês sem
    nada pra gerar."""
    return _last_tick_at


@dataclass(frozen=True)
class Decision:
    competence: str
    # "sem_rodada" | "rodada_falhou" | "pedidos_pendentes"
    reason: str


def previous_competence(now_local: datetime) -> str:
    year, month = (now_local.year, now_local.month - 1) if now_local.month > 1 else (now_local.year - 1, 12)
    return f"{year:04d}-{month:02d}"


def _settings(config: dict | None) -> tuple[bool, int, int, int]:
    effective = rules.effective(config, None)
    hour, minute = (int(part) for part in effective["schedule_time"].split(":"))
    return bool(effective["schedule_enabled"]), int(effective["schedule_day"]), hour, minute


def due_at(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TIMEZONE)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(tzinfo=None)


def decide(now_local: datetime, config: dict | None, run: dict | None, pending: list[dict], state: dict | None) -> Decision | None:
    """Deve rodar agora? `run` = rodada da competência-alvo (ou None),
    `pending` = os pedidos personalizados dela, `state` = tentativas já feitas
    (`{competence, attempts, last_attempt_at}`)."""
    enabled, day, hour, minute = _settings(config)
    if not enabled:
        return None
    if now_local < due_at(now_local.year, now_local.month, day, hour, minute):
        return None
    target = previous_competence(now_local)
    now = _naive_utc(now_local)
    running = bool(run and run["status"] == "running")
    if running and now - run["started_at"] < service._STALE_RUN:
        return None  # rodando de verdade (esse ou outro processo)
    if state and state.get("competence") == target:
        if int(state.get("attempts") or 0) >= MAX_ATTEMPTS:
            return None
        last = state.get("last_attempt_at")
        if last and now - datetime.fromisoformat(last) < RETRY_AFTER:
            return None
    if run is None:
        return Decision(target, "sem_rodada")
    if run["status"] == "failed" or running:  # `running` aqui = rodada morta (processo caiu)
        return Decision(target, "rodada_falhou")
    if any(r.get("status") == "agendado" for r in pending):
        return Decision(target, "pedidos_pendentes")
    return None


def tick(now: datetime | None = None) -> Decision | None:
    """Um ciclo: lê o estado, decide e, se for o caso, roda a rodada do mês
    que fechou (síncrono — quem chama é o loop, numa thread)."""
    now_local = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    target = previous_competence(now_local)
    config = store.get_config()
    decision = decide(now_local, config, store.get_run(target), store.get_custom_requests().get(target, []), store.get_scheduler_state())
    if decision is None:
        return None
    state = store.get_scheduler_state()
    attempts = (int(state.get("attempts") or 0) if state.get("competence") == target else 0) + 1
    with store.write_session() as s:
        s.set_scheduler_state({"competence": target, "attempts": attempts, "last_attempt_at": _naive_utc(now_local).isoformat()})
    logger.info("Agendador: rodando %s (%s, tentativa %d)", target, decision.reason, attempts)
    record_event(
        actor_id=SYSTEM_ACTOR["login"],
        actor_name=SYSTEM_ACTOR["name"],
        action="auto_run_scheduled",
        entity_type="auto_run",
        entity_id=target,
        source="auto_generation",
        metadata={"competence": target, "reason": decision.reason, "attempt": attempts},
    )
    try:
        service.start_run(target, SYSTEM_ACTOR, background=False)
    except service.RunInProgress:
        logger.info("Agendador: %s já está rodando em outro lugar", target)
    return decision


async def loop() -> None:
    """Acorda a cada 5 min. Erro de um ciclo (banco/Projectile fora do ar) é
    logado e o próximo tenta de novo, respeitando o intervalo entre tentativas."""
    global _last_tick_at
    while True:
        if get_settings().auto_generation_enabled:
            try:
                await asyncio.to_thread(tick)
            except Exception:  # noqa: BLE001 — o agendador nunca pode morrer por um ciclo ruim
                logger.exception("Falha no ciclo do agendador da geração automática")
        _last_tick_at = datetime.now(UTC)
        await asyncio.sleep(POLL_SECONDS)


def schedule_info(now: datetime | None = None) -> dict:
    """O que a tela mostra: ligado?, dia/hora, a próxima geração e o mês que
    ela vai gerar, e a rodada do mês que acabou de fechar."""
    now_local = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    config = store.get_config()
    enabled, day, hour, minute = _settings(config)
    this_month = due_at(now_local.year, now_local.month, day, hour, minute)
    if now_local < this_month:
        next_at = this_month
    else:
        year, month = (now_local.year, now_local.month + 1) if now_local.month < 12 else (now_local.year + 1, 1)
        next_at = due_at(year, month, day, hour, minute)
    target = previous_competence(next_at)
    last_target = previous_competence(now_local)
    return {
        "enabled": enabled,
        "day": day,
        "time": f"{hour:02d}:{minute:02d}",
        "timezone": "America/Sao_Paulo",
        "next_at": next_at.isoformat(),
        "target": target,
        "target_label": builder.month_label(target),
        "last_run": service._public_run(store.get_run(last_target)),
    }
