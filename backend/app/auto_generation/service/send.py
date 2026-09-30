"""Envio ao cliente: destinatários, formatos, envio único e em lote."""

from __future__ import annotations

import logging
import re
import threading
from contextlib import contextmanager

from ... import email_ingest
from ...core.redis_client import get_redis_client
from ...services import auto_generation_store as store
from ...services.audit import record_event
from ...services.report_files import dedupe_name
from .. import builder
from .approval import _MAX_BULK, approved_files
from .common import SENDABLE, STATUS_SENT, InvalidRequest, WorkflowError, _load

logger = logging.getLogger(__name__)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MAX_RECIPIENTS = 20

_sending: set[str] = set()

_sending_lock = threading.Lock()


def _default_texts(report: dict) -> tuple[str, str]:
    """Mesmo assunto/mensagem padrão do envio manual (`SendReportModal`)."""
    frozen = report.get("approved_payload_json") or {}
    packages = frozen.get("packages") or []
    custom_report = report.get("kind") == store.KIND_CUSTOM
    fallback_month = (report.get("scope_json") or {}).get("label") if custom_report else None
    month = (packages[0].get("header") or {}).get("month_label") if packages else (fallback_month or builder.month_label(report["competence"]))
    name = (packages[0].get("header") or {}).get("project_name") if len(packages) == 1 else report["project_name"]
    if custom_report:
        # o recorte pode ser uma pessoa, vários projetos… não é "o projeto X"
        return (f"Relatório de Horas - {name} - {month}", f"Segue em anexo o relatório de horas de {name} referente a {month}.")
    return (f"Relatório de Horas - {name} - {month}", f"Segue em anexo o relatório de horas do projeto {name} referente a {month}.")


def send_defaults(report_id: str, actor: dict) -> dict:
    """O que o modal de envio já abre preenchido: destinatários do último
    envio da família, assunto/mensagem padrão, os anexos (do payload
    congelado) e se o envio vai contar no Diagnóstico."""
    report = _load(report_id)
    if report["status"] not in SENDABLE:
        raise WorkflowError("Só dá pra enviar um relatório aprovado.")
    # personalizado não tem família: sem destinatários lembrados
    remembered = (
        {}
        if report.get("kind") == store.KIND_CUSTOM
        else ((store.get_memories([report["family_key"]]).get(report["family_key"]) or {}).get("recipients") or {})
    )
    subject, message = _default_texts(report)
    sender = (actor.get("email") or "").strip()
    return {
        "to": remembered.get("to", []),
        "cc": remembered.get("cc", []),
        "subject": subject,
        "message": message,
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
        raise InvalidRequest(f"\"{project_name}\" não tem arquivo aprovado nesse formato — escolha XLSX, PDF ou os dois entre os aprovados.")
    return picked


def send_report(report_id: str, to: list[str], cc: list[str], subject: str, message: str, actor: dict, formats: list[str] | None = None) -> dict:
    """Um relatório, um e-mail (ver `send_reports`)."""
    return send_reports([report_id], to, cc, subject, message, actor, formats)


@contextmanager
def _sending_guard(ids: list[str]):
    """Marca os relatórios como "enviando" durante o envio: Redis `SET NX`
    com TTL de 15 min quando `REDIS_URL` está setada (vale entre processos da
    topologia de containers); senão o set em memória de sempre (processo
    único — default de dev/testes)."""
    client = get_redis_client()
    if client is None:
        with _sending_lock:
            if any(i in _sending for i in ids):
                raise WorkflowError("Um desses relatórios já está sendo enviado.")
            _sending.update(ids)
        try:
            yield
        finally:
            with _sending_lock:
                _sending.difference_update(ids)
        return
    keys = [f"sending:{i}" for i in ids]
    acquired: list[str] = []
    try:
        for key in keys:
            if not client.set(key, "1", nx=True, ex=900):
                raise WorkflowError("Um desses relatórios já está sendo enviado.")
            acquired.append(key)
        yield
    finally:
        if acquired:
            client.delete(*acquired)


def send_reports(report_ids: list[str], to: list[str], cc: list[str], subject: str, message: str, actor: dict, formats: list[str] | None = None) -> dict:
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
    with _sending_guard(ids):
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
            sender_email=sender, to_email=to_list, cc_emails=cc_list, subject=subject.strip(), body_text=message, attachments=attachments
        )
        # leitura FORA da transação de escrita (ver `approve`)
        families_sent = sorted({r["family_key"] for r in reports if r.get("kind") != store.KIND_CUSTOM})
        previous = store.get_memories(families_sent)
        now = store.utcnow()
        with store.write_session() as s:
            for report in reports:
                s.update_report(report["id"], status=STATUS_SENT, sent_by=actor.get("login"), sent_at=now)
                s.add_event(
                    report["id"],
                    "sent",
                    actor,
                    None,
                    {
                        "to": to_list,
                        "cc": cc_list,
                        "subject": subject.strip(),
                        "files": names_by_report[report["id"]],
                        # enviado junto com outros no mesmo e-mail
                        "combined_with": [i for i in ids if i != report["id"]],
                    },
                )
            for family in families_sent:
                source = next(r["id"] for r in reports if r["family_key"] == family)
                s.set_memory(family, {**(previous.get(family) or {}), "recipients": {"to": to_list, "cc": cc_list}}, source)
    for report in reports:
        record_event(
            actor_id=actor.get("login", ""),
            actor_name=actor.get("name", ""),
            action="auto_report_sent",
            entity_type="auto_report",
            entity_id=report["id"],
            source="auto_generation",
            metadata={"competence": report["competence"], "project_id": report["project_id"], "to": to_list, "cc": cc_list, "combined": len(ids) > 1},
        )
    return {"status": STATUS_SENT, "sent_at": now, "sent": ids}
