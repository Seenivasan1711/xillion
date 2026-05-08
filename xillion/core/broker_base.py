"""
Broker plugin contract. Each broker file must export one class inheriting
from Broker. The framework calls these; strategies never import brokers directly.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

from xillion.core.events import Bar, Order, OrderRequest, Position, Tick


@dataclass
class BrokerCapabilities:
    """Declares what a broker supports. Disables unsupported UI features."""
    supports_websocket: bool = True
    supports_historical: bool = True
    supports_bracket_orders: bool = False
    supports_cover_orders: bool = False
    supports_modify_order: bool = True
    supports_partial_fills: bool = True
    supported_timeframes: list[str] = field(
        default_factory=lambda: ["1m", "5m", "15m", "30m", "1h", "1d"]
    )
    supported_exchanges: list[str] = field(
        default_factory=lambda: ["NSE", "BSE", "NFO", "MCX"]
    )


class Broker(ABC):
    """Broker plugin contract."""

    name: str = ""
    version: str = "0.0.1"
    capabilities: BrokerCapabilities = field(default_factory=BrokerCapabilities)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def connect(self, credentials: dict) -> None:
        """Authenticate and establish session. credentials comes from env/DB."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Quick liveness check. Returns False if reconnect is needed."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        ...

    # ── Account ────────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_holdings(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_margins(self) -> dict:
        ...

    # ── Orders ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> Order:
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        ...

    @abstractmethod
    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        ...

    @abstractmethod
    async def get_order(self, broker_order_id: str) -> Order:
        ...

    @abstractmethod
    async def get_orders_today(self) -> list[Order]:
        ...

    # ── Market data ────────────────────────────────────────────────────────────

    @abstractmethod
    async def subscribe_ticks(self, symbols: list[str]) -> None:
        ...

    @abstractmethod
    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        ...

    @abstractmethod
    def tick_stream(self) -> AsyncIterator[Tick]:
        """Yields Tick objects for all subscribed symbols."""
        ...

    @abstractmethod
    async def order_event_stream(self) -> AsyncIterator[Order]:
        """Yields order updates as they arrive."""
        ...

    @abstractmethod
    async def get_history(
        self,
        symbol: str,
        timeframe: str,
        from_ts,
        to_ts,
    ) -> list[Bar]:
        ...

    @abstractmethod
    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        ...
