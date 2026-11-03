"""Money value object (BRL). Always Decimal, always two decimal places."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")


def _to_decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, order=True)
class Money:
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _to_decimal(self.amount).quantize(_CENTS, ROUND_HALF_UP))

    @classmethod
    def of(cls, value: Decimal | int | str) -> Money:
        return cls(_to_decimal(value))

    @classmethod
    def zero(cls) -> Money:
        return cls(Decimal(0))

    def __add__(self, other: Money) -> Money:
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        return Money(self.amount - other.amount)

    def times(self, factor: Decimal | int) -> Money:
        return Money(self.amount * _to_decimal(factor))

    def divided_by(self, parts: int) -> Money:
        return Money(self.amount / parts)

    def minus_percent(self, percent: Decimal | int) -> Money:
        return Money(self.amount * (Decimal(100) - _to_decimal(percent)) / Decimal(100))

    def format(self) -> str:
        """Brazilian format: R$ 1.234,56"""
        integer, _, cents = f"{self.amount:,.2f}".partition(".")
        return f"R$ {integer.replace(',', '.')},{cents}"

    def __str__(self) -> str:
        return self.format()
