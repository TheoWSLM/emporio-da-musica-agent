"""Conversation endpoints. Messages are answered as a Server-Sent Events stream."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import TypeAdapter, ValidationError
from sse_starlette.sse import EventSourceResponse

from emporio.api.runtime import Runtime
from emporio.api.schemas import (
    ConversationView,
    CreateConversationResponse,
    ErrorBody,
    ErrorEvent,
    MessageView,
    PublicConfig,
    SendMessageRequest,
    SseEvent,
)

log = logging.getLogger(__name__)
router = APIRouter()
EVENT = TypeAdapter[Any](SseEvent)
UI_DETAIL_KEYS = ("outcome", "classification", "route", "tools", "cited_sections")


def _runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


@router.get("/config", response_model=PublicConfig, tags=["meta"])
async def public_config(request: Request) -> PublicConfig:
    settings = _runtime(request).settings
    return PublicConfig(
        agent_model=settings.agent_model,
        classifier_provider="jev" if settings.jev_enabled else "openai",
        classifier_model=settings.jev_model if settings.jev_enabled else settings.classifier_model,
        embedding_model=settings.embedding_model,
        reference_date=settings.app_reference_date.isoformat()
        if settings.app_reference_date
        else None,
        release=settings.release_id,
    )


@router.post(
    "/conversations", response_model=CreateConversationResponse, status_code=201, tags=["chat"]
)
async def create_conversation(request: Request) -> CreateConversationResponse:
    conversation_id = await _runtime(request).conversations.create("web")
    return CreateConversationResponse(conversation_id=conversation_id)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationView,
    responses={404: {"model": ErrorBody}},
    tags=["chat"],
)
async def get_conversation(conversation_id: uuid.UUID, request: Request) -> ConversationView:
    store = _runtime(request).conversations
    if not await store.exists(conversation_id):
        raise HTTPException(404, "conversation not found")
    messages = await store.history(conversation_id, limit=200)
    return ConversationView(
        conversation_id=conversation_id,
        messages=[
            MessageView(
                role=m.role.value,
                content=m.content,
                created_at=m.created_at,
                details={k: m.payload[k] for k in UI_DETAIL_KEYS if k in m.payload},
            )
            for m in messages
        ],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    responses={
        200: {
            "description": "text/event-stream of SseEvent objects",
            "content": {"text/event-stream": {}},
        },
        404: {"model": ErrorBody},
        429: {"model": ErrorBody},
    },
    tags=["chat"],
)
async def send_message(
    conversation_id: uuid.UUID, body: SendMessageRequest, request: Request
) -> EventSourceResponse:
    runtime = _runtime(request)
    if not await runtime.conversations.exists(conversation_id):
        raise HTTPException(404, "conversation not found")
    client_ip = request.client.host if request.client else "unknown"
    if not runtime.ip_limiter.allow(client_ip):
        raise HTTPException(
            429, "Muitas mensagens em pouco tempo. Aguarde alguns minutos e tente de novo."
        )
    if (
        await runtime.conversations.count_user_messages(conversation_id)
        >= runtime.settings.max_turns_per_conversation
    ):
        raise HTTPException(
            429, "Esta conversa atingiu o limite da demonstração. Inicie uma nova conversa."
        )
    if not runtime.daily_budget.allow():
        raise HTTPException(
            429, "A demonstração atingiu o limite diário de mensagens. Tente novamente amanhã."
        )

    async def events() -> AsyncIterator[dict[str, str]]:
        try:
            async for raw in runtime.assistant.stream(conversation_id, body.content):
                try:
                    event = EVENT.validate_python(raw)
                except ValidationError:
                    log.exception("invalid event from the graph: %s", raw.get("type"))
                    continue
                yield {"event": event.type, "data": event.model_dump_json()}
        except Exception:
            log.exception("turn failed")
            error = ErrorEvent(
                type="error",
                detail="Tive um problema para responder agora. Tente novamente em instantes.",
            )
            yield {"event": "error", "data": error.model_dump_json()}

    return EventSourceResponse(events(), ping=15)
