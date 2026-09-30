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
from .common import SENDABLE, STATUS_SENT, InvalidRequest, SendUncertain, WorkflowError, _load

logger = logging.getLogger(__name__)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MAX_RECIPIENTS = 20

# eventos que contam a história de um envio: a ÚLTIMA ação de cada relatório diz
# em que pé ele está. `send_attempt` sem nada depois = envio incerto.
SEND_ACTIONS = ("send_attempt", "sent", "send_failed", "send_resolved")

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


def uncertain_sends(report_ids: list[str]) -> dict[str, dict]:
    """Relatórios cuja ÚLTIMA ação de envio é uma tentativa sem desfecho: o
    e-mail pode ou não ter saído (queda do banco depois do Graph, timeout,
    processo reiniciado no meio). Devolve o evento da tentativa por relatório."""
    latest = store.latest_comments(report_ids, SEND_ACTIONS)
    return {report_id: event for report_id, event in latest.items() if event["action"] == "send_attempt"}


def _uncertain_message(reports: list[dict], pending: dict[str, dict]) -> str:
    names = ", ".join(f"\"{r['project_name']}\"" for r in reports if r["id"] in pending)
    return f"Há um envio sem confirmação para {names}: o e-mail pode já ter chegado ao cliente. Confirme se chegou ou não chegou antes de enviar de novo."


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


def _record_send_failed(ids: list[str], actor: dict) -> None:
    """Graph recusou (4xx / configuração): provadamente NÃO saiu, então a tentativa
    se resolve sozinha e o envio pode ser repetido. Fail-open: se nem isso gravar,
    o relatório fica "incerto" (o lado seguro)."""
    try:
        with store.write_session() as s:
            for report_id in ids:
                s.add_event(report_id, "send_failed", actor, None, None)
    except Exception:
        logger.exception("Não consegui registrar a falha do envio (%s)", ids)


def resolve_send(report_id: str, resolution: str, actor: dict) -> dict:
    """O gerente diz o que aconteceu com um envio incerto: `sent` (chegou — vira
    `enviado`, sem mandar nada) ou `not_sent` (não chegou — libera enviar de novo)."""
    if resolution not in ("sent", "not_sent"):
        raise InvalidRequest("Resolução inválida (use sent ou not_sent).")
    report = _load(report_id)
    pending = uncertain_sends([report_id]).get(report_id)
    if pending is None:
        raise WorkflowError("Este relatório não tem envio pendente de confirmação.")
    now = store.utcnow()
    meta = pending.get("metadata") or {}
    with store.write_session() as s:
        if resolution == "sent":
            s.update_report(report_id, status=STATUS_SENT, sent_by=actor.get("login"), sent_at=now)
            s.add_event(report_id, "sent", actor, None, {**meta, "confirmed_manually": True})
        else:
            s.add_event(report_id, "send_resolved", actor, None, {"resolution": "not_sent"})
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action="auto_report_send_resolved",
        entity_type="auto_report",
        entity_id=report_id,
        source="auto_generation",
        metadata={"competence": report["competence"], "project_id": report["project_id"], "resolution": resolution},
    )
    return {"status": STATUS_SENT if resolution == "sent" else report["status"], "resolution": resolution}


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
        if pending := uncertain_sends(ids):
            raise SendUncertain(_uncertain_message(reports, pending))
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
        # 1) a tentativa é gravada (e confirmada) ANTES do Graph: se nada mais puder ser
        # gravado depois, o envio fica "incerto" em vez de parecer que nunca aconteceu
        # (e o próximo clique mandar o e-mail de novo). Sem conseguir gravar, não envia.
        with store.write_session() as s:
            for report in reports:
                s.add_event(
                    report["id"],
                    "send_attempt",
                    actor,
                    None,
                    {"to": to_list, "cc": cc_list, "subject": subject.strip(), "files": names_by_report[report["id"]]},
                )
        try:
            email_ingest.send_report_email(
                sender_email=sender, to_email=to_list, cc_emails=cc_list, subject=subject.strip(), body_text=message, attachments=attachments
            )
        except email_ingest.EmailIngestError as e:
            if getattr(e, "maybe_delivered", False):
                # timeout / queda / 5xx: o Graph pode ter aceitado — a tentativa fica sem desfecho
                logger.warning("Envio sem confirmação do Graph (%s): %s", ids, e)
                raise SendUncertain(
                    "Não deu pra confirmar se o e-mail foi enviado (o Microsoft Graph não respondeu direito). "
                    "Confira na sua caixa de saída e marque se chegou ou não chegou."
                ) from e
            _record_send_failed(ids, actor)
            raise
        # 2) o Graph aceitou: daqui pra frente uma falha de registro NÃO pode virar "não enviado"
        try:
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
        except Exception as e:
            logger.exception("E-mail aceito pelo Graph, mas o registro do envio falhou (%s)", ids)
            raise SendUncertain(
                "O e-mail FOI enviado, mas não consegui registrar o envio no sistema. Confirme em \"Envio incerto\" que ele chegou; não envie de novo."
            ) from e
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
