"""SQL implementations of the catalog ports (Postgres + pgvector + pg_trgm)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.catalog.application.ports import ProductFilter, ScoredProduct
from emporio.catalog.domain.models import Category, Product, ProductStatus, Promotion
from emporio.infrastructure.orm import CategoryRow, ProductRow, PromotionRow
from emporio.shared.money import Money

NAME_SIMILARITY_THRESHOLD = 0.2


def to_product(row: ProductRow) -> Product:
    return Product(
        id=row.id,
        name=row.name,
        category_id=row.category_id,
        description=row.description,
        price=Money.of(row.price),
        stock_quantity=row.stock_quantity,
        status=ProductStatus(row.status),
        specs={str(k): str(v) for k, v in row.specs.items()},
        created_at=row.created_at,
    )


def _conditions(filters: ProductFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.category_ids:
        conditions.append(ProductRow.category_id.in_(filters.category_ids))
    if filters.min_price is not None:
        conditions.append(ProductRow.price >= filters.min_price)
    if filters.max_price is not None:
        conditions.append(ProductRow.price <= filters.max_price)
    if filters.in_stock_only:
        conditions += [ProductRow.status == "active", ProductRow.stock_quantity > 0]
    if filters.strings is not None:
        conditions.append(ProductRow.specs["strings"].astext == filters.strings)
    if filters.electric is not None:
        conditions.append(
            ProductRow.specs["electronics"].astext == ("yes" if filters.electric else "no")
        )
    if filters.exclude_ids:
        conditions.append(ProductRow.id.not_in(filters.exclude_ids))
    return conditions


class SqlProductReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, product_id: int) -> Product | None:
        async with self._sessions() as session:
            row = await session.get(ProductRow, product_id)
            return to_product(row) if row else None

    async def get_many(self, product_ids: Sequence[int]) -> list[Product]:
        if not product_ids:
            return []
        async with self._sessions() as session:
            rows = await session.scalars(select(ProductRow).where(ProductRow.id.in_(product_ids)))
            by_id = {row.id: to_product(row) for row in rows}
        return [by_id[pid] for pid in product_ids if pid in by_id]

    async def find_by_name(self, text: str, limit: int = 5) -> list[ScoredProduct]:
        """Fuzzy name match with pg_trgm (handles 'takamine gd 20', typos, partial names)."""
        score = func.greatest(
            func.similarity(ProductRow.name, text), func.word_similarity(text, ProductRow.name)
        ).label("score")
        statement = (
            select(ProductRow, score)
            .where(score >= NAME_SIMILARITY_THRESHOLD)
            .order_by(score.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [ScoredProduct(to_product(row), float(s)) for row, s in rows]

    async def search(
        self, query_embedding: Sequence[float] | None, filters: ProductFilter, limit: int
    ) -> list[ScoredProduct]:
        """Semantic ranking (cosine) inside SQL filters; without an embedding, cheapest first."""
        conditions = _conditions(filters)
        if query_embedding is not None:
            distance = ProductRow.embedding.cosine_distance(list(query_embedding))
            statement = (
                select(ProductRow, (1 - distance).label("score"))
                .where(*conditions, ProductRow.embedding.is_not(None))
                .order_by(distance)
            )
        else:
            statement = (
                select(ProductRow, literal(1.0).label("score"))
                .where(*conditions)
                .order_by(ProductRow.price)
            )
        async with self._sessions() as session:
            rows = (await session.execute(statement.limit(limit))).all()
        return [ScoredProduct(to_product(row), float(s)) for row, s in rows]


class SqlPromotionReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def for_products(self, product_ids: Sequence[int]) -> list[Promotion]:
        if not product_ids:
            return []
        async with self._sessions() as session:
            rows = await session.scalars(
                select(PromotionRow).where(PromotionRow.product_id.in_(product_ids))
            )
            return [
                Promotion(
                    r.id, r.product_id, Decimal(r.discount_percent), r.description, r.is_active
                )
                for r in rows
            ]


class SqlCategoryReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def all(self) -> list[Category]:
        async with self._sessions() as session:
            rows = await session.scalars(select(CategoryRow).order_by(CategoryRow.id))
            return [Category(r.id, r.name, r.description, tuple(r.synonyms)) for r in rows]
