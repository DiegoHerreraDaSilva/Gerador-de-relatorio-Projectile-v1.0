"""Rodada mensal: `start_run` (idempotente) e a geração de cada projeto."""

from __future__ import annotations

import logging
import threading
from datetime import date

from ulid import ULID

from ... import management
from ...services import auto_generation_store as store
from .. import builder, rules
from .common import _STALE_RUN, STATUS_ERROR, STATUS_IN_REVIEW, STATUS_SKIPPED, RunInProgress, _badges
from .config import _family_for
from .custom_flow import generate_custom_requests

logger = logging.getLogger(__name__)


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
            run = {"id": str(ULID()), "competence": competence, "status": "running", "triggered_by": actor.get("login"), "started_at": now}
            s.insert_run(run)
        else:
            s.update_run(run["id"], status="running", triggered_by=actor.get("login"), started_at=now, finished_at=None, error=None)
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
        planned_numbers = store.get_planned_numbers(competence)
        today = date.today()

        for project in projects:
            status = _generate_one(
                run_id,
                competence,
                project,
                keys[project["project_id"]],
                global_config,
                family_rules,
                memories,
                rows_by_project.get(project["project_id"], []),
                closed_projects,
                closed_clients,
                today,
                planned_numbers,
            )
            counts[status] = counts.get(status, 0) + 1
        if not project_ids:
            # "gerar só estes projetos" não leva junto os pedidos personalizados
            made = generate_custom_requests(competence, actor)
            if made:
                counts["personalizados"] = made
        final = {"status": "done", "error": None}
    except Exception as e:  # Projectile/reports_db fora do ar: a rodada falha, os já gravados ficam
        logger.exception("Rodada de geração automática %s falhou", competence)
        final = {"status": "failed", "error": str(e)[:2000]}
    try:
        with store.write_session() as s:
            s.update_run(run_id, finished_at=store.utcnow(), counts_json=counts, **final)
    except Exception:
        logger.exception("Não consegui fechar a rodada %s", competence)


def _apply_planned_number(draft: dict, number: str | None) -> None:
    """Número digitado na prévia do mês. Só cabe quando o relatório é UM (modo
    projeto): com vários pacotes não dá pra saber a qual deles pertence."""
    if number and len(draft.get("packages", [])) == 1:
        draft["packages"][0]["project_code"] = number[:100]


def _generate_one(
    run_id, competence, project, family_key, global_config, family_rules, memories, rows, closed_projects, closed_clients, today, planned_numbers=None
) -> str:
    """Um projeto — erro aqui vira `erro` SÓ nele, a rodada continua."""
    base = {
        "id": str(ULID()),
        "run_id": run_id,
        "competence": competence,
        "project_id": project["project_id"],
        "family_key": family_key,
        "project_name": project["name"][:255],
        "client": project["client"][:255],
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
            _apply_planned_number(draft, (planned_numbers or {}).get(project["project_id"]))
            report = {
                **base,
                "status": STATUS_IN_REVIEW,
                "draft_json": draft,
                "source_hours": project["hours"],
                "badges_json": _badges(draft, project["hours"]),
            }
            # revisor da configuração do projeto; sem ele, quem revisou o último
            # relatório aprovado da família — o rascunho já nasce atribuído
            remembered = (
                {"login": config["reviewer_login"], "name": config.get("reviewer_name")}
                if config.get("reviewer_login")
                else (memories.get(family_key) or {}).get("reviewer") or {}
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
