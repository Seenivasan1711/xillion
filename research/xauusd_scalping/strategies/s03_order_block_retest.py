"""
Candidate #3: Order Block Retest After BOS. Composes
PriceActionSignals.break_of_structure -> .order_block_zone; entry on the
retest touch itself (order_block_zone's own `fired` flag), no extra pending
state machine needed since both checks are pure functions of the same bar
window.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, PriceActionSignals
from signals.risk_floor import apply_floor

pa = PriceActionSignals()
ind = IndicatorSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    swing_lookback: int = 3
    decisive_atr_mult: float = 0.3
    target_r_mult: float = 2.0  # x distance from entry to the BOS swing point


class OrderBlockRetestStrategy:
    name = "Order Block Retest After BOS"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._bos_cache = None  # holds the most recent BOS awaiting a retest

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(500)
        if len(bars) < 30:
            return None

        atr = ind.atr(bars, period=14)
        if atr <= 0:
            return None

        if self._bos_cache is not None:
            ob = pa.order_block_zone(bars, self._bos_cache)
            if ob.fired:
                return self._fire_entry(bar, ob, self._bos_cache)
            # give up on a stale BOS after it's clearly run away without a retest
            if len(bars) - 1 - (self._bos_cache.order_block_bar_index or 0) > 100:
                self._bos_cache = None

        bos = pa.break_of_structure(
            bars, atr_value=atr, swing_lookback=self.p.swing_lookback, decisive_atr_mult=self.p.decisive_atr_mult
        )
        if bos.fired and bos.order_block_bar_index is not None:
            self._bos_cache = bos
        return None

    def _fire_entry(self, bar: Bar, ob, bos) -> Signal:
        side = Side.LONG if bos.direction == Direction.UP else Side.SHORT
        entry = bar.close
        if side == Side.LONG:
            stop = min(ob.zone_low - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            dist_to_bos = abs(entry - bos.swing_broken_price)
            target = entry + self.p.target_r_mult * dist_to_bos
        else:
            stop = max(ob.zone_high + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            dist_to_bos = abs(entry - bos.swing_broken_price)
            target = entry - self.p.target_r_mult * dist_to_bos
        reason = f"BOS beyond {bos.swing_broken_price:.2f}, order block retest {ob.zone_low:.2f}-{ob.zone_high:.2f}"
        self._bos_cache = None
        stop, target = apply_floor(entry, stop, target, side)
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
