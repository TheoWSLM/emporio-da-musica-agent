"""The per-turn LangGraph.

    START → load_history ─┬─ classify_input  (heuristics + InputClassifier) ─┐
                          └─ policy_prefetch (embedding + hybrid search)    ─┴→ route
    route ─ blocked/off_topic → canned_reply → persist
          └ proceed → agent ⇄ tools (parallel tool calls) → validate_output
    validate_output ─ ok → persist ; fail once → agent (with the reasons) ; fail twice → safe_fallback → persist

The model never computes business facts: tools do. The final answer is a CustomerReply produced with
Structured Outputs in the same call that may request tools.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from emporio.assistant.classification.decision import Route, decide
from emporio.assistant.classification.ports import InputClassifier
from emporio.assistant.context import STATIC_FACTS, turn_context
from emporio.assistant.guardrails.heuristics import inspect, normalize
from emporio.assistant.guardrails.output_validator import OutputValidator
from emporio.assistant.llm import ChatModel, ToolCall
from emporio.assistant.prompts import canned
from emporio.assistant.reply import CustomerReply
from emporio.assistant.state import TurnState
from emporio.assistant.tools.context import Services, ToolContext
from emporio.assistant.tools.registry import TOOLS, execute
from emporio.conversation.application.ports import ConversationStore
from emporio.conversation.domain.models import Message, Role
from emporio.knowledge.domain.models import PolicyHit
from emporio.store.domain.info import EMPORIO

log = logging.getLogger(__name__)

PREFETCH_MIN_SIMILARITY = 0.35
MAX_ATTEMPTS = 2
STATUS_BY_TOOL = {
    "search_products": "Consultando o catálogo…",
    "get_product": "Consultando o produto…",
    "calculate_payment_options": "Calculando as condições de pagamento…",
    "get_order_status": "Consultando o pedido…",
    "check_return_eligibility": "Verificando a política de trocas para o pedido…",
    "estimate_shipping": "Verificando o frete…",
    "get_store_status": "Verificando o horário da loja…",
    "search_policies": "Lendo as políticas da loja…",
    "open_support_ticket": "Registrando o atendimento…",
}


@dataclass(frozen=True)
class AgentConfig:
    max_tool_rounds: int
    history_window: int


def _emit(event: dict[str, Any]) -> None:
    with contextlib.suppress(RuntimeError):  # not running under a streaming call
        get_stream_writer()(event)


class Assistant:
    def __init__(
        self,
        *,
        model: ChatModel,
        system_prompt: str,
        services: Services,
        conversations: ConversationStore,
        input_classifier: InputClassifier,
        validator: OutputValidator,
        config: AgentConfig,
    ) -> None:
        self._model = model
        self._system_prompt = system_prompt
        self._services = services
        self._conversations = conversations
        self._input_classifier = input_classifier
        self._validator = validator
        self._config = config
        self.graph = self._build()

    # ------------------------------------------------------------------ graph wiring

    def _build(self) -> Any:
        graph = StateGraph(TurnState)
        graph.add_node("load_history", self.load_history)
        graph.add_node("classify_input", self.classify_input)
        graph.add_node("policy_prefetch", self.policy_prefetch)
        graph.add_node("route", self.route)
        graph.add_node("canned_reply", self.canned_reply)
        graph.add_node("agent", self.agent)
        graph.add_node("tools", self.tools)
        graph.add_node("validate_output", self.validate_output)
        graph.add_node("safe_fallback", self.safe_fallback)
        graph.add_node("persist", self.persist)

        graph.add_edge(START, "load_history")
        graph.add_edge("load_history", "classify_input")
        graph.add_edge("load_history", "policy_prefetch")
        graph.add_edge(["classify_input", "policy_prefetch"], "route")
        graph.add_conditional_edges(
            "route", self._after_route, {"canned": "canned_reply", "agent": "agent"}
        )
        graph.add_conditional_edges(
            "agent",
            self._after_agent,
            {"tools": "tools", "validate": "validate_output", "fallback": "safe_fallback"},
        )
        graph.add_edge("tools", "agent")
        graph.add_conditional_edges(
            "validate_output",
            self._after_validation,
            {"ok": "persist", "retry": "agent", "fallback": "safe_fallback"},
        )
        graph.add_edge("canned_reply", "persist")
        graph.add_edge("safe_fallback", "persist")
        graph.add_edge("persist", END)
        return graph.compile()

    # ------------------------------------------------------------------ nodes

    async def load_history(self, state: TurnState) -> dict[str, Any]:
        history = await self._conversations.history(
            state["conversation_id"], self._config.history_window
        )
        previous = next((m.content for m in reversed(history) if m.role is Role.ASSISTANT), None)
        return {
            "history": history,
            "previous_reply": previous,
            "tool_context": ToolContext(
                services=self._services, conversation_id=state["conversation_id"]
            ),
            "attempts": 0,
            "model_rounds": 0,
        }

    async def classify_input(self, state: TurnState) -> dict[str, Any]:
        heuristics = inspect(state["user_message"])
        classified = await self._input_classifier.assess(
            normalize(state["user_message"]), state.get("previous_reply")
        )
        decision = decide(classified.value, heuristics)
        _emit(
            {
                "type": "classification",
                "provider": classified.provider,
                "latency_ms": classified.latency_ms,
                "assessment": classified.value.model_dump(),
                "route": decision.route.value,
                "reason": decision.reason,
                "heuristic_flags": heuristics.flags,
            }
        )
        return {"classification": classified, "decision": decision}

    async def policy_prefetch(self, state: TurnState) -> dict[str, Any]:
        """Runs in parallel with the classifier; whether the hits are used is decided after the join."""
        try:
            hits = await self._services.policies.search(state["user_message"], k=3)
        except (
            Exception
        ) as exc:  # retrieval is an optimisation here, never a reason to fail the turn
            log.warning("policy prefetch failed: %s", exc)
            hits = []
        return {"prefetched": hits}

    async def route(self, state: TurnState) -> dict[str, Any]:
        return {}

    def _after_route(self, state: TurnState) -> Literal["canned", "agent"]:
        return "agent" if state["decision"].route is Route.PROCEED else "canned"

    async def canned_reply(self, state: TurnState) -> dict[str, Any]:
        blocked = state["decision"].route is Route.BLOCK
        reply = CustomerReply(
            message=canned.BLOCKED if blocked else canned.OFF_TOPIC,
            cited_sections=[],
            needs_human=False,
            suggested_replies=canned.SUGGESTIONS,
        )
        _emit(
            {
                "type": "message",
                "reply": reply.model_dump(),
                "outcome": "blocked" if blocked else "off_topic",
            }
        )
        return {"final": reply, "outcome": "blocked" if blocked else "off_topic"}

    def _injected_policies(self, state: TurnState) -> list[PolicyHit]:
        if not state["decision"].prefetch_policies:
            return []
        return [h for h in state.get("prefetched", []) if h.similarity >= PREFETCH_MIN_SIMILARITY]

    async def agent(self, state: TurnState) -> dict[str, Any]:
        rounds = state.get("model_rounds", 0) + 1
        context = turn_context(
            now=self._services.clock.now(),
            store=self._services.store.status(),
            assessment=state["classification"].value,
            heightened_caution=state["decision"].heightened_caution,
            policies=self._injected_policies(state),
        )
        turn = await self._model.respond(
            instructions=self._system_prompt,
            history=state.get("history", []),
            context=context,
            user_message=state["user_message"],
            transcript=state.get("items", []),
            tools=TOOLS,
            reply_schema=CustomerReply,
            allow_tools=rounds <= self._config.max_tool_rounds,
        )
        update: dict[str, Any] = {
            "model_rounds": rounds,
            "items": turn.transcript,
            "pending_calls": turn.tool_calls,
            "usage": [turn.usage],
        }
        if turn.tool_calls:
            return update
        try:
            update["reply"] = CustomerReply.model_validate_json(turn.text)
        except ValidationError:
            log.warning("agent returned an invalid structured reply")
            update["reply"] = None
        return update

    def _after_agent(self, state: TurnState) -> Literal["tools", "validate", "fallback"]:
        if state.get("pending_calls"):
            return "tools"
        return "validate" if state.get("reply") is not None else "fallback"

    async def tools(self, state: TurnState) -> dict[str, Any]:
        calls: list[ToolCall] = state["pending_calls"]
        ctx = state["tool_context"]
        for call in calls:
            _emit({"type": "status", "text": STATUS_BY_TOOL.get(call.name, "Consultando…")})
        results = await asyncio.gather(
            *(execute(call.name, call.arguments, call.call_id, ctx) for call in calls)
        )
        for result in results:
            _emit(
                {
                    "type": "tool",
                    "name": result.name,
                    "arguments": result.arguments,
                    "ok": result.ok,
                    "duration_ms": result.duration_ms,
                    "output": json.loads(result.output),
                }
            )
        outputs = [
            self._model.tool_result(call, r.output) for call, r in zip(calls, results, strict=True)
        ]
        return {"items": outputs, "tool_results": list(results), "pending_calls": []}

    def _verified_sources(self, state: TurnState) -> list[str]:
        sources = [r.output for r in state.get("tool_results", [])]
        sources += [f"{h.section_path} {h.content}" for h in self._injected_policies(state)]
        sources += [m.content for m in state.get("history", [])]
        sources.append(STATIC_FACTS)
        return sources

    async def validate_output(self, state: TurnState) -> dict[str, Any]:
        reply = state["reply"]
        assert reply is not None
        ctx = state["tool_context"]
        problems = await self._validator.problems(
            reply=reply.message,
            customer_message=state["user_message"],
            sources=self._verified_sources(state),
            allowed_contacts=[
                *ctx.verified_contacts,
                EMPORIO.phone,
                EMPORIO.whatsapp,
                EMPORIO.email,
            ],
        )
        attempts = state.get("attempts", 0) + 1
        update: dict[str, Any] = {
            "attempts": attempts,
            "rejections": problems,
        }
        if not problems:
            final = reply.model_copy(
                update={"cited_sections": sorted(set(reply.cited_sections) | ctx.cited_sections)}
            )
            _emit({"type": "message", "reply": final.model_dump(), "outcome": "answered"})
            update |= {"final": final, "outcome": "answered"}
        elif attempts < MAX_ATTEMPTS:
            _emit({"type": "status", "text": "Revisando a resposta…"})
            log.info("reply rejected: %s", problems)
            update["items"] = [
                self._model.feedback(
                    "Sua resposta anterior foi rejeitada pela verificação automática: "
                    + "; ".join(problems)
                    + ". Reescreva usando apenas valores que vieram das ferramentas (consulte-as se preciso) "
                    "e sem dados pessoais não verificados."
                )
            ]
            update["reply"] = None
        return update

    def _after_validation(self, state: TurnState) -> Literal["ok", "retry", "fallback"]:
        if state.get("outcome") == "answered":
            return "ok"
        return "retry" if state.get("attempts", 0) < MAX_ATTEMPTS else "fallback"

    async def safe_fallback(self, state: TurnState) -> dict[str, Any]:
        reply = CustomerReply(
            message=canned.FALLBACK,
            cited_sections=[],
            needs_human=True,
            suggested_replies=["Sim, pode registrar"],
        )
        _emit({"type": "message", "reply": reply.model_dump(), "outcome": "fallback"})
        return {"final": reply, "outcome": "fallback"}

    async def persist(self, state: TurnState) -> dict[str, Any]:
        classification = state["classification"]
        payload = {
            "outcome": state["outcome"],
            "classification": {
                "provider": classification.provider,
                "latency_ms": classification.latency_ms,
                **classification.value.model_dump(),
            },
            "route": state["decision"].route.value,
            "tools": [
                {"name": r.name, "arguments": r.arguments, "ok": r.ok, "duration_ms": r.duration_ms}
                for r in state.get("tool_results", [])
            ],
            "cited_sections": state["final"].cited_sections,
            "rejections": state.get("rejections", []),
            "usage": state.get("usage", []),
        }
        await self._conversations.append(
            state["conversation_id"],
            [
                Message(Role.USER, state["user_message"]),
                Message(Role.ASSISTANT, state["final"].message, payload),
            ],
        )
        return {}

    # ------------------------------------------------------------------ entry points

    async def stream(
        self, conversation_id: uuid.UUID, message: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Yields UI events (classification, status, tool, message) and finally a `done` event."""
        started = time.perf_counter()
        state: TurnState = {"conversation_id": conversation_id, "user_message": message}
        final_state: dict[str, Any] = {}
        async for mode, chunk in self.graph.astream(state, stream_mode=["custom", "values"]):
            if mode == "custom":
                yield chunk
            else:
                final_state = chunk
        yield {
            "type": "done",
            "outcome": final_state.get("outcome"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model_rounds": final_state.get("model_rounds", 0),
        }
