"""
Backtest engine: loads historical bars, drives strategy on_bar hooks in
chronological order, collects trades and equity curve, computes metrics.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import structlog

from xillion.core.contracts import ContractSpec
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Side, Tick
from xillion.core.instruments import resolve_option
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.option_chain import OptionChainWarehouse
from xillion.engine.metrics import ClosedTrade, compute_metrics
from xillion.engine.position_math import PositionState, apply_fill

logger = structlog.get_logger(__name__)

# Underlyings this backtest engine can resolve options for -- NSE Bhavcopy
# (the only option-chain-capable provider today) is NSE-listed derivatives
# only, so Sensex (BSE) isn't reachable here. Raising a clear error for it
# beats a silent wrong answer.
_BACKTEST_OPTION_EXCHANGE = {"NIFTY": "NFO", "BANKNIFTY": "NFO"}


@dataclass
class FeeConfig:
    """Percentages of turnover. STT is charged on the SELL side only, which is
    how the Indian equity/F&O regime actually works -- charging it both ways
    roughly doubles the modelled cost and makes marginal strategies look worse
    than they are."""
    brokerage_pct: float = 0.03    # 0.03% of turnover, both sides
    stt_pct: float = 0.01          # sell side only
    other_pct: float = 0.005       # exchange + regulatory, both sides

    @classmethod
    def zero(cls) -> "FeeConfig":
        """Frictionless — for tests that assert exact arithmetic."""
        return cls(brokerage_pct=0.0, stt_pct=0.0, other_pct=0.0)


@dataclass
class BacktestResult:
    run_id: str
    strategy_name: str
    params: dict
    instruments: list[str]
    timeframe: str
    from_ts: datetime
    to_ts: datetime
    initial_capital: float
    slippage_bps: int
    metrics: dict
    equity_curve: list[float]
    trades: list[dict]
    status: str
    error: Optional[str] = None


class _BacktestContext(StrategyContext):
    """StrategyContext used exclusively during backtesting."""

    def __init__(
        self,
        instance_id: str,
        params: dict,
        capital: Decimal,
        slippage_bps: int,
        fee_config: FeeConfig,
        bars_by_sym_tf: dict[tuple[str, str], list[Bar]],
        contracts: Optional[dict[str, ContractSpec]] = None,
        option_chain_warehouse: Optional[OptionChainWarehouse] = None,
    ) -> None:
        self.instance_id = instance_id
        self.mode = "backtest"
        self.capital_allocated = capital
        self.params = params
        self.state: dict = {}
        self._slippage = slippage_bps / 10000
        self._fees = fee_config
        self._bars = bars_by_sym_tf
        self._contracts = contracts or {}
        self._current_ts: Optional[datetime] = None
        self._cash: Decimal = capital
        # Signed net position per symbol (see engine/position_math.py)
        self._positions: dict[str, PositionState] = {}
        # Per-symbol last traded price, for mark-to-market. A single scalar
        # would silently mark every symbol at the last bar seen, whichever
        # instrument that happened to belong to.
        self._last_price: dict[str, Decimal] = {}
        self.closed_trades: list[ClosedTrade] = []
        self.equity_curve: list[float] = []
        self._orders: list[Order] = []
        self._pending: dict[str, Order] = {}
        self._chain = option_chain_warehouse
        # Symbols resolved at runtime via resolve_strike + subscribe_instrument
        # (options legs) -- the engine synthesizes a daily Tick for each of
        # these from the chain snapshot's close so on_tick-driven logic (e.g.
        # CP11's protective-order monitoring) actually runs in a backtest,
        # which is otherwise driven purely by on_bar. See BacktestEngine.run().
        self._dynamic_tick_symbols: dict[str, str] = {}  # symbol -> exchange

    def _multiplier(self, symbol: str) -> int:
        spec = self._contracts.get(symbol)
        return spec.multiplier if spec else 1

    def _set_time(self, bar: Bar) -> None:
        self._current_ts = bar.ts
        self._last_price[bar.symbol] = bar.close

    def _fee_for(self, side: Side, turnover: Decimal) -> Decimal:
        pct = self._fees.brokerage_pct + self._fees.other_pct
        if side == Side.SELL:
            pct += self._fees.stt_pct
        return turnover * Decimal(str(pct / 100))

    def _current_equity(self) -> Decimal:
        """Cash plus mark-to-market of all open positions.

        Previously this returned cash only, which made the equity curve flat
        for the whole time a position was open -- so max drawdown, Sharpe and
        Sortino were all computed off a curve that never moved mid-trade.
        """
        unrealised = Decimal("0")
        for sym, pos in self._positions.items():
            if pos.qty == 0:
                continue
            mark = self._last_price.get(sym, pos.avg_price)
            unrealised += Decimal(pos.qty) * mark * Decimal(self._multiplier(sym))
        return self._cash + unrealised

    async def place_order(self, request: OrderRequest) -> Order:
        now = self._current_ts or datetime.now(timezone.utc)
        slippage = Decimal(str(self._slippage))
        sym = request.symbol

        if request.order_type.value == "MARKET":
            # Simulate fill at this symbol's latest close +/- slippage
            base = request.price or self._last_price.get(sym) or Decimal("0")
            fill_price = base * (1 + slippage) if request.side == Side.BUY else base * (1 - slippage)
        else:
            fill_price = request.price or Decimal("0")

        mult = self._multiplier(sym)
        turnover = fill_price * request.quantity * mult
        fee = self._fee_for(request.side, turnover)

        # Cash moves the same way regardless of whether this fill opens, adds
        # to, reduces or reverses a position: a buy always debits, a sell
        # always credits. The old code special-cased "sell with no position"
        # by crediting cash and tracking nothing, which silently discarded
        # every short.
        if request.side == Side.BUY:
            self._cash -= turnover + fee
        else:
            self._cash += turnover - fee

        outcome = apply_fill(
            self._positions.get(sym),
            symbol=sym,
            side=request.side,
            quantity=request.quantity,
            price=fill_price,
            ts=now,
            multiplier=mult,
            tag=request.tag or "",
        )
        self._positions[sym] = outcome.state
        if outcome.closed_trade:
            # Charge the closing side's fee against the trade's P&L, prorated
            # when this fill only partially closed the position, so per-trade
            # P&L stays comparable to the fee-inclusive equity curve.
            closed_share = Decimal(outcome.closed_trade.quantity) / Decimal(request.quantity)
            outcome.closed_trade.pnl = float(
                Decimal(str(outcome.closed_trade.pnl)) - fee * closed_share
            )
            self.closed_trades.append(outcome.closed_trade)

        order = Order(
            client_order_id=request.client_order_id,
            symbol=sym,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.FILLED,
            submitted_at=now,
            updated_at=now,
            filled_quantity=request.quantity,
            avg_fill_price=fill_price,
            tag=request.tag,
            strategy_instance_id=self.instance_id,
        )
        self._orders.append(order)
        return order

    async def cancel_order(self, client_order_id: str) -> bool:
        return self._pending.pop(client_order_id, None) is not None

    async def modify_order(self, client_order_id: str, **changes) -> Order:
        order = self._pending.get(client_order_id)
        if order is None:
            raise ValueError(f"No pending order {client_order_id!r} to modify")
        for key, value in changes.items():
            if hasattr(order, key):
                setattr(order, key, value)
        return order

    def position(self, symbol: str) -> Optional[Position]:
        pos = self._positions.get(symbol)
        if not pos or pos.qty == 0:
            return None
        mark = self._last_price.get(symbol, pos.avg_price)
        mult = Decimal(self._multiplier(symbol))
        return Position(
            symbol=symbol,
            quantity=pos.qty,
            avg_price=pos.avg_price,
            realised_pnl=pos.realised_pnl,
            unrealised_pnl=(mark - pos.avg_price) * Decimal(pos.qty) * mult,
            last_price=mark,
        )

    def positions(self) -> list[Position]:
        out = [self.position(s) for s in self._positions]
        return [p for p in out if p is not None]

    def open_orders(self) -> list[Order]:
        return list(self._pending.values())

    def equity(self) -> Decimal:
        return self._current_equity()

    def realised_pnl_today(self) -> Decimal:
        return sum((Decimal(str(t.pnl)) for t in self.closed_trades), Decimal("0"))

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        bars = self._bars.get((symbol, timeframe), [])
        as_of = self._current_ts
        if as_of:
            bars = [b for b in bars if b.ts < as_of]
        return bars[-lookback:] if lookback < len(bars) else bars

    def log(self, level: str, message: str, **fields) -> None:
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(message, mode="backtest", **fields)

    async def now(self) -> datetime:
        if self._current_ts is None:
            raise RuntimeError("now() called before the first bar was processed")
        return self._current_ts

    async def notify_critical(self, title: str, body: str) -> None:
        # No Telegram in backtest mode -- a structured critical log line is
        # the whole channel (surfaced via the same structlog pipeline every
        # other backtest log line goes through).
        logger.critical(title, mode="backtest", detail=body)

    # ── Options resolution (Options Stage 2 / CP11 follow-up) ──────────────────

    def _current_date(self):
        if self._current_ts is None:
            raise RuntimeError("options resolution called before the first bar was processed")
        return self._current_ts.date()

    def _option_exchange(self, underlying: str) -> str:
        exchange = _BACKTEST_OPTION_EXCHANGE.get(underlying)
        if exchange is None:
            raise NotImplementedError(
                f"backtest options resolution doesn't support {underlying!r} -- only "
                f"{sorted(_BACKTEST_OPTION_EXCHANGE)} are resolvable via the free NSE "
                "Bhavcopy provider (NSE-listed derivatives only; Sensex is BSE-listed "
                "and isn't in this file)"
            )
        return exchange

    async def get_spot(self, underlying: str) -> Decimal:
        if self._chain is None:
            raise RuntimeError(
                "get_spot requires an option_chain_warehouse -- this backtest run "
                "wasn't configured for options (see BacktestEngine.run)"
            )
        exchange = self._option_exchange(underlying)
        price = await self._chain.get_underlying_price(underlying, exchange, self._current_date())
        if price is None:
            raise RuntimeError(
                f"no option chain data for {underlying!r} {exchange} on {self._current_date()} "
                "-- likely a non-trading day or a gap in the backfill"
            )
        return price

    async def resolve_strike(self, underlying: str, expiry_selector: str, strike_offset: int, opt_type: str):
        if self._chain is None:
            raise RuntimeError(
                "resolve_strike requires an option_chain_warehouse -- this backtest run "
                "wasn't configured for options (see BacktestEngine.run)"
            )
        exchange = self._option_exchange(underlying)
        day = self._current_date()
        chain_rows = await self._chain.get_chain(underlying, exchange, day)
        instrument_rows = [r.as_instrument_row() for r in chain_rows]
        return resolve_option(instrument_rows, underlying, expiry_selector, strike_offset, opt_type, await self.get_spot(underlying), as_of=day)

    async def get_option_price(self, symbol: str, exchange: str) -> Decimal:
        if self._chain is None:
            raise RuntimeError(
                "get_option_price requires an option_chain_warehouse -- this backtest run "
                "wasn't configured for options (see BacktestEngine.run)"
            )
        # get_close needs an underlying to scope its chain lookup, and this
        # call site only has a bare symbol/exchange -- scan the underlyings
        # this engine can resolve at all (small, fixed set) rather than
        # threading underlying through every StrategyContext caller.
        for candidate in _BACKTEST_OPTION_EXCHANGE:
            price = await self._chain.get_close(symbol, exchange, candidate, self._current_date())
            if price is not None:
                # Real bug found running the credit-spread strategy through
                # this end-to-end: a MARKET order for a freshly-resolved
                # option leg filled at price 0 the moment it was opened,
                # because place_order's MARKET-order fallback reads
                # self._last_price, which _set_time() only ever populates
                # for the bar-driven symbol -- a dynamically resolved leg
                # has no bar of its own. Caching the fetched close here (the
                # same "last known price" _dynamic_ticks_for_current_day
                # already caches after on_bar) means the very first order
                # for this symbol, placed within the SAME on_bar call that
                # just fetched this price, fills correctly instead of at 0.
                self._last_price[symbol] = price
                return price
        raise RuntimeError(f"no close price found for {symbol!r} on {exchange} for {self._current_date()}")

    async def subscribe_instrument(self, symbol: str, exchange: str) -> None:
        """Live mode subscribes real ticks; backtest instead remembers to
        synthesize a daily Tick for this symbol from its chain-snapshot
        close (see BacktestEngine.run) so on_tick-driven logic actually
        fires here too."""
        self._dynamic_tick_symbols[symbol] = exchange

    async def place_protective_gtt(
        self, symbol: str, exchange: str, side, quantity: int,
        stop_price, target_price, last_price,
    ):
        """No real broker in backtest mode -- the software stop (evaluated
        every synthesized tick, same as live) is the only protection here,
        same as it always was before this CP11 follow-up existed."""
        return None

    async def cancel_gtt(self, gtt_id: str) -> None:
        pass

    async def _dynamic_ticks_for_current_day(self) -> list[Tick]:
        if self._chain is None or not self._dynamic_tick_symbols:
            return []
        day = self._current_date()
        ticks: list[Tick] = []
        for symbol, exchange in self._dynamic_tick_symbols.items():
            for underlying in _BACKTEST_OPTION_EXCHANGE:
                price = await self._chain.get_close(symbol, exchange, underlying, day)
                if price is not None:
                    ticks.append(Tick(symbol=symbol, ltp=price, ltt=self._current_ts))
                    self._last_price[symbol] = price
                    break
        return ticks


class BacktestEngine:
    """Runs a strategy against historical data and returns BacktestResult."""

    async def run(
        self,
        strategy: Strategy,
        bars: list[Bar],
        instruments: list[str],
        timeframe: str,
        initial_capital: float,
        params: dict,
        slippage_bps: int = 5,
        fee_config: Optional[FeeConfig] = None,
        contracts: Optional[dict[str, ContractSpec]] = None,
        option_chain_warehouse: Optional[OptionChainWarehouse] = None,
    ) -> BacktestResult:
        if fee_config is None:
            fee_config = FeeConfig()

        run_id = str(uuid4())
        capital = Decimal(str(initial_capital))

        sorted_bars = sorted(bars, key=lambda b: b.ts)
        if not sorted_bars:
            return BacktestResult(
                run_id=run_id,
                strategy_name=strategy.name,
                params=params,
                instruments=instruments,
                timeframe=timeframe,
                from_ts=datetime.now(timezone.utc),
                to_ts=datetime.now(timezone.utc),
                initial_capital=initial_capital,
                slippage_bps=slippage_bps,
                metrics={},
                equity_curve=[],
                trades=[],
                status="failed",
                error="No bars provided",
            )

        bars_by_sym_tf: dict[tuple[str, str], list[Bar]] = {}
        for bar in sorted_bars:
            key = (bar.symbol, bar.timeframe)
            bars_by_sym_tf.setdefault(key, []).append(bar)

        ctx = _BacktestContext(
            instance_id=run_id,
            params=params,
            capital=capital,
            slippage_bps=slippage_bps,
            fee_config=fee_config,
            bars_by_sym_tf=bars_by_sym_tf,
            contracts=contracts,
            option_chain_warehouse=option_chain_warehouse,
        )

        ctx.equity_curve.append(float(capital))

        try:
            await strategy.on_start(ctx)
            for bar in sorted_bars:
                if bar.symbol not in instruments:
                    continue
                ctx._set_time(bar)
                await strategy.on_bar(bar, ctx)
                # Synthesize a daily Tick for any dynamically-resolved option
                # leg (see _BacktestContext.subscribe_instrument) so on_tick-
                # driven logic -- e.g. CP11's protective-order monitoring --
                # actually runs in a backtest, which otherwise only calls
                # on_bar. Matches bhavcopy's own daily granularity honestly;
                # this is not a claim of intraday accuracy.
                for tick in await ctx._dynamic_ticks_for_current_day():
                    await strategy.on_tick(tick, ctx)
                ctx.equity_curve.append(float(ctx.equity()))
            await strategy.on_stop(ctx, "backtest_complete")
        except Exception as exc:
            logger.error("backtest strategy raised exception", error=str(exc))
            return BacktestResult(
                run_id=run_id,
                strategy_name=strategy.name,
                params=params,
                instruments=instruments,
                timeframe=timeframe,
                from_ts=sorted_bars[0].ts,
                to_ts=sorted_bars[-1].ts,
                initial_capital=initial_capital,
                slippage_bps=slippage_bps,
                metrics={},
                equity_curve=ctx.equity_curve,
                trades=[],
                status="failed",
                error=str(exc),
            )

        metrics = compute_metrics(
            trades=ctx.closed_trades,
            equity_curve=ctx.equity_curve,
            initial_capital=initial_capital,
        )
        trades_dict = [
            {
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "quantity": t.quantity,
                "symbol": t.symbol,
                "side": t.side,
                "entry_ts": t.entry_ts.isoformat() if t.entry_ts else None,
                "exit_ts": t.exit_ts.isoformat() if t.exit_ts else None,
                "tag": t.tag,
            }
            for t in ctx.closed_trades
        ]

        return BacktestResult(
            run_id=run_id,
            strategy_name=strategy.name,
            params=params,
            instruments=instruments,
            timeframe=timeframe,
            from_ts=sorted_bars[0].ts,
            to_ts=sorted_bars[-1].ts,
            initial_capital=initial_capital,
            slippage_bps=slippage_bps,
            metrics=metrics,
            equity_curve=ctx.equity_curve,
            trades=trades_dict,
            status="done",
        )
