"""Idempotent ingestion. Each stage records the hash of its inputs and is skipped when nothing changed."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.infrastructure.orm import (
    CategoryRow,
    CustomerRow,
    IngestionRunRow,
    OrderItemRow,
    OrderRow,
    ProductRow,
    PromotionRow,
)
from emporio.ingestion.enrichment import CATEGORY_SYNONYMS, product_search_text
from emporio.ingestion.loader import CSV_FILES, RawDataset, load_raw_dataset

log = logging.getLogger(__name__)

STRUCTURED_STAGE = "structured"
ENRICHMENT_VERSION = "1"


def files_hash(paths: Iterable[Path], *extra: str) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for value in extra:
        digest.update(value.encode())
    return digest.hexdigest()


async def last_hash(session: AsyncSession, stage: str) -> str | None:
    result = await session.execute(
        select(IngestionRunRow.content_hash)
        .where(IngestionRunRow.stage == stage)
        .order_by(IngestionRunRow.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def ingest_structured(
    sessions: async_sessionmaker[AsyncSession], data_dir: Path, *, force: bool = False
) -> bool:
    """Loads the CSVs into the relational tables. Returns True when data was (re)loaded."""
    content_hash = files_hash((data_dir / name for name in CSV_FILES), ENRICHMENT_VERSION)
    async with sessions() as session, session.begin():
        if not force and await last_hash(session, STRUCTURED_STAGE) == content_hash:
            log.info("structured data unchanged, skipping")
            return False
        dataset = load_raw_dataset(data_dir)
        await _replace_all(session, dataset)
        session.add(
            IngestionRunRow(
                stage=STRUCTURED_STAGE,
                content_hash=content_hash,
                details={"products": len(dataset.products), "rejected_rows": len(dataset.errors)},
            )
        )
    log.info("structured data loaded (%d products)", len(dataset.products))
    return True


async def _replace_all(session: AsyncSession, data: RawDataset) -> None:
    for table in (OrderItemRow, OrderRow, PromotionRow, CustomerRow, ProductRow, CategoryRow):
        await session.execute(delete(table))

    categories = {c.category_id: c for c in data.categories}
    session.add_all(
        CategoryRow(
            id=c.category_id,
            name=c.name,
            description=c.description,
            synonyms=list(CATEGORY_SYNONYMS.get(c.category_id, ())),
        )
        for c in data.categories
    )
    await session.flush()

    products = [p for p in data.products if p.category_id in categories]
    session.add_all(
        ProductRow(
            id=p.product_id,
            category_id=p.category_id,
            name=p.name,
            description=p.description,
            price=p.price_brl,
            stock_quantity=p.stock_quantity,
            status=p.status,
            specs=dict(p.specs),
            created_at=p.created_at,
            search_text=product_search_text(
                p.name, categories[p.category_id].name, p.description, p.specs
            ),
        )
        for p in products
    )
    await session.flush()
    product_ids = {p.product_id for p in products}

    session.add_all(
        PromotionRow(
            id=p.promotion_id,
            product_id=p.product_id,
            discount_percent=p.discount_percent,
            description=p.description,
            is_active=p.is_active,
        )
        for p in data.promotions
        if p.product_id in product_ids
    )
    session.add_all(
        CustomerRow(id=c.customer_id, name=c.name, phone=c.phone, email=c.email, city=c.city)
        for c in data.customers
    )
    await session.flush()
    customer_ids = {c.customer_id for c in data.customers}

    orders = [o for o in data.orders if o.customer_id in customer_ids]
    session.add_all(
        OrderRow(
            id=o.order_id,
            customer_id=o.customer_id,
            order_date=o.order_date,
            status=o.status,
            total=o.total_brl,
            payment_method=o.payment_method,
            tracking_code=o.tracking_code,
            estimated_delivery=o.estimated_delivery,
            notes=o.notes,
        )
        for o in orders
    )
    await session.flush()
    order_ids = {o.order_id for o in orders}
    session.add_all(
        OrderItemRow(order_id=i.order_id, product_id=i.product_id, quantity=i.quantity)
        for i in data.order_items
        if i.order_id in order_ids and i.product_id in product_ids
    )
