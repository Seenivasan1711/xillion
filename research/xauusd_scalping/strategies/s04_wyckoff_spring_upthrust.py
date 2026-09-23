"""
Candidate #4: Wyckoff Spring/Upthrust at Range Extremes. Composes
`_common.daily_bars_from_m1` (pure resampling, not a signal) ->
PriceActionSignals.range_spring_upthrust. Needs a genuine multi-day range
first -- on the ~3-6 real trading days available in this backfill this will
mostly report "not enough daily history," which is the honest answer for a
strategy whose whole premise requires more days than currently exist.
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
    range_tolerance_pct: float = 1.5


class WyckoffSpringUpthrustStrategy:
    name = "Wyckoff Spring/Upthrust at Range Extremes"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        # 5000 M1 bars (~3.5 trading days) was never enough to produce
        # `range_min_days=5` resampled daily bars -- found 2026-09-23 once
        # 6.5 months of real continuous data still showed zero signals,
        # ruling out "not enough history in the dataset" as the cause.
        # 12000 bars (~8.3 trading days on a 24/5 market) gives comfortable
        # margin above the 5-day gate even accounting for thin/holiday days.
        bars = ctx.bars(12000)
        if len(bars) < 30:
            return None
        daily = daily_bars_from_m1(bars)
        result = pa.range_spring_upthrust(
            daily,
            intraday_bars=bars[-3:],
            range_min_days=self.p.range_min_days,
            range_tolerance_pct=self.p.range_tolerance_pct,
        )
        if not result.fired or not result.reclaimed:
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
