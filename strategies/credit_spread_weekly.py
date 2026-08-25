"""
Nifty/Sensex weekly defined-risk credit spread -- the strategy recommended
in docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md (KB Rank 1,
07-RANKED-LOW-RISK-HIGH-WIN.md), chosen specifically because it's the
fastest 2-leg, fully-mechanical structure to validate or kill on a backtest.

Full mechanical rules are written out in docs/strategies/credit-spread-
weekly.md per the asset-pipeline's Stage 1 rule ("write the rules in plain
language before backtesting"). This file is the implementation of exactly
those rules -- nothing here should surprise that doc.

Honest scope notes (read before trusting a backtest run of this):
- The VIX percentile entry filter (KB 10 §5 Filter 1 -- "the single largest
  improvement found in any research reviewed") is NOT applied: no VIX data
  provider is wired into xillion yet. `require_vix_filter` exists as a
  param so this is visible in the UI, not silently skipped.
- Strike selection uses a strike-count offset from ATM (walking the real
  listed ladder), not a delta model -- xillion has no options-greeks engine.
  This is a coarser proxy for "20-delta short strike" than the KB's ideal.
- The liquidity filter (KB 10 §5 Filter 5, bid-ask spread) is only checked
  when a broker actually returns bid/ask on its Tick (NSE Bhavcopy backtests
  won't have it) -- skipped, not faked, when unavailable.
- Only the 2-leg credit spread is implemented, not the iron condor "no clear
  trend" arm -- KB 10 §3 explicitly allows SKIP as the simpler alternative,
  and the spec picked 2 legs specifically to keep the first validation run
  fast.
- Options-Stage-2 backtesting IS wired (xillion/data/option_chain.py +
  BacktestEngine's option_chain_warehouse), NSE-listed underlyings only
  (NIFTY/BANKNIFTY -- Sensex is BSE-listed and NSE Bhavcopy doesn't cover
  it). This strategy calls `ctx.now()`, not a bare wall-clock read, so its
  entry-window/DTE gates correctly track the backtest's simulated time
  instead of always checking against today's real date.
"""
from datetime import date, datetime
from decimal import Decimal

from xillion.core.events import Bar, OrderType, Side, Tick
from xillion.core.market_calendar import IST
from xillion.core.multileg import (
    Leg, LegRole, MultiLegSpec, StructureType,
    credit_adequate, max_loss_per_lot, size_defined_risk_position,
)
from xillion.core.multileg_execution import ExecutionOutcome, MultiLegExecutor
from xillion.core.protective_orders import (
    check_exit_trigger, credit_spread_protective_levels, short_leg_gtt_levels, spread_value,
)
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext
from xillion.engine.indicators import ema, vwap

_UNDERLYING_SPOT_SYMBOL = {"NIFTY": "NIFTY 50", "SENSEX": "SENSEX"}


async def _now_ist(ctx: StrategyContext) -> datetime:
    """Environment-aware "now", in IST -- live/paper gets real wall-clock
    time, backtest gets the currently-simulated bar's timestamp (see
    StrategyContext.now()'s docstring for why this must not be a bare
    datetime.now() call: that would make every backtest only ever check
    against today's real date, regardless of which historical period is
    being replayed)."""
    return (await ctx.now()).astimezone(IST)


class CreditSpreadWeeklyStrategy(Strategy):
    name = "Credit Spread Weekly"
    version = "1.0.0"
    description = (
        "Nifty/Sensex weekly Bull Put / Bear Call credit spread, defined risk. "
        "See docs/strategies/credit-spread-weekly.md for the full mechanical rules."
    )
    author = "xillion"
    timeframe = "15m"
    instruments = ["NIFTY 50", "SENSEX"]

    params_schema = [
        ParamSpec("underlying", "choice", default="NIFTY", choices=["NIFTY", "SENSEX"],
                  description="Which index to trade -- Sensex's smaller lot (20 vs 65) fits far more capital tiers (KB 10 §1)"),
        ParamSpec("entry_dte", "int", default=4, min=1, max=6,
                  description="Days-to-expiry to enter at (S3=4 is the primary arm; KB 10 §2)"),
        ParamSpec("short_offset_strikes", "int", default=4, min=1, max=20,
                  description="Strikes OTM from ATM for the short (premium-collecting) leg"),
        ParamSpec("width_strikes", "int", default=4, min=1, max=20,
                  description="Additional strikes further OTM for the long (protective) leg"),
        ParamSpec("risk_pct", "float", default=0.01, min=0.001, max=0.05,
                  description="Fraction of capital risked per trade (KB 10 §7 worked example uses 1%)"),
        ParamSpec("min_credit_pct_of_width", "float", default=0.15, min=0.0, max=1.0,
                  description="Skip if credit < this fraction of spread width (KB 10 §5 Filter 4)"),
        ParamSpec("profit_target_pct", "float", default=0.50, min=0.1, max=1.0,
                  description="Close at this fraction of entry credit captured"),
        ParamSpec("stop_multiple_of_credit", "float", default=2.0, min=1.0, max=5.0,
                  description="Stop when spread value reaches this multiple of entry credit (2.0 = 100% loss)"),
        ParamSpec("time_stop_dte", "int", default=1, min=0, max=3,
                  description="Force-exit at this DTE regardless of P&L (KB 10 §6 -- avoid expiry-day gamma)"),
        ParamSpec("require_vix_filter", "bool", default=False,
                  description="Not wired yet (no VIX data provider) -- leave off; see module docstring"),
        ParamSpec("vwap_period", "int", default=26, min=5, max=50,
                  description="15m bars used for the rolling VWAP trend check (~1 session)"),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("open_position", None)  # dict describing the open spread, or None
        ctx.state.setdefault("leg_ltp", {})           # symbol -> last known LTP (str, for JSON state)
        ctx.log(
            "info", "Credit Spread Weekly started",
            underlying=ctx.params["underlying"], entry_dte=ctx.params["entry_dte"],
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
            return  # one spread at a time per instance

        now_ist = await _now_ist(ctx)
        if not (now_ist.hour == 9 and now_ist.minute >= 45 or (now_ist.hour == 10 and now_ist.minute <= 30)):
            return  # KB 10 §2: 09:45-10:30 IST entry window only

        bars = await ctx.history(bar.symbol, bar.timeframe, lookback=max(60, ctx.params["vwap_period"] + 1))
        bars = bars + [bar]
        if len(bars) < 50:
            return  # not enough history yet for the 50EMA

        closes = [float(b.close) for b in bars]
        ema20, ema50 = ema(closes, 20), ema(closes, 50)
        vw = vwap(bars, ctx.params["vwap_period"])
        if ema20 is None or ema50 is None or vw is None:
            return

        price = float(bar.close)
        if price > vw and ema20 > ema50:
            side = "BULL_PUT"
        elif price < vw and ema20 < ema50:
            side = "BEAR_CALL"
        else:
            ctx.log("info", "credit spread: no clear trend, skipping entry", underlying=underlying)
            return

        try:
            spot = await ctx.get_spot(underlying)
            short = await ctx.resolve_strike(
                underlying, "this_week",
                strike_offset=(-ctx.params["short_offset_strikes"] if side == "BULL_PUT" else ctx.params["short_offset_strikes"]),
                opt_type=("PE" if side == "BULL_PUT" else "CE"),
            )
        except Exception as exc:
            ctx.log("warning", "credit spread: strike resolution failed", error=str(exc))
            return

        dte = (short.expiry - now_ist.date()).days
        if dte != ctx.params["entry_dte"]:
            return

        long_offset_magnitude = ctx.params["short_offset_strikes"] + ctx.params["width_strikes"]
        long_offset = -long_offset_magnitude if side == "BULL_PUT" else long_offset_magnitude
        try:
            long_leg = await ctx.resolve_strike(
                underlying, "this_week", strike_offset=long_offset,
                opt_type=("PE" if side == "BULL_PUT" else "CE"),
            )
            short_ltp = await ctx.get_option_price(short.tradingsymbol, short.exchange)
            long_ltp = await ctx.get_option_price(long_leg.tradingsymbol, long_leg.exchange)
        except Exception as exc:
            ctx.log("warning", "credit spread: leg pricing failed", error=str(exc))
            return

        width = abs(short.strike - long_leg.strike)
        credit = short_ltp - long_ltp
        if credit <= 0:
            ctx.log("info", "credit spread: non-positive credit, skipping", credit=str(credit))
            return
        if not credit_adequate(credit, width, Decimal(str(ctx.params["min_credit_pct_of_width"]))):
            ctx.log(
                "info", "credit spread: credit below minimum, skipping",
                credit=str(credit), width=str(width),
            )
            return

        loss_per_lot = max_loss_per_lot(
            StructureType.CREDIT_SPREAD, short.lot_size, width=width, credit=credit,
        )
        size = size_defined_risk_position(
            ctx.capital_allocated, Decimal(str(ctx.params["risk_pct"])), loss_per_lot,
        )
        if size.lots < 1:
            ctx.log("info", "credit spread: position too large for account, skipping", reason=size.reason)
            return

        qty = size.lots * short.lot_size
        # Long leg first in the list -- order_entry_sequence() enforces this
        # regardless of list order, but writing it long-first here too keeps
        # the leg-pairing (protects_leg_index) trivially readable.
        long_order_leg = Leg(
            symbol=long_leg.tradingsymbol, exchange=long_leg.exchange, role=LegRole.LONG,
            side=Side.BUY, quantity=qty, order_type=OrderType.MARKET, index=0,
        )
        short_order_leg = Leg(
            symbol=short.tradingsymbol, exchange=short.exchange, role=LegRole.SHORT,
            side=Side.SELL, quantity=qty, order_type=OrderType.MARKET, index=1,
            protects_leg_index=0,
        )
        spec = MultiLegSpec(
            structure_type=StructureType.CREDIT_SPREAD, underlying=underlying,
            legs=[long_order_leg, short_order_leg], lot_size=short.lot_size,
            width=width, credit=credit, expiry=short.expiry.isoformat(),
            metadata={"side": side},
        )

        await ctx.subscribe_instrument(long_leg.tradingsymbol, long_leg.exchange)
        await ctx.subscribe_instrument(short.tradingsymbol, short.exchange)

        result = await self._executor(ctx).execute_entry(spec, tag=f"credit_spread_{short.expiry.isoformat()}")
        if result.outcome != ExecutionOutcome.SUCCESS:
            ctx.log(
                "warning", "credit spread: entry did not complete cleanly",
                outcome=result.outcome.value, detail=result.message,
            )
            return

        entry_credit = credit  # true realised credit is refined below from real fills, if both filled at expected prices
        fills_by_symbol = {lf.leg.symbol: lf.order for lf in result.fills}
        long_fill = fills_by_symbol.get(long_leg.tradingsymbol)
        short_fill = fills_by_symbol.get(short.tradingsymbol)
        if long_fill and long_fill.avg_fill_price is not None and short_fill and short_fill.avg_fill_price is not None:
            entry_credit = short_fill.avg_fill_price - long_fill.avg_fill_price

        expiry_date = short.expiry
        time_stop_date = None
        # Compute the calendar date that is `time_stop_dte` days before expiry
        # by counting back trading-agnostic calendar days -- exact enough for
        # a "force exit by N DTE" gate (mirrors the entry_dte check above).
        from datetime import timedelta
        time_stop_date = expiry_date - timedelta(days=ctx.params["time_stop_dte"])

        protective = credit_spread_protective_levels(
            entry_credit if entry_credit > 0 else credit,
            target_pct_of_credit=Decimal(str(ctx.params["profit_target_pct"])),
            stop_multiple_of_credit=Decimal(str(ctx.params["stop_multiple_of_credit"])),
            time_stop_date=time_stop_date,
        )

        # Broker-native backstop alongside the software stop below, not
        # instead of it -- best-effort: only possible with a real long-leg
        # fill price to anchor the approximation to (see
        # short_leg_gtt_levels), and place_protective_gtt itself already
        # returns None gracefully if the connected broker doesn't support
        # GTT (paper/backtest/Dhan-not-yet-wired).
        gtt_id = None
        if long_fill and long_fill.avg_fill_price is not None and short_fill and short_fill.avg_fill_price is not None:
            gtt_stop_price, gtt_target_price = short_leg_gtt_levels(long_fill.avg_fill_price, protective)
            gtt_id = await ctx.place_protective_gtt(
                symbol=short.tradingsymbol, exchange=short.exchange, side=Side.BUY,
                quantity=qty, stop_price=gtt_stop_price, target_price=gtt_target_price,
                last_price=short_fill.avg_fill_price,
            )

        ctx.state["open_position"] = {
            "spec": {
                "underlying": underlying, "side": side,
                "long_symbol": long_leg.tradingsymbol, "long_exchange": long_leg.exchange,
                "short_symbol": short.tradingsymbol, "short_exchange": short.exchange,
                "lot_size": short.lot_size, "qty": qty,
                "width": str(width), "credit": str(entry_credit),
                "expiry": expiry_date.isoformat(),
            },
            "protective": {
                "stop_value": str(protective.stop_value),
                "target_value": str(protective.target_value) if protective.target_value is not None else None,
                "time_stop_date": protective.time_stop_date.isoformat() if protective.time_stop_date else None,
            },
            "gtt_id": gtt_id,
        }
        ctx.log(
            "info", "credit spread opened",
            underlying=underlying, side=side, credit=str(entry_credit), width=str(width),
            lots=size.lots, short=short.tradingsymbol, long=long_leg.tradingsymbol,
            gtt_id=gtt_id,
        )

    # ── Protective-order monitoring + exit ──────────────────────────────────

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        pos = ctx.state.get("open_position")
        if pos is None:
            return
        spec_state = pos["spec"]
        if tick.symbol not in (spec_state["short_symbol"], spec_state["long_symbol"]):
            return

        leg_ltp = ctx.state.setdefault("leg_ltp", {})
        leg_ltp[tick.symbol] = str(tick.ltp)
        if spec_state["short_symbol"] not in leg_ltp or spec_state["long_symbol"] not in leg_ltp:
            return  # need both legs' LTP before spread value is meaningful

        current_value = spread_value(
            Decimal(leg_ltp[spec_state["short_symbol"]]), Decimal(leg_ltp[spec_state["long_symbol"]]),
        )
        from xillion.core.protective_orders import ProtectiveOrderSpec
        protective_state = pos["protective"]
        protective = ProtectiveOrderSpec(
            stop_value=Decimal(protective_state["stop_value"]),
            target_value=Decimal(protective_state["target_value"]) if protective_state["target_value"] else None,
            time_stop_date=(
                date.fromisoformat(protective_state["time_stop_date"])
                if protective_state["time_stop_date"] else None
            ),
        )
        trigger = check_exit_trigger(protective, current_value, (await _now_ist(ctx)).date())
        if trigger is None:
            return

        await self._close_position(ctx, pos, trigger, current_value)

    async def _close_position(self, ctx: StrategyContext, pos: dict, reason: str, current_value: Decimal) -> None:
        spec_state = pos["spec"]
        qty = spec_state["qty"]
        long_order_leg = Leg(
            symbol=spec_state["long_symbol"], exchange=spec_state["long_exchange"], role=LegRole.LONG,
            side=Side.BUY, quantity=qty, order_type=OrderType.MARKET, index=0,
        )
        short_order_leg = Leg(
            symbol=spec_state["short_symbol"], exchange=spec_state["short_exchange"], role=LegRole.SHORT,
            side=Side.SELL, quantity=qty, order_type=OrderType.MARKET, index=1,
            protects_leg_index=0,
        )
        spec = MultiLegSpec(
            structure_type=StructureType.CREDIT_SPREAD, underlying=spec_state["underlying"],
            legs=[long_order_leg, short_order_leg], lot_size=spec_state["lot_size"],
            width=Decimal(spec_state["width"]), credit=Decimal(spec_state["credit"]),
            expiry=spec_state["expiry"],
        )
        result = await self._executor(ctx).execute_exit(spec, tag=f"credit_spread_exit_{reason}")
        ctx.log(
            "info", "credit spread exit", reason=reason, outcome=result.outcome.value,
            current_spread_value=str(current_value),
        )
        # HALTED_FOR_HUMAN means the short leg's real broker position is
        # unclear -- do NOT cancel its GTT here, that broker-native stop
        # is exactly the protection a human-review window still needs.
        # Every other outcome means the position is genuinely flat, so a
        # still-active GTT is now stale and must be torn down before it
        # can fire against a symbol no longer held.
        if result.outcome != ExecutionOutcome.HALTED_FOR_HUMAN:
            gtt_id = pos.get("gtt_id")
            if gtt_id:
                await ctx.cancel_gtt(gtt_id)
        # Cleared regardless of outcome: FORCE_UNWOUND/UNWOUND both mean no
        # position remains; HALTED_FOR_HUMAN means a human takes it from
        # here, and this instance must not keep trying to exit an unclear
        # partial structure on every subsequent tick.
        ctx.state["open_position"] = None
        ctx.state["leg_ltp"] = {}
        if result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN:
            await ctx.notify_critical(
                "credit spread exit halted for human review",
                f"{spec_state['underlying']} {spec_state['short_symbol']}/{spec_state['long_symbol']}: "
                f"{result.message}",
            )

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        ctx.log("info", "Credit Spread Weekly stopped", reason=reason)
