"""Rotas de geração e envio de relatório (`/generate`, `/send-report`) —
extraído de `main.py` na Fase 5."""
from __future__ import annotations

import os
import re
import tempfile
import uuid
import zipfile
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ... import email_ingest
from ...generator import ActivityInput, GroupInput, NonFiniteValueError, ReportHeader, generate_report
from ...pdf_generator import generate_report_pdf
from ...services.report_persistence import (
    GenerationGuard,
    finish_generation_failure,
    finish_generation_success,
)
from ..dependencies import require_session
from ..errors import GENERIC_EMAIL_ERROR, log_and_generic_error

router = APIRouter()

OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "relatorio_horas_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


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
    # idioma dos RÓTULOS FIXOS do arquivo gerado (título, cabeçalhos de
    # coluna, "Bruto"/"Performance", "Total de horas.../Total hours...") —
    # ver generator._LABELS/pdf_generator.generate_report_pdf. Por pacote
    # (não no nível de GeneratePayload, como include_performance): reflete
    # se ESSE pacote já foi traduzido pelo botão "EN" do preview (que também
    # traduz nomes de grupo/descrições de atividade via IA, antes de este
    # payload ser montado) — por isso já vale tanto pra /generate quanto
    # pra /send-report, sem precisar duplicar o campo em SendReportPayload.
    language: Literal["pt", "en", "de"] = "pt"


class GeneratePayload(BaseModel):
    packages: list[ReportPackagePayload] = Field(min_length=1)
    formats: list[Literal["xlsx", "pdf"]] = Field(default=["xlsx"], min_length=1)
    # checkbox "Incluir performance" no rodapé de Gerar Relatório — inclui no
    # arquivo o Bruto/Performance por grupo e o total geral (ver
    # generator._build_group_rows/_build_totals_row e
    # pdf_generator.generate_report_pdf), mesma informação que já aparece só
    # no preview (PreviewSheet.tsx). Não se aplica ao /send-report (envio por
    # e-mail) — fora do pedido original, sempre False lá.
    include_performance: bool = False


def _persistence_pkg_data(pkg_payload: ReportPackagePayload) -> dict:
    """Converte o payload Pydantic pro dict plano que
    `services/report_persistence.begin_generation` espera — mantém aquele
    módulo desacoplado dos modelos definidos aqui (evita import circular)."""
    return {
        "header": pkg_payload.header.model_dump(),
        "groups": [g.model_dump() for g in pkg_payload.groups],
        "pacote_scope": pkg_payload.pacote_scope,
        "language": pkg_payload.language,
        "has_chart_bar": bool(pkg_payload.chart_image_bar),
        "has_chart_pie": bool(pkg_payload.chart_image_pie),
    }


def _persistence_headers(handle) -> dict[str, str]:
    """`handle` é `None` quando a persistência estava desligada
    (`REPORTS_DB_ENABLED=false`) ou falhou (fail-open) — nesse caso não há
    nada aditivo pra incluir, e a resposta continua idêntica à de hoje."""
    if handle is None:
        return {}
    return {
        "X-Report-Id": handle.report_id,
        "X-Report-Version-Id": handle.version_id,
        "X-Report-Version-Number": str(handle.version_number),
    }


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


def _build_report(
    pkg_payload: ReportPackagePayload,
    output_path: str,
    fmt: Literal["xlsx", "pdf"] = "xlsx",
    include_performance: bool = False,
) -> ReportHeader:
    header, groups = _report_groups(pkg_payload)
    if fmt == "pdf":
        generate_report_pdf(
            header,
            groups,
            output_path,
            chart_image_bar_b64=pkg_payload.chart_image_bar,
            chart_image_pie_b64=pkg_payload.chart_image_pie,
            pacote_scope=pkg_payload.pacote_scope,
            include_performance=include_performance,
            language=pkg_payload.language,
        )
    else:
        generate_report(
            header,
            groups,
            output_path,
            chart_image_bar_b64=pkg_payload.chart_image_bar,
            chart_image_pie_b64=pkg_payload.chart_image_pie,
            pacote_scope=pkg_payload.pacote_scope,
            include_performance=include_performance,
            language=pkg_payload.language,
        )
    return header


_FORMAT_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _build_download_name(month_label: str, project_name: str) -> str:
    mes_ano = month_label.replace("/", ".").strip()
    projeto = re.sub(r'[\\/:*?"<>|]', "-", project_name).strip()
    return f"Relatório_Horas-{mes_ano}-{projeto}.xlsx"


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


@router.post("/generate")
async def generate_endpoint(payload: GeneratePayload, _user: dict = Depends(require_session)):
    formats = payload.formats
    # Só 1 pacote E 1 formato no payload — devolve o arquivo direto, sem
    # zipar, mantendo o comportamento original do app. Qualquer outra
    # combinação (mais pacotes e/ou mais formatos) zipa tudo junto.
    if len(payload.packages) == 1 and len(formats) == 1:
        fmt = formats[0]
        output_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.{fmt}")
        # Persistência em reports_db é fail-open: `handle` vem `None` se a
        # persistência estiver desligada ou falhar (ver GenerationGuard/
        # begin_generation) — a geração do arquivo nunca fica bloqueada por
        # causa disso.
        handle = GenerationGuard().begin(
            _persistence_pkg_data(payload.packages[0]), fmt, _user["login"], _user["name"]
        )
        try:
            header = _build_report(payload.packages[0], output_path, fmt, payload.include_performance)
        except NonFiniteValueError as e:
            # Um valor individualmente válido (finito, >= 0) ainda pode virar
            # infinito ao ser somado com outro (ex: duas horas enormes que juntas
            # estouram o float) — isso é culpa dos dados enviados, vira 400.
            # (Outras ValueError de generate_report indicam o TEMPLATE corrompido/
            # incompatível — um bug do servidor, não do usuário — e devem cair no
            # except Exception abaixo para virar 500 de verdade.)
            finish_generation_failure(handle, e)
            if os.path.exists(output_path):
                os.remove(output_path)
            raise HTTPException(400, str(e))
        except Exception as e:
            finish_generation_failure(handle, e)
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
        download_name = _sanitized_file_name(payload.packages[0].file_name, header, fmt)
        finish_generation_success(handle, output_path, download_name, fmt, _FORMAT_MEDIA_TYPES[fmt])
        return FileResponse(
            output_path,
            filename=download_name,
            media_type=_FORMAT_MEDIA_TYPES[fmt],
            background=BackgroundTask(os.remove, output_path),
            headers=_persistence_headers(handle),
        )

    # Um arquivo por (pacote, formato) escolhido, zipados juntos.
    zip_path = os.path.join(OUTPUT_DIR, f"relatorios_{uuid.uuid4().hex}.zip")
    used_arcnames: set[str] = set()
    guard = GenerationGuard()
    persisted_ids: list[str] = []
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pkg_payload in payload.packages:
                for fmt in formats:
                    tmp_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.{fmt}")
                    handle = guard.begin(_persistence_pkg_data(pkg_payload), fmt, _user["login"], _user["name"])
                    try:
                        header = _build_report(pkg_payload, tmp_path, fmt, payload.include_performance)
                        download_name = _sanitized_file_name(pkg_payload.file_name, header, fmt)
                        final_name = _dedupe_name(download_name, used_arcnames)
                        used_arcnames.add(final_name)
                        zf.write(tmp_path, arcname=final_name)
                    except Exception as e:
                        finish_generation_failure(handle, e)
                        raise
                    else:
                        finish_generation_success(handle, tmp_path, final_name, fmt, _FORMAT_MEDIA_TYPES[fmt])
                        if handle is not None:
                            persisted_ids.append(f"{handle.report_id}:{handle.version_id}")
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

    headers = {"X-Report-Ids": ",".join(persisted_ids)} if persisted_ids else {}
    return FileResponse(
        zip_path,
        filename="Relatórios_Horas.zip",
        media_type="application/zip",
        background=BackgroundTask(os.remove, zip_path),
        headers=headers,
    )


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SendReportPayload(BaseModel):
    packages: list[ReportPackagePayload] = Field(min_length=1)
    to: str
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=5000)
    formats: list[Literal["xlsx", "pdf"]] = Field(default=["xlsx"], min_length=1)


@router.post("/send-report")
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
    guard = GenerationGuard()
    try:
        attachments: list[tuple[str, bytes]] = []
        used_names: set[str] = set()
        for pkg_payload in payload.packages:
            for fmt in payload.formats:
                output_path = os.path.join(OUTPUT_DIR, f"relatorio_{uuid.uuid4().hex}.{fmt}")
                output_paths.append(output_path)
                # Mesma persistência fail-open de /generate — um relatório
                # mandado por e-mail é tão real quanto um baixado, então
                # entra no mesmo histórico (ver plano de implementação).
                handle = guard.begin(
                    _persistence_pkg_data(pkg_payload), fmt, _user["login"], _user["name"],
                    created_from="send_report_endpoint",
                )
                try:
                    header = _build_report(pkg_payload, output_path, fmt)
                except Exception as e:
                    finish_generation_failure(handle, e)
                    raise
                download_name = _sanitized_file_name(pkg_payload.file_name, header, fmt)
                # mesma dedupe de nome que /generate usa no modo zip — dois
                # anexos não podem ter o mesmo nome final no mesmo e-mail.
                final_name = _dedupe_name(download_name, used_names)
                used_names.add(final_name)
                finish_generation_success(handle, output_path, final_name, fmt, _FORMAT_MEDIA_TYPES[fmt])
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
        raise log_and_generic_error(e, generic_message=GENERIC_EMAIL_ERROR)
    finally:
        for output_path in output_paths:
            if os.path.exists(output_path):
                os.remove(output_path)

    return {"ok": True}
