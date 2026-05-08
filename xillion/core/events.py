"""
Canonical event and data types shared by all plugins and the framework.
Strategies and brokers must use ONLY these types — no redefining.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"           # SL-M
    STOP_LIMIT = "STOP_LIMIT"  # SL


class OrderStatus(str, Enum):
    PENDING = "PENDING"       # in our queue, not yet sent
    SUBMITTED = "SUBMITTED"   # sent to broker, awaiting ack
    ACCEPTED = "ACCEPTED"     # broker accepted, in market
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TimeInForce(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


@dataclass(frozen=True)
class Tick:
    symbol: str
    ltp: Decimal
    ltt: datetime
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    volume: Optional[int] = None
    oi: Optional[int] = None


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str       # "1m", "5m", "15m", "1h", "1d"
    ts: datetime         # bar open time
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
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    tif: TimeInForce = TimeInForce.DAY
    tag: Optional[str] = None
    strategy_instance_id: Optional[str] = None
    client_order_id: str = field(default_factory=lambda: str(uuid4()))


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
    broker_order_id: Optional[str] = None
    filled_quantity: int = 0
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    avg_fill_price: Optional[Decimal] = None
    rejection_reason: Optional[str] = None
    strategy_instance_id: Optional[str] = None
    tag: Optional[str] = None


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
    quantity: int          # signed: positive = long, negative = short
    avg_price: Decimal
    realised_pnl: Decimal
    unrealised_pnl: Decimal
    last_price: Decimal
    strategy_instance_id: Optional[str] = None
