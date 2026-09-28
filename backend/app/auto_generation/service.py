"""Orquestração da geração automática: rodada por competência, rascunho,
números, aprovação e o que a tela lista.

Estados (`STATUS_*`), transições validadas aqui — nunca confiar no que a tela
mostra:
    gerando → em_revisao → revisado → aprovado → enviado
       ↓          ↑   ↓        ↓
      erro    devolvido ←──────┘
    pulado (desativado / fechado) · o gerente aprova direto de em_revisao

Revisão por colaborador: o gerente atribui um revisor (`reviewer_login`); ele
vê o relatório em "Minhas revisões" (`/my-reviews/*`, só os atribuídos a ele —
o resto é 404), edita em `em_revisao`/`devolvido` e manda pra aprovação
(`revisado`). O gerente aprova ou devolve com um comentário (`devolvido`).
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import date, timedelta

from ulid import ULID

import re

from .. import email_ingest, management, projectile_db
from ..generator import NonFiniteValueError
from ..services import auto_generation_store as store
from ..services.audit import record_event
from ..services.report_files import (
    FORMAT_MEDIA_TYPES,
    GeneratePayload,
    build_report_file,
    dedupe_name,
    persistence_pkg_data,
    sanitized_file_name,
)
from ..services.report_persistence import GenerationGuard, finish_generation_failure, finish_generation_success
from . import builder, families, memory, rules
from .schemas import Draft

logger = logging.getLogger(__name__)

STATUS_GENERATING = "gerando"
STATUS_ERROR = "erro"
STATUS_IN_REVIEW = "em_revisao"
STATUS_REVIEWED = "revisado"
STATUS_RETURNED = "devolvido"
STATUS_APPROVED = "aprovado"
STATUS_SENT = "enviado"
STATUS_SKIPPED = "pulado"
STATUSES = (
    STATUS_GENERATING, STATUS_ERROR, STATUS_IN_REVIEW, STATUS_REVIEWED, STATUS_RETURNED,
    STATUS_APPROVED, STATUS_SENT, STATUS_SKIPPED,
)
EDITABLE = {STATUS_IN_REVIEW, STATUS_REVIEWED, STATUS_RETURNED}
APPROVABLE = EDITABLE
# o que o REVISOR pode editar (depois de mandar pra aprovação, só o gerente mexe)
REVIEWER_EDITABLE = {STATUS_IN_REVIEW, STATUS_RETURNED}
# o que aparece em "Minhas revisões"
REVIEW_LIST_STATUSES = (STATUS_IN_REVIEW, STATUS_RETURNED, STATUS_REVIEWED, STATUS_APPROVED, STATUS_SENT)
REGENERABLE = {STATUS_ERROR, STATUS_SKIPPED, *EDITABLE}
# enviar de novo (esqueceu alguém) é permitido
SENDABLE = {STATUS_APPROVED, STATUS_SENT}

# rodada "presa" (processo morreu no meio) libera depois disso
_STALE_RUN = timedelta(minutes=30)


class WorkflowError(Exception):
    """Ação que o estado atual não permite (vira 409 na rota)."""


class NotFound(Exception):
    pass


class RunInProgress(Exception):
    pass


class InvalidRequest(Exception):
    """Pedido com dado inválido (revisor fora da lista, devolução sem
    comentário) — vira 400 com a mensagem."""


class ApprovalRejected(Exception):
    """Número/assinatura/conteúdo inválido na aprovação (vira 400)."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# --- configuração -------------------------------------------------------------


def get_configuration() -> dict:
    config = store.get_config()
    rule_list = []
    labels = _family_labels()
    for family_key, cfg in sorted(store.get_rules().items()):
        rule_list.append({"family_key": family_key, "label": labels.get(family_key, family_key), "config": cfg})
    return {"defaults": rules.DEFAULTS, "config": config, "effective": rules.effective(config, None), "rules": rule_list}


def set_global_config(raw: dict, actor: dict) -> dict:
    config = rules.validate_global(raw)
    with store.write_session() as s:
        s.set_config(config)
    return config


def set_family_rule(family_key: str, raw: dict | None, actor: dict) -> dict:
    config = rules.validate_rule(raw or {})
    config.pop("reviewer_name", None)
    if config.get("reviewer_login", "").strip():
        reviewer = _resolve_reviewer(config["reviewer_login"])
        config["reviewer_login"], config["reviewer_name"] = reviewer["login"], reviewer["name"]
    else:
        config.pop("reviewer_login", None)
    with store.write_session() as s:
        s.set_rule(family_key, config, actor.get("login", ""))
    return config


def set_family_override(project_id: str, family_key: str | None, actor: dict) -> None:
    with store.write_session() as s:
        s.set_family_override(project_id, family_key, actor.get("login", ""))


def _family_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for run in store.list_runs():
        for item in store.list_reports(run["competence"]):
            labels.setdefault(item["family_key"], families.family_label(item["project_name"]))
    return labels


def _family_for(project: dict, overrides: dict[str, str]) -> str:
    return overrides.get(project["project_id"]) or families.family_key(project["client"], project["name"])


# --- resumo leve do rascunho (vai pra lista sem carregar o rascunho inteiro) ---


def _badges(draft: dict | None, source_hours: float | None = None, extra: dict | None = None) -> dict:
    """`source_hours` = total do projeto no Projectile na geração; o que o
    rascunho tem a menos são linhas SEM DESCRIÇÃO (viram aviso no editor, como
    na busca manual) — "X h sem descrição" na lista, pro revisor não aprovar
    sem ver."""
    badges = dict(extra or {})
    if draft:
        if source_hours is not None:
            missing = round(source_hours - builder.draft_hours(draft), 2)
            if missing > 0.01:
                badges["missing_hours"] = missing
        badges["packages"] = len(draft.get("packages", []))
        badges["package_ids"] = [p.get("id") for p in draft.get("packages", [])]
        badges["package_names"] = [p.get("project_name", "") for p in draft.get("packages", [])]
        # modo em que o rascunho FOI gerado (a configuração pode ter mudado depois)
        badges["mode"] = draft.get("mode", "pacote")
        badges["numbers"] = [p.get("project_code", "") for p in draft.get("packages", [])]
        badges["suggested"] = [p.get("suggested_code", "") for p in draft.get("packages", [])]
        badges["memory_applied"] = bool(draft.get("memory_applied"))
        badges["issues"] = len(draft.get("issues", []))
    return badges


# --- rodada -------------------------------------------------------------------


def start_run(competence: str, actor: dict, project_ids: list[str] | None = None, background: bool = True) -> dict:
    """Reserva a rodada da competência (idempotente: UNIQUE competência +
    `FOR UPDATE`) e gera os rascunhos que faltam — em thread, pra rota
    responder na hora; a tela acompanha pelo status da rodada."""
    builder.parse_competence(competence)
    now = store.utcnow()
    with store.write_session() as s:
        run = s.get_run_for_update(competence)
        if run and run["status"] == "running" and now - run["started_at"] < _STALE_RUN:
            raise RunInProgress(competence)
        if run is None:
            run = {"id": str(ULID()), "competence": competence, "status": "running",
                   "triggered_by": actor.get("login"), "started_at": now}
            s.insert_run(run)
        else:
            s.update_run(run["id"], status="running", triggered_by=actor.get("login"), started_at=now,
                         finished_at=None, error=None)
            run = {**run, "status": "running", "started_at": now}
    args = (run["id"], competence, actor, project_ids or [])
    if background:
        threading.Thread(target=_execute_run, args=args, daemon=True, name=f"auto-run-{competence}").start()
    else:
        _execute_run(*args)
    return run


def _execute_run(run_id: str, competence: str, actor: dict, project_ids: list[str]) -> None:
    counts: dict[str, int] = {}
    try:
        projects = builder.month_projects(competence)
        if project_ids:
            wanted = set(project_ids)
            projects = [p for p in projects if p["project_id"] in wanted]
        with store.write_session() as s:
            existing = s.existing_project_ids(competence)
        projects = [p for p in projects if p["project_id"] not in existing]

        global_config = store.get_config()
        family_rules = store.get_rules()
        overrides = store.get_family_overrides()
        closed = management.get_closed_registry()
        closed_projects = set(closed.get("closed_projects", []))
        closed_clients = set(closed.get("closed_clients", []))
        keys = {p["project_id"]: _family_for(p, overrides) for p in projects}
        memories = store.get_memories(sorted(set(keys.values())))
        rows_by_project = builder.fetch_rows_by_project(competence, [p["project_id"] for p in projects])
        today = date.today()

        for project in projects:
            status = _generate_one(
                run_id, competence, project, keys[project["project_id"]], global_config, family_rules,
                memories, rows_by_project.get(project["project_id"], []), closed_projects, closed_clients, today,
            )
            counts[status] = counts.get(status, 0) + 1
        final = {"status": "done", "error": None}
    except Exception as e:  # Projectile/reports_db fora do ar: a rodada falha, os já gravados ficam
        logger.exception("Rodada de geração automática %s falhou", competence)
        final = {"status": "failed", "error": str(e)[:2000]}
    try:
        with store.write_session() as s:
            s.update_run(run_id, finished_at=store.utcnow(), counts_json=counts, **final)
    except Exception:
        logger.exception("Não consegui fechar a rodada %s", competence)


def _generate_one(run_id, competence, project, family_key, global_config, family_rules, memories, rows,
                  closed_projects, closed_clients, today) -> str:
    """Um projeto — erro aqui vira `erro` SÓ nele, a rodada continua."""
    base = {
        "id": str(ULID()), "run_id": run_id, "competence": competence, "project_id": project["project_id"],
        "family_key": family_key, "project_name": project["name"][:255], "client": project["client"][:255],
        "draft_version": 1,
    }
    config = rules.effective(global_config, family_rules.get(family_key))
    try:
        if project["project_id"] in closed_projects or project["client"] in closed_clients:
            report = {**base, "status": STATUS_SKIPPED, "badges_json": {"skip_reason": "fechado no Diagnóstico"}}
            event = ("skipped", "Projeto/cliente fechado no Diagnóstico.")
        elif not config.get("enabled", True):
            report = {**base, "status": STATUS_SKIPPED, "badges_json": {"skip_reason": "desativado na configuração"}}
            event = ("skipped", "Família desativada na configuração.")
        else:
            draft = builder.build_draft(competence, project, rows, config, memories.get(family_key), today)
            if not draft["packages"]:
                raise ValueError("nenhum lançamento com descrição encontrado pro projeto no mês")
            report = {
                **base, "status": STATUS_IN_REVIEW, "draft_json": draft,
                "source_hours": project["hours"], "badges_json": _badges(draft, project["hours"]),
            }
            # revisor da configuração do projeto; sem ele, quem revisou o último
            # relatório aprovado da família — o rascunho já nasce atribuído
            remembered = (
                {"login": config["reviewer_login"], "name": config.get("reviewer_name")}
                if config.get("reviewer_login") else (memories.get(family_key) or {}).get("reviewer") or {}
            )
            if remembered.get("login"):
                report["reviewer_login"] = remembered["login"][:100]
                report["reviewer_name"] = (remembered.get("name") or remembered["login"])[:255]
            event = ("generated", None)
    except Exception as e:
        logger.exception("Geração automática falhou pro projeto %s", project["project_id"])
        report = {**base, "status": STATUS_ERROR, "error": str(e)[:2000]}
        event = ("error", str(e)[:500])
    with store.write_session() as s:
        s.insert_report(report)
        s.add_event(report["id"], event[0], {"login": "sistema", "name": "Geração automática"}, event[1])
    return report["status"]


# --- o que a tela lista --------------------------------------------------------


def competence_view(competence: str) -> dict:
    builder.parse_competence(competence)
    run = store.get_run(competence)
    items = store.list_reports(competence)
    try:
        current = {p["project_id"]: p for p in builder.month_projects(competence)}
    except Exception:  # Projectile fora do ar: a lista ainda aparece, sem "horas agora"
        logger.warning("Horas atuais indisponíveis pra %s", competence, exc_info=True)
        current = None
    items = _backfill_badges(items)
    listed = set()
    out = []
    for item in items:
        listed.add(item["project_id"])
        hours_now = current.get(item["project_id"], {}).get("hours", 0.0) if current is not None else None
        badges = dict(item.get("badges_json") or {})
        if (
            hours_now is not None and item.get("source_hours") is not None
            and item["status"] not in (STATUS_SENT, STATUS_SKIPPED, STATUS_ERROR)
            and abs(hours_now - item["source_hours"]) > 0.01
        ):
            badges["hours_changed"] = True
        out.append({**_public(item), "hours_now": hours_now, "badges": badges})
    # configuração individual de cada projeto (guardada pela família, pra
    # valer nos meses seguintes do mesmo trabalho) e o que vale de fato
    global_config = store.get_config()
    family_rules = store.get_rules()
    comments = store.latest_comments(
        [i["id"] for i in out if i["status"] in (STATUS_REVIEWED, STATUS_RETURNED)], ("submitted", "returned"),
    )
    sends = store.latest_comments([i["id"] for i in out if i["status"] == STATUS_SENT], ("sent",))
    for item in out:
        item["rule"] = family_rules.get(item["family_key"], {})
        item["effective"] = rules.effective(global_config, item["rule"])
        item["last_comment"] = comments.get(item["id"])
        sent = sends.get(item["id"])
        item["last_sent"] = {"to": (sent.get("metadata") or {}).get("to", []), "cc": (sent.get("metadata") or {}).get("cc", []),
                             "actor_name": sent["actor_name"], "created_at": sent["created_at"]} if sent else None
    counts: dict[str, int] = {}
    for item in out:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    new_projects = [p for p in (current or {}).values() if p["project_id"] not in listed] if run else []
    return {
        "competence": competence,
        "month_label": builder.month_label(competence),
        "run": _public_run(run),
        "items": out,
        "counts": counts,
        "new_projects": sorted(new_projects, key=lambda p: p["name"].casefold()),
    }


def _backfill_badges(items: list[dict]) -> list[dict]:
    """Rascunho gerado antes de um campo novo do resumo (`mode`,
    `package_names`) — recalcula uma vez a partir do rascunho e grava."""
    out = []
    for item in items:
        badges = item.get("badges_json") or {}
        if item["status"] in (STATUS_SKIPPED, STATUS_ERROR) or "mode" in badges:
            out.append(item)
            continue
        report = store.get_report(item["id"])
        draft = (report or {}).get("draft_json")
        if not draft:
            out.append(item)
            continue
        fresh = {**badges, **_badges(draft, item.get("source_hours"))}
        with store.write_session() as s:
            s.update_report(item["id"], badges_json=fresh)
        out.append({**item, "badges_json": fresh})
    return out


def preview(competence: str) -> dict:
    """Mês em andamento: quais projetos têm horas até agora e o que
    aconteceria com cada um — nada é gravado."""
    projects = builder.month_projects(competence)
    overrides = store.get_family_overrides()
    global_config = store.get_config()
    family_rules = store.get_rules()
    closed = management.get_closed_registry()
    memories = store.get_memories(sorted({_family_for(p, overrides) for p in projects}))
    out = []
    for p in projects:
        key = _family_for(p, overrides)
        config = rules.effective(global_config, family_rules.get(key))
        if p["project_id"] in closed.get("closed_projects", []) or p["client"] in closed.get("closed_clients", []):
            planned = "fechado"
        elif not config.get("enabled", True):
            planned = "desativado"
        else:
            planned = "sera_gerado"
        out.append({**p, "family_key": key, "family_label": families.family_label(p["name"]), "planned": planned,
                    "mode": config.get("mode"), "rule": family_rules.get(key, {}), "effective": config,
                    # quem revisou o último aprovado (vale se a configuração não tiver revisor)
                    "remembered_reviewer": (memories.get(key) or {}).get("reviewer")})
    return {"competence": competence, "month_label": builder.month_label(competence), "projects": out}


def list_competences(today: date | None = None) -> dict:
    today = today or date.today()
    current = f"{today.year:04d}-{today.month:02d}"
    previous_month = date(today.year, today.month, 1) - timedelta(days=1)
    previous = f"{previous_month.year:04d}-{previous_month.month:02d}"
    runs = [_public_run(r) for r in store.list_runs()]
    return {"current": current, "previous": previous, "runs": runs}


def _public(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("draft_json", "approved_payload_json", "ai_original_json",
                                                        "badges_json", "history_links_json")}


def _public_run(run: dict | None) -> dict | None:
    if not run:
        return None
    return {k: run.get(k) for k in ("id", "competence", "status", "triggered_by", "started_at", "finished_at",
                                     "counts_json", "error")}


# --- um relatório ----------------------------------------------------------------


def _load(report_id: str) -> dict:
    report = store.get_report(report_id)
    if report is None:
        raise NotFound(report_id)
    return report


def detail(report_id: str) -> dict:
    report = _load(report_id)
    return {
        **_public(report),
        "draft": report.get("draft_json"),
        "badges": report.get("badges_json") or {},
        "history_links": report.get("history_links_json") or [],
        "has_approved_payload": report.get("approved_payload_json") is not None,
        "events": [
            {k: e[k] for k in ("action", "actor_login", "actor_name", "comment", "metadata_json", "created_at")}
            for e in store.list_events(report_id)
        ],
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
            report_id, expected_version=expected_version, bump_version=True,
            draft_json=data, badges_json=_badges(data, report.get("source_hours")),
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
            report_id, expected_version=expected_version, bump_version=True,
            draft_json=draft, badges_json=_badges(draft, report.get("source_hours")),
        )
        s.add_event(report_id, "numbers", actor, None, {"numbers": [p.get("project_code") for p in packages]})
    return version


def _transition(report_id: str, allowed: set[str], new_status: str, actor: dict, action: str,
                comment: str | None = None, **fields) -> None:
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report["status"] not in allowed:
            raise WorkflowError(f"Não dá pra {action} um relatório {report['status']}.")
        s.update_report(report_id, bump_version=True, status=new_status, **fields)
        s.add_event(report_id, action, actor, comment or None)


def skip(report_id: str, actor: dict, comment: str = "") -> None:
    _transition(report_id, {STATUS_ERROR, *EDITABLE}, STATUS_SKIPPED, actor, "skipped", comment)


def reopen(report_id: str, actor: dict, comment: str = "") -> None:
    """Aprovado (ainda não enviado) volta pra revisão — o que foi pro
    histórico continua lá; a próxima aprovação vira uma versão nova."""
    _transition(report_id, {STATUS_APPROVED}, STATUS_IN_REVIEW, actor, "reopened", comment,
                approved_payload_json=None, approved_by=None, approved_at=None)


def regenerate(report_id: str, actor: dict) -> None:
    """Monta o rascunho de novo a partir do Projectile (descarta as edições —
    a tela confirma antes). Mantém revisor e histórico de eventos."""
    report = _load(report_id)
    if report["status"] not in REGENERABLE:
        raise WorkflowError(f"Não dá pra regenerar um relatório {report['status']}.")
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
    with store.write_session() as s:
        current = s.get_report_for_update(report_id)
        if current is None or current["status"] not in REGENERABLE:
            raise WorkflowError("O relatório mudou de estado enquanto regenerava.")
        s.update_report(
            report_id, bump_version=True, status=STATUS_IN_REVIEW, draft_json=draft,
            source_hours=project["hours"], badges_json=_badges(draft, project["hours"]), error=None,
            project_name=project["name"][:255], client=project["client"][:255],
        )
        s.add_event(report_id, "regenerated", actor, None)


# --- revisão por colaborador -------------------------------------------------------

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
    employees = projectile_db.fetch_engineering_employees(
        (today - timedelta(days=_REVIEWERS_WINDOW_DAYS)).isoformat(), today.isoformat(),
    )
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
        fields = {
            "reviewer_login": reviewer["login"] if reviewer else None,
            "reviewer_name": reviewer["name"] if reviewer else None,
        }
        if (report.get("reviewer_login") or "").casefold() == (fields["reviewer_login"] or "").casefold():
            return {"status": report["status"], **fields}
        if reviewer and report["status"] == STATUS_REVIEWED:
            fields["status"] = STATUS_IN_REVIEW
        s.update_report(report_id, **fields)
        s.add_event(report_id, "assigned" if reviewer else "unassigned", actor, None,
                    {"reviewer_login": fields["reviewer_login"], "reviewer_name": fields["reviewer_name"]})
    record_event(
        actor_id=actor.get("login", ""), actor_name=actor.get("name", ""), action="auto_report_assigned",
        entity_type="auto_report", entity_id=report_id, source="auto_generation",
        metadata={"reviewer_login": fields["reviewer_login"]},
    )
    return {"status": fields.get("status", report["status"]), "reviewer_login": fields["reviewer_login"],
            "reviewer_name": fields["reviewer_name"]}


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
    """"Minhas revisões": o que está com a pessoa (em revisão/devolvido), o
    que ela mandou e espera o gerente, e os últimos concluídos."""
    items = store.list_assigned(user.get("login") or "", REVIEW_LIST_STATUSES, competence_from)
    comments = store.latest_comments(
        [i["id"] for i in items if i["status"] in (STATUS_REVIEWED, STATUS_RETURNED)], ("submitted", "returned"),
    )
    out = [
        {**_public(i), "badges": i.get("badges_json") or {}, "last_comment": comments.get(i["id"])}
        for i in items
    ]
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


def review_detail(report_id: str, user: dict, competence_from: str | None = None) -> dict:
    _load_assigned(report_id, user, competence_from)
    return detail(report_id)


def _keep_manager_fields(data: dict, current: dict) -> dict:
    """O revisor mexe no conteúdo; número do relatório, arquivos e
    "incluir performance" são do gerente — ficam como estão no servidor."""
    numbers = {p.get("id"): (p.get("project_code", ""), p.get("suggested_code", "")) for p in current.get("packages", [])}
    packages = []
    for pkg in data.get("packages", []):
        code, suggested = numbers.get(pkg.get("id"), ("", pkg.get("suggested_code", "")))
        packages.append({**pkg, "project_code": code, "suggested_code": suggested})
    return {
        **data, "packages": packages,
        "formats": current.get("formats") or data.get("formats"),
        "include_performance": bool(current.get("include_performance")),
    }


def review_save(report_id: str, draft: Draft, expected_version: int, user: dict,
                competence_from: str | None = None) -> int:
    data = draft.dump()
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None or not _is_assigned(report, user, competence_from):
            raise NotFound(report_id)
        if report["status"] not in REVIEWER_EDITABLE:
            raise WorkflowError("Esse relatório já foi mandado pra aprovação — não dá mais pra editar.")
        data = _keep_manager_fields(data, report.get("draft_json") or {})
        return s.update_report(
            report_id, expected_version=expected_version, bump_version=True,
            draft_json=data, badges_json=_badges(data, report.get("source_hours")),
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
        actor_id=user.get("login", ""), actor_name=user.get("name", ""), action="auto_report_review_submitted",
        entity_type="auto_report", entity_id=report_id, source="auto_generation",
        metadata={"competence": report["competence"], "project_id": report["project_id"]},
    )
    return STATUS_REVIEWED


# --- envio ao cliente ---------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_RECIPIENTS = 20
# um envio por relatório de cada vez (duplo clique não manda dois e-mails)
_sending: set[str] = set()
_sending_lock = threading.Lock()


def _default_texts(report: dict) -> tuple[str, str]:
    """Mesmo assunto/mensagem padrão do envio manual (`SendReportModal`)."""
    frozen = report.get("approved_payload_json") or {}
    packages = frozen.get("packages") or []
    month = (packages[0].get("header") or {}).get("month_label") if packages else builder.month_label(report["competence"])
    name = (packages[0].get("header") or {}).get("project_name") if len(packages) == 1 else report["project_name"]
    return (
        f"Relatório de Horas - {name} - {month}",
        f"Segue em anexo o relatório de horas do projeto {name} referente a {month}.",
    )


def send_defaults(report_id: str, actor: dict) -> dict:
    """O que o modal de envio já abre preenchido: destinatários do último
    envio da família, assunto/mensagem padrão, os anexos (do payload
    congelado) e se o envio vai contar no Diagnóstico."""
    report = _load(report_id)
    if report["status"] not in SENDABLE:
        raise WorkflowError("Só dá pra enviar um relatório aprovado.")
    remembered = (store.get_memories([report["family_key"]]).get(report["family_key"]) or {}).get("recipients") or {}
    subject, message = _default_texts(report)
    sender = (actor.get("email") or "").strip()
    return {
        "to": remembered.get("to", []), "cc": remembered.get("cc", []),
        "subject": subject, "message": message,
        "files": [name for name, _ in approved_files(report_id)],
        "sender": sender,
        # o Diagnóstico só marca "Enviado" pra remetentes de ALBERTO_EMAIL
        "counts_in_diagnostics": sender.casefold() in {e.casefold() for e in email_ingest.diagnostics_sender_emails()},
    }


def _clean_addresses(raw: list[str], label: str) -> list[str]:
    out: list[str] = []
    for address in (a.strip() for a in raw):
        if not address:
            continue
        if not _EMAIL_RE.match(address):
            raise InvalidRequest(f"E-mail inválido em {label}: {address}")
        if address.casefold() not in {a.casefold() for a in out}:
            out.append(address)
    if len(out) > _MAX_RECIPIENTS:
        raise InvalidRequest(f"No máximo {_MAX_RECIPIENTS} endereços em {label}.")
    return out


def _pick_formats(files: list[tuple[str, bytes]], formats: list[str] | None, project_name: str) -> list[tuple[str, bytes]]:
    """Só os anexos dos formatos escolhidos no envio (XLSX, PDF ou os dois),
    entre os que foram aprovados."""
    if not formats:
        return files
    wanted = {f.lower() for f in formats}
    picked = [(name, data) for name, data in files if name.rsplit(".", 1)[-1].lower() in wanted]
    if not picked:
        raise InvalidRequest(
            f"\"{project_name}\" não tem arquivo aprovado nesse formato — escolha XLSX, PDF ou os dois entre os aprovados."
        )
    return picked


def send_report(report_id: str, to: list[str], cc: list[str], subject: str, message: str, actor: dict,
                formats: list[str] | None = None) -> dict:
    """Um relatório, um e-mail (ver `send_reports`)."""
    return send_reports([report_id], to, cc, subject, message, actor, formats)


def send_reports(report_ids: list[str], to: list[str], cc: list[str], subject: str, message: str, actor: dict,
                 formats: list[str] | None = None) -> dict:
    """Manda os arquivos APROVADOS (payload congelado — exatamente o que o
    gerente baixa em "Arquivos") de um ou mais relatórios num ÚNICO e-mail,
    pela caixa de quem está logado, com a caixa do agente em cópia, como o
    `/send-report`. Cada arquivo é um anexo próprio (nunca zipado). Só marca
    `enviado` depois que o Graph aceitou; se ele falhar, todos continuam
    aprovados. Relatório sem arquivo no formato escolhido recusa o e-mail
    inteiro (não sai um e-mail pela metade)."""
    ids = list(dict.fromkeys(report_ids))
    if not ids or len(ids) > _MAX_BULK:
        raise InvalidRequest(f"Escolha de 1 a {_MAX_BULK} relatórios.")
    sender = (actor.get("email") or "").strip()
    if not sender:
        raise InvalidRequest("Seu usuário não tem e-mail cadastrado no Projectile — não é possível enviar.")
    to_list = _clean_addresses(to, "Para")
    cc_list = [a for a in _clean_addresses(cc, "Cópia") if a.casefold() not in {t.casefold() for t in to_list}]
    if not to_list:
        raise InvalidRequest("Informe pelo menos um destinatário.")
    with _sending_lock:
        if any(i in _sending for i in ids):
            raise WorkflowError("Um desses relatórios já está sendo enviado.")
        _sending.update(ids)
    try:
        reports = [_load(i) for i in ids]
        for report in reports:
            if report["status"] not in SENDABLE:
                raise WorkflowError(f"\"{report['project_name']}\" não está aprovado.")
        attachments: list[tuple[str, bytes]] = []
        names_by_report: dict[str, list[str]] = {}
        used: set[str] = set()
        for report in reports:
            names_by_report[report["id"]] = []
            for name, data in _pick_formats(approved_files(report["id"]), formats, report["project_name"]):
                unique = dedupe_name(name, used)
                used.add(unique)
                attachments.append((unique, data))
                names_by_report[report["id"]].append(unique)
        email_ingest.send_report_email(
            sender_email=sender, to_email=to_list, cc_emails=cc_list,
            subject=subject.strip(), body_text=message, attachments=attachments,
        )
        # leitura FORA da transação de escrita (ver `approve`)
        families_sent = sorted({r["family_key"] for r in reports})
        previous = store.get_memories(families_sent)
        now = store.utcnow()
        with store.write_session() as s:
            for report in reports:
                s.update_report(report["id"], status=STATUS_SENT, sent_by=actor.get("login"), sent_at=now)
                s.add_event(report["id"], "sent", actor, None, {
                    "to": to_list, "cc": cc_list, "subject": subject.strip(), "files": names_by_report[report["id"]],
                    # enviado junto com outros no mesmo e-mail
                    "combined_with": [i for i in ids if i != report["id"]],
                })
            for family in families_sent:
                source = next(r["id"] for r in reports if r["family_key"] == family)
                s.set_memory(family, {**(previous.get(family) or {}), "recipients": {"to": to_list, "cc": cc_list}}, source)
    finally:
        with _sending_lock:
            _sending.difference_update(ids)
    for report in reports:
        record_event(
            actor_id=actor.get("login", ""), actor_name=actor.get("name", ""), action="auto_report_sent",
            entity_type="auto_report", entity_id=report["id"], source="auto_generation",
            metadata={"competence": report["competence"], "project_id": report["project_id"], "to": to_list,
                      "cc": cc_list, "combined": len(ids) > 1},
        )
    return {"status": STATUS_SENT, "sent_at": now, "sent": ids}


# --- aprovação -------------------------------------------------------------------


def _pattern_label(pattern: str) -> str:
    """Formato do número pra gente ler — o modelo com `#` por dígito
    ("SE.##.###"), nunca a expressão regular crua."""
    model = rules.pattern_to_model(pattern)
    if model is None:
        return f"configurado no padrão geral ({pattern})"
    return f"{model} (ex.: SE.26.053)" if pattern == rules.DEFAULT_NUMBER_PATTERN else model


def _number_errors(report: dict, payload: GeneratePayload, pattern: str) -> tuple[list[str], list[str]]:
    import re

    errors: list[str] = []
    warnings: list[str] = []
    codes = [p.header.project_code.strip() for p in payload.packages]
    regex = re.compile(pattern)
    for pkg, code in zip(payload.packages, codes):
        if not code:
            errors.append(f"Falta o número do relatório de \"{pkg.header.project_name}\".")
        elif not regex.fullmatch(code):
            errors.append(f"Número \"{code}\" fora do formato {_pattern_label(pattern)}.")
    duplicated = {c for c in codes if c and codes.count(c) > 1}
    if duplicated:
        errors.append(f"Número repetido no mesmo relatório: {', '.join(sorted(duplicated))}.")
    for other in store.list_drafts(report["competence"]):
        if other["id"] == report["id"] or other["status"] == STATUS_SKIPPED:
            continue
        other_codes = {p.get("project_code", "").strip() for p in (other.get("draft_json") or {}).get("packages", [])}
        clash = sorted({c for c in codes if c} & other_codes)
        if clash:
            errors.append(f"Número {', '.join(clash)} já está em outro relatório desta competência.")
    wanted = [c for c in codes if c]
    if wanted:
        rows = store.find_history_numbers(wanted)
        month = payload.packages[0].header.month_label
        names = {p.header.project_code.strip(): p.header.project_name for p in payload.packages}
        for number, project_name, competence_label in rows:
            mine = names.get(number, "")
            if families.normalize_key(project_name) == families.normalize_key(mine):
                continue
            if competence_label == month:
                errors.append(f"O número {number} já foi usado em {month} por \"{project_name}\".")
            else:
                warnings.append(f"O número {number} já foi usado em {competence_label} por \"{project_name}\".")
    return errors, sorted(set(warnings))


def _payload_hours(payload: GeneratePayload) -> float:
    return round(sum(a.hours or 0 for p in payload.packages for g in p.groups for a in g.activities), 3)


def approve(report_id: str, raw_payload: dict, expected_version: int, actor: dict) -> dict:
    """Só a partir do editor aberto (os gráficos vêm desenhados pelo
    navegador). Valida número e conteúdo, grava no histórico (fail-open, como
    o `/generate`), congela o payload pro envio e atualiza a memória da
    família pro mês seguinte."""
    report = _load(report_id)
    if report["status"] not in APPROVABLE:
        raise WorkflowError(f"Não dá pra aprovar um relatório {report['status']}.")
    if report["draft_version"] != expected_version:
        raise store.VersionConflict(report["draft_version"])
    # número vazio antes do modelo (que exige número): mensagem clara, não 422
    missing = [
        (pkg.get("header") or {}).get("project_name", "")
        for pkg in (raw_payload.get("packages") or [])
        if isinstance(pkg, dict) and not str((pkg.get("header") or {}).get("project_code") or "").strip()
    ]
    if missing:
        raise ApprovalRejected([f"Falta o número do relatório de \"{name}\"." for name in missing])
    payload = GeneratePayload.model_validate(raw_payload)
    draft = report.get("draft_json") or {}
    errors: list[str] = []
    if len(payload.packages) != len(draft.get("packages", [])):
        errors.append("O conteúdo aprovado não corresponde ao rascunho salvo — recarregue o relatório.")
    elif abs(_payload_hours(payload) - builder.draft_hours(draft)) > 0.001:
        errors.append("As horas aprovadas não batem com o rascunho salvo — recarregue o relatório.")
    pattern = rules.effective(store.get_config(), None).get("number_pattern") or rules.DEFAULT_NUMBER_PATTERN
    number_errors, warnings = _number_errors(report, payload, pattern)
    errors += number_errors
    if errors:
        raise ApprovalRejected(errors)

    links = _persist_approval_files(payload, actor)
    # leitura FORA da transação de escrita (outra conexão dentro dela podia
    # desfazer a transação no SQLite dos testes — e não precisa do lock)
    previous = store.get_memories([report["family_key"]]).get(report["family_key"])
    with store.write_session() as s:
        current = s.get_report_for_update(report_id)
        if current is None or current["status"] not in APPROVABLE or current["draft_version"] != expected_version:
            raise WorkflowError("O relatório mudou enquanto era aprovado — recarregue.")
        now = store.utcnow()
        s.update_report(
            report_id, bump_version=True, status=STATUS_APPROVED,
            approved_payload_json=payload.model_dump(), approved_by=actor.get("login"), approved_at=now,
            history_links_json=links,
        )
        reviewer = {"login": report.get("reviewer_login"), "name": report.get("reviewer_name")}
        s.set_memory(report["family_key"], memory.extract(draft, previous, reviewer), report_id)
        s.add_event(report_id, "approved", actor, None, {"numbers": [p.header.project_code for p in payload.packages]})
    record_event(
        actor_id=actor.get("login", ""), actor_name=actor.get("name", ""), action="auto_report_approved",
        entity_type="auto_report", entity_id=report_id, source="auto_generation",
        metadata={"competence": report["competence"], "project_id": report["project_id"], "history": links},
    )
    return {"status": STATUS_APPROVED, "warnings": warnings, "history_links": links}


def _persist_approval_files(payload: GeneratePayload, actor: dict) -> list[str]:
    """Gera cada (pacote × formato) com o mesmo código do `/generate` — prova
    que o arquivo sai — e grava no histórico. Arquivo que não gera derruba a
    aprovação (400); histórico fora do ar não (fail-open)."""
    guard = GenerationGuard()
    links: list[str] = []
    for pkg in payload.packages:
        for fmt in payload.formats:
            tmp_path = os.path.join(tempfile.gettempdir(), f"auto_{uuid.uuid4().hex}.{fmt}")
            handle = guard.begin(persistence_pkg_data(pkg), fmt, actor.get("login", ""), actor.get("name", ""),
                                 created_from="auto_approval")
            try:
                header = build_report_file(pkg, tmp_path, fmt)
            except NonFiniteValueError as e:
                finish_generation_failure(handle, e)
                raise ApprovalRejected([str(e)]) from e
            except Exception as e:
                finish_generation_failure(handle, e)
                raise
            else:
                finish_generation_success(handle, tmp_path, sanitized_file_name(pkg.file_name, header, fmt), fmt,
                                          FORMAT_MEDIA_TYPES[fmt])
                if handle is not None:
                    links.append(f"{handle.report_id}:{handle.version_id}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
    return links


_MAX_BULK = 100


def approved_files_many(report_ids: list[str]) -> list[tuple[str, bytes]]:
    """Arquivos aprovados de vários relatórios (download em lote), com nome
    único no conjunto. Todos precisam estar aprovados/enviados — um que não
    esteja recusa o pedido inteiro, em vez de baixar pela metade calado."""
    ids = list(dict.fromkeys(report_ids))
    if not ids or len(ids) > _MAX_BULK:
        raise InvalidRequest(f"Escolha de 1 a {_MAX_BULK} relatórios.")
    files: list[tuple[str, bytes]] = []
    used: set[str] = set()
    for report_id in ids:
        report = _load(report_id)
        if report["status"] not in SENDABLE:
            raise WorkflowError(f"\"{report['project_name']}\" não está aprovado.")
        for name, data in approved_files(report_id):
            unique = dedupe_name(name, used)
            used.add(unique)
            files.append((unique, data))
    return files


def approved_files(report_id: str) -> list[tuple[str, bytes]]:
    """Arquivos do payload CONGELADO na aprovação (o que vai pro cliente)."""
    report = _load(report_id)
    frozen = report.get("approved_payload_json")
    if not frozen:
        raise WorkflowError("Relatório ainda não aprovado.")
    payload = GeneratePayload.model_validate(frozen)
    files: list[tuple[str, bytes]] = []
    used: set[str] = set()
    for pkg in payload.packages:
        for fmt in payload.formats:
            tmp_path = os.path.join(tempfile.gettempdir(), f"auto_{uuid.uuid4().hex}.{fmt}")
            try:
                header = build_report_file(pkg, tmp_path, fmt)
                name = dedupe_name(sanitized_file_name(pkg.file_name, header, fmt), used)
                used.add(name)
                with open(tmp_path, "rb") as f:
                    files.append((name, f.read()))
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
    return files
