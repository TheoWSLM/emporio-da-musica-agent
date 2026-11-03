import pytest

from emporio.catalog.domain.installments import (
    check_installments,
    combined_payment_allowed,
    installment_options,
    max_installments,
)
from emporio.shared.money import Money


@pytest.mark.parametrize(
    ("amount", "count", "allowed"),
    [
        ("150", 3, True),  # R$50 per installment: exactly the minimum
        ("149.99", 3, False),
        ("320", 4, True),  # R$80
        ("319.99", 4, False),
        ("480", 6, True),
        ("700", 7, True),  # R$100
        ("699.99", 7, False),
        ("1200", 12, True),
        ("1199.99", 12, False),
        ("10", 1, True),  # 1x is always allowed
        ("5000", 13, False),
    ],
)
def test_installment_minimums_from_the_manual(amount: str, count: int, allowed: bool) -> None:
    assert check_installments(Money.of(amount), count).allowed is allowed


def test_rejection_explains_the_minimum() -> None:
    check = check_installments(Money.of("599"), 12)

    assert not check.allowed
    assert "R$ 100,00" in check.reason


def test_options_and_maximum() -> None:
    amount = Money.of("599")

    # 599 / 6 = 99.83 >= R$80 (4x-6x rule); 599 / 7 = 85.57 < R$100 (7x-12x rule)
    assert [o.count for o in installment_options(amount)] == [1, 2, 3, 4, 5, 6]
    assert max_installments(amount) == 6
    assert max_installments(Money.of("11499")) == 12


def test_combined_payment_only_above_two_thousand() -> None:
    assert not combined_payment_allowed(Money.of(2000))
    assert combined_payment_allowed(Money.of("2000.01"))
