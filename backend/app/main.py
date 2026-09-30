"""App FastAPI — monta middlewares, inclui os routers de cada domínio (ver
`api/routers/`) e serve o build do frontend. As rotas em si vivem em
`api/routers/*.py`; este arquivo não deve voltar a acumular endpoints — ver CLAUDE.md "Adicionar
rota API"."""

import asyncio
import logging
import math
import os
import time

from dotenv import load_dotenv

# precisa rodar ANTES de qualquer `from .xxx import`: as allowlists de papel
# (`core/authz.py`) leem MANAGEMENT_PANEL_LOGINS/COORDINATOR_LOGINS/
# TRANSLATE_ALLOWED_LOGINS no import do módulo, e `core/config.Settings` lê o
# `.env` na primeira construção — chamar load_dotenv() depois desses imports
# carregava o .env tarde demais e o valor lido já tinha caído no fallback,
# fazendo qualquer edição no .env parecer não ter efeito nenhum sem reiniciar
# o processo (e mesmo reiniciando, continuava quebrado por causa da ordem).
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles


class NoCacheStaticFiles(StaticFiles):
    """Em prod (Vite build) assets com hash ficam em /assets/* e podem ter cache
    longo (immutable); index.html e demais continuam no-store para F5 buscar
    versão atual. Em dev (web/ sem hash) tudo fica no-store como antes."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


from . import projectile_db
from .api.dependencies import (  # noqa: F401 — reexportado: testes fazem `from .main import require_session`
    require_manager,
    require_session,
    require_translate_access,
)
from .api.errors import GENERIC_INTERNAL_ERROR, GENERIC_MANAGEMENT_DB_ERROR
from .api.routers import analytics, analytics_chat, auth, auto_generation, chat, generation, health, history, my_hours, my_reviews, parsing
from .api.routers import management as management_router
from .core.config import get_settings
from .core.logging import capture_exception, configure_logging, get_request_id, sanitize_request_id, set_request_context, set_request_id
from .services.management_store import ManagementStoreError
from .services.report_persistence import reconcile_orphaned_generations

# loops de background vivem em `worker.py`; estes nomes continuam neste módulo
# porque os testes os substituem por versões ociosas (conftest) e os hooks de
# startup abaixo decidem se sobem (PROCESS_ROLE)
from .worker import email_polling_loop as _poll_emails_loop  # noqa: F401
from .worker import jobs_enabled
from .worker import scheduler_loop as _auto_scheduler_loop  # noqa: F401

# logging estruturado + request-id + Sentry (só com SENTRY_DSN setado) antes
# de qualquer coisa que logue — ver `core/logging.py`.
configure_logging()

app = FastAPI(
    title="Automação de Relatório de Horas",
    # Ferramenta interna sem uso legítimo de Swagger UI/ReDoc em operação normal —
    # /docs, /redoc e /openapi.json expunham toda a estrutura de rotas/schema pra
    # qualquer um com acesso de rede, sem exigir login. Desativado incondicionalmente
    # (sem flag dev/prod).
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# Restrito às origens locais de dev/prod deste app — "*" deixava QUALQUER site
# que o usuário visitasse no navegador chamar /parse, /generate e /chat (que usa
# a chave da Anthropic do servidor) e ler a resposta. Em prod (backend servindo
# o build do React na mesma origem) o CORS nem é consultado pelo navegador, mas
# manter a lista explícita evita reabrir esse buraco sem querer no futuro.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8011", "http://127.0.0.1:8011"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(parsing.router)
app.include_router(my_hours.router)
app.include_router(management_router.router)
app.include_router(generation.router)
app.include_router(history.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(analytics_chat.router)
app.include_router(auto_generation.router)
app.include_router(my_reviews.router)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    """Dá um request-id a toda requisição (aceita `X-Request-Id` do cliente
    só se for seguro pra log — ver `core/logging.sanitize_request_id`), marca
    o contexto de log/Sentry e devolve o id no header da resposta. Também é
    aqui que requisição lenta vira aviso (`SLOW_REQUEST_MS`; 0 loga toda
    requisição, negativo desliga)."""
    request_id = sanitize_request_id(request.headers.get("X-Request-Id"))
    set_request_id(request_id)
    set_request_context(request_id)
    request.state.request_id = request_id

    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-Id"] = request_id
        return response
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        threshold = get_settings().slow_request_ms
        # esta linha É o access log do app (o do uvicorn é desligado em
        # core/logging.py justamente pra ter o request-id certo aqui)
        message = f"{request.method} {request.url.path} -> {status} em {elapsed_ms} ms"
        if threshold >= 0 and elapsed_ms >= threshold:
            logging.getLogger(__name__).warning("Requisição lenta: " + message)
        else:
            logging.getLogger(__name__).info(message)


@app.middleware("http")
async def _security_headers_middleware(request: Request, call_next):
    """Cabeçalhos de reforço básicos, sem impacto funcional conhecido: impedem
    o navegador de "sniffar" o Content-Type (mitiga alguns vetores de XSS via
    upload/arquivo servido com tipo errado), bloqueiam a página de ser
    embutida em <iframe> de outra origem (clickjacking na tela de login) e
    evitam vazar a URL completa (que pode incluir dados de sessão/estado) no
    cabeçalho Referer de navegação para fora do app."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.on_event("startup")
async def _start_email_polling() -> None:
    # os loops vivem em `worker.py` (o container `worker` roda só eles);
    # aqui sobem quando PROCESS_ROLE permite — "web" deixa tudo com o worker
    if not jobs_enabled():
        return
    asyncio.create_task(_poll_emails_loop())


_background_tasks: set[asyncio.Task] = set()


@app.on_event("startup")
async def _start_auto_scheduler() -> None:
    """Agendador da rodada mensal da geração automática (`auto_generation/scheduler.py`)
    — a referência fica guardada: o loop só tem uma referência fraca no asyncio e
    o coletor poderia recolhê-lo. Com PROCESS_ROLE=web quem roda é o container
    worker; o UNIQUE da rodada protege se houver mais de um de qualquer forma."""
    if not jobs_enabled():
        return
    task = asyncio.create_task(_auto_scheduler_loop())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@app.on_event("startup")
async def _warm_projectile_pool() -> None:
    """Abre as conexões do Projectile em segundo plano (cada uma leva ~20 s no servidor atual, ver
    `projectile_db.warm_pool`): o boot não espera e o primeiro usuário não paga. Sem
    PROJECTILE_DB_HOST (dev sem banco) ou com `PROJECTILE_DB_WARMUP=false` (testes) não faz nada."""
    if not os.environ.get("PROJECTILE_DB_HOST") or os.environ.get("PROJECTILE_DB_WARMUP", "true").strip().lower() in ("0", "false", "no"):
        return
    asyncio.get_running_loop().run_in_executor(None, projectile_db.warm_pool)


@app.on_event("startup")
async def _reconcile_reports_db_on_boot() -> None:
    """Qualquer `report_generation` deixada em 'started' é órfã de um
    processo anterior que morreu no meio (crash, kill, queda de energia) —
    ver `services/report_persistence.reconcile_orphaned_generations`.
    Fail-open: se o reports_db estiver fora do ar, só loga e o boot segue."""
    await asyncio.to_thread(reconcile_orphaned_generations)


def _sanitize_nonfinite(obj):
    """Troca floats não-finitos (NaN/Infinity) por sua representação em texto. Um
    cliente que manda um JSON não-padrão com esses valores literais (ex: via
    json.dumps do Python, que aceita NaN/Infinity por padrão) faz o Pydantic rejeitar
    o campo — mas o valor rejeitado é ecoado de volta dentro do corpo do erro de
    validação, e o JSONResponse padrão do FastAPI usa allow_nan=False, então
    serializar esse erro levantaria um ValueError próprio, virando um 500 sem
    conteúdo em vez do 422 esperado."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nonfinite(v) for v in obj]
    return obj


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = _sanitize_nonfinite(jsonable_encoder(exc.errors()))
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(ManagementStoreError)
async def _management_store_exception_handler(request: Request, exc: ManagementStoreError):
    """Dados de Gerência/Diagnóstico vivem no reports_db (sem fail-open):
    banco fora do ar vira 502 com mensagem genérica em qualquer rota, sem
    cada uma das rotas de /management/* precisar capturar isso à parte. O
    detalhe (host, erro do driver) só vai pro log."""
    logging.getLogger(__name__).error("Falha no reports_db (dados de gerência)", exc_info=exc)
    return JSONResponse(status_code=502, content={"detail": GENERIC_MANAGEMENT_DB_ERROR})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """Erro não tratado: loga com o request-id da requisição, manda pro
    Sentry (se `SENTRY_DSN` estiver setado) e devolve um 500 JSON genérico
    com o mesmo request-id no header — o detalhe real fica só no log."""
    logging.getLogger(__name__).exception("Erro não tratado: %s %s", request.method, request.url.path)
    capture_exception(exc)
    response = JSONResponse(status_code=500, content={"detail": GENERIC_INTERNAL_ERROR})
    response.headers["X-Request-Id"] = getattr(request.state, "request_id", None) or get_request_id()
    return response


_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_DIST_DIR = os.path.join(_FRONTEND_DIR, "dist")
_STATIC_DIR = _DIST_DIR if os.path.isdir(_DIST_DIR) else _FRONTEND_DIR
app.mount("/", NoCacheStaticFiles(directory=_STATIC_DIR, html=True), name="web")
