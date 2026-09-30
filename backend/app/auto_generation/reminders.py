"""Lembretes de revisão e aprovação paradas (Onda 3 do roadmap; opt-in, DESLIGADO por padrão).

Um relatório fica "esperando alguém": em revisão/devolvido (o revisor, ou o gerente quando não há revisor) ou
aguardando aprovação (o gerente). Sem ação por `reminder_after_days` dias (padrão 3), a pessoa recebe UM e-mail
consolidado com tudo o que está parado com ela — nunca um por relatório. Regras:

- só liga no Padrão geral (`reminders_enabled`) E com o Graph configurado E `notify_email` ligado;
- no máximo `MAX_REMINDERS` (3) lembretes por relatório, e só depois de `reminder_after_days` dias sem nenhuma
  ação (`updated_at` mexe a cada edição, troca de estado ou comentário) e sem outro lembrete;
- o destinatário é sempre resolvido no Projectile (login → e-mail), nunca vem da tela;
- cada lembrete enviado vira o evento `reminder_sent` (com `n`) na linha do tempo do relatório — é o que impede
  repetir no dia seguinte;
- fail-open: lembrete é acompanhamento, nunca derruba o agendador.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .. import notifications, projectile_db
from ..core import authz
from ..core.config import get_settings
from ..services import auto_generation_store as store
from . import rules
from .service.common import STATUS_IN_REVIEW, STATUS_RETURNED, STATUS_REVIEWED

logger = logging.getLogger(__name__)

MAX_REMINDERS = 3
STALLED_STATUSES = (STATUS_IN_REVIEW, STATUS_RETURNED, STATUS_REVIEWED)
SYSTEM_ACTOR = {"login": "sistema", "name": "Lembretes"}


def owner_of(item: dict) -> str:
    """Com quem o relatório está: "reviewer" (em revisão/devolvido COM revisor) ou "manager" (aguardando
    aprovação, ou em revisão sem revisor — o gerente revisa e aprova direto)."""
    if item["status"] == STATUS_REVIEWED or not (item.get("reviewer_login") or "").strip():
        return "manager"
    return "reviewer"


def plan(items: list[dict], last_reminders: dict[str, dict], now: datetime, after_days: int) -> list[dict]:
    """Quais relatórios recebem lembrete agora. Função pura (sem banco): `last_reminders` é o último evento
    `reminder_sent` por relatório (`created_at` e `metadata.n`). Datas em UTC sem fuso, como o banco guarda."""
    due = []
    for item in items:
        if item["status"] not in STALLED_STATUSES:
            continue
        last = last_reminders.get(item["id"])
        idle_since = max(item["updated_at"], last["created_at"]) if last else item["updated_at"]
        idle_days = (now - idle_since).days
        if idle_days < after_days:
            continue
        n = int(((last or {}).get("metadata") or {}).get("n", 0)) + 1
        if n > MAX_REMINDERS:
            continue
        due.append(
            {
                "id": item["id"],
                "project_name": item.get("project_name") or item["id"],
                "competence": item.get("competence") or "",
                "status": item["status"],
                "owner": owner_of(item),
                "reviewer_login": (item.get("reviewer_login") or "").strip(),
                "reviewer_name": item.get("reviewer_name") or "",
                "idle_days": (now - item["updated_at"]).days,
                "n": n,
            }
        )
    return due


_STATUS_TEXT = {STATUS_IN_REVIEW: "em revisão", STATUS_RETURNED: "devolvido para ajuste", STATUS_REVIEWED: "aguardando aprovação"}


def _link(view: str, report_id: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/?view={view}&report={report_id}"


def digest(owner: str, name: str, reminders: list[dict]) -> tuple[str, str]:
    """(assunto, corpo) do e-mail consolidado de uma pessoa."""
    count = len(reminders)
    plural = "relatório" if count == 1 else "relatórios"
    view = "my-reviews" if owner == "reviewer" else "auto-generation"
    where = "Minhas revisões" if owner == "reviewer" else "Geração automática"
    lines = [
        f"- {r['project_name']} ({r['competence']}) — {_STATUS_TEXT.get(r['status'], r['status'])}, sem ação há {r['idle_days']} dias: {_link(view, r['id'])}"
        for r in sorted(reminders, key=lambda r: -r["idle_days"])
    ]
    subject = f"Lembrete: {count} {plural} esperando {'sua revisão' if owner == 'reviewer' else 'você'}"
    body = (
        f"{name}, {'este relatório está parado' if count == 1 else 'estes relatórios estão parados'} aguardando você.\n\n"
        + "\n".join(lines)
        + f"\n\nAbra em {where}. Este é um lembrete automático: ele para quando houver qualquer ação no relatório.\n"
    )
    return subject, body


def run(now: datetime | None = None) -> dict:
    """Um ciclo: decide, manda os e-mails consolidados e registra `reminder_sent`. Devolve um resumo
    (`reason` = por que não rodou; `sent` = e-mails enviados; `reminders` = relatórios lembrados)."""
    now = now or store.utcnow()
    config = rules.effective(store.get_config(), None)
    if not config.get("reminders_enabled"):
        return {"reason": "desligado", "sent": 0, "reminders": 0}
    if not notifications.enabled():
        return {"reason": "sem e-mail", "sent": 0, "reminders": 0}
    items = store.list_open_monthly(STALLED_STATUSES)
    last = store.latest_comments([i["id"] for i in items], ("reminder_sent",))
    due = plan(items, last, now, int(config.get("reminder_after_days", 3)))
    if not due:
        return {"reason": "nada parado", "sent": 0, "reminders": 0}

    groups: dict[str, list[dict]] = {}
    for reminder in due:
        key = "manager" if reminder["owner"] == "manager" else f"reviewer:{reminder['reviewer_login']}"
        groups.setdefault(key, []).append(reminder)

    sender = notifications.system_sender()
    if not sender:
        return {"reason": "sem remetente", "sent": 0, "reminders": 0}
    sent = 0
    reminded: list[tuple[dict, list[str]]] = []
    for key, reminders in groups.items():
        if key == "manager":
            logins, name, owner = sorted(authz.MANAGEMENT_PANEL_LOGINS), "Gerência", "manager"
        else:
            logins, name, owner = [reminders[0]["reviewer_login"]], reminders[0]["reviewer_name"] or reminders[0]["reviewer_login"], "reviewer"
        try:
            recipients = list(projectile_db.fetch_user_emails(logins).values())
        except Exception:  # noqa: BLE001
            logger.exception("Não consegui resolver os e-mails dos lembretes (fail-open)")
            continue
        if not recipients:
            continue
        subject, body = digest(owner, name, reminders)
        if notifications.send_checked(sender, recipients, subject, body):
            sent += 1
            reminded += [(r, recipients) for r in reminders]
    if reminded:
        with store.write_session() as s:
            for reminder, recipients in reminded:
                s.add_event(reminder["id"], "reminder_sent", SYSTEM_ACTOR, None, {"n": reminder["n"], "to": recipients})
    return {"reason": "ok", "sent": sent, "reminders": len(reminded)}
