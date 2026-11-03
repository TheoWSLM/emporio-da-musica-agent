"""HTTP and SSE contracts (Pydantic v2). The frontend's TypeScript types mirror these."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from emporio.assistant.reply import CustomerReply

MAX_MESSAGE_CHARS = 2000
"""Maximum customer message length (the edge also caps the request body)."""


class CreateConversationResponse(BaseModel):
    conversation_id: uuid.UUID


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]


class MessageView(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime | None
    details: dict[str, Any] = Field(default_factory=dict)


class ConversationView(BaseModel):
    conversation_id: uuid.UUID
    messages: list[MessageView]


class PublicConfig(BaseModel):
    agent_model: str
    classifier_provider: Literal["openai", "jev"]
    classifier_model: str
    embedding_model: str
    reference_date: str | None
    release: str


class ErrorBody(BaseModel):
    detail: str


# ----------------------------------------------------------------------- SSE events


class ClassificationEvent(BaseModel):
    type: Literal["classification"]
    provider: str
    latency_ms: int
    assessment: dict[str, Any]
    route: str
    reason: str
    heuristic_flags: list[str]


class StatusEvent(BaseModel):
    type: Literal["status"]
    text: str


class ToolEvent(BaseModel):
    type: Literal["tool"]
    name: str
    arguments: dict[str, Any]
    ok: bool
    duration_ms: int
    output: dict[str, Any]


class MessageEvent(BaseModel):
    type: Literal["message"]
    reply: CustomerReply
    outcome: Literal["answered", "blocked", "off_topic", "fallback"]


class DoneEvent(BaseModel):
    type: Literal["done"]
    outcome: str | None
    latency_ms: int
    model_rounds: int


class ErrorEvent(BaseModel):
    type: Literal["error"]
    detail: str


SseEvent = Annotated[
    ClassificationEvent | StatusEvent | ToolEvent | MessageEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]
