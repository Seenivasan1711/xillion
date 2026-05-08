# 04 — Plugin Contracts

This is the most important technical document in this set. The whole "drop a file to add a strategy or broker" idea hangs on these two interfaces being clean and stable. **Treat them as a public API**: changes here ripple through every plugin.

## 1. Design tenets for the contracts

1. **Small surface, big leverage.** Few methods, each pulling its weight.
2. **No leakage.** A strategy never imports anything from a specific broker. A broker never knows what a strategy is.
3. **Same shape across modes.** A `Bar` looks the same in backtest and live. An `OrderRequest` looks the same.
4. **Async first.** The whole runtime is async. Plugins implement async methods.
5. **Fail gracefully.** Plugin errors should be catchable and reportable, never crash the host.

## 2. Common types (used by both contracts)

These live in `algotrader/core/events.py`. No plugin should redefine them.

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"           # SL-M
    STOP_LIMIT = "STOP_LIMIT"  # SL

class OrderStatus(str, Enum):
    PENDING = "PENDING"     # in our queue, not yet sent
    SUBMITTED = "SUBMITTED" # sent to broker, awaiting ack
    ACCEPTED = "ACCEPTED"   # broker accepted, in market
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
    timeframe: str           # "1m", "5m", "1h", "1d"
    ts: datetime             # bar open time
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

@dataclass
class OrderRequest:
    """What a strategy asks for. Brokers receive these via Risk → Execution."""
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType
    price: Optional[Decimal] = None         # for LIMIT, STOP_LIMIT
    stop_price: Optional[Decimal] = None    # for STOP, STOP_LIMIT
    tif: TimeInForce = TimeInForce.DAY
    tag: Optional[str] = None               # strategy-defined, for tracking

    # Filled by the framework, not the strategy
    strategy_instance_id: Optional[str] = None
    client_order_id: Optional[str] = None   # idempotency key

@dataclass
class Order:
    """An order as known to the system after submission."""
    client_order_id: str
    broker_order_id: Optional[str]
    symbol: str
    side: Side
    quantity: int
    filled_quantity: int
    order_type: OrderType
    price: Optional[Decimal]
    stop_price: Optional[Decimal]
    status: OrderStatus
    avg_fill_price: Optional[Decimal]
    submitted_at: datetime
    updated_at: datetime
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
    quantity: int            # signed: positive = long, negative = short
    avg_price: Decimal
    realised_pnl: Decimal
    unrealised_pnl: Decimal
    last_price: Decimal
```

## 3. The Strategy contract

A strategy lives at `strategies/<name>.py`. It must define exactly one class that subclasses `Strategy`. The framework will instantiate it.

```python
# algotrader/core/strategy_base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from algotrader.core.events import Bar, Tick, Order, OrderRequest, Position, Side, OrderType

@dataclass
class ParamSpec:
    """Schema entry for one configurable parameter."""
    name: str
    type: str                      # "int", "float", "str", "bool", "choice"
    default: Any
    description: str = ""
    min: Optional[float] = None    # for numeric types
    max: Optional[float] = None
    choices: Optional[list] = None # for "choice"

class StrategyContext:
    """
    The framework injects this into every strategy lifecycle call.
    It's the strategy's window into the world: order placement,
    position queries, history access, logging, state.

    Strategies use ONLY this context — never import brokers directly.
    """
    instance_id: str               # unique per running strategy instance
    mode: str                      # "backtest" | "paper" | "live"
    capital_allocated: Decimal
    params: dict                   # current parameter values (from DB)

    # ---- Order management ----
    async def place_order(self, request: OrderRequest) -> Order: ...
    async def cancel_order(self, client_order_id: str) -> bool: ...
    async def modify_order(self, client_order_id: str, **changes) -> Order: ...

    # ---- Convenience helpers (sugar over place_order) ----
    async def buy(self, symbol: str, qty: int, *, price: Optional[Decimal] = None,
                  tag: str = None) -> Order: ...
    async def sell(self, symbol: str, qty: int, *, price: Optional[Decimal] = None,
                   tag: str = None) -> Order: ...

    # ---- State queries ----
    def position(self, symbol: str) -> Optional[Position]: ...
    def positions(self) -> list[Position]: ...
    def open_orders(self) -> list[Order]: ...
    def equity(self) -> Decimal: ...
    def realised_pnl_today(self) -> Decimal: ...

    # ---- Historical data ----
    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        """Returns up to `lookback` bars ending at the current moment.
        In backtest, returns up to current simulated moment (no lookahead)."""
        ...

    # ---- Logging ----
    def log(self, level: str, message: str, **fields) -> None:
        """Structured log; appears in UI, audit log, and Telegram if configured."""
        ...

    # ---- Persistent state ----
    state: dict   # pickled to DB on `on_stop`, restored on `on_start`

class Strategy(ABC):
    """
    The plugin contract. Every strategy file must export a class
    inheriting from this.
    """

    # ---- Class-level metadata ----
    name: str = ""                    # human-readable, must be unique
    version: str = "0.0.1"
    description: str = ""
    author: str = ""
    timeframe: str = "5m"             # default bar timeframe to subscribe to
    instruments: list[str] = []       # default instruments (overridable per instance)

    # Parameter schema — drives the UI form
    params_schema: list[ParamSpec] = []

    # ---- Lifecycle hooks (override what you need) ----

    async def on_start(self, ctx: StrategyContext) -> None:
        """Called once when the strategy instance starts.
        Use to load extra data, validate params, prep state."""
        return None

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        """Called when a new bar closes for a subscribed (symbol, timeframe).
        This is where most strategies live."""
        return None

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        """Called on every tick for subscribed symbols.
        Override only if you need sub-bar reactivity (e.g., trailing stops)."""
        return None

    async def on_order_update(self, order: Order, ctx: StrategyContext) -> None:
        """Called when one of THIS strategy's orders changes status."""
        return None

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        """Called when stopping (graceful shutdown, kill switch, error pause).
        Use to clean up. ctx.state is auto-persisted after this returns."""
        return None
```

### Example strategy — minimal SMA crossover

```python
# strategies/example_sma_cross.py
from decimal import Decimal
from algotrader.core.strategy_base import Strategy, StrategyContext, ParamSpec
from algotrader.core.events import Bar

class SMACrossStrategy(Strategy):
    name = "SMA Cross"
    version = "1.0.0"
    description = "Buy on fast SMA crossing slow SMA from below; sell on opposite."
    author = "you"
    timeframe = "15m"

    params_schema = [
        ParamSpec("fast", "int", default=10, min=2, max=200),
        ParamSpec("slow", "int", default=30, min=5, max=500),
        ParamSpec("qty", "int", default=1, min=1),
    ]

    async def on_start(self, ctx):
        ctx.state.setdefault("position", "flat")
        ctx.log("info", "SMA Cross started",
                fast=ctx.params["fast"], slow=ctx.params["slow"])

    async def on_bar(self, bar, ctx):
        bars = await ctx.history(bar.symbol, "15m", lookback=ctx.params["slow"] + 2)
        if len(bars) < ctx.params["slow"] + 1:
            return  # warmup

        closes = [float(b.close) for b in bars]
        fast = sum(closes[-ctx.params["fast"]:]) / ctx.params["fast"]
        slow = sum(closes[-ctx.params["slow"]:]) / ctx.params["slow"]
        prev_closes = closes[:-1]
        prev_fast = sum(prev_closes[-ctx.params["fast"]:]) / ctx.params["fast"]
        prev_slow = sum(prev_closes[-ctx.params["slow"]:]) / ctx.params["slow"]

        crossed_up = prev_fast <= prev_slow and fast > slow
        crossed_down = prev_fast >= prev_slow and fast < slow

        pos = ctx.position(bar.symbol)
        qty = ctx.params["qty"]

        if crossed_up and (pos is None or pos.quantity == 0):
            await ctx.buy(bar.symbol, qty, tag="entry")
            ctx.state["position"] = "long"
        elif crossed_down and pos and pos.quantity > 0:
            await ctx.sell(bar.symbol, pos.quantity, tag="exit")
            ctx.state["position"] = "flat"
```

That's it. **No imports of brokers, no mode-checking code, no risk-management code.** The strategy is the same in backtest, paper, and live.

## 4. The Broker contract

Brokers live at `brokers/<name>.py`. Each file exports one class subclassing `Broker`.

```python
# algotrader/core/broker_base.py

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import AsyncIterator, Optional
from algotrader.core.events import (
    Tick, Bar, Order, OrderRequest, Position
)

class BrokerCapabilities:
    """Each broker declares what it supports. The system uses these
    to disable UI features that the broker can't do."""
    supports_websocket: bool = True
    supports_historical: bool = True
    supports_bracket_orders: bool = False
    supports_cover_orders: bool = False
    supports_modify_order: bool = True
    supports_partial_fills: bool = True
    supported_timeframes: list[str] = ["1m", "5m", "15m", "30m", "1h", "1d"]
    supported_exchanges: list[str] = ["NSE", "BSE", "NFO", "MCX"]

class Broker(ABC):
    """The broker plugin contract."""

    name: str = ""           # human-readable, unique
    version: str = "0.0.1"
    capabilities: BrokerCapabilities = BrokerCapabilities()

    # ---- Lifecycle ----

    @abstractmethod
    async def connect(self, credentials: dict) -> None:
        """Authenticate and establish session.
        `credentials` comes from env/DB; broker decides what keys it needs."""
        ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Quick liveness check. Returns False if reconnect needed."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

    # ---- Account ----

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_holdings(self) -> list[dict]: ...   # broker-shaped

    @abstractmethod
    async def get_margins(self) -> dict: ...          # broker-shaped

    # ---- Orders ----

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> Order: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool: ...

    @abstractmethod
    async def modify_order(self, broker_order_id: str, **changes) -> Order: ...

    @abstractmethod
    async def get_order(self, broker_order_id: str) -> Order: ...

    @abstractmethod
    async def get_orders_today(self) -> list[Order]: ...

    # ---- Market data ----

    @abstractmethod
    async def subscribe_ticks(self, symbols: list[str]) -> None: ...

    @abstractmethod
    async def unsubscribe_ticks(self, symbols: list[str]) -> None: ...

    @abstractmethod
    def tick_stream(self) -> AsyncIterator[Tick]:
        """Yields Tick objects for all subscribed symbols.
        The framework consumes this and forwards to the data bus."""
        ...

    @abstractmethod
    async def order_event_stream(self) -> AsyncIterator[Order]:
        """Yields order updates as they arrive (postbacks, status changes)."""
        ...

    @abstractmethod
    async def get_history(
        self,
        symbol: str,
        timeframe: str,
        from_ts,
        to_ts,
    ) -> list[Bar]: ...

    @abstractmethod
    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]: ...
```

### Example broker — Zerodha sketch

```python
# brokers/zerodha.py
from kiteconnect import KiteConnect, KiteTicker
from algotrader.core.broker_base import Broker, BrokerCapabilities
from algotrader.core.events import OrderRequest, Order, OrderStatus, OrderType, Side

class ZerodhaBroker(Broker):
    name = "Zerodha"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_bracket_orders=True,
        supports_cover_orders=True,
    )

    def __init__(self):
        self._kite: KiteConnect | None = None
        self._ticker: KiteTicker | None = None
        self._access_token: str | None = None

    async def connect(self, credentials: dict) -> None:
        api_key = credentials["api_key"]
        api_secret = credentials["api_secret"]
        request_token = credentials.get("request_token")  # from auto-login flow

        self._kite = KiteConnect(api_key=api_key)
        if request_token:
            session = self._kite.generate_session(request_token, api_secret)
            self._access_token = session["access_token"]
            self._kite.set_access_token(self._access_token)
            # Cache token to disk so we don't re-login every restart;
            # tokens expire ~6 AM IST so we still need a daily refresh job.

        self._ticker = KiteTicker(api_key, self._access_token)
        # ... wire up callbacks, start ticker on a thread or asyncio loop ...

    async def place_order(self, request: OrderRequest) -> Order:
        kite_args = self._translate_to_kite(request)
        broker_order_id = self._kite.place_order(**kite_args)
        return Order(
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=0,
            order_type=request.order_type,
            price=request.price,
            stop_price=request.stop_price,
            status=OrderStatus.SUBMITTED,
            avg_fill_price=None,
            submitted_at=now_utc(),
            updated_at=now_utc(),
            tag=request.tag,
            strategy_instance_id=request.strategy_instance_id,
        )

    # ... other methods translate between our types and Kite's API
```

The key insight: **the strategy doesn't see this code at all.** Its `ctx.buy()` becomes an `OrderRequest`, which the Risk Manager approves, which the Execution Router hands to whichever broker the instance is configured with.

## 5. The plugin loader

Pseudocode for the loader:

```python
def discover_strategies(folder: Path) -> dict[str, type[Strategy]]:
    found = {}
    for py_file in folder.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module = import_module(py_file)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Strategy) and obj is not Strategy:
                validate_strategy_class(obj)
                found[obj.name or obj.__name__] = obj
    return found
```

`validate_strategy_class` checks:
- `name` is non-empty and unique
- `params_schema` is well-formed
- `on_bar` is implemented (warns if not, since most strategies need it)

Brokers are discovered the same way.

## 6. Versioning the contracts

These contracts are part of the public-ish surface. When they change:

- **Additive change** (new optional method, new optional field): bump `algotrader.__version__` patch; keep backward compat.
- **Breaking change**: bump minor; document migration in `CHANGELOG.md`; provide a checker script that scans existing plugins for incompatibilities.

For v1 development, treat contracts as **soft frozen after Phase 1** in the progress tracker. Add things rather than changing existing things.

## 7. What plugin authors do NOT do

To make sure the abstractions stay clean:

- Strategies do **not** import `brokers/` or `kiteconnect`.
- Strategies do **not** call `RiskManager` directly — it's invoked automatically inside `ctx.place_order`.
- Brokers do **not** import strategies.
- Brokers do **not** persist anything to the main DB. They may keep their own caches/files but state-of-truth lives in the framework's DB.
- Plugins do **not** spawn their own threads / loops. The framework owns concurrency.

If you find yourself wanting to do any of the above, the abstraction probably needs a new hook — add it once in the contract, not in one plugin.
