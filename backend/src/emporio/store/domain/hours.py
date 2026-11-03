"""Opening hours (store manual §2).

Mon–Fri 09:00–18:00, Sat 09:00–13:00, Sundays and holidays closed. The manual does not list holidays:
we use Brazil's fixed-date national holidays (movable ones such as Carnival or Good Friday are a known
limitation).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WEEKDAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

# (month, day) -> name
FIXED_NATIONAL_HOLIDAYS: dict[tuple[int, int], str] = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia da Consciência Negra",
    (12, 25): "Natal",
}


@dataclass(frozen=True)
class OpeningWindow:
    opens: time
    closes: time


WEEKLY_SCHEDULE: dict[int, OpeningWindow | None] = {
    0: OpeningWindow(time(9), time(18)),
    1: OpeningWindow(time(9), time(18)),
    2: OpeningWindow(time(9), time(18)),
    3: OpeningWindow(time(9), time(18)),
    4: OpeningWindow(time(9), time(18)),
    5: OpeningWindow(time(9), time(13)),
    6: None,
}


@dataclass(frozen=True)
class StoreStatus:
    is_open: bool
    now: datetime
    today_window: OpeningWindow | None
    closed_reason: str | None
    next_opening: datetime | None


def describe_weekly_hours() -> list[str]:
    """The schedule in words, derived from WEEKLY_SCHEDULE (e.g. "segunda a sexta: 09:00 às 18:00")."""
    lines: list[str] = []
    day = 0
    while day < 7:
        window = WEEKLY_SCHEDULE[day]
        last = day
        while last + 1 < 7 and WEEKLY_SCHEDULE[last + 1] == window:
            last += 1
        if window is not None:
            days = (
                WEEKDAY_NAMES[day]
                if day == last
                else f"{WEEKDAY_NAMES[day]} a {WEEKDAY_NAMES[last]}"
            )
            lines.append(f"{days}: {window.opens:%H:%M} às {window.closes:%H:%M}")
        day = last + 1
    closed = [f"{WEEKDAY_NAMES[d]}s" for d in range(7) if WEEKLY_SCHEDULE[d] is None]
    lines.append(f"{', '.join(closed)} e feriados: fechado")
    return lines


def holiday_name(day: date) -> str | None:
    return FIXED_NATIONAL_HOLIDAYS.get((day.month, day.day))


def window_for(day: date) -> OpeningWindow | None:
    if holiday_name(day) is not None:
        return None
    return WEEKLY_SCHEDULE[day.weekday()]


def next_opening_after(moment: datetime) -> datetime:
    day = moment.date()
    for offset in range(0, 15):
        candidate_day = day + timedelta(days=offset)
        window = window_for(candidate_day)
        if window is None:
            continue
        opening = datetime.combine(candidate_day, window.opens, tzinfo=moment.tzinfo)
        if opening > moment:
            return opening
    raise RuntimeError("no opening found in the next two weeks")  # pragma: no cover


def store_status(moment: datetime) -> StoreStatus:
    window = window_for(moment.date())
    holiday = holiday_name(moment.date())
    if window is not None and window.opens <= moment.time() < window.closes:
        return StoreStatus(True, moment, window, None, None)
    if holiday:
        reason = f"feriado ({holiday})"
    elif window is None:
        reason = "domingo"
    elif moment.time() < window.opens:
        reason = "ainda não abrimos hoje"
    else:
        reason = "já encerramos o expediente de hoje"
    return StoreStatus(False, moment, window, reason, next_opening_after(moment))
