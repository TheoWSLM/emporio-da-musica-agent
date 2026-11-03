"""Shipping policy (store manual §5).

- Campo Grande metropolitan region: free above R$ 500,00, otherwise a flat R$ 35,00; 1 to 3 business
  days by the store's own courier. (Assumption: we treat the city of Campo Grande as the metro region,
  since the manual does not list the municipalities.)
- Other cities: Correios PAC/SEDEX or Jadlog; the price depends on ZIP code, weight and dimensions, so
  we never invent a value. Large instruments may need a special quote.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from emporio.shared.money import Money

FREE_SHIPPING_THRESHOLD = Money.of(500)
METRO_FLAT_FEE = Money.of(35)
METRO_CITIES = frozenset({"campo grande"})
LARGE_INSTRUMENT_NOTE = (
    "Instrumentos de grande porte (baterias acústicas, pianos digitais, contrabaixos) podem exigir "
    "frete especial com cotação individual."
)


@dataclass(frozen=True)
class ShippingOption:
    carrier: str
    estimated_days: str
    tracking: bool = True
    insurance_included: bool = True


@dataclass(frozen=True)
class ShippingQuote:
    city: str
    metro_region: bool
    fee: Money | None
    """Known fee; None means it must be quoted by ZIP code."""
    free_shipping: bool
    options: tuple[ShippingOption, ...]
    notes: tuple[str, ...]


def _normalize(city: str) -> str:
    text = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split()).removesuffix(" ms").strip()


def is_metro_region(city: str) -> bool:
    return _normalize(city) in METRO_CITIES


def estimate_shipping(city: str, order_value: Money) -> ShippingQuote:
    if is_metro_region(city):
        free = order_value.amount > FREE_SHIPPING_THRESHOLD.amount
        return ShippingQuote(
            city=city,
            metro_region=True,
            fee=Money.zero() if free else METRO_FLAT_FEE,
            free_shipping=free,
            options=(
                ShippingOption("Motoboy próprio da loja", "1 a 3 dias úteis", tracking=False),
            ),
            notes=("O cliente é contactado por telefone antes da entrega.",),
        )
    return ShippingQuote(
        city=city,
        metro_region=False,
        fee=None,
        free_shipping=False,
        options=(
            ShippingOption("PAC (Correios)", "5 a 12 dias úteis"),
            ShippingOption("SEDEX (Correios)", "2 a 5 dias úteis"),
            ShippingOption("Jadlog (.package)", "3 a 8 dias úteis"),
        ),
        notes=(
            "O valor do frete é calculado pelo CEP de destino, peso e dimensões do produto.",
            LARGE_INSTRUMENT_NOTE,
            "Todos os envios têm rastreamento e seguro contra extravio e avarias.",
        ),
    )
