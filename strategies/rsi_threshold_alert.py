"""
Generic RSI-threshold strategy: buy when RSI crosses above a threshold,
sell when RSI crosses below one -- entirely UI-configurable, no code changes
needed per setup. Works for any instrument (set at instance-creation time,
not hardcoded here) and any asset class the platform already supports.

Works identically in backtest, paper, live, and alert modes. No broker
imports. No mode-checking code. Just signal logic -- same pattern as
example_sma_cross.py and nifty_spot_alert.py.
"""
from xillion.core.events import Bar
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext


def _rsi(closes: list[float], period: int) -> float:
    """Simple (non-Wilder) RSI over the last `period` changes in `closes`."""
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


class RSIThresholdStrategy(Strategy):
    name = "RSI Threshold"
    version = "1.0.0"
    description = "Buy on RSI crossing above a threshold; sell on crossing below."
    author = "xillion"
    timeframe = "15m"

    params_schema = [
        ParamSpec("period", "int", default=14, min=2, max=200,
                  description="RSI lookback period"),
        ParamSpec("threshold", "float", default=70.0, min=0, max=100,
                  description="RSI level to watch for a cross"),
        ParamSpec("direction", "choice", default="above", choices=["above", "below"],
                  description="Buy when RSI crosses above (momentum), or sell when it crosses below (reversal)"),
        ParamSpec("qty", "int", default=1, min=1,
                  description="Quantity per trade"),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("position", "flat")
        ctx.log(
            "info", "RSI Threshold started",
            period=ctx.params["period"],
            threshold=ctx.params["threshold"],
            direction=ctx.params["direction"],
        )

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        period = ctx.params["period"]
        threshold = ctx.params["threshold"]
        direction = ctx.params["direction"]
        qty = ctx.params["qty"]

        bars = await ctx.history(bar.symbol, bar.timeframe, lookback=period + 2)
        if len(bars) < period + 2:
            return  # not enough data yet

        closes = [float(b.close) for b in bars]
        rsi_now = _rsi(closes[-(period + 1):], period)
        rsi_prev = _rsi(closes[-(period + 2):-1], period)

        crossed_above = rsi_prev <= threshold and rsi_now > threshold
        crossed_below = rsi_prev >= threshold and rsi_now < threshold

        pos = ctx.position(bar.symbol)
        is_flat = pos is None or pos.quantity == 0

        if direction == "above" and crossed_above and is_flat:
            await ctx.buy(bar.symbol, qty, tag="rsi_threshold_entry")
            ctx.state["position"] = "long"
            ctx.log("info", "BUY signal", rsi=round(rsi_now, 2), threshold=threshold)

        elif direction == "below" and crossed_below and pos and pos.quantity > 0:
            await ctx.sell(bar.symbol, pos.quantity, tag="rsi_threshold_exit")
            ctx.state["position"] = "flat"
            ctx.log("info", "SELL signal", rsi=round(rsi_now, 2), threshold=threshold)

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "RSI Threshold stopped", reason=reason)
