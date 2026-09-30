"""Cliente Redis compartilhado (sessões em `auth.py`, trava de envio em
`auto_generation/service/send.py`).

Um único cliente por processo, criado na primeira chamada a partir de
`REDIS_URL` (`core.config.Settings`). Sem `REDIS_URL`, devolve `None` e os
consumidores caem no caminho em memória (processo único) — o container de
produção sempre seta as duas variáveis juntas (`SESSIONS_BACKEND=redis`).
"""

from __future__ import annotations

from .config import get_settings

_client = None


def get_redis_client():
    """`redis.Redis` compartilhado ou `None` se `REDIS_URL` não está setada.
    Timeouts curtos de propósito: Redis fora do ar não pode pendurar uma
    requisição HTTP."""
    global _client
    if _client is not None:
        return _client
    url = get_settings().redis_url.strip()
    if not url:
        return None
    import redis

    _client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)
    return _client


def reset_client_for_tests(client=None) -> None:
    global _client
    _client = client
