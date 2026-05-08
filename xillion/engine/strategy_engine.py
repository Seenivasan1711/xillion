"""
Strategy Engine: manages running strategy instances, spawns asyncio tasks per
instance, isolates crashes, and exposes state to the API layer.
"""
import asyncio
import pickle
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import structlog

from xillion.core.broker_base import Broker
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Tick
from xillion.core.execution import ExecutionRouter
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.bus import MarketDataBus
from xillion.data.history import HistoryManager

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _StrategyContextImpl(StrategyContext):
    """Concrete StrategyContext handed to strategy lifecycle hooks."""

    def __init__(
        self,
        instance_id: str,
        mode: str,
        capital_allocated: Decimal,
        params: dict,
        execution_router: ExecutionRouter,
        history_manager: HistoryManager,
    ) -> None:
        self.instance_id = instance_id
        self.mode = mode
        self.capital_allocated = capital_allocated
        self.params = params
        self.state: dict = {}
        self._router = execution_router
        self._history = history_manager
        self._positions: dict[str, Position] = {}

    async def place_order(self, request: OrderRequest) -> Order:
        request.strategy_instance_id = self.instance_id
        return await self._router.submit(request)

    async def cancel_order(self, client_order_id: str) -> bool:
        return await self._router.cancel(client_order_id)

    async def modify_order(self, client_order_id: str, **changes) -> Order:
        raise NotImplementedError("modify_order not yet implemented")

    def position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def open_orders(self) -> list[Order]:
        return self._router.get_open_orders(self.instance_id)

    def equity(self) -> Decimal:
        realised = sum(
            p.realised_pnl for p in self._positions.values()
        )
        unrealised = sum(
            p.unrealised_pnl for p in self._positions.values()
        )
        return self.capital_allocated + Decimal(str(realised)) + Decimal(str(unrealised))

    def realised_pnl_today(self) -> Decimal:
        return sum(
            (p.realised_pnl for p in self._positions.values()),
            Decimal("0"),
        )

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        return await self._history.get_bars(symbol, timeframe, lookback)

    def log(self, level: str, message: str, **fields) -> None:
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(message, instance_id=self.instance_id, **fields)

    def _update_position_from_order(self, order: Order) -> None:
        if order.status != OrderStatus.FILLED or order.avg_fill_price is None:
            return
        pos = self._positions.get(order.symbol)
        fill_price = order.avg_fill_price
        qty = order.filled_quantity if order.side.value == "BUY" else -order.filled_quantity

        if pos is None:
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=qty,
                avg_price=fill_price,
                realised_pnl=Decimal("0"),
                unrealised_pnl=Decimal("0"),
                last_price=fill_price,
                strategy_instance_id=self.instance_id,
            )
        else:
            if pos.quantity * qty >= 0:
                # Same direction: average in
                total_qty = pos.quantity + qty
                if total_qty != 0:
                    pos.avg_price = (
                        pos.avg_price * abs(pos.quantity) + fill_price * abs(qty)
                    ) / abs(total_qty)
                pos.quantity = total_qty
            else:
                # Reducing or reversing
                closed_qty = min(abs(pos.quantity), abs(qty))
                pnl = (fill_price - pos.avg_price) * closed_qty * (1 if pos.quantity > 0 else -1)
                pos.realised_pnl += pnl
                pos.quantity += qty
                if pos.quantity == 0:
                    pos.avg_price = Decimal("0")
            pos.last_price = fill_price


class StrategyRunner:
    """Manages one running strategy instance."""

    def __init__(
        self,
        instance_id: str,
        strategy: Strategy,
        context: _StrategyContextImpl,
        bus: MarketDataBus,
        instruments: list[str],
        timeframe: str,
    ) -> None:
        self._instance_id = instance_id
        self._strategy = strategy
        self._ctx = context
        self._bus = bus
        self._instruments = instruments
        self._timeframe = timeframe
        self._task: Optional[asyncio.Task] = None
        self.status: str = "idle"
        self.last_error: Optional[str] = None

    async def start(self) -> None:
        self.status = "running"
        try:
            await self._strategy.on_start(self._ctx)
            for sym in self._instruments:
                self._bus.subscribe_bars(sym, self._timeframe, self._handle_bar)
                self._bus.subscribe_ticks(sym, self._handle_tick)
            logger.info("strategy started", instance_id=self._instance_id)
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            logger.error("strategy on_start failed", instance_id=self._instance_id, error=str(exc))

    async def stop(self, reason: str = "stopped") -> None:
        for sym in self._instruments:
            self._bus.unsubscribe_bars(sym, self._timeframe, self._handle_bar)
            self._bus.unsubscribe_ticks(sym, self._handle_tick)
        try:
            await self._strategy.on_stop(self._ctx, reason)
        except Exception as exc:
            logger.error("strategy on_stop failed", instance_id=self._instance_id, error=str(exc))
        self.status = "idle"
        logger.info("strategy stopped", instance_id=self._instance_id, reason=reason)

    async def _handle_bar(self, bar: Bar) -> None:
        try:
            await self._strategy.on_bar(bar, self._ctx)
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            logger.error(
                "strategy on_bar raised exception",
                instance_id=self._instance_id,
                symbol=bar.symbol,
                error=str(exc),
            )

    async def _handle_tick(self, tick: Tick) -> None:
        try:
            await self._strategy.on_tick(tick, self._ctx)
        except Exception as exc:
            logger.error(
                "strategy on_tick raised exception",
                instance_id=self._instance_id,
                error=str(exc),
            )


class StrategyEngine:
    """Registry of all running strategy instances."""

    def __init__(self, bus: MarketDataBus, risk_manager: RiskManager) -> None:
        self._bus = bus
        self._risk = risk_manager
        self._runners: dict[str, StrategyRunner] = {}
        self._registry: Optional[PluginRegistry] = None

    def set_registry(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def spawn(
        self,
        instance_id: str,
        strategy_name: str,
        broker: Broker,
        instruments: list[str],
        timeframe: str,
        capital: Decimal,
        params: dict,
        mode: str = "paper",
    ) -> StrategyRunner:
        if self._registry is None:
            raise RuntimeError("PluginRegistry not set on StrategyEngine")
        cls = self._registry.strategies.get(strategy_name)
        if cls is None:
            raise ValueError(f"Strategy '{strategy_name}' not found in registry")

        router = ExecutionRouter(broker, self._risk)
        history = HistoryManager()
        ctx = _StrategyContextImpl(
            instance_id=instance_id,
            mode=mode,
            capital_allocated=capital,
            params=params,
            execution_router=router,
            history_manager=history,
        )
        strategy = cls()
        runner = StrategyRunner(
            instance_id=instance_id,
            strategy=strategy,
            context=ctx,
            bus=self._bus,
            instruments=instruments,
            timeframe=timeframe,
        )
        self._runners[instance_id] = runner
        await runner.start()
        return runner

    async def stop_instance(self, instance_id: str, reason: str = "stopped") -> None:
        runner = self._runners.get(instance_id)
        if runner:
            await runner.stop(reason)
            del self._runners[instance_id]

    def get_runner(self, instance_id: str) -> Optional[StrategyRunner]:
        return self._runners.get(instance_id)

    def list_runners(self) -> list[StrategyRunner]:
        return list(self._runners.values())
