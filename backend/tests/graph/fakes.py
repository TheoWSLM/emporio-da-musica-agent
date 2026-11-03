"""In-memory fakes for graph tests: scripted model, classifiers, stores."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from emporio.assistant.classification.assessment import InputAssessment, OutputAssessment
from emporio.assistant.classification.ports import Classified
from emporio.assistant.llm import ModelTurn, ToolCall
from emporio.assistant.tools.context import Services
from emporio.conversation.domain.models import Message, SupportTicket, TicketType
from emporio.knowledge.domain.models import PolicyHit
from emporio.store.application.use_cases import StoreService
from tests.support import FixedClock

CLOCK = FixedClock(datetime(2026, 11, 4, 10, 0, tzinfo=ZoneInfo("America/Campo_Grande")))


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "c1") -> ToolCall:
    return ToolCall(call_id, name, json.dumps(arguments))


def final(message: str) -> ModelTurn:
    reply = {
        "message": message,
        "cited_sections": [],
        "needs_human": False,
        "suggested_replies": [],
    }
    text = json.dumps(reply, ensure_ascii=False)
    return ModelTurn([{"role": "assistant", "content": text}], [], text, {"input": 10, "output": 5})


def calls(*tool_calls: ToolCall) -> ModelTurn:
    return ModelTurn([{"call": c.call_id} for c in tool_calls], list(tool_calls), "")


class ScriptedChatModel:
    """Implements the ChatModel port with a fixed script and records every request."""

    def __init__(self, script: Sequence[ModelTurn]) -> None:
        self._script = list(script)
        self.requests: list[dict[str, Any]] = []

    async def respond(self, **request: Any) -> ModelTurn:
        self.requests.append({**request, "transcript": list(request["transcript"])})
        return self._script.pop(0)

    def tool_result(self, call: ToolCall, output: str) -> dict[str, Any]:
        return {"tool_result": call.call_id, "output": output}

    def feedback(self, text: str) -> dict[str, Any]:
        return {"feedback": text}


def assessment(**overrides: Any) -> InputAssessment:
    base = {
        "threat": "safe",
        "threat_confidence": "high",
        "scope": "store_related",
        "scope_confidence": "high",
        "intent": "other",
        "frustration": "calm",
        "wants_human": False,
    }
    return InputAssessment.model_validate(base | overrides)


class FakeInputClassifier:
    def __init__(self, value: InputAssessment, delay: float = 0.0) -> None:
        self.value = value
        self.delay = delay

    async def assess(self, message: str, previous_reply: str | None) -> Classified[InputAssessment]:
        await asyncio.sleep(self.delay)
        return Classified(self.value, "fake", int(self.delay * 1000))


class FakeOutputClassifier:
    def __init__(self, **flags: bool) -> None:
        self.value = OutputAssessment.model_validate(
            {"promises_unsupported_offer": False, "off_persona": False, "leaks_instructions": False}
            | flags
        )

    async def review(self, message: str, reply: str, facts: str) -> Classified[OutputAssessment]:
        return Classified(self.value, "fake", 0)


class FakeRetriever:
    def __init__(self, hits: list[PolicyHit] | None = None, delay: float = 0.0) -> None:
        self.hits = hits or []
        self.delay = delay

    async def search(
        self, query: str, k: int = 4, embedding: Sequence[float] | None = None
    ) -> list[PolicyHit]:
        await asyncio.sleep(self.delay)
        return self.hits[:k]


class MemoryConversations:
    def __init__(self) -> None:
        self.messages: dict[uuid.UUID, list[Message]] = {}

    async def create(self, channel: str) -> uuid.UUID:
        conversation_id = uuid.uuid4()
        self.messages[conversation_id] = []
        return conversation_id

    async def exists(self, conversation_id: uuid.UUID) -> bool:
        return conversation_id in self.messages

    async def history(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        return self.messages.get(conversation_id, [])[-limit:]

    async def append(self, conversation_id: uuid.UUID, messages: list[Message]) -> None:
        self.messages.setdefault(conversation_id, []).extend(messages)

    async def count_user_messages(self, conversation_id: uuid.UUID) -> int:
        return sum(1 for m in self.messages.get(conversation_id, []) if m.role.value == "user")


class MemoryTickets:
    async def open(
        self, type: TicketType, summary: str, contact: str | None, conversation_id: uuid.UUID | None
    ) -> SupportTicket:
        return SupportTicket("EM-TEST-0001", type, summary, contact, conversation_id)


def services(retriever: FakeRetriever | None = None) -> Services:
    unused: Any = None  # catalog/orders are not exercised by the graph tests
    return Services(
        catalog=unused,
        orders=unused,
        store=StoreService(CLOCK),
        policies=retriever or FakeRetriever(),
        tickets=MemoryTickets(),
        clock=CLOCK,
    )
