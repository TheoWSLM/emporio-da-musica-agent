import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from emporio.api.app import Runtime, create_app
from emporio.api.rate_limit import DailyBudget, SlidingWindowLimiter
from emporio.config import Settings
from tests.graph.fakes import MemoryConversations
from tests.support import sse_events

REPLY = {
    "message": "Olá! Como posso ajudar?",
    "cited_sections": [],
    "needs_human": False,
    "suggested_replies": [],
}


class FakeAssistant:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def stream(
        self, conversation_id: uuid.UUID, message: str
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "status", "text": "Consultando…"}
        if self.fail:
            raise RuntimeError("boom")
        yield {"type": "message", "reply": REPLY, "outcome": "answered"}
        yield {"type": "not-a-real-event"}  # invalid events are dropped, not sent
        yield {"type": "done", "outcome": "answered", "latency_ms": 12, "model_rounds": 1}


def client_for(
    per_ip: int = 20, daily: int = 100, max_turns: int = 40, fail: bool = False
) -> Iterator[TestClient]:
    def factory(settings: Settings) -> Runtime:
        settings = settings.model_copy(update={"max_turns_per_conversation": max_turns})
        return Runtime(
            settings=settings,
            assistant=FakeAssistant(fail),
            conversations=MemoryConversations(),
            ip_limiter=SlidingWindowLimiter(per_ip, 600),
            daily_budget=DailyBudget(daily),
            close=lambda: _noop(),
        )

    with TestClient(create_app(factory)) as client:
        yield client


async def _noop() -> None:
    return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from client_for()


def start(client: TestClient) -> str:
    response = client.post("/conversations")
    assert response.status_code == 201
    return str(response.json()["conversation_id"])


def test_message_is_answered_as_typed_sse_events(client: TestClient) -> None:
    cid = start(client)

    response = client.post(f"/conversations/{cid}/messages", json={"content": "oi"})

    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)
    assert [e["type"] for e in events] == ["status", "message", "done"]
    assert events[1]["reply"]["message"] == REPLY["message"]


def test_message_validation(client: TestClient) -> None:
    cid = start(client)

    assert client.post(f"/conversations/{cid}/messages", json={"content": "   "}).status_code == 422
    assert (
        client.post(f"/conversations/{cid}/messages", json={"content": "x" * 2001}).status_code
        == 422
    )
    assert (
        client.post(
            f"/conversations/{cid}/messages", json={"content": "oi", "role": "system"}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/conversations/{uuid.uuid4()}/messages", json={"content": "oi"}).status_code
        == 404
    )


def test_rate_limit_per_ip() -> None:
    for client in client_for(per_ip=2):
        cid = start(client)
        codes = [
            client.post(f"/conversations/{cid}/messages", json={"content": "oi"}).status_code
            for _ in range(3)
        ]
        assert codes == [200, 200, 429]


def test_daily_budget_and_turn_limit() -> None:
    for client in client_for(daily=1):
        cid = start(client)
        assert (
            client.post(f"/conversations/{cid}/messages", json={"content": "oi"}).status_code == 200
        )
        assert (
            client.post(f"/conversations/{cid}/messages", json={"content": "oi"}).status_code == 429
        )


def test_failures_become_an_error_event() -> None:
    for client in client_for(fail=True):
        cid = start(client)
        events = sse_events(
            client.post(f"/conversations/{cid}/messages", json={"content": "oi"}).text
        )
        assert events[-1]["type"] == "error"


def test_config_and_openapi(client: TestClient) -> None:
    assert client.get("/config").json()["agent_model"]
    schema = client.get("/openapi.json").json()
    assert "/conversations/{conversation_id}/messages" in schema["paths"]
