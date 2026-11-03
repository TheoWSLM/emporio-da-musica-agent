"""Conversation history and support tickets (handoff to the human team)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    payload: dict[str, Any] = field(default_factory=dict)
    """Assistant turns keep tool calls, classification and citations for audit and grounding."""
    created_at: datetime | None = None


class TicketType(StrEnum):
    COMPLAINT = "complaint"
    EXCHANGE = "exchange"
    HUMAN = "human"

    @property
    def label(self) -> str:
        return {
            TicketType.COMPLAINT: "reclamação",
            TicketType.EXCHANGE: "troca/devolução",
            TicketType.HUMAN: "atendimento humano",
        }[self]


RESPONSE_SLA = "24 horas úteis"


@dataclass(frozen=True)
class SupportTicket:
    protocol: str
    type: TicketType
    summary: str
    contact: str | None
    conversation_id: uuid.UUID | None
