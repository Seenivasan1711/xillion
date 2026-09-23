"""
Candidate #9: Session Liquidity Run + Reversal into Opposing Pool. Weakest-
sourced candidate (T3, first-principles reasoning, no specific citation) --
included to actually test that reasoning rather than take it on faith.
Composes PriceActionSignals.liquidity_run (across the same 4 session levels
`_common.session_levels` marks) -> .displacement_candle (the reversal
confirmation) -> targets the nearest untouched opposing-side level.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.price_action import Direction, PriceActionSignals

from ._common import session_levels

pa = PriceActionSignals()


@dataclass
class Params:
    fallback_target_pts: float = 7.5  # was a bare 7.5 literal; a param so instruments.py can scale it
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    min_levels_in_run: int = 2
    displacement_body_mult: float = 1.5
    displacement_close_pct: float = 25.0


class SessionLiquidityRunReversalStrategy:
    name = "Session Liquidity Run + Reversal into Opposing Pool"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None
        bars = ctx.bars(500)
        if len(bars) < 30:
            return None
        levels = session_levels(bars, bar.ts)
        if len(levels) < 2:
            return None

        level_prices = list(levels.values())
        level_is_high = ["high" in k for k in levels]
        run = pa.liquidity_run(bars, level_prices, level_is_high, min_levels_in_run=self.p.min_levels_in_run)
        if not run.fired:
            return None

        reversal_direction = Direction.DOWN if run.direction == Direction.UP else Direction.UP
        disp = pa.displacement_candle(
            bars,
            body_mult=self.p.displacement_body_mult,
            close_pct_threshold=self.p.displacement_close_pct,
            direction=reversal_direction,
        )
        if not disp.fired:
            return None

        entry = bar.close
        untouched_opposite = [
            v
            for k, v in levels.items()
            if ("high" in k) != (run.direction == Direction.UP)
        ]
        if run.direction == Direction.UP:
            side = Side.SHORT
            stop = max(run.final_extreme + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            target = max(untouched_opposite) if untouched_opposite else entry - self.p.fallback_target_pts
        else:
            side = Side.LONG
            stop = min(run.final_extreme - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            target = min(untouched_opposite) if untouched_opposite else entry + self.p.fallback_target_pts

        reason = f"{run.reason}, displacement reversal at {entry:.2f}, targeting opposing pool {target:.2f}"
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
