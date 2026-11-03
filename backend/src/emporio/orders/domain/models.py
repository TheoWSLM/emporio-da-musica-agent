"""Orders and customers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from emporio.shared.money import Money


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {
            OrderStatus.PENDING: "aguardando confirmação do pagamento",
            OrderStatus.CONFIRMED: "pagamento confirmado, em separação",
            OrderStatus.SHIPPED: "enviado (em trânsito)",
            OrderStatus.DELIVERED: "entregue",
            OrderStatus.CANCELLED: "cancelado",
        }[self]


class PaymentKind(StrEnum):
    PIX = "pix"
    DEBIT = "debit"
    CREDIT = "credit"
    BOLETO = "boleto"


_PAYMENT_LABELS = {
    PaymentKind.PIX: "PIX",
    PaymentKind.DEBIT: "cartão de débito",
    PaymentKind.CREDIT: "cartão de crédito",
    PaymentKind.BOLETO: "boleto bancário",
}

_PAYMENT_PATTERN = re.compile(r"^(?P<kind>pix|debit|credit|boleto)(?:_(?P<n>\d{1,2})x)?$")


@dataclass(frozen=True)
class PaymentMethod:
    kind: PaymentKind
    installments: int = 1

    @classmethod
    def parse(cls, raw: str) -> PaymentMethod:
        """Parses the source format: 'pix', 'debit', 'boleto', 'credit_6x'."""
        match = _PAYMENT_PATTERN.match(raw.strip().lower())
        if match is None:
            raise ValueError(f"unknown payment method: {raw!r}")
        kind = PaymentKind(match["kind"])
        installments = int(match["n"]) if match["n"] else 1
        if kind is not PaymentKind.CREDIT and installments != 1:
            raise ValueError(f"only credit card payments have installments: {raw!r}")
        return cls(kind, installments)

    @property
    def label(self) -> str:
        base = _PAYMENT_LABELS[self.kind]
        return f"{base} em {self.installments}x" if self.installments > 1 else base


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str
    city: str

    @property
    def first_name(self) -> str:
        return self.name.split()[0]

    def matches(self, *, email: str | None = None, phone: str | None = None) -> bool:
        """Identity check used before disclosing any order data (LGPD)."""
        if email and normalize_email(email) == normalize_email(self.email):
            return True
        if phone:
            given, own = normalize_phone(phone), normalize_phone(self.phone)
            # Accept with or without the area code (DDD).
            return len(given) >= 8 and own.endswith(given)
        return False


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total: Money
    payment: PaymentMethod
    items: tuple[OrderItem, ...] = ()
    tracking_code: str | None = None
    estimated_delivery: date | None = None
    notes: str | None = None

    @property
    def received_on(self) -> date | None:
        """The data has no actual receipt date: for delivered orders we assume the estimated delivery
        date (documented assumption)."""
        return self.estimated_delivery if self.status is OrderStatus.DELIVERED else None
