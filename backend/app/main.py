import math
import os
import re
import tempfile
import uuid
import zipfile
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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

from .chatbot import ChatConfigError, ChatUpstreamError, call_chat
from .generator import ActivityInput, GroupInput, NonFiniteValueError, ReportHeader, generate_report
from .parser import parse_projectile_export

load_dotenv()

app = FastAPI(title="Automação de Relatório de Horas")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/parse")
async def parse_endpoint(file: UploadFile = File(...), mode: Literal["single", "multi"] = Form("single")):
    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
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


class ActivityPayload(BaseModel):
    description: str
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class GroupPayload(BaseModel):
    name: str
    performance: float = Field(ge=0, allow_inf_nan=False)
    activities: list[ActivityPayload]


class HeaderPayload(BaseModel):
    project_code: str
    project_name: str
    location_date: str
    month_label: str
    signer1_name: str = ""
    signer1_company: str = "Schwaben Engineering"
    signer2_name: str = ""
    signer2_company: str = "Mercedes-Benz do Brasil"


class ReportPackagePayload(BaseModel):
    header: HeaderPayload
    groups: list[GroupPayload]
    file_name: str | None = None


class GeneratePayload(BaseModel):
    packages: list[ReportPackagePayload] = Field(min_length=1)


def _build_report(pkg_payload: ReportPackagePayload, output_path: str) -> ReportHeader:
    header = ReportHeader(**pkg_payload.header.model_dump())
    groups = [
        GroupInput(
            name=g.name,
            performance=g.performance,
            activities=[ActivityInput(description=a.description, hours=a.hours) for a in g.activities],
        )
        for g in pkg_payload.groups
    ]
    generate_report(header, groups, output_path)
    return header


def _sanitized_file_name(raw_name: str | None, fallback_header: ReportHeader) -> str:
    if raw_name and raw_name.strip():
        stem = re.sub(r'[\\/:*?"<>|]', "-", raw_name.strip())
        if stem.lower().endswith(".xlsx"):
            stem = stem[: -len(".xlsx")]
        stem = stem.strip(". ")
        if stem:
            return f"{stem}.xlsx"
    return _build_download_name(fallback_header.month_label, fallback_header.project_name)


@app.post("/generate")
async def generate_endpoint(payload: GeneratePayload):
    # Modo "relatório único": só 1 pacote no payload — devolve o .xlsx direto,
    # sem zipar, mantendo o comportamento original do app.
    if len(payload.packages) == 1:
        output_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.xlsx")
        try:
            header = _build_report(payload.packages[0], output_path)
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
        download_name = _sanitized_file_name(payload.packages[0].file_name, header)
        return FileResponse(
            output_path,
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(os.remove, output_path),
        )

    # Modo "múltiplos relatórios": um .xlsx por pacote de trabalho, zipados juntos.
    zip_path = os.path.join(OUTPUT_DIR, f"relatorios_{uuid.uuid4().hex}.zip")
    used_arcnames: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pkg_payload in payload.packages:
                tmp_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.xlsx")
                try:
                    header = _build_report(pkg_payload, tmp_path)

                    download_name = _sanitized_file_name(pkg_payload.file_name, header)
                    # Deduplica contra o nome FINAL já usado (não só o nome-base antes do
                    # sufixo "(n)") — senão um nome legítimo que coincida com um nome já
                    # sufixado de outro pacote sobrescreve silenciosamente esse relatório
                    # dentro do zip.
                    final_name = download_name
                    suffix = 0
                    while final_name in used_arcnames:
                        suffix += 1
                        stem = download_name[: -len(".xlsx")]
                        final_name = f"{stem} ({suffix}).xlsx"
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
async def chat_endpoint(payload: ChatRequest):
    try:
        summary, new_state = call_chat(payload.message, payload.state.model_dump())
    except ChatConfigError as e:
        raise HTTPException(500, str(e))
    except ChatUpstreamError as e:
        raise HTTPException(502, str(e))

    try:
        validated_state = ChatState.model_validate(new_state)
    except Exception:
        raise HTTPException(502, "A IA retornou um formato inválido. Tente reformular o pedido.")

    if len(validated_state.packages) != len(payload.state.packages):
        raise HTTPException(
            502,
            "A IA devolveu um número diferente de relatórios do esperado. Tente reformular o pedido.",
        )

    return ChatResponse(reply=summary, state=validated_state)


def _build_download_name(month_label: str, project_name: str) -> str:
    mes_ano = month_label.replace("/", ".").strip()
    projeto = re.sub(r'[\\/:*?"<>|]', "-", project_name).strip()
    return f"Relatório_Horas-{mes_ano}-{projeto}.xlsx"


_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_DIST_DIR = os.path.join(_FRONTEND_DIR, "dist")
_STATIC_DIR = _DIST_DIR if os.path.isdir(_DIST_DIR) else _FRONTEND_DIR
app.mount("/", NoCacheStaticFiles(directory=_STATIC_DIR, html=True), name="web")
