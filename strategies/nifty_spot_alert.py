"""
Placeholder validation strategy: alerts when the configured symbol's spot
price crosses a level. This is the build spec's own suggested placeholder --
"until the real strategy rules are provided, implement a trivial strategy so
the full pipeline can be tested end to end" -- and validates alert mode
without needing options resolution (resolve_strike/subscribe_instrument) at
all: it only needs spot ticks, which already flow through the existing
static-instruments subscription path.

Works identically in backtest, paper, and alert modes. No broker imports.
No mode-checking code. Just signal logic.
"""

from decimal import Decimal

from xillion.core.events import Tick
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext


class NiftySpotAlertStrategy(Strategy):
    name = "Nifty Spot Alert"
    version = "1.0.0"
    description = "Alerts when the configured symbol's spot price crosses a level."
    author = "xillion"
    timeframe = "1m"
    instruments = ["NIFTY 50"]

    params_schema = [
        ParamSpec(
            "level", "float", default=25000.0, description="Price level to watch for a cross"
        ),
        ParamSpec(
            "direction",
            "choice",
            default="above",
            choices=["above", "below"],
            description="Alert when price crosses above or below the level",
        ),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("side", None)  # "above" | "below" | None (unknown yet)
        ctx.log(
            "info",
            "Nifty Spot Alert started",
            watch_level=ctx.params["level"],
            direction=ctx.params["direction"],
        )

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        level = Decimal(str(ctx.params["level"]))
        direction = ctx.params["direction"]

        current_side = "above" if tick.ltp >= level else "below"
        prev_side = ctx.state.get("side")
        ctx.state["side"] = current_side

        if prev_side is None or prev_side == current_side:
            return  # no cross yet, or this is the first tick (establishing baseline)
        if current_side != direction:
            return  # crossed, but not the direction we're watching for

        if direction == "above":
            await ctx.buy(tick.symbol, 1, tag="spot_level_cross")
        else:
            await ctx.sell(tick.symbol, 1, tag="spot_level_cross")
        ctx.log(
            "info",
            "level cross alert",
            direction=direction,
            watch_level=str(level),
            ltp=str(tick.ltp),
        )

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "Nifty Spot Alert stopped", reason=reason)
