"""Clock port. Business code never calls datetime.now() directly."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    def __init__(self, timezone: str) -> None:
        self._tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def today(self) -> date:
        return self.now().date()


class ReferenceDateClock:
    """Pins the calendar date (for demos over historical data) but keeps the real time of day."""

    def __init__(self, reference_date: date, timezone: str) -> None:
        self._date = reference_date
        self._tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        real = datetime.now(self._tz)
        return datetime.combine(self._date, real.timetz())

    def today(self) -> date:
        return self._date
