"""
Twelve Data live XAUUSD feed -- a data-only "broker" plugin for the Gold
Sweep-Reversal alert engine (docs/strategies/gold-xauusd-sweep-reversal.md).

Deliberately NOT the Funding Pips MT5 broker: this strategy runs in
alert-only mode for v1 (Telegram notification + manual taken/skipped
tracking, no order placement), so it needs a live price feed, not an
execution path -- no Wine, no MT5 terminal, no bridge. Registered as a
Broker plugin (not a HistoricalDataProvider) purely so it plugs into the
existing live-tick/alert-instance machinery
(subscribe_ticks -> MarketDataBus -> BarAggregator -> on_bar) with zero
changes to strategy_engine.py/instances.py -- see _try_connect_twelve_data
in xillion/main.py for how it gets registered at startup, mirroring
_try_connect_dhan/_try_connect_mt5.

Free tier: 800 requests/day, 8/min (twelvedata.com/pricing). Polls
/time_series for completed 5-min XAU/USD bars every
_POLL_INTERVAL_SECONDS (one symbol, well inside quota during the strategy's
6-hour trading window) and, when a new bar closes, replays it as four
synthetic ticks (open/high/low/close, correctly time-ordered within the
bucket) through the normal tick_stream() -> BarAggregator path. This reuses
BarAggregator's OHLC accumulation completely unmodified, and the resulting
bar matches Twelve Data's own OHLC exactly -- not an approximation
reconstructed from sparse polling.

No order execution, structurally -- every order method raises
NotImplementedError or returns empty, same "can't silently do the thing it
isn't supposed to do" guarantee the MCP server's missing order-placement
tool gives (see test_no_order_placement_tool_exists in
tests/unit/test_mcp_server.py). This is a read-only market-data feed, not
an account Rakesh holds.

Honest gap, not hidden: this feed is a different liquidity source than
Funding Pips' own MT5 print -- fine for alert-only v1 since no money moves
off it directly, but should be reconciled against the real MT5 feed before
any execution path is ever wired to this strategy. See the strategy doc's
Section 7.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import structlog

from xillion.core.broker_base import Broker, BrokerCapabilities
from xillion.core.events import Bar, Order, OrderRequest, Position, Tick

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.twelvedata.com"
_POLL_INTERVAL_SECONDS = 30
_TIMEFRAME_TO_INTERVAL = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "1d": "1day",
}
# XAUUSD as used elsewhere in this codebase -> Twelve Data's own symbol convention
_SYMBOL_MAP = {"XAUUSD": "XAU/USD"}


def _map_symbol(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol, symbol)


def _parse_bar(symbol: str, timeframe: str, row: dict) -> Bar:
    ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return Bar(
        symbol=symbol,
        timeframe=timeframe,
        ts=ts,
        open=Decimal(row["open"]),
        high=Decimal(row["high"]),
        low=Decimal(row["low"]),
        close=Decimal(row["close"]),
        # Twelve Data's FX/commodity time series carries no volume field
        # (retail FX/CFD data generally doesn't) -- 0, not faked.
        volume=int(row.get("volume") or 0),
    )


class TwelveDataBroker(Broker):
    name = "Twelve Data (Gold Feed)"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_websocket=False,
        supports_historical=True,
        supports_bracket_orders=False,
        supports_gtt_orders=False,
        supports_realised_pnl_query=False,
        supported_timeframes=["1m", "5m", "15m", "30m", "1h", "1d"],
        supported_exchanges=["FX"],
    )

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue()
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._last_bar_ts: dict[str, datetime] = {}
        self._connected = False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self, credentials: dict) -> None:
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Twelve Data broker needs an api_key (TWELVE_DATA_API_KEY)")
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=15.0)
        # Cheap liveness check -- a real quote call, not just "key is non-empty"
        try:
            resp = await self._client.get(
                f"{_BASE_URL}/quote", params={"symbol": "XAU/USD", "apikey": api_key}
            )
            data = resp.json()
        except Exception:
            await self._client.aclose()
            self._client = None
            raise
        if isinstance(data, dict) and data.get("status") == "error":
            await self._client.aclose()
            self._client = None
            raise RuntimeError(f"Twelve Data connect check failed: {data.get('message')}")
        self._connected = True

    async def disconnect(self) -> None:
        for task in self._poll_tasks.values():
            task.cancel()
        self._poll_tasks.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def healthcheck(self) -> bool:
        return self._connected and self._client is not None

    async def is_connected(self) -> bool:
        return self._connected

    # ── Account -- none; data-only feed ──────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        return []

    async def get_holdings(self) -> list[dict]:
        return []

    async def get_margins(self) -> dict:
        return {}

    # ── Orders -- structurally none. See module docstring. ───────────────────

    async def place_order(self, request: OrderRequest) -> Order:
        raise NotImplementedError(
            "Twelve Data (Gold Feed) is a data-only feed and places no orders -- "
            "Gold Sweep-Reversal runs in alert-only mode. See "
            "docs/strategies/gold-xauusd-sweep-reversal.md."
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        raise NotImplementedError("Twelve Data (Gold Feed) places no orders.")

    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        raise NotImplementedError("Twelve Data (Gold Feed) places no orders.")

    async def get_order(self, broker_order_id: str) -> Order:
        raise NotImplementedError("Twelve Data (Gold Feed) places no orders.")

    async def get_orders_today(self) -> list[Order]:
        return []

    # ── Market data ────────────────────────────────────────────────────────

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        for symbol in symbols:
            if symbol in self._poll_tasks:
                continue
            self._poll_tasks[symbol] = asyncio.create_task(self._poll_loop(symbol))
            logger.info("twelve_data: subscribed", symbol=symbol)

    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        for symbol in symbols:
            task = self._poll_tasks.pop(symbol, None)
            if task is not None:
                task.cancel()

    async def _poll_loop(self, symbol: str) -> None:
        td_symbol = _map_symbol(symbol)
        while True:
            try:
                await self._poll_once(symbol, td_symbol)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("twelve_data: poll failed", symbol=symbol, error=str(exc))
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def _poll_once(self, symbol: str, td_symbol: str) -> None:
        assert self._client is not None
        resp = await self._client.get(
            f"{_BASE_URL}/time_series",
            params={
                "symbol": td_symbol,
                "interval": "5min",
                "outputsize": 2,
                "timezone": "UTC",
                "apikey": self._api_key,
            },
        )
        data = resp.json()
        values = data.get("values") if isinstance(data, dict) else None
        if not values:
            logger.warning("twelve_data: no values in response", symbol=symbol, response=data)
            return

        # Twelve Data returns newest-first; the newest row can still be the
        # currently-forming bar, not a closed one -- only replay values[1]
        # (the most recently *closed* 5-min bar) so a bar is never emitted
        # before its close is final.
        if len(values) < 2:
            return
        closed = values[1]
        bar_ts = datetime.strptime(closed["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        if self._last_bar_ts.get(symbol) == bar_ts:
            return  # already replayed this bar

        o, h, low, c = (Decimal(closed[k]) for k in ("open", "high", "low", "close"))
        # Four synthetic ticks spanning the bucket, correctly time-ordered, so
        # BarAggregator's running high/low and open-by-first/close-by-last
        # reconstruct this exact OHLC rather than an approximation.
        for offset, price in ((0, o), (100, h), (200, low), (299, c)):
            await self._tick_queue.put(
                Tick(symbol=symbol, ltp=price, ltt=bar_ts + timedelta(seconds=offset))
            )
        # BarAggregator only finalizes/publishes a bucket once it sees a
        # tick belonging to the *next* one (correct for a real streaming
        # feed -- a later tick proves the earlier bucket is truly done).
        # All 4 ticks above are backdated into bar_ts's own window for OHLC
        # accuracy, so without this, the bar just built would sit
        # unpublished until the *next* poll cycle's ticks arrive -- a full
        # bar late, every time. A tick stamped with real "now" (always in
        # a later bucket, since Twelve Data only reports a bar as closed
        # after its 5 minutes have fully elapsed) forces the just-built bar
        # to publish immediately, and doubles as a reasonable seed for the
        # new bucket now forming. Found 2026-09-21: verified via a live
        # WebSocket listen that ticks were flowing end-to-end but no bar
        # ever reached on_bar -- this was why.
        await self._tick_queue.put(Tick(symbol=symbol, ltp=c, ltt=datetime.now(UTC)))
        self._last_bar_ts[symbol] = bar_ts

    async def tick_stream(self) -> AsyncIterator[Tick]:
        while True:
            tick = await self._tick_queue.get()
            yield tick

    async def order_event_stream(self) -> AsyncIterator[Order]:
        return
        yield  # pragma: no cover -- never placed, never updated; empty generator

    async def get_history(
        self,
        symbol: str,
        timeframe: str,
        from_ts,
        to_ts,
    ) -> list[Bar]:
        interval = _TIMEFRAME_TO_INTERVAL.get(timeframe)
        if interval is None:
            raise ValueError(f"Twelve Data (Gold Feed): unsupported timeframe {timeframe!r}")
        assert self._client is not None
        resp = await self._client.get(
            f"{_BASE_URL}/time_series",
            params={
                "symbol": _map_symbol(symbol),
                "interval": interval,
                "start_date": from_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": to_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "timezone": "UTC",
                "apikey": self._api_key,
            },
        )
        data = resp.json()
        values = data.get("values") if isinstance(data, dict) else None
        if not values:
            return []
        return [_parse_bar(symbol, timeframe, row) for row in reversed(values)]

    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        assert self._client is not None
        out: dict[str, Tick] = {}
        for symbol in symbols:
            resp = await self._client.get(
                f"{_BASE_URL}/quote",
                params={"symbol": _map_symbol(symbol), "apikey": self._api_key},
            )
            data = resp.json()
            if not isinstance(data, dict) or "close" not in data:
                continue
            out[symbol] = Tick(symbol=symbol, ltp=Decimal(data["close"]), ltt=datetime.now(UTC))
        return out
