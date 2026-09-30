"""Constantes de estado, exceções e helpers compartilhados da geração automática (`service/`)."""

from __future__ import annotations

import logging
from datetime import timedelta

from ...services import auto_generation_store as store
from .. import builder, rules

logger = logging.getLogger(__name__)


STATUS_GENERATING = "gerando"

STATUS_ERROR = "erro"

STATUS_IN_REVIEW = "em_revisao"

STATUS_REVIEWED = "revisado"

STATUS_RETURNED = "devolvido"

STATUS_APPROVED = "aprovado"

STATUS_SENT = "enviado"

STATUS_SKIPPED = "pulado"

STATUSES = (STATUS_GENERATING, STATUS_ERROR, STATUS_IN_REVIEW, STATUS_REVIEWED, STATUS_RETURNED, STATUS_APPROVED, STATUS_SENT, STATUS_SKIPPED)

EDITABLE = {STATUS_IN_REVIEW, STATUS_REVIEWED, STATUS_RETURNED}

APPROVABLE = EDITABLE

REVIEWER_EDITABLE = {STATUS_IN_REVIEW, STATUS_RETURNED}

REVIEW_LIST_STATUSES = (STATUS_IN_REVIEW, STATUS_RETURNED, STATUS_REVIEWED, STATUS_APPROVED, STATUS_SENT)

REGENERABLE = {STATUS_ERROR, STATUS_SKIPPED, *EDITABLE}

SENDABLE = {STATUS_APPROVED, STATUS_SENT}

_STALE_RUN = timedelta(minutes=30)


class WorkflowError(Exception):
    """Ação que o estado atual não permite (vira 409 na rota)."""


class SendUncertain(WorkflowError):
    """Não dá pra afirmar se o e-mail saiu (vira 409 na rota): reenviar às cegas
    poderia duplicar o que o cliente recebe. O gerente confirma em "Envio incerto"."""


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


def _public(item: dict) -> dict:
    out = {k: v for k, v in item.items() if k not in ("draft_json", "approved_payload_json", "ai_original_json", "badges_json", "history_links_json")}
    saved = out.get("scope_json")
    if saved:
        # o recorte inteiro (ids de colaborador, blocos) é do gerente — quem revisa só vê o período e o resumo
        inner = saved.get("scope") or {}
        out["scope_json"] = {
            "label": saved.get("label"),
            "summary": saved.get("summary"),
            "package_unit": inner.get("package_unit"),
            "config": inner.get("config") or {},
            "blocks": saved.get("blocks") or [],
        }
    return out


def _public_run(run: dict | None) -> dict | None:
    if not run:
        return None
    return {k: run.get(k) for k in ("id", "competence", "status", "triggered_by", "started_at", "finished_at", "counts_json", "error")}


def _load(report_id: str) -> dict:
    report = store.get_report(report_id)
    if report is None:
        raise NotFound(report_id)
    return report


def _transition(report_id: str, allowed: set[str], new_status: str, actor: dict, action: str, comment: str | None = None, **fields) -> None:
    with store.write_session() as s:
        report = s.get_report_for_update(report_id)
        if report is None:
            raise NotFound(report_id)
        if report["status"] not in allowed:
            raise WorkflowError(f"Não dá pra {action} um relatório {report['status']}.")
        s.update_report(report_id, bump_version=True, status=new_status, **fields)
        s.add_event(report_id, action, actor, comment or None)


SYSTEM_ACTOR = {"login": "sistema", "name": "Sistema"}

# o que ainda está em aberto e, por isso, sai quando o projeto/cliente é fechado
CLOSABLE = {STATUS_ERROR, STATUS_IN_REVIEW, STATUS_REVIEWED, STATUS_RETURNED}


def skip_closed_drafts() -> int:
    """Projeto ou cliente fechado no Diagnóstico NÃO entra na geração automática: o que já
    tinha rascunho em aberto (erro, em revisão, aguardando aprovação, devolvido) vira `pulado`,
    com o motivo e um evento na linha do tempo. Aprovado/enviado não muda: já foi pro
    histórico e/ou pro cliente. Reabrir o fechamento não ressuscita o rascunho (o "Regenerar"
    continua valendo pra pulado). Personalizado não entra: o recorte é escolha explícita.
    Devolve quantos foram pulados; nunca derruba quem chamou (leitura de lista/contador)."""
    from ... import management

    try:
        closed = management.get_closed_registry()
        projects = set(closed.get("closed_projects", []))
        clients = set(closed.get("closed_clients", []))
        if not projects and not clients:
            return 0
        skipped = 0
        for item in store.list_open_monthly(tuple(CLOSABLE)):
            if item["project_id"] not in projects and item["client"] not in clients:
                continue
            badges = {**(item.get("badges_json") or {}), "skip_reason": "fechado no Diagnóstico"}
            try:
                _transition(
                    item["id"],
                    CLOSABLE,
                    STATUS_SKIPPED,
                    SYSTEM_ACTOR,
                    "skipped",
                    "Projeto/cliente fechado no Diagnóstico depois de gerado.",
                    badges_json=badges,
                )
                skipped += 1
            except (WorkflowError, NotFound):
                continue  # mudou de estado no meio: a próxima leitura confere de novo
        return skipped
    except Exception:
        logger.warning("Não consegui pular os rascunhos de projetos fechados", exc_info=True)
        return 0


def _pattern_label(pattern: str) -> str:
    """Formato do número pra gente ler — o modelo com `#` por dígito
    ("SE.##.###"), nunca a expressão regular crua."""
    model = rules.pattern_to_model(pattern)
    if model is None:
        return f"configurado no padrão geral ({pattern})"
    return f"{model} (ex.: SE.26.053)" if pattern == rules.DEFAULT_NUMBER_PATTERN else model
