"""Request do `POST /analytics/chat`. O contexto da conversa vem do
navegador (o servidor não guarda sessão de chat), então é validado como
qualquer entrada: formato fixo, tamanhos limitados, e ainda revalidado
contra o catálogo e as opções antes de ser usado."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    month_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    relative: str | None = Field(default=None, max_length=30)
    client: str | None = Field(default=None, max_length=255)
    employee: str | None = Field(default=None, max_length=255)


class ChatContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    last_intent: str | None = Field(default=None, max_length=50)
    last_filters: ChatFilters | None = None


class AnalyticsChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
    context: ChatContext | None = None
