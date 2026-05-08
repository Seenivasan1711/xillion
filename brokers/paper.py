"""
PaperBroker — simulates live trading using real market ticks with fake fills.
Phase 3+ will connect this to a real broker's WebSocket for live tick data.
For now (Phase 1-2) it uses the BacktestBroker's fill logic.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, Optional
from uuid import uuid4

from xillion.core.broker_base import Broker, BrokerCapabilities
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Tick


class PaperBroker(Broker):
    """
    Paper trading broker. Accepts orders, simulates immediate fills.
    In Phase 3+, wire tick_stream() to a real broker's WebSocket.
    """

    name = "Paper"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_websocket=True,
        supports_historical=False,
        supports_bracket_orders=False,
        supports_modify_order=False,
    )

    def __init__(self, slippage_bps: int = 10) -> None:
        self._slippage = slippage_bps / 10000
        self._connected = False
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._last_prices: dict[str, Decimal] = {}

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
        return {"available": 999_999_999, "note": "paper mode"}

    async def place_order(self, request: OrderRequest) -> Order:
        now = datetime.now(timezone.utc)
        from xillion.core.events import Side

        last_price = self._last_prices.get(request.symbol, Decimal("0"))
        fill_price = request.price or last_price

        if request.order_type.value == "MARKET":
            if request.side == Side.BUY:
                fill_price = fill_price * Decimal(str(1 + self._slippage))
            else:
                fill_price = fill_price * Decimal(str(1 - self._slippage))

        order = Order(
            client_order_id=request.client_order_id,
            broker_order_id=f"PAPER-{uuid4().hex[:8].upper()}",
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
        raise NotImplementedError

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
        # Phase 3: connect to real broker WebSocket and yield live ticks
        return
        yield

    async def order_event_stream(self) -> AsyncIterator[Order]:
        return
        yield

    async def get_history(self, symbol: str, timeframe: str, from_ts, to_ts) -> list[Bar]:
        return []

    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        now = datetime.now(timezone.utc)
        return {
            sym: Tick(
                symbol=sym,
                ltp=self._last_prices.get(sym, Decimal("0")),
                ltt=now,
            )
            for sym in symbols
            if sym in self._last_prices
        }

    def on_tick(self, tick: Tick) -> None:
        """Update last known price (called externally by the data bus in live mode)."""
        self._last_prices[tick.symbol] = tick.ltp
