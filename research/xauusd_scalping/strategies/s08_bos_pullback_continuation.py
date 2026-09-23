"""
Candidate #8: Break-of-Structure Pullback Continuation -- the trend-following
counterpart to #2/#3's reversal framing. Composes
PriceActionSignals.break_of_structure -> .order_block_zone (reused purely
to measure the impulse leg's origin, not for its own retest signal) -> a
local pending-pullback state machine tracking the shallow retracement and
its own breakout, per the spec card's continuation-confirmation rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, PriceActionSignals

pa = PriceActionSignals()
ind = IndicatorSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5  # was a bare 0.5 literal in _fire_entry; a param so instruments.py can scale it
    swing_lookback: int = 3
    decisive_atr_mult: float = 0.3
    max_pullback_pct: float = 38.2
    invalidate_pct: float = 61.8
    target_leg_mult: float = 1.0


@dataclass
class _Pending:
    direction: Direction
    impulse_leg: float
    bos_close: float
    extreme_price: float
    extreme_bar_bound: float  # the opposite side of the bar that set the current pullback extreme


class BosPullbackContinuationStrategy:
    name = "Break-of-Structure Pullback Continuation"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._pending: _Pending | None = None

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(500)
        if len(bars) < 30:
            return None

        if self._pending is not None:
            pend = self._pending
            if pend.direction == Direction.UP:
                if bar.low < pend.extreme_price:
                    pend.extreme_price = bar.low
                    pend.extreme_bar_bound = bar.high
                retracement = (pend.bos_close - pend.extreme_price) / pend.impulse_leg * 100.0
                if retracement > self.p.invalidate_pct:
                    self._pending = None
                elif retracement <= self.p.max_pullback_pct and bar.close > pend.extreme_bar_bound:
                    return self._fire_entry(bar, pend)
            else:
                if bar.high > pend.extreme_price:
                    pend.extreme_price = bar.high
                    pend.extreme_bar_bound = bar.low
                retracement = (pend.extreme_price - pend.bos_close) / pend.impulse_leg * 100.0
                if retracement > self.p.invalidate_pct:
                    self._pending = None
                elif retracement <= self.p.max_pullback_pct and bar.close < pend.extreme_bar_bound:
                    return self._fire_entry(bar, pend)
            if self._pending is not None:
                return None

        atr = ind.atr(bars, period=14)
        if atr <= 0:
            return None
        bos = pa.break_of_structure(
            bars, atr_value=atr, swing_lookback=self.p.swing_lookback, decisive_atr_mult=self.p.decisive_atr_mult
        )
        if bos.fired and bos.order_block_bar_index is not None:
            ob = pa.order_block_zone(bars, bos)
            impulse_origin = ob.zone_high if bos.direction == Direction.UP else ob.zone_low
            impulse_leg = abs(bar.close - impulse_origin)
            if impulse_leg > 0:
                self._pending = _Pending(
                    direction=bos.direction,
                    impulse_leg=impulse_leg,
                    bos_close=bar.close,
                    extreme_price=bar.close,
                    extreme_bar_bound=bar.high if bos.direction == Direction.UP else bar.low,
                )
        return None

    def _fire_entry(self, bar: Bar, pend: _Pending) -> Signal:
        entry = bar.close
        if pend.direction == Direction.UP:
            side = Side.LONG
            stop = min(pend.extreme_price - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            target = entry + self.p.target_leg_mult * pend.impulse_leg
        else:
            side = Side.SHORT
            stop = max(pend.extreme_price + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            target = entry - self.p.target_leg_mult * pend.impulse_leg
        reason = f"BOS continuation, {pend.impulse_leg:.2f}pt impulse, pullback broken at {entry:.2f}"
        self._pending = None
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
