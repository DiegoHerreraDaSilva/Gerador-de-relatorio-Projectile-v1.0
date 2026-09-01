"""Automação do preenchimento de Horas Faturadas e KPI (Dias) no Painel de
Gerência a partir dos e-mails do gerente de engenharia (Alberto) pros
clientes, com a caixa `agente.reunioes@schwaben.com.br` em cópia.

Fluxo (`process_new_emails`, chamado periodicamente pelo loop de polling em
`main.py`): busca mensagens novas na caixa via Microsoft Graph (client
credentials, sem interação de usuário) → baixa o anexo `.xlsx` → lê o projeto
(células `B8`/`C9`, ver `generator.py`) e resolve o valor de "Total de horas
Mês/Ano:" (fórmula, não valor em cache — ver `resolve_total_hours`) → faz
fuzzy match do nome do projeto contra o Projectile → calcula dias úteis entre
o fechamento do mês do relatório e o envio do e-mail → grava uma amostra em
`backend/data/management_kpi.json` via `management.append_project_kpi_sample`.

Não usa `data_only=True`/valor em cache do Excel: os relatórios deste app são
gerados via ZIP/XML manual (`generator.py`, nunca `openpyxl.save()`), então a
fórmula nunca tem um `<v>` calculado embutido — even que o anexo já tenha
sido aberto no Excel por alguém no meio do caminho, não há garantia disso.
`resolve_total_hours` por isso segue a cadeia de fórmulas manualmente,
reconhecendo só as 3 formas exatas que `generator._build_groups_xml` escreve.
"""
from __future__ import annotations

import base64
import difflib
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone

import msal
import requests
from openpyxl import load_workbook

from . import management
from .generator import _parse_month_label, count_business_days
from .projectile_db import ProjectileDbError, fetch_all_projects

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MAX_FORMULA_DEPTH = 10
_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


class EmailIngestError(RuntimeError):
    """Falha ao consultar o Graph, ler um anexo ou resolver a fórmula de
    "Total de horas" — nunca um erro do usuário, sempre um problema de
    configuração/anexo/template que precisa de atenção manual."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EmailIngestError(
            f"Configuração ausente para a automação de e-mail: defina {name} no .env "
            "(veja .env.example)."
        )
    return value


# App confidencial único em nível de módulo — o MSAL já cacheia o token de
# acesso internamente entre chamadas, então não é preciso gerenciar expiração
# aqui manualmente (mesmo espírito de reaproveitamento de
# `projectile_db._get_connection`, adaptado pra um client HTTP em vez de uma
# conexão de banco).
_msal_app: msal.ConfidentialClientApplication | None = None


def _get_msal_app() -> msal.ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        tenant_id = _require_env("AZURE_TENANT_ID")
        client_id = _require_env("AZURE_CLIENT_ID")
        client_secret = _require_env("AZURE_CLIENT_SECRET")
        _msal_app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
    return _msal_app


def _get_graph_token() -> str:
    app = _get_msal_app()
    result = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise EmailIngestError(
            f"Falha ao autenticar no Microsoft Graph: {result.get('error_description') or result}"
        )
    return result["access_token"]


def _graph_get(url: str, params: dict | None = None) -> dict:
    """Isola toda chamada HTTP ao Graph num único ponto — facilita mockar a
    orquestração (`process_new_emails`) em teste sem precisar de credencial
    real, e centraliza o tratamento de erro."""
    token = _get_graph_token()
    try:
        resp = requests.get(
            url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise EmailIngestError(f"Falha ao consultar o Microsoft Graph: {e}") from e


def fetch_new_messages() -> list[dict]:
    """Mensagens do Alberto na caixa `GRAPH_MAILBOX` com anexo, ainda não
    processadas (ver `management.is_message_processed`). Filtra no próprio
    Graph (`$filter`) pra não baixar corpo/metadado de mensagens irrelevantes.

    Sem `$orderby`: combinado com este `$filter` (que usa uma propriedade
    aninhada, `from/emailAddress/address`), o Graph devolve 400
    "InefficientFilter" ("restriction or sort order is too complex") —
    confirmado testando ao vivo contra a caixa real. Não precisamos de ordem
    nenhuma aqui (a idempotência é por `message_id`, não por posição), então
    a solução é simplesmente não pedir ordenação, em vez de contornar com o
    header `ConsistencyLevel: eventual` (que muda semântica de contagem e
    paginação sem necessidade real neste caso)."""
    mailbox = _require_env("GRAPH_MAILBOX")
    sender = _require_env("ALBERTO_EMAIL")
    url = f"{GRAPH_BASE}/users/{mailbox}/messages"
    params = {
        "$filter": f"from/emailAddress/address eq '{sender}' and hasAttachments eq true",
        "$select": "id,subject,receivedDateTime,from",
        "$top": "50",
    }
    messages: list[dict] = []
    while url:
        data = _graph_get(url, params)
        for msg in data.get("value", []):
            if not management.is_message_processed(msg["id"]):
                messages.append(msg)
        url = data.get("@odata.nextLink")
        params = None  # já embutido no nextLink
    return messages


def fetch_xlsx_attachments(message_id: str) -> list[str]:
    """Baixa os anexos `.xlsx` da mensagem pra arquivos temporários (mesmo
    padrão de `parser.py`/`generator.py`, que também usam `tempfile`) e
    devolve os caminhos."""
    mailbox = _require_env("GRAPH_MAILBOX")
    data = _graph_get(f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}/attachments")
    paths = []
    for att in data.get("value", []):
        name = att.get("name") or ""
        content_bytes = att.get("contentBytes")
        if not content_bytes or not name.lower().endswith(".xlsx"):
            continue
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(base64.b64decode(content_bytes))
            paths.append(tmp.name)
    return paths


def _resolve_cell(ws, ref: str, seen: set[str], depth: int = 0) -> float:
    """Segue a cadeia de fórmulas escrita por `generator._build_groups_xml`
    até um número. Reconhece só as 3 formas que esse template gera:
    `=SUM(ref,ref,...)`, referência simples a outra célula (`=E12`), e
    produto de duas células (`=E12*F12`). Qualquer outra forma é um sinal de
    que o template mudou — falha alto em vez de devolver um número errado
    silenciosamente."""
    if depth > _MAX_FORMULA_DEPTH or ref in seen:
        raise EmailIngestError(f"Fórmula circular ou profunda demais ao resolver {ref}.")
    seen = seen | {ref}

    value = ws[ref].value
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.startswith("="):
        raise EmailIngestError(f"Valor inesperado (não numérico, não fórmula) em {ref}: {value!r}")

    formula = value[1:]

    sum_match = re.fullmatch(r"SUM\(([^()]+)\)", formula)
    if sum_match:
        refs = [r.strip() for r in sum_match.group(1).split(",") if r.strip()]
        return sum(_resolve_cell(ws, r, seen, depth + 1) for r in refs)

    product_match = re.fullmatch(r"([A-Z]+\d+)\*([A-Z]+\d+)", formula)
    if product_match:
        return _resolve_cell(ws, product_match.group(1), seen, depth + 1) * _resolve_cell(
            ws, product_match.group(2), seen, depth + 1
        )

    if _CELL_REF_RE.fullmatch(formula):
        return _resolve_cell(ws, formula, seen, depth + 1)

    raise EmailIngestError(f"Forma de fórmula não reconhecida em {ref}: ={formula}")


def resolve_total_hours(xlsx_path: str) -> tuple[float, str]:
    """Acha a linha "Total de horas <mês/ano>:" na coluna B e resolve a
    fórmula da coluna C na mesma linha. Devolve (horas, month_label) — o
    `month_label` (ex: "Julho/2026") vem do próprio texto da label, é a
    competência do relatório, não a data de hoje nem a data de envio."""
    wb = load_workbook(xlsx_path, data_only=False)
    ws = wb.active
    label_re = re.compile(r"^Total de horas\s+(.+?):$")
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            match = label_re.match(cell.value.strip())
            if not match:
                continue
            total_ref = f"C{cell.row}"
            hours = _resolve_cell(ws, total_ref, set())
            return round(hours, 3), match.group(1).strip()
    raise EmailIngestError("Não encontrei a célula 'Total de horas ...:' no anexo.")


def read_project_identity(xlsx_path: str) -> tuple[str, str]:
    """Lê `project_code` (B8) e `project_name` (C9), gravados por
    `generator.generate_report` em todo relatório emitido pelo app."""
    wb = load_workbook(xlsx_path, data_only=False)
    ws = wb.active
    project_code = str(ws["B8"].value or "").strip()
    project_name = str(ws["C9"].value or "").strip()
    if not project_name:
        raise EmailIngestError("Não encontrei o nome do projeto (célula C9) no anexo.")
    return project_code, project_name


def match_project(report_project_name: str, candidates: dict[str, str]) -> tuple[str, str, float]:
    """Fuzzy match do texto livre do relatório contra `tproject.pDescription`
    — decisão do usuário: sempre aplica o melhor candidato disponível, mesmo
    com pouca confiança (sem fila de revisão manual). `match_score` fica
    salvo na amostra pra auditoria via o endpoint de diagnóstico."""
    if not candidates:
        raise EmailIngestError("Nenhum projeto cadastrado no Projectile para comparar.")
    names = list(candidates.values())
    ids_by_name: dict[str, str] = {}
    for pid, name in candidates.items():
        ids_by_name.setdefault(name, pid)

    best_name = None
    best_score = 0.0
    for name in names:
        score = difflib.SequenceMatcher(None, report_project_name.casefold(), name.casefold()).ratio()
        if score > best_score:
            best_score, best_name = score, name
    return ids_by_name[best_name], best_name, round(best_score, 3)


def _month_end(year: int, month: int) -> date:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return next_month - timedelta(days=1)


def compute_business_days_elapsed(month_label: str, sent_at: datetime) -> int:
    """Dias úteis entre o último dia do mês do relatório (competência lida da
    própria label "Total de horas <mês/ano>:") e a data de envio do e-mail."""
    parsed = _parse_month_label(month_label)
    if parsed is None:
        raise EmailIngestError(f"Não reconheço o formato de competência: {month_label!r}")
    year, month = parsed
    anchor = _month_end(year, month)
    return count_business_days(anchor, sent_at.date())


def process_new_emails() -> dict:
    """Orquestra um ciclo de polling. Chamado periodicamente pelo loop em
    `main.py` (`_poll_emails_loop`) e também sob demanda pelo botão
    "Verificar horas faturadas" do painel (`POST /management/kpis/check-emails`).
    Idempotente por `message_id` — seguro de chamar repetidamente, inclusive
    após um restart do `--reload` ou disparado manualmente enquanto o
    polling automático também está rodando. Devolve um resumo (contagens)
    pra dar feedback imediato de quem chamou sob demanda."""
    messages = fetch_new_messages()
    summary = {"messages_found": len(messages), "samples_added": 0, "skipped": 0}
    if not messages:
        return summary

    candidates = fetch_all_projects()

    for msg in messages:
        message_id = msg["id"]
        received_at = msg.get("receivedDateTime") or ""
        try:
            sent_at = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        except ValueError:
            sent_at = datetime.now(timezone.utc)

        try:
            attachments = fetch_xlsx_attachments(message_id)
            if not attachments:
                management.append_skipped_message(message_id, received_at, "anexo .xlsx não encontrado")
                summary["skipped"] += 1
                continue

            xlsx_path = attachments[0]
            try:
                billed_hours, month_label = resolve_total_hours(xlsx_path)
                _, report_project_name = read_project_identity(xlsx_path)
            finally:
                for path in attachments:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

            project_id, project_name, score = match_project(report_project_name, candidates)
            business_days = compute_business_days_elapsed(month_label, sent_at)
            parsed_month = _parse_month_label(month_label)
            month_key = f"{parsed_month[0]:04d}-{parsed_month[1]:02d}"

            management.append_project_kpi_sample({
                "email_message_id": message_id,
                "received_at": received_at,
                "sender": (msg.get("from") or {}).get("emailAddress", {}).get("address", ""),
                "report_project_text": report_project_name,
                "project_id": project_id,
                "project_name": project_name,
                "match_score": score,
                "month": month_key,
                "billed_hours": billed_hours,
                "business_days": business_days,
            })
            summary["samples_added"] += 1
        except (EmailIngestError, ProjectileDbError) as e:
            management.append_skipped_message(message_id, received_at, str(e))
            summary["skipped"] += 1

    return summary
