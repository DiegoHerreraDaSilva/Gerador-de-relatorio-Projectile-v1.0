import asyncio
import html
import io
import logging
import math
import os
import re
import tempfile
import uuid
import zipfile
from datetime import date, timedelta
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask


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

from dotenv import load_dotenv

import calendar

from .auth import (
    LoginError,
    RateLimitError,
    check_rate_limit,
    create_session,
    delete_session,
    get_session,
    register_login_failure,
    register_login_success,
    verify_projectile_login,
)
from .chat_ops import OperationError, apply_operations
from .chatbot import ChatConfigError, ChatUpstreamError, call_chat
from .generator import (
    ActivityInput,
    GroupInput,
    NonFiniteValueError,
    ReportHeader,
    business_days_between,
    count_business_days,
    national_holidays_between,
    parse_month_label,
    generate_report,
)
from .hours_analytics import (
    daily_stats,
    day_matched_comparison,
    expected_hours_for_days,
    format_hhmm,
    gap_days,
    monthly_series,
    outlier_days,
    parse_hhmm,
    resolve_reference,
)
from .pdf_generator import generate_report_pdf
from . import email_ingest
from .management import (
    MANAGEMENT_PANEL_LOGINS,
    compute_monthly_kpis,
    create_manual_project_kpi_sample,
    delete_project_kpi_sample,
    list_samples,
    set_manual_entry,
    update_project_kpi_sample,
)
from .parser import parse_projectile_export
from .projectile_db import (
    ProjectileDbError,
    fetch_all_projects_with_details,
    fetch_clients_for_projects,
    fetch_daily_hours_totals,
    fetch_employee_contracts,
    fetch_employee_hours,
    fetch_my_hours,
    fetch_project_codes,
    fetch_project_details,
    fetch_project_hours,
    fetch_project_ids_for_clients,
    fetch_project_ids_with_hours,
    group_hours,
    group_hours_by_project,
)

load_dotenv()

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

OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "relatorio_horas_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SESSION_COOKIE = "session_token"

# mensagens genéricas pra falha de infra (banco fora do ar, credencial errada no
# .env, timeout de rede, Graph indisponível) devolvidas pro cliente — o detalhe real
# (que pode incluir host/porta/erro do driver MySQL, ou resposta de erro do Graph)
# só vai pro log do servidor, nunca na resposta HTTP, pra não vazar detalhe de infra
# pra quem está chamando a API (inclusive antes de logar).
_GENERIC_DB_ERROR = "Erro ao conectar no banco do Projectile. Tente de novo em instantes."
_GENERIC_EMAIL_ERROR = "Erro ao enviar/consultar e-mail pelo Microsoft Graph. Tente de novo em instantes."


def _log_and_generic_error(e: Exception, status_code: int = 502, generic_message: str | None = None) -> HTTPException:
    """`generic_message` default é o de banco (`_GENERIC_DB_ERROR`) — a maioria
    dos call sites é `ProjectileDbError`. Chamadas envolvendo `EmailIngestError`
    (Graph) passam `_GENERIC_EMAIL_ERROR` explicitamente, senão a mensagem
    devolvida falava em "banco do Projectile" pra uma falha que não tinha nada
    a ver com banco — confuso pra quem está tentando entender o erro real."""
    logging.exception("Falha ao processar requisição")
    return HTTPException(status_code, generic_message or _GENERIC_DB_ERROR)


def require_session(request: Request) -> dict:
    """Dependência do FastAPI que barra a rota com 401 se não houver sessão
    válida — sem isso, as rotas que tocam dado sensível (Projectile, geração
    de relatório, IA) ficariam acessíveis por qualquer um com acesso de rede
    ao backend, mesmo sem logar (a tela de login só bloqueia no navegador)."""
    session = get_session(request.cookies.get(SESSION_COOKIE))
    if not session:
        raise HTTPException(401, "Sessão expirada ou inválida. Faça login de novo.")
    return session


def require_manager(_user: dict = Depends(require_session)) -> dict:
    """Barra com 403 quem não é gerente — o painel de gerência mostra dados
    de TODOS os engenheiros, não só do usuário logado, então precisa de um
    controle de acesso além da sessão comum."""
    if _user["login"] not in MANAGEMENT_PANEL_LOGINS:
        raise HTTPException(403, "Sem acesso ao painel de gerência.")
    return _user


class LoginRequest(BaseModel):
    login: str
    password: str


@app.post("/auth/login")
async def login_endpoint(payload: LoginRequest, request: Request, response: Response):
    client_key = request.client.host if request.client else "unknown"

    try:
        check_rate_limit(client_key)
    except RateLimitError as e:
        raise HTTPException(429, str(e))

    try:
        user = verify_projectile_login(payload.login.strip(), payload.password)
    except LoginError as e:
        register_login_failure(client_key)
        raise HTTPException(401, str(e))
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)

    register_login_success(client_key)
    token = create_session(user)
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax", max_age=8 * 60 * 60,
        # secure=True automaticamente quando servido via HTTPS — hoje é HTTP puro
        # (rede interna), então isso já fica pronto pro dia que rodar atrás de TLS.
        secure=(request.url.scheme == "https"),
    )
    return {
        "name": user["name"], "login": user["login"], "email": user["email"],
        "is_manager": user["login"] in MANAGEMENT_PANEL_LOGINS,
    }


@app.get("/auth/me")
async def me_endpoint(request: Request):
    session = get_session(request.cookies.get(SESSION_COOKIE))
    if not session:
        raise HTTPException(401, "Não autenticado.")
    return {
        "name": session["name"], "login": session["login"], "email": session["email"],
        "is_manager": session["login"] in MANAGEMENT_PANEL_LOGINS,
    }


@app.post("/auth/logout")
async def logout_endpoint(request: Request, response: Response):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
_MAX_UNCOMPRESSED_XLSX_BYTES = 200 * 1024 * 1024  # 200 MB


def _reject_if_oversized_xlsx(content: bytes) -> None:
    """Duas camadas de defesa pro upload de /parse: (1) tamanho do próprio
    upload e (2) tamanho DESCOMPRIMIDO do conteúdo do zip (.xlsx é um ZIP) —
    um "zip bomb" pode pesar poucos KB no disco e ainda assim descomprimir pra
    gigabytes, derrubando o servidor quando openpyxl carrega o workbook. Zip
    inválido não é rejeitado aqui: deixa o erro de "arquivo inválido" existente
    de parse_projectile_export tratar. Duplicado de propósito em
    email_ingest.py pro anexo de e-mail (ponto de entrada diferente, bytes já
    vêm decodificados de base64 lá) — ver CLAUDE.md."""
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Arquivo muito grande. O limite é 25 MB.")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
    except zipfile.BadZipFile:
        return

    if total_uncompressed > _MAX_UNCOMPRESSED_XLSX_BYTES:
        raise HTTPException(413, "Arquivo .xlsx com conteúdo descomprimido excessivo — recusado por segurança.")


@app.post("/parse")
async def parse_endpoint(
    file: UploadFile = File(...),
    mode: Literal["single", "multi"] = Form("single"),
    _user: dict = Depends(require_session),
):
    content = await file.read()
    _reject_if_oversized_xlsx(content)

    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        packages, issues = parse_projectile_export(tmp_path, split_by_package=(mode == "multi"))
    except zipfile.BadZipFile:
        raise HTTPException(400, "O arquivo enviado não é um .xlsx válido.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(400, f"Planilha inválida: não encontrei a coluna {e}.")
    finally:
        os.remove(tmp_path)

    return _build_parse_response(packages, issues)


def _build_parse_response(packages, issues) -> dict:
    return {
        "packages": [
            {
                "key": pkg.key,
                "project_name": pkg.project_name,
                "groups": [
                    {
                        "name": g.name,
                        "total_hours": g.total_hours,
                        "activities": [{"description": a.description, "hours": a.hours} for a in g.activities],
                    }
                    for g in pkg.groups
                ],
            }
            for pkg in packages
        ],
        "issues": [{"row": i.row, "reason": i.reason, "message": i.message} for i in issues],
    }


class ParseDbRequest(BaseModel):
    month_label: str
    mode: Literal["single", "multi"] = "single"


@app.post("/parse-db")
async def parse_db_endpoint(payload: ParseDbRequest, _user: dict = Depends(require_session)):
    # busca sempre as horas do PRÓPRIO usuário logado — nunca confia em nome de
    # funcionário vindo do cliente, senão qualquer um logado poderia forjar o
    # request e puxar as horas de outra pessoa.
    employee_name = _user["name"]

    parsed_month = parse_month_label(payload.month_label)
    if not parsed_month:
        raise HTTPException(400, f'Mês de referência inválido: "{payload.month_label}" (use o formato "Julho/2026").')
    year, month = parsed_month
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"

    try:
        rows = fetch_employee_hours(
            start_date, end_date, employee_id=_user.get("employee_id"), employee_name=employee_name
        )
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)

    if not rows:
        raise HTTPException(
            404,
            f'Nenhum lançamento encontrado pro nome "{employee_name}" em {payload.month_label}. '
            "Confira o nome (a busca é parcial) e o mês.",
        )

    packages, issues = group_hours(rows, split_by_package=(payload.mode == "multi"))
    return _build_parse_response(packages, issues)


_MY_HOURS_PERIOD_MONTHS = {"current_month": 1, "last_3": 3, "last_6": 6, "last_12": 12}


def _my_hours_date_range(period: str) -> tuple[date, date]:
    """(início, fim) do período pedido — sempre até HOJE (não faz sentido
    pedir horas de um dia que ainda não aconteceu), voltando N meses
    completos a partir do mês corrente. `current_month` = só o mês corrente
    (o caso de uso principal: "como estou indo esse mês")."""
    today = date.today()
    months_back = _MY_HOURS_PERIOD_MONTHS[period]
    month_index = today.month - 1 - (months_back - 1)
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1), today


_BILLING_CLASS = {"1": "externo", "0": "interno"}

# Janela do histórico longo, independente do período exibido: alimenta a
# tendência de 13 meses, o baseline empírico de jornada (até 365 dias) e os
# percentis diários. Sem isso, "Mês atual" zeraria a tendência e o baseline.
_MY_HOURS_HISTORY_DAYS = 400


def _unescape_twice(value: object) -> str:
    """`html.unescape` em ponto fixo (2 passes) — o Projectile tem texto com
    entidade dupla (`&amp;#243;`), em que um passe só devolveria `&#243;`."""
    text = html.unescape(str(value or ""))
    return html.unescape(text)


def _entry_times(row: dict) -> tuple[str | None, str | None]:
    """`ttimebit.pStart`/`pEnd` validados para "HH:MM". Um span negativo
    (fim antes do início, virada de meia-noite) invalida os DOIS lados: exibir
    só uma ponta faria a faixa de jornada do dia ser desenhada errada."""
    start, end = parse_hhmm(row.get("inicio")), parse_hhmm(row.get("fim"))
    if start is not None and end is not None and end < start:
        return None, None
    return format_hhmm(start), format_hhmm(end)


@app.get("/my-hours")
async def my_hours_endpoint(period: str = "current_month", _user: dict = Depends(require_session)):
    """Dashboard de horas pessoal — dado do PRÓPRIO usuário logado (mesma
    regra de `/parse-db`: nunca confia em identidade vinda do cliente).

    Devolve os lançamentos do período MAIS o contexto que o frontend não pode
    derivar deles: a lista de dias úteis (pra achar os que ficaram sem
    apontamento — um dia sem apontamento é uma linha que não existe), a
    referência de jornada com a FONTE (contrato/histórico/calendário), a série
    de 13 meses e a comparação com a janela anterior de mesmo número de dias
    úteis.

    `reference.allows_percentage` é a chave que autoriza percentual na tela:
    só jornada de contrato declarado permite afirmar aderência. Medido que o
    usuário de referência não tem contrato cadastrado e pratica 6 h/dia, então
    aplicar as 8 h do calendário mostraria 76% de cumprimento num mês
    integralmente cumprido."""
    if period not in _MY_HOURS_PERIOD_MONTHS:
        raise HTTPException(400, f"Período inválido: {period!r} (use current_month/last_3/last_6/last_12).")
    start_date, end_date = _my_hours_date_range(period)
    today = date.today()
    employee_id, employee_name = _user.get("employee_id"), _user["name"]

    try:
        rows = fetch_my_hours(
            start_date.isoformat(), end_date.isoformat(),
            employee_id=employee_id, employee_name=employee_name,
        )
        history_rows = fetch_daily_hours_totals(
            (today - timedelta(days=_MY_HOURS_HISTORY_DAYS)).isoformat(), end_date.isoformat(),
            employee_id=employee_id, employee_name=employee_name,
        )
        contracts = fetch_employee_contracts(employee_id) if employee_id else []
        project_ids = sorted({r["project_id"] for r in rows if r.get("project_id")})
        project_details = fetch_project_details(project_ids) if project_ids else {}
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)

    daily_totals = {
        (r["data"] if isinstance(r["data"], date) else date.fromisoformat(str(r["data"]))): float(r["horas"] or 0)
        for r in history_rows
    }

    entries = []
    for i, r in enumerate(rows):
        entry_date = r["data"] if isinstance(r["data"], date) else date.fromisoformat(str(r["data"]))
        start_hhmm, end_hhmm = _entry_times(r)
        entries.append({
            # `ttimebit` não expõe PK utilizável nesta query; o ordinal do
            # resultado é estável dentro de um payload porque a query tem
            # ORDER BY determinístico (pDate, pStart).
            "id": f"{i}-{entry_date.isoformat()}-{start_hhmm or ''}",
            "date": entry_date.isoformat(),
            "start": start_hhmm,
            "end": end_hhmm,
            "hours": float(r["horas"] or 0),
            "pacote": _unescape_twice(r.get("pacote")),
            "observacao": _unescape_twice(r.get("observacao")),
            "project_id": r.get("project_id"),
            "project_name": _unescape_twice(
                (project_details.get(r.get("project_id")) or {}).get("name")
            ) or "Sem projeto",
            "top_project": _unescape_twice(r.get("top_project")) or None,
            "cost_center": r.get("cost_center"),
            # tri-estado deliberado: `external != "0"` empurrava NULL e
            # qualquer valor inesperado pra "faturável", inventando receita.
            "billing_class": _BILLING_CLASS.get(str(r.get("external") or ""), "nao_classificado"),
        })

    period_business = business_days_between(start_date, end_date)
    closed_business = [d for d in period_business if d < today]
    month_start = date(today.year, today.month, 1)
    month_end = date(today.year + (today.month == 12), (today.month % 12) + 1, 1) - timedelta(days=1)
    month_business = business_days_between(month_start, month_end)

    reference = resolve_reference(contracts, daily_totals, today)

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "today": today.isoformat(),
        "entries": entries,
        "business_days": {
            "list": [d.isoformat() for d in period_business],
            "closed": [d.isoformat() for d in closed_business],
            "count": len(period_business),
            "closed_count": len(closed_business),
            "month_total": len(month_business),
            "month_remaining": sum(1 for d in month_business if d >= today),
            "holidays": [d.isoformat() for d in national_holidays_between(start_date, end_date)],
            "source": "national_hardcoded",
            "note": (
                "seg–sex, feriados nacionais; feriado municipal e ponte "
                "facultativa não estão considerados"
            ),
        },
        "reference": reference,
        "expected": {
            "closed": expected_hours_for_days(closed_business, reference),
            "period": expected_hours_for_days(period_business, reference),
            "month": expected_hours_for_days(month_business, reference),
        },
        "gap_days": [d.isoformat() for d in gap_days(closed_business, daily_totals)],
        "outlier_days": sorted(d.isoformat() for d in outlier_days(daily_totals)),
        "monthly_series": monthly_series(daily_totals, today),
        "comparison": day_matched_comparison(daily_totals, start_date, end_date, today),
        "daily_stats": daily_stats(daily_totals, today),
    }


def _resolve_month_range(month_label: str) -> tuple[str, str]:
    parsed_month = parse_month_label(month_label)
    if not parsed_month:
        raise HTTPException(400, f'Mês de referência inválido: "{month_label}" (use o formato "Julho/2026").')
    year, month = parsed_month
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    return start_date, end_date


@app.get("/management/clients-with-hours")
async def management_clients_with_hours_endpoint(month_label: str, _user: dict = Depends(require_manager)):
    """Clientes com ao menos um lançamento de hora no mês — popula a busca de
    Cliente na tela de importação "por cliente" (`FileUpload.tsx`), só com
    quem teve movimento naquele período (não o cadastro inteiro do
    Projectile)."""
    start_date, end_date = _resolve_month_range(month_label)
    try:
        project_ids = fetch_project_ids_with_hours(start_date, end_date)
        clients = fetch_clients_for_projects(project_ids)
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)
    return {"clients": clients}


@app.get("/management/client-projects")
async def management_client_projects_endpoint(
    client: str, month_label: str, _user: dict = Depends(require_manager)
):
    """Projetos de um cliente com ao menos um lançamento de hora no mês —
    popula o seletor multi-seleção de projeto da tela de importação "por
    cliente"."""
    start_date, end_date = _resolve_month_range(month_label)
    try:
        active_ids = set(fetch_project_ids_with_hours(start_date, end_date))
        client_ids = set(fetch_project_ids_for_clients([client]))
        codes = fetch_project_codes(start_date, end_date)
        details = fetch_project_details(sorted(active_ids & client_ids))
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)
    projects = sorted(
        ({"id": pid, "name": info["name"], "code": codes.get(pid, "")} for pid, info in details.items()),
        key=lambda p: (int(p["code"]) if p["code"].isdigit() else float("inf"), p["name"]),
    )
    return {"projects": projects}


class ParseDbClientRequest(BaseModel):
    project_ids: list[str] = Field(min_length=1)
    month_label: str
    mode: Literal["pacote", "projeto"] = "pacote"


@app.post("/parse-db-client")
async def parse_db_client_endpoint(payload: ParseDbClientRequest, _user: dict = Depends(require_manager)):
    start_date, end_date = _resolve_month_range(payload.month_label)

    try:
        rows = fetch_project_hours(payload.project_ids, start_date, end_date)
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)

    if not rows:
        raise HTTPException(404, f"Nenhum lançamento encontrado pros projetos escolhidos em {payload.month_label}.")

    if payload.mode == "projeto":
        try:
            details = fetch_project_details(payload.project_ids)
        except ProjectileDbError as e:
            raise _log_and_generic_error(e)
        project_names = {pid: info["name"] for pid, info in details.items()}
        packages, issues = group_hours_by_project(rows, project_names)
    else:
        packages, issues = group_hours(rows, split_by_package=True)
    return _build_parse_response(packages, issues)


@app.get("/management/kpis")
async def management_kpis_endpoint(
    months: int = 12,
    year: int | None = None,
    cost_centers: list[str] = Query(default=[]),
    clients: list[str] = Query(default=[]),
    projects: list[str] = Query(default=[]),
    packages: list[str] = Query(default=[]),
    force_refresh: bool = False,
    _user: dict = Depends(require_manager),
):
    try:
        return compute_monthly_kpis(
            months,
            year=year,
            cost_centers=cost_centers or None,
            clients=clients or None,
            projects=projects or None,
            packages=packages or None,
            force_refresh=force_refresh,
        )
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)


@app.post("/management/kpis/check-emails")
async def management_check_emails_endpoint(_user: dict = Depends(require_manager)):
    """Dispara sob demanda o mesmo ciclo de `_poll_emails_loop` (botão
    "Verificar horas faturadas" no painel), sem esperar o próximo intervalo
    de polling. Síncrono/bloqueante por natureza (Graph + openpyxl), por isso
    roda em thread separada (`to_thread`) pra não travar o event loop."""
    if not os.environ.get("AZURE_CLIENT_ID"):
        raise HTTPException(400, "Automação de e-mail não configurada (AZURE_* ausente no .env).")
    try:
        return await asyncio.to_thread(email_ingest.process_new_emails)
    except (email_ingest.EmailIngestError, ProjectileDbError) as e:
        generic = _GENERIC_EMAIL_ERROR if isinstance(e, email_ingest.EmailIngestError) else _GENERIC_DB_ERROR
        raise _log_and_generic_error(e, generic_message=generic)


@app.get("/management/projects")
async def management_projects_endpoint(_user: dict = Depends(require_manager)):
    """Lista de todos os projetos do Projectile (id/nome/cliente), sem
    recorte por período — alimenta o seletor de projeto da tela de
    Diagnóstico (cadastro/edição manual de amostra), onde o gerente precisa
    poder escolher qualquer projeto, não só os que já apareceram num
    período específico."""
    try:
        return fetch_all_projects_with_details()
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)


@app.get("/management/kpis/samples")
async def management_kpi_samples_endpoint(month: str | None = None, _user: dict = Depends(require_manager)):
    """Tela de Diagnóstico: mostra de quais e-mails (ou cadastro manual)
    vieram as horas faturadas/dias de cada (projeto, mês), e o que foi
    pulado e por quê — necessário porque o match de projeto é automático,
    sem fila de revisão humana (ver `email_ingest.match_project`). Sem
    `month`, lista tudo (aba "Todos" da tela)."""
    if month is not None and not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "Mês inválido, use o formato AAAA-MM.")
    return list_samples(month)


class ManualSampleCreatePayload(BaseModel):
    project_id: str
    month: str
    billed_hours: float = Field(ge=0, allow_inf_nan=False)
    business_days: float = Field(ge=0, allow_inf_nan=False)


@app.post("/management/kpis/samples")
async def management_kpi_sample_create_endpoint(
    payload: ManualSampleCreatePayload, _user: dict = Depends(require_manager)
):
    """Cadastro manual de amostra — pra quando um relatório foi enviado fora
    do fluxo de e-mail, ou o match automático nunca achou o projeto certo."""
    if not re.fullmatch(r"\d{4}-\d{2}", payload.month):
        raise HTTPException(400, "Mês inválido, use o formato AAAA-MM.")
    try:
        projects = fetch_all_projects_with_details()
    except ProjectileDbError as e:
        raise _log_and_generic_error(e)
    project = next((p for p in projects if p["id"] == payload.project_id), None)
    if not project:
        raise HTTPException(400, "Projeto não encontrado no Projectile.")
    return create_manual_project_kpi_sample(
        project_id=payload.project_id,
        project_name=project["name"],
        month=payload.month,
        billed_hours=payload.billed_hours,
        business_days=payload.business_days,
    )


class SampleUpdatePayload(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    billed_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    business_days: float | None = Field(default=None, ge=0, allow_inf_nan=False)


@app.patch("/management/kpis/samples/{sample_id}")
async def management_kpi_sample_update_endpoint(
    sample_id: str, payload: SampleUpdatePayload, _user: dict = Depends(require_manager)
):
    """Corrige uma amostra existente — projeto errado (match automático
    fraco), horas/dias lidos errado, ou competência errada."""
    patch = payload.model_dump(exclude_unset=True)
    if not update_project_kpi_sample(sample_id, patch):
        raise HTTPException(404, "Amostra não encontrada.")
    return {"ok": True}


@app.delete("/management/kpis/samples/{sample_id}")
async def management_kpi_sample_delete_endpoint(sample_id: str, _user: dict = Depends(require_manager)):
    """Remove uma amostra errada. O e-mail original continua marcado como
    processado — não volta a ser reprocessado no próximo polling."""
    if not delete_project_kpi_sample(sample_id):
        raise HTTPException(404, "Amostra não encontrada.")
    return {"ok": True}


class ManualEntryPayload(BaseModel):
    billed_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    elaboration_days: float | None = Field(default=None, ge=0, allow_inf_nan=False)


@app.put("/management/kpis/{month}")
async def management_manual_entry_endpoint(
    month: str, payload: ManualEntryPayload, _user: dict = Depends(require_manager)
):
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "Mês inválido, use o formato AAAA-MM.")
    set_manual_entry(month, payload.billed_hours, payload.elaboration_days)
    return {"ok": True}


class ActivityPayload(BaseModel):
    description: str
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class GroupPayload(BaseModel):
    name: str
    performance: float = Field(ge=0, allow_inf_nan=False)
    activities: list[ActivityPayload]


class HeaderPayload(BaseModel):
    project_code: str = Field(min_length=1, description='Número do relatório (ex: "SE.XX.XXX") — obrigatório.')
    project_name: str
    location_date: str
    month_label: str
    signer1_name: str = Field(min_length=1, description="Nome de quem assina pela Schwaben — obrigatório.")
    signer1_company: str = "Schwaben Engineering"
    signer2_name: str = Field(min_length=1, description="Nome de quem assina pelo cliente — obrigatório.")
    signer2_company: str = "Mercedes-Benz do Brasil"


class ReportPackagePayload(BaseModel):
    header: HeaderPayload
    groups: list[GroupPayload]
    file_name: str | None = None
    chart_image_bar: str | None = None
    chart_image_pie: str | None = None
    # None = relatório cobre o projeto inteiro; texto = cobre só esse pacote
    # de trabalho — vira uma marca oculta no .xlsx (ver generator.py), lida
    # de volta por email_ingest.py pra status "enviado"/"parcial" por projeto.
    pacote_scope: str | None = None


class GeneratePayload(BaseModel):
    packages: list[ReportPackagePayload] = Field(min_length=1)
    formats: list[Literal["xlsx", "pdf"]] = Field(default=["xlsx"], min_length=1)


def _report_groups(pkg_payload: ReportPackagePayload) -> tuple[ReportHeader, list[GroupInput]]:
    header = ReportHeader(**pkg_payload.header.model_dump())
    groups = [
        GroupInput(
            name=g.name,
            performance=g.performance,
            activities=[ActivityInput(description=a.description, hours=a.hours) for a in g.activities],
        )
        for g in pkg_payload.groups
    ]
    return header, groups


def _build_report(pkg_payload: ReportPackagePayload, output_path: str, fmt: Literal["xlsx", "pdf"] = "xlsx") -> ReportHeader:
    header, groups = _report_groups(pkg_payload)
    if fmt == "pdf":
        generate_report_pdf(
            header,
            groups,
            output_path,
            chart_image_bar_b64=pkg_payload.chart_image_bar,
            chart_image_pie_b64=pkg_payload.chart_image_pie,
            pacote_scope=pkg_payload.pacote_scope,
        )
    else:
        generate_report(
            header,
            groups,
            output_path,
            chart_image_bar_b64=pkg_payload.chart_image_bar,
            chart_image_pie_b64=pkg_payload.chart_image_pie,
            pacote_scope=pkg_payload.pacote_scope,
        )
    return header


_FORMAT_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _sanitized_file_name(raw_name: str | None, fallback_header: ReportHeader, fmt: Literal["xlsx", "pdf"] = "xlsx") -> str:
    ext = f".{fmt}"
    if raw_name and raw_name.strip():
        stem = re.sub(r'[\\/:*?"<>|]', "-", raw_name.strip())
        if stem.lower().endswith((".xlsx", ".pdf")):
            stem = stem.rsplit(".", 1)[0]
        stem = stem.strip(". ")
        if stem:
            return f"{stem}{ext}"
    stem = _build_download_name(fallback_header.month_label, fallback_header.project_name)
    if stem.lower().endswith(".xlsx"):
        stem = stem[: -len(".xlsx")]
    return f"{stem}{ext}"


def _dedupe_name(name: str, used: set[str]) -> str:
    """Sufixa " (n)" antes da extensão se `name` já estiver em `used` —
    compara o nome final COM extensão, então "Relatório.xlsx" e
    "Relatório.pdf" nunca colidem entre si, só duplicatas de verdade."""
    if name not in used:
        return name
    stem, _, ext = name.rpartition(".")
    suffix = 0
    candidate = name
    while candidate in used:
        suffix += 1
        candidate = f"{stem} ({suffix}).{ext}"
    return candidate


@app.post("/generate")
async def generate_endpoint(payload: GeneratePayload, _user: dict = Depends(require_session)):
    formats = payload.formats
    # Só 1 pacote E 1 formato no payload — devolve o arquivo direto, sem
    # zipar, mantendo o comportamento original do app. Qualquer outra
    # combinação (mais pacotes e/ou mais formatos) zipa tudo junto.
    if len(payload.packages) == 1 and len(formats) == 1:
        fmt = formats[0]
        output_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.{fmt}")
        try:
            header = _build_report(payload.packages[0], output_path, fmt)
        except NonFiniteValueError as e:
            # Um valor individualmente válido (finito, >= 0) ainda pode virar
            # infinito ao ser somado com outro (ex: duas horas enormes que juntas
            # estouram o float) — isso é culpa dos dados enviados, vira 400.
            # (Outras ValueError de generate_report indicam o TEMPLATE corrompido/
            # incompatível — um bug do servidor, não do usuário — e devem cair no
            # except Exception abaixo para virar 500 de verdade.)
            if os.path.exists(output_path):
                os.remove(output_path)
            raise HTTPException(400, str(e))
        except Exception:
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
        download_name = _sanitized_file_name(payload.packages[0].file_name, header, fmt)
        return FileResponse(
            output_path,
            filename=download_name,
            media_type=_FORMAT_MEDIA_TYPES[fmt],
            background=BackgroundTask(os.remove, output_path),
        )

    # Um arquivo por (pacote, formato) escolhido, zipados juntos.
    zip_path = os.path.join(OUTPUT_DIR, f"relatorios_{uuid.uuid4().hex}.zip")
    used_arcnames: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pkg_payload in payload.packages:
                for fmt in formats:
                    tmp_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.{fmt}")
                    try:
                        header = _build_report(pkg_payload, tmp_path, fmt)
                        download_name = _sanitized_file_name(pkg_payload.file_name, header, fmt)
                        final_name = _dedupe_name(download_name, used_arcnames)
                        used_arcnames.add(final_name)
                        zf.write(tmp_path, arcname=final_name)
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
    except NonFiniteValueError as e:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise HTTPException(400, str(e))
    except Exception:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise

    return FileResponse(
        zip_path,
        filename="Relatórios_Horas.zip",
        media_type="application/zip",
        background=BackgroundTask(os.remove, zip_path),
    )


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SendReportPayload(BaseModel):
    packages: list[ReportPackagePayload] = Field(min_length=1)
    to: str
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=5000)
    formats: list[Literal["xlsx", "pdf"]] = Field(default=["xlsx"], min_length=1)


@app.post("/send-report")
async def send_report_endpoint(payload: SendReportPayload, _user: dict = Depends(require_session)):
    """Gera 1 ou mais relatórios (mesmo caminho de `/generate`, um arquivo
    por `(pacote, formato)` escolhido) e manda TUDO num único e-mail via
    Microsoft Graph, "como" o usuário logado, sempre com a caixa do agente
    em cópia — cada arquivo vira seu próprio anexo dentro do mesmo e-mail
    (nunca zipado). Pra mandar pacotes diferentes em e-mails separados, o
    frontend chama esse endpoint uma vez por pacote (uma lista de 1 item
    cada vez). Tanto `.xlsx` quanto `.pdf` são capturados pela automação de
    Horas Faturadas/KPI (`email_ingest.resolve_total_hours` pro `.xlsx`,
    `email_ingest.read_pdf_report_data` pro `.pdf`, que lê metadado gravado
    em `pdf_generator.py` em vez de célula/fórmula)."""
    sender_email = (_user.get("email") or "").strip()
    if not sender_email:
        raise HTTPException(
            400,
            "Seu usuário não tem e-mail cadastrado no Projectile — não é possível enviar o relatório.",
        )
    if not _EMAIL_RE.match(payload.to.strip()):
        raise HTTPException(400, "E-mail do destinatário inválido.")

    output_paths: list[str] = []
    try:
        attachments: list[tuple[str, bytes]] = []
        used_names: set[str] = set()
        for pkg_payload in payload.packages:
            for fmt in payload.formats:
                output_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.{fmt}")
                output_paths.append(output_path)
                header = _build_report(pkg_payload, output_path, fmt)
                download_name = _sanitized_file_name(pkg_payload.file_name, header, fmt)
                # mesma dedupe de nome que /generate usa no modo zip — dois
                # anexos não podem ter o mesmo nome final no mesmo e-mail.
                final_name = _dedupe_name(download_name, used_names)
                used_names.add(final_name)
                with open(output_path, "rb") as f:
                    attachments.append((final_name, f.read()))

        email_ingest.send_report_email(
            sender_email=sender_email,
            to_email=payload.to.strip(),
            subject=payload.subject,
            body_text=payload.message,
            attachments=attachments,
        )
    except NonFiniteValueError as e:
        raise HTTPException(400, str(e))
    except email_ingest.EmailIngestError as e:
        raise _log_and_generic_error(e, generic_message=_GENERIC_EMAIL_ERROR)
    finally:
        for output_path in output_paths:
            if os.path.exists(output_path):
                os.remove(output_path)

    return {"ok": True}


class ChatActivity(BaseModel):
    description: str
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ChatGroup(BaseModel):
    name: str
    performance: float = Field(ge=0, allow_inf_nan=False)
    activities: list[ChatActivity]


class ChatPackage(BaseModel):
    key: str
    projectCode: str
    projectName: str
    groups: list[ChatGroup]


class ChatState(BaseModel):
    packages: list[ChatPackage] = Field(min_length=1)
    activePackageIndex: int
    locationDate: str
    monthLabel: str
    signer1Name: str = ""
    signer1Company: str = ""
    signer2Name: str = ""
    signer2Company: str = ""


class ChatRequest(BaseModel):
    message: str
    state: ChatState


class ChatResponse(BaseModel):
    reply: str
    state: ChatState


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest, _user: dict = Depends(require_session)):
    try:
        summary, operations = call_chat(payload.message, payload.state.model_dump())
    except ChatConfigError as e:
        raise HTTPException(500, str(e))
    except ChatUpstreamError as e:
        raise HTTPException(502, str(e))

    try:
        new_state = apply_operations(payload.state.model_dump(), operations)
    except OperationError as e:
        # a IA pediu uma operação que não bate com o estado real (pacote/grupo/
        # atividade inexistente, campo inválido) — nunca aplica parte da lista
        raise HTTPException(502, f"A IA pediu uma alteração inválida: {e} Tente reformular o pedido.")

    try:
        validated_state = ChatState.model_validate(new_state)
    except Exception:
        raise HTTPException(502, "A IA retornou dados inválidos (ex: horas negativas). Tente reformular o pedido.")

    return ChatResponse(reply=summary, state=validated_state)


def _build_download_name(month_label: str, project_name: str) -> str:
    mes_ano = month_label.replace("/", ".").strip()
    projeto = re.sub(r'[\\/:*?"<>|]', "-", project_name).strip()
    return f"Relatório_Horas-{mes_ano}-{projeto}.xlsx"


_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_DIST_DIR = os.path.join(_FRONTEND_DIR, "dist")
_STATIC_DIR = _DIST_DIR if os.path.isdir(_DIST_DIR) else _FRONTEND_DIR
app.mount("/", NoCacheStaticFiles(directory=_STATIC_DIR, html=True), name="web")
