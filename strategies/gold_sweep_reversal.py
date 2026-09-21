"""
Gold Sweep-Reversal -- session-liquidity-sweep fade on XAUUSD.

Full rules: docs/strategies/gold-xauusd-sweep-reversal.md. Runs ALERT MODE
ONLY -- a Telegram notification with full reasoning (via ctx.alert_entry's
`reason`), no order placement. Live data comes from
brokers/twelve_data_feed.py (Twelve Data's free intraday feed), not the
Funding Pips MT5 broker -- alert mode needs a price feed, not an execution
path, so there's no Wine/MT5 terminal dependency. See the strategy doc's
Section 7 for the feed-divergence caveat this implies.

Mechanical rules, mechanically applied:
  - 4 daily levels: Asian session high/low (00:00-07:00 UTC by default =
    05:30-12:30 IST) and the previous trading day's high/low (whole
    calendar day, whichever trading day actually has bars -- walks back
    over closed weekends automatically).
  - Only inside the trading window (07:00-13:00 UTC by default =
    12:30-18:30 IST).
  - Trigger: price trades beyond a line (a "sweep"), the very next M5
    candle closes back inside it -> enter at that close, opposite the
    sweep direction (fade).
  - SL: sl_buffer_pts beyond the sweep's wick extreme, minimum min_sl_pts
    (whichever is further from entry).
  - TP: fixed tp_pts.
  - Max max_trades_per_day ENTER alerts/day, with a cooldown_minutes gap
    after any entry -- the card's own FundingPips-rule mapping ("10-min
    same-direction grouping rule -- handled by 'never re-enter'").

Known, stated simplifications vs. the reference backtest
(scripts/gold_sweep_backtest.py) -- see the strategy doc's Section 7 for
the full writeup, not hidden here:
  - Session-level marking uses M5 bars (this feed's only granularity), not
    M1 -- slightly coarser wick precision on the 4 lines than the
    backtest's M1-derived levels.
  - No real position is tracked (alert-only) -- "max trades/day" is a pure
    count plus a cooldown, not "wait for the open trade to actually
    resolve" the way the backtest's busy_until models a real single-
    position account. In practice the user only ever holds one real
    position at a time; this doesn't try to simulate that.
  - Spread filter (the card's "skip if spread > 0.30") is NOT applied --
    Twelve Data's time_series endpoint returns OHLC only, no bid/ask, so
    there's no spread figure available to check.
  - News veto (no entry within 15 min of a red-folder USD release) is a
    stub, `_news_veto_active` below, until the Finnhub ritual check (G3)
    is wired -- always returns False (never vetoes) rather than silently
    pretending to check something real.
  - On a freshly started instance, `ctx.history()` only has whatever bars
    have accumulated live in memory (see xillion/data/history.py) plus
    whatever's in the DB warehouse for this symbol/exchange, which is
    unverified for XAUUSD/Twelve Data in this repo -- the first day or
    two of running may have incomplete daily levels (fewer than 4 lines)
    until enough live M5 bars have actually been seen. Logged, not
    silently guessed at.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from xillion.core.events import Bar, Side
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext

_LEVEL_ASIAN_HIGH = "Asian High"
_LEVEL_ASIAN_LOW = "Asian Low"
_LEVEL_PD_HIGH = "PD High"
_LEVEL_PD_LOW = "PD Low"

# How far back _roll_day looks for real (already-traded) bars -- 700 M5
# bars is ~58 hours of actual market time, comfortably covering a Monday's
# "previous day" reaching back through a closed weekend to Friday, since
# history() only returns bars that actually traded (no bars during a
# closed weekend consume any of this budget).
_LEVEL_LOOKBACK_BARS = 700
_PREV_DAY_SEARCH_DAYS = 5


def _news_veto_active(ctx: StrategyContext) -> bool:
    """Stub for the news/econ-calendar ritual check (G3, Finnhub) -- not
    wired yet. Always False (no veto) rather than silently pretending to
    check something real. See the strategy doc's Section 7."""
    return False


def _cooldown_active(ctx: StrategyContext, bar: Bar) -> bool:
    cooldown_until = ctx.state.get("cooldown_until")
    return bool(cooldown_until) and bar.ts.isoformat() < cooldown_until


class GoldSweepReversal(Strategy):
    name = "Gold Sweep-Reversal"
    version = "1.0.0"
    description = (
        "XAUUSD session-liquidity-sweep fade, alert-only. Sweeps of the Asian "
        "high/low or previous-day high/low, faded on an M5 close back inside, "
        "trading-window only. See docs/strategies/gold-xauusd-sweep-reversal.md."
    )
    author = "Rakesh"
    timeframe = "5m"
    instruments = ["XAUUSD"]

    params_schema = [
        ParamSpec(
            "tp_pts",
            "float",
            default=7.5,
            min=1.0,
            max=50.0,
            description="Fixed take-profit, in points",
        ),
        ParamSpec(
            "min_sl_pts",
            "float",
            default=3.0,
            min=0.5,
            max=20.0,
            description="Minimum stop-loss distance, in points",
        ),
        ParamSpec(
            "sl_buffer_pts",
            "float",
            default=0.5,
            min=0.0,
            max=5.0,
            description="Buffer beyond the sweep's wick extreme for the stop",
        ),
        ParamSpec(
            "max_trades_per_day",
            "int",
            default=2,
            min=1,
            max=10,
            description="Max ENTER alerts per day",
        ),
        ParamSpec(
            "cooldown_minutes",
            "int",
            default=10,
            min=0,
            max=120,
            description="Minimum gap after any ENTER before the next one",
        ),
        ParamSpec(
            "sweep_lookback_bars",
            "int",
            default=3,
            min=1,
            max=20,
            description="How many M5 bars a sweep stays 'live' waiting for the reclaim close",
        ),
        ParamSpec(
            "session_start_utc_hour",
            "float",
            default=7.0,
            min=0.0,
            max=23.5,
            description="Trading window start, UTC hour (7.0 = 12:30 IST)",
        ),
        ParamSpec(
            "session_end_utc_hour",
            "float",
            default=13.0,
            min=0.0,
            max=24.0,
            description="Trading window end, UTC hour (13.0 = 18:30 IST)",
        ),
        ParamSpec(
            "asian_start_utc_hour",
            "float",
            default=0.0,
            min=0.0,
            max=23.5,
            description="Asian session start, UTC hour (0.0 = 05:30 IST)",
        ),
        ParamSpec(
            "asian_end_utc_hour",
            "float",
            default=7.0,
            min=0.0,
            max=24.0,
            description="Asian session end, UTC hour (7.0 = 12:30 IST)",
        ),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("trade_date", None)  # UTC date (ISO) of the last daily reset
        ctx.state.setdefault("trades_today", 0)
        ctx.state.setdefault("levels", {})  # name -> {"price": float, "kind": "res"|"sup"}
        ctx.state.setdefault("pending", {})  # name -> {"bar_index": int, "extreme": float}
        ctx.state.setdefault("bar_index", 0)
        ctx.state.setdefault("cooldown_until", None)  # ISO timestamp string
        ctx.log("info", f"{self.name} started (alert mode)", params=ctx.params)

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        # Use bar.timeframe, not self.timeframe -- a hardcoded-timeframe
        # check here has silently produced 0-trade backtests before.
        if bar.timeframe != self.timeframe:
            return

        p = ctx.params
        bar_date = bar.ts.date().isoformat()
        hour = bar.ts.hour + bar.ts.minute / 60.0

        if ctx.state.get("trade_date") != bar_date:
            await self._roll_day(bar, ctx, bar_date)

        ctx.state["bar_index"] = ctx.state.get("bar_index", 0) + 1
        bar_index = ctx.state["bar_index"]

        if not (p["session_start_utc_hour"] <= hour < p["session_end_utc_hour"]):
            return  # outside the trading window: no observation, no trade

        levels: dict = ctx.state.get("levels") or {}
        if not levels:
            return  # no daily levels yet -- see the module docstring's bootstrap caveat

        # Gates below suppress FIRING a new entry, not the underlying sweep/
        # reclaim tracking -- price still sweeps and reclaims levels during a
        # cooldown, and that pending state must survive to be evaluated once
        # the cooldown clears, rather than being silently dropped (found via
        # testing: gating the whole loop on these caused a bar right at the
        # cooldown boundary to look like a fresh one-bar sweep+reclaim
        # instead of continuing a sweep that started during the cooldown).
        can_fire = (
            ctx.state["trades_today"] < p["max_trades_per_day"]
            and not _cooldown_active(ctx, bar)
            and not _news_veto_active(ctx)
        )

        pending: dict = ctx.state.setdefault("pending", {})
        for level_name, level in levels.items():
            price = level["price"]
            kind = level["kind"]
            poked = float(bar.high) > price if kind == "res" else float(bar.low) < price
            closed_inside = float(bar.close) < price if kind == "res" else float(bar.close) > price

            if poked:
                extreme = float(bar.high) if kind == "res" else float(bar.low)
                prior = pending.get(level_name)
                if prior is None:
                    pending[level_name] = {"bar_index": bar_index, "extreme": extreme}
                else:
                    new_extreme = (
                        max(prior["extreme"], extreme)
                        if kind == "res"
                        else min(prior["extreme"], extreme)
                    )
                    pending[level_name] = {"bar_index": prior["bar_index"], "extreme": new_extreme}

            live = pending.get(level_name)
            if live is None:
                continue
            if bar_index - live["bar_index"] > p["sweep_lookback_bars"]:
                pending.pop(level_name, None)
                continue
            if not closed_inside:
                continue

            pending.pop(level_name, None)
            if can_fire:
                await self._fire_entry(bar, ctx, level_name, kind, live["extreme"])
                break  # one trigger per bar -- matches the reference backtest's behaviour

    async def _roll_day(self, bar: Bar, ctx: StrategyContext, bar_date: str) -> None:
        ctx.state["trade_date"] = bar_date
        ctx.state["trades_today"] = 0
        ctx.state["pending"] = {}
        ctx.state["cooldown_until"] = None

        p = ctx.params
        history = await ctx.history(bar.symbol, bar.timeframe, lookback=_LEVEL_LOOKBACK_BARS)
        if not history:
            ctx.state["levels"] = {}
            ctx.log("warning", "no history available yet for daily levels", date=bar_date)
            return

        today = bar.ts.date()

        def _hour(b: Bar) -> float:
            return b.ts.hour + b.ts.minute / 60.0

        asian_bars = [
            b
            for b in history
            if b.ts.date() == today
            and p["asian_start_utc_hour"] <= _hour(b) < p["asian_end_utc_hour"]
        ]

        # Previous trading day -- whole calendar day, walking back from
        # yesterday until one with bars is found, so a Monday reaches back
        # through the closed weekend to Friday instead of finding nothing.
        prev_day_bars: list[Bar] = []
        probe = today - timedelta(days=1)
        for _ in range(_PREV_DAY_SEARCH_DAYS):
            candidates = [b for b in history if b.ts.date() == probe]
            if candidates:
                prev_day_bars = candidates
                break
            probe -= timedelta(days=1)

        levels: dict[str, dict] = {}
        if asian_bars:
            levels[_LEVEL_ASIAN_HIGH] = {
                "price": float(max(b.high for b in asian_bars)),
                "kind": "res",
            }
            levels[_LEVEL_ASIAN_LOW] = {
                "price": float(min(b.low for b in asian_bars)),
                "kind": "sup",
            }
        if prev_day_bars:
            levels[_LEVEL_PD_HIGH] = {
                "price": float(max(b.high for b in prev_day_bars)),
                "kind": "res",
            }
            levels[_LEVEL_PD_LOW] = {
                "price": float(min(b.low for b in prev_day_bars)),
                "kind": "sup",
            }

        ctx.state["levels"] = levels
        ctx.log(
            "info",
            "daily levels marked",
            date=bar_date,
            levels={k: v["price"] for k, v in levels.items()},
            missing=4 - len(levels),
        )

    async def _fire_entry(
        self, bar: Bar, ctx: StrategyContext, level_name: str, kind: str, extreme: float
    ) -> None:
        p = ctx.params
        entry = float(bar.close)
        if kind == "res":
            side = Side.SELL
            sl = max(extreme + p["sl_buffer_pts"], entry + p["min_sl_pts"])
            tp = entry - p["tp_pts"]
            direction = "SHORT -- fading the sweep up through resistance"
        else:
            side = Side.BUY
            sl = min(extreme - p["sl_buffer_pts"], entry - p["min_sl_pts"])
            tp = entry + p["tp_pts"]
            direction = "LONG -- fading the sweep down through support"
        sl_pts = abs(sl - entry)
        rr = p["tp_pts"] / sl_pts if sl_pts else 0.0

        trades_today = ctx.state["trades_today"] + 1
        remaining = p["max_trades_per_day"] - trades_today
        progress = (
            f"{remaining} left after this one."
            if remaining > 0
            else "last one allowed today. Two losses today = done, close the platform."
        )
        reason = (
            f"Swept {level_name} at {extreme:.2f}, M5 candle closed back inside at "
            f"{entry:.2f} -- {direction}.\n"
            f"Entry {entry:.2f} | SL {sl:.2f} ({sl_pts:.2f} pts) | "
            f"TP {tp:.2f} ({p['tp_pts']:.1f} pts) | R:R {rr:.2f}:1\n"
            f"Trade {trades_today}/{p['max_trades_per_day']} today -- {progress}\n"
            "Fixed 0.08 lot. Never move the stop. No partials. No re-entry on this line today."
        )

        await ctx.alert_entry(
            bar.symbol,
            side,
            price=Decimal(str(round(entry, 2))),
            target=Decimal(str(round(tp, 2))),
            stop_loss=Decimal(str(round(sl, 2))),
            tag=level_name,
            reason=reason,
        )
        ctx.state["trades_today"] = trades_today
        cooldown_until = bar.ts + timedelta(minutes=p["cooldown_minutes"])
        ctx.state["cooldown_until"] = cooldown_until.isoformat()
        ctx.log(
            "info",
            "sweep-reversal ENTER fired",
            swept_level=level_name,
            side=side.value,
            entry=entry,
            sl=sl,
            tp=tp,
            trades_today=trades_today,
        )
