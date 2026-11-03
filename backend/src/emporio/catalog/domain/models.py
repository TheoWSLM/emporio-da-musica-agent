"""Catalog entities and value objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from emporio.shared.money import Money


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"

    @property
    def label(self) -> str:
        return {
            ProductStatus.ACTIVE: "à venda",
            ProductStatus.DISCONTINUED: "descontinuado",
            ProductStatus.COMING_SOON: "em breve (ainda não disponível para venda)",
        }[self]


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"

    @property
    def label(self) -> str:
        return {
            Availability.IN_STOCK: "disponível",
            Availability.OUT_OF_STOCK: "temporariamente sem estoque",
            Availability.DISCONTINUED: "descontinuado (fora do catálogo)",
            Availability.COMING_SOON: "em breve",
        }[self]


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    description: str
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    discount_percent: Decimal
    description: str
    is_active: bool


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    description: str
    price: Money
    stock_quantity: int
    status: ProductStatus
    specs: Mapping[str, str] = field(default_factory=dict)
    created_at: date | None = None

    @property
    def availability(self) -> Availability:
        if self.status is ProductStatus.DISCONTINUED:
            return Availability.DISCONTINUED
        if self.status is ProductStatus.COMING_SOON:
            return Availability.COMING_SOON
        return Availability.IN_STOCK if self.stock_quantity > 0 else Availability.OUT_OF_STOCK

    @property
    def is_sellable(self) -> bool:
        return self.availability is Availability.IN_STOCK
