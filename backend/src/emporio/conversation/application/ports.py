"""Persistence ports for conversations and tickets."""

from __future__ import annotations

import uuid
from typing import Protocol

from emporio.conversation.domain.models import Message, SupportTicket, TicketType


class ConversationStore(Protocol):
    async def create(self, channel: str) -> uuid.UUID: ...

    async def exists(self, conversation_id: uuid.UUID) -> bool: ...

    async def history(self, conversation_id: uuid.UUID, limit: int) -> list[Message]: ...

    async def append(self, conversation_id: uuid.UUID, messages: list[Message]) -> None: ...

    async def count_user_messages(self, conversation_id: uuid.UUID) -> int: ...


class TicketStore(Protocol):
    async def open(
        self, type: TicketType, summary: str, contact: str | None, conversation_id: uuid.UUID | None
    ) -> SupportTicket: ...
