"""
Candidate #6: Premium/Discount OTE Fibonacci Retracement. T3 evidence tier
(widely taught, zero backtest evidence found in the original research
pass) -- included to test that claim directly rather than take it on faith.

Deviation from the spec card, disclosed rather than hidden: the spec calls
for an H1 bias EMA and an H1-measured swing leg; this harness feeds native
M1 bars (whatever the real data actually is), and no swing-point primitive
is exposed as a public method on PriceActionSignals for this timeframe, so
the swing leg here is the highest-high/lowest-low pair over a trailing
window on the SAME M1 series the strategy trades on, and the bias EMA is
computed on that M1 series too. This is a faster, noisier proxy for the
card's true H1 mechanics, not the card's exact rule -- flagged in
03_results.md, not swept under the rug.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals

ind = IndicatorSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    swing_window: int = 100
    min_swing_atr_mult: float = 1.5
    ote_low_pct: float = 61.8
    ote_high_pct: float = 79.0
    bias_ema_period: int = 50
    target_r_mult: float = 1.0


class OteFibRetracementStrategy:
    name = "Premium/Discount OTE Fibonacci Retracement"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(max(self.p.swing_window + 20, self.p.bias_ema_period + 5))
        if len(bars) < self.p.swing_window:
            return None

        atr = ind.atr(bars, period=14)
        if atr <= 0:
            return None

        window = bars[-self.p.swing_window :]
        high_idx = max(range(len(window)), key=lambda i: window[i].high)
        low_idx = min(range(len(window)), key=lambda i: window[i].low)
        swing_high = window[high_idx].high
        swing_low = window[low_idx].low
        swing_range = swing_high - swing_low
        if swing_range < self.p.min_swing_atr_mult * atr:
            return None

        ema_now = ind.ema(bars, self.p.bias_ema_period)
        ema_prior = ind.ema(bars[:-5], self.p.bias_ema_period) if len(bars) > 5 else ema_now
        bias_up = ema_now > ema_prior
        bias_down = ema_now < ema_prior

        zone_lo = self.p.ote_low_pct / 100.0
        zone_hi = self.p.ote_high_pct / 100.0

        if low_idx < high_idx and bias_up:
            # bullish leg (low then high); OTE = pullback zone below the high
            level_shallow = swing_high - zone_lo * swing_range
            level_deep = swing_high - zone_hi * swing_range
            in_zone = level_deep <= bar.close <= level_shallow
            reversing = bar.close > bar.open
            if in_zone and reversing:
                entry = bar.close
                stop = min(level_deep - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
                target = swing_high + self.p.target_r_mult * swing_range
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
                return Signal(
                    side=Side.LONG,
                    stop_price=stop,
                    target_price=target,
                    reason=f"OTE pullback into {level_deep:.2f}-{level_shallow:.2f} of bullish {swing_low:.2f}-{swing_high:.2f} leg",
                )

        if high_idx < low_idx and bias_down:
            # bearish leg (high then low); OTE = pullback zone above the low
            level_shallow = swing_low + zone_lo * swing_range
            level_deep = swing_low + zone_hi * swing_range
            in_zone = level_shallow <= bar.close <= level_deep
            reversing = bar.close < bar.open
            if in_zone and reversing:
                entry = bar.close
                stop = max(level_deep + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
                target = swing_low - self.p.target_r_mult * swing_range
                return Signal(
                    side=Side.SHORT,
                    stop_price=stop,
                    target_price=target,
                    reason=f"OTE pullback into {level_shallow:.2f}-{level_deep:.2f} of bearish {swing_high:.2f}-{swing_low:.2f} leg",
                )
        return None
