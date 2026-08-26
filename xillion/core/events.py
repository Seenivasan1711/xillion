"""
Canonical event and data types shared by all plugins and the framework.
Strategies and brokers must use ONLY these types — no redefining.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"  # SL-M
    STOP_LIMIT = "STOP_LIMIT"  # SL


class OrderStatus(StrEnum):
    PENDING = "PENDING"  # in our queue, not yet sent
    SUBMITTED = "SUBMITTED"  # sent to broker, awaiting ack
    ACCEPTED = "ACCEPTED"  # broker accepted, in market
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TimeInForce(StrEnum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


@dataclass(frozen=True)
class Tick:
    symbol: str
    ltp: Decimal
    ltt: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int | None = None
    oi: int | None = None


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str  # "1m", "5m", "15m", "1h", "1d"
    ts: datetime  # bar open time
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass
class OrderRequest:
    """What a strategy asks for. Passes through Risk → Execution → Broker."""

    symbol: str
    side: Side
    quantity: int
    order_type: OrderType
    price: Decimal | None = None
    stop_price: Decimal | None = None
    tif: TimeInForce = TimeInForce.DAY
    tag: str | None = None
    strategy_instance_id: str | None = None
    client_order_id: str = field(default_factory=lambda: str(uuid4()))
    # Alert-mode-only fields (ignored by Risk/Execution/Broker -- alert mode
    # never reaches them, see _StrategyContextImpl._handle_alert_signal).
    # signal_type distinguishes an ENTER from the EXIT that later closes it;
    # target_price/stop_loss_price are informational levels shown in the
    # alert, not real broker stop orders (that's `stop_price`, above).
    signal_type: str | None = None
    target_price: Decimal | None = None
    stop_loss_price: Decimal | None = None


@dataclass
class Order:
    """An order as known to the system after submission."""

    client_order_id: str
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType
    status: OrderStatus
    submitted_at: datetime
    updated_at: datetime
    broker_order_id: str | None = None
    filled_quantity: int = 0
    price: Decimal | None = None
    stop_price: Decimal | None = None
    avg_fill_price: Decimal | None = None
    rejection_reason: str | None = None
    strategy_instance_id: str | None = None
    tag: str | None = None


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    fees: Decimal
    ts: datetime


@dataclass
class Position:
    symbol: str
    quantity: int  # signed: positive = long, negative = short
    avg_price: Decimal
    realised_pnl: Decimal
    unrealised_pnl: Decimal
    last_price: Decimal
    strategy_instance_id: str | None = None
