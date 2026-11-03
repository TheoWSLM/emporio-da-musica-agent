"""In-memory limits protecting the public demo (single API replica). Excess -> HTTP 429."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import date


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_seconds: float, now: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._now = now
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._now()
        hits = self._hits[key]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True


class DailyBudget:
    def __init__(self, limit: int, today: Callable[[], date] = date.today) -> None:
        self._limit = limit
        self._today = today
        self._day = today()
        self._count = 0

    def allow(self) -> bool:
        if self._today() != self._day:
            self._day, self._count = self._today(), 0
        if self._count >= self._limit:
            return False
        self._count += 1
        return True
