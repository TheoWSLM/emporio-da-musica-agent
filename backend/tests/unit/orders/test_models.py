import pytest

from emporio.orders.domain.models import Customer, PaymentKind, PaymentMethod


@pytest.mark.parametrize(
    ("raw", "kind", "n"),
    [
        ("pix", PaymentKind.PIX, 1),
        ("credit_12x", PaymentKind.CREDIT, 12),
        ("boleto", PaymentKind.BOLETO, 1),
    ],
)
def test_parse_payment_method(raw: str, kind: PaymentKind, n: int) -> None:
    method = PaymentMethod.parse(raw)

    assert (method.kind, method.installments) == (kind, n)


def test_payment_method_label() -> None:
    assert PaymentMethod.parse("credit_6x").label == "cartão de crédito em 6x"


def test_unknown_payment_method_is_rejected() -> None:
    with pytest.raises(ValueError):
        PaymentMethod.parse("cheque")


def test_customer_identity_check() -> None:
    customer = Customer(
        2,
        "Ana Carolina Ferreira",
        "(67) 99654-7821",
        "anacarol.ferreira@coldmail.com",
        "Campo Grande",
    )

    assert customer.matches(email=" AnaCarol.Ferreira@coldmail.com ")
    assert customer.matches(phone="67996547821")
    assert customer.matches(phone="99654-7821")
    assert not customer.matches(email="outra@coldmail.com")
    assert not customer.matches(phone="7821")
    assert not customer.matches()
