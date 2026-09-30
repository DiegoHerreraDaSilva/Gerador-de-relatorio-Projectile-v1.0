"""Revisão por colaborador: candidatos, atribuição, 'Minhas revisões' e salvamento do revisor."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from ... import notifications, projectile_db
from ...services import auto_generation_store as store
from ...services.audit import record_event
from ..schemas import Draft
from .common import (
    EDITABLE,
    REVIEW_LIST_STATUSES,
    REVIEWER_EDITABLE,
    STATUS_APPROVED,
    STATUS_IN_REVIEW,
    STATUS_RETURNED,
    STATUS_REVIEWED,
    STATUS_SENT,
    InvalidRequest,
    NotFound,
    WorkflowError,
    _badges,
    _public,
)
from .drafts import detail

logger = logging.getLogger(__name__)


_REVIEWERS_TTL_SECONDS = 15 * 60

_REVIEWERS_WINDOW_DAYS = 180

_reviewers_cache: dict = {"at": 0.0, "items": None}


def reviewer_candidates() -> list[dict]:
    """Quem pode revisar: engenharia (CAD+CAE) com apontamento nos últimos 6
    meses e login no Projectile (sem login a pessoa não entra no app). Cache
    de 15 min, como o seletor do Dashboard de horas."""
    cached = _reviewers_cache["items"]
    if cached is not None and time.time() - _reviewers_cache["at"] < _REVIEWERS_TTL_SECONDS:
        return cached
    today = date.today()
    employees = projectile_db.fetch_engineering_employees((today - timedelta(days=_REVIEWERS_WINDOW_DAYS)).isoformat(), today.isoformat())
    seen: set[str] = set()
    items = []
    for employee in employees:
        login = (employee.get("login") or "").strip()
        if not login or login.casefold() in seen:
            continue
        seen.add(login.casefold())
        items.append({"login": login, "name": employee["name"]})
    _reviewers_cache.update(at=time.time(), items=items)
    return items


def _resolve_reviewer(login: str) -> dict:
    """O login vindo da tela nunca é gravado direto: tem que estar na lista
    (e o nome gravado é o do Projectile, não o do cliente)."""
    wanted = login.strip().casefold()
    match = next((r for r in reviewer_candidates() if r["login"].casefold() == wanted), None)
    if match is None:
        raise InvalidRequest("Colaborador não encontrado na engenharia (CAD/CAE).")
    return match


def assign_reviewer(report_id: str, login: str | None, actor: dict) -> dict:
    """Atribui (ou tira, com `login` vazio) o revisor. Relatório que já tinha
    sido mandado pra aprovação volta pra revisão se o revisor muda."""
    reviewer = _resolve_reviewer(login) if login and login.strip() else None
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report["status"] not in EDITABLE:
            raise WorkflowError(f"Não dá pra trocar o revisor de um relatório {report['status']}.")
        fields = {"reviewer_login": reviewer["login"] if reviewer else None, "reviewer_name": reviewer["name"] if reviewer else None}
        if (report.get("reviewer_login") or "").casefold() == (fields["reviewer_login"] or "").casefold():
            return {"status": report["status"], **fields}
        if reviewer and report["status"] == STATUS_REVIEWED:
            fields["status"] = STATUS_IN_REVIEW
        s.update_report(report_id, **fields)
        s.add_event(
            report_id,
            "assigned" if reviewer else "unassigned",
            actor,
            None,
            {"reviewer_login": fields["reviewer_login"], "reviewer_name": fields["reviewer_name"]},
        )
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action="auto_report_assigned",
        entity_type="auto_report",
        entity_id=report_id,
        source="auto_generation",
        metadata={"reviewer_login": fields["reviewer_login"]},
    )
    if reviewer:
        notifications.notify_reviewer_assigned(report, reviewer, actor)
    return {"status": fields.get("status", report["status"]), "reviewer_login": fields["reviewer_login"], "reviewer_name": fields["reviewer_name"]}


def return_to_reviewer(report_id: str, comment: str, actor: dict) -> None:
    """Gerente devolve o que o revisor mandou pra aprovação, dizendo o que
    precisa mudar (o revisor vê o comentário na lista e no editor)."""
    comment = (comment or "").strip()
    if not comment:
        raise InvalidRequest("Escreva o que precisa mudar — o revisor vê esse comentário.")
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report["status"] != STATUS_REVIEWED or not report.get("reviewer_login"):
            raise WorkflowError("Só dá pra devolver um relatório que o revisor mandou pra aprovação.")
        s.update_report(report_id, status=STATUS_RETURNED)
        s.add_event(report_id, "returned", actor, comment)
    notifications.notify_reviewer_returned(report, comment, actor)


def _is_assigned(report: dict, user: dict, competence_from: str | None = None) -> bool:
    """Atribuído a quem pede e dentro da janela dele (`competence_from`,
    "AAAA-MM", vem da rota — `api/period_access.py`; None = gerente)."""
    login = (user.get("login") or "").strip().casefold()
    if competence_from and report.get("competence", "") < competence_from:
        return False
    return bool(login) and (report.get("reviewer_login") or "").strip().casefold() == login


def _load_assigned(report_id: str, user: dict, competence_from: str | None = None) -> dict:
    """Relatório atribuído a quem pede — de outra pessoa (ou inexistente, ou
    fora da janela) é 404, não 403: não revela que o relatório existe."""
    report = store.get_report(report_id)
    if report is None or not _is_assigned(report, user, competence_from):
        raise NotFound(report_id)
    return report


_REVIEW_DONE_LIMIT = 20


def my_reviews(user: dict, competence_from: str | None = None) -> dict:
    """ "Minhas revisões": o que está com a pessoa (em revisão/devolvido), o
    que ela mandou e espera o gerente, e os últimos concluídos."""
    items = store.list_assigned(user.get("login") or "", REVIEW_LIST_STATUSES, competence_from)
    comments = store.latest_comments([i["id"] for i in items if i["status"] in (STATUS_REVIEWED, STATUS_RETURNED)], ("submitted", "returned"))
    out = [{**_without_blocks(_public(i)), "badges": i.get("badges_json") or {}, "last_comment": comments.get(i["id"])} for i in items]
    done = [i for i in out if i["status"] in (STATUS_APPROVED, STATUS_SENT)]
    done.sort(key=lambda i: i["updated_at"], reverse=True)
    return {
        "to_review": [i for i in out if i["status"] in REVIEWER_EDITABLE],
        "awaiting_approval": [i for i in out if i["status"] == STATUS_REVIEWED],
        "done": done[:_REVIEW_DONE_LIMIT],
    }


def review_summary(user: dict, is_manager: bool, competence_from: str | None = None) -> dict:
    """Contadores da sidebar: o que espera a revisão da pessoa e, pro
    gerente, o que espera a aprovação dele."""
    login = user.get("login") or ""
    return {
        "to_review": store.count_by_status(tuple(REVIEWER_EDITABLE), reviewer_login=login, competence_from=competence_from),
        # tudo o que já foi atribuído à pessoa (decide se o menu aparece)
        "assigned": store.count_by_status(REVIEW_LIST_STATUSES, reviewer_login=login, competence_from=competence_from),
        "awaiting_approval": store.count_by_status((STATUS_REVIEWED,)) if is_manager else None,
    }


def _without_blocks(item: dict) -> dict:
    """Os recortes (clientes, projetos, PESSOAS escolhidas) são do gerente: o
    revisor vê o período e o resumo, não a lista de quem entrou no recorte."""
    saved = item.get("scope_json")
    if saved:
        item = {**item, "scope_json": {k: v for k, v in saved.items() if k != "blocks"}}
    return item


def review_detail(report_id: str, user: dict, competence_from: str | None = None) -> dict:
    _load_assigned(report_id, user, competence_from)
    return _without_blocks(detail(report_id))


def _keep_manager_fields(data: dict, current: dict) -> dict:
    """O revisor mexe no conteúdo; número do relatório, arquivos e
    "incluir performance" são do gerente — ficam como estão no servidor."""
    numbers = {p.get("id"): (p.get("project_code", ""), p.get("suggested_code", "")) for p in current.get("packages", [])}
    packages = []
    for pkg in data.get("packages", []):
        code, suggested = numbers.get(pkg.get("id"), ("", pkg.get("suggested_code", "")))
        packages.append({**pkg, "project_code": code, "suggested_code": suggested})
    return {
        **data,
        "packages": packages,
        "formats": current.get("formats") or data.get("formats"),
        "include_performance": bool(current.get("include_performance")),
    }


def review_save(report_id: str, draft: Draft, expected_version: int, user: dict, competence_from: str | None = None) -> int:
    data = draft.dump()
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None or not _is_assigned(report, user, competence_from):
            raise NotFound(report_id)
        if report["status"] not in REVIEWER_EDITABLE:
            raise WorkflowError("Esse relatório já foi mandado pra aprovação — não dá mais pra editar.")
        data = _keep_manager_fields(data, report.get("draft_json") or {})
        return s.update_report(
            report_id, expected_version=expected_version, bump_version=True, draft_json=data, badges_json=_badges(data, report.get("source_hours"))
        )


def submit_review(report_id: str, user: dict, comment: str = "", competence_from: str | None = None) -> str:
    """Revisor terminou: manda pro gerente aprovar (`revisado`)."""
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None or not _is_assigned(report, user, competence_from):
            raise NotFound(report_id)
        if report["status"] not in REVIEWER_EDITABLE:
            raise WorkflowError("Esse relatório já foi mandado pra aprovação.")
        s.update_report(report_id, status=STATUS_REVIEWED)
        s.add_event(report_id, "submitted", user, (comment or "").strip() or None)
    record_event(
        actor_id=user.get("login", ""),
        actor_name=user.get("name", ""),
        action="auto_report_review_submitted",
        entity_type="auto_report",
        entity_id=report_id,
        source="auto_generation",
        metadata={"competence": report["competence"], "project_id": report["project_id"]},
    )
    notifications.notify_awaiting_approval(report, user)
    return STATUS_REVIEWED
