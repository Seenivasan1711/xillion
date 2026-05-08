"""
BacktestBroker — built-in broker for backtesting.
Deterministic, no network calls, replays historical bars.
This broker is used by the BacktestEngine, not directly by strategies.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, Optional
from uuid import uuid4

from xillion.core.broker_base import Broker, BrokerCapabilities
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Tick


class BacktestBroker(Broker):
    """
    Deterministic broker for backtests. The BacktestEngine drives it directly;
    strategies never instantiate this — they use the context injected by the engine.
    """

    name = "Backtest"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_websocket=False,
        supports_historical=True,
        supports_bracket_orders=False,
        supports_modify_order=False,
    )

    def __init__(self, slippage_bps: int = 5) -> None:
        self._slippage = slippage_bps / 10000
        self._connected = False
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._bars: list[Bar] = []
        self._current_index: int = 0

    async def connect(self, credentials: dict) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def healthcheck(self) -> bool:
        return self._connected

    async def is_connected(self) -> bool:
        return self._connected

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_holdings(self) -> list[dict]:
        return []

    async def get_margins(self) -> dict:
        return {"available": 0}

    async def place_order(self, request: OrderRequest) -> Order:
        now = datetime.now(timezone.utc)
        fill_price = request.price or Decimal("0")
        if request.order_type.value == "MARKET":
            from xillion.core.events import Side
            if request.side == Side.BUY:
                fill_price = fill_price * Decimal(str(1 + self._slippage))
            else:
                fill_price = fill_price * Decimal(str(1 - self._slippage))

        order = Order(
            client_order_id=request.client_order_id,
            broker_order_id=str(uuid4()),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.FILLED,
            submitted_at=now,
            updated_at=now,
            filled_quantity=request.quantity,
            avg_fill_price=fill_price,
            tag=request.tag,
            strategy_instance_id=request.strategy_instance_id,
        )
        self._orders[order.client_order_id] = order
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        return False

    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        raise NotImplementedError("BacktestBroker does not support modify_order")

    async def get_order(self, broker_order_id: str) -> Order:
        for o in self._orders.values():
            if o.broker_order_id == broker_order_id:
                return o
        raise ValueError(f"Order {broker_order_id} not found")

    async def get_orders_today(self) -> list[Order]:
        return list(self._orders.values())

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        pass

    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        pass

    async def tick_stream(self) -> AsyncIterator[Tick]:
        return
        yield  # make it a generator

    async def order_event_stream(self) -> AsyncIterator[Order]:
        return
        yield

    async def get_history(
        self, symbol: str, timeframe: str, from_ts, to_ts
    ) -> list[Bar]:
        return [
            b
            for b in self._bars
            if b.symbol == symbol
            and b.timeframe == timeframe
            and from_ts <= b.ts <= to_ts
        ]

    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        return {}
