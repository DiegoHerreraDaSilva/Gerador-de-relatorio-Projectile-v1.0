"""Mensagens genéricas e helper de erro compartilhados entre routers —
extraído de `main.py` na Fase 5 (GUIA_EVOLUCAO_GERADOR_PROJECTILE.md)."""
from __future__ import annotations

import logging

from fastapi import HTTPException

# mensagens genéricas pra falha de infra (banco fora do ar, credencial errada no
# .env, timeout de rede, Graph indisponível) devolvidas pro cliente — o detalhe real
# (que pode incluir host/porta/erro do driver MySQL, ou resposta de erro do Graph)
# só vai pro log do servidor, nunca na resposta HTTP, pra não vazar detalhe de infra
# pra quem está chamando a API (inclusive antes de logar).
GENERIC_DB_ERROR = "Erro ao conectar no banco do Projectile. Tente de novo em instantes."
GENERIC_EMAIL_ERROR = "Erro ao enviar/consultar e-mail pelo Microsoft Graph. Tente de novo em instantes."
GENERIC_REPORTS_DB_ERROR = "Erro ao consultar o histórico de relatórios. Tente de novo em instantes."


def log_and_generic_error(e: Exception, status_code: int = 502, generic_message: str | None = None) -> HTTPException:
    """`generic_message` default é o de banco (`GENERIC_DB_ERROR`) — a maioria
    dos call sites é `ProjectileDbError`. Chamadas envolvendo `EmailIngestError`
    (Graph) passam `GENERIC_EMAIL_ERROR` explicitamente, senão a mensagem
    devolvida falava em "banco do Projectile" pra uma falha que não tinha nada
    a ver com banco — confuso pra quem está tentando entender o erro real."""
    logging.exception("Falha ao processar requisição")
    return HTTPException(status_code, generic_message or GENERIC_DB_ERROR)
