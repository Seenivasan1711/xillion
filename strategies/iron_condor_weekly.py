"""
Nifty/Sensex weekly iron condor -- docs/strategies/knowledge-base/03-BAG-A-
SELLING-DEFINED-RISK.md A1. The first 4-leg consumer of the multi-leg
infrastructure CP11 built generically (xillion/core/multileg.py,
multileg_execution.py, protective_orders.py already had IRON_CONDOR support
and a "generalises to condor/butterfly" leg-pairing design from the start --
this is the strategy that actually exercises it, which is how two real bugs
in multileg_execution.py's leg-failure protocol were found and fixed on
2026-08-29 (see that module's own docstring): entry silently stopped
attempting legs after the first failure instead of trying an unrelated pair,
and a failed exit's "force unwind" would have re-sold an already-closed leg.

Deliberately shares the SAME weekly-cycle conventions as
strategies/credit_spread_weekly.py (entry_dte, time_stop_dte defaults,
09:45-10:30 entry window, VWAP+EMA trend check, strike-count strike
selection) rather than the KB's more generic "S1-S3, DTE 6-3, close by 7
DTE" framing, which reads as describing a monthly-cycle condor -- this
codebase's options infra is uniformly weekly, and reusing one set of
conventions is more valuable than mirroring the KB literally per structure.

**Key difference in entry LOGIC, not just leg count:** the credit spread
picks a directional side (BULL_PUT/BEAR_CALL) when a trend IS present. The
iron condor is the opposite market view (KB 02 §Regime: "range-bound ->
neutral structures (condor, straddle)... do not sell a neutral structure
into a trend day") -- this strategy enters exactly when the SAME trend
check finds NEITHER a bull NOR a bear signal, i.e. the credit spread's own
"skip" case is this strategy's entry signal.

Honest scope notes (read before trusting a run of this):
- Same inherited gaps as credit_spread_weekly.py: no VIX filter, no event
  calendar veto, liquidity filter only when a broker returns bid/ask,
  strike-count offset instead of a delta model. See that file's own
  docstring for the full reasoning -- not repeated here.
- **No broker-native GTT backstop for this structure (a real, deliberate
  scope cut, not an oversight).** credit_spread_weekly.py's GTT anchors a
  single-instrument broker trigger to ONE spread's entry-fill price.
  Splitting a condor's COMBINED stop/target threshold fairly across two
  independent single-instrument GTTs (one per side) needs its own
  allocation logic that doesn't exist yet -- the software stop (tick-
  driven, monitoring condor_value() across all four legs every tick) is
  the PRIMARY protection mechanism regardless (see protective_orders.py's
  own module docstring), so this is a real gap in the worst-case backstop,
  not in day-to-day protection.
- Both sides use the SAME short_offset_strikes/width_strikes (one pair of
  params, not four) -- matches max_loss_per_lot()'s IRON_CONDOR formula,
  which takes a single `width`, and the KB's own symmetric worked example.
  The actual call-side and put-side point-widths are computed independently
  from the real listed strike ladder and may differ slightly if it isn't
  perfectly symmetric around spot; sizing conservatively uses whichever
  side is wider (the worst case a single-side breach could cost).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from xillion.core.events import Bar, OrderType, Side, Tick
from xillion.core.market_calendar import IST
from xillion.core.multileg import (
    Leg,
    LegRole,
    MultiLegSpec,
    StructureType,
    credit_adequate,
    max_loss_per_lot,
    size_defined_risk_position,
)
from xillion.core.multileg_execution import ExecutionOutcome, MultiLegExecutor
from xillion.core.protective_orders import (
    ProtectiveOrderSpec,
    check_exit_trigger,
    condor_value,
    credit_spread_protective_levels,
)
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext
from xillion.engine.indicators import ema, vwap

_UNDERLYING_SPOT_SYMBOL = {"NIFTY": "NIFTY 50", "SENSEX": "SENSEX"}


async def _now_ist(ctx: StrategyContext) -> datetime:
    """Same environment-aware "now" as credit_spread_weekly.py -- see that
    file's own helper for why this must not be a bare datetime.now()."""
    return (await ctx.now()).astimezone(IST)


class IronCondorWeeklyStrategy(Strategy):
    name = "Iron Condor Weekly"
    version = "1.0.0"
    description = (
        "Nifty/Sensex weekly iron condor, defined risk, 4 legs. Entered on a range-bound "
        "trend signal (the opposite market view from Credit Spread Weekly). See "
        "docs/strategies/iron-condor-weekly.md for the full mechanical rules."
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
            description="Which index to trade -- Sensex's smaller lot (20 vs 65) fits far more capital tiers",
        ),
        ParamSpec(
            "entry_dte",
            "int",
            default=4,
            min=1,
            max=6,
            description=(
                "Target days-to-expiry to enter at. Entry fires on the first trading day "
                "where DTE <= this value, not an exact match -- same nearest-reachable-DTE "
                "rule as credit_spread_weekly.py, for the same reason (expiry weekday "
                "regime changes shouldn't silently stop entries firing)."
            ),
        ),
        ParamSpec(
            "short_offset_strikes",
            "int",
            default=6,
            min=1,
            max=20,
            description="Strikes OTM from ATM for BOTH short legs (call and put) -- KB A1's worked example uses a symmetric offset",
        ),
        ParamSpec(
            "width_strikes",
            "int",
            default=4,
            min=1,
            max=20,
            description="Additional strikes further OTM for BOTH long (protective/wing) legs",
        ),
        ParamSpec(
            "risk_pct",
            "float",
            default=0.01,
            min=0.001,
            max=0.05,
            description="Fraction of capital risked per trade, against the worse-side max loss",
        ),
        ParamSpec(
            "min_credit_pct_of_width",
            "float",
            default=0.25,
            min=0.0,
            max=1.0,
            description="Skip if combined credit < this fraction of the wider side's width (KB A1: target 25-33%)",
        ),
        ParamSpec(
            "profit_target_pct",
            "float",
            default=0.50,
            min=0.1,
            max=1.0,
            description="Close at this fraction of entry credit captured (KB A1: 50%)",
        ),
        ParamSpec(
            "stop_multiple_of_credit",
            "float",
            default=2.0,
            min=1.0,
            max=5.0,
            description="Stop when combined condor value reaches this multiple of entry credit (KB A1: 200%)",
        ),
        ParamSpec(
            "time_stop_dte",
            "int",
            default=1,
            min=0,
            max=3,
            description="Force-exit at this DTE regardless of P&L -- avoid expiry-day gamma",
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
            "Iron Condor Weekly started",
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
            return  # one condor at a time per instance

        now_ist = await _now_ist(ctx)
        is_daily = bar.timeframe == "1d"
        if not is_daily and not (
            now_ist.hour == 9
            and now_ist.minute >= 45
            or (now_ist.hour == 10 and now_ist.minute <= 30)
        ):
            return  # same 09:45-10:30 IST entry window as the credit spread

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
            # KB 02 §Regime: do not sell a neutral structure into a trend
            # day -- this is the exact inverse of credit_spread_weekly's
            # own "no clear trend, skipping entry" branch.
            ctx.log("info", "iron condor: trend present, skipping entry", underlying=underlying)
            return

        try:
            await ctx.get_spot(underlying)
            short_call = await ctx.resolve_strike(
                underlying,
                "this_week",
                strike_offset=ctx.params["short_offset_strikes"],
                opt_type="CE",
            )
            short_put = await ctx.resolve_strike(
                underlying,
                "this_week",
                strike_offset=-ctx.params["short_offset_strikes"],
                opt_type="PE",
            )
        except Exception as exc:
            ctx.log("warning", "iron condor: strike resolution failed", error=str(exc))
            return

        dte = (short_call.expiry - now_ist.date()).days
        if dte > ctx.params["entry_dte"]:
            return

        wing = ctx.params["short_offset_strikes"] + ctx.params["width_strikes"]
        try:
            long_call = await ctx.resolve_strike(
                underlying, "this_week", strike_offset=wing, opt_type="CE"
            )
            long_put = await ctx.resolve_strike(
                underlying, "this_week", strike_offset=-wing, opt_type="PE"
            )
            short_call_ltp = await ctx.get_option_price(
                short_call.tradingsymbol, short_call.exchange
            )
            long_call_ltp = await ctx.get_option_price(long_call.tradingsymbol, long_call.exchange)
            short_put_ltp = await ctx.get_option_price(short_put.tradingsymbol, short_put.exchange)
            long_put_ltp = await ctx.get_option_price(long_put.tradingsymbol, long_put.exchange)
        except Exception as exc:
            ctx.log("warning", "iron condor: leg pricing failed", error=str(exc))
            return

        call_width = abs(long_call.strike - short_call.strike)
        put_width = abs(short_put.strike - long_put.strike)
        # Loss can only occur on ONE side, never both (KB A1) -- size
        # against whichever side is wider, the worst case a single-side
        # breach could actually cost.
        width = max(call_width, put_width)
        credit = (short_call_ltp - long_call_ltp) + (short_put_ltp - long_put_ltp)
        if credit <= 0:
            ctx.log("info", "iron condor: non-positive credit, skipping", credit=str(credit))
            return
        if not credit_adequate(credit, width, Decimal(str(ctx.params["min_credit_pct_of_width"]))):
            ctx.log(
                "info",
                "iron condor: credit below minimum, skipping",
                credit=str(credit),
                width=str(width),
            )
            return
        try:
            loss_per_lot = max_loss_per_lot(
                StructureType.IRON_CONDOR, short_call.lot_size, width=width, credit=credit
            )
            size = size_defined_risk_position(
                ctx.capital_allocated, Decimal(str(ctx.params["risk_pct"])), loss_per_lot
            )
        except ValueError as exc:
            # Same stale/illiquid-EOD-close reasoning as credit_spread_weekly.py
            # -- a defined-risk structure can never legitimately have a
            # non-positive max loss.
            ctx.log(
                "warning",
                "iron condor: credit too close to width, likely stale/illiquid leg price, skipping",
                credit=str(credit),
                width=str(width),
                error=str(exc),
            )
            return
        if size.lots < 1:
            ctx.log(
                "info", "iron condor: position too large for account, skipping", reason=size.reason
            )
            return

        qty = size.lots * short_call.lot_size
        long_call_leg = Leg(
            symbol=long_call.tradingsymbol,
            exchange=long_call.exchange,
            role=LegRole.LONG,
            side=Side.BUY,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=0,
        )
        long_put_leg = Leg(
            symbol=long_put.tradingsymbol,
            exchange=long_put.exchange,
            role=LegRole.LONG,
            side=Side.BUY,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=1,
        )
        short_call_leg = Leg(
            symbol=short_call.tradingsymbol,
            exchange=short_call.exchange,
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=2,
            protects_leg_index=0,
        )
        short_put_leg = Leg(
            symbol=short_put.tradingsymbol,
            exchange=short_put.exchange,
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=3,
            protects_leg_index=1,
        )
        spec = MultiLegSpec(
            structure_type=StructureType.IRON_CONDOR,
            underlying=underlying,
            legs=[long_call_leg, long_put_leg, short_call_leg, short_put_leg],
            lot_size=short_call.lot_size,
            width=width,
            credit=credit,
            expiry=short_call.expiry.isoformat(),
        )

        for leg in (long_call, long_put, short_call, short_put):
            await ctx.subscribe_instrument(leg.tradingsymbol, leg.exchange)

        result = await self._executor(ctx).execute_entry(
            spec, tag=f"iron_condor_{short_call.expiry.isoformat()}"
        )
        if result.outcome != ExecutionOutcome.SUCCESS:
            ctx.log(
                "warning",
                "iron condor: entry did not complete cleanly",
                outcome=result.outcome.value,
                detail=result.message,
            )
            return

        fills_by_symbol = {lf.leg.symbol: lf.order for lf in result.fills}
        entry_credit = credit
        realised = self._realised_credit(
            fills_by_symbol, long_call, long_put, short_call, short_put
        )
        if realised is not None:
            entry_credit = realised

        expiry_date = short_call.expiry
        time_stop_date = expiry_date - timedelta(days=ctx.params["time_stop_dte"])
        protective = credit_spread_protective_levels(
            entry_credit if entry_credit > 0 else credit,
            target_pct_of_credit=Decimal(str(ctx.params["profit_target_pct"])),
            stop_multiple_of_credit=Decimal(str(ctx.params["stop_multiple_of_credit"])),
            time_stop_date=time_stop_date,
        )

        ctx.state["open_position"] = {
            "spec": {
                "underlying": underlying,
                "long_call_symbol": long_call.tradingsymbol,
                "long_call_exchange": long_call.exchange,
                "long_put_symbol": long_put.tradingsymbol,
                "long_put_exchange": long_put.exchange,
                "short_call_symbol": short_call.tradingsymbol,
                "short_call_exchange": short_call.exchange,
                "short_put_symbol": short_put.tradingsymbol,
                "short_put_exchange": short_put.exchange,
                "lot_size": short_call.lot_size,
                "qty": qty,
                "width": str(width),
                "credit": str(entry_credit),
                "expiry": expiry_date.isoformat(),
            },
            "protective": {
                "stop_value": str(protective.stop_value),
                "target_value": (
                    str(protective.target_value) if protective.target_value is not None else None
                ),
                "time_stop_date": (
                    protective.time_stop_date.isoformat() if protective.time_stop_date else None
                ),
            },
        }
        ctx.log(
            "info",
            "iron condor opened",
            underlying=underlying,
            credit=str(entry_credit),
            width=str(width),
            lots=size.lots,
            short_call=short_call.tradingsymbol,
            short_put=short_put.tradingsymbol,
        )

    def _realised_credit(
        self, fills_by_symbol, long_call, long_put, short_call, short_put
    ) -> Decimal | None:
        """True realised credit from actual fill prices, refining the
        pre-trade estimate -- None if any leg's fill price is unavailable
        (falls back to the pre-trade credit estimate, same precedent as
        credit_spread_weekly.py)."""
        prices = {}
        for key, inst in (
            ("long_call", long_call),
            ("long_put", long_put),
            ("short_call", short_call),
            ("short_put", short_put),
        ):
            order = fills_by_symbol.get(inst.tradingsymbol)
            if order is None or order.avg_fill_price is None:
                return None
            prices[key] = order.avg_fill_price
        return (prices["short_call"] - prices["long_call"]) + (
            prices["short_put"] - prices["long_put"]
        )

    # ── Protective-order monitoring + exit ──────────────────────────────────

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        pos = ctx.state.get("open_position")
        if pos is None:
            return
        spec_state = pos["spec"]
        leg_symbols = {
            spec_state["long_call_symbol"],
            spec_state["long_put_symbol"],
            spec_state["short_call_symbol"],
            spec_state["short_put_symbol"],
        }
        if tick.symbol not in leg_symbols:
            return

        leg_ltp = ctx.state.setdefault("leg_ltp", {})
        leg_ltp[tick.symbol] = str(tick.ltp)
        if not leg_symbols.issubset(leg_ltp.keys()):
            return  # need all four legs' LTP before condor value is meaningful

        current_value = condor_value(
            Decimal(leg_ltp[spec_state["short_call_symbol"]]),
            Decimal(leg_ltp[spec_state["long_call_symbol"]]),
            Decimal(leg_ltp[spec_state["short_put_symbol"]]),
            Decimal(leg_ltp[spec_state["long_put_symbol"]]),
        )

        protective_state = pos["protective"]
        protective = ProtectiveOrderSpec(
            stop_value=Decimal(protective_state["stop_value"]),
            target_value=(
                Decimal(protective_state["target_value"])
                if protective_state["target_value"]
                else None
            ),
            time_stop_date=(
                date.fromisoformat(protective_state["time_stop_date"])
                if protective_state["time_stop_date"]
                else None
            ),
        )
        trigger = check_exit_trigger(protective, current_value, (await _now_ist(ctx)).date())
        if trigger is None:
            return

        await self._close_position(ctx, pos, trigger, current_value)

    async def _close_position(
        self, ctx: StrategyContext, pos: dict, reason: str, current_value: Decimal
    ) -> None:
        spec_state = pos["spec"]
        qty = spec_state["qty"]
        long_call_leg = Leg(
            symbol=spec_state["long_call_symbol"],
            exchange=spec_state["long_call_exchange"],
            role=LegRole.LONG,
            side=Side.BUY,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=0,
        )
        long_put_leg = Leg(
            symbol=spec_state["long_put_symbol"],
            exchange=spec_state["long_put_exchange"],
            role=LegRole.LONG,
            side=Side.BUY,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=1,
        )
        short_call_leg = Leg(
            symbol=spec_state["short_call_symbol"],
            exchange=spec_state["short_call_exchange"],
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=2,
            protects_leg_index=0,
        )
        short_put_leg = Leg(
            symbol=spec_state["short_put_symbol"],
            exchange=spec_state["short_put_exchange"],
            role=LegRole.SHORT,
            side=Side.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
            index=3,
            protects_leg_index=1,
        )
        spec = MultiLegSpec(
            structure_type=StructureType.IRON_CONDOR,
            underlying=spec_state["underlying"],
            legs=[long_call_leg, long_put_leg, short_call_leg, short_put_leg],
            lot_size=spec_state["lot_size"],
            width=Decimal(spec_state["width"]),
            credit=Decimal(spec_state["credit"]),
            expiry=spec_state["expiry"],
        )
        result = await self._executor(ctx).execute_exit(spec, tag=f"iron_condor_exit_{reason}")
        ctx.log(
            "info",
            "iron condor exit",
            reason=reason,
            outcome=result.outcome.value,
            current_condor_value=str(current_value),
        )
        # Any leg(s) left open by a HALTED_FOR_HUMAN exit need this
        # instance to stop trying to close them on every subsequent tick --
        # a human takes it from here, matching credit_spread_weekly.py's
        # own precedent, generalised: this instance clears its own
        # tracking regardless of outcome, since multileg_execution.py's
        # exit-side dependency gate (2026-08-29) already ensures nothing
        # was left dangerously unprotected -- a still-open leg here is
        # either fully hedged (its pair partner also still open) or
        # genuinely flat.
        ctx.state["open_position"] = None
        ctx.state["leg_ltp"] = {}
        if result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN:
            await ctx.notify_critical(
                "iron condor exit halted for human review",
                f"{spec_state['underlying']} {spec_state['short_call_symbol']}/"
                f"{spec_state['short_put_symbol']}: {result.message}",
            )

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "Iron Condor Weekly stopped", reason=reason)
