"""
Shared helpers used by more than one of the 10 shortlisted strategies --
kept here rather than duplicated per-strategy, same "don't reimplement
detection logic inline" principle as the signals/ toolkit itself. Each
function is still a pure function of the bars it's given, no hidden state.
"""

from __future__ import annotations

from datetime import UTC, datetime

from engine.backtest_engine import Bar


def session_levels(bars: list[Bar], as_of: datetime) -> dict[str, float]:
    """Asian session high/low (00:00-07:00 UTC) and previous calendar day's
    high/low -- the same 4 levels `strategies/gold_sweep_reversal.py` marks
    in the production xillion app, reused here rather than reinvented.
    `bars` should be enough history to cover at least today's Asian session
    and yesterday's full day; returns whichever of the 4 levels can
    actually be computed from what's available (fewer than 4 is a real,
    logged possibility on sparse data, not silently guessed at)."""
    today = as_of.date()
    asian = [b for b in bars if b.ts.date() == today and 0 <= b.ts.hour < 7]
    prev_day_bars: list[Bar] = []
    for back in range(1, 6):
        candidate_date = today - _days(back)
        day_bars = [b for b in bars if b.ts.date() == candidate_date]
        if day_bars:
            prev_day_bars = day_bars
            break

    levels: dict[str, float] = {}
    if asian:
        levels["asian_high"] = max(b.high for b in asian)
        levels["asian_low"] = min(b.low for b in asian)
    if prev_day_bars:
        levels["pd_high"] = max(b.high for b in prev_day_bars)
        levels["pd_low"] = min(b.low for b in prev_day_bars)
    return levels


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


def daily_bars_from_m1(bars: list[Bar]) -> list[Bar]:
    """Resamples M1 (or any intraday) bars into one-bar-per-calendar-day
    OHLC -- used by candidate #4 (Wyckoff), which needs a genuinely
    multi-day range, not an intraday one. A pure resampling function, no
    detection logic -- kept separate from signals/price_action.py since
    it's a data-shaping utility, not a signal."""
    by_day: dict[str, list[Bar]] = {}
    for b in bars:
        key = b.ts.date().isoformat()
        by_day.setdefault(key, []).append(b)
    daily: list[Bar] = []
    for key in sorted(by_day):
        day_bars = by_day[key]
        daily.append(
            Bar(
                ts=datetime.combine(day_bars[0].ts.date(), datetime.min.time(), tzinfo=UTC),
                open=day_bars[0].open,
                high=max(b.high for b in day_bars),
                low=min(b.low for b in day_bars),
                close=day_bars[-1].close,
                volume=sum(b.volume for b in day_bars),
            )
        )
    return daily
