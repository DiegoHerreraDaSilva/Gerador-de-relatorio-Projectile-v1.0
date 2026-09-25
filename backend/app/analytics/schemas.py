"""Request do `POST /analytics/chat`. O contexto da conversa vem do
navegador (o servidor não guarda sessão de chat), então é validado como
qualquer entrada: formato fixo, tamanhos limitados, e ainda revalidado
contra o catálogo e as opções antes de ser usado (`crossquery.build_spec`)."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

_Name = Annotated[str, Field(max_length=255)]
_Key = Annotated[str, Field(max_length=40)]
_Month = Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]
_Cell = Annotated[str, Field(max_length=1000)] | Annotated[float, Field(allow_inf_nan=False)] | int | None


class ChatFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: _Month | None = None
    month_end: _Month | None = None
    relative: str | None = Field(default=None, max_length=30)
    client: _Name | None = None
    employee: _Name | None = None
    project: _Name | None = None


class ChatSpec(BaseModel):
    """Consulta cruzada anterior (`QuerySpec.as_context()`), pra follow-up
    de cruzamento ("e em julho?"). Só formato aqui; o conteúdo é revalidado
    por `crossquery.build_spec` como se viesse do planner."""
    model_config = ConfigDict(extra="forbid")
    measures: list[_Key] = Field(default_factory=list, max_length=4)
    group_by: list[_Key] = Field(default_factory=list, max_length=2)
    clients: list[_Name] = Field(default_factory=list, max_length=20)
    projects: list[_Name] = Field(default_factory=list, max_length=20)
    project_match: list[_Name] = Field(default_factory=list, max_length=5)
    employees: list[_Name] = Field(default_factory=list, max_length=20)
    packages: list[_Name] = Field(default_factory=list, max_length=20)
    cost_centers: list[_Key] = Field(default_factory=list, max_length=2)
    statuses: list[_Key] = Field(default_factory=list, max_length=4)
    billing_type: _Key | None = None
    month: _Month | None = None
    month_end: _Month | None = None
    relative_period: _Key | None = None
    top_n: int | None = Field(default=None, ge=1, le=100)
    sort_by: _Key | None = None
    sort_order: _Key | None = None
    threshold_measure: _Key | None = None
    threshold_op: _Key | None = None
    threshold_value: float | None = Field(default=None, allow_inf_nan=False)


class ChatContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    last_intent: str | None = Field(default=None, max_length=50)
    last_filters: ChatFilters | None = None
    last_spec: ChatSpec | None = None


class AnalyticsChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
    context: ChatContext | None = None


class ExportRequest(BaseModel):
    """`POST /analytics/chat/export` — a tabela JÁ exibida vira .xlsx. Não
    consulta nada: o servidor só formata o que o navegador já tem."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    columns: list[Annotated[str, Field(max_length=200)]] = Field(min_length=1, max_length=60)
    column_types: list[_Key] | None = Field(default=None, max_length=60)
    rows: list[Annotated[list[Annotated[_Cell, Field(union_mode="left_to_right")]], Field(max_length=60)]] = Field(
        max_length=5000,
    )
    totals: list[_Cell] | None = Field(default=None, max_length=60)
