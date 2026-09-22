"""
Candidate #5: NR7/Inside-Bar Compression Breakout. The one non-SMC
candidate (Crabel-style volatility contraction), kept for mechanism
independence from the other 9. Composes
PriceActionSignals.nr7_inside_bar -> waits for a close beyond that bar's
own high/low as the actual breakout trigger.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.price_action import PriceActionSignals
from signals.risk_floor import apply_floor

pa = PriceActionSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    nr_lookback: int = 7
    target_range_mult: float = 1.5


@dataclass
class _Pending:
    bar_high: float
    bar_low: float
    bar_range: float


class Nr7InsideBarBreakoutStrategy:
    name = "NR7/Inside-Bar Compression Breakout"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._pending: _Pending | None = None

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(200)
        if len(bars) < self.p.nr_lookback + 1:
            return None

        if self._pending is not None:
            pend = self._pending
            if bar.close > pend.bar_high:
                return self._fire_entry(bar, pend, Side.LONG)
            if bar.close < pend.bar_low:
                return self._fire_entry(bar, pend, Side.SHORT)
            # invalidate once price has drifted well away without breaking out
            if abs(bar.close - (pend.bar_high + pend.bar_low) / 2) > 3 * pend.bar_range:
                self._pending = None
            return None

        result = pa.nr7_inside_bar(bars, nr_lookback=self.p.nr_lookback)
        if result.fired:
            self._pending = _Pending(bar_high=bar.high, bar_low=bar.low, bar_range=result.bar_range)
        return None

    def _fire_entry(self, bar: Bar, pend: _Pending, side: Side) -> Signal:
        entry = bar.close
        if side == Side.LONG:
            stop = pend.bar_low
            target = entry + self.p.target_range_mult * pend.bar_range
        else:
            stop = pend.bar_high
            target = entry - self.p.target_range_mult * pend.bar_range
        if abs(entry - stop) < self.p.min_sl_pts:
            stop = entry - self.p.min_sl_pts if side == Side.LONG else entry + self.p.min_sl_pts
        reason = f"NR7/inside bar {pend.bar_low:.2f}-{pend.bar_high:.2f} broken at {entry:.2f}"
        self._pending = None
        stop, target = apply_floor(entry, stop, target, side)
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
