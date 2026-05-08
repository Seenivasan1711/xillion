"""
Example strategy: Simple Moving Average crossover.

Buy when fast SMA crosses above slow SMA.
Sell when fast SMA crosses below slow SMA.

Works identically in backtest, paper, and live modes.
No broker imports. No mode-checking code. Just signal logic.
"""
from decimal import Decimal

from xillion.core.events import Bar
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext


class SMACrossStrategy(Strategy):
    name = "SMA Cross"
    version = "1.0.0"
    description = "Buy on fast SMA crossing slow SMA from below; sell on the reverse."
    author = "xillion"
    timeframe = "15m"

    params_schema = [
        ParamSpec("fast", "int", default=10, min=2, max=200,
                  description="Fast SMA period"),
        ParamSpec("slow", "int", default=30, min=5, max=500,
                  description="Slow SMA period"),
        ParamSpec("qty", "int", default=1, min=1,
                  description="Quantity per trade"),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("position", "flat")
        ctx.log(
            "info", "SMA Cross started",
            fast=ctx.params["fast"],
            slow=ctx.params["slow"],
        )

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        slow = ctx.params["slow"]
        fast = ctx.params["fast"]
        qty = ctx.params["qty"]

        bars = await ctx.history(bar.symbol, self.timeframe, lookback=slow + 2)
        if len(bars) < slow + 1:
            return  # not enough data yet

        closes = [float(b.close) for b in bars]
        fast_now = sum(closes[-fast:]) / fast
        slow_now = sum(closes[-slow:]) / slow
        fast_prev = sum(closes[-fast - 1:-1]) / fast
        slow_prev = sum(closes[-slow - 1:-1]) / slow

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        pos = ctx.position(bar.symbol)
        is_flat = pos is None or pos.quantity == 0

        if crossed_up and is_flat:
            await ctx.buy(bar.symbol, qty, tag="sma_cross_entry")
            ctx.state["position"] = "long"
            ctx.log("info", "BUY signal", fast=round(fast_now, 2), slow=round(slow_now, 2))

        elif crossed_down and pos and pos.quantity > 0:
            await ctx.sell(bar.symbol, pos.quantity, tag="sma_cross_exit")
            ctx.state["position"] = "flat"
            ctx.log("info", "SELL signal", fast=round(fast_now, 2), slow=round(slow_now, 2))

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "SMA Cross stopped", reason=reason)
