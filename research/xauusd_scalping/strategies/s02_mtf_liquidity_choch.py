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
from signals.risk_floor import apply_floor

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
        bars = ctx.bars(3000)
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
        stop, target = apply_floor(entry, stop, target, side)
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
