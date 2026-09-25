"""Rotas do Painel de Gerência e Diagnóstico (`/management/*`) — extraído de
`main.py`. Nome igual ao módulo `backend/app/management.py` (regra
de negócio/persistência JSON) de propósito — são camadas diferentes
(`backend.app.api.routers.management` vs `backend.app.management`), mesmo
domínio; sempre importe explicitamente com alias se os dois forem usados no
mesmo arquivo (ver `main.py`)."""
from __future__ import annotations

import asyncio
import os
import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ... import email_ingest
from ...management import (
    _resolve_period,
    compute_monthly_kpis,
    create_manual_project_kpi_sample,
    delete_project_kpi_sample,
    get_closed_registry,
    list_pacotes_for_project,
    list_samples,
    set_client_closed,
    set_manual_entry,
    set_project_closed,
    update_project_kpi_sample,
)
from ...projectile_db import (
    ProjectileDbError,
    fetch_all_projects_with_details,
    fetch_clients_for_projects,
    fetch_project_codes,
    fetch_project_details,
    fetch_project_ids_for_clients,
    fetch_project_ids_with_hours,
)
from ..dependencies import is_manager, require_manager, require_manager_or_coordinator
from ..errors import GENERIC_DB_ERROR, GENERIC_EMAIL_ERROR, log_and_generic_error
from ..shared import resolve_month_range

router = APIRouter()

COORDINATOR_PERIOD_ERROR = "Coordenador vê só os últimos 12 meses e o ano passado."


def _coordinator_months() -> set[str]:
    """Meses que o coordenador pode ver no Diagnóstico: os últimos 12 meses
    corridos e o ano passado inteiro. Gerente vê todos os períodos."""
    _, _, rolling = _resolve_period(12, None)
    _, _, last_year = _resolve_period(12, date.today().year - 1)
    return set(rolling) | set(last_year)


def _check_coordinator_period(user: dict, months: int, year: int | None) -> None:
    """Barra no backend o que a tela já esconde: coordenador só pede os
    últimos 12 meses (`months=12`, sem `year`) ou o ano passado."""
    if is_manager(user):
        return
    if year is None and months == 12:
        return
    if year == date.today().year - 1:
        return
    raise HTTPException(403, COORDINATOR_PERIOD_ERROR)


@router.get("/management/clients-with-hours")
async def management_clients_with_hours_endpoint(month_label: str, _user: dict = Depends(require_manager_or_coordinator)):
    """Clientes com ao menos um lançamento de hora no mês — popula a busca de
    Cliente na tela de importação "por cliente" (`FileUpload.tsx`), só com
    quem teve movimento naquele período (não o cadastro inteiro do
    Projectile)."""
    start_date, end_date = resolve_month_range(month_label)
    try:
        project_ids = fetch_project_ids_with_hours(start_date, end_date)
        clients = fetch_clients_for_projects(project_ids)
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    return {"clients": clients}


@router.get("/management/client-projects")
async def management_client_projects_endpoint(
    client: str, month_label: str, _user: dict = Depends(require_manager_or_coordinator)
):
    """Projetos de um cliente com ao menos um lançamento de hora no mês —
    popula o seletor multi-seleção de projeto da tela de importação "por
    cliente"."""
    start_date, end_date = resolve_month_range(month_label)
    try:
        active_ids = set(fetch_project_ids_with_hours(start_date, end_date))
        client_ids = set(fetch_project_ids_for_clients([client]))
        codes = fetch_project_codes(start_date, end_date)
        details = fetch_project_details(sorted(active_ids & client_ids))
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    projects = sorted(
        ({"id": pid, "name": info["name"], "code": codes.get(pid, "")} for pid, info in details.items()),
        key=lambda p: (int(p["code"]) if p["code"].isdigit() else float("inf"), p["name"]),
    )
    return {"projects": projects}


@router.get("/management/kpis")
async def management_kpis_endpoint(
    months: int = 12,
    year: int | None = None,
    cost_centers: list[str] = Query(default=[]),
    clients: list[str] = Query(default=[]),
    projects: list[str] = Query(default=[]),
    packages: list[str] = Query(default=[]),
    selected_months: list[str] = Query(default=[]),
    persons: list[str] = Query(default=[]),
    force_refresh: bool = False,
    _user: dict = Depends(require_manager),
):
    try:
        return compute_monthly_kpis(
            months,
            year=year,
            cost_centers=cost_centers or None,
            clients=clients or None,
            projects=projects or None,
            packages=packages or None,
            selected_months=selected_months or None,
            persons=persons or None,
            force_refresh=force_refresh,
        )
    except ProjectileDbError as e:
        raise log_and_generic_error(e)


# o que o Diagnóstico precisa de `compute_monthly_kpis`, e nada além disso —
# lista BRANCA de propósito: um campo novo de KPI que entrar em
# `compute_monthly_kpis` não vaza sozinho pra coordenador.
_SEND_STATUS_KEYS = (
    "project_send_status", "available_projects", "available_clients",
    "available_packages", "available_persons", "project_codes", "project_clients",
)


@router.get("/management/send-status")
async def management_send_status_endpoint(
    months: int = 12,
    year: int | None = None,
    cost_centers: list[str] = Query(default=[]),
    clients: list[str] = Query(default=[]),
    projects: list[str] = Query(default=[]),
    packages: list[str] = Query(default=[]),
    selected_months: list[str] = Query(default=[]),
    persons: list[str] = Query(default=[]),
    force_refresh: bool = False,
    _user: dict = Depends(require_manager_or_coordinator),
):
    """Versão de `/management/kpis` pro Diagnóstico, acessível a coordenador
    (só nos períodos de `_check_coordinator_period`):
    status de envio por projeto/mês e opções de filtro, SEM horas
    trabalhadas/faturadas, performance ou não faturáveis. `months` vem só com
    a chave do mês (a tela usa pra saber quais meses estão no período)."""
    _check_coordinator_period(_user, months, year)
    try:
        result = compute_monthly_kpis(
            months,
            year=year,
            cost_centers=cost_centers or None,
            clients=clients or None,
            projects=projects or None,
            packages=packages or None,
            selected_months=selected_months or None,
            persons=persons or None,
            force_refresh=force_refresh,
        )
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    return {
        "months": [{"month": row["month"]} for row in result["months"]],
        **{key: result[key] for key in _SEND_STATUS_KEYS},
    }


@router.post("/management/kpis/check-emails")
async def management_check_emails_endpoint(_user: dict = Depends(require_manager)):
    """Dispara sob demanda o mesmo ciclo de polling de e-mail (botão
    "Verificar horas faturadas" no painel), sem esperar o próximo intervalo
    de polling. Síncrono/bloqueante por natureza (Graph + openpyxl), por isso
    roda em thread separada (`to_thread`) pra não travar o event loop."""
    if not os.environ.get("AZURE_CLIENT_ID"):
        raise HTTPException(400, "Automação de e-mail não configurada (AZURE_* ausente no .env).")
    try:
        return await asyncio.to_thread(email_ingest.process_new_emails)
    except (email_ingest.EmailIngestError, ProjectileDbError) as e:
        generic = GENERIC_EMAIL_ERROR if isinstance(e, email_ingest.EmailIngestError) else GENERIC_DB_ERROR
        raise log_and_generic_error(e, generic_message=generic)


@router.get("/management/projects")
async def management_projects_endpoint(_user: dict = Depends(require_manager_or_coordinator)):
    """Lista de todos os projetos do Projectile (id/nome/cliente), sem
    recorte por período — alimenta o seletor de projeto da tela de
    Diagnóstico (cadastro/edição manual de amostra), onde o gerente precisa
    poder escolher qualquer projeto, não só os que já apareceram num
    período específico."""
    try:
        return fetch_all_projects_with_details()
    except ProjectileDbError as e:
        raise log_and_generic_error(e)


@router.get("/management/kpis/samples")
async def management_kpi_samples_endpoint(month: str | None = None, _user: dict = Depends(require_manager_or_coordinator)):
    """Tela de Diagnóstico: mostra de quais e-mails (ou cadastro manual)
    vieram as horas faturadas/dias de cada (projeto, mês), e o que foi
    pulado e por quê — necessário porque o match de projeto é automático,
    sem fila de revisão humana (ver `email_ingest.match_project`). Sem
    `month`, lista tudo (aba "Todos" da tela)."""
    if month is not None and not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "Mês inválido, use o formato AAAA-MM.")
    result = list_samples(month)
    if is_manager(_user):
        return result
    # coordenador: só amostras e mensagens puladas dos meses que ele pode ver
    allowed = _coordinator_months()
    return {
        "samples": [s for s in result["samples"] if s.get("month") in allowed],
        "skipped_messages": [
            s for s in result["skipped_messages"] if str(s.get("received_at") or "")[:7] in allowed
        ],
    }


class ManualSampleCreatePayload(BaseModel):
    project_id: str
    month: str
    billed_hours: float = Field(ge=0, allow_inf_nan=False)
    business_days: float = Field(ge=0, allow_inf_nan=False)


@router.post("/management/kpis/samples")
async def management_kpi_sample_create_endpoint(
    payload: ManualSampleCreatePayload, _user: dict = Depends(require_manager_or_coordinator)
):
    """Cadastro manual de amostra — pra quando um relatório foi enviado fora
    do fluxo de e-mail, ou o match automático nunca achou o projeto certo."""
    if not re.fullmatch(r"\d{4}-\d{2}", payload.month):
        raise HTTPException(400, "Mês inválido, use o formato AAAA-MM.")
    try:
        projects = fetch_all_projects_with_details()
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    project = next((p for p in projects if p["id"] == payload.project_id), None)
    if not project:
        raise HTTPException(400, "Projeto não encontrado no Projectile.")
    return create_manual_project_kpi_sample(
        project_id=payload.project_id,
        project_name=project["name"],
        month=payload.month,
        billed_hours=payload.billed_hours,
        business_days=payload.business_days,
    )


class SampleUpdatePayload(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    billed_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    business_days: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    # None/lista vazia = "projeto inteiro"; 1+ pacotes = só esses pacotes de
    # trabalho foram cobertos por essa amostra (ver management.py,
    # compute_monthly_kpis/_recompute_duplicate_flags). Sentinela
    # `"__unset__"` (em vez do default None de todo campo aqui) porque None
    # É um valor válido de verdade ("projeto inteiro") — sem isso,
    # `exclude_unset` não conseguiria distinguir "o usuário quer limpar pra
    # projeto inteiro" de "o usuário não mexeu nesse campo".
    pacote_scope: list[str] | None | Literal["__unset__"] = "__unset__"


@router.patch("/management/kpis/samples/{sample_id}")
async def management_kpi_sample_update_endpoint(
    sample_id: str, payload: SampleUpdatePayload, _user: dict = Depends(require_manager_or_coordinator)
):
    """Corrige uma amostra existente — projeto errado (match automático
    fraco), horas/dias lidos errado, competência errada, ou pacote de
    trabalho coberto (projeto inteiro vs 1+ pacotes específicos)."""
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("pacote_scope") == "__unset__":
        del patch["pacote_scope"]
    if not update_project_kpi_sample(sample_id, patch):
        raise HTTPException(404, "Amostra não encontrada.")
    return {"ok": True}


@router.get("/management/projects/{project_id}/packages")
async def management_project_packages_endpoint(
    project_id: str, month: str = Query(pattern=r"^\d{4}-\d{2}$"), _user: dict = Depends(require_manager_or_coordinator)
):
    """Pacotes de trabalho com hora de verdade nesse projeto/mês no
    Projectile — alimenta o multi-select de "Pacote de trabalho" na edição
    de amostra do Diagnóstico (ver `list_pacotes_for_project`)."""
    try:
        return {"packages": list_pacotes_for_project(project_id, month)}
    except ProjectileDbError as e:
        raise log_and_generic_error(e)


@router.get("/management/projects/{project_id}/all-packages")
async def management_project_all_packages_endpoint(project_id: str, _user: dict = Depends(require_manager_or_coordinator)):
    """Todo o histórico de pacotes de trabalho desse projeto (sem recorte de
    mês) — alimenta a lista só-leitura de pacotes ao expandir um projeto no
    popup de "Fechados": fechar é permanente, então o gerente precisa ver
    todos os pacotes que já existiram, não só os do mês/Período em vista no
    painel no momento (ver `list_pacotes_for_project(month=None)`)."""
    try:
        return {"packages": list_pacotes_for_project(project_id, None)}
    except ProjectileDbError as e:
        raise log_and_generic_error(e)


@router.get("/management/closed-registry")
async def management_closed_registry_endpoint(_user: dict = Depends(require_manager_or_coordinator)):
    """Popup de "Fechados" do Painel de Gerência: todos os projetos do
    Projectile (fechar é permanente/atemporal, não só do período em vista
    no painel, ao contrário do resto da tela) junto com o registro atual de
    clientes/projetos fechados."""
    try:
        projects = fetch_all_projects_with_details()
    except ProjectileDbError as e:
        raise log_and_generic_error(e)
    for p in projects:
        p["client"] = p["client"] or "Sem cliente"
    return {**get_closed_registry(), "projects": projects}


@router.post("/management/closed-registry/clients/{client}")
async def management_close_client_endpoint(client: str, _user: dict = Depends(require_manager_or_coordinator)):
    set_client_closed(client, True)
    return {"ok": True}


@router.delete("/management/closed-registry/clients/{client}")
async def management_reopen_client_endpoint(client: str, _user: dict = Depends(require_manager_or_coordinator)):
    set_client_closed(client, False)
    return {"ok": True}


@router.post("/management/closed-registry/projects/{project_id}")
async def management_close_project_endpoint(project_id: str, _user: dict = Depends(require_manager_or_coordinator)):
    set_project_closed(project_id, True)
    return {"ok": True}


@router.delete("/management/closed-registry/projects/{project_id}")
async def management_reopen_project_endpoint(project_id: str, _user: dict = Depends(require_manager_or_coordinator)):
    set_project_closed(project_id, False)
    return {"ok": True}


@router.delete("/management/kpis/samples/{sample_id}")
async def management_kpi_sample_delete_endpoint(sample_id: str, _user: dict = Depends(require_manager_or_coordinator)):
    """Remove uma amostra errada. O e-mail original continua marcado como
    processado — não volta a ser reprocessado no próximo polling."""
    if not delete_project_kpi_sample(sample_id):
        raise HTTPException(404, "Amostra não encontrada.")
    return {"ok": True}


class ManualEntryPayload(BaseModel):
    billed_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    elaboration_days: float | None = Field(default=None, ge=0, allow_inf_nan=False)


@router.put("/management/kpis/{month}")
async def management_manual_entry_endpoint(
    month: str, payload: ManualEntryPayload, _user: dict = Depends(require_manager)
):
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "Mês inválido, use o formato AAAA-MM.")
    set_manual_entry(month, payload.billed_hours, payload.elaboration_days)
    return {"ok": True}
