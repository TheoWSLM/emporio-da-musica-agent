"""OpenAI Responses API adapter for the ChatModel port (strict tools + Structured Outputs in one call)."""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from typing import Any

from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema  # the only use of this SDK helper
from pydantic import BaseModel

from emporio.assistant.llm import ModelTurn, ToolCall
from emporio.assistant.tools.registry import Tool
from emporio.conversation.domain.models import Message


@cache
def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema accepted by OpenAI strict mode (every field required, no extra properties)."""
    return to_strict_json_schema(model)


def _tool_definition(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": strict_json_schema(tool.args),
        "strict": True,
    }


class OpenAIChatModel:
    def __init__(
        self, client: AsyncOpenAI, *, model: str, reasoning_effort: str, max_output_tokens: int
    ) -> None:
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens

    async def respond(
        self,
        *,
        instructions: str,
        history: Sequence[Message],
        context: str,
        user_message: str,
        transcript: Sequence[dict[str, Any]],
        tools: Sequence[Tool],
        reply_schema: type[BaseModel],
        allow_tools: bool,
    ) -> ModelTurn:
        # Static instructions + tool schemas come first (prompt cache); dynamic context goes last.
        items: list[dict[str, Any]] = [
            {"role": m.role.value, "content": m.content} for m in history
        ]
        items += [
            {"role": "developer", "content": context},
            {"role": "user", "content": user_message},
            *transcript,
        ]
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": instructions,
            "input": items,
            "tools": [_tool_definition(tool) for tool in tools],
            "tool_choice": "auto" if allow_tools else "none",
            "parallel_tool_calls": True,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": reply_schema.__name__,
                    "schema": strict_json_schema(reply_schema),
                    "strict": True,
                }
            },
            "reasoning": {"effort": self._reasoning_effort},
            "max_output_tokens": self._max_output_tokens,
            "prompt_cache_key": "emporio-agent",
            "store": False,
            # Nothing is stored server-side, so encrypted reasoning items must travel with tool calls.
            "include": ["reasoning.encrypted_content"],
        }
        response = await self._client.responses.create(**request)
        produced = [item.model_dump(exclude_none=True) for item in response.output]
        calls = [
            ToolCall(item["call_id"], item["name"], item.get("arguments") or "{}")
            for item in produced
            if item.get("type") == "function_call"
        ]
        usage = (
            {"input": response.usage.input_tokens, "output": response.usage.output_tokens}
            if response.usage
            else {}
        )
        return ModelTurn(produced, calls, "" if calls else response.output_text, usage)

    def tool_result(self, call: ToolCall, output: str) -> dict[str, Any]:
        return {"type": "function_call_output", "call_id": call.call_id, "output": output}

    def feedback(self, text: str) -> dict[str, Any]:
        return {"role": "developer", "content": text}
