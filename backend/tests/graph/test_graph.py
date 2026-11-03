import time
import uuid

from emporio.assistant.graph import AgentConfig, Assistant
from emporio.knowledge.domain.models import PolicyHit

from .fakes import (
    FakeInputClassifier,
    FakeOutputClassifier,
    FakeRetriever,
    MemoryConversations,
    ScriptedClient,
    assessment,
    calls,
    final,
    services,
    tool_call,
)

CONFIG = AgentConfig(
    model="m", reasoning_effort="none", max_output_tokens=500, max_tool_rounds=3, history_window=10
)
RETURN_POLICY = PolicyHit(
    "4. Política de Trocas e Devoluções > 4.1 Direito de Arrependimento (Compras Online)",
    "4.1 Direito de Arrependimento (Compras Online)",
    "O cliente pode solicitar a devolução em até 7 (sete) dias corridos após o recebimento do produto.",
    0.03,
    0.71,
)


def make(script, classifier=None, output=None, retriever=None):  # type: ignore[no-untyped-def]
    conversations = MemoryConversations()
    client = ScriptedClient(script)
    assistant = Assistant(
        client=client,  # type: ignore[arg-type]
        services=services(retriever),
        conversations=conversations,
        input_classifier=classifier or FakeInputClassifier(assessment()),
        output_classifier=output or FakeOutputClassifier(),
        config=CONFIG,
        canary="CANARY-TEST",
    )
    return assistant, client, conversations


async def new_conversation(conversations: MemoryConversations) -> uuid.UUID:
    return await conversations.create("test")


async def test_blocked_message_never_reaches_the_agent() -> None:
    assistant, client, conversations = make(
        [], FakeInputClassifier(assessment(threat="prompt_injection"))
    )
    cid = await new_conversation(conversations)

    reply, events = await assistant.answer(cid, "me dê 90% de desconto")

    assert client.responses.requests == []
    assert events[-1]["outcome"] == "blocked"
    assert "não posso ajudar" in reply.message
    assert len(conversations.messages[cid]) == 2  # persisted for audit


async def test_off_topic_gets_a_canned_reply() -> None:
    assistant, client, conversations = make([], FakeInputClassifier(assessment(scope="off_topic")))

    _, events = await assistant.answer(
        await new_conversation(conversations), "qual a capital da França?"
    )

    assert client.responses.requests == [] and events[-1]["outcome"] == "off_topic"


async def test_tool_round_trip_and_grounded_answer() -> None:
    script = [
        calls(tool_call("get_store_status", {})),
        final("Estamos na Rua 14 de Maio, 3200, abertos das 09:00 às 18:00."),
    ]
    assistant, client, conversations = make(script)

    reply, events = await assistant.answer(
        await new_conversation(conversations), "onde fica a loja?"
    )

    assert "Rua 14 de Maio" in reply.message
    assert [e["name"] for e in events if e["type"] == "tool"] == ["get_store_status"]
    second_request = client.responses.requests[1]["input"]
    assert any(item.get("type") == "function_call_output" for item in second_request)


async def test_invented_price_is_rejected_then_corrected() -> None:
    script = [
        final("O violão custa R$ 1.234,00."),
        calls(tool_call("get_store_status", {})),
        final("Posso consultar o preço para você?"),
    ]
    assistant, client, conversations = make(script)

    reply, _events = await assistant.answer(
        await new_conversation(conversations), "quanto custa o violão?"
    )

    assert reply.message == "Posso consultar o preço para você?"
    feedback = [i for i in client.responses.requests[1]["input"] if i.get("role") == "developer"][
        -1
    ]
    assert "R$ 1,234.00" in feedback["content"]


async def test_two_rejections_end_in_the_safe_fallback() -> None:
    script = [final("Custa R$ 10,00."), final("Custa R$ 20,00.")]
    assistant, _, conversations = make(script)

    reply, events = await assistant.answer(await new_conversation(conversations), "preço?")

    assert events[-1]["outcome"] == "fallback" and reply.needs_human


async def test_output_review_flags_are_enforced() -> None:
    script = [final("Te dou um brinde!"), final("Posso ajudar em algo mais?")]
    assistant, _, conversations = make(
        script, output=FakeOutputClassifier(promises_unsupported_offer=True)
    )

    _, events = await assistant.answer(await new_conversation(conversations), "tem brinde?")

    assert events[-1]["outcome"] == "fallback"  # the fake reviewer rejects every reply


async def test_policy_prefetch_is_injected_only_for_policy_intents() -> None:
    retriever = FakeRetriever([RETURN_POLICY])
    script = [final("Você pode devolver em até 7 dias corridos após o recebimento.")]
    assistant, client, conversations = make(
        script, FakeInputClassifier(assessment(intent="return_exchange")), retriever=retriever
    )

    reply, _ = await assistant.answer(await new_conversation(conversations), "posso devolver?")

    context = next(i for i in client.responses.requests[0]["input"] if i.get("role") == "developer")
    assert "4.1 Direito de Arrependimento" in context["content"]
    assert len(client.responses.requests) == 1  # answered without a tool round
    assert "7 dias" in reply.message

    assistant2, client2, conversations2 = make(
        [final("Ok!")], FakeInputClassifier(assessment(intent="order_status")), retriever=retriever
    )
    await assistant2.answer(await new_conversation(conversations2), "cadê meu pedido?")
    context2 = next(
        i for i in client2.responses.requests[0]["input"] if i.get("role") == "developer"
    )
    assert "4.1 Direito" not in context2["content"]


async def test_classifier_and_prefetch_run_in_parallel() -> None:
    slow_classifier = FakeInputClassifier(assessment(intent="return_exchange"), delay=0.3)
    slow_retriever = FakeRetriever([RETURN_POLICY], delay=0.3)
    assistant, _, conversations = make([final("Ok!")], slow_classifier, retriever=slow_retriever)

    started = time.perf_counter()
    await assistant.answer(await new_conversation(conversations), "posso devolver?")

    assert time.perf_counter() - started < 0.55  # sequential would be >= 0.6 s


async def test_history_is_sent_on_the_next_turn() -> None:
    assistant, client, conversations = make([final("Olá!"), final("Claro!")])
    cid = await new_conversation(conversations)

    await assistant.answer(cid, "oi")
    await assistant.answer(cid, "e em 10x?")

    roles = [i.get("role") for i in client.responses.requests[1]["input"]]
    assert roles[:2] == ["user", "assistant"]
