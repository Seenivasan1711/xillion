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

from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Side
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.engine.metrics import ClosedTrade, compute_metrics

logger = structlog.get_logger(__name__)


@dataclass
class FeeConfig:
    brokerage_pct: float = 0.03    # 0.03% of turnover
    stt_pct: float = 0.01          # STT 0.01% on sell side
    other_pct: float = 0.005       # exchange + regulatory


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


class _OpenPosition:
    def __init__(self, symbol: str, side: Side, qty: int, price: Decimal, ts: datetime, tag: str) -> None:
        self.symbol = symbol
        self.side = side
        self.qty = qty
        self.entry_price = price
        self.entry_ts = ts
        self.tag = tag


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
    ) -> None:
        self.instance_id = instance_id
        self.mode = "backtest"
        self.capital_allocated = capital
        self.params = params
        self.state: dict = {}
        self._slippage = slippage_bps / 10000
        self._fees = fee_config
        self._bars = bars_by_sym_tf
        self._current_ts: Optional[datetime] = None
        self._current_bar_close: Decimal = Decimal("0")
        self._cash: Decimal = capital
        self._open_positions: dict[str, _OpenPosition] = {}
        self._positions: dict[str, Position] = {}
        self.closed_trades: list[ClosedTrade] = []
        self.equity_curve: list[float] = []
        self._orders: list[Order] = []

    def _set_time(self, ts: datetime, bar_close: Decimal = Decimal("0")) -> None:
        self._current_ts = ts
        self._current_bar_close = bar_close

    def _current_equity(self) -> Decimal:
        unrealised = Decimal("0")
        for sym, pos in self._open_positions.items():
            # Use last known close as mark-to-market
            pass  # simplified: just use cash + realised for equity curve
        return self._cash

    async def place_order(self, request: OrderRequest) -> Order:
        now = self._current_ts or datetime.now(timezone.utc)
        slippage = Decimal(str(self._slippage))

        if request.order_type.value == "MARKET":
            # Simulate fill at current bar's close +/- slippage
            fill_price = request.price or self._current_bar_close or Decimal("0")
            if request.side == Side.BUY:
                fill_price = fill_price * (1 + slippage)
            else:
                fill_price = fill_price * (1 - slippage)
        else:
            fill_price = request.price or Decimal("0")

        # Compute fee
        turnover = fill_price * request.quantity
        fee = turnover * Decimal(str(
            self._fees.brokerage_pct / 100 + self._fees.stt_pct / 100 + self._fees.other_pct / 100
        ))

        # Update P&L
        sym = request.symbol
        if request.side == Side.BUY:
            self._cash -= turnover + fee
            existing = self._open_positions.get(sym)
            if existing:
                existing.qty += request.quantity
            else:
                self._open_positions[sym] = _OpenPosition(
                    sym, Side.BUY, request.quantity, fill_price, now, request.tag or ""
                )
        else:
            # Selling — close position
            open_pos = self._open_positions.get(sym)
            if open_pos:
                pnl = (fill_price - open_pos.entry_price) * min(request.quantity, open_pos.qty)
                pnl -= fee
                self._cash += turnover - fee
                self.closed_trades.append(
                    ClosedTrade(
                        pnl=float(pnl),
                        entry_price=float(open_pos.entry_price),
                        exit_price=float(fill_price),
                        quantity=request.quantity,
                    )
                )
                open_pos.qty -= request.quantity
                if open_pos.qty <= 0:
                    del self._open_positions[sym]
            else:
                self._cash += turnover - fee

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
        return False

    async def modify_order(self, client_order_id: str, **changes) -> Order:
        raise NotImplementedError

    def position(self, symbol: str) -> Optional[Position]:
        op = self._open_positions.get(symbol)
        if not op:
            return None
        return Position(
            symbol=symbol,
            quantity=op.qty,
            avg_price=op.entry_price,
            realised_pnl=Decimal("0"),
            unrealised_pnl=Decimal("0"),
            last_price=op.entry_price,
        )

    def positions(self) -> list[Position]:
        return [self.position(s) for s in self._open_positions if self.position(s)]

    def open_orders(self) -> list[Order]:
        return []

    def equity(self) -> Decimal:
        return self._cash

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
        )

        ctx.equity_curve.append(float(capital))

        try:
            await strategy.on_start(ctx)
            for bar in sorted_bars:
                if bar.symbol not in instruments:
                    continue
                ctx._set_time(bar.ts, bar.close)
                await strategy.on_bar(bar, ctx)
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
