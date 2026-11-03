"""Store use cases (hours and shipping). Thin on purpose: the rules live in the domain."""

from __future__ import annotations

from emporio.shared.clock import Clock
from emporio.shared.money import Money
from emporio.store.domain.hours import StoreStatus, store_status
from emporio.store.domain.shipping import ShippingQuote, estimate_shipping


class StoreService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def status(self) -> StoreStatus:
        return store_status(self._clock.now())

    def shipping(self, city: str, order_value: Money) -> ShippingQuote:
        return estimate_shipping(city, order_value)
