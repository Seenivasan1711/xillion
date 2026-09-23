"""
Candidate #4: Wyckoff Spring/Upthrust at Range Extremes. Composes
`_common.daily_bars_from_m1` (pure resampling, not a signal) ->
PriceActionSignals.range_spring_upthrust. Range-vs-trend detection is now
the 3-gate design from 2026-09-23 (see
research/xauusd_scalping/S04_range_detection_design_question.md) -- the
old "every day touches both extremes" check was confirmed broken by direct
tracing (852/873 real windows failed it), not a data-volume problem.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.price_action import Direction, PriceActionSignals
from signals.risk_floor import apply_floor

from ._common import daily_bars_from_m1

pa = PriceActionSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    range_min_days: int = 5
    trend_lookback_days: int = 10
    reclaim_within_bars: int = 15


class WyckoffSpringUpthrustStrategy:
    name = "Wyckoff Spring/Upthrust at Range Extremes"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._cached_date = None
        self._cached_historical_daily: list[Bar] = []

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        # The 3-gate detector needs max(range_min_days, trend_lookback_days)
        # + atr_period + 2 = max(5,10)+14+2 = 26 daily bars minimum -- found
        # 2026-09-23 that the previous 12000-bar window (~8.3 trading days,
        # sized for the OLD 5-day-only requirement) made every real window
        # hit "not enough daily history" silently, which a naive read of
        # gate_failed=="" misreports as "all gates pass" (same failure mode
        # as S02's original too-small window, just recurring at the next
        # layer). 45000 bars (~31 trading days) gives comfortable margin.
        # Measured gate pass rate on real data at this window size: 7.12%
        # (confirmed independently by the coordinator at 6.62% on a
        # coarser sample) -- below the 10-25% prior-expectation band stated
        # before checking (S04_range_detection_design_question.md section
        # A3), though not under the <2% "debug, don't retune" trigger
        # either. Reported honestly as a real, unresolved discrepancy, not
        # adjusted to fit the band after the fact.
        bars = ctx.bars(45000)
        if len(bars) < 30:
            return None

        # Resampling the full 45000-bar window to daily on EVERY M1 bar cost
        # ~40min for a single full-dataset backtest (found 2026-09-23 when a
        # coordinator flagged S04 running far slower than S02's similarly-
        # sized window) -- the design doc's own note (A6.6) already called
        # this out: the daily gate only changes once per calendar day, so
        # resample the historical (pre-today) portion once per day and
        # cache it, only re-resampling the small "today so far" slice (at
        # most ~1440 bars, found via a cheap reverse scan since today's
        # bars are always the last contiguous chunk) on every call. The
        # shared range_spring_upthrust function itself stays pure -- all
        # the caching lives here in the caller, per the design doc's
        # explicit instruction not to break that function's purity for it.
        today = bars[-1].ts.date()
        if today != self._cached_date:
            split = 0
            for i in range(len(bars) - 1, -1, -1):
                if bars[i].ts.date() != today:
                    split = i + 1
                    break
            self._cached_historical_daily = daily_bars_from_m1(bars[:split])
            self._today_split = split
            self._cached_date = today

        todays_bars = bars[self._today_split :]
        today_daily = daily_bars_from_m1(todays_bars) if todays_bars else []
        daily = self._cached_historical_daily + today_daily

        # The 3-gate detector scans back over `reclaim_within_bars` intraday
        # bars for a penetration+reclaim pair as a pure function -- needs
        # that many trailing M1 bars, not just the last 3.
        result = pa.range_spring_upthrust(
            daily,
            intraday_bars=bars[-(self.p.reclaim_within_bars + 1) :],
            range_min_days=self.p.range_min_days,
            trend_lookback_days=self.p.trend_lookback_days,
            reclaim_within_bars=self.p.reclaim_within_bars,
        )
        if not result.fired:
            return None

        entry = bar.close
        if result.direction == Direction.DOWN:  # spring -- go long, target the range top
            side = Side.LONG
            stop = min(bars[-1].low - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            target = result.range_high
        else:  # upthrust -- go short, target the range bottom
            side = Side.SHORT
            stop = max(bars[-1].high + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            target = result.range_low
        reason = f"{result.reason}, range {result.range_low:.2f}-{result.range_high:.2f}, reclaimed"
        stop, target = apply_floor(entry, stop, target, side)
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
