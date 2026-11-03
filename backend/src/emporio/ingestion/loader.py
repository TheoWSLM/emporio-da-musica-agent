"""Reads the raw CSVs and validates every row with Pydantic. Invalid rows are reported, not fatal."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ValidationError

from emporio.ingestion.rows import (
    CategoryIn,
    CustomerIn,
    OrderIn,
    OrderItemIn,
    ProductIn,
    PromotionIn,
)

CSV_FILES: dict[str, type[BaseModel]] = {
    "categories.csv": CategoryIn,
    "products.csv": ProductIn,
    "promotions.csv": PromotionIn,
    "customers.csv": CustomerIn,
    "orders.csv": OrderIn,
    "order_items.csv": OrderItemIn,
}


@dataclass(frozen=True)
class RowError:
    file: str
    line: int
    message: str


@dataclass
class RawDataset:
    categories: list[CategoryIn] = field(default_factory=list)
    products: list[ProductIn] = field(default_factory=list)
    promotions: list[PromotionIn] = field(default_factory=list)
    customers: list[CustomerIn] = field(default_factory=list)
    orders: list[OrderIn] = field(default_factory=list)
    order_items: list[OrderItemIn] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _read(path: Path, model: type[BaseModel], errors: list[RowError]) -> list[BaseModel]:
    valid: list[BaseModel] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for line, raw in enumerate(csv.DictReader(handle), start=2):
            try:
                valid.append(model.model_validate(raw))
            except ValidationError as exc:
                detail = "; ".join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
                )
                errors.append(RowError(path.name, line, detail))
    return valid


def load_raw_dataset(data_dir: Path) -> RawDataset:
    dataset = RawDataset()
    for filename, model in CSV_FILES.items():
        rows = _read(data_dir / filename, model, dataset.errors)
        attribute = filename.removesuffix(".csv")
        getattr(dataset, attribute).extend(rows)
    return dataset
