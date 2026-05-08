"""
DummyBroker — records all calls for testing. Not discovered by the plugin loader
(underscore prefix). Import directly in tests.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator
from uuid import uuid4

from xillion.core.broker_base import Broker, BrokerCapabilities
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Tick


class DummyBroker(Broker):
    """Records every call for test assertions. Always fills market orders instantly."""

    name = "Dummy"
    version = "1.0.0"
    capabilities = BrokerCapabilities()

    def __init__(self, default_fill_price: Decimal = Decimal("100")) -> None:
        self._fill_price = default_fill_price
        self.calls: list[tuple[str, dict]] = []
        self.placed_orders: list[Order] = []

    def _record(self, method: str, **kwargs) -> None:
        self.calls.append((method, kwargs))

    async def connect(self, credentials: dict) -> None:
        self._record("connect", credentials=credentials)

    async def disconnect(self) -> None:
        self._record("disconnect")

    async def healthcheck(self) -> bool:
        self._record("healthcheck")
        return True

    async def is_connected(self) -> bool:
        return True

    async def get_positions(self) -> list[Position]:
        return []

    async def get_holdings(self) -> list[dict]:
        return []

    async def get_margins(self) -> dict:
        return {"available": 999_999_999}

    async def place_order(self, request: OrderRequest) -> Order:
        self._record("place_order", request=request)
        now = datetime.now(timezone.utc)
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
            avg_fill_price=request.price or self._fill_price,
            tag=request.tag,
            strategy_instance_id=request.strategy_instance_id,
        )
        self.placed_orders.append(order)
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        self._record("cancel_order", broker_order_id=broker_order_id)
        return True

    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        raise NotImplementedError

    async def get_order(self, broker_order_id: str) -> Order:
        raise NotImplementedError

    async def get_orders_today(self) -> list[Order]:
        return self.placed_orders.copy()

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        self._record("subscribe_ticks", symbols=symbols)

    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        self._record("unsubscribe_ticks", symbols=symbols)

    async def tick_stream(self) -> AsyncIterator[Tick]:
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
            sym: Tick(symbol=sym, ltp=self._fill_price, ltt=now)
            for sym in symbols
        }
