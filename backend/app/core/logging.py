"""Logging estruturado, request-id e Sentry (GlitchTip) — ver README
"Observabilidade (logs e erros)".

`configure_logging()` roda uma vez no import de `main.py`, logo depois do
`load_dotenv()`:

- unifica o formato dos logs (inclusive os do uvicorn, que instala handlers
  próprios ANTES de importar o app) e inclui o request-id em cada linha;
- em `LOG_FORMAT=json`, uma linha = um JSON (pra coletor de log);
- inicializa o Sentry só quando `SENTRY_DSN` existe (o GlitchTip
  self-hosted usa o mesmo protocolo); sem DSN, nada é enviado e nada muda.

O request-id chega pelo header `X-Request-Id` (aceito só se for seguro pra
log — qualquer coisa estranha vira um id novo) ou é gerado por requisição, e
volta no header da resposta. Nenhum token/senha passa por aqui."""

from __future__ import annotations

import json
import logging
import re
import secrets
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from .config import get_settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# aceita só id simples e curto: um header com quebra de linha/enorme viraria
# poluição (ou forja) de log; qualquer coisa fora disso gera id novo.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_TEXT_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"

_configured = False
_sentry_enabled = False


def new_request_id() -> str:
    return secrets.token_hex(8)


def sanitize_request_id(raw: str | None) -> str:
    if raw and _REQUEST_ID_RE.match(raw):
        return raw
    return new_request_id()


def set_request_id(request_id: str) -> None:
    # Sem reset de propósito: cada requisição roda no próprio task do asyncio,
    # e o handler global de erro (ServerErrorMiddleware, o mais externo) roda
    # DEPOIS deste middleware — o id precisa continuar visível lá.
    request_id_var.set(request_id)


def get_request_id() -> str:
    return request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Uma linha = um JSON; o traceback vai como texto no campo `exception`
    (o objeto de exceção não serializa)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_sentry() -> None:
    global _sentry_enabled
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    # import tardio: a dependência é do requirements.txt, mas o app não pode
    # quebrar se ela faltar (e o mypy não precisa tipar módulo-ou-None).
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or None,
        # sem tracing de performance: o valor aqui é o erro com contexto,
        # não amostragem de latência (que o painel de Saúde vai mostrar)
        traces_sample_rate=0.0,
        # ferramenta interna com dado de pessoa: nunca manda PII por padrão
        send_default_pii=False,
    )
    _sentry_enabled = True


def set_request_context(request_id: str) -> None:
    """Marca o request-id no evento do Sentry (se ligado), pra cruzar
    erro × log × resposta do cliente."""
    if not _sentry_enabled:
        return
    import sentry_sdk

    sentry_sdk.set_tag("request_id", request_id)


def capture_exception(exc: BaseException) -> None:
    if not _sentry_enabled:
        return
    import sentry_sdk

    sentry_sdk.capture_exception(exc)


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    fmt = get_settings().log_format.strip().lower()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(_TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # o uvicorn.error propaga pro root (startup/shutdown no formato daqui);
    # o ACCESS log do uvicorn é desligado de propósito: ele é emitido fora do
    # contexto da requisição e sairia com request_id vazio — o middleware em
    # main.py loga cada requisição com o id certo.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False

    configure_sentry()
