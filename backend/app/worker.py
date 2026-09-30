"""Processo de background da topologia de containers (`docker-compose.prod.yml`).

Roda os dois loops que antes viviam só no processo web:
- polling de e-mail (`email_ingest.process_new_emails`);
- agendador da rodada mensal da geração automática (`scheduler.loop`).

`PROCESS_ROLE` decide quem roda o quê (ver `main.py`): `all` = HTTP +
background no mesmo processo (padrão, NSSM de sempre), `web` = só HTTP,
`worker` = só estes loops. O container `worker` roda
`python -m backend.app.worker`.
"""

from __future__ import annotations

import asyncio
import logging
import os

from . import email_ingest
from .auto_generation import scheduler
from .core.config import get_settings
from .core.logging import configure_logging

logger = logging.getLogger(__name__)

_VALID_ROLES = ("all", "web", "worker")


def process_role() -> str:
    role = get_settings().process_role.strip().lower()
    if role not in _VALID_ROLES:
        raise RuntimeError(f"PROCESS_ROLE inválido: {role!r} (use {' ou '.join(_VALID_ROLES)}).")
    return role


def jobs_enabled() -> bool:
    """O processo atual deve subir os loops de background?"""
    return process_role() in ("all", "worker")


async def email_polling_loop() -> None:
    """Ciclo de polling da automação de e-mail (ver `email_ingest.py`) — só
    roda se as variáveis `AZURE_*`/`GRAPH_MAILBOX`/`ALBERTO_EMAIL` estiverem
    configuradas no `.env`; sem elas, fica ocioso (não impede o resto do app
    de funcionar). Idempotência por `message_id` (ver
    `management.is_message_processed`) torna reinícios do `--reload` no meio
    de um ciclo inofensivos — na pior hipótese uma mensagem é buscada de novo
    e descartada por já estar processada."""
    interval = int(os.environ.get("EMAIL_POLL_INTERVAL_SECONDS", "30"))
    while True:
        if os.environ.get("AZURE_CLIENT_ID"):
            try:
                await asyncio.to_thread(email_ingest.process_new_emails)
            except Exception:
                logger.exception("Falha no ciclo de polling de e-mail")
        await asyncio.sleep(interval)


async def scheduler_loop() -> None:
    await scheduler.loop()


async def _run_loops() -> None:
    await asyncio.gather(asyncio.create_task(email_polling_loop()), asyncio.create_task(scheduler_loop()))


def run() -> None:
    """Entrypoint do processo worker (container): valida o papel e roda os
    loops pra sempre."""
    configure_logging()
    if process_role() == "web":
        raise RuntimeError("PROCESS_ROLE=web não roda o worker — use o serviço web.")
    asyncio.run(_run_loops())


if __name__ == "__main__":
    run()
