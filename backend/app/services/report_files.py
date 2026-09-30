"""Montagem de arquivo de relatório (XLSX/PDF) a partir do payload de
geração — compartilhado entre `/generate`, `/send-report`
(`api/routers/generation.py`) e a geração automática
(`auto_generation/service.py`, aprovação e envio), pra que os três produzam
exatamente o mesmo arquivo pro mesmo conteúdo."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..generator import ActivityInput, GroupInput, ReportHeader, generate_report
from ..pdf_generator import generate_report_pdf

# Tetos de entrada — largos de propósito (um relatório real tem dezenas de
# grupos e algumas centenas de atividades), só barram payload absurdo antes de
# ele virar memória/CPU no gerador. Valem pra /generate, /send-report e pra
# aprovação da geração automática, que reusam estes mesmos modelos.
MAX_PACKAGES = 100
MAX_GROUPS = 500
MAX_ACTIVITIES_PER_GROUP = 2000
MAX_ACTIVITIES_TOTAL = 20_000
MAX_DESCRIPTION = 2000
MAX_NAME = 500
MAX_HEADER_TEXT = 500
MAX_CHART_B64 = 4_000_000  # ~3 MB de PNG; o gráfico do navegador tem ~100 KB
_IMAGE_MAGIC = (bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]), bytes([0xFF, 0xD8, 0xFF]))  # PNG, JPEG


def _check_image(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) > MAX_CHART_B64:
        raise ValueError("imagem do gráfico grande demais")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("imagem do gráfico não é base64 válido") from exc
    if not raw.startswith(_IMAGE_MAGIC):
        raise ValueError("imagem do gráfico precisa ser PNG ou JPEG")
    return value


class ActivityPayload(BaseModel):
    description: str = Field(max_length=MAX_DESCRIPTION)
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class GroupPayload(BaseModel):
    name: str = Field(max_length=MAX_NAME)
    performance: float = Field(ge=0, allow_inf_nan=False)
    activities: list[ActivityPayload] = Field(max_length=MAX_ACTIVITIES_PER_GROUP)


class HeaderPayload(BaseModel):
    project_code: str = Field(min_length=1, max_length=MAX_HEADER_TEXT, description='Número do relatório (ex: "SE.XX.XXX") — obrigatório.')
    project_name: str = Field(max_length=MAX_HEADER_TEXT)
    location_date: str = Field(max_length=MAX_HEADER_TEXT)
    month_label: str = Field(max_length=MAX_HEADER_TEXT)
    signer1_name: str = Field(min_length=1, max_length=MAX_HEADER_TEXT, description="Nome de quem assina pela Schwaben — obrigatório.")
    signer1_company: str = Field(default="Schwaben Engineering", max_length=MAX_HEADER_TEXT)
    signer2_name: str = Field(min_length=1, max_length=MAX_HEADER_TEXT, description="Nome de quem assina pelo cliente — obrigatório.")
    signer2_company: str = Field(default="Mercedes-Benz do Brasil", max_length=MAX_HEADER_TEXT)


class ReportPackagePayload(BaseModel):
    header: HeaderPayload
    groups: list[GroupPayload] = Field(max_length=MAX_GROUPS)
    file_name: str | None = Field(default=None, max_length=MAX_NAME)
    chart_image_bar: str | None = None
    chart_image_pie: str | None = None
    # None = relatório cobre o projeto inteiro; texto = cobre só esse pacote
    # de trabalho — vira uma marca oculta no .xlsx (ver generator.py), lida
    # de volta por email_ingest.py pra status "enviado"/"parcial" por projeto.
    pacote_scope: str | None = Field(default=None, max_length=MAX_NAME)
    # idioma dos RÓTULOS FIXOS do arquivo gerado (título, cabeçalhos de
    # coluna, "Bruto"/"Performance", "Total de horas.../Total hours...") —
    # ver generator._LABELS/pdf_generator.generate_report_pdf. Por pacote
    # (não no nível de GeneratePayload, como include_performance): reflete
    # se ESSE pacote já foi traduzido pelo botão "EN" do preview (que também
    # traduz nomes de grupo/descrições de atividade via IA, antes de este
    # payload ser montado) — por isso já vale tanto pra /generate quanto
    # pra /send-report, sem precisar duplicar o campo em SendReportPayload.
    language: Literal["pt", "en", "de"] = "pt"

    @field_validator("chart_image_bar", "chart_image_pie")
    @classmethod
    def _valid_chart_image(cls, value: str | None) -> str | None:
        return _check_image(value)

    def activity_count(self) -> int:
        return sum(len(g.activities) for g in self.groups)


def check_total_size(packages: list[ReportPackagePayload]) -> list[ReportPackagePayload]:
    if sum(p.activity_count() for p in packages) > MAX_ACTIVITIES_TOTAL:
        raise ValueError(f"atividades demais na geração (máximo {MAX_ACTIVITIES_TOTAL})")
    return packages


class GeneratePayload(BaseModel):
    packages: list[ReportPackagePayload] = Field(min_length=1, max_length=MAX_PACKAGES)
    formats: list[Literal["xlsx", "pdf"]] = Field(default=["xlsx"], min_length=1)
    # checkbox "Incluir performance" no rodapé de Gerar Relatório — inclui no
    # arquivo o Bruto/Performance por grupo e o total geral (ver
    # generator._build_group_rows/_build_totals_row e
    # pdf_generator.generate_report_pdf), mesma informação que já aparece só
    # no preview (PreviewSheet.tsx). Não se aplica ao /send-report (envio por
    # e-mail) — fora do pedido original, sempre False lá.
    # ignorado: arquivo nunca mostra performance (ver `build_report_file`)
    include_performance: bool = False

    @field_validator("packages")
    @classmethod
    def _total_size(cls, value: list[ReportPackagePayload]) -> list[ReportPackagePayload]:
        return check_total_size(value)


def persistence_pkg_data(pkg_payload: ReportPackagePayload) -> dict:
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


def persistence_headers(handle) -> dict[str, str]:
    """`handle` é `None` quando a persistência estava desligada
    (`REPORTS_DB_ENABLED=false`) ou falhou (fail-open) — nesse caso não há
    nada aditivo pra incluir, e a resposta continua idêntica à de hoje."""
    if handle is None:
        return {}
    return {"X-Report-Id": handle.report_id, "X-Report-Version-Id": handle.version_id, "X-Report-Version-Number": str(handle.version_number)}


def report_groups(pkg_payload: ReportPackagePayload) -> tuple[ReportHeader, list[GroupInput]]:
    header = ReportHeader(**pkg_payload.header.model_dump())
    groups = [
        GroupInput(name=g.name, performance=g.performance, activities=[ActivityInput(description=a.description, hours=a.hours) for a in g.activities])
        for g in pkg_payload.groups
    ]
    return header, groups


def build_report_file(pkg_payload: ReportPackagePayload, output_path: str, fmt: Literal["xlsx", "pdf"] = "xlsx") -> ReportHeader:
    """Todo XLSX/PDF que sai do sistema passa por aqui (`/generate`,
    `/send-report`, aprovação e envio da geração automática) — e NUNCA com as
    colunas de Bruto/Performance (decisão do usuário, 2026-09-28: relatório
    gerado por qualquer meio não mostra performance). A performance continua
    no CÁLCULO das horas (bruto × performance, igual a `calc.ts`); só a
    exibição dela no arquivo é que não existe mais. `include_performance` dos
    payloads é aceito por compatibilidade e ignorado."""
    header, groups = report_groups(pkg_payload)
    if fmt == "pdf":
        generate_report_pdf(
            header,
            groups,
            output_path,
            chart_image_bar_b64=pkg_payload.chart_image_bar,
            chart_image_pie_b64=pkg_payload.chart_image_pie,
            pacote_scope=pkg_payload.pacote_scope,
            include_performance=False,
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
            include_performance=False,
            language=pkg_payload.language,
        )
    return header


FORMAT_MEDIA_TYPES = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pdf": "application/pdf"}


def build_download_name(month_label: str, project_name: str) -> str:
    mes_ano = month_label.replace("/", ".").strip()
    projeto = re.sub(r'[\\/:*?"<>|]', "-", project_name).strip()
    return f"Relatório_Horas-{mes_ano}-{projeto}.xlsx"


def sanitized_file_name(raw_name: str | None, fallback_header: ReportHeader, fmt: Literal["xlsx", "pdf"] = "xlsx") -> str:
    ext = f".{fmt}"
    if raw_name and raw_name.strip():
        stem = re.sub(r'[\\/:*?"<>|]', "-", raw_name.strip())
        if stem.lower().endswith((".xlsx", ".pdf")):
            stem = stem.rsplit(".", 1)[0]
        stem = stem.strip(". ")
        if stem:
            return f"{stem}{ext}"
    stem = build_download_name(fallback_header.month_label, fallback_header.project_name)
    if stem.lower().endswith(".xlsx"):
        stem = stem[: -len(".xlsx")]
    return f"{stem}{ext}"


def dedupe_name(name: str, used: set[str]) -> str:
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
