"""
Candidate #10: Equal Highs/Lows Sweep + RSI Divergence. The one candidate
where an indicator is a HARD GATE rather than an optional confidence
input -- deliberately satisfying "don't skip the indicator work" a
different way than the other 9's confidence-layer treatment. Composes
PriceActionSignals.equal_highs_lows -> .liquidity_sweep ->
IndicatorSignals.rsi_divergence as a required precondition, not a score.

Note on indices: `equal_highs_lows` returns touch_indices relative to its
OWN internal lookback window, not the full bars list -- this module
reconstructs that same window before calling rsi_divergence so the indices
line up (documented here rather than left as a silent assumption).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals
from signals.price_action import PriceActionSignals

pa = PriceActionSignals()
ind = IndicatorSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    tolerance_pct: float = 0.1
    lookback: int = 50
    swing_lookback: int = 3
    rsi_period: int = 14


class EqualLevelsRsiDivergenceStrategy:
    name = "Equal Highs/Lows Sweep + RSI Divergence"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(500)
        if len(bars) < 30:
            return None

        window = bars[-self.p.lookback :] if len(bars) > self.p.lookback else bars
        pools = pa.equal_highs_lows(
            bars, tolerance_pct=self.p.tolerance_pct, lookback=self.p.lookback, swing_lookback=self.p.swing_lookback
        )
        if not pools:
            return None

        for pool in pools:
            sweep = pa.liquidity_sweep(bars, level_price=pool.level_price, level_is_high=pool.is_high)
            if not sweep.fired or not sweep.reclaimed:
                continue

            prior_touch = max(pool.touch_indices)
            current_index = len(window) - 1
            divergence = ind.rsi_divergence(window, prior_touch, current_index, period=self.p.rsi_period)

            # Hard gate: sweeping a high needs BEARISH divergence (RSI lower
            # now than at the prior touch); sweeping a low needs BULLISH
            # divergence (RSI higher now). No divergence -> no trade, full stop.
            gate_passed = divergence < 0 if pool.is_high else divergence > 0
            if not gate_passed:
                continue

            opposite = [p for p in pools if p.is_high != pool.is_high]
            entry = bar.close
            if pool.is_high:
                side = Side.SHORT
                stop = max(sweep.extreme_price + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
                target = min((p.level_price for p in opposite), default=entry - 7.5)
            else:
                side = Side.LONG
                stop = min(sweep.extreme_price - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
                target = max((p.level_price for p in opposite), default=entry + 7.5)

            reason = (
                f"{pool.reason} swept + reclaimed, RSI divergence {divergence:.1f} "
                f"(gate {'bearish' if pool.is_high else 'bullish'} required)"
            )
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
            return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
        return None
