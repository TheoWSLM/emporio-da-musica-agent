"""SQL implementations of the order ports."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.infrastructure.orm import CustomerRow, OrderRow
from emporio.orders.domain.models import Customer, Order, OrderItem, OrderStatus, PaymentMethod
from emporio.shared.money import Money


def to_order(row: OrderRow) -> Order:
    return Order(
        id=row.id,
        customer_id=row.customer_id,
        order_date=row.order_date,
        status=OrderStatus(row.status),
        total=Money.of(row.total),
        payment=PaymentMethod.parse(row.payment_method),
        items=tuple(OrderItem(i.product_id, i.quantity) for i in row.items),
        tracking_code=row.tracking_code,
        estimated_delivery=row.estimated_delivery,
        notes=row.notes,
    )


class SqlOrderReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, order_id: int) -> Order | None:
        async with self._sessions() as session:
            row = await session.get(OrderRow, order_id)
            return to_order(row) if row else None


class SqlCustomerReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, customer_id: int) -> Customer | None:
        async with self._sessions() as session:
            row = await session.get(CustomerRow, customer_id)
            if row is None:
                return None
            return Customer(row.id, row.name, row.phone, row.email, row.city)
