from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from emporio.store.domain.hours import store_status

TZ = ZoneInfo("America/Campo_Grande")


def at(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ)


@pytest.mark.parametrize(
    ("moment", "is_open"),
    [
        (at(2026, 11, 4, 9, 0), True),  # Wednesday opening
        (at(2026, 11, 4, 17, 59), True),
        (at(2026, 11, 4, 18, 0), False),
        (at(2026, 11, 7, 12, 59), True),  # Saturday
        (at(2026, 11, 7, 13, 1), False),
        (at(2026, 11, 8, 10, 0), False),  # Sunday
        (at(2026, 11, 2, 10, 0), False),  # Finados (Monday)
    ],
)
def test_opening_hours(moment: datetime, is_open: bool) -> None:
    assert store_status(moment).is_open is is_open


def test_next_opening_skips_sunday() -> None:
    status = store_status(at(2026, 11, 7, 14, 0))

    assert status.next_opening == at(2026, 11, 9, 9, 0)


def test_holiday_reason_is_reported() -> None:
    status = store_status(at(2026, 11, 2, 10, 0))

    assert status.closed_reason is not None and "Finados" in status.closed_reason
    assert status.next_opening == at(2026, 11, 3, 9, 0)
