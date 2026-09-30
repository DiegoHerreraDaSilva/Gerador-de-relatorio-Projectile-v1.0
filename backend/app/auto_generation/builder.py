"""Monta o rascunho de um relatório automático a partir do Projectile.

Reproduz, no servidor, o que a busca por cliente faz hoje em duas metades:
`/parse-db-client` (`fetch_project_hours` → `group_hours`/`group_hours_by_project`
→ `build_parse_response`) e `FileUpload.applyParseResponse` +
`useReportStore.createInitialHeader` no navegador (performance 1, "Santo André,
dd.mm.aaaa", mês por extenso, empresas dos assinantes, `pacoteScope`). Os
defaults do navegador estão espelhados aqui de propósito — o teste de paridade
em `test_auto_generation.py` quebra se um dos lados mudar sozinho.

Projectile e cache do Painel acessados como ATRIBUTO do módulo
(`management._get_cached_rows`), nunca por `from import` — senão o
`monkeypatch` dos testes não alcança (ver CLAUDE.md, "Gotcha de teste")."""

from __future__ import annotations

import calendar
import re
import uuid
from datetime import date

from .. import management, projectile_db
from ..api.shared import build_parse_response
from ..projectile_db import group_hours, group_hours_by_project
from . import families, memory

MONTH_NAMES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_COMPETENCE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
DRAFT_SCHEMA = 1


class InvalidCompetence(ValueError):
    pass


def parse_competence(competence: str) -> tuple[int, int]:
    match = _COMPETENCE.match(competence or "")
    if not match:
        raise InvalidCompetence("Competência inválida, use AAAA-MM.")
    return int(match.group(1)), int(match.group(2))


def competence_range(competence: str) -> tuple[str, str]:
    year, month = parse_competence(competence)
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def month_label(competence: str) -> str:
    """ "2026-08" → "Agosto/2026" (mesmo formato de `createInitialHeader`)."""
    year, month = parse_competence(competence)
    return f"{MONTH_NAMES_PT[month - 1]}/{year}"


def location_date(location: str, today: date) -> str:
    return f"{location}, {today.day:02d}.{today.month:02d}.{today.year}"


def month_projects(competence: str) -> list[dict]:
    """Projetos (CAD+CAE) com horas na competência — as mesmas linhas do
    Painel/Diagnóstico (`management._get_cached_rows`, cache de 15 min)."""
    start, end = competence_range(competence)
    hours: dict[str, float] = {}
    for row in management._get_cached_rows(start, end):
        pid = row.get("project_id")
        value = float(row.get("horas") or 0)
        if pid and value > 0:
            hours[str(pid)] = hours.get(str(pid), 0.0) + value
    details = projectile_db.fetch_project_details(sorted(hours)) if hours else {}
    projects = []
    for pid, total in hours.items():
        info = details.get(pid)
        if not info:
            continue
        projects.append(
            {
                "project_id": pid,
                "name": families.clean(info.get("name")) or pid,
                "client": families.clean(info.get("client")) or "Sem cliente",
                "hours": round(total, 2),
            }
        )
    return sorted(projects, key=lambda p: (p["client"].casefold(), p["name"].casefold()))


def _new_id() -> str:
    return uuid.uuid4().hex


def _draft_packages(parsed: dict, mode: str) -> list[dict]:
    packages = []
    for pkg in parsed["packages"]:
        name = pkg.get("project_name") or pkg["key"]
        packages.append(
            {
                "id": _new_id(),
                "key": pkg["key"],
                # no modo "projeto" a chave é o project_id (muda todo mês) — a
                # memória casa pelo nome do projeto sem a data. É o nome do
                # PACOTE do rascunho, não o de um "projeto único": a geração
                # personalizada junta vários projetos num relatório só
                "source_key": families.normalize_key(pkg["key"] if mode == "pacote" else name),
                "project_code": "",
                "suggested_code": "",
                "project_name": name,
                "pacote_scope": pkg["key"] if mode == "pacote" else None,
                "language": "pt",
                "chart_bar": False,
                "chart_pie": False,
                "groups": [
                    {
                        "id": _new_id(),
                        "source_key": families.normalize_key(group["name"]),
                        "name": group["name"],
                        "performance": 1,
                        "activities": [
                            {
                                "id": _new_id(),
                                "source_key": families.normalize_key(activity["description"]),
                                "description": activity["description"],
                                "hours": activity["hours"],
                            }
                            for activity in group["activities"]
                        ],
                    }
                    for group in pkg["groups"]
                ],
            }
        )
    return packages


def draft_hours(draft: dict) -> float:
    return round(sum(a.get("hours") or 0 for p in draft.get("packages", []) for g in p.get("groups", []) for a in g.get("activities", [])), 3)


def period_label(start: str, end: str) -> str:
    """Rótulo do período do relatório, o mesmo que `buildPeriodLabel` (front)
    produz e que `generator.parse_period_label` lê de volta: "Agosto/2026" pra
    um mês, "Julho a Novembro/2026" no mesmo ano, "Dezembro/2025 a
    Fevereiro/2026" cruzando o ano. `start`/`end` são "AAAA-MM"."""
    if start == end:
        return month_label(start)
    (start_year, start_month), (end_year, end_month) = parse_competence(start), parse_competence(end)
    if start_year == end_year:
        return f"{MONTH_NAMES_PT[start_month - 1]} a {MONTH_NAMES_PT[end_month - 1]}/{end_year}"
    return f"{month_label(start)} a {month_label(end)}"


def _header(label: str, config: dict, today: date) -> dict:
    return {
        "location_date": location_date(config.get("location") or "Santo André", today),
        "month_label": label,
        "signer1_name": config.get("signer1_name", ""),
        "signer1_company": config.get("signer1_company", "Schwaben Engineering"),
        "signer2_name": config.get("signer2_name", ""),
        "signer2_company": config.get("signer2_company", "Mercedes-Benz do Brasil"),
    }


def _draft(mode: str, label: str, config: dict, today: date, packages, issues) -> dict:
    parsed = build_parse_response(packages, issues)
    return {
        "schema": DRAFT_SCHEMA,
        "mode": mode,
        "header": _header(label, config, today),
        # arquivo nunca mostra performance (`report_files.build_report_file`)
        "include_performance": False,
        "formats": list(config.get("formats") or ["xlsx"]),
        "packages": _draft_packages(parsed, mode),
        "issues": parsed["issues"],
        "memory_applied": False,
    }


def build_draft(competence: str, project: dict, rows: list[dict], config: dict, remembered: dict | None, today: date) -> dict:
    """Rascunho de UM projeto a partir das linhas dele (`fetch_project_hours`)."""
    mode = config.get("mode", "projeto")
    if mode == "projeto":
        packages, issues = group_hours_by_project(rows, {project["project_id"]: project["name"]})
    else:
        packages, issues = group_hours(rows, split_by_package=True)
    draft = _draft(mode, month_label(competence), config, today, packages, issues)
    draft["memory_applied"] = memory.apply(draft, remembered)
    return draft


def build_custom_draft(rows: list[dict], names: dict[str, str], label: str, unit: str, config: dict, today: date) -> dict:
    """Rascunho de um relatório PERSONALIZADO: as linhas podem vir de vários
    projetos (e de vários colaboradores), num período qualquer. `unit` diz o
    que vira "pacote" do relatório: "projeto" (um por projeto, o pacote de
    trabalho vira o grupo — `names` dá o nome de cada chave de projeto) ou
    "pacote" (um por pacote de trabalho, o prefixo da observação vira o grupo,
    como na busca manual em modo pacote). Sem memória: o relatório avulso não
    tem família."""
    if unit == "projeto":
        packages, issues = group_hours_by_project(rows, names)
    else:
        # `group_hours` chaveia só pelo nome do pacote de trabalho: roda por
        # projeto e junta, pra dois projetos com o mesmo nome de pacote não
        # se fundirem. (O número da linha nos avisos é o da linha DENTRO do
        # projeto.)
        by_project: dict[str, list[dict]] = {}
        for row in rows:
            by_project.setdefault(str(row.get("project_id") or ""), []).append(row)
        packages, issues = [], []
        for project_rows in by_project.values():
            found, found_issues = group_hours(project_rows, split_by_package=True)
            packages += found
            issues += found_issues
    return _draft(unit, label, config, today, packages, issues)


def fetch_rows_by_project(competence: str, project_ids: list[str]) -> dict[str, list[dict]]:
    """UMA consulta pra todos os projetos (o pool do Projectile tem 5
    conexões — uma por projeto enfileiraria dezenas)."""
    start, end = competence_range(competence)
    by_project: dict[str, list[dict]] = {pid: [] for pid in project_ids}
    if not project_ids:
        return by_project
    for row in projectile_db.fetch_project_hours(project_ids, start, end):
        pid = str(row.get("project_id"))
        if pid in by_project:
            by_project[pid].append(row)
    return by_project
