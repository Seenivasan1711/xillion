"""
Generic condition-based strategy (CP5 Strategy Builder): entry and exit are
each a list of metric/operator/threshold conditions (ANDed together), fed in
as JSON params -- so a new setup is a UI form submission, not a new Python
file. See xillion/engine/condition.py for the condition schema and
xillion/engine/indicators.py for the metric library (SMA, EMA, RSI, ATR,
VWAP, Bollinger, MACD, Supertrend).

Works identically in backtest, paper, live, and alert modes -- same pattern
as every other strategy file here. No broker imports, no mode-checking code.
"""

from xillion.core.events import Bar
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext
from xillion.engine.condition import evaluate_all


class ConditionStrategy(Strategy):
    name = "Condition Strategy"
    version = "1.0.0"
    description = (
        "Entry and exit rules built from metric/operator/threshold conditions "
        "-- no code needed per setup. Long or short, any of the standard indicators."
    )
    author = "xillion"
    timeframe = "15m"

    params_schema = [
        ParamSpec(
            "entry_conditions",
            "condition_list",
            default=[],
            description="ALL must be true to enter (AND)",
        ),
        ParamSpec(
            "exit_conditions",
            "condition_list",
            default=[],
            description="ALL must be true to exit (AND) -- only checked while in a position",
        ),
        ParamSpec(
            "direction",
            "choice",
            default="long",
            choices=["long", "short"],
            description="long: buy to enter, sell to exit. short: sell to enter, buy to exit",
        ),
        ParamSpec("qty", "int", default=1, min=1, description="Quantity per trade"),
        ParamSpec(
            "lookback",
            "int",
            default=100,
            min=10,
            max=1000,
            description="Bars of history fetched per evaluation -- must cover the largest indicator period used",
        ),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.log(
            "info",
            "Condition Strategy started",
            direction=ctx.params["direction"],
            entry_conditions=len(ctx.params["entry_conditions"]),
            exit_conditions=len(ctx.params["exit_conditions"]),
        )

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        entry_conditions = ctx.params["entry_conditions"]
        exit_conditions = ctx.params["exit_conditions"]
        direction = ctx.params["direction"]
        qty = ctx.params["qty"]
        lookback = ctx.params["lookback"]

        # ctx.history() returns bars strictly BEFORE this one (see
        # _BacktestContext.history()'s `b.ts < as_of` filter) -- append the
        # current bar so a condition's "close" means the price this bar just
        # closed at, not the previous bar's. Every indicator here is a
        # function of the full window handed to it, so this is enough;
        # nothing needs a separate "current price" argument.
        bars = await ctx.history(bar.symbol, bar.timeframe, lookback=lookback)
        bars = [*bars, bar]

        pos = ctx.position(bar.symbol)
        is_flat = pos is None or pos.quantity == 0

        if is_flat:
            if evaluate_all(entry_conditions, bars):
                if direction == "long":
                    await ctx.buy(bar.symbol, qty, tag="condition_entry")
                else:
                    await ctx.sell(bar.symbol, qty, tag="condition_entry")
                ctx.log("info", "entry signal", direction=direction, symbol=bar.symbol)
        else:
            if evaluate_all(exit_conditions, bars):
                exit_qty = abs(pos.quantity)
                if direction == "long":
                    await ctx.sell(bar.symbol, exit_qty, tag="condition_exit")
                else:
                    await ctx.buy(bar.symbol, exit_qty, tag="condition_exit")
                ctx.log("info", "exit signal", direction=direction, symbol=bar.symbol)

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "Condition Strategy stopped", reason=reason)
