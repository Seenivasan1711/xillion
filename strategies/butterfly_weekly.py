"""
Nifty/Sensex weekly long butterfly -- docs/strategies/knowledge-base/06-BAG-
D-DEBIT-AND-EXOTIC.md D1. The third consumer of the multi-leg infrastructure
CP11 built generically, and the first DEBIT structure (credit_spread_weekly.py
and iron_condor_weekly.py are both credit structures) -- 1:2:1 ratio,
equidistant strikes, all one option type: buy 1 lower strike, sell 2 middle
strike, buy 1 upper strike.

**Modeled as 4 legs at 3 distinct strikes, not 3 legs with a 2-lot middle
order.** The middle strike's 2-lot short is split into TWO separate 1-lot
SHORT legs (same symbol, same side, each with its own protects_leg_index --
one pointing at the lower wing, one at the upper wing) rather than a single
Leg with quantity=2*lot_size. This is deliberate, not an execution-cost
oversight: multileg_execution.py's naked-short protocol pairs each SHORT leg
with exactly ONE protecting LONG leg (xillion/core/multileg.py's own
docstring: "protects_leg_index pairing, not a hardcoded 2-leg assumption").
A butterfly's middle short is actually protected by BOTH wings at once -- if
either wing fails on entry, the position is left with a real naked exposure
on that side specifically, which two independently-paired 1-lot legs let the
existing leg-failure protocol reason about correctly, reusing the exact same
generalization the iron condor's independent call/put pairs already proved
out (2026-08-29). The cost is one extra chargeable order versus a combined
2-lot sell; correctness in the failure protocol was judged worth it, same
tradeoff CP11 already made everywhere else in this codebase.

Shares the SAME weekly-cycle conventions as credit_spread_weekly.py and
iron_condor_weekly.py (09:45-10:30 entry window, 15m VWAP+EMA20/EMA50 trend
check) for the same reason those two share them with each other -- one set
of conventions is more valuable than mirroring each KB section's own framing
literally.

**Entry signal, an honest gap:** KB D1's market view is "index pins at a
SPECIFIC level at expiry" -- a narrower claim than "no trend", and real pin
plays are typically built around high-OI round numbers (KB 06 D1's own "Best
use" section), which needs open-interest data this codebase doesn't warehouse
anywhere. This strategy reuses the iron condor's own range-bound/no-trend
signal as the entry gate, and pins the middle strike at the CURRENT ATM
(ctx.get_spot()'s nearest listed strike, strike_offset=0) rather than any
model of where the market is likely to actually settle. That's a genuine
simplification, not a claim of real pin-detection -- flagged here the same
way iron_condor_weekly.py flags its own inherited gaps, not hidden.

**Time stop, deliberately NOT ProtectiveOrderSpec.time_stop_date.** KB D1's
whole edge lives in holding through the expiry DAY itself (Cycle stage
S4-S5, DTE 1-0) -- max profit only exists if the position is still open when
the index pins at expiry. ProtectiveOrderSpec.time_stop_date is date-only
(see protective_orders.py), and check_exit_trigger() fires the instant
current_date >= that date -- if used here with time_stop_date=expiry_date,
it would force-exit at the FIRST tick of the very day the strategy exists to
hold through, defeating the whole structure. So this strategy leaves that
field unset and instead checks its own date+time-of-day gate in on_tick,
mirroring the entry window's own inline IST time handling: force-flatten at
_EXPIRY_DAY_FLATTEN_TIME IST on the expiry date itself, ahead of X02's own
15:15 IST broker-level square-off backstop (CP14) so this strategy's own
careful shorts-first unwind (journal entries, GTT cancellation) runs first
rather than leaving cleanup to X02's blunter broker-level enforcement.
"""

from datetime import date, datetime, time
from decimal import Decimal

from xillion.core.events import Bar, OrderType, Side, Tick
from xillion.core.market_calendar import IST
from xillion.core.multileg import (
    Leg,
    LegRole,
    MultiLegSpec,
    StructureType,
    max_loss_per_lot,
    size_defined_risk_position,
)
from xillion.core.multileg_execution import ExecutionOutcome, MultiLegExecutor
from xillion.core.protective_orders import (
    ProtectiveOrderSpec,
    butterfly_protective_levels,
    butterfly_value,
    check_exit_trigger,
)
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext
from xillion.engine.indicators import ema, vwap

_UNDERLYING_SPOT_SYMBOL = {"NIFTY": "NIFTY 50", "SENSEX": "SENSEX"}
_EXPIRY_DAY_FLATTEN_TIME = time(15, 10)  # ahead of X02's 15:15 IST square-off (CP14)


async def _now_ist(ctx: StrategyContext) -> datetime:
    """Same environment-aware "now" as the other weekly strategies -- see
    credit_spread_weekly.py's own helper for why this must not be a bare
    datetime.now()."""
    return (await ctx.now()).astimezone(IST)


class ButterflyWeeklyStrategy(Strategy):
    name = "Butterfly Weekly"
    version = "1.0.0"
    description = (
        "Nifty/Sensex weekly long butterfly, defined risk (debit-capped), 1:2:1 ratio. "
        "Entered near expiry on a range-bound signal, pinned at ATM. See "
        "docs/strategies/butterfly-weekly.md for the full mechanical rules."
    )
    author = "xillion"
    timeframe = "15m"
    instruments = ["NIFTY 50", "SENSEX"]

    params_schema = [
        ParamSpec(
            "underlying",
            "choice",
            default="NIFTY",
            choices=["NIFTY", "SENSEX"],
            description="Which index to trade",
        ),
        ParamSpec(
            "option_type",
            "choice",
            default="CE",
            choices=["CE", "PE"],
            description="All three legs use this option type (KB D1: 'all calls, or all puts')",
        ),
        ParamSpec(
            "entry_dte",
            "int",
            default=1,
            min=0,
            max=3,
            description="Target DTE to enter at (KB D1: S4-S5, DTE 1-0 -- needs low time value to be cheap)",
        ),
        ParamSpec(
            "middle_offset_strikes",
            "int",
            default=0,
            min=-10,
            max=10,
            description="Strikes from ATM for the middle (short) strike -- 0 = pinned at current ATM",
        ),
        ParamSpec(
            "wing_offset_strikes",
            "int",
            default=4,
            min=1,
            max=20,
            description="Strikes from the middle to each wing (symmetric, equidistant per KB D1)",
        ),
        ParamSpec(
            "risk_pct",
            "float",
            default=0.01,
            min=0.001,
            max=0.05,
            description="Fraction of capital risked per trade, against the debit paid (the max loss)",
        ),
        ParamSpec(
            "min_reward_to_risk",
            "float",
            default=1.0,
            min=0.0,
            max=5.0,
            description=(
                "Skip if (width - debit) / debit is below this -- KB D1 doesn't state an explicit "
                "filter number the way A1/A2 do for credit; this codebase's own conservative default"
            ),
        ),
        ParamSpec(
            "target_pct_of_max_profit",
            "float",
            default=0.50,
            min=0.1,
            max=1.0,
            description="Close at this fraction of max theoretical profit (width - debit) captured",
        ),
        ParamSpec(
            "stop_pct_of_debit",
            "float",
            default=0.75,
            min=0.1,
            max=1.0,
            description="Stop once this fraction of the entry debit has been given back",
        ),
        ParamSpec(
            "vwap_period",
            "int",
            default=26,
            min=5,
            max=50,
            description="15m bars used for the rolling VWAP trend check (~1 session)",
        ),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("open_position", None)
        ctx.state.setdefault("leg_ltp", {})
        ctx.log(
            "info",
            "Butterfly Weekly started",
            underlying=ctx.params["underlying"],
            entry_dte=ctx.params["entry_dte"],
        )

    def _executor(self, ctx: StrategyContext) -> MultiLegExecutor:
        return MultiLegExecutor(
            place_order_fn=ctx.place_order,
            cancel_order_fn=ctx.cancel_order,
            get_order_fn=ctx.get_order,
            alert_fn=ctx.notify_critical,
        )

    # ── Entry ────────────────────────────────────────────────────────────────

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        underlying = ctx.params["underlying"]
        if bar.symbol != _UNDERLYING_SPOT_SYMBOL[underlying]:
            return
        if ctx.state.get("open_position") is not None:
            return  # one butterfly at a time per instance

        now_ist = await _now_ist(ctx)
        is_daily = bar.timeframe == "1d"
        if not is_daily and not (
            now_ist.hour == 9
            and now_ist.minute >= 45
            or (now_ist.hour == 10 and now_ist.minute <= 30)
        ):
            return  # same 09:45-10:30 IST entry window as the other two weekly strategies

        bars = await ctx.history(
            bar.symbol, bar.timeframe, lookback=max(60, ctx.params["vwap_period"] + 1)
        )
        bars = bars + [bar]
        if len(bars) < 50:
            return

        closes = [float(b.close) for b in bars]
        ema20, ema50 = ema(closes, 20), ema(closes, 50)
        price = float(bar.close)

        if is_daily:
            if ema20 is None or ema50 is None:
                return
            trending = (price > ema20 > ema50) or (price < ema20 < ema50)
        else:
            vw = vwap(bars, ctx.params["vwap_period"])
            if ema20 is None or ema50 is None or vw is None:
                return
            trending = (price > vw and ema20 > ema50) or (price < vw and ema20 < ema50)

        if trending:
            # Same reused signal as iron_condor_weekly.py -- see this
            # module's own docstring for why "no trend" stands in for
            # "expect a pin" absent real OI-based pin detection.
            ctx.log("info", "butterfly: trend present, skipping entry", underlying=underlying)
            return

        opt_type = ctx.params["option_type"]
        try:
            await ctx.get_spot(underlying)
            middle = await ctx.resolve_strike(
                underlying,
                "this_week",
                strike_offset=ctx.params["middle_offset_strikes"],
                opt_type=opt_type,
            )
        except Exception as exc:
            ctx.log("warning", "butterfly: strike resolution failed", error=str(exc))
            return

        dte = (middle.expiry - now_ist.date()).days
        if dte > ctx.params["entry_dte"]:
            return

        wing = ctx.params["wing_offset_strikes"]
        try:
            lower = await ctx.resolve_strike(
                underlying,
                "this_week",
                strike_offset=ctx.params["middle_offset_strikes"] - wing,
                opt_type=opt_type,
            )
            upper = await ctx.resolve_strike(
                underlying,
                "this_week",
                strike_offset=ctx.params["middle_offset_strikes"] + wing,
                opt_type=opt_type,
            )
            middle_ltp = await ctx.get_option_price(middle.tradingsymbol, middle.exchange)
            lower_ltp = await ctx.get_option_price(lower.tradingsymbol, lower.exchange)
            upper_ltp = await ctx.get_option_price(upper.tradingsymbol, upper.exchange)
        except Exception as exc:
            ctx.log("warning", "butterfly: leg pricing failed", error=str(exc))
            return

        # Real listed strike ladder isn't always perfectly symmetric -- size
        # against the wider side, same worse-case-cost reasoning
        # iron_condor_weekly.py uses for its own two independent sides.
        width = max(abs(middle.strike - lower.strike), abs(upper.strike - middle.strike))

        debit = (lower_ltp + upper_ltp) - (Decimal("2") * middle_ltp)
        if debit <= 0:
            ctx.log("info", "butterfly: non-positive debit, skipping", debit=str(debit))
            return
        if width <= debit:
            ctx.log(
                "info",
                "butterfly: debit exceeds width, no possible profit, skipping",
                debit=str(debit),
                width=str(width),
            )
            return
        max_profit = width - debit
        if max_profit / debit < Decimal(str(ctx.params["min_reward_to_risk"])):
            ctx.log(
                "info",
                "butterfly: reward:risk below minimum, skipping",
                max_profit=str(max_profit),
                debit=str(debit),
            )
            return

        try:
            loss_per_lot = max_loss_per_lot(StructureType.BUTTERFLY, middle.lot_size, debit=debit)
            size = size_defined_risk_position(
                ctx.capital_allocated, Decimal(str(ctx.params["risk_pct"])), loss_per_lot
            )
        except ValueError as exc:
            ctx.log(
                "warning",
                "butterfly: invalid debit, likely stale/illiquid leg price, skipping",
                debit=str(debit),
                error=str(exc),
            )
            return
        if size.lots < 1:
            ctx.log(
                "info", "butterfly: position too large for account, skipping", reason=size.reason
            )
            return

        qty = size.lots * middle.lot_size
        # Both wings are always BUY regardless of option type -- a long
        # butterfly buys the wings (call or put) and sells the middle either way.
        side = Side.BUY
        lower_leg = Leg(
            symbol=lower.tradingsymbol,
            exchange=lower.exchange,
            role=LegRole.LONG,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=0,
        )
        upper_leg = Leg(
            symbol=upper.tradingsymbol,
            exchange=upper.exchange,
            role=LegRole.LONG,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=1,
        )
        middle_leg_a = Leg(
            symbol=middle.tradingsymbol,
            exchange=middle.exchange,
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=2,
            protects_leg_index=0,
        )
        middle_leg_b = Leg(
            symbol=middle.tradingsymbol,
            exchange=middle.exchange,
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=3,
            protects_leg_index=1,
        )
        spec = MultiLegSpec(
            structure_type=StructureType.BUTTERFLY,
            underlying=underlying,
            legs=[lower_leg, upper_leg, middle_leg_a, middle_leg_b],
            lot_size=middle.lot_size,
            width=width,
            debit=debit,
            expiry=middle.expiry.isoformat(),
        )

        for leg in (lower, middle, upper):
            await ctx.subscribe_instrument(leg.tradingsymbol, leg.exchange)

        result = await self._executor(ctx).execute_entry(
            spec, tag=f"butterfly_{middle.expiry.isoformat()}"
        )
        if result.outcome != ExecutionOutcome.SUCCESS:
            ctx.log(
                "warning",
                "butterfly: entry did not complete cleanly",
                outcome=result.outcome.value,
                detail=result.message,
            )
            return

        fills_by_index = {lf.leg.index: lf.order for lf in result.fills}
        entry_debit = debit
        realised = self._realised_debit(fills_by_index)
        if realised is not None:
            entry_debit = realised

        expiry_date = middle.expiry
        protective = butterfly_protective_levels(
            entry_debit if entry_debit > 0 else debit,
            width,
            target_pct_of_max_profit=Decimal(str(ctx.params["target_pct_of_max_profit"])),
            stop_pct_of_debit=Decimal(str(ctx.params["stop_pct_of_debit"])),
            time_stop_date=None,  # see module docstring -- handled inline in on_tick instead
        )

        ctx.state["open_position"] = {
            "spec": {
                "underlying": underlying,
                "option_type": opt_type,
                "lower_symbol": lower.tradingsymbol,
                "lower_exchange": lower.exchange,
                "upper_symbol": upper.tradingsymbol,
                "upper_exchange": upper.exchange,
                "middle_symbol": middle.tradingsymbol,
                "middle_exchange": middle.exchange,
                "lot_size": middle.lot_size,
                "qty": qty,
                "width": str(width),
                "debit": str(entry_debit),
                "expiry": expiry_date.isoformat(),
            },
            "protective": {
                "stop_value": str(protective.stop_value),
                "target_value": (
                    str(protective.target_value) if protective.target_value is not None else None
                ),
            },
        }
        ctx.log(
            "info",
            "butterfly opened",
            underlying=underlying,
            debit=str(entry_debit),
            width=str(width),
            lots=size.lots,
            middle=middle.tradingsymbol,
        )

    def _realised_debit(self, fills_by_index: dict) -> Decimal | None:
        """True realised debit from actual fill prices, refining the
        pre-trade estimate -- None if any leg's fill price is unavailable
        (falls back to the pre-trade estimate, same precedent as the other
        two weekly strategies). Keyed by leg INDEX, not symbol -- the two
        middle-strike legs share a symbol, so a symbol-keyed dict would
        silently drop one of their fills."""
        prices = {}
        for idx in (0, 1, 2, 3):
            order = fills_by_index.get(idx)
            if order is None or order.avg_fill_price is None:
                return None
            prices[idx] = order.avg_fill_price
        return (prices[0] + prices[1]) - (prices[2] + prices[3])

    # ── Protective-order monitoring + exit ──────────────────────────────────

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        pos = ctx.state.get("open_position")
        if pos is None:
            return
        spec_state = pos["spec"]
        leg_symbols = {
            spec_state["lower_symbol"],
            spec_state["upper_symbol"],
            spec_state["middle_symbol"],
        }
        if tick.symbol not in leg_symbols:
            return

        leg_ltp = ctx.state.setdefault("leg_ltp", {})
        leg_ltp[tick.symbol] = str(tick.ltp)
        if not leg_symbols.issubset(leg_ltp.keys()):
            return  # need all three strikes' LTP before butterfly value is meaningful

        current_value = butterfly_value(
            Decimal(leg_ltp[spec_state["middle_symbol"]]),
            Decimal(leg_ltp[spec_state["lower_symbol"]]),
            Decimal(leg_ltp[spec_state["upper_symbol"]]),
        )

        now_ist = await _now_ist(ctx)
        expiry_date = date.fromisoformat(spec_state["expiry"])
        if now_ist.date() >= expiry_date and now_ist.time() >= _EXPIRY_DAY_FLATTEN_TIME:
            # See module docstring -- ProtectiveOrderSpec.time_stop_date is
            # deliberately not used for this strategy; this inline date+
            # time gate is what actually flattens it, ahead of X02.
            await self._close_position(ctx, pos, "TIME_STOP", current_value)
            return

        protective_state = pos["protective"]
        protective = ProtectiveOrderSpec(
            stop_value=Decimal(protective_state["stop_value"]),
            target_value=(
                Decimal(protective_state["target_value"])
                if protective_state["target_value"]
                else None
            ),
            time_stop_date=None,
        )
        trigger = check_exit_trigger(protective, current_value, now_ist.date())
        if trigger is None:
            return

        await self._close_position(ctx, pos, trigger, current_value)

    async def _close_position(
        self, ctx: StrategyContext, pos: dict, reason: str, current_value: Decimal
    ) -> None:
        spec_state = pos["spec"]
        qty = spec_state["qty"]
        side = Side.BUY  # both wings are always BUY regardless of option type
        lower_leg = Leg(
            symbol=spec_state["lower_symbol"],
            exchange=spec_state["lower_exchange"],
            role=LegRole.LONG,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=0,
        )
        upper_leg = Leg(
            symbol=spec_state["upper_symbol"],
            exchange=spec_state["upper_exchange"],
            role=LegRole.LONG,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=1,
        )
        middle_leg_a = Leg(
            symbol=spec_state["middle_symbol"],
            exchange=spec_state["middle_exchange"],
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=2,
            protects_leg_index=0,
        )
        middle_leg_b = Leg(
            symbol=spec_state["middle_symbol"],
            exchange=spec_state["middle_exchange"],
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=3,
            protects_leg_index=1,
        )
        spec = MultiLegSpec(
            structure_type=StructureType.BUTTERFLY,
            underlying=spec_state["underlying"],
            legs=[lower_leg, upper_leg, middle_leg_a, middle_leg_b],
            lot_size=spec_state["lot_size"],
            width=Decimal(spec_state["width"]),
            debit=Decimal(spec_state["debit"]),
            expiry=spec_state["expiry"],
        )
        result = await self._executor(ctx).execute_exit(spec, tag=f"butterfly_exit_{reason}")
        ctx.log(
            "info",
            "butterfly exit",
            reason=reason,
            outcome=result.outcome.value,
            current_butterfly_value=str(current_value),
        )
        # Same precedent as credit_spread_weekly.py / iron_condor_weekly.py:
        # this instance stops tracking regardless of outcome -- a still-open
        # leg after HALTED_FOR_HUMAN is either fully hedged (its pair
        # partner also still open) or genuinely flat, per multileg_
        # execution.py's exit-side dependency gate (2026-08-29).
        ctx.state["open_position"] = None
        ctx.state["leg_ltp"] = {}
        if result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN:
            await ctx.notify_critical(
                "butterfly exit halted for human review",
                f"{spec_state['underlying']} {spec_state['middle_symbol']}: {result.message}",
            )

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "Butterfly Weekly stopped", reason=reason)
