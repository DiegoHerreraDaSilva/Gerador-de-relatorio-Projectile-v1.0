"""Rotas de chat de IA e tradução (`/chat`, `/translate-activities`) —
extraído de `main.py` na Fase 5."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...chat_ops import OperationError, apply_operations
from ...chatbot import ChatConfigError, ChatUpstreamError, call_chat, call_translate
from ..dependencies import require_session, require_translate_access

router = APIRouter()


class ChatActivity(BaseModel):
    # id estável (do frontend, `Activity.id`) — chat_ops.py localiza o alvo
    # das operações por id, nunca por descrição (ver chat_ops.py, Fase 8 do
    # GUIA_EVOLUCAO_GERADOR_PROJECTILE.md).
    id: str
    description: str
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ChatGroup(BaseModel):
    id: str
    name: str
    performance: float = Field(ge=0, allow_inf_nan=False)
    activities: list[ChatActivity]


class ChatPackage(BaseModel):
    key: str
    projectCode: str
    projectName: str
    groups: list[ChatGroup]


class ChatState(BaseModel):
    packages: list[ChatPackage] = Field(min_length=1)
    activePackageIndex: int
    locationDate: str
    monthLabel: str
    signer1Name: str = ""
    signer1Company: str = ""
    signer2Name: str = ""
    signer2Company: str = ""


class ChatHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatRequest(BaseModel):
    message: str
    state: ChatState
    history: list[ChatHistoryTurn] = []


class ChatResponse(BaseModel):
    reply: str
    state: ChatState


@router.post("/chat")
async def chat_endpoint(payload: ChatRequest, _user: dict = Depends(require_session)):
    try:
        summary, operations = call_chat(
            payload.message,
            payload.state.model_dump(),
            [turn.model_dump() for turn in payload.history],
        )
    except ChatConfigError as e:
        raise HTTPException(500, str(e))
    except ChatUpstreamError as e:
        raise HTTPException(502, str(e))

    try:
        new_state = apply_operations(payload.state.model_dump(), operations)
    except OperationError as e:
        # a IA pediu uma operação que não bate com o estado real (pacote/grupo/
        # atividade inexistente, campo inválido) — nunca aplica parte das operações
        raise HTTPException(502, f"A IA pediu uma alteração inválida: {e} Tente reformular o pedido.")

    try:
        validated_state = ChatState.model_validate(new_state)
    except Exception:
        raise HTTPException(502, "A IA retornou dados inválidos (ex: horas negativas). Tente reformular o pedido.")

    return ChatResponse(reply=summary, state=validated_state)


class TranslateItem(BaseModel):
    id: str
    text: str


class TranslatePayload(BaseModel):
    # nomes de grupo e descrições de atividade misturados numa lista só —
    # ver comentário em translate_ops.py sobre por que `id` nunca é ambíguo.
    items: list[TranslateItem] = Field(min_length=1)
    target_language: Literal["en", "de"] = "en"


@router.post("/translate-activities")
async def translate_activities_endpoint(payload: TranslatePayload, _user: dict = Depends(require_translate_access)):
    try:
        translations = call_translate([item.model_dump() for item in payload.items], payload.target_language)
    except ChatConfigError as e:
        raise HTTPException(500, str(e))
    except ChatUpstreamError as e:
        raise HTTPException(502, str(e))
    # não valida que a lista bate 1:1 com o pedido — o frontend aplica só os
    # ids que vierem, e mantém o texto original pra qualquer id que a IA não
    # tenha devolvido (mais seguro que rejeitar a resposta inteira por causa
    # de um item faltando).
    return {"translations": [item for item in translations if isinstance(item, dict) and "id" in item]}
