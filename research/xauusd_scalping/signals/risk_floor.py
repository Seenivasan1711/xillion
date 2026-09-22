"""
Shared stop/target floor, factored out after 03_results.md's first real
backtest run found 5 of the 10 strategies losing on effectively every
trade. Root cause: each strategy computed its stop/target off the raw
bar.close it observed, using a `min_sl_pts=3.0` floor that was never
checked against the cost model living one file over in
`engine/cost_model.py` -- the engine's own worst-typical round-trip cost
(spread/2 + entry slippage, then spread/2 + exit slippage again) is
~27-108 points depending on session/vol bucket, dwarfing a 3-point stop
and frequently exceeding a small structural target too, so the "target"
ended up on the losing side of the actual fill before the trade was even
placed.

This is a floor, not a retune: it only WIDENS a stop/target that's
already narrower than a realistic cost-clearing distance, and never
shrinks a strategy's own structural level when that level is already
wide enough. min_sl_pts=40 and min_target_pts=80 are read directly off
cost_model.py's own spread table (DEAD_ZONE/MEDIUM round-trip ~68pts,
DEAD_ZONE/HIGH ~108pts) with headroom for a 2:1 R:R baseline -- not
chosen to make any particular backtest number look better, and it does
not guarantee a positive result (see 03_results.md v2 for the honest
outcome).
"""

from __future__ import annotations

from engine.backtest_engine import Side


def apply_floor(
    entry: float,
    stop: float,
    target: float,
    side: Side,
    min_sl_pts: float = 40.0,
    min_target_pts: float = 80.0,
) -> tuple[float, float]:
    """Widens `stop`/`target` outward (away from entry) if either is
    closer to entry than the given floor, in the direction implied by
    `side`. Never moves a level that's already past the floor."""
    if side == Side.LONG:
        stop = min(stop, entry - min_sl_pts)
        target = max(target, entry + min_target_pts)
    else:
        stop = max(stop, entry + min_sl_pts)
        target = min(target, entry - min_target_pts)
    return stop, target
