"""Credit-card installment rules (store manual §3 and §3.1).

Interest-free up to 12x, with a minimum installment value that depends on the number of installments:
  - up to 3x: minimum R$ 50,00   (assumption: the manual says "no minimum, except below R$ 50,00")
  - 4x to 6x: minimum R$ 80,00
  - 7x to 12x: minimum R$ 100,00
Combining payment methods (e.g. PIX + card) is allowed for purchases above R$ 2.000,00.
"""

from __future__ import annotations

from dataclasses import dataclass

from emporio.shared.money import Money

MAX_INSTALLMENTS = 12
COMBINED_PAYMENT_THRESHOLD = Money.of(2000)


def minimum_installment_for(count: int) -> Money:
    if not 1 <= count <= MAX_INSTALLMENTS:
        raise ValueError(f"installments must be between 1 and {MAX_INSTALLMENTS}")
    if count <= 3:
        return Money.of(50)
    if count <= 6:
        return Money.of(80)
    return Money.of(100)


@dataclass(frozen=True)
class InstallmentOption:
    count: int
    installment_value: Money
    total: Money


@dataclass(frozen=True)
class InstallmentCheck:
    count: int
    allowed: bool
    installment_value: Money
    minimum_installment: Money
    reason: str


def _installment_value(amount: Money, count: int) -> Money:
    return amount.divided_by(count)


def check_installments(amount: Money, count: int) -> InstallmentCheck:
    if count < 1 or count > MAX_INSTALLMENTS:
        return InstallmentCheck(
            count=count,
            allowed=False,
            installment_value=Money.zero(),
            minimum_installment=Money.zero(),
            reason=f"O parcelamento vai de 1x até {MAX_INSTALLMENTS}x sem juros.",
        )
    value = _installment_value(amount, count)
    if count == 1:
        return InstallmentCheck(count, True, value, Money.zero(), "Pagamento à vista no cartão.")
    minimum = minimum_installment_for(count)
    # Compare the exact split (amount / count), not the rounded installment value.
    if amount.amount >= minimum.amount * count:
        return InstallmentCheck(count, True, value, minimum, f"{count}x sem juros.")
    return InstallmentCheck(
        count=count,
        allowed=False,
        installment_value=value,
        minimum_installment=minimum,
        reason=(
            f"Em {count}x a parcela seria {value}, abaixo do mínimo de {minimum} "
            f"exigido para {count} parcelas."
        ),
    )


def installment_options(amount: Money) -> list[InstallmentOption]:
    """All interest-free installment plans allowed for the amount (1x is always allowed)."""
    options: list[InstallmentOption] = []
    for count in range(1, MAX_INSTALLMENTS + 1):
        check = check_installments(amount, count)
        if check.allowed:
            options.append(InstallmentOption(count, check.installment_value, amount))
    return options


def max_installments(amount: Money) -> int:
    return max(option.count for option in installment_options(amount))


def combined_payment_allowed(amount: Money) -> bool:
    return amount.amount > COMBINED_PAYMENT_THRESHOLD.amount
