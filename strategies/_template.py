"""
Strategy template — copy this to start a new strategy.

Steps:
1. cp strategies/_template.py strategies/my_strategy.py
2. Rename MyStrategy class and fill in name/description/params_schema
3. Implement on_bar() (and optionally on_tick / on_order_update / on_start / on_stop)
4. Click "Reload" in the dashboard — your strategy appears in the list
5. Configure an instance: symbol, capital, params → backtest → paper → live

Contract rules:
- Do NOT import any broker modules.
- Do NOT import any xillion internals except events and strategy_base.
- Do NOT spawn threads or processes.
- Access the world exclusively through `ctx`.
"""
from decimal import Decimal
from typing import Optional

from xillion.core.events import Bar, Order, Tick
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext


class MyStrategy(Strategy):
    # ── Metadata ──────────────────────────────────────────────────────────────
    name = "My Strategy"               # Must be unique across all loaded strategies
    version = "0.1.0"
    description = "A brief description of what this strategy does."
    author = "you"
    timeframe = "5m"                   # Default bar timeframe to subscribe to
    instruments = ["NIFTY 50"]         # Default instruments (overridable per instance)

    # ── Parameter schema ──────────────────────────────────────────────────────
    # These drive the config form in the dashboard.
    params_schema = [
        ParamSpec("period", "int", default=14, min=2, max=200,
                  description="Lookback period in bars"),
        ParamSpec("qty", "int", default=1, min=1,
                  description="Quantity per order (lots or shares)"),
    ]

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    async def on_start(self, ctx: StrategyContext) -> None:
        """Called once when this instance starts. Load state, validate params."""
        ctx.state.setdefault("position", "flat")
        ctx.log("info", f"{self.name} started", params=ctx.params)

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        """Main logic. Called when a new bar closes."""
        bars = await ctx.history(bar.symbol, self.timeframe, lookback=ctx.params["period"])
        if len(bars) < ctx.params["period"]:
            return  # warmup period

        # ── Your signal logic goes here ─────────────────────────────────────
        # Example: buy if close > SMA(period)
        closes = [float(b.close) for b in bars]
        sma = sum(closes) / len(closes)
        pos = ctx.position(bar.symbol)

        if float(bar.close) > sma and (pos is None or pos.quantity == 0):
            await ctx.buy(bar.symbol, ctx.params["qty"], tag="entry")
            ctx.state["position"] = "long"

        elif float(bar.close) < sma and pos and pos.quantity > 0:
            await ctx.sell(bar.symbol, pos.quantity, tag="exit")
            ctx.state["position"] = "flat"

    async def on_tick(self, tick, ctx: StrategyContext) -> None:
        """Optional. Override for sub-bar reactivity (e.g. trailing stops)."""

    async def on_order_update(self, order: Order, ctx: StrategyContext) -> None:
        """Called when one of this strategy's orders changes status."""
        ctx.log("info", "order update", order_id=order.client_order_id, status=order.status)

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        """Called on shutdown. ctx.state is auto-persisted after this."""
        ctx.log("info", f"{self.name} stopped", reason=reason)
