from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.catalog.application.ports import ProductFilter
from emporio.catalog.domain.models import Availability
from emporio.catalog.infrastructure.repositories import (
    SqlCategoryReader,
    SqlProductReader,
    SqlPromotionReader,
)
from emporio.infrastructure.orm import IngestionRunRow, OrderItemRow, ProductRow
from emporio.ingestion.pipeline import ingest_structured
from emporio.orders.domain.models import OrderStatus
from emporio.orders.infrastructure.repositories import SqlCustomerReader, SqlOrderReader

from .conftest import DATA_DIR


async def test_ingestion_is_idempotent(sessions: async_sessionmaker[AsyncSession]) -> None:
    reloaded = await ingest_structured(sessions, DATA_DIR)

    assert reloaded is False
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProductRow)) == 65
        assert await session.scalar(select(func.count()).select_from(OrderItemRow)) == 22
        assert await session.scalar(select(func.count()).select_from(IngestionRunRow)) >= 1


async def test_fuzzy_name_lookup_finds_takamine_gd20(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    results = await SqlProductReader(sessions).find_by_name("takamine gd 20")

    assert results[0].product.id == 95


async def test_filters_respect_price_stock_and_category(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    results = await SqlProductReader(sessions).search(
        None, ProductFilter(category_ids=(5,), max_price=Decimal(1000)), limit=50
    )

    assert results
    assert all(r.product.price.amount <= 1000 and r.product.category_id == 5 for r in results)
    assert all(r.product.availability is Availability.IN_STOCK for r in results)
    assert 96 not in {r.product.id for r in results}  # active but zero stock


async def test_spec_filters(sessions: async_sessionmaker[AsyncSession]) -> None:
    results = await SqlProductReader(sessions).search(
        None, ProductFilter(category_ids=(5,), strings="nylon", electric=True), limit=50
    )

    assert results and all(
        r.product.specs["strings"] == "nylon" and r.product.specs["electronics"] == "yes"
        for r in results
    )


async def test_promotions_and_categories(sessions: async_sessionmaker[AsyncSession]) -> None:
    promotions = await SqlPromotionReader(sessions).for_products([90, 96])
    categories = await SqlCategoryReader(sessions).all()

    assert {(p.product_id, p.is_active) for p in promotions} >= {(90, True), (96, False)}
    assert "violão" in next(c for c in categories if c.id == 5).synonyms


async def test_order_and_customer_mapping(sessions: async_sessionmaker[AsyncSession]) -> None:
    order = await SqlOrderReader(sessions).get(15)
    assert order is not None
    customer = await SqlCustomerReader(sessions).get(order.customer_id)

    assert order.status is OrderStatus.PENDING
    assert order.payment.installments == 12
    assert {i.product_id for i in order.items} == {82, 106}
    assert customer is not None and customer.matches(email="aline.monteiro@jmail.com")
