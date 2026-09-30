"""Um relatório: carregar, salvar rascunho, números, pular, reabrir e regenerar."""

from __future__ import annotations

import logging
from datetime import date

from ...services import auto_generation_store as store
from .. import builder, rules
from ..schemas import Draft
from .common import (
    EDITABLE,
    REGENERABLE,
    STATUS_APPROVED,
    STATUS_ERROR,
    STATUS_IN_REVIEW,
    STATUS_SENT,
    STATUS_SKIPPED,
    NotFound,
    WorkflowError,
    _badges,
    _load,
    _public,
    _transition,
)
from .custom_flow import _regenerate_custom
from .run import _apply_planned_number

logger = logging.getLogger(__name__)


def detail(report_id: str) -> dict:
    report = _load(report_id)
    return {
        **_public(report),
        "draft": report.get("draft_json"),
        "badges": report.get("badges_json") or {},
        "history_links": report.get("history_links_json") or [],
        "has_approved_payload": report.get("approved_payload_json") is not None,
        "events": [{k: e[k] for k in ("action", "actor_login", "actor_name", "comment", "metadata_json", "created_at")} for e in store.list_events(report_id)],
    }


def save_draft(report_id: str, draft: Draft, expected_version: int, actor: dict) -> int:
    data = draft.dump()
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report["status"] not in EDITABLE:
            raise WorkflowError(f"Relatório {report['status']} não pode mais ser editado.")
        return s.update_report(
            report_id, expected_version=expected_version, bump_version=True, draft_json=data, badges_json=_badges(data, report.get("source_hours"))
        )


def set_numbers(report_id: str, numbers: dict[str, str], expected_version: int, actor: dict) -> int:
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report["status"] not in EDITABLE:
            raise WorkflowError(f"Relatório {report['status']} não pode mais ser editado.")
        draft = dict(report["draft_json"] or {})
        packages = [dict(p) for p in draft.get("packages", [])]
        for pkg in packages:
            if pkg["id"] in numbers:
                pkg["project_code"] = numbers[pkg["id"]].strip()[:100]
        draft["packages"] = packages
        version = s.update_report(
            report_id, expected_version=expected_version, bump_version=True, draft_json=draft, badges_json=_badges(draft, report.get("source_hours"))
        )
        s.add_event(report_id, "numbers", actor, None, {"numbers": [p.get("project_code") for p in packages]})
    return version


def skip(report_id: str, actor: dict, comment: str = "") -> None:
    _transition(report_id, {STATUS_ERROR, *EDITABLE}, STATUS_SKIPPED, actor, "skipped", comment)


def reopen(report_id: str, actor: dict, comment: str = "") -> None:
    """Aprovado ou já ENVIADO volta pra revisão — o que foi pro histórico
    continua lá, e o envio anterior continua na linha do tempo (evento
    `sent`); a próxima aprovação vira uma versão nova, e ela precisa ser
    enviada de novo (o cliente só tem a versão antiga)."""
    _transition(
        report_id,
        {STATUS_APPROVED, STATUS_SENT},
        STATUS_IN_REVIEW,
        actor,
        "reopened",
        comment,
        approved_payload_json=None,
        approved_by=None,
        approved_at=None,
        sent_by=None,
        sent_at=None,
    )


def regenerate(report_id: str, actor: dict) -> None:
    """Monta o rascunho de novo a partir do Projectile (descarta as edições —
    a tela confirma antes). Mantém revisor e histórico de eventos."""
    report = _load(report_id)
    if report["status"] not in REGENERABLE:
        raise WorkflowError(f"Não dá pra regenerar um relatório {report['status']}.")
    if report.get("kind") == store.KIND_CUSTOM:
        return _regenerate_custom(report, actor)
    projects = {p["project_id"]: p for p in builder.month_projects(report["competence"])}
    project = projects.get(report["project_id"])
    if project is None:
        raise WorkflowError("O projeto não tem mais horas nessa competência.")
    config = rules.effective(store.get_config(), store.get_rules().get(report["family_key"]))
    rows = builder.fetch_rows_by_project(report["competence"], [report["project_id"]])[report["project_id"]]
    remembered = store.get_memories([report["family_key"]]).get(report["family_key"])
    draft = builder.build_draft(report["competence"], project, rows, config, remembered, date.today())
    if not draft["packages"]:
        raise WorkflowError("Nenhum lançamento com descrição encontrado pro projeto no mês.")
    _apply_planned_number(draft, store.get_planned_numbers(report["competence"]).get(report["project_id"]))
    with store.write_session() as s:
        current = s.get_report_for_update(report_id)
        if current is None or current["status"] not in REGENERABLE:
            raise WorkflowError("O relatório mudou de estado enquanto regenerava.")
        s.update_report(
            report_id,
            bump_version=True,
            status=STATUS_IN_REVIEW,
            draft_json=draft,
            source_hours=project["hours"],
            badges_json=_badges(draft, project["hours"]),
            error=None,
            project_name=project["name"][:255],
            client=project["client"][:255],
        )
        s.add_event(report_id, "regenerated", actor, None)
