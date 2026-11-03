"""What the order use cases need from the outside world."""

from __future__ import annotations

from typing import Protocol

from emporio.orders.domain.models import Customer, Order


class OrderReader(Protocol):
    async def get(self, order_id: int) -> Order | None: ...


class CustomerReader(Protocol):
    async def get(self, customer_id: int) -> Customer | None: ...
