"""LangGraph state (TypedDict + reducers). Pydantic objects travel inside it."""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict

from emporio.assistant.classification.assessment import InputAssessment
from emporio.assistant.classification.decision import Decision
from emporio.assistant.classification.ports import Classified
from emporio.assistant.guardrails.heuristics import HeuristicResult
from emporio.assistant.llm import ToolCall
from emporio.assistant.reply import CustomerReply
from emporio.assistant.tools.context import ToolContext
from emporio.assistant.tools.registry import ToolResult
from emporio.conversation.domain.models import Message
from emporio.knowledge.domain.models import PolicyHit


class TurnState(TypedDict, total=False):
    conversation_id: uuid.UUID
    user_message: str
    history: list[Message]
    previous_reply: str | None

    heuristics: HeuristicResult
    classification: Classified[InputAssessment]
    decision: Decision
    prefetched: list[PolicyHit]

    tool_context: ToolContext
    items: Annotated[list[dict[str, Any]], operator.add]
    """Responses-API input items produced during this turn (model outputs, tool outputs, feedback)."""
    pending_calls: list[ToolCall]
    tool_results: Annotated[list[ToolResult], operator.add]
    model_rounds: int
    usage: Annotated[list[dict[str, int]], operator.add]

    reply: CustomerReply | None
    attempts: int
    validation_problems: list[str]
    rejections: Annotated[list[str], operator.add]
    """Every problem found across attempts (audit: shows what the validators actually catch)."""
    outcome: str
    """answered | blocked | off_topic | fallback"""
    final: CustomerReply
