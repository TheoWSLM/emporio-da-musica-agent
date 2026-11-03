"""Pydantic models for the raw CSV rows. Dirty data becomes validation errors in the quality report."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from emporio.orders.domain.models import PaymentMethod, normalize_email


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


TRACKING_CODE = re.compile(r"^BR[A-Z0-9]{9}BR$")


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class CategoryIn(_Row):
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    description: str


class ProductIn(_Row):
    product_id: int = Field(gt=0)
    price_brl: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    name: str = Field(min_length=1)
    category_id: int = Field(gt=0)
    description: str
    stock_quantity: int = Field(ge=0)
    status: Literal["active", "discontinued", "coming_soon"]
    specs: dict[str, str]
    created_at: date | None = None

    @field_validator("specs", mode="before")
    @classmethod
    def _parse_specs(cls, value: Any) -> Any:
        if isinstance(value, str):
            parsed = json.loads(value) if value.strip() else {}
            if not isinstance(parsed, dict):
                raise ValueError("specs must be a JSON object")
            return {str(k): str(v) for k, v in parsed.items()}
        return value


class PromotionIn(_Row):
    promotion_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    discount_percent: Decimal = Field(gt=0, lt=100)
    description: str
    is_active: bool


class CustomerIn(_Row):
    customer_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    phone: str = Field(pattern=r"^\(\d{2}\) \d{4,5}-\d{4}$")
    email: str
    city: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("invalid e-mail")
        return normalize_email(value)


class OrderIn(_Row):
    order_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    order_date: date
    status: Literal["pending", "confirmed", "shipped", "delivered", "cancelled"]
    total_brl: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    payment_method: str
    tracking_code: Annotated[str | None, BeforeValidator(_blank_to_none)] = None
    estimated_delivery: Annotated[date | None, BeforeValidator(_blank_to_none)] = None
    notes: Annotated[str | None, BeforeValidator(_blank_to_none)] = None

    @field_validator("payment_method")
    @classmethod
    def _known_payment(cls, value: str) -> str:
        PaymentMethod.parse(value)
        return value

    @field_validator("tracking_code")
    @classmethod
    def _tracking_format(cls, value: str | None) -> str | None:
        if value is not None and not TRACKING_CODE.match(value):
            raise ValueError("tracking code must be BR + 9 alphanumerics + BR (manual §5.3)")
        return value


class OrderItemIn(_Row):
    order_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    product_id: int = Field(gt=0)
