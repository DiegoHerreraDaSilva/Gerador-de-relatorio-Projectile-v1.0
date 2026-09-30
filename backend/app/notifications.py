"""Notificações por e-mail da geração automática (fase 4): revisor atribuído,
relatório devolvido e aguardando aprovação — imediatas, pelo mesmo caminho do
envio ao cliente (Microsoft Graph, caixa do ator, cópia do agente).

Fail-open por princípio: aviso é acompanhamento, nunca pode derrubar a ação —
quem chama não trata erro. Sem `AZURE_CLIENT_ID` (Graph não configurado) ou
com o opt-out do Padrão geral (`notify_email=false`), vira no-op. O
destinatário é SEMPRE resolvido no Projectile (login → `auser.rEmail`),
nunca digitado/vindo da tela."""

from __future__ import annotations

import logging
import os

from . import email_ingest, projectile_db
from .auto_generation import rules
from .core import authz
from .core.config import get_settings
from .services import auto_generation_store as store

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    """Ligado? Depende de Graph configurado E do opt-out do Padrão geral."""
    if not os.environ.get("AZURE_CLIENT_ID"):
        return False
    try:
        config = store.get_config()
        return bool(rules.effective(config, None).get("notify_email", True))
    except Exception:
        logger.exception("Não consegui ler a configuração pra decidir a notificação (fail-open)")
        return False


def _link(view: str, report_id: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/?view={view}&report={report_id}"


def _sender_for(actor: dict) -> str | None:
    """Remetente = caixa do ator (é quem agiu); sem e-mail na sessão, a caixa
    do agente (`GRAPH_MAILBOX`) — nunca inventa um remetente."""
    actor_email = (actor.get("email") or "").strip()
    if actor_email:
        return actor_email
    return (os.environ.get("GRAPH_MAILBOX") or "").strip() or None


def _emails_for(logins: list[str]) -> list[str]:
    try:
        return list(projectile_db.fetch_user_emails(logins).values())
    except Exception:
        logger.exception("Não consegui resolver e-mails no Projectile pra notificação (fail-open)")
        return []


def _send(sender: str, recipients: list[str], subject: str, body: str) -> None:
    """Envia com o mesmo helper do relatório (sempre com o agente em cópia,
    sem anexos). Erro aqui nunca sobe — só loga."""
    try:
        email_ingest.send_report_email(sender_email=sender, to_email=recipients, subject=subject, body_text=body, attachments=[])
    except Exception:
        logger.exception("Falha ao enviar notificação por e-mail (fail-open)")


def notify_reviewer_assigned(report: dict, reviewer: dict, actor: dict) -> None:
    if not reviewer or not _enabled():
        return
    sender = _sender_for(actor)
    recipients = _emails_for([reviewer["login"]])
    if not sender or not recipients:
        return
    name = report.get("project_name") or report.get("id")
    _send(
        sender,
        recipients,
        f"Relatório para revisar: {name} ({report.get('competence', '')})",
        (
            f"{reviewer['name']}, um relatório foi atribuído a você para revisão.\n\n"
            f"Projeto: {report.get('project_name')}\n"
            f"Competência: {report.get('competence')}\n"
            f"Atribuído por: {actor.get('name') or actor.get('login')}\n\n"
            f"Abra em Minhas revisões: {_link('my-reviews', report['id'])}\n"
        ),
    )


def notify_reviewer_returned(report: dict, comment: str, actor: dict) -> None:
    login = (report.get("reviewer_login") or "").strip()
    if not login or not _enabled():
        return
    sender = _sender_for(actor)
    recipients = _emails_for([login])
    if not sender or not recipients:
        return
    name = report.get("project_name") or report.get("id")
    _send(
        sender,
        recipients,
        f"Relatório devolvido para ajuste: {name}",
        (
            f"{report.get('reviewer_name') or login}, o gerente devolveu o relatório {name} "
            f"({report.get('competence', '')}) com um comentário.\n\n"
            f"Comentário: {comment}\n\n"
            f"Abra em Minhas revisões: {_link('my-reviews', report['id'])}\n"
        ),
    )


def notify_awaiting_approval(report: dict, reviewer: dict) -> None:
    """Avisa os gerentes que um relatório foi mandado pra aprovação (quem
    manda é o revisor — vira o remetente quando tem e-mail)."""
    if not _enabled():
        return
    recipients = _emails_for(sorted(authz.MANAGEMENT_PANEL_LOGINS))
    if not recipients:
        return
    sender = _sender_for(reviewer) or (os.environ.get("GRAPH_MAILBOX") or "").strip() or None
    if not sender:
        return
    name = report.get("project_name") or report.get("id")
    _send(
        sender,
        recipients,
        f"Relatório aguardando aprovação: {name}",
        (
            f"O relatório {name} ({report.get('competence', '')}) foi revisado por "
            f"{reviewer.get('name') or reviewer.get('login')} e está aguardando aprovação.\n\n"
            f"Abra em Geração automática: {_link('auto-generation', report['id'])}\n"
        ),
    )
