"""Pricing rules from the store manual (§3 payment methods, §6.2 promotion rules).

- PIX gives 5% off the *list* price.
- Promotions are not cumulative: the PIX discount does not apply on top of a promotional price.
- Only active promotions count; if several are active for a product, the best one wins.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from emporio.catalog.domain.models import Product, Promotion
from emporio.shared.money import Money

PIX_DISCOUNT_PERCENT = Decimal(5)


@dataclass(frozen=True)
class PriceQuote:
    list_price: Money
    active_promotion: Promotion | None
    final_price: Money
    """Price for card, debit and boleto (the promotional price when a promotion is active)."""
    pix_price: Money
    pix_discount_applies: bool

    @property
    def discount_percent(self) -> Decimal | None:
        return self.active_promotion.discount_percent if self.active_promotion else None


def best_active_promotion(promotions: Iterable[Promotion]) -> Promotion | None:
    active = [p for p in promotions if p.is_active]
    return max(active, key=lambda p: p.discount_percent, default=None)


def quote_price(product: Product, promotions: Iterable[Promotion]) -> PriceQuote:
    promotion = best_active_promotion(p for p in promotions if p.product_id == product.id)
    if promotion is not None:
        promo_price = product.price.minus_percent(promotion.discount_percent)
        return PriceQuote(
            list_price=product.price,
            active_promotion=promotion,
            final_price=promo_price,
            pix_price=promo_price,
            pix_discount_applies=False,
        )
    return PriceQuote(
        list_price=product.price,
        active_promotion=None,
        final_price=product.price,
        pix_price=product.price.minus_percent(PIX_DISCOUNT_PERCENT),
        pix_discount_applies=True,
    )
