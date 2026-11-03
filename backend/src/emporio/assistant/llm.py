"""The chat-model port used by the agent node. The graph never sees a provider SDK or message format:
it keeps the turn's transcript as opaque items produced and consumed by the adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from emporio.conversation.domain.models import Message


class ToolSpec(Protocol):
    """What a model needs to know about a tool (the registry's Tool satisfies it)."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def args(self) -> type[BaseModel]: ...


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str
    """JSON text, exactly as produced by the model."""


@dataclass(frozen=True)
class ModelTurn:
    transcript: list[dict[str, Any]]
    """Items to append to the turn's transcript (opaque, provider-specific)."""
    tool_calls: list[ToolCall]
    text: str
    """Final structured answer as JSON text (empty when the model asked for tools)."""
    usage: dict[str, int] = field(default_factory=dict)


class ChatModel(Protocol):
    async def respond(
        self,
        *,
        instructions: str,
        history: Sequence[Message],
        context: str,
        user_message: str,
        transcript: Sequence[dict[str, Any]],
        tools: Sequence[ToolSpec],
        reply_schema: type[BaseModel],
        allow_tools: bool,
    ) -> ModelTurn: ...

    def tool_result(self, call: ToolCall, output: str) -> dict[str, Any]:
        """Transcript item carrying a tool result back to the model."""
        ...

    def feedback(self, text: str) -> dict[str, Any]:
        """Transcript item with a system-side note (e.g. why the previous draft was rejected)."""
        ...
