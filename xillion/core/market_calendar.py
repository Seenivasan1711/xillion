"""
Market-hours and holiday awareness. Pluggable by `market` identifier so a
future asset class (e.g. forex, near-24/5 session hours) can register its
own calendar alongside NSE_BSE, rather than requiring a rewrite of this
module.
"""
import zoneinfo
from datetime import date, datetime, time, timezone

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Hand-maintained -- NSE/BSE publish next year's holiday calendar each
# December. This is an MVP simplification: a static list that needs manual
# annual updates, NOT a live-fetched exchange calendar. Verify against the
# official NSE/BSE circular before relying on it.
NSE_BSE_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 4),    # Holi (indicative -- verify against the official circular)
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 12, 25),  # Christmas
}


def _is_nse_bse_open(now: datetime) -> bool:
    local = now.astimezone(IST)
    if local.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if local.date() in NSE_BSE_HOLIDAYS_2026:
        return False
    return MARKET_OPEN <= local.time() <= MARKET_CLOSE


_CALENDARS = {
    "NSE_BSE": _is_nse_bse_open,
}


def is_market_open(now: datetime, market: str = "NSE_BSE") -> bool:
    """`now` may be naive (assumed UTC) or tz-aware."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    calendar = _CALENDARS.get(market)
    if calendar is None:
        raise ValueError(f"unknown market calendar: {market!r}")
    return calendar(now)
