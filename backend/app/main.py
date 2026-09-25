"""App FastAPI — monta middlewares, inclui os routers de cada domínio (ver
`api/routers/`) e serve o build do frontend. As rotas em si vivem em
`api/routers/*.py`; este arquivo não deve voltar a acumular endpoints — ver CLAUDE.md "Adicionar
rota API"."""
import asyncio
import logging
import math
import os

from dotenv import load_dotenv

# precisa rodar ANTES de qualquer `from .xxx import` — módulos como
# `management.py` leem variável de ambiente (MANAGEMENT_PANEL_LOGINS) direto
# no nível do módulo, na hora do import; chamar load_dotenv() depois desses
# imports (como estava antes) carregava o .env tarde demais e o valor lido
# já tinha caído no fallback, fazendo qualquer edição no .env parecer não
# ter efeito nenhum sem reiniciar o processo (e mesmo reiniciando, continuava
# quebrado por causa da ordem).
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


from . import email_ingest
from .api.dependencies import (  # noqa: F401 — re-exportado: testes fazem `from .main import require_session`
    require_manager,
    require_session,
    require_translate_access,
)
from .api.routers import analytics, analytics_chat, auth, chat, generation, history, my_hours, parsing
from .api.errors import GENERIC_MANAGEMENT_DB_ERROR
from .api.routers import management as management_router
from .services.management_store import ManagementStoreError
from .services.report_persistence import reconcile_orphaned_generations

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
app.include_router(parsing.router)
app.include_router(my_hours.router)
app.include_router(management_router.router)
app.include_router(generation.router)
app.include_router(history.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(analytics_chat.router)


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


async def _poll_emails_loop() -> None:
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
                logging.getLogger(__name__).exception("Falha no ciclo de polling de e-mail")
        await asyncio.sleep(interval)


@app.on_event("startup")
async def _start_email_polling() -> None:
    asyncio.create_task(_poll_emails_loop())


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


_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_DIST_DIR = os.path.join(_FRONTEND_DIR, "dist")
_STATIC_DIR = _DIST_DIR if os.path.isdir(_DIST_DIR) else _FRONTEND_DIR
app.mount("/", NoCacheStaticFiles(directory=_STATIC_DIR, html=True), name="web")
