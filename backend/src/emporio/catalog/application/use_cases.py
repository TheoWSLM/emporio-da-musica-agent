"""Catalog use cases: product search, product lookup and payment options."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from emporio.catalog.application.ports import (
    CategoryReader,
    ProductFilter,
    ProductReader,
    PromotionReader,
    ScoredProduct,
)
from emporio.catalog.domain.installments import (
    InstallmentCheck,
    InstallmentOption,
    check_installments,
    combined_payment_allowed,
    installment_options,
)
from emporio.catalog.domain.models import Product, Promotion
from emporio.catalog.domain.pricing import PIX_DISCOUNT_PERCENT, PriceQuote, quote_price
from emporio.catalog.domain.scope import detect_accessory, resolve_categories
from emporio.knowledge.application.ports import Embedder
from emporio.shared.errors import NotFoundError
from emporio.shared.money import Money


@dataclass(frozen=True)
class ProductOffer:
    product: Product
    category: str
    quote: PriceQuote


@dataclass(frozen=True)
class SearchCriteria:
    query: str | None = None
    category: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock_only: bool = True
    strings: str | None = None
    electric: bool | None = None
    limit: int = 5


@dataclass(frozen=True)
class SearchResult:
    offers: list[ProductOffer]
    alternatives: list[ProductOffer] = field(default_factory=list)
    out_of_catalog: str | None = None
    unknown_category: str | None = None
    empty_category: str | None = None


class CatalogService:
    """Groups the catalog read use cases; each public method is one intention."""

    def __init__(
        self,
        products: ProductReader,
        promotions: PromotionReader,
        categories: CategoryReader,
        embedder: Embedder,
    ) -> None:
        self._products = products
        self._promotions = promotions
        self._categories = categories
        self._embedder = embedder

    async def _offers(self, scored: list[ScoredProduct]) -> list[ProductOffer]:
        products = [s.product for s in scored]
        promotions = await self._promotions.for_products([p.id for p in products])
        names = {c.id: c.name for c in await self._categories.all()}
        return [
            ProductOffer(p, names.get(p.category_id, ""), quote_price(p, promotions))
            for p in products
        ]

    async def search(self, criteria: SearchCriteria) -> SearchResult:
        text = " ".join(filter(None, [criteria.category, criteria.query]))
        accessory = detect_accessory(text)
        if accessory and not criteria.category:
            return SearchResult(offers=[], out_of_catalog=accessory)

        all_categories = await self._categories.all()
        matched = resolve_categories(text, all_categories)
        if criteria.category and not resolve_categories(criteria.category, all_categories):
            return SearchResult(offers=[], unknown_category=criteria.category)

        filters = ProductFilter(
            category_ids=tuple(c.id for c in matched),
            min_price=criteria.min_price,
            max_price=criteria.max_price,
            in_stock_only=criteria.in_stock_only,
            strings=criteria.strings,
            electric=criteria.electric,
        )
        embedding = (await self._embedder.embed([criteria.query]))[0] if criteria.query else None
        scored = await self._products.search(embedding, filters, criteria.limit)
        if scored:
            return SearchResult(offers=await self._offers(scored))

        # Nothing matched: say so honestly and offer the closest in-stock items of the same category.
        relaxed = ProductFilter(category_ids=filters.category_ids, in_stock_only=True)
        alternatives = await self._products.search(embedding, relaxed, 3)
        empty = matched[0].name if matched and not alternatives else None
        return SearchResult(
            offers=[], alternatives=await self._offers(alternatives), empty_category=empty
        )

    async def get_product(self, reference: str) -> ProductDetails:
        reference = reference.strip()
        product: Product | None = None
        candidates: list[ScoredProduct] = []
        if reference.isdigit():
            product = await self._products.get(int(reference))
        else:
            candidates = await self._products.find_by_name(reference, limit=4)
            if candidates and (
                len(candidates) == 1 or candidates[0].score - candidates[1].score >= 0.1
            ):
                product = candidates[0].product
        if product is None:
            if not candidates:
                raise NotFoundError(f"produto não encontrado: {reference}")
            return ProductDetails(offer=None, candidates=await self._offers(candidates))

        promotions = await self._promotions.for_products([product.id])
        [offer] = await self._offers([ScoredProduct(product, 1.0)])
        expired = [p for p in promotions if not p.is_active]
        alternatives: list[ProductOffer] = []
        if not product.is_sellable:
            [embedding] = await self._embedder.embed([f"{product.name}. {product.description}"])
            similar = await self._products.search(
                embedding,
                ProductFilter(category_ids=(product.category_id,), exclude_ids=(product.id,)),
                3,
            )
            alternatives = await self._offers(similar)
        return ProductDetails(offer=offer, expired_promotions=expired, alternatives=alternatives)

    async def payment_options(
        self, *, product_id: int | None, amount: Decimal | None, installments: int | None
    ) -> PaymentOptions:
        offer: ProductOffer | None = None
        if product_id is not None:
            product = await self._products.get(product_id)
            if product is None:
                raise NotFoundError(f"produto {product_id} não encontrado")
            [offer] = await self._offers([ScoredProduct(product, 1.0)])
            card_total = offer.quote.final_price
            pix_total = offer.quote.pix_price
            pix_discount = offer.quote.pix_discount_applies
        elif amount is not None:
            card_total = Money.of(amount)
            pix_total = card_total.minus_percent(PIX_DISCOUNT_PERCENT)
            pix_discount = True
        else:
            raise ValueError("informe product_id ou amount")
        return PaymentOptions(
            offer=offer,
            card_total=card_total,
            pix_total=pix_total,
            pix_discount_applies=pix_discount,
            installments=installment_options(card_total),
            requested=check_installments(card_total, installments) if installments else None,
            combined_payment_allowed=combined_payment_allowed(card_total),
        )


@dataclass(frozen=True)
class ProductDetails:
    offer: ProductOffer | None
    candidates: list[ProductOffer] = field(default_factory=list)
    expired_promotions: list[Promotion] = field(default_factory=list)
    alternatives: list[ProductOffer] = field(default_factory=list)


@dataclass(frozen=True)
class PaymentOptions:
    offer: ProductOffer | None
    card_total: Money
    pix_total: Money
    pix_discount_applies: bool
    installments: list[InstallmentOption]
    requested: InstallmentCheck | None
    combined_payment_allowed: bool
