from decimal import Decimal

from emporio.shared.money import Money


def test_money_rounds_to_cents_half_up() -> None:
    assert Money.of("10.005").amount == Decimal("10.01")


def test_money_formats_in_brazilian_style() -> None:
    assert Money.of("11499").format() == "R$ 11.499,00"
    assert Money.of("599.9").format() == "R$ 599,90"


def test_minus_percent() -> None:
    assert Money.of(2399).minus_percent(18) == Money.of("1967.18")
