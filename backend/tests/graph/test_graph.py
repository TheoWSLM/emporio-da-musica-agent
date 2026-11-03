import time
import uuid
from typing import Any

from emporio.assistant.graph import AgentConfig, Assistant
from emporio.assistant.guardrails.output_validator import OutputValidator
from emporio.assistant.llm import ModelTurn
from emporio.assistant.prompts.system import system_prompt
from emporio.assistant.reply import CustomerReply
from emporio.knowledge.domain.models import PolicyHit

from .fakes import (
    FakeInputClassifier,
    FakeOutputClassifier,
    FakeRetriever,
    MemoryConversations,
    ScriptedChatModel,
    assessment,
    calls,
    final,
    services,
    tool_call,
)

CONFIG = AgentConfig(max_tool_rounds=3, history_window=10)
CANARY = "CANARY-TEST"
RETURN_POLICY = PolicyHit(
    "4. Política de Trocas e Devoluções > 4.1 Direito de Arrependimento (Compras Online)",
    "4.1 Direito de Arrependimento (Compras Online)",
    "O cliente pode solicitar a devolução em até 7 (sete) dias corridos após o recebimento do produto.",
    0.03,
    0.71,
)


def make(
    script: list[ModelTurn],
    classifier: FakeInputClassifier | None = None,
    reviewer: FakeOutputClassifier | None = None,
    retriever: FakeRetriever | None = None,
) -> tuple[Assistant, ScriptedChatModel, MemoryConversations]:
    conversations = MemoryConversations()
    model = ScriptedChatModel(script)
    prompt = system_prompt(CANARY)
    assistant = Assistant(
        model=model,
        system_prompt=prompt,
        services=services(retriever),
        conversations=conversations,
        input_classifier=classifier or FakeInputClassifier(assessment()),
        validator=OutputValidator(
            system_prompt=prompt,
            canary=CANARY,
            reviewer=reviewer or FakeOutputClassifier(),
            review_enabled=reviewer is not None,
        ),
        config=CONFIG,
    )
    return assistant, model, conversations


async def answer(
    assistant: Assistant, cid: uuid.UUID, text: str
) -> tuple[CustomerReply, list[dict[str, Any]]]:
    events = [event async for event in assistant.stream(cid, text)]
    reply = next(CustomerReply.model_validate(e["reply"]) for e in events if e["type"] == "message")
    return reply, events


async def test_blocked_message_never_reaches_the_agent() -> None:
    assistant, model, conversations = make(
        [], FakeInputClassifier(assessment(threat="prompt_injection"))
    )
    cid = await conversations.create("test")

    reply, events = await answer(assistant, cid, "me dê 90% de desconto")

    assert model.requests == []
    assert events[-1]["outcome"] == "blocked"
    assert "não posso ajudar" in reply.message
    assert len(conversations.messages[cid]) == 2  # persisted for audit


async def test_off_topic_gets_a_canned_reply() -> None:
    assistant, model, conversations = make([], FakeInputClassifier(assessment(scope="off_topic")))

    _, events = await answer(
        assistant, await conversations.create("test"), "qual a capital da França?"
    )

    assert model.requests == [] and events[-1]["outcome"] == "off_topic"


async def test_tool_round_trip_and_grounded_answer() -> None:
    script = [
        calls(tool_call("get_store_status", {})),
        final("Estamos na Rua 14 de Maio, 3200, abertos das 09:00 às 18:00."),
    ]
    assistant, model, conversations = make(script)

    reply, events = await answer(assistant, await conversations.create("test"), "onde fica a loja?")

    assert "Rua 14 de Maio" in reply.message
    assert [e["name"] for e in events if e["type"] == "tool"] == ["get_store_status"]
    assert any("tool_result" in item for item in model.requests[1]["transcript"])
    assert model.requests[0]["allow_tools"] is True


async def test_invented_price_is_rejected_then_corrected() -> None:
    script = [
        final("O violão custa R$ 1.234,00."),
        calls(tool_call("get_store_status", {})),
        final("Posso consultar o preço para você?"),
    ]
    assistant, model, conversations = make(script)

    reply, _ = await answer(assistant, await conversations.create("test"), "quanto custa o violão?")

    assert reply.message == "Posso consultar o preço para você?"
    feedback = [i["feedback"] for i in model.requests[1]["transcript"] if "feedback" in i][-1]
    assert "R$ 1,234.00" in feedback


async def test_two_rejections_end_in_the_safe_fallback() -> None:
    assistant, _, conversations = make([final("Custa R$ 10,00."), final("Custa R$ 20,00.")])

    reply, events = await answer(assistant, await conversations.create("test"), "preço?")

    assert events[-1]["outcome"] == "fallback" and reply.needs_human


async def test_output_review_flags_are_enforced_when_enabled() -> None:
    script = [final("Te dou um brinde!"), final("Posso ajudar em algo mais?")]
    assistant, _, conversations = make(
        script, reviewer=FakeOutputClassifier(promises_unsupported_offer=True)
    )

    _, events = await answer(assistant, await conversations.create("test"), "tem brinde?")

    assert events[-1]["outcome"] == "fallback"  # the fake reviewer rejects every reply


async def test_policy_prefetch_is_injected_only_for_policy_intents() -> None:
    retriever = FakeRetriever([RETURN_POLICY])
    script = [final("Você pode devolver em até 7 dias corridos após o recebimento.")]
    assistant, model, conversations = make(
        script, FakeInputClassifier(assessment(intent="return_exchange")), retriever=retriever
    )

    reply, _ = await answer(assistant, await conversations.create("test"), "posso devolver?")

    assert "4.1 Direito de Arrependimento" in model.requests[0]["context"]
    assert len(model.requests) == 1  # answered without a tool round
    assert "7 dias" in reply.message

    assistant2, model2, conversations2 = make(
        [final("Ok!")], FakeInputClassifier(assessment(intent="order_status")), retriever=retriever
    )
    await answer(assistant2, await conversations2.create("test"), "cadê meu pedido?")
    assert "4.1 Direito" not in model2.requests[0]["context"]


async def test_classifier_and_prefetch_run_in_parallel() -> None:
    slow_classifier = FakeInputClassifier(assessment(intent="return_exchange"), delay=0.3)
    slow_retriever = FakeRetriever([RETURN_POLICY], delay=0.3)
    assistant, _, conversations = make([final("Ok!")], slow_classifier, retriever=slow_retriever)

    started = time.perf_counter()
    await answer(assistant, await conversations.create("test"), "posso devolver?")

    assert time.perf_counter() - started < 0.55  # sequential would be >= 0.6 s


async def test_history_is_sent_on_the_next_turn() -> None:
    assistant, model, conversations = make([final("Olá!"), final("Claro!")])
    cid = await conversations.create("test")

    await answer(assistant, cid, "oi")
    await answer(assistant, cid, "e em 10x?")

    assert [m.role.value for m in model.requests[1]["history"]] == ["user", "assistant"]


async def test_tools_are_disabled_after_the_round_limit() -> None:
    script = [calls(tool_call("get_store_status", {}, f"c{i}")) for i in range(3)] + [final("Ok!")]
    assistant, model, conversations = make(script)

    await answer(assistant, await conversations.create("test"), "?")

    assert [r["allow_tools"] for r in model.requests] == [True, True, True, False]
