"""
Candidate #2: Multi-Timeframe Liquidity Alignment (HTF Pool + LTF CHoCH).
Daily equal-highs/lows (a liquidity pool) get swept, then an LTF
change-of-character confirms before entry -- composes
PriceActionSignals.equal_highs_lows (on resampled daily bars) ->
.liquidity_sweep -> .change_of_character (on the native intraday bars).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, PriceActionSignals

from ._common import daily_bars_from_m1

pa = PriceActionSignals()
ind = IndicatorSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    equal_level_tolerance_pct: float = 0.15
    htf_lookback_days: int = 10
    choch_swing_lookback: int = 3
    daily_swing_lookback: int = 2  # smaller than a typical fractal window -- sparse daily history


@dataclass
class _Pending:
    level_price: float
    level_is_high: bool
    extreme: float


class MtfLiquidityChochStrategy:
    name = "Multi-Timeframe Liquidity Alignment (HTF Pool + LTF CHoCH)"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._pending: _Pending | None = None

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        # 3000 M1 bars (~2 trading days) could never reach the 5 daily bars
        # the swing check below needs, let alone a real htf_lookback_days=10
        # window -- found 2026-09-23 once 6.5 months of real continuous data
        # still produced zero signals, ruling out "dataset too short" as the
        # cause. 25000 bars (~17 trading days on a 24/5 market) gives margin
        # above the 10-day HTF lookback even with thin/holiday days mixed in.
        bars = ctx.bars(25000)
        if len(bars) < 30:
            return None

        if self._pending is not None:
            choch = pa.change_of_character(bars, swing_lookback=self.p.choch_swing_lookback)
            expected = Direction.DOWN if self._pending.level_is_high else Direction.UP
            if choch.fired and choch.direction == expected:
                return self._fire_entry(bar, self._pending)
            # void the setup if too many bars have passed without CHoCH
            self._pending = None

        daily = daily_bars_from_m1(bars)
        if len(daily) < 2 * self.p.daily_swing_lookback + 1:
            return None
        pools = pa.equal_highs_lows(
            daily,
            tolerance_pct=self.p.equal_level_tolerance_pct,
            lookback=self.p.htf_lookback_days,
            swing_lookback=self.p.daily_swing_lookback,
        )
        for pool in pools:
            sweep = pa.liquidity_sweep(bars, level_price=pool.level_price, level_is_high=pool.is_high)
            if sweep.fired:
                self._pending = _Pending(
                    level_price=pool.level_price, level_is_high=pool.is_high, extreme=sweep.extreme_price
                )
                break
        return None

    def _fire_entry(self, bar: Bar, pend: _Pending) -> Signal:
        side = Side.LONG if not pend.level_is_high else Side.SHORT
        entry = bar.close
        if pend.level_is_high:
            stop = max(pend.extreme + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            target = entry - 2 * abs(entry - stop)
        else:
            stop = min(pend.extreme - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            target = entry + 2 * abs(entry - stop)
        reason = f"HTF pool {pend.level_price:.2f} swept to {pend.extreme:.2f}, LTF CHoCH confirmed at {entry:.2f}"
        self._pending = None
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
