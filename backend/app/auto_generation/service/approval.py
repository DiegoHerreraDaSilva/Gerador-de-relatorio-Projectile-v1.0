"""Aprovação: validação de número, arquivos congelados e persistência."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid

from ...generator import NonFiniteValueError
from ...services import auto_generation_store as store
from ...services.audit import record_event
from ...services.report_files import FORMAT_MEDIA_TYPES, GeneratePayload, build_report_file, dedupe_name, persistence_pkg_data, sanitized_file_name
from ...services.report_persistence import GenerationGuard, finish_generation_failure, finish_generation_success
from .. import builder, families, memory, rules
from .common import APPROVABLE, SENDABLE, STATUS_APPROVED, STATUS_SKIPPED, ApprovalRejected, InvalidRequest, WorkflowError, _load, _pattern_label

logger = logging.getLogger(__name__)


def _number_errors(report: dict, payload: GeneratePayload, pattern: str) -> tuple[list[str], list[str]]:

    errors: list[str] = []
    warnings: list[str] = []
    codes = [p.header.project_code.strip() for p in payload.packages]
    regex = re.compile(pattern)
    for pkg, code in zip(payload.packages, codes, strict=False):
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
    is_custom = report.get("kind") == store.KIND_CUSTOM
    previous = None if is_custom else store.get_memories([report["family_key"]]).get(report["family_key"])
    with store.write_session() as s:
        current = s.get_report_for_update(report_id)
        if current is None or current["status"] not in APPROVABLE or current["draft_version"] != expected_version:
            raise WorkflowError("O relatório mudou enquanto era aprovado — recarregue.")
        now = store.utcnow()
        s.update_report(
            report_id,
            bump_version=True,
            status=STATUS_APPROVED,
            approved_payload_json=payload.model_dump(),
            approved_by=actor.get("login"),
            approved_at=now,
            history_links_json=links,
        )
        reviewer = {"login": report.get("reviewer_login"), "name": report.get("reviewer_name")}
        if not is_custom:  # o recorte avulso não tem família: não sobrescreve memória de ninguém
            s.set_memory(report["family_key"], memory.extract(draft, previous, reviewer), report_id)
        s.add_event(report_id, "approved", actor, None, {"numbers": [p.header.project_code for p in payload.packages]})
    record_event(
        actor_id=actor.get("login", ""),
        actor_name=actor.get("name", ""),
        action="auto_report_approved",
        entity_type="auto_report",
        entity_id=report_id,
        source="auto_generation",
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
            handle = guard.begin(persistence_pkg_data(pkg), fmt, actor.get("login", ""), actor.get("name", ""), created_from="auto_approval")
            try:
                header = build_report_file(pkg, tmp_path, fmt)
            except NonFiniteValueError as e:
                finish_generation_failure(handle, e)
                raise ApprovalRejected([str(e)]) from e
            except Exception as e:
                finish_generation_failure(handle, e)
                raise
            else:
                finish_generation_success(handle, tmp_path, sanitized_file_name(pkg.file_name, header, fmt), fmt, FORMAT_MEDIA_TYPES[fmt])
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
