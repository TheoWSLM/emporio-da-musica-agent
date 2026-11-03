"""Order use cases. Every disclosure of order data requires an identity check (LGPD, manual §9)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from emporio.catalog.application.ports import ProductReader
from emporio.orders.application.ports import CustomerReader, OrderReader
from emporio.orders.domain.models import Customer, Order
from emporio.orders.domain.returns import ReturnDecision, ReturnReason, evaluate_return
from emporio.shared.clock import Clock


class Verification(StrEnum):
    VERIFIED = "verified"
    MISSING_IDENTITY = "missing_identity"
    FAILED = "failed"
    """Order not found *or* identity mismatch — deliberately indistinguishable, so the assistant cannot
    be used to discover which order numbers exist."""


@dataclass(frozen=True)
class OrderLine:
    product_id: int
    product_name: str
    quantity: int


@dataclass(frozen=True)
class OrderLookup:
    verification: Verification
    order: Order | None = None
    customer: Customer | None = None
    lines: tuple[OrderLine, ...] = ()


@dataclass(frozen=True)
class ReturnCheck:
    lookup: OrderLookup
    decision: ReturnDecision | None = None


class OrderService:
    def __init__(
        self, orders: OrderReader, customers: CustomerReader, products: ProductReader, clock: Clock
    ) -> None:
        self._orders = orders
        self._customers = customers
        self._products = products
        self._clock = clock

    async def lookup(self, order_id: int, *, email: str | None, phone: str | None) -> OrderLookup:
        if not (email or phone):
            return OrderLookup(Verification.MISSING_IDENTITY)
        order = await self._orders.get(order_id)
        customer = await self._customers.get(order.customer_id) if order else None
        if order is None or customer is None or not customer.matches(email=email, phone=phone):
            return OrderLookup(Verification.FAILED)
        products = {
            p.id: p for p in await self._products.get_many([i.product_id for i in order.items])
        }
        lines = tuple(
            OrderLine(
                i.product_id,
                products[i.product_id].name if i.product_id in products else "?",
                i.quantity,
            )
            for i in order.items
        )
        return OrderLookup(Verification.VERIFIED, order, customer, lines)

    async def check_return(
        self, order_id: int, reason: ReturnReason, *, email: str | None, phone: str | None
    ) -> ReturnCheck:
        lookup = await self.lookup(order_id, email=email, phone=phone)
        if lookup.order is None:
            return ReturnCheck(lookup)
        return ReturnCheck(lookup, evaluate_return(lookup.order, reason, self._clock.today()))
