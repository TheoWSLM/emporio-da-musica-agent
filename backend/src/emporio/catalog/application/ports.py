"""What the catalog use cases need from the outside world."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from emporio.catalog.domain.models import Category, Product, Promotion


@dataclass(frozen=True)
class ProductFilter:
    category_ids: tuple[int, ...] = ()
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock_only: bool = True
    strings: str | None = None
    """'nylon' | 'steel'"""
    electric: bool | None = None
    exclude_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ScoredProduct:
    product: Product
    score: float


class ProductReader(Protocol):
    async def get(self, product_id: int) -> Product | None: ...

    async def get_many(self, product_ids: Sequence[int]) -> list[Product]: ...

    async def find_by_name(self, text: str, limit: int = 5) -> list[ScoredProduct]: ...

    async def search(
        self, query_embedding: Sequence[float] | None, filters: ProductFilter, limit: int
    ) -> list[ScoredProduct]: ...


class PromotionReader(Protocol):
    async def for_products(self, product_ids: Sequence[int]) -> list[Promotion]: ...


class CategoryReader(Protocol):
    async def all(self) -> list[Category]: ...
