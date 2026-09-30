"""Contratos da geração automática — o rascunho que volta do editor e os
pedidos das rotas. Tudo com `extra="forbid"` e números finitos: o rascunho
vem do navegador e vira arquivo e memória do mês seguinte."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

_Id = Field(min_length=1, max_length=64)
_Name = Field(max_length=500)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftActivity(_Strict):
    id: str = _Id
    source_key: str | None = Field(default=None, max_length=500)
    description: str = _Name
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class DraftGroup(_Strict):
    id: str = _Id
    source_key: str | None = Field(default=None, max_length=500)
    name: str = _Name
    performance: float = Field(ge=0, allow_inf_nan=False)
    activities: list[DraftActivity] = Field(max_length=2000)


class DraftPackage(_Strict):
    id: str = _Id
    key: str = Field(max_length=500)
    source_key: str | None = Field(default=None, max_length=500)
    project_code: str = Field(default="", max_length=100)
    suggested_code: str = Field(default="", max_length=100)
    project_name: str = _Name
    pacote_scope: str | None = Field(default=None, max_length=500)
    language: Literal["pt", "en", "de"] = "pt"
    chart_bar: bool = False
    chart_pie: bool = False
    groups: list[DraftGroup] = Field(max_length=500)


class DraftHeader(_Strict):
    location_date: str = Field(max_length=200)
    month_label: str = Field(max_length=100)
    signer1_name: str = Field(default="", max_length=200)
    signer1_company: str = Field(default="", max_length=200)
    signer2_name: str = Field(default="", max_length=200)
    signer2_company: str = Field(default="", max_length=200)


class DraftIssue(BaseModel):
    """Linha do Projectile que não virou atividade (ex.: horas sem descrição)
    — o revisor vê no aviso do editor e pode "Adicionar como atividade"."""

    model_config = ConfigDict(extra="ignore")
    row: int | None = None
    reason: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None, max_length=1000)
    raw_hours: float | None = Field(default=None, allow_inf_nan=False)
    raw_description: str | None = Field(default=None, max_length=1000)


class Draft(_Strict):
    schema_: int = Field(default=1, alias="schema")
    mode: Literal["pacote", "projeto"] = "projeto"
    header: DraftHeader
    include_performance: bool = False
    formats: list[Literal["xlsx", "pdf"]] = Field(default=["xlsx"], min_length=1, max_length=2)
    packages: list[DraftPackage] = Field(min_length=1, max_length=200)
    issues: list[DraftIssue] = Field(default_factory=list, max_length=2000)
    memory_applied: bool = False

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def dump(self) -> dict:
        return self.model_dump(by_alias=True)


class SaveDraftRequest(_Strict):
    draft: Draft
    draft_version: int = Field(ge=1)


class NumbersRequest(_Strict):
    # id do pacote do rascunho → número digitado
    numbers: dict[str, str] = Field(max_length=200)
    draft_version: int = Field(ge=1)


class ApproveRequest(_Strict):
    # formato GeneratePayload — validado em `service.approve` DEPOIS de checar
    # número vazio, pra devolver "falta o número de X" em vez de um 422
    payload: dict = Field(default_factory=dict)
    draft_version: int = Field(ge=1)


class RunRequest(_Strict):
    # vazio = todos os projetos com horas que ainda não têm rascunho
    project_ids: list[str] = Field(default_factory=list, max_length=500)


class CommentRequest(_Strict):
    comment: str = Field(default="", max_length=2000)


class ReviewerRequest(_Strict):
    # vazio/None = tirar o revisor; o login é conferido contra a lista do
    # Projectile no backend (o nome gravado nunca vem do cliente)
    login: str | None = Field(default=None, max_length=100)


_Email = Field(min_length=3, max_length=254)


class SendRequest(_Strict):
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=5000)
    # quais dos formatos APROVADOS vão anexados (vazio/ausente = todos)
    formats: list[Literal["xlsx", "pdf"]] | None = Field(default=None, max_length=2)


class CombinedSendRequest(SendRequest):
    # vários relatórios aprovados num e-mail só
    report_ids: list[str] = Field(min_length=1, max_length=100)


class PlannedNumberRequest(_Strict):
    # vazio/None = tirar o número reservado
    number: str | None = Field(default=None, max_length=100)


_Short = Annotated[str, Field(min_length=1, max_length=500)]


class CustomBlock(_Strict):
    """Um recorte da geração personalizada. Os filtros de um bloco se
    cruzam; blocos diferentes se somam (`auto_generation/custom.py`)."""

    clients: list[_Short] = Field(default_factory=list, max_length=50)
    project_ids: list[_Short] = Field(default_factory=list, max_length=300)
    packages: list[_Short] = Field(default_factory=list, max_length=300)
    employee_ids: list[_Short] = Field(default_factory=list, max_length=100)


class CustomPeriod(_Strict):
    start: str = Field(max_length=7)  # AAAA-MM
    end: str = Field(max_length=7)


class CustomConfig(_Strict):
    """A configuração PRÓPRIA de uma geração personalizada — os mesmos campos da
    configuração de um projeto (assinantes, empresas, arquivos). Vazio = herda
    a do projeto (família) e, sem ela, o padrão geral. O "Relatório" (um por
    projeto ou por pacote de trabalho) é o `package_unit` do pedido."""

    signer1_name: str | None = Field(default=None, max_length=200)
    signer1_company: str | None = Field(default=None, max_length=200)
    signer2_name: str | None = Field(default=None, max_length=200)
    signer2_company: str | None = Field(default=None, max_length=200)
    formats: list[Literal["xlsx", "pdf"]] | None = Field(default=None, min_length=1, max_length=2)


class CustomConfigRequest(_Strict):
    package_unit: Literal["projeto", "pacote"]
    config: CustomConfig | None = None


class CustomRequest(_Strict):
    period: CustomPeriod
    blocks: list[CustomBlock] = Field(min_length=1, max_length=20)
    # quantos relatórios saem (um com tudo, ou um por projeto/pacote/colaborador)
    split_by: Literal["nenhum", "projeto", "pacote", "colaborador"] = "nenhum"
    # o que vira "pacote" dentro de cada relatório
    package_unit: Literal["projeto", "pacote"] = "projeto"
    title: str | None = Field(default=None, max_length=200)
    reviewer_login: str | None = Field(default=None, max_length=100)
    config: CustomConfig | None = None


class FamilyRequest(_Strict):
    family_key: str | None = Field(default=None, max_length=255)
