"""O que a tela lista: competências, itens, contadores, prévia calculada e número planejado."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from ... import management
from ...services import auto_generation_store as store
from .. import builder, families, rules
from .common import (
    STATUS_ERROR,
    STATUS_RETURNED,
    STATUS_REVIEWED,
    STATUS_SENT,
    STATUS_SKIPPED,
    InvalidRequest,
    NotFound,
    _badges,
    _pattern_label,
    _public,
    _public_run,
)
from .config import _family_for

logger = logging.getLogger(__name__)


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
            hours_now is not None
            and item.get("source_hours") is not None
            and item["status"] not in (STATUS_SENT, STATUS_SKIPPED, STATUS_ERROR)
            and abs(hours_now - item["source_hours"]) > 0.01
        ):
            badges["hours_changed"] = True
        out.append({**_public(item), "hours_now": hours_now, "badges": badges})
    # configuração individual de cada projeto (guardada pela família, pra
    # valer nos meses seguintes do mesmo trabalho) e o que vale de fato
    global_config = store.get_config()
    family_rules = store.get_rules()
    _attach_activity(out)
    for item in out:
        item["rule"] = family_rules.get(item["family_key"], {})
        item["effective"] = rules.effective(global_config, item["rule"])
    counts = _count_statuses(out)
    new_projects = [p for p in (current or {}).values() if p["project_id"] not in listed] if run else []
    return {
        "competence": competence,
        "month_label": builder.month_label(competence),
        "run": _public_run(run),
        "items": out,
        "counts": counts,
        "new_projects": sorted(new_projects, key=lambda p: p["name"].casefold()),
    }


def _attach_activity(items: list[dict]) -> None:
    """`last_comment` (devolução/observação de quem revisou) e `last_sent`
    (pra quem foi o último envio) de cada item da lista."""
    comments = store.latest_comments([i["id"] for i in items if i["status"] in (STATUS_REVIEWED, STATUS_RETURNED)], ("submitted", "returned"))
    sends = store.latest_comments([i["id"] for i in items if i["status"] == STATUS_SENT], ("sent",))
    for item in items:
        item["last_comment"] = comments.get(item["id"])
        sent = sends.get(item["id"])
        item["last_sent"] = (
            {
                "to": (sent.get("metadata") or {}).get("to", []),
                "cc": (sent.get("metadata") or {}).get("cc", []),
                "actor_name": sent["actor_name"],
                "created_at": sent["created_at"],
            }
            if sent
            else None
        )


def _count_statuses(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


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
    planned_numbers = store.get_planned_numbers(competence)
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
        out.append(
            {
                **p,
                "family_key": key,
                "family_label": families.family_label(p["name"]),
                "planned": planned,
                "mode": config.get("mode"),
                "rule": family_rules.get(key, {}),
                "effective": config,
                # quem revisou o último aprovado (vale se a configuração não tiver revisor)
                "remembered_reviewer": (memories.get(key) or {}).get("reviewer"),
                # número digitado antes do rascunho existir (vale quando ele for gerado)
                "planned_number": planned_numbers.get(p["project_id"]),
            }
        )
    return {"competence": competence, "month_label": builder.month_label(competence), "projects": out}


def set_planned_number(competence: str, project_id: str, number: str | None, actor: dict) -> str | None:
    """Reserva o número do relatório de um projeto do mês (a prévia ainda não
    tem rascunho). Confere o formato (o mesmo da aprovação) e que o número não
    está reservado pra outro projeto do mês; o resto — histórico, outras
    competências — é conferido na aprovação, como sempre."""
    builder.parse_competence(competence)
    if not any(p["project_id"] == project_id for p in builder.month_projects(competence)):
        raise NotFound(project_id)
    code = (number or "").strip()
    if code:
        pattern = rules.effective(store.get_config(), None).get("number_pattern") or rules.DEFAULT_NUMBER_PATTERN
        if not re.fullmatch(pattern, code):
            raise InvalidRequest(f"Número \"{code}\" fora do formato {_pattern_label(pattern)}.")
    with store.write_session() as s:
        taken = [pid for pid, n in s.planned_numbers(competence).items() if n == code and pid != project_id]
        if code and taken:
            raise InvalidRequest(f"O número {code} já está reservado pra outro projeto deste mês.")
        s.set_planned_number(competence, project_id, code or None)
    return code or None


def list_competences(today: date | None = None) -> dict:
    today = today or date.today()
    current = f"{today.year:04d}-{today.month:02d}"
    previous_month = date(today.year, today.month, 1) - timedelta(days=1)
    previous = f"{previous_month.year:04d}-{previous_month.month:02d}"
    runs = [_public_run(r) for r in store.list_runs()]
    return {"current": current, "previous": previous, "runs": runs}
