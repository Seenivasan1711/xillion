"""
Candidate #7: Market Profile Value-Area Rotation. Classical CBOT/Steidlmayer
methodology, not SMC -- the odd one out on purpose, to test a genuinely
different mechanism family. Builds a time-at-price profile of the previous
calendar day (volume in this feed is tick-count-derived, not true traded
volume, so time-at-price is the honest choice here -- the spec card's own
documented fallback "if volume unreliable"), then fades a touch of
yesterday's value-area high/low back toward the point of control, but only
when today opened inside yesterday's value area (a balance-day precondition
from the same methodology).

`_value_area` is a pure data-shaping helper (bins typical price by bar
count), not a signal -- kept local to this module since candidate #7 is its
only caller, same "don't share what nothing else needs" reasoning as the
signals toolkit's own scoping.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals

ind = IndicatorSignals()


def _value_area(day_bars: list[Bar], bin_pts: float = 0.5, value_area_pct: float = 0.70):
    if not day_bars:
        return None
    counts: dict[float, int] = {}
    for b in day_bars:
        typical = (b.high + b.low + b.close) / 3.0
        key = round(typical / bin_pts) * bin_pts
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    bins = sorted(counts)
    poc = max(counts, key=lambda k: counts[k])
    total = sum(counts.values())
    target = total * value_area_pct
    idx = bins.index(poc)
    lo, hi = idx, idx
    acc = counts[poc]
    while acc < target and (lo > 0 or hi < len(bins) - 1):
        lo_val = counts[bins[lo - 1]] if lo > 0 else -1
        hi_val = counts[bins[hi + 1]] if hi < len(bins) - 1 else -1
        if hi_val >= lo_val and hi < len(bins) - 1:
            hi += 1
            acc += counts[bins[hi]]
        elif lo > 0:
            lo -= 1
            acc += counts[bins[lo]]
        else:
            break
    return poc, bins[hi], bins[lo]  # poc, vah, val


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    bin_pts: float = 0.5
    value_area_pct: float = 0.70


class ValueAreaRotationStrategy:
    name = "Market Profile Value-Area Rotation"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(3000)
        today = bar.ts.date()
        prev_day_bars: list[Bar] = []
        for back in range(1, 6):
            from datetime import timedelta

            candidate_date = today - timedelta(days=back)
            day_bars = [b for b in bars if b.ts.date() == candidate_date]
            if day_bars:
                prev_day_bars = day_bars
                break
        if not prev_day_bars:
            return None

        va = _value_area(prev_day_bars, bin_pts=self.p.bin_pts, value_area_pct=self.p.value_area_pct)
        if va is None:
            return None
        poc, vah, val = va

        todays_bars = [b for b in bars if b.ts.date() == today]
        if not todays_bars:
            return None
        opened_inside = val <= todays_bars[0].open <= vah
        if not opened_inside:
            return None

        adx = ind.adx(bars, period=14)
        entry = bar.close
        if bar.high >= vah:
            stop = max(bar.high + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            target = poc
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
            return Signal(
                side=Side.SHORT,
                stop_price=stop,
                target_price=target,
                reason=f"faded VAH {vah:.2f} toward POC {poc:.2f} (balance day, ADX {adx:.0f})",
            )
        if bar.low <= val:
            stop = min(bar.low - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            target = poc
            return Signal(
                side=Side.LONG,
                stop_price=stop,
                target_price=target,
                reason=f"faded VAL {val:.2f} toward POC {poc:.2f} (balance day, ADX {adx:.0f})",
            )
        return None
