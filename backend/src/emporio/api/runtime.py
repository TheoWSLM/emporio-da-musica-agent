"""What the HTTP layer needs at runtime (built once at startup by the app factory)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from emporio.api.rate_limit import DailyBudget, SlidingWindowLimiter
from emporio.config import Settings
from emporio.conversation.application.ports import ConversationStore


class ChatAssistant(Protocol):
    def stream(self, conversation_id: uuid.UUID, message: str) -> AsyncIterator[dict[str, Any]]: ...


@dataclass
class Runtime:
    settings: Settings
    assistant: ChatAssistant
    conversations: ConversationStore
    ip_limiter: SlidingWindowLimiter
    daily_budget: DailyBudget
    close: Callable[[], Awaitable[None]]
