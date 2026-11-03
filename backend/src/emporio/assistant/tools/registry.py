"""Tool registry: name, model-facing description, argument model and handler."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from emporio.assistant.tools import handlers
from emporio.assistant.tools.context import ToolContext
from emporio.assistant.tools.schemas import (
    Args,
    ErrorView,
    GetProductArgs,
    OpenTicketArgs,
    OrderLookupArgs,
    PaymentOptionsArgs,
    ReturnEligibilityArgs,
    SearchPoliciesArgs,
    SearchProductsArgs,
    ShippingArgs,
    StoreStatusArgs,
    View,
)

log = logging.getLogger(__name__)

Handler = Callable[[Any, ToolContext], Awaitable[View]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[Args]
    handler: Handler


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    arguments: dict[str, Any]
    output: str
    """JSON of the view, exactly what the model reads."""
    ok: bool
    duration_ms: int


TOOLS: tuple[Tool, ...] = (
    Tool(
        "search_products",
        "Search the instrument catalog with filters (category, price range, string type, electro-acoustic). "
        "Returns prices already computed (list, promotional, PIX), availability and alternatives.",
        SearchProductsArgs,
        handlers.search_products,
    ),
    Tool(
        "get_product",
        "Look up one product by id or approximate name: price, active and expired promotions, stock, "
        "status, and similar alternatives when it is unavailable or discontinued.",
        GetProductArgs,
        handlers.get_product,
    ),
    Tool(
        "calculate_payment_options",
        "Payment conditions for a product or amount: PIX price, every allowed interest-free installment plan, "
        "whether a requested number of installments is possible and why, and combined payment eligibility.",
        PaymentOptionsArgs,
        handlers.calculate_payment_options,
    ),
    Tool(
        "get_order_status",
        "Status, items, tracking and delivery estimate of an order. Requires the order number AND the "
        "customer's e-mail or phone (identity check).",
        OrderLookupArgs,
        handlers.get_order_status,
    ),
    Tool(
        "check_return_eligibility",
        "Applies the return/exchange policy to a specific order (regret, defect or preference) using today's "
        "date: eligibility, deadline, conditions and next steps. Requires order number AND e-mail or phone.",
        ReturnEligibilityArgs,
        handlers.check_return_eligibility,
    ),
    Tool(
        "estimate_shipping",
        "Shipping rule for a destination city and order value: fee or quote rule, carriers and delivery times.",
        ShippingArgs,
        handlers.estimate_shipping,
    ),
    Tool(
        "get_store_status",
        "Whether the store is open right now, next opening time, opening hours, address and contacts.",
        StoreStatusArgs,
        handlers.get_store_status,
    ),
    Tool(
        "search_policies",
        "Search the store's policy manual (exchanges, returns, warranty, payment, shipping, promotions, "
        "privacy, service guidelines). Returns the relevant sections to cite.",
        SearchPoliciesArgs,
        handlers.search_policies,
    ),
    Tool(
        "open_support_ticket",
        "Register a complaint, an exchange/return request for the team, or a request to talk to a human. "
        "Returns the protocol number and response time.",
        OpenTicketArgs,
        handlers.open_support_ticket,
    ),
)
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


async def execute(name: str, raw_arguments: str, call_id: str, ctx: ToolContext) -> ToolResult:
    """Runs one tool call. Never raises: problems come back to the model as structured errors."""
    started = time.perf_counter()
    arguments: dict[str, Any] = {}
    tool = TOOLS_BY_NAME.get(name)
    try:
        arguments = json.loads(raw_arguments or "{}")
        if tool is None:
            view: View = ErrorView(error=f"unknown tool {name}")
        else:
            view = await tool.handler(tool.args.model_validate(arguments), ctx)
    except ValidationError as exc:
        view = ErrorView(error=f"invalid arguments: {exc.errors(include_url=False)}")
    except json.JSONDecodeError:
        view = ErrorView(error="arguments are not valid JSON")
    except (
        Exception
    ):  # infrastructure failure: report it to the model instead of failing the whole turn
        log.exception("tool %s failed", name)
        view = ErrorView(
            error="temporary failure while consulting the system; do not guess the data"
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    return ToolResult(
        call_id=call_id,
        name=name,
        arguments=arguments,
        output=view.model_dump_json(exclude_none=True),
        ok=not isinstance(view, ErrorView),
        duration_ms=elapsed,
    )
