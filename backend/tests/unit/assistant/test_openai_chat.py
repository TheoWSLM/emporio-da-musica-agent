"""The OpenAI adapter of the ChatModel port: request shape and response mapping (no network)."""

from dataclasses import dataclass, field
from typing import Any

from emporio.assistant.llm import ToolCall
from emporio.assistant.openai_chat import OpenAIChatModel
from emporio.assistant.reply import CustomerReply
from emporio.assistant.tools.registry import TOOLS
from emporio.conversation.domain.models import Message, Role


@dataclass
class _Item:
    data: dict[str, Any]

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        return dict(self.data)


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 20


@dataclass
class _Response:
    output: list[_Item]
    output_text: str = ""
    usage: _Usage = field(default_factory=_Usage)


class _Responses:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.request: dict[str, Any] = {}

    async def create(self, **request: Any) -> _Response:
        self.request = request
        return self.response


class _Client:
    def __init__(self, response: _Response) -> None:
        self.responses = _Responses(response)


def adapter(response: _Response) -> tuple[OpenAIChatModel, _Client]:
    client = _Client(response)
    model = OpenAIChatModel(client, model="m", reasoning_effort="none", max_output_tokens=500)  # type: ignore[arg-type]
    return model, client


async def respond(model: OpenAIChatModel, allow_tools: bool = True) -> Any:
    return await model.respond(
        instructions="SYSTEM",
        history=[Message(Role.USER, "oi"), Message(Role.ASSISTANT, "Olá!")],
        context="CONTEXT",
        user_message="quanto custa?",
        transcript=[{"type": "function_call_output", "call_id": "x", "output": "{}"}],
        tools=TOOLS,
        reply_schema=CustomerReply,
        allow_tools=allow_tools,
    )


async def test_request_order_strict_schemas_and_tool_choice() -> None:
    model, client = adapter(_Response([], output_text="{}"))

    await respond(model, allow_tools=False)

    request = client.responses.request
    assert request["instructions"] == "SYSTEM"
    assert [i.get("role") for i in request["input"]] == [
        "user",
        "assistant",
        "developer",
        "user",
        None,
    ]
    assert all(t["strict"] for t in request["tools"]) and len(request["tools"]) == len(TOOLS)
    assert (
        request["text"]["format"]["name"] == "CustomerReply" and request["text"]["format"]["strict"]
    )
    assert request["tool_choice"] == "none" and request["store"] is False


async def test_tool_calls_are_mapped_and_reasoning_items_kept() -> None:
    items = [
        _Item({"type": "reasoning", "encrypted_content": "..."}),
        _Item(
            {
                "type": "function_call",
                "call_id": "c1",
                "name": "get_product",
                "arguments": '{"product_ref":"x"}',
            }
        ),
    ]
    model, _ = adapter(_Response(items))

    turn = await respond(model)

    assert turn.tool_calls == [ToolCall("c1", "get_product", '{"product_ref":"x"}')]
    assert [i["type"] for i in turn.transcript] == ["reasoning", "function_call"]
    assert turn.text == "" and turn.usage == {"input": 100, "output": 20}


async def test_final_answer_and_transcript_items() -> None:
    model, _ = adapter(_Response([_Item({"type": "message"})], output_text='{"message":"oi"}'))

    turn = await respond(model)

    assert turn.text == '{"message":"oi"}' and turn.tool_calls == []
    assert model.tool_result(ToolCall("c1", "n", "{}"), "OUT") == {
        "type": "function_call_output",
        "call_id": "c1",
        "output": "OUT",
    }
    assert model.feedback("x") == {"role": "developer", "content": "x"}
