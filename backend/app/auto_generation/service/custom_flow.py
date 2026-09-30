"""Geração personalizada: recorte livre, pedidos agendados e relatórios avulsos."""

from __future__ import annotations

import logging
from datetime import date

from ulid import ULID

from ...services import auto_generation_store as store
from ...services.audit import record_event
from .. import builder, custom
from .common import (
    REGENERABLE,
    STATUS_APPROVED,
    STATUS_ERROR,
    STATUS_GENERATING,
    STATUS_IN_REVIEW,
    STATUS_RETURNED,
    STATUS_REVIEWED,
    STATUS_SENT,
    STATUS_SKIPPED,
    InvalidRequest,
    NotFound,
    WorkflowError,
    _badges,
    _public,
)
from .views import _attach_activity, _count_statuses

logger = logging.getLogger(__name__)


def _custom_scope(request: dict) -> dict:
    """O que fica guardado (e o que o "Regenerar" relê): só o recorte —
    o revisor escolhido é uma ação da criação, não parte dele."""
    scope = {k: v for k, v in request.items() if k != "reviewer_login"}
    config = custom.clean_config(scope.pop("config", None))
    if config:
        scope["config"] = config
    return scope


def _custom_plan(scope: dict) -> tuple[custom.Resolved, list[custom.CustomReport], list[str]]:
    """Recorte → relatórios calculados (sem gravar nada). Compartilhado pela
    prévia, pela criação e pelo "Regenerar"."""
    try:
        resolved = custom.resolve(scope)
        rows, warnings = custom.collect(resolved)
        reports = custom.build_reports(resolved, rows, store.get_config(), date.today())
    except custom.InvalidScope as e:
        raise InvalidRequest(str(e)) from e
    warnings = [*resolved.warnings, *warnings]
    usable = []
    for report in reports:
        if report.draft["packages"]:
            usable.append(report)
            warnings.extend(f"\"{report.title}\": {note}" for note in report.notes)
        else:  # só linhas sem descrição: não há o que revisar
            warnings.append(f"\"{report.title}\" só tem horas sem descrição ({str(round(report.hours, 1)).replace('.', ',')} h) e não gerou relatório.")
    if not usable:
        raise InvalidRequest("Nenhuma hora com descrição nesse recorte e período.")
    return resolved, usable, warnings


def preview_custom(request: dict) -> dict:
    """O que a geração personalizada criaria — nada é gravado."""
    resolved, reports, warnings = _custom_plan(_custom_scope(request))
    return {
        "period_label": resolved.label,
        "summary": custom.scope_summary(resolved),
        "reports": custom.summarize(resolved, reports),
        "total_hours": round(sum(r.hours for r in reports), 2),
        "warnings": warnings,
    }


def create_custom(request: dict, actor: dict) -> dict:
    """Cria os rascunhos do recorte na mesma esteira dos mensais (revisão →
    aprovação → envio). Cada relatório vira uma linha `kind = "avulso"` com o
    recorte em `scope_json` (é o que o "Regenerar" relê); `competence` é o mês
    final do período e `project_id`/`family_key` são sintéticos — nunca
    colidem com um projeto ou família de verdade, e por isso o avulso não lê
    nem grava memória. Tudo numa transação: ou saem todos, ou nenhum."""
    from .reviews import _resolve_reviewer  # local: quebra ciclo reviews↔custom_flow

    login = (request.get("reviewer_login") or "").strip()
    reviewer = _resolve_reviewer(login) if login else None
    scope = _custom_scope(request)
    resolved, reports, warnings = _custom_plan(scope)
    blocks_view = custom.describe_blocks(scope, resolved.employees)
    created = []
    with store.write_session() as s:
        for report in reports:
            report_id = str(ULID())
            row = {
                "id": report_id,
                "run_id": None,
                "kind": store.KIND_CUSTOM,
                "scope_json": {"scope": scope, "part": report.key, "label": resolved.label, "summary": custom.scope_summary(resolved), "blocks": blocks_view},
                "competence": resolved.end_competence,
                "project_id": f"custom:{report_id}",
                "family_key": f"custom:{report_id}",
                "project_name": report.title,
                "client": report.client or None,
                "status": STATUS_IN_REVIEW,
                "draft_json": report.draft,
                "draft_version": 1,
                "source_hours": report.hours,
                "badges_json": _badges(report.draft, report.hours, {"custom": True, "partial": report.partial}),
            }
            # revisor escolhido no pedido; sem ele, o do projeto (configuração ou último aprovado)
            chosen = reviewer or ({"login": report.reviewer_login, "name": report.reviewer_name} if report.reviewer_login else None)
            if chosen:
                row["reviewer_login"], row["reviewer_name"] = chosen["login"][:100], (chosen["name"] or chosen["login"])[:255]
            s.insert_report(row)
            s.add_event(report_id, "generated", actor, None, {"custom": True, "label": resolved.label})
            created.append({"id": report_id, "title": report.title})
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action="auto_custom_created",
        entity_type="auto_report",
        entity_id=created[0]["id"],
        source="auto_generation",
        metadata={"label": resolved.label, "reports": len(created), "split_by": resolved.split_by, "package_unit": resolved.package_unit},
    )
    return {"created": created, "warnings": warnings}


def _current_competence() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _public_request(competence: str, entry: dict) -> dict:
    return {
        "id": entry["id"],
        "competence": competence,
        "label": entry.get("label"),
        "summary": entry.get("summary"),
        "title": entry.get("title"),
        "split_by": (entry.get("scope") or {}).get("split_by"),
        "package_unit": (entry.get("scope") or {}).get("package_unit"),
        "config": (entry.get("scope") or {}).get("config") or {},
        "blocks": entry.get("blocks") or [],
        "reviewer_name": entry.get("reviewer_name"),
        "status": entry.get("status", "agendado"),
        "error": entry.get("error"),
        "created_by_name": entry.get("created_by_name"),
        "created_at": entry.get("created_at"),
    }


def schedule_custom(request: dict, actor: dict) -> dict:
    """AGENDA uma geração personalizada — não cria rascunho agora. Vale só pro
    MÊS ATUAL (decisão do usuário, 2026-09-29) e é gerada junto com os
    projetos da rodada dessa competência (`generate_custom_requests`, chamada
    por `_execute_run`), quando o mês já fechou e as horas estão completas. Aqui
    só confere que o recorte é válido (colaborador na engenharia, pacotes com
    um projeto…) e o revisor; a prévia (`preview_custom`) mostra o que sairia
    com as horas de agora."""
    current = _current_competence()
    period = request.get("period") or {}
    if period.get("start") != current or period.get("end") != current:
        raise InvalidRequest(f"A geração personalizada vale só pro mês atual ({builder.month_label(current)}).")
    from .reviews import _resolve_reviewer  # local: quebra ciclo reviews↔custom_flow

    login = (request.get("reviewer_login") or "").strip()
    reviewer = _resolve_reviewer(login) if login else None
    scope = _custom_scope(request)
    try:
        resolved = custom.resolve(scope)
    except custom.InvalidScope as e:
        raise InvalidRequest(str(e)) from e
    entry = {
        "id": str(ULID()),
        "scope": scope,
        "title": resolved.title or None,
        "reviewer_login": reviewer["login"] if reviewer else None,
        "reviewer_name": reviewer["name"] if reviewer else None,
        "label": resolved.label,
        "summary": custom.scope_summary(resolved),
        "status": "agendado",
        "error": None,
        "blocks": custom.describe_blocks(scope, resolved.employees),
        "created_by": actor.get("login"),
        "created_by_name": actor.get("name"),
        "created_at": store.utcnow().isoformat(),
    }
    with store.write_session() as s:
        s.set_custom_requests(current, [*s.custom_requests(current), entry])
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action="auto_custom_scheduled",
        entity_type="auto_custom_request",
        entity_id=entry["id"],
        source="auto_generation",
        metadata={"competence": current, "label": resolved.label, "split_by": resolved.split_by, "package_unit": resolved.package_unit},
    )
    return _public_request(current, entry)


def update_custom_request_config(request_id: str, package_unit: str, config: dict | None, actor: dict) -> dict:
    """Muda a configuração de um pedido AGENDADO (Relatório, arquivos, assinantes,
    empresas) — vale quando a rodada gerar o pedido."""
    for competence, entries in store.get_custom_requests().items():
        if not any(e.get("id") == request_id for e in entries):
            continue
        with store.write_session() as s:
            current = s.custom_requests(competence)
            entry = next((e for e in current if e.get("id") == request_id), None)
            if entry is None:
                raise NotFound(request_id)
            scope = {k: v for k, v in (entry.get("scope") or {}).items() if k != "config"}
            scope["package_unit"] = package_unit
            cleaned = custom.clean_config(config)
            if cleaned:
                scope["config"] = cleaned
            updated = {**entry, "scope": scope}
            s.set_custom_requests(competence, [updated if e.get("id") == request_id else e for e in current])
        return _public_request(competence, updated)
    raise NotFound(request_id)


def update_custom_config(report_id: str, package_unit: str, config: dict | None, actor: dict) -> None:
    """Muda a configuração guardada de um personalizado JÁ GERADO. O rascunho não
    muda sozinho (a tela oferece "Regenerar" pra aplicar); aprovado/enviado
    precisa ser reaberto antes, como pra apagar."""
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report.get("kind") != store.KIND_CUSTOM:
            raise WorkflowError("Só um relatório personalizado tem configuração própria.")
        if report["status"] in (STATUS_APPROVED, STATUS_SENT):
            raise WorkflowError(f"Um relatório {report['status']} não muda de configuração — reabra antes.")
        saved = dict(report.get("scope_json") or {})
        scope = {k: v for k, v in (saved.get("scope") or {}).items() if k != "config"}
        scope["package_unit"] = package_unit
        cleaned = custom.clean_config(config)
        if cleaned:
            scope["config"] = cleaned
        s.update_report(report_id, scope_json={**saved, "scope": scope})
        s.add_event(report_id, "config", actor, None, {"package_unit": package_unit, "config": cleaned})


def delete_custom_request(request_id: str, actor: dict) -> None:
    """Cancela um pedido que ainda não virou rascunho (agendado ou que deu
    erro na rodada)."""
    for competence, entries in store.get_custom_requests().items():
        if not any(e.get("id") == request_id for e in entries):
            continue
        with store.write_session() as s:
            current = s.custom_requests(competence)
            if not any(e.get("id") == request_id for e in current):
                raise NotFound(request_id)
            s.set_custom_requests(competence, [e for e in current if e.get("id") != request_id])
        record_event(
            actor_id=actor.get("login", ""),
            actor_name=actor.get("name", ""),
            action="auto_custom_request_deleted",
            entity_type="auto_custom_request",
            entity_id=request_id,
            source="auto_generation",
            metadata={"competence": competence},
        )
        return
    raise NotFound(request_id)


def generate_custom_requests(competence: str, actor: dict) -> int:
    """Gera os rascunhos dos pedidos personalizados agendados pra `competence`
    — junto com os projetos da rodada. Pedido que deu certo sai da fila (os
    relatórios aparecem em "Personalizados"); o que falhou (recorte sem horas,
    revisor que saiu da engenharia…) fica com o motivo, e a próxima rodada tenta
    de novo. Um pedido com erro não derruba os outros nem a rodada."""
    pending = [e for e in store.get_custom_requests().get(competence, []) if e.get("status") in ("agendado", "erro")]
    done: set[str] = set()
    failed: dict[str, str] = {}
    for entry in pending:
        try:
            create_custom({**entry["scope"], "reviewer_login": entry.get("reviewer_login")}, actor)
            done.add(entry["id"])
        except Exception as e:  # noqa: BLE001 — qualquer falha vira o motivo do pedido
            logger.warning("Pedido personalizado %s de %s falhou: %s", entry.get("id"), competence, e)
            failed[entry["id"]] = str(e)[:500]
    if done or failed:
        with store.write_session() as s:
            kept = []
            for entry in s.custom_requests(competence):
                if entry.get("id") in done:
                    continue
                if entry.get("id") in failed:
                    entry = {**entry, "status": "erro", "error": failed[entry["id"]]}
                kept.append(entry)
            s.set_custom_requests(competence, kept)
    return len(done)


def _backfill_request_blocks() -> None:
    """Pedido agendado ANTES de `blocks` existir: completa uma vez (nomes de
    projeto e de colaborador) e grava. Falha (colaborador que saiu, Projectile
    fora do ar) não atrapalha a lista — o cartão cai no resumo e tenta de novo depois."""
    for competence, entries in store.get_custom_requests().items():
        missing = [e for e in entries if "blocks" not in e and e.get("scope")]
        if not missing:
            continue
        filled: dict[str, list[dict]] = {}
        for entry in missing:
            try:
                filled[entry["id"]] = custom.describe_blocks(entry["scope"], custom.resolve(entry["scope"]).employees)
            except Exception:  # noqa: BLE001
                logger.warning("Não deu pra completar os recortes do pedido %s", entry.get("id"), exc_info=True)
        if filled:
            with store.write_session() as s:
                s.set_custom_requests(competence, [{**e, "blocks": filled[e["id"]]} if e.get("id") in filled else e for e in s.custom_requests(competence)])


def custom_view() -> dict:
    """A aba "Personalizados": os pedidos agendados (ainda sem rascunho) e os
    relatórios já gerados."""
    _backfill_request_blocks()
    out = [{**_public(item), "badges": item.get("badges_json") or {}} for item in store.list_custom()]
    _attach_activity(out)
    requests = [_public_request(competence, entry) for competence, entries in store.get_custom_requests().items() for entry in entries]
    requests.sort(key=lambda r: (r["competence"], r["created_at"] or ""), reverse=True)
    return {"items": out, "counts": _count_statuses(out), "requests": requests}


DELETABLE_CUSTOM = {STATUS_GENERATING, STATUS_ERROR, STATUS_IN_REVIEW, STATUS_REVIEWED, STATUS_RETURNED, STATUS_SKIPPED}


def delete_custom(report_id: str, actor: dict) -> None:
    """Apaga um relatório PERSONALIZADO ainda em rascunho (com a linha do tempo
    dele). Só o avulso: os mensais são da rodada (apagar um faria a próxima
    rodada recriá-lo, e o projeto some da lista do mês). Aprovado ou enviado
    já gravou no histórico e/ou está com o cliente — reabra primeiro. O
    revisor perde o acesso na hora (o item deixa de existir)."""
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report.get("kind") != store.KIND_CUSTOM:
            raise WorkflowError("Só um relatório personalizado pode ser apagado.")
        if report["status"] not in DELETABLE_CUSTOM:
            raise WorkflowError(f"Um relatório {report['status']} já foi pro histórico ou pro cliente — reabra antes de apagar.")
        s.delete_report(report_id)
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action="auto_custom_deleted",
        entity_type="auto_report",
        entity_id=report_id,
        source="auto_generation",
        metadata={"title": report["project_name"], "status": report["status"], "label": (report.get("scope_json") or {}).get("label")},
    )


def _regenerate_custom(report: dict, actor: dict) -> None:
    """Refaz o rascunho de um personalizado relendo o recorte e o período
    guardados (descarta as edições — a tela confirma antes)."""
    saved = report.get("scope_json") or {}
    if not saved.get("scope"):
        raise WorkflowError("Esse relatório não guardou o recorte que o gerou.")
    _resolved, reports, _warnings = _custom_plan(saved["scope"])
    fresh = next((r for r in reports if r.key == saved.get("part")), None)
    if fresh is None:
        raise WorkflowError("O recorte não tem mais horas pra esse relatório.")
    with store.write_session() as s:
        current = s.get_report_for_update(report["id"])
        if current is None or current["status"] not in REGENERABLE:
            raise WorkflowError("O relatório mudou de estado enquanto regenerava.")
        s.update_report(
            report["id"],
            bump_version=True,
            status=STATUS_IN_REVIEW,
            draft_json=fresh.draft,
            source_hours=fresh.hours,
            error=None,
            project_name=fresh.title,
            client=fresh.client or None,
            badges_json=_badges(fresh.draft, fresh.hours, {"custom": True, "partial": fresh.partial}),
        )
        s.add_event(report["id"], "regenerated", actor, None)
