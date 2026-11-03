from decimal import Decimal

from emporio.catalog.domain.models import Availability, Product, ProductStatus, Promotion
from emporio.catalog.domain.pricing import quote_price
from emporio.shared.money import Money


def product(
    price: str = "2399", stock: int = 3, status: ProductStatus = ProductStatus.ACTIVE
) -> Product:
    return Product(1, "Crafter HT-100", 5, "Violão folk", Money.of(price), stock, status)


def promo(percent: int, active: bool, promo_id: int = 1, product_id: int = 1) -> Promotion:
    return Promotion(promo_id, product_id, Decimal(percent), "Desconto Exclusivo", active)


def test_pix_discount_applies_without_promotion() -> None:
    quote = quote_price(product(), [])

    assert quote.final_price == Money.of(2399)
    assert quote.pix_price == Money.of("2279.05")
    assert quote.pix_discount_applies is True


def test_promotion_is_not_cumulative_with_pix() -> None:
    quote = quote_price(product(), [promo(18, active=True)])

    assert quote.final_price == Money.of("1967.18")
    assert quote.pix_price == quote.final_price
    assert quote.pix_discount_applies is False
    assert quote.discount_percent == Decimal(18)


def test_inactive_promotions_are_ignored() -> None:
    quote = quote_price(product(), [promo(30, active=False)])

    assert quote.active_promotion is None


def test_best_active_promotion_wins() -> None:
    quote = quote_price(product(), [promo(10, True, 1), promo(15, True, 2), promo(40, False, 3)])

    assert quote.discount_percent == Decimal(15)


def test_promotions_of_other_products_are_ignored() -> None:
    quote = quote_price(product(), [promo(20, True, product_id=99)])

    assert quote.active_promotion is None


def test_availability_is_derived_from_status_and_stock() -> None:
    assert product(stock=0).availability is Availability.OUT_OF_STOCK
    assert product(status=ProductStatus.DISCONTINUED).availability is Availability.DISCONTINUED
    assert product(status=ProductStatus.COMING_SOON).availability is Availability.COMING_SOON
    assert product().is_sellable
