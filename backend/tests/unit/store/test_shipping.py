from emporio.shared.money import Money
from emporio.store.domain.shipping import estimate_shipping


def test_metro_region_free_above_500() -> None:
    quote = estimate_shipping("Campo Grande", Money.of("500.01"))

    assert quote.metro_region and quote.free_shipping and quote.fee == Money.zero()


def test_metro_region_flat_fee_up_to_500() -> None:
    quote = estimate_shipping("campo grande - MS", Money.of(500))

    assert quote.fee == Money.of(35)


def test_other_cities_never_get_an_invented_price() -> None:
    quote = estimate_shipping("Dourados", Money.of(3000))

    assert quote.fee is None
    assert {o.carrier for o in quote.options} >= {"PAC (Correios)", "SEDEX (Correios)"}
