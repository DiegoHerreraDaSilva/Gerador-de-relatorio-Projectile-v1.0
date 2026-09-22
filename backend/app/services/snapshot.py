"""Funções puras (sem I/O, sem banco) de hash/identidade pro histórico de
relatórios em `reports_db`. `pkg_data` em toda função aqui é um dict plano
(não os modelos Pydantic de `main.py`) — mantém este módulo testável sem
precisar montar um `ReportPackagePayload` completo, e evita import circular
entre `main.py` e `services/`.

Formato esperado de `pkg_data`:
    {
        "header": {"project_code", "project_name", "location_date", "month_label",
                   "signer1_name", "signer1_company", "signer2_name", "signer2_company"},
        "groups": [{"name", "performance", "activities": [{"description", "hours"}]}],
        "pacote_scope": str | None,
        "language": "pt" | "en" | "de",
        "has_chart_bar": bool,
        "has_chart_pie": bool,
    }
"""
from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date

from ..generator import parse_month_label, parse_period_label

_SNAPSHOT_SCHEMA_VERSION = "1.0"

_HEADER_FIELDS = (
    "project_code",
    "project_name",
    "location_date",
    "month_label",
    "signer1_name",
    "signer1_company",
    "signer2_name",
    "signer2_company",
)


def canonical_json(data: dict) -> str:
    """JSON determinístico: mesma entrada -> sempre a mesma string, ordem de
    chaves e espaçamento nunca importam pro hash."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_data_hash(data: dict) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def build_snapshot_data(pkg_data: dict) -> dict:
    """Reconstrói explicitamente só os campos de negócio a partir de
    `pkg_data` — proteção defensiva contra um chamador futuro que acabe
    incluindo os bytes base64 de `chart_image_bar`/`chart_image_pie` no dict
    (decorativos, derivados dos mesmos `groups`; inflam a coluna JSON sem
    ganho de reprodutibilidade)."""
    header = pkg_data.get("header") or {}
    groups = pkg_data.get("groups") or []
    return {
        "header": {field: header.get(field) for field in _HEADER_FIELDS},
        "groups": [
            {
                "name": g.get("name"),
                "performance": g.get("performance"),
                "activities": [
                    {"description": a.get("description"), "hours": a.get("hours")}
                    for a in (g.get("activities") or [])
                ],
            }
            for g in groups
        ],
        "pacote_scope": pkg_data.get("pacote_scope"),
        "language": pkg_data.get("language", "pt"),
        "has_chart_bar": bool(pkg_data.get("has_chart_bar")),
        "has_chart_pie": bool(pkg_data.get("has_chart_pie")),
    }


def snapshot_schema_version() -> str:
    return _SNAPSHOT_SCHEMA_VERSION


def _normalize_identity_part(value: str | None) -> str:
    return (value or "").strip().casefold()


def compute_identity_hash(report_number: str, scope: str | None, competence_label: str) -> str:
    """Identifica o "report" lógico por `(report_number, scope,
    competence_label)`, sem incluir quem gerou — ver plano de implementação
    (seção "Divergências do guia") pro raciocínio e o risco residual aceito
    de colisão entre relatórios pessoais com o mesmo texto por coincidência."""
    parts = "\x1f".join(
        _normalize_identity_part(v) for v in (report_number, scope, competence_label)
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def parse_competence_range(month_label: str) -> tuple[date | None, date | None]:
    """Best-effort: nunca levanta exceção, mesmo pra texto não reconhecido —
    `competence_start`/`competence_end` são metadado de conveniência (pra
    filtro/ordenação futuros), não uma fonte da verdade; `competence_label`
    (texto bruto) é o que sempre existe."""
    single = parse_month_label(month_label)
    if single:
        year, month = single
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    period = parse_period_label(month_label)
    if period:
        (start_year, start_month), (end_year, end_month) = period
        last_day = calendar.monthrange(end_year, end_month)[1]
        return date(start_year, start_month, 1), date(end_year, end_month, last_day)

    return None, None
