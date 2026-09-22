"""
Candidate #1 (01_shortlist_v2.md): Liquidity Sweep + Displacement + FVG
Retest. Composes PriceActionSignals.liquidity_sweep -> .displacement_candle
-> .fair_value_gap -> .fvg_retest; confidence from IndicatorSignals.atr +
.rsi_divergence. Differs from the falsified gold_sweep_reversal.py rule via
the displacement + FVG-retest requirement and an opposing-liquidity target
instead of a fixed point value -- see the spec card for the full argument.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.confidence import ConfidenceComponent, ConfidenceScorer
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, FVGResult, PriceActionSignals
from signals.risk_floor import apply_floor

from ._common import session_levels

pa = PriceActionSignals()
ind = IndicatorSignals()
scorer = ConfidenceScorer()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    displacement_body_mult: float = 1.5
    displacement_close_pct: float = 25.0
    enable_confidence_score: bool = False


@dataclass
class _Pending:
    level_name: str
    level_price: float
    level_is_high: bool
    extreme: float
    stage: str = "awaiting_displacement"  # -> "awaiting_retest" once displacement confirms
    fvg_low: float = 0.0
    fvg_high: float = 0.0


class LiquiditySweepFvgStrategy:
    name = "Liquidity Sweep + Displacement + FVG Retest"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._pending: _Pending | None = None

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        bars = ctx.bars(500)
        if ctx.has_open_position or len(bars) < 30:
            return None

        levels = session_levels(bars, bar.ts)
        if not levels:
            return None

        # ── Advance a pending setup first ──
        if self._pending is not None:
            pend = self._pending
            if pend.stage == "awaiting_displacement":
                disp = pa.displacement_candle(
                    bars,
                    body_mult=self.p.displacement_body_mult,
                    close_pct_threshold=self.p.displacement_close_pct,
                    direction=Direction.DOWN if pend.level_is_high else Direction.UP,
                )
                if disp.fired:
                    fvg = pa.fair_value_gap(bars)
                    if fvg.fired:
                        pend.stage = "awaiting_retest"
                        pend.fvg_low, pend.fvg_high = fvg.gap_low, fvg.gap_high
                    else:
                        self._pending = None  # no gap formed -- setup void
                else:
                    self._pending = None  # displacement didn't confirm within one bar -- void
            elif pend.stage == "awaiting_retest":
                fvg_result = FVGResult(fired=True, gap_low=pend.fvg_low, gap_high=pend.fvg_high)
                if pa.fvg_retest(bars, fvg_result):
                    return self._fire_entry(bar, ctx, pend, levels)
                # invalidation: fully filled through without triggering
                if (pend.level_is_high and bar.close < pend.fvg_low) or (
                    not pend.level_is_high and bar.close > pend.fvg_high
                ):
                    self._pending = None

        if self._pending is not None:
            return None

        # ── Look for a fresh sweep ──
        for name, price in levels.items():
            is_high = "high" in name
            sweep = pa.liquidity_sweep(bars, level_price=price, level_is_high=is_high)
            if sweep.fired:
                self._pending = _Pending(
                    level_name=name, level_price=price, level_is_high=is_high, extreme=sweep.extreme_price
                )
                break
        return None

    def _fire_entry(self, bar: Bar, ctx, pend: _Pending, levels: dict[str, float]) -> Signal:
        side = Side.LONG if not pend.level_is_high else Side.SHORT
        entry = bar.close
        if pend.level_is_high:
            stop = max(pend.extreme + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
        else:
            stop = min(pend.extreme - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)

        opposing = [v for k, v in levels.items() if ("high" in k) != pend.level_is_high]
        if opposing:
            target = min(opposing) if side == Side.LONG else max(opposing)
        else:
            target = entry + 7.5 if side == Side.LONG else entry - 7.5  # fallback if no opposing level marked

        reason = f"Swept {pend.level_name} at {pend.extreme:.2f}, displacement + FVG retest at {entry:.2f}"
        if self.p.enable_confidence_score:
            bars = ctx.bars(200)
            atr = ind.atr(bars)
            sweep_depth_atr = abs(pend.extreme - pend.level_price) / atr if atr > 0 else 0.0
            depth_score = min(100.0, sweep_depth_atr * 50)
            components = [
                ConfidenceComponent("sweep_depth_atr", depth_score, weight=1.0, reason=f"sweep depth {sweep_depth_atr:.2f}x ATR"),
            ]
            conf = scorer.score(components)
            reason += f" | confidence {conf.score}/100 ({'; '.join(conf.reasons)})"

        self._pending = None
        stop, target = apply_floor(entry, stop, target, side)
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
