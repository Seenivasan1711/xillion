"""
MT5 (Funding Pips) broker plugin -- Gold Lane B1's broker. Drop this file
in brokers/ -- it is auto-discovered on startup, same as zerodha.py/dhan.py.

Structurally different from those two, and deliberately so: the official
MetaTrader5 Python package only works by talking to a real MT5 desktop
terminal running ON THE SAME MACHINE. xillion's backend runs on Render (a
Linux container) -- it can never run that terminal, or call it directly,
no matter how this file is written.

So this broker doesn't hold a live connection to anything. It queues work
into xillion's own DB (mt5_pending_order / mt5_bridge_tick /
mt5_bridge_state, migration 014) and a separate local process --
mt5_bridge/bridge.py, run on whichever machine has the real MT5 terminal
open and logged into your Funding Pips account -- polls
GET /api/mt5-bridge/poll for work, executes it against the real terminal,
and reports back via POST /api/mt5-bridge/report (xillion/api/mt5_bridge.py
wires those into this broker's in-memory queues so tick_stream()/
order_event_stream() react immediately, not just on the next DB read).
Same "local process talks to the real backend over its own REST API" shape
xillion-mcp already uses.

Quantity/lot convention: MT5 lot sizes are fractional (0.01, 0.1, 1.0 ...)
but OrderRequest.quantity is int project-wide -- changing that globally for
one broker's sake would be a much bigger, riskier change than this
strategy needs. Instead this broker treats OrderRequest.quantity as
MICRO-LOTS (hundredths of a lot): quantity=100 -> 1.00 lot, quantity=1 ->
0.01 lot (MT5's own minimum on most symbols). Documented here, not hidden;
see _quantity_to_lots/_lots_to_quantity below.

Known gap, not hidden: get_history() is not implemented. Live/paper price
data flows from the bridge's tick reports (real, from your real Funding
Pips terminal); a historical OHLC feed for backtesting Gold is separate
data-acquisition work (Stage 2 of the asset pipeline), not needed for
Stage 1 (this file) or Stage 3 (paper trading) to work.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import structlog

from xillion.core.broker_base import Broker, BrokerCapabilities
from xillion.core.events import (
    Bar,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    Side,
    Tick,
)

logger = structlog.get_logger(__name__)

# MT5's own minimum lot step on most symbols (including XAUUSD at Funding
# Pips) is 0.01 -- one "micro-lot" in this file's own convention, not an
# MT5/industry-standard term.
_MICRO_LOTS_PER_LOT = Decimal("100")


def _quantity_to_lots(quantity: int) -> Decimal:
    return Decimal(quantity) / _MICRO_LOTS_PER_LOT


def _lots_to_quantity(lots: Decimal) -> int:
    return int((lots * _MICRO_LOTS_PER_LOT).to_integral_value())


class MT5FundingPipsBroker(Broker):
    name = "MT5 Funding Pips"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_websocket=False,  # ticks arrive via bridge polling, not a live socket
        supports_historical=False,  # see module docstring
        supports_bracket_orders=False,
        supports_cover_orders=False,
        supports_gtt_orders=False,
        supports_modify_order=True,
        supports_partial_fills=False,  # MT5 market/limit fills are all-or-nothing in practice here
        supported_timeframes=["1m", "5m", "15m", "30m", "1h", "1d"],
        supported_exchanges=["MT5"],
    )

    # Bridge polling reports state at least this often when healthy --
    # healthcheck() treats a longer silence as "bridge is down" (terminal
    # closed, your machine asleep, etc), not a xillion-side failure.
    _STALE_AFTER_SECONDS = 120

    def __init__(self, session_factory=None, connection_name: str | None = None) -> None:
        if session_factory is None:
            from xillion.db.session import get_session_factory

            session_factory = get_session_factory()
        self._factory = session_factory
        self._connection_name = connection_name or self.name
        self._connected = False
        self._subscribed: set[str] = set()
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=5000)
        self._order_queue: asyncio.Queue[Order] = asyncio.Queue(maxsize=1000)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self, credentials: dict) -> None:
        # No real network call -- the bridge owns the actual MT5 login, on
        # its own machine, with credentials that never reach this backend.
        # "Connected" here just means "ready to queue/serve work"; real
        # liveness is healthcheck()'s job.
        self._connected = True
        logger.info("mt5 broker: ready", connection_name=self._connection_name)

    async def disconnect(self) -> None:
        self._connected = False

    async def healthcheck(self) -> bool:
        state = await self._get_state()
        if state is None:
            return False
        updated_at = datetime.fromisoformat(state["updated_at"])
        age = (datetime.now(UTC) - updated_at).total_seconds()
        return age < self._STALE_AFTER_SECONDS

    async def is_connected(self) -> bool:
        return self._connected

    # ── Account ────────────────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        state = await self._get_state()
        if state is None:
            return []
        return [
            Position(
                symbol=p["symbol"],
                quantity=int(p["quantity"]),
                avg_price=Decimal(str(p["avg_price"])),
                realised_pnl=Decimal(str(p.get("realised_pnl", "0"))),
                unrealised_pnl=Decimal(str(p.get("unrealised_pnl", "0"))),
                last_price=Decimal(str(p["last_price"])),
            )
            for p in json.loads(state["positions_json"])
        ]

    async def get_holdings(self) -> list[dict]:
        return []  # forex/CFD accounts don't hold delivery-settled positions

    async def get_margins(self) -> dict:
        state = await self._get_state()
        if state is None:
            return {}
        return json.loads(state["margins_json"])

    # ── Orders ─────────────────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> Order:
        from xillion.db.models import MT5PendingOrder

        now = datetime.now(UTC).isoformat()
        async with self._factory() as db:
            db.add(
                MT5PendingOrder(
                    broker_connection_name=self._connection_name,
                    client_order_id=request.client_order_id,
                    symbol=request.symbol,
                    side=request.side.value,
                    quantity=str(_quantity_to_lots(request.quantity)),
                    order_type=request.order_type.value,
                    price=str(request.price) if request.price is not None else None,
                    stop_loss=str(request.stop_price) if request.stop_price is not None else None,
                    status="PENDING",
                    created_at=now,
                    updated_at=now,
                )
            )
            await db.commit()

        return Order(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.SUBMITTED,  # queued for the bridge -- not yet acked by MT5
            submitted_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            price=request.price,
            stop_price=request.stop_price,
            strategy_instance_id=request.strategy_instance_id,
            tag=request.tag,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        from sqlalchemy import select

        from xillion.db.models import MT5PendingOrder

        async with self._factory() as db:
            result = await db.execute(
                select(MT5PendingOrder).where(MT5PendingOrder.client_order_id == broker_order_id)
            )
            row = result.scalar_one_or_none()
            if row is None or row.status in ("FILLED", "REJECTED", "CANCELLED"):
                return False
            row.status = "CANCEL_REQUESTED"
            row.updated_at = datetime.now(UTC).isoformat()
            await db.commit()
        return True

    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        raise NotImplementedError(
            "MT5 Funding Pips: modify not yet wired through the bridge -- cancel and re-place"
        )

    async def get_order(self, broker_order_id: str) -> Order:
        row = await self._get_pending_order(broker_order_id)
        if row is None:
            raise ValueError(f"no such order: {broker_order_id}")
        return self._row_to_order(row)

    async def get_orders_today(self) -> list[Order]:
        from sqlalchemy import select

        from xillion.db.models import MT5PendingOrder

        today = datetime.now(UTC).date().isoformat()
        async with self._factory() as db:
            result = await db.execute(
                select(MT5PendingOrder).where(
                    MT5PendingOrder.broker_connection_name == self._connection_name,
                    MT5PendingOrder.created_at >= today,
                )
            )
            rows = result.scalars().all()
        return [self._row_to_order(r) for r in rows]

    # ── Market data ────────────────────────────────────────────────────────────

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        self._subscribed.update(symbols)

    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        self._subscribed.difference_update(symbols)

    def tick_stream(self) -> AsyncIterator[Tick]:
        async def _gen():
            while True:
                yield await self._tick_queue.get()

        return _gen()

    async def order_event_stream(self) -> AsyncIterator[Order]:
        while True:
            yield await self._order_queue.get()

    async def get_history(self, symbol: str, timeframe: str, from_ts, to_ts) -> list[Bar]:
        raise NotImplementedError(
            "MT5 Funding Pips: no historical data source wired yet -- see module docstring"
        )

    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        from sqlalchemy import select

        from xillion.db.models import MT5BridgeTick

        async with self._factory() as db:
            result = await db.execute(
                select(MT5BridgeTick).where(MT5BridgeTick.symbol.in_(symbols))
            )
            rows = result.scalars().all()
        return {
            r.symbol: Tick(
                symbol=r.symbol,
                ltp=Decimal(r.ltp),
                ltt=datetime.fromisoformat(r.updated_at),
                bid=Decimal(r.bid) if r.bid else None,
                ask=Decimal(r.ask) if r.ask else None,
            )
            for r in rows
        }

    # ── Bridge-facing helpers (called by xillion/api/mt5_bridge.py, same
    #    process, not part of the Broker ABC) ────────────────────────────────

    def subscribed_symbols(self) -> list[str]:
        return sorted(self._subscribed)

    async def ingest_tick(self, tick: Tick) -> None:
        """Called by the /mt5-bridge/report handler for each price the
        bridge reports, so live/paper strategies see it immediately instead
        of waiting for their own next DB read."""
        if self._tick_queue.full():
            self._tick_queue.get_nowait()  # drop oldest -- same overflow policy as dhan.py
        await self._tick_queue.put(tick)

    async def ingest_order_update(self, order: Order) -> None:
        if self._order_queue.full():
            self._order_queue.get_nowait()
        await self._order_queue.put(order)

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _get_state(self) -> dict | None:
        from sqlalchemy import select

        from xillion.db.models import MT5BridgeState

        async with self._factory() as db:
            result = await db.execute(
                select(MT5BridgeState).where(
                    MT5BridgeState.broker_connection_name == self._connection_name
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "positions_json": row.positions_json,
            "margins_json": row.margins_json,
            "holdings_json": row.holdings_json,
            "updated_at": row.updated_at,
        }

    async def _get_pending_order(self, client_order_id: str):
        from sqlalchemy import select

        from xillion.db.models import MT5PendingOrder

        async with self._factory() as db:
            result = await db.execute(
                select(MT5PendingOrder).where(MT5PendingOrder.client_order_id == client_order_id)
            )
            return result.scalar_one_or_none()

    _STATUS_MAP = {
        "PENDING": OrderStatus.SUBMITTED,
        "ACKED": OrderStatus.SUBMITTED,
        "FILLED": OrderStatus.FILLED,
        "REJECTED": OrderStatus.REJECTED,
        "CANCEL_REQUESTED": OrderStatus.SUBMITTED,
        "CANCELLED": OrderStatus.CANCELLED,
    }

    def _row_to_order(self, row) -> Order:
        return Order(
            client_order_id=row.client_order_id,
            symbol=row.symbol,
            side=Side(row.side),
            quantity=_lots_to_quantity(Decimal(row.quantity)),
            order_type=row.order_type,  # type: ignore[arg-type]
            status=self._STATUS_MAP.get(row.status, OrderStatus.SUBMITTED),
            submitted_at=datetime.fromisoformat(row.created_at),
            updated_at=datetime.fromisoformat(row.updated_at),
            broker_order_id=row.mt5_ticket_id,
            price=Decimal(row.price) if row.price else None,
            stop_price=Decimal(row.stop_loss) if row.stop_loss else None,
            avg_fill_price=Decimal(row.avg_fill_price) if row.avg_fill_price else None,
            rejection_reason=row.error_message,
        )
